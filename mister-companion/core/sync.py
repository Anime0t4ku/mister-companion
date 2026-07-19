"""RomM ↔ MiSTer sync engine.

Two-phase design:
  1. plan_sync(...)  → walks RomM (subscribed platforms + collections) and the
     MiSTer /media/fat/games/<Core>/ folders. Returns a SyncPlan bucketing each
     file into an ActionKind.
  2. execute_sync(plan, ...) → performs the decisions the UI already resolved.

**Manifest-scoped orphans.** ``plan_sync`` takes a manifest of files this tool
has previously placed on the MiSTer (keyed by remote path). Only manifested
files can be ORPHAN candidates — pre-existing user content is invisible to the
engine. ``execute_sync`` mutates the manifest in place. Callers persist it.

**Manifest v2 shape.** Entries are dicts ``{mtime: float, size: int, hash: str}``
capturing the last-known state of each placed file. Enables two robustness
gains: (a) detect intentional RomM deletions — if MiSTer file is unchanged
since manifest AND RomM has no counterpart, the user deleted it there; don't
re-upload. (b) short-circuit no-op reconciliations — if MiSTer is unchanged
and RomM size still matches, skip regardless of ``updated_at`` drift.
Legacy ``True`` values from older manifests are treated as "we own this but
lack details" (falls back to weaker checks).

**Read-only subscriptions.** Platforms/collections in the ``readonly_*_ids``
sets never generate upload actions — RomM is treated as canonical, MiSTer is
a receive-only mirror.

**Newest-wins for saves/states.** When both sides have a file, compare
content hash first (RomM ``content_hash`` MD5 vs MiSTer ``md5sum`` over SSH);
if hashes match → skip. If they differ, compare timestamps (``updated_at`` vs
``st_mtime``) and auto-pick the newer side. For hashless states with sizes
matching, an optional streaming byte-hash tie-breaker fetches the RomM asset
and hashes it locally before deciding to transfer. Prompt only when truly
ambiguous.

Kinds:
  ROMs   :  download / overwrite / skip / orphan
  Saves  :  save_download / save_upload / save_conflict / save_skip
  States :  state_download / state_upload / state_conflict / state_skip
"""
from __future__ import annotations

import hashlib
import posixpath
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from core.mister_cores import core_folder_for_slug, saves_dir, states_dir

ActionKind = str

# Timestamps within this window are treated as "equal" (clock skew / rounding).
_MTIME_TOLERANCE_SECONDS = 5

# UI-side default resolutions (each entry may be overridden per-file):
RESOLVE_ROMM = "romm"        # keep RomM version (download over local)
RESOLVE_MISTER = "mister"    # keep MiSTer version (skip)
RESOLVE_DELETE = "delete"    # delete the orphan on MiSTer
RESOLVE_KEEP = "keep"        # keep the orphan on MiSTer (do nothing)


@dataclass
class SyncAction:
    kind: ActionKind
    core_folder: str
    remote_path: str                 # on-MiSTer path
    file_name: str
    size_romm: int = 0
    size_mister: int = 0
    sha1_romm: str = ""
    rom_id: int | None = None        # None for ROM orphans
    rom_name: str = ""
    resolution: str = ""             # UI fills for overwrite / orphan / *_conflict
    # save/state extras
    asset_id: int | None = None      # RomM save/state id (None for pure MiSTer→RomM uploads)
    asset_emulator: str = ""         # RomM emulator tag (e.g. "mister")
    asset_slot: str = ""             # save slot (states have no slot)
    asset_updated_at: str = ""       # RomM updated_at ISO — used to sync MiSTer mtime after transfer


@dataclass
class UnsupportedSubscription:
    kind: str                        # "platform" | "collection"
    id: int
    name: str
    slug: str
    rom_count: int


@dataclass
class SyncPlan:
    actions: list[SyncAction] = field(default_factory=list)
    unsupported: list[UnsupportedSubscription] = field(default_factory=list)
    # RomM saves/states tagged for another emulator (fceux, retroarch, dolphin…)
    # — not MiSTer-format, silently filtered out of the download plan.
    filtered_incompatible: int = 0

    def by_kind(self, kind: ActionKind) -> list[SyncAction]:
        return [a for a in self.actions if a.kind == kind]

    def totals(self) -> dict[str, int]:
        return {
            "download": len(self.by_kind("download")),
            "overwrite": len(self.by_kind("overwrite")),
            "skip": len(self.by_kind("skip")),
            "orphan": len(self.by_kind("orphan")),
            "save_download": len(self.by_kind("save_download")),
            "save_upload": len(self.by_kind("save_upload")),
            "save_conflict": len(self.by_kind("save_conflict")),
            "save_skip": len(self.by_kind("save_skip")),
            "state_download": len(self.by_kind("state_download")),
            "state_upload": len(self.by_kind("state_upload")),
            "state_conflict": len(self.by_kind("state_conflict")),
            "state_skip": len(self.by_kind("state_skip")),
            "unsupported": len(self.unsupported),
            "bytes_to_download": sum(
                a.size_romm for a in self.actions if a.kind in ("download", "overwrite")
            ),
        }


# ── planning ────────────────────────────────────────────────────────────────

def _rom_file_name(rom: dict) -> str:
    """Best-effort file name for a ROM record.

    Single-file ROMs: ``fs_name`` is the file. Multi-file ROMs (folder-based,
    e.g. Wii U Loadiine, multi-disc bin/cue): ``fs_name`` is the folder — those
    aren't handled in Phase A.
    """
    return rom.get("fs_name") or rom.get("file_name") or ""


def _rom_is_folder(rom: dict) -> bool:
    """RomM sets multi_file / has_multiple_files for folder-based ROMs."""
    if rom.get("multi_file"):
        return True
    files = rom.get("files") or []
    return len(files) > 1


def _basename(fs_name: str) -> str:
    """ROM's basename without extension — matches how MiSTer names save files."""
    dot = fs_name.rfind(".")
    return fs_name[:dot] if dot > 0 else fs_name


def _parse_iso_to_unix(iso: str) -> float | None:
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.timestamp()
    except Exception:
        return None


def _remote_md5(ssh_client, remote_path: str) -> str | None:
    """Run ``md5sum <path>`` on the MiSTer, return the hex digest or None."""
    if ssh_client is None:
        return None
    try:
        quoted = "'" + remote_path.replace("'", "'\\''") + "'"
        _, stdout, _ = ssh_client.exec_command(f"md5sum {quoted} 2>/dev/null")
        raw = stdout.read().decode("utf-8", errors="ignore").strip()
        return raw.split()[0] if raw else None
    except Exception:
        return None


def _romm_asset_md5(client, asset_kind: str, asset_id: int) -> str | None:
    """Stream a RomM save/state and compute its MD5 client-side.

    Used as a definitive tie-breaker for hashless assets (RomM's states table
    has no content_hash column) when size + mtime look ambiguous. One transfer
    per uncertainty — the cost buys us "identical → skip" over "wasted upload/download".
    """
    try:
        resp = client.stream_asset(asset_kind, asset_id)
        h = hashlib.md5()
        try:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                if chunk:
                    h.update(chunk)
        finally:
            resp.close()
        return h.hexdigest()
    except Exception:
        return None


def _sftp_mkdir_p(sftp, path: str) -> None:
    """SFTP equivalent of ``mkdir -p`` — handles absolute paths correctly.

    A naive ``path.split('/')`` produces an empty first element for absolute
    paths, and a `cur = cur + '/' + p if cur else p` accumulator loses the
    leading slash on the first non-empty segment — files then land under the
    SSH session's home directory instead of the filesystem root.
    """
    if not path or path == "/":
        return
    absolute = path.startswith("/")
    parts = [p for p in path.split("/") if p]
    cur = "" if not absolute else ""
    for p in parts:
        cur = f"{cur}/{p}" if absolute else (f"{cur}/{p}" if cur else p)
        try:
            sftp.stat(cur)
        except (FileNotFoundError, IOError):
            sftp.mkdir(cur)


def _manifest_entry_matches(entry, current_mtime, current_size) -> bool:
    """True if the manifest entry indicates the MiSTer file is unchanged since
    last sync. Requires v2 dict entries with concrete mtime+size; legacy ``True``
    entries return False (we don't know the previous state)."""
    if not isinstance(entry, dict):
        return False
    m_prev = entry.get("mtime")
    s_prev = entry.get("size")
    if m_prev is None or s_prev is None or current_mtime is None or current_size is None:
        return False
    return abs(float(m_prev) - float(current_mtime)) <= _MTIME_TOLERANCE_SECONDS and int(s_prev) == int(current_size)


def _asset_is_mister_compatible(asset: dict) -> bool:
    """RomM save/state format compatibility gate for MiSTer.

    Save states are strongly emulator-specific (a fceux/retroarch/dolphin state
    can't be loaded by a MiSTer core). SRAM saves are more portable in theory,
    but we treat them the same for safety: only assets tagged for MiSTer (or
    legacy/blank-tagged) are pulled down. Uploads FROM MiSTer are always tagged
    ``emulator="mister"``, so this filter is naturally consistent.
    """
    emu = (asset.get("emulator") or "").strip().lower()
    return emu == "" or emu == "mister"


def _plan_asset_actions(
    client,
    rom: dict,
    core: str,
    asset_kind: str,             # "save" or "state"
    remote_dir: str,
    plan: "SyncPlan",
    remote_entries: dict[str, int],  # MiSTer basename-matched files: fname → size
    sftp,
    ssh_client=None,
    parent_rom_managed: bool = True,
    readonly: bool = False,
    manifest: dict | None = None,
    mister_root: str = "/media/fat",
    upload_claimed: dict[str, tuple[int, str]] | None = None,  # remote_path → (rom_id, rom_name)
    log: Callable[[str], None] | None = None,
) -> None:
    """Reconcile one ROM's saves (or states) between RomM and MiSTer.

    Newest-wins logic when a file exists on both sides:
      1. If MD5 matches → skip
      2. Else if MiSTer mtime is newer (beyond tolerance) → auto-upload
      3. Else if RomM updated_at is newer → auto-download
      4. Else → conflict prompt (user picks)
    """
    rom_base = _basename(rom.get("fs_name") or "")
    if not rom_base:
        return
    getter = client.get_saves if asset_kind == "save" else client.get_states
    try:
        remote_assets = getter(rom["id"])
    except Exception:
        return

    matched_remote_names: set[str] = set()

    for asset in remote_assets or []:
        fname = asset.get("file_name") or ""
        if not fname:
            continue
        if not _asset_is_mister_compatible(asset):
            plan.filtered_incompatible += 1
            matched_remote_names.add(fname)
            continue
        matched_remote_names.add(fname)
        remote_path = f"{remote_dir}/{fname}"
        r_size = int(asset.get("file_size_bytes") or 0)
        m_size = remote_entries.get(fname)

        common = dict(
            core_folder=core, remote_path=remote_path, file_name=fname,
            rom_id=rom["id"],
            rom_name=rom.get("name") or rom.get("fs_name") or "",
            asset_id=asset.get("id"),
            asset_emulator=str(asset.get("emulator") or ""),
            asset_slot=str(asset.get("slot") or ""),
            asset_updated_at=str(asset.get("updated_at") or ""),
        )

        if m_size is None:
            plan.actions.append(SyncAction(kind=f"{asset_kind}_download",
                                           size_romm=r_size, **common))
            continue

        # Both sides have a file — decide by, in order:
        #   1. content hash match → skip
        #   2. manifest says MiSTer unchanged + RomM size unchanged → skip
        #   3. size + mtime identity → skip
        #   4. streaming byte-hash (hashless states) → skip if equal
        #   5. mtime direction → upload/download
        #   6. hash-less + size match + no timestamps → last-ditch skip
        #   7. otherwise → conflict prompt
        r_hash = str(asset.get("content_hash") or "").lower()
        m_hash = _remote_md5(ssh_client, remote_path)
        if r_hash and m_hash and r_hash == m_hash:
            plan.actions.append(SyncAction(kind=f"{asset_kind}_skip",
                                           size_romm=r_size, size_mister=m_size, **common))
            continue

        r_ts = _parse_iso_to_unix(asset.get("updated_at") or "")
        try:
            m_ts = float(sftp.stat(remote_path).st_mtime)
        except Exception:
            m_ts = None

        sizes_match = bool(r_size and m_size == r_size)
        both_ts = r_ts is not None and m_ts is not None

        # 2. Manifest metadata: if MiSTer file is unchanged since last sync
        # AND sizes still match, skip. Kills metadata-only bump re-downloads.
        if manifest is not None and sizes_match:
            entry = manifest.get(_relpath_key(remote_path, mister_root))
            if _manifest_entry_matches(entry, m_ts, m_size):
                plan.actions.append(SyncAction(kind=f"{asset_kind}_skip",
                                               size_romm=r_size, size_mister=m_size, **common))
                continue

        # 3. size + mtime identity (post sftp.utime convergence).
        if sizes_match and both_ts and abs(m_ts - r_ts) <= _MTIME_TOLERANCE_SECONDS:
            plan.actions.append(SyncAction(kind=f"{asset_kind}_skip",
                                           size_romm=r_size, size_mister=m_size, **common))
            continue

        # 4. Streaming byte-hash tie-breaker for hashless assets (states) —
        # only when sizes match. Costs one MB-scale fetch per uncertain case.
        if sizes_match and not r_hash and m_hash:
            streamed = _romm_asset_md5(client, asset_kind, asset.get("id"))
            if streamed and streamed == m_hash:
                plan.actions.append(SyncAction(kind=f"{asset_kind}_skip",
                                               size_romm=r_size, size_mister=m_size, **common))
                continue

        # 5. Timestamps disagree → follow direction.
        if both_ts:
            delta = m_ts - r_ts
            if delta > _MTIME_TOLERANCE_SECONDS:
                if readonly:
                    if log:
                        log(f"  read-only: MiSTer newer {asset_kind} '{fname}' not uploaded")
                    plan.actions.append(SyncAction(kind=f"{asset_kind}_skip",
                                                   size_romm=r_size, size_mister=m_size, **common))
                else:
                    plan.actions.append(SyncAction(kind=f"{asset_kind}_upload",
                                                   size_romm=r_size, size_mister=m_size, **common))
                continue
            if delta < -_MTIME_TOLERANCE_SECONDS:
                plan.actions.append(SyncAction(kind=f"{asset_kind}_download",
                                               size_romm=r_size, size_mister=m_size, **common))
                continue

        # 6. Timestamps unusable AND no hashes: size-only skip (weakest signal,
        # only used when we truly can't check anything else).
        if not both_ts and sizes_match and not r_hash and not m_hash:
            plan.actions.append(SyncAction(kind=f"{asset_kind}_skip",
                                           size_romm=r_size, size_mister=m_size, **common))
            continue

        # 7. Truly ambiguous → ask the user.
        plan.actions.append(SyncAction(kind=f"{asset_kind}_conflict",
                                       size_romm=r_size, size_mister=m_size, **common))

    # MiSTer-side files with no RomM counterpart → upload (tagged emulator=mister).
    # Gates:
    #  - parent_rom_managed: don't vacuum saves for pre-existing unmanaged ROMs.
    #  - readonly: subscription treats RomM as canonical, never uploads.
    #  - manifest deletion detection: if MiSTer file is UNCHANGED since last
    #    manifest snapshot and RomM has no counterpart, the user deleted it
    #    from RomM on purpose — don't re-upload it.
    if not parent_rom_managed or readonly:
        return
    for fname, sz in remote_entries.items():
        if fname in matched_remote_names or not fname.startswith(rom_base):
            continue
        rest = fname[len(rom_base):]
        if rest and not (rest.startswith(".") or rest.startswith("_")):
            continue  # e.g. "Mario" would match "Mario 2.sav" — reject
        remote_path = f"{remote_dir}/{fname}"
        # Intentional-deletion gate
        if manifest is not None:
            key = _relpath_key(remote_path, mister_root)
            entry = manifest.get(key)
            if isinstance(entry, dict):
                try:
                    cur_mt = float(sftp.stat(remote_path).st_mtime)
                except Exception:
                    cur_mt = None
                if _manifest_entry_matches(entry, cur_mt, sz):
                    if log:
                        log(f"  skip re-upload {asset_kind} '{fname}' — MiSTer unchanged, RomM copy was deleted intentionally")
                    continue
        # Duplicate-basename guard: if two RomM ROMs share the same basename
        # (e.g. duplicate imports, dupes across editions), the first ROM to reach
        # this point owns the upload. Anything else attempting the same file is
        # skipped + logged, so we never silently attribute one save to two ROMs.
        if upload_claimed is not None:
            prior = upload_claimed.get(remote_path)
            if prior is not None:
                if log:
                    log(
                        f"  ! ambiguous {asset_kind} '{fname}' — attributed to "
                        f"'{prior[1]}' (rom #{prior[0]}), skipping conflicting "
                        f"claim by '{rom.get('name') or rom.get('fs_name')}' "
                        f"(rom #{rom['id']})"
                    )
                continue
            upload_claimed[remote_path] = (rom["id"], rom.get("name") or rom.get("fs_name") or "")
        slot = ""
        if asset_kind == "save" and rest.startswith("_"):
            middle = rest.lstrip("_").split(".", 1)[0]
            if middle.isdigit():
                slot = middle
        plan.actions.append(SyncAction(
            kind=f"{asset_kind}_upload",
            core_folder=core,
            remote_path=remote_path,
            file_name=fname, size_mister=int(sz),
            rom_id=rom["id"],
            rom_name=rom.get("name") or rom.get("fs_name") or "",
            asset_emulator="mister", asset_slot=slot,
        ))


def _relpath_key(remote_path: str, mister_root: str) -> str:
    """Compact manifest key: strip the mister_root prefix so hosts survive remount."""
    if remote_path.startswith(mister_root + "/"):
        return remote_path[len(mister_root) + 1:]
    return remote_path


def plan_sync(
    client,
    *,
    subscribed_platform_ids: list[int],
    subscribed_collection_ids: list[int],
    readonly_platform_ids: list[int] | None = None,
    readonly_collection_ids: list[int] | None = None,
    sftp,
    ssh_client=None,
    manifest: dict | None = None,
    mister_root: str = "/media/fat",
    include_assets: bool = False,
    progress: Callable[[str], None] | None = None,
) -> SyncPlan:
    """Compute a SyncPlan against a live RomM + live SFTP session.

    ``mister_root`` is the SD/USB mount base (default /media/fat). Games live at
    ``<mister_root>/games/<Core>/``; saves/states at ``<mister_root>/{saves,savestates}/<Core>/``.
    Enable ``include_assets`` to also reconcile saves and states per ROM.

    ``manifest`` (per-MiSTer, keyed by ``<subpath>`` under ``mister_root``) records
    every file this tool has placed on the device. Orphan detection ONLY considers
    files present in the manifest — pre-existing user content is left alone.
    ``ssh_client`` (paramiko SSHClient) is used for remote ``md5sum`` during
    save/state hash comparison; if None, hash-check is skipped.
    """
    games_root = f"{mister_root}/games"
    manifest = manifest or {}
    readonly_platform_ids = set(readonly_platform_ids or [])
    readonly_collection_ids = set(readonly_collection_ids or [])
    # Track which cores derive from at least one read-only subscription. A core
    # in this set will suppress uploads (readonly wins if any source subscription
    # is readonly — safer default).
    readonly_cores: set[str] = set()
    plan = SyncPlan()
    log = progress or (lambda _s: None)

    # ── build RomM-side wishlist (rom + core_folder), grouped by core ───────
    wanted_per_core: dict[str, list[dict]] = {}
    covered_cores: set[str] = set()

    platforms = {p["id"]: p for p in client.get_platforms()}

    for pid in subscribed_platform_ids:
        p = platforms.get(pid)
        if not p:
            log(f"platform #{pid} no longer exists on RomM — skipping")
            continue
        core = core_folder_for_slug(p.get("slug"))
        if core is None:
            plan.unsupported.append(
                UnsupportedSubscription("platform", pid, p.get("name", ""), p.get("slug", ""),
                                        int(p.get("rom_count") or 0))
            )
            continue
        covered_cores.add(core)
        if pid in readonly_platform_ids:
            readonly_cores.add(core)
        log(f"listing RomM platform: {p.get('name')} ({p.get('rom_count', '?')})")
        roms = client.get_roms(platform_id=pid)
        for rom in roms:
            wanted_per_core.setdefault(core, []).append(rom)

    # Collections can span platforms — resolve per-ROM
    for cid in subscribed_collection_ids:
        log(f"listing RomM collection #{cid}")
        roms = client.get_roms(collection_id=cid)
        for rom in roms:
            slug = (rom.get("platform_fs_slug") or rom.get("platform_slug") or "").lower()
            core = core_folder_for_slug(slug)
            if core is None:
                if not any(u.slug == slug and u.kind == "collection" and u.id == cid for u in plan.unsupported):
                    plan.unsupported.append(
                        UnsupportedSubscription("collection", cid, rom.get("platform_name") or slug, slug, 0)
                    )
                continue
            covered_cores.add(core)
            if cid in readonly_collection_ids:
                readonly_cores.add(core)
            wanted_per_core.setdefault(core, []).append(rom)

    # ── walk MiSTer /media/fat/games/<Core>/ for each core we care about ────
    remote_per_core: dict[str, dict[str, int]] = {}
    for core in sorted(covered_cores):
        path = f"{games_root}/{core}"
        entries: dict[str, int] = {}
        try:
            for attr in sftp.listdir_attr(path):
                # skip subdirs (multi-file / folder ROMs handled Phase B)
                if attr.st_mode is not None and attr.st_mode & 0o170000 == 0o040000:
                    continue
                entries[attr.filename] = int(attr.st_size or 0)
        except (FileNotFoundError, IOError) as exc:
            # MiSTer may not have the folder yet — that's fine, we'll create it
            log(f"MiSTer folder {path} is empty or missing ({exc.__class__.__name__})")
        remote_per_core[core] = entries

    # ── produce actions ────────────────────────────────────────────────────
    for core, roms in wanted_per_core.items():
        remote_files = remote_per_core.get(core, {})
        seen_files: set[str] = set()

        for rom in roms:
            if _rom_is_folder(rom):
                # Phase A: skip folder-based ROMs. Log once.
                log(f"skip (multi-file): {rom.get('name') or rom.get('fs_name')}")
                continue
            fname = _rom_file_name(rom)
            if not fname:
                continue
            if fname in seen_files:
                # duplicated across platform + collection subscriptions — dedupe
                continue
            seen_files.add(fname)

            size_romm = int(rom.get("fs_size_bytes") or 0)
            # sha1: prefer files[0].sha1_hash, fall back to top-level if present
            sha1 = ""
            files = rom.get("files") or []
            if files:
                sha1 = str(files[0].get("sha1_hash") or "")
            sha1 = sha1 or str(rom.get("sha1_hash") or "")

            remote_size = remote_files.get(fname)
            remote_path = f"{games_root}/{core}/{fname}"

            if remote_size is None:
                plan.actions.append(SyncAction(
                    kind="download",
                    core_folder=core,
                    remote_path=remote_path,
                    file_name=fname,
                    size_romm=size_romm,
                    sha1_romm=sha1,
                    rom_id=rom.get("id"),
                    rom_name=rom.get("name") or fname,
                ))
            elif size_romm and remote_size == size_romm:
                # size match — treat as identical (Phase A: skip remote sha1sum RPC).
                plan.actions.append(SyncAction(
                    kind="skip",
                    core_folder=core,
                    remote_path=remote_path,
                    file_name=fname,
                    size_romm=size_romm,
                    size_mister=remote_size,
                    sha1_romm=sha1,
                    rom_id=rom.get("id"),
                    rom_name=rom.get("name") or fname,
                ))
            else:
                # size mismatch (or RomM size unknown) — UI must ask
                plan.actions.append(SyncAction(
                    kind="overwrite",
                    core_folder=core,
                    remote_path=remote_path,
                    file_name=fname,
                    size_romm=size_romm,
                    size_mister=remote_size,
                    sha1_romm=sha1,
                    rom_id=rom.get("id"),
                    rom_name=rom.get("name") or fname,
                ))

        # Files on MiSTer not in the wishlist COULD be orphans — but only if
        # this tool placed them there (manifest-scoped). Pre-existing files the
        # user built up over years are invisible to orphan detection.
        wanted_names = {_rom_file_name(r) for r in roms if not _rom_is_folder(r)}
        for fname, rsize in remote_files.items():
            if fname in wanted_names:
                continue
            remote_path = f"{games_root}/{core}/{fname}"
            if _relpath_key(remote_path, mister_root) not in manifest:
                continue  # pre-existing user content — leave alone
            plan.actions.append(SyncAction(
                kind="orphan",
                core_folder=core,
                remote_path=remote_path,
                file_name=fname,
                size_mister=int(rsize),
            ))

    # Compute the set of ROM paths this run will consider "managed" — either
    # already in the manifest OR being touched by a download/skip/overwrite
    # action this sync. Used to gate save/state uploads: saves for a pre-existing
    # unmanaged ROM must not be silently vacuumed into RomM.
    managed_rom_paths: set[str] = set(manifest.keys())
    for a in plan.actions:
        if a.kind in ("download", "skip", "overwrite"):
            managed_rom_paths.add(_relpath_key(a.remote_path, mister_root))

    # ── save/state reconciliation (opt-in) ─────────────────────────────
    # Track upload attributions across all ROMs so duplicate-basename ROMs
    # don't both "claim" the same MiSTer file. Keyed by remote_path per asset kind.
    save_claims: dict[str, tuple[int, str]] = {}
    state_claims: dict[str, tuple[int, str]] = {}
    if include_assets:
        # Walk each subscribed ROM once; skip folder-ROMs (Phase A).
        # Cache per-slug MiSTer directory listings so we don't re-list per rom.
        saves_listing: dict[str, dict[str, int]] = {}
        states_listing: dict[str, dict[str, int]] = {}

        def _listdir_cached(cache: dict, path: str) -> dict[str, int]:
            if path in cache:
                return cache[path]
            entries: dict[str, int] = {}
            try:
                for attr in sftp.listdir_attr(path):
                    if attr.st_mode and attr.st_mode & 0o170000 == 0o040000:
                        continue
                    entries[attr.filename] = int(attr.st_size or 0)
            except (FileNotFoundError, IOError):
                pass
            cache[path] = entries
            return entries

        for core, roms in wanted_per_core.items():
            # locate a matching slug just so we can derive save/state dirs
            slug_for_core = None
            for pid in subscribed_platform_ids:
                p = platforms.get(pid)
                if p and core_folder_for_slug(p.get("slug")) == core:
                    slug_for_core = p.get("slug"); break
            # (collections have per-rom slugs, so also try from any rom)
            if not slug_for_core and roms:
                slug_for_core = (roms[0].get("platform_fs_slug")
                                 or roms[0].get("platform_slug") or "")
            sdir = saves_dir(slug_for_core or "", root=mister_root)
            tdir = states_dir(slug_for_core or "", root=mister_root)
            if not sdir or not tdir:
                continue
            s_entries = _listdir_cached(saves_listing, sdir)
            t_entries = _listdir_cached(states_listing, tdir)

            # Only consider entries matching the ROMs' basenames in this core
            # (avoids uploading orphaned MiSTer saves for unsubscribed ROMs).
            for rom in roms:
                if _rom_is_folder(rom):
                    continue
                rom_base = _basename(rom.get("fs_name") or "")
                if not rom_base:
                    continue
                s_for_rom = {n: sz for n, sz in s_entries.items()
                             if n == rom_base or n.startswith(rom_base + ".") or n.startswith(rom_base + "_")}
                t_for_rom = {n: sz for n, sz in t_entries.items()
                             if n == rom_base or n.startswith(rom_base + ".") or n.startswith(rom_base + "_")}
                rom_key = _relpath_key(f"{games_root}/{core}/{rom.get('fs_name') or ''}", mister_root)
                parent_managed = rom_key in managed_rom_paths
                core_readonly = core in readonly_cores
                _plan_asset_actions(client, rom, core, "save",  sdir, plan, s_for_rom,
                                    sftp=sftp, ssh_client=ssh_client,
                                    parent_rom_managed=parent_managed,
                                    readonly=core_readonly,
                                    manifest=manifest, mister_root=mister_root,
                                    upload_claimed=save_claims, log=log)
                _plan_asset_actions(client, rom, core, "state", tdir, plan, t_for_rom,
                                    sftp=sftp, ssh_client=ssh_client,
                                    parent_rom_managed=parent_managed,
                                    readonly=core_readonly,
                                    manifest=manifest, mister_root=mister_root,
                                    upload_claimed=state_claims, log=log)

    return plan


# ── execution ──────────────────────────────────────────────────────────────

def download_and_push(
    client,
    sftp,
    rom_id: int,
    file_name: str,
    remote_path: str,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """Stream one RomM ROM directly into an SFTP file on the MiSTer.

    Returns the bytes written. ``progress`` (if given) is called with
    (bytes_written, total_bytes_or_zero) after each chunk.
    """
    _sftp_mkdir_p(sftp, posixpath.dirname(remote_path))

    written = 0
    resp = client.stream_rom(rom_id, file_name)
    total = int(resp.headers.get("Content-Length") or 0)
    tmp = remote_path + ".part"
    try:
        with sftp.open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                written += len(chunk)
                if progress:
                    progress(written, total)
        sftp.posix_rename(tmp, remote_path) if hasattr(sftp, "posix_rename") else sftp.rename(tmp, remote_path)
    finally:
        resp.close()
    return written


def _sync_mtime_to_updated_at(sftp, remote_path: str, updated_at_iso: str) -> None:
    """After any transfer, force MiSTer file mtime to match RomM's updated_at.

    This lets the planner recognise "same content" via size+mtime identity, which
    matters for states (RomM's states schema has no content_hash column).
    """
    ts = _parse_iso_to_unix(updated_at_iso)
    if ts is None:
        return
    try:
        sftp.utime(remote_path, (ts, ts))
    except Exception:
        pass  # non-fatal — worst case is a redundant sync next round


def _download_asset(client, sftp, asset_kind: str, action: SyncAction) -> None:
    """Stream a RomM save/state into an SFTP file (with mkdir -p)."""
    _sftp_mkdir_p(sftp, posixpath.dirname(action.remote_path))
    resp = client.stream_asset(asset_kind, action.asset_id)
    tmp = action.remote_path + ".part"
    try:
        with sftp.open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                if chunk:
                    f.write(chunk)
        rename = sftp.posix_rename if hasattr(sftp, "posix_rename") else sftp.rename
        rename(tmp, action.remote_path)
    finally:
        resp.close()
    _sync_mtime_to_updated_at(sftp, action.remote_path, action.asset_updated_at)


def _upload_asset(client, sftp, asset_kind: str, action: SyncAction) -> None:
    """Read a MiSTer save/state via SFTP, POST/PUT it to RomM.

    Then set the MiSTer file's mtime to the server-returned updated_at so the
    next sync recognises them as identical (essential for hash-less states).
    """
    with sftp.open(action.remote_path, "rb") as f:
        payload = f.read()
    if action.asset_id is not None:
        resp = client.update_asset(asset_kind, action.asset_id, action.file_name, payload)
    else:
        resp = client.upload_asset(
            asset_kind,
            action.rom_id,
            action.file_name,
            payload,
            emulator=action.asset_emulator or "mister",
            slot=action.asset_slot or None,
        )
    _sync_mtime_to_updated_at(sftp, action.remote_path, (resp or {}).get("updated_at", ""))


def download_firmware_for_platform(
    client,
    sftp,
    *,
    platform_id: int,
    platform_slug: str,
    mister_root: str = "/media/fat",
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Pull all firmware registered for a platform into ``<mister_root>/games/<Core>/bios/``.

    Explicit user action (not part of Sync Now). Skips files whose size on MiSTer
    already matches RomM; otherwise streams with a ``.part`` staging file +
    atomic rename. Returns counters. NOT tracked in the manifest — BIOS is
    set-once-and-forget by design; user re-runs this action to refresh.
    """
    log = progress or (lambda _s: None)
    stats = {"downloaded": 0, "skipped": 0, "errors": 0, "bytes": 0}
    core = core_folder_for_slug(platform_slug)
    if core is None:
        log(f"! platform '{platform_slug}' has no MiSTer core — skipping BIOS download")
        return stats
    remote_dir = f"{mister_root}/games/{core}/bios"

    try:
        firmware = client.get_firmware(platform_id) or []
    except Exception as exc:
        log(f"! fetch firmware list failed: {exc}")
        stats["errors"] += 1
        return stats
    if not firmware:
        log(f"no firmware in RomM for platform '{platform_slug}' (core: {core})")
        return stats

    log(f"↓ {len(firmware)} BIOS file(s) → {remote_dir}/")

    try:
        _sftp_mkdir_p(sftp, remote_dir)
    except Exception as exc:
        log(f"! mkdir {remote_dir} failed: {exc}")
        stats["errors"] += 1
        return stats

    for fw in firmware:
        fname = fw.get("file_name") or ""
        fid = fw.get("id")
        r_size = int(fw.get("file_size_bytes") or 0)
        if not fname or fid is None:
            continue
        remote_path = f"{remote_dir}/{fname}"

        # Skip if already present with matching size
        try:
            m_size = int(sftp.stat(remote_path).st_size or 0)
            if r_size and m_size == r_size:
                log(f"  = {fname} (unchanged, {r_size} B)")
                stats["skipped"] += 1
                continue
        except (FileNotFoundError, IOError):
            pass

        tmp = remote_path + ".part"
        try:
            resp = client.stream_firmware(fid, fname)
            try:
                with sftp.open(tmp, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=256 * 1024):
                        if chunk:
                            f.write(chunk)
            finally:
                resp.close()
            rename = sftp.posix_rename if hasattr(sftp, "posix_rename") else sftp.rename
            rename(tmp, remote_path)
            log(f"  ↓ {fname} ({r_size} B)")
            stats["downloaded"] += 1
            stats["bytes"] += r_size
        except Exception as exc:
            log(f"  ! {fname}: {exc}")
            stats["errors"] += 1
    return stats


def execute_sync(
    plan: SyncPlan,
    client,
    sftp,
    *,
    ssh_client=None,
    manifest: dict | None = None,
    mister_root: str = "/media/fat",
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Perform the resolved plan. Returns a counters dict.

    Mutates ``manifest`` in place with v2 entries ``{mtime,size,hash}``.
    """
    log = progress or (lambda _s: None)
    manifest = manifest if manifest is not None else {}
    stats = {
        "downloaded": 0, "overwritten": 0, "deleted": 0, "skipped": 0, "kept": 0,
        "saves_down": 0, "saves_up": 0, "saves_skip": 0,
        "states_down": 0, "states_up": 0, "states_skip": 0,
        "errors": 0,
    }

    def _snapshot(remote_path: str) -> dict:
        """Read post-transfer mtime+size (+ hash if cheap) for the manifest."""
        entry: dict = {}
        try:
            st = sftp.stat(remote_path)
            entry["mtime"] = float(st.st_mtime)
            entry["size"] = int(st.st_size or 0)
        except Exception:
            pass
        h = _remote_md5(ssh_client, remote_path)
        if h:
            entry["hash"] = h
        return entry

    def _mark_placed(a: SyncAction) -> None:
        manifest[_relpath_key(a.remote_path, mister_root)] = _snapshot(a.remote_path)

    def _mark_removed(a: SyncAction) -> None:
        manifest.pop(_relpath_key(a.remote_path, mister_root), None)

    for a in plan.actions:
        try:
            if a.kind == "skip":
                stats["skipped"] += 1
                # Ensure files that already match are still tracked as ours,
                # so a later unsubscribe can prune them.
                _mark_placed(a)
                continue

            if a.kind == "download":
                log(f"↓ {a.rom_name}  ({a.size_romm} B)")
                download_and_push(client, sftp, a.rom_id, a.file_name, a.remote_path)
                _mark_placed(a); stats["downloaded"] += 1

            elif a.kind == "overwrite":
                if a.resolution == RESOLVE_ROMM:
                    log(f"↓ overwrite {a.rom_name}")
                    download_and_push(client, sftp, a.rom_id, a.file_name, a.remote_path)
                    _mark_placed(a); stats["overwritten"] += 1
                elif a.resolution == RESOLVE_MISTER:
                    log(f"= keep MiSTer copy of {a.file_name}")
                    stats["skipped"] += 1
                else:
                    log(f"?  unresolved overwrite for {a.file_name} — skipping")
                    stats["errors"] += 1

            elif a.kind == "orphan":
                if a.resolution == RESOLVE_DELETE:
                    log(f"× delete orphan {a.remote_path}")
                    try:
                        sftp.remove(a.remote_path)
                        _mark_removed(a); stats["deleted"] += 1
                    except (FileNotFoundError, IOError) as exc:
                        log(f"  remove failed: {exc}")
                        stats["errors"] += 1
                elif a.resolution == RESOLVE_KEEP:
                    stats["kept"] += 1
                else:
                    log(f"?  unresolved orphan {a.file_name} — keeping")
                    stats["kept"] += 1

            # ── SAVES / STATES ────────────────────────────────────────
            elif a.kind in ("save_skip", "state_skip"):
                stats["saves_skip" if a.kind == "save_skip" else "states_skip"] += 1
                _mark_placed(a)

            elif a.kind == "save_download":
                log(f"↓ save {a.file_name}"); _download_asset(client, sftp, "save", a)
                _mark_placed(a); stats["saves_down"] += 1
            elif a.kind == "state_download":
                log(f"↓ state {a.file_name}"); _download_asset(client, sftp, "state", a)
                _mark_placed(a); stats["states_down"] += 1

            elif a.kind == "save_upload":
                log(f"↑ save {a.file_name}");  _upload_asset(client, sftp, "save", a)
                stats["saves_up"] += 1  # uploads don't touch MiSTer, no manifest change
            elif a.kind == "state_upload":
                log(f"↑ state {a.file_name}"); _upload_asset(client, sftp, "state", a)
                stats["states_up"] += 1

            elif a.kind in ("save_conflict", "state_conflict"):
                asset_kind = "save" if a.kind == "save_conflict" else "state"
                if a.resolution == RESOLVE_ROMM:
                    log(f"↓ {asset_kind} conflict → RomM wins {a.file_name}")
                    _download_asset(client, sftp, asset_kind, a)
                    _mark_placed(a)
                    stats["saves_down" if asset_kind == "save" else "states_down"] += 1
                elif a.resolution == RESOLVE_MISTER:
                    log(f"↑ {asset_kind} conflict → MiSTer wins {a.file_name}")
                    _upload_asset(client, sftp, asset_kind, a)
                    stats["saves_up" if asset_kind == "save" else "states_up"] += 1
                else:
                    log(f"?  unresolved {asset_kind} conflict {a.file_name} — skipping")
                    stats["errors"] += 1
        except Exception as exc:
            log(f"! {a.file_name}: {exc}")
            stats["errors"] += 1

    return stats

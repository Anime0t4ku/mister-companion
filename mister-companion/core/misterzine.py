import hashlib
import json
import os
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import certifi
except Exception:  # pragma: no cover - fall back to the platform trust store
    certifi = None

from core.app_paths import generated_path

MISTERZINE_BASE_URL = "https://misterzine.fyi"
META_URL = f"{MISTERZINE_BASE_URL}/releases/meta.json"
DATA_URL = f"{MISTERZINE_BASE_URL}/releases/data.json"
CACHE_DIR = generated_path("MiSTerZine")
META_CACHE = CACHE_DIR / "meta.json"
DATA_CACHE = CACHE_DIR / "data.json"
CHECK_STATE = CACHE_DIR / "check.json"
IMAGE_CACHE_DIR = CACHE_DIR / "images"
USER_AGENT = "MiSTer Companion MiSTerZine integration"


def _ensure_cache_dirs():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _ssl_context():
    """Return a verified TLS context that also works in packaged macOS builds."""
    if certifi is not None:
        try:
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    return ssl.create_default_context()


def _request_bytes(url: str, timeout: int = 12) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
        return response.read()


def _request_json(url: str, timeout: int = 12):
    return json.loads(_request_bytes(url, timeout=timeout).decode("utf-8"))


def _read_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def _write_bytes_atomic(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_name, path)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception:
            pass


def _write_json_atomic(path: Path, value):
    _write_bytes_atomic(path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


def cached_catalog():
    data = _read_json(DATA_CACHE, [])
    return data if isinstance(data, list) else []


def cached_meta():
    meta = _read_json(META_CACHE, {})
    return meta if isinstance(meta, dict) else {}


def refresh_catalog(force: bool = False, timeout: int = 12) -> dict:
    """Refresh MiSTerZine's live feed, falling back to the last local cache."""
    _ensure_cache_dirs()
    cached_data = cached_catalog()
    old_meta = cached_meta()

    if cached_data and not force:
        check = _read_json(CHECK_STATE, {})
        try:
            last = datetime.fromisoformat(str(check.get("checked_at", "")).replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - last).total_seconds() < 3600:
                return {
                    "entries": cached_data,
                    "meta": old_meta,
                    "from_cache": True,
                    "changed": False,
                    "throttled": True,
                }
        except Exception:
            pass

    try:
        live_meta = _request_json(META_URL, timeout=timeout)
        _write_json_atomic(CHECK_STATE, {"checked_at": datetime.now(timezone.utc).isoformat()})
        if not isinstance(live_meta, dict):
            raise ValueError("MiSTerZine meta.json did not contain an object.")

        live_hash = str(live_meta.get("hash", "") or "").strip()
        old_hash = str(old_meta.get("hash", "") or "").strip()
        needs_data = force or not cached_data or not live_hash or live_hash != old_hash

        if needs_data:
            raw = _request_bytes(DATA_URL, timeout=timeout)
            live_data = json.loads(raw.decode("utf-8"))
            if not isinstance(live_data, list):
                raise ValueError("MiSTerZine data.json did not contain a list.")
            _write_bytes_atomic(DATA_CACHE, raw)
            cached_data = live_data

        _write_json_atomic(META_CACHE, live_meta)
        return {
            "entries": cached_data,
            "meta": live_meta,
            "from_cache": False,
            "changed": needs_data,
        }
    except Exception as exc:
        if cached_data:
            return {
                "entries": cached_data,
                "meta": old_meta,
                "from_cache": True,
                "changed": False,
                "error": str(exc),
            }
        raise


def entry_deep_link(entry: dict) -> str:
    key = str((entry or {}).get("k", "") or "").strip()
    if not key:
        return f"{MISTERZINE_BASE_URL}/releases/"
    return f"{MISTERZINE_BASE_URL}/releases/#{urllib.parse.quote(key, safe='')}"


def entry_repo_link(entry: dict) -> str:
    repo = str((entry or {}).get("repo", "") or "").strip()
    if not repo:
        return ""
    if repo.startswith(("http://", "https://")):
        return repo
    return f"https://github.com/{repo}"


def entry_zaparoo_command(entry: dict) -> str:
    """Return a Zaparoo ZapScript target using MiSTerZine's live launch metadata."""
    item = entry or {}
    mra = str(item.get("mra", "") or "").strip()
    if mra:
        if not mra.startswith("/"):
            mra = f"/media/fat/{mra.lstrip('/')}"
        return f"**launch:{mra}"

    system = str(item.get("system", "") or item.get("core", "") or "").strip()
    if system:
        return f"**launch.system:{system}"
    return ""


def entry_type_text(entry: dict) -> str:
    item = entry or {}
    base = str(item.get("base", "") or "").strip()
    genre = str(item.get("genre", "") or "").strip()
    if base.lower() == "arcade":
        return f"Arcade, {genre}" if genre else "Arcade"
    if base:
        return f"{base} core"
    return ""


def entry_image_slots(entry: dict) -> list[str]:
    item = entry or {}
    slots = item.get("img_slots", [])
    if isinstance(slots, list):
        clean = [str(slot).strip().lower() for slot in slots if str(slot).strip()]
        if clean:
            return clean
    # Be defensive with older/newer feed variants.
    if item.get("img") or item.get("sn"):
        return ["title", "snap", "ingame"] if str(item.get("base", "")).lower() == "arcade" else ["system"]
    return []


def preferred_image_slot(entry: dict) -> str:
    slots = entry_image_slots(entry)
    # Prefer a title screen rather than an arbitrary in-game/game-over frame.
    for candidate in ("title", "snap", "ingame", "system"):
        if candidate in slots:
            return candidate
    return slots[0] if slots else ""


def _image_key(entry: dict) -> str:
    return str((entry or {}).get("img", "") or (entry or {}).get("sn", "") or "").strip()


def image_url_candidates(entry: dict, slot: str | None = None) -> list[str]:
    key = _image_key(entry)
    if not key:
        return []
    slot = (slot or preferred_image_slot(entry)).strip().lower()
    if not slot:
        return []
    encoded = urllib.parse.quote(key, safe="")
    directory = "systems" if slot == "system" else slot
    return [
        f"{MISTERZINE_BASE_URL}/images/{directory}/{encoded}.png",
        f"{MISTERZINE_BASE_URL}/images/{directory}/{encoded}.jpg",
        f"{MISTERZINE_BASE_URL}/images/{directory}/{encoded}.webp",
    ]


def _image_cache_stem(entry: dict, slot: str) -> str:
    key = f"{slot}:{_image_key(entry)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def cached_image_path(entry: dict, slot: str | None = None) -> Path | None:
    slot = (slot or preferred_image_slot(entry)).strip().lower()
    if not slot or not _image_key(entry):
        return None
    stem = _image_cache_stem(entry, slot)
    for suffix in (".png", ".jpg", ".webp"):
        path = IMAGE_CACHE_DIR / f"{stem}{suffix}"
        if path.exists() and path.stat().st_size > 0:
            return path
    return None


def fetch_image(entry: dict, slot: str | None = None, timeout: int = 10) -> Path | None:
    _ensure_cache_dirs()
    slot = (slot or preferred_image_slot(entry)).strip().lower()
    if not slot or not _image_key(entry):
        return None

    existing = cached_image_path(entry, slot)
    if existing is not None:
        return existing

    stem = _image_cache_stem(entry, slot)
    for url in image_url_candidates(entry, slot):
        try:
            data = _request_bytes(url, timeout=timeout)
            if not data:
                continue
            suffix = Path(urllib.parse.urlparse(url).path).suffix.lower() or ".img"
            target = IMAGE_CACHE_DIR / f"{stem}{suffix}"
            _write_bytes_atomic(target, data)
            return target
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
        except Exception:
            continue
    return None

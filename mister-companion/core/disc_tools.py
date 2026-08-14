from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

import requests

from core.app_paths import generated_path

CDRDAO_VERSION = "1.2.6"
CDRDAO_DIR = generated_path("tools", "cdrdao", default_root=Path(__file__).resolve().parent.parent)
CDRDAO_COMPANION_RELEASE_BASE = (
    "https://github.com/Anime0t4ku/cdrdao-Companion/releases/download/"
    f"cdrdao-{CDRDAO_VERSION}"
)

# Known-good upstream packages that Companion can install without relying on a
# system package manager or an external manifest. Additional native packages can
# be added here as they are validated. Windows ARM64 intentionally uses this same
# x64 bundle through Windows' built-in x64 emulation.
_BUILTIN_CDRDAO_PACKAGES = {
    # The official upstream Windows build is used on both x64 and ARM64.
    # Windows 11 on ARM runs this x64 helper through its built-in emulation.
    "windows-x64": {
        "version": CDRDAO_VERSION,
        "url": "https://sourceforge.net/projects/cdrdao/files/rel_1_2_6/cdrdao126.zip/download",
        "filename": "cdrdao126.zip",
    },
    "linux-x64": {
        "version": CDRDAO_VERSION,
        "url": f"{CDRDAO_COMPANION_RELEASE_BASE}/cdrdao-{CDRDAO_VERSION}-linux-x64.tar.gz",
        "filename": f"cdrdao-{CDRDAO_VERSION}-linux-x64.tar.gz",
    },
    "linux-arm64": {
        "version": CDRDAO_VERSION,
        "url": f"{CDRDAO_COMPANION_RELEASE_BASE}/cdrdao-{CDRDAO_VERSION}-linux-arm64.tar.gz",
        "filename": f"cdrdao-{CDRDAO_VERSION}-linux-arm64.tar.gz",
    },
    "macos-x64": {
        "version": CDRDAO_VERSION,
        "url": f"{CDRDAO_COMPANION_RELEASE_BASE}/cdrdao-{CDRDAO_VERSION}-macos-x64.tar.gz",
        "filename": f"cdrdao-{CDRDAO_VERSION}-macos-x64.tar.gz",
    },
    "macos-arm64": {
        "version": CDRDAO_VERSION,
        "url": f"{CDRDAO_COMPANION_RELEASE_BASE}/cdrdao-{CDRDAO_VERSION}-macos-arm64.tar.gz",
        "filename": f"cdrdao-{CDRDAO_VERSION}-macos-arm64.tar.gz",
    },
}


class DiscToolError(RuntimeError):
    pass


def platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arm64 = machine in {"arm64", "aarch64"}
    if system == "windows":
        # Windows 11 ARM can run the same x64 cdrdao helper via x64 emulation.
        return "windows-x64"
    if system == "darwin":
        return "macos-arm64" if arm64 else "macos-x64"
    if system == "linux":
        return "linux-arm64" if arm64 else "linux-x64"
    raise DiscToolError(f"Unsupported platform: {platform.system()} {platform.machine()}")


def _tool_name(name: str) -> str:
    return name + (".exe" if os.name == "nt" else "")


def cdrdao_executable() -> Path:
    return CDRDAO_DIR / _tool_name("cdrdao")


def toc2cue_executable() -> Path:
    return CDRDAO_DIR / _tool_name("toc2cue")


def cue2toc_executable() -> Path:
    return CDRDAO_DIR / _tool_name("cue2toc")


def has_cdrdao() -> bool:
    return all(p.is_file() for p in (cdrdao_executable(), toc2cue_executable(), cue2toc_executable()))


def remove_cdrdao() -> None:
    if CDRDAO_DIR.exists():
        shutil.rmtree(CDRDAO_DIR)


def _download(url: str, target: Path, progress_callback=None) -> None:
    with requests.get(url, stream=True, timeout=90) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0) or 0)
        done = 0
        with target.open("wb") as handle:
            for chunk in response.iter_content(1024 * 256):
                if not chunk:
                    continue
                handle.write(chunk)
                done += len(chunk)
                if progress_callback and total:
                    progress_callback(done, total)


def _extract_archive(archive: Path, destination: Path) -> None:
    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(destination)
        return
    if name.endswith((".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar")):
        with tarfile.open(archive, "r:*") as tf:
            tf.extractall(destination)
        return
    raise DiscToolError(f"Unsupported cdrdao package type: {archive.name}")


def _find_tool(root: Path, name: str) -> Path | None:
    wanted = _tool_name(name).lower()
    for path in root.rglob("*"):
        if path.is_file() and path.name.lower() == wanted:
            return path
    return None


def install_cdrdao(progress_callback=None) -> Path:
    """Install Companion's private cdrdao bundle.

    Companion uses its own published native Linux/macOS builds and the official
    upstream Windows package. Windows ARM64 maps to the Windows x64 package and
    runs it through Windows' x64 emulation.
    """
    key = platform_key()
    package = _BUILTIN_CDRDAO_PACKAGES.get(key)
    if not package:
        raise DiscToolError(
            f"No Companion-managed cdrdao {CDRDAO_VERSION} package is available for {key} yet."
        )

    if str(package.get("version", "")) != CDRDAO_VERSION:
        raise DiscToolError("The cdrdao package version does not match the Companion-pinned version.")

    url = str(package.get("url", "")).strip()
    if not url:
        raise DiscToolError(f"The cdrdao package URL for {key} is missing.")

    CDRDAO_DIR.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mister-companion-cdrdao-") as tmp:
        tmpdir = Path(tmp)
        filename = str(package.get("filename", "")).strip()
        if not filename:
            filename = Path(url.split("?", 1)[0]).name or "cdrdao-package.zip"
        archive = tmpdir / filename
        _download(url, archive, progress_callback)

        # Catch SourceForge/host error pages before presenting an opaque archive
        # exception to the user.
        if archive.suffix.lower() == ".zip":
            try:
                with archive.open("rb") as handle:
                    if handle.read(2) != b"PK":
                        raise DiscToolError("The cdrdao download did not return a valid ZIP archive.")
            except OSError as exc:
                raise DiscToolError("The downloaded cdrdao package could not be opened.") from exc

        unpacked = tmpdir / "unpacked"
        unpacked.mkdir()
        _extract_archive(archive, unpacked)

        found = {name: _find_tool(unpacked, name) for name in ("cdrdao", "toc2cue", "cue2toc")}
        missing = [name for name, path in found.items() if path is None]
        if missing:
            raise DiscToolError("The downloaded cdrdao package is incomplete: " + ", ".join(missing))

        staged = tmpdir / "staged"
        staged.mkdir()
        # Keep the whole executable directory so DLLs/dylibs/shared libraries stay
        # beside the tools. Copy helper executables into that same root if needed.
        exe_dir = found["cdrdao"].parent
        shutil.copytree(exe_dir, staged, dirs_exist_ok=True)
        for name, src in found.items():
            target = staged / _tool_name(name)
            if not target.exists():
                shutil.copy2(src, target)

        if CDRDAO_DIR.exists():
            shutil.rmtree(CDRDAO_DIR)
        shutil.copytree(staged, CDRDAO_DIR)

    if os.name != "nt":
        for tool in (cdrdao_executable(), toc2cue_executable(), cue2toc_executable()):
            tool.chmod(tool.stat().st_mode | 0o755)
    _verify_cdrdao()
    if progress_callback:
        progress_callback(1, 1)
    return cdrdao_executable()


def _tool_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = str(CDRDAO_DIR) + os.pathsep + env.get("PATH", "")
    if platform.system().lower() == "darwin":
        env["DYLD_LIBRARY_PATH"] = str(CDRDAO_DIR) + (os.pathsep + env["DYLD_LIBRARY_PATH"] if env.get("DYLD_LIBRARY_PATH") else "")
    elif platform.system().lower() == "linux":
        env["LD_LIBRARY_PATH"] = str(CDRDAO_DIR) + (os.pathsep + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    return env


def _verify_cdrdao() -> None:
    """Verify that Companion's private cdrdao bundle can actually execute.

    cdrdao releases/platform builds have not always exposed version information
    through exactly the same command-line form.  Treat successful process launch
    as the important check instead of rejecting a working install solely because
    a particular --version spelling/output differs.
    """
    if not has_cdrdao():
        raise DiscToolError("cdrdao helper files were not found after installation.")

    exe = str(cdrdao_executable())
    attempts = ([exe, "version"], [exe, "--version"])
    launched = False
    outputs: list[str] = []

    for command in attempts:
        try:
            proc = subprocess.run(
                command, cwd=str(CDRDAO_DIR), env=_tool_env(),
                capture_output=True, text=True, errors="replace", timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            continue

        launched = True
        text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        outputs.append(text)
        lower = text.lower()
        # Accept the normal version output regardless of whether the build prints
        # the pinned version to stdout or stderr.  Some Windows bundles return a
        # non-zero status for the unsupported --version spelling, so do not make
        # that spelling alone determine whether the installed binary is usable.
        if "cdrdao" in lower and (CDRDAO_VERSION in text or "version" in lower):
            return
        if proc.returncode == 0 and "cdrdao" in lower:
            return

    if launched:
        # The executable itself started, which is sufficient for installation.
        # Operational commands such as scanbus/read-cd will surface any real
        # runtime/device error later with their full cdrdao output.
        return

    raise DiscToolError(
        "cdrdao was installed, but the executable could not be started. "
        "The installed files may be incomplete or blocked by the operating system."
    )


def scan_drives() -> list[tuple[str, str]]:
    if not has_cdrdao():
        return []
    proc = subprocess.run(
        [str(cdrdao_executable()), "scanbus"], cwd=str(CDRDAO_DIR), env=_tool_env(),
        capture_output=True, text=True, errors="replace", timeout=25,
    )
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    results: list[tuple[str, str]] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("Cdrdao", "SCSI", "Using")):
            continue

        # Native Windows scanbus output uses drive-root tokens such as:
        #   D:\\ : HL-DT-ST, DVDRAM GP65NB60, PF00
        # cdrdao expects --device D on Windows, so normalize the scan result to
        # the drive letter while keeping the reported vendor/model as the label.
        m = re.match(r"^([A-Za-z]):[\\/]*\s*:\s*(.*)$", line)
        if m:
            device = m.group(1).upper()
            details = m.group(2).strip().strip("'").strip()
            parts = [part.strip().strip("'") for part in details.split(",") if part.strip().strip("'")]
            label = " ".join(parts) if parts else f"{device}: Optical Drive"
            results.append((device, label))
            continue

        # Unix/macOS native device paths, e.g. /dev/sr0 : VENDOR, MODEL, REV.
        m = re.match(r"^(/dev/\S+)\s*:\s*(.*)$", line)
        if m:
            device = m.group(1).strip()
            details = m.group(2).strip().strip("'")
            parts = [part.strip().strip("'") for part in details.split(",") if part.strip().strip("'")]
            label = " ".join(parts) if parts else device
            results.append((device, label))
            continue

        # Older/platform-specific SCSI bus notation.
        m = re.match(r"^(\d+[,/:]\d+[,/:]\d+)\s*(?::\s*|\s+)(.+)$", line)
        if m:
            results.append((m.group(1), m.group(2).strip().strip("'")))

    seen = set()
    unique = []
    for device, label in results:
        if device not in seen:
            seen.add(device)
            unique.append((device, label))
    return unique


def _run_streaming(command: list[str], log_callback=None, cwd: Path | None = None) -> None:
    proc = subprocess.Popen(
        command, cwd=str(cwd or CDRDAO_DIR), env=_tool_env(), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        if log_callback:
            log_callback(line.rstrip())
    code = proc.wait()
    if code != 0:
        raise DiscToolError(f"{Path(command[0]).name} exited with code {code}.")


def _msf_to_frames(value: str) -> int:
    try:
        minutes, seconds, frames = (int(part) for part in value.split(":", 2))
    except (TypeError, ValueError):
        return 0
    return ((minutes * 60) + seconds) * 75 + frames


def rip_disc(
    device: str,
    output_cue: str | Path,
    log_callback=None,
    progress_callback=None,
) -> tuple[Path, Path, Path]:
    if not has_cdrdao():
        raise DiscToolError("Install cdrdao first.")
    cue = Path(output_cue)
    cue.parent.mkdir(parents=True, exist_ok=True)
    if cue.suffix.lower() != ".cue":
        cue = cue.with_suffix(".cue")
    stem = cue.with_suffix("")
    bin_path = stem.with_suffix(".bin")
    toc_path = stem.with_suffix(".toc")
    for path in (cue, bin_path, toc_path):
        if path.exists():
            raise FileExistsError(f"Output already exists: {path}")

    # Run cdrdao from the selected output directory and pass only relative
    # filenames. On Windows, cdrdao writes the --datafile value verbatim into
    # the generated TOC. An absolute path such as D:\\Game.bin therefore
    # leaves backslashes in the TOC, which toc2cue parses as TOC syntax and
    # fails to reopen. Relative filenames avoid that problem entirely and also
    # keep the generated TOC portable.
    workdir = cue.parent
    command = [
        str(cdrdao_executable()), "read-cd", "--read-raw", "--device", device,
        "--datafile", bin_path.name, toc_path.name,
    ]

    track_lengths: dict[int, int] = {}
    current_track: int | None = None
    current_kind = "track"
    last_percent = -1

    track_row_re = re.compile(
        r"^\s*(\d+)\s+([A-Z0-9_]+)\s+\S+\s+\d{1,3}:\d{2}:\d{2}\([^)]*\)\s+(\d{1,3}:\d{2}:\d{2})\("
    )
    copying_re = re.compile(
        r"^Copying\s+(data|audio)\s+track\s+(\d+).*?length\s+(\d{1,3}:\d{2}:\d{2})",
        re.IGNORECASE,
    )
    time_re = re.compile(r"^(\d{1,3}:\d{2}:\d{2})$")

    def report_progress(percent: int, message: str) -> None:
        nonlocal last_percent
        percent = max(0, min(100, int(percent)))
        if progress_callback and percent != last_percent:
            last_percent = percent
            progress_callback(percent, message)

    def rip_output(line: str) -> None:
        nonlocal current_track, current_kind
        stripped = line.strip()
        if not stripped:
            return

        match = track_row_re.match(stripped)
        if match:
            track_lengths[int(match.group(1))] = _msf_to_frames(match.group(3))
            return
        if stripped.lower().startswith("leadout"):
            return

        match = copying_re.match(stripped)
        if match:
            current_kind = match.group(1).lower()
            current_track = int(match.group(2))
            track_lengths.setdefault(current_track, _msf_to_frames(match.group(3)))
            count = max(track_lengths) if track_lengths else current_track
            label = current_kind.capitalize()
            message = f"Ripping track {current_track} of {count} ({label}) — 0%"
            if log_callback:
                log_callback(f"Ripping track {current_track} of {count} ({label})...")
            report_progress(0 if current_track == 1 else int(100 * sum(v for k, v in track_lengths.items() if k < current_track) / max(1, sum(track_lengths.values()))), message)
            return

        match = time_re.match(stripped)
        if match and current_track is not None:
            position = _msf_to_frames(match.group(1))
            total = sum(track_lengths.values())
            before = sum(length for number, length in track_lengths.items() if number < current_track)
            current_length = max(1, track_lengths.get(current_track, position or 1))
            track_percent = min(100, int(position * 100 / current_length))
            overall = min(99, int((before + min(position, current_length)) * 100 / total)) if total else track_percent
            count = max(track_lengths) if track_lengths else current_track
            report_progress(overall, f"Ripping track {current_track} of {count} — {track_percent}%")
            return

        lower = stripped.lower()
        if "reading toc and track data" in lower:
            if log_callback:
                log_callback("Reading disc layout...")
            report_progress(0, "Reading disc layout...")
            return
        if "reading of toc and track data finished successfully" in lower:
            report_progress(100, "Disc read complete — 100%")
            if log_callback:
                log_callback("Disc read completed successfully.")
            return

        # cdrdao prints hardware capability details and a raw track table before
        # the copy begins. They are useful diagnostically but noisy for normal
        # users, so only pass warnings/errors and other meaningful messages on.
        if stripped.startswith(("Track   Mode", "----", "PQ sub-channel", "Raw P-W", "Cooked R-W", "CD-TEXT", "Using driver", "Cdrdao version")):
            return
        if log_callback and ("error" in lower or "warning" in lower):
            log_callback(stripped)

    _run_streaming(command, rip_output, workdir)

    # toc2cue 1.2.6 uses -C <output-bin-file> to create a CUE-compatible
    # BIN and -s to byte-swap AUDIO sectors while doing so.  The previous
    # implementation incorrectly used a non-existent --binfile option, which
    # makes toc2cue exit with code 1 after an otherwise successful rip.
    converted = stem.with_name(stem.name + "-cue").with_suffix(".bin")
    convert_cmd = [
        str(toc2cue_executable()),
        "-C", converted.name,
        "-s",
        toc_path.name, cue.name,
    ]
    if log_callback:
        log_callback("Creating BIN/CUE image...")

    def toc2cue_output(line: str) -> None:
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("toc2cue version"):
            return
        if log_callback and ("error" in stripped.lower() or "warning" in stripped.lower()):
            log_callback(stripped)

    _run_streaming(convert_cmd, toc2cue_output, workdir)

    if not converted.is_file() or not cue.is_file():
        raise DiscToolError("toc2cue did not create the expected BIN/CUE output.")

    # Keep the public output name selected by the user. toc2cue writes the
    # converted filename into the CUE, so update that reference after renaming.
    bin_path.unlink(missing_ok=True)
    converted.replace(bin_path)
    text = cue.read_text(encoding="utf-8", errors="replace")
    cue.write_text(text.replace(converted.name, bin_path.name), encoding="utf-8")
    # The TOC is only an internal cdrdao intermediate. The public Disc to Image
    # result is BIN/CUE (or CHD), so do not leave the TOC beside the user's image.
    toc_path.unlink(missing_ok=True)
    return cue, bin_path, toc_path


def _burn_output_handler(line: str, log_callback=None, progress_callback=None, state=None) -> None:
    """Translate cdrdao's console output into concise burn status/progress."""
    stripped = line.strip()
    if not stripped:
        return
    state = state if state is not None else {}

    # cdrdao reports actual written data as "Wrote X of Y MB". Use that as
    # the authoritative burn percentage instead of exposing raw console output.
    m = re.search(r"Wrote\s+(\d+(?:\.\d+)?)\s+of\s+(\d+(?:\.\d+)?)\s+MB", stripped, re.IGNORECASE)
    if m:
        done = float(m.group(1))
        total = float(m.group(2))
        percent = max(0, min(100, int(done * 100 / total))) if total > 0 else 0
        track = state.get("track")
        message = f"Writing track {track} — {percent}%" if track else f"Writing disc — {percent}%"
        if progress_callback:
            progress_callback(percent, message)
        return

    m = re.search(r"Writing track\s+(\d+)", stripped, re.IGNORECASE)
    if m:
        track = int(m.group(1))
        state["track"] = track
        if progress_callback:
            progress_callback(state.get("percent", 0), f"Writing track {track}...")
        return

    lower = stripped.lower()
    if "lead-out" in lower or "leadout" in lower:
        if progress_callback:
            progress_callback(max(99, state.get("percent", 0)), "Finalizing disc...")
        return
    if "power calibration" in lower:
        if progress_callback:
            progress_callback(0, "Calibrating writer...")
        return

    # Keep the user-facing output concise. Surface only useful milestones and
    # diagnostics; cdrdao's device/sector chatter stays hidden.
    if log_callback and (
        "error" in lower
        or "warning" in lower
        or "writing finished" in lower
        or "writing completed" in lower
        or "blanking" in lower
    ):
        log_callback(stripped)


def burn_cue(device: str, cue_path: str | Path, speed: int | None = None, log_callback=None, progress_callback=None) -> None:
    if not has_cdrdao():
        raise DiscToolError("Install cdrdao first.")
    cue = Path(cue_path)
    if not cue.is_file():
        raise FileNotFoundError(cue)
    if progress_callback:
        progress_callback(0, "Preparing game disc...")
    with tempfile.TemporaryDirectory(prefix="mister-companion-burn-") as tmp:
        toc = Path(tmp) / "image.toc"
        _run_streaming([str(cue2toc_executable()), str(cue), str(toc)], log_callback, cue.parent)
        command = [str(cdrdao_executable()), "write", "--device", device]
        if speed:
            command += ["--speed", str(speed)]
        command.append(str(toc))
        state = {"percent": 0}
        def output(line):
            m = re.search(r"Wrote\s+(\d+(?:\.\d+)?)\s+of\s+(\d+(?:\.\d+)?)\s+MB", line, re.IGNORECASE)
            if m and float(m.group(2)) > 0:
                state["percent"] = max(0, min(100, int(float(m.group(1)) * 100 / float(m.group(2)))))
            _burn_output_handler(line, log_callback, progress_callback, state)
        _run_streaming(command, output, cue.parent)
    if progress_callback:
        progress_callback(100, "Disc written successfully — 100%")


def create_iso9660_from_folder(source_folder: str | Path, output_iso: str | Path, volume_id: str | None = None) -> Path:
    try:
        import pycdlib
    except ImportError as exc:
        raise DiscToolError("ISO 9660 creation requires the pycdlib Python package.") from exc

    source = Path(source_folder)
    output = Path(output_iso)
    if not source.is_dir():
        raise NotADirectoryError(source)
    files = [p for p in source.iterdir() if p.is_file()]
    if not files:
        raise DiscToolError("The selected MSU-1 / MD+ folder contains no files at its root.")
    # Deliberately do not recurse: selected-folder contents are authored directly
    # at disc root, and a containing game folder is never added to the ISO.
    # ISO 9660 volume identifiers are limited to 32 characters. Keep the user
    # supplied label predictable and portable; if none is supplied, derive a
    # sensible label from the selected folder name.
    requested_label = (volume_id or source.name or "MISTER_DISC").strip().upper()
    safe_label = re.sub(r"[^A-Z0-9_]", "_", requested_label)[:32].strip("_") or "MISTER_DISC"
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, vol_ident=safe_label)
    used_iso_names: set[str] = set()
    try:
        for path in files:
            # Joliet preserves the real filename for MiSTer. Add a conservative,
            # unique ISO9660 alias as the primary tree entry.
            cleaned = re.sub(r"[^A-Z0-9_]", "_", path.stem.upper())[:24] or "FILE"
            ext = re.sub(r"[^A-Z0-9]", "", path.suffix.upper().lstrip("."))[:3]
            base = cleaned + (("." + ext) if ext else "")
            candidate = base
            n = 1
            while candidate in used_iso_names:
                suffix = f"_{n}"
                candidate = (cleaned[: max(1, 24 - len(suffix))] + suffix) + (("." + ext) if ext else "")
                n += 1
            used_iso_names.add(candidate)
            iso_path = f"/{candidate};1"
            joliet_path = "/" + path.name
            iso.add_file(str(path), iso_path=iso_path, joliet_path=joliet_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        iso.write(str(output))
    finally:
        iso.close()
    return output


def burn_iso9660_folder(device: str, source_folder: str | Path, speed: int | None = None, volume_id: str | None = None, log_callback=None, progress_callback=None) -> None:
    if not has_cdrdao():
        raise DiscToolError("Install cdrdao first.")
    if progress_callback:
        progress_callback(0, "Creating ISO 9660 data image...")
    with tempfile.TemporaryDirectory(prefix="mister-companion-data-disc-") as tmp:
        tmpdir = Path(tmp)
        iso_path = create_iso9660_from_folder(source_folder, tmpdir / "data.iso", volume_id=volume_id)
        toc_path = tmpdir / "data.toc"
        toc_path.write_text(
            'CD_ROM\n\nTRACK MODE1\nNO COPY\nDATAFILE "data.iso"\n',
            encoding="ascii",
        )
        if progress_callback:
            progress_callback(0, "ISO 9660 image ready. Starting burn...")
        command = [str(cdrdao_executable()), "write", "--device", device]
        if speed:
            command += ["--speed", str(speed)]
        command.append(str(toc_path))
        state = {"percent": 0}
        def output(line):
            m = re.search(r"Wrote\s+(\d+(?:\.\d+)?)\s+of\s+(\d+(?:\.\d+)?)\s+MB", line, re.IGNORECASE)
            if m and float(m.group(2)) > 0:
                state["percent"] = max(0, min(100, int(float(m.group(1)) * 100 / float(m.group(2)))))
            _burn_output_handler(line, log_callback, progress_callback, state)
        _run_streaming(command, output, tmpdir)
    if progress_callback:
        progress_callback(100, "Disc written successfully — 100%")

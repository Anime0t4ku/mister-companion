from __future__ import annotations

import os
import hashlib
import platform
import plistlib
import re
import shutil
import subprocess
import threading
import time
import tarfile
import tempfile
import zipfile
from pathlib import Path

import requests

from core.app_paths import app_base_dir, generated_path

CDRDAO_VERSION = "1.2.6"
CDRDAO_DIR = generated_path("tools", "cdrdao", default_root=app_base_dir())
CDRDAO_COMPANION_RELEASE_BASE = (
    "https://github.com/Anime0t4ku/cdrdao-Companion/releases/download/"
    f"cdrdao-{CDRDAO_VERSION}"
)




_BUILTIN_CDRDAO_PACKAGES = {
    
    
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
}


class DiscToolError(RuntimeError):
    pass



def platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arm64 = machine in {"arm64", "aarch64"}
    if system == "windows":
        
        return "windows-x64"
    if system == "darwin":
        return "macos-arm64" if arm64 else "macos-x64"
    if system == "linux":
        return "linux-arm64" if arm64 else "linux-x64"
    raise DiscToolError(f"Unsupported platform: {platform.system()} {platform.machine()}")



def _is_macos() -> bool:
    return platform.system().lower() == "darwin"



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
    if _is_macos():
        raise DiscToolError("macOS uses the native Disc Recording backend and does not require cdrdao.")

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
    tool_dir = cdrdao_executable().parent if has_cdrdao() else CDRDAO_DIR
    env["PATH"] = str(tool_dir) + os.pathsep + env.get("PATH", "")
    if platform.system().lower() == "linux":
        env["LD_LIBRARY_PATH"] = str(tool_dir) + (os.pathsep + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
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
                command, cwd=str(cdrdao_executable().parent), env=_tool_env(),
                capture_output=True, text=True, errors="replace", timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            continue

        launched = True
        text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        outputs.append(text)
        lower = text.lower()
        
        
        
        
        if "cdrdao" in lower and (CDRDAO_VERSION in text or "version" in lower):
            return
        if proc.returncode == 0 and "cdrdao" in lower:
            return

    if launched:
        
        
        
        return

    raise DiscToolError(
        "cdrdao was installed, but the executable could not be started. "
        "The installed files may be incomplete or blocked by the operating system."
    )




def _macos_drutil() -> Path:
    return Path("/usr/bin/drutil")


def has_native_macos_disc_backend() -> bool:
    """Return whether macOS' built-in DiscRecording command-line frontend exists."""
    return _is_macos() and _macos_drutil().is_file()


def disc_backend_ready() -> bool:
    """Disc tools are native on macOS and cdrdao-backed elsewhere."""
    return has_native_macos_disc_backend() if _is_macos() else has_cdrdao()


def _macos_drutil_run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [str(_macos_drutil()), *args],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )
    if proc.returncode != 0:
        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        raise DiscToolError(output or f"drutil exited with code {proc.returncode}.")
    return proc


def _macos_media_nodes() -> list[tuple[str, str]]:
    """Return (drive label, raw BSD node) pairs for inserted optical media.

    Prefer ioreg's XML property-list output instead of scraping its human-readable
    tree.  The latter can vary between macOS versions and was the reason an
    otherwise visible IOCDMedia device could be missed.  A short retry window
    also handles the momentary unpublish/republish that can occur after drutil
    probes an optical disc.
    """

    def collect_from_plist(value) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []

        def walk(obj) -> None:
            if isinstance(obj, dict):
                bsd = obj.get("BSD Name")
                whole = obj.get("Whole")
                if isinstance(bsd, str) and re.fullmatch(r"disk\d+", bsd) and whole is not False:
                    label = (
                        obj.get("IORegistryEntryName")
                        or obj.get("Product Name")
                        or obj.get("Model")
                        or "Optical Drive"
                    )
                    pair = (str(label), f"/dev/r{bsd}")
                    if pair not in found:
                        found.append(pair)
                for child in obj.values():
                    if isinstance(child, (dict, list)):
                        walk(child)
            elif isinstance(obj, list):
                for child in obj:
                    walk(child)

        walk(value)
        return found

    def query_ioreg() -> list[tuple[str, str]]:
        try:
            proc = subprocess.run(
                ["/usr/sbin/ioreg", "-a", "-r", "-c", "IOCDMedia"],
                capture_output=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if proc.returncode != 0 or not proc.stdout:
            return []
        try:
            return collect_from_plist(plistlib.loads(proc.stdout))
        except Exception:
            return []

    def query_ioreg_text() -> list[tuple[str, str]]:
        
        
        
        try:
            proc = subprocess.run(
                ["/usr/sbin/ioreg", "-r", "-c", "IOCDMedia", "-l"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if proc.returncode != 0:
            return []
        results: list[tuple[str, str]] = []
        current_label = ""
        for raw in (proc.stdout or "").splitlines():
            line = raw.strip()
            m = re.search(r"\+-o\s+(.+?)\s+Media\s+<class IOCDMedia", line)
            if m:
                current_label = m.group(1).strip()
                continue
            m = re.search(r'"BSD Name"\s*=\s*"(disk\d+)"', line)
            if m and current_label:
                results.append((current_label, f"/dev/r{m.group(1)}"))
                current_label = ""
        return results

    
    
    
    for attempt in range(9):
        results = query_ioreg() or query_ioreg_text()
        if results:
            return results
        if attempt < 8:
            time.sleep(0.25)
    return []


def _macos_parse_device(device: str) -> tuple[int, str | None]:
    
    m = re.fullmatch(r"macos:(\d+):(.*)", str(device))
    if not m:
        raise DiscToolError("The selected macOS optical drive is no longer valid. Refresh the drive list.")
    index = int(m.group(1))
    raw = m.group(2)
    return index, None if raw == "-" else raw


def _scan_macos_drives() -> list[tuple[str, str]]:
    if not has_native_macos_disc_backend():
        return []
    try:
        proc = _macos_drutil_run(["list"], timeout=20)
    except DiscToolError:
        return []
    media = _macos_media_nodes()
    used_nodes: set[str] = set()
    results: list[tuple[str, str]] = []
    
    for raw in (proc.stdout or "").splitlines():
        line = raw.strip()
        m = re.match(r"^(\d+)\s+(.+)$", line)
        if not m:
            continue
        index = int(m.group(1))
        rest = m.group(2).strip()
        
        parts = re.split(r"\s{2,}", rest)
        label = " ".join(parts[:3]).strip() if len(parts) >= 3 else rest
        
        
        raw_node = None
        lower = rest.lower()
        for media_label, node in media:
            if node in used_nodes:
                continue
            tokens = [t for t in re.split(r"\s+", media_label.lower()) if len(t) > 2]
            if tokens and all(t in lower for t in tokens[-2:]):
                raw_node = node
                used_nodes.add(node)
                break
        if raw_node is None and len(media) == 1 and len(results) == 0:
            raw_node = media[0][1]
            used_nodes.add(raw_node)
        results.append((f"macos:{index}:{raw_node or '-'}", label))
    return results


def _macos_current_raw_device(index: int, preferred: str | None = None) -> str:
    """Resolve the current raw BSD node for a drutil drive index.

    BSD disk numbers can change when media is inserted/ejected or when macOS
    re-enumerates a USB optical drive, so never trust the node captured when
    the UI drive list was populated.
    """
    if preferred and Path(preferred).exists():
        return preferred

    media = _macos_media_nodes()
    if not media:
        raise DiscToolError("macOS could not find inserted CD media. Refresh the drive list and try again.")

    
    try:
        proc = _macos_drutil_run(["list"], timeout=20)
        selected = ""
        for raw in (proc.stdout or "").splitlines():
            line = raw.strip()
            m = re.match(r"^(\d+)\s+(.+)$", line)
            if m and int(m.group(1)) == index:
                selected = m.group(2).lower()
                break
        if selected:
            for media_label, node in media:
                tokens = [t for t in re.split(r"\s+", media_label.lower()) if len(t) > 2]
                if tokens and all(t in selected for t in tokens[-2:]) and Path(node).exists():
                    return node
    except DiscToolError:
        pass

    
    existing = [node for _label, node in media if Path(node).exists()]
    if len(existing) == 1:
        return existing[0]

    raise DiscToolError(
        "macOS could not match the selected optical drive to its current raw device. "
        "Refresh the drive list and try again."
    )


def _frames_to_msf(frames: int) -> str:
    frames = max(0, int(frames))
    minutes, rem = divmod(frames, 75 * 60)
    seconds, ff = divmod(rem, 75)
    return f"{minutes:02d}:{seconds:02d}:{ff:02d}"


def _macos_toc(index: int) -> tuple[list[dict], int]:
    proc = _macos_drutil_run(["-drive", str(index), "toc"], timeout=25)
    tracks: list[dict] = []
    leadout_abs = None
    for raw in (proc.stdout or "").splitlines():
        line = raw.strip()
        m = re.match(r"Lead-out\s*:\s*(\d{1,3}:\d{2}[.:]\d{2})", line, re.IGNORECASE)
        if m:
            leadout_abs = _msf_to_frames(m.group(1))
            continue
        m = re.match(
            r"Session\s+(\d+)\s*,\s*Track\s+(\d+)\s*:\s*(\d{1,3}:\d{2}[.:]\d{2})\s+(.+)$",
            line,
            re.IGNORECASE,
        )
        if m:
            desc = m.group(4).lower()
            tracks.append({
                "session": int(m.group(1)),
                "number": int(m.group(2)),
                "absolute": _msf_to_frames(m.group(3)),
                "audio": "audio" in desc or "2ch" in desc,
                "description": m.group(4).strip(),
            })
    if not tracks or leadout_abs is None:
        raise DiscToolError("macOS could not read the disc TOC.")
    
    
    for track in tracks:
        track["lba"] = max(0, track["absolute"] - 150)
    total_sectors = max(0, leadout_abs - 150)
    if total_sectors <= 0:
        raise DiscToolError("macOS reported an invalid CD lead-out address.")
    return tracks, total_sectors


def _macos_open_current_raw_device(index: int, preferred: str | None = None, timeout: float = 8.0):
    """Resolve and immediately open the current whole-disc raw BSD device.

    Mixed-mode CDs may be republished by macOS while Disc Recording probes the
    TOC.  Do not return a path and open it later: resolve + open in the same
    retry loop so a transient disk-number change cannot leave us with a stale
    /dev/rdiskN.
    """
    deadline = time.monotonic() + max(0.5, timeout)
    last_error: OSError | None = None
    hint = preferred
    while time.monotonic() < deadline:
        try:
            raw_device = _macos_current_raw_device(index, hint)
        except DiscToolError:
            raw_device = None
        hint = None  

        if raw_device:
            candidates = [raw_device]
            
            
            if raw_device.startswith("/dev/rdisk"):
                candidates.append(raw_device.replace("/dev/rdisk", "/dev/disk", 1))
            for candidate in candidates:
                try:
                    return open(candidate, "rb", buffering=0), candidate
                except (FileNotFoundError, PermissionError, OSError) as exc:
                    last_error = exc

        time.sleep(0.20)

    if isinstance(last_error, PermissionError):
        raise DiscToolError("macOS denied access to the optical disc device.") from last_error
    if last_error is not None:
        raise DiscToolError(
            "macOS could not open the inserted CD media after it was detected. "
            "Eject and reinsert the disc, then refresh the drive list."
        ) from last_error
    raise DiscToolError("macOS could not find inserted CD media. Refresh the drive list and try again.")


def _macos_cue_track_mode(handle, track: dict) -> str:
    if track.get("audio"):
        return "AUDIO"
    
    
    
    try:
        handle.seek(int(track["lba"]) * 2352)
        header = handle.read(16)
        if len(header) >= 16 and header[:12] == b"\x00" + (b"\xff" * 10) + b"\x00":
            if header[15] == 2:
                return "MODE2/2352"
            if header[15] == 1:
                return "MODE1/2352"
    except OSError:
        pass
    return "MODE1/2352"


def _rip_disc_macos(
    device: str,
    output_cue: str | Path,
    log_callback=None,
    progress_callback=None,
) -> tuple[Path, Path, Path]:
    index, preferred_raw_device = _macos_parse_device(device)
    cue = Path(output_cue)
    if cue.suffix.lower() != ".cue":
        cue = cue.with_suffix(".cue")
    cue.parent.mkdir(parents=True, exist_ok=True)
    bin_path = cue.with_suffix(".bin")
    toc_path = cue.with_suffix(".toc")  
    for path in (cue, bin_path):
        if path.exists():
            raise FileExistsError(f"Output already exists: {path}")

    if progress_callback:
        progress_callback(0, "Reading disc layout...")
    
    
    tracks, total_sectors = _macos_toc(index)
    src, raw_device = _macos_open_current_raw_device(index, preferred_raw_device)
    try:
        modes = {track["number"]: _macos_cue_track_mode(src, track) for track in tracks}
        src.seek(0)
        if log_callback:
            log_callback(f"Using native macOS Disc Recording ({len(tracks)} tracks).")

        
        
        
        
        
        
        write_group_sectors = 64
        copied = 0
        current_track_idx = 0
        pending = bytearray()
        with src, bin_path.open("xb") as dst:
            while copied < total_sectors:
                while current_track_idx + 1 < len(tracks) and copied >= tracks[current_track_idx + 1]["lba"]:
                    current_track_idx += 1

                sector = None
                last_error = None
                for attempt in range(4):
                    try:
                        
                        
                        if attempt:
                            src.seek(copied * 2352)
                            time.sleep(0.05 * attempt)
                        sector = src.read(2352)
                        if len(sector) == 2352:
                            break
                        if not sector:
                            last_error = OSError("optical drive returned no data")
                        else:
                            last_error = OSError(f"partial raw CD sector ({len(sector)} bytes)")
                    except OSError as exc:
                        last_error = exc
                        sector = None

                if sector is None or len(sector) != 2352:
                    detail = f": {last_error}" if last_error else ""
                    raise DiscToolError(
                        f"The optical drive could not read raw sector {copied}{detail}"
                    )

                pending.extend(sector)
                copied += 1
                if len(pending) >= write_group_sectors * 2352 or copied >= total_sectors:
                    dst.write(pending)
                    pending.clear()

                percent = min(100, int(copied * 100 / total_sectors))
                track_no = tracks[current_track_idx]["number"]
                if progress_callback and (copied == 1 or copied % write_group_sectors == 0 or copied >= total_sectors):
                    progress_callback(percent, f"Ripping track {track_no} of {len(tracks)} — {percent}%")
    except Exception:
        bin_path.unlink(missing_ok=True)
        raise

    cue_lines = [f'FILE "{bin_path.name}" BINARY']
    for track in tracks:
        cue_lines.append(f'  TRACK {track["number"]:02d} {modes[track["number"]]}')
        cue_lines.append(f'    INDEX 01 {_frames_to_msf(track["lba"])}')
    cue.write_text("\n".join(cue_lines) + "\n", encoding="utf-8")
    if progress_callback:
        progress_callback(100, "Disc read complete — 100%")
    return cue, bin_path, toc_path


def _run_native_macos_burn(
    index: int,
    image_path: Path,
    speed: int | None = None,
    log_callback=None,
    progress_callback=None,
) -> None:
    script = r"""
ObjC.import('Foundation')
ObjC.import('DiscRecording')

function val(dict, key) {
    var item = dict.objectForKey(key)
    if (!item) return null
    try { return ObjC.unwrap(item) } catch (e) { return String(item) }
}

function emit(obj) {
    console.log(JSON.stringify(obj))
}

function run(argv) {
    var wanted = parseInt(argv[0], 10) - 1
    var imagePath = String(argv[1])
    var xfactor = parseFloat(argv[2] || '0')
    var devices = $.DRDevice.devices
    var count = Number(devices.count)
    if (wanted < 0 || wanted >= count) throw new Error('Selected optical drive is unavailable')
    var device = devices.objectAtIndex(wanted)
    var layout = $.DRBurn.layoutForImageFile($(imagePath))
    if (!layout) throw new Error('Disc Recording could not create a burn layout for this image')
    var burn = $.DRBurn.burnForDevice(device)
    burn.setVerifyDisc(false)
    burn.setAppendable(false)
    if (xfactor > 0) {
        var kps = $.DRDeviceKPSForXFactor(device, xfactor)
        if (kps > 0) burn.setRequestedBurnSpeed(kps)
    }
    burn.writeLayout(layout)
    var lastState = ''
    var lastPercent = -1
    while (true) {
        var status = burn.status
        var state = val(status, $.DRStatusStateKey)
        var percent = val(status, $.DRStatusPercentCompleteKey)
        var track = val(status, $.DRStatusCurrentTrackKey)
        var numericPercent = percent === null ? -1 : Math.max(0, Math.min(100, Math.round(Number(percent) * (Number(percent) <= 1 ? 100 : 1))))
        var stateText = state === null ? '' : String(state)
        if (stateText !== lastState || numericPercent !== lastPercent) {
            emit({state: stateText, percent: numericPercent, track: track})
            lastState = stateText
            lastPercent = numericPercent
        }
        var lower = stateText.toLowerCase()
        if (lower.indexOf('done') >= 0) return
        if (lower.indexOf('failed') >= 0) {
            var err = val(status, $.DRErrorStatusKey)
            throw new Error(err === null ? 'Disc Recording reported a burn failure' : String(err))
        }
        $.NSThread.sleepForTimeInterval(0.2)
    }
}
"""
    with tempfile.TemporaryDirectory(prefix="mister-companion-native-burn-") as tmp:
        script_path = Path(tmp) / "burn.js"
        script_path.write_text(script, encoding="utf-8")
        command = [
            "/usr/bin/osascript", "-l", "JavaScript", str(script_path),
            str(index), str(image_path), str(speed or 0),
        ]
        proc = subprocess.Popen(
            command,
            cwd=str(image_path.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert proc.stdout is not None
        output: list[str] = []
        for raw in proc.stdout:
            line = raw.strip()
            if not line:
                continue
            output.append(line)
            try:
                import json
                event = json.loads(line)
            except Exception:
                if log_callback and "error" in line.lower():
                    log_callback(line)
                continue
            state = str(event.get("state") or "")
            lower = state.lower()
            percent = int(event.get("percent", -1) or 0) if event.get("percent", -1) != -1 else -1
            track = event.get("track")
            if "prepar" in lower:
                message = "Preparing disc..."
                value = -1
            elif "sessionopen" in lower or ("session" in lower and "open" in lower):
                message = "Opening write session..."
                value = -1
            elif "trackopen" in lower or ("track" in lower and "open" in lower):
                message = f"Opening track {track}..." if track else "Opening track..."
                value = -1
            elif "trackwrite" in lower or ("track" in lower and "write" in lower):
                value = max(0, percent)
                message = f"Writing track {track} — {value}%" if track else f"Writing disc — {value}%"
            elif "trackclose" in lower or "sessionclose" in lower or "finishing" in lower:
                message = "Finalizing disc..."
                value = -1
            elif "done" in lower:
                message = "Disc written successfully — 100%"
                value = 100
            else:
                message = "Burning disc..."
                value = percent if percent >= 0 else -1
            if progress_callback:
                progress_callback(value, "")
        code = proc.wait()
        if code != 0:
            detail = output[-1] if output else f"Native Disc Recording exited with code {code}."
            raise DiscToolError(detail)
    if progress_callback:
        progress_callback(100, "")


def scan_drives() -> list[tuple[str, str]]:
    if _is_macos():
        return _scan_macos_drives()
    if not has_cdrdao():
        return []
    proc = subprocess.run(
        [str(cdrdao_executable()), "scanbus"], cwd=str(cdrdao_executable().parent), env=_tool_env(),
        capture_output=True, text=True, errors="replace", timeout=25,
    )
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    results: list[tuple[str, str]] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("Cdrdao", "SCSI", "Using")):
            continue

        
        
        
        
        m = re.match(r"^([A-Za-z]):[\\/]*\s*:\s*(.*)$", line)
        if m:
            device = m.group(1).upper()
            details = m.group(2).strip().strip("'").strip()
            parts = [part.strip().strip("'") for part in details.split(",") if part.strip().strip("'")]
            label = " ".join(parts) if parts else f"{device}: Optical Drive"
            results.append((device, label))
            continue

        
        m = re.match(r"^(/dev/\S+)\s*:\s*(.*)$", line)
        if m:
            device = m.group(1).strip()
            details = m.group(2).strip().strip("'")
            parts = [part.strip().strip("'") for part in details.split(",") if part.strip().strip("'")]
            label = " ".join(parts) if parts else device
            results.append((device, label))
            continue

        
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
        command, cwd=str(cwd or cdrdao_executable().parent), env=_tool_env(), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        if log_callback:
            log_callback(line.rstrip())
    code = proc.wait()
    if code != 0:
        raise DiscToolError(f"{Path(command[0]).name} exited with code {code}.")


def _linux_mount_points(device: str) -> list[str]:
    if platform.system().lower() != "linux" or not str(device).startswith("/dev/"):
        return []
    wanted = os.path.realpath(str(device))
    mounts: list[str] = []
    try:
        with open("/proc/self/mounts", "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) < 2:
                    continue
                source = parts[0].replace("\\040", " ")
                target = parts[1].replace("\\040", " ")
                if source.startswith("/dev/") and os.path.realpath(source) == wanted:
                    mounts.append(target)
    except OSError:
        pass
    return mounts


def _linux_unmount_optical(device: str) -> None:
    if platform.system().lower() != "linux" or not str(device).startswith("/dev/"):
        return
    device = os.path.realpath(str(device))
    udisksctl = shutil.which("udisksctl")
    umount = shutil.which("umount")
    for _ in range(4):
        mounts = _linux_mount_points(device)
        if not mounts:
            return
        if udisksctl:
            try:
                subprocess.run(
                    [udisksctl, "unmount", "-b", device],
                    capture_output=True, text=True, errors="replace", timeout=15,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        mounts = _linux_mount_points(device)
        if mounts and umount:
            for mount_point in mounts:
                try:
                    subprocess.run(
                        [umount, mount_point],
                        capture_output=True, text=True, errors="replace", timeout=15,
                    )
                except (OSError, subprocess.SubprocessError):
                    pass
        time.sleep(0.25)
    if _linux_mount_points(device):
        raise DiscToolError(
            "The disc is mounted by Linux and could not be released automatically. "
            "Close any file manager windows using the disc and try again."
        )


def _msf_to_frames(value: str) -> int:
    
    
    try:
        match = re.fullmatch(r"(\d+):(\d{1,2})[.:](\d{1,2})", str(value).strip())
        if not match:
            return 0
        minutes, seconds, frames = (int(part) for part in match.groups())
    except (TypeError, ValueError):
        return 0
    return ((minutes * 60) + seconds) * 75 + frames


def rip_disc(
    device: str,
    output_cue: str | Path,
    log_callback=None,
    progress_callback=None,
) -> tuple[Path, Path, Path]:
    if _is_macos():
        return _rip_disc_macos(device, output_cue, log_callback, progress_callback)
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

    
    
    
    
    
    
    workdir = cue.parent
    _linux_unmount_optical(device)
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
        if percent < last_percent:
            return
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

        
        
        
        if stripped.startswith(("Track   Mode", "----", "PQ sub-channel", "Raw P-W", "Cooked R-W", "CD-TEXT", "Using driver", "Cdrdao version")):
            return
        if re.search(r"found\s+\d+\s+q\s+sub-channels?\s+with\s+crc\s+errors?", lower):
            return
        if "warning" in lower:
            return
        if log_callback and "error" in lower:
            log_callback(stripped)

    if platform.system().lower() == "linux":
        done = threading.Event()

        def monitor_size() -> None:
            last_size_percent = -1
            while not done.wait(0.2):
                try:
                    size = bin_path.stat().st_size
                except OSError:
                    continue
                lengths = dict(track_lengths)
                total = sum(lengths.values())
                if not total or size <= 0:
                    continue
                copied = min(total, size // 2352)
                overall = min(99, int(copied * 100 / total))
                if overall == last_size_percent:
                    continue
                last_size_percent = overall
                before = 0
                track_no = 1
                track_length = total
                for number in sorted(lengths):
                    length = lengths[number]
                    if copied < before + length or number == max(lengths):
                        track_no = number
                        track_length = max(1, length)
                        break
                    before += length
                within = max(0, min(track_length, copied - before))
                track_percent = min(100, int(within * 100 / track_length))
                report_progress(overall, f"Ripping track {track_no} of {max(lengths)} — {track_percent}%")

        monitor = threading.Thread(target=monitor_size, daemon=True)
        monitor.start()
        try:
            _run_streaming(command, rip_output, workdir)
        finally:
            done.set()
            monitor.join(timeout=1)
    else:
        _run_streaming(command, rip_output, workdir)

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

    
    
    bin_path.unlink(missing_ok=True)
    converted.replace(bin_path)
    text = cue.read_text(encoding="utf-8", errors="replace")
    cue.write_text(text.replace(converted.name, bin_path.name), encoding="utf-8")
    
    
    toc_path.unlink(missing_ok=True)
    return cue, bin_path, toc_path


def _burn_output_handler(line: str, log_callback=None, progress_callback=None, state=None) -> None:
    stripped = line.strip()
    if not stripped:
        return
    state = state if state is not None else {}
    m = re.search(r"Wrote\s+(\d+(?:\.\d+)?)\s+of\s+(\d+(?:\.\d+)?)\s+MB", stripped, re.IGNORECASE)
    if m:
        done = float(m.group(1))
        total = float(m.group(2))
        percent = max(0, min(100, int(done * 100 / total))) if total > 0 else 0
        state["percent"] = max(state.get("percent", 0), percent)
        if progress_callback:
            progress_callback(state["percent"], "")
        return
    lower = stripped.lower()
    if "lead-out" in lower or "leadout" in lower:
        if progress_callback:
            progress_callback(max(99, state.get("percent", 0)), "")
        return
    if "error" in lower and log_callback:
        log_callback(stripped)

def _cdrdao_needs_raw_driver(lines: list[str]) -> bool:
    text = "\n".join(lines).lower()
    return (
        "cannot set write parameters mode page" in text
        or "cannot setup write parameters for session-at-once mode" in text
    )


def _run_cdrdao_write_with_compatibility(command: list[str], output_callback, cwd: Path) -> None:
    """Run cdrdao normally, retrying once with generic-mmc-raw for the known SAO incompatibility."""
    captured: list[str] = []

    def capture(line: str) -> None:
        captured.append(line.rstrip())
        output_callback(line)

    try:
        _run_streaming(command, capture, cwd)
        return
    except DiscToolError:
        if not _cdrdao_needs_raw_driver(captured):
            raise

    output_callback("Standard write mode is unsupported by this drive. Retrying in compatibility mode...")
    retry_command = list(command)
    # cdrdao accepts --driver before the TOC argument. Insert it immediately after the device pair.
    try:
        device_index = retry_command.index("--device")
        insert_at = device_index + 2
    except ValueError:
        insert_at = max(1, len(retry_command) - 1)
    retry_command[insert_at:insert_at] = ["--driver", "generic-mmc-raw"]
    _run_streaming(retry_command, output_callback, cwd)


def burn_cue(device: str, cue_path: str | Path, speed: int | None = None, log_callback=None, progress_callback=None) -> None:
    cue = Path(cue_path)
    if _is_macos():
        if not has_native_macos_disc_backend():
            raise DiscToolError("The macOS Disc Recording backend is unavailable.")
        if not cue.is_file():
            raise FileNotFoundError(cue)
        index, _raw = _macos_parse_device(device)
        if log_callback:
            log_callback("Burning disc...")
        if progress_callback:
            progress_callback(0, "")
        _run_native_macos_burn(index, cue, speed, log_callback, progress_callback)
        if log_callback:
            log_callback("Disc written successfully.")
        return
    if not has_cdrdao():
        raise DiscToolError("Install cdrdao first.")
    if not cue.is_file():
        raise FileNotFoundError(cue)
    if log_callback:
        log_callback("Burning disc...")
    if progress_callback:
        progress_callback(0, "")
    _linux_unmount_optical(device)
    with tempfile.TemporaryDirectory(prefix="mister-companion-burn-") as tmp:
        toc = Path(tmp) / "image.toc"
        _run_streaming([str(cue2toc_executable()), "-q", "-o", str(toc), str(cue)], log_callback, cue.parent)
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
        _run_cdrdao_write_with_compatibility(command, output, cue.parent)
    if progress_callback:
        progress_callback(100, "")
    if log_callback:
        log_callback("Disc written successfully.")



_JOLIET_COMPONENT_LIMIT = 64
_MSU_ROM_EXTS = {".sfc", ".smc"}
_MD_ROM_EXTS = {".md", ".gen", ".mdx", ".bin"}


def _joliet_name_too_long(name: str) -> bool:
    # Joliet level 3 allows at most 64 UCS-2 characters per path component.
    return len(name) > _JOLIET_COMPONENT_LIMIT


def _short_disc_name(stem: str, suffix: str, reserved: set[str], max_len: int = _JOLIET_COMPONENT_LIMIT) -> str:
    digest = hashlib.sha1((stem + suffix).encode("utf-8", errors="replace")).hexdigest()[:6].upper()
    tail = f"_{digest}{suffix}"
    keep = max(1, max_len - len(tail))
    candidate = stem[:keep] + tail
    n = 1
    while candidate.casefold() in reserved:
        extra = f"_{n}"
        keep = max(1, max_len - len(tail) - len(extra))
        candidate = stem[:keep] + extra + tail
        n += 1
    reserved.add(candidate.casefold())
    return candidate


def _parse_cue_file_references(text: str) -> list[str]:
    refs = []
    pattern = re.compile(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))\s+.+$', re.IGNORECASE)
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            refs.append(match.group(1) or match.group(2))
    return refs


def _rewrite_cue_file_references(text: str, replacements: dict[str, str]) -> str:
    pattern = re.compile(r'^(\s*FILE\s+)(?:"([^"]+)"|(\S+))(\s+.+)$', re.IGNORECASE)
    out = []
    for line in text.splitlines(keepends=True):
        newline = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
        body = line[:-len(newline)] if newline else line
        match = pattern.match(body)
        if not match:
            out.append(line)
            continue
        ref = match.group(2) or match.group(3)
        replacement = replacements.get(ref)
        if replacement is None:
            replacement = replacements.get(Path(ref).name)
        if replacement is None:
            out.append(line)
            continue
        out.append(f'{match.group(1)}"{replacement}"{match.group(4)}{newline}')
    return "".join(out)


def _prepare_joliet_name_map(source: Path, log_callback=None):
    """Return (disc_names, cue_overrides) without touching the user's source files.

    disc_names maps source Paths to Joliet names. cue_overrides contains rewritten
    CUE text for MD+ sets whose referenced files had to be renamed.
    """
    files = [p for p in source.iterdir() if p.is_file()]
    disc_names = {p: p.name for p in files}
    cue_overrides: dict[Path, str] = {}
    reserved = {p.name.casefold() for p in files if not _joliet_name_too_long(p.name)}
    handled: set[Path] = set()

    def report(path: Path, new_name: str):
        if path.name != new_name and log_callback:
            log_callback(f'Joliet filename limit exceeded: "{path.name}" -> "{new_name}"')

    # SNES MSU-1: keep one common basename for ROM, .msu and numbered PCM tracks.
    for msu in [p for p in files if p.suffix.lower() == ".msu"]:
        base = msu.stem
        related = []
        for item in files:
            lower_suffix = item.suffix.lower()
            if item.stem == base and lower_suffix in (_MSU_ROM_EXTS | {".msu"}):
                related.append((item, item.suffix))
                continue
            match = re.fullmatch(re.escape(base) + r"-(\d+)\.pcm", item.name, re.IGNORECASE)
            if match:
                related.append((item, f"-{match.group(1)}{item.suffix}"))
        if not related or not any(_joliet_name_too_long(item.name) for item, _suffix in related):
            handled.update(item for item, _suffix in related)
            continue
        longest_tail = max(len(tail) for _item, tail in related)
        digest = hashlib.sha1(base.encode("utf-8", errors="replace")).hexdigest()[:6].upper()
        tail_room = 1 + len(digest) + longest_tail
        keep = max(1, _JOLIET_COMPONENT_LIMIT - tail_room)
        short_base = f"{base[:keep]}_{digest}"
        if log_callback:
            log_callback(f'MSU-1 set uses a Joliet-safe temporary basename: "{base}" -> "{short_base}"')
        for item, tail in related:
            new_name = short_base + tail
            # The shared basename must remain identical, so a collision means we cannot rename safely.
            if new_name.casefold() in reserved and new_name.casefold() != item.name.casefold():
                raise DiscToolError(f'Cannot create a unique Joliet-safe MSU-1 filename for "{item.name}".')
            reserved.add(new_name.casefold())
            disc_names[item] = new_name
            handled.add(item)
            report(item, new_name)

    # MD+: ROM and CUE keep a common basename; every renamed CUE reference is rewritten.
    for cue in [p for p in files if p.suffix.lower() == ".cue"]:
        try:
            cue_text = cue.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            cue_text = cue.read_text(encoding="latin-1")
        refs = _parse_cue_file_references(cue_text)
        ref_paths = []
        for ref in refs:
            ref_path = source / Path(ref).name
            if ref_path.is_file():
                ref_paths.append((ref, ref_path))

        referenced_paths = {p.resolve() for _ref, p in ref_paths}
        matching_roms = [
            p for p in files
            if p.stem == cue.stem and p.suffix.lower() in _MD_ROM_EXTS and p != cue
            and p.resolve() not in referenced_paths
        ]
        md_related = [cue] + matching_roms + [p for _ref, p in ref_paths]
        if not any(_joliet_name_too_long(p.name) for p in md_related):
            handled.update(md_related)
            continue

        # Only treat this as MD+ when there is a matching ROM. A standalone CUE may be unrelated data.
        if not matching_roms:
            continue

        common_suffixes = [cue.suffix] + [p.suffix for p in matching_roms]
        longest_common_tail = max(len(x) for x in common_suffixes)
        digest = hashlib.sha1(cue.stem.encode("utf-8", errors="replace")).hexdigest()[:6].upper()
        keep = max(1, _JOLIET_COMPONENT_LIMIT - (1 + len(digest) + longest_common_tail))
        short_base = f"{cue.stem[:keep]}_{digest}"
        if log_callback:
            log_callback(f'MD+ set uses a Joliet-safe temporary basename: "{cue.stem}" -> "{short_base}"')

        cue_new = short_base + cue.suffix
        disc_names[cue] = cue_new
        handled.add(cue)
        report(cue, cue_new)
        for rom in matching_roms:
            new_name = short_base + rom.suffix
            disc_names[rom] = new_name
            handled.add(rom)
            report(rom, new_name)

        replacements: dict[str, str] = {}
        for ref, ref_path in ref_paths:
            handled.add(ref_path)
            if _joliet_name_too_long(ref_path.name):
                new_name = _short_disc_name(ref_path.stem, ref_path.suffix, reserved)
                disc_names[ref_path] = new_name
                replacements[ref] = new_name
                replacements[Path(ref).name] = new_name
                report(ref_path, new_name)
            else:
                replacements[ref] = disc_names[ref_path]
                replacements[Path(ref).name] = disc_names[ref_path]
        if replacements:
            rewritten = _rewrite_cue_file_references(cue_text, replacements)
            # Validate every rewritten FILE target exists in the on-disc name set.
            available = {name.casefold() for name in disc_names.values()}
            missing = [ref for ref in _parse_cue_file_references(rewritten) if Path(ref).name.casefold() not in available]
            if missing:
                raise DiscToolError(f'MD+ CUE rewrite failed; missing referenced file: {missing[0]}')
            cue_overrides[cue] = rewritten
            if log_callback:
                log_callback(f'Updated temporary CUE references in "{cue_new}".')

    # Never silently truncate an unknown long filename; that could break a game-specific relationship.
    for item in files:
        if _joliet_name_too_long(disc_names[item]) and item not in handled:
            raise DiscToolError(
                f'"{item.name}" exceeds the Joliet filename limit and is not part of a recognized '
                "MSU-1 or MD+ naming relationship, so Companion will not rename it automatically."
            )

    return disc_names, cue_overrides


def create_iso9660_from_folder(source_folder: str | Path, output_iso: str | Path, volume_id: str | None = None, log_callback=None) -> Path:
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

    disc_names, cue_overrides = _prepare_joliet_name_map(source, log_callback=log_callback)
    requested_label = (volume_id or "MISTER_DISC").strip().upper()
    safe_label = re.sub(r"[^A-Z0-9_]", "_", requested_label)[:32].strip("_") or "MISTER_DISC"
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, vol_ident=safe_label)
    used_iso_names: set[str] = set()
    rewrite_tmp = tempfile.TemporaryDirectory(prefix="mister-companion-cue-rewrite-") if cue_overrides else None
    try:
        rewritten_paths: dict[Path, Path] = {}
        if rewrite_tmp:
            rewrite_root = Path(rewrite_tmp.name)
            for cue_path, cue_text in cue_overrides.items():
                staged = rewrite_root / cue_path.name
                staged.write_text(cue_text, encoding="utf-8", newline="")
                rewritten_paths[cue_path] = staged

        for index, path in enumerate(files, start=1):
            # ISO9660 identifiers are only compatibility aliases here; Joliet carries the
            # real on-disc filename. Keep aliases deliberately short so pycdlib never
            # rejects a valid MSU-1/MD+ filename because of the ISO9660 side.
            ext = re.sub(r"[^A-Z0-9]", "", path.suffix.upper().lstrip("."))[:3]
            candidate = f"F{index:07d}" + (("." + ext) if ext else "")
            while candidate in used_iso_names:
                index += 1
                candidate = f"F{index:07d}" + (("." + ext) if ext else "")
            used_iso_names.add(candidate)
            iso_path = f"/{candidate};1"
            joliet_path = "/" + disc_names[path]
            source_path = rewritten_paths.get(path, path)
            iso.add_file(str(source_path), iso_path=iso_path, joliet_path=joliet_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        iso.write(str(output))
    finally:
        iso.close()
        if rewrite_tmp:
            rewrite_tmp.cleanup()
    return output


def burn_iso9660_folder(device: str, source_folder: str | Path, speed: int | None = None, volume_id: str | None = None, log_callback=None, progress_callback=None) -> None:
    if _is_macos():
        if not has_native_macos_disc_backend():
            raise DiscToolError("The macOS Disc Recording backend is unavailable.")
        if progress_callback:
            progress_callback(0, "Creating ISO 9660 data image...")
        with tempfile.TemporaryDirectory(prefix="mister-companion-data-disc-") as tmp:
            iso_path = create_iso9660_from_folder(source_folder, Path(tmp) / "data.iso", volume_id=volume_id, log_callback=log_callback)
            index, _raw = _macos_parse_device(device)
            if progress_callback:
                progress_callback(0, "ISO 9660 image ready. Starting burn...")
            _run_native_macos_burn(index, iso_path, speed, log_callback, progress_callback)
        return
    if not has_cdrdao():
        raise DiscToolError("Install cdrdao first.")
    if progress_callback:
        progress_callback(0, "Creating ISO 9660 data image...")
    with tempfile.TemporaryDirectory(prefix="mister-companion-data-disc-") as tmp:
        tmpdir = Path(tmp)
        iso_path = create_iso9660_from_folder(source_folder, tmpdir / "data.iso", volume_id=volume_id, log_callback=log_callback)
        toc_path = tmpdir / "data.toc"
        toc_path.write_text(
            'CD_ROM\n\nTRACK MODE1\nNO COPY\nDATAFILE "data.iso"\n',
            encoding="ascii",
        )
        if progress_callback:
            progress_callback(0, "ISO 9660 image ready. Starting burn...")
        _linux_unmount_optical(device)
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
        _run_cdrdao_write_with_compatibility(command, output, tmpdir)
    if progress_callback:
        progress_callback(100, "Disc written successfully — 100%")

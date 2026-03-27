from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Callable

import requests


APP_NAME = "MiSTer Companion"

BASE_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = BASE_DIR / "tools"
BALENA_DIR = TOOLS_DIR / "balena-cli"
MR_FUSION_DIR = TOOLS_DIR / "mr-fusion"

BALENA_REPO = "balena-io/balena-cli"
MR_FUSION_REPO = "MiSTer-devel/mr-fusion"

GITHUB_API_BASE = "https://api.github.com/repos"
REQUEST_HEADERS = {
    "User-Agent": APP_NAME,
    "Accept": "application/vnd.github+json",
}

LogCallback = Callable[[str], None]


def _noop_log(_: str) -> None:
    pass


def _log(log_callback: LogCallback | None, message: str) -> None:
    (log_callback or _noop_log)(message)


def is_flash_supported() -> bool:
    return platform.system() in {"Windows", "Linux"}


def get_platform_key() -> str:
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Linux":
        return "linux"
    if system == "Darwin":
        return "macos"
    return "unsupported"


def get_arch_key() -> str:
    machine = platform.machine().lower()

    if machine in {"x86_64", "amd64"}:
        return "x64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"

    raise RuntimeError(f"Unsupported CPU architecture: {machine}")


def is_admin_windows() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def is_root_linux() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def _ensure_flash_privileges() -> None:
    system = platform.system()

    if system == "Windows":
        if not is_admin_windows():
            raise RuntimeError(
                "Administrator privileges are required to flash an SD card.\n\n"
                "Please restart MiSTer Companion as Administrator and try again."
            )

    elif system == "Linux":
        if not is_root_linux():
            if shutil.which("pkexec"):
                raise RuntimeError(
                    "Root privileges are required to flash an SD card.\n\n"
                    "Please run MiSTer Companion with pkexec or sudo and try again."
                )
            raise RuntimeError(
                "Root privileges are required to flash an SD card.\n\n"
                "Please run MiSTer Companion with sudo and try again."
            )


def ensure_tools_dirs() -> None:
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    BALENA_DIR.mkdir(parents=True, exist_ok=True)
    MR_FUSION_DIR.mkdir(parents=True, exist_ok=True)


def _get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    return session


def _github_latest_release(repo: str) -> dict:
    url = f"{GITHUB_API_BASE}/{repo}/releases/latest"
    session = _get_session()
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def _download_file(
    url: str,
    dest_path: Path,
    log_callback: LogCallback | None = None,
) -> Path:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    _log(log_callback, f"Downloading {dest_path.name}...")

    session = _get_session()
    with session.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()

        total_bytes = int(response.headers.get("Content-Length", 0))
        written_bytes = 0
        last_logged_percent = -1

        with dest_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue

                f.write(chunk)
                written_bytes += len(chunk)

                if total_bytes > 0:
                    percent = int((written_bytes / total_bytes) * 100)
                    if percent >= last_logged_percent + 10:
                        last_logged_percent = percent
                        _log(log_callback, f"{dest_path.name}: {percent}%")

    _log(log_callback, f"Finished downloading {dest_path.name}")
    return dest_path


def _clear_directory_contents(folder: Path) -> None:
    if not folder.exists():
        return

    for item in folder.iterdir():
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            try:
                item.unlink()
            except FileNotFoundError:
                pass


def _safe_extract_tar(archive_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "r:*") as tar:
        resolved_dest = dest_dir.resolve()

        for member in tar.getmembers():
            member_path = dest_dir / member.name
            resolved_member = member_path.resolve()
            if not str(resolved_member).startswith(str(resolved_dest)):
                raise RuntimeError(f"Unsafe path in tar archive: {member.name}")

        tar.extractall(dest_dir)


def _extract_zip(archive_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(dest_dir)


def _extract_archive(
    archive_path: Path,
    dest_dir: Path,
    log_callback: LogCallback | None = None,
) -> None:
    _log(log_callback, f"Extracting {archive_path.name}...")

    name = archive_path.name.lower()
    if name.endswith((".tar.gz", ".tgz", ".tar")):
        _safe_extract_tar(archive_path, dest_dir)
    elif name.endswith(".zip"):
        _extract_zip(archive_path, dest_dir)
    else:
        raise RuntimeError(f"Unsupported archive format: {archive_path.name}")

    _log(log_callback, f"Finished extracting {archive_path.name}")


def _make_executable(path: Path) -> None:
    if not path.exists():
        return

    current_mode = path.stat().st_mode
    path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _find_first_matching_file(root: Path, pattern: str) -> Path | None:
    matches = sorted(p for p in root.rglob(pattern) if p.is_file())
    return matches[0] if matches else None


def has_balena_cli() -> bool:
    try:
        get_balena_executable()
        return True
    except Exception:
        return False


def has_mr_fusion_image() -> bool:
    try:
        get_mr_fusion_image()
        return True
    except Exception:
        return False


def get_balena_executable() -> Path:
    platform_key = get_platform_key()

    if platform_key == "windows":
        exe = _find_first_matching_file(BALENA_DIR, "balena.cmd")
        if exe:
            return exe

    if platform_key == "linux":
        exe = _find_first_matching_file(BALENA_DIR, "balena")
        if exe:
            return exe

    raise RuntimeError("balena CLI executable not found. Download it first.")


def get_mr_fusion_image() -> Path:
    image = _find_first_matching_file(MR_FUSION_DIR, "*.img")
    if image:
        return image

    raise RuntimeError("Mr. Fusion image not found. Download it first.")


def _select_balena_asset(release_data: dict) -> dict:
    platform_key = get_platform_key()
    arch_key = get_arch_key()

    if platform_key not in {"windows", "linux"}:
        raise RuntimeError("Flash Mr. Fusion is only supported on Windows and Linux.")

    expected_fragment = f"{platform_key}-{arch_key}-standalone.tar.gz"
    assets = release_data.get("assets", [])

    for asset in assets:
        name = asset.get("name", "").lower()
        if expected_fragment in name:
            return asset

    raise RuntimeError(
        f"Could not find a balena CLI asset for {platform_key}/{arch_key}."
    )


def _select_mr_fusion_asset(release_data: dict) -> dict:
    assets = release_data.get("assets", [])

    for asset in assets:
        lower_name = asset.get("name", "").lower()
        if re.fullmatch(r"mr-fusion-v[\d.]+\.img\.zip", lower_name):
            return asset

    for asset in assets:
        lower_name = asset.get("name", "").lower()
        if lower_name.endswith(".img.zip") and "mr-fusion" in lower_name:
            return asset

    raise RuntimeError("Could not find a Mr. Fusion .img.zip asset.")


def ensure_balena_cli(
    force_download: bool = False,
    log_callback: LogCallback | None = None,
) -> Path:
    if not is_flash_supported():
        raise RuntimeError("Flash Mr. Fusion is not available on macOS yet.")

    ensure_tools_dirs()

    if not force_download:
        try:
            exe = get_balena_executable()
            if platform.system() == "Linux":
                _make_executable(exe)
            _log(log_callback, f"Using existing balena CLI: {exe}")
            return exe
        except Exception:
            pass

    _log(log_callback, "Checking latest balena CLI release...")
    release_data = _github_latest_release(BALENA_REPO)
    asset = _select_balena_asset(release_data)

    archive_path = BALENA_DIR / asset["name"]

    _clear_directory_contents(BALENA_DIR)
    _download_file(asset["browser_download_url"], archive_path, log_callback)
    _extract_archive(archive_path, BALENA_DIR, log_callback)

    exe = get_balena_executable()
    if platform.system() == "Linux":
        _make_executable(exe)

    _log(log_callback, f"balena CLI ready: {exe}")
    return exe


def ensure_mr_fusion_image(
    force_download: bool = False,
    log_callback: LogCallback | None = None,
) -> Path:
    if not is_flash_supported():
        raise RuntimeError("Flash Mr. Fusion is not available on macOS yet.")

    ensure_tools_dirs()

    if not force_download:
        try:
            image = get_mr_fusion_image()
            _log(log_callback, f"Using existing Mr. Fusion image: {image}")
            return image
        except Exception:
            pass

    _log(log_callback, "Checking latest Mr. Fusion release...")
    release_data = _github_latest_release(MR_FUSION_REPO)
    asset = _select_mr_fusion_asset(release_data)

    archive_path = MR_FUSION_DIR / asset["name"]

    _clear_directory_contents(MR_FUSION_DIR)
    _download_file(asset["browser_download_url"], archive_path, log_callback)
    _extract_archive(archive_path, MR_FUSION_DIR, log_callback)

    image = get_mr_fusion_image()
    _log(log_callback, f"Mr. Fusion image ready: {image}")
    return image


def _run_subprocess(
    cmd: list[str],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    startupinfo = None
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        startupinfo=startupinfo,
    )


def _size_text_to_bytes(size_text: str) -> int | None:
    match = re.match(r"^\s*([\d.]+)\s*([KMGTP]?B)\s*$", size_text, re.IGNORECASE)
    if not match:
        return None

    value = float(match.group(1))
    unit = match.group(2).upper()

    multipliers = {
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
        "TB": 1024 ** 4,
        "PB": 1024 ** 5,
    }

    return int(value * multipliers.get(unit, 1))


def _parse_available_drives_output(output: str) -> list[dict]:
    drives: list[dict] = []

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return drives

    for line in lines:
        upper_line = line.upper()
        if "DEVICE" in upper_line and "SIZE" in upper_line:
            continue

        match = re.match(
            r"^(?P<device>\S+)\s+(?P<size>[\d.]+\s*[KMGTP]?B)\s+(?P<description>.+)$",
            line,
            re.IGNORECASE,
        )
        if not match:
            continue

        device = match.group("device").strip()
        size_text = match.group("size").strip()
        description = match.group("description").strip()

        drives.append(
            {
                "device": device,
                "size": _size_text_to_bytes(size_text),
                "description": description,
            }
        )

    return drives


def list_available_drives(
    log_callback: LogCallback | None = None,
) -> list[dict]:
    if not is_flash_supported():
        return []

    if not has_balena_cli():
        raise RuntimeError("balena CLI is not downloaded yet. Download it first.")

    balena_exe = get_balena_executable()
    _log(log_callback, "Refreshing available drives...")

    result = _run_subprocess(
        [str(balena_exe), "util", "available-drives"],
        cwd=balena_exe.parent,
    )

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(stderr or "Failed to get available drives.")

    stdout = (result.stdout or "").strip()
    if not stdout:
        return []

    _log(log_callback, "Raw balena drive output:")
    for line in stdout.splitlines():
        _log(log_callback, line)

    drives = _parse_available_drives_output(stdout)
    _log(log_callback, f"Parsed {len(drives)} drive(s).")
    return drives


def flash_image(
    image_path: str | Path,
    drive: str,
    log_callback: LogCallback | None = None,
) -> None:
    if not is_flash_supported():
        raise RuntimeError("Flash Mr. Fusion is not available on macOS yet.")

    _ensure_flash_privileges()

    image_path = Path(image_path)
    if not image_path.exists():
        raise RuntimeError(f"Image file not found: {image_path}")

    if not drive:
        raise RuntimeError("No drive selected.")

    if not has_balena_cli():
        raise RuntimeError("balena CLI is not downloaded yet. Download it first.")

    balena_exe = get_balena_executable()

    cmd = [
        str(balena_exe),
        "local",
        "flash",
        str(image_path),
        "--drive",
        drive,
        "--yes",
    ]

    _log(log_callback, f"Starting flash: {image_path.name}")
    _log(log_callback, f"Target drive: {drive}")

    startupinfo = None
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(balena_exe.parent),
        startupinfo=startupinfo,
        bufsize=1,
    )

    output_lines: list[str] = []

    try:
        assert process.stdout is not None

        for raw_line in process.stdout:
            line = raw_line.strip()
            if line:
                output_lines.append(line)
                _log(log_callback, line)

        return_code = process.wait()
        combined_output = "\n".join(output_lines).lower()

        error_markers = [
            "eacces",
            "couldn't clean the drive",
            "could not clean the drive",
            "try running this command with elevated privileges",
            "administrator privileges",
            "access is denied",
            "permission denied",
            "error:",
        ]

        if return_code != 0:
            raise RuntimeError(f"Flash failed with exit code {return_code}.")

        for marker in error_markers:
            if marker in combined_output:
                if platform.system() == "Windows":
                    raise RuntimeError(
                        "Flash failed. balena CLI reported a permission or drive access error.\n\n"
                        "Run MiSTer Companion as Administrator and try again."
                    )
                if platform.system() == "Linux":
                    raise RuntimeError(
                        "Flash failed. balena CLI reported a permission or drive access error.\n\n"
                        "Run MiSTer Companion with sudo or pkexec and try again."
                    )
                raise RuntimeError(
                    "Flash failed. balena CLI reported a permission or drive access error."
                )

        _log(log_callback, "Flash completed successfully.")
    finally:
        if process.stdout is not None:
            process.stdout.close()
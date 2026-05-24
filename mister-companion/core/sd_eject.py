from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

LogCallback = Callable[[str], None]

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def clean_output(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def _noop_log(_: str) -> None:
    pass


def _log(log_callback: LogCallback | None, message: str) -> None:
    (log_callback or _noop_log)(message)


def _clean_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()

    if platform.system() in {"Linux", "Darwin"}:
        original_ld_library_path = env.get("LD_LIBRARY_PATH_ORIG")

        if original_ld_library_path is not None:
            if original_ld_library_path:
                env["LD_LIBRARY_PATH"] = original_ld_library_path
            else:
                env.pop("LD_LIBRARY_PATH", None)
        else:
            env.pop("LD_LIBRARY_PATH", None)

        env.pop("LD_PRELOAD", None)

    return env


def _run_command(
    cmd: list[str],
    log_callback: LogCallback | None = None,
) -> subprocess.CompletedProcess[str]:
    startupinfo = None
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        startupinfo=startupinfo,
        env=_clean_subprocess_env(),
    )

    for output in (result.stdout, result.stderr):
        if not output:
            continue
        for line in output.splitlines():
            cleaned_line = clean_output(line).strip()
            if cleaned_line:
                _log(log_callback, cleaned_line)

    return result


def _run_quiet(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    startupinfo = None
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        startupinfo=startupinfo,
        env=_clean_subprocess_env(),
    )


def _windows_drive_letter_from_path(path_text: str) -> str:
    drive = Path(path_text).drive
    if not drive:
        match = re.match(r"^([A-Za-z]:)", str(path_text).strip())
        if match:
            drive = match.group(1)

    drive = drive.strip().upper()
    if not re.match(r"^[A-Z]:$", drive):
        return ""

    return drive


def _eject_windows_path(
    path_text: str,
    log_callback: LogCallback | None = None,
) -> bool:
    drive_letter = _windows_drive_letter_from_path(path_text)
    if not drive_letter:
        _log(log_callback, "Unable to determine the Windows drive letter.")
        return False

    script = f"""
$ErrorActionPreference = 'Stop'
$driveLetter = '{drive_letter}'
Write-Output "Ejecting $driveLetter..."
$shell = New-Object -ComObject Shell.Application
$item = $shell.Namespace(17).ParseName($driveLetter)
if ($item -eq $null) {{
    Write-Output "Unable to find shell item for $driveLetter."
    exit 2
}}
$item.InvokeVerb('Eject')
Start-Sleep -Seconds 2
exit 0
"""

    result = _run_command(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        log_callback,
    )
    return result.returncode == 0


def _linux_mount_source(path_text: str) -> str:
    if not shutil.which("findmnt"):
        return ""

    result = _run_quiet(["findmnt", "-n", "-o", "SOURCE", "--target", path_text])
    if result.returncode != 0:
        return ""

    return (result.stdout or "").splitlines()[0].strip() if result.stdout else ""


def _linux_parent_block_device(source: str) -> str:
    source = str(source or "").strip()
    if not source.startswith("/dev/"):
        return ""

    if not shutil.which("lsblk"):
        return source

    result = _run_quiet(["lsblk", "-no", "PKNAME", source])
    parent = (result.stdout or "").strip().splitlines()[0].strip() if result.stdout else ""
    if parent:
        return f"/dev/{parent}"

    return source


def _eject_linux_path(
    path_text: str,
    log_callback: LogCallback | None = None,
) -> bool:
    source = _linux_mount_source(path_text)
    if not source:
        _log(log_callback, "Unable to determine the mounted block device.")
        return False

    parent_device = _linux_parent_block_device(source)
    if not parent_device:
        _log(log_callback, "Unable to determine the parent block device.")
        return False

    if shutil.which("udisksctl"):
        _log(log_callback, f"Unmounting {source}...")
        _run_command(["udisksctl", "unmount", "-b", source], log_callback)

        _log(log_callback, f"Powering off {parent_device}...")
        result = _run_command(["udisksctl", "power-off", "-b", parent_device], log_callback)
        return result.returncode == 0

    _log(log_callback, f"Unmounting {path_text}...")
    unmount_result = _run_command(["umount", path_text], log_callback)

    if shutil.which("eject"):
        _log(log_callback, f"Ejecting {parent_device}...")
        eject_result = _run_command(["eject", parent_device], log_callback)
        return eject_result.returncode == 0

    return unmount_result.returncode == 0


def _eject_macos_path(
    path_text: str,
    log_callback: LogCallback | None = None,
) -> bool:
    if not shutil.which("diskutil"):
        _log(log_callback, "diskutil is not available.")
        return False

    _log(log_callback, "Ejecting SD card...")
    result = _run_command(["diskutil", "eject", path_text], log_callback)
    return result.returncode == 0


def eject_sd_card_path(
    path_text: str,
    log_callback: LogCallback | None = None,
) -> bool:
    path_text = str(path_text or "").strip()
    if not path_text:
        _log(log_callback, "No SD card path selected.")
        return False

    system = platform.system()

    if system == "Windows":
        return _eject_windows_path(path_text, log_callback)

    if system == "Linux":
        return _eject_linux_path(path_text, log_callback)

    if system == "Darwin":
        return _eject_macos_path(path_text, log_callback)

    _log(log_callback, "SD card eject is not supported on this platform.")
    return False

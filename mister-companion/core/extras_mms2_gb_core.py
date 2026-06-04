import posixpath
import re
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests

from core.extras_common import (
    _ensure_local_dir,
    _ensure_remote_dir,
    _path_exists,
    _path_exists_local,
    _quote,
    _remove_glob,
    _remove_if_empty_dir,
    _remove_if_empty_dir_local,
    _remove_local_glob,
    _remove_local_path,
    _write_local_bytes,
    _write_remote_bytes,
)


MMS2_GB_RELEASES_URL = "https://github.com/Heber-co-uk/Gameboy_MiSTer_Cart/tree/master/releases"
MMS2_GB_RAW_RELEASE_BASE_URL = "https://raw.githubusercontent.com/Heber-co-uk/Gameboy_MiSTer_Cart/master/releases"

MMS2_GB_MGL_URL = "https://raw.githubusercontent.com/Anime0t4ku/mister-companion/main/assets/Load%20GB-GBC%20Cartridge.mgl"
MMS2_GB_CFG_URL = "https://raw.githubusercontent.com/Anime0t4ku/mister-companion/main/assets/MMS2_GB_Cart.CFG"

MMS2_GB_REMOTE_DIR = "/media/fat/MMS2"
MMS2_GB_RBF_PATTERN = "/media/fat/MMS2/Gameboy_*.rbf"
MMS2_GB_MGL_PATH = "/media/fat/Load GB-GBC Cartridge.mgl"
MMS2_GB_CFG_PATH = "/media/fat/config/MMS2_GB_Cart.CFG"

MMS2_GB_FILENAME_RE = re.compile(r"Gameboy_(\d{8})\.rbf$", re.IGNORECASE)


def _download_bytes(url: str, timeout: int = 90) -> bytes:
    response = requests.get(
        url,
        headers={"User-Agent": "MiSTer-Companion"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.content


def _fetch_latest_mms2_gb_release() -> dict:
    response = requests.get(
        MMS2_GB_RELEASES_URL,
        headers={
            "User-Agent": "MiSTer-Companion",
            "Accept": "text/html",
        },
        timeout=30,
    )
    response.raise_for_status()

    candidates = {}
    href_pattern = re.compile(r'href="([^"]+)"')

    for match in href_pattern.finditer(response.text):
        href = unquote(match.group(1))
        filename = posixpath.basename(href.split("?", 1)[0])
        file_match = MMS2_GB_FILENAME_RE.match(filename)
        if not file_match:
            continue

        date = file_match.group(1)
        candidates[date] = filename

    if not candidates:
        raise RuntimeError("Unable to find Gameboy_YYYYMMDD.rbf in the MMS2 GB releases folder.")

    latest_date = sorted(candidates.keys())[-1]
    latest_filename = candidates[latest_date]

    return {
        "version": latest_date,
        "filename": latest_filename,
        "rbf_url": urljoin(MMS2_GB_RAW_RELEASE_BASE_URL + "/", latest_filename),
    }


def _latest_installed_mms2_gb_date_from_names(names: list[str]) -> str:
    dates = []

    for name in names:
        filename = posixpath.basename(str(name).strip())
        match = MMS2_GB_FILENAME_RE.match(filename)
        if match:
            dates.append(match.group(1))

    return sorted(dates)[-1] if dates else ""


def _read_installed_mms2_gb_date(connection) -> str:
    command = (
        f"for f in {MMS2_GB_RBF_PATTERN}; do "
        f'[ -e "$f" ] && basename "$f"; '
        f"done"
    )
    output = connection.run_command(command) or ""
    return _latest_installed_mms2_gb_date_from_names(output.splitlines())


def _read_installed_mms2_gb_date_local(sd_root: str) -> str:
    root = Path(str(sd_root or "")).expanduser()
    if not root.exists() or not root.is_dir():
        return ""

    mms2_dir = root / "MMS2"
    if not mms2_dir.exists() or not mms2_dir.is_dir():
        return ""

    return _latest_installed_mms2_gb_date_from_names(
        [path.name for path in mms2_dir.glob("Gameboy_*.rbf")]
    )


def _build_status(installed_date: str, mgl_exists: bool, cfg_exists: bool, check_latest: bool) -> dict:
    installed = bool(installed_date and mgl_exists and cfg_exists)
    partial = bool(installed_date or mgl_exists or cfg_exists) and not installed

    latest_version = ""
    latest_error = ""
    update_available = False

    if check_latest:
        try:
            latest = _fetch_latest_mms2_gb_release()
            latest_version = latest["version"]
            update_available = bool(installed and latest_version > installed_date)
        except Exception as e:
            latest_error = str(e)

    if installed:
        status_text = f"✓ Installed ({installed_date})"
        install_label = "Install"
        install_enabled = False
    elif partial:
        status_text = "⚠ Missing files"
        install_label = "Install"
        install_enabled = True
    else:
        status_text = "✗ Not installed"
        install_label = "Install"
        install_enabled = True

    if update_available:
        status_text = f"▲ Update available ({installed_date} → {latest_version})"
        install_label = "Update"
        install_enabled = True

    return {
        "installed": installed,
        "partial": partial,
        "installed_version": installed_date,
        "latest_version": latest_version,
        "latest_error": latest_error,
        "update_available": update_available,
        "status_text": status_text,
        "install_label": install_label,
        "install_enabled": install_enabled,
        "uninstall_enabled": bool(installed or partial),
    }


def get_mms2_gb_core_status(connection, check_latest: bool = False) -> dict:
    installed_date = _read_installed_mms2_gb_date(connection)
    mgl_exists = _path_exists(connection, MMS2_GB_MGL_PATH)
    cfg_exists = _path_exists(connection, MMS2_GB_CFG_PATH)
    return _build_status(installed_date, mgl_exists, cfg_exists, check_latest)


def get_mms2_gb_core_status_local(sd_root: str, check_latest: bool = False) -> dict:
    installed_date = _read_installed_mms2_gb_date_local(sd_root)
    mgl_exists = _path_exists_local(sd_root, MMS2_GB_MGL_PATH)
    cfg_exists = _path_exists_local(sd_root, MMS2_GB_CFG_PATH)
    return _build_status(installed_date, mgl_exists, cfg_exists, check_latest)


def install_or_update_mms2_gb_core(connection, log):
    log("Checking latest MMS2 GB Core release...\n")
    latest = _fetch_latest_mms2_gb_release()
    version = latest["version"]
    filename = latest["filename"]

    log(f"Latest MMS2 GB Core: {filename}\n")
    rbf_data = _download_bytes(latest["rbf_url"])
    mgl_data = _download_bytes(MMS2_GB_MGL_URL, timeout=30)
    cfg_data = _download_bytes(MMS2_GB_CFG_URL, timeout=30)

    _ensure_remote_dir(connection, MMS2_GB_REMOTE_DIR)
    _ensure_remote_dir(connection, "/media/fat/config")

    remote_rbf_path = f"{MMS2_GB_REMOTE_DIR}/{filename}"

    log(f"Installing {remote_rbf_path}...\n")
    _write_remote_bytes(connection, remote_rbf_path, rbf_data)

    log(f"Installing {MMS2_GB_MGL_PATH}...\n")
    _write_remote_bytes(connection, MMS2_GB_MGL_PATH, mgl_data)

    log(f"Installing {MMS2_GB_CFG_PATH}...\n")
    _write_remote_bytes(connection, MMS2_GB_CFG_PATH, cfg_data)

    _remove_old_mms2_gb_rbfs(connection, filename)

    log(f"MMS2 GB Core {version} installed.\n")
    return {
        "installed_version": version,
        "soft_reboot_required": True,
        "soft_reboot_title": "Soft Reboot Required",
        "soft_reboot_message": (
            "A soft reboot is required to apply the MMS2 GB Core changes.\n\n"
            "Do you want to soft reboot MiSTer now?"
        ),
    }


def install_or_update_mms2_gb_core_local(sd_root: str, log):
    log("Checking latest MMS2 GB Core release...\n")
    latest = _fetch_latest_mms2_gb_release()
    version = latest["version"]
    filename = latest["filename"]

    log(f"Latest MMS2 GB Core: {filename}\n")
    rbf_data = _download_bytes(latest["rbf_url"])
    mgl_data = _download_bytes(MMS2_GB_MGL_URL, timeout=30)
    cfg_data = _download_bytes(MMS2_GB_CFG_URL, timeout=30)

    _ensure_local_dir(sd_root, MMS2_GB_REMOTE_DIR)
    _ensure_local_dir(sd_root, "/media/fat/config")

    remote_rbf_path = f"{MMS2_GB_REMOTE_DIR}/{filename}"

    log(f"Installing {remote_rbf_path}...\n")
    _write_local_bytes(sd_root, remote_rbf_path, rbf_data)

    log(f"Installing {MMS2_GB_MGL_PATH}...\n")
    _write_local_bytes(sd_root, MMS2_GB_MGL_PATH, mgl_data)

    log(f"Installing {MMS2_GB_CFG_PATH}...\n")
    _write_local_bytes(sd_root, MMS2_GB_CFG_PATH, cfg_data)

    _remove_old_mms2_gb_rbfs_local(sd_root, filename)

    log(f"MMS2 GB Core {version} installed.\n")
    return {
        "installed_version": version,
        "soft_reboot_required": True,
        "soft_reboot_title": "Soft Reboot Required",
        "soft_reboot_message": (
            "A soft reboot is required to apply the MMS2 GB Core changes.\n\n"
            "Do you want to soft reboot MiSTer now?"
        ),
    }


def _remove_old_mms2_gb_rbfs(connection, keep_filename: str):
    keep_path = f"{MMS2_GB_REMOTE_DIR}/{keep_filename}"
    command = (
        f"for f in {MMS2_GB_RBF_PATTERN}; do "
        f'[ -e "$f" ] || continue; '
        f"[ \"$f\" = {_quote(keep_path)} ] && continue; "
        f'rm -f "$f"; '
        f"done"
    )
    connection.run_command(command)


def _remove_old_mms2_gb_rbfs_local(sd_root: str, keep_filename: str):
    root = Path(str(sd_root or "")).expanduser()
    mms2_dir = root / "MMS2"
    keep_path = mms2_dir / keep_filename

    if not mms2_dir.exists() or not mms2_dir.is_dir():
        return

    for path in mms2_dir.glob("Gameboy_*.rbf"):
        if path == keep_path:
            continue
        try:
            path.unlink()
        except Exception:
            pass


def uninstall_mms2_gb_core(connection, log):
    log("Removing MMS2 GB Core files...\n")
    _remove_glob(connection, MMS2_GB_RBF_PATTERN)
    connection.run_command(f"rm -f {_quote(MMS2_GB_MGL_PATH)} {_quote(MMS2_GB_CFG_PATH)}")
    _remove_if_empty_dir(connection, MMS2_GB_REMOTE_DIR)
    log("MMS2 GB Core files removed.\n")
    return {
        "soft_reboot_required": True,
        "soft_reboot_title": "Soft Reboot Required",
        "soft_reboot_message": (
            "A soft reboot is required to apply the MMS2 GB Core uninstall changes.\n\n"
            "Do you want to soft reboot MiSTer now?"
        ),
    }


def uninstall_mms2_gb_core_local(sd_root: str, log):
    log("Removing MMS2 GB Core files from Offline SD Card...\n")
    _remove_local_glob(sd_root, MMS2_GB_RBF_PATTERN)
    _remove_local_path(sd_root, MMS2_GB_MGL_PATH)
    _remove_local_path(sd_root, MMS2_GB_CFG_PATH)
    _remove_if_empty_dir_local(sd_root, MMS2_GB_REMOTE_DIR)
    log("MMS2 GB Core files removed.\n")
    return {}

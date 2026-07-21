import html as html_lib
import posixpath
import re
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests

from core.extras_common import (
    _ensure_local_dir,
    _ensure_remote_dir,
    _local_path,
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
from core.open_helpers import open_local_folder, open_smb_share


PAPRIUM_REPO = "MisterPezz82/Paprium_MegaDrive_MiSTer"
PAPRIUM_RELEASES_URL = "https://github.com/MisterPezz82/Paprium_MegaDrive_MiSTer/releases"
PAPRIUM_LATEST_URL = "https://github.com/MisterPezz82/Paprium_MegaDrive_MiSTer/releases/latest"
PAPRIUM_MGL_URL = "https://raw.githubusercontent.com/Anime0t4ku/mister-companion/main/assets/PapriumMD.mgl"

PAPRIUM_CUSTOM_DIR = "/media/fat/_Custom Cores"
PAPRIUM_CORES_DIR = "/media/fat/_Custom Cores/Cores"
PAPRIUM_GAME_DIR = "/media/fat/games/PapriumMD"
PAPRIUM_MGL_PATH = "/media/fat/_Custom Cores/PapriumMD.mgl"
PAPRIUM_RBF_PATTERN = "/media/fat/_Custom Cores/Cores/MegaDrive_Paprium_*.rbf"
PAPRIUM_RBF_NAME_PATTERN = "MegaDrive_Paprium_*.rbf"

PAPRIUM_FILENAME_RE = re.compile(r"MegaDrive_Paprium_(\d{8})\.rbf$", re.IGNORECASE)


def _paprium_remote_rbf_glob() -> str:
    return f"{_quote(PAPRIUM_CORES_DIR)}/{PAPRIUM_RBF_NAME_PATTERN}"


def _download_bytes(url: str, timeout: int = 90) -> bytes:
    response = requests.get(
        url,
        headers={"User-Agent": "MiSTer-Companion"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.content


def _fetch_latest_paprium_release() -> dict:
    response = requests.get(
        PAPRIUM_LATEST_URL,
        headers={"User-Agent": "MiSTer-Companion", "Accept": "text/html"},
        timeout=30,
        allow_redirects=True,
    )
    response.raise_for_status()

    final_url = response.url
    marker = "/releases/tag/"
    if marker not in final_url:
        raise RuntimeError("Unable to determine latest Paprium MegaDrive release.")

    tag_name = unquote(final_url.split(marker, 1)[1].split("?", 1)[0].strip())
    if not tag_name:
        raise RuntimeError("Unable to determine latest Paprium MegaDrive release.")

    assets_url = f"https://github.com/{PAPRIUM_REPO}/releases/expanded_assets/{tag_name}"
    assets_response = requests.get(
        assets_url,
        headers={"User-Agent": "MiSTer-Companion", "Accept": "text/html"},
        timeout=30,
    )
    assets_response.raise_for_status()

    candidates = {}
    href_pattern = re.compile(r'href="([^"]+)"')

    for match in href_pattern.finditer(assets_response.text):
        href = html_lib.unescape(match.group(1))
        if "/releases/download/" not in href:
            continue
        if f"/{PAPRIUM_REPO}/releases/download/{tag_name}/" not in href:
            continue

        url = urljoin("https://github.com", href)
        filename = unquote(posixpath.basename(url.split("?", 1)[0]))
        file_match = PAPRIUM_FILENAME_RE.match(filename)
        if not file_match:
            continue

        candidates[file_match.group(1)] = {
            "version": file_match.group(1),
            "filename": filename,
            "rbf_url": url,
            "tag": tag_name,
        }

    if not candidates:
        raise RuntimeError("Unable to find MegaDrive_Paprium_YYYYMMDD.rbf in the latest Paprium MegaDrive release.")

    return candidates[sorted(candidates.keys())[-1]]


def _latest_installed_paprium_date_from_names(names: list[str]) -> str:
    dates = []

    for name in names:
        filename = posixpath.basename(str(name).strip())
        match = PAPRIUM_FILENAME_RE.match(filename)
        if match:
            dates.append(match.group(1))

    return sorted(dates)[-1] if dates else ""


def _read_installed_paprium_date(connection) -> str:
    command = (
        f"for f in {_paprium_remote_rbf_glob()}; do "
        f'[ -e "$f" ] && basename "$f"; '
        f"done"
    )
    output = connection.run_command(command) or ""
    return _latest_installed_paprium_date_from_names(output.splitlines())


def _read_installed_paprium_date_local(sd_root: str) -> str:
    root = Path(str(sd_root or "")).expanduser()
    if not root.exists() or not root.is_dir():
        return ""

    cores_dir = root / "_Custom Cores" / "Cores"
    if not cores_dir.exists() or not cores_dir.is_dir():
        return ""

    return _latest_installed_paprium_date_from_names(
        [path.name for path in cores_dir.glob("MegaDrive_Paprium_*.rbf")]
    )


def _is_smb_enabled(connection) -> bool:
    result = connection.run_command("test -f /media/fat/linux/samba.sh && echo EXISTS || echo MISSING")
    return "EXISTS" in (result or "")


def _build_status(
    installed_date: str,
    mgl_exists: bool,
    game_dir_exists: bool,
    check_latest: bool,
    folder_open_enabled: bool = False,
) -> dict:
    installed = bool(installed_date and mgl_exists)
    partial = bool(installed_date or mgl_exists) and not installed

    latest_version = ""
    latest_error = ""
    update_available = False

    if check_latest:
        try:
            latest = _fetch_latest_paprium_release()
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
        "game_dir_exists": game_dir_exists,
        "folder_open_enabled": bool(installed and folder_open_enabled),
        "status_text": status_text,
        "install_label": install_label,
        "install_enabled": install_enabled,
        "uninstall_enabled": bool(installed or partial),
    }


def get_paprium_megadrive_status(connection, check_latest: bool = False) -> dict:
    installed_date = _read_installed_paprium_date(connection)
    mgl_exists = _path_exists(connection, PAPRIUM_MGL_PATH)
    game_dir_exists = _path_exists(connection, PAPRIUM_GAME_DIR)
    folder_open_enabled = bool(installed_date and mgl_exists and _is_smb_enabled(connection))
    return _build_status(
        installed_date,
        mgl_exists,
        game_dir_exists,
        check_latest,
        folder_open_enabled=folder_open_enabled,
    )


def get_paprium_megadrive_status_local(sd_root: str, check_latest: bool = False) -> dict:
    installed_date = _read_installed_paprium_date_local(sd_root)
    mgl_exists = _path_exists_local(sd_root, PAPRIUM_MGL_PATH)
    game_dir_exists = _path_exists_local(sd_root, PAPRIUM_GAME_DIR)
    installed = bool(installed_date and mgl_exists)
    return _build_status(
        installed_date,
        mgl_exists,
        game_dir_exists,
        check_latest,
        folder_open_enabled=installed,
    )


def install_or_update_paprium_megadrive(connection, log):
    log("Checking latest Paprium MegaDrive release...\n")
    latest = _fetch_latest_paprium_release()
    version = latest["version"]
    filename = latest["filename"]

    log(f"Latest Paprium MegaDrive core: {filename}\n")
    rbf_data = _download_bytes(latest["rbf_url"])
    mgl_data = _download_bytes(PAPRIUM_MGL_URL, timeout=30)

    _ensure_remote_dir(connection, PAPRIUM_CORES_DIR)
    _ensure_remote_dir(connection, PAPRIUM_GAME_DIR)

    remote_rbf_path = f"{PAPRIUM_CORES_DIR}/{filename}"

    log(f"Installing {remote_rbf_path}...\n")
    _write_remote_bytes(connection, remote_rbf_path, rbf_data)

    log(f"Installing {PAPRIUM_MGL_PATH}...\n")
    _write_remote_bytes(connection, PAPRIUM_MGL_PATH, mgl_data)

    _remove_old_paprium_rbfs(connection, filename)

    log(f"Paprium MegaDrive {version} installed.\n")
    log("Game folder ready at /media/fat/games/PapriumMD.\n")
    return {
        "installed_version": version,
        "soft_reboot_required": True,
        "soft_reboot_title": "Soft Reboot Required",
        "soft_reboot_message": (
            "A soft reboot is required before the Paprium MegaDrive menu entry becomes visible.\n\n"
            "Do you want to soft reboot MiSTer now?"
        ),
    }


def install_or_update_paprium_megadrive_local(sd_root: str, log):
    log("Checking latest Paprium MegaDrive release...\n")
    latest = _fetch_latest_paprium_release()
    version = latest["version"]
    filename = latest["filename"]

    log(f"Latest Paprium MegaDrive core: {filename}\n")
    rbf_data = _download_bytes(latest["rbf_url"])
    mgl_data = _download_bytes(PAPRIUM_MGL_URL, timeout=30)

    _ensure_local_dir(sd_root, PAPRIUM_CORES_DIR)
    _ensure_local_dir(sd_root, PAPRIUM_GAME_DIR)

    remote_rbf_path = f"{PAPRIUM_CORES_DIR}/{filename}"

    log(f"Installing {remote_rbf_path}...\n")
    _write_local_bytes(sd_root, remote_rbf_path, rbf_data)

    log(f"Installing {PAPRIUM_MGL_PATH}...\n")
    _write_local_bytes(sd_root, PAPRIUM_MGL_PATH, mgl_data)

    _remove_old_paprium_rbfs_local(sd_root, filename)

    log(f"Paprium MegaDrive {version} installed.\n")
    log("Game folder ready at /media/fat/games/PapriumMD.\n")
    return {
        "installed_version": version,
        "soft_reboot_required": True,
        "soft_reboot_title": "Soft Reboot Required",
        "soft_reboot_message": (
            "A soft reboot is required before the Paprium MegaDrive menu entry becomes visible.\n\n"
            "Do you want to soft reboot MiSTer now?"
        ),
    }


def _remove_old_paprium_rbfs(connection, keep_filename: str):
    keep_path = f"{PAPRIUM_CORES_DIR}/{keep_filename}"
    command = (
        f"for f in {_paprium_remote_rbf_glob()}; do "
        f'[ -e "$f" ] || continue; '
        f"[ \"$f\" = {_quote(keep_path)} ] && continue; "
        f'rm -f "$f"; '
        f"done"
    )
    connection.run_command(command)


def _remove_old_paprium_rbfs_local(sd_root: str, keep_filename: str):
    root = Path(str(sd_root or "")).expanduser()
    cores_dir = root / "_Custom Cores" / "Cores"
    keep_path = cores_dir / keep_filename

    if not cores_dir.exists() or not cores_dir.is_dir():
        return

    for path in cores_dir.glob("MegaDrive_Paprium_*.rbf"):
        if path == keep_path:
            continue
        try:
            path.unlink()
        except Exception:
            pass


def uninstall_paprium_megadrive(connection, log, remove_game_folder: bool = False):
    log("Removing Paprium MegaDrive files...\n")
    command = (
        f"for f in {_paprium_remote_rbf_glob()}; do "
        f'[ -e "$f" ] && rm -f "$f"; '
        f"done"
    )
    connection.run_command(command)
    connection.run_command(f"rm -f {_quote(PAPRIUM_MGL_PATH)}")

    if remove_game_folder:
        log("Removing /media/fat/games/PapriumMD...\n")
        connection.run_command(f"rm -rf {_quote(PAPRIUM_GAME_DIR)}")
    else:
        log("Keeping /media/fat/games/PapriumMD.\n")

    _remove_if_empty_dir(connection, PAPRIUM_CORES_DIR)
    _remove_if_empty_dir(connection, PAPRIUM_CUSTOM_DIR)

    log("Paprium MegaDrive files removed.\n")
    return {
        "soft_reboot_required": True,
        "soft_reboot_title": "Soft Reboot Required",
        "soft_reboot_message": (
            "A soft reboot is required to refresh the MiSTer menu after removing Paprium MegaDrive.\n\n"
            "Do you want to soft reboot MiSTer now?"
        ),
    }


def uninstall_paprium_megadrive_local(sd_root: str, log, remove_game_folder: bool = False):
    log("Removing Paprium MegaDrive files from Offline SD Card...\n")
    _remove_local_glob(sd_root, PAPRIUM_RBF_PATTERN)
    _remove_local_path(sd_root, PAPRIUM_MGL_PATH)

    if remove_game_folder:
        log("Removing /media/fat/games/PapriumMD...\n")
        _remove_local_path(sd_root, PAPRIUM_GAME_DIR)
    else:
        log("Keeping /media/fat/games/PapriumMD.\n")

    _remove_if_empty_dir_local(sd_root, PAPRIUM_CORES_DIR)
    _remove_if_empty_dir_local(sd_root, PAPRIUM_CUSTOM_DIR)

    log("Paprium MegaDrive files removed.\n")
    return {}


def open_paprium_game_folder_local(sd_root: str) -> None:
    game_dir = _local_path(sd_root, PAPRIUM_GAME_DIR)
    game_dir.mkdir(parents=True, exist_ok=True)
    open_local_folder(game_dir)


def open_paprium_game_folder_on_host(ip: str) -> None:
    open_smb_share(ip, "sdcard/games/PapriumMD")


# Downloader-backed Install Center implementation.
from core.downloader_backend import (
    database_registered_local,
    database_registered_online,
    ensure_database_source_local,
    ensure_database_source_online,
    remove_database_source_local,
    remove_database_source_online,
    restore_local,
    restore_online,
    run_named_database_local,
    run_named_database_online,
    check_named_database_local,
    check_named_database_online,
    uninstall_named_database_local,
    uninstall_named_database_online,
)

PAPRIUM_DB_ID = "MultiDatabases/paprium"
PAPRIUM_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/paprium/db.json"


def _manual_paprium_install(connection):
    present = bool(_read_installed_paprium_date(connection) or _path_exists(connection, PAPRIUM_MGL_PATH))
    return bool(present and not database_registered_online(connection, PAPRIUM_DB_ID))


def _manual_paprium_install_local(sd_root):
    present = bool(_read_installed_paprium_date_local(sd_root) or _path_exists_local(sd_root, PAPRIUM_MGL_PATH))
    return bool(present and not database_registered_local(sd_root, PAPRIUM_DB_ID))


def _prepare_manual_paprium_for_downloader(connection, log, manual=None):
    if manual is None:
        manual = _manual_paprium_install(connection)
    if not manual:
        return False
    log("Detected a manual Companion installation; preparing it for Downloader...\n")
    _remove_glob(connection, PAPRIUM_RBF_PATTERN)
    connection.run_command(f"rm -f {_quote(PAPRIUM_MGL_PATH)}")
    log(f"Preserved user ROM and audio files in {PAPRIUM_GAME_DIR}\n")
    return True


def _prepare_manual_paprium_for_downloader_local(sd_root, log, manual=None):
    if manual is None:
        manual = _manual_paprium_install_local(sd_root)
    if not manual:
        return False
    log("Detected a manual Companion installation; preparing it for Downloader...\n")
    _remove_local_glob(sd_root, PAPRIUM_RBF_PATTERN)
    _remove_local_path(sd_root, PAPRIUM_MGL_PATH)
    log(f"Preserved user ROM and audio files in {PAPRIUM_GAME_DIR}\n")
    return True


_manual_get_paprium_status = get_paprium_megadrive_status
_manual_get_paprium_status_local = get_paprium_megadrive_status_local


def _apply_paprium_downloader_status(status, manual, update_available=False):
    status = dict(status)
    if manual:
        status.update({"update_available": True, "status_text": "▲ Manual install found", "install_label": "Migrate / Update", "install_enabled": True})
    elif status.get("installed"):
        status.update({"installed_version": "", "latest_version": "", "update_available": bool(update_available), "status_text": "▲ Update available" if update_available else "✓ Installed", "install_label": "Update" if update_available else "Installed", "install_enabled": bool(update_available)})
    return status


def get_paprium_megadrive_status(connection, check_latest=False):
    status = _manual_get_paprium_status(connection, check_latest=False)
    manual = _manual_paprium_install(connection)
    update = bool(check_latest and status.get("installed") and not manual and check_named_database_online(connection, PAPRIUM_DB_ID))
    return _apply_paprium_downloader_status(status, manual, update)


def get_paprium_megadrive_status_local(sd_root, check_latest=False):
    status = _manual_get_paprium_status_local(sd_root, check_latest=False)
    manual = _manual_paprium_install_local(sd_root)
    update = bool(check_latest and status.get("installed") and not manual and check_named_database_local(sd_root, PAPRIUM_DB_ID))
    return _apply_paprium_downloader_status(status, manual, update)


def _paprium_reboot_result(uninstall=False):
    message = "A soft reboot is required to refresh the MiSTer menu after removing Paprium MegaDrive." if uninstall else "A soft reboot is required before the Paprium MegaDrive menu entry becomes visible."
    return {"soft_reboot_required": True, "soft_reboot_title": "Soft Reboot Required", "soft_reboot_message": message + "\n\nDo you want to soft reboot MiSTer now?"}


def install_or_update_paprium_megadrive(connection, log):
    manual = _manual_paprium_install(connection)
    original = ensure_database_source_online(connection, PAPRIUM_DB_ID, PAPRIUM_DB_URL)
    try:
        _prepare_manual_paprium_for_downloader(connection, log, manual=manual)
        run_named_database_online(connection, PAPRIUM_DB_ID, log=log)
        _ensure_remote_dir(connection, PAPRIUM_GAME_DIR)
    except Exception:
        restore_online(connection, original)
        raise
    return _paprium_reboot_result()


def install_or_update_paprium_megadrive_local(sd_root, log):
    manual = _manual_paprium_install_local(sd_root)
    original = ensure_database_source_local(sd_root, PAPRIUM_DB_ID, PAPRIUM_DB_URL)
    try:
        _prepare_manual_paprium_for_downloader_local(sd_root, log, manual=manual)
        run_named_database_local(sd_root, PAPRIUM_DB_ID, log=log)
        _ensure_local_dir(sd_root, PAPRIUM_GAME_DIR)
    except Exception:
        restore_local(sd_root, original)
        raise
    return _paprium_reboot_result()


def uninstall_paprium_megadrive(connection, log, remove_game_folder=False, force=False):
    if _manual_paprium_install(connection):
        _prepare_manual_paprium_for_downloader(connection, log, manual=True)
        remove_database_source_online(connection, PAPRIUM_DB_ID)
        return _paprium_reboot_result(uninstall=True)
    original = ensure_database_source_online(connection, PAPRIUM_DB_ID, PAPRIUM_DB_URL)
    try:
        native = uninstall_named_database_online(connection, PAPRIUM_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(connection, PAPRIUM_DB_ID, PAPRIUM_DB_URL, filter_value="!all")
            run_named_database_online(connection, PAPRIUM_DB_ID, log=log)
            remove_database_source_online(connection, PAPRIUM_DB_ID)
        if remove_game_folder:
            connection.run_command(f"rm -rf {_quote(PAPRIUM_GAME_DIR)}")
    except Exception:
        restore_online(connection, original)
        raise
    return _paprium_reboot_result(uninstall=True)


def uninstall_paprium_megadrive_local(sd_root, log, remove_game_folder=False, force=False):
    if _manual_paprium_install_local(sd_root):
        _prepare_manual_paprium_for_downloader_local(sd_root, log, manual=True)
        remove_database_source_local(sd_root, PAPRIUM_DB_ID)
        return _paprium_reboot_result(uninstall=True)
    original = ensure_database_source_local(sd_root, PAPRIUM_DB_ID, PAPRIUM_DB_URL)
    try:
        native = uninstall_named_database_local(sd_root, PAPRIUM_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(sd_root, PAPRIUM_DB_ID, PAPRIUM_DB_URL, filter_value="!all")
            run_named_database_local(sd_root, PAPRIUM_DB_ID, log=log)
            remove_database_source_local(sd_root, PAPRIUM_DB_ID)
        if remove_game_folder:
            _remove_local_path(sd_root, PAPRIUM_GAME_DIR)
    except Exception:
        restore_local(sd_root, original)
        raise
    return _paprium_reboot_result(uninstall=True)

import html as html_lib
import json
import posixpath
import re
from datetime import datetime, timezone
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
    _remove_if_empty_dir,
    _remove_if_empty_dir_local,
    _remove_local_path,
    _write_local_bytes,
    _write_remote_bytes,
)
from core.open_helpers import open_local_folder, open_smb_share


MEGAVGMD_REPO = "dai-VGM/MegaVGMDrive"
MEGAVGMD_RELEASES_URL = "https://github.com/dai-VGM/MegaVGMDrive/releases"
MEGAVGMD_LATEST_URL = "https://github.com/dai-VGM/MegaVGMDrive/releases/latest"
MEGAVGMD_RBF_FILENAME = "VGM_MD_MiSTer.rbf"
MEGAVGMD_MGL_URL = "https://raw.githubusercontent.com/Anime0t4ku/mister-companion/main/assets/MegaVGMDrive.mgl"

MEGAVGMD_CUSTOM_DIR = "/media/fat/_Custom Cores"
MEGAVGMD_CORES_DIR = "/media/fat/_Custom Cores/Cores"
MEGAVGMD_GAME_DIR = "/media/fat/games/MegaVGMDrive"
MEGAVGMD_MGL_PATH = "/media/fat/_Custom Cores/MegaVGMDrive.mgl"
MEGAVGMD_RBF_PATH = "/media/fat/_Custom Cores/Cores/VGM_MD_MiSTer.rbf"
MEGAVGMD_RBF_PREFIX = "MegaVGMdrive_MiSTer"
MEGAVGMD_CONFIG_DIR = "/media/fat/Scripts/.config/MegaVGMDrive"
MEGAVGMD_RELEASE_MARKER_PATH = "/media/fat/Scripts/.config/MegaVGMDrive/release.json"


def _download_bytes(url: str, timeout: int = 90) -> bytes:
    response = requests.get(
        url,
        headers={"User-Agent": "MiSTer-Companion"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.content


def _fetch_latest_megavgmdrive_release() -> dict:
    response = requests.get(
        MEGAVGMD_LATEST_URL,
        headers={"User-Agent": "MiSTer-Companion", "Accept": "text/html"},
        timeout=30,
        allow_redirects=True,
    )
    response.raise_for_status()

    final_url = response.url
    marker = "/releases/tag/"
    if marker not in final_url:
        raise RuntimeError("Unable to determine latest MegaVGMDrive release.")

    tag_name = unquote(final_url.split(marker, 1)[1].split("?", 1)[0].strip())
    if not tag_name:
        raise RuntimeError("Unable to determine latest MegaVGMDrive release.")

    assets_url = f"https://github.com/{MEGAVGMD_REPO}/releases/expanded_assets/{tag_name}"
    assets_response = requests.get(
        assets_url,
        headers={"User-Agent": "MiSTer-Companion", "Accept": "text/html"},
        timeout=30,
    )
    assets_response.raise_for_status()

    href_pattern = re.compile(r'href="([^"]+)"')
    for match in href_pattern.finditer(assets_response.text):
        href = html_lib.unescape(match.group(1))
        if "/releases/download/" not in href:
            continue
        if f"/{MEGAVGMD_REPO}/releases/download/{tag_name}/" not in href:
            continue

        url = urljoin("https://github.com", href)
        filename = unquote(posixpath.basename(url.split("?", 1)[0]))
        if filename.lower() != MEGAVGMD_RBF_FILENAME.lower():
            continue

        return {
            "version": tag_name,
            "filename": filename,
            "rbf_url": url,
            "tag": tag_name,
        }

    raise RuntimeError(f"Unable to find {MEGAVGMD_RBF_FILENAME} in the latest MegaVGMDrive release.")


def _release_marker_payload(release: dict) -> dict:
    return {
        "schema_version": 1,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "tag": release.get("tag") or release.get("version") or "",
        "version": release.get("version") or release.get("tag") or "",
        "filename": release.get("filename") or MEGAVGMD_RBF_FILENAME,
        "rbf_url": release.get("rbf_url") or "",
    }


def _marker_version(marker: dict) -> str:
    if not isinstance(marker, dict):
        return ""
    return str(marker.get("version") or marker.get("tag") or "").strip()


def _read_marker(connection) -> dict:
    raw = connection.run_command(f"cat {_quote(MEGAVGMD_RELEASE_MARKER_PATH)} 2>/dev/null") or ""
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_marker_local(sd_root: str) -> dict:
    path = _local_path(sd_root, MEGAVGMD_RELEASE_MARKER_PATH)
    if not path.exists() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_marker(connection, release: dict):
    payload = json.dumps(_release_marker_payload(release), indent=2, ensure_ascii=False).encode("utf-8")
    _ensure_remote_dir(connection, MEGAVGMD_CONFIG_DIR)
    _write_remote_bytes(connection, MEGAVGMD_RELEASE_MARKER_PATH, payload)


def _write_marker_local(sd_root: str, release: dict):
    payload = json.dumps(_release_marker_payload(release), indent=2, ensure_ascii=False).encode("utf-8")
    _ensure_local_dir(sd_root, MEGAVGMD_CONFIG_DIR)
    _write_local_bytes(sd_root, MEGAVGMD_RELEASE_MARKER_PATH, payload)


def _is_smb_enabled(connection) -> bool:
    result = connection.run_command("test -f /media/fat/linux/samba.sh && echo EXISTS || echo MISSING")
    return "EXISTS" in (result or "")


def _megavgmd_rbf_paths(connection) -> list[str]:
    command = (
        f"find {_quote(MEGAVGMD_CORES_DIR)} -maxdepth 1 -type f "
        f"\\( -iname {_quote(MEGAVGMD_RBF_FILENAME)} -o -iname {_quote(MEGAVGMD_RBF_PREFIX + '*.rbf')} \\) "
        "-print 2>/dev/null || true"
    )
    return [line.strip() for line in (connection.run_command(command) or "").splitlines() if line.strip()]


def _megavgmd_rbf_paths_local(sd_root: str) -> list[Path]:
    directory = _local_path(sd_root, MEGAVGMD_CORES_DIR)
    if not directory.exists() or not directory.is_dir():
        return []
    legacy = MEGAVGMD_RBF_FILENAME.lower()
    prefix = MEGAVGMD_RBF_PREFIX.lower()
    return [
        path for path in directory.iterdir()
        if path.is_file() and (path.name.lower() == legacy or (path.name.lower().startswith(prefix) and path.suffix.lower() == ".rbf"))
    ]


def _megavgmd_rbf_exists(connection) -> bool:
    return bool(_megavgmd_rbf_paths(connection))


def _megavgmd_rbf_exists_local(sd_root: str) -> bool:
    return bool(_megavgmd_rbf_paths_local(sd_root))


def _remove_megavgmd_rbfs(connection, log=None):
    for path in _megavgmd_rbf_paths(connection):
        connection.run_command(f"rm -f {_quote(path)}")
        if log:
            log(f"Removed legacy managed file: {path}\n")


def _remove_megavgmd_rbfs_local(sd_root: str, log=None):
    for path in _megavgmd_rbf_paths_local(sd_root):
        path.unlink(missing_ok=True)
        if log:
            log(f"Removed legacy managed file: /media/fat/_Custom Cores/Cores/{path.name}\n")


def _build_status(
    rbf_exists: bool,
    mgl_exists: bool,
    game_dir_exists: bool,
    installed_version: str,
    check_latest: bool,
    folder_open_enabled: bool = False,
) -> dict:
    installed = bool(rbf_exists and mgl_exists)
    partial = bool(rbf_exists or mgl_exists) and not installed

    latest_version = ""
    latest_error = ""
    update_available = False

    if check_latest:
        try:
            latest = _fetch_latest_megavgmdrive_release()
            latest_version = latest["version"]
            update_available = bool(installed and (not installed_version or latest_version != installed_version))
        except Exception as e:
            latest_error = str(e)

    if installed:
        display_version = installed_version or "version unknown"
        status_text = f"✓ Installed ({display_version})"
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
        from_version = installed_version or "unknown"
        status_text = f"▲ Update available ({from_version} → {latest_version})"
        install_label = "Update"
        install_enabled = True

    return {
        "installed": installed,
        "partial": partial,
        "installed_version": installed_version,
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


def get_megavgmdrive_status(connection, check_latest: bool = False) -> dict:
    rbf_exists = _megavgmd_rbf_exists(connection)
    mgl_exists = _path_exists(connection, MEGAVGMD_MGL_PATH)
    game_dir_exists = _path_exists(connection, MEGAVGMD_GAME_DIR)
    installed_version = _marker_version(_read_marker(connection))
    folder_open_enabled = bool(rbf_exists and mgl_exists and _is_smb_enabled(connection))
    return _build_status(
        rbf_exists,
        mgl_exists,
        game_dir_exists,
        installed_version,
        check_latest,
        folder_open_enabled=folder_open_enabled,
    )


def get_megavgmdrive_status_local(sd_root: str, check_latest: bool = False) -> dict:
    rbf_exists = _megavgmd_rbf_exists_local(sd_root)
    mgl_exists = _path_exists_local(sd_root, MEGAVGMD_MGL_PATH)
    game_dir_exists = _path_exists_local(sd_root, MEGAVGMD_GAME_DIR)
    installed_version = _marker_version(_read_marker_local(sd_root))
    installed = bool(rbf_exists and mgl_exists)
    return _build_status(
        rbf_exists,
        mgl_exists,
        game_dir_exists,
        installed_version,
        check_latest,
        folder_open_enabled=installed,
    )


def install_or_update_megavgmdrive(connection, log):
    log("Checking latest MegaVGMDrive release...\n")
    latest = _fetch_latest_megavgmdrive_release()
    version = latest["version"]
    filename = latest["filename"]

    log(f"Latest MegaVGMDrive core: {filename} ({version})\n")
    rbf_data = _download_bytes(latest["rbf_url"])
    mgl_data = _download_bytes(MEGAVGMD_MGL_URL, timeout=30)

    _ensure_remote_dir(connection, MEGAVGMD_CORES_DIR)
    _ensure_remote_dir(connection, MEGAVGMD_GAME_DIR)
    _ensure_remote_dir(connection, MEGAVGMD_CONFIG_DIR)

    log(f"Installing {MEGAVGMD_RBF_PATH}...\n")
    _write_remote_bytes(connection, MEGAVGMD_RBF_PATH, rbf_data)

    log(f"Installing {MEGAVGMD_MGL_PATH}...\n")
    _write_remote_bytes(connection, MEGAVGMD_MGL_PATH, mgl_data)

    log(f"Storing release marker at {MEGAVGMD_RELEASE_MARKER_PATH}...\n")
    _write_marker(connection, latest)

    log(f"MegaVGMDrive {version} installed.\n")
    log("Game folder ready at /media/fat/games/MegaVGMDrive.\n")
    return {
        "installed_version": version,
        "soft_reboot_required": True,
        "soft_reboot_title": "Soft Reboot Required",
        "soft_reboot_message": (
            "A soft reboot is required before the MegaVGMDrive menu entry becomes visible.\n\n"
            "Do you want to soft reboot MiSTer now?"
        ),
    }


def install_or_update_megavgmdrive_local(sd_root: str, log):
    log("Checking latest MegaVGMDrive release...\n")
    latest = _fetch_latest_megavgmdrive_release()
    version = latest["version"]
    filename = latest["filename"]

    log(f"Latest MegaVGMDrive core: {filename} ({version})\n")
    rbf_data = _download_bytes(latest["rbf_url"])
    mgl_data = _download_bytes(MEGAVGMD_MGL_URL, timeout=30)

    _ensure_local_dir(sd_root, MEGAVGMD_CORES_DIR)
    _ensure_local_dir(sd_root, MEGAVGMD_GAME_DIR)
    _ensure_local_dir(sd_root, MEGAVGMD_CONFIG_DIR)

    log(f"Installing {MEGAVGMD_RBF_PATH}...\n")
    _write_local_bytes(sd_root, MEGAVGMD_RBF_PATH, rbf_data)

    log(f"Installing {MEGAVGMD_MGL_PATH}...\n")
    _write_local_bytes(sd_root, MEGAVGMD_MGL_PATH, mgl_data)

    log(f"Storing release marker at {MEGAVGMD_RELEASE_MARKER_PATH}...\n")
    _write_marker_local(sd_root, latest)

    log(f"MegaVGMDrive {version} installed.\n")
    log("Game folder ready at /media/fat/games/MegaVGMDrive.\n")
    return {
        "installed_version": version,
        "soft_reboot_required": True,
        "soft_reboot_title": "Soft Reboot Required",
        "soft_reboot_message": (
            "A soft reboot is required before the MegaVGMDrive menu entry becomes visible.\n\n"
            "Do you want to soft reboot MiSTer now?"
        ),
    }


def uninstall_megavgmdrive(connection, log, remove_game_folder: bool = False):
    log("Removing MegaVGMDrive files...\n")
    connection.run_command(f"rm -f {_quote(MEGAVGMD_RBF_PATH)}")
    connection.run_command(f"rm -f {_quote(MEGAVGMD_MGL_PATH)}")
    connection.run_command(f"rm -f {_quote(MEGAVGMD_RELEASE_MARKER_PATH)}")
    _remove_if_empty_dir(connection, MEGAVGMD_CONFIG_DIR)

    if remove_game_folder:
        log("Removing /media/fat/games/MegaVGMDrive...\n")
        connection.run_command(f"rm -rf {_quote(MEGAVGMD_GAME_DIR)}")
    else:
        log("Keeping /media/fat/games/MegaVGMDrive.\n")

    _remove_if_empty_dir(connection, MEGAVGMD_CORES_DIR)
    _remove_if_empty_dir(connection, MEGAVGMD_CUSTOM_DIR)

    log("MegaVGMDrive files removed.\n")
    return {
        "soft_reboot_required": True,
        "soft_reboot_title": "Soft Reboot Required",
        "soft_reboot_message": (
            "A soft reboot is required to refresh the MiSTer menu after removing MegaVGMDrive.\n\n"
            "Do you want to soft reboot MiSTer now?"
        ),
    }


def uninstall_megavgmdrive_local(sd_root: str, log, remove_game_folder: bool = False):
    log("Removing MegaVGMDrive files from Offline SD Card...\n")
    _remove_local_path(sd_root, MEGAVGMD_RBF_PATH)
    _remove_local_path(sd_root, MEGAVGMD_MGL_PATH)
    _remove_local_path(sd_root, MEGAVGMD_RELEASE_MARKER_PATH)
    _remove_if_empty_dir_local(sd_root, MEGAVGMD_CONFIG_DIR)

    if remove_game_folder:
        log("Removing /media/fat/games/MegaVGMDrive...\n")
        _remove_local_path(sd_root, MEGAVGMD_GAME_DIR)
    else:
        log("Keeping /media/fat/games/MegaVGMDrive.\n")

    _remove_if_empty_dir_local(sd_root, MEGAVGMD_CORES_DIR)
    _remove_if_empty_dir_local(sd_root, MEGAVGMD_CUSTOM_DIR)

    log("MegaVGMDrive files removed.\n")
    return {}


def open_megavgmdrive_game_folder_local(sd_root: str) -> None:
    game_dir = _local_path(sd_root, MEGAVGMD_GAME_DIR)
    game_dir.mkdir(parents=True, exist_ok=True)
    open_local_folder(game_dir)


def open_megavgmdrive_game_folder_on_host(ip: str) -> None:
    open_smb_share(ip, "sdcard/games/MegaVGMDrive")


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

MEGAVGMD_DB_ID = "MultiDatabases/megavgmdrive"
MEGAVGMD_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/megavgmdrive/db.json"
MEGAVGMD_DB_FILES = (MEGAVGMD_MGL_PATH,)


def _megavgmd_managed_files_present(connection) -> bool:
    return bool(_megavgmd_rbf_exists(connection) or any(_path_exists(connection, path) for path in MEGAVGMD_DB_FILES))


def _megavgmd_managed_files_present_local(sd_root) -> bool:
    return bool(_megavgmd_rbf_exists_local(sd_root) or any(_path_exists_local(sd_root, path) for path in MEGAVGMD_DB_FILES))


def _manual_megavgmdrive_install(connection) -> bool:
    return False

def _manual_megavgmdrive_install_local(sd_root) -> bool:
    return False

def _prepare_manual_megavgmdrive_for_downloader(connection, log, manual=None):
    if manual is None:
        manual = _manual_megavgmdrive_install(connection)
    if not manual:
        return False
    log("Detected a manual Companion installation; preparing it for Downloader...\n")
    _remove_megavgmd_rbfs(connection, log=log)
    for path in MEGAVGMD_DB_FILES:
        connection.run_command(f"rm -f {_quote(path)}")
        log(f"Removed legacy managed file: {path}\n")
    connection.run_command(f"rm -f {_quote(MEGAVGMD_RELEASE_MARKER_PATH)}")
    _remove_if_empty_dir(connection, MEGAVGMD_CONFIG_DIR)
    log(f"Preserved user content in {MEGAVGMD_GAME_DIR}\n")
    return True


def _prepare_manual_megavgmdrive_for_downloader_local(sd_root, log, manual=None):
    if manual is None:
        manual = _manual_megavgmdrive_install_local(sd_root)
    if not manual:
        return False
    log("Detected a manual Companion installation; preparing it for Downloader...\n")
    _remove_megavgmd_rbfs_local(sd_root, log=log)
    for path in MEGAVGMD_DB_FILES:
        _remove_local_path(sd_root, path)
        log(f"Removed legacy managed file: {path}\n")
    _remove_local_path(sd_root, MEGAVGMD_RELEASE_MARKER_PATH)
    _remove_if_empty_dir_local(sd_root, MEGAVGMD_CONFIG_DIR)
    log(f"Preserved user content in {MEGAVGMD_GAME_DIR}\n")
    return True


_manual_get_megavgmdrive_status = get_megavgmdrive_status
_manual_get_megavgmdrive_status_local = get_megavgmdrive_status_local


def _apply_megavgmdrive_downloader_status(status, manual, update_available=False):
    status = dict(status)
    if manual:
        status.update({
            "update_available": True,
            "status_text": "▲ Manual install found",
            "install_label": "Migrate / Update",
            "install_enabled": True,
        })
    elif status.get("installed"):
        status.update({
            "installed_version": "",
            "latest_version": "",
            "update_available": bool(update_available),
            "status_text": "▲ Update available" if update_available else "✓ Installed",
            "install_label": "Update" if update_available else "Installed",
            "install_enabled": bool(update_available),
        })
    return status


def get_megavgmdrive_status(connection, check_latest: bool = False) -> dict:
    status = _manual_get_megavgmdrive_status(connection, check_latest=False)
    manual = _manual_megavgmdrive_install(connection) if (status.get("installed") or status.get("partial")) else False
    update = False
    if check_latest and status.get("installed") and not manual:
        update = check_named_database_online(connection, MEGAVGMD_DB_ID)
    return _apply_megavgmdrive_downloader_status(status, manual, update)


def get_megavgmdrive_status_local(sd_root: str, check_latest: bool = False) -> dict:
    status = _manual_get_megavgmdrive_status_local(sd_root, check_latest=False)
    manual = _manual_megavgmdrive_install_local(sd_root) if (status.get("installed") or status.get("partial")) else False
    update = False
    if check_latest and status.get("installed") and not manual:
        update = check_named_database_local(sd_root, MEGAVGMD_DB_ID)
    return _apply_megavgmdrive_downloader_status(status, manual, update)


def _megavgmdrive_reboot_result():
    return {
        "soft_reboot_required": True,
        "soft_reboot_title": "Soft Reboot Required",
        "soft_reboot_message": (
            "A soft reboot is required to refresh the MegaVGMDrive menu entry.\n\n"
            "Do you want to soft reboot MiSTer now?"
        ),
    }


def _finish_megavgmdrive_install_online(connection, log):
    _ensure_remote_dir(connection, MEGAVGMD_GAME_DIR)
    connection.run_command(f"rm -f {_quote(MEGAVGMD_RELEASE_MARKER_PATH)}")
    _remove_if_empty_dir(connection, MEGAVGMD_CONFIG_DIR)
    log(f"Game folder ready at {MEGAVGMD_GAME_DIR}\n")


def _finish_megavgmdrive_install_local(sd_root, log):
    _ensure_local_dir(sd_root, MEGAVGMD_GAME_DIR)
    _remove_local_path(sd_root, MEGAVGMD_RELEASE_MARKER_PATH)
    _remove_if_empty_dir_local(sd_root, MEGAVGMD_CONFIG_DIR)
    log(f"Game folder ready at {MEGAVGMD_GAME_DIR}\n")


def install_or_update_megavgmdrive(connection, log):
    manual = _manual_megavgmdrive_install(connection)
    original = ensure_database_source_online(connection, MEGAVGMD_DB_ID, MEGAVGMD_DB_URL)
    try:
        _prepare_manual_megavgmdrive_for_downloader(connection, log, manual=manual)
        run_named_database_online(connection, MEGAVGMD_DB_ID, log=log)
        _finish_megavgmdrive_install_online(connection, log)
    except Exception:
        restore_online(connection, original)
        raise
    return _megavgmdrive_reboot_result()


def install_or_update_megavgmdrive_local(sd_root: str, log):
    manual = _manual_megavgmdrive_install_local(sd_root)
    original = ensure_database_source_local(sd_root, MEGAVGMD_DB_ID, MEGAVGMD_DB_URL)
    try:
        _prepare_manual_megavgmdrive_for_downloader_local(sd_root, log, manual=manual)
        run_named_database_local(sd_root, MEGAVGMD_DB_ID, log=log)
        _finish_megavgmdrive_install_local(sd_root, log)
    except Exception:
        restore_local(sd_root, original)
        raise
    return _megavgmdrive_reboot_result()


def uninstall_megavgmdrive(connection, log, force=False, remove_game_folder=False):
    if _manual_megavgmdrive_install(connection):
        _prepare_manual_megavgmdrive_for_downloader(connection, log, manual=True)
        remove_database_source_online(connection, MEGAVGMD_DB_ID)
        return _megavgmdrive_reboot_result()
    original = ensure_database_source_online(connection, MEGAVGMD_DB_ID, MEGAVGMD_DB_URL)
    try:
        native = uninstall_named_database_online(connection, MEGAVGMD_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(connection, MEGAVGMD_DB_ID, MEGAVGMD_DB_URL, filter_value="!all")
            run_named_database_online(connection, MEGAVGMD_DB_ID, log=log)
            remove_database_source_online(connection, MEGAVGMD_DB_ID)
        connection.run_command(f"rm -f {_quote(MEGAVGMD_RELEASE_MARKER_PATH)}")
        _remove_if_empty_dir(connection, MEGAVGMD_CONFIG_DIR)
    except Exception:
        restore_online(connection, original)
        raise
    log(f"Preserved user content in {MEGAVGMD_GAME_DIR}\n")
    return _megavgmdrive_reboot_result()


def uninstall_megavgmdrive_local(sd_root: str, log, force=False, remove_game_folder=False):
    if _manual_megavgmdrive_install_local(sd_root):
        _prepare_manual_megavgmdrive_for_downloader_local(sd_root, log, manual=True)
        remove_database_source_local(sd_root, MEGAVGMD_DB_ID)
        return _megavgmdrive_reboot_result()
    original = ensure_database_source_local(sd_root, MEGAVGMD_DB_ID, MEGAVGMD_DB_URL)
    try:
        native = uninstall_named_database_local(sd_root, MEGAVGMD_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(sd_root, MEGAVGMD_DB_ID, MEGAVGMD_DB_URL, filter_value="!all")
            run_named_database_local(sd_root, MEGAVGMD_DB_ID, log=log)
            remove_database_source_local(sd_root, MEGAVGMD_DB_ID)
        _remove_local_path(sd_root, MEGAVGMD_RELEASE_MARKER_PATH)
        _remove_if_empty_dir_local(sd_root, MEGAVGMD_CONFIG_DIR)
    except Exception:
        restore_local(sd_root, original)
        raise
    log(f"Preserved user content in {MEGAVGMD_GAME_DIR}\n")
    return _megavgmdrive_reboot_result()

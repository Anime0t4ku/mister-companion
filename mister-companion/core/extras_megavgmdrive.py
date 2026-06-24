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
    rbf_exists = _path_exists(connection, MEGAVGMD_RBF_PATH)
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
    rbf_exists = _path_exists_local(sd_root, MEGAVGMD_RBF_PATH)
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

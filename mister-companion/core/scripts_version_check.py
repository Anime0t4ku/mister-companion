import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from core.scripts_common import _local_path


GITHUB_SCRIPTS_BASE_URL = "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/main/Scripts"


@dataclass(frozen=True)
class ScriptUpdateTarget:
    handler: str
    filename: str
    remote_path: str
    remote_url: str


SCRIPT_UPDATE_TARGETS = {
    "auto_time": ScriptUpdateTarget(
        handler="auto_time",
        filename="auto_time.sh",
        remote_path="/media/fat/Scripts/auto_time.sh",
        remote_url=f"{GITHUB_SCRIPTS_BASE_URL}/auto_time.sh",
    ),
    "cd_game_organizer": ScriptUpdateTarget(
        handler="cd_game_organizer",
        filename="cd_game_organizer.sh",
        remote_path="/media/fat/Scripts/cd_game_organizer.sh",
        remote_url=f"{GITHUB_SCRIPTS_BASE_URL}/cd_game_organizer.sh",
    ),
    "dav_browser": ScriptUpdateTarget(
        handler="dav_browser",
        filename="dav_browser.sh",
        remote_path="/media/fat/Scripts/dav_browser.sh",
        remote_url=f"{GITHUB_SCRIPTS_BASE_URL}/dav_browser.sh",
    ),
    "ftp_save_sync": ScriptUpdateTarget(
        handler="ftp_save_sync",
        filename="ftp_save_sync.sh",
        remote_path="/media/fat/Scripts/ftp_save_sync.sh",
        remote_url=f"{GITHUB_SCRIPTS_BASE_URL}/ftp_save_sync.sh",
    ),
    "ra_viewer": ScriptUpdateTarget(
        handler="ra_viewer",
        filename="ra_viewer.sh",
        remote_path="/media/fat/Scripts/ra_viewer.sh",
        remote_url=f"{GITHUB_SCRIPTS_BASE_URL}/ra_viewer.sh",
    ),
    "static_wallpaper": ScriptUpdateTarget(
        handler="static_wallpaper",
        filename="static_wallpaper.sh",
        remote_path="/media/fat/Scripts/static_wallpaper.sh",
        remote_url=f"{GITHUB_SCRIPTS_BASE_URL}/static_wallpaper.sh",
    ),
    "syncthing": ScriptUpdateTarget(
        handler="syncthing",
        filename="syncthing.sh",
        remote_path="/media/fat/Scripts/syncthing.sh",
        remote_url=f"{GITHUB_SCRIPTS_BASE_URL}/syncthing.sh",
    ),
}


_VERSION_ASSIGNMENT_RE = re.compile(
    r"^\s*(?:SCRIPT_)?VERSION\s*=\s*['\"]?([^'\"\s#]+)",
    re.IGNORECASE | re.MULTILINE,
)
_VERSION_RE = re.compile(r"v?([0-9]+(?:\.[0-9]+){1,3})", re.IGNORECASE)


def supports_script_update_check(handler: str) -> bool:
    return str(handler or "") in SCRIPT_UPDATE_TARGETS


def normalize_script_version(value: str) -> str:
    match = _VERSION_RE.search(str(value or ""))
    return f"v{match.group(1)}" if match else ""


def parse_script_version(text: str) -> str:
    text = str(text or "")
    assignment = _VERSION_ASSIGNMENT_RE.search(text)
    if assignment:
        version = normalize_script_version(assignment.group(1))
        if version:
            return version
    return ""


def _version_tuple(value: str):
    normalized = normalize_script_version(value).lstrip("vV")
    parts = []
    for part in normalized.split("."):
        try:
            parts.append(int(part))
        except Exception:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_version_older(installed: str, latest: str) -> bool:
    if not installed:
        return bool(latest)
    if not latest:
        return False
    return _version_tuple(installed) < _version_tuple(latest)


def fetch_remote_script_version(handler: str) -> str:
    target = SCRIPT_UPDATE_TARGETS.get(handler)
    if not target:
        return ""
    response = requests.get(target.remote_url, timeout=20)
    response.raise_for_status()
    return parse_script_version(response.text)


def read_installed_script_version(connection, handler: str) -> str:
    target = SCRIPT_UPDATE_TARGETS.get(handler)
    if not target or connection is None:
        return ""
    output = connection.run_command(f"cat {target.remote_path} 2>/dev/null || true")
    return parse_script_version(output)


def read_installed_script_version_local(sd_root, handler: str) -> str:
    target = SCRIPT_UPDATE_TARGETS.get(handler)
    if not target:
        return ""
    path = _local_path(sd_root, target.remote_path)
    try:
        if not path.is_file():
            return ""
        return parse_script_version(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return ""


def apply_script_update_status(
    handler: str,
    base_status: dict,
    *,
    check_latest: bool = False,
    connection=None,
    sd_root: Optional[str] = None,
    offline: bool = False,
    log=None,
) -> dict:
    status = dict(base_status or {})
    if not supports_script_update_check(handler):
        return status
    if not status.get("installed"):
        return status

    installed_version = ""
    latest_version = ""
    latest_error = ""

    if offline:
        installed_version = read_installed_script_version_local(sd_root, handler)
    else:
        installed_version = read_installed_script_version(connection, handler)

    update_available = False

    if check_latest:
        try:
            target = SCRIPT_UPDATE_TARGETS[handler]
            if log:
                log(f"Checking latest {target.filename} version...\n")
            latest_version = fetch_remote_script_version(handler)
        except Exception as e:
            latest_error = str(e)

        # For these script entries, legacy MiSTer-side scripts without a VERSION
        # marker should always be offered an update.
        if not installed_version:
            update_available = True
        elif latest_version:
            update_available = is_version_older(installed_version, latest_version)

    status["installed_version"] = installed_version
    status["latest_version"] = latest_version
    status["latest_error"] = latest_error

    if update_available:
        status["state"] = "update_available"
        status["installed"] = True
        status["update_available"] = True
        status["install_label"] = "Update"
        status["install_enabled"] = True
        if installed_version and latest_version:
            status["status_text"] = f"Update available ({installed_version} → {latest_version})"
        elif installed_version:
            status["status_text"] = f"Update available ({installed_version})"
        elif latest_version:
            status["status_text"] = f"Update available (unknown → {latest_version})"
        else:
            status["status_text"] = "Update available (unknown installed version)"
        return status

    if installed_version:
        # Keep any useful configured/running wording, but expose the version in the
        # primary Installed label for simple script entries.
        text = str(status.get("status_text") or "Installed")
        if text == "Installed":
            status["status_text"] = f"Installed ({installed_version})"
    elif check_latest and latest_error:
        text = str(status.get("status_text") or "Installed")
        if text == "Installed":
            status["status_text"] = f"Installed (update check failed)"

    return status

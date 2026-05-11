import platform
import re
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path

import requests

from core.app_info import APP_VERSION, GITHUB_OWNER, GITHUB_REPO


@dataclass
class UpdateInfo:
    update_available: bool
    current_version: str
    latest_version: str
    release_url: str
    release_name: str


def normalize_version(version: str) -> tuple[int, int, int]:
    if not version:
        return (0, 0, 0)

    match = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        return (0, 0, 0)

    return tuple(int(part) for part in match.groups())


def check_for_update(timeout: int = 10) -> UpdateInfo:
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "MiSTer-Companion-Updater",
        },
    )
    response.raise_for_status()

    data = response.json()

    latest_version = data.get("tag_name", "") or data.get("name", "")
    release_url = data.get("html_url", "")
    release_name = data.get("name", latest_version)

    current_tuple = normalize_version(APP_VERSION)
    latest_tuple = normalize_version(latest_version)

    return UpdateInfo(
        update_available=latest_tuple > current_tuple,
        current_version=APP_VERSION,
        latest_version=latest_version,
        release_url=release_url,
        release_name=release_name,
    )


def is_windows() -> bool:
    return platform.system().lower() == "windows"


def get_app_folder() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


def get_mc_updater_path() -> Path:
    return get_app_folder() / "MC-Updater.exe"


def get_update_now_path() -> Path:
    return get_app_folder() / "updatenow.txt"


def mc_updater_available() -> bool:
    if not is_windows():
        return False

    return get_mc_updater_path().exists()


def launch_mc_updater() -> bool:
    if not is_windows():
        return False

    updater_path = get_mc_updater_path()

    if not updater_path.exists():
        return False

    update_now_path = get_update_now_path()
    update_now_path.write_text("", encoding="utf-8")

    subprocess.Popen(
        [str(updater_path)],
        cwd=str(updater_path.parent),
        shell=False,
    )

    return True


def open_release_page(url: str):
    if url:
        webbrowser.open(url)
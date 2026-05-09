import re
import webbrowser
from dataclasses import dataclass

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


def open_release_page(url: str):
    if url:
        webbrowser.open(url)
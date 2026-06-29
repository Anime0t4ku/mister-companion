import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import requests
from core.open_helpers import open_uri

from core.app_info import APP_VERSION, GITHUB_OWNER, GITHUB_REPO
from core.config import CONFIG_PATH
from core.app_paths import macos_application_support_dir


@dataclass
class UpdateInfo:
    update_available: bool
    current_version: str
    latest_version: str
    release_url: str
    release_name: str
    release_body: str


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
    release_body = data.get("body", "") or ""

    current_tuple = normalize_version(APP_VERSION)
    latest_tuple = normalize_version(latest_version)

    return UpdateInfo(
        update_available=latest_tuple > current_tuple,
        current_version=APP_VERSION,
        latest_version=latest_version,
        release_url=release_url,
        release_name=release_name,
        release_body=release_body,
    )


def current_platform_name() -> str:
    return platform.system().lower()


def is_windows() -> bool:
    return current_platform_name() == "windows"


def is_linux() -> bool:
    return current_platform_name() == "linux"


def is_macos() -> bool:
    return current_platform_name() == "darwin"


def is_macos_apple_silicon() -> bool:
    return is_macos() and platform.machine().lower() in {"arm64", "aarch64"}


def updater_supported() -> bool:
    return is_windows() or is_linux() or is_macos_apple_silicon()


def get_app_folder() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


def get_mc_updater_filename() -> str:
    if is_windows():
        return "MC-Updater.exe"

    if is_macos():
        return "MC-Updater.app"

    return "MC-Updater"


def get_mc_updater_path() -> Path:
    if is_macos():
        return Path("/Applications") / get_mc_updater_filename()

    return CONFIG_PATH.resolve().parent / get_mc_updater_filename()


def get_update_now_path() -> Path:
    if is_macos():
        update_root = macos_application_support_dir()
        update_root.mkdir(parents=True, exist_ok=True)
        return update_root / "updatenow.txt"

    return get_app_folder() / "updatenow.txt"


def make_executable(path: Path):
    if not path.exists():
        return

    if not is_linux():
        return

    current_mode = os.stat(path).st_mode
    os.chmod(
        path,
        current_mode
        | 0o100
        | 0o010
        | 0o001,
    )


def mc_updater_available() -> bool:
    if not updater_supported():
        return False

    updater_path = get_mc_updater_path()

    if not updater_path.exists():
        return False

    if is_linux():
        make_executable(updater_path)

    return True


def launch_mc_updater() -> bool:
    if not updater_supported():
        return False

    updater_path = get_mc_updater_path()

    if not updater_path.exists():
        return False

    if is_linux():
        make_executable(updater_path)

    update_now_path = get_update_now_path()
    update_now_path.write_text("", encoding="utf-8")

    if is_macos():
        subprocess.Popen(
            ["open", str(updater_path)],
            cwd=str(updater_path.parent),
            shell=False,
        )
    else:
        subprocess.Popen(
            [str(updater_path)],
            cwd=str(updater_path.parent),
            shell=False,
        )

    return True


def open_release_page(url: str):
    if url:
        open_uri(url)
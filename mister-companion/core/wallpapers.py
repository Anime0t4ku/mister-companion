import os
import subprocess
import sys
from typing import Callable

import requests


RANNY_API_URL = "https://api.github.com/repos/Ranny-Snice/Ranny-Snice-Wallpapers/contents/Wallpapers"
PCN_API_URL = "https://api.github.com/repos/Anime0t4ku/MiSTerWallpapers/contents/pcnchallenge"
OT4KU_API_URL = "https://api.github.com/repos/Anime0t4ku/MiSTerWallpapers/contents/0t4kuwallpapers"

WALLPAPER_DIR = "/media/fat/wallpapers"


def _fetch_github_files(url: str) -> list[dict]:
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return []

        data = response.json()
        return [item for item in data if item.get("type") == "file"]
    except Exception:
        return []


def fetch_ranny_wallpapers() -> tuple[list[dict], list[dict]]:
    files = _fetch_github_files(RANNY_API_URL)

    wallpapers_169 = []
    wallpapers_43 = []

    for item in files:
        name = item.get("name", "")
        if "4x3" in name.lower():
            wallpapers_43.append(item)
        else:
            wallpapers_169.append(item)

    return wallpapers_169, wallpapers_43


def fetch_pcn_wallpapers() -> list[dict]:
    return _fetch_github_files(PCN_API_URL)


def fetch_ot4ku_wallpapers() -> list[dict]:
    return _fetch_github_files(OT4KU_API_URL)


def get_installed_wallpapers(connection) -> list[str]:
    if not connection.is_connected():
        return []

    try:
        result = connection.run_command(f"ls -1 {WALLPAPER_DIR} 2>/dev/null")
        if not result:
            return []

        return [
            line.strip().replace("\r", "")
            for line in result.splitlines()
            if line.strip()
        ]
    except Exception:
        return []


def wallpaper_folder_exists(connection) -> bool:
    if not connection.is_connected():
        return False

    try:
        result = connection.run_command(f"test -d {WALLPAPER_DIR} && echo EXISTS")
        return "EXISTS" in (result or "")
    except Exception:
        return False


def ensure_wallpaper_folder(connection) -> None:
    if not connection.is_connected():
        return

    connection.run_command(f"mkdir -p {WALLPAPER_DIR}")


def download_wallpaper(url: str) -> bytes | None:
    try:
        response = requests.get(url, timeout=20)
        if response.status_code == 200:
            return response.content
    except Exception:
        pass

    return None


def upload_wallpaper(connection, name: str, data: bytes) -> bool:
    if not connection.is_connected():
        return False

    sftp = None
    try:
        sftp = connection.client.open_sftp()
        remote_path = f"{WALLPAPER_DIR}/{name}"

        with sftp.file(remote_path, "wb") as remote_file:
            remote_file.write(data)

        return True
    except Exception:
        return False
    finally:
        if sftp is not None:
            try:
                sftp.close()
            except Exception:
                pass


def install_wallpaper_items(
    connection,
    wallpapers: list[dict],
    log: Callable[[str], None],
) -> int:
    if not connection.is_connected():
        raise RuntimeError("Not connected")

    if not wallpapers:
        return 0

    ensure_wallpaper_folder(connection)
    installed = get_installed_wallpapers(connection)

    new_count = 0

    for item in wallpapers:
        name = item.get("name", "")
        download_url = item.get("download_url", "")

        if not name or not download_url:
            continue

        if any(name.lower() == installed_name.lower() for installed_name in installed):
            continue

        log(f"Downloading {name}...\n")
        data = download_wallpaper(download_url)

        if not data:
            log("Download failed\n")
            continue

        log(f"Uploading {name}...\n")
        ok = upload_wallpaper(connection, name, data)

        if ok:
            new_count += 1
            log(f"Installed {name}\n")
        else:
            log(f"Upload failed: {name}\n")

    return new_count


def remove_installed_wallpapers(
    connection,
    repo_items: list[dict],
    log: Callable[[str], None],
) -> int:
    if not connection.is_connected():
        raise RuntimeError("Not connected")

    repo_files = {item.get("name", "") for item in repo_items if item.get("name")}
    installed = get_installed_wallpapers(connection)

    removed = 0

    for name in installed:
        if name in repo_files:
            connection.run_command(f'rm "{WALLPAPER_DIR}/{name}"')
            removed += 1
            log(f"Removed {name}\n")

    return removed


def build_install_state(repo_items: list[dict], installed_files: list[str]) -> tuple[bool, bool]:
    installed_set = {name.lower() for name in installed_files}
    repo_names = {item.get("name", "").lower() for item in repo_items if item.get("name")}

    installed_matches = repo_names & installed_set
    missing = repo_names - installed_set

    has_installed = bool(installed_matches)
    has_missing = bool(missing)

    return has_installed, has_missing


def open_wallpaper_folder_on_host(ip: str, username: str = "root", password: str = "1") -> None:
    if not ip:
        raise ValueError("No MiSTer IP address is available.")

    if sys.platform.startswith("win"):
        subprocess.Popen(f'explorer "\\\\{ip}\\sdcard\\wallpapers"')
        return

    if sys.platform.startswith("linux"):
        env = os.environ.copy()

        subprocess.run(
            ["gio", "mount", f"smb://{ip}/"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        subprocess.Popen(
            ["gio", "open", f"smb://{ip}/sdcard/wallpapers"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    if sys.platform == "darwin":
        username = username or "root"
        password = password or "1"
        home = os.path.expanduser("~")
        mount_point = os.path.join(home, "MiSTer_sdcard")

        subprocess.run(["mkdir", "-p", mount_point], capture_output=True)
        subprocess.run(
            ["mount_smbfs", f"//{username}:{password}@{ip}/sdcard", mount_point],
            capture_output=True,
        )
        subprocess.Popen(["open", os.path.join(mount_point, "wallpapers")])
        return

    raise RuntimeError(f"Unsupported platform: {sys.platform}")
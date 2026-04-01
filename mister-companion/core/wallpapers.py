import io
import json
import os
import subprocess
import sys
import time
import zipfile
from typing import Callable

import requests


RANNY_DB_URL = "https://raw.githubusercontent.com/Ranny-Snice/Ranny-Snice-Wallpapers/db/db.json.zip"
PCN_DB_URL = "https://raw.githubusercontent.com/Anime0t4ku/MiSTerWallpapers/db/db/pcnchallenge.json.zip"
PCN_PREMIUM_DB_URL = "https://raw.githubusercontent.com/Anime0t4ku/MiSTerWallpapers/db/db/pcnpremium.json.zip"
OT4KU_DB_URL = "https://raw.githubusercontent.com/Anime0t4ku/MiSTerWallpapers/db/db/0t4kuwallpapers.json.zip"

RANNY_RAW_BASE = "https://raw.githubusercontent.com/Ranny-Snice/Ranny-Snice-Wallpapers/main/"
PCN_RAW_BASE = "https://raw.githubusercontent.com/Anime0t4ku/MiSTerWallpapers/main/"
PCN_PREMIUM_RAW_BASE = "https://raw.githubusercontent.com/Anime0t4ku/MiSTerWallpapers/main/"
OT4KU_RAW_BASE = "https://raw.githubusercontent.com/Anime0t4ku/MiSTerWallpapers/main/"

WALLPAPER_DIR = "/media/fat/wallpapers"

REQUEST_HEADERS = {
    "User-Agent": "MiSTer-Companion",
    "Accept": "*/*",
    "Cache-Control": "no-cache",
}

SESSION = requests.Session()
SESSION.headers.update(REQUEST_HEADERS)


def _request_with_retry(url: str, timeout: int = 15) -> requests.Response | None:
    for attempt in range(2):
        try:
            return SESSION.get(url, timeout=timeout)
        except requests.RequestException:
            if attempt == 0:
                time.sleep(1)
    return None


def _candidate_db_urls(url: str) -> list[str]:
    urls = [url]
    if url.lower().endswith(".json.zip"):
        urls.append(url[:-4])  # .json.zip -> .json
    return urls


def _load_db_json_from_bytes(data: bytes, source_url: str) -> dict | list | None:
    try:
        if source_url.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                json_name = next(
                    (name for name in zf.namelist() if name.lower().endswith(".json")),
                    None,
                )
                if not json_name:
                    return None

                with zf.open(json_name) as f:
                    return json.load(f)

        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def _join_raw_url(raw_base: str, repo_path: str) -> str:
    raw_base = raw_base.rstrip("/") + "/"
    repo_path = repo_path.lstrip("/")
    return raw_base + repo_path


def _normalize_db_items(data: dict | list, raw_base: str = "") -> list[dict]:
    items: list[dict] = []

    def build_item(repo_path: str, info: dict) -> dict | None:
        if not repo_path:
            return None

        name = repo_path.split("/")[-1].strip()
        if not name:
            return None

        download_url = (
            info.get("url")
            or info.get("raw_url")
            or info.get("download_url")
            or ""
        ).strip()

        if not download_url and raw_base:
            download_url = _join_raw_url(raw_base, repo_path)

        if not download_url:
            return None

        return {
            "name": name,
            "download_url": download_url,
        }

    if isinstance(data, dict):
        files = data.get("files")

        if isinstance(files, dict):
            for repo_path, info in files.items():
                if not isinstance(info, dict):
                    continue

                item = build_item(repo_path, info)
                if item:
                    items.append(item)

            if items:
                return items

        # fallback: top-level dict keyed by path
        for repo_path, info in data.items():
            if not isinstance(info, dict):
                continue

            item = build_item(repo_path, info)
            if item:
                items.append(item)

        if items:
            return items

    if isinstance(data, list):
        for entry in data:
            if not isinstance(entry, dict):
                continue

            repo_path = (
                entry.get("path")
                or entry.get("name")
                or ""
            ).strip()

            if not repo_path:
                continue

            item = build_item(repo_path, entry)
            if item:
                items.append(item)

    return items


def _fetch_db_items(url: str, raw_base: str = "") -> list[dict]:
    for candidate_url in _candidate_db_urls(url):
        response = _request_with_retry(candidate_url, timeout=20)
        if response is None or response.status_code != 200:
            continue

        data = _load_db_json_from_bytes(response.content, candidate_url)
        if data is None:
            continue

        items = _normalize_db_items(data, raw_base=raw_base)
        if items:
            return items

    return []


def fetch_ranny_wallpapers() -> tuple[list[dict], list[dict]]:
    files = _fetch_db_items(RANNY_DB_URL, raw_base=RANNY_RAW_BASE)

    wallpapers_169 = []
    wallpapers_43 = []

    for item in files:
        name = item.get("name", "")
        lower_name = name.lower()

        if "4x3" in lower_name or "4:3" in lower_name or "4-3" in lower_name:
            wallpapers_43.append(item)
        else:
            wallpapers_169.append(item)

    return wallpapers_169, wallpapers_43


def fetch_pcn_wallpapers() -> list[dict]:
    return _fetch_db_items(PCN_DB_URL, raw_base=PCN_RAW_BASE)


def fetch_pcn_premium_wallpapers() -> list[dict]:
    return _fetch_db_items(PCN_PREMIUM_DB_URL, raw_base=PCN_PREMIUM_RAW_BASE)


def fetch_ot4ku_wallpapers() -> list[dict]:
    return _fetch_db_items(OT4KU_DB_URL, raw_base=OT4KU_RAW_BASE)


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
    response = _request_with_retry(url, timeout=30)
    if response is not None and response.status_code == 200:
        return response.content
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
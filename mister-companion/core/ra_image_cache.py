import hashlib
import sys
from pathlib import Path

import requests
from PyQt6.QtCore import QThread, pyqtSignal


def get_app_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


def get_cache_dir():
    cache_dir = get_app_base_dir() / "ra_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def cache_path_for_url(url):
    url = str(url or "").strip()

    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()

    suffix = ".img"
    lowered = url.lower()

    for ext in [".png", ".jpg", ".jpeg", ".webp"]:
        if lowered.endswith(ext):
            suffix = ext
            break

    return get_cache_dir() / f"{digest}{suffix}"


def get_cached_image_bytes(url):
    url = str(url or "").strip()

    if not url:
        return b""

    path = cache_path_for_url(url)

    if path.exists() and path.is_file():
        try:
            return path.read_bytes()
        except Exception:
            return b""

    try:
        response = requests.get(url, timeout=12)
        response.raise_for_status()
        data = response.content or b""

        if data:
            path.write_bytes(data)

        return data

    except Exception:
        return b""


class RAImageWorker(QThread):
    loaded = pyqtSignal(str, bytes)

    def __init__(self, token, url):
        super().__init__()
        self.token = str(token)
        self.url = str(url or "").strip()

    def run(self):
        data = get_cached_image_bytes(self.url)
        self.loaded.emit(self.token, data)
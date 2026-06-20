import re
from pathlib import Path

from core.app_paths import generated_path


ZAPLAUNCHER_DIR = generated_path("zaplauncher")
ZAPLAUNCHER_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize(name: str) -> str:
    name = (name or "").strip()

    if not name:
        return "unknown"

    name = name.replace(".", "_").replace(" ", "_")
    name = re.sub(r'[<>:"/\\|?*]', "_", name)

    return name


def _get_cache_name(profile_name: str | None, ip: str) -> str:
    if profile_name:
        return _sanitize(profile_name)

    return _sanitize(ip)


def get_media_db_path(profile_name: str | None, ip: str) -> Path:
    name = _get_cache_name(profile_name, ip)
    return ZAPLAUNCHER_DIR / f"{name}_media.db"


def rename_db(old_name: str, new_name: str):
    if not old_name or not new_name or old_name == new_name:
        return

    old_safe = _sanitize(old_name)
    new_safe = _sanitize(new_name)

    old_path = ZAPLAUNCHER_DIR / f"{old_safe}_media.db"
    new_path = ZAPLAUNCHER_DIR / f"{new_safe}_media.db"

    if old_path.exists() and not new_path.exists():
        old_path.rename(new_path)


def get_last_scan_time(path: Path):
    if not path or not path.exists():
        return None

    return path.stat().st_mtime
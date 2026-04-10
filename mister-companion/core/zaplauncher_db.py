import json
from pathlib import Path

from core.app_dirs import USER_DATA_DIR

ZAPLAUNCHER_DIR = USER_DATA_DIR / "zaplauncher"
ZAPLAUNCHER_DIR.mkdir(exist_ok=True)

def _sanitize(name: str) -> str:
    return name.replace(".", "_").replace(" ", "_")


def get_db_path(profile_name: str | None, ip: str) -> Path:
    if profile_name:
        name = _sanitize(profile_name)
    else:
        name = _sanitize(ip)
    return ZAPLAUNCHER_DIR / f"{name}.json"


def rename_db(old_name: str, new_name: str):
    if not old_name or not new_name or old_name == new_name:
        return

    old_path = ZAPLAUNCHER_DIR / f"{_sanitize(old_name)}.json"
    new_path = ZAPLAUNCHER_DIR / f"{_sanitize(new_name)}.json"

    if old_path.exists() and not new_path.exists():
        old_path.rename(new_path)


def load_db(path: Path):
    if not path.exists():
        return {"entries": []}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_db(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_last_scan_time(path: Path):
    if not path.exists():
        return None
    return path.stat().st_mtime
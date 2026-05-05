import json
import re
from pathlib import Path


ZAPLAUNCHER_DIR = Path("zaplauncher")
ZAPLAUNCHER_DIR.mkdir(exist_ok=True)


def _sanitize(name: str) -> str:
    """
    Make a profile name or IP address safe for use as a filename.
    """
    name = (name or "").strip()

    if not name:
        return "unknown"

    # Keep simple readable names, but replace unsafe path characters.
    name = name.replace(".", "_").replace(" ", "_")
    name = re.sub(r'[<>:"/\\|?*]', "_", name)

    return name


def _get_cache_name(profile_name: str | None, ip: str) -> str:
    if profile_name:
        return _sanitize(profile_name)

    return _sanitize(ip)


def get_db_path(profile_name: str | None, ip: str) -> Path:
    """
    Legacy JSON cache path.

    Kept for compatibility with existing ZapScripts code.
    """
    name = _get_cache_name(profile_name, ip)
    return ZAPLAUNCHER_DIR / f"{name}.json"


def get_media_db_path(profile_name: str | None, ip: str) -> Path:
    """
    New downloaded Zaparoo media.db cache path.

    Example:
        zaplauncher/livingroom_media.db
        zaplauncher/192_168_1_50_media.db
    """
    name = _get_cache_name(profile_name, ip)
    return ZAPLAUNCHER_DIR / f"{name}_media.db"


def rename_db(old_name: str, new_name: str):
    """
    Rename cached ZapScripts files when a profile is renamed.

    Supports both:
        zaplauncher/<name>.json
        zaplauncher/<name>_media.db
    """
    if not old_name or not new_name or old_name == new_name:
        return

    old_safe = _sanitize(old_name)
    new_safe = _sanitize(new_name)

    rename_pairs = [
        (
            ZAPLAUNCHER_DIR / f"{old_safe}.json",
            ZAPLAUNCHER_DIR / f"{new_safe}.json",
        ),
        (
            ZAPLAUNCHER_DIR / f"{old_safe}_media.db",
            ZAPLAUNCHER_DIR / f"{new_safe}_media.db",
        ),
    ]

    for old_path, new_path in rename_pairs:
        if old_path.exists() and not new_path.exists():
            old_path.rename(new_path)


def load_db(path: Path):
    """
    Load the legacy JSON cache.

    Kept so old cached libraries and existing UI logic do not break.
    """
    if not path or not path.exists():
        return {"entries": []}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"entries": []}


def save_db(path: Path, data):
    """
    Save the legacy JSON cache.

    Kept for compatibility. The new media.db flow can avoid using this later.
    """
    if not path:
        return

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_last_scan_time(path: Path):
    """
    Return the modified time for either a JSON cache or downloaded media.db.
    """
    if not path or not path.exists():
        return None

    return path.stat().st_mtime
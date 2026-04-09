"""
app_dirs.py — Shared path resolution for MiSTer Companion
==========================================================
Import this wherever you need paths to user data (config, saves, etc.)

    from core.app_dirs import USER_DATA_DIR

When running from source:  USER_DATA_DIR = the source folder (original behaviour)
When running as a .app:    USER_DATA_DIR = ~/Library/Application Support/MiSTer Companion/

This means config.json, SaveManager/, etc. live in the right place in both
cases and persist across app updates when installed as a bundle.
"""

import sys
from pathlib import Path


def _resolve_user_data_dir() -> Path:
    if getattr(sys, "frozen", False) and sys.platform == "darwin":
        # Packaged .app on macOS → use the standard Application Support location
        base = Path.home() / "Library" / "Application Support" / "MiSTer Companion"
    elif getattr(sys, "frozen", False):
        # Packaged on Windows / Linux → next to the executable
        base = Path(sys.executable).resolve().parent
    else:
        # Running from source → project root (original behaviour, keeps nothing)
        base = Path(__file__).resolve().parent.parent

    base.mkdir(parents=True, exist_ok=True)
    return base


USER_DATA_DIR: Path = _resolve_user_data_dir()

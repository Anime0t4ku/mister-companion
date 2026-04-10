"""
app_dirs.py — Shared path resolution for MiSTer Companion
"""
import sys
from pathlib import Path

def _resolve_user_data_dir() -> Path:
    if getattr(sys, "frozen", False) and sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "MiSTer Companion"
    elif getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    base.mkdir(parents=True, exist_ok=True)
    return base

USER_DATA_DIR: Path = _resolve_user_data_dir()

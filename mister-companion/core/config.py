import json
from pathlib import Path

CONFIG_PATH = Path("config.json")

DEFAULT_CONFIG = {
    "devices": [],
    "last_connected": None,
    "theme_mode": "auto",
    "language": "en",
    "hide_setup_notice": False,
    "hide_update_all_warning": False,
    "hide_zapscripts_scan_notice": False,
    "use_ssh_agent": False,
    "look_for_ssh_keys": False,
}


def load_config():
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        merged = DEFAULT_CONFIG.copy()

        if isinstance(data, dict):
            merged.update(data)

        return merged

    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(data):
    merged = DEFAULT_CONFIG.copy()

    if isinstance(data, dict):
        merged.update(data)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=4)
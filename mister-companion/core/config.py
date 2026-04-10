import json
from pathlib import Path

CONFIG_PATH = Path("config.json")

DEFAULT_CONFIG = {
    "devices": [],
    "last_connected": None,
    "theme_mode": "auto",
    "hide_update_all_warning": False,
    "hide_zapscripts_scan_notice": False,
}


def load_config():
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

            merged = DEFAULT_CONFIG.copy()
            merged.update(data)

            for key, value in DEFAULT_CONFIG.items():
                if key not in merged:
                    merged[key] = value

            return merged

    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(data):
    merged = DEFAULT_CONFIG.copy()
    merged.update(data)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=4)
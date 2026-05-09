import json
from pathlib import Path

CONFIG_PATH = Path("config.json")

VALID_THEME_MODES = {"auto", "light", "dark"}

THEME_MODE_MIGRATIONS = {
    "purple": "dark",
}

DEFAULT_CONFIG = {
    "devices": [],
    "last_connected": None,
    "theme_mode": "auto",
    "hide_update_all_warning": False,
    "hide_zapscripts_scan_notice": False,
    "use_ssh_agent": False,
    "look_for_ssh_keys": False,
}


def normalize_theme_mode(value):
    mode = str(value or "auto").strip().lower()
    mode = THEME_MODE_MIGRATIONS.get(mode, mode)

    if mode not in VALID_THEME_MODES:
        return "auto"

    return mode


def normalize_config(data):
    merged = DEFAULT_CONFIG.copy()

    if isinstance(data, dict):
        merged.update(data)

    for key, value in DEFAULT_CONFIG.items():
        if key not in merged:
            merged[key] = value

    merged["theme_mode"] = normalize_theme_mode(merged.get("theme_mode"))

    merged.pop("offline_sd_root", None)

    return merged


def load_config():
    if not CONFIG_PATH.exists():
        return normalize_config(DEFAULT_CONFIG)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        return normalize_config(data)

    except Exception:
        return normalize_config(DEFAULT_CONFIG)


def save_config(data):
    merged = normalize_config(data)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=4)
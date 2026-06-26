import json
from core.app_info import APP_VERSION
from core.app_paths import generated_path

CONFIG_PATH = generated_path("config.json")

VALID_THEME_MODES = {"auto", "light", "dark"}
VALID_MENU_STYLES = {"side_menu", "tabs"}

THEME_MODE_MIGRATIONS = {
    "purple": "dark",
}

DEFAULT_CONFIG = {
    "app_version": APP_VERSION,
    "devices": [],
    "last_connected": None,
    "theme_mode": "auto",
    "hide_update_all_warning": False,
    "hide_zapscripts_scan_notice": False,
    "check_updates_on_startup": True,
    "use_ssh_agent": False,
    "look_for_ssh_keys": False,
    "menu_style": "side_menu",
    "remember_offline_sd_root": False,
    "offline_sd_root": "",
}


def normalize_theme_mode(value):
    mode = str(value or "auto").strip().lower()
    mode = THEME_MODE_MIGRATIONS.get(mode, mode)

    if mode.startswith("custom:") and len(mode.split(":", 1)[1].strip()) > 0:
        return mode

    if mode not in VALID_THEME_MODES:
        return "auto"

    return mode


def normalize_menu_style(value):
    style = str(value or "side_menu").strip().lower().replace("-", "_").replace(" ", "_")

    if style == "overlay":
        style = "side_menu"

    if style not in VALID_MENU_STYLES:
        return "side_menu"

    return style


def normalize_config(data):
    merged = DEFAULT_CONFIG.copy()

    if isinstance(data, dict):
        merged.update(data)

    for key, value in DEFAULT_CONFIG.items():
        if key not in merged:
            merged[key] = value

    merged["app_version"] = APP_VERSION
    merged["theme_mode"] = normalize_theme_mode(merged.get("theme_mode"))
    merged["menu_style"] = normalize_menu_style(merged.get("menu_style"))
    merged["remember_offline_sd_root"] = bool(merged.get("remember_offline_sd_root", False))

    if merged["remember_offline_sd_root"]:
        merged["offline_sd_root"] = str(merged.get("offline_sd_root", "") or "").strip()
    else:
        merged["offline_sd_root"] = ""

    return merged


def load_config():
    if not CONFIG_PATH.exists():
        config = normalize_config(DEFAULT_CONFIG)
        save_config(config)
        return config

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        config = normalize_config(data)
        save_config(config)
        return config

    except Exception:
        config = normalize_config(DEFAULT_CONFIG)
        save_config(config)
        return config


def save_config(data):
    merged = normalize_config(data)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=4)
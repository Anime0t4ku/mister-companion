import json
from core.app_info import APP_VERSION
from core.app_paths import generated_path

CONFIG_PATH = generated_path("config.json")

VALID_THEME_MODES = {"auto", "light", "dark"}
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
    "remember_offline_sd_root": False,
    "show_support_message": True,
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


def normalize_config(data):
    merged = DEFAULT_CONFIG.copy()

    if isinstance(data, dict):
        merged.update(data)

    for key, value in DEFAULT_CONFIG.items():
        if key not in merged:
            merged[key] = value

    merged["app_version"] = APP_VERSION
    merged["theme_mode"] = normalize_theme_mode(merged.get("theme_mode"))

    # Migrate the retired Files dialog settings to the File Manager tab.
    legacy_file_browser = merged.pop("file_browser", None)
    if "file_manager" not in merged and isinstance(legacy_file_browser, dict):
        file_manager = {}
        columns = legacy_file_browser.get("columns")
        if isinstance(columns, dict):
            file_manager["columns"] = columns
        sort_column = legacy_file_browser.get("sort_column")
        if sort_column in {"name", "size", "modified"}:
            file_manager["sort_column"] = sort_column
        file_manager["sort_descending"] = bool(legacy_file_browser.get("sort_descending", False))
        if file_manager:
            merged["file_manager"] = file_manager

    # Remove retired settings from existing configs.
    merged.pop("menu_style", None)
    merged.pop("show_news_widget", None)
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
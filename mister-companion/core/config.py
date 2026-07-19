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
    "romm_config": {
        "url": "",
        "token": "",
        "token_id": None,
        "token_name": "",
        "user_display": "",
        "sync_platforms": [],
        "sync_collections": [],
        "readonly_platforms": [],
        "readonly_collections": [],
        "sync_last_run": "",
        "sync_last_stats": {},
        "sync_manifest": {},
        "auto_sync": False,
        "sync_saves": False,
        "core_overrides": {},
        "mister_root": "/media/fat",
        "hide_unsupported": True,
        "hide_empty": True,
    },
}


def _normalize_mister_root(value) -> str:
    """MiSTer's game root path. Must be absolute, no trailing slash.

    Common values: /media/fat (SD), /media/usb0..5 (USB), /media/network (CIFS).
    """
    raw = str(value or "/media/fat").strip()
    if not raw.startswith("/"):
        raw = "/media/fat"
    return raw.rstrip("/") or "/media/fat"


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

    romm = merged.get("romm_config") or {}
    if not isinstance(romm, dict):
        romm = {}
    token_id = romm.get("token_id")
    if not isinstance(token_id, int):
        token_id = None

    def _int_list(v):
        if not isinstance(v, list):
            return []
        out = []
        for x in v:
            if isinstance(x, int):
                out.append(x)
        return out

    merged["romm_config"] = {
        "url": str(romm.get("url", "") or "").strip(),
        "token": str(romm.get("token", "") or ""),
        "token_id": token_id,
        "token_name": str(romm.get("token_name", "") or ""),
        "user_display": str(romm.get("user_display", "") or ""),
        "sync_platforms": _int_list(romm.get("sync_platforms")),
        "sync_collections": _int_list(romm.get("sync_collections")),
        "readonly_platforms": _int_list(romm.get("readonly_platforms")),
        "readonly_collections": _int_list(romm.get("readonly_collections")),
        "sync_last_run": str(romm.get("sync_last_run", "") or ""),
        "sync_last_stats": romm.get("sync_last_stats") if isinstance(romm.get("sync_last_stats"), dict) else {},
        "sync_manifest": romm.get("sync_manifest") if isinstance(romm.get("sync_manifest"), dict) else {},
        "auto_sync": bool(romm.get("auto_sync", False)),
        "sync_saves": bool(romm.get("sync_saves", False)),
        "core_overrides": {
            str(k).lower().strip(): str(v or "").strip()
            for k, v in (romm.get("core_overrides") or {}).items()
            if k
        } if isinstance(romm.get("core_overrides"), dict) else {},
        "mister_root": _normalize_mister_root(romm.get("mister_root")),
        "hide_unsupported": bool(romm.get("hide_unsupported", True)),
        "hide_empty": bool(romm.get("hide_empty", True)),
    }

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
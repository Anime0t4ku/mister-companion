import json
import time
import urllib.request
import ssl
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.app_paths import generated_path
from core.file_browser import join_remote_path, normalize_remote_path, ensure_remote_dir
from core.scripts_actions import (
    get_scripts_status,
    get_scripts_status_local,
    get_syncthing_status,
    get_syncthing_status_local,
    get_ra_viewer_status,
    get_ra_viewer_status_local,
    install_update_all,
    install_update_all_local,
    uninstall_update_all,
    uninstall_update_all_local,
    install_zaparoo,
    install_zaparoo_local,
    uninstall_zaparoo,
    uninstall_zaparoo_local,
    install_migrate_sd,
    install_migrate_sd_local,
    uninstall_migrate_sd,
    uninstall_migrate_sd_local,
    install_cifs_mount,
    install_cifs_mount_local,
    uninstall_cifs_mount,
    uninstall_cifs_mount_local,
    install_auto_time,
    install_auto_time_local,
    uninstall_auto_time,
    uninstall_auto_time_local,
    install_cd_game_organizer,
    install_cd_game_organizer_local,
    uninstall_cd_game_organizer,
    uninstall_cd_game_organizer_local,
    install_dav_browser,
    install_dav_browser_local,
    uninstall_dav_browser,
    uninstall_dav_browser_local,
    install_ftp_save_sync,
    install_ftp_save_sync_local,
    uninstall_ftp_save_sync,
    uninstall_ftp_save_sync_local,
    install_static_wallpaper,
    install_static_wallpaper_local,
    uninstall_static_wallpaper,
    uninstall_static_wallpaper_local,
    install_syncthing,
    install_syncthing_local,
    uninstall_syncthing,
    uninstall_syncthing_local,
    install_ra_viewer,
    install_ra_viewer_local,
    uninstall_ra_viewer,
    uninstall_ra_viewer_local,
)
from core.extras_3s_arm import (
    get_3sx_status,
    get_3sx_status_local,
    install_or_update_3sx,
    install_or_update_3sx_local,
    uninstall_3sx,
    uninstall_3sx_local,
)
from core.extras_sonic_mania import (
    get_sonic_mania_status,
    get_sonic_mania_status_local,
    install_or_update_sonic_mania,
    install_or_update_sonic_mania_local,
    uninstall_sonic_mania,
    uninstall_sonic_mania_local,
)
from core.extras_zaparoo_launcher import (
    get_zaparoo_launcher_status,
    get_zaparoo_launcher_status_local,
    install_or_update_zaparoo_launcher,
    install_or_update_zaparoo_launcher_local,
    uninstall_zaparoo_launcher,
    uninstall_zaparoo_launcher_local,
)
from core.extras_mms2_gb_core import (
    get_mms2_gb_core_status,
    get_mms2_gb_core_status_local,
    install_or_update_mms2_gb_core,
    install_or_update_mms2_gb_core_local,
    uninstall_mms2_gb_core,
    uninstall_mms2_gb_core_local,
)
from core.extras_paprium_megadrive import (
    get_paprium_megadrive_status,
    get_paprium_megadrive_status_local,
    install_or_update_paprium_megadrive,
    install_or_update_paprium_megadrive_local,
    uninstall_paprium_megadrive,
    uninstall_paprium_megadrive_local,
)
from core.extras_megavgmdrive import (
    get_megavgmdrive_status,
    get_megavgmdrive_status_local,
    install_or_update_megavgmdrive,
    install_or_update_megavgmdrive_local,
    uninstall_megavgmdrive,
    uninstall_megavgmdrive_local,
)
from core.extras_ra_cores import (
    get_ra_cores_status,
    get_ra_cores_status_local,
    install_or_update_ra_cores,
    install_or_update_ra_cores_local,
    uninstall_ra_cores,
    uninstall_ra_cores_local,
)

from core.wallpapers import (
    build_install_state,
    fetch_ot4ku_wallpapers,
    fetch_pcn_premium_wallpapers,
    fetch_pcn_wallpapers,
    fetch_ranny_wallpapers,
    get_installed_wallpapers,
    get_installed_wallpapers_local,
    install_wallpaper_items,
    install_wallpaper_items_local,
    open_wallpaper_folder_local,
    open_wallpaper_folder_on_host,
    remove_installed_wallpapers,
    remove_installed_wallpapers_local,
    wallpaper_folder_exists,
)

HUB_RAW_BASE_URL = "https://raw.githubusercontent.com/Anime0t4ku/mister-companion-hub/main/"
HUB_ROOT_CATALOG_URL = HUB_RAW_BASE_URL + "catalog.json"
HUB_CATALOG_URL = HUB_RAW_BASE_URL + "generated/catalog_full.json"
HUB_CATALOG_MIN_URL = HUB_RAW_BASE_URL + "generated/catalog_min.json"
ROM_MANIFEST_REMOTE_PATH = "/media/fat/Scripts/.config/mister_companion/install_center/installed_roms.json"

CATEGORY_FALLBACK = [
    {"id": "scripts", "name": "Scripts", "description": "Add extra functionality to your standard MiSTer FPGA setup through useful scripts and utilities.", "sort_order": 10},
    {"id": "cores", "name": "Cores", "description": "Custom and alternative cores that add features, improve compatibility, or offer different behavior from the standard MiSTer cores.", "sort_order": 20},
    {"id": "extras", "name": "Extras", "description": "MiSTer ARM ports, frontends, and additional tools that expand what your MiSTer setup can do.", "sort_order": 30},
    {"id": "roms", "name": "ROMs", "description": "Free homebrew games and demos for retro systems supported by MiSTer.", "sort_order": 40, "hide_when_empty": True},
    {"id": "wallpaper_packs", "name": "Wallpaper Packs", "description": "MiSTer wallpaper packs for customizing the look of your MiSTer menu.", "sort_order": 50},
]

FALLBACK_ITEMS = [
    ("update_all", "scripts", "script", "update_all", "update_all", "theypsilon", "update_all keeps your MiSTer FPGA setup up to date by downloading cores, scripts, databases, tools, and optional community content from configured update sources."),
    ("zaparoo", "scripts", "script", "zaparoo", "Zaparoo", "Zaparoo Project", "Zaparoo lets you launch games, media, scripts, and other MiSTer content by scanning NFC cards, tags, barcodes, or other supported readers. It also allows MiSTer Companion to launch games remotely from the ZapScripts tab."),
    ("migrate_sd", "scripts", "script", "migrate_sd", "migrate_sd", "theypsilon", "migrate_sd helps migrate an existing MiSTer SD card setup to another SD card, such as when moving to a larger card."),
    ("cifs_mount", "scripts", "script", "cifs_mount", "cifs_mount", "MiSTer community", "cifs_mount connects your MiSTer to a shared network folder, such as a NAS or PC share, so games and files can be accessed over your local network."),
    ("auto_time", "scripts", "script", "auto_time", "auto_time", "MiSTer community", "auto_time automatically detects your timezone and applies the correct date and time to your MiSTer."),
    ("cd_game_organizer", "scripts", "script", "cd_game_organizer", "CD Game Organizer", "MiSTer community", "cd_game_organizer organizes CD-based games into their own folders, helping keep virtual memory cards separated per game."),
    ("dav_browser", "scripts", "script", "dav_browser", "DAV Browser", "MiSTer community", "DAV Browser lets your MiSTer browse a WebDAV server, such as a NAS or remote file server, download ROMs or files, and optionally launch them after downloading."),
    ("ftp_save_sync", "scripts", "script", "ftp_save_sync", "FTP Save Sync", "Anime0t4ku", "ftp_save_sync automatically syncs your MiSTer saves to a remote FTP or SFTP server. It can also sync savestates and keep saves shared between multiple MiSTers."),
    ("static_wallpaper", "scripts", "script", "static_wallpaper", "Static Wallpaper", "Anime0t4ku", "static_wallpaper lets your MiSTer use a fixed menu wallpaper instead of the default changing wallpaper behavior."),
    ("syncthing", "scripts", "script", "syncthing", "Syncthing", "Syncthing", "Syncthing is a peer-to-peer file synchronization tool. On MiSTer, it can be used to sync folders such as saves or other files with your PC, NAS, or other devices."),
    ("ra_viewer", "scripts", "script", "ra_viewer", "RA Viewer", "MiSTer community", "RA Viewer shows your RetroAchievements progress directly on the MiSTer, including achievement information for your configured RetroAchievements account."),
    ("mms2_gb_core", "cores", "core", "mms2_gb_core", "MMS2 GB Core", "Heber", "Installs Heber’s custom GB core for MMS2 with physical cartridge support. The core is installed in a separate custom location and adds a MiSTer home screen shortcut for directly loading cartridges."),
    ("paprium_megadrive", "cores", "core", "paprium_megadrive", "Paprium MegaDrive", "Pezz82", "Installs Pezz82’s customized MegaDrive core for running Paprium. This only installs the core and launcher. Provide your own ROM and make sure you use the correct ROM version with WAV files."),
    ("megavgmdrive", "cores", "core", "megavgmdrive", "MegaVGMDrive", "dai-VGM", "Installs MegaVGMDrive, a MegaDrive/Genesis VGM playback core for MiSTer. This only installs the core, launcher, and game folder structure."),
    ("retroachievement_cores", "cores", "core", "retroachievement_cores", "RetroAchievement Cores", "MiSTer community", "RetroAchievement Cores adds RetroAchievements-enabled MiSTer cores and the required MiSTer_RA support files. It uses MGL launchers so your normal cores remain untouched."),
    ("3s_arm", "extras", "extra", "3s_arm", "3S-ARM", "MiSTer community", "3S-ARM is a MiSTer port/support package for Street Fighter III: Third Strike based on the PS2 version. It installs binaries/support files only, not game files."),
    ("sonic_mania_mister", "extras", "extra", "sonic_mania_mister", "Sonic Mania MiSTer", "MiSTer community", "Sonic Mania MiSTer lets your MiSTer run Sonic Mania using the MiSTer port, with support for the required Data.rsdk game file."),
    ("zaparoo_frontend", "extras", "extra", "zaparoo_frontend", "Zaparoo Frontend", "Zaparoo Project", "Zaparoo Frontend is a MiSTer frontend that provides a controller-friendly interface for browsing and launching your games, media, and other MiSTer content, with artwork support."),
    ("ranny_snice_wallpapers", "wallpaper_packs", "wallpaper_pack", "ranny_snice_wallpapers", "Ranny Snice Wallpapers", "Ranny Snice", "A collection of MiSTer menu wallpapers by Ranny Snice, available in both 16:9 and 4:3 versions."),
    ("pcn_challenge_wallpapers", "wallpaper_packs", "wallpaper_pack", "pcn_challenge_wallpapers", "PCN Challenge Wallpapers", "Pixel Cherry Ninja", "Wallpapers created during PCN livestreams based on audience requests."),
    ("pcn_premium_wallpapers", "wallpaper_packs", "wallpaper_pack", "pcn_premium_wallpapers", "PCN Premium Member Wallpapers", "Pixel Cherry Ninja", "A wallpaper pack created for PCN Premium members on YouTube and Patreon."),
    ("anime0t4ku_wallpapers", "wallpaper_packs", "wallpaper_pack", "anime0t4ku_wallpapers", "Anime0t4ku Wallpapers", "Anime0t4ku", "A personal wallpaper pack by Anime0t4ku, made without fixed constraints."),
]

SCRIPT_STATUS_ATTRS = {
    "update_all": "update_all_installed",
    "zaparoo": "zaparoo_installed",
    "migrate_sd": "migrate_sd_installed",
    "cifs_mount": "cifs_installed",
    "auto_time": "auto_time_installed",
    "cd_game_organizer": "cd_game_organizer_installed",
    "dav_browser": "dav_browser_installed",
    "ftp_save_sync": "ftp_save_sync_installed",
    "static_wallpaper": "static_wallpaper_installed",
}

SCRIPT_INSTALLERS = {
    "update_all": (install_update_all, install_update_all_local, uninstall_update_all, uninstall_update_all_local),
    "zaparoo": (install_zaparoo, install_zaparoo_local, uninstall_zaparoo, uninstall_zaparoo_local),
    "migrate_sd": (install_migrate_sd, install_migrate_sd_local, uninstall_migrate_sd, uninstall_migrate_sd_local),
    "cifs_mount": (install_cifs_mount, install_cifs_mount_local, uninstall_cifs_mount, uninstall_cifs_mount_local),
    "auto_time": (install_auto_time, install_auto_time_local, uninstall_auto_time, uninstall_auto_time_local),
    "cd_game_organizer": (install_cd_game_organizer, install_cd_game_organizer_local, uninstall_cd_game_organizer, uninstall_cd_game_organizer_local),
    "dav_browser": (install_dav_browser, install_dav_browser_local, uninstall_dav_browser, uninstall_dav_browser_local),
    "ftp_save_sync": (install_ftp_save_sync, install_ftp_save_sync_local, uninstall_ftp_save_sync, uninstall_ftp_save_sync_local),
    "static_wallpaper": (install_static_wallpaper, install_static_wallpaper_local, uninstall_static_wallpaper, uninstall_static_wallpaper_local),
    "syncthing": (install_syncthing, install_syncthing_local, uninstall_syncthing, uninstall_syncthing_local),
    "ra_viewer": (install_ra_viewer, install_ra_viewer_local, uninstall_ra_viewer, uninstall_ra_viewer_local),
}

EXTRA_HANDLERS = {
    "3s_arm": (get_3sx_status, get_3sx_status_local, install_or_update_3sx, install_or_update_3sx_local, uninstall_3sx, uninstall_3sx_local),
    "3sx_mister": (get_3sx_status, get_3sx_status_local, install_or_update_3sx, install_or_update_3sx_local, uninstall_3sx, uninstall_3sx_local),
    "sonic_mania_mister": (get_sonic_mania_status, get_sonic_mania_status_local, install_or_update_sonic_mania, install_or_update_sonic_mania_local, uninstall_sonic_mania, uninstall_sonic_mania_local),
    "zaparoo_frontend": (get_zaparoo_launcher_status, get_zaparoo_launcher_status_local, install_or_update_zaparoo_launcher, install_or_update_zaparoo_launcher_local, uninstall_zaparoo_launcher, uninstall_zaparoo_launcher_local),
    "mms2_gb_core": (get_mms2_gb_core_status, get_mms2_gb_core_status_local, install_or_update_mms2_gb_core, install_or_update_mms2_gb_core_local, uninstall_mms2_gb_core, uninstall_mms2_gb_core_local),
    "paprium_megadrive": (get_paprium_megadrive_status, get_paprium_megadrive_status_local, install_or_update_paprium_megadrive, install_or_update_paprium_megadrive_local, uninstall_paprium_megadrive, uninstall_paprium_megadrive_local),
    "megavgmdrive": (get_megavgmdrive_status, get_megavgmdrive_status_local, install_or_update_megavgmdrive, install_or_update_megavgmdrive_local, uninstall_megavgmdrive, uninstall_megavgmdrive_local),
    "retroachievement_cores": (get_ra_cores_status, get_ra_cores_status_local, install_or_update_ra_cores, install_or_update_ra_cores_local, uninstall_ra_cores, uninstall_ra_cores_local),
}

@dataclass
class InstallCenterContext:
    mode: str
    connection: object = None
    sd_root: str = ""

    @property
    def offline(self) -> bool:
        return self.mode == "offline"

    @property
    def online(self) -> bool:
        return not self.offline


def fallback_catalog() -> dict:
    return {
        "schema_version": 1,
        "catalog_version": "bundled",
        "name": "MiSTer Companion Hub",
        "updated": "bundled",
        "minimum_app_version": "6.0.0",
        "categories": CATEGORY_FALLBACK,
        "items": [
            {
                "schema_version": 1,
                "id": item_id,
                "category": category,
                "type": item_type,
                "handler": handler,
                "name": name,
                "author": author,
                "date_added": "2026-06-23T00:00:00Z",
                "description": description,
                "visibility": "public",
                "sort_order": index * 10,
            }
            for index, (item_id, category, item_type, handler, name, author, description) in enumerate(FALLBACK_ITEMS, start=1)
        ],
    }


def _read_url_json(url: str, timeout: int = 12) -> dict:
    headers = {
        "User-Agent": "MiSTer-Companion/Install-Center",
        "Accept": "application/json,text/plain,*/*",
        "Cache-Control": "no-cache",
    }
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read().decode("utf-8")
    except Exception:
        # Some Python.org macOS installs can fail GitHub HTTPS requests when
        # the local certificate bundle has not been installed. Retrying with an
        # unverified context keeps the public Hub catalog reachable without
        # requiring users to run an extra certificate installer first.
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            data = response.read().decode("utf-8")
    return json.loads(data)


def _cache_path() -> Path:
    return generated_path("install_center", "catalog_cache.json")


def _hub_url(path: str) -> str:
    path = str(path or "").strip()
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return HUB_RAW_BASE_URL + path.lstrip("/")


def _read_index_catalog(url: str) -> dict:
    catalog = _read_url_json(url)
    item_refs = catalog.get("items") or []
    if not item_refs or not all(isinstance(item, str) for item in item_refs):
        return catalog

    categories_file = catalog.get("categories_file") or "categories.json"
    categories_payload = _read_url_json(_hub_url(categories_file))
    if isinstance(categories_payload, dict):
        categories = categories_payload.get("categories") or []
    else:
        categories = categories_payload or []

    items = []
    for item_ref in item_refs:
        items.append(_read_url_json(_hub_url(item_ref)))

    full_catalog = dict(catalog)
    full_catalog["categories"] = categories
    full_catalog["items"] = items
    return full_catalog


def load_catalog() -> dict:
    errors = []

    for url, reader in (
        (HUB_CATALOG_URL, _read_url_json),
        (HUB_ROOT_CATALOG_URL, _read_index_catalog),
        (HUB_CATALOG_MIN_URL, _read_url_json),
    ):
        try:
            catalog = normalize_catalog(reader(url))
            catalog["source"] = url
            return catalog
        except Exception as e:
            errors.append(f"{url}: {e}")

    raise RuntimeError("Install Center catalog could not be loaded from GitHub.\n" + "\n".join(errors))


def normalize_catalog(catalog: dict) -> dict:
    if not isinstance(catalog, dict):
        raise ValueError("Catalog is not a JSON object.")

    categories = catalog.get("categories") or CATEGORY_FALLBACK
    items = catalog.get("items") or []
    category_default_thumbnails = {
        cat.get("id"): cat.get("default_thumbnail")
        for cat in categories
        if isinstance(cat, dict)
    }

    normalized_items = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if item.get("visibility") == "template":
            continue
        if not item.get("id") or not item.get("name"):
            continue
        normalized = dict(item)
        normalized.setdefault("sort_order", index * 10)
        normalized.setdefault("version", None)
        normalized.setdefault("release_date", None)
        normalized.setdefault("description", "")
        normalized.setdefault("category", "extras")
        normalized.setdefault("type", normalized.get("category", "extra"))
        normalized.setdefault("handler", normalized.get("id"))
        if not normalized.get("resolved_thumbnail"):
            normalized["resolved_thumbnail"] = normalized.get("thumbnail") or category_default_thumbnails.get(normalized.get("category"))
        normalized_items.append(normalized)

    category_ids_with_items = {item.get("category") for item in normalized_items}
    normalized_categories = []
    for cat in categories:
        if not isinstance(cat, dict):
            continue
        if cat.get("hide_when_empty") and cat.get("id") not in category_ids_with_items:
            continue
        normalized_categories.append(dict(cat))

    catalog = dict(catalog)
    catalog["categories"] = sorted(normalized_categories, key=lambda c: c.get("sort_order", 999))
    catalog["items"] = sorted(normalized_items, key=lambda i: (i.get("category", ""), i.get("sort_order", 999), i.get("name", "")))
    return catalog


def build_context(main_window) -> InstallCenterContext:
    offline = hasattr(main_window, "is_offline_mode") and main_window.is_offline_mode()
    if offline:
        sd_root = main_window.get_offline_sd_root() if hasattr(main_window, "get_offline_sd_root") else ""
        return InstallCenterContext(mode="offline", connection=main_window.connection, sd_root=sd_root)
    return InstallCenterContext(mode="online", connection=main_window.connection, sd_root="")


def context_ready(context: InstallCenterContext) -> tuple[bool, str]:
    if context.offline:
        if not context.sd_root:
            return False, "Needs SD card"
        return True, "Ready"
    if not context.connection or not context.connection.is_connected():
        return False, "Needs connection"
    return True, "Ready"


def _script_status_text(handler: str, scripts_status, syncthing_status=None, ra_viewer_status=None) -> dict:
    if handler == "syncthing":
        if isinstance(syncthing_status, dict):
            result = _status_from_text(syncthing_status.get("status_text", "Status unknown"), bool(syncthing_status.get("installed", False)), False)
            result.update({k: syncthing_status.get(k) for k in (
                "install_enabled", "boot_label", "boot_enabled", "uninstall_enabled",
                "running", "start_on_boot_enabled"
            )})
            return result
        return {"state": "unknown", "status_text": "Status unknown", "installed": False, "update_available": False}

    if handler == "ra_viewer":
        if isinstance(ra_viewer_status, dict):
            result = _status_from_text(ra_viewer_status.get("status_text", "Status unknown"), bool(ra_viewer_status.get("installed", False)), False)
            result.update({k: ra_viewer_status.get(k) for k in (
                "install_enabled", "edit_config_enabled", "uninstall_enabled"
            )})
            return result
        return {"state": "unknown", "status_text": "Status unknown", "installed": False, "update_available": False}

    attr = SCRIPT_STATUS_ATTRS.get(handler)
    installed = bool(getattr(scripts_status, attr, False)) if attr else False

    if not installed:
        return {"state": "not_installed", "status_text": "Not installed", "installed": False, "update_available": False}

    if handler == "zaparoo":
        if not getattr(scripts_status, "zaparoo_service_enabled", False):
            return {"state": "installed", "status_text": "Installed, service disabled", "installed": True, "update_available": False}
        return {"state": "installed", "status_text": "Installed", "installed": True, "update_available": False}

    if handler == "cifs_mount":
        if not getattr(scripts_status, "cifs_configured", False):
            return {"state": "installed", "status_text": "Installed, not configured", "installed": True, "update_available": False}
        return {"state": "installed", "status_text": "Configured", "installed": True, "update_available": False}

    if handler == "dav_browser":
        if not getattr(scripts_status, "dav_browser_configured", False):
            return {"state": "installed", "status_text": "Installed, not configured", "installed": True, "update_available": False}
        return {"state": "installed", "status_text": "Configured", "installed": True, "update_available": False}

    if handler == "ftp_save_sync":
        if not getattr(scripts_status, "ftp_save_sync_configured", False):
            return {"state": "installed", "status_text": "Installed, not configured", "installed": True, "update_available": False}
        if getattr(scripts_status, "ftp_save_sync_service_enabled", False):
            return {"state": "installed", "status_text": "Configured, service enabled", "installed": True, "update_available": False}
        return {"state": "installed", "status_text": "Configured, service disabled", "installed": True, "update_available": False}

    if handler == "static_wallpaper":
        if getattr(scripts_status, "static_wallpaper_active", False):
            return {"state": "installed", "status_text": "Installed, wallpaper active", "installed": True, "update_available": False}
        if getattr(scripts_status, "static_wallpaper_saved", False):
            return {"state": "installed", "status_text": "Installed, selection saved", "installed": True, "update_available": False}

    return {"state": "installed", "status_text": "Installed", "installed": True, "update_available": False}


def _status_from_text(text: str, installed=False, update_available=False) -> dict:
    lowered = str(text or "").lower()
    state = "unknown"
    if update_available or "update" in lowered:
        state = "update_available"
    elif installed or "installed" in lowered or "configured" in lowered:
        state = "installed"
    elif "not installed" in lowered:
        state = "not_installed"
    return {"state": state, "status_text": text or "Status unknown", "installed": state in {"installed", "update_available"}, "update_available": update_available or state == "update_available"}


def _extra_status(handler: str, context: InstallCenterContext, check_latest: bool, log=None) -> dict:
    functions = EXTRA_HANDLERS.get(handler)
    if not functions:
        return {"state": "unknown", "status_text": "Status unknown", "installed": False, "update_available": False}

    get_online, get_local = functions[0], functions[1]
    if log:
        log(f"Checking {handler.replace('_', ' ')}...\n")
    if context.offline:
        if handler == "retroachievement_cores":
            status = get_local(context.sd_root, check_latest=check_latest, log=log)
        else:
            status = get_local(context.sd_root, check_latest=check_latest)
    else:
        if handler == "retroachievement_cores":
            status = get_online(context.connection, check_latest=check_latest, log=log)
        else:
            status = get_online(context.connection, check_latest=check_latest)

    if not isinstance(status, dict):
        return {"state": "unknown", "status_text": "Status unknown", "installed": False, "update_available": False}

    installed = bool(status.get("installed"))
    update_available = bool(status.get("update_available"))
    text = status.get("status_text") or ("Update available" if update_available else "Installed" if installed else "Not installed")
    result = _status_from_text(text, installed=installed, update_available=update_available)
    result["installed_version"] = status.get("installed_version")
    result["latest_version"] = status.get("latest_version")
    for key in (
        "install_label", "install_enabled", "uninstall_enabled", "upload_enabled",
        "folder_open_enabled", "edit_config_enabled", "installed", "update_available"
    ):
        if key in status:
            result[key] = status.get(key)
    return result


def check_item_status(item: dict, context: InstallCenterContext, check_latest: bool = False, log=None) -> dict:
    ready, reason = context_ready(context)
    if not ready:
        return {"state": reason.lower().replace(" ", "_"), "status_text": reason, "installed": False, "update_available": False}

    item_id = item.get("id")
    handler = item.get("handler") or item_id
    item_type = item.get("type") or item.get("category")
    category = item.get("category")

    if item_type == "script" or category == "scripts":
        if log:
            log(f"Scanning {item.get('name') or handler} script status...\n")
        scripts_status = get_scripts_status_local(context.sd_root) if context.offline else get_scripts_status(context.connection)
        syncthing_status = None
        ra_viewer_status = None
        if handler == "syncthing":
            try:
                syncthing_status = get_syncthing_status_local(context.sd_root) if context.offline else get_syncthing_status(context.connection)
            except Exception as e:
                syncthing_status = {"status_text": f"Status unknown ({e})"}
        if handler == "ra_viewer":
            try:
                ra_viewer_status = get_ra_viewer_status_local(context.sd_root) if context.offline else get_ra_viewer_status(context.connection)
            except Exception as e:
                ra_viewer_status = {"status_text": f"Status unknown ({e})"}
        return _script_status_text(handler, scripts_status, syncthing_status, ra_viewer_status)
    if item_type in {"extra", "core"} or category in {"extras", "cores"}:
        return _extra_status(handler, context, check_latest, log=log)
    if item_type == "rom" or category == "roms":
        if log:
            log(f"Scanning ROM install manifest for {item.get('name') or item_id}...\n")
        return check_rom_status(item, context)
    if item_type == "wallpaper_pack" or category == "wallpaper_packs":
        if log:
            log(f"Scanning wallpaper pack status for {item.get('name') or item_id}...\n")
        return check_wallpaper_status(item, context)
    return {"state": "unknown", "status_text": "Status unknown", "installed": False, "update_available": False}

def check_all_status(catalog: dict, context: InstallCenterContext, check_latest: bool = False, log=None) -> dict:
    ready, reason = context_ready(context)
    results = {}

    if not ready:
        for item in catalog.get("items", []):
            results[item.get("id")] = {"state": reason.lower().replace(" ", "_"), "status_text": reason, "installed": False, "update_available": False}
        return results

    scripts_status = None
    syncthing_status = None
    ra_viewer_status = None

    if any((item.get("type") == "script" or item.get("category") == "scripts") for item in catalog.get("items", [])):
        if log:
            log("Scanning installed scripts once for all script entries...\n")
        scripts_status = get_scripts_status_local(context.sd_root) if context.offline else get_scripts_status(context.connection)
        try:
            syncthing_status = get_syncthing_status_local(context.sd_root) if context.offline else get_syncthing_status(context.connection)
        except Exception as e:
            syncthing_status = {"status_text": f"Status unknown ({e})"}
        try:
            ra_viewer_status = get_ra_viewer_status_local(context.sd_root) if context.offline else get_ra_viewer_status(context.connection)
        except Exception as e:
            ra_viewer_status = {"status_text": f"Status unknown ({e})"}

    for item in catalog.get("items", []):
        item_id = item.get("id")
        handler = item.get("handler") or item_id
        item_type = item.get("type") or item.get("category")
        category = item.get("category")

        try:
            item_name = item.get("name") or item_id or "item"
            if log:
                log(f"Checking {item_name}...\n")
            if item_type == "script" or category == "scripts":
                results[item_id] = _script_status_text(handler, scripts_status, syncthing_status, ra_viewer_status)
            elif item_type in {"extra", "core"} or category in {"extras", "cores"}:
                results[item_id] = _extra_status(handler, context, check_latest, log=log)
            elif item_type == "rom" or category == "roms":
                results[item_id] = check_rom_status(item, context)
            elif item_type == "wallpaper_pack" or category == "wallpaper_packs":
                results[item_id] = check_wallpaper_status(item, context)
            else:
                results[item_id] = {"state": "unknown", "status_text": "Status unknown", "installed": False, "update_available": False}
        except Exception as e:
            results[item_id] = {"state": "unknown", "status_text": f"Status unknown ({e})", "installed": False, "update_available": False}

    return results


def _local_manifest_path(sd_root: str) -> Path:
    root = Path(sd_root).expanduser().resolve()
    return root / "Scripts" / ".config" / "mister_companion" / "install_center" / "installed_roms.json"




def _wallpaper_handler_id(item_or_handler) -> str:
    if isinstance(item_or_handler, dict):
        handler = item_or_handler.get("handler") or item_or_handler.get("id")
        item_id = item_or_handler.get("id") or handler
    else:
        handler = item_or_handler
        item_id = handler
    if handler == "wallpaper_pack":
        return item_id
    return handler


def _wallpaper_fetch_items(handler: str, variant: str | None = None):
    handler = _wallpaper_handler_id(handler)
    if handler == "ranny_snice_wallpapers":
        wallpapers_169, wallpapers_43 = fetch_ranny_wallpapers()
        if variant == "169":
            return wallpapers_169
        if variant == "43":
            return wallpapers_43
        return wallpapers_169 + wallpapers_43
    if handler == "pcn_challenge_wallpapers":
        return fetch_pcn_wallpapers()
    if handler == "pcn_premium_wallpapers":
        return fetch_pcn_premium_wallpapers()
    if handler == "anime0t4ku_wallpapers":
        return fetch_ot4ku_wallpapers()
    return []


def check_wallpaper_status(item: dict, context: InstallCenterContext) -> dict:
    handler = _wallpaper_handler_id(item)
    installed_files = get_installed_wallpapers_local(context.sd_root) if context.offline else get_installed_wallpapers(context.connection)

    if handler == "ranny_snice_wallpapers":
        wallpapers_169, wallpapers_43 = fetch_ranny_wallpapers()
        installed_169, missing_169 = build_install_state(wallpapers_169, installed_files)
        installed_43, missing_43 = build_install_state(wallpapers_43, installed_files)
        installed = bool(installed_169 or installed_43)
        update_available = bool((installed_169 and missing_169) or (installed_43 and missing_43))
        result = {
            "ranny_169_installed": bool(installed_169),
            "ranny_169_missing": bool(missing_169),
            "ranny_43_installed": bool(installed_43),
            "ranny_43_missing": bool(missing_43),
        }
    else:
        wallpapers = _wallpaper_fetch_items(handler)
        installed, missing = build_install_state(wallpapers, installed_files)
        installed = bool(installed)
        update_available = bool(installed and missing)
        result = {
            "wallpaper_installed": bool(installed),
            "wallpaper_missing": bool(missing),
        }

    result.update({
        "state": "update_available" if update_available else "installed" if installed else "not_installed",
        "status_text": "Update available" if update_available else "Installed" if installed else "Not installed",
        "installed": installed,
        "update_available": update_available,
    })
    try:
        result["folder_available"] = True if context.offline else wallpaper_folder_exists(context.connection)
    except Exception:
        result["folder_available"] = False
    return result


def install_wallpaper_pack(item: dict, context: InstallCenterContext, log: Callable[[str], None], variant: str | None = None):
    handler = _wallpaper_handler_id(item)
    wallpapers = _wallpaper_fetch_items(handler, variant=variant)
    if not wallpapers:
        log("No wallpapers found.\n")
        return
    if context.offline:
        count = install_wallpaper_items_local(context.sd_root, wallpapers, log)
    else:
        count = install_wallpaper_items(context.connection, wallpapers, log)
    log(f"\nFinished. {count} wallpapers installed.\n")


def uninstall_wallpaper_pack(item: dict, context: InstallCenterContext, log: Callable[[str], None]):
    wallpapers = _wallpaper_fetch_items(_wallpaper_handler_id(item))
    if context.offline:
        removed = remove_installed_wallpapers_local(context.sd_root, wallpapers, log)
    else:
        removed = remove_installed_wallpapers(context.connection, wallpapers, log)
    log(f"\nFinished. {removed} wallpapers removed.\n")


def open_wallpaper_folder(context: InstallCenterContext):
    if context.offline:
        open_wallpaper_folder_local(context.sd_root)
    else:
        open_wallpaper_folder_on_host(
            context.connection.host,
            context.connection.username or "root",
            context.connection.password or "1",
        )


def _rom_manifest_path_for_context(context: InstallCenterContext):
    if context.offline:
        return _local_manifest_path(context.sd_root)
    return ROM_MANIFEST_REMOTE_PATH


def _empty_rom_manifest():
    return {"schema_version": 1, "installed_roms": {}}


def _read_rom_manifest(context: InstallCenterContext) -> dict:
    try:
        if context.offline:
            path = _local_manifest_path(context.sd_root)
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data.setdefault("installed_roms", {})
                    return data
        else:
            raw = context.connection.run_command(f"cat {ROM_MANIFEST_REMOTE_PATH} 2>/dev/null")
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    data.setdefault("installed_roms", {})
                    return data
    except Exception:
        pass
    return _empty_rom_manifest()


def _write_rom_manifest(context: InstallCenterContext, manifest: dict):
    manifest.setdefault("schema_version", 1)
    manifest.setdefault("installed_roms", {})
    text = json.dumps(manifest, indent=2, ensure_ascii=False)
    if context.offline:
        path = _local_manifest_path(context.sd_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return

    sftp = context.connection.client.open_sftp()
    try:
        ensure_remote_dir(sftp, "/media/fat/Scripts/.config/mister_companion/install_center")
        with sftp.open(ROM_MANIFEST_REMOTE_PATH, "w") as handle:
            handle.write(text)
    finally:
        sftp.close()


def normalize_mister_relative_path(path: str, default="/games") -> str:
    text = str(path or default).replace("\\", "/").strip()
    if not text:
        text = default
    if text.startswith("/media/fat"):
        text = text[len("/media/fat"):]
    if text.startswith("/media/usb0"):
        text = text[len("/media/usb0"):]
    if not text.startswith("/"):
        text = "/" + text
    text = normalize_remote_path(text)
    if text == "/":
        text = default
    return text


def resolve_mister_relative_path(context: InstallCenterContext, relative_path: str) -> str:
    relative_path = normalize_mister_relative_path(relative_path)
    if context.offline:
        return str(Path(context.sd_root).expanduser().resolve() / relative_path.strip("/"))
    return "/media/fat" + relative_path


def _download_rom_file(url: str, log: Callable[[str], None]) -> bytes:
    if not url:
        raise RuntimeError("This ROM entry does not have a download URL.")
    log(f"Downloading {url}...\n")
    request = urllib.request.Request(url, headers={"User-Agent": "MiSTer-Companion/Install-Center"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except Exception:
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=60, context=context) as response:
            return response.read()


def _rom_install_extensions(item: dict):
    download = item.get("download") or {}
    extensions = download.get("install_extensions") or []
    if isinstance(extensions, str):
        extensions = [extensions]
    return {str(ext).lower() for ext in extensions if str(ext).startswith(".")}


def _rom_download_filename(item: dict, url: str) -> str:
    name = str((item.get("download") or {}).get("filename") or "").strip()
    if not name:
        name = Path(str(url).split("?", 1)[0]).name
    if not name:
        name = f"{item.get('id', 'rom')}.rom"
    return name


def _write_rom_file(context: InstallCenterContext, target_relative: str, data: bytes, log: Callable[[str], None]):
    target_relative = normalize_mister_relative_path(target_relative)
    if context.offline:
        target = Path(resolve_mister_relative_path(context, target_relative))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    else:
        target = resolve_mister_relative_path(context, target_relative)
        sftp = context.connection.client.open_sftp()
        try:
            ensure_remote_dir(sftp, str(Path(target).parent).replace("\\", "/"))
            with sftp.open(target, "wb") as handle:
                handle.write(data)
        finally:
            sftp.close()
    log(f"Installed {target_relative}\n")


def _delete_rom_file(context: InstallCenterContext, target_relative: str, log: Callable[[str], None]):
    target_relative = normalize_mister_relative_path(target_relative)
    if context.offline:
        target = Path(resolve_mister_relative_path(context, target_relative))
        if target.exists() and target.is_file():
            target.unlink()
            log(f"Removed {target_relative}\n")
    else:
        target = resolve_mister_relative_path(context, target_relative)
        try:
            context.connection.run_command(f"rm -f {json.dumps(target)}")
            log(f"Removed {target_relative}\n")
        except Exception as e:
            log(f"Could not remove {target_relative}: {e}\n")


def install_rom_item(item: dict, context: InstallCenterContext, log: Callable[[str], None], install_path: str | None = None):
    item_id = item.get("id")
    if not item_id:
        raise RuntimeError("ROM entry is missing an id.")
    download = item.get("download") or {}
    url = download.get("url")
    download_type = str(download.get("type") or "file").lower()
    install_path = normalize_mister_relative_path(install_path or item.get("default_install_path") or "/games")
    data = _download_rom_file(url, log)
    installed_files = []

    if download_type == "archive":
        allowed_exts = _rom_install_extensions(item)
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "download.zip"
            archive_path.write_bytes(data)
            try:
                with zipfile.ZipFile(archive_path, "r") as archive:
                    for info in archive.infolist():
                        if info.is_dir():
                            continue
                        name = Path(info.filename).name
                        if not name:
                            continue
                        ext = Path(name).suffix.lower()
                        if allowed_exts and ext not in allowed_exts:
                            continue
                        file_data = archive.read(info.filename)
                        target_relative = normalize_mister_relative_path(join_remote_path(install_path, name))
                        _write_rom_file(context, target_relative, file_data, log)
                        installed_files.append(target_relative)
            except zipfile.BadZipFile:
                raise RuntimeError("The downloaded archive could not be opened.")
    else:
        filename = _rom_download_filename(item, url)
        target_relative = normalize_mister_relative_path(join_remote_path(install_path, filename))
        _write_rom_file(context, target_relative, data, log)
        installed_files.append(target_relative)

    if not installed_files:
        raise RuntimeError("No installable ROM files were found in the download.")

    manifest = _read_rom_manifest(context)
    manifest.setdefault("installed_roms", {})[item_id] = {
        "id": item_id,
        "name": item.get("name") or item_id,
        "system": item.get("system"),
        "installed_version": item.get("version"),
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "install_path": install_path,
        "installed_files": installed_files,
        "source_catalog_version": item.get("version"),
    }
    _write_rom_manifest(context, manifest)
    log("ROM install manifest updated.\n")


def uninstall_rom_item(item: dict, context: InstallCenterContext, log: Callable[[str], None]):
    item_id = item.get("id")
    manifest = _read_rom_manifest(context)
    installed_roms = manifest.setdefault("installed_roms", {})
    entry = installed_roms.get(item_id)
    if not entry:
        log("This ROM is not tracked as installed.\n")
        return
    for target_relative in entry.get("installed_files") or []:
        _delete_rom_file(context, target_relative, log)
    installed_roms.pop(item_id, None)
    _write_rom_manifest(context, manifest)
    log("ROM install manifest updated.\n")


def check_rom_status(item: dict, context: InstallCenterContext) -> dict:
    item_id = item.get("id")
    catalog_version = item.get("version")
    manifest = _read_rom_manifest(context)
    entry = (manifest.get("installed_roms") or {}).get(item_id)
    if not entry:
        return {"state": "not_installed", "status_text": "Not installed", "installed": False, "update_available": False}

    installed_version = entry.get("installed_version")
    update_available = bool(catalog_version and installed_version and str(catalog_version) != str(installed_version))
    return {
        "state": "update_available" if update_available else "installed",
        "status_text": "Update available" if update_available else "Installed",
        "installed": True,
        "update_available": update_available,
        "installed_version": installed_version,
        "latest_version": catalog_version,
        "install_path": entry.get("install_path"),
    }

def action_supported(item: dict, status: dict, action: str) -> bool:
    category = item.get("category")
    item_type = item.get("type")
    state = (status or {}).get("state")
    installed = bool((status or {}).get("installed"))

    if category == "wallpaper_packs" or item_type == "wallpaper_pack":
        if action == "install_update":
            return True
        if action == "uninstall":
            return installed
        if action == "open_folder":
            return True
        return False

    if item_type == "rom" or category == "roms":
        if action == "install_update":
            return state in {"not_installed", "update_available"}
        if action == "uninstall":
            return installed
        if action == "choose_install_folder":
            return bool(item.get("allow_custom_install_path", False)) and not installed
        return False

    if action == "install_update":
        return state in {"not_installed", "update_available"}
    if action == "uninstall":
        return installed
    if action == "configure":
        return installed and (item.get("handler") in {"update_all", "cifs_mount", "dav_browser", "ftp_save_sync", "ra_viewer", "retroachievement_cores"})
    if action == "run":
        return installed and item.get("handler") == "update_all"
    return False


def run_install_or_update(item: dict, context: InstallCenterContext, log: Callable[[str], None]):
    handler = item.get("handler") or item.get("id")
    category = item.get("category")
    item_type = item.get("type")

    if item_type == "script" or category == "scripts":
        functions = SCRIPT_INSTALLERS.get(handler)
        if not functions:
            raise RuntimeError("This script does not have an Install Center installer yet.")
        install_online, install_local = functions[0], functions[1]
        if context.offline:
            install_local(context.sd_root, log)
        else:
            install_online(context.connection, log)
        return

    if item_type in {"extra", "core"} or category in {"extras", "cores"}:
        functions = EXTRA_HANDLERS.get(handler)
        if not functions:
            raise RuntimeError("This entry does not have an Install Center installer yet.")
        install_online, install_local = functions[2], functions[3]
        if context.offline:
            install_local(context.sd_root, log)
        else:
            install_online(context.connection, log)
        return

    if item_type == "rom" or category == "roms":
        install_rom_item(item, context, log, install_path=item.get("_selected_install_path"))
        return

    if item_type == "wallpaper_pack" or category == "wallpaper_packs":
        install_wallpaper_pack(item, context, log)
        return

    raise RuntimeError("Install is not available for this entry yet.")


def run_uninstall(item: dict, context: InstallCenterContext, log: Callable[[str], None]):
    handler = item.get("handler") or item.get("id")
    category = item.get("category")
    item_type = item.get("type")

    if item_type == "script" or category == "scripts":
        functions = SCRIPT_INSTALLERS.get(handler)
        if not functions:
            raise RuntimeError("This script does not have an Install Center uninstaller yet.")
        uninstall_online, uninstall_local = functions[2], functions[3]
        if handler in {"syncthing", "ra_viewer"}:
            if context.offline:
                uninstall_local(context.sd_root, log)
            else:
                uninstall_online(context.connection, log)
        else:
            if context.offline:
                uninstall_local(context.sd_root)
            else:
                uninstall_online(context.connection)
        log("Uninstall finished.\n")
        return

    if item_type in {"extra", "core"} or category in {"extras", "cores"}:
        functions = EXTRA_HANDLERS.get(handler)
        if not functions:
            raise RuntimeError("This entry does not have an Install Center uninstaller yet.")
        uninstall_online, uninstall_local = functions[4], functions[5]
        if context.offline:
            uninstall_local(context.sd_root, log)
        else:
            uninstall_online(context.connection, log)
        return

    if item_type == "rom" or category == "roms":
        uninstall_rom_item(item, context, log)
        return

    if item_type == "wallpaper_pack" or category == "wallpaper_packs":
        uninstall_wallpaper_pack(item, context, log)
        return

    raise RuntimeError("Uninstall is not available for this entry yet.")

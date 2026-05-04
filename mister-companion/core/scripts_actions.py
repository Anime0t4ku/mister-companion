from core.scripts_common import (
    ScriptsStatus,
    check_update_all_initialized,
    ensure_remote_scripts_dir,
    ensure_update_all_config_bootstrap,
    get_scripts_status,
    get_static_wallpaper_saved_selection,
    get_static_wallpaper_state,
    has_static_wallpaper_saved_selection,
    is_ftp_save_sync_service_enabled,
    is_static_wallpaper_active,
    open_scripts_folder_on_host,
    reload_mister_menu,
)

from core.scripts_update_all import (
    install_update_all,
    run_update_all_stream,
    uninstall_update_all,
)

from core.scripts_zaparoo import (
    enable_zaparoo_service,
    install_zaparoo,
    uninstall_zaparoo,
)

from core.scripts_migrate_sd import (
    install_migrate_sd,
    uninstall_migrate_sd,
)

from core.scripts_cifs_mount import (
    install_cifs_mount,
    load_cifs_config,
    remove_cifs_config,
    run_cifs_mount,
    run_cifs_umount,
    save_cifs_config,
    test_cifs_connection,
    uninstall_cifs_mount,
)

from core.scripts_auto_time import (
    install_auto_time,
    uninstall_auto_time,
)

from core.scripts_dav_browser import (
    install_dav_browser,
    load_dav_browser_config,
    remove_dav_browser_config,
    save_dav_browser_config,
    uninstall_dav_browser,
)

from core.scripts_ftp_save_sync import (
    disable_ftp_save_sync_service,
    enable_ftp_save_sync_service,
    ensure_ftp_save_sync_bootstrap,
    install_ftp_save_sync,
    load_ftp_save_sync_config,
    remove_ftp_save_sync_config,
    save_ftp_save_sync_config,
    uninstall_ftp_save_sync,
)

from core.scripts_static_wallpaper import (
    apply_static_wallpaper,
    get_static_wallpaper_preview_bytes,
    install_static_wallpaper,
    list_static_wallpapers,
    remove_static_wallpaper,
    uninstall_static_wallpaper,
)

from core.scripts_syncthing import (
    disable_syncthing_start_on_boot,
    enable_syncthing_start_on_boot,
    get_syncthing_status,
    install_syncthing,
    is_syncthing_running,
    is_syncthing_start_on_boot_enabled,
    start_syncthing,
    stop_syncthing,
    toggle_syncthing_start_on_boot,
    uninstall_syncthing,
)

from core.scripts_ra_viewer import (
    get_ra_viewer_status,
    install_ra_viewer,
    load_ra_viewer_config,
    save_ra_viewer_config,
    uninstall_ra_viewer,
)


__all__ = [
    "ScriptsStatus",
    "ensure_remote_scripts_dir",
    "ensure_update_all_config_bootstrap",
    "check_update_all_initialized",
    "get_scripts_status",
    "open_scripts_folder_on_host",

    "install_update_all",
    "uninstall_update_all",
    "run_update_all_stream",

    "install_zaparoo",
    "enable_zaparoo_service",
    "uninstall_zaparoo",

    "install_migrate_sd",
    "uninstall_migrate_sd",

    "install_cifs_mount",
    "uninstall_cifs_mount",
    "run_cifs_mount",
    "run_cifs_umount",
    "remove_cifs_config",
    "load_cifs_config",
    "save_cifs_config",
    "test_cifs_connection",

    "install_auto_time",
    "uninstall_auto_time",

    "install_dav_browser",
    "uninstall_dav_browser",
    "load_dav_browser_config",
    "save_dav_browser_config",
    "remove_dav_browser_config",

    "install_ftp_save_sync",
    "uninstall_ftp_save_sync",
    "load_ftp_save_sync_config",
    "save_ftp_save_sync_config",
    "remove_ftp_save_sync_config",
    "enable_ftp_save_sync_service",
    "disable_ftp_save_sync_service",
    "ensure_ftp_save_sync_bootstrap",
    "is_ftp_save_sync_service_enabled",

    "install_static_wallpaper",
    "uninstall_static_wallpaper",
    "remove_static_wallpaper",
    "list_static_wallpapers",
    "get_static_wallpaper_preview_bytes",
    "apply_static_wallpaper",
    "reload_mister_menu",
    "is_static_wallpaper_active",
    "has_static_wallpaper_saved_selection",
    "get_static_wallpaper_saved_selection",
    "get_static_wallpaper_state",

    "install_syncthing",
    "uninstall_syncthing",
    "get_syncthing_status",
    "start_syncthing",
    "stop_syncthing",
    "is_syncthing_running",
    "is_syncthing_start_on_boot_enabled",
    "enable_syncthing_start_on_boot",
    "disable_syncthing_start_on_boot",
    "toggle_syncthing_start_on_boot",

    "get_ra_viewer_status",
    "install_ra_viewer",
    "uninstall_ra_viewer",
    "load_ra_viewer_config",
    "save_ra_viewer_config",
]
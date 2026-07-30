import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from core.open_helpers import open_local_folder, open_smb_share


UPDATE_ALL_JSON_PATH = "/media/fat/Scripts/.config/update_all/update_all.json"
DOWNLOADER_INI_PATH = "/media/fat/downloader.ini"

DAV_BROWSER_CONFIG_DIR = "/media/fat/Scripts/.config/dav_browser"
DAV_BROWSER_CONFIG_PATH = "/media/fat/Scripts/.config/dav_browser/dav_browser.ini"
DAV_BROWSER_RCLONE_PATH = "/media/fat/Scripts/.config/dav_browser/rclone"
DAV_BROWSER_RCLONE_URL = "https://downloads.rclone.org/rclone-current-linux-arm.zip"

FTP_SAVE_SYNC_CONFIG_DIR = "/media/fat/Scripts/.config/ftp_save_sync"
FTP_SAVE_SYNC_CONFIG_PATH = "/media/fat/Scripts/.config/ftp_save_sync/ftp_save_sync.ini"
FTP_SAVE_SYNC_STARTUP_PATH = "/media/fat/linux/user-startup.sh"
FTP_SAVE_SYNC_DAEMON_PATH = "/media/fat/Scripts/.config/ftp_save_sync/ftp_save_sync_daemon.sh"
FTP_SAVE_SYNC_DAEMON_LINE = "/media/fat/Scripts/.config/ftp_save_sync/ftp_save_sync_daemon.sh >/dev/null 2>&1"
FTP_SAVE_SYNC_RCLONE_PATH = "/media/fat/Scripts/.config/ftp_save_sync/rclone"
FTP_SAVE_SYNC_RCLONE_URL = "https://downloads.rclone.org/rclone-current-linux-arm.zip"
FTP_SAVE_SYNC_LOG_PATH = "/media/fat/Scripts/.config/ftp_save_sync/ftp_save_sync.log"
FTP_SAVE_SYNC_STATE_PATH = "/media/fat/Scripts/.config/ftp_save_sync/ftp_save_sync_state.db"

CIFS_MOUNT_SCRIPT_PATH = "/media/fat/Scripts/cifs_mount.sh"
CIFS_UMOUNT_SCRIPT_PATH = "/media/fat/Scripts/cifs_umount.sh"
CIFS_COMMON_SCRIPT_PATH = "/media/fat/Scripts/cifs_common.sh"

STATIC_WALLPAPER_SCRIPT_PATH = "/media/fat/Scripts/static_wallpaper.sh"
STATIC_WALLPAPER_CONFIG_DIR = "/media/fat/Scripts/.config/static_wallpaper"
STATIC_WALLPAPER_CONFIG_PATH = "/media/fat/Scripts/.config/static_wallpaper/selected_wallpaper.txt"
STATIC_WALLPAPER_DIR = "/media/fat/wallpapers"
STATIC_WALLPAPER_TARGET_JPG = "/media/fat/menu.jpg"
STATIC_WALLPAPER_TARGET_PNG = "/media/fat/menu.png"
MISTER_MENU_RELOAD_CMD = 'echo "load_core /media/fat/menu.rbf" > /dev/MiSTer_cmd'

DEFAULT_UPDATE_ALL_JSON = """{"migration_version": 6, "theme": "Blue Installer", "mirror": "", "countdown_time": 15, "log_viewer": true, "use_settings_screen_theme_in_log_viewer": true, "autoreboot": true, "download_beta_cores": false, "names_region": "JP", "names_char_code": "CHAR18", "names_sort_code": "Common", "introduced_arcade_names_txt": true, "pocket_firmware_update": false, "pocket_backup": false, "timeline_after_logs": true, "overscan": "medium", "monochrome_ui": false}
"""

DEFAULT_DOWNLOADER_INI = """[distribution_mister]
db_url = https://raw.githubusercontent.com/MiSTer-devel/Distribution_MiSTer/main/db.json.zip

[jtcores]
db_url = https://raw.githubusercontent.com/jotego/jtcores_mister/main/jtbindb.json.zip

[Coin-OpCollection/Distribution-MiSTerFPGA]
db_url = https://raw.githubusercontent.com/Coin-OpCollection/Distribution-MiSTerFPGA/db/db.json.zip

[update_all_mister]
db_url = https://raw.githubusercontent.com/theypsilon/Update_All_MiSTer/db/update_all_db.json
"""


@dataclass
class ScriptsStatus:
    update_all_installed: bool
    update_all_initialized: bool
    zaparoo_installed: bool
    zaparoo_service_enabled: bool
    migrate_sd_installed: bool
    cifs_installed: bool
    cifs_configured: bool
    auto_time_installed: bool
    cd_game_organizer_installed: bool
    dav_browser_installed: bool
    dav_browser_configured: bool
    ftp_save_sync_installed: bool
    ftp_save_sync_configured: bool
    ftp_save_sync_service_enabled: bool
    static_wallpaper_installed: bool
    static_wallpaper_active: bool
    static_wallpaper_saved: bool
    cifs_common_installed: bool = False
    cifs_common_required: bool = False
    cifs_umount_installed: bool = False


def empty_scripts_status() -> ScriptsStatus:
    return ScriptsStatus(
        False, False, False, False, False, False, False,
        False, False, False, False, False, False, False,
        False, False, False,
    )


def _local_path(sd_root, remote_path):
    if not sd_root:
        raise ValueError("No Offline SD Card root is selected.")

    normalized = str(remote_path).replace("\\", "/")

    if normalized == "/media/fat":
        relative = ""
    elif normalized.startswith("/media/fat/"):
        relative = normalized[len("/media/fat/"):]
    else:
        relative = normalized.lstrip("/")

    return Path(sd_root).expanduser().resolve() / relative


def ensure_local_scripts_dir(sd_root):
    _local_path(sd_root, "/media/fat/Scripts").mkdir(parents=True, exist_ok=True)
    _local_path(sd_root, "/media/fat/Scripts/.config/update_all").mkdir(parents=True, exist_ok=True)
    _local_path(sd_root, "/media/fat/Scripts/.config/dav_browser").mkdir(parents=True, exist_ok=True)
    _local_path(sd_root, FTP_SAVE_SYNC_CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    _local_path(sd_root, STATIC_WALLPAPER_CONFIG_DIR).mkdir(parents=True, exist_ok=True)


def _local_file_exists(sd_root, remote_path):
    try:
        return _local_path(sd_root, remote_path).is_file()
    except Exception:
        return False


def _cifs_mount_text_requires_common(text):
    return "cifs_common.sh" in (text or "")


def _local_dir_exists(sd_root, remote_path):
    try:
        return _local_path(sd_root, remote_path).is_dir()
    except Exception:
        return False


def _write_local_bytes(sd_root, remote_path, data):
    path = _local_path(sd_root, remote_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_local_text(sd_root, remote_path, text):
    path = _local_path(sd_root, remote_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_local_bytes(sd_root, remote_path):
    return _local_path(sd_root, remote_path).read_bytes()


def _read_local_text(sd_root, remote_path):
    return _local_path(sd_root, remote_path).read_text(encoding="utf-8", errors="ignore")


def _chmod_local_executable(sd_root, remote_path):
    path = _local_path(sd_root, remote_path)
    if not path.exists():
        return

    try:
        path.chmod(path.stat().st_mode | 0o755)
    except Exception:
        pass


def _remove_local_file(sd_root, remote_path):
    path = _local_path(sd_root, remote_path)
    if path.exists() and path.is_file():
        path.unlink()


def ensure_remote_scripts_dir(connection):
    connection.run_command("mkdir -p /media/fat/Scripts")
    connection.run_command("mkdir -p /media/fat/Scripts/.config/update_all")
    connection.run_command("mkdir -p /media/fat/Scripts/.config/dav_browser")
    connection.run_command(f"mkdir -p {FTP_SAVE_SYNC_CONFIG_DIR}")
    connection.run_command(f"mkdir -p {STATIC_WALLPAPER_CONFIG_DIR}")


def _remote_file_exists(sftp, path):
    try:
        sftp.stat(path)
        return True
    except Exception:
        return False


def _write_remote_bytes(connection, path, data):
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "wb") as remote_file:
            remote_file.write(data)
    finally:
        sftp.close()


def _write_remote_text(connection, path, text):
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "w") as remote_file:
            remote_file.write(text)
    finally:
        sftp.close()


def _read_remote_bytes(connection, path):
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "rb") as remote_file:
            return remote_file.read()
    finally:
        sftp.close()


def _read_remote_text(connection, path):
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "r") as remote_file:
            return remote_file.read()
    finally:
        sftp.close()


def _remote_command_success(connection, command):
    result = connection.run_command(f"{command} >/dev/null 2>&1 && echo OK || echo FAIL")
    return "OK" in (result or "")


def ensure_update_all_config_bootstrap(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    ensure_remote_scripts_dir(connection)

    created = {
        "update_all_json_created": False,
        "downloader_ini_created": False,
    }

    sftp = connection.client.open_sftp()
    try:
        if not _remote_file_exists(sftp, UPDATE_ALL_JSON_PATH):
            with sftp.open(UPDATE_ALL_JSON_PATH, "w") as handle:
                handle.write(DEFAULT_UPDATE_ALL_JSON)
            created["update_all_json_created"] = True

        if not _remote_file_exists(sftp, DOWNLOADER_INI_PATH):
            with sftp.open(DOWNLOADER_INI_PATH, "w") as handle:
                handle.write(DEFAULT_DOWNLOADER_INI)
            created["downloader_ini_created"] = True
    finally:
        sftp.close()

    return created


def ensure_update_all_config_bootstrap_local(sd_root):
    ensure_local_scripts_dir(sd_root)

    created = {
        "update_all_json_created": False,
        "downloader_ini_created": False,
    }

    update_all_json = _local_path(sd_root, UPDATE_ALL_JSON_PATH)
    downloader_ini = _local_path(sd_root, DOWNLOADER_INI_PATH)

    if not update_all_json.exists():
        update_all_json.parent.mkdir(parents=True, exist_ok=True)
        update_all_json.write_text(DEFAULT_UPDATE_ALL_JSON, encoding="utf-8")
        created["update_all_json_created"] = True

    if not downloader_ini.exists():
        downloader_ini.parent.mkdir(parents=True, exist_ok=True)
        downloader_ini.write_text(DEFAULT_DOWNLOADER_INI, encoding="utf-8")
        created["downloader_ini_created"] = True

    return created


def check_update_all_initialized(connection) -> bool:
    if not connection.is_connected():
        return False

    sftp = None
    try:
        sftp = connection.client.open_sftp()
        sftp.stat(UPDATE_ALL_JSON_PATH)
        return True
    except Exception:
        return False
    finally:
        if sftp is not None:
            sftp.close()


def check_update_all_initialized_local(sd_root) -> bool:
    return _local_file_exists(sd_root, UPDATE_ALL_JSON_PATH)


def is_ftp_save_sync_service_enabled(connection) -> bool:
    if not connection.is_connected():
        return False

    check = connection.run_command(
        f"grep -F '{FTP_SAVE_SYNC_DAEMON_LINE}' {FTP_SAVE_SYNC_STARTUP_PATH} 2>/dev/null"
    )
    return bool(check and "ftp_save_sync_daemon.sh" in check)


def is_ftp_save_sync_service_enabled_local(sd_root) -> bool:
    startup_path = _local_path(sd_root, FTP_SAVE_SYNC_STARTUP_PATH)

    if not startup_path.exists():
        return False

    try:
        text = startup_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False

    return FTP_SAVE_SYNC_DAEMON_LINE in text


def reload_mister_menu(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    connection.run_command(MISTER_MENU_RELOAD_CMD)


def is_static_wallpaper_active(connection) -> bool:
    if not connection.is_connected():
        return False

    jpg_check = connection.run_command(
        f"test -f {STATIC_WALLPAPER_TARGET_JPG} && echo EXISTS"
    )
    png_check = connection.run_command(
        f"test -f {STATIC_WALLPAPER_TARGET_PNG} && echo EXISTS"
    )
    return ("EXISTS" in (jpg_check or "")) or ("EXISTS" in (png_check or ""))


def is_static_wallpaper_active_local(sd_root) -> bool:
    return (
        _local_file_exists(sd_root, STATIC_WALLPAPER_TARGET_JPG)
        or _local_file_exists(sd_root, STATIC_WALLPAPER_TARGET_PNG)
    )


def has_static_wallpaper_saved_selection(connection) -> bool:
    if not connection.is_connected():
        return False

    check = connection.run_command(
        f"test -f {STATIC_WALLPAPER_CONFIG_PATH} && echo EXISTS"
    )
    return "EXISTS" in (check or "")


def has_static_wallpaper_saved_selection_local(sd_root) -> bool:
    return _local_file_exists(sd_root, STATIC_WALLPAPER_CONFIG_PATH)


def get_static_wallpaper_saved_selection(connection) -> str:
    if not connection.is_connected():
        return ""

    output = connection.run_command(f"cat {STATIC_WALLPAPER_CONFIG_PATH} 2>/dev/null")
    return (output or "").strip()


def get_static_wallpaper_saved_selection_local(sd_root) -> str:
    path = _local_path(sd_root, STATIC_WALLPAPER_CONFIG_PATH)

    if not path.exists():
        return ""

    try:
        return path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""


def get_static_wallpaper_state(connection) -> dict:
    if not connection.is_connected():
        return {
            "installed": False,
            "active": False,
            "active_target": "",
            "saved": False,
            "saved_path": "",
            "saved_name": "",
        }

    installed_check = connection.run_command(
        f"test -f {STATIC_WALLPAPER_SCRIPT_PATH} && echo EXISTS"
    )
    jpg_check = connection.run_command(
        f"test -f {STATIC_WALLPAPER_TARGET_JPG} && echo EXISTS"
    )
    png_check = connection.run_command(
        f"test -f {STATIC_WALLPAPER_TARGET_PNG} && echo EXISTS"
    )
    saved_path = get_static_wallpaper_saved_selection(connection)

    active_target = ""
    if "EXISTS" in (jpg_check or ""):
        active_target = "menu.jpg"
    elif "EXISTS" in (png_check or ""):
        active_target = "menu.png"

    return {
        "installed": "EXISTS" in (installed_check or ""),
        "active": bool(active_target),
        "active_target": active_target,
        "saved": bool(saved_path),
        "saved_path": saved_path,
        "saved_name": os.path.basename(saved_path) if saved_path else "",
    }


def get_static_wallpaper_state_local(sd_root) -> dict:
    saved_path = get_static_wallpaper_saved_selection_local(sd_root)

    active_target = ""
    if _local_file_exists(sd_root, STATIC_WALLPAPER_TARGET_JPG):
        active_target = "menu.jpg"
    elif _local_file_exists(sd_root, STATIC_WALLPAPER_TARGET_PNG):
        active_target = "menu.png"

    return {
        "installed": _local_file_exists(sd_root, STATIC_WALLPAPER_SCRIPT_PATH),
        "active": bool(active_target),
        "active_target": active_target,
        "saved": bool(saved_path),
        "saved_path": saved_path,
        "saved_name": os.path.basename(saved_path) if saved_path else "",
    }


def get_scripts_status(connection) -> ScriptsStatus:
    if not connection.is_connected():
        return empty_scripts_status()

    checks = [
        ("update_all_installed", "/media/fat/Scripts/update_all.sh"),
        ("update_all_initialized", UPDATE_ALL_JSON_PATH),
        ("zaparoo_installed", "/media/fat/Scripts/zaparoo.sh"),
        ("migrate_sd_installed", "/media/fat/Scripts/migrate_sd.sh"),
        ("cifs_installed", CIFS_MOUNT_SCRIPT_PATH),
        ("cifs_umount_installed", CIFS_UMOUNT_SCRIPT_PATH),
        ("cifs_configured", "/media/fat/Scripts/cifs_mount.ini"),
        ("cifs_common_installed", CIFS_COMMON_SCRIPT_PATH),
        ("auto_time_installed", "/media/fat/Scripts/auto_time.sh"),
        ("cd_game_organizer_installed", "/media/fat/Scripts/cd_game_organizer.sh"),
        ("dav_browser_installed", "/media/fat/Scripts/dav_browser.sh"),
        ("dav_browser_configured", DAV_BROWSER_CONFIG_PATH),
        ("ftp_save_sync_installed", "/media/fat/Scripts/ftp_save_sync.sh"),
        ("ftp_save_sync_configured", FTP_SAVE_SYNC_CONFIG_PATH),
        ("static_wallpaper_installed", STATIC_WALLPAPER_SCRIPT_PATH),
        ("static_wallpaper_saved", STATIC_WALLPAPER_CONFIG_PATH),
        ("static_wallpaper_jpg", STATIC_WALLPAPER_TARGET_JPG),
        ("static_wallpaper_png", STATIC_WALLPAPER_TARGET_PNG),
    ]

    command_parts = [
        f"test -f '{path}' && printf '{key}=1\n' || printf '{key}=0\n'"
        for key, path in checks
    ]
    command_parts.extend([
        "grep -q 'mrext/zaparoo' /media/fat/linux/user-startup.sh 2>/dev/null "
        "&& printf 'zaparoo_service_enabled=1\n' || printf 'zaparoo_service_enabled=0\n'",
        f"grep -Fq '{FTP_SAVE_SYNC_DAEMON_LINE}' {FTP_SAVE_SYNC_STARTUP_PATH} 2>/dev/null "
        "&& printf 'ftp_save_sync_service_enabled=1\n' || printf 'ftp_save_sync_service_enabled=0\n'",
        f"grep -q 'cifs_common.sh' {CIFS_MOUNT_SCRIPT_PATH} 2>/dev/null "
        "&& printf 'cifs_common_required=1\n' || printf 'cifs_common_required=0\n'",
    ])

    output = connection.run_command("; ".join(command_parts)) or ""
    values = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator and value in {"0", "1"}:
            values[key.strip()] = value == "1"

    static_wallpaper_active = bool(
        values.get("static_wallpaper_jpg") or values.get("static_wallpaper_png")
    )

    return ScriptsStatus(
        update_all_installed=values.get("update_all_installed", False),
        update_all_initialized=values.get("update_all_initialized", False),
        zaparoo_installed=values.get("zaparoo_installed", False),
        zaparoo_service_enabled=values.get("zaparoo_service_enabled", False),
        migrate_sd_installed=values.get("migrate_sd_installed", False),
        cifs_installed=values.get("cifs_installed", False),
        cifs_configured=values.get("cifs_configured", False),
        cifs_common_installed=values.get("cifs_common_installed", False),
        cifs_common_required=values.get("cifs_common_required", False),
        cifs_umount_installed=values.get("cifs_umount_installed", False),
        auto_time_installed=values.get("auto_time_installed", False),
        cd_game_organizer_installed=values.get("cd_game_organizer_installed", False),
        dav_browser_installed=values.get("dav_browser_installed", False),
        dav_browser_configured=values.get("dav_browser_configured", False),
        ftp_save_sync_installed=values.get("ftp_save_sync_installed", False),
        ftp_save_sync_configured=values.get("ftp_save_sync_configured", False),
        ftp_save_sync_service_enabled=values.get("ftp_save_sync_service_enabled", False),
        static_wallpaper_installed=values.get("static_wallpaper_installed", False),
        static_wallpaper_active=static_wallpaper_active,
        static_wallpaper_saved=values.get("static_wallpaper_saved", False),
    )


def get_scripts_status_local(sd_root) -> ScriptsStatus:
    if not sd_root:
        return empty_scripts_status()

    try:
        update_all_installed = _local_file_exists(sd_root, "/media/fat/Scripts/update_all.sh")
        zaparoo_installed = _local_file_exists(sd_root, "/media/fat/Scripts/zaparoo.sh")
        migrate_sd_installed = _local_file_exists(sd_root, "/media/fat/Scripts/migrate_sd.sh")
        cifs_installed = _local_file_exists(sd_root, CIFS_MOUNT_SCRIPT_PATH)
        cifs_umount_installed = _local_file_exists(sd_root, CIFS_UMOUNT_SCRIPT_PATH)
        cifs_configured = _local_file_exists(sd_root, "/media/fat/Scripts/cifs_mount.ini")
        cifs_common_installed = _local_file_exists(sd_root, CIFS_COMMON_SCRIPT_PATH)
        cifs_common_required = _cifs_mount_text_requires_common(_read_local_text(sd_root, CIFS_MOUNT_SCRIPT_PATH)) if cifs_installed else False
        auto_time_installed = _local_file_exists(sd_root, "/media/fat/Scripts/auto_time.sh")
        cd_game_organizer_installed = _local_file_exists(sd_root, "/media/fat/Scripts/cd_game_organizer.sh")
        dav_browser_installed = _local_file_exists(sd_root, "/media/fat/Scripts/dav_browser.sh")
        dav_browser_configured = _local_file_exists(sd_root, DAV_BROWSER_CONFIG_PATH)
        ftp_save_sync_installed = _local_file_exists(sd_root, "/media/fat/Scripts/ftp_save_sync.sh")
        ftp_save_sync_configured = _local_file_exists(sd_root, FTP_SAVE_SYNC_CONFIG_PATH)
        static_wallpaper_installed = _local_file_exists(sd_root, STATIC_WALLPAPER_SCRIPT_PATH)
        static_wallpaper_active = is_static_wallpaper_active_local(sd_root)
        static_wallpaper_saved = has_static_wallpaper_saved_selection_local(sd_root)

        zaparoo_service_enabled = False
        startup_path = _local_path(sd_root, "/media/fat/linux/user-startup.sh")
        if startup_path.exists():
            startup_text = startup_path.read_text(encoding="utf-8", errors="ignore")
            zaparoo_service_enabled = "mrext/zaparoo" in startup_text

        ftp_save_sync_service_enabled = (
            is_ftp_save_sync_service_enabled_local(sd_root)
            if ftp_save_sync_installed
            else False
        )

        return ScriptsStatus(
            update_all_installed=update_all_installed,
            update_all_initialized=check_update_all_initialized_local(sd_root) if update_all_installed else False,
            zaparoo_installed=zaparoo_installed,
            zaparoo_service_enabled=zaparoo_service_enabled,
            migrate_sd_installed=migrate_sd_installed,
            cifs_installed=cifs_installed,
            cifs_configured=cifs_configured,
            cifs_common_installed=cifs_common_installed,
            cifs_common_required=cifs_common_required,
            cifs_umount_installed=cifs_umount_installed,
            auto_time_installed=auto_time_installed,
            cd_game_organizer_installed=cd_game_organizer_installed,
            dav_browser_installed=dav_browser_installed,
            dav_browser_configured=dav_browser_configured,
            ftp_save_sync_installed=ftp_save_sync_installed,
            ftp_save_sync_configured=ftp_save_sync_configured,
            ftp_save_sync_service_enabled=ftp_save_sync_service_enabled,
            static_wallpaper_installed=static_wallpaper_installed,
            static_wallpaper_active=static_wallpaper_active,
            static_wallpaper_saved=static_wallpaper_saved,
        )
    except Exception:
        return empty_scripts_status()


def open_scripts_folder_on_host(ip, username="root", password="1"):
    open_smb_share(ip, "sdcard/Scripts")


def open_scripts_folder_local(sd_root):
    scripts_dir = _local_path(sd_root, "/media/fat/Scripts")
    scripts_dir.mkdir(parents=True, exist_ok=True)
    open_local_folder(scripts_dir)

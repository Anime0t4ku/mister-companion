import os
import subprocess
import sys
import time

from core.profile_folder_sync import sanitize_folder_name, ip_to_folder_name


from core.app_dirs import USER_DATA_DIR
MISTER_SETTINGS_ROOT = str(USER_DATA_DIR / "MiSTerSettings")


def ensure_settings_root_exists():
    os.makedirs(MISTER_SETTINGS_ROOT, exist_ok=True)


def get_mister_settings_device_name(profile_name, host):
    profile_name = (profile_name or "").strip()
    if profile_name and profile_name != "Select Device":
        return sanitize_folder_name(profile_name)

    host = (host or "").strip()
    if host:
        return ip_to_folder_name(host)

    return ""


def get_mister_settings_device_path(profile_name, host):
    device_name = get_mister_settings_device_name(profile_name, host)
    if not device_name:
        return os.path.abspath(MISTER_SETTINGS_ROOT)
    return os.path.abspath(os.path.join(MISTER_SETTINGS_ROOT, device_name))


def save_mister_settings_retention_setting(config_data, value):
    value = max(1, int(value))
    config_data["mister_settings_retention"] = value

    from core.config import save_config
    save_config(config_data)


def open_mister_settings_folder(path):
    os.makedirs(path, exist_ok=True)

    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", path])
    elif sys.platform.startswith("linux"):
        env = os.environ.copy()
        subprocess.Popen(
            ["gio", "open", path],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])


def ensure_mister_ini_exists(connection):
    if not connection.is_connected():
        return False, "Not connected"

    ini_exists = connection.run_command('test -f /media/fat/MiSTer.ini && echo EXISTS')
    if "EXISTS" in (ini_exists or ""):
        return True, "MiSTer.ini exists"

    example_exists = connection.run_command('test -f /media/fat/MiSTer_example.ini && echo EXISTS')
    if "EXISTS" not in (example_exists or ""):
        return False, "Neither MiSTer.ini nor MiSTer_example.ini exists."

    result = connection.run_command('cp /media/fat/MiSTer_example.ini /media/fat/MiSTer.ini && echo COPIED')
    if "COPIED" in (result or ""):
        return True, "MiSTer.ini created from MiSTer_example.ini"

    return False, "Unable to create MiSTer.ini from MiSTer_example.ini"


def enforce_mister_settings_retention(device_path, retention):
    if not os.path.exists(device_path):
        return

    backups = sorted(
        f for f in os.listdir(device_path)
        if os.path.isfile(os.path.join(device_path, f))
    )

    while len(backups) > retention:
        oldest = backups.pop(0)
        try:
            os.remove(os.path.join(device_path, oldest))
        except Exception:
            pass


def create_mister_settings_backup(connection, device_path, retention):
    os.makedirs(device_path, exist_ok=True)

    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    backup_file = os.path.join(device_path, f"MiSTer.ini.{timestamp}.bak")

    ok, message = ensure_mister_ini_exists(connection)
    if not ok:
        return False, message, ""

    sftp = connection.client.open_sftp()
    try:
        sftp.get("/media/fat/MiSTer.ini", backup_file)
    finally:
        sftp.close()

    enforce_mister_settings_retention(device_path, retention)
    return True, "Backup created", backup_file


def list_mister_settings_backups(device_path):
    if not os.path.exists(device_path):
        return []

    return sorted(
        [
            f for f in os.listdir(device_path)
            if os.path.isfile(os.path.join(device_path, f))
        ],
        reverse=True,
    )


def restore_mister_settings_backup(connection, backup_path):
    sftp = connection.client.open_sftp()
    try:
        sftp.put(backup_path, "/media/fat/MiSTer.ini")
    finally:
        sftp.close()


def restore_default_mister_settings(connection):
    return connection.run_command('cp /media/fat/MiSTer_example.ini /media/fat/MiSTer.ini && echo RESTORED')
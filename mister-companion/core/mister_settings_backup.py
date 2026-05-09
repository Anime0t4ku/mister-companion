import os
import shlex
import subprocess
import sys
import time

from core.profile_folder_sync import sanitize_folder_name, ip_to_folder_name


MISTER_SETTINGS_ROOT = "MiSTerSettings"


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


def normalize_mister_ini_filename(ini_filename="MiSTer.ini"):
    ini_filename = os.path.basename(str(ini_filename or "MiSTer.ini").strip())

    if not ini_filename:
        ini_filename = "MiSTer.ini"

    if ini_filename == "MiSTer.ini":
        return ini_filename

    if ini_filename.startswith("MiSTer_") and ini_filename.endswith(".ini"):
        return ini_filename

    raise ValueError(f"Unsupported MiSTer INI filename: {ini_filename}")


def remote_mister_ini_path(ini_filename="MiSTer.ini"):
    ini_filename = normalize_mister_ini_filename(ini_filename)
    return f"/media/fat/{ini_filename}"


def remote_example_ini_candidates():
    return [
        "/media/fat/MiSTer_example.ini",
        "/media/fat/MiSTer_Example.ini",
    ]


def backup_prefix_for_ini(ini_filename="MiSTer.ini"):
    ini_filename = normalize_mister_ini_filename(ini_filename)
    return f"{ini_filename}."


def safe_backup_filename(ini_filename, timestamp):
    ini_filename = normalize_mister_ini_filename(ini_filename)
    return f"{ini_filename}.{timestamp}.bak"


def ensure_mister_ini_exists(connection, ini_filename="MiSTer.ini", create_if_missing=True):
    ini_filename = normalize_mister_ini_filename(ini_filename)

    if not connection.is_connected():
        return False, "Not connected"

    remote_path = remote_mister_ini_path(ini_filename)
    remote_path_q = shlex.quote(remote_path)

    ini_exists = connection.run_command(f"test -f {remote_path_q} && echo EXISTS")
    if "EXISTS" in (ini_exists or ""):
        return True, f"{ini_filename} exists"

    if not create_if_missing:
        return False, f"{ini_filename} does not exist."

    if ini_filename != "MiSTer.ini":
        return False, f"{ini_filename} does not exist."

    example_path = ""

    for candidate in remote_example_ini_candidates():
        candidate_q = shlex.quote(candidate)
        example_exists = connection.run_command(f"test -f {candidate_q} && echo EXISTS")
        if "EXISTS" in (example_exists or ""):
            example_path = candidate
            break

    if not example_path:
        return False, "Neither MiSTer.ini nor MiSTer_example.ini exists."

    result = connection.run_command(
        f"cp {shlex.quote(example_path)} {remote_path_q} && echo COPIED"
    )

    if "COPIED" in (result or ""):
        return True, "MiSTer.ini created from example ini"

    return False, "Unable to create MiSTer.ini from example ini"


def enforce_mister_settings_retention(device_path, retention, ini_filename=None):
    if not os.path.exists(device_path):
        return

    prefix = None
    if ini_filename:
        prefix = backup_prefix_for_ini(ini_filename)

    backups = sorted(
        [
            f for f in os.listdir(device_path)
            if os.path.isfile(os.path.join(device_path, f))
            and (prefix is None or f.startswith(prefix))
        ]
    )

    while len(backups) > retention:
        oldest = backups.pop(0)
        try:
            os.remove(os.path.join(device_path, oldest))
        except Exception:
            pass


def create_mister_settings_backup(
    connection,
    device_path,
    retention,
    ini_filename="MiSTer.ini",
):
    ini_filename = normalize_mister_ini_filename(ini_filename)
    os.makedirs(device_path, exist_ok=True)

    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    backup_file = os.path.join(device_path, safe_backup_filename(ini_filename, timestamp))

    ok, message = ensure_mister_ini_exists(
        connection,
        ini_filename=ini_filename,
        create_if_missing=False,
    )
    if not ok:
        return False, message, ""

    sftp = connection.client.open_sftp()
    try:
        sftp.get(remote_mister_ini_path(ini_filename), backup_file)
    finally:
        sftp.close()

    enforce_mister_settings_retention(device_path, retention, ini_filename=ini_filename)
    return True, "Backup created", backup_file


def list_mister_settings_backups(device_path, ini_filename=None):
    if not os.path.exists(device_path):
        return []

    prefix = None
    if ini_filename:
        prefix = backup_prefix_for_ini(ini_filename)

    return sorted(
        [
            f for f in os.listdir(device_path)
            if os.path.isfile(os.path.join(device_path, f))
            and (prefix is None or f.startswith(prefix))
        ],
        reverse=True,
    )


def restore_mister_settings_backup(
    connection,
    backup_path,
    ini_filename="MiSTer.ini",
):
    ini_filename = normalize_mister_ini_filename(ini_filename)

    sftp = connection.client.open_sftp()
    try:
        sftp.put(backup_path, remote_mister_ini_path(ini_filename))
    finally:
        sftp.close()


def restore_default_mister_settings(connection, ini_filename="MiSTer.ini"):
    ini_filename = normalize_mister_ini_filename(ini_filename)
    remote_path = remote_mister_ini_path(ini_filename)

    example_path = ""

    for candidate in remote_example_ini_candidates():
        candidate_q = shlex.quote(candidate)
        example_exists = connection.run_command(f"test -f {candidate_q} && echo EXISTS")
        if "EXISTS" in (example_exists or ""):
            example_path = candidate
            break

    if not example_path:
        return "ERROR: No MiSTer example ini found"

    return connection.run_command(
        f"cp {shlex.quote(example_path)} {shlex.quote(remote_path)} && echo RESTORED"
    )
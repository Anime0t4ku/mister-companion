import requests

from core.scripts_common import (
    _chmod_local_executable,
    _local_path,
    _write_local_bytes,
    ensure_local_scripts_dir,
    ensure_remote_scripts_dir,
)


AUTO_TIME_URL = "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/main/Scripts/auto_time.sh"
AUTO_TIME_SCRIPT_PATH = "/media/fat/Scripts/auto_time.sh"


def _download_auto_time_script():
    response = requests.get(AUTO_TIME_URL, timeout=30)
    response.raise_for_status()
    return response.content


def install_auto_time(connection, log):
    log("Installing auto_time...\n")
    script_data = _download_auto_time_script()

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(AUTO_TIME_SCRIPT_PATH, "wb") as remote_file:
            remote_file.write(script_data)
    finally:
        sftp.close()

    connection.run_command(f"chmod +x {AUTO_TIME_SCRIPT_PATH}")
    log("auto_time installed successfully.\n")


def install_auto_time_local(sd_root, log):
    log("Installing auto_time to Offline SD Card...\n")
    script_data = _download_auto_time_script()

    ensure_local_scripts_dir(sd_root)
    _write_local_bytes(sd_root, AUTO_TIME_SCRIPT_PATH, script_data)
    _chmod_local_executable(sd_root, AUTO_TIME_SCRIPT_PATH)

    log("auto_time installed successfully.\n")
    log("Run it from the MiSTer Scripts menu after booting this SD card.\n")


def uninstall_auto_time(connection):
    connection.run_command(f"rm -f {AUTO_TIME_SCRIPT_PATH}")


def uninstall_auto_time_local(sd_root):
    path = _local_path(sd_root, AUTO_TIME_SCRIPT_PATH)
    if path.exists():
        path.unlink()
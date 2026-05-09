import requests

from core.scripts_common import (
    _chmod_local_executable,
    _local_path,
    _write_local_bytes,
    ensure_local_scripts_dir,
    ensure_remote_scripts_dir,
)


MIGRATE_SD_URL = "https://raw.githubusercontent.com/Natrox/MiSTer_Utils_Natrox/main/scripts/migrate_sd.sh"
MIGRATE_SD_SCRIPT_PATH = "/media/fat/Scripts/migrate_sd.sh"


def _download_migrate_sd_script():
    response = requests.get(MIGRATE_SD_URL, timeout=30)
    response.raise_for_status()
    return response.content


def install_migrate_sd(connection, log):
    log("Installing migrate_sd...\n")
    script_data = _download_migrate_sd_script()

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(MIGRATE_SD_SCRIPT_PATH, "wb") as remote_file:
            remote_file.write(script_data)
    finally:
        sftp.close()

    connection.run_command(f"chmod +x {MIGRATE_SD_SCRIPT_PATH}")
    log("migrate_sd installed successfully.\n")
    log("Run it from the MiSTer Scripts menu.\n")


def install_migrate_sd_local(sd_root, log):
    log("Installing migrate_sd to Offline SD Card...\n")
    script_data = _download_migrate_sd_script()

    ensure_local_scripts_dir(sd_root)
    _write_local_bytes(sd_root, MIGRATE_SD_SCRIPT_PATH, script_data)
    _chmod_local_executable(sd_root, MIGRATE_SD_SCRIPT_PATH)

    log("migrate_sd installed successfully.\n")
    log("Run it from the MiSTer Scripts menu after booting this SD card.\n")


def uninstall_migrate_sd(connection):
    connection.run_command(f"rm -f {MIGRATE_SD_SCRIPT_PATH}")


def uninstall_migrate_sd_local(sd_root):
    path = _local_path(sd_root, MIGRATE_SD_SCRIPT_PATH)
    if path.exists():
        path.unlink()
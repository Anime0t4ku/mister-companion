import requests

from core.scripts_common import ensure_remote_scripts_dir


MIGRATE_SD_URL = "https://raw.githubusercontent.com/Natrox/MiSTer_Utils_Natrox/main/scripts/migrate_sd.sh"


def install_migrate_sd(connection, log):
    log("Installing migrate_sd...\n")
    script_data = requests.get(MIGRATE_SD_URL, timeout=30).content

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/migrate_sd.sh", "wb") as remote_file:
            remote_file.write(script_data)
    finally:
        sftp.close()

    connection.run_command("chmod +x /media/fat/Scripts/migrate_sd.sh")
    log("migrate_sd installed successfully.\n")
    log("Run it from the MiSTer Scripts menu.\n")


def uninstall_migrate_sd(connection):
    connection.run_command("rm -f /media/fat/Scripts/migrate_sd.sh")
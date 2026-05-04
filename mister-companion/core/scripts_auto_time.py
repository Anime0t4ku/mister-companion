import requests

from core.scripts_common import ensure_remote_scripts_dir


AUTO_TIME_URL = "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/main/Scripts/auto_time.sh"


def install_auto_time(connection, log):
    log("Installing auto_time...\n")
    script_data = requests.get(AUTO_TIME_URL, timeout=30).content

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/auto_time.sh", "wb") as remote_file:
            remote_file.write(script_data)
    finally:
        sftp.close()

    connection.run_command("chmod +x /media/fat/Scripts/auto_time.sh")
    log("auto_time installed successfully.\n")


def uninstall_auto_time(connection):
    connection.run_command("rm -f /media/fat/Scripts/auto_time.sh")
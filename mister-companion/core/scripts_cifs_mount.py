import requests

from core.scripts_common import ensure_remote_scripts_dir


CIFS_MOUNT_URL = "https://raw.githubusercontent.com/MiSTer-devel/Scripts_MiSTer/master/cifs_mount.sh"
CIFS_UMOUNT_URL = "https://raw.githubusercontent.com/MiSTer-devel/Scripts_MiSTer/master/cifs_umount.sh"


def install_cifs_mount(connection, log):
    log("Installing cifs_mount scripts...\n")
    mount_script = requests.get(CIFS_MOUNT_URL, timeout=30).content
    umount_script = requests.get(CIFS_UMOUNT_URL, timeout=30).content

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/cifs_mount.sh", "wb") as remote_file:
            remote_file.write(mount_script)
        with sftp.open("/media/fat/Scripts/cifs_umount.sh", "wb") as remote_file:
            remote_file.write(umount_script)
    finally:
        sftp.close()

    connection.run_command("chmod +x /media/fat/Scripts/cifs_mount.sh")
    connection.run_command("chmod +x /media/fat/Scripts/cifs_umount.sh")
    log("CIFS scripts installed.\n")


def uninstall_cifs_mount(connection):
    connection.run_command("rm -f /media/fat/Scripts/cifs_mount.sh")
    connection.run_command("rm -f /media/fat/Scripts/cifs_umount.sh")


def run_cifs_mount(connection):
    return connection.run_command("/media/fat/Scripts/cifs_mount.sh")


def run_cifs_umount(connection):
    return connection.run_command("/media/fat/Scripts/cifs_umount.sh")


def remove_cifs_config(connection):
    connection.run_command("rm -f /media/fat/Scripts/cifs_mount.ini")


def load_cifs_config(connection):
    config = {}

    if not connection.is_connected():
        return config

    output = connection.run_command("cat /media/fat/Scripts/cifs_mount.ini 2>/dev/null")
    if not output:
        return config

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip()] = value.strip().strip('"')

    return config


def save_cifs_config(connection, server, share, username, password, mount_at_boot):
    ini = f'''SERVER="{server}"
SHARE="{share}"
USERNAME="{username}"
PASSWORD="{password}"
LOCAL_DIR="cifs/games"
WAIT_FOR_SERVER="true"
MOUNT_AT_BOOT="{str(mount_at_boot).lower()}"
SINGLE_CIFS_CONNECTION="true"
'''

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/cifs_mount.ini", "w") as remote_file:
            remote_file.write(ini)
    finally:
        sftp.close()


def test_cifs_connection(connection, server, share, username, password):
    test_cmd = (
        f'mount -t cifs //{server}/{share} /tmp/cifs_test '
        f'-o username="{username}",password="{password}"'
    )
    result = connection.run_command(
        f'mkdir -p /tmp/cifs_test && {test_cmd} && umount /tmp/cifs_test && echo SUCCESS'
    )
    return bool(result and "SUCCESS" in result)
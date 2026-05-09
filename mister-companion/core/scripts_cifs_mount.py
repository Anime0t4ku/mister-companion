import requests

from core.scripts_common import (
    _chmod_local_executable,
    _local_path,
    _write_local_bytes,
    ensure_local_scripts_dir,
    ensure_remote_scripts_dir,
)


CIFS_MOUNT_URL = "https://raw.githubusercontent.com/MiSTer-devel/Scripts_MiSTer/master/cifs_mount.sh"
CIFS_UMOUNT_URL = "https://raw.githubusercontent.com/MiSTer-devel/Scripts_MiSTer/master/cifs_umount.sh"

CIFS_MOUNT_SCRIPT_PATH = "/media/fat/Scripts/cifs_mount.sh"
CIFS_UMOUNT_SCRIPT_PATH = "/media/fat/Scripts/cifs_umount.sh"
CIFS_CONFIG_PATH = "/media/fat/Scripts/cifs_mount.ini"


def _download_cifs_scripts():
    mount_response = requests.get(CIFS_MOUNT_URL, timeout=30)
    mount_response.raise_for_status()

    umount_response = requests.get(CIFS_UMOUNT_URL, timeout=30)
    umount_response.raise_for_status()

    return mount_response.content, umount_response.content


def _parse_cifs_config_text(text):
    config = {}

    if not text:
        return config

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue

        key, value = line.split("=", 1)
        config[key.strip()] = value.strip().strip('"')

    return config


def _build_cifs_ini(server, share, username, password, mount_at_boot):
    return f'''SERVER="{server}"
SHARE="{share}"
USERNAME="{username}"
PASSWORD="{password}"
LOCAL_DIR="cifs/games"
WAIT_FOR_SERVER="true"
MOUNT_AT_BOOT="{str(mount_at_boot).lower()}"
SINGLE_CIFS_CONNECTION="true"
'''


def install_cifs_mount(connection, log):
    log("Installing cifs_mount scripts...\n")
    mount_script, umount_script = _download_cifs_scripts()

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(CIFS_MOUNT_SCRIPT_PATH, "wb") as remote_file:
            remote_file.write(mount_script)
        with sftp.open(CIFS_UMOUNT_SCRIPT_PATH, "wb") as remote_file:
            remote_file.write(umount_script)
    finally:
        sftp.close()

    connection.run_command(f"chmod +x {CIFS_MOUNT_SCRIPT_PATH}")
    connection.run_command(f"chmod +x {CIFS_UMOUNT_SCRIPT_PATH}")
    log("CIFS scripts installed.\n")


def install_cifs_mount_local(sd_root, log):
    log("Installing cifs_mount scripts to Offline SD Card...\n")
    mount_script, umount_script = _download_cifs_scripts()

    ensure_local_scripts_dir(sd_root)

    _write_local_bytes(sd_root, CIFS_MOUNT_SCRIPT_PATH, mount_script)
    _write_local_bytes(sd_root, CIFS_UMOUNT_SCRIPT_PATH, umount_script)

    _chmod_local_executable(sd_root, CIFS_MOUNT_SCRIPT_PATH)
    _chmod_local_executable(sd_root, CIFS_UMOUNT_SCRIPT_PATH)

    log("CIFS scripts installed.\n")
    log("Mount and unmount actions require Online / SSH Mode because they execute on a running MiSTer.\n")


def uninstall_cifs_mount(connection):
    connection.run_command(f"rm -f {CIFS_MOUNT_SCRIPT_PATH}")
    connection.run_command(f"rm -f {CIFS_UMOUNT_SCRIPT_PATH}")


def uninstall_cifs_mount_local(sd_root):
    for remote_path in [
        CIFS_MOUNT_SCRIPT_PATH,
        CIFS_UMOUNT_SCRIPT_PATH,
    ]:
        path = _local_path(sd_root, remote_path)
        if path.exists():
            path.unlink()


def run_cifs_mount(connection):
    return connection.run_command(CIFS_MOUNT_SCRIPT_PATH)


def run_cifs_umount(connection):
    return connection.run_command(CIFS_UMOUNT_SCRIPT_PATH)


def remove_cifs_config(connection):
    connection.run_command(f"rm -f {CIFS_CONFIG_PATH}")


def remove_cifs_config_local(sd_root):
    path = _local_path(sd_root, CIFS_CONFIG_PATH)
    if path.exists():
        path.unlink()


def load_cifs_config(connection):
    if not connection.is_connected():
        return {}

    output = connection.run_command(f"cat {CIFS_CONFIG_PATH} 2>/dev/null")
    return _parse_cifs_config_text(output or "")


def load_cifs_config_local(sd_root):
    path = _local_path(sd_root, CIFS_CONFIG_PATH)
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8", errors="ignore")
    return _parse_cifs_config_text(text)


def save_cifs_config(connection, server, share, username, password, mount_at_boot):
    ini = _build_cifs_ini(server, share, username, password, mount_at_boot)

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(CIFS_CONFIG_PATH, "w") as remote_file:
            remote_file.write(ini)
    finally:
        sftp.close()


def save_cifs_config_local(sd_root, server, share, username, password, mount_at_boot):
    ini = _build_cifs_ini(server, share, username, password, mount_at_boot)

    ensure_local_scripts_dir(sd_root)

    path = _local_path(sd_root, CIFS_CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ini, encoding="utf-8")


def test_cifs_connection(connection, server, share, username, password):
    test_cmd = (
        f'mount -t cifs //{server}/{share} /tmp/cifs_test '
        f'-o username="{username}",password="{password}"'
    )
    result = connection.run_command(
        f'mkdir -p /tmp/cifs_test && {test_cmd} && umount /tmp/cifs_test && echo SUCCESS'
    )
    return bool(result and "SUCCESS" in result)
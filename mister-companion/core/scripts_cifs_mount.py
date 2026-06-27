import shlex

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
CIFS_COMMON_URL = "https://raw.githubusercontent.com/MiSTer-devel/Scripts_MiSTer/master/cifs_common.sh"

CIFS_MOUNT_SCRIPT_PATH = "/media/fat/Scripts/cifs_mount.sh"
CIFS_UMOUNT_SCRIPT_PATH = "/media/fat/Scripts/cifs_umount.sh"
CIFS_COMMON_SCRIPT_PATH = "/media/fat/Scripts/cifs_common.sh"
CIFS_CONFIG_PATH = "/media/fat/Scripts/cifs_mount.ini"


def _cifs_mount_needs_common(mount_script):
    if isinstance(mount_script, bytes):
        mount_script = mount_script.decode("utf-8", errors="ignore")
    return "cifs_common.sh" in (mount_script or "")


def _download_cifs_scripts():
    mount_response = requests.get(CIFS_MOUNT_URL, timeout=30)
    mount_response.raise_for_status()
    mount_script = mount_response.content

    umount_response = requests.get(CIFS_UMOUNT_URL, timeout=30)
    umount_response.raise_for_status()
    umount_script = umount_response.content

    common_script = None
    if _cifs_mount_needs_common(mount_script):
        common_response = requests.get(CIFS_COMMON_URL, timeout=30)
        common_response.raise_for_status()
        common_script = common_response.content

    return mount_script, umount_script, common_script


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


def _clean_config_value(value):
    if value is None:
        return ""

    return str(value).replace('"', '\\"')


def _build_cifs_ini(
    server,
    share,
    username,
    password,
    mount_at_boot,
    share_directory="",
    domain="",
    local_dir="cifs/games",
    additional_mount_options="",
    existing_config=None,
):
    config = dict(existing_config or {})

    config["SERVER"] = server
    config["SHARE"] = share
    config["SHARE_DIRECTORY"] = share_directory
    config["USERNAME"] = username
    config["PASSWORD"] = password
    config["DOMAIN"] = domain
    config["LOCAL_DIR"] = local_dir or "cifs/games"
    config["ADDITIONAL_MOUNT_OPTIONS"] = additional_mount_options
    config["WAIT_FOR_SERVER"] = config.get("WAIT_FOR_SERVER", "true") or "true"
    config["MOUNT_AT_BOOT"] = str(mount_at_boot).lower()
    config["SINGLE_CIFS_CONNECTION"] = config.get("SINGLE_CIFS_CONNECTION", "true") or "true"

    preferred_order = [
        "SERVER",
        "SHARE",
        "SHARE_DIRECTORY",
        "USERNAME",
        "PASSWORD",
        "DOMAIN",
        "LOCAL_DIR",
        "ADDITIONAL_MOUNT_OPTIONS",
        "WAIT_FOR_SERVER",
        "MOUNT_AT_BOOT",
        "SINGLE_CIFS_CONNECTION",
    ]

    lines = []
    written = set()

    for key in preferred_order:
        lines.append(f'{key}="{_clean_config_value(config.get(key, ""))}"')
        written.add(key)

    for key, value in config.items():
        if key not in written:
            lines.append(f'{key}="{_clean_config_value(value)}"')

    return "\n".join(lines) + "\n"

def install_cifs_mount(connection, log):
    log("Installing cifs_mount scripts...\n")
    mount_script, umount_script, common_script = _download_cifs_scripts()

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(CIFS_MOUNT_SCRIPT_PATH, "wb") as remote_file:
            remote_file.write(mount_script)
        with sftp.open(CIFS_UMOUNT_SCRIPT_PATH, "wb") as remote_file:
            remote_file.write(umount_script)
        if common_script is not None:
            with sftp.open(CIFS_COMMON_SCRIPT_PATH, "wb") as remote_file:
                remote_file.write(common_script)
    finally:
        sftp.close()

    connection.run_command(f"chmod +x {CIFS_MOUNT_SCRIPT_PATH}")
    connection.run_command(f"chmod +x {CIFS_UMOUNT_SCRIPT_PATH}")
    if common_script is not None:
        connection.run_command(f"chmod +x {CIFS_COMMON_SCRIPT_PATH}")
    log("CIFS scripts installed.\n")


def install_cifs_mount_local(sd_root, log):
    log("Installing cifs_mount scripts to Offline SD Card...\n")
    mount_script, umount_script, common_script = _download_cifs_scripts()

    ensure_local_scripts_dir(sd_root)

    _write_local_bytes(sd_root, CIFS_MOUNT_SCRIPT_PATH, mount_script)
    _write_local_bytes(sd_root, CIFS_UMOUNT_SCRIPT_PATH, umount_script)
    if common_script is not None:
        _write_local_bytes(sd_root, CIFS_COMMON_SCRIPT_PATH, common_script)

    _chmod_local_executable(sd_root, CIFS_MOUNT_SCRIPT_PATH)
    _chmod_local_executable(sd_root, CIFS_UMOUNT_SCRIPT_PATH)
    if common_script is not None:
        _chmod_local_executable(sd_root, CIFS_COMMON_SCRIPT_PATH)

    log("CIFS scripts installed.\n")
    log("Mount and unmount actions require Online / SSH Mode because they execute on a running MiSTer.\n")


def uninstall_cifs_mount(connection):
    connection.run_command(f"rm -f {CIFS_MOUNT_SCRIPT_PATH}")
    connection.run_command(f"rm -f {CIFS_UMOUNT_SCRIPT_PATH}")
    connection.run_command(f"rm -f {CIFS_COMMON_SCRIPT_PATH}")


def uninstall_cifs_mount_local(sd_root):
    for remote_path in [
        CIFS_MOUNT_SCRIPT_PATH,
        CIFS_UMOUNT_SCRIPT_PATH,
        CIFS_COMMON_SCRIPT_PATH,
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


def save_cifs_config(
    connection,
    server,
    share,
    username,
    password,
    mount_at_boot,
    share_directory="",
    domain="",
    local_dir="cifs/games",
    additional_mount_options="",
):
    existing_config = load_cifs_config(connection)
    ini = _build_cifs_ini(
        server,
        share,
        username,
        password,
        mount_at_boot,
        share_directory=share_directory,
        domain=domain,
        local_dir=local_dir,
        additional_mount_options=additional_mount_options,
        existing_config=existing_config,
    )

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(CIFS_CONFIG_PATH, "w") as remote_file:
            remote_file.write(ini)
    finally:
        sftp.close()


def save_cifs_config_local(
    sd_root,
    server,
    share,
    username,
    password,
    mount_at_boot,
    share_directory="",
    domain="",
    local_dir="cifs/games",
    additional_mount_options="",
):
    existing_config = load_cifs_config_local(sd_root)
    ini = _build_cifs_ini(
        server,
        share,
        username,
        password,
        mount_at_boot,
        share_directory=share_directory,
        domain=domain,
        local_dir=local_dir,
        additional_mount_options=additional_mount_options,
        existing_config=existing_config,
    )

    ensure_local_scripts_dir(sd_root)

    path = _local_path(sd_root, CIFS_CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ini, encoding="utf-8")


def test_cifs_connection(
    connection,
    server,
    share,
    username,
    password,
    share_directory="",
    domain="",
    additional_mount_options="",
):
    remote_share = f"//{server}/{share}"
    clean_share_directory = share_directory.strip().strip("/")
    if clean_share_directory:
        remote_share = f"{remote_share}/{clean_share_directory}"

    mount_options = []
    if username:
        mount_options.append(f"username={username}")
    if password:
        mount_options.append(f"password={password}")
    if domain:
        mount_options.append(f"domain={domain}")
    if additional_mount_options:
        mount_options.append(additional_mount_options)

    options = ",".join(mount_options) if mount_options else "guest"
    test_cmd = (
        f"mount -t cifs {shlex.quote(remote_share)} /tmp/cifs_test "
        f"-o {shlex.quote(options)}"
    )
    result = connection.run_command(
        f"mkdir -p /tmp/cifs_test && {test_cmd} && umount /tmp/cifs_test && echo SUCCESS"
    )
    return bool(result and "SUCCESS" in result)

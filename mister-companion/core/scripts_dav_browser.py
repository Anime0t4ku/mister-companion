import shutil

import requests

from core.scripts_common import (
    DAV_BROWSER_CONFIG_DIR,
    DAV_BROWSER_CONFIG_PATH,
    _chmod_local_executable,
    _local_path,
    _write_local_bytes,
    ensure_local_scripts_dir,
    ensure_remote_scripts_dir,
)


DAV_BROWSER_URL = "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/main/Scripts/dav_browser.sh"
DAV_BROWSER_SCRIPT_PATH = "/media/fat/Scripts/dav_browser.sh"


def _download_dav_browser_script():
    response = requests.get(DAV_BROWSER_URL, timeout=30)
    response.raise_for_status()
    return response.content


def _parse_dav_browser_config_text(text):
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


def _build_dav_browser_ini(
    server_url,
    username,
    password,
    remote_path,
    skip_tls_verify,
):
    return f"""SERVER_URL={server_url}
USERNAME={username}
PASSWORD={password}
REMOTE_PATH={remote_path}
SKIP_TLS_VERIFY={"true" if skip_tls_verify else "false"}
"""


def install_dav_browser(connection, log):
    log("Installing dav_browser...\n")
    script_data = _download_dav_browser_script()

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(DAV_BROWSER_SCRIPT_PATH, "wb") as remote_file:
            remote_file.write(script_data)
    finally:
        sftp.close()

    connection.run_command(f"chmod +x {DAV_BROWSER_SCRIPT_PATH}")
    log("dav_browser installed successfully.\n")


def install_dav_browser_local(sd_root, log):
    log("Installing dav_browser to Offline SD Card...\n")
    script_data = _download_dav_browser_script()

    ensure_local_scripts_dir(sd_root)

    _write_local_bytes(sd_root, DAV_BROWSER_SCRIPT_PATH, script_data)
    _chmod_local_executable(sd_root, DAV_BROWSER_SCRIPT_PATH)

    log("dav_browser installed successfully.\n")
    log("Run it from the MiSTer Scripts menu after booting this SD card.\n")


def uninstall_dav_browser(connection):
    connection.run_command(f"rm -f {DAV_BROWSER_SCRIPT_PATH}")
    connection.run_command(f"rm -rf {DAV_BROWSER_CONFIG_DIR}")


def uninstall_dav_browser_local(sd_root):
    script_path = _local_path(sd_root, DAV_BROWSER_SCRIPT_PATH)
    config_dir = _local_path(sd_root, DAV_BROWSER_CONFIG_DIR)

    if script_path.exists():
        script_path.unlink()

    if config_dir.exists():
        shutil.rmtree(config_dir)


def load_dav_browser_config(connection):
    if not connection.is_connected():
        return {}

    output = connection.run_command(f"cat {DAV_BROWSER_CONFIG_PATH} 2>/dev/null")
    return _parse_dav_browser_config_text(output or "")


def load_dav_browser_config_local(sd_root):
    path = _local_path(sd_root, DAV_BROWSER_CONFIG_PATH)
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8", errors="ignore")
    return _parse_dav_browser_config_text(text)


def save_dav_browser_config(
    connection,
    server_url,
    username,
    password,
    remote_path,
    skip_tls_verify,
):
    ini = _build_dav_browser_ini(
        server_url=server_url,
        username=username,
        password=password,
        remote_path=remote_path,
        skip_tls_verify=skip_tls_verify,
    )

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(DAV_BROWSER_CONFIG_PATH, "w") as remote_file:
            remote_file.write(ini)
    finally:
        sftp.close()


def save_dav_browser_config_local(
    sd_root,
    server_url,
    username,
    password,
    remote_path,
    skip_tls_verify,
):
    ini = _build_dav_browser_ini(
        server_url=server_url,
        username=username,
        password=password,
        remote_path=remote_path,
        skip_tls_verify=skip_tls_verify,
    )

    ensure_local_scripts_dir(sd_root)

    path = _local_path(sd_root, DAV_BROWSER_CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ini, encoding="utf-8")


def remove_dav_browser_config(connection):
    connection.run_command(f"rm -f {DAV_BROWSER_CONFIG_PATH}")


def remove_dav_browser_config_local(sd_root):
    path = _local_path(sd_root, DAV_BROWSER_CONFIG_PATH)
    if path.exists():
        path.unlink()
import requests

from core.scripts_common import (
    DAV_BROWSER_CONFIG_DIR,
    DAV_BROWSER_CONFIG_PATH,
    ensure_remote_scripts_dir,
)


DAV_BROWSER_URL = "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/main/Scripts/dav_browser.sh"


def install_dav_browser(connection, log):
    log("Installing dav_browser...\n")
    script_data = requests.get(DAV_BROWSER_URL, timeout=30).content

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/dav_browser.sh", "wb") as remote_file:
            remote_file.write(script_data)
    finally:
        sftp.close()

    connection.run_command("chmod +x /media/fat/Scripts/dav_browser.sh")
    log("dav_browser installed successfully.\n")


def uninstall_dav_browser(connection):
    connection.run_command("rm -f /media/fat/Scripts/dav_browser.sh")
    connection.run_command(f"rm -rf {DAV_BROWSER_CONFIG_DIR}")


def load_dav_browser_config(connection):
    config = {}

    if not connection.is_connected():
        return config

    output = connection.run_command(f"cat {DAV_BROWSER_CONFIG_PATH} 2>/dev/null")
    if not output:
        return config

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip()] = value.strip().strip('"')

    return config


def save_dav_browser_config(
    connection,
    server_url,
    username,
    password,
    remote_path,
    skip_tls_verify,
):
    ini = f"""SERVER_URL={server_url}
USERNAME={username}
PASSWORD={password}
REMOTE_PATH={remote_path}
SKIP_TLS_VERIFY={"true" if skip_tls_verify else "false"}
"""

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(DAV_BROWSER_CONFIG_PATH, "w") as remote_file:
            remote_file.write(ini)
    finally:
        sftp.close()


def remove_dav_browser_config(connection):
    connection.run_command(f"rm -f {DAV_BROWSER_CONFIG_PATH}")
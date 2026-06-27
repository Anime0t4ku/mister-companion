import shutil
import zipfile
from io import BytesIO

import requests

from core.scripts_common import (
    DAV_BROWSER_CONFIG_DIR,
    DAV_BROWSER_CONFIG_PATH,
    DAV_BROWSER_RCLONE_PATH,
    DAV_BROWSER_RCLONE_URL,
    _chmod_local_executable,
    _local_path,
    _remote_command_success,
    _write_local_bytes,
    _write_remote_bytes,
    ensure_local_scripts_dir,
    ensure_remote_scripts_dir,
)


DAV_BROWSER_URL = "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/main/Scripts/dav_browser.sh"
DAV_BROWSER_SCRIPT_PATH = "/media/fat/Scripts/dav_browser.sh"


def _download_dav_browser_script():
    response = requests.get(DAV_BROWSER_URL, timeout=30)
    response.raise_for_status()
    return response.content


def _download_dav_browser_rclone_binary():
    response = requests.get(DAV_BROWSER_RCLONE_URL, timeout=60)
    response.raise_for_status()

    zip_file = zipfile.ZipFile(BytesIO(response.content))
    for entry in zip_file.namelist():
        normalized = entry.replace("\\", "/")
        if normalized.endswith("/rclone") or normalized == "rclone":
            return zip_file.read(entry)

    raise RuntimeError("Could not find rclone binary inside the downloaded ZIP.")


def _install_dav_browser_rclone_on_mister(connection):
    command = f"""set -eu
BASE_DIR="{DAV_BROWSER_CONFIG_DIR}"
RCLONE_BIN="{DAV_BROWSER_RCLONE_PATH}"
RCLONE_ZIP="/tmp/dav_browser_rclone.zip"
RCLONE_EXTRACT_DIR="/tmp/dav_browser_rclone_extract"
RCLONE_URL="{DAV_BROWSER_RCLONE_URL}"
DOWNLOAD_LOG="/tmp/dav_browser_rclone_download.log"
UNZIP_LOG="/tmp/dav_browser_rclone_unzip.log"
mkdir -p "$BASE_DIR"
rm -f "$RCLONE_ZIP" "$DOWNLOAD_LOG" "$UNZIP_LOG"
rm -rf "$RCLONE_EXTRACT_DIR"
mkdir -p "$RCLONE_EXTRACT_DIR"
DOWNLOAD_OK=0
if command -v curl >/dev/null 2>&1; then
    curl -L --fail "$RCLONE_URL" -o "$RCLONE_ZIP" >"$DOWNLOAD_LOG" 2>&1 && DOWNLOAD_OK=1 || true
    if [ "$DOWNLOAD_OK" -ne 1 ]; then
        curl -k -L --fail "$RCLONE_URL" -o "$RCLONE_ZIP" >"$DOWNLOAD_LOG" 2>&1 && DOWNLOAD_OK=1 || true
    fi
fi
if [ "$DOWNLOAD_OK" -ne 1 ] && command -v wget >/dev/null 2>&1; then
    wget -O "$RCLONE_ZIP" "$RCLONE_URL" >"$DOWNLOAD_LOG" 2>&1 && DOWNLOAD_OK=1 || true
    if [ "$DOWNLOAD_OK" -ne 1 ]; then
        wget --no-check-certificate -O "$RCLONE_ZIP" "$RCLONE_URL" >"$DOWNLOAD_LOG" 2>&1 && DOWNLOAD_OK=1 || true
    fi
fi
if [ "$DOWNLOAD_OK" -ne 1 ] || [ ! -s "$RCLONE_ZIP" ]; then
    echo "Failed to download dav_browser rclone."
    tail -n 8 "$DOWNLOAD_LOG" 2>/dev/null || true
    exit 10
fi
if command -v unzip >/dev/null 2>&1; then
    unzip -o "$RCLONE_ZIP" -d "$RCLONE_EXTRACT_DIR" >"$UNZIP_LOG" 2>&1
elif command -v busybox >/dev/null 2>&1; then
    busybox unzip -o "$RCLONE_ZIP" -d "$RCLONE_EXTRACT_DIR" >"$UNZIP_LOG" 2>&1
else
    echo "No unzip tool found on MiSTer."
    exit 11
fi
BIN_PATH="$(find "$RCLONE_EXTRACT_DIR" -type f -name rclone 2>/dev/null | head -n1)"
if [ -z "$BIN_PATH" ] || [ ! -f "$BIN_PATH" ]; then
    echo "Failed to extract dav_browser rclone."
    tail -n 8 "$UNZIP_LOG" 2>/dev/null || true
    exit 12
fi
cp "$BIN_PATH" "$RCLONE_BIN"
chmod +x "$RCLONE_BIN"
"$RCLONE_BIN" version >/dev/null 2>&1
rm -f "$RCLONE_ZIP" "$DOWNLOAD_LOG" "$UNZIP_LOG"
rm -rf "$RCLONE_EXTRACT_DIR"
"""
    result = connection.run_command(command)
    if not _remote_command_success(connection, f"{DAV_BROWSER_RCLONE_PATH} version"):
        raise RuntimeError(f"dav_browser rclone could not be installed on MiSTer.\n{result or ''}".strip())


def ensure_dav_browser_bootstrap(connection, log=None):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    def _log(message):
        if log:
            log(message)

    ensure_remote_scripts_dir(connection)
    connection.run_command(f"mkdir -p {DAV_BROWSER_CONFIG_DIR}")

    if _remote_command_success(connection, f"{DAV_BROWSER_RCLONE_PATH} version"):
        _log("Existing dav_browser rclone binary is valid, keeping it.\n")
        return

    _log("Installing dav_browser rclone binary on MiSTer...\n")
    _install_dav_browser_rclone_on_mister(connection)
    _log("dav_browser rclone installed successfully.\n")


def ensure_dav_browser_bootstrap_local(sd_root, log=None):
    def _log(message):
        if log:
            log(message)

    ensure_local_scripts_dir(sd_root)
    config_dir = _local_path(sd_root, DAV_BROWSER_CONFIG_DIR)
    config_dir.mkdir(parents=True, exist_ok=True)

    rclone_path = _local_path(sd_root, DAV_BROWSER_RCLONE_PATH)
    if rclone_path.exists() and rclone_path.stat().st_size > 0:
        _log("Existing dav_browser rclone binary found, keeping it.\n")
        return

    _log("Installing dav_browser rclone binary...\n")
    rclone_binary = _download_dav_browser_rclone_binary()
    _write_local_bytes(sd_root, DAV_BROWSER_RCLONE_PATH, rclone_binary)
    _chmod_local_executable(sd_root, DAV_BROWSER_RCLONE_PATH)
    _log("dav_browser rclone installed successfully.\n")


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
    log("dav_browser main script uploaded.\n")

    ensure_dav_browser_bootstrap(connection, log)
    log("dav_browser installed successfully.\n")


def install_dav_browser_local(sd_root, log):
    log("Installing dav_browser to Offline SD Card...\n")
    script_data = _download_dav_browser_script()

    ensure_local_scripts_dir(sd_root)

    _write_local_bytes(sd_root, DAV_BROWSER_SCRIPT_PATH, script_data)
    _chmod_local_executable(sd_root, DAV_BROWSER_SCRIPT_PATH)
    log("dav_browser main script copied.\n")

    ensure_dav_browser_bootstrap_local(sd_root, log)
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
import io
import shutil
import tarfile

import requests

from core.scripts_common import (
    _chmod_local_executable,
    _local_path,
    _write_local_bytes,
    _write_local_text,
)


SYNCTHING_SCRIPT_URL = (
    "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/main/Scripts/syncthing.sh"
)

SYNCTHING_VERSION = "v2.0.16"
SYNCTHING_ARCHIVE_NAME = f"syncthing-linux-arm-{SYNCTHING_VERSION}.tar.gz"
SYNCTHING_DOWNLOAD_URL = (
    f"https://github.com/syncthing/syncthing/releases/download/"
    f"{SYNCTHING_VERSION}/{SYNCTHING_ARCHIVE_NAME}"
)

SYNCTHING_SCRIPT_PATH = "/media/fat/Scripts/syncthing.sh"

SYNCTHING_BASE_DIR = "/media/fat/Scripts/.config/syncthing"
SYNCTHING_BIN_DIR = f"{SYNCTHING_BASE_DIR}/bin"
SYNCTHING_HOME_DIR = f"{SYNCTHING_BASE_DIR}/home"
SYNCTHING_TMP_DIR = f"{SYNCTHING_BASE_DIR}/tmp"
SYNCTHING_LOG_FILE = f"{SYNCTHING_BASE_DIR}/syncthing.log"
SYNCTHING_PID_FILE = f"{SYNCTHING_BASE_DIR}/syncthing.pid"
SYNCTHING_BINARY_PATH = f"{SYNCTHING_BIN_DIR}/syncthing"
SYNCTHING_SERVICE_PATH = f"{SYNCTHING_BASE_DIR}/syncthing_service.sh"

USER_STARTUP_PATH = "/media/fat/linux/user-startup.sh"

SYNCTHING_STARTUP_BEGIN = "# Start Syncthing"
SYNCTHING_STARTUP_LINE = f"{SYNCTHING_SERVICE_PATH} start &"

SYNCTHING_INSTALL_LOG = f"{SYNCTHING_BASE_DIR}/install.log"
SYNCTHING_DOWNLOAD_DEBUG = f"{SYNCTHING_TMP_DIR}/download_debug.txt"

SYNCTHING_SERVICE_SCRIPT = f"""#!/bin/sh

BASE="{SYNCTHING_BASE_DIR}"
BIN="{SYNCTHING_BINARY_PATH}"
HOME_DIR="{SYNCTHING_HOME_DIR}"
LOG_FILE="{SYNCTHING_LOG_FILE}"
PID_FILE="{SYNCTHING_PID_FILE}"
GUI_ADDRESS="0.0.0.0:8384"

mkdir -p "$BASE" "$HOME_DIR"

is_running() {{
    if [ -f "$PID_FILE" ]; then
        PID="$(cat "$PID_FILE" 2>/dev/null)"
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            return 0
        fi
    fi

    ps | grep "$BIN" | grep -v grep >/dev/null 2>&1
}}

stop_existing() {{
    if [ -f "$PID_FILE" ]; then
        PID="$(cat "$PID_FILE" 2>/dev/null)"
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            kill "$PID" 2>/dev/null || true
            rm -f "$PID_FILE"
            sleep 1
        fi
    fi

    PIDS="$(ps | grep "$BIN" | grep -v grep | cut -d ' ' -f 1)"
    for PID in $PIDS; do
        if [ "$PID" != "$$" ]; then
            kill "$PID" 2>/dev/null || true
        fi
    done
}}

case "$1" in
    start)
        if [ ! -x "$BIN" ]; then
            echo "Syncthing binary missing or not executable: $BIN" >> "$LOG_FILE"
            exit 1
        fi

        if is_running; then
            echo "Syncthing is already running."
            exit 0
        fi

        nohup "$BIN" serve \
            --home "$HOME_DIR" \
            --no-browser \
            --gui-address "$GUI_ADDRESS" \
            > "$LOG_FILE" 2>&1 &

        echo $! > "$PID_FILE"
        echo "Syncthing started."
        ;;
    stop)
        stop_existing
        echo "Syncthing stopped."
        ;;
    restart)
        stop_existing
        "$0" start
        ;;
    status)
        if is_running; then
            echo "Syncthing is running."
            exit 0
        fi
        echo "Syncthing is not running."
        exit 1
        ;;
    *)
        echo "Usage: $0 {{start|stop|restart|status}}"
        exit 1
        ;;
esac
"""


def _write_remote_bytes(connection, path, data):
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "wb") as remote_file:
            remote_file.write(data)
    finally:
        sftp.close()


def _write_remote_text(connection, path, text):
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "w") as remote_file:
            remote_file.write(text)
    finally:
        sftp.close()


def _remote_command_success(connection, command):
    result = connection.run_command(f"{command} >/dev/null 2>&1 && echo OK || echo FAIL")
    return "OK" in (result or "")


def _read_remote_tail(connection, path, lines=40):
    output = connection.run_command(f"tail -n {int(lines)} {path} 2>/dev/null || true")
    return output.strip() if output else ""


def _download_bytes(url, timeout=60):
    response = requests.get(
        url,
        headers={"User-Agent": "MiSTer-Companion"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.content


def _download_syncthing_binary():
    archive_data = _download_bytes(SYNCTHING_DOWNLOAD_URL, timeout=120)
    expected_name = f"syncthing-linux-arm-{SYNCTHING_VERSION}/syncthing"

    with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as tf:
        members = tf.getmembers()

        for member in members:
            if member.isdir():
                continue

            name = member.name.replace("\\", "/").lstrip("./")

            if name == expected_name:
                extracted = tf.extractfile(member)
                if extracted is not None:
                    return extracted.read()

        for member in members:
            if member.isdir():
                continue

            name = member.name.replace("\\", "/").lstrip("./")
            basename = name.rsplit("/", 1)[-1]

            if basename != "syncthing":
                continue

            if not (member.mode & 0o111):
                continue

            extracted = tf.extractfile(member)
            if extracted is not None:
                return extracted.read()

    raise RuntimeError("Could not find the Syncthing executable inside the downloaded archive.")


def _run_remote_syncthing_binary_install(connection, log):
    remote_installer_path = "/tmp/mc_syncthing_install.sh"
    success_marker = "MC_SYNCTHING_INSTALL_OK"

    installer_script = """#!/bin/sh
set -u

BASE="__BASE__"
BIN_DIR="__BIN_DIR__"
HOME_DIR="__HOME_DIR__"
TMP_DIR="__TMP_DIR__"
LOG_FILE="__LOG_FILE__"
INSTALL_LOG="__INSTALL_LOG__"
DOWNLOAD_DEBUG="__DOWNLOAD_DEBUG__"
PID_FILE="__PID_FILE__"
VERSION="__VERSION__"
ARCHIVE="__ARCHIVE__"
DOWNLOAD_URL="__DOWNLOAD_URL__"
EXTRACTED_DIR="$TMP_DIR/syncthing-linux-arm-$VERSION"
BIN="$BIN_DIR/syncthing"

log_line() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)] $1" >> "$INSTALL_LOG"
}

fail() {
    log_line "ERROR: $1"
    echo "ERROR: $1"
    echo "Installer log: $INSTALL_LOG"
    exit 1
}

has_cmd() {
    command -v "$1" >/dev/null 2>&1
}

reset_install_log() {
    mkdir -p "$BASE" "$BIN_DIR" "$HOME_DIR" "$TMP_DIR"
    {
        echo "Syncthing for MiSTer Installer Log"
        echo "=================================="
        echo "Started: $(date 2>/dev/null)"
        echo "Version: $VERSION"
        echo "Archive: $ARCHIVE"
        echo "URL: $DOWNLOAD_URL"
        echo "Base: $BASE"
        echo ""
        echo "===== System / command info ====="
        echo "Date: $(date 2>/dev/null)"
        echo "uname: $(uname -a 2>/dev/null)"
        echo "PATH: $PATH"
        echo "dialog: $(command -v dialog 2>/dev/null)"
        echo "curl: $(command -v curl 2>/dev/null)"
        echo "wget: $(command -v wget 2>/dev/null)"
        echo "tar: $(command -v tar 2>/dev/null)"
        echo "gzip: $(command -v gzip 2>/dev/null)"
        echo "find: $(command -v find 2>/dev/null)"
        echo "================================="
        echo ""
    } > "$INSTALL_LOG"
}

append_download_debug() {
    {
        echo ""
        echo "===== Download debug ====="
        if [ -f "$DOWNLOAD_DEBUG" ]; then
            cat "$DOWNLOAD_DEBUG"
        else
            echo "File not found: $DOWNLOAD_DEBUG"
        fi
        echo "===== End Download debug ====="
        echo ""
    } >> "$INSTALL_LOG"
}

download_file() {
    URL="$1"
    OUT="$2"
    rm -f "$OUT" "$DOWNLOAD_DEBUG"
    {
        echo "Download debug"
        echo "=============="
        echo "Date: $(date 2>/dev/null)"
        echo "URL: $URL"
        echo "Output: $OUT"
        echo ""
    } > "$DOWNLOAD_DEBUG"

    if has_cmd curl; then
        echo "Trying curl..."
        log_line "Trying curl download."
        curl -k -L --fail --connect-timeout 20 --max-time 300 -A "MiSTer-Syncthing-Installer" -o "$OUT" "$URL" >> "$DOWNLOAD_DEBUG" 2>&1
        CURL_RESULT=$?
        echo "curl exit code: $CURL_RESULT" >> "$DOWNLOAD_DEBUG"
        if [ -f "$OUT" ]; then
            SIZE="$(wc -c < "$OUT" 2>/dev/null)"
            echo "Downloaded size: $SIZE bytes" >> "$DOWNLOAD_DEBUG"
            log_line "curl downloaded size: $SIZE bytes"
        fi
        if [ $CURL_RESULT -eq 0 ] && [ -s "$OUT" ] && gzip -t "$OUT" >/dev/null 2>&1; then
            log_line "curl download succeeded and gzip validation passed."
            append_download_debug
            return 0
        fi
    else
        echo "curl not found." >> "$DOWNLOAD_DEBUG"
        log_line "curl not found."
    fi

    if has_cmd wget; then
        echo "Trying wget..."
        log_line "Trying wget download."
        wget --no-check-certificate --timeout=20 --tries=3 -O "$OUT" "$URL" >> "$DOWNLOAD_DEBUG" 2>&1
        WGET_RESULT=$?
        echo "wget exit code: $WGET_RESULT" >> "$DOWNLOAD_DEBUG"
        if [ -f "$OUT" ]; then
            SIZE="$(wc -c < "$OUT" 2>/dev/null)"
            echo "Downloaded size: $SIZE bytes" >> "$DOWNLOAD_DEBUG"
            log_line "wget downloaded size: $SIZE bytes"
        fi
        if [ $WGET_RESULT -eq 0 ] && [ -s "$OUT" ] && gzip -t "$OUT" >/dev/null 2>&1; then
            log_line "wget download succeeded and gzip validation passed."
            append_download_debug
            return 0
        fi
    else
        echo "wget not found." >> "$DOWNLOAD_DEBUG"
        log_line "wget not found."
    fi

    append_download_debug
    rm -f "$OUT"
    return 1
}

extract_archive() {
    ARCHIVE_PATH="$1"
    DEST_DIR="$2"
    log_line "Extracting archive."
    tar --no-same-owner --no-same-permissions -xzf "$ARCHIVE_PATH" -C "$DEST_DIR" >> "$INSTALL_LOG" 2>&1
    RESULT=$?
    if [ $RESULT -eq 0 ]; then
        return 0
    fi

    log_line "tar extraction failed with exit code $RESULT. Trying gzip pipe fallback."
    gzip -dc "$ARCHIVE_PATH" | tar --no-same-owner --no-same-permissions -xf - -C "$DEST_DIR" >> "$INSTALL_LOG" 2>&1
    return $?
}

find_real_binary() {
    REAL_BIN="$EXTRACTED_DIR/syncthing"
    if [ -x "$REAL_BIN" ]; then
        echo "$REAL_BIN"
        return 0
    fi
    if [ -f "$REAL_BIN" ]; then
        chmod +x "$REAL_BIN"
        echo "$REAL_BIN"
        return 0
    fi

    FOUND="$(find "$TMP_DIR" -type f -name syncthing 2>/dev/null | head -n 1)"
    if [ -n "$FOUND" ]; then
        chmod +x "$FOUND" 2>/dev/null || true
        echo "$FOUND"
        return 0
    fi

    return 1
}

is_running() {
    if [ -f "$PID_FILE" ]; then
        PID="$(cat "$PID_FILE" 2>/dev/null)"
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            return 0
        fi
    fi

    ps | grep "$BIN" | grep -v grep >/dev/null 2>&1
}

stop_existing_syncthing() {
    if [ -f "$PID_FILE" ]; then
        PID="$(cat "$PID_FILE" 2>/dev/null)"
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            kill "$PID" 2>/dev/null || true
            rm -f "$PID_FILE"
            sleep 1
        fi
    fi

    PIDS="$(ps | grep "$BIN" | grep -v grep | cut -d ' ' -f 1)"
    for PID in $PIDS; do
        if [ "$PID" != "$$" ]; then
            kill "$PID" 2>/dev/null || true
        fi
    done
}

reset_install_log

if ! has_cmd tar; then
    fail "tar was not found on this MiSTer installation."
fi
if ! has_cmd gzip; then
    fail "gzip was not found on this MiSTer installation."
fi
if ! has_cmd curl && ! has_cmd wget; then
    fail "Neither curl nor wget was found, cannot download Syncthing."
fi

rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR" "$BIN_DIR" "$HOME_DIR"
: > "$LOG_FILE"

ARCHIVE_PATH="$TMP_DIR/$ARCHIVE"
echo "Step 1/4: Downloading Syncthing $VERSION..."
if ! download_file "$DOWNLOAD_URL" "$ARCHIVE_PATH"; then
    fail "Download failed or the archive was invalid."
fi

echo "Step 2/4: Validating archive..."
if ! gzip -t "$ARCHIVE_PATH" >/dev/null 2>&1; then
    fail "Downloaded file is not a valid gzip archive."
fi

echo "Step 3/4: Extracting Syncthing..."
if ! extract_archive "$ARCHIVE_PATH" "$TMP_DIR"; then
    fail "Extraction failed."
fi

{
    echo ""
    echo "===== Extracted file list ====="
    find "$TMP_DIR" -maxdepth 4 -type f 2>/dev/null
    echo "===== End extracted file list ====="
    echo ""
} >> "$INSTALL_LOG"

FOUND_BIN="$(find_real_binary)"
if [ -z "$FOUND_BIN" ]; then
    fail "Could not find the real Syncthing binary after extraction."
fi
log_line "Found real binary: $FOUND_BIN"

echo "Step 4/4: Installing Syncthing binary..."
if is_running; then
    log_line "Existing Syncthing process is running. Stopping before install."
    stop_existing_syncthing >> "$INSTALL_LOG" 2>&1
    sleep 1
else
    log_line "No existing Syncthing process detected."
fi

cp "$FOUND_BIN" "$BIN" >> "$INSTALL_LOG" 2>&1 || fail "Failed to copy Syncthing binary."
chmod +x "$BIN"

VERSION_TEXT="$($BIN --version 2>>"$INSTALL_LOG" | head -n 1)"
if [ -z "$VERSION_TEXT" ]; then
    VERSION_TEXT="$($BIN version 2>>"$INSTALL_LOG" | head -n 1)"
fi
if [ -z "$VERSION_TEXT" ]; then
    fail "Syncthing binary was copied, but the version check failed."
fi

log_line "Installed binary version: $VERSION_TEXT"
echo "$VERSION_TEXT"
echo "__SUCCESS_MARKER__"
"""

    replacements = {
        "__BASE__": SYNCTHING_BASE_DIR,
        "__BIN_DIR__": SYNCTHING_BIN_DIR,
        "__HOME_DIR__": SYNCTHING_HOME_DIR,
        "__TMP_DIR__": SYNCTHING_TMP_DIR,
        "__LOG_FILE__": SYNCTHING_LOG_FILE,
        "__INSTALL_LOG__": SYNCTHING_INSTALL_LOG,
        "__DOWNLOAD_DEBUG__": SYNCTHING_DOWNLOAD_DEBUG,
        "__PID_FILE__": SYNCTHING_PID_FILE,
        "__VERSION__": SYNCTHING_VERSION,
        "__ARCHIVE__": SYNCTHING_ARCHIVE_NAME,
        "__DOWNLOAD_URL__": SYNCTHING_DOWNLOAD_URL,
        "__SUCCESS_MARKER__": success_marker,
    }
    for placeholder, value in replacements.items():
        installer_script = installer_script.replace(placeholder, value)

    _write_remote_text(connection, remote_installer_path, installer_script)
    connection.run_command(f"chmod +x {remote_installer_path}")

    output_chunks = []

    def capture_and_log(text):
        output_chunks.append(text)
        log(text)

    connection.run_command_stream(
        f"sh {remote_installer_path}; result=$?; rm -f {remote_installer_path}; exit $result",
        capture_and_log,
    )

    output = "".join(output_chunks)
    if success_marker not in output:
        tail = _read_remote_tail(connection, SYNCTHING_INSTALL_LOG, lines=80)
        if tail:
            raise RuntimeError(
                "Syncthing install did not complete.\n\n"
                f"Last installer log output:\n{tail}"
            )
        raise RuntimeError("Syncthing install did not complete.")


def _ensure_syncthing_local_dirs(sd_root):
    for path in [
        "/media/fat/Scripts",
        SYNCTHING_BASE_DIR,
        SYNCTHING_BIN_DIR,
        SYNCTHING_HOME_DIR,
        SYNCTHING_TMP_DIR,
    ]:
        _local_path(sd_root, path).mkdir(parents=True, exist_ok=True)

    log_path = _local_path(sd_root, SYNCTHING_LOG_FILE)
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")


def is_syncthing_start_on_boot_enabled(connection):
    if not connection.is_connected():
        return False

    output = connection.run_command(
        f"grep -F '{SYNCTHING_SERVICE_PATH}' {USER_STARTUP_PATH} 2>/dev/null"
    )

    return bool(
        output
        and SYNCTHING_SERVICE_PATH in output
        and "start" in output
    )


def is_syncthing_start_on_boot_enabled_local(sd_root):
    startup_path = _local_path(sd_root, USER_STARTUP_PATH)
    if not startup_path.exists():
        return False

    text = startup_path.read_text(encoding="utf-8", errors="ignore")
    return SYNCTHING_SERVICE_PATH in text and "start" in text


def is_syncthing_running(connection):
    if not connection.is_connected():
        return False

    check = connection.run_command(
        f"""
if [ -f {SYNCTHING_PID_FILE} ]; then
    pid="$(cat {SYNCTHING_PID_FILE} 2>/dev/null)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo RUNNING
    else
        echo STOPPED
    fi
else
    pgrep -f "{SYNCTHING_BINARY_PATH}" >/dev/null 2>&1 && echo RUNNING || echo STOPPED
fi
"""
    )
    return "RUNNING" in (check or "")


def get_syncthing_status(connection):
    if not connection.is_connected():
        return {
            "installed": False,
            "running": False,
            "start_on_boot_enabled": False,
            "status_text": "Unknown",
            "install_enabled": False,
            "boot_label": "Enable Start on Boot",
            "boot_enabled": False,
            "uninstall_enabled": False,
        }

    script_check = connection.run_command(
        f"test -f {SYNCTHING_SCRIPT_PATH} && echo EXISTS"
    )
    binary_check = connection.run_command(
        f"test -x {SYNCTHING_BINARY_PATH} && echo EXISTS"
    )
    service_check = connection.run_command(
        f"test -x {SYNCTHING_SERVICE_PATH} && echo EXISTS"
    )

    installed = (
        "EXISTS" in (script_check or "")
        and "EXISTS" in (binary_check or "")
        and "EXISTS" in (service_check or "")
    )

    running = is_syncthing_running(connection) if installed else False
    start_on_boot_enabled = (
        is_syncthing_start_on_boot_enabled(connection) if installed else False
    )

    if not installed:
        status_text = "✗ Not installed"
        install_enabled = True
        boot_label = "Enable Start on Boot"
        boot_enabled = False
        uninstall_enabled = False
    else:
        if running and start_on_boot_enabled:
            status_text = "✓ Installed, running, start on boot enabled"
        elif running:
            status_text = "✓ Installed, running"
        elif start_on_boot_enabled:
            status_text = "✓ Installed, start on boot enabled"
        else:
            status_text = "✓ Installed"

        install_enabled = False
        boot_label = (
            "Disable Start on Boot"
            if start_on_boot_enabled
            else "Enable Start on Boot"
        )
        boot_enabled = True
        uninstall_enabled = True

    return {
        "installed": installed,
        "running": running,
        "start_on_boot_enabled": start_on_boot_enabled,
        "status_text": status_text,
        "install_enabled": install_enabled,
        "boot_label": boot_label,
        "boot_enabled": boot_enabled,
        "uninstall_enabled": uninstall_enabled,
    }


def get_syncthing_status_local(sd_root):
    script_path = _local_path(sd_root, SYNCTHING_SCRIPT_PATH)
    binary_path = _local_path(sd_root, SYNCTHING_BINARY_PATH)
    service_path = _local_path(sd_root, SYNCTHING_SERVICE_PATH)

    installed = (
        script_path.exists()
        and binary_path.exists()
        and service_path.exists()
    )

    running = False
    start_on_boot_enabled = (
        is_syncthing_start_on_boot_enabled_local(sd_root) if installed else False
    )

    if not installed:
        status_text = "✗ Not installed"
        install_enabled = True
        boot_label = "Enable Start on Boot"
        boot_enabled = False
        uninstall_enabled = False
    else:
        if start_on_boot_enabled:
            status_text = "✓ Installed, start on boot enabled"
        else:
            status_text = "✓ Installed"

        install_enabled = False
        boot_label = (
            "Disable Start on Boot"
            if start_on_boot_enabled
            else "Enable Start on Boot"
        )
        boot_enabled = True
        uninstall_enabled = True

    return {
        "installed": installed,
        "running": running,
        "start_on_boot_enabled": start_on_boot_enabled,
        "status_text": status_text,
        "install_enabled": install_enabled,
        "boot_label": boot_label,
        "boot_enabled": boot_enabled,
        "uninstall_enabled": uninstall_enabled,
    }


def install_syncthing(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log("Installing Syncthing...\n")

    connection.run_command("mkdir -p /media/fat/Scripts")
    connection.run_command(f"mkdir -p {SYNCTHING_BASE_DIR}")
    connection.run_command(f"mkdir -p {SYNCTHING_BIN_DIR}")
    connection.run_command(f"mkdir -p {SYNCTHING_HOME_DIR}")
    connection.run_command(f"mkdir -p {SYNCTHING_TMP_DIR}")
    connection.run_command(f"test -f {SYNCTHING_LOG_FILE} || : > {SYNCTHING_LOG_FILE}")

    log("Downloading syncthing.sh...\n")
    script_data = _download_bytes(SYNCTHING_SCRIPT_URL, timeout=60)

    log(f"Uploading script: {SYNCTHING_SCRIPT_PATH}\n")
    _write_remote_bytes(connection, SYNCTHING_SCRIPT_PATH, script_data)
    connection.run_command(f"chmod +x {SYNCTHING_SCRIPT_PATH}")

    log(f"Installing Syncthing {SYNCTHING_VERSION} binary on MiSTer...\n")
    _run_remote_syncthing_binary_install(connection, log)

    log(f"Writing service script: {SYNCTHING_SERVICE_PATH}\n")
    _write_remote_text(connection, SYNCTHING_SERVICE_PATH, SYNCTHING_SERVICE_SCRIPT)
    connection.run_command(f"chmod +x {SYNCTHING_SERVICE_PATH}")

    if not _remote_command_success(connection, f"test -x {SYNCTHING_SERVICE_PATH}"):
        raise RuntimeError("Syncthing service script could not be prepared on MiSTer.")

    if not _remote_command_success(connection, f"{SYNCTHING_BINARY_PATH} --version"):
        raise RuntimeError(
            "Syncthing binary install completed, but it is not executable on MiSTer."
        )

    log("Starting Syncthing...\n")
    start_syncthing(connection)

    if not is_syncthing_running(connection):
        log_tail = _read_remote_tail(connection, SYNCTHING_LOG_FILE)
        if log_tail:
            raise RuntimeError(
                "Syncthing was installed, but it failed to start.\n\n"
                f"Last runtime log output:\n{log_tail}"
            )

        install_tail = _read_remote_tail(connection, SYNCTHING_INSTALL_LOG)
        if install_tail:
            raise RuntimeError(
                "Syncthing was installed, but it failed to start.\n\n"
                f"Last installer log output:\n{install_tail}"
            )

        raise RuntimeError("Syncthing was installed, but it failed to start.")

    log("Syncthing installed and started successfully.\n")
    log("Web UI should be available on port 8384.\n")

    return {
        "installed": True,
        "running": True,
    }


def install_syncthing_local(sd_root, log):
    log("Installing Syncthing to Offline SD Card...\n")

    _ensure_syncthing_local_dirs(sd_root)

    log("Downloading syncthing.sh...\n")
    script_data = _download_bytes(SYNCTHING_SCRIPT_URL, timeout=60)

    log(f"Writing script: {SYNCTHING_SCRIPT_PATH}\n")
    _write_local_bytes(sd_root, SYNCTHING_SCRIPT_PATH, script_data)
    _chmod_local_executable(sd_root, SYNCTHING_SCRIPT_PATH)

    log(f"Downloading Syncthing {SYNCTHING_VERSION} binary...\n")
    binary_data = _download_syncthing_binary()

    log(f"Writing binary: {SYNCTHING_BINARY_PATH}\n")
    _write_local_bytes(sd_root, SYNCTHING_BINARY_PATH, binary_data)
    _chmod_local_executable(sd_root, SYNCTHING_BINARY_PATH)

    log(f"Writing service script: {SYNCTHING_SERVICE_PATH}\n")
    _write_local_text(sd_root, SYNCTHING_SERVICE_PATH, SYNCTHING_SERVICE_SCRIPT)
    _chmod_local_executable(sd_root, SYNCTHING_SERVICE_PATH)

    log("Syncthing installed successfully.\n")
    log("Syncthing was not started because Offline Mode cannot execute services.\n")
    log("Enable Start on Boot if you want it to start after booting this SD card.\n")

    return {
        "installed": True,
        "running": False,
    }


def start_syncthing(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    connection.run_command(f"{SYNCTHING_SERVICE_PATH} start >/dev/null 2>&1")


def stop_syncthing(connection):
    if not connection.is_connected():
        return

    connection.run_command(f"{SYNCTHING_SERVICE_PATH} stop >/dev/null 2>&1 || true")

    connection.run_command(
        f"""
if [ -f {SYNCTHING_PID_FILE} ]; then
    pid="$(cat {SYNCTHING_PID_FILE} 2>/dev/null)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        sleep 1
        kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f {SYNCTHING_PID_FILE}
fi

pkill -f "{SYNCTHING_BINARY_PATH}" 2>/dev/null || true
"""
    )


def enable_syncthing_start_on_boot(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    connection.run_command("mkdir -p /media/fat/linux")

    exists = connection.run_command(
        f"test -f {USER_STARTUP_PATH} && echo EXISTS"
    )

    if "EXISTS" not in (exists or ""):
        script = f"""#!/bin/sh

{SYNCTHING_STARTUP_BEGIN}
{SYNCTHING_STARTUP_LINE}
"""
        _write_remote_text(connection, USER_STARTUP_PATH, script)
        connection.run_command(f"chmod +x {USER_STARTUP_PATH}")
        return

    if is_syncthing_start_on_boot_enabled(connection):
        return

    connection.run_command(f'echo "" >> {USER_STARTUP_PATH}')
    connection.run_command(f'echo "{SYNCTHING_STARTUP_BEGIN}" >> {USER_STARTUP_PATH}')
    connection.run_command(f'echo "{SYNCTHING_STARTUP_LINE}" >> {USER_STARTUP_PATH}')
    connection.run_command(f"chmod +x {USER_STARTUP_PATH}")


def enable_syncthing_start_on_boot_local(sd_root):
    startup_path = _local_path(sd_root, USER_STARTUP_PATH)
    startup_path.parent.mkdir(parents=True, exist_ok=True)

    if not startup_path.exists():
        startup_path.write_text(
            f"""#!/bin/sh

{SYNCTHING_STARTUP_BEGIN}
{SYNCTHING_STARTUP_LINE}
""",
            encoding="utf-8",
        )
        _chmod_local_executable(sd_root, USER_STARTUP_PATH)
        return

    if is_syncthing_start_on_boot_enabled_local(sd_root):
        return

    text = startup_path.read_text(encoding="utf-8", errors="ignore").rstrip()
    text = f"{text}\n\n{SYNCTHING_STARTUP_BEGIN}\n{SYNCTHING_STARTUP_LINE}\n"
    startup_path.write_text(text, encoding="utf-8")
    _chmod_local_executable(sd_root, USER_STARTUP_PATH)


def disable_syncthing_start_on_boot(connection):
    if not connection.is_connected():
        return

    connection.run_command(
        f"sed -i '\\|{SYNCTHING_STARTUP_BEGIN}|,+1d' "
        f"{USER_STARTUP_PATH} 2>/dev/null || true"
    )


def disable_syncthing_start_on_boot_local(sd_root):
    startup_path = _local_path(sd_root, USER_STARTUP_PATH)
    if not startup_path.exists():
        return

    lines = startup_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    new_lines = []
    skip_next = False

    for line in lines:
        if skip_next:
            skip_next = False
            continue

        if line.strip() == SYNCTHING_STARTUP_BEGIN:
            skip_next = True
            continue

        new_lines.append(line)

    startup_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def toggle_syncthing_start_on_boot(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    if is_syncthing_start_on_boot_enabled(connection):
        disable_syncthing_start_on_boot(connection)
        return {
            "start_on_boot_enabled": False,
        }

    enable_syncthing_start_on_boot(connection)
    return {
        "start_on_boot_enabled": True,
    }


def toggle_syncthing_start_on_boot_local(sd_root):
    if is_syncthing_start_on_boot_enabled_local(sd_root):
        disable_syncthing_start_on_boot_local(sd_root)
        return {
            "start_on_boot_enabled": False,
        }

    enable_syncthing_start_on_boot_local(sd_root)
    return {
        "start_on_boot_enabled": True,
    }


def uninstall_syncthing(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log("Stopping Syncthing...\n")
    stop_syncthing(connection)

    log("Removing Syncthing start-on-boot entry...\n")
    disable_syncthing_start_on_boot(connection)

    log(f"Removing script: {SYNCTHING_SCRIPT_PATH}\n")
    connection.run_command(f"rm -f {SYNCTHING_SCRIPT_PATH}")

    log(f"Removing config and binary folder: {SYNCTHING_BASE_DIR}\n")
    connection.run_command(f"rm -rf {SYNCTHING_BASE_DIR}")

    log("Syncthing uninstalled successfully.\n")

    return {
        "uninstalled": True,
    }


def uninstall_syncthing_local(sd_root, log):
    log("Removing Syncthing start-on-boot entry...\n")
    disable_syncthing_start_on_boot_local(sd_root)

    script_path = _local_path(sd_root, SYNCTHING_SCRIPT_PATH)
    base_dir = _local_path(sd_root, SYNCTHING_BASE_DIR)

    log(f"Removing script: {SYNCTHING_SCRIPT_PATH}\n")
    if script_path.exists():
        script_path.unlink()

    log(f"Removing config and binary folder: {SYNCTHING_BASE_DIR}\n")
    if base_dir.exists():
        shutil.rmtree(base_dir)

    log("Syncthing uninstalled successfully.\n")

    return {
        "uninstalled": True,
    }
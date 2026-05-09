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

SYNCTHING_SERVICE_SCRIPT = f"""#!/bin/sh

BASE="{SYNCTHING_BASE_DIR}"
BIN="{SYNCTHING_BINARY_PATH}"
HOME_DIR="{SYNCTHING_HOME_DIR}"
LOG_FILE="{SYNCTHING_LOG_FILE}"
PID_FILE="{SYNCTHING_PID_FILE}"
GUI_ADDRESS="0.0.0.0:8384"

mkdir -p "$BASE" "$HOME_DIR"

start_syncthing() {{
    if [ ! -x "$BIN" ]; then
        echo "Syncthing binary missing or not executable: $BIN" >> "$LOG_FILE"
        exit 1
    fi

    if [ -f "$PID_FILE" ]; then
        old_pid="$(cat "$PID_FILE" 2>/dev/null)"
        if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
            exit 0
        fi
        rm -f "$PID_FILE"
    fi

    nohup "$BIN" serve \\
        --home "$HOME_DIR" \\
        --no-browser \\
        --gui-address "$GUI_ADDRESS" \\
        > "$LOG_FILE" 2>&1 &

    echo "$!" > "$PID_FILE"

    sleep 2

    new_pid="$(cat "$PID_FILE" 2>/dev/null)"
    if [ -z "$new_pid" ] || ! kill -0 "$new_pid" 2>/dev/null; then
        rm -f "$PID_FILE"
        echo "Syncthing failed to stay running after start." >> "$LOG_FILE"
        exit 1
    fi

    exit 0
}}

stop_syncthing() {{
    if [ -f "$PID_FILE" ]; then
        pid="$(cat "$PID_FILE" 2>/dev/null)"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            sleep 1
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
    fi

    pkill -f "$BIN" 2>/dev/null || true
    exit 0
}}

case "$1" in
    start)
        start_syncthing
        ;;
    stop)
        stop_syncthing
        ;;
    restart)
        stop_syncthing
        start_syncthing
        ;;
    *)
        echo "Usage: $0 {{start|stop|restart}}"
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

    log(f"Downloading Syncthing {SYNCTHING_VERSION} binary...\n")
    binary_data = _download_syncthing_binary()

    log(f"Uploading binary: {SYNCTHING_BINARY_PATH}\n")
    _write_remote_bytes(connection, SYNCTHING_BINARY_PATH, binary_data)
    connection.run_command(f"chmod +x {SYNCTHING_BINARY_PATH}")

    if not _remote_command_success(connection, f"{SYNCTHING_BINARY_PATH} version"):
        raise RuntimeError(
            "Syncthing binary upload succeeded, but it is not executable on MiSTer."
        )

    log(f"Writing service script: {SYNCTHING_SERVICE_PATH}\n")
    _write_remote_text(connection, SYNCTHING_SERVICE_PATH, SYNCTHING_SERVICE_SCRIPT)
    connection.run_command(f"chmod +x {SYNCTHING_SERVICE_PATH}")

    if not _remote_command_success(connection, f"test -x {SYNCTHING_SERVICE_PATH}"):
        raise RuntimeError("Syncthing service script could not be prepared on MiSTer.")

    log("Starting Syncthing...\n")
    start_syncthing(connection)

    if not is_syncthing_running(connection):
        log_tail = _read_remote_tail(connection, SYNCTHING_LOG_FILE)
        if log_tail:
            raise RuntimeError(
                "Syncthing was installed, but it failed to start.\n\n"
                f"Last log output:\n{log_tail}"
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
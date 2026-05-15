from dataclasses import dataclass
import json
import sys
import threading
from pathlib import Path
from typing import Any, Dict

from websocket import create_connection


REMOTE_DAEMON_PORT = 9191
REMOTE_WS_PATH = "/remote/v1"
REMOTE_SCRIPT_PATH = "/media/fat/Scripts/companion_remote.sh"
REMOTE_CONFIG_DIR = "/media/fat/Scripts/.config/companion_remote"
REMOTE_DAEMON_PATH = "/media/fat/Scripts/.config/companion_remote/companion_remote_daemon"
REMOTE_LOG_PATH = "/media/fat/Scripts/.config/companion_remote/companion_remote.log"
REMOTE_STARTUP_PATH = "/media/fat/linux/user-startup.sh"


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


BASE_DIR = app_base_dir()
LOCAL_REMOTE_SCRIPT_PATH = BASE_DIR / "assets" / "companion_remote.sh"


@dataclass
class RemoteDaemonStatus:
    script_exists: bool = False
    config_dir_exists: bool = False
    daemon_exists: bool = False
    process_running: bool = False
    port_listening: bool = False
    startup_enabled: bool = False
    version: str = ""
    raw_output: str = ""
    error: str = ""

    @property
    def installed(self) -> bool:
        return self.script_exists and self.config_dir_exists and self.daemon_exists

    @property
    def running(self) -> bool:
        return self.process_running or self.port_listening

    @property
    def ready(self) -> bool:
        return self.installed and self.running and self.port_listening


def remote_websocket_url(host: str) -> str:
    host = str(host or "").strip()
    if not host:
        return ""
    return f"ws://{host}:{REMOTE_DAEMON_PORT}{REMOTE_WS_PATH}"


def _parse_bool(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _value(values: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        key = str(key or "").strip().lower()
        if key in values:
            return values[key]
    return default


def _parse_status_output(output: str) -> RemoteDaemonStatus:
    values = {}

    for line in str(output or "").splitlines():
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip().lower()] = value.strip()

    return RemoteDaemonStatus(
        script_exists=_parse_bool(_value(values, "script_exists", "script_installed")),
        config_dir_exists=_parse_bool(_value(values, "config_dir_exists", "base_exists")),
        daemon_exists=_parse_bool(_value(values, "daemon_exists", "daemon_installed")),
        process_running=_parse_bool(_value(values, "process_running", "daemon_running")),
        port_listening=_parse_bool(_value(values, "port_listening")),
        startup_enabled=_parse_bool(_value(values, "startup_enabled", "start_on_boot")),
        version=_value(values, "version"),
        raw_output=str(output or ""),
    )


def get_remote_daemon_status(connection) -> RemoteDaemonStatus:
    if connection is None or not connection.is_connected():
        return RemoteDaemonStatus(error="Not connected")

    command = f"""
SCRIPT_PATH='{REMOTE_SCRIPT_PATH}'
CONFIG_DIR='{REMOTE_CONFIG_DIR}'
DAEMON_PATH='{REMOTE_DAEMON_PATH}'
STARTUP_PATH='{REMOTE_STARTUP_PATH}'
PORT='{REMOTE_DAEMON_PORT}'

if [ -f "$SCRIPT_PATH" ]; then
    sh "$SCRIPT_PATH" status --unattended
    exit 0
fi

echo_bool() {{
    if "$@" >/dev/null 2>&1; then
        echo 1
    else
        echo 0
    fi
}}

script_exists=$(echo_bool test -f "$SCRIPT_PATH")
config_dir_exists=$(echo_bool test -d "$CONFIG_DIR")
daemon_exists=$(echo_bool test -f "$DAEMON_PATH")

if command -v pgrep >/dev/null 2>&1; then
    process_running=$(echo_bool pgrep -f "$DAEMON_PATH")
else
    process_running=$(ps 2>/dev/null | grep "$DAEMON_PATH" | grep -v grep >/dev/null 2>&1 && echo 1 || echo 0)
fi

if command -v ss >/dev/null 2>&1; then
    port_listening=$(ss -ltn 2>/dev/null | grep -E "[:.]$PORT[[:space:]]" >/dev/null 2>&1 && echo 1 || echo 0)
elif command -v netstat >/dev/null 2>&1; then
    port_listening=$(netstat -ltn 2>/dev/null | grep -E "[:.]$PORT[[:space:]]" >/dev/null 2>&1 && echo 1 || echo 0)
else
    port_listening=0
fi

if [ -f "$STARTUP_PATH" ]; then
    startup_enabled=$(grep -F "# MiSTer Companion Remote BEGIN" "$STARTUP_PATH" >/dev/null 2>&1 && echo 1 || echo 0)
else
    startup_enabled=0
fi

echo "script_exists=$script_exists"
echo "config_dir_exists=$config_dir_exists"
echo "daemon_exists=$daemon_exists"
echo "process_running=$process_running"
echo "port_listening=$port_listening"
echo "startup_enabled=$startup_enabled"
echo "version="
"""

    try:
        output = connection.run_command(command)
        return _parse_status_output(output)
    except Exception as e:
        return RemoteDaemonStatus(error=str(e))


def run_remote_daemon_command(connection, command_name: str) -> str:
    if connection is None or not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    command_name = str(command_name or "").strip()

    allowed = {
        "status",
        "status-human",
        "install",
        "uninstall",
        "start",
        "stop",
        "restart",
        "enable-boot",
        "disable-boot",
        "log",
        "clear-log",
    }

    if command_name not in allowed:
        raise ValueError(f"Unsupported remote daemon command: {command_name}")

    command = f"""
SCRIPT_PATH='{REMOTE_SCRIPT_PATH}'

if [ ! -f "$SCRIPT_PATH" ]; then
    echo "ERROR: Companion Remote script is missing:"
    echo "$SCRIPT_PATH"
    exit 1
fi

sh "$SCRIPT_PATH" {command_name} --unattended
"""

    return connection.run_command(command)


def install_remote_daemon(connection) -> str:
    if connection is None or not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    if not LOCAL_REMOTE_SCRIPT_PATH.exists():
        raise FileNotFoundError(
            f"Local Companion Remote script not found: {LOCAL_REMOTE_SCRIPT_PATH}"
        )

    script_text = LOCAL_REMOTE_SCRIPT_PATH.read_text(encoding="utf-8")

    command = f"""
mkdir -p /media/fat/Scripts

cat > '{REMOTE_SCRIPT_PATH}' <<'EOF_COMPANION_REMOTE'
{script_text}
EOF_COMPANION_REMOTE

chmod +x '{REMOTE_SCRIPT_PATH}'

echo "Installing Companion Remote..."
sh '{REMOTE_SCRIPT_PATH}' install --unattended
INSTALL_RESULT=$?

if [ $INSTALL_RESULT -ne 0 ]; then
    echo "ERROR: Companion Remote install failed."
    exit $INSTALL_RESULT
fi

echo ""
echo "Starting Companion Remote daemon..."
sh '{REMOTE_SCRIPT_PATH}' start --unattended
START_RESULT=$?

if [ $START_RESULT -ne 0 ]; then
    echo "ERROR: Companion Remote daemon failed to start."
    exit $START_RESULT
fi

echo ""
echo "OK: Companion Remote installed and started."
"""

    return connection.run_command(command)


def uninstall_remote_daemon(connection) -> str:
    if connection is None or not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    command = f"""
SCRIPT_PATH='{REMOTE_SCRIPT_PATH}'
CONFIG_DIR='{REMOTE_CONFIG_DIR}'
DAEMON_PATH='{REMOTE_DAEMON_PATH}'
STARTUP_PATH='{REMOTE_STARTUP_PATH}'

echo "Uninstalling Companion Remote..."

if [ -f "$SCRIPT_PATH" ]; then
    sh "$SCRIPT_PATH" stop --unattended >/dev/null 2>&1
    sh "$SCRIPT_PATH" disable-boot --unattended >/dev/null 2>&1
else
    if [ -f "$STARTUP_PATH" ]; then
        TMP_FILE="$STARTUP_PATH.tmp.$$"

        awk '
            BEGIN {{ skip = 0 }}

            /^# MiSTer Companion Remote BEGIN$/ {{
                skip = 1
                next
            }}

            /^# MiSTer Companion Remote END$/ {{
                skip = 0
                next
            }}

            /^# MiSTer Companion Remote$/ {{
                skip = 1
                next
            }}

            skip == 1 && /^fi$/ {{
                skip = 0
                next
            }}

            skip == 1 {{
                next
            }}

            /companion_remote_daemon/ {{
                next
            }}

            {{
                print
            }}
        ' "$STARTUP_PATH" > "$TMP_FILE" 2>/dev/null

        if [ -f "$TMP_FILE" ]; then
            mv "$TMP_FILE" "$STARTUP_PATH"
            chmod +x "$STARTUP_PATH" 2>/dev/null
        else
            rm -f "$TMP_FILE" 2>/dev/null
        fi
    fi

    if command -v pkill >/dev/null 2>&1; then
        pkill -f "$DAEMON_PATH" >/dev/null 2>&1
    else
        PIDS=$(ps 2>/dev/null | grep "$DAEMON_PATH" | grep -v grep | awk '{{print $1}}')
        for PID in $PIDS; do
            kill "$PID" >/dev/null 2>&1
        done
    fi
fi

rm -f "$SCRIPT_PATH" >/dev/null 2>&1
rm -rf "$CONFIG_DIR" >/dev/null 2>&1

echo "OK: Companion Remote uninstalled."
"""

    return connection.run_command(command)


def start_remote_daemon(connection) -> str:
    return run_remote_daemon_command(connection, "start")


def stop_remote_daemon(connection) -> str:
    return run_remote_daemon_command(connection, "stop")


def start_stop_remote_daemon(connection) -> str:
    status = get_remote_daemon_status(connection)

    if status.running:
        return stop_remote_daemon(connection)

    return start_remote_daemon(connection)


def restart_remote_daemon(connection) -> str:
    return run_remote_daemon_command(connection, "restart")


def enable_remote_daemon_boot(connection) -> str:
    return run_remote_daemon_command(connection, "enable-boot")


def disable_remote_daemon_boot(connection) -> str:
    return run_remote_daemon_command(connection, "disable-boot")


def toggle_remote_daemon_boot(connection) -> str:
    status = get_remote_daemon_status(connection)

    if status.startup_enabled:
        return disable_remote_daemon_boot(connection)

    return enable_remote_daemon_boot(connection)


class RemoteWebSocketClient:
    def __init__(self, host: str, timeout: float = 2.0):
        self.host = str(host or "").strip()
        self.timeout = float(timeout)
        self.ws = None
        self.lock = threading.RLock()
        self.last_hello = None

    @property
    def url(self) -> str:
        return remote_websocket_url(self.host)

    def is_connected(self) -> bool:
        return self.ws is not None

    def connect(self):
        if not self.host:
            raise RuntimeError("Missing MiSTer host.")

        with self.lock:
            if self.ws is not None:
                return

            self.ws = create_connection(self.url, timeout=self.timeout)

            try:
                raw = self.ws.recv()
                self.last_hello = json.loads(raw)
            except Exception:
                self.last_hello = None

    def close(self):
        try:
            if self.ws is not None:
                try:
                    self.release_all()
                except Exception:
                    pass
        finally:
            with self.lock:
                if self.ws is not None:
                    try:
                        self.ws.close()
                    except Exception:
                        pass

                    self.ws = None

    def send_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if self.ws is None:
                self.connect()

            self.ws.send(json.dumps(payload))
            raw = self.ws.recv()

        try:
            result = json.loads(raw)
        except Exception:
            result = {
                "ok": False,
                "type": "error",
                "message": str(raw),
            }

        if not result.get("ok", False):
            raise RuntimeError(result.get("message") or "Remote command failed.")

        return result

    def ping(self) -> Dict[str, Any]:
        return self.send_json({
            "type": "ping",
        })

    def send_controller_button(self, name: str, action: str = "tap") -> Dict[str, Any]:
        return self.send_json({
            "type": "controller",
            "control": "button",
            "name": str(name or "").lower().strip(),
            "action": str(action or "tap").lower().strip(),
        })

    def send_dpad(self, direction: str, action: str = "tap") -> Dict[str, Any]:
        return self.send_json({
            "type": "controller",
            "control": "dpad",
            "name": str(direction or "").lower().strip(),
            "action": str(action or "tap").lower().strip(),
        })

    def send_keyboard_key(self, key: str, action: str = "tap") -> Dict[str, Any]:
        return self.send_json({
            "type": "keyboard",
            "key": str(key or "").upper().strip(),
            "action": str(action or "tap").lower().strip(),
        })

    def release_all(self) -> Dict[str, Any]:
        return self.send_json({
            "type": "system",
            "command": "release_all",
        })
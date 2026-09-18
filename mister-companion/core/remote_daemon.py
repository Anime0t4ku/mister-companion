from dataclasses import dataclass
import json
import logging
import re
import sys
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from websocket import create_connection

from core.app_paths import app_base_dir as executable_base_dir


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
REMOTE_SCRIPT_SOURCE_URL = "https://raw.githubusercontent.com/Anime0t4ku/mister-companion/main/mister-companion/assets/companion_remote.sh"
BUNDLED_REMOTE_SCRIPT_VERSION = "3.0.0"

_logger = logging.getLogger(__name__)
_remote_script_cache_lock = threading.Lock()
_cached_remote_script_text = ""
_cached_remote_script_version = ""


def _parse_remote_script_version(script_text: str) -> str:
    match = re.search(r'^\s*SCRIPT_VERSION=["\']?([^"\'\r\n]+)', str(script_text or ""), re.MULTILINE)
    return match.group(1).strip() if match else ""


def _fetch_remote_script_text(timeout: int = 15) -> str:
    request = urllib.request.Request(
        REMOTE_SCRIPT_SOURCE_URL,
        headers={
            "User-Agent": "MiSTer-Companion/Remote-Daemon",
            "Accept": "text/plain,*/*",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def get_latest_remote_daemon_script() -> tuple[str, str, str]:
    global _cached_remote_script_text, _cached_remote_script_version

    try:
        script_text = _fetch_remote_script_text()
        version = _parse_remote_script_version(script_text) or BUNDLED_REMOTE_SCRIPT_VERSION

        with _remote_script_cache_lock:
            _cached_remote_script_text = script_text
            _cached_remote_script_version = version

        return script_text, version, "remote"
    except Exception as exc:
        _logger.warning("Failed to fetch Companion Remote script from GitHub: %s", exc)

        with _remote_script_cache_lock:
            if _cached_remote_script_text:
                return (
                    _cached_remote_script_text,
                    _cached_remote_script_version or BUNDLED_REMOTE_SCRIPT_VERSION,
                    "remote",
                )

        script_text = LOCAL_REMOTE_SCRIPT_PATH.read_text(encoding="utf-8")
        version = _parse_remote_script_version(script_text) or BUNDLED_REMOTE_SCRIPT_VERSION
        return script_text, version, "bundled"


def _version_tuple(value: str):
    parts = []
    for part in str(value or "").strip().split("."):
        try:
            parts.append(int(part))
        except Exception:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])



@dataclass
class RemoteDaemonStatus:
    script_exists: bool = False
    config_dir_exists: bool = False
    daemon_exists: bool = False
    process_running: bool = False
    port_listening: bool = False
    startup_enabled: bool = False
    version: str = ""
    latest_version: str = BUNDLED_REMOTE_SCRIPT_VERSION
    latest_source: str = "bundled"
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

    @property
    def update_available(self) -> bool:
        if not self.script_exists:
            return False

        installed_version = str(self.version or "").strip()

        if not installed_version:
            return True

        return _version_tuple(installed_version) < _version_tuple(self.latest_version)

    @property
    def version_label(self) -> str:
        return str(self.version or "Unknown").strip() or "Unknown"




def remote_daemon_supports_screenshots(version: str) -> bool:
    return _version_tuple(version) >= (3, 0, 0)


def local_screenshot_dir(create: bool = True) -> Path:
    folder = executable_base_dir() / "screenshots"
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def _unique_screenshot_path(folder: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = folder / f"MiSTer_Screenshot_{stamp}.png"
    index = 2
    while candidate.exists():
        candidate = folder / f"MiSTer_Screenshot_{stamp}_{index}.png"
        index += 1
    return candidate


def capture_remote_screenshot(host: str, timeout: int = 15) -> Path:
    host = str(host or "").strip()
    if not host:
        raise RuntimeError("Missing MiSTer host.")

    url = f"http://{host}:{REMOTE_DAEMON_PORT}/api/screenshot?fresh=1"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MiSTer-Companion/Screenshot",
            "Accept": "image/png",
            "Cache-Control": "no-cache",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
    except Exception as exc:
        raise RuntimeError(f"Screenshot request failed: {exc}") from exc

    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("The daemon did not return a valid PNG screenshot.")

    folder = local_screenshot_dir(create=True)
    output_path = _unique_screenshot_path(folder)
    output_path.write_bytes(data)
    return output_path

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
        version=_value(values, "version", "script_version", "companion_remote_version"),
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
        status = _parse_status_output(output)
        try:
            _script_text, latest_version, latest_source = get_latest_remote_daemon_script()
            status.latest_version = latest_version or BUNDLED_REMOTE_SCRIPT_VERSION
            status.latest_source = latest_source or "bundled"
        except Exception:
            pass
        return status
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
    """Install or update Companion Remote using a deterministic stop/replace/start flow.

    Updating a running daemon must stop the *old* process before replacing the
    script/daemon files.  Otherwise the newly written daemon can be current on
    disk while the old process continues serving the previous version.
    """
    if connection is None or not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    if not LOCAL_REMOTE_SCRIPT_PATH.exists():
        raise FileNotFoundError(
            f"Local Companion Remote script not found: {LOCAL_REMOTE_SCRIPT_PATH}"
        )

    script_text, expected_version, _latest_source = get_latest_remote_daemon_script()
    expected_version = str(expected_version or BUNDLED_REMOTE_SCRIPT_VERSION).strip()

    # 1) Stop the currently running daemon while the installed script still
    # matches that daemon.  Fall back to killing the daemon process when an
    # older/missing script cannot stop it cleanly.
    stop_command = f"""
SCRIPT_PATH='{REMOTE_SCRIPT_PATH}'
DAEMON_PATH='{REMOTE_DAEMON_PATH}'

if [ -f "$SCRIPT_PATH" ]; then
    sh "$SCRIPT_PATH" stop --unattended >/dev/null 2>&1 || true
fi

if command -v pkill >/dev/null 2>&1; then
    pkill -f "$DAEMON_PATH" >/dev/null 2>&1 || true
else
    PIDS=$(ps 2>/dev/null | grep "$DAEMON_PATH" | grep -v grep | awk '{{print $1}}')
    for PID in $PIDS; do
        kill "$PID" >/dev/null 2>&1 || true
    done
fi

rm -f '{REMOTE_CONFIG_DIR}/companion_remote.pid' >/dev/null 2>&1 || true
mkdir -p /media/fat/Scripts
"""
    connection.run_command(stop_command)

    # 2) Replace companion_remote.sh over SFTP.  Do not embed the full script
    # in one SSH command; besides being fragile for a large script, that makes
    # it much harder to distinguish an upload failure from an install failure.
    sftp = connection.client.open_sftp()
    temp_path = REMOTE_SCRIPT_PATH + ".update"
    try:
        try:
            sftp.remove(temp_path)
        except Exception:
            pass

        with sftp.open(temp_path, "wb") as remote_file:
            remote_file.write(script_text.encode("utf-8"))

        sftp.chmod(temp_path, 0o755)

        try:
            sftp.remove(REMOTE_SCRIPT_PATH)
        except Exception:
            pass

        sftp.rename(temp_path, REMOTE_SCRIPT_PATH)
        sftp.chmod(REMOTE_SCRIPT_PATH, 0o755)
    finally:
        try:
            sftp.remove(temp_path)
        except Exception:
            pass
        sftp.close()

    # 3) Regenerate/install the daemon from the newly uploaded script, then
    # start a fresh process.
    install_start_command = f"""
echo "Installing or updating Companion Remote..."
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

# 4) Verify that the daemon generated on the MiSTer is the version we just
# uploaded and that the service reports itself running.
ACTUAL_VERSION=""
if [ -x '{REMOTE_DAEMON_PATH}' ]; then
    ACTUAL_VERSION=$("{REMOTE_DAEMON_PATH}" --version 2>/dev/null | head -n 1)
fi

if [ -z "$ACTUAL_VERSION" ]; then
    echo "ERROR: Companion Remote daemon version could not be verified."
    exit 1
fi

if [ "$ACTUAL_VERSION" != '{expected_version}' ]; then
    echo "ERROR: Companion Remote daemon version mismatch."
    echo "Expected: {expected_version}"
    echo "Actual:   $ACTUAL_VERSION"
    exit 1
fi

STATUS_OUTPUT=$(sh '{REMOTE_SCRIPT_PATH}' status --unattended 2>/dev/null)
printf '%s\n' "$STATUS_OUTPUT"

if ! printf '%s\n' "$STATUS_OUTPUT" | grep -Eq '^DAEMON_RUNNING=1$'; then
    echo "ERROR: Companion Remote daemon is not running after update."
    exit 1
fi

echo ""
echo "OK: Companion Remote updated to $ACTUAL_VERSION and restarted."
"""

    return connection.run_command(install_start_command)


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
        last_error = None

        for attempt in range(2):
            with self.lock:
                if self.ws is None:
                    self.connect()

                try:
                    self.ws.send(json.dumps(payload))
                    raw = self.ws.recv()
                    break
                except Exception as e:
                    last_error = e

                    try:
                        self.ws.close()
                    except Exception:
                        pass

                    self.ws = None

                    if attempt == 1:
                        raise RuntimeError(f"WebSocket command failed: {last_error}")
        else:
            raise RuntimeError(f"WebSocket command failed: {last_error}")

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
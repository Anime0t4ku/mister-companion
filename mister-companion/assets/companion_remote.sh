#!/bin/sh

TITLE="MiSTer Companion Remote by Anime0t4ku"
SCRIPT_PATH="/media/fat/Scripts/companion_remote.sh"

BASE="/media/fat/Scripts/.config/companion_remote"
DAEMON="$BASE/companion_remote_daemon"
CONFIG="$BASE/config.ini"
LOG="$BASE/companion_remote.log"
PID="$BASE/companion_remote.pid"

STARTUP="/media/fat/linux/user-startup.sh"
STARTUP_DIR="/media/fat/linux"

PORT="9191"
HOST="0.0.0.0"
WS_PATH="/remote/v1"

UNATTENDED=0
COMMAND=""

mkdir -p "$BASE"

print_line() {
    printf '%s\n' "$1"
}

has_cmd() {
    command -v "$1" >/dev/null 2>&1
}

dialog_box() {
    clear
    dialog --clear --title "$TITLE" "$@"
    RESULT=$?
    clear
    sleep 0.3
    return $RESULT
}

show_message() {
    dialog_box --msgbox "$1" 14 82
}

log_line() {
    mkdir -p "$BASE" 2>/dev/null
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG"
}

ensure_base() {
    mkdir -p "$BASE" 2>/dev/null
}

write_default_config() {
    ensure_base

    if [ ! -f "$CONFIG" ]; then
        cat > "$CONFIG" <<EOF
[server]
host=$HOST
port=$PORT
path=$WS_PATH

[input]
virtual_keyboard=true
virtual_controller=true
EOF
    fi
}

create_daemon_file() {
    ensure_base

    cat > "$DAEMON" <<'PYEOF'
#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import os
import signal
import socket
import struct
import sys
import time
import fcntl

UINPUT_PATH = "/dev/uinput"

UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_ABSBIT = 0x40045567

EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03

SYN_REPORT = 0
BUS_USB = 0x03

ABS_HAT0X = 16
ABS_HAT0Y = 17

BTN_SOUTH = 304
BTN_EAST = 305
BTN_WEST = 307
BTN_NORTH = 308
BTN_TL = 310
BTN_TR = 311
BTN_SELECT = 314
BTN_START = 315
BTN_MODE = 316

KEY_CODES = {
    "KEY_ESC": 1,
    "KEY_1": 2,
    "KEY_2": 3,
    "KEY_3": 4,
    "KEY_4": 5,
    "KEY_5": 6,
    "KEY_6": 7,
    "KEY_7": 8,
    "KEY_8": 9,
    "KEY_9": 10,
    "KEY_0": 11,
    "KEY_MINUS": 12,
    "KEY_EQUAL": 13,
    "KEY_BACKSPACE": 14,
    "KEY_TAB": 15,
    "KEY_Q": 16,
    "KEY_W": 17,
    "KEY_E": 18,
    "KEY_R": 19,
    "KEY_T": 20,
    "KEY_Y": 21,
    "KEY_U": 22,
    "KEY_I": 23,
    "KEY_O": 24,
    "KEY_P": 25,
    "KEY_LEFTBRACE": 26,
    "KEY_RIGHTBRACE": 27,
    "KEY_ENTER": 28,
    "KEY_LEFTCTRL": 29,
    "KEY_A": 30,
    "KEY_S": 31,
    "KEY_D": 32,
    "KEY_F": 33,
    "KEY_G": 34,
    "KEY_H": 35,
    "KEY_J": 36,
    "KEY_K": 37,
    "KEY_L": 38,
    "KEY_SEMICOLON": 39,
    "KEY_APOSTROPHE": 40,
    "KEY_GRAVE": 41,
    "KEY_LEFTSHIFT": 42,
    "KEY_BACKSLASH": 43,
    "KEY_Z": 44,
    "KEY_X": 45,
    "KEY_C": 46,
    "KEY_V": 47,
    "KEY_B": 48,
    "KEY_N": 49,
    "KEY_M": 50,
    "KEY_COMMA": 51,
    "KEY_DOT": 52,
    "KEY_SLASH": 53,
    "KEY_RIGHTSHIFT": 54,
    "KEY_KPASTERISK": 55,
    "KEY_LEFTALT": 56,
    "KEY_SPACE": 57,
    "KEY_CAPSLOCK": 58,
    "KEY_F1": 59,
    "KEY_F2": 60,
    "KEY_F3": 61,
    "KEY_F4": 62,
    "KEY_F5": 63,
    "KEY_F6": 64,
    "KEY_F7": 65,
    "KEY_F8": 66,
    "KEY_F9": 67,
    "KEY_F10": 68,
    "KEY_NUMLOCK": 69,
    "KEY_SCROLLLOCK": 70,
    "KEY_KP7": 71,
    "KEY_KP8": 72,
    "KEY_KP9": 73,
    "KEY_KPMINUS": 74,
    "KEY_KP4": 75,
    "KEY_KP5": 76,
    "KEY_KP6": 77,
    "KEY_KPPLUS": 78,
    "KEY_KP1": 79,
    "KEY_KP2": 80,
    "KEY_KP3": 81,
    "KEY_KP0": 82,
    "KEY_KPDOT": 83,
    "KEY_F11": 87,
    "KEY_F12": 88,
    "KEY_RIGHTCTRL": 97,
    "KEY_KPSLASH": 98,
    "KEY_RIGHTALT": 100,
    "KEY_HOME": 102,
    "KEY_UP": 103,
    "KEY_PAGEUP": 104,
    "KEY_LEFT": 105,
    "KEY_RIGHT": 106,
    "KEY_END": 107,
    "KEY_DOWN": 108,
    "KEY_PAGEDOWN": 109,
    "KEY_INSERT": 110,
    "KEY_DELETE": 111,
    "KEY_PAUSE": 119,
    "KEY_LEFTMETA": 125,
    "KEY_RIGHTMETA": 126,
}

CONTROLLER_BUTTONS = {
    "a": BTN_SOUTH,
    "b": BTN_EAST,
    "x": BTN_WEST,
    "y": BTN_NORTH,
    "l": BTN_TL,
    "r": BTN_TR,
    "lb": BTN_TL,
    "rb": BTN_TR,
    "select": BTN_SELECT,
    "start": BTN_START,
    "mode": BTN_MODE,
    "home": BTN_MODE,
}

running = True


def ioctl_set(fd, request, value):
    fcntl.ioctl(fd, request, int(value))


def input_event(event_type, code, value):
    now = time.time()
    sec = int(now)
    usec = int((now - sec) * 1000000)
    return struct.pack("llHHi", sec, usec, event_type, code, value)


class UInputDevice:
    def __init__(self, name):
        self.name = name
        self.fd = os.open(UINPUT_PATH, os.O_WRONLY | os.O_NONBLOCK)

    def enable_ev(self, code):
        ioctl_set(self.fd, UI_SET_EVBIT, code)

    def enable_key(self, code):
        ioctl_set(self.fd, UI_SET_KEYBIT, code)

    def enable_abs(self, code):
        ioctl_set(self.fd, UI_SET_ABSBIT, code)

    def create(self, vendor, product, abs_ranges=None):
        if abs_ranges is None:
            abs_ranges = {}

        data = bytearray(1116)
        name_bytes = self.name.encode("utf-8")[:79]
        data[0:len(name_bytes)] = name_bytes

        struct.pack_into("HHHH", data, 80, BUS_USB, vendor, product, 1)

        absmax_offset = 92
        absmin_offset = absmax_offset + (64 * 4)

        for code, values in abs_ranges.items():
            min_value, max_value = values
            struct.pack_into("i", data, absmin_offset + code * 4, min_value)
            struct.pack_into("i", data, absmax_offset + code * 4, max_value)

        os.write(self.fd, data)
        fcntl.ioctl(self.fd, UI_DEV_CREATE, 0)
        time.sleep(0.25)

    def emit(self, event_type, code, value):
        os.write(self.fd, input_event(event_type, code, value))
        os.write(self.fd, input_event(EV_SYN, SYN_REPORT, 0))

    def key(self, code, down):
        self.emit(EV_KEY, code, 1 if down else 0)

    def abs(self, code, value):
        self.emit(EV_ABS, code, value)

    def destroy(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY, 0)
        except Exception:
            pass

        try:
            os.close(self.fd)
        except Exception:
            pass


class RemoteState:
    def __init__(self):
        self.keyboard = None
        self.controller = None
        self.held_keys = set()
        self.held_buttons = set()
        self.dpad = {
            "up": False,
            "down": False,
            "left": False,
            "right": False,
        }

    def init_devices(self):
        self.keyboard = UInputDevice("MiSTer Companion Virtual Keyboard")
        self.keyboard.enable_ev(EV_KEY)

        for code in KEY_CODES.values():
            self.keyboard.enable_key(code)

        self.keyboard.create(0x4D43, 0x0001)

        self.controller = UInputDevice("MiSTer Companion Virtual Controller")
        self.controller.enable_ev(EV_KEY)
        self.controller.enable_ev(EV_ABS)

        for code in CONTROLLER_BUTTONS.values():
            self.controller.enable_key(code)

        self.controller.enable_abs(ABS_HAT0X)
        self.controller.enable_abs(ABS_HAT0Y)

        self.controller.create(
            0x4D43,
            0x0002,
            {
                ABS_HAT0X: (-1, 1),
                ABS_HAT0Y: (-1, 1),
            },
        )

    def keyboard_key(self, code, down):
        if down:
            self.held_keys.add(code)
        else:
            self.held_keys.discard(code)

        self.keyboard.key(code, down)

    def controller_button(self, code, down):
        if down:
            self.held_buttons.add(code)
        else:
            self.held_buttons.discard(code)

        self.controller.key(code, down)

    def set_dpad(self, name, down):
        if name not in self.dpad:
            raise ValueError("Unknown D-pad direction: %s" % name)

        self.dpad[name] = down

        x = 0
        y = 0

        if self.dpad["left"] and not self.dpad["right"]:
            x = -1
        elif self.dpad["right"] and not self.dpad["left"]:
            x = 1

        if self.dpad["up"] and not self.dpad["down"]:
            y = -1
        elif self.dpad["down"] and not self.dpad["up"]:
            y = 1

        self.controller.abs(ABS_HAT0X, x)
        self.controller.abs(ABS_HAT0Y, y)

    def release_all(self):
        for code in list(self.held_keys):
            try:
                self.keyboard.key(code, False)
            except Exception:
                pass

        for code in list(self.held_buttons):
            try:
                self.controller.key(code, False)
            except Exception:
                pass

        self.held_keys.clear()
        self.held_buttons.clear()

        self.dpad = {
            "up": False,
            "down": False,
            "left": False,
            "right": False,
        }

        try:
            self.controller.abs(ABS_HAT0X, 0)
            self.controller.abs(ABS_HAT0Y, 0)
        except Exception:
            pass

    def destroy(self):
        self.release_all()

        if self.keyboard:
            self.keyboard.destroy()

        if self.controller:
            self.controller.destroy()


state = RemoteState()


def normalize_action(action):
    action = (action or "").lower().strip()

    if action == "press":
        return "down"

    if action == "release":
        return "up"

    if action in ("down", "up", "tap"):
        return action

    return ""


def run_action(action, callback):
    action = normalize_action(action)

    if action == "down":
        callback(True)
        return

    if action == "up":
        callback(False)
        return

    if action == "tap":
        callback(True)
        time.sleep(0.045)
        callback(False)
        return

    raise ValueError("Unknown action: %s" % action)


def response(ok=True, response_type="result", message="", version="1"):
    return {
        "ok": ok,
        "type": response_type,
        "message": message,
        "version": version,
    }


def handle_command(command):
    command_type = str(command.get("type", "")).lower().strip()

    if command_type in ("ping", "status"):
        return response(True, "status", "MiSTer Companion Remote daemon is running")

    if command_type == "system":
        system_command = str(command.get("command", "")).lower().strip()

        if system_command in ("release_all", "release-all"):
            state.release_all()
            return response(True, "system", "Released all inputs")

        return response(False, "error", "Unknown system command")

    if command_type == "keyboard":
        key = str(command.get("key", "")).upper().strip()
        action = command.get("action", "")

        if key not in KEY_CODES:
            return response(False, "error", "Unknown keyboard key: %s" % key)

        run_action(action, lambda down: state.keyboard_key(KEY_CODES[key], down))
        return response(True, "keyboard", "OK")

    if command_type == "controller":
        control = str(command.get("control", "")).lower().strip()
        name = str(command.get("name", "") or command.get("button", "")).lower().strip()
        action = command.get("action", "")

        if control == "dpad" or name in ("up", "down", "left", "right"):
            run_action(action, lambda down: state.set_dpad(name, down))
            return response(True, "controller", "OK")

        if name not in CONTROLLER_BUTTONS:
            return response(False, "error", "Unknown controller button: %s" % name)

        run_action(action, lambda down: state.controller_button(CONTROLLER_BUTTONS[name], down))
        return response(True, "controller", "OK")

    return response(False, "error", "Unknown command type: %s" % command_type)


def read_exact(sock, size):
    data = b""

    while len(data) < size:
        chunk = sock.recv(size - len(data))

        if not chunk:
            raise ConnectionError("socket closed")

        data += chunk

    return data


def read_ws_frame(sock):
    header = read_exact(sock, 2)
    b1, b2 = header[0], header[1]

    opcode = b1 & 0x0F
    masked = b2 & 0x80
    length = b2 & 0x7F

    if length == 126:
        length = struct.unpack(">H", read_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", read_exact(sock, 8))[0]

    mask = b""

    if masked:
        mask = read_exact(sock, 4)

    payload = read_exact(sock, length) if length else b""

    if masked:
        payload = bytes(payload[i] ^ mask[i % 4] for i in range(len(payload)))

    return opcode, payload


def send_ws_frame(sock, payload):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")

    header = bytearray()
    header.append(0x81)

    length = len(payload)

    if length < 126:
        header.append(length)
    elif length <= 65535:
        header.append(126)
        header.extend(struct.pack(">H", length))
    else:
        header.append(127)
        header.extend(struct.pack(">Q", length))

    sock.sendall(bytes(header) + payload)


def send_json(sock, payload):
    send_ws_frame(sock, json.dumps(payload))


def websocket_accept(key):
    value = key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    digest = hashlib.sha1(value.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def handle_client(sock, address, path):
    try:
        request = sock.recv(4096).decode("iso-8859-1", errors="ignore")

        if not request:
            return

        lines = request.split("\r\n")
        request_line = lines[0].split()

        if len(request_line) < 2:
            return

        request_path = request_line[1].split("?")[0]

        if request_path == "/status":
            body = json.dumps(response(True, "status", "MiSTer Companion Remote daemon is running")).encode("utf-8")
            sock.sendall(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                + ("Content-Length: %d\r\n" % len(body)).encode("ascii")
                + b"Connection: close\r\n\r\n"
                + body
            )
            return

        if request_path != path:
            sock.sendall(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")
            return

        headers = {}

        for line in lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.lower().strip()] = value.strip()

        ws_key = headers.get("sec-websocket-key")

        if not ws_key:
            sock.sendall(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            return

        accept = websocket_accept(ws_key)

        response_headers = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Accept: %s\r\n"
            "\r\n"
        ) % accept

        sock.sendall(response_headers.encode("ascii"))

        send_json(sock, response(True, "hello", "MiSTer Companion Remote daemon connected"))

        while running:
            opcode, payload = read_ws_frame(sock)

            if opcode == 0x8:
                break

            if opcode == 0x9:
                continue

            if opcode != 0x1:
                continue

            try:
                command = json.loads(payload.decode("utf-8"))
                result = handle_command(command)
            except Exception as e:
                result = response(False, "error", str(e))

            send_json(sock, result)

    except Exception:
        pass
    finally:
        try:
            state.release_all()
        except Exception:
            pass

        try:
            sock.close()
        except Exception:
            pass


def signal_handler(_signum, _frame):
    global running
    running = False

    try:
        state.release_all()
    except Exception:
        pass

    try:
        state.destroy()
    except Exception:
        pass

    sys.exit(0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default="9191")
    parser.add_argument("--path", default="/remote/v1")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    state.init_devices()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, int(args.port)))
    server.listen(5)

    print("MiSTer Companion Remote daemon listening on ws://%s:%s%s" % (args.host, args.port, args.path), flush=True)

    try:
        while running:
            client, address = server.accept()
            handle_client(client, address, args.path)
    finally:
        try:
            server.close()
        except Exception:
            pass

        state.destroy()


if __name__ == "__main__":
    main()
PYEOF

    chmod +x "$DAEMON" 2>/dev/null
}

script_installed() {
    [ -f "$SCRIPT_PATH" ]
}

daemon_installed() {
    [ -f "$DAEMON" ]
}

pid_value() {
    if [ -f "$PID" ]; then
        cat "$PID" 2>/dev/null | head -n 1
    fi
}

process_running_by_pid() {
    _pid="$1"

    if [ -z "$_pid" ]; then
        return 1
    fi

    if kill -0 "$_pid" 2>/dev/null; then
        return 0
    fi

    return 1
}

daemon_running() {
    _pid="$(pid_value)"

    if process_running_by_pid "$_pid"; then
        return 0
    fi

    if command -v pgrep >/dev/null 2>&1; then
        if pgrep -f "$DAEMON" >/dev/null 2>&1; then
            return 0
        fi
    fi

    ps | grep "$DAEMON" | grep -v grep >/dev/null 2>&1
}

port_listening() {
    if command -v netstat >/dev/null 2>&1; then
        netstat -lnt 2>/dev/null | grep -q ":$PORT "
        return $?
    fi

    if command -v ss >/dev/null 2>&1; then
        ss -lnt 2>/dev/null | grep -q ":$PORT "
        return $?
    fi

    return 1
}

startup_enabled() {
    if [ ! -f "$STARTUP" ]; then
        return 1
    fi

    grep -F "# MiSTer Companion Remote BEGIN" "$STARTUP" >/dev/null 2>&1
}

remove_startup_block() {
    if [ ! -f "$STARTUP" ]; then
        return 0
    fi

    _tmp="$STARTUP.tmp.$$"

    awk '
        BEGIN { skip = 0 }

        /^# MiSTer Companion Remote BEGIN$/ {
            skip = 1
            next
        }

        /^# MiSTer Companion Remote END$/ {
            skip = 0
            next
        }

        /^# MiSTer Companion Remote$/ {
            skip = 1
            next
        }

        skip == 1 && /^fi$/ {
            skip = 0
            next
        }

        skip == 1 {
            next
        }

        /companion_remote_daemon/ {
            next
        }

        {
            print
        }
    ' "$STARTUP" > "$_tmp" 2>/dev/null

    if [ -f "$_tmp" ]; then
        mv "$_tmp" "$STARTUP"
        chmod +x "$STARTUP" 2>/dev/null
        return 0
    fi

    rm -f "$_tmp" 2>/dev/null
    return 1
}

print_status() {
    if script_installed; then
        SCRIPT_INSTALLED=1
    else
        SCRIPT_INSTALLED=0
    fi

    if [ -d "$BASE" ]; then
        BASE_EXISTS=1
    else
        BASE_EXISTS=0
    fi

    if [ -f "$CONFIG" ]; then
        CONFIG_EXISTS=1
    else
        CONFIG_EXISTS=0
    fi

    if daemon_installed; then
        DAEMON_INSTALLED=1
    else
        DAEMON_INSTALLED=0
    fi

    if daemon_running; then
        DAEMON_RUNNING=1
    else
        DAEMON_RUNNING=0
    fi

    if port_listening; then
        PORT_LISTENING=1
    else
        PORT_LISTENING=0
    fi

    if startup_enabled; then
        START_ON_BOOT=1
    else
        START_ON_BOOT=0
    fi

    print_line "SCRIPT_INSTALLED=$SCRIPT_INSTALLED"
    print_line "BASE_EXISTS=$BASE_EXISTS"
    print_line "CONFIG_EXISTS=$CONFIG_EXISTS"
    print_line "DAEMON_INSTALLED=$DAEMON_INSTALLED"
    print_line "DAEMON_RUNNING=$DAEMON_RUNNING"
    print_line "PORT_LISTENING=$PORT_LISTENING"
    print_line "START_ON_BOOT=$START_ON_BOOT"
    print_line "HOST=$HOST"
    print_line "PORT=$PORT"
    print_line "WS_PATH=$WS_PATH"
    print_line "SCRIPT_PATH=$SCRIPT_PATH"
    print_line "BASE=$BASE"
    print_line "DAEMON=$DAEMON"
    print_line "CONFIG=$CONFIG"
    print_line "LOG=$LOG"
    print_line "PID=$PID"
}

status_text() {
    if daemon_installed; then
        DAEMON_INSTALLED_TEXT="Installed"
    else
        DAEMON_INSTALLED_TEXT="Missing"
    fi

    if daemon_running; then
        DAEMON_RUNNING_TEXT="Running"
    else
        DAEMON_RUNNING_TEXT="Stopped"
    fi

    if port_listening; then
        PORT_TEXT="Listening"
    else
        PORT_TEXT="Not listening"
    fi

    if startup_enabled; then
        BOOT_TEXT="Enabled"
    else
        BOOT_TEXT="Disabled"
    fi

    cat <<EOF
Status: $DAEMON_RUNNING_TEXT
Daemon: $DAEMON_INSTALLED_TEXT
Boot: $BOOT_TEXT
Port $PORT: $PORT_TEXT
EOF
}

full_status_text() {
    cat <<EOF
$(status_text)

WebSocket:
ws://<MiSTer IP>:$PORT$WS_PATH

Script:
$SCRIPT_PATH

Config:
$CONFIG

Log:
$LOG
EOF
}

print_status_human() {
    print_line "Status"
    print_line "------"
    full_status_text
}

install_manager() {
    ensure_base
    write_default_config
    create_daemon_file

    log_line "Install requested."

    if daemon_installed; then
        chmod +x "$DAEMON" 2>/dev/null
        log_line "Daemon file created."
        print_line "OK: Daemon manager installed. Daemon file created."
        return 0
    fi

    log_line "Daemon file could not be created."
    print_line "ERROR: Daemon file could not be created:"
    print_line "$DAEMON"
    return 1
}

stop_daemon() {
    log_line "Stop requested."

    _pid="$(pid_value)"

    if process_running_by_pid "$_pid"; then
        kill "$_pid" 2>/dev/null
        sleep 1

        if process_running_by_pid "$_pid"; then
            kill -9 "$_pid" 2>/dev/null
            sleep 1
        fi
    fi

    if command -v pkill >/dev/null 2>&1; then
        pkill -f "$DAEMON" 2>/dev/null
    fi

    rm -f "$PID" 2>/dev/null

    if daemon_running; then
        print_line "ERROR: Daemon still appears to be running."
        log_line "Stop failed. Daemon still appears to be running."
        return 1
    fi

    print_line "OK: Daemon stopped."
    log_line "Daemon stopped."
    return 0
}

start_daemon() {
    ensure_base
    write_default_config
    log_line "Start requested."

    if daemon_running; then
        print_line "OK: Daemon already running."
        log_line "Daemon already running."
        return 0
    fi

    if ! daemon_installed; then
        print_line "ERROR: Daemon is missing."
        print_line ""
        print_line "Expected:"
        print_line "$DAEMON"
        print_line ""
        print_line "Run Install / Prepare first."
        log_line "Start failed. Daemon is missing."
        return 1
    fi

    chmod +x "$DAEMON" 2>/dev/null

    if [ ! -e /dev/uinput ] && command -v modprobe >/dev/null 2>&1; then
        modprobe uinput >/dev/null 2>&1
    fi

    "$DAEMON" --host "$HOST" --port "$PORT" --path "$WS_PATH" >> "$LOG" 2>&1 &
    _pid="$!"
    echo "$_pid" > "$PID"

    sleep 1

    if daemon_running; then
        print_line "OK: Daemon started."
        log_line "Daemon started with PID $_pid."
        return 0
    fi

    rm -f "$PID" 2>/dev/null
    print_line "ERROR: Daemon failed to start."
    print_line ""
    print_line "Check log:"
    print_line "$LOG"
    log_line "Daemon failed to start."
    return 1
}

restart_daemon() {
    stop_daemon >/dev/null 2>&1
    start_daemon
}

start_stop_daemon() {
    if daemon_running; then
        stop_daemon
    else
        start_daemon
    fi
}

enable_startup() {
    ensure_base
    write_default_config
    mkdir -p "$STARTUP_DIR" 2>/dev/null

    if [ ! -f "$STARTUP" ]; then
        cat > "$STARTUP" <<'EOF'
#!/bin/sh
EOF
        chmod +x "$STARTUP" 2>/dev/null
    fi

    remove_startup_block >/dev/null 2>&1

    cat >> "$STARTUP" <<EOF

# MiSTer Companion Remote BEGIN
if [ ! -e /dev/uinput ] && command -v modprobe >/dev/null 2>&1; then
    modprobe uinput >/dev/null 2>&1
fi

if [ -x "$DAEMON" ]; then
    "$DAEMON" --host "$HOST" --port "$PORT" --path "$WS_PATH" >> "$LOG" 2>&1 &
fi
# MiSTer Companion Remote END
EOF

    chmod +x "$STARTUP" 2>/dev/null
    print_line "OK: Start on boot enabled."
    log_line "Start on boot enabled."
    return 0
}

disable_startup() {
    if [ ! -f "$STARTUP" ]; then
        print_line "OK: Start on boot already disabled."
        log_line "Start on boot already disabled. user-startup.sh missing."
        return 0
    fi

    if ! remove_startup_block; then
        print_line "ERROR: Could not update:"
        print_line "$STARTUP"
        log_line "Failed to disable start on boot."
        return 1
    fi

    print_line "OK: Start on boot disabled."
    log_line "Start on boot disabled."
    return 0
}

toggle_startup_unattended() {
    if startup_enabled; then
        disable_startup
    else
        enable_startup
    fi
}

uninstall_manager() {
    log_line "Uninstall requested."

    stop_daemon >/dev/null 2>&1
    disable_startup >/dev/null 2>&1

    if [ -d "$BASE" ]; then
        rm -rf "$BASE" 2>/dev/null
    fi

    print_line "OK: Companion Remote daemon files removed."
    log_line "Daemon files removed."
    return 0
}

show_log() {
    if [ ! -f "$LOG" ]; then
        print_line "No log file found yet."
        return 0
    fi

    print_line "Last log lines:"
    print_line "---------------"

    if command -v tail >/dev/null 2>&1; then
        tail -n 40 "$LOG"
    else
        cat "$LOG"
    fi
}

clear_log() {
    ensure_base
    : > "$LOG"
    print_line "OK: Log cleared."
}

run_menu_action() {
    ACTION="$1"
    RESULT_FILE="$BASE/.last_action_result"

    mkdir -p "$BASE"
    rm -f "$RESULT_FILE"

    case "$ACTION" in
        install)
            install_manager > "$RESULT_FILE" 2>&1
            ACTION_RESULT=$?
            ;;
        start-stop)
            start_stop_daemon > "$RESULT_FILE" 2>&1
            ACTION_RESULT=$?
            ;;
        toggle-boot)
            toggle_startup_unattended > "$RESULT_FILE" 2>&1
            ACTION_RESULT=$?
            ;;
        uninstall)
            uninstall_manager > "$RESULT_FILE" 2>&1
            ACTION_RESULT=$?
            ;;
        *)
            echo "Unknown action: $ACTION" > "$RESULT_FILE"
            ACTION_RESULT=1
            ;;
    esac

    if [ ! -s "$RESULT_FILE" ]; then
        echo "Done." > "$RESULT_FILE"
    fi

    RESULT_TEXT="$(cat "$RESULT_FILE" 2>/dev/null)"
    show_message "$RESULT_TEXT"

    rm -f "$RESULT_FILE" 2>/dev/null
    return $ACTION_RESULT
}

main_menu() {
    if ! has_cmd dialog; then
        echo "dialog was not found. This script requires dialog for controller-friendly menu support."
        exit 1
    fi

    while true; do
        MENU_TEXT="$(status_text)

Choose an option:"

        CHOICE="$(dialog --clear --title "$TITLE" \
            --menu "$MENU_TEXT" 18 82 5 \
            1 "Install / Prepare" \
            2 "Start / Stop Daemon" \
            3 "Toggle Start on Boot" \
            0 "Exit" \
            3>&1 1>&2 2>&3)"

        DIALOG_RESULT=$?
        clear
        sleep 0.3

        if [ $DIALOG_RESULT -ne 0 ]; then
            break
        fi

        case "$CHOICE" in
            1)
                run_menu_action install
                ;;
            2)
                run_menu_action start-stop
                ;;
            3)
                run_menu_action toggle-boot
                ;;
            0)
                break
                ;;
        esac

        clear
        sleep 0.3
    done

    clear
}

usage() {
    print_line "$TITLE"
    print_line ""
    print_line "Usage:"
    print_line "  $SCRIPT_PATH"
    print_line "  $SCRIPT_PATH status --unattended"
    print_line "  $SCRIPT_PATH status-human"
    print_line "  $SCRIPT_PATH install --unattended"
    print_line "  $SCRIPT_PATH uninstall --unattended"
    print_line "  $SCRIPT_PATH start --unattended"
    print_line "  $SCRIPT_PATH stop --unattended"
    print_line "  $SCRIPT_PATH restart --unattended"
    print_line "  $SCRIPT_PATH enable-boot --unattended"
    print_line "  $SCRIPT_PATH disable-boot --unattended"
    print_line "  $SCRIPT_PATH log --unattended"
    print_line "  $SCRIPT_PATH clear-log --unattended"
    print_line ""
    print_line "Direct MiSTer use:"
    print_line "  Run without arguments to open the minimal controller-friendly menu."
}

for arg in "$@"; do
    case "$arg" in
        --unattended)
            UNATTENDED=1
            ;;
        status|status-human|install|uninstall|start|stop|restart|enable-boot|disable-boot|log|clear-log|help)
            if [ -z "$COMMAND" ]; then
                COMMAND="$arg"
            fi
            ;;
    esac
done

if [ -z "$COMMAND" ]; then
    if [ "$UNATTENDED" -eq 1 ]; then
        COMMAND="status"
    else
        main_menu
        exit 0
    fi
fi

case "$COMMAND" in
    status)
        print_status
        ;;
    status-human)
        print_status_human
        ;;
    install)
        install_manager
        ;;
    uninstall)
        uninstall_manager
        ;;
    start)
        start_daemon
        ;;
    stop)
        stop_daemon
        ;;
    restart)
        restart_daemon
        ;;
    enable-boot)
        enable_startup
        ;;
    disable-boot)
        disable_startup
        ;;
    log)
        show_log
        ;;
    clear-log)
        clear_log
        ;;
    help)
        usage
        ;;
    *)
        usage
        exit 1
        ;;
esac

exit $?
import shutil
import zipfile
from io import BytesIO

import requests

from core.scripts_common import (
    FTP_SAVE_SYNC_CONFIG_DIR,
    FTP_SAVE_SYNC_CONFIG_PATH,
    FTP_SAVE_SYNC_DAEMON_LINE,
    FTP_SAVE_SYNC_DAEMON_PATH,
    FTP_SAVE_SYNC_LOG_PATH,
    FTP_SAVE_SYNC_RCLONE_PATH,
    FTP_SAVE_SYNC_RCLONE_URL,
    FTP_SAVE_SYNC_STARTUP_PATH,
    FTP_SAVE_SYNC_STATE_PATH,
    _chmod_local_executable,
    _local_path,
    _remote_command_success,
    _write_local_bytes,
    _write_local_text,
    _write_remote_bytes,
    _write_remote_text,
    ensure_local_scripts_dir,
    ensure_remote_scripts_dir,
    is_ftp_save_sync_service_enabled,
    is_ftp_save_sync_service_enabled_local,
)


FTP_SAVE_SYNC_URL = "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/refs/heads/main/Scripts/ftp_save_sync.sh"
FTP_SAVE_SYNC_RCLONE_URL = "https://downloads.rclone.org/rclone-current-linux-arm.zip"
FTP_SAVE_SYNC_SCRIPT_PATH = "/media/fat/Scripts/ftp_save_sync.sh"


FTP_SAVE_SYNC_DAEMON_SCRIPT = """#!/bin/sh

APP_NAME="ftp_save_sync"
BASE_DIR="/media/fat/Scripts/.config/$APP_NAME"
CONFIG_FILE="$BASE_DIR/ftp_save_sync.ini"
LOG_FILE="$BASE_DIR/ftp_save_sync.log"
STATE_FILE="$BASE_DIR/ftp_save_sync_state.db"
PID_FILE="/tmp/ftp_save_sync.pid"
RCLONE_BIN="$BASE_DIR/rclone"
RCLONE_CONFIG_TMP="/tmp/ftp_save_sync_rclone.conf.$$"
CORENAME_FILE="/tmp/CORENAME"
SYNC_ERROR_LOG="/tmp/ftp_save_sync_sync_error.log.$$"

PROTOCOL="sftp"
HOST=""
PORT="22"
USERNAME=""
PASSWORD=""
REMOTE_BASE="/mister-sync"
DEVICE_NAME="mister_1"
SYNC_SAVES="true"
SYNC_SAVESTATES="false"
SYNC_INTERVAL="15"
SKIP_HOST_KEY_CHECK="true"
SKIP_TLS_VERIFY="false"
MIN_AGE_SECONDS="5"
CURRENT_CORE_NAME=""
LAST_RUN_STATE=""

trim() {
    echo "$1" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}

bool_is_true() {
    case "$1" in
        true|TRUE|1|yes|YES) return 0 ;;
        *) return 1 ;;
    esac
}

log() {
    mkdir -p "$BASE_DIR"
    [ -f "$LOG_FILE" ] || : > "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

file_mtime() {
    stat -c %Y "$1" 2>/dev/null
}

file_age_is_old_enough() {
    f="$1"
    mtime="$(file_mtime "$f")"
    [ -n "$mtime" ] || return 1
    now="$(date +%s)"
    age=$((now - mtime))
    [ "$age" -ge "$MIN_AGE_SECONDS" ]
}

load_config() {
    [ -f "$CONFIG_FILE" ] || return 1

    PROTOCOL="$(trim "$(sed -n 's/^PROTOCOL=//p' "$CONFIG_FILE" | head -n1)")"
    HOST="$(trim "$(sed -n 's/^HOST=//p' "$CONFIG_FILE" | head -n1)")"
    PORT="$(trim "$(sed -n 's/^PORT=//p' "$CONFIG_FILE" | head -n1)")"
    USERNAME="$(trim "$(sed -n 's/^USERNAME=//p' "$CONFIG_FILE" | head -n1)")"
    PASSWORD="$(trim "$(sed -n 's/^PASSWORD=//p' "$CONFIG_FILE" | head -n1)")"
    REMOTE_BASE="$(trim "$(sed -n 's/^REMOTE_BASE=//p' "$CONFIG_FILE" | head -n1)")"
    DEVICE_NAME="$(trim "$(sed -n 's/^DEVICE_NAME=//p' "$CONFIG_FILE" | head -n1)")"
    SYNC_SAVES="$(trim "$(sed -n 's/^SYNC_SAVES=//p' "$CONFIG_FILE" | head -n1)")"
    SYNC_SAVESTATES="$(trim "$(sed -n 's/^SYNC_SAVESTATES=//p' "$CONFIG_FILE" | head -n1)")"
    SYNC_INTERVAL="$(trim "$(sed -n 's/^SYNC_INTERVAL=//p' "$CONFIG_FILE" | head -n1)")"
    SKIP_HOST_KEY_CHECK="$(trim "$(sed -n 's/^SKIP_HOST_KEY_CHECK=//p' "$CONFIG_FILE" | head -n1)")"
    SKIP_TLS_VERIFY="$(trim "$(sed -n 's/^SKIP_TLS_VERIFY=//p' "$CONFIG_FILE" | head -n1)")"
    MIN_AGE_SECONDS="$(trim "$(sed -n 's/^MIN_AGE_SECONDS=//p' "$CONFIG_FILE" | head -n1)")"

    [ -z "$PROTOCOL" ] && PROTOCOL="sftp"
    [ -z "$PORT" ] && PORT="22"
    [ -z "$REMOTE_BASE" ] && REMOTE_BASE="/mister-sync"
    [ -z "$DEVICE_NAME" ] && DEVICE_NAME="mister_1"
    [ -z "$SYNC_SAVES" ] && SYNC_SAVES="true"
    [ -z "$SYNC_SAVESTATES" ] && SYNC_SAVESTATES="false"
    [ -z "$SYNC_INTERVAL" ] && SYNC_INTERVAL="15"
    [ -z "$SKIP_HOST_KEY_CHECK" ] && SKIP_HOST_KEY_CHECK="true"
    [ -z "$SKIP_TLS_VERIFY" ] && SKIP_TLS_VERIFY="false"
    [ -z "$MIN_AGE_SECONDS" ] && MIN_AGE_SECONDS="5"

    return 0
}

cleanup() {
    if [ -f "$PID_FILE" ]; then
        run_pid="$(cat "$PID_FILE" 2>/dev/null)"
        if [ "$run_pid" = "$$" ]; then
            rm -f "$PID_FILE"
        fi
    fi
    rm -f "$SYNC_ERROR_LOG" "$RCLONE_CONFIG_TMP"
}

cleanup_and_exit() {
    cleanup
    exit 0
}

build_rclone_config() {
    obscured_pass="$($RCLONE_BIN obscure "$PASSWORD" 2>/dev/null)"
    [ -n "$obscured_pass" ] || return 1

    {
        echo "[remote]"
        echo "type = $PROTOCOL"
        echo "host = $HOST"
        echo "user = $USERNAME"
        echo "pass = $obscured_pass"
        echo "port = $PORT"

        case "$PROTOCOL" in
            sftp)
                echo "shell_type = unix"
                if bool_is_true "$SKIP_HOST_KEY_CHECK"; then
                    echo "skip_host_key_check = true"
                fi
                ;;
            ftp)
                echo "disable_mlsd = true"
                if bool_is_true "$SKIP_TLS_VERIFY"; then
                    echo "no_check_certificate = true"
                fi
                ;;
        esac
    } > "$RCLONE_CONFIG_TMP"

    return 0
}

test_connection() {
    "$RCLONE_BIN" --config "$RCLONE_CONFIG_TMP" lsf "remote:$REMOTE_BASE" >/dev/null 2>&1
}

is_sync_allowed() {
    CURRENT_CORE_NAME=""

    if [ ! -f "$CORENAME_FILE" ]; then
        return 0
    fi

    CURRENT_CORE_NAME="$(tr -d '\\r\\n' < "$CORENAME_FILE" 2>/dev/null)"

    case "$CURRENT_CORE_NAME" in
        ""|MENU)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

manifest_get_mtime() {
    manifest_file="$1"
    rel_path="$2"
    awk -F'|' -v p="$rel_path" '$1==p {print $2; exit}' "$manifest_file" 2>/dev/null
}

manifest_upsert() {
    manifest_file="$1"
    rel_path="$2"
    mtime="$3"
    device="$4"
    tmp_file="${manifest_file}.tmp.$$"

    [ -f "$manifest_file" ] || : > "$manifest_file"

    awk -F'|' -v p="$rel_path" -v m="$mtime" -v d="$device" '
        BEGIN { found=0 }
        $1==p { print p "|" m "|" d; found=1; next }
        { print }
        END { if (!found) print p "|" m "|" d }
    ' "$manifest_file" > "$tmp_file" && mv "$tmp_file" "$manifest_file"
}

build_local_manifest() {
    local_dir="$1"
    out_file="$2"

    : > "$out_file"

    [ -d "$local_dir" ] || return 0

    find "$local_dir" -type f | while IFS= read -r file_path; do
        rel_path="${file_path#$local_dir/}"
        mtime="$(file_mtime "$file_path")"
        [ -n "$mtime" ] || continue
        printf '%s|%s|%s\\n' "$rel_path" "$mtime" "$DEVICE_NAME"
    done | sort > "$out_file"
}

download_remote_manifest() {
    remote_manifest_path="$1"
    local_manifest_path="$2"

    : > "$local_manifest_path"

    "$RCLONE_BIN" --config "$RCLONE_CONFIG_TMP" copyto \
        "remote:$remote_manifest_path" "$local_manifest_path" >/dev/null 2>"$SYNC_ERROR_LOG"

    if [ $? -ne 0 ]; then
        : > "$local_manifest_path"
    fi
}

upload_manifest() {
    local_manifest_path="$1"
    remote_manifest_path="$2"

    "$RCLONE_BIN" --config "$RCLONE_CONFIG_TMP" copyto \
        "$local_manifest_path" "remote:$remote_manifest_path" >/dev/null 2>"$SYNC_ERROR_LOG"
}

sync_folder_sftp() {
    local_dir="$1"
    remote_sub="$2"
    remote_path="remote:${REMOTE_BASE}/${remote_sub}"

    [ -d "$local_dir" ] || return 0

    : > "$SYNC_ERROR_LOG"

    "$RCLONE_BIN" --config "$RCLONE_CONFIG_TMP" copy \
        "$local_dir" "$remote_path" \
        --update \
        --create-empty-src-dirs \
        --min-age "${MIN_AGE_SECONDS}s" \
        --log-file "$LOG_FILE" \
        --log-level NOTICE >/dev/null 2>"$SYNC_ERROR_LOG"

    if [ $? -ne 0 ]; then
        err_msg="$(tail -n 5 "$SYNC_ERROR_LOG" 2>/dev/null)"
        [ -z "$err_msg" ] && err_msg="Unknown upload error"
        log "Upload sync warning for $remote_sub: $err_msg"
    fi

    : > "$SYNC_ERROR_LOG"

    "$RCLONE_BIN" --config "$RCLONE_CONFIG_TMP" copy \
        "$remote_path" "$local_dir" \
        --update \
        --create-empty-src-dirs \
        --min-age "${MIN_AGE_SECONDS}s" \
        --log-file "$LOG_FILE" \
        --log-level NOTICE >/dev/null 2>"$SYNC_ERROR_LOG"

    if [ $? -ne 0 ]; then
        err_msg="$(tail -n 5 "$SYNC_ERROR_LOG" 2>/dev/null)"
        [ -z "$err_msg" ] && err_msg="Unknown download error"
        log "Download sync warning for $remote_sub: $err_msg"
    fi
}

sync_folder_ftp_manifest() {
    local_dir="$1"
    remote_sub="$2"
    remote_base_path="${REMOTE_BASE}/${remote_sub}"
    remote_manifest_path="${remote_base_path}/.ftp_save_sync_manifest.tsv"
    safe_name="$(echo "$remote_sub" | tr '/ ' '__')"
    remote_manifest_tmp="/tmp/ftp_save_sync_${safe_name}_remote_manifest.tsv.$$"
    local_manifest_tmp="/tmp/ftp_save_sync_${safe_name}_local_manifest.tsv.$$"
    final_manifest_tmp="/tmp/ftp_save_sync_${safe_name}_final_manifest.tsv.$$"

    [ -d "$local_dir" ] || return 0

    download_remote_manifest "$remote_manifest_path" "$remote_manifest_tmp"
    build_local_manifest "$local_dir" "$local_manifest_tmp"

    while IFS='|' read -r rel_path local_mtime local_device; do
        [ -n "$rel_path" ] || continue

        local_file="${local_dir}/${rel_path}"
        [ -f "$local_file" ] || continue
        file_age_is_old_enough "$local_file" || continue

        remote_mtime="$(manifest_get_mtime "$remote_manifest_tmp" "$rel_path")"

        if [ -z "$remote_mtime" ] || [ "$local_mtime" -gt "$remote_mtime" ]; then
            : > "$SYNC_ERROR_LOG"
            "$RCLONE_BIN" --config "$RCLONE_CONFIG_TMP" copyto \
                "$local_file" "remote:${remote_base_path}/${rel_path}" >/dev/null 2>"$SYNC_ERROR_LOG"

            if [ $? -eq 0 ]; then
                manifest_upsert "$remote_manifest_tmp" "$rel_path" "$local_mtime" "$DEVICE_NAME"
            else
                err_msg="$(tail -n 5 "$SYNC_ERROR_LOG" 2>/dev/null)"
                [ -z "$err_msg" ] && err_msg="Unknown upload error"
                log "Upload sync warning for $remote_sub/$rel_path: $err_msg"
            fi
        fi
    done < "$local_manifest_tmp"

    while IFS='|' read -r rel_path remote_mtime remote_device; do
        [ -n "$rel_path" ] || continue

        local_file="${local_dir}/${rel_path}"
        local_mtime=""
        if [ -f "$local_file" ]; then
            local_mtime="$(file_mtime "$local_file")"
        fi

        if [ ! -f "$local_file" ] || [ "$remote_mtime" -gt "$local_mtime" ]; then
            mkdir -p "$(dirname "$local_file")"
            : > "$SYNC_ERROR_LOG"

            "$RCLONE_BIN" --config "$RCLONE_CONFIG_TMP" copyto \
                "remote:${remote_base_path}/${rel_path}" "$local_file" >/dev/null 2>"$SYNC_ERROR_LOG"

            if [ $? -ne 0 ]; then
                err_msg="$(tail -n 5 "$SYNC_ERROR_LOG" 2>/dev/null)"
                [ -z "$err_msg" ] && err_msg="Unknown download error"
                log "Download sync warning for $remote_sub/$rel_path: $err_msg"
            fi
        fi
    done < "$remote_manifest_tmp"

    build_local_manifest "$local_dir" "$final_manifest_tmp"
    : > "$SYNC_ERROR_LOG"
    upload_manifest "$final_manifest_tmp" "$remote_manifest_path"

    if [ $? -ne 0 ]; then
        err_msg="$(tail -n 5 "$SYNC_ERROR_LOG" 2>/dev/null)"
        [ -z "$err_msg" ] && err_msg="Unknown manifest upload error"
        log "Manifest sync warning for $remote_sub: $err_msg"
    fi

    rm -f "$remote_manifest_tmp" "$local_manifest_tmp" "$final_manifest_tmp"
}

sync_folder() {
    local_dir="$1"
    remote_sub="$2"

    if [ "$PROTOCOL" = "ftp" ]; then
        sync_folder_ftp_manifest "$local_dir" "$remote_sub"
    else
        sync_folder_sftp "$local_dir" "$remote_sub"
    fi
}

run_sync_pass() {
    if ! load_config; then
        log "Config missing during sync pass."
        return 1
    fi

    if ! build_rclone_config; then
        log "Failed to rebuild rclone config for sync pass."
        return 1
    fi

    if bool_is_true "$SYNC_SAVES"; then
        sync_folder "/media/fat/saves" "saves"
    fi

    if bool_is_true "$SYNC_SAVESTATES"; then
        sync_folder "/media/fat/savestates" "savestates"
    fi
}

main() {
    one_shot="false"
    if [ "$1" = "--sync-once" ]; then
        one_shot="true"
    fi

    mkdir -p "$BASE_DIR"
    [ -f "$LOG_FILE" ] || : > "$LOG_FILE"
    [ -f "$STATE_FILE" ] || : > "$STATE_FILE"

    if [ "$one_shot" != "true" ]; then
        if [ -f "$PID_FILE" ]; then
            old_pid="$(cat "$PID_FILE" 2>/dev/null)"
            if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
                exit 0
            fi
            rm -f "$PID_FILE"
        fi

        echo $$ > "$PID_FILE"
    fi

    trap 'cleanup_and_exit' INT TERM EXIT

    if ! load_config; then
        log "Config missing, daemon exiting."
        exit 1
    fi

    if [ ! -x "$RCLONE_BIN" ]; then
        log "rclone missing, daemon exiting."
        exit 1
    fi

    if ! "$RCLONE_BIN" version >/dev/null 2>&1; then
        log "rclone exists but is not executable on this MiSTer, daemon exiting."
        exit 1
    fi

    if ! build_rclone_config; then
        log "Failed to build rclone config, daemon exiting."
        exit 1
    fi

    if ! test_connection; then
        log "Initial connection test failed, daemon will keep retrying."
    fi

    if [ "$one_shot" = "true" ]; then
        if test_connection && is_sync_allowed; then
            run_sync_pass
        else
            log "Manual sync skipped, connection unavailable or sync not allowed."
        fi
        rm -f "$RCLONE_CONFIG_TMP" "$SYNC_ERROR_LOG"
        exit 0
    fi

    log "Service started for device: $DEVICE_NAME"

    while true; do
        if is_sync_allowed; then
            if test_connection; then
                if [ "$LAST_RUN_STATE" != "allowed" ]; then
                    log "Sync resumed."
                    LAST_RUN_STATE="allowed"
                fi
                run_sync_pass
            else
                if [ "$LAST_RUN_STATE" != "waiting_for_connection" ]; then
                    log "Connection unavailable, waiting to retry."
                    LAST_RUN_STATE="waiting_for_connection"
                fi
            fi
        else
            if [ "$LAST_RUN_STATE" != "paused:$CURRENT_CORE_NAME" ]; then
                log "Sync paused, active core detected: $CURRENT_CORE_NAME"
                LAST_RUN_STATE="paused:$CURRENT_CORE_NAME"
            fi
        fi

        sleep "$SYNC_INTERVAL"
    done
}

main "$@"
"""


def _download_ftp_save_sync_script():
    response = requests.get(FTP_SAVE_SYNC_URL, timeout=30)
    response.raise_for_status()
    return response.content


def _download_ftp_save_sync_rclone_binary():
    response = requests.get(FTP_SAVE_SYNC_RCLONE_URL, timeout=60)
    response.raise_for_status()

    zip_file = zipfile.ZipFile(BytesIO(response.content))

    for entry in zip_file.namelist():
        normalized = entry.replace("\\", "/")
        if normalized.endswith("/rclone") or normalized == "rclone":
            return zip_file.read(entry)

    raise RuntimeError("Could not find rclone binary inside the downloaded ZIP.")


def _parse_ftp_save_sync_config_text(text):
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


def _build_ftp_save_sync_ini(
    protocol,
    host,
    port,
    username,
    password,
    remote_base,
    device_name,
    sync_savestates,
):
    return f"""PROTOCOL={protocol}
HOST={host}
PORT={port}
USERNAME={username}
PASSWORD={password}
REMOTE_BASE={remote_base}
DEVICE_NAME={device_name}

SYNC_SAVES=true
SYNC_SAVESTATES={"true" if sync_savestates else "false"}
SYNC_INTERVAL=15

SKIP_HOST_KEY_CHECK=true
SKIP_TLS_VERIFY=false
PAUSE_WHILE_CORE_RUNNING=true

MIN_AGE_SECONDS=5
"""


def _ftp_save_sync_startup_block():
    return f"""# ftp_save_sync START
(
    sleep 15
    {FTP_SAVE_SYNC_DAEMON_LINE}
) &
# ftp_save_sync END
"""


def ensure_ftp_save_sync_bootstrap(connection, log=None):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    def _log(message):
        if log:
            log(message)

    ensure_remote_scripts_dir(connection)

    connection.run_command(f"mkdir -p {FTP_SAVE_SYNC_CONFIG_DIR}")
    connection.run_command(f"test -f {FTP_SAVE_SYNC_LOG_PATH} || : > {FTP_SAVE_SYNC_LOG_PATH}")
    connection.run_command(f"test -f {FTP_SAVE_SYNC_STATE_PATH} || : > {FTP_SAVE_SYNC_STATE_PATH}")

    rclone_ok = _remote_command_success(connection, f"{FTP_SAVE_SYNC_RCLONE_PATH} version")
    if rclone_ok:
        _log("Existing ftp_save_sync rclone binary is valid, keeping it.\n")
    else:
        _log("Installing ftp_save_sync rclone binary...\n")
        rclone_binary = _download_ftp_save_sync_rclone_binary()
        _write_remote_bytes(connection, FTP_SAVE_SYNC_RCLONE_PATH, rclone_binary)
        connection.run_command(f"chmod +x {FTP_SAVE_SYNC_RCLONE_PATH}")

        if not _remote_command_success(connection, f"{FTP_SAVE_SYNC_RCLONE_PATH} version"):
            raise RuntimeError("ftp_save_sync rclone upload succeeded, but the binary is not executable on MiSTer.")

        _log("ftp_save_sync rclone installed successfully.\n")

    _log("Writing ftp_save_sync daemon script...\n")
    _write_remote_text(connection, FTP_SAVE_SYNC_DAEMON_PATH, FTP_SAVE_SYNC_DAEMON_SCRIPT)
    connection.run_command(f"chmod +x {FTP_SAVE_SYNC_DAEMON_PATH}")

    if not _remote_command_success(connection, f"test -x {FTP_SAVE_SYNC_DAEMON_PATH}"):
        raise RuntimeError("ftp_save_sync daemon script could not be prepared on MiSTer.")

    _log("ftp_save_sync bootstrap complete.\n")


def ensure_ftp_save_sync_bootstrap_local(sd_root, log=None):
    def _log(message):
        if log:
            log(message)

    ensure_local_scripts_dir(sd_root)

    config_dir = _local_path(sd_root, FTP_SAVE_SYNC_CONFIG_DIR)
    config_dir.mkdir(parents=True, exist_ok=True)

    log_path = _local_path(sd_root, FTP_SAVE_SYNC_LOG_PATH)
    state_path = _local_path(sd_root, FTP_SAVE_SYNC_STATE_PATH)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")

    if not state_path.exists():
        state_path.write_text("", encoding="utf-8")

    rclone_path = _local_path(sd_root, FTP_SAVE_SYNC_RCLONE_PATH)
    if rclone_path.exists() and rclone_path.stat().st_size > 0:
        _log("Existing ftp_save_sync rclone binary found, keeping it.\n")
    else:
        _log("Installing ftp_save_sync rclone binary...\n")
        rclone_binary = _download_ftp_save_sync_rclone_binary()
        _write_local_bytes(sd_root, FTP_SAVE_SYNC_RCLONE_PATH, rclone_binary)
        _chmod_local_executable(sd_root, FTP_SAVE_SYNC_RCLONE_PATH)
        _log("ftp_save_sync rclone installed successfully.\n")

    _log("Writing ftp_save_sync daemon script...\n")
    _write_local_text(sd_root, FTP_SAVE_SYNC_DAEMON_PATH, FTP_SAVE_SYNC_DAEMON_SCRIPT)
    _chmod_local_executable(sd_root, FTP_SAVE_SYNC_DAEMON_PATH)

    _log("ftp_save_sync bootstrap complete.\n")


def install_ftp_save_sync(connection, log):
    log("Installing ftp_save_sync...\n")
    script_data = _download_ftp_save_sync_script()

    ensure_remote_scripts_dir(connection)
    _write_remote_bytes(connection, FTP_SAVE_SYNC_SCRIPT_PATH, script_data)

    connection.run_command(f"chmod +x {FTP_SAVE_SYNC_SCRIPT_PATH}")
    log("ftp_save_sync main script uploaded.\n")

    ensure_ftp_save_sync_bootstrap(connection, log)
    log("ftp_save_sync installed successfully.\n")


def install_ftp_save_sync_local(sd_root, log):
    log("Installing ftp_save_sync to Offline SD Card...\n")
    script_data = _download_ftp_save_sync_script()

    ensure_local_scripts_dir(sd_root)
    _write_local_bytes(sd_root, FTP_SAVE_SYNC_SCRIPT_PATH, script_data)
    _chmod_local_executable(sd_root, FTP_SAVE_SYNC_SCRIPT_PATH)

    log("ftp_save_sync main script copied.\n")

    ensure_ftp_save_sync_bootstrap_local(sd_root, log)
    log("ftp_save_sync installed successfully.\n")


def uninstall_ftp_save_sync(connection):
    disable_ftp_save_sync_service(connection)
    connection.run_command(f"rm -f {FTP_SAVE_SYNC_SCRIPT_PATH}")
    connection.run_command(f"rm -rf {FTP_SAVE_SYNC_CONFIG_DIR}")


def uninstall_ftp_save_sync_local(sd_root):
    disable_ftp_save_sync_service_local(sd_root)

    script_path = _local_path(sd_root, FTP_SAVE_SYNC_SCRIPT_PATH)
    config_dir = _local_path(sd_root, FTP_SAVE_SYNC_CONFIG_DIR)

    if script_path.exists():
        script_path.unlink()

    if config_dir.exists():
        shutil.rmtree(config_dir)


def load_ftp_save_sync_config(connection):
    if not connection.is_connected():
        return {}

    output = connection.run_command(f"cat {FTP_SAVE_SYNC_CONFIG_PATH} 2>/dev/null")
    return _parse_ftp_save_sync_config_text(output or "")


def load_ftp_save_sync_config_local(sd_root):
    path = _local_path(sd_root, FTP_SAVE_SYNC_CONFIG_PATH)
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8", errors="ignore")
    return _parse_ftp_save_sync_config_text(text)


def save_ftp_save_sync_config(
    connection,
    protocol,
    host,
    port,
    username,
    password,
    remote_base,
    device_name,
    sync_savestates,
):
    ini = _build_ftp_save_sync_ini(
        protocol=protocol,
        host=host,
        port=port,
        username=username,
        password=password,
        remote_base=remote_base,
        device_name=device_name,
        sync_savestates=sync_savestates,
    )

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(FTP_SAVE_SYNC_CONFIG_PATH, "w") as remote_file:
            remote_file.write(ini)
    finally:
        sftp.close()


def save_ftp_save_sync_config_local(
    sd_root,
    protocol,
    host,
    port,
    username,
    password,
    remote_base,
    device_name,
    sync_savestates,
):
    ini = _build_ftp_save_sync_ini(
        protocol=protocol,
        host=host,
        port=port,
        username=username,
        password=password,
        remote_base=remote_base,
        device_name=device_name,
        sync_savestates=sync_savestates,
    )

    ensure_local_scripts_dir(sd_root)

    path = _local_path(sd_root, FTP_SAVE_SYNC_CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ini, encoding="utf-8")


def remove_ftp_save_sync_config(connection):
    connection.run_command(f"rm -f {FTP_SAVE_SYNC_CONFIG_PATH}")


def remove_ftp_save_sync_config_local(sd_root):
    path = _local_path(sd_root, FTP_SAVE_SYNC_CONFIG_PATH)
    if path.exists():
        path.unlink()


def enable_ftp_save_sync_service(connection):
    exists = connection.run_command(
        f"test -f {FTP_SAVE_SYNC_STARTUP_PATH} && echo EXISTS"
    )

    if "EXISTS" not in (exists or ""):
        script = f"""#!/bin/sh

{_ftp_save_sync_startup_block()}"""
        sftp = connection.client.open_sftp()
        try:
            with sftp.open(FTP_SAVE_SYNC_STARTUP_PATH, "w") as handle:
                handle.write(script)
        finally:
            sftp.close()
        return

    if is_ftp_save_sync_service_enabled(connection):
        return

    connection.run_command(f'echo "" >> {FTP_SAVE_SYNC_STARTUP_PATH}')
    connection.run_command(f'echo "# ftp_save_sync START" >> {FTP_SAVE_SYNC_STARTUP_PATH}')
    connection.run_command(f'echo "(" >> {FTP_SAVE_SYNC_STARTUP_PATH}')
    connection.run_command(f'echo "    sleep 15" >> {FTP_SAVE_SYNC_STARTUP_PATH}')
    connection.run_command(
        f'echo "    {FTP_SAVE_SYNC_DAEMON_LINE}" >> {FTP_SAVE_SYNC_STARTUP_PATH}'
    )
    connection.run_command(f'echo ") &" >> {FTP_SAVE_SYNC_STARTUP_PATH}')
    connection.run_command(f'echo "# ftp_save_sync END" >> {FTP_SAVE_SYNC_STARTUP_PATH}')


def enable_ftp_save_sync_service_local(sd_root):
    startup_path = _local_path(sd_root, FTP_SAVE_SYNC_STARTUP_PATH)
    startup_path.parent.mkdir(parents=True, exist_ok=True)

    if not startup_path.exists():
        startup_path.write_text(
            f"#!/bin/sh\n\n{_ftp_save_sync_startup_block()}",
            encoding="utf-8",
        )
        _chmod_local_executable(sd_root, FTP_SAVE_SYNC_STARTUP_PATH)
        return

    if is_ftp_save_sync_service_enabled_local(sd_root):
        return

    text = startup_path.read_text(encoding="utf-8", errors="ignore").rstrip()
    text = f"{text}\n\n{_ftp_save_sync_startup_block()}"
    startup_path.write_text(text, encoding="utf-8")
    _chmod_local_executable(sd_root, FTP_SAVE_SYNC_STARTUP_PATH)


def disable_ftp_save_sync_service(connection):
    if not connection.is_connected():
        return

    connection.run_command(
        f"sed -i '/# ftp_save_sync START/,/# ftp_save_sync END/d' {FTP_SAVE_SYNC_STARTUP_PATH} 2>/dev/null"
    )


def disable_ftp_save_sync_service_local(sd_root):
    startup_path = _local_path(sd_root, FTP_SAVE_SYNC_STARTUP_PATH)
    if not startup_path.exists():
        return

    lines = startup_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    new_lines = []
    skipping = False

    for line in lines:
        stripped = line.strip()

        if stripped == "# ftp_save_sync START":
            skipping = True
            continue

        if stripped == "# ftp_save_sync END":
            skipping = False
            continue

        if not skipping:
            new_lines.append(line)

    startup_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
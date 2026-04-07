import os
import shlex
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from io import BytesIO

import requests


UPDATE_ALL_RELEASE_API = "https://api.github.com/repos/theypsilon/Update_All_MiSTer/releases/latest"
ZAPAROO_RELEASE_API = "https://api.github.com/repos/ZaparooProject/zaparoo-core/releases/latest"
MIGRATE_SD_URL = "https://raw.githubusercontent.com/Natrox/MiSTer_Utils_Natrox/main/scripts/migrate_sd.sh"
CIFS_MOUNT_URL = "https://raw.githubusercontent.com/MiSTer-devel/Scripts_MiSTer/master/cifs_mount.sh"
CIFS_UMOUNT_URL = "https://raw.githubusercontent.com/MiSTer-devel/Scripts_MiSTer/master/cifs_umount.sh"
AUTO_TIME_URL = "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/main/Scripts/auto_time.sh"
DAV_BROWSER_URL = "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/main/Scripts/dav_browser.sh"
FTP_SAVE_SYNC_URL = "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/refs/heads/main/Scripts/ftp_save_sync.sh"
FTP_SAVE_SYNC_RCLONE_URL = "https://downloads.rclone.org/rclone-current-linux-arm.zip"
STATIC_WALLPAPER_URL = "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/main/Scripts/static_wallpaper.sh"

UPDATE_ALL_JSON_PATH = "/media/fat/Scripts/.config/update_all/update_all.json"
DOWNLOADER_INI_PATH = "/media/fat/downloader.ini"

DAV_BROWSER_CONFIG_DIR = "/media/fat/Scripts/.config/dav_browser"
DAV_BROWSER_CONFIG_PATH = "/media/fat/Scripts/.config/dav_browser/dav_browser.ini"

FTP_SAVE_SYNC_CONFIG_DIR = "/media/fat/Scripts/.config/ftp_save_sync"
FTP_SAVE_SYNC_CONFIG_PATH = "/media/fat/Scripts/.config/ftp_save_sync/ftp_save_sync.ini"
FTP_SAVE_SYNC_STARTUP_PATH = "/media/fat/linux/user-startup.sh"
FTP_SAVE_SYNC_DAEMON_PATH = "/media/fat/Scripts/.config/ftp_save_sync/ftp_save_sync_daemon.sh"
FTP_SAVE_SYNC_DAEMON_LINE = "/media/fat/Scripts/.config/ftp_save_sync/ftp_save_sync_daemon.sh >/dev/null 2>&1"
FTP_SAVE_SYNC_RCLONE_PATH = "/media/fat/Scripts/.config/ftp_save_sync/rclone"
FTP_SAVE_SYNC_LOG_PATH = "/media/fat/Scripts/.config/ftp_save_sync/ftp_save_sync.log"
FTP_SAVE_SYNC_STATE_PATH = "/media/fat/Scripts/.config/ftp_save_sync/ftp_save_sync_state.db"

STATIC_WALLPAPER_SCRIPT_PATH = "/media/fat/Scripts/static_wallpaper.sh"
STATIC_WALLPAPER_CONFIG_DIR = "/media/fat/Scripts/.config/static_wallpaper"
STATIC_WALLPAPER_CONFIG_PATH = "/media/fat/Scripts/.config/static_wallpaper/selected_wallpaper.txt"
STATIC_WALLPAPER_DIR = "/media/fat/wallpapers"
STATIC_WALLPAPER_TARGET_JPG = "/media/fat/menu.jpg"
STATIC_WALLPAPER_TARGET_PNG = "/media/fat/menu.png"
MISTER_MENU_RELOAD_CMD = 'echo "load_core /media/fat/menu.rbf" > /dev/MiSTer_cmd'

DEFAULT_UPDATE_ALL_JSON = """{"migration_version": 6, "theme": "Blue Installer", "mirror": "", "countdown_time": 15, "log_viewer": true, "use_settings_screen_theme_in_log_viewer": true, "autoreboot": true, "download_beta_cores": false, "names_region": "JP", "names_char_code": "CHAR18", "names_sort_code": "Common", "introduced_arcade_names_txt": true, "pocket_firmware_update": false, "pocket_backup": false, "timeline_after_logs": true, "overscan": "medium", "monochrome_ui": false}
"""

DEFAULT_DOWNLOADER_INI = """[distribution_mister]
db_url = https://raw.githubusercontent.com/MiSTer-devel/Distribution_MiSTer/main/db.json.zip

[jtcores]
db_url = https://raw.githubusercontent.com/jotego/jtcores_mister/main/jtbindb.json.zip

[Coin-OpCollection/Distribution-MiSTerFPGA]
db_url = https://raw.githubusercontent.com/Coin-OpCollection/Distribution-MiSTerFPGA/db/db.json.zip

[update_all_mister]
db_url = https://raw.githubusercontent.com/theypsilon/Update_All_MiSTer/db/update_all_db.json
"""

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


@dataclass
class ScriptsStatus:
    update_all_installed: bool
    update_all_initialized: bool
    zaparoo_installed: bool
    zaparoo_service_enabled: bool
    migrate_sd_installed: bool
    cifs_installed: bool
    cifs_configured: bool
    auto_time_installed: bool
    dav_browser_installed: bool
    dav_browser_configured: bool
    ftp_save_sync_installed: bool
    ftp_save_sync_configured: bool
    ftp_save_sync_service_enabled: bool
    static_wallpaper_installed: bool
    static_wallpaper_active: bool
    static_wallpaper_saved: bool


def ensure_remote_scripts_dir(connection):
    connection.run_command("mkdir -p /media/fat/Scripts")
    connection.run_command("mkdir -p /media/fat/Scripts/.config/update_all")
    connection.run_command("mkdir -p /media/fat/Scripts/.config/dav_browser")
    connection.run_command(f"mkdir -p {FTP_SAVE_SYNC_CONFIG_DIR}")
    connection.run_command(f"mkdir -p {STATIC_WALLPAPER_CONFIG_DIR}")


def _remote_file_exists(sftp, path):
    try:
        sftp.stat(path)
        return True
    except Exception:
        return False


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


def _read_remote_bytes(connection, path):
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "rb") as remote_file:
            return remote_file.read()
    finally:
        sftp.close()


def _read_remote_text(connection, path):
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "r") as remote_file:
            return remote_file.read()
    finally:
        sftp.close()


def _remote_command_success(connection, command):
    result = connection.run_command(f"{command} >/dev/null 2>&1 && echo OK || echo FAIL")
    return "OK" in (result or "")


def _download_ftp_save_sync_rclone_binary():
    response = requests.get(FTP_SAVE_SYNC_RCLONE_URL, timeout=60)
    response.raise_for_status()

    zip_file = zipfile.ZipFile(BytesIO(response.content))

    for entry in zip_file.namelist():
        normalized = entry.replace("\\", "/")
        if normalized.endswith("/rclone") or normalized == "rclone":
            return zip_file.read(entry)

    raise RuntimeError("Could not find rclone binary inside the downloaded ZIP.")


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


def ensure_update_all_config_bootstrap(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    ensure_remote_scripts_dir(connection)

    created = {
        "update_all_json_created": False,
        "downloader_ini_created": False,
    }

    sftp = connection.client.open_sftp()
    try:
        if not _remote_file_exists(sftp, UPDATE_ALL_JSON_PATH):
            with sftp.open(UPDATE_ALL_JSON_PATH, "w") as handle:
                handle.write(DEFAULT_UPDATE_ALL_JSON)
            created["update_all_json_created"] = True

        if not _remote_file_exists(sftp, DOWNLOADER_INI_PATH):
            with sftp.open(DOWNLOADER_INI_PATH, "w") as handle:
                handle.write(DEFAULT_DOWNLOADER_INI)
            created["downloader_ini_created"] = True
    finally:
        sftp.close()

    return created


def check_update_all_initialized(connection) -> bool:
    if not connection.is_connected():
        return False

    sftp = None
    try:
        sftp = connection.client.open_sftp()
        sftp.stat(UPDATE_ALL_JSON_PATH)
        return True
    except Exception:
        return False
    finally:
        if sftp is not None:
            sftp.close()


def is_ftp_save_sync_service_enabled(connection) -> bool:
    if not connection.is_connected():
        return False

    check = connection.run_command(
        f"grep -F '{FTP_SAVE_SYNC_DAEMON_LINE}' {FTP_SAVE_SYNC_STARTUP_PATH} 2>/dev/null"
    )
    return bool(check and "ftp_save_sync_daemon.sh" in check)


def reload_mister_menu(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    connection.run_command(MISTER_MENU_RELOAD_CMD)


def is_static_wallpaper_active(connection) -> bool:
    if not connection.is_connected():
        return False

    jpg_check = connection.run_command(
        f"test -f {STATIC_WALLPAPER_TARGET_JPG} && echo EXISTS"
    )
    png_check = connection.run_command(
        f"test -f {STATIC_WALLPAPER_TARGET_PNG} && echo EXISTS"
    )
    return ("EXISTS" in (jpg_check or "")) or ("EXISTS" in (png_check or ""))


def has_static_wallpaper_saved_selection(connection) -> bool:
    if not connection.is_connected():
        return False

    check = connection.run_command(
        f"test -f {STATIC_WALLPAPER_CONFIG_PATH} && echo EXISTS"
    )
    return "EXISTS" in (check or "")


def get_static_wallpaper_saved_selection(connection) -> str:
    if not connection.is_connected():
        return ""

    output = connection.run_command(f"cat {STATIC_WALLPAPER_CONFIG_PATH} 2>/dev/null")
    return (output or "").strip()


def get_static_wallpaper_state(connection) -> dict:
    if not connection.is_connected():
        return {
            "installed": False,
            "active": False,
            "active_target": "",
            "saved": False,
            "saved_path": "",
            "saved_name": "",
        }

    installed_check = connection.run_command(
        f"test -f {STATIC_WALLPAPER_SCRIPT_PATH} && echo EXISTS"
    )
    jpg_check = connection.run_command(
        f"test -f {STATIC_WALLPAPER_TARGET_JPG} && echo EXISTS"
    )
    png_check = connection.run_command(
        f"test -f {STATIC_WALLPAPER_TARGET_PNG} && echo EXISTS"
    )
    saved_path = get_static_wallpaper_saved_selection(connection)

    active_target = ""
    if "EXISTS" in (jpg_check or ""):
        active_target = "menu.jpg"
    elif "EXISTS" in (png_check or ""):
        active_target = "menu.png"

    return {
        "installed": "EXISTS" in (installed_check or ""),
        "active": bool(active_target),
        "active_target": active_target,
        "saved": bool(saved_path),
        "saved_path": saved_path,
        "saved_name": os.path.basename(saved_path) if saved_path else "",
    }


def get_scripts_status(connection) -> ScriptsStatus:
    if not connection.is_connected():
        return ScriptsStatus(
            False, False, False, False, False, False, False,
            False, False, False, False, False, False,
            False, False, False
        )

    update_check = connection.run_command(
        "test -f /media/fat/Scripts/update_all.sh && echo EXISTS"
    )
    update_all_installed = "EXISTS" in (update_check or "")

    zaparoo_check = connection.run_command(
        "test -f /media/fat/Scripts/zaparoo.sh && echo EXISTS"
    )
    zaparoo_installed = "EXISTS" in (zaparoo_check or "")

    zaparoo_service_check = connection.run_command(
        "grep 'mrext/zaparoo' /media/fat/linux/user-startup.sh 2>/dev/null"
    )
    zaparoo_service_enabled = bool(
        zaparoo_service_check and "mrext/zaparoo" in zaparoo_service_check
    )

    migrate_check = connection.run_command(
        "test -f /media/fat/Scripts/migrate_sd.sh && echo EXISTS"
    )
    migrate_sd_installed = "EXISTS" in (migrate_check or "")

    cifs_script_check = connection.run_command(
        "test -f /media/fat/Scripts/cifs_mount.sh && echo EXISTS"
    )
    cifs_ini_check = connection.run_command(
        "test -f /media/fat/Scripts/cifs_mount.ini && echo CONFIG"
    )
    cifs_installed = "EXISTS" in (cifs_script_check or "")
    cifs_configured = "CONFIG" in (cifs_ini_check or "")

    auto_time_check = connection.run_command(
        "test -f /media/fat/Scripts/auto_time.sh && echo EXISTS"
    )
    auto_time_installed = "EXISTS" in (auto_time_check or "")

    dav_browser_script_check = connection.run_command(
        "test -f /media/fat/Scripts/dav_browser.sh && echo EXISTS"
    )
    dav_browser_ini_check = connection.run_command(
        f"test -f {DAV_BROWSER_CONFIG_PATH} && echo CONFIG"
    )
    dav_browser_installed = "EXISTS" in (dav_browser_script_check or "")
    dav_browser_configured = "CONFIG" in (dav_browser_ini_check or "")

    ftp_save_sync_script_check = connection.run_command(
        "test -f /media/fat/Scripts/ftp_save_sync.sh && echo EXISTS"
    )
    ftp_save_sync_ini_check = connection.run_command(
        f"test -f {FTP_SAVE_SYNC_CONFIG_PATH} && echo CONFIG"
    )
    ftp_save_sync_installed = "EXISTS" in (ftp_save_sync_script_check or "")
    ftp_save_sync_configured = "CONFIG" in (ftp_save_sync_ini_check or "")
    ftp_save_sync_service_enabled = (
        is_ftp_save_sync_service_enabled(connection) if ftp_save_sync_installed else False
    )

    static_wallpaper_script_check = connection.run_command(
        f"test -f {STATIC_WALLPAPER_SCRIPT_PATH} && echo EXISTS"
    )
    static_wallpaper_installed = "EXISTS" in (static_wallpaper_script_check or "")
    static_wallpaper_active = is_static_wallpaper_active(connection)
    static_wallpaper_saved = has_static_wallpaper_saved_selection(connection)

    return ScriptsStatus(
        update_all_installed=update_all_installed,
        update_all_initialized=check_update_all_initialized(connection) if update_all_installed else False,
        zaparoo_installed=zaparoo_installed,
        zaparoo_service_enabled=zaparoo_service_enabled,
        migrate_sd_installed=migrate_sd_installed,
        cifs_installed=cifs_installed,
        cifs_configured=cifs_configured,
        auto_time_installed=auto_time_installed,
        dav_browser_installed=dav_browser_installed,
        dav_browser_configured=dav_browser_configured,
        ftp_save_sync_installed=ftp_save_sync_installed,
        ftp_save_sync_configured=ftp_save_sync_configured,
        ftp_save_sync_service_enabled=ftp_save_sync_service_enabled,
        static_wallpaper_installed=static_wallpaper_installed,
        static_wallpaper_active=static_wallpaper_active,
        static_wallpaper_saved=static_wallpaper_saved,
    )


def install_update_all(connection, log):
    log("Installing update_all...\n")
    api_data = requests.get(UPDATE_ALL_RELEASE_API, timeout=15).json()

    download_url = None
    asset_name = None
    for asset in api_data.get("assets", []):
        if asset["name"].endswith(".sh"):
            download_url = asset["browser_download_url"]
            asset_name = asset["name"]
            break

    if not download_url:
        raise RuntimeError("Could not find update_all script.")

    log(f"Found release: {asset_name}\n")
    log("Downloading release...\n")
    script_data = requests.get(download_url, timeout=30).content

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/update_all.sh", "wb") as remote_file:
            remote_file.write(script_data)
    finally:
        sftp.close()

    connection.run_command("chmod +x /media/fat/Scripts/update_all.sh")
    log("Installation complete.\n")


def uninstall_update_all(connection):
    connection.run_command("rm -f /media/fat/Scripts/update_all.sh")


def run_update_all_stream(connection, log):
    connection.run_command_stream("/media/fat/Scripts/update_all.sh", log)


def install_zaparoo(connection, log):
    log("Installing Zaparoo...\n")
    api_data = requests.get(ZAPAROO_RELEASE_API, timeout=15).json()

    download_url = None
    asset_name = None

    for asset in api_data.get("assets", []):
        name = asset["name"].lower()
        if "mister_arm" in name and name.endswith(".zip"):
            download_url = asset["browser_download_url"]
            asset_name = asset["name"]
            break

    if not download_url:
        raise RuntimeError("Could not find MiSTer Zaparoo release.")

    log(f"Found release: {asset_name}\n")
    log("Downloading release...\n")
    zip_data = requests.get(download_url, timeout=30).content
    zip_file = zipfile.ZipFile(BytesIO(zip_data))

    ensure_remote_scripts_dir(connection)

    zaparoo_data = None
    for entry in zip_file.namelist():
        if entry.endswith("zaparoo.sh"):
            zaparoo_data = zip_file.read(entry)
            break

    if zaparoo_data is None:
        raise RuntimeError("Could not find zaparoo.sh inside the release ZIP.")

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/zaparoo.sh", "wb") as remote_file:
            remote_file.write(zaparoo_data)
    finally:
        sftp.close()

    connection.run_command("chmod +x /media/fat/Scripts/zaparoo.sh")
    log("Zaparoo installation complete.\n")
    log("Next step: Enable the Zaparoo service from the Scripts tab.\n")


def enable_zaparoo_service(connection):
    exists = connection.run_command(
        "test -f /media/fat/linux/user-startup.sh && echo EXISTS"
    )

    if "EXISTS" not in (exists or ""):
        script = """#!/bin/sh

# mrext/zaparoo
[[ -e /media/fat/Scripts/zaparoo.sh ]] && /media/fat/Scripts/zaparoo.sh -service $1
"""
        sftp = connection.client.open_sftp()
        try:
            with sftp.open("/media/fat/linux/user-startup.sh", "w") as handle:
                handle.write(script)
        finally:
            sftp.close()
        return

    check = connection.run_command(
        "grep 'mrext/zaparoo' /media/fat/linux/user-startup.sh"
    )

    if not check:
        connection.run_command('echo "" >> /media/fat/linux/user-startup.sh')
        connection.run_command('echo "# mrext/zaparoo" >> /media/fat/linux/user-startup.sh')
        connection.run_command(
            'echo "[[ -e /media/fat/Scripts/zaparoo.sh ]] && /media/fat/Scripts/zaparoo.sh -service $1" >> /media/fat/linux/user-startup.sh'
        )


def uninstall_zaparoo(connection):
    connection.run_command("rm -f /media/fat/Scripts/zaparoo.sh")
    connection.run_command("rm -rf /media/fat/zaparoo")


def install_migrate_sd(connection, log):
    log("Installing migrate_sd...\n")
    script_data = requests.get(MIGRATE_SD_URL, timeout=30).content

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/migrate_sd.sh", "wb") as remote_file:
            remote_file.write(script_data)
    finally:
        sftp.close()

    connection.run_command("chmod +x /media/fat/Scripts/migrate_sd.sh")
    log("migrate_sd installed successfully.\n")
    log("Run it from the MiSTer Scripts menu.\n")


def uninstall_migrate_sd(connection):
    connection.run_command("rm -f /media/fat/Scripts/migrate_sd.sh")


def install_cifs_mount(connection, log):
    log("Installing cifs_mount scripts...\n")
    mount_script = requests.get(CIFS_MOUNT_URL, timeout=30).content
    umount_script = requests.get(CIFS_UMOUNT_URL, timeout=30).content

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/cifs_mount.sh", "wb") as remote_file:
            remote_file.write(mount_script)
        with sftp.open("/media/fat/Scripts/cifs_umount.sh", "wb") as remote_file:
            remote_file.write(umount_script)
    finally:
        sftp.close()

    connection.run_command("chmod +x /media/fat/Scripts/cifs_mount.sh")
    connection.run_command("chmod +x /media/fat/Scripts/cifs_umount.sh")
    log("CIFS scripts installed.\n")


def uninstall_cifs_mount(connection):
    connection.run_command("rm -f /media/fat/Scripts/cifs_mount.sh")
    connection.run_command("rm -f /media/fat/Scripts/cifs_umount.sh")


def run_cifs_mount(connection):
    return connection.run_command("/media/fat/Scripts/cifs_mount.sh")


def run_cifs_umount(connection):
    return connection.run_command("/media/fat/Scripts/cifs_umount.sh")


def remove_cifs_config(connection):
    connection.run_command("rm -f /media/fat/Scripts/cifs_mount.ini")


def load_cifs_config(connection):
    config = {}

    if not connection.is_connected():
        return config

    output = connection.run_command("cat /media/fat/Scripts/cifs_mount.ini 2>/dev/null")
    if not output:
        return config

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip()] = value.strip().strip('"')

    return config


def save_cifs_config(connection, server, share, username, password, mount_at_boot):
    ini = f'''SERVER="{server}"
SHARE="{share}"
USERNAME="{username}"
PASSWORD="{password}"
LOCAL_DIR="cifs/games"
WAIT_FOR_SERVER="true"
MOUNT_AT_BOOT="{str(mount_at_boot).lower()}"
SINGLE_CIFS_CONNECTION="true"
'''

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/cifs_mount.ini", "w") as remote_file:
            remote_file.write(ini)
    finally:
        sftp.close()


def test_cifs_connection(connection, server, share, username, password):
    test_cmd = (
        f'mount -t cifs //{server}/{share} /tmp/cifs_test '
        f'-o username="{username}",password="{password}"'
    )
    result = connection.run_command(
        f'mkdir -p /tmp/cifs_test && {test_cmd} && umount /tmp/cifs_test && echo SUCCESS'
    )
    return bool(result and "SUCCESS" in result)


def install_auto_time(connection, log):
    log("Installing auto_time...\n")
    script_data = requests.get(AUTO_TIME_URL, timeout=30).content

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/auto_time.sh", "wb") as remote_file:
            remote_file.write(script_data)
    finally:
        sftp.close()

    connection.run_command("chmod +x /media/fat/Scripts/auto_time.sh")
    log("auto_time installed successfully.\n")


def uninstall_auto_time(connection):
    connection.run_command("rm -f /media/fat/Scripts/auto_time.sh")


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


def install_ftp_save_sync(connection, log):
    log("Installing ftp_save_sync...\n")
    script_data = requests.get(FTP_SAVE_SYNC_URL, timeout=30).content

    ensure_remote_scripts_dir(connection)
    _write_remote_bytes(connection, "/media/fat/Scripts/ftp_save_sync.sh", script_data)

    connection.run_command("chmod +x /media/fat/Scripts/ftp_save_sync.sh")
    log("ftp_save_sync main script uploaded.\n")

    ensure_ftp_save_sync_bootstrap(connection, log)
    log("ftp_save_sync installed successfully.\n")


def uninstall_ftp_save_sync(connection):
    disable_ftp_save_sync_service(connection)
    connection.run_command("rm -f /media/fat/Scripts/ftp_save_sync.sh")
    connection.run_command(f"rm -rf {FTP_SAVE_SYNC_CONFIG_DIR}")


def load_ftp_save_sync_config(connection):
    config = {}

    if not connection.is_connected():
        return config

    output = connection.run_command(f"cat {FTP_SAVE_SYNC_CONFIG_PATH} 2>/dev/null")
    if not output:
        return config

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip()] = value.strip().strip('"')

    return config


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
    ini = f"""PROTOCOL={protocol}
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

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(FTP_SAVE_SYNC_CONFIG_PATH, "w") as remote_file:
            remote_file.write(ini)
    finally:
        sftp.close()


def remove_ftp_save_sync_config(connection):
    connection.run_command(f"rm -f {FTP_SAVE_SYNC_CONFIG_PATH}")


def enable_ftp_save_sync_service(connection):
    exists = connection.run_command(
        f"test -f {FTP_SAVE_SYNC_STARTUP_PATH} && echo EXISTS"
    )

    if "EXISTS" not in (exists or ""):
        script = f"""#!/bin/sh

# ftp_save_sync START
(
    sleep 15
    {FTP_SAVE_SYNC_DAEMON_LINE}
) &
# ftp_save_sync END
"""
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


def disable_ftp_save_sync_service(connection):
    if not connection.is_connected():
        return

    connection.run_command(
        f"sed -i '/# ftp_save_sync START/,/# ftp_save_sync END/d' {FTP_SAVE_SYNC_STARTUP_PATH} 2>/dev/null"
    )


def install_static_wallpaper(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log("Installing static_wallpaper...\n")
    script_data = requests.get(STATIC_WALLPAPER_URL, timeout=30).content

    ensure_remote_scripts_dir(connection)
    _write_remote_bytes(connection, STATIC_WALLPAPER_SCRIPT_PATH, script_data)

    connection.run_command(f"chmod +x {STATIC_WALLPAPER_SCRIPT_PATH}")
    connection.run_command(f"mkdir -p {STATIC_WALLPAPER_CONFIG_DIR}")
    log("static_wallpaper installed successfully.\n")


def uninstall_static_wallpaper(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    connection.run_command(f"rm -f {STATIC_WALLPAPER_SCRIPT_PATH}")
    connection.run_command(f"rm -rf {STATIC_WALLPAPER_CONFIG_DIR}")
    connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_JPG}")
    connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_PNG}")


def remove_static_wallpaper(connection, reload_menu=True):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_JPG}")
    connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_PNG}")
    connection.run_command("sync")

    if reload_menu:
        reload_mister_menu(connection)


def list_static_wallpapers(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    cmd = (
        f'find {STATIC_WALLPAPER_DIR} -maxdepth 1 -type f '
        r'\( -iname "*.png" -o -iname "*.jpg" -o -iname "*.jpeg" \) | sort'
    )
    output = connection.run_command(cmd)
    lines = [line.strip() for line in (output or "").splitlines() if line.strip()]

    wallpapers = []
    for path in lines:
        wallpapers.append(
            {
                "name": os.path.basename(path),
                "path": path,
            }
        )

    return wallpapers


def get_static_wallpaper_preview_bytes(connection, remote_path):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    if not remote_path:
        raise RuntimeError("No wallpaper path provided.")

    quoted_path = shlex.quote(remote_path)
    check = connection.run_command(f"test -f {quoted_path} && echo EXISTS")
    if "EXISTS" not in (check or ""):
        raise RuntimeError("Wallpaper file not found on MiSTer.")

    return _read_remote_bytes(connection, remote_path)


def apply_static_wallpaper(connection, wallpaper_path, reload_menu=True):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    if not wallpaper_path:
        raise RuntimeError("No wallpaper selected.")

    ext = os.path.splitext(wallpaper_path)[1].lower()
    quoted_src = shlex.quote(wallpaper_path)
    quoted_cfg = shlex.quote(STATIC_WALLPAPER_CONFIG_PATH)

    ensure_remote_scripts_dir(connection)

    exists_check = connection.run_command(f"test -f {quoted_src} && echo EXISTS")
    if "EXISTS" not in (exists_check or ""):
        raise RuntimeError("Selected wallpaper no longer exists on MiSTer.")

    if ext in {".jpg", ".jpeg"}:
        connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_PNG}")
        connection.run_command(f"cp {quoted_src} {STATIC_WALLPAPER_TARGET_JPG}")
        connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_PNG}")
    elif ext == ".png":
        connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_JPG}")
        connection.run_command(f"cp {quoted_src} {STATIC_WALLPAPER_TARGET_PNG}")
        connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_JPG}")
    else:
        raise RuntimeError("Unsupported wallpaper format. Use PNG, JPG, or JPEG.")

    connection.run_command(f"printf %s {quoted_src} > {quoted_cfg}")
    connection.run_command("sync")

    if reload_menu:
        reload_mister_menu(connection)


def open_scripts_folder_on_host(ip, username="root", password="1"):
    if not ip:
        raise ValueError("No MiSTer IP address is available.")

    if sys.platform.startswith("win"):
        subprocess.Popen(f'explorer "\\\\{ip}\\sdcard\\Scripts"')
        return

    if sys.platform.startswith("linux"):
        env = os.environ.copy()
        subprocess.run(
            ["gio", "mount", f"smb://{ip}/"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.Popen(
            ["gio", "open", f"smb://{ip}/sdcard/Scripts"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    if sys.platform == "darwin":
        username = username or "root"
        password = password or "1"
        home = os.path.expanduser("~")
        mount_point = os.path.join(home, "MiSTer_sdcard")
        subprocess.run(["mkdir", "-p", mount_point], capture_output=True)
        subprocess.run(
            ["mount_smbfs", f"//{username}:{password}@{ip}/sdcard", mount_point],
            capture_output=True
        )
        subprocess.Popen(["open", os.path.join(mount_point, "Scripts")])
        return

    raise RuntimeError(f"Unsupported platform: {sys.platform}")
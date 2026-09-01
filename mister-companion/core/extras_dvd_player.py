import os
import re

from core.downloader_backend import (
    ensure_database_source_local,
    ensure_database_source_online,
    inspect_named_databases_local,
    inspect_named_databases_online,
    check_named_database_local,
    check_named_database_online,
    remove_database_source_local,
    remove_database_source_online,
    restore_local,
    restore_online,
    run_named_database_local,
    run_named_database_online,
    uninstall_named_database_local,
    uninstall_named_database_online,
)
from core.extras_common import (
    _copy_local_file_to_sd,
    _ensure_local_dir,
    _ensure_remote_dir,
    _normalize_ini_text_for_append,
    _path_exists,
    _path_exists_local,
    _read_local_text,
    _read_remote_text,
    _write_local_text,
    _write_remote_text,
)

DVD_PLAYER_DB_ID = "MultiDatabases/dvd-player"
DVD_PLAYER_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/dvd-player/db.json"
REMOTE_LIB_DIR = "/media/fat/DVD/lib"
REMOTE_LIBDVDCSS_PATH = "/media/fat/DVD/lib/libdvdcss.so.2"
REMOTE_INI_PATH = "/media/fat/MiSTer.ini"
INI_SECTION = "DVD-Player"
INI_MAIN = "MiSTer_DVD"
INI_BLOCK = f"[{INI_SECTION}]\nmain={INI_MAIN}\n"


def _ini_entry_present(text: str) -> bool:
    normalized = (text or "").replace("\r\n", "\n")
    pattern = re.compile(
        rf"(?ms)^\[{re.escape(INI_SECTION)}\]\s*$.*?^main\s*=\s*{re.escape(INI_MAIN)}\s*$"
    )
    return bool(pattern.search(normalized))


def _ensure_ini_entry_text(text: str) -> tuple[str, bool]:
    normalized = (text or "").replace("\r\n", "\n")
    if _ini_entry_present(normalized):
        return normalized, False

    section_pattern = re.compile(
        rf"(?ms)^\[{re.escape(INI_SECTION)}\]\s*$\n(?P<body>.*?)(?=^\[|\Z)"
    )
    match = section_pattern.search(normalized)
    if match:
        body = match.group("body")
        main_pattern = re.compile(r"(?m)^main\s*=.*$")
        if main_pattern.search(body):
            new_body = main_pattern.sub(f"main={INI_MAIN}", body, count=1)
        else:
            new_body = f"main={INI_MAIN}\n" + body
        updated = normalized[:match.start("body")] + new_body + normalized[match.end("body"):]
        return updated, True

    updated = _normalize_ini_text_for_append(normalized.rstrip("\n")) + INI_BLOCK
    return updated, True


def _remove_ini_entry_text(text: str) -> tuple[str, bool]:
    normalized = (text or "").replace("\r\n", "\n")
    if not normalized:
        return normalized, False

    section_pattern = re.compile(
        rf"(?ms)^\[{re.escape(INI_SECTION)}\]\s*$\n(?P<body>.*?)(?=^\[|\Z)"
    )
    match = section_pattern.search(normalized)
    if not match:
        return normalized, False

    body = match.group("body")
    target_main = re.compile(rf"(?m)^main\s*=\s*{re.escape(INI_MAIN)}\s*\n?")
    if not target_main.search(body):
        return normalized, False

    new_body = target_main.sub("", body, count=1)
    if not new_body.strip():
        updated = normalized[:match.start()] + normalized[match.end():]
    else:
        updated = normalized[:match.start("body")] + new_body + normalized[match.end("body"):]

    updated = re.sub(r"\n{3,}", "\n\n", updated).strip("\n")
    if updated:
        updated += "\n"
    return updated, True


def _ensure_ini_entry(connection) -> bool:
    current = _read_remote_text(connection, REMOTE_INI_PATH)
    updated, changed = _ensure_ini_entry_text(current)
    if changed:
        _write_remote_text(connection, REMOTE_INI_PATH, updated)
    return changed


def _ensure_ini_entry_local(sd_root: str) -> bool:
    current = _read_local_text(sd_root, REMOTE_INI_PATH)
    updated, changed = _ensure_ini_entry_text(current)
    if changed:
        _write_local_text(sd_root, REMOTE_INI_PATH, updated)
    return changed


def _remove_ini_entry(connection) -> bool:
    current = _read_remote_text(connection, REMOTE_INI_PATH)
    updated, changed = _remove_ini_entry_text(current)
    if changed:
        _write_remote_text(connection, REMOTE_INI_PATH, updated)
    return changed


def _remove_ini_entry_local(sd_root: str) -> bool:
    current = _read_local_text(sd_root, REMOTE_INI_PATH)
    updated, changed = _remove_ini_entry_text(current)
    if changed:
        _write_local_text(sd_root, REMOTE_INI_PATH, updated)
    return changed


def _status(state, *, css_present: bool, ini_present: bool, check_latest=False):
    installed = bool(state.get("installed"))
    update_available = bool(state.get("update_available")) if check_latest else False
    status = {
        "installed": installed,
        "update_available": update_available,
        "status_text": "Update available" if update_available else "Installed" if installed else "Not installed",
        "install_label": "Update" if update_available else "Installed" if installed else "Install",
        "install_enabled": update_available or not installed,
        "uninstall_enabled": installed,
        "libdvdcss_present": bool(css_present),
        "upload_enabled": bool(installed and not css_present),
    }
    if installed and not ini_present:
        status.update({
            "status_text": "⚠ MiSTer.ini entry missing",
            "install_label": "Add INI Entry",
            "install_enabled": True,
            "update_available": False,
            "repair_action": True,
        })
    return status


def get_dvd_player_status(connection, check_latest=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    states = inspect_named_databases_online(connection, [DVD_PLAYER_DB_ID], log=None)
    state = states.get(DVD_PLAYER_DB_ID) or {}
    installed = bool(state.get("installed"))
    if check_latest and installed:
        state = dict(state)
        state["update_available"] = bool(check_named_database_online(connection, DVD_PLAYER_DB_ID))
    return _status(
        state,
        css_present=installed and _path_exists(connection, REMOTE_LIBDVDCSS_PATH),
        ini_present=_ini_entry_present(_read_remote_text(connection, REMOTE_INI_PATH)),
        check_latest=check_latest,
    )


def get_dvd_player_status_local(sd_root, check_latest=False):
    states = inspect_named_databases_local(sd_root, [DVD_PLAYER_DB_ID], log=None)
    state = states.get(DVD_PLAYER_DB_ID) or {}
    installed = bool(state.get("installed"))
    if check_latest and installed:
        state = dict(state)
        state["update_available"] = bool(check_named_database_local(sd_root, DVD_PLAYER_DB_ID))
    return _status(
        state,
        css_present=installed and _path_exists_local(sd_root, REMOTE_LIBDVDCSS_PATH),
        ini_present=_ini_entry_present(_read_local_text(sd_root, REMOTE_INI_PATH)),
        check_latest=check_latest,
    )


def install_or_update_dvd_player(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    states = inspect_named_databases_online(connection, [DVD_PLAYER_DB_ID], log=None)
    installed = bool((states.get(DVD_PLAYER_DB_ID) or {}).get("installed"))
    if installed and not _ini_entry_present(_read_remote_text(connection, REMOTE_INI_PATH)):
        if _ensure_ini_entry(connection):
            log("Added [DVD-Player] main=MiSTer_DVD to MiSTer.ini.\n")
        return

    original = ensure_database_source_online(connection, DVD_PLAYER_DB_ID, DVD_PLAYER_DB_URL)
    try:
        run_named_database_online(connection, DVD_PLAYER_DB_ID, log=log)
        if _ensure_ini_entry(connection):
            log("Added [DVD-Player] main=MiSTer_DVD to MiSTer.ini.\n")
    except Exception:
        restore_online(connection, original)
        raise


def install_or_update_dvd_player_local(sd_root, log):
    states = inspect_named_databases_local(sd_root, [DVD_PLAYER_DB_ID], log=None)
    installed = bool((states.get(DVD_PLAYER_DB_ID) or {}).get("installed"))
    if installed and not _ini_entry_present(_read_local_text(sd_root, REMOTE_INI_PATH)):
        if _ensure_ini_entry_local(sd_root):
            log("Added [DVD-Player] main=MiSTer_DVD to MiSTer.ini.\n")
        return

    original = ensure_database_source_local(sd_root, DVD_PLAYER_DB_ID, DVD_PLAYER_DB_URL)
    try:
        run_named_database_local(sd_root, DVD_PLAYER_DB_ID, log=log)
        if _ensure_ini_entry_local(sd_root):
            log("Added [DVD-Player] main=MiSTer_DVD to MiSTer.ini.\n")
    except Exception:
        restore_local(sd_root, original)
        raise


def upload_libdvdcss(connection, local_path: str, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    if not os.path.isfile(local_path):
        raise RuntimeError("Selected libdvdcss.so.2 file does not exist.")

    local_name = os.path.basename(local_path)
    if local_name != "libdvdcss.so.2":
        log(f"Warning: selected file name is {local_name}, expected libdvdcss.so.2\n")

    states = inspect_named_databases_online(connection, [DVD_PLAYER_DB_ID], log=None)
    if not bool((states.get(DVD_PLAYER_DB_ID) or {}).get("installed")):
        raise RuntimeError("DVD-Player is not installed.")

    _ensure_remote_dir(connection, REMOTE_LIB_DIR)
    file_size = os.path.getsize(local_path)
    log(f"Uploading library to {REMOTE_LIBDVDCSS_PATH}\n")
    log(f"File size: {file_size} bytes\n")

    last_percent = {"value": -1}

    def progress_callback(transferred, total):
        if total <= 0:
            return
        percent = int((transferred / total) * 100)
        if percent != last_percent["value"]:
            last_percent["value"] = percent
            log(f"[PROGRESS] {percent}%")

    sftp = connection.client.open_sftp()
    try:
        sftp.put(local_path, REMOTE_LIBDVDCSS_PATH, callback=progress_callback)
    finally:
        sftp.close()

    log("Upload completed.\n")
    return {"libdvdcss_present": True}


def upload_libdvdcss_local(sd_root: str, local_path: str, log):
    if not os.path.isfile(local_path):
        raise RuntimeError("Selected libdvdcss.so.2 file does not exist.")

    local_name = os.path.basename(local_path)
    if local_name != "libdvdcss.so.2":
        log(f"Warning: selected file name is {local_name}, expected libdvdcss.so.2\n")

    states = inspect_named_databases_local(sd_root, [DVD_PLAYER_DB_ID], log=None)
    if not bool((states.get(DVD_PLAYER_DB_ID) or {}).get("installed")):
        raise RuntimeError("DVD-Player is not installed.")

    _ensure_local_dir(sd_root, REMOTE_LIB_DIR)
    file_size = os.path.getsize(local_path)
    log(f"Copying library to {REMOTE_LIBDVDCSS_PATH}\n")
    log(f"File size: {file_size} bytes\n")
    _copy_local_file_to_sd(sd_root, local_path, REMOTE_LIBDVDCSS_PATH)
    log("Copy completed.\n")
    return {"libdvdcss_present": True}


def uninstall_dvd_player(connection, log, force=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    original = ensure_database_source_online(connection, DVD_PLAYER_DB_ID, DVD_PLAYER_DB_URL)
    try:
        native = uninstall_named_database_online(connection, DVD_PLAYER_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(connection, DVD_PLAYER_DB_ID, DVD_PLAYER_DB_URL, filter_value="!all")
            run_named_database_online(connection, DVD_PLAYER_DB_ID, log=log)
            remove_database_source_online(connection, DVD_PLAYER_DB_ID)
        if _remove_ini_entry(connection):
            log("Removed [DVD-Player] main=MiSTer_DVD from MiSTer.ini.\n")
    except Exception:
        restore_online(connection, original)
        raise
    if _path_exists(connection, REMOTE_LIBDVDCSS_PATH):
        log(f"Preserved user library: {REMOTE_LIBDVDCSS_PATH}\n")
    return {"uninstalled": True}


def uninstall_dvd_player_local(sd_root, log, force=False):
    original = ensure_database_source_local(sd_root, DVD_PLAYER_DB_ID, DVD_PLAYER_DB_URL)
    try:
        native = uninstall_named_database_local(sd_root, DVD_PLAYER_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(sd_root, DVD_PLAYER_DB_ID, DVD_PLAYER_DB_URL, filter_value="!all")
            run_named_database_local(sd_root, DVD_PLAYER_DB_ID, log=log)
            remove_database_source_local(sd_root, DVD_PLAYER_DB_ID)
        if _remove_ini_entry_local(sd_root):
            log("Removed [DVD-Player] main=MiSTer_DVD from MiSTer.ini.\n")
    except Exception:
        restore_local(sd_root, original)
        raise
    if _path_exists_local(sd_root, REMOTE_LIBDVDCSS_PATH):
        log(f"Preserved user library: {REMOTE_LIBDVDCSS_PATH}\n")
    return {"uninstalled": True}

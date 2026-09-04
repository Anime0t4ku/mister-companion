import re

from core.downloader_backend import (
    database_registered_local,
    database_registered_online,
    ensure_database_source_local,
    ensure_database_source_online,
    inspect_named_databases_local,
    inspect_named_databases_online,
    remove_database_source_local,
    remove_database_source_online,
    restore_local,
    restore_online,
    run_named_database_local,
    run_named_database_online,
    check_named_database_local,
    check_named_database_online,
    uninstall_named_database_local,
    uninstall_named_database_online,
)
from core.extras_common import (
    _normalize_ini_text_for_append,
    _read_local_text,
    _read_remote_text,
    _write_local_text,
    _write_remote_text,
)

MISTER_DVD_DB_ID = "MultiDatabases/mister-dvd"
MISTER_DVD_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/mister-dvd/db.json"
REMOTE_INI_PATH = "/media/fat/MiSTer.ini"
INI_SECTION = "DVD"
INI_MAIN = "MiSTer_DVDcss"
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
    # If Companion's managed main line was the only meaningful content in [DVD],
    # remove the empty section too. Otherwise preserve any user-owned settings.
    if not new_body.strip():
        start = match.start()
        end = match.end()
        updated = normalized[:start] + normalized[end:]
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


def _status(state: dict, *, ini_present: bool, check_latest: bool = False, update_available: bool = False) -> dict:
    installed = bool(state.get("installed"))
    available = bool(update_available) if check_latest else False
    status = {
        "installed": installed,
        "update_available": available,
        "state": "update_available" if available else "installed" if installed else "not_installed",
        "status_text": "Update available" if available else "Installed" if installed else "Not installed",
        "install_label": "Update" if available else "Installed" if installed else "Install",
        "install_enabled": available or not installed,
        "uninstall_enabled": installed,
    }
    if installed and not ini_present:
        status.update({
            "state": "installed",
            "status_text": "⚠ MiSTer.ini entry missing",
            "install_label": "Add INI Entry",
            "install_enabled": True,
            "update_available": False,
            "repair_action": True,
        })
    return status


def get_mister_dvd_status(connection, check_latest=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    state = {"installed": database_registered_online(connection, MISTER_DVD_DB_ID)}
    update = bool(check_latest and state["installed"] and check_named_database_online(connection, MISTER_DVD_DB_ID))
    return _status(
        state,
        ini_present=_ini_entry_present(_read_remote_text(connection, REMOTE_INI_PATH)),
        check_latest=check_latest,
        update_available=update,
    )


def get_mister_dvd_status_local(sd_root, check_latest=False):
    state = {"installed": database_registered_local(sd_root, MISTER_DVD_DB_ID)}
    update = bool(check_latest and state["installed"] and check_named_database_local(sd_root, MISTER_DVD_DB_ID))
    return _status(
        state,
        ini_present=_ini_entry_present(_read_local_text(sd_root, REMOTE_INI_PATH)),
        check_latest=check_latest,
        update_available=update,
    )


def install_or_update_mister_dvd(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    states = inspect_named_databases_online(connection, [MISTER_DVD_DB_ID], log=None)
    installed = bool((states.get(MISTER_DVD_DB_ID) or {}).get("installed"))
    if installed and not _ini_entry_present(_read_remote_text(connection, REMOTE_INI_PATH)):
        if _ensure_ini_entry(connection):
            log("Added [DVD] main=MiSTer_DVDcss to MiSTer.ini.\n")
        return

    original = ensure_database_source_online(connection, MISTER_DVD_DB_ID, MISTER_DVD_DB_URL)
    try:
        run_named_database_online(connection, MISTER_DVD_DB_ID, log=log)
        if _ensure_ini_entry(connection):
            log("Added [DVD] main=MiSTer_DVDcss to MiSTer.ini.\n")
    except Exception:
        restore_online(connection, original)
        raise


def install_or_update_mister_dvd_local(sd_root, log):
    states = inspect_named_databases_local(sd_root, [MISTER_DVD_DB_ID], log=None)
    installed = bool((states.get(MISTER_DVD_DB_ID) or {}).get("installed"))
    if installed and not _ini_entry_present(_read_local_text(sd_root, REMOTE_INI_PATH)):
        if _ensure_ini_entry_local(sd_root):
            log("Added [DVD] main=MiSTer_DVDcss to MiSTer.ini.\n")
        return

    original = ensure_database_source_local(sd_root, MISTER_DVD_DB_ID, MISTER_DVD_DB_URL)
    try:
        run_named_database_local(sd_root, MISTER_DVD_DB_ID, log=log)
        if _ensure_ini_entry_local(sd_root):
            log("Added [DVD] main=MiSTer_DVDcss to MiSTer.ini.\n")
    except Exception:
        restore_local(sd_root, original)
        raise


def uninstall_mister_dvd(connection, log, force=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    original = ensure_database_source_online(connection, MISTER_DVD_DB_ID, MISTER_DVD_DB_URL)
    try:
        native = uninstall_named_database_online(connection, MISTER_DVD_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(connection, MISTER_DVD_DB_ID, MISTER_DVD_DB_URL, filter_value="!all")
            run_named_database_online(connection, MISTER_DVD_DB_ID, log=log)
            remove_database_source_online(connection, MISTER_DVD_DB_ID)
        if _remove_ini_entry(connection):
            log("Removed [DVD] main=MiSTer_DVDcss from MiSTer.ini.\n")
    except Exception:
        restore_online(connection, original)
        raise
    return {"uninstalled": True}


def uninstall_mister_dvd_local(sd_root, log, force=False):
    original = ensure_database_source_local(sd_root, MISTER_DVD_DB_ID, MISTER_DVD_DB_URL)
    try:
        native = uninstall_named_database_local(sd_root, MISTER_DVD_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(sd_root, MISTER_DVD_DB_ID, MISTER_DVD_DB_URL, filter_value="!all")
            run_named_database_local(sd_root, MISTER_DVD_DB_ID, log=log)
            remove_database_source_local(sd_root, MISTER_DVD_DB_ID)
        if _remove_ini_entry_local(sd_root):
            log("Removed [DVD] main=MiSTer_DVDcss from MiSTer.ini.\n")
    except Exception:
        restore_local(sd_root, original)
        raise
    return {"uninstalled": True}

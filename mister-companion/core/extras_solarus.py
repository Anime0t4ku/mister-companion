from core.downloader_backend import (
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
    uninstall_named_database_local,
    uninstall_named_database_online,
)

SOLARUS_DB_ID = "MultiDatabases/solarus"
SOLARUS_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/solarus/db.json"


def _status(state, check_latest=False):
    installed = bool(state.get("installed"))
    update_available = bool(state.get("update_available")) if check_latest else False
    return {
        "installed": installed,
        "update_available": update_available,
        "status_text": "Update available" if update_available else "Installed" if installed else "Not installed",
        "install_label": "Update" if update_available else "Installed" if installed else "Install",
        "install_enabled": update_available or not installed,
        "uninstall_enabled": installed,
    }


def get_solarus_status(connection, check_latest=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    states = inspect_named_databases_online(connection, [SOLARUS_DB_ID], log=None)
    return _status(states.get(SOLARUS_DB_ID) or {}, check_latest=check_latest)


def get_solarus_status_local(sd_root, check_latest=False):
    states = inspect_named_databases_local(sd_root, [SOLARUS_DB_ID], log=None)
    return _status(states.get(SOLARUS_DB_ID) or {}, check_latest=check_latest)


def install_or_update_solarus(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    original = ensure_database_source_online(connection, SOLARUS_DB_ID, SOLARUS_DB_URL)
    try:
        run_named_database_online(connection, SOLARUS_DB_ID, log=log)
    except Exception:
        restore_online(connection, original)
        raise


def install_or_update_solarus_local(sd_root, log):
    original = ensure_database_source_local(sd_root, SOLARUS_DB_ID, SOLARUS_DB_URL)
    try:
        run_named_database_local(sd_root, SOLARUS_DB_ID, log=log)
    except Exception:
        restore_local(sd_root, original)
        raise


def uninstall_solarus(connection, log, force=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    original = ensure_database_source_online(connection, SOLARUS_DB_ID, SOLARUS_DB_URL)
    try:
        native = uninstall_named_database_online(connection, SOLARUS_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(connection, SOLARUS_DB_ID, SOLARUS_DB_URL, filter_value="!all")
            run_named_database_online(connection, SOLARUS_DB_ID, log=log)
            remove_database_source_online(connection, SOLARUS_DB_ID)
    except Exception:
        restore_online(connection, original)
        raise
    return {"uninstalled": True}


def uninstall_solarus_local(sd_root, log, force=False):
    original = ensure_database_source_local(sd_root, SOLARUS_DB_ID, SOLARUS_DB_URL)
    try:
        native = uninstall_named_database_local(sd_root, SOLARUS_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(sd_root, SOLARUS_DB_ID, SOLARUS_DB_URL, filter_value="!all")
            run_named_database_local(sd_root, SOLARUS_DB_ID, log=log)
            remove_database_source_local(sd_root, SOLARUS_DB_ID)
    except Exception:
        restore_local(sd_root, original)
        raise
    return {"uninstalled": True}

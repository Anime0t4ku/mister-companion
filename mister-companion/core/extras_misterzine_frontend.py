from core.downloader_backend import (
    database_registered_local,
    database_registered_online,
    check_named_database_local,
    check_named_database_online,
    ensure_database_source_local,
    ensure_database_source_online,
    remove_database_source_local,
    remove_database_source_online,
    restore_local,
    restore_online,
    run_named_database_local,
    run_named_database_online,
    uninstall_named_database_local,
    uninstall_named_database_online,
)

MISTERZINE_DB_ID = "misterzine"
MISTERZINE_DB_URL = "https://github.com/matijaerceg/misterzine-on-device/releases/latest/download/misterzine.json.zip"


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


def get_misterzine_frontend_status(connection, check_latest=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    installed = database_registered_online(connection, MISTERZINE_DB_ID)
    state = {
        "installed": installed,
        "update_available": bool(
            check_latest and installed and check_named_database_online(connection, MISTERZINE_DB_ID)
        ),
    }
    return _status(state, check_latest=check_latest)


def get_misterzine_frontend_status_local(sd_root, check_latest=False):
    installed = database_registered_local(sd_root, MISTERZINE_DB_ID)
    state = {
        "installed": installed,
        "update_available": bool(
            check_latest and installed and check_named_database_local(sd_root, MISTERZINE_DB_ID)
        ),
    }
    return _status(state, check_latest=check_latest)


def install_or_update_misterzine_frontend(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    original = ensure_database_source_online(connection, MISTERZINE_DB_ID, MISTERZINE_DB_URL)
    try:
        run_named_database_online(connection, MISTERZINE_DB_ID, log=log)
    except Exception:
        restore_online(connection, original)
        raise


def install_or_update_misterzine_frontend_local(sd_root, log):
    original = ensure_database_source_local(sd_root, MISTERZINE_DB_ID, MISTERZINE_DB_URL)
    try:
        run_named_database_local(sd_root, MISTERZINE_DB_ID, log=log)
    except Exception:
        restore_local(sd_root, original)
        raise


def uninstall_misterzine_frontend(connection, log, force=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    original = ensure_database_source_online(connection, MISTERZINE_DB_ID, MISTERZINE_DB_URL)
    try:
        native = uninstall_named_database_online(connection, MISTERZINE_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(
                connection, MISTERZINE_DB_ID, MISTERZINE_DB_URL, filter_value="!all"
            )
            run_named_database_online(connection, MISTERZINE_DB_ID, log=log)
            remove_database_source_online(connection, MISTERZINE_DB_ID)
    except Exception:
        restore_online(connection, original)
        raise
    return {"uninstalled": True}


def uninstall_misterzine_frontend_local(sd_root, log, force=False):
    original = ensure_database_source_local(sd_root, MISTERZINE_DB_ID, MISTERZINE_DB_URL)
    try:
        native = uninstall_named_database_local(sd_root, MISTERZINE_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(
                sd_root, MISTERZINE_DB_ID, MISTERZINE_DB_URL, filter_value="!all"
            )
            run_named_database_local(sd_root, MISTERZINE_DB_ID, log=log)
            remove_database_source_local(sd_root, MISTERZINE_DB_ID)
    except Exception:
        restore_local(sd_root, original)
        raise
    return {"uninstalled": True}

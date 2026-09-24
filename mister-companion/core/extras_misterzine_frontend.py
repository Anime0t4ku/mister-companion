from core.downloader_backend import (
    _run_remote_streaming_result,
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
from core.extras_common import (
    _path_exists,
    _path_exists_local,
    _read_local_text,
    _read_remote_text,
    _write_local_text,
)

MISTERZINE_DB_ID = "misterzine"
MISTERZINE_DB_URL = "https://github.com/matijaerceg/misterzine-on-device/releases/latest/download/misterzine.json.zip"

# Downloader installs the files. The main-menu entry and the startup helper
# that opens it are a separate one-time setup, the same as running
# Scripts/MisterZine-Setup.sh on the MiSTer.
MISTERZINE_BINARY = "/media/fat/misterzine/misterzine"
MISTERZINE_MGL_PATH = "/media/fat/MisterZine.mgl"
MISTERZINE_MGL_TEXT = "<mistergamedescription>\n\t<rbf>menu</rbf>\n\t<setname>misterzine</setname>\n</mistergamedescription>\n"
MISTERZINE_STARTUP_PATH = "/media/fat/linux/user-startup.sh"
MISTERZINE_STARTUP_MARK = "# misterzine"
MISTERZINE_STARTUP_LINE = "[[ -e /media/fat/misterzine/misterzine ]] && /media/fat/misterzine/misterzine launcher start"
MISTERZINE_SETUP_NOTE = "MisterZine is installed. Press Set Up Menu Entry, or run MisterZine-Setup from Scripts on the MiSTer once.\n"


def _menu_entry_set_up(startup_text: str) -> bool:
    for line in startup_text.replace("\r\n", "\n").split("\n"):
        code = line.split("#", 1)[0].strip()
        if code == MISTERZINE_STARTUP_LINE:
            return True
    return False


def _status(state, check_latest=False):
    installed = bool(state.get("installed"))
    files_present = bool(state.get("files_present"))
    set_up = bool(state.get("set_up"))
    update_available = bool(state.get("update_available")) if check_latest else False
    status = {
        "installed": installed,
        "update_available": update_available,
        "status_text": "Update available" if update_available else "Installed" if installed else "Not installed",
        "install_label": "Update" if update_available else "Installed" if installed else "Install",
        "install_enabled": update_available or not installed,
        "uninstall_enabled": installed,
    }
    if installed and files_present and not set_up:
        status.update({
            "status_text": "⚠ Menu entry not set up",
            "install_label": "Set Up Menu Entry",
            "install_enabled": True,
            "update_available": False,
            "repair_action": True,
        })
    return status


def get_misterzine_frontend_status(connection, check_latest=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    installed = database_registered_online(connection, MISTERZINE_DB_ID)
    state = {
        "installed": installed,
        "files_present": installed and _path_exists(connection, MISTERZINE_BINARY),
        "set_up": installed and _menu_entry_set_up(_read_remote_text(connection, MISTERZINE_STARTUP_PATH)),
        "update_available": bool(
            check_latest and installed and check_named_database_online(connection, MISTERZINE_DB_ID)
        ),
    }
    return _status(state, check_latest=check_latest)


def get_misterzine_frontend_status_local(sd_root, check_latest=False):
    installed = database_registered_local(sd_root, MISTERZINE_DB_ID)
    state = {
        "installed": installed,
        "files_present": installed and _path_exists_local(sd_root, MISTERZINE_BINARY),
        "set_up": installed and _menu_entry_set_up(_read_local_text(sd_root, MISTERZINE_STARTUP_PATH)),
        "update_available": bool(
            check_latest and installed and check_named_database_local(sd_root, MISTERZINE_DB_ID)
        ),
    }
    return _status(state, check_latest=check_latest)


def set_up_misterzine_menu_entry(connection, log):
    """Create the menu entry and startup helper on a connected MiSTer.

    MisterZine's own launcher does the work, so the result matches
    MisterZine-Setup and takes effect without a reboot.
    """
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    if not _path_exists(connection, MISTERZINE_BINARY):
        raise RuntimeError("MisterZine files are not installed. Install MisterZine first.")
    output, code = _run_remote_streaming_result(connection, f"{MISTERZINE_BINARY} launcher enable 2>&1", log=log)
    if code:
        raise RuntimeError(f"MisterZine setup failed (exit {code}).\n{output}")
    log("MisterZine menu entry set up. Choose MisterZine in the MiSTer main menu.\n")


def set_up_misterzine_menu_entry_local(sd_root, log):
    """Write the menu entry and startup line on an SD card; the helper starts at boot."""
    if not _path_exists_local(sd_root, MISTERZINE_BINARY):
        raise RuntimeError("MisterZine files are not installed. Install MisterZine first.")
    if not _path_exists_local(sd_root, MISTERZINE_MGL_PATH):
        _write_local_text(sd_root, MISTERZINE_MGL_PATH, MISTERZINE_MGL_TEXT)
    startup = _read_local_text(sd_root, MISTERZINE_STARTUP_PATH).replace("\r\n", "\n")
    if not _menu_entry_set_up(startup):
        if not startup:
            startup = "#!/bin/sh\n"
        if not startup.endswith("\n"):
            startup += "\n"
        startup += "\n" + MISTERZINE_STARTUP_MARK + "\n" + MISTERZINE_STARTUP_LINE + "\n"
        _write_local_text(sd_root, MISTERZINE_STARTUP_PATH, startup)
    log("MisterZine menu entry set up. Boot the MiSTer and choose MisterZine in the main menu.\n")


def install_or_update_misterzine_frontend(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    if get_misterzine_frontend_status(connection).get("repair_action"):
        set_up_misterzine_menu_entry(connection, log)
        return
    original = ensure_database_source_online(connection, MISTERZINE_DB_ID, MISTERZINE_DB_URL)
    try:
        run_named_database_online(connection, MISTERZINE_DB_ID, log=log)
    except Exception:
        restore_online(connection, original)
        raise
    if not _menu_entry_set_up(_read_remote_text(connection, MISTERZINE_STARTUP_PATH)):
        log(MISTERZINE_SETUP_NOTE)


def install_or_update_misterzine_frontend_local(sd_root, log):
    if get_misterzine_frontend_status_local(sd_root).get("repair_action"):
        set_up_misterzine_menu_entry_local(sd_root, log)
        return
    original = ensure_database_source_local(sd_root, MISTERZINE_DB_ID, MISTERZINE_DB_URL)
    try:
        run_named_database_local(sd_root, MISTERZINE_DB_ID, log=log)
    except Exception:
        restore_local(sd_root, original)
        raise
    if not _menu_entry_set_up(_read_local_text(sd_root, MISTERZINE_STARTUP_PATH)):
        log(MISTERZINE_SETUP_NOTE)


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

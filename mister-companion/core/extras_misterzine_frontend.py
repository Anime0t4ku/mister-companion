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
    _quote,
    _read_local_text,
    _read_remote_text,
    _remove_local_path,
    _remove_startup_line,
    _write_local_bytes,
)

MISTERZINE_DB_ID = "misterzine"
MISTERZINE_DB_URL = "https://github.com/matijaerceg/misterzine-on-device/releases/latest/download/misterzine.json.zip"
# An empty per-database filter, as in MisterZine's own downloader_misterzine.ini:
# the app's files carry no tags, so a global filter would otherwise skip them all.
MISTERZINE_DB_FILTER = ""

# Downloader installs the files. The main-menu entry and the startup helper
# that opens it are a separate one-time setup, the same as running
# Scripts/MisterZine-Setup.sh on the MiSTer.
MISTERZINE_BINARY = "/media/fat/misterzine/misterzine"
# MisterZine writes its main-menu entry itself, under the name its release
# uses: "MisterZine Arcade.mgl" from the rename on, MisterZine.mgl before it.
MISTERZINE_MGL_PATHS = (
    "/media/fat/MisterZine Arcade.mgl",
    "/media/fat/MisterZine.mgl",
    "/media/fat/misterzine.mgl",
)
MISTERZINE_STARTUP_PATH = "/media/fat/linux/user-startup.sh"
MISTERZINE_STARTUP_MARK = "# misterzine"
MISTERZINE_STARTUP_LINE = "[[ -e /media/fat/misterzine/misterzine ]] && /media/fat/misterzine/misterzine launcher start"
# Stops a startup helper whose binary is already gone; Linux keeps it running.
MISTERZINE_STOP_HELPER = (
    "for p in /proc/[0-9]*; do tr '\\0' ' ' < $p/cmdline 2>/dev/null"
    " | grep -q '^/media/fat/misterzine/misterzine launcher watch' && kill ${p#/proc/}; done"
)
MISTERZINE_SETUP_NOTE ="MisterZine is installed. Press Set Up Menu Entry, or run MisterZine-Setup from Scripts on the MiSTer once.\n"


def _is_startup_hook(line: str) -> bool:
    return line.split("#", 1)[0].strip() == MISTERZINE_STARTUP_LINE


def _menu_entry_set_up(startup_text: str) -> bool:
    return any(_is_startup_hook(line) for line in startup_text.replace("\r\n", "\n").split("\n"))


def _write_card_text(sd_root, remote_path, text):
    # The MiSTer reads these files with Linux tools, so keep LF line endings
    # when Companion runs on Windows: a CRLF user-startup.sh fails at #!/bin/sh.
    _write_local_bytes(sd_root, remote_path, text.encode("utf-8"))


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
    """Write the startup line on an SD card.

    The helper it starts at boot writes the menu entry itself, under the
    name the installed MisterZine release uses.
    """
    if not _path_exists_local(sd_root, MISTERZINE_BINARY):
        raise RuntimeError("MisterZine files are not installed. Install MisterZine first.")
    startup = _read_local_text(sd_root, MISTERZINE_STARTUP_PATH).replace("\r\n", "\n")
    if not _menu_entry_set_up(startup):
        if not startup:
            startup = "#!/bin/sh\n"
        if not startup.endswith("\n"):
            startup += "\n"
        startup += "\n" + MISTERZINE_STARTUP_MARK + "\n" + MISTERZINE_STARTUP_LINE + "\n"
        _write_card_text(sd_root, MISTERZINE_STARTUP_PATH, startup)
    log("MisterZine menu entry set up. Boot the MiSTer and choose MisterZine in the main menu.\n")


def _remove_misterzine_menu_entry(connection, log) -> bool:
    """Remove the menu entry and stop the startup helper before the files go.

    Returns True when MisterZine's launcher did it, so it can be re-enabled
    if the uninstall fails.
    """
    launcher = _path_exists(connection, MISTERZINE_BINARY)
    if launcher:
        output, code = _run_remote_streaming_result(connection, f"{MISTERZINE_BINARY} launcher disable 2>&1", log=log)
        if code:
            raise RuntimeError(f"Could not remove the MisterZine menu entry (exit {code}).\n{output}")
    else:
        connection.run_command(MISTERZINE_STOP_HELPER)
        _remove_startup_line(connection, MISTERZINE_STARTUP_PATH, MISTERZINE_STARTUP_MARK)
        _remove_startup_line(connection, MISTERZINE_STARTUP_PATH, MISTERZINE_STARTUP_LINE)
    # A launcher from before the rename removes only the name it writes.
    connection.run_command("rm -f " + " ".join(_quote(path) for path in MISTERZINE_MGL_PATHS))
    return launcher


def _restore_misterzine_menu_entry(connection, log):
    try:
        if _path_exists(connection, MISTERZINE_BINARY):
            output, code = _run_remote_streaming_result(connection, f"{MISTERZINE_BINARY} launcher enable 2>&1", log=log)
            if not code:
                return
    except Exception:
        pass
    log("Could not put the MisterZine menu entry back. Press Set Up Menu Entry, or run MisterZine-Setup from Scripts.\n")


def _remove_misterzine_menu_entry_local(sd_root):
    startup = _read_local_text(sd_root, MISTERZINE_STARTUP_PATH).replace("\r\n", "\n")
    kept = [
        line for line in startup.split("\n")
        if line.strip() != MISTERZINE_STARTUP_MARK and not _is_startup_hook(line)
    ]
    if startup and "\n".join(kept) != startup:
        _write_card_text(sd_root, MISTERZINE_STARTUP_PATH, "\n".join(kept))
    for path in MISTERZINE_MGL_PATHS:
        _remove_local_path(sd_root, path)


def install_or_update_misterzine_frontend(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    if get_misterzine_frontend_status(connection).get("repair_action"):
        set_up_misterzine_menu_entry(connection, log)
        return
    original = ensure_database_source_online(
        connection, MISTERZINE_DB_ID, MISTERZINE_DB_URL, filter_value=MISTERZINE_DB_FILTER
    )
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
    original = ensure_database_source_local(
        sd_root, MISTERZINE_DB_ID, MISTERZINE_DB_URL, filter_value=MISTERZINE_DB_FILTER
    )
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
    launcher_disabled = False
    try:
        # Setup wrote the menu entry and startup line, so Downloader does not track them.
        launcher_disabled = _remove_misterzine_menu_entry(connection, log)
        native = uninstall_named_database_online(connection, MISTERZINE_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(
                connection, MISTERZINE_DB_ID, MISTERZINE_DB_URL, filter_value="!all"
            )
            run_named_database_online(connection, MISTERZINE_DB_ID, log=log)
            remove_database_source_online(connection, MISTERZINE_DB_ID)
    except Exception:
        restore_online(connection, original)
        if launcher_disabled:
            _restore_misterzine_menu_entry(connection, log)
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
    _remove_misterzine_menu_entry_local(sd_root)
    return {"uninstalled": True}

from core.extras_common import _path_exists, _path_exists_local, _quote, _remove_local_path
from core.downloader_backend import (
    database_registered_local,
    database_registered_online,
    ensure_database_source_local,
    ensure_database_source_online,
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

PHYSICAL_DISC_DB_ID = "MultiDatabases/physical-disc"
PHYSICAL_DISC_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/physical-disc/db.json"
PHYSICAL_DISC_BINARY = "/media/fat/MiSTer_Physical-CD"
PHYSICAL_DISC_FILES = (
    PHYSICAL_DISC_BINARY,
    "/media/fat/_Physical Disc Cores/CDi.mgl",
    "/media/fat/_Physical Disc Cores/Cores/CDi.rbf",
    "/media/fat/_Physical Disc Cores/MegaCD.mgl",
    "/media/fat/_Physical Disc Cores/PSX.mgl",
    "/media/fat/_Physical Disc Cores/Saturn.mgl",
    "/media/fat/_Physical Disc Cores/TurboGrafx16-CD.mgl",
)


def _presence(exists):
    found = [path for path in PHYSICAL_DISC_FILES if exists(path)]
    return found, len(found) == len(PHYSICAL_DISC_FILES)


def _manual_physical_disc_install(connection):
    found, _complete = _presence(lambda path: _path_exists(connection, path))
    return bool(found and not database_registered_online(connection, PHYSICAL_DISC_DB_ID))


def _manual_physical_disc_install_local(sd_root):
    found, _complete = _presence(lambda path: _path_exists_local(sd_root, path))
    return bool(found and not database_registered_local(sd_root, PHYSICAL_DISC_DB_ID))


def _prepare_manual_physical_disc_for_downloader(connection, log, manual=None):
    if manual is None:
        manual = _manual_physical_disc_install(connection)
    if not manual:
        return False
    log("Detected a manual Physical Disc Cores installation; preparing it for Downloader...\n")
    for path in PHYSICAL_DISC_FILES:
        connection.run_command(f"rm -f {_quote(path)}")
        log(f"Removed legacy managed file: {path}\n")
    log("Preserved unknown files inside /media/fat/_Physical Disc Cores.\n")
    return True


def _prepare_manual_physical_disc_for_downloader_local(sd_root, log, manual=None):
    if manual is None:
        manual = _manual_physical_disc_install_local(sd_root)
    if not manual:
        return False
    log("Detected a manual Physical Disc Cores installation; preparing it for Downloader...\n")
    for path in PHYSICAL_DISC_FILES:
        _remove_local_path(sd_root, path)
        log(f"Removed legacy managed file: {path}\n")
    log("Preserved unknown files inside /media/fat/_Physical Disc Cores.\n")
    return True


def _status(found, complete, manual, update_available=False, connected=True):
    installed = bool(found)
    partial = bool(found and not complete)
    if not connected:
        return {"installed": False, "partial": False, "update_available": False, "status_text": "Unknown", "install_label": "Install", "install_enabled": False, "uninstall_enabled": False}
    if manual:
        text, label, enabled, update = "▲ Manual install found", "Migrate / Update", True, True
    elif not installed:
        text, label, enabled, update = "✗ Not installed", "Install", True, False
    elif partial:
        text, label, enabled, update = "⚠ Missing files", "Install", True, False
    elif update_available:
        text, label, enabled, update = "▲ Update available", "Update", True, True
    else:
        text, label, enabled, update = "✓ Installed", "Installed", False, False
    return {"installed": installed, "partial": partial, "installed_version": "", "latest_version": "", "latest_error": "", "update_available": update, "status_text": text, "install_label": label, "install_enabled": enabled, "uninstall_enabled": installed}


def get_physical_disc_status(connection, check_latest=False):
    if not connection.is_connected():
        return _status([], False, False, connected=False)
    found, complete = _presence(lambda path: _path_exists(connection, path))
    manual = bool(found and not database_registered_online(connection, PHYSICAL_DISC_DB_ID))
    update = bool(check_latest and found and complete and not manual and check_named_database_online(connection, PHYSICAL_DISC_DB_ID))
    return _status(found, complete, manual, update)


def get_physical_disc_status_local(sd_root, check_latest=False):
    found, complete = _presence(lambda path: _path_exists_local(sd_root, path))
    manual = bool(found and not database_registered_local(sd_root, PHYSICAL_DISC_DB_ID))
    update = bool(check_latest and found and complete and not manual and check_named_database_local(sd_root, PHYSICAL_DISC_DB_ID))
    return _status(found, complete, manual, update)


def _reboot_result(uninstall=False):
    action = "uninstall changes" if uninstall else "installation"
    return {"soft_reboot_required": True, "soft_reboot_title": "Soft Reboot Required", "soft_reboot_message": f"A soft reboot is required to apply the Physical Disc Cores {action}.\n\nDo you want to soft reboot MiSTer now?"}


def install_or_update_physical_disc(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    manual = _manual_physical_disc_install(connection)
    original = ensure_database_source_online(connection, PHYSICAL_DISC_DB_ID, PHYSICAL_DISC_DB_URL)
    try:
        _prepare_manual_physical_disc_for_downloader(connection, log, manual=manual)
        run_named_database_online(connection, PHYSICAL_DISC_DB_ID, log=log)
        connection.run_command(f"chmod +x {_quote(PHYSICAL_DISC_BINARY)}")
    except Exception:
        restore_online(connection, original)
        raise
    return _reboot_result()


def install_or_update_physical_disc_local(sd_root, log):
    manual = _manual_physical_disc_install_local(sd_root)
    original = ensure_database_source_local(sd_root, PHYSICAL_DISC_DB_ID, PHYSICAL_DISC_DB_URL)
    try:
        _prepare_manual_physical_disc_for_downloader_local(sd_root, log, manual=manual)
        run_named_database_local(sd_root, PHYSICAL_DISC_DB_ID, log=log)
    except Exception:
        restore_local(sd_root, original)
        raise
    return _reboot_result()


def uninstall_physical_disc(connection, log, force=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    if _manual_physical_disc_install(connection):
        _prepare_manual_physical_disc_for_downloader(connection, log, manual=True)
        remove_database_source_online(connection, PHYSICAL_DISC_DB_ID)
        return _reboot_result(uninstall=True)
    original = ensure_database_source_online(connection, PHYSICAL_DISC_DB_ID, PHYSICAL_DISC_DB_URL)
    try:
        native = uninstall_named_database_online(connection, PHYSICAL_DISC_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(connection, PHYSICAL_DISC_DB_ID, PHYSICAL_DISC_DB_URL, filter_value="!all")
            run_named_database_online(connection, PHYSICAL_DISC_DB_ID, log=log)
            remove_database_source_online(connection, PHYSICAL_DISC_DB_ID)
    except Exception:
        restore_online(connection, original)
        raise
    return _reboot_result(uninstall=True)


def uninstall_physical_disc_local(sd_root, log, force=False):
    if _manual_physical_disc_install_local(sd_root):
        _prepare_manual_physical_disc_for_downloader_local(sd_root, log, manual=True)
        remove_database_source_local(sd_root, PHYSICAL_DISC_DB_ID)
        return _reboot_result(uninstall=True)
    original = ensure_database_source_local(sd_root, PHYSICAL_DISC_DB_ID, PHYSICAL_DISC_DB_URL)
    try:
        native = uninstall_named_database_local(sd_root, PHYSICAL_DISC_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(sd_root, PHYSICAL_DISC_DB_ID, PHYSICAL_DISC_DB_URL, filter_value="!all")
            run_named_database_local(sd_root, PHYSICAL_DISC_DB_ID, log=log)
            remove_database_source_local(sd_root, PHYSICAL_DISC_DB_ID)
    except Exception:
        restore_local(sd_root, original)
        raise
    return _reboot_result(uninstall=True)

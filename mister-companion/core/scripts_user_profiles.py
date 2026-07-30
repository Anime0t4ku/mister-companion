from core.downloader_backend import (
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

USER_PROFILES_DB_ID = "BertSVG/MiSTer_FPGA_User_Profiles"
USER_PROFILES_DB_URL = "https://raw.githubusercontent.com/BertSVG/MiSTer_FPGA_User_Profiles/db/db.json.zip"


def install_or_update_user_profiles(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    original = ensure_database_source_online(connection, USER_PROFILES_DB_ID, USER_PROFILES_DB_URL)
    try:
        run_named_database_online(connection, USER_PROFILES_DB_ID, log=log)
    except Exception:
        restore_online(connection, original)
        raise


def install_or_update_user_profiles_local(sd_root, log):
    original = ensure_database_source_local(sd_root, USER_PROFILES_DB_ID, USER_PROFILES_DB_URL)
    try:
        run_named_database_local(sd_root, USER_PROFILES_DB_ID, log=log)
    except Exception:
        restore_local(sd_root, original)
        raise


def uninstall_user_profiles(connection, log, force=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    original = ensure_database_source_online(connection, USER_PROFILES_DB_ID, USER_PROFILES_DB_URL)
    try:
        native = uninstall_named_database_online(connection, USER_PROFILES_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(connection, USER_PROFILES_DB_ID, USER_PROFILES_DB_URL, filter_value="!all")
            run_named_database_online(connection, USER_PROFILES_DB_ID, log=log)
            remove_database_source_online(connection, USER_PROFILES_DB_ID)
    except Exception:
        restore_online(connection, original)
        raise
    return {"uninstalled": True}


def uninstall_user_profiles_local(sd_root, log, force=False):
    original = ensure_database_source_local(sd_root, USER_PROFILES_DB_ID, USER_PROFILES_DB_URL)
    try:
        native = uninstall_named_database_local(sd_root, USER_PROFILES_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(sd_root, USER_PROFILES_DB_ID, USER_PROFILES_DB_URL, filter_value="!all")
            run_named_database_local(sd_root, USER_PROFILES_DB_ID, log=log)
            remove_database_source_local(sd_root, USER_PROFILES_DB_ID)
    except Exception:
        restore_local(sd_root, original)
        raise
    return {"uninstalled": True}

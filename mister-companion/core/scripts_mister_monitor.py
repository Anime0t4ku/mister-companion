import configparser
import posixpath
from io import StringIO

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


MISTER_MONITOR_DB_ID = "chipster6502/MiSTer_monitor_DB"
MISTER_MONITOR_DB_URL = "https://raw.githubusercontent.com/chipster6502/MiSTer_monitor_DB/db/db.json.zip"
MISTER_MONITOR_CONFIG_DIR = "/media/fat/Scripts/.config/mister_monitor"
MISTER_MONITOR_RA_CONFIG_PATH = f"{MISTER_MONITOR_CONFIG_DIR}/ra_credentials.ini"
MISTER_MONITOR_SCRIPT_PATH = "/media/fat/Scripts/MiSTer_Monitor.sh"


def _quote(path: str) -> str:
    return "'" + path.replace("'", "'\"'\"'") + "'"


def _parse_ra_credentials(text: str) -> dict:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_file(StringIO(text or ""))
    except configparser.Error:
        return {"username": "", "api_key": ""}
    return {
        "username": parser.get("retroachievements", "username", fallback=""),
        "api_key": parser.get("retroachievements", "api_key", fallback=""),
    }


def _build_ra_credentials(username: str, api_key: str) -> str:
    parser = configparser.ConfigParser(interpolation=None)
    parser["retroachievements"] = {
        "username": username.strip(),
        "api_key": api_key.strip(),
    }
    output = StringIO()
    parser.write(output)
    return output.getvalue()


def load_mister_monitor_ra_config(connection) -> dict:
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    sftp = connection.client.open_sftp()
    try:
        try:
            with sftp.open(MISTER_MONITOR_RA_CONFIG_PATH, "rb") as remote_file:
                data = remote_file.read()
        except OSError:
            return {"username": "", "api_key": ""}
    finally:
        sftp.close()

    return _parse_ra_credentials(data.decode("utf-8", errors="replace"))


def save_mister_monitor_ra_config(connection, username: str, api_key: str):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    username = username.strip()
    api_key = api_key.strip()
    if not username or not api_key:
        raise ValueError("RetroAchievements username and Web API key are required.")

    connection.run_command(f"mkdir -p {_quote(MISTER_MONITOR_CONFIG_DIR)}")
    text = _build_ra_credentials(username, api_key).encode("utf-8")
    temporary_path = f"{MISTER_MONITOR_RA_CONFIG_PATH}.companion.tmp"

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(temporary_path, "wb") as remote_file:
            remote_file.write(text)
            remote_file.flush()
    finally:
        sftp.close()

    write_result = connection.run_command(
        f"chmod 600 {_quote(temporary_path)} && "
        f"mv -f {_quote(temporary_path)} {_quote(MISTER_MONITOR_RA_CONFIG_PATH)} && "
        "echo COMPANION_WRITE_OK"
    )
    if "COMPANION_WRITE_OK" not in (write_result or ""):
        connection.run_command(f"rm -f {_quote(temporary_path)}")
        raise RuntimeError("Unable to write the MiSTer Monitor credentials file.")

    result = connection.run_command(
        f"bash {_quote(MISTER_MONITOR_SCRIPT_PATH)} restart && echo COMPANION_OK"
    )
    if "COMPANION_OK" not in (result or ""):
        raise RuntimeError("Credentials were saved, but MiSTer Monitor could not be restarted.")

    return {"configured": True}


def install_or_update_mister_monitor(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    original = ensure_database_source_online(connection, MISTER_MONITOR_DB_ID, MISTER_MONITOR_DB_URL)
    try:
        run_named_database_online(connection, MISTER_MONITOR_DB_ID, log=log)
    except Exception:
        restore_online(connection, original)
        raise


def install_or_update_mister_monitor_local(sd_root, log):
    original = ensure_database_source_local(sd_root, MISTER_MONITOR_DB_ID, MISTER_MONITOR_DB_URL)
    try:
        run_named_database_local(sd_root, MISTER_MONITOR_DB_ID, log=log)
    except Exception:
        restore_local(sd_root, original)
        raise


def uninstall_mister_monitor(connection, log, force=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    original = ensure_database_source_online(connection, MISTER_MONITOR_DB_ID, MISTER_MONITOR_DB_URL)
    try:
        native = uninstall_named_database_online(connection, MISTER_MONITOR_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(
                connection,
                MISTER_MONITOR_DB_ID,
                MISTER_MONITOR_DB_URL,
                filter_value="!all",
            )
            run_named_database_online(connection, MISTER_MONITOR_DB_ID, log=log)
            remove_database_source_online(connection, MISTER_MONITOR_DB_ID)
    except Exception:
        restore_online(connection, original)
        raise
    return {"uninstalled": True}


def uninstall_mister_monitor_local(sd_root, log, force=False):
    original = ensure_database_source_local(sd_root, MISTER_MONITOR_DB_ID, MISTER_MONITOR_DB_URL)
    try:
        native = uninstall_named_database_local(sd_root, MISTER_MONITOR_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(
                sd_root,
                MISTER_MONITOR_DB_ID,
                MISTER_MONITOR_DB_URL,
                filter_value="!all",
            )
            run_named_database_local(sd_root, MISTER_MONITOR_DB_ID, log=log)
            remove_database_source_local(sd_root, MISTER_MONITOR_DB_ID)
    except Exception:
        restore_local(sd_root, original)
        raise
    return {"uninstalled": True}

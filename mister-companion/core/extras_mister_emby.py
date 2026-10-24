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

MISTEREMBY_DB_ID = "freemchr/misteremby"
MISTEREMBY_DB_URL = "https://raw.githubusercontent.com/freemchr/MiSTerEmby/db/db.json"


def install_or_update_misteremby(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    original = ensure_database_source_online(connection, MISTEREMBY_DB_ID, MISTEREMBY_DB_URL)
    try:
        run_named_database_online(connection, MISTEREMBY_DB_ID, log=log)
    except Exception:
        restore_online(connection, original)
        raise


def install_or_update_misteremby_local(sd_root, log):
    original = ensure_database_source_local(sd_root, MISTEREMBY_DB_ID, MISTEREMBY_DB_URL)
    try:
        run_named_database_local(sd_root, MISTEREMBY_DB_ID, log=log)
    except Exception:
        restore_local(sd_root, original)
        raise


def uninstall_misteremby(connection, log, force=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    original = ensure_database_source_online(connection, MISTEREMBY_DB_ID, MISTEREMBY_DB_URL)
    try:
        native = uninstall_named_database_online(connection, MISTEREMBY_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(connection, MISTEREMBY_DB_ID, MISTEREMBY_DB_URL, filter_value="!all")
            run_named_database_online(connection, MISTEREMBY_DB_ID, log=log)
            remove_database_source_online(connection, MISTEREMBY_DB_ID)
    except Exception:
        restore_online(connection, original)
        raise
    remove_database_source_online(connection, MISTEREMBY_DB_ID)
    from core.file_browser import delete_path
    for path in ('/media/fat/misteremby', '/media/fat/Scripts/MiSTerEmby.sh'):
        try:
            delete_path(connection, path)
        except FileNotFoundError:
            pass
    return {"uninstalled": True}


def uninstall_misteremby_local(sd_root, log, force=False):
    original = ensure_database_source_local(sd_root, MISTEREMBY_DB_ID, MISTEREMBY_DB_URL)
    try:
        native = uninstall_named_database_local(sd_root, MISTEREMBY_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(sd_root, MISTEREMBY_DB_ID, MISTEREMBY_DB_URL, filter_value="!all")
            run_named_database_local(sd_root, MISTEREMBY_DB_ID, log=log)
            remove_database_source_local(sd_root, MISTEREMBY_DB_ID)
    except Exception:
        restore_local(sd_root, original)
        raise
    remove_database_source_local(sd_root, MISTEREMBY_DB_ID)
    import shutil
    from pathlib import Path
    folder = Path(sd_root) / 'misteremby'
    if folder.is_dir():
        shutil.rmtree(folder)
    (Path(sd_root) / 'Scripts/MiSTerEmby.sh').unlink(missing_ok=True)
    return {"uninstalled": True}


def get_misteremby_status(target, check_latest=False):
    # Shared Install Center file markers and Downloader checks supply the status.
    return {}


def validate_server(value):
    import re
    from urllib.parse import urlsplit
    value = value.strip().rstrip('/')
    if not re.fullmatch(r"[A-Za-z0-9:/._%?=&+@\[\]~-]+", value):
        raise ValueError('Enter an HTTP or HTTPS server URL, for example http://192.168.1.10:8096.')
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Enter an HTTP or HTTPS server URL without credentials.')
    parsed.port
    return value


def save_server(context, value, log):
    from pathlib import Path
    import re
    import shlex
    value = validate_server(value)
    sftp = None
    try:
        if context.offline:
            path = Path(context.sd_root) / 'misteremby/emby.conf'
            old = path.read_text() if path.exists() else ''
        else:
            sftp = context.connection.client.open_sftp()
            path = '/media/fat/misteremby/emby.conf'
            try:
                with sftp.open(path, 'rb') as stream:
                    old = stream.read().decode('utf-8')
            except FileNotFoundError:
                old = ''
        # Quote shell metacharacters while keeping ordinary server URLs readable.
        line = 'SERVER=' + shlex.quote(value)
        if re.search(r'^SERVER=.*$', old, flags=re.M):
            text = re.sub(r'^SERVER=.*$', lambda _: line, old, flags=re.M)
        else:
            text = old + ('\n' if old and not old.endswith('\n') else '') + line + '\n'
        if context.offline:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        else:
            from core.file_browser import ensure_remote_dir
            ensure_remote_dir(sftp, '/media/fat/misteremby')
            with sftp.open(path, 'wb') as stream:
                stream.write(text.encode('utf-8'))
    finally:
        if sftp:
            sftp.close()
    log('MiSTerEmby server saved. Launch Scripts/MiSTerEmby.sh, then enter the on-screen PIN at https://emby.media/pin.\n')

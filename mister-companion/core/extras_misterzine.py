"""MisterZine's stable Downloader package and one-time menu setup."""

import os
from pathlib import Path
import shlex
import tempfile

from core import downloader_backend as downloader
from core.extras_common import _path_exists, _path_exists_local, _read_local_text, _read_remote_text


DB_ID = "misterzine"
DB_URL = "https://github.com/matijaerceg/misterzine-on-device/releases/latest/download/misterzine.json.zip"
APP_DIR = "/media/fat/misterzine"
BINARY = APP_DIR + "/misterzine"
STARTUP = "/media/fat/linux/user-startup.sh"
STARTUP_LINE = "[[ -e /media/fat/misterzine/misterzine ]] && /media/fat/misterzine/misterzine launcher start"
MENU_FILES = ("MisterZine.mgl", "misterzine.mgl")
SETUP_NOTE = "Boot MiSTer, run MisterZine-Setup from Scripts once, then choose MisterZine in the main menu."


def _enabled(text):
    return any(line.split("#", 1)[0].strip() == STARTUP_LINE for line in text.splitlines())


def _status(*, present, complete, registered, enabled, offline, check):
    available = False
    error = ""
    if check and complete and registered:
        try:
            available = bool(check())
        except Exception as exc:
            error = str(exc)
    repair = present and (not complete or not registered)
    setup = complete and not enabled
    label = "Update" if available else "Installed" if complete else "Install"
    text = "Update available" if available else "Installed" if complete else "Not installed"
    install_enabled = not complete or available
    if repair:
        label, text, install_enabled = "Repair / Update", "Incomplete or unregistered installation", True
    elif setup:
        text += " — run MisterZine-Setup on MiSTer" if offline else " — menu setup needed"
        if not offline:
            label, install_enabled = "Update and Set Up" if available else "Set Up", True
    if error:
        text += f" (update check failed: {error})"
    return {
        "installed": present or registered,
        "update_available": available,
        "status_text": text,
        "install_label": label,
        "install_enabled": install_enabled,
        "uninstall_enabled": registered and complete,
        "repair_action": repair or (setup and not offline),
    }


def _get_status(target, offline, check_latest):
    exists = (lambda path: _path_exists_local(target, path)) if offline else (lambda path: _path_exists(target, path))
    read = (lambda path: _read_local_text(target, path)) if offline else (lambda path: _read_remote_text(target, path))
    registered = (downloader.database_registered_local if offline else downloader.database_registered_online)(target, DB_ID)
    present = exists(BINARY)
    complete = present and exists(APP_DIR + "/maintenance.py") and exists("/media/fat/Scripts/MisterZine-Setup.sh")
    check = downloader.check_named_database_local if offline else downloader.check_named_database_online
    return _status(
        present=present, complete=complete, registered=registered,
        enabled=_enabled(read(STARTUP)) and exists("/media/fat/MisterZine.mgl"),
        offline=offline, check=(lambda: check(target, DB_ID)) if check_latest else None,
    )


def get_misterzine_status(connection, check_latest=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    return _get_status(connection, False, check_latest)


def get_misterzine_status_local(sd_root, check_latest=False):
    return _get_status(sd_root, True, check_latest)


def _remote_checked(connection, command, log):
    output, code = downloader._run_remote_streaming_result(connection, command, log=log)
    if code:
        raise RuntimeError(f"MisterZine command failed (exit {code}).\n{output}")
    return output


def install_or_update_misterzine(connection, log):
    # Keep this handler outside the deferred batch: setup requires downloaded files.
    original = downloader.ensure_database_source_online(connection, DB_ID, DB_URL, filter_value="")
    try:
        _remote_checked(connection, downloader._remote_downloader_command("--run-only", DB_ID) + " 2>&1", log)
    except Exception:
        downloader.restore_online(connection, original)
        raise
    # Keep registration after a setup failure so updates and a setup retry work.
    _remote_checked(connection, f"{BINARY} launcher enable", log)
    log("MisterZine is ready. Choose MisterZine in the MiSTer main menu.\n")


def install_or_update_misterzine_local(sd_root, log):
    original = downloader.ensure_database_source_local(sd_root, DB_ID, DB_URL, filter_value="")
    try:
        downloader.run_named_database_local(sd_root, DB_ID, log=log)
    except Exception:
        downloader.restore_local(sd_root, original)
        raise
    if not _path_exists_local(sd_root, BINARY):
        raise RuntimeError("MisterZine files are missing after Downloader finished. Retry installation.")
    if not (_enabled(_read_local_text(sd_root, STARTUP)) and _path_exists_local(sd_root, "/media/fat/MisterZine.mgl")):
        log(SETUP_NOTE + "\n")
    else:
        log("MisterZine updated. Existing menu setup was preserved.\n")


def _require_native_uninstall(target, offline):
    version = (downloader.get_downloader_version_local if offline else downloader.get_downloader_version_online)(target)
    if not downloader._supports_native_uninstall(version):
        raise RuntimeError("Update Downloader to version 2.4.3 or newer before removing MisterZine.")


def uninstall_misterzine(connection, log, force=False):
    # Reject a running frontend before the Downloader launcher performs any
    # potentially slow startup/network work. Check again immediately before cleanup.
    preflight = (
        "import sys; "
        f"sys.path.insert(0, {APP_DIR!r}); import maintenance as m; "
        "card, app = m.checked_app_directory('/media/fat'); m.idle_watchers(app)"
    )
    _remote_checked(connection, "python3 -c " + shlex.quote(preflight), log)
    _require_native_uninstall(connection, False)
    # Use the shipped helper's process checks before stopping the menu watcher.
    # This refuses removal while the frontend or an updater is still running.
    prepare = (
        "import sys; from pathlib import Path; "
        f"sys.path.insert(0, {APP_DIR!r}); import maintenance as m; "
        "card, app = m.checked_app_directory('/media/fat'); "
        "watchers = m.idle_watchers(app); "
        "m.remove_startup_hook(card); m.stop_watchers(watchers); "
        "[(card / name).unlink(missing_ok=True) for name in ('MisterZine.mgl', 'misterzine.mgl')]"
    )
    _remote_checked(connection, "python3 -c " + shlex.quote(prepare), log)
    try:
        if not downloader.uninstall_named_database_online(connection, DB_ID, log=log, force=force):
            raise RuntimeError("Downloader does not support native uninstall.")
        downloader.remove_database_source_online(connection, DB_ID)
    except Exception:
        log("Removal did not finish. Saved data was kept. Repair / Update can restore the menu entry.\n")
        raise
    log("MisterZine removed. Favorites, preferences, and cached pictures were kept.\n")


def _card_path(sd_root, relative):
    root = Path(sd_root).resolve(strict=True)
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise RuntimeError(f"Refusing to modify a redirected SD-card path: {relative}")
    return path


def _remove_local_menu(sd_root):
    startup = _card_path(sd_root, "linux/user-startup.sh")
    menu_paths = [_card_path(sd_root, name) for name in MENU_FILES]
    if startup.exists():
        original = startup.read_bytes()
        kept = b"".join(
            line for line in original.splitlines(keepends=True)
            if line.strip() != b"# misterzine"
            and line.split(b"#", 1)[0].strip() != STARTUP_LINE.encode()
        )
        if original != kept:
            fd, name = tempfile.mkstemp(prefix=".misterzine-startup-", dir=startup.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(kept)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(name, startup.stat().st_mode & 0o777)
                os.replace(name, startup)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
    for path in menu_paths:
        path.unlink(missing_ok=True)


def uninstall_misterzine_local(sd_root, log, force=False):
    _require_native_uninstall(sd_root, True)
    _remove_local_menu(sd_root)
    try:
        if not downloader.uninstall_named_database_local(sd_root, DB_ID, log=log, force=force):
            raise RuntimeError("Downloader does not support native uninstall.")
        downloader.remove_database_source_local(sd_root, DB_ID)
    except Exception:
        log("Removal did not finish. Saved data was kept. Run MisterZine-Setup on MiSTer to restore the menu entry.\n")
        raise
    log("MisterZine removed. Favorites, preferences, and cached pictures were kept.\n")

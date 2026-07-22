import io
import os
import posixpath
import re
import shutil
import zipfile

import requests

from core.extras_common import (
    _ensure_local_dir,
    _ensure_remote_dir,
    _fetch_latest_release_from_html,
    _local_path,
    _normalize_ini_text_for_append,
    _path_exists,
    _path_exists_local,
    _quote,
    _read_local_text,
    _read_remote_text,
    _remove_if_empty_dir,
    _remove_local_path,
    _write_local_bytes,
    _write_local_text,
    _write_remote_text,
)

QUAKE_GITHUB_REPO = "neofreno/Mister_Quake"
QUAKE_TITLE = "MiSTer Quake"
QUAKE_ASSET_PATTERN = re.compile(r"^MiSTer_Quake_(\d{8})\.zip$", re.IGNORECASE)

QUAKE_REMOTE_LAUNCHER = "/media/fat/MiSTer_Quake"
QUAKE_REMOTE_RBF = "/media/fat/_Other/Quake.rbf"
QUAKE_REMOTE_GAME_DIR = "/media/fat/games/quake"
QUAKE_REMOTE_BIN = "/media/fat/games/quake/bin/quake-mister"
QUAKE_REMOTE_ID1_DIR = "/media/fat/games/quake/id1"
QUAKE_REMOTE_VERSION_FILE = "/media/fat/games/quake/.mister_companion_version"
REMOTE_INI_PATH = "/media/fat/MiSTer.ini"

QUAKE_INI_SECTIONS = {
    "Quake": {"main": "MiSTer_Quake", "vga_scaler": "0"},
    "MiSTer_Quake": {"main": "MiSTer_Quake", "vga_scaler": "0"},
}


def _fetch_latest_quake_release():
    release = _fetch_latest_release_from_html(QUAKE_GITHUB_REPO, QUAKE_TITLE)
    candidates = []
    for asset in release.get("assets", []):
        name = str(asset.get("name", ""))
        match = QUAKE_ASSET_PATTERN.match(name)
        if match:
            candidates.append((match.group(1), asset.get("url", "")))
    if not candidates:
        raise RuntimeError("Unable to find a MiSTer_Quake_YYYYMMDD.zip asset in the latest release.")
    candidates.sort(reverse=True)
    version, zip_url = candidates[0]
    return {"version": version, "zip_url": zip_url}


def _is_installed(connection):
    return all(_path_exists(connection, p) for p in (QUAKE_REMOTE_LAUNCHER, QUAKE_REMOTE_RBF, QUAKE_REMOTE_BIN))


def _is_installed_local(sd_root):
    return all(_path_exists_local(sd_root, p) for p in (QUAKE_REMOTE_LAUNCHER, QUAKE_REMOTE_RBF, QUAKE_REMOTE_BIN))


def _read_version(connection):
    return _read_remote_text(connection, QUAKE_REMOTE_VERSION_FILE).strip()


def _read_version_local(sd_root):
    return _read_local_text(sd_root, QUAKE_REMOTE_VERSION_FILE).strip()


def _write_version(connection, version):
    _ensure_remote_dir(connection, posixpath.dirname(QUAKE_REMOTE_VERSION_FILE))
    _write_remote_text(connection, QUAKE_REMOTE_VERSION_FILE, version.strip() + "\n")


def _write_version_local(sd_root, version):
    _ensure_local_dir(sd_root, posixpath.dirname(QUAKE_REMOTE_VERSION_FILE))
    _write_local_text(sd_root, QUAKE_REMOTE_VERSION_FILE, version.strip() + "\n")


def _pak_state(connection):
    return {
        "pak0_present": _path_exists(connection, posixpath.join(QUAKE_REMOTE_ID1_DIR, "PAK0.PAK")),
        "pak1_present": _path_exists(connection, posixpath.join(QUAKE_REMOTE_ID1_DIR, "PAK1.PAK")),
    }


def _pak_state_local(sd_root):
    return {
        "pak0_present": _path_exists_local(sd_root, posixpath.join(QUAKE_REMOTE_ID1_DIR, "PAK0.PAK")),
        "pak1_present": _path_exists_local(sd_root, posixpath.join(QUAKE_REMOTE_ID1_DIR, "PAK1.PAK")),
    }


def _status(installed, installed_version, latest_version, latest_error, pak):
    update_available = bool(installed and latest_version and (not installed_version or installed_version != latest_version))
    if not installed:
        status_text, label, enabled = "✗ Not installed", "Install", True
    elif update_available:
        status_text, label, enabled = f"▲ Update available ({installed_version or 'unknown'} → {latest_version})", "Update", True
    else:
        status_text, label, enabled = f"✓ Installed ({installed_version or 'unknown'})", "Installed", False
    if latest_error:
        status_text += f" (update check failed: {latest_error})"
    return {
        "installed": installed,
        "installed_version": installed_version,
        "latest_version": latest_version,
        "latest_error": latest_error,
        "update_available": update_available,
        "status_text": status_text,
        "install_label": label,
        "install_enabled": enabled,
        "upload_enabled": installed,
        "uninstall_enabled": installed,
        **pak,
    }


def get_mister_quake_status(connection, check_latest=False):
    if not connection.is_connected():
        return _status(False, "", "", "", {"pak0_present": False, "pak1_present": False}) | {"install_enabled": False}
    latest_version = ""; latest_error = ""
    if check_latest:
        try: latest_version = _fetch_latest_quake_release()["version"]
        except Exception as exc: latest_error = str(exc)
    installed = _is_installed(connection)
    return _status(installed, _read_version(connection) if installed else "", latest_version, latest_error, _pak_state(connection) if installed else {"pak0_present": False, "pak1_present": False})


def get_mister_quake_status_local(sd_root, check_latest=False):
    latest_version = ""; latest_error = ""
    if check_latest:
        try: latest_version = _fetch_latest_quake_release()["version"]
        except Exception as exc: latest_error = str(exc)
    installed = _is_installed_local(sd_root)
    return _status(installed, _read_version_local(sd_root) if installed else "", latest_version, latest_error, _pak_state_local(sd_root) if installed else {"pak0_present": False, "pak1_present": False})


def _upsert_ini_sections(text):
    normalized = text.replace("\r\n", "\n")
    for section, values in QUAKE_INI_SECTIONS.items():
        pattern = re.compile(rf"(?ms)^\[{re.escape(section)}\]\n(.*?)(?=^\[|\Z)")
        match = pattern.search(normalized)
        if match:
            body = match.group(1)
            lines = body.rstrip("\n").split("\n") if body else []
            for key, value in values.items():
                key_pattern = re.compile(rf"^\s*{re.escape(key)}\s*=", re.IGNORECASE)
                replaced = False
                for i, line in enumerate(lines):
                    if key_pattern.match(line):
                        lines[i] = f"{key}={value}"; replaced = True; break
                if not replaced: lines.append(f"{key}={value}")
            replacement = f"[{section}]\n" + "\n".join(lines).rstrip("\n") + "\n\n"
            normalized = normalized[:match.start()] + replacement + normalized[match.end():]
        else:
            block = f"[{section}]\n" + "\n".join(f"{k}={v}" for k, v in values.items()) + "\n"
            normalized = _normalize_ini_text_for_append(normalized) + block
    return re.sub(r"\n{3,}", "\n\n", normalized).rstrip("\n") + "\n"


def _remove_ini_sections(text):
    normalized = text.replace("\r\n", "\n")
    for section in QUAKE_INI_SECTIONS:
        normalized = re.sub(rf"(?ms)(?:^|\n)\[{re.escape(section)}\]\n.*?(?=\n\[|\Z)", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip("\n")
    return normalized + ("\n" if normalized else "")


def _quake_ini_present(text):
    normalized = (text or "").replace("\r\n", "\n")
    for section, values in QUAKE_INI_SECTIONS.items():
        match = re.search(rf"(?ms)^\[{re.escape(section)}\]\n(.*?)(?=^\[|\Z)", normalized)
        if not match or any(not re.search(rf"(?mi)^\s*{re.escape(key)}\s*=\s*{re.escape(value)}\s*$", match.group(1)) for key, value in values.items()):
            return False
    return True


def _archive_files(zf):
    files = [m for m in zf.infolist() if not m.is_dir()]
    if not files: raise RuntimeError("The MiSTer Quake release archive is empty.")
    return files


def install_or_update_mister_quake(connection, log):
    if not connection.is_connected(): raise RuntimeError("Not connected to MiSTer.")
    latest = _fetch_latest_quake_release(); version = latest["version"]
    log(f"Latest version on GitHub: {version}\nDownloading: {latest['zip_url']}\n")
    response = requests.get(latest["zip_url"], timeout=60); response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        sftp = connection.client.open_sftp()
        try:
            for member in _archive_files(zf):
                name = member.filename.replace("\\", "/").lstrip("/")
                if name.lower().endswith(("/pak0.pak", "/pak1.pak")): continue
                remote = "/media/fat/" + name
                _ensure_remote_dir(connection, posixpath.dirname(remote))
                log(f"Installing {remote}\n")
                with sftp.open(remote, "wb") as fh: fh.write(zf.read(member))
        finally: sftp.close()
    connection.run_command(f"chmod +x {_quote(QUAKE_REMOTE_LAUNCHER)} {_quote(QUAKE_REMOTE_BIN)}")
    _write_remote_text(connection, REMOTE_INI_PATH, _upsert_ini_sections(_read_remote_text(connection, REMOTE_INI_PATH)))
    log("Added/updated Quake sections in MiSTer.ini\n")
    _write_version(connection, version)
    return {"installed_version": version}


def install_or_update_mister_quake_local(sd_root, log):
    latest = _fetch_latest_quake_release(); version = latest["version"]
    log(f"Latest version on GitHub: {version}\nDownloading: {latest['zip_url']}\n")
    response = requests.get(latest["zip_url"], timeout=60); response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        for member in _archive_files(zf):
            name = member.filename.replace("\\", "/").lstrip("/")
            if name.lower().endswith(("/pak0.pak", "/pak1.pak")): continue
            remote = "/media/fat/" + name
            log(f"Installing {remote}\n")
            _write_local_bytes(sd_root, remote, zf.read(member))
    _write_local_text(sd_root, REMOTE_INI_PATH, _upsert_ini_sections(_read_local_text(sd_root, REMOTE_INI_PATH)))
    log("Added/updated Quake sections in MiSTer.ini\n")
    _write_version_local(sd_root, version)
    return {"installed_version": version}


def _validate_paks(paths):
    result = []
    for path in paths:
        if not os.path.isfile(path): raise RuntimeError(f"Selected file does not exist: {path}")
        name = os.path.basename(path).upper()
        if name not in {"PAK0.PAK", "PAK1.PAK"}: raise RuntimeError(f"Unsupported file: {os.path.basename(path)}. Select PAK0.PAK and/or PAK1.PAK.")
        result.append((path, name))
    if not result: raise RuntimeError("No PAK files were selected.")
    return result


def upload_mister_quake_paks(connection, paths, log):
    if not connection.is_connected(): raise RuntimeError("Not connected to MiSTer.")
    if not _is_installed(connection): raise RuntimeError("MiSTer Quake is not installed.")
    files = _validate_paks(paths); _ensure_remote_dir(connection, QUAKE_REMOTE_ID1_DIR)
    sftp = connection.client.open_sftp()
    try:
        for source, name in files:
            target = posixpath.join(QUAKE_REMOTE_ID1_DIR, name)
            log(f"Uploading {name} to {target}\n")
            sftp.put(source, target)
    finally: sftp.close()
    return _pak_state(connection)


def upload_mister_quake_paks_local(sd_root, paths, log):
    if not _is_installed_local(sd_root): raise RuntimeError("MiSTer Quake is not installed.")
    files = _validate_paks(paths); _ensure_local_dir(sd_root, QUAKE_REMOTE_ID1_DIR)
    for source, name in files:
        target = _local_path(sd_root, posixpath.join(QUAKE_REMOTE_ID1_DIR, name))
        log(f"Copying {name} to {target}\n")
        shutil.copy2(source, target)
    return _pak_state_local(sd_root)


def uninstall_mister_quake(connection, log):
    if not connection.is_connected(): raise RuntimeError("Not connected to MiSTer.")
    for path in (QUAKE_REMOTE_LAUNCHER, QUAKE_REMOTE_RBF, QUAKE_REMOTE_VERSION_FILE):
        log(f"Removing {path}\n"); connection.run_command(f"rm -f {_quote(path)}")
    for path in ("/media/fat/games/quake/bin", "/media/fat/games/quake/lib", "/media/fat/games/quake/README_INSTALL.txt"):
        log(f"Removing {path}\n"); connection.run_command(f"rm -rf {_quote(path)}")
    _write_remote_text(connection, REMOTE_INI_PATH, _remove_ini_sections(_read_remote_text(connection, REMOTE_INI_PATH)))
    _remove_if_empty_dir(connection, QUAKE_REMOTE_GAME_DIR)
    log("Personal files in /media/fat/games/quake/id1 were preserved.\n")
    return {"uninstalled": True}


def uninstall_mister_quake_local(sd_root, log):
    for path in (QUAKE_REMOTE_LAUNCHER, QUAKE_REMOTE_RBF, QUAKE_REMOTE_VERSION_FILE, "/media/fat/games/quake/bin", "/media/fat/games/quake/lib", "/media/fat/games/quake/README_INSTALL.txt"):
        log(f"Removing {path}\n"); _remove_local_path(sd_root, path)
    _write_local_text(sd_root, REMOTE_INI_PATH, _remove_ini_sections(_read_local_text(sd_root, REMOTE_INI_PATH)))
    game_dir = _local_path(sd_root, QUAKE_REMOTE_GAME_DIR)
    try: game_dir.rmdir()
    except OSError: pass
    log("Personal files in /media/fat/games/quake/id1 were preserved.\n")
    return {"uninstalled": True}


# Downloader-backed Install Center implementation.
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

QUAKE_DB_ID = "MultiDatabases/mister-quake"
QUAKE_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/mister-quake/db.json"

# Exact files owned by the database. PAK files and the entire id1 directory are
# intentionally excluded because they belong to the user.
QUAKE_DB_FILES = (
    QUAKE_REMOTE_LAUNCHER,
    QUAKE_REMOTE_RBF,
    "/media/fat/games/quake/README_INSTALL.txt",
    QUAKE_REMOTE_BIN,
    "/media/fat/games/quake/lib/ld-linux-armhf.so.3",
    "/media/fat/games/quake/lib/libc.so.6",
    "/media/fat/games/quake/lib/libdl.so.2",
    "/media/fat/games/quake/lib/libgcc_s.so.1",
    "/media/fat/games/quake/lib/libm.so.6",
    "/media/fat/games/quake/lib/libpthread.so.0",
    "/media/fat/games/quake/lib/librt.so.1",
    "/media/fat/games/quake/lib/libstdc++.so.6",
)


def _manual_mister_quake_install(connection):
    present = any(_path_exists(connection, path) for path in (QUAKE_REMOTE_LAUNCHER, QUAKE_REMOTE_RBF, QUAKE_REMOTE_BIN))
    return bool(present and (_path_exists(connection, QUAKE_REMOTE_VERSION_FILE) or not database_registered_online(connection, QUAKE_DB_ID)))


def _manual_mister_quake_install_local(sd_root):
    present = any(_path_exists_local(sd_root, path) for path in (QUAKE_REMOTE_LAUNCHER, QUAKE_REMOTE_RBF, QUAKE_REMOTE_BIN))
    return bool(present and (_path_exists_local(sd_root, QUAKE_REMOTE_VERSION_FILE) or not database_registered_local(sd_root, QUAKE_DB_ID)))


def _prepare_manual_mister_quake_for_downloader(connection, log, manual=None):
    if manual is None:
        manual = _manual_mister_quake_install(connection)
    if not manual:
        return False
    log("Detected a manual Companion installation; preparing it for Downloader...\n")
    for path in QUAKE_DB_FILES:
        connection.run_command(f"rm -f {_quote(path)}")
    connection.run_command(f"rm -f {_quote(QUAKE_REMOTE_VERSION_FILE)}")
    log(f"Preserved user game data in {QUAKE_REMOTE_ID1_DIR}\n")
    return True


def _prepare_manual_mister_quake_for_downloader_local(sd_root, log, manual=None):
    if manual is None:
        manual = _manual_mister_quake_install_local(sd_root)
    if not manual:
        return False
    log("Detected a manual Companion installation; preparing it for Downloader...\n")
    for path in QUAKE_DB_FILES:
        _remove_local_path(sd_root, path)
    _remove_local_path(sd_root, QUAKE_REMOTE_VERSION_FILE)
    log(f"Preserved user game data in {QUAKE_REMOTE_ID1_DIR}\n")
    return True


_manual_get_mister_quake_status = get_mister_quake_status
_manual_get_mister_quake_status_local = get_mister_quake_status_local


def _apply_quake_downloader_status(status, manual, update_available=False):
    status = dict(status)
    if manual:
        status.update({"update_available": True, "status_text": "▲ Manual install found", "install_label": "Migrate / Update", "install_enabled": True})
    elif status.get("installed"):
        status.update({"installed_version": "", "latest_version": "", "update_available": bool(update_available), "status_text": "▲ Update available" if update_available else "✓ Installed", "install_label": "Update" if update_available else "Installed", "install_enabled": bool(update_available)})
    return status


def get_mister_quake_status(connection, check_latest=False):
    status = _manual_get_mister_quake_status(connection, check_latest=False)
    manual = _manual_mister_quake_install(connection)
    update = bool(check_latest and status.get("installed") and not manual and check_named_database_online(connection, QUAKE_DB_ID))
    status = _apply_quake_downloader_status(status, manual, update)
    if status.get("installed") and not manual and not _quake_ini_present(_read_remote_text(connection, REMOTE_INI_PATH)):
        status.update({"status_text": "⚠ MiSTer.ini entry missing", "install_label": "Add INI Entry", "install_enabled": True, "update_available": False, "repair_action": True})
    return status


def get_mister_quake_status_local(sd_root, check_latest=False):
    status = _manual_get_mister_quake_status_local(sd_root, check_latest=False)
    manual = _manual_mister_quake_install_local(sd_root)
    update = bool(check_latest and status.get("installed") and not manual and check_named_database_local(sd_root, QUAKE_DB_ID))
    status = _apply_quake_downloader_status(status, manual, update)
    if status.get("installed") and not manual and not _quake_ini_present(_read_local_text(sd_root, REMOTE_INI_PATH)):
        status.update({"status_text": "⚠ MiSTer.ini entry missing", "install_label": "Add INI Entry", "install_enabled": True, "update_available": False, "repair_action": True})
    return status


def install_or_update_mister_quake(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    manual = _manual_mister_quake_install(connection)
    if not manual and _manual_get_mister_quake_status(connection, check_latest=False).get("installed") and not _quake_ini_present(_read_remote_text(connection, REMOTE_INI_PATH)):
        _write_remote_text(connection, REMOTE_INI_PATH, _upsert_ini_sections(_read_remote_text(connection, REMOTE_INI_PATH)))
        return
    original = ensure_database_source_online(connection, QUAKE_DB_ID, QUAKE_DB_URL)
    try:
        _prepare_manual_mister_quake_for_downloader(connection, log, manual=manual)
        _write_remote_text(connection, REMOTE_INI_PATH, _upsert_ini_sections(_read_remote_text(connection, REMOTE_INI_PATH)))
        run_named_database_online(connection, QUAKE_DB_ID, log=log)
        connection.run_command(f"chmod +x {_quote(QUAKE_REMOTE_LAUNCHER)} {_quote(QUAKE_REMOTE_BIN)}")
        connection.run_command(f"rm -f {_quote(QUAKE_REMOTE_VERSION_FILE)}")
    except Exception:
        restore_online(connection, original)
        raise


def install_or_update_mister_quake_local(sd_root, log):
    manual = _manual_mister_quake_install_local(sd_root)
    if not manual and _manual_get_mister_quake_status_local(sd_root, check_latest=False).get("installed") and not _quake_ini_present(_read_local_text(sd_root, REMOTE_INI_PATH)):
        _write_local_text(sd_root, REMOTE_INI_PATH, _upsert_ini_sections(_read_local_text(sd_root, REMOTE_INI_PATH)))
        return
    original = ensure_database_source_local(sd_root, QUAKE_DB_ID, QUAKE_DB_URL)
    try:
        _prepare_manual_mister_quake_for_downloader_local(sd_root, log, manual=manual)
        _write_local_text(sd_root, REMOTE_INI_PATH, _upsert_ini_sections(_read_local_text(sd_root, REMOTE_INI_PATH)))
        run_named_database_local(sd_root, QUAKE_DB_ID, log=log)
        _remove_local_path(sd_root, QUAKE_REMOTE_VERSION_FILE)
    except Exception:
        restore_local(sd_root, original)
        raise


def uninstall_mister_quake(connection, log, force=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    if _manual_mister_quake_install(connection):
        _prepare_manual_mister_quake_for_downloader(connection, log, manual=True)
        remove_database_source_online(connection, QUAKE_DB_ID)
        _write_remote_text(connection, REMOTE_INI_PATH, _remove_ini_sections(_read_remote_text(connection, REMOTE_INI_PATH)))
        return {"uninstalled": True}
    original = ensure_database_source_online(connection, QUAKE_DB_ID, QUAKE_DB_URL)
    try:
        _write_remote_text(connection, REMOTE_INI_PATH, _remove_ini_sections(_read_remote_text(connection, REMOTE_INI_PATH)))
        native = uninstall_named_database_online(connection, QUAKE_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(connection, QUAKE_DB_ID, QUAKE_DB_URL, filter_value="!all")
            run_named_database_online(connection, QUAKE_DB_ID, log=log)
            remove_database_source_online(connection, QUAKE_DB_ID)
        connection.run_command(f"rm -f {_quote(QUAKE_REMOTE_VERSION_FILE)}")
    except Exception:
        restore_online(connection, original)
        raise
    return {"uninstalled": True}


def uninstall_mister_quake_local(sd_root, log, force=False):
    if _manual_mister_quake_install_local(sd_root):
        _prepare_manual_mister_quake_for_downloader_local(sd_root, log, manual=True)
        remove_database_source_local(sd_root, QUAKE_DB_ID)
        _write_local_text(sd_root, REMOTE_INI_PATH, _remove_ini_sections(_read_local_text(sd_root, REMOTE_INI_PATH)))
        return {"uninstalled": True}
    original = ensure_database_source_local(sd_root, QUAKE_DB_ID, QUAKE_DB_URL)
    try:
        _write_local_text(sd_root, REMOTE_INI_PATH, _remove_ini_sections(_read_local_text(sd_root, REMOTE_INI_PATH)))
        native = uninstall_named_database_local(sd_root, QUAKE_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(sd_root, QUAKE_DB_ID, QUAKE_DB_URL, filter_value="!all")
            run_named_database_local(sd_root, QUAKE_DB_ID, log=log)
            remove_database_source_local(sd_root, QUAKE_DB_ID)
        _remove_local_path(sd_root, QUAKE_REMOTE_VERSION_FILE)
    except Exception:
        restore_local(sd_root, original)
        raise
    return {"uninstalled": True}

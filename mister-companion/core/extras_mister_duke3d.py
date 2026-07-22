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

DUKE3D_GITHUB_REPO = "neofreno/Mister_Duke3d"
DUKE3D_TITLE = "MiSTer Duke3D"
DUKE3D_ASSET_PATTERN = re.compile(r"^Mister_duke3d_(\d{8})\.zip$", re.IGNORECASE)

DUKE3D_REMOTE_LAUNCHER = "/media/fat/Mister_duke3d"
DUKE3D_REMOTE_RBF = "/media/fat/_Other/DUKE3D.rbf"
DUKE3D_REMOTE_GAME_DIR = "/media/fat/games/DUKE3D"
DUKE3D_REMOTE_BIN = "/media/fat/games/DUKE3D/bin/duke3d-mister"
DUKE3D_REMOTE_GRP = "/media/fat/games/DUKE3D/duke3d.grp"
DUKE3D_REMOTE_VERSION_FILE = "/media/fat/games/DUKE3D/.mister_companion_version"
REMOTE_INI_PATH = "/media/fat/MiSTer.ini"

DUKE3D_INI_SECTIONS = {
    "DUKE3D": {"main": "Mister_duke3d", "vga_scaler": "0"},
    "Mister_duke3d": {"main": "Mister_duke3d", "vga_scaler": "0"},
}


def _fetch_latest_duke3d_release():
    release = _fetch_latest_release_from_html(DUKE3D_GITHUB_REPO, DUKE3D_TITLE)
    candidates = []
    for asset in release.get("assets", []):
        name = str(asset.get("name", ""))
        match = DUKE3D_ASSET_PATTERN.match(name)
        if match:
            candidates.append((match.group(1), asset.get("url", "")))
    if not candidates:
        raise RuntimeError("Unable to find a Mister_duke3d_YYYYMMDD.zip asset in the latest release.")
    candidates.sort(reverse=True)
    version, zip_url = candidates[0]
    return {"version": version, "zip_url": zip_url}


def _is_installed(connection):
    return all(_path_exists(connection, path) for path in (
        DUKE3D_REMOTE_LAUNCHER, DUKE3D_REMOTE_RBF, DUKE3D_REMOTE_BIN,
    ))


def _is_installed_local(sd_root):
    return all(_path_exists_local(sd_root, path) for path in (
        DUKE3D_REMOTE_LAUNCHER, DUKE3D_REMOTE_RBF, DUKE3D_REMOTE_BIN,
    ))


def _read_version(connection):
    return _read_remote_text(connection, DUKE3D_REMOTE_VERSION_FILE).strip()


def _read_version_local(sd_root):
    return _read_local_text(sd_root, DUKE3D_REMOTE_VERSION_FILE).strip()


def _write_version(connection, version):
    _ensure_remote_dir(connection, DUKE3D_REMOTE_GAME_DIR)
    _write_remote_text(connection, DUKE3D_REMOTE_VERSION_FILE, version.strip() + "\n")


def _write_version_local(sd_root, version):
    _ensure_local_dir(sd_root, DUKE3D_REMOTE_GAME_DIR)
    _write_local_text(sd_root, DUKE3D_REMOTE_VERSION_FILE, version.strip() + "\n")


def _status(installed, installed_version, latest_version, latest_error, grp_present):
    update_available = bool(installed and latest_version and (
        not installed_version or installed_version != latest_version
    ))
    if not installed:
        status_text, label, enabled = "✗ Not installed", "Install", True
    elif update_available:
        status_text = f"▲ Update available ({installed_version or 'unknown'} → {latest_version})"
        label, enabled = "Update", True
    else:
        status_text = f"✓ Installed ({installed_version or 'unknown'})"
        label, enabled = "Installed", False
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
        "grp_present": grp_present,
        "upload_enabled": installed and not grp_present,
        "uninstall_enabled": installed,
    }


def get_mister_duke3d_status(connection, check_latest=False):
    if not connection.is_connected():
        return _status(False, "", "", "", False) | {"install_enabled": False}
    latest_version = ""
    latest_error = ""
    if check_latest:
        try:
            latest_version = _fetch_latest_duke3d_release()["version"]
        except Exception as exc:
            latest_error = str(exc)
    installed = _is_installed(connection)
    return _status(
        installed,
        _read_version(connection) if installed else "",
        latest_version,
        latest_error,
        _path_exists(connection, DUKE3D_REMOTE_GRP) if installed else False,
    )


def get_mister_duke3d_status_local(sd_root, check_latest=False):
    latest_version = ""
    latest_error = ""
    if check_latest:
        try:
            latest_version = _fetch_latest_duke3d_release()["version"]
        except Exception as exc:
            latest_error = str(exc)
    installed = _is_installed_local(sd_root)
    return _status(
        installed,
        _read_version_local(sd_root) if installed else "",
        latest_version,
        latest_error,
        _path_exists_local(sd_root, DUKE3D_REMOTE_GRP) if installed else False,
    )


def _upsert_ini_sections(text):
    normalized = text.replace("\r\n", "\n")
    for section, values in DUKE3D_INI_SECTIONS.items():
        pattern = re.compile(rf"(?ms)^\[{re.escape(section)}\]\n(.*?)(?=^\[|\Z)")
        match = pattern.search(normalized)
        if match:
            body = match.group(1)
            lines = body.rstrip("\n").split("\n") if body else []
            for key, value in values.items():
                key_pattern = re.compile(rf"^\s*{re.escape(key)}\s*=", re.IGNORECASE)
                for index, line in enumerate(lines):
                    if key_pattern.match(line):
                        lines[index] = f"{key}={value}"
                        break
                else:
                    lines.append(f"{key}={value}")
            replacement = f"[{section}]\n" + "\n".join(lines).rstrip("\n") + "\n\n"
            normalized = normalized[:match.start()] + replacement + normalized[match.end():]
        else:
            block = f"[{section}]\n" + "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
            normalized = _normalize_ini_text_for_append(normalized) + block
    return re.sub(r"\n{3,}", "\n\n", normalized).rstrip("\n") + "\n"


def _remove_ini_sections(text):
    normalized = text.replace("\r\n", "\n")
    for section in DUKE3D_INI_SECTIONS:
        normalized = re.sub(
            rf"(?ms)(?:^|\n)\[{re.escape(section)}\]\n.*?(?=\n\[|\Z)",
            "\n",
            normalized,
        )
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip("\n")
    return normalized + ("\n" if normalized else "")


def _duke3d_ini_present(text):
    normalized = (text or "").replace("\r\n", "\n")
    for section, values in DUKE3D_INI_SECTIONS.items():
        match = re.search(rf"(?ms)^\[{re.escape(section)}\]\n(.*?)(?=^\[|\Z)", normalized)
        if not match or any(not re.search(rf"(?mi)^\s*{re.escape(key)}\s*=\s*{re.escape(value)}\s*$", match.group(1)) for key, value in values.items()):
            return False
    return True


def _archive_files(zf):
    files = [member for member in zf.infolist() if not member.is_dir()]
    if not files:
        raise RuntimeError("The MiSTer Duke3D release archive is empty.")
    names = {member.filename.replace("\\", "/").lstrip("/").lower() for member in files}
    required = {
        "mister_duke3d",
        "_other/duke3d.rbf",
        "games/duke3d/bin/duke3d-mister",
    }
    if not required.issubset(names):
        raise RuntimeError("The MiSTer Duke3D release archive is missing required files.")
    return files


def install_or_update_mister_duke3d(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    latest = _fetch_latest_duke3d_release()
    version = latest["version"]
    log(f"Latest version on GitHub: {version}\nDownloading: {latest['zip_url']}\n")
    response = requests.get(latest["zip_url"], timeout=60)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        sftp = connection.client.open_sftp()
        try:
            for member in _archive_files(zf):
                name = member.filename.replace("\\", "/").lstrip("/")
                if name.lower() == "games/duke3d/duke3d.grp":
                    continue
                remote_path = "/media/fat/" + name
                _ensure_remote_dir(connection, posixpath.dirname(remote_path))
                log(f"Installing {remote_path}\n")
                with sftp.open(remote_path, "wb") as remote_file:
                    remote_file.write(zf.read(member))
        finally:
            sftp.close()
    connection.run_command(f"chmod +x {_quote(DUKE3D_REMOTE_LAUNCHER)} {_quote(DUKE3D_REMOTE_BIN)}")
    _write_remote_text(connection, REMOTE_INI_PATH, _upsert_ini_sections(_read_remote_text(connection, REMOTE_INI_PATH)))
    log("Added/updated DUKE3D sections in MiSTer.ini\n")
    _write_version(connection, version)
    return {"installed_version": version}


def install_or_update_mister_duke3d_local(sd_root, log):
    latest = _fetch_latest_duke3d_release()
    version = latest["version"]
    log(f"Latest version on GitHub: {version}\nDownloading: {latest['zip_url']}\n")
    response = requests.get(latest["zip_url"], timeout=60)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        for member in _archive_files(zf):
            name = member.filename.replace("\\", "/").lstrip("/")
            if name.lower() == "games/duke3d/duke3d.grp":
                continue
            remote_path = "/media/fat/" + name
            log(f"Installing {remote_path}\n")
            _write_local_bytes(sd_root, remote_path, zf.read(member))
    for path in (DUKE3D_REMOTE_LAUNCHER, DUKE3D_REMOTE_BIN):
        try:
            local_path = _local_path(sd_root, path)
            local_path.chmod(local_path.stat().st_mode | 0o111)
        except OSError:
            pass
    _write_local_text(sd_root, REMOTE_INI_PATH, _upsert_ini_sections(_read_local_text(sd_root, REMOTE_INI_PATH)))
    log("Added/updated DUKE3D sections in MiSTer.ini\n")
    _write_version_local(sd_root, version)
    return {"installed_version": version}


def _validate_grp(local_path):
    if not os.path.isfile(local_path):
        raise RuntimeError("Selected DUKE3D.GRP file does not exist.")
    if os.path.basename(local_path).lower() != "duke3d.grp":
        raise RuntimeError("Select a file named DUKE3D.GRP.")


def upload_mister_duke3d_grp(connection, local_path, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    if not _is_installed(connection):
        raise RuntimeError("MiSTer Duke3D is not installed.")
    _validate_grp(local_path)
    _ensure_remote_dir(connection, DUKE3D_REMOTE_GAME_DIR)
    log(f"Uploading DUKE3D.GRP to {DUKE3D_REMOTE_GRP}\n")
    sftp = connection.client.open_sftp()
    try:
        sftp.put(local_path, DUKE3D_REMOTE_GRP)
    finally:
        sftp.close()
    return {"grp_present": True}


def upload_mister_duke3d_grp_local(sd_root, local_path, log):
    if not _is_installed_local(sd_root):
        raise RuntimeError("MiSTer Duke3D is not installed.")
    _validate_grp(local_path)
    _ensure_local_dir(sd_root, DUKE3D_REMOTE_GAME_DIR)
    target = _local_path(sd_root, DUKE3D_REMOTE_GRP)
    log(f"Copying DUKE3D.GRP to {target}\n")
    shutil.copy2(local_path, target)
    return {"grp_present": True}


def uninstall_mister_duke3d(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    for path in (DUKE3D_REMOTE_LAUNCHER, DUKE3D_REMOTE_RBF, DUKE3D_REMOTE_VERSION_FILE):
        log(f"Removing {path}\n")
        connection.run_command(f"rm -f {_quote(path)}")
    for path in (
        "/media/fat/games/DUKE3D/bin",
        "/media/fat/games/DUKE3D/lib",
        "/media/fat/games/DUKE3D/README_INSTALL.txt",
    ):
        log(f"Removing {path}\n")
        connection.run_command(f"rm -rf {_quote(path)}")
    _write_remote_text(connection, REMOTE_INI_PATH, _remove_ini_sections(_read_remote_text(connection, REMOTE_INI_PATH)))
    _remove_if_empty_dir(connection, DUKE3D_REMOTE_GAME_DIR)
    log("Personal files in /media/fat/games/DUKE3D were preserved.\n")
    return {"uninstalled": True}


def uninstall_mister_duke3d_local(sd_root, log):
    for path in (
        DUKE3D_REMOTE_LAUNCHER,
        DUKE3D_REMOTE_RBF,
        DUKE3D_REMOTE_VERSION_FILE,
        "/media/fat/games/DUKE3D/bin",
        "/media/fat/games/DUKE3D/lib",
        "/media/fat/games/DUKE3D/README_INSTALL.txt",
    ):
        log(f"Removing {path}\n")
        _remove_local_path(sd_root, path)
    _write_local_text(sd_root, REMOTE_INI_PATH, _remove_ini_sections(_read_local_text(sd_root, REMOTE_INI_PATH)))
    try:
        _local_path(sd_root, DUKE3D_REMOTE_GAME_DIR).rmdir()
    except OSError:
        pass
    log("Personal files in /media/fat/games/DUKE3D were preserved.\n")
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

DUKE3D_DB_ID = "MultiDatabases/duke3d"
DUKE3D_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/duke3d/db.json"
DUKE3D_DB_FILES = (
    "/media/fat/Mister_duke3d",
    "/media/fat/_Other/DUKE3D.rbf",
    "/media/fat/games/DUKE3D/README_INSTALL.txt",
    "/media/fat/games/DUKE3D/bin/duke3d-mister",
    "/media/fat/games/DUKE3D/lib/ld-linux-armhf.so.3",
    "/media/fat/games/DUKE3D/lib/libc.so.6",
    "/media/fat/games/DUKE3D/lib/libdl.so.2",
    "/media/fat/games/DUKE3D/lib/libgcc_s.so.1",
    "/media/fat/games/DUKE3D/lib/libm.so.6",
    "/media/fat/games/DUKE3D/lib/libpthread.so.0",
    "/media/fat/games/DUKE3D/lib/librt.so.1",
    "/media/fat/games/DUKE3D/lib/libstdc++.so.6",
)


def _manual_duke3d_install(connection) -> bool:
    return bool(_is_installed(connection) and (
        _path_exists(connection, DUKE3D_REMOTE_VERSION_FILE)
        or not database_registered_online(connection, DUKE3D_DB_ID)
    ))


def _manual_duke3d_install_local(sd_root) -> bool:
    return bool(_is_installed_local(sd_root) and (
        _path_exists_local(sd_root, DUKE3D_REMOTE_VERSION_FILE)
        or not database_registered_local(sd_root, DUKE3D_DB_ID)
    ))


def _prepare_manual_duke3d_for_downloader(connection, log, manual=None):
    if manual is None:
        manual = _manual_duke3d_install(connection)
    if not manual:
        return False
    log("Detected a manual Companion installation; preparing it for Downloader...\n")
    for path in DUKE3D_DB_FILES:
        connection.run_command(f"rm -f {_quote(path)}")
        log(f"Removed legacy managed file: {path}\n")
    connection.run_command(f"rm -f {_quote(DUKE3D_REMOTE_VERSION_FILE)}")
    log(f"Preserved DUKE3D.GRP and personal files in {DUKE3D_REMOTE_GAME_DIR}\n")
    return True


def _prepare_manual_duke3d_for_downloader_local(sd_root, log, manual=None):
    if manual is None:
        manual = _manual_duke3d_install_local(sd_root)
    if not manual:
        return False
    log("Detected a manual Companion installation; preparing it for Downloader...\n")
    for path in DUKE3D_DB_FILES:
        _remove_local_path(sd_root, path)
        log(f"Removed legacy managed file: {path}\n")
    _remove_local_path(sd_root, DUKE3D_REMOTE_VERSION_FILE)
    log(f"Preserved DUKE3D.GRP and personal files in {DUKE3D_REMOTE_GAME_DIR}\n")
    return True


_manual_get_mister_duke3d_status = get_mister_duke3d_status
_manual_get_mister_duke3d_status_local = get_mister_duke3d_status_local


def _apply_duke3d_downloader_status(status, manual, update_available=False):
    status = dict(status)
    if manual:
        status.update({
            "update_available": True,
            "status_text": "▲ Manual install found",
            "install_label": "Migrate / Update",
            "install_enabled": True,
        })
    elif status.get("installed"):
        status.update({
            "installed_version": "",
            "latest_version": "",
            "update_available": bool(update_available),
            "status_text": "▲ Update available" if update_available else "✓ Installed",
            "install_label": "Update" if update_available else "Installed",
            "install_enabled": bool(update_available),
        })
    return status


def get_mister_duke3d_status(connection, check_latest=False):
    status = _manual_get_mister_duke3d_status(connection, check_latest=False)
    manual = _manual_duke3d_install(connection) if status.get("installed") else False
    update = False
    if check_latest and status.get("installed") and not manual:
        update = check_named_database_online(connection, DUKE3D_DB_ID)
    status = _apply_duke3d_downloader_status(status, manual, update)
    if status.get("installed") and not manual and not _duke3d_ini_present(_read_remote_text(connection, REMOTE_INI_PATH)):
        status.update({"status_text": "⚠ MiSTer.ini entry missing", "install_label": "Add INI Entry", "install_enabled": True, "update_available": False, "repair_action": True})
    return status


def get_mister_duke3d_status_local(sd_root, check_latest=False):
    status = _manual_get_mister_duke3d_status_local(sd_root, check_latest=False)
    manual = _manual_duke3d_install_local(sd_root) if status.get("installed") else False
    update = False
    if check_latest and status.get("installed") and not manual:
        update = check_named_database_local(sd_root, DUKE3D_DB_ID)
    status = _apply_duke3d_downloader_status(status, manual, update)
    if status.get("installed") and not manual and not _duke3d_ini_present(_read_local_text(sd_root, REMOTE_INI_PATH)):
        status.update({"status_text": "⚠ MiSTer.ini entry missing", "install_label": "Add INI Entry", "install_enabled": True, "update_available": False, "repair_action": True})
    return status


def _finish_duke3d_install_online(connection, log):
    _ensure_remote_dir(connection, DUKE3D_REMOTE_GAME_DIR)
    connection.run_command(f"chmod +x {_quote(DUKE3D_REMOTE_LAUNCHER)} {_quote(DUKE3D_REMOTE_BIN)}")
    _write_remote_text(connection, REMOTE_INI_PATH, _upsert_ini_sections(_read_remote_text(connection, REMOTE_INI_PATH)))
    connection.run_command(f"rm -f {_quote(DUKE3D_REMOTE_VERSION_FILE)}")
    log("Added/updated DUKE3D sections in MiSTer.ini\n")
    log(f"Preserved DUKE3D.GRP and personal files in {DUKE3D_REMOTE_GAME_DIR}\n")


def _finish_duke3d_install_local(sd_root, log):
    _ensure_local_dir(sd_root, DUKE3D_REMOTE_GAME_DIR)
    for path in (DUKE3D_REMOTE_LAUNCHER, DUKE3D_REMOTE_BIN):
        try:
            local_path = _local_path(sd_root, path)
            local_path.chmod(local_path.stat().st_mode | 0o111)
        except OSError:
            pass
    _write_local_text(sd_root, REMOTE_INI_PATH, _upsert_ini_sections(_read_local_text(sd_root, REMOTE_INI_PATH)))
    _remove_local_path(sd_root, DUKE3D_REMOTE_VERSION_FILE)
    log("Added/updated DUKE3D sections in MiSTer.ini\n")
    log(f"Preserved DUKE3D.GRP and personal files in {DUKE3D_REMOTE_GAME_DIR}\n")


def install_or_update_mister_duke3d(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    manual = _manual_duke3d_install(connection)
    if not manual and _manual_get_mister_duke3d_status(connection, check_latest=False).get("installed") and not _duke3d_ini_present(_read_remote_text(connection, REMOTE_INI_PATH)):
        _write_remote_text(connection, REMOTE_INI_PATH, _upsert_ini_sections(_read_remote_text(connection, REMOTE_INI_PATH)))
        return
    original = ensure_database_source_online(connection, DUKE3D_DB_ID, DUKE3D_DB_URL)
    try:
        _prepare_manual_duke3d_for_downloader(connection, log, manual=manual)
        _write_remote_text(connection, REMOTE_INI_PATH, _upsert_ini_sections(_read_remote_text(connection, REMOTE_INI_PATH)))
        run_named_database_online(connection, DUKE3D_DB_ID, log=log)
        _finish_duke3d_install_online(connection, log)
    except Exception:
        restore_online(connection, original)
        raise


def install_or_update_mister_duke3d_local(sd_root, log):
    manual = _manual_duke3d_install_local(sd_root)
    if not manual and _manual_get_mister_duke3d_status_local(sd_root, check_latest=False).get("installed") and not _duke3d_ini_present(_read_local_text(sd_root, REMOTE_INI_PATH)):
        _write_local_text(sd_root, REMOTE_INI_PATH, _upsert_ini_sections(_read_local_text(sd_root, REMOTE_INI_PATH)))
        return
    original = ensure_database_source_local(sd_root, DUKE3D_DB_ID, DUKE3D_DB_URL)
    try:
        _prepare_manual_duke3d_for_downloader_local(sd_root, log, manual=manual)
        _write_local_text(sd_root, REMOTE_INI_PATH, _upsert_ini_sections(_read_local_text(sd_root, REMOTE_INI_PATH)))
        run_named_database_local(sd_root, DUKE3D_DB_ID, log=log)
        _finish_duke3d_install_local(sd_root, log)
    except Exception:
        restore_local(sd_root, original)
        raise


def uninstall_mister_duke3d(connection, log, force=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    if _manual_duke3d_install(connection):
        _prepare_manual_duke3d_for_downloader(connection, log, manual=True)
        remove_database_source_online(connection, DUKE3D_DB_ID)
        _write_remote_text(connection, REMOTE_INI_PATH, _remove_ini_sections(_read_remote_text(connection, REMOTE_INI_PATH)))
        return {"uninstalled": True}
    original = ensure_database_source_online(connection, DUKE3D_DB_ID, DUKE3D_DB_URL)
    try:
        _write_remote_text(connection, REMOTE_INI_PATH, _remove_ini_sections(_read_remote_text(connection, REMOTE_INI_PATH)))
        native = uninstall_named_database_online(connection, DUKE3D_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(connection, DUKE3D_DB_ID, DUKE3D_DB_URL, filter_value="!all")
            run_named_database_online(connection, DUKE3D_DB_ID, log=log)
            remove_database_source_online(connection, DUKE3D_DB_ID)
        connection.run_command(f"rm -f {_quote(DUKE3D_REMOTE_VERSION_FILE)}")
    except Exception:
        restore_online(connection, original)
        raise
    return {"uninstalled": True}


def uninstall_mister_duke3d_local(sd_root, log, force=False):
    if _manual_duke3d_install_local(sd_root):
        _prepare_manual_duke3d_for_downloader_local(sd_root, log, manual=True)
        remove_database_source_local(sd_root, DUKE3D_DB_ID)
        _write_local_text(sd_root, REMOTE_INI_PATH, _remove_ini_sections(_read_local_text(sd_root, REMOTE_INI_PATH)))
        return {"uninstalled": True}
    original = ensure_database_source_local(sd_root, DUKE3D_DB_ID, DUKE3D_DB_URL)
    try:
        _write_local_text(sd_root, REMOTE_INI_PATH, _remove_ini_sections(_read_local_text(sd_root, REMOTE_INI_PATH)))
        native = uninstall_named_database_local(sd_root, DUKE3D_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(sd_root, DUKE3D_DB_ID, DUKE3D_DB_URL, filter_value="!all")
            run_named_database_local(sd_root, DUKE3D_DB_ID, log=log)
            remove_database_source_local(sd_root, DUKE3D_DB_ID)
        _remove_local_path(sd_root, DUKE3D_REMOTE_VERSION_FILE)
    except Exception:
        restore_local(sd_root, original)
        raise
    return {"uninstalled": True}

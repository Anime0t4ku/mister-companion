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
    _fetch_latest_zip_release,
    _glob_exists,
    _glob_exists_local,
    _normalize_ini_text_for_append,
    _path_exists,
    _path_exists_local,
    _quote,
    _read_local_text,
    _read_remote_text,
    _remove_glob,
    _remove_local_glob,
    _remove_local_path,
    _write_local_bytes,
    _write_local_text,
    _write_remote_text,
)


SONIC_MANIA_GITHUB_REPO = "kimchiman52/sonic-mania-mister"

SONIC_MANIA_REMOTE_RBF_DIR = "/media/fat/_Other"
SONIC_MANIA_REMOTE_GAME_DIR = "/media/fat/games/sonic-mania"
SONIC_MANIA_REMOTE_LAUNCHER_PATH = "/media/fat/MiSTer_SonicMania"
SONIC_MANIA_REMOTE_VERSION_FILE = "/media/fat/games/sonic-mania/.mister_companion_version"
SONIC_MANIA_REMOTE_DATA_RSDK_PATH = "/media/fat/games/sonic-mania/Data.rsdk"

SONIC_MANIA_INI_BLOCKS = (
    "[Sonic Mania]\n"
    "main=MiSTer_SonicMania\n"
    "\n"
    "[Sonic Mania (4:3)]\n"
    "main=MiSTer_SonicMania\n"
)

REMOTE_INI_PATH = "/media/fat/MiSTer.ini"


def _has_sonic_mania_rbf(connection) -> bool:
    return _glob_exists(connection, "/media/fat/_Other/Sonic_Mania*.rbf")


def _has_sonic_mania_rbf_local(sd_root: str) -> bool:
    return _glob_exists_local(sd_root, "/media/fat/_Other/Sonic_Mania*.rbf")


def _is_sonic_mania_installed(connection) -> bool:
    return (
        _has_sonic_mania_rbf(connection)
        and _path_exists(connection, SONIC_MANIA_REMOTE_GAME_DIR)
        and _path_exists(connection, SONIC_MANIA_REMOTE_LAUNCHER_PATH)
    )


def _is_sonic_mania_installed_local(sd_root: str) -> bool:
    return (
        _has_sonic_mania_rbf_local(sd_root)
        and _path_exists_local(sd_root, SONIC_MANIA_REMOTE_GAME_DIR)
        and _path_exists_local(sd_root, SONIC_MANIA_REMOTE_LAUNCHER_PATH)
    )


def _fetch_latest_sonic_mania_release():
    return _fetch_latest_zip_release(
        SONIC_MANIA_GITHUB_REPO,
        "Sonic Mania MiSTer",
    )


def _read_installed_sonic_mania_version(connection) -> str:
    return _read_remote_text(connection, SONIC_MANIA_REMOTE_VERSION_FILE).strip()


def _write_installed_sonic_mania_version(connection, version: str):
    _ensure_remote_dir(connection, posixpath.dirname(SONIC_MANIA_REMOTE_VERSION_FILE))
    _write_remote_text(connection, SONIC_MANIA_REMOTE_VERSION_FILE, version.strip() + "\n")


def _read_installed_sonic_mania_version_local(sd_root: str) -> str:
    return _read_local_text(sd_root, SONIC_MANIA_REMOTE_VERSION_FILE).strip()


def _write_installed_sonic_mania_version_local(sd_root: str, version: str):
    _ensure_local_dir(sd_root, posixpath.dirname(SONIC_MANIA_REMOTE_VERSION_FILE))
    _write_local_text(sd_root, SONIC_MANIA_REMOTE_VERSION_FILE, version.strip() + "\n")


def _ensure_sonic_mania_ini_blocks(connection) -> bool:
    current = _read_remote_text(connection, REMOTE_INI_PATH)
    normalized = current.replace("\r\n", "\n")

    has_16_9 = "[Sonic Mania]" in normalized and "main=MiSTer_SonicMania" in normalized
    has_4_3 = "[Sonic Mania (4:3)]" in normalized and "main=MiSTer_SonicMania" in normalized

    if has_16_9 and has_4_3:
        return False

    updated = normalized

    if not has_16_9:
        updated = _normalize_ini_text_for_append(updated) + "[Sonic Mania]\nmain=MiSTer_SonicMania\n"

    if not has_4_3:
        updated = _normalize_ini_text_for_append(updated) + "[Sonic Mania (4:3)]\nmain=MiSTer_SonicMania\n"

    _write_remote_text(connection, REMOTE_INI_PATH, updated)
    return True


def _ensure_sonic_mania_ini_blocks_local(sd_root: str) -> bool:
    current = _read_local_text(sd_root, REMOTE_INI_PATH)
    normalized = current.replace("\r\n", "\n")

    has_16_9 = "[Sonic Mania]" in normalized and "main=MiSTer_SonicMania" in normalized
    has_4_3 = "[Sonic Mania (4:3)]" in normalized and "main=MiSTer_SonicMania" in normalized

    if has_16_9 and has_4_3:
        return False

    updated = normalized

    if not has_16_9:
        updated = _normalize_ini_text_for_append(updated) + "[Sonic Mania]\nmain=MiSTer_SonicMania\n"

    if not has_4_3:
        updated = _normalize_ini_text_for_append(updated) + "[Sonic Mania (4:3)]\nmain=MiSTer_SonicMania\n"

    _write_local_text(sd_root, REMOTE_INI_PATH, updated)
    return True


def _remove_sonic_mania_ini_blocks(connection) -> bool:
    current = _read_remote_text(connection, REMOTE_INI_PATH)
    if not current:
        return False

    normalized = current.replace("\r\n", "\n")

    pattern = re.compile(
        r"(?:\n{0,2})\[Sonic Mania(?: \(4:3\))?\]\nmain=MiSTer_SonicMania\n?",
        re.MULTILINE,
    )
    updated = re.sub(pattern, "\n", normalized)
    updated = re.sub(r"\n{3,}", "\n\n", updated).rstrip("\n")

    if updated:
        updated += "\n"

    if updated == normalized:
        return False

    _write_remote_text(connection, REMOTE_INI_PATH, updated)
    return True


def _remove_sonic_mania_ini_blocks_local(sd_root: str) -> bool:
    current = _read_local_text(sd_root, REMOTE_INI_PATH)
    if not current:
        return False

    normalized = current.replace("\r\n", "\n")

    pattern = re.compile(
        r"(?:\n{0,2})\[Sonic Mania(?: \(4:3\))?\]\nmain=MiSTer_SonicMania\n?",
        re.MULTILINE,
    )
    updated = re.sub(pattern, "\n", normalized)
    updated = re.sub(r"\n{3,}", "\n\n", updated).rstrip("\n")

    if updated:
        updated += "\n"

    if updated == normalized:
        return False

    _write_local_text(sd_root, REMOTE_INI_PATH, updated)
    return True


def get_sonic_mania_status(connection, check_latest: bool = False):
    if not connection.is_connected():
        return {
            "installed": False,
            "installed_version": "",
            "latest_version": "",
            "latest_error": "",
            "update_available": False,
            "data_rsdk_present": False,
            "status_text": "Unknown",
            "install_label": "Install",
            "install_enabled": False,
            "upload_enabled": False,
            "uninstall_enabled": False,
        }

    latest_version = ""
    latest_error = ""

    if check_latest:
        try:
            latest = _fetch_latest_sonic_mania_release()
            latest_version = latest["version"]
        except Exception as exc:
            latest_error = str(exc)

    installed = _is_sonic_mania_installed(connection)
    installed_version = _read_installed_sonic_mania_version(connection) if installed else ""
    data_rsdk_present = _path_exists(connection, SONIC_MANIA_REMOTE_DATA_RSDK_PATH) if installed else False

    update_available = False
    if check_latest:
        if installed and latest_version and installed_version:
            update_available = installed_version != latest_version
        elif installed and latest_version and not installed_version:
            update_available = True

    if not installed:
        status_text = "✗ Not installed"
        install_label = "Install"
        install_enabled = True
        upload_enabled = False
        uninstall_enabled = False
    elif update_available:
        status_text = f"▲ Update available ({installed_version or 'unknown'} → {latest_version})"
        install_label = "Update"
        install_enabled = True
        upload_enabled = not data_rsdk_present
        uninstall_enabled = True
    else:
        version_display = installed_version or "unknown"
        status_text = f"✓ Installed ({version_display})"
        install_label = "Installed"
        install_enabled = False
        upload_enabled = not data_rsdk_present
        uninstall_enabled = True

    if latest_error and check_latest:
        status_text = f"{status_text} (update check failed: {latest_error})"

    return {
        "installed": installed,
        "installed_version": installed_version,
        "latest_version": latest_version,
        "latest_error": latest_error,
        "update_available": update_available,
        "data_rsdk_present": data_rsdk_present,
        "status_text": status_text,
        "install_label": install_label,
        "install_enabled": install_enabled,
        "upload_enabled": upload_enabled,
        "uninstall_enabled": uninstall_enabled,
    }


def get_sonic_mania_status_local(sd_root: str, check_latest: bool = False):
    latest_version = ""
    latest_error = ""

    if check_latest:
        try:
            latest = _fetch_latest_sonic_mania_release()
            latest_version = latest["version"]
        except Exception as exc:
            latest_error = str(exc)

    installed = _is_sonic_mania_installed_local(sd_root)
    installed_version = _read_installed_sonic_mania_version_local(sd_root) if installed else ""
    data_rsdk_present = _path_exists_local(sd_root, SONIC_MANIA_REMOTE_DATA_RSDK_PATH) if installed else False

    update_available = False
    if check_latest:
        if installed and latest_version and installed_version:
            update_available = installed_version != latest_version
        elif installed and latest_version and not installed_version:
            update_available = True

    if not installed:
        status_text = "✗ Not installed"
        install_label = "Install"
        install_enabled = True
        upload_enabled = False
        uninstall_enabled = False
    elif update_available:
        status_text = f"▲ Update available ({installed_version or 'unknown'} → {latest_version})"
        install_label = "Update"
        install_enabled = True
        upload_enabled = not data_rsdk_present
        uninstall_enabled = True
    else:
        version_display = installed_version or "unknown"
        status_text = f"✓ Installed ({version_display})"
        install_label = "Installed"
        install_enabled = False
        upload_enabled = not data_rsdk_present
        uninstall_enabled = True

    if latest_error and check_latest:
        status_text = f"{status_text} (update check failed: {latest_error})"

    return {
        "installed": installed,
        "installed_version": installed_version,
        "latest_version": latest_version,
        "latest_error": latest_error,
        "update_available": update_available,
        "data_rsdk_present": data_rsdk_present,
        "status_text": status_text,
        "install_label": install_label,
        "install_enabled": install_enabled,
        "upload_enabled": upload_enabled,
        "uninstall_enabled": uninstall_enabled,
    }


def _collect_sonic_mania_payloads(zf):
    members = [m for m in zf.infolist() if not m.is_dir()]
    if not members:
        raise RuntimeError("The Sonic Mania MiSTer ZIP archive is empty.")

    payloads = []
    for member in members:
        name = member.filename.replace("\\", "/")
        basename = posixpath.basename(name)
        lower_basename = basename.lower()

        if not basename:
            continue

        if lower_basename in ("readme.txt", "readme.md", "license.txt", "license.md"):
            continue

        payloads.append(member)

    return payloads


def install_or_update_sonic_mania(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    latest = _fetch_latest_sonic_mania_release()
    version = latest["version"]
    zip_url = latest["zip_url"]

    log(f"Latest version on GitHub: {version}\n")
    log(f"Downloading: {zip_url}\n")

    response = requests.get(zip_url, timeout=60)
    response.raise_for_status()
    archive_data = response.content

    log(f"Downloaded {len(archive_data)} bytes.\n")

    with zipfile.ZipFile(io.BytesIO(archive_data)) as zf:
        log("Inspecting archive contents...\n")
        payloads = _collect_sonic_mania_payloads(zf)

        sftp = connection.client.open_sftp()
        try:
            _ensure_remote_dir(connection, SONIC_MANIA_REMOTE_RBF_DIR)
            _ensure_remote_dir(connection, SONIC_MANIA_REMOTE_GAME_DIR)

            log("Removing old Sonic Mania RBF files from /media/fat/_Other...\n")
            _remove_glob(connection, "/media/fat/_Other/Sonic_Mania*.rbf")

            for member in payloads:
                name = member.filename.replace("\\", "/")
                basename = posixpath.basename(name)
                data = zf.read(member)

                if basename == "MiSTer_SonicMania":
                    log(f"Uploading launcher: {SONIC_MANIA_REMOTE_LAUNCHER_PATH}\n")
                    with sftp.open(SONIC_MANIA_REMOTE_LAUNCHER_PATH, "wb") as remote_file:
                        remote_file.write(data)
                    continue

                parts = [p for p in name.split("/") if p]
                if not parts:
                    continue

                if "_Other" in parts:
                    idx = parts.index("_Other")
                    relative = parts[idx + 1:]
                    if not relative:
                        continue

                    remote_path = posixpath.join("/media/fat/_Other", *relative)
                    _ensure_remote_dir(connection, posixpath.dirname(remote_path))
                    log(f"Merging into /media/fat/_Other: {'/'.join(relative)}\n")
                    with sftp.open(remote_path, "wb") as remote_file:
                        remote_file.write(data)
                    continue

                if "games" in parts:
                    idx = parts.index("games")
                    relative = parts[idx + 1:]
                    if not relative:
                        continue

                    if relative == ["sonic-mania", "Data.rsdk"]:
                        log("Skipping bundled Data.rsdk placeholder. Use Upload Data.rsdk instead.\n")
                        continue

                    remote_path = posixpath.join("/media/fat/games", *relative)
                    _ensure_remote_dir(connection, posixpath.dirname(remote_path))
                    log(f"Merging into /media/fat/games: {'/'.join(relative)}\n")
                    with sftp.open(remote_path, "wb") as remote_file:
                        remote_file.write(data)
                    continue

                log(f"Skipping unhandled file: {name}\n")

        finally:
            sftp.close()

    connection.run_command(f"chmod +x {_quote(SONIC_MANIA_REMOTE_LAUNCHER_PATH)}")
    connection.run_command(f"chmod +x {_quote('/media/fat/games/sonic-mania/bin/RSDKv5U')}")
    connection.run_command(f"chmod +x {_quote('/media/fat/games/sonic-mania/scripts/run-mania.sh')}")

    ini_added = _ensure_sonic_mania_ini_blocks(connection)
    if ini_added:
        log("Added Sonic Mania blocks to MiSTer.ini\n")
    else:
        log("Sonic Mania blocks already present in MiSTer.ini\n")

    _write_installed_sonic_mania_version(connection, version)
    log(f"Stored installed version marker: {version}\n")

    return {
        "installed_version": version,
    }


def install_or_update_sonic_mania_local(sd_root: str, log):
    latest = _fetch_latest_sonic_mania_release()
    version = latest["version"]
    zip_url = latest["zip_url"]

    log(f"Latest version on GitHub: {version}\n")
    log(f"Downloading: {zip_url}\n")

    response = requests.get(zip_url, timeout=60)
    response.raise_for_status()
    archive_data = response.content

    log(f"Downloaded {len(archive_data)} bytes.\n")

    with zipfile.ZipFile(io.BytesIO(archive_data)) as zf:
        log("Inspecting archive contents...\n")
        payloads = _collect_sonic_mania_payloads(zf)

        _ensure_local_dir(sd_root, SONIC_MANIA_REMOTE_RBF_DIR)
        _ensure_local_dir(sd_root, SONIC_MANIA_REMOTE_GAME_DIR)

        log("Removing old Sonic Mania RBF files from /media/fat/_Other...\n")
        _remove_local_glob(sd_root, "/media/fat/_Other/Sonic_Mania*.rbf")

        for member in payloads:
            name = member.filename.replace("\\", "/")
            basename = posixpath.basename(name)
            data = zf.read(member)

            if basename == "MiSTer_SonicMania":
                log(f"Writing launcher: {SONIC_MANIA_REMOTE_LAUNCHER_PATH}\n")
                _write_local_bytes(sd_root, SONIC_MANIA_REMOTE_LAUNCHER_PATH, data)
                continue

            parts = [p for p in name.split("/") if p]
            if not parts:
                continue

            if "_Other" in parts:
                idx = parts.index("_Other")
                relative = parts[idx + 1:]
                if not relative:
                    continue

                local_path = posixpath.join("/media/fat/_Other", *relative)
                log(f"Merging into /media/fat/_Other: {'/'.join(relative)}\n")
                _write_local_bytes(sd_root, local_path, data)
                continue

            if "games" in parts:
                idx = parts.index("games")
                relative = parts[idx + 1:]
                if not relative:
                    continue

                if relative == ["sonic-mania", "Data.rsdk"]:
                    log("Skipping bundled Data.rsdk placeholder. Use Upload Data.rsdk instead.\n")
                    continue

                local_path = posixpath.join("/media/fat/games", *relative)
                log(f"Merging into /media/fat/games: {'/'.join(relative)}\n")
                _write_local_bytes(sd_root, local_path, data)
                continue

            log(f"Skipping unhandled file: {name}\n")

    ini_added = _ensure_sonic_mania_ini_blocks_local(sd_root)
    if ini_added:
        log("Added Sonic Mania blocks to MiSTer.ini\n")
    else:
        log("Sonic Mania blocks already present in MiSTer.ini\n")

    _write_installed_sonic_mania_version_local(sd_root, version)
    log(f"Stored installed version marker: {version}\n")

    return {
        "installed_version": version,
    }


def upload_sonic_mania_data_rsdk(connection, local_path: str, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    if not os.path.isfile(local_path):
        raise RuntimeError("Selected Data.rsdk file does not exist.")

    local_name = os.path.basename(local_path)
    if local_name.lower() != "data.rsdk":
        log(f"Warning: selected file name is {local_name}, expected Data.rsdk\n")

    if not _is_sonic_mania_installed(connection):
        raise RuntimeError("Sonic Mania MiSTer is not installed.")

    _ensure_remote_dir(connection, SONIC_MANIA_REMOTE_GAME_DIR)

    file_size = os.path.getsize(local_path)
    log(f"Uploading Data.rsdk to {SONIC_MANIA_REMOTE_DATA_RSDK_PATH}\n")
    log(f"File size: {file_size} bytes\n")

    last_percent = {"value": -1}

    def progress_callback(transferred, total):
        if total <= 0:
            return
        percent = int((transferred / total) * 100)
        if percent != last_percent["value"]:
            last_percent["value"] = percent
            log(f"[PROGRESS] {percent}%")

    sftp = connection.client.open_sftp()
    try:
        sftp.put(local_path, SONIC_MANIA_REMOTE_DATA_RSDK_PATH, callback=progress_callback)
    finally:
        sftp.close()

    log("Upload completed.\n")
    return {"data_rsdk_present": True}


def upload_sonic_mania_data_rsdk_local(sd_root: str, local_path: str, log):
    if not os.path.isfile(local_path):
        raise RuntimeError("Selected Data.rsdk file does not exist.")

    local_name = os.path.basename(local_path)
    if local_name.lower() != "data.rsdk":
        log(f"Warning: selected file name is {local_name}, expected Data.rsdk\n")

    if not _is_sonic_mania_installed_local(sd_root):
        raise RuntimeError("Sonic Mania MiSTer is not installed.")

    _ensure_local_dir(sd_root, SONIC_MANIA_REMOTE_GAME_DIR)

    file_size = os.path.getsize(local_path)
    target = _local_target_path(sd_root, SONIC_MANIA_REMOTE_DATA_RSDK_PATH)

    log(f"Copying Data.rsdk to {SONIC_MANIA_REMOTE_DATA_RSDK_PATH}\n")
    log(f"File size: {file_size} bytes\n")

    shutil.copy2(local_path, target)

    log("Copy completed.\n")
    return {"data_rsdk_present": True}


def _local_target_path(sd_root: str, remote_path: str):
    clean = remote_path
    if clean.startswith("/media/fat/"):
        clean = clean[len("/media/fat/"):]
    elif clean.startswith("/"):
        clean = clean.lstrip("/")

    return os.path.join(str(sd_root), clean)


def uninstall_sonic_mania(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log("Removing Sonic Mania RBF files from /media/fat/_Other\n")
    _remove_glob(connection, "/media/fat/_Other/Sonic_Mania*.rbf")

    log(f"Removing {SONIC_MANIA_REMOTE_LAUNCHER_PATH}\n")
    connection.run_command(f"rm -f {_quote(SONIC_MANIA_REMOTE_LAUNCHER_PATH)}")

    if _path_exists(connection, SONIC_MANIA_REMOTE_VERSION_FILE):
        log(f"Removing version marker: {SONIC_MANIA_REMOTE_VERSION_FILE}\n")
        connection.run_command(f"rm -f {_quote(SONIC_MANIA_REMOTE_VERSION_FILE)}")

    log(f"Removing {SONIC_MANIA_REMOTE_GAME_DIR}\n")
    connection.run_command(f"rm -rf {_quote(SONIC_MANIA_REMOTE_GAME_DIR)}")

    removed_ini = _remove_sonic_mania_ini_blocks(connection)
    if removed_ini:
        log("Removed Sonic Mania blocks from MiSTer.ini\n")
    else:
        log("No Sonic Mania blocks found in MiSTer.ini\n")

    return {"uninstalled": True}


def uninstall_sonic_mania_local(sd_root: str, log):
    log("Removing Sonic Mania RBF files from /media/fat/_Other\n")
    _remove_local_glob(sd_root, "/media/fat/_Other/Sonic_Mania*.rbf")

    log(f"Removing {SONIC_MANIA_REMOTE_LAUNCHER_PATH}\n")
    _remove_local_path(sd_root, SONIC_MANIA_REMOTE_LAUNCHER_PATH)

    if _path_exists_local(sd_root, SONIC_MANIA_REMOTE_VERSION_FILE):
        log(f"Removing version marker: {SONIC_MANIA_REMOTE_VERSION_FILE}\n")
        _remove_local_path(sd_root, SONIC_MANIA_REMOTE_VERSION_FILE)

    log(f"Removing {SONIC_MANIA_REMOTE_GAME_DIR}\n")
    _remove_local_path(sd_root, SONIC_MANIA_REMOTE_GAME_DIR)

    removed_ini = _remove_sonic_mania_ini_blocks_local(sd_root)
    if removed_ini:
        log("Removed Sonic Mania blocks from MiSTer.ini\n")
    else:
        log("No Sonic Mania blocks found in MiSTer.ini\n")

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

SONIC_MANIA_DB_ID = "MultiDatabases/sonic-mania"
SONIC_MANIA_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/sonic-mania/db.json"
SONIC_MANIA_DB_FILES = (
    SONIC_MANIA_REMOTE_LAUNCHER_PATH,
    "/media/fat/games/sonic-mania/Data.rsdk.MISSING.txt",
    "/media/fat/games/sonic-mania/bin/RSDKv5U",
    "/media/fat/games/sonic-mania/lib/libtheora.so.0",
    "/media/fat/games/sonic-mania/lib/libtheoradec.so.1",
    "/media/fat/games/sonic-mania/scripts/run-mania.sh",
)


def _manual_sonic_mania_install(connection):
    present = bool(_has_sonic_mania_rbf(connection) or _path_exists(connection, SONIC_MANIA_REMOTE_LAUNCHER_PATH))
    return bool(present and (_path_exists(connection, SONIC_MANIA_REMOTE_VERSION_FILE) or not database_registered_online(connection, SONIC_MANIA_DB_ID)))


def _manual_sonic_mania_install_local(sd_root):
    present = bool(_has_sonic_mania_rbf_local(sd_root) or _path_exists_local(sd_root, SONIC_MANIA_REMOTE_LAUNCHER_PATH))
    return bool(present and (_path_exists_local(sd_root, SONIC_MANIA_REMOTE_VERSION_FILE) or not database_registered_local(sd_root, SONIC_MANIA_DB_ID)))


def _prepare_manual_sonic_mania_for_downloader(connection, log, manual=None):
    if manual is None:
        manual = _manual_sonic_mania_install(connection)
    if not manual:
        return False
    log("Detected a manual Companion installation; preparing it for Downloader...\n")
    _remove_glob(connection, "/media/fat/_Other/Sonic_Mania*.rbf")
    for path in SONIC_MANIA_DB_FILES:
        connection.run_command(f"rm -f {_quote(path)}")
    connection.run_command(f"rm -f {_quote(SONIC_MANIA_REMOTE_VERSION_FILE)}")
    log(f"Preserved user game data: {SONIC_MANIA_REMOTE_DATA_RSDK_PATH}\n")
    return True


def _prepare_manual_sonic_mania_for_downloader_local(sd_root, log, manual=None):
    if manual is None:
        manual = _manual_sonic_mania_install_local(sd_root)
    if not manual:
        return False
    log("Detected a manual Companion installation; preparing it for Downloader...\n")
    _remove_local_glob(sd_root, "/media/fat/_Other/Sonic_Mania*.rbf")
    for path in SONIC_MANIA_DB_FILES:
        _remove_local_path(sd_root, path)
    _remove_local_path(sd_root, SONIC_MANIA_REMOTE_VERSION_FILE)
    log(f"Preserved user game data: {SONIC_MANIA_REMOTE_DATA_RSDK_PATH}\n")
    return True


_manual_get_sonic_mania_status = get_sonic_mania_status
_manual_get_sonic_mania_status_local = get_sonic_mania_status_local


def _apply_sonic_mania_downloader_status(status, manual, update_available=False):
    status = dict(status)
    if manual:
        status.update({"update_available": True, "status_text": "▲ Manual install found", "install_label": "Migrate / Update", "install_enabled": True})
    elif status.get("installed"):
        status.update({"installed_version": "", "latest_version": "", "update_available": bool(update_available), "status_text": "▲ Update available" if update_available else "✓ Installed", "install_label": "Update" if update_available else "Installed", "install_enabled": bool(update_available)})
    return status


def get_sonic_mania_status(connection, check_latest=False):
    status = _manual_get_sonic_mania_status(connection, check_latest=False)
    manual = _manual_sonic_mania_install(connection)
    update = bool(check_latest and status.get("installed") and not manual and check_named_database_online(connection, SONIC_MANIA_DB_ID))
    return _apply_sonic_mania_downloader_status(status, manual, update)


def get_sonic_mania_status_local(sd_root, check_latest=False):
    status = _manual_get_sonic_mania_status_local(sd_root, check_latest=False)
    manual = _manual_sonic_mania_install_local(sd_root)
    update = bool(check_latest and status.get("installed") and not manual and check_named_database_local(sd_root, SONIC_MANIA_DB_ID))
    return _apply_sonic_mania_downloader_status(status, manual, update)


def install_or_update_sonic_mania(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    manual = _manual_sonic_mania_install(connection)
    original = ensure_database_source_online(connection, SONIC_MANIA_DB_ID, SONIC_MANIA_DB_URL)
    try:
        _prepare_manual_sonic_mania_for_downloader(connection, log, manual=manual)
        run_named_database_online(connection, SONIC_MANIA_DB_ID, log=log)
        connection.run_command(f"chmod +x {_quote(SONIC_MANIA_REMOTE_LAUNCHER_PATH)} {_quote('/media/fat/games/sonic-mania/bin/RSDKv5U')} {_quote('/media/fat/games/sonic-mania/scripts/run-mania.sh')}")
        _ensure_sonic_mania_ini_blocks(connection)
        connection.run_command(f"rm -f {_quote(SONIC_MANIA_REMOTE_VERSION_FILE)}")
    except Exception:
        restore_online(connection, original)
        raise


def install_or_update_sonic_mania_local(sd_root, log):
    manual = _manual_sonic_mania_install_local(sd_root)
    original = ensure_database_source_local(sd_root, SONIC_MANIA_DB_ID, SONIC_MANIA_DB_URL)
    try:
        _prepare_manual_sonic_mania_for_downloader_local(sd_root, log, manual=manual)
        run_named_database_local(sd_root, SONIC_MANIA_DB_ID, log=log)
        _ensure_sonic_mania_ini_blocks_local(sd_root)
        _remove_local_path(sd_root, SONIC_MANIA_REMOTE_VERSION_FILE)
    except Exception:
        restore_local(sd_root, original)
        raise


def uninstall_sonic_mania(connection, log, force=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    if _manual_sonic_mania_install(connection):
        _prepare_manual_sonic_mania_for_downloader(connection, log, manual=True)
        remove_database_source_online(connection, SONIC_MANIA_DB_ID)
        _remove_sonic_mania_ini_blocks(connection)
        return {"uninstalled": True}
    original = ensure_database_source_online(connection, SONIC_MANIA_DB_ID, SONIC_MANIA_DB_URL)
    try:
        native = uninstall_named_database_online(connection, SONIC_MANIA_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(connection, SONIC_MANIA_DB_ID, SONIC_MANIA_DB_URL, filter_value="!all")
            run_named_database_online(connection, SONIC_MANIA_DB_ID, log=log)
            remove_database_source_online(connection, SONIC_MANIA_DB_ID)
        _remove_sonic_mania_ini_blocks(connection)
        connection.run_command(f"rm -f {_quote(SONIC_MANIA_REMOTE_VERSION_FILE)}")
    except Exception:
        restore_online(connection, original)
        raise
    return {"uninstalled": True}


def uninstall_sonic_mania_local(sd_root, log, force=False):
    if _manual_sonic_mania_install_local(sd_root):
        _prepare_manual_sonic_mania_for_downloader_local(sd_root, log, manual=True)
        remove_database_source_local(sd_root, SONIC_MANIA_DB_ID)
        _remove_sonic_mania_ini_blocks_local(sd_root)
        return {"uninstalled": True}
    original = ensure_database_source_local(sd_root, SONIC_MANIA_DB_ID, SONIC_MANIA_DB_URL)
    try:
        native = uninstall_named_database_local(sd_root, SONIC_MANIA_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(sd_root, SONIC_MANIA_DB_ID, SONIC_MANIA_DB_URL, filter_value="!all")
            run_named_database_local(sd_root, SONIC_MANIA_DB_ID, log=log)
            remove_database_source_local(sd_root, SONIC_MANIA_DB_ID)
        _remove_sonic_mania_ini_blocks_local(sd_root)
        _remove_local_path(sd_root, SONIC_MANIA_REMOTE_VERSION_FILE)
    except Exception:
        restore_local(sd_root, original)
        raise
    return {"uninstalled": True}

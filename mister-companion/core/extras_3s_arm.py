import io
import os
import posixpath
import re
import zipfile

import requests

from core.extras_common import (
    _copy_local_file_to_sd,
    _ensure_local_dir,
    _ensure_remote_dir,
    _fetch_latest_zip_release,
    _local_path,
    _normalize_ini_text_for_append,
    _path_exists,
    _path_exists_local,
    _quote,
    _read_local_text,
    _read_remote_text,
    _remove_local_path,
    _write_local_bytes,
    _write_local_text,
    _write_remote_text,
)


GITHUB_3SX_REPO = "kimchiman52/3s-mister-arm"

REMOTE_RBF_PATH = "/media/fat/_Other/3S-ARM.rbf"
REMOTE_GAME_DIR = "/media/fat/games/3s-arm"
REMOTE_RESOURCES_DIR = "/media/fat/games/3s-arm/resources"
REMOTE_LAUNCHER_PATH = "/media/fat/MiSTer_3S-ARM"
REMOTE_VERSION_FILE = "/media/fat/games/3s-arm/.mister_companion_version"
REMOTE_INI_PATH = "/media/fat/MiSTer.ini"
REMOTE_AFS_PATH = "/media/fat/games/3s-arm/resources/SF33RD.AFS"

OLD_REMOTE_RBF_PATH = "/media/fat/_Other/3SX.rbf"
OLD_REMOTE_GAME_DIR = "/media/fat/games/3sx"
OLD_REMOTE_RESOURCES_DIR = "/media/fat/games/3sx/resources"
OLD_REMOTE_LAUNCHER_PATH = "/media/fat/MiSTer_3SX"
OLD_REMOTE_VERSION_FILE = "/media/fat/games/3sx/.mister_companion_version"
OLD_REMOTE_AFS_PATH = "/media/fat/games/3sx/resources/SF33RD.AFS"

INI_BLOCK = "[3S-ARM]\nmain=MiSTer_3S-ARM\n"


def _is_3sx_installed(connection) -> bool:
    return (
        _path_exists(connection, REMOTE_RBF_PATH)
        and _path_exists(connection, REMOTE_GAME_DIR)
        and _path_exists(connection, REMOTE_LAUNCHER_PATH)
    )


def _is_old_3sx_installed(connection) -> bool:
    return (
        _path_exists(connection, OLD_REMOTE_RBF_PATH)
        and _path_exists(connection, OLD_REMOTE_GAME_DIR)
        and _path_exists(connection, OLD_REMOTE_LAUNCHER_PATH)
    )


def _is_3sx_installed_local(sd_root: str) -> bool:
    return (
        _path_exists_local(sd_root, REMOTE_RBF_PATH)
        and _path_exists_local(sd_root, REMOTE_GAME_DIR)
        and _path_exists_local(sd_root, REMOTE_LAUNCHER_PATH)
    )


def _is_old_3sx_installed_local(sd_root: str) -> bool:
    return (
        _path_exists_local(sd_root, OLD_REMOTE_RBF_PATH)
        and _path_exists_local(sd_root, OLD_REMOTE_GAME_DIR)
        and _path_exists_local(sd_root, OLD_REMOTE_LAUNCHER_PATH)
    )


def _fetch_latest_release():
    return _fetch_latest_zip_release(
        GITHUB_3SX_REPO,
        "3s-mister-arm",
    )


def _read_installed_version(connection) -> str:
    version = _read_remote_text(connection, REMOTE_VERSION_FILE).strip()
    if version:
        return version
    return _read_remote_text(connection, OLD_REMOTE_VERSION_FILE).strip()


def _write_installed_version(connection, version: str):
    _ensure_remote_dir(connection, posixpath.dirname(REMOTE_VERSION_FILE))
    _write_remote_text(connection, REMOTE_VERSION_FILE, version.strip() + "\n")


def _read_installed_version_local(sd_root: str) -> str:
    version = _read_local_text(sd_root, REMOTE_VERSION_FILE).strip()
    if version:
        return version
    return _read_local_text(sd_root, OLD_REMOTE_VERSION_FILE).strip()


def _write_installed_version_local(sd_root: str, version: str):
    _ensure_local_dir(sd_root, posixpath.dirname(REMOTE_VERSION_FILE))
    _write_local_text(sd_root, REMOTE_VERSION_FILE, version.strip() + "\n")


def _ensure_ini_block(connection) -> bool:
    current = _read_remote_text(connection, REMOTE_INI_PATH)
    normalized = current.replace("\r\n", "\n")

    if "[3S-ARM]" in normalized and "main=MiSTer_3S-ARM" in normalized:
        return False

    old_pattern = re.compile(
        r"(?:\n{0,2})\[3SX\]\nmain=MiSTer_3SX\n(?:video_mode=8\n?)?",
        re.MULTILINE,
    )
    normalized = re.sub(old_pattern, "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).rstrip("\n")

    updated = _normalize_ini_text_for_append(normalized) + INI_BLOCK
    _write_remote_text(connection, REMOTE_INI_PATH, updated)
    return True


def _remove_ini_block(connection) -> bool:
    current = _read_remote_text(connection, REMOTE_INI_PATH)
    if not current:
        return False

    normalized = current.replace("\r\n", "\n")

    pattern = re.compile(
        r"(?:\n{0,2})\[(?:3SX|3S-ARM)\]\nmain=(?:MiSTer_3SX|MiSTer_3S-ARM)\n(?:video_mode=8\n?)?",
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


def _ensure_ini_block_local(sd_root: str) -> bool:
    current = _read_local_text(sd_root, REMOTE_INI_PATH)
    normalized = current.replace("\r\n", "\n")

    if "[3S-ARM]" in normalized and "main=MiSTer_3S-ARM" in normalized:
        return False

    old_pattern = re.compile(
        r"(?:\n{0,2})\[3SX\]\nmain=MiSTer_3SX\n(?:video_mode=8\n?)?",
        re.MULTILINE,
    )
    normalized = re.sub(old_pattern, "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).rstrip("\n")

    updated = _normalize_ini_text_for_append(normalized) + INI_BLOCK
    _write_local_text(sd_root, REMOTE_INI_PATH, updated)
    return True


def _remove_ini_block_local(sd_root: str) -> bool:
    current = _read_local_text(sd_root, REMOTE_INI_PATH)
    if not current:
        return False

    normalized = current.replace("\r\n", "\n")

    pattern = re.compile(
        r"(?:\n{0,2})\[(?:3SX|3S-ARM)\]\nmain=(?:MiSTer_3SX|MiSTer_3S-ARM)\n(?:video_mode=8\n?)?",
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


def _migrate_old_install(connection, log):
    old_present = _is_old_3sx_installed(connection)
    if not old_present:
        return False

    log("Detected legacy 3SX install, migrating to 3S-ARM layout...\n")

    _ensure_remote_dir(connection, "/media/fat/_Other")
    _ensure_remote_dir(connection, "/media/fat/games")

    if _path_exists(connection, OLD_REMOTE_LAUNCHER_PATH) and not _path_exists(connection, REMOTE_LAUNCHER_PATH):
        log(f"Renaming launcher: {OLD_REMOTE_LAUNCHER_PATH} -> {REMOTE_LAUNCHER_PATH}\n")
        connection.run_command(
            f"mv {_quote(OLD_REMOTE_LAUNCHER_PATH)} {_quote(REMOTE_LAUNCHER_PATH)}"
        )

    if _path_exists(connection, OLD_REMOTE_RBF_PATH) and not _path_exists(connection, REMOTE_RBF_PATH):
        log(f"Renaming RBF: {OLD_REMOTE_RBF_PATH} -> {REMOTE_RBF_PATH}\n")
        connection.run_command(
            f"mv {_quote(OLD_REMOTE_RBF_PATH)} {_quote(REMOTE_RBF_PATH)}"
        )

    if _path_exists(connection, OLD_REMOTE_GAME_DIR) and not _path_exists(connection, REMOTE_GAME_DIR):
        log(f"Renaming game data: {OLD_REMOTE_GAME_DIR} -> {REMOTE_GAME_DIR}\n")
        connection.run_command(
            f"mv {_quote(OLD_REMOTE_GAME_DIR)} {_quote(REMOTE_GAME_DIR)}"
        )

    if _path_exists(connection, OLD_REMOTE_VERSION_FILE) and not _path_exists(connection, REMOTE_VERSION_FILE):
        _ensure_remote_dir(connection, posixpath.dirname(REMOTE_VERSION_FILE))
        log(f"Moving version marker: {OLD_REMOTE_VERSION_FILE} -> {REMOTE_VERSION_FILE}\n")
        connection.run_command(
            f"mv {_quote(OLD_REMOTE_VERSION_FILE)} {_quote(REMOTE_VERSION_FILE)}"
        )

    ini_changed = _ensure_ini_block(connection)
    if ini_changed:
        log("Updated MiSTer.ini to [3S-ARM]\n")

    if _path_exists(connection, REMOTE_LAUNCHER_PATH):
        connection.run_command(f"chmod +x {_quote(REMOTE_LAUNCHER_PATH)}")

    return True


def _rename_local_path(sd_root: str, old_remote_path: str, new_remote_path: str):
    old_path = _local_path(sd_root, old_remote_path)
    new_path = _local_path(sd_root, new_remote_path)

    if not old_path.exists() or new_path.exists():
        return False

    new_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.rename(new_path)
    return True


def _migrate_old_install_local(sd_root: str, log):
    old_present = _is_old_3sx_installed_local(sd_root)
    if not old_present:
        return False

    log("Detected legacy 3SX install, migrating to 3S-ARM layout...\n")

    _ensure_local_dir(sd_root, "/media/fat/_Other")
    _ensure_local_dir(sd_root, "/media/fat/games")

    if _rename_local_path(sd_root, OLD_REMOTE_LAUNCHER_PATH, REMOTE_LAUNCHER_PATH):
        log(f"Renaming launcher: {OLD_REMOTE_LAUNCHER_PATH} -> {REMOTE_LAUNCHER_PATH}\n")

    if _rename_local_path(sd_root, OLD_REMOTE_RBF_PATH, REMOTE_RBF_PATH):
        log(f"Renaming RBF: {OLD_REMOTE_RBF_PATH} -> {REMOTE_RBF_PATH}\n")

    if _rename_local_path(sd_root, OLD_REMOTE_GAME_DIR, REMOTE_GAME_DIR):
        log(f"Renaming game data: {OLD_REMOTE_GAME_DIR} -> {REMOTE_GAME_DIR}\n")

    if _rename_local_path(sd_root, OLD_REMOTE_VERSION_FILE, REMOTE_VERSION_FILE):
        log(f"Moving version marker: {OLD_REMOTE_VERSION_FILE} -> {REMOTE_VERSION_FILE}\n")

    ini_changed = _ensure_ini_block_local(sd_root)
    if ini_changed:
        log("Updated MiSTer.ini to [3S-ARM]\n")

    return True


def get_3sx_status(connection, check_latest: bool = False):
    if not connection.is_connected():
        return {
            "installed": False,
            "installed_version": "",
            "latest_version": "",
            "latest_error": "",
            "update_available": False,
            "afs_present": False,
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
            latest = _fetch_latest_release()
            latest_version = latest["version"]
        except Exception as exc:
            latest_error = str(exc)

    installed = _is_3sx_installed(connection)
    legacy_installed = _is_old_3sx_installed(connection)
    installed_version = _read_installed_version(connection) if (installed or legacy_installed) else ""

    afs_present = False
    if installed:
        afs_present = _path_exists(connection, REMOTE_AFS_PATH)
    elif legacy_installed:
        afs_present = _path_exists(connection, OLD_REMOTE_AFS_PATH)

    update_available = False
    if check_latest:
        if (installed or legacy_installed) and latest_version and installed_version:
            update_available = installed_version != latest_version
        elif (installed or legacy_installed) and latest_version and not installed_version:
            update_available = True

    if not installed and not legacy_installed:
        status_text = "✗ Not installed"
        install_label = "Install"
        install_enabled = True
        upload_enabled = False
        uninstall_enabled = False
    elif legacy_installed and not installed:
        status_text = "✓ Legacy 3SX install detected"
        install_label = "Migrate / Install"
        install_enabled = True
        upload_enabled = not afs_present
        uninstall_enabled = True
    elif update_available:
        status_text = f"▲ Update available ({installed_version or 'unknown'} → {latest_version})"
        install_label = "Update"
        install_enabled = True
        upload_enabled = not afs_present
        uninstall_enabled = True
    else:
        version_display = installed_version or "unknown"
        status_text = f"✓ Installed ({version_display})"
        install_label = "Installed"
        install_enabled = False
        upload_enabled = not afs_present
        uninstall_enabled = True

    if latest_error and check_latest:
        status_text = f"{status_text} (update check failed: {latest_error})"

    return {
        "installed": installed or legacy_installed,
        "installed_version": installed_version,
        "latest_version": latest_version,
        "latest_error": latest_error,
        "update_available": update_available,
        "afs_present": afs_present,
        "status_text": status_text,
        "install_label": install_label,
        "install_enabled": install_enabled,
        "upload_enabled": upload_enabled,
        "uninstall_enabled": uninstall_enabled,
    }


def get_3sx_status_local(sd_root: str, check_latest: bool = False):
    latest_version = ""
    latest_error = ""

    if check_latest:
        try:
            latest = _fetch_latest_release()
            latest_version = latest["version"]
        except Exception as exc:
            latest_error = str(exc)

    installed = _is_3sx_installed_local(sd_root)
    legacy_installed = _is_old_3sx_installed_local(sd_root)
    installed_version = _read_installed_version_local(sd_root) if (installed or legacy_installed) else ""

    afs_present = False
    if installed:
        afs_present = _path_exists_local(sd_root, REMOTE_AFS_PATH)
    elif legacy_installed:
        afs_present = _path_exists_local(sd_root, OLD_REMOTE_AFS_PATH)

    update_available = False
    if check_latest:
        if (installed or legacy_installed) and latest_version and installed_version:
            update_available = installed_version != latest_version
        elif (installed or legacy_installed) and latest_version and not installed_version:
            update_available = True

    if not installed and not legacy_installed:
        status_text = "✗ Not installed"
        install_label = "Install"
        install_enabled = True
        upload_enabled = False
        uninstall_enabled = False
    elif legacy_installed and not installed:
        status_text = "✓ Legacy 3SX install detected"
        install_label = "Migrate / Install"
        install_enabled = True
        upload_enabled = not afs_present
        uninstall_enabled = True
    elif update_available:
        status_text = f"▲ Update available ({installed_version or 'unknown'} → {latest_version})"
        install_label = "Update"
        install_enabled = True
        upload_enabled = not afs_present
        uninstall_enabled = True
    else:
        version_display = installed_version or "unknown"
        status_text = f"✓ Installed ({version_display})"
        install_label = "Installed"
        install_enabled = False
        upload_enabled = not afs_present
        uninstall_enabled = True

    if latest_error and check_latest:
        status_text = f"{status_text} (update check failed: {latest_error})"

    return {
        "installed": installed or legacy_installed,
        "installed_version": installed_version,
        "latest_version": latest_version,
        "latest_error": latest_error,
        "update_available": update_available,
        "afs_present": afs_present,
        "status_text": status_text,
        "install_label": install_label,
        "install_enabled": install_enabled,
        "upload_enabled": upload_enabled,
        "uninstall_enabled": uninstall_enabled,
    }


def install_or_update_3sx(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    _migrate_old_install(connection, log)

    latest = _fetch_latest_release()
    version = latest["version"]
    zip_url = latest["zip_url"]

    log(f"Latest version on GitHub: {version}\n")
    log(f"Downloading: {zip_url}\n")

    response = requests.get(zip_url, timeout=60)
    response.raise_for_status()
    archive_data = response.content

    log(f"Downloaded {len(archive_data)} bytes.\n")

    with zipfile.ZipFile(io.BytesIO(archive_data)) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        if not members:
            raise RuntimeError("The 3s-mister-arm ZIP archive is empty.")

        log("Inspecting archive contents...\n")

        payloads = []
        for member in members:
            name = member.filename.replace("\\", "/")
            basename = posixpath.basename(name)

            if not basename:
                continue

            if basename.lower() == "readme.txt":
                log(f"Skipping README: {name}\n")
                continue

            payloads.append(member)

        sftp = connection.client.open_sftp()
        try:
            for member in payloads:
                name = member.filename.replace("\\", "/")
                basename = posixpath.basename(name)
                data = zf.read(member)

                if basename == "MiSTer_3S-ARM":
                    log(f"Uploading launcher: {REMOTE_LAUNCHER_PATH}\n")
                    with sftp.open(REMOTE_LAUNCHER_PATH, "wb") as remote_file:
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
                    remote_path = posixpath.join("/media/fat/games", *relative)
                    _ensure_remote_dir(connection, posixpath.dirname(remote_path))
                    log(f"Merging into /media/fat/games: {'/'.join(relative)}\n")
                    with sftp.open(remote_path, "wb") as remote_file:
                        remote_file.write(data)
                    continue

                if basename == "3S-ARM.rbf":
                    _ensure_remote_dir(connection, "/media/fat/_Other")
                    log(f"Uploading RBF: {REMOTE_RBF_PATH}\n")
                    with sftp.open(REMOTE_RBF_PATH, "wb") as remote_file:
                        remote_file.write(data)
                    continue

                log(f"Skipping unhandled file: {name}\n")

        finally:
            sftp.close()

    connection.run_command(f"chmod +x {_quote(REMOTE_LAUNCHER_PATH)}")

    ini_added = _ensure_ini_block(connection)
    if ini_added:
        log("Added [3S-ARM] block to MiSTer.ini\n")
    else:
        log("[3S-ARM] block already present in MiSTer.ini\n")

    _write_installed_version(connection, version)
    log(f"Stored installed version marker: {version}\n")

    return {
        "installed_version": version,
    }


def install_or_update_3sx_local(sd_root: str, log):
    _migrate_old_install_local(sd_root, log)

    latest = _fetch_latest_release()
    version = latest["version"]
    zip_url = latest["zip_url"]

    log(f"Latest version on GitHub: {version}\n")
    log(f"Downloading: {zip_url}\n")

    response = requests.get(zip_url, timeout=60)
    response.raise_for_status()
    archive_data = response.content

    log(f"Downloaded {len(archive_data)} bytes.\n")

    with zipfile.ZipFile(io.BytesIO(archive_data)) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        if not members:
            raise RuntimeError("The 3s-mister-arm ZIP archive is empty.")

        log("Inspecting archive contents...\n")

        payloads = []
        for member in members:
            name = member.filename.replace("\\", "/")
            basename = posixpath.basename(name)

            if not basename:
                continue

            if basename.lower() == "readme.txt":
                log(f"Skipping README: {name}\n")
                continue

            payloads.append(member)

        for member in payloads:
            name = member.filename.replace("\\", "/")
            basename = posixpath.basename(name)
            data = zf.read(member)

            if basename == "MiSTer_3S-ARM":
                log(f"Writing launcher: {REMOTE_LAUNCHER_PATH}\n")
                _write_local_bytes(sd_root, REMOTE_LAUNCHER_PATH, data)
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
                log(f"Merging into /media/fat/_Other: {'/'.join(relative)}\n")
                _write_local_bytes(sd_root, remote_path, data)
                continue

            if "games" in parts:
                idx = parts.index("games")
                relative = parts[idx + 1:]
                if not relative:
                    continue
                remote_path = posixpath.join("/media/fat/games", *relative)
                log(f"Merging into /media/fat/games: {'/'.join(relative)}\n")
                _write_local_bytes(sd_root, remote_path, data)
                continue

            if basename == "3S-ARM.rbf":
                log(f"Writing RBF: {REMOTE_RBF_PATH}\n")
                _write_local_bytes(sd_root, REMOTE_RBF_PATH, data)
                continue

            log(f"Skipping unhandled file: {name}\n")

    ini_added = _ensure_ini_block_local(sd_root)
    if ini_added:
        log("Added [3S-ARM] block to MiSTer.ini\n")
    else:
        log("[3S-ARM] block already present in MiSTer.ini\n")

    _write_installed_version_local(sd_root, version)
    log(f"Stored installed version marker: {version}\n")

    return {
        "installed_version": version,
    }


def upload_3sx_afs(connection, local_path: str, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    if not os.path.isfile(local_path):
        raise RuntimeError("Selected SF33RD.AFS file does not exist.")

    local_name = os.path.basename(local_path)
    if local_name.lower() != "sf33rd.afs":
        log(f"Warning: selected file name is {local_name}, expected SF33RD.AFS\n")

    if not (_is_3sx_installed(connection) or _is_old_3sx_installed(connection)):
        raise RuntimeError("3s-mister-arm is not installed.")

    if _is_3sx_installed(connection):
        target_resources_dir = REMOTE_RESOURCES_DIR
        target_afs_path = REMOTE_AFS_PATH
    else:
        target_resources_dir = OLD_REMOTE_RESOURCES_DIR
        target_afs_path = OLD_REMOTE_AFS_PATH

    _ensure_remote_dir(connection, target_resources_dir)

    file_size = os.path.getsize(local_path)
    log(f"Uploading asset to {target_afs_path}\n")
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
        sftp.put(local_path, target_afs_path, callback=progress_callback)
    finally:
        sftp.close()

    log("Upload completed.\n")
    return {"afs_present": True}


def upload_3sx_afs_local(sd_root: str, local_path: str, log):
    if not os.path.isfile(local_path):
        raise RuntimeError("Selected SF33RD.AFS file does not exist.")

    local_name = os.path.basename(local_path)
    if local_name.lower() != "sf33rd.afs":
        log(f"Warning: selected file name is {local_name}, expected SF33RD.AFS\n")

    if not (_is_3sx_installed_local(sd_root) or _is_old_3sx_installed_local(sd_root)):
        raise RuntimeError("3s-mister-arm is not installed.")

    if _is_3sx_installed_local(sd_root):
        target_resources_dir = REMOTE_RESOURCES_DIR
        target_afs_path = REMOTE_AFS_PATH
    else:
        target_resources_dir = OLD_REMOTE_RESOURCES_DIR
        target_afs_path = OLD_REMOTE_AFS_PATH

    _ensure_local_dir(sd_root, target_resources_dir)

    file_size = os.path.getsize(local_path)
    log(f"Copying asset to {target_afs_path}\n")
    log(f"File size: {file_size} bytes\n")

    _copy_local_file_to_sd(sd_root, local_path, target_afs_path)

    log("Copy completed.\n")
    return {"afs_present": True}


def uninstall_3sx(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log(f"Removing {REMOTE_RBF_PATH}\n")
    connection.run_command(f"rm -f {_quote(REMOTE_RBF_PATH)}")

    log(f"Removing {REMOTE_LAUNCHER_PATH}\n")
    connection.run_command(f"rm -f {_quote(REMOTE_LAUNCHER_PATH)}")

    if _path_exists(connection, REMOTE_VERSION_FILE):
        log(f"Removing version marker: {REMOTE_VERSION_FILE}\n")
        connection.run_command(f"rm -f {_quote(REMOTE_VERSION_FILE)}")

    log(f"Removing {REMOTE_GAME_DIR}\n")
    connection.run_command(f"rm -rf {_quote(REMOTE_GAME_DIR)}")

    log(f"Removing legacy {OLD_REMOTE_RBF_PATH}\n")
    connection.run_command(f"rm -f {_quote(OLD_REMOTE_RBF_PATH)}")

    log(f"Removing legacy {OLD_REMOTE_LAUNCHER_PATH}\n")
    connection.run_command(f"rm -f {_quote(OLD_REMOTE_LAUNCHER_PATH)}")

    if _path_exists(connection, OLD_REMOTE_VERSION_FILE):
        log(f"Removing legacy version marker: {OLD_REMOTE_VERSION_FILE}\n")
        connection.run_command(f"rm -f {_quote(OLD_REMOTE_VERSION_FILE)}")

    log(f"Removing legacy {OLD_REMOTE_GAME_DIR}\n")
    connection.run_command(f"rm -rf {_quote(OLD_REMOTE_GAME_DIR)}")

    removed_ini = _remove_ini_block(connection)
    if removed_ini:
        log("Removed 3S-ARM / 3SX block from MiSTer.ini\n")
    else:
        log("No 3S-ARM / 3SX block found in MiSTer.ini\n")

    return {"uninstalled": True}


def uninstall_3sx_local(sd_root: str, log):
    log(f"Removing {REMOTE_RBF_PATH}\n")
    _remove_local_path(sd_root, REMOTE_RBF_PATH)

    log(f"Removing {REMOTE_LAUNCHER_PATH}\n")
    _remove_local_path(sd_root, REMOTE_LAUNCHER_PATH)

    if _path_exists_local(sd_root, REMOTE_VERSION_FILE):
        log(f"Removing version marker: {REMOTE_VERSION_FILE}\n")
        _remove_local_path(sd_root, REMOTE_VERSION_FILE)

    log(f"Removing {REMOTE_GAME_DIR}\n")
    _remove_local_path(sd_root, REMOTE_GAME_DIR)

    log(f"Removing legacy {OLD_REMOTE_RBF_PATH}\n")
    _remove_local_path(sd_root, OLD_REMOTE_RBF_PATH)

    log(f"Removing legacy {OLD_REMOTE_LAUNCHER_PATH}\n")
    _remove_local_path(sd_root, OLD_REMOTE_LAUNCHER_PATH)

    if _path_exists_local(sd_root, OLD_REMOTE_VERSION_FILE):
        log(f"Removing legacy version marker: {OLD_REMOTE_VERSION_FILE}\n")
        _remove_local_path(sd_root, OLD_REMOTE_VERSION_FILE)

    log(f"Removing legacy {OLD_REMOTE_GAME_DIR}\n")
    _remove_local_path(sd_root, OLD_REMOTE_GAME_DIR)

    removed_ini = _remove_ini_block_local(sd_root)
    if removed_ini:
        log("Removed 3S-ARM / 3SX block from MiSTer.ini\n")
    else:
        log("No 3S-ARM / 3SX block found in MiSTer.ini\n")

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

THREE_S_ARM_DB_ID = "MultiDatabases/3s-arm"
THREE_S_ARM_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/3s-arm/db.json"

# These are exactly the files owned by the Downloader database. The user's
# SF33RD.AFS is deliberately absent and remains untouched during migration.
THREE_S_ARM_DB_FILES = (
    "/media/fat/MiSTer_3S-ARM",
    "/media/fat/_Other/3S-ARM.rbf",
    "/media/fat/games/3s-arm/bin/3s-arm",
    "/media/fat/games/3s-arm/lib/libSDL3.so",
    "/media/fat/games/3s-arm/lib/libSDL3.so.0",
    "/media/fat/games/3s-arm/lib/libSDL3.so.0.4.0",
    "/media/fat/games/3s-arm/licenses/LICENSE",
    "/media/fat/games/3s-arm/licenses/THIRD_PARTY_NOTICES.txt",
    "/media/fat/games/3s-arm/scripts/launch-osd.sh",
    "/media/fat/games/3s-arm/scripts/run-3s-arm.sh",
)


def _manual_3sx_install(connection) -> bool:
    installed = _is_3sx_installed(connection) or _is_old_3sx_installed(connection)
    return bool(installed and (
        _path_exists(connection, REMOTE_VERSION_FILE)
        or _path_exists(connection, OLD_REMOTE_VERSION_FILE)
        or not database_registered_online(connection, THREE_S_ARM_DB_ID)
    ))


def _manual_3sx_install_local(sd_root: str) -> bool:
    installed = _is_3sx_installed_local(sd_root) or _is_old_3sx_installed_local(sd_root)
    return bool(installed and (
        _path_exists_local(sd_root, REMOTE_VERSION_FILE)
        or _path_exists_local(sd_root, OLD_REMOTE_VERSION_FILE)
        or not database_registered_local(sd_root, THREE_S_ARM_DB_ID)
    ))


def _prepare_manual_3sx_for_downloader(connection, log, manual=None):
    if manual is None:
        manual = _manual_3sx_install(connection)
    if not manual:
        return False
    _migrate_old_install(connection, log)
    log("Detected a manual Companion installation; preparing it for Downloader...\n")
    for path in THREE_S_ARM_DB_FILES:
        connection.run_command(f"rm -f {_quote(path)}")
        log(f"Removed legacy managed file: {path}\n")
    connection.run_command(f"rm -f {_quote(REMOTE_VERSION_FILE)} {_quote(OLD_REMOTE_VERSION_FILE)}")
    log(f"Preserved user game file when present: {REMOTE_AFS_PATH}\n")
    return True


def _ini_block_present(text: str) -> bool:
    normalized = (text or "").replace("\r\n", "\n")
    return "[3S-ARM]" in normalized and "main=MiSTer_3S-ARM" in normalized


def _prepare_manual_3sx_for_downloader_local(sd_root: str, log, manual=None):
    if manual is None:
        manual = _manual_3sx_install_local(sd_root)
    if not manual:
        return False
    _migrate_old_install_local(sd_root, log)
    log("Detected a manual Companion installation; preparing it for Downloader...\n")
    for path in THREE_S_ARM_DB_FILES:
        _remove_local_path(sd_root, path)
        log(f"Removed legacy managed file: {path}\n")
    _remove_local_path(sd_root, REMOTE_VERSION_FILE)
    _remove_local_path(sd_root, OLD_REMOTE_VERSION_FILE)
    log(f"Preserved user game file when present: {REMOTE_AFS_PATH}\n")
    return True


_manual_get_3sx_status = get_3sx_status
_manual_get_3sx_status_local = get_3sx_status_local


def _apply_3sx_downloader_status(status: dict, manual: bool, update_available: bool = False) -> dict:
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


def get_3sx_status(connection, check_latest: bool = False):
    status = _manual_get_3sx_status(connection, check_latest=False)
    manual = _manual_3sx_install(connection) if status.get("installed") else False
    update = False
    if check_latest and status.get("installed") and not manual:
        update = check_named_database_online(connection, THREE_S_ARM_DB_ID)
    status = _apply_3sx_downloader_status(status, manual, update)
    if status.get("installed") and not manual and not _ini_block_present(_read_remote_text(connection, REMOTE_INI_PATH)):
        status.update({"status_text": "⚠ MiSTer.ini entry missing", "install_label": "Add INI Entry", "install_enabled": True, "update_available": False, "repair_action": True})
    return status


def get_3sx_status_local(sd_root: str, check_latest: bool = False):
    status = _manual_get_3sx_status_local(sd_root, check_latest=False)
    manual = _manual_3sx_install_local(sd_root) if status.get("installed") else False
    update = False
    if check_latest and status.get("installed") and not manual:
        update = check_named_database_local(sd_root, THREE_S_ARM_DB_ID)
    status = _apply_3sx_downloader_status(status, manual, update)
    if status.get("installed") and not manual and not _ini_block_present(_read_local_text(sd_root, REMOTE_INI_PATH)):
        status.update({"status_text": "⚠ MiSTer.ini entry missing", "install_label": "Add INI Entry", "install_enabled": True, "update_available": False, "repair_action": True})
    return status


def install_or_update_3sx(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    manual = _manual_3sx_install(connection)
    if not manual and _manual_get_3sx_status(connection, check_latest=False).get("installed") and not _ini_block_present(_read_remote_text(connection, REMOTE_INI_PATH)):
        _ensure_ini_block(connection)
        return
    original = ensure_database_source_online(connection, THREE_S_ARM_DB_ID, THREE_S_ARM_DB_URL)
    try:
        _prepare_manual_3sx_for_downloader(connection, log, manual=manual)
        _ensure_ini_block(connection)
        run_named_database_online(connection, THREE_S_ARM_DB_ID, log=log)
        connection.run_command(f"chmod +x {_quote(REMOTE_LAUNCHER_PATH)}")
        connection.run_command(f"rm -f {_quote(REMOTE_VERSION_FILE)} {_quote(OLD_REMOTE_VERSION_FILE)}")
    except Exception:
        restore_online(connection, original)
        raise


def install_or_update_3sx_local(sd_root: str, log):
    manual = _manual_3sx_install_local(sd_root)
    if not manual and _manual_get_3sx_status_local(sd_root, check_latest=False).get("installed") and not _ini_block_present(_read_local_text(sd_root, REMOTE_INI_PATH)):
        _ensure_ini_block_local(sd_root)
        return
    original = ensure_database_source_local(sd_root, THREE_S_ARM_DB_ID, THREE_S_ARM_DB_URL)
    try:
        _prepare_manual_3sx_for_downloader_local(sd_root, log, manual=manual)
        _ensure_ini_block_local(sd_root)
        run_named_database_local(sd_root, THREE_S_ARM_DB_ID, log=log)
        _remove_local_path(sd_root, REMOTE_VERSION_FILE)
        _remove_local_path(sd_root, OLD_REMOTE_VERSION_FILE)
    except Exception:
        restore_local(sd_root, original)
        raise


def uninstall_3sx(connection, log, force=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    if _manual_3sx_install(connection):
        _prepare_manual_3sx_for_downloader(connection, log, manual=True)
        remove_database_source_online(connection, THREE_S_ARM_DB_ID)
        _remove_ini_block(connection)
        return {"uninstalled": True}
    original = ensure_database_source_online(connection, THREE_S_ARM_DB_ID, THREE_S_ARM_DB_URL)
    try:
        _remove_ini_block(connection)
        native = uninstall_named_database_online(connection, THREE_S_ARM_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(connection, THREE_S_ARM_DB_ID, THREE_S_ARM_DB_URL, filter_value="!all")
            run_named_database_online(connection, THREE_S_ARM_DB_ID, log=log)
            remove_database_source_online(connection, THREE_S_ARM_DB_ID)
        connection.run_command(f"rm -f {_quote(REMOTE_VERSION_FILE)} {_quote(OLD_REMOTE_VERSION_FILE)}")
    except Exception:
        restore_online(connection, original)
        raise
    return {"uninstalled": True}


def uninstall_3sx_local(sd_root: str, log, force=False):
    if _manual_3sx_install_local(sd_root):
        _prepare_manual_3sx_for_downloader_local(sd_root, log, manual=True)
        remove_database_source_local(sd_root, THREE_S_ARM_DB_ID)
        _remove_ini_block_local(sd_root)
        return {"uninstalled": True}
    original = ensure_database_source_local(sd_root, THREE_S_ARM_DB_ID, THREE_S_ARM_DB_URL)
    try:
        _remove_ini_block_local(sd_root)
        native = uninstall_named_database_local(sd_root, THREE_S_ARM_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(sd_root, THREE_S_ARM_DB_ID, THREE_S_ARM_DB_URL, filter_value="!all")
            run_named_database_local(sd_root, THREE_S_ARM_DB_ID, log=log)
            remove_database_source_local(sd_root, THREE_S_ARM_DB_ID)
        _remove_local_path(sd_root, REMOTE_VERSION_FILE)
        _remove_local_path(sd_root, OLD_REMOTE_VERSION_FILE)
    except Exception:
        restore_local(sd_root, original)
        raise
    return {"uninstalled": True}

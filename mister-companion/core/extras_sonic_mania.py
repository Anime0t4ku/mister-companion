import io
import os
import posixpath
import re
import zipfile

import requests

from core.extras_common import (
    _ensure_remote_dir,
    _fetch_latest_zip_release,
    _glob_exists,
    _normalize_ini_text_for_append,
    _path_exists,
    _quote,
    _read_remote_text,
    _remove_glob,
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


def _is_sonic_mania_installed(connection) -> bool:
    return (
        _has_sonic_mania_rbf(connection)
        and _path_exists(connection, SONIC_MANIA_REMOTE_GAME_DIR)
        and _path_exists(connection, SONIC_MANIA_REMOTE_LAUNCHER_PATH)
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
        members = [m for m in zf.infolist() if not m.is_dir()]
        if not members:
            raise RuntimeError("The Sonic Mania MiSTer ZIP archive is empty.")

        log("Inspecting archive contents...\n")

        payloads = []
        for member in members:
            name = member.filename.replace("\\", "/")
            basename = posixpath.basename(name)
            lower_basename = basename.lower()

            if not basename:
                continue

            if lower_basename in ("readme.txt", "readme.md", "license.txt", "license.md"):
                log(f"Skipping documentation file: {name}\n")
                continue

            payloads.append(member)

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
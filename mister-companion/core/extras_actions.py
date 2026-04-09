import io
import os
import posixpath
import re
import shlex
import zipfile

import requests


GITHUB_RELEASES_API = "https://api.github.com/repos/kimchiman52/3sx-mister/releases/latest"

REMOTE_RBF_PATH = "/media/fat/_Other/3SX.rbf"
REMOTE_GAME_DIR = "/media/fat/games/3sx"
REMOTE_RESOURCES_DIR = "/media/fat/games/3sx/resources"
REMOTE_LAUNCHER_PATH = "/media/fat/MiSTer_3SX"
REMOTE_VERSION_FILE = "/media/fat/games/3sx/.mister_companion_version"
REMOTE_INI_PATH = "/media/fat/MiSTer.ini"
REMOTE_AFS_PATH = "/media/fat/games/3sx/resources/SF33RD.AFS"

INI_BLOCK = "[3SX]\nmain=MiSTer_3SX\nvideo_mode=8\n"


def _quote(value: str) -> str:
    return shlex.quote(value)


def _remote_file_exists(sftp, path: str) -> bool:
    try:
        sftp.stat(path)
        return True
    except Exception:
        return False


def _write_remote_bytes(connection, path: str, data: bytes):
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "wb") as remote_file:
            remote_file.write(data)
    finally:
        sftp.close()


def _write_remote_text(connection, path: str, text: str):
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "wb") as remote_file:
            remote_file.write(text.encode("utf-8"))
    finally:
        sftp.close()


def _read_remote_text(connection, path: str) -> str:
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "r") as remote_file:
            data = remote_file.read()
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="replace")
            return data
    except Exception:
        return ""
    finally:
        sftp.close()


def _ensure_remote_dir(connection, remote_dir: str):
    connection.run_command(f"mkdir -p {_quote(remote_dir)}")


def _remote_command_success(connection, command: str) -> bool:
    result = connection.run_command(f"{command} >/dev/null 2>&1 && echo OK || echo FAIL")
    return "OK" in (result or "")


def _path_exists(connection, path: str) -> bool:
    result = connection.run_command(f"test -e {_quote(path)} && echo EXISTS || echo MISSING")
    return "EXISTS" in (result or "")


def _is_3sx_installed(connection) -> bool:
    return (
        _path_exists(connection, REMOTE_RBF_PATH)
        and _path_exists(connection, REMOTE_GAME_DIR)
        and _path_exists(connection, REMOTE_LAUNCHER_PATH)
    )


def _fetch_latest_release():
    response = requests.get(
        GITHUB_RELEASES_API,
        headers={"Accept": "application/vnd.github+json"},
        timeout=20,
    )
    response.raise_for_status()

    payload = response.json()
    tag_name = (payload.get("tag_name") or "").strip()

    zip_url = None
    for asset in payload.get("assets", []):
        url = asset.get("browser_download_url", "")
        name = asset.get("name", "")
        if url.lower().endswith(".zip") or name.lower().endswith(".zip"):
            zip_url = url
            break

    if not tag_name:
        raise RuntimeError("Unable to determine latest 3SX-MiSTer version from GitHub.")

    if not zip_url:
        raise RuntimeError("Unable to find a ZIP asset in the latest 3SX-MiSTer release.")

    return {
        "version": tag_name,
        "zip_url": zip_url,
        "release_name": payload.get("name", tag_name),
    }


def _read_installed_version(connection) -> str:
    return _read_remote_text(connection, REMOTE_VERSION_FILE).strip()


def _write_installed_version(connection, version: str):
    _ensure_remote_dir(connection, posixpath.dirname(REMOTE_VERSION_FILE))
    _write_remote_text(connection, REMOTE_VERSION_FILE, version.strip() + "\n")


def _normalize_ini_text_for_append(text: str) -> str:
    normalized = text.replace("\r\n", "\n").rstrip("\n")
    if normalized:
        normalized += "\n\n"
    return normalized


def _ensure_ini_block(connection) -> bool:
    current = _read_remote_text(connection, REMOTE_INI_PATH)
    normalized = current.replace("\r\n", "\n")

    if "[3SX]" in normalized and "main=MiSTer_3SX" in normalized:
        return False

    updated = _normalize_ini_text_for_append(normalized) + INI_BLOCK
    _write_remote_text(connection, REMOTE_INI_PATH, updated)
    return True


def _remove_ini_block(connection) -> bool:
    current = _read_remote_text(connection, REMOTE_INI_PATH)
    if not current:
        return False

    normalized = current.replace("\r\n", "\n")

    pattern = re.compile(
        r"(?:\n{0,2})\[3SX\]\nmain=MiSTer_3SX\nvideo_mode=8\n?",
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


def get_3sx_status(connection):
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

    try:
        latest = _fetch_latest_release()
        latest_version = latest["version"]
    except Exception as exc:
        latest_error = str(exc)

    installed = _is_3sx_installed(connection)
    installed_version = _read_installed_version(connection) if installed else ""
    afs_present = _path_exists(connection, REMOTE_AFS_PATH) if installed else False

    update_available = False
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
        upload_enabled = not afs_present
        uninstall_enabled = True
    else:
        version_display = installed_version or latest_version or "unknown"
        status_text = f"✓ Installed ({version_display})"
        install_label = "Installed"
        install_enabled = False
        upload_enabled = not afs_present
        uninstall_enabled = True

    return {
        "installed": installed,
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
            raise RuntimeError("The 3SX-MiSTer ZIP archive is empty.")

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

                if basename == "MiSTer_3SX":
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

                if basename == "3SX.rbf":
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
        log("Added [3SX] block to MiSTer.ini\n")
    else:
        log("[3SX] block already present in MiSTer.ini\n")

    _write_installed_version(connection, version)
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

    if not _is_3sx_installed(connection):
        raise RuntimeError("3SX-MiSTer is not installed.")

    _ensure_remote_dir(connection, REMOTE_RESOURCES_DIR)

    file_size = os.path.getsize(local_path)
    log(f"Uploading asset to {REMOTE_AFS_PATH}\n")
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
        sftp.put(local_path, REMOTE_AFS_PATH, callback=progress_callback)
    finally:
        sftp.close()

    log("Upload completed.\n")
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

    removed_ini = _remove_ini_block(connection)
    if removed_ini:
        log("Removed [3SX] block from MiSTer.ini\n")
    else:
        log("No [3SX] block found in MiSTer.ini\n")

    return {"uninstalled": True}
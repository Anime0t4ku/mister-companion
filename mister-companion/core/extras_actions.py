import io
import os
import posixpath
import re
import shlex
import zipfile

import requests


GITHUB_RELEASES_API = "https://api.github.com/repos/kimchiman52/3s-mister-arm/releases/latest"
PICO8_GITHUB_RELEASES_API = "https://api.github.com/repos/MiSTerOrganize/MiSTer_PICO-8/releases/latest"

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

INI_BLOCK = "[3S-ARM]\nmain=MiSTer_3S-ARM\nvideo_mode=8\n"

PICO8_REMOTE_RBF_DIR = "/media/fat/_Other"
PICO8_LEGACY_REMOTE_RBF_DIR = "/media/fat/_Console"
PICO8_REMOTE_GAME_DIR = "/media/fat/games/PICO-8"
PICO8_REMOTE_DOCS_DIR = "/media/fat/docs/PICO-8"
PICO8_REMOTE_SCRIPTS_DIR = "/media/fat/Scripts"
PICO8_REMOTE_INPUTS_DIR = "/media/fat/config/inputs"
PICO8_REMOTE_VERSION_FILE = "/media/fat/games/PICO-8/.mister_companion_version"
PICO8_REMOTE_BINARY_PATH = "/media/fat/games/PICO-8/PICO-8"
PICO8_REMOTE_BOOTROM_PATH = "/media/fat/games/PICO-8/boot.rom"
PICO8_REMOTE_DAEMON_PATH = "/media/fat/games/PICO-8/pico8_daemon.sh"
PICO8_REMOTE_README_PATH = "/media/fat/docs/PICO-8/README.md"
PICO8_REMOTE_INSTALL_SCRIPT_PATH = "/media/fat/Scripts/Install_PICO-8.sh"
PICO8_REMOTE_USER_STARTUP_PATH = "/media/fat/linux/user-startup.sh"
PICO8_DAEMON_STARTUP_LINE = "/media/fat/games/PICO-8/pico8_daemon.sh &"


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


def _glob_exists(connection, pattern: str) -> bool:
    command = (
        f"for f in {pattern}; do "
        f'[ -e "$f" ] && echo EXISTS && exit 0; '
        f"done; echo MISSING"
    )
    result = connection.run_command(command)
    return "EXISTS" in (result or "")


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


def _has_pico8_rbf_in_other(connection) -> bool:
    return _glob_exists(connection, "/media/fat/_Other/PICO-8_*.rbf")


def _has_pico8_rbf_in_console(connection) -> bool:
    return _glob_exists(connection, "/media/fat/_Console/PICO-8_*.rbf")


def _is_pico8_installed(connection) -> bool:
    return (
        _has_pico8_rbf_in_other(connection)
        and _path_exists(connection, PICO8_REMOTE_BINARY_PATH)
        and _path_exists(connection, PICO8_REMOTE_BOOTROM_PATH)
        and _path_exists(connection, PICO8_REMOTE_DAEMON_PATH)
    )


def _is_pico8_legacy_installed(connection) -> bool:
    return (
        _has_pico8_rbf_in_console(connection)
        and _path_exists(connection, PICO8_REMOTE_BINARY_PATH)
        and _path_exists(connection, PICO8_REMOTE_BOOTROM_PATH)
        and _path_exists(connection, PICO8_REMOTE_DAEMON_PATH)
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
        raise RuntimeError("Unable to determine latest 3s-mister-arm version from GitHub.")

    if not zip_url:
        raise RuntimeError("Unable to find a ZIP asset in the latest 3s-mister-arm release.")

    return {
        "version": tag_name,
        "zip_url": zip_url,
        "release_name": payload.get("name", tag_name),
    }


def _fetch_latest_pico8_release():
    response = requests.get(
        PICO8_GITHUB_RELEASES_API,
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
        lower_name = name.lower()
        lower_url = url.lower()
        if lower_name.endswith(".zip") or lower_url.endswith(".zip"):
            zip_url = url
            break

    if not tag_name:
        raise RuntimeError("Unable to determine latest MiSTer Pico-8 version from GitHub.")

    if not zip_url:
        raise RuntimeError("Unable to find a ZIP asset in the latest MiSTer Pico-8 release.")

    return {
        "version": tag_name,
        "zip_url": zip_url,
        "release_name": payload.get("name", tag_name),
    }


def _read_installed_version(connection) -> str:
    version = _read_remote_text(connection, REMOTE_VERSION_FILE).strip()
    if version:
        return version
    return _read_remote_text(connection, OLD_REMOTE_VERSION_FILE).strip()


def _read_installed_pico8_version(connection) -> str:
    return _read_remote_text(connection, PICO8_REMOTE_VERSION_FILE).strip()


def _write_installed_version(connection, version: str):
    _ensure_remote_dir(connection, posixpath.dirname(REMOTE_VERSION_FILE))
    _write_remote_text(connection, REMOTE_VERSION_FILE, version.strip() + "\n")


def _write_installed_pico8_version(connection, version: str):
    _ensure_remote_dir(connection, posixpath.dirname(PICO8_REMOTE_VERSION_FILE))
    _write_remote_text(connection, PICO8_REMOTE_VERSION_FILE, version.strip() + "\n")


def _normalize_ini_text_for_append(text: str) -> str:
    normalized = text.replace("\r\n", "\n").rstrip("\n")
    if normalized:
        normalized += "\n\n"
    return normalized


def _ensure_ini_block(connection) -> bool:
    current = _read_remote_text(connection, REMOTE_INI_PATH)
    normalized = current.replace("\r\n", "\n")

    if "[3S-ARM]" in normalized and "main=MiSTer_3S-ARM" in normalized:
        return False

    old_pattern = re.compile(
        r"(?:\n{0,2})\[3SX\]\nmain=MiSTer_3SX\nvideo_mode=8\n?",
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
        r"(?:\n{0,2})\[(?:3SX|3S-ARM)\]\nmain=(?:MiSTer_3SX|MiSTer_3S-ARM)\nvideo_mode=8\n?",
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


def _ensure_startup_line(connection, startup_path: str, line: str) -> bool:
    current = _read_remote_text(connection, startup_path)
    normalized = current.replace("\r\n", "\n")

    existing_lines = [entry.rstrip() for entry in normalized.split("\n") if entry.strip()]
    if line in existing_lines:
        return False

    updated = normalized.rstrip("\n")
    if updated:
        updated += "\n"
    updated += line + "\n"

    _ensure_remote_dir(connection, posixpath.dirname(startup_path))
    _write_remote_text(connection, startup_path, updated)
    return True


def _remove_startup_line(connection, startup_path: str, line: str) -> bool:
    current = _read_remote_text(connection, startup_path)
    if not current:
        return False

    normalized = current.replace("\r\n", "\n")
    original_lines = normalized.split("\n")
    kept_lines = [entry for entry in original_lines if entry.strip() != line]

    if kept_lines == original_lines:
        return False

    updated = "\n".join(kept_lines).rstrip("\n")
    if updated:
        updated += "\n"

    _write_remote_text(connection, startup_path, updated)
    return True


def _remove_if_empty_dir(connection, path: str):
    connection.run_command(
        f"if [ -d {_quote(path)} ] && [ -z \"$(ls -A {_quote(path)} 2>/dev/null)\" ]; then rmdir {_quote(path)}; fi"
    )


def _remove_glob(connection, pattern: str):
    command = (
        f"for f in {pattern}; do "
        f'[ -e "$f" ] && rm -f "$f"; '
        f"done"
    )
    connection.run_command(command)


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


def _migrate_old_pico8_install(connection, log):
    if not _has_pico8_rbf_in_console(connection):
        return False

    log("Detected legacy MiSTer Pico-8 v1.1 install in /media/fat/_Console, migrating to /media/fat/_Other...\n")
    _ensure_remote_dir(connection, PICO8_REMOTE_RBF_DIR)

    connection.run_command(
        "for f in /media/fat/_Console/PICO-8_*.rbf; do "
        '[ -e "$f" ] || continue; '
        'mv "$f" /media/fat/_Other/; '
        "done"
    )

    _remove_if_empty_dir(connection, PICO8_LEGACY_REMOTE_RBF_DIR)
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
    legacy_installed = _is_old_3sx_installed(connection)
    installed_version = _read_installed_version(connection) if (installed or legacy_installed) else ""
    afs_present = False
    if installed:
        afs_present = _path_exists(connection, REMOTE_AFS_PATH)
    elif legacy_installed:
        afs_present = _path_exists(connection, OLD_REMOTE_AFS_PATH)

    update_available = False
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
        version_display = installed_version or latest_version or "unknown"
        status_text = f"✓ Installed ({version_display})"
        install_label = "Installed"
        install_enabled = False
        upload_enabled = not afs_present
        uninstall_enabled = True

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


def get_pico8_status(connection):
    if not connection.is_connected():
        return {
            "installed": False,
            "installed_version": "",
            "latest_version": "",
            "latest_error": "",
            "update_available": False,
            "status_text": "Unknown",
            "install_label": "Install",
            "install_enabled": False,
            "uninstall_enabled": False,
        }

    latest_version = ""
    latest_error = ""

    try:
        latest = _fetch_latest_pico8_release()
        latest_version = latest["version"]
    except Exception as exc:
        latest_error = str(exc)

    installed = _is_pico8_installed(connection)
    legacy_installed = _is_pico8_legacy_installed(connection)
    installed_version = _read_installed_pico8_version(connection) if (installed or legacy_installed) else ""

    update_available = False
    if (installed or legacy_installed) and latest_version and installed_version:
        update_available = installed_version != latest_version
    elif (installed or legacy_installed) and latest_version and not installed_version:
        update_available = True

    if not installed and not legacy_installed:
        status_text = "✗ Not installed"
        install_label = "Install"
        install_enabled = True
        uninstall_enabled = False
    elif legacy_installed and not installed:
        status_text = "✓ Legacy v1.1 install detected"
        install_label = "Migrate / Install"
        install_enabled = True
        uninstall_enabled = True
    elif update_available:
        status_text = f"▲ Update available ({installed_version or 'unknown'} → {latest_version})"
        install_label = "Update"
        install_enabled = True
        uninstall_enabled = True
    else:
        version_display = installed_version or latest_version or "unknown"
        status_text = f"✓ Installed ({version_display})"
        install_label = "Installed"
        install_enabled = False
        uninstall_enabled = True

    return {
        "installed": installed or legacy_installed,
        "installed_version": installed_version,
        "latest_version": latest_version,
        "latest_error": latest_error,
        "update_available": update_available,
        "status_text": status_text,
        "install_label": install_label,
        "install_enabled": install_enabled,
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


def install_or_update_pico8(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    _migrate_old_pico8_install(connection, log)

    latest = _fetch_latest_pico8_release()
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
            raise RuntimeError("The MiSTer Pico-8 ZIP archive is empty.")

        log("Inspecting archive contents...\n")

        rbf_member = None
        input_map_member = None
        binary_member = None
        bootrom_member = None
        daemon_member = None
        readme_member = None
        install_script_member = None

        for member in members:
            name = member.filename.replace("\\", "/")
            basename = posixpath.basename(name)
            parts = [p for p in name.split("/") if p]

            if parts[:1] == ["_Other"] and basename.startswith("PICO-8_") and basename.lower().endswith(".rbf"):
                rbf_member = member
                continue

            if parts[:2] == ["config", "inputs"] and basename.startswith("PICO-8_input_") and basename.lower().endswith(".map"):
                input_map_member = member
                continue

            if parts[:2] == ["games", "PICO-8"] and basename == "PICO-8":
                binary_member = member
                continue

            if parts[:2] == ["games", "PICO-8"] and basename == "boot.rom":
                bootrom_member = member
                continue

            if parts[:2] == ["games", "PICO-8"] and basename == "pico8_daemon.sh":
                daemon_member = member
                continue

            if parts[:2] == ["docs", "PICO-8"] and basename.lower() == "readme.md":
                readme_member = member
                continue

            if parts[:1] == ["Scripts"] and basename == "Install_PICO-8.sh":
                install_script_member = member
                continue

        missing = []
        if rbf_member is None:
            missing.append("_Other/PICO-8_*.rbf")
        if binary_member is None:
            missing.append("games/PICO-8/PICO-8")
        if bootrom_member is None:
            missing.append("games/PICO-8/boot.rom")
        if daemon_member is None:
            missing.append("games/PICO-8/pico8_daemon.sh")
        if readme_member is None:
            missing.append("docs/PICO-8/README.md")
        if install_script_member is None:
            missing.append("Scripts/Install_PICO-8.sh")

        if missing:
            raise RuntimeError(
                "The MiSTer Pico-8 ZIP archive is missing required files:\n- " + "\n- ".join(missing)
            )

        _ensure_remote_dir(connection, PICO8_REMOTE_RBF_DIR)
        _ensure_remote_dir(connection, PICO8_REMOTE_GAME_DIR)
        _ensure_remote_dir(connection, posixpath.join(PICO8_REMOTE_GAME_DIR, "Carts"))
        _ensure_remote_dir(connection, "/media/fat/logs/PICO-8")
        _ensure_remote_dir(connection, "/media/fat/saves/PICO-8")
        _ensure_remote_dir(connection, PICO8_REMOTE_DOCS_DIR)
        _ensure_remote_dir(connection, PICO8_REMOTE_SCRIPTS_DIR)
        _ensure_remote_dir(connection, PICO8_REMOTE_INPUTS_DIR)

        log("Removing old PICO-8 RBF files from /media/fat/_Other...\n")
        _remove_glob(connection, "/media/fat/_Other/PICO-8_*.rbf")

        log("Removing legacy PICO-8 RBF files from /media/fat/_Console...\n")
        _remove_glob(connection, "/media/fat/_Console/PICO-8_*.rbf")

        log("Removing old PICO-8 input map files...\n")
        _remove_glob(connection, "/media/fat/config/inputs/PICO-8_input_*.map")

        uploads = [
            (rbf_member, posixpath.join(PICO8_REMOTE_RBF_DIR, posixpath.basename(rbf_member.filename.replace("\\", "/")))),
            (binary_member, PICO8_REMOTE_BINARY_PATH),
            (bootrom_member, PICO8_REMOTE_BOOTROM_PATH),
            (daemon_member, PICO8_REMOTE_DAEMON_PATH),
            (readme_member, PICO8_REMOTE_README_PATH),
            (install_script_member, PICO8_REMOTE_INSTALL_SCRIPT_PATH),
        ]
        if input_map_member is not None:
            uploads.insert(
                1,
                (
                    input_map_member,
                    posixpath.join(
                        PICO8_REMOTE_INPUTS_DIR,
                        posixpath.basename(input_map_member.filename.replace("\\", "/")),
                    ),
                ),
            )

        sftp = connection.client.open_sftp()
        try:
            for member, destination in uploads:
                data = zf.read(member)
                log(f"Uploading {destination}\n")
                with sftp.open(destination, "wb") as remote_file:
                    remote_file.write(data)
        finally:
            sftp.close()

    connection.run_command(f"chmod +x {_quote(PICO8_REMOTE_BINARY_PATH)}")
    connection.run_command(f"chmod +x {_quote(PICO8_REMOTE_DAEMON_PATH)}")
    connection.run_command(f"chmod +x {_quote(PICO8_REMOTE_INSTALL_SCRIPT_PATH)}")

    added_startup = _ensure_startup_line(
        connection,
        PICO8_REMOTE_USER_STARTUP_PATH,
        PICO8_DAEMON_STARTUP_LINE,
    )
    if added_startup:
        log("Added pico8_daemon.sh entry to user-startup.sh\n")
    else:
        log("pico8_daemon.sh entry already present in user-startup.sh\n")

    _write_installed_pico8_version(connection, version)
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


def uninstall_pico8(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log("Removing PICO-8 RBF files from /media/fat/_Other\n")
    _remove_glob(connection, "/media/fat/_Other/PICO-8_*.rbf")

    log("Removing legacy PICO-8 RBF files from /media/fat/_Console\n")
    _remove_glob(connection, "/media/fat/_Console/PICO-8_*.rbf")

    log(f"Removing {PICO8_REMOTE_BINARY_PATH}\n")
    connection.run_command(f"rm -f {_quote(PICO8_REMOTE_BINARY_PATH)}")

    log(f"Removing {PICO8_REMOTE_DAEMON_PATH}\n")
    connection.run_command(f"rm -f {_quote(PICO8_REMOTE_DAEMON_PATH)}")

    log(f"Removing {PICO8_REMOTE_BOOTROM_PATH}\n")
    connection.run_command(f"rm -f {_quote(PICO8_REMOTE_BOOTROM_PATH)}")

    log(f"Removing {PICO8_REMOTE_README_PATH}\n")
    connection.run_command(f"rm -f {_quote(PICO8_REMOTE_README_PATH)}")

    log(f"Removing {PICO8_REMOTE_INSTALL_SCRIPT_PATH}\n")
    connection.run_command(f"rm -f {_quote(PICO8_REMOTE_INSTALL_SCRIPT_PATH)}")

    log("Removing PICO-8 input map files from /media/fat/config/inputs\n")
    _remove_glob(connection, "/media/fat/config/inputs/PICO-8_input_*.map")

    if _path_exists(connection, PICO8_REMOTE_VERSION_FILE):
        log(f"Removing version marker: {PICO8_REMOTE_VERSION_FILE}\n")
        connection.run_command(f"rm -f {_quote(PICO8_REMOTE_VERSION_FILE)}")

    removed_startup = _remove_startup_line(
        connection,
        PICO8_REMOTE_USER_STARTUP_PATH,
        PICO8_DAEMON_STARTUP_LINE,
    )
    if removed_startup:
        log("Removed pico8_daemon.sh entry from user-startup.sh\n")
    else:
        log("No pico8_daemon.sh entry found in user-startup.sh\n")

    _remove_if_empty_dir(connection, PICO8_REMOTE_DOCS_DIR)
    _remove_if_empty_dir(connection, PICO8_REMOTE_GAME_DIR)
    _remove_if_empty_dir(connection, PICO8_REMOTE_INPUTS_DIR)
    _remove_if_empty_dir(connection, PICO8_REMOTE_SCRIPTS_DIR)
    _remove_if_empty_dir(connection, PICO8_LEGACY_REMOTE_RBF_DIR)

    return {"uninstalled": True}
import io
import posixpath
import zipfile

import requests

from core.extras_common import (
    _ensure_remote_dir,
    _fetch_latest_zip_release,
    _glob_exists,
    _path_exists,
    _quote,
    _read_remote_text,
    _remove_glob,
    _remove_if_empty_dir,
    _write_remote_text,
)


OPENBOR_7533_GITHUB_REPO = "MiSTerOrganize/MiSTer_OpenBOR_7533"

OPENBOR_7533_REMOTE_RBF_DIR = "/media/fat/_Other"
OPENBOR_7533_REMOTE_GAME_DIR = "/media/fat/games/OpenBOR_7533"
OPENBOR_7533_REMOTE_PAKS_DIR = "/media/fat/games/OpenBOR_7533/Paks"
OPENBOR_7533_REMOTE_DOCS_DIR = "/media/fat/docs/OpenBOR_7533"
OPENBOR_7533_REMOTE_SCRIPTS_DIR = "/media/fat/Scripts"
OPENBOR_7533_REMOTE_LOGS_DIR = "/media/fat/logs/OpenBOR_7533"
OPENBOR_7533_REMOTE_SAVES_DIR = "/media/fat/saves/OpenBOR_7533"
OPENBOR_7533_REMOTE_SAVESTATES_DIR = "/media/fat/savestates/OpenBOR_7533"
OPENBOR_7533_REMOTE_VERSION_FILE = "/media/fat/games/OpenBOR_7533/.mister_companion_version"
OPENBOR_7533_REMOTE_BINARY_PATH = "/media/fat/games/OpenBOR_7533/OpenBOR"
OPENBOR_7533_REMOTE_DAEMON_PATH = "/media/fat/games/OpenBOR_7533/openbor_7533_daemon.sh"
OPENBOR_7533_REMOTE_README_PATH = "/media/fat/docs/OpenBOR_7533/README.md"
OPENBOR_7533_REMOTE_INSTALL_SCRIPT_PATH = "/media/fat/Scripts/Install_OpenBOR.sh"
OPENBOR_7533_REMOTE_USER_STARTUP_PATH = "/media/fat/linux/user-startup.sh"
OPENBOR_7533_DAEMON_STARTUP_COMMENT = "# OpenBOR 7533 auto-launch daemon"
OPENBOR_7533_DAEMON_STARTUP_LINE = "/media/fat/games/OpenBOR_7533/openbor_7533_daemon.sh &"


def _has_openbor_7533_rbf(connection) -> bool:
    return _glob_exists(connection, "/media/fat/_Other/OpenBOR_7533_*.rbf")


def _is_openbor_7533_installed(connection) -> bool:
    return (
        _has_openbor_7533_rbf(connection)
        and _path_exists(connection, OPENBOR_7533_REMOTE_BINARY_PATH)
        and _path_exists(connection, OPENBOR_7533_REMOTE_DAEMON_PATH)
    )


def _fetch_latest_openbor_7533_release():
    return _fetch_latest_zip_release(
        OPENBOR_7533_GITHUB_REPO,
        "MiSTer OpenBOR 7533",
    )


def _read_installed_openbor_7533_version(connection) -> str:
    return _read_remote_text(connection, OPENBOR_7533_REMOTE_VERSION_FILE).strip()


def _write_installed_openbor_7533_version(connection, version: str):
    _ensure_remote_dir(connection, posixpath.dirname(OPENBOR_7533_REMOTE_VERSION_FILE))
    _write_remote_text(connection, OPENBOR_7533_REMOTE_VERSION_FILE, version.strip() + "\n")


def _ensure_openbor_7533_startup_entry(connection) -> bool:
    current = _read_remote_text(connection, OPENBOR_7533_REMOTE_USER_STARTUP_PATH)
    normalized = current.replace("\r\n", "\n")

    kept_lines = []
    for entry in normalized.split("\n"):
        stripped = entry.strip()
        if "openbor_7533_daemon.sh" in stripped:
            continue
        if "OpenBOR 7533 auto-launch" in stripped:
            continue
        kept_lines.append(entry)

    updated = "\n".join(kept_lines).rstrip("\n")
    if updated:
        updated += "\n\n"

    updated += OPENBOR_7533_DAEMON_STARTUP_COMMENT + "\n"
    updated += OPENBOR_7533_DAEMON_STARTUP_LINE + "\n"

    if updated == normalized:
        return False

    _ensure_remote_dir(connection, posixpath.dirname(OPENBOR_7533_REMOTE_USER_STARTUP_PATH))
    _write_remote_text(connection, OPENBOR_7533_REMOTE_USER_STARTUP_PATH, updated)
    return True


def _remove_openbor_7533_startup_entry(connection) -> bool:
    current = _read_remote_text(connection, OPENBOR_7533_REMOTE_USER_STARTUP_PATH)
    if not current:
        return False

    normalized = current.replace("\r\n", "\n")
    original_lines = normalized.split("\n")

    kept_lines = []
    for entry in original_lines:
        stripped = entry.strip()
        if "openbor_7533_daemon.sh" in stripped:
            continue
        if "OpenBOR 7533 auto-launch" in stripped:
            continue
        kept_lines.append(entry)

    if kept_lines == original_lines:
        return False

    updated = "\n".join(kept_lines).rstrip("\n")
    if updated:
        updated += "\n"

    _write_remote_text(connection, OPENBOR_7533_REMOTE_USER_STARTUP_PATH, updated)
    return True


def get_openbor_7533_status(connection, check_latest: bool = False):
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

    if check_latest:
        try:
            latest = _fetch_latest_openbor_7533_release()
            latest_version = latest["version"]
        except Exception as exc:
            latest_error = str(exc)

    installed = _is_openbor_7533_installed(connection)
    installed_version = _read_installed_openbor_7533_version(connection) if installed else ""

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
        uninstall_enabled = False
    elif update_available:
        status_text = f"▲ Update available ({installed_version or 'unknown'} → {latest_version})"
        install_label = "Update"
        install_enabled = True
        uninstall_enabled = True
    else:
        version_display = installed_version or "unknown"
        status_text = f"✓ Installed ({version_display})"
        install_label = "Installed"
        install_enabled = False
        uninstall_enabled = True

    if latest_error and check_latest:
        status_text = f"{status_text} (update check failed: {latest_error})"

    return {
        "installed": installed,
        "installed_version": installed_version,
        "latest_version": latest_version,
        "latest_error": latest_error,
        "update_available": update_available,
        "status_text": status_text,
        "install_label": install_label,
        "install_enabled": install_enabled,
        "uninstall_enabled": uninstall_enabled,
    }


def install_or_update_openbor_7533(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    latest = _fetch_latest_openbor_7533_release()
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
            raise RuntimeError("The MiSTer OpenBOR 7533 ZIP archive is empty.")

        log("Inspecting archive contents...\n")

        rbf_member = None
        binary_member = None
        daemon_member = None
        readme_member = None
        install_script_member = None

        for member in members:
            name = member.filename.replace("\\", "/")
            basename = posixpath.basename(name)
            parts = [p for p in name.split("/") if p]

            if parts[:1] == ["_Other"] and basename.startswith("OpenBOR_7533_") and basename.lower().endswith(".rbf"):
                rbf_member = member
                continue

            if parts[:2] == ["games", "OpenBOR_7533"] and basename == "OpenBOR":
                binary_member = member
                continue

            if parts[:2] == ["games", "OpenBOR_7533"] and basename == "openbor_7533_daemon.sh":
                daemon_member = member
                continue

            if parts[:2] == ["docs", "OpenBOR_7533"] and basename.lower() == "readme.md":
                readme_member = member
                continue

            if parts[:1] == ["Scripts"] and basename == "Install_OpenBOR.sh":
                install_script_member = member
                continue

        missing = []
        if rbf_member is None:
            missing.append("_Other/OpenBOR_7533_*.rbf")
        if binary_member is None:
            missing.append("games/OpenBOR_7533/OpenBOR")
        if daemon_member is None:
            missing.append("games/OpenBOR_7533/openbor_7533_daemon.sh")
        if readme_member is None:
            missing.append("docs/OpenBOR_7533/README.md")
        if install_script_member is None:
            missing.append("Scripts/Install_OpenBOR.sh")

        if missing:
            raise RuntimeError(
                "The MiSTer OpenBOR 7533 ZIP archive is missing required files:\n- "
                + "\n- ".join(missing)
            )

        _ensure_remote_dir(connection, OPENBOR_7533_REMOTE_RBF_DIR)
        _ensure_remote_dir(connection, OPENBOR_7533_REMOTE_GAME_DIR)
        _ensure_remote_dir(connection, OPENBOR_7533_REMOTE_PAKS_DIR)
        _ensure_remote_dir(connection, OPENBOR_7533_REMOTE_LOGS_DIR)
        _ensure_remote_dir(connection, OPENBOR_7533_REMOTE_SAVES_DIR)
        _ensure_remote_dir(connection, OPENBOR_7533_REMOTE_SAVESTATES_DIR)
        _ensure_remote_dir(connection, OPENBOR_7533_REMOTE_DOCS_DIR)
        _ensure_remote_dir(connection, OPENBOR_7533_REMOTE_SCRIPTS_DIR)

        log("Removing old OpenBOR 7533 RBF files from /media/fat/_Other...\n")
        _remove_glob(connection, "/media/fat/_Other/OpenBOR_7533_*.rbf")

        uploads = [
            (
                rbf_member,
                posixpath.join(
                    OPENBOR_7533_REMOTE_RBF_DIR,
                    posixpath.basename(rbf_member.filename.replace("\\", "/")),
                ),
            ),
            (binary_member, OPENBOR_7533_REMOTE_BINARY_PATH),
            (daemon_member, OPENBOR_7533_REMOTE_DAEMON_PATH),
            (readme_member, OPENBOR_7533_REMOTE_README_PATH),
            (install_script_member, OPENBOR_7533_REMOTE_INSTALL_SCRIPT_PATH),
        ]

        sftp = connection.client.open_sftp()
        try:
            for member, destination in uploads:
                data = zf.read(member)
                log(f"Uploading {destination}\n")
                with sftp.open(destination, "wb") as remote_file:
                    remote_file.write(data)
        finally:
            sftp.close()

    connection.run_command(f"chmod +x {_quote(OPENBOR_7533_REMOTE_BINARY_PATH)}")
    connection.run_command(f"chmod +x {_quote(OPENBOR_7533_REMOTE_DAEMON_PATH)}")
    connection.run_command(f"chmod +x {_quote(OPENBOR_7533_REMOTE_INSTALL_SCRIPT_PATH)}")

    added_startup = _ensure_openbor_7533_startup_entry(connection)
    if added_startup:
        log("Added OpenBOR 7533 daemon entry to user-startup.sh\n")
    else:
        log("OpenBOR 7533 daemon entry already present in user-startup.sh\n")

    _write_installed_openbor_7533_version(connection, version)
    log(f"Stored installed version marker: {version}\n")

    return {
        "installed_version": version,
    }


def uninstall_openbor_7533(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log("Removing OpenBOR 7533 RBF files from /media/fat/_Other\n")
    _remove_glob(connection, "/media/fat/_Other/OpenBOR_7533_*.rbf")

    log(f"Removing {OPENBOR_7533_REMOTE_BINARY_PATH}\n")
    connection.run_command(f"rm -f {_quote(OPENBOR_7533_REMOTE_BINARY_PATH)}")

    log(f"Removing {OPENBOR_7533_REMOTE_DAEMON_PATH}\n")
    connection.run_command(f"rm -f {_quote(OPENBOR_7533_REMOTE_DAEMON_PATH)}")

    log(f"Removing {OPENBOR_7533_REMOTE_README_PATH}\n")
    connection.run_command(f"rm -f {_quote(OPENBOR_7533_REMOTE_README_PATH)}")

    log(f"Removing {OPENBOR_7533_REMOTE_INSTALL_SCRIPT_PATH}\n")
    connection.run_command(f"rm -f {_quote(OPENBOR_7533_REMOTE_INSTALL_SCRIPT_PATH)}")

    if _path_exists(connection, OPENBOR_7533_REMOTE_VERSION_FILE):
        log(f"Removing version marker: {OPENBOR_7533_REMOTE_VERSION_FILE}\n")
        connection.run_command(f"rm -f {_quote(OPENBOR_7533_REMOTE_VERSION_FILE)}")

    removed_startup = _remove_openbor_7533_startup_entry(connection)
    if removed_startup:
        log("Removed OpenBOR 7533 daemon entry from user-startup.sh\n")
    else:
        log("No OpenBOR 7533 daemon entry found in user-startup.sh\n")

    _remove_if_empty_dir(connection, OPENBOR_7533_REMOTE_DOCS_DIR)
    _remove_if_empty_dir(connection, OPENBOR_7533_REMOTE_GAME_DIR)
    _remove_if_empty_dir(connection, OPENBOR_7533_REMOTE_SCRIPTS_DIR)

    return {"uninstalled": True}
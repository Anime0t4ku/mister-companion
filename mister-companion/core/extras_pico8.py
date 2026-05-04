import io
import posixpath
import zipfile

import requests

from core.extras_common import (
    _ensure_remote_dir,
    _ensure_startup_line,
    _fetch_latest_zip_release,
    _glob_exists,
    _path_exists,
    _quote,
    _read_remote_text,
    _remove_glob,
    _remove_if_empty_dir,
    _remove_startup_line,
    _write_remote_text,
)


PICO8_GITHUB_REPO = "MiSTerOrganize/MiSTer_PICO-8"

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


def _fetch_latest_pico8_release():
    return _fetch_latest_zip_release(
        PICO8_GITHUB_REPO,
        "MiSTer Pico-8",
    )


def _read_installed_pico8_version(connection) -> str:
    return _read_remote_text(connection, PICO8_REMOTE_VERSION_FILE).strip()


def _write_installed_pico8_version(connection, version: str):
    _ensure_remote_dir(connection, posixpath.dirname(PICO8_REMOTE_VERSION_FILE))
    _write_remote_text(connection, PICO8_REMOTE_VERSION_FILE, version.strip() + "\n")


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


def get_pico8_status(connection, check_latest: bool = False):
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
            latest = _fetch_latest_pico8_release()
            latest_version = latest["version"]
        except Exception as exc:
            latest_error = str(exc)

    installed = _is_pico8_installed(connection)
    legacy_installed = _is_pico8_legacy_installed(connection)
    installed_version = _read_installed_pico8_version(connection) if (installed or legacy_installed) else ""

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
        version_display = installed_version or "unknown"
        status_text = f"✓ Installed ({version_display})"
        install_label = "Installed"
        install_enabled = False
        uninstall_enabled = True

    if latest_error and check_latest:
        status_text = f"{status_text} (update check failed: {latest_error})"

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
            (
                rbf_member,
                posixpath.join(
                    PICO8_REMOTE_RBF_DIR,
                    posixpath.basename(rbf_member.filename.replace("\\", "/")),
                ),
            ),
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
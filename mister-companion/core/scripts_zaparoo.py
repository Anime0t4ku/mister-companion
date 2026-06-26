import re
import shutil
import zipfile
from io import BytesIO

import requests

from core.scripts_common import (
    _chmod_local_executable,
    _local_path,
    _write_local_bytes,
    ensure_local_scripts_dir,
    ensure_remote_scripts_dir,
)


ZAPAROO_RELEASE_API = "https://api.github.com/repos/ZaparooProject/zaparoo-core/releases/latest"

ZAPAROO_SCRIPT_PATH = "/media/fat/Scripts/zaparoo.sh"
ZAPAROO_CONFIG_DIR = "/media/fat/zaparoo"
ZAPAROO_STARTUP_PATH = "/media/fat/linux/user-startup.sh"
ZAPAROO_STARTUP_MARKER = "# mrext/zaparoo"
ZAPAROO_STARTUP_LINE = "[[ -e /media/fat/Scripts/zaparoo.sh ]] && /media/fat/Scripts/zaparoo.sh -service $1"


def _normalize_version(value: str) -> str:
    match = re.search(r"v?([0-9]+(?:\.[0-9]+){1,3})", str(value or ""), re.IGNORECASE)
    return match.group(1) if match else ""


def _version_tuple(value: str):
    parts = []
    for part in _normalize_version(value).split("."):
        try:
            parts.append(int(part))
        except Exception:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _fetch_latest_zaparoo_version() -> str:
    response = requests.get(ZAPAROO_RELEASE_API, timeout=15)
    response.raise_for_status()
    data = response.json()
    return _normalize_version(data.get("tag_name") or data.get("name") or "")


def _parse_zaparoo_version_output(output: str) -> str:
    return _normalize_version(output)


def get_zaparoo_update_status(connection, check_latest: bool = False, log=None) -> dict:
    if connection is None or not connection.is_connected():
        return {"state": "needs_connection", "status_text": "Needs connection", "installed": False, "update_available": False}

    exists_output = connection.run_command(f"test -f {ZAPAROO_SCRIPT_PATH} && echo EXISTS")
    installed = "EXISTS" in (exists_output or "")
    if not installed:
        return {"state": "not_installed", "status_text": "Not installed", "installed": False, "update_available": False}

    installed_version = ""
    try:
        version_output = connection.run_command(f"sh {ZAPAROO_SCRIPT_PATH} --version 2>/dev/null || {ZAPAROO_SCRIPT_PATH} --version 2>/dev/null || true")
        installed_version = _parse_zaparoo_version_output(version_output)
    except Exception:
        installed_version = ""

    latest_version = ""
    latest_error = ""
    update_available = False

    if check_latest:
        if log:
            log("Checking latest Zaparoo release...\n")
        try:
            latest_version = _fetch_latest_zaparoo_version()
            if latest_version and installed_version:
                update_available = _version_tuple(installed_version) < _version_tuple(latest_version)
            elif latest_version and not installed_version:
                update_available = True
        except Exception as e:
            latest_error = str(e)

    service_output = connection.run_command(f"grep 'mrext/zaparoo' {ZAPAROO_STARTUP_PATH} 2>/dev/null || true")
    service_enabled = bool(service_output and "mrext/zaparoo" in service_output)

    if update_available:
        status_text = f"Update available ({installed_version or 'unknown'} → {latest_version})"
        state = "update_available"
    elif latest_error:
        status_text = f"Installed ({installed_version or 'unknown'}, update check failed)"
        state = "installed"
    elif installed_version:
        status_text = f"Installed ({installed_version})"
        state = "installed"
    else:
        status_text = "Installed"
        state = "installed"

    if not service_enabled and not update_available:
        if installed_version:
            status_text = f"Installed ({installed_version}), service disabled"
        else:
            status_text = "Installed, service disabled"

    return {
        "state": state,
        "status_text": status_text,
        "installed": True,
        "update_available": update_available,
        "installed_version": installed_version,
        "latest_version": latest_version,
        "latest_error": latest_error,
        "service_enabled": service_enabled,
    }


def get_zaparoo_update_status_local(sd_root, check_latest: bool = False, log=None) -> dict:
    script_path = _local_path(sd_root, ZAPAROO_SCRIPT_PATH)
    installed = script_path.is_file()
    if not installed:
        return {"state": "not_installed", "status_text": "Not installed", "installed": False, "update_available": False}

    latest_version = ""
    latest_error = ""
    if check_latest:
        try:
            latest_version = _fetch_latest_zaparoo_version()
        except Exception as e:
            latest_error = str(e)

    status_text = "Installed"
    if latest_error:
        status_text = f"Installed (update check failed: {latest_error})"

    return {
        "state": "installed",
        "status_text": status_text,
        "installed": True,
        "update_available": False,
        "installed_version": "",
        "latest_version": latest_version,
        "latest_error": latest_error,
        "service_enabled": False,
    }

def _download_zaparoo_script(log=None):
    if log:
        log("Fetching latest Zaparoo release...\n")

    response = requests.get(ZAPAROO_RELEASE_API, timeout=15)
    response.raise_for_status()
    api_data = response.json()

    download_url = None
    asset_name = None

    for asset in api_data.get("assets", []):
        name = asset["name"].lower()
        if "mister_arm" in name and name.endswith(".zip"):
            download_url = asset["browser_download_url"]
            asset_name = asset["name"]
            break

    if not download_url:
        raise RuntimeError("Could not find MiSTer Zaparoo release.")

    if log:
        log(f"Found release: {asset_name}\n")
        log("Downloading release...\n")

    zip_response = requests.get(download_url, timeout=30)
    zip_response.raise_for_status()

    zip_file = zipfile.ZipFile(BytesIO(zip_response.content))

    for entry in zip_file.namelist():
        if entry.endswith("zaparoo.sh"):
            return zip_file.read(entry)

    raise RuntimeError("Could not find zaparoo.sh inside the release ZIP.")


def _zaparoo_startup_block():
    return f"""#!/bin/sh

{ZAPAROO_STARTUP_MARKER}
{ZAPAROO_STARTUP_LINE}
"""


def _zaparoo_startup_entry():
    return f"""{ZAPAROO_STARTUP_MARKER}
{ZAPAROO_STARTUP_LINE}
"""


def install_zaparoo(connection, log):
    log("Installing Zaparoo...\n")
    zaparoo_data = _download_zaparoo_script(log)

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(ZAPAROO_SCRIPT_PATH, "wb") as remote_file:
            remote_file.write(zaparoo_data)
    finally:
        sftp.close()

    connection.run_command(f"chmod +x {ZAPAROO_SCRIPT_PATH}")
    log("Zaparoo installation complete.\n")
    log("Next step: Enable the Zaparoo service from the Scripts tab.\n")


def install_zaparoo_local(sd_root, log):
    log("Installing Zaparoo to Offline SD Card...\n")
    zaparoo_data = _download_zaparoo_script(log)

    ensure_local_scripts_dir(sd_root)

    _write_local_bytes(sd_root, ZAPAROO_SCRIPT_PATH, zaparoo_data)
    _chmod_local_executable(sd_root, ZAPAROO_SCRIPT_PATH)

    log("Zaparoo installation complete.\n")
    log("Next step: Enable the Zaparoo service so it starts when this SD card boots.\n")


def enable_zaparoo_service(connection):
    exists = connection.run_command(
        f"test -f {ZAPAROO_STARTUP_PATH} && echo EXISTS"
    )

    if "EXISTS" not in (exists or ""):
        sftp = connection.client.open_sftp()
        try:
            with sftp.open(ZAPAROO_STARTUP_PATH, "w") as handle:
                handle.write(_zaparoo_startup_block())
        finally:
            sftp.close()

        connection.run_command(f"chmod +x {ZAPAROO_STARTUP_PATH}")
        return

    check = connection.run_command(
        f"grep 'mrext/zaparoo' {ZAPAROO_STARTUP_PATH}"
    )

    if not check:
        connection.run_command(f'echo "" >> {ZAPAROO_STARTUP_PATH}')
        connection.run_command(f'echo "{ZAPAROO_STARTUP_MARKER}" >> {ZAPAROO_STARTUP_PATH}')
        connection.run_command(
            f'echo "{ZAPAROO_STARTUP_LINE}" >> {ZAPAROO_STARTUP_PATH}'
        )
        connection.run_command(f"chmod +x {ZAPAROO_STARTUP_PATH}")


def enable_zaparoo_service_local(sd_root):
    startup_path = _local_path(sd_root, ZAPAROO_STARTUP_PATH)
    startup_path.parent.mkdir(parents=True, exist_ok=True)

    if not startup_path.exists():
        startup_path.write_text(_zaparoo_startup_block(), encoding="utf-8")
        _chmod_local_executable(sd_root, ZAPAROO_STARTUP_PATH)
        return

    text = startup_path.read_text(encoding="utf-8", errors="ignore")
    if "mrext/zaparoo" in text:
        return

    text = text.rstrip() + "\n\n" + _zaparoo_startup_entry() + "\n"
    startup_path.write_text(text, encoding="utf-8")
    _chmod_local_executable(sd_root, ZAPAROO_STARTUP_PATH)


def disable_zaparoo_service_local(sd_root):
    startup_path = _local_path(sd_root, ZAPAROO_STARTUP_PATH)
    if not startup_path.exists():
        return

    lines = startup_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    new_lines = []
    skip_next = False

    for line in lines:
        if skip_next:
            skip_next = False
            continue

        if line.strip() == ZAPAROO_STARTUP_MARKER:
            skip_next = True
            continue

        new_lines.append(line)

    startup_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def uninstall_zaparoo(connection):
    connection.run_command(f"rm -f {ZAPAROO_SCRIPT_PATH}")
    connection.run_command(f"rm -rf {ZAPAROO_CONFIG_DIR}")


def uninstall_zaparoo_local(sd_root):
    script_path = _local_path(sd_root, ZAPAROO_SCRIPT_PATH)
    config_dir = _local_path(sd_root, ZAPAROO_CONFIG_DIR)

    disable_zaparoo_service_local(sd_root)

    if script_path.exists():
        script_path.unlink()

    if config_dir.exists():
        shutil.rmtree(config_dir)
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
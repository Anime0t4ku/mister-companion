import zipfile
from io import BytesIO

import requests

from core.scripts_common import ensure_remote_scripts_dir


ZAPAROO_RELEASE_API = "https://api.github.com/repos/ZaparooProject/zaparoo-core/releases/latest"


def install_zaparoo(connection, log):
    log("Installing Zaparoo...\n")
    api_data = requests.get(ZAPAROO_RELEASE_API, timeout=15).json()

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

    log(f"Found release: {asset_name}\n")
    log("Downloading release...\n")
    zip_data = requests.get(download_url, timeout=30).content
    zip_file = zipfile.ZipFile(BytesIO(zip_data))

    ensure_remote_scripts_dir(connection)

    zaparoo_data = None
    for entry in zip_file.namelist():
        if entry.endswith("zaparoo.sh"):
            zaparoo_data = zip_file.read(entry)
            break

    if zaparoo_data is None:
        raise RuntimeError("Could not find zaparoo.sh inside the release ZIP.")

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/zaparoo.sh", "wb") as remote_file:
            remote_file.write(zaparoo_data)
    finally:
        sftp.close()

    connection.run_command("chmod +x /media/fat/Scripts/zaparoo.sh")
    log("Zaparoo installation complete.\n")
    log("Next step: Enable the Zaparoo service from the Scripts tab.\n")


def enable_zaparoo_service(connection):
    exists = connection.run_command(
        "test -f /media/fat/linux/user-startup.sh && echo EXISTS"
    )

    if "EXISTS" not in (exists or ""):
        script = """#!/bin/sh

# mrext/zaparoo
[[ -e /media/fat/Scripts/zaparoo.sh ]] && /media/fat/Scripts/zaparoo.sh -service $1
"""
        sftp = connection.client.open_sftp()
        try:
            with sftp.open("/media/fat/linux/user-startup.sh", "w") as handle:
                handle.write(script)
        finally:
            sftp.close()
        return

    check = connection.run_command(
        "grep 'mrext/zaparoo' /media/fat/linux/user-startup.sh"
    )

    if not check:
        connection.run_command('echo "" >> /media/fat/linux/user-startup.sh')
        connection.run_command('echo "# mrext/zaparoo" >> /media/fat/linux/user-startup.sh')
        connection.run_command(
            'echo "[[ -e /media/fat/Scripts/zaparoo.sh ]] && /media/fat/Scripts/zaparoo.sh -service $1" >> /media/fat/linux/user-startup.sh'
        )


def uninstall_zaparoo(connection):
    connection.run_command("rm -f /media/fat/Scripts/zaparoo.sh")
    connection.run_command("rm -rf /media/fat/zaparoo")
import os
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from io import BytesIO

import requests


UPDATE_ALL_RELEASE_API = "https://api.github.com/repos/theypsilon/Update_All_MiSTer/releases/latest"
ZAPAROO_RELEASE_API = "https://api.github.com/repos/ZaparooProject/zaparoo-core/releases/latest"
MIGRATE_SD_URL = "https://raw.githubusercontent.com/Natrox/MiSTer_Utils_Natrox/main/scripts/migrate_sd.sh"
CIFS_MOUNT_URL = "https://raw.githubusercontent.com/MiSTer-devel/Scripts_MiSTer/master/cifs_mount.sh"
CIFS_UMOUNT_URL = "https://raw.githubusercontent.com/MiSTer-devel/Scripts_MiSTer/master/cifs_umount.sh"

UPDATE_ALL_JSON_PATH = "/media/fat/Scripts/.config/update_all/update_all.json"
DOWNLOADER_INI_PATH = "/media/fat/downloader.ini"

DEFAULT_UPDATE_ALL_JSON = """{"migration_version": 6, "theme": "Blue Installer", "mirror": "", "countdown_time": 15, "log_viewer": true, "use_settings_screen_theme_in_log_viewer": true, "autoreboot": true, "download_beta_cores": false, "names_region": "JP", "names_char_code": "CHAR18", "names_sort_code": "Common", "introduced_arcade_names_txt": true, "pocket_firmware_update": false, "pocket_backup": false, "timeline_after_logs": true, "overscan": "medium", "monochrome_ui": false}
"""

DEFAULT_DOWNLOADER_INI = """[distribution_mister]
db_url = https://raw.githubusercontent.com/MiSTer-devel/Distribution_MiSTer/main/db.json.zip

[jtcores]
db_url = https://raw.githubusercontent.com/jotego/jtcores_mister/main/jtbindb.json.zip

[Coin-OpCollection/Distribution-MiSTerFPGA]
db_url = https://raw.githubusercontent.com/Coin-OpCollection/Distribution-MiSTerFPGA/db/db.json.zip

[update_all_mister]
db_url = https://raw.githubusercontent.com/theypsilon/Update_All_MiSTer/db/update_all_db.json
"""


@dataclass
class ScriptsStatus:
    update_all_installed: bool
    update_all_initialized: bool
    zaparoo_installed: bool
    zaparoo_service_enabled: bool
    migrate_sd_installed: bool
    cifs_installed: bool
    cifs_configured: bool


def ensure_remote_scripts_dir(connection):
    connection.run_command("mkdir -p /media/fat/Scripts")
    connection.run_command("mkdir -p /media/fat/Scripts/.config/update_all")


def _remote_file_exists(sftp, path):
    try:
        sftp.stat(path)
        return True
    except Exception:
        return False


def ensure_update_all_config_bootstrap(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    ensure_remote_scripts_dir(connection)

    created = {
        "update_all_json_created": False,
        "downloader_ini_created": False,
    }

    sftp = connection.client.open_sftp()
    try:
        if not _remote_file_exists(sftp, UPDATE_ALL_JSON_PATH):
            with sftp.open(UPDATE_ALL_JSON_PATH, "w") as handle:
                handle.write(DEFAULT_UPDATE_ALL_JSON)
            created["update_all_json_created"] = True

        if not _remote_file_exists(sftp, DOWNLOADER_INI_PATH):
            with sftp.open(DOWNLOADER_INI_PATH, "w") as handle:
                handle.write(DEFAULT_DOWNLOADER_INI)
            created["downloader_ini_created"] = True
    finally:
        sftp.close()

    return created


def check_update_all_initialized(connection) -> bool:
    if not connection.is_connected():
        return False

    sftp = None
    try:
        sftp = connection.client.open_sftp()
        sftp.stat(UPDATE_ALL_JSON_PATH)
        return True
    except Exception:
        return False
    finally:
        if sftp is not None:
            sftp.close()


def get_scripts_status(connection) -> ScriptsStatus:
    if not connection.is_connected():
        return ScriptsStatus(False, False, False, False, False, False, False)

    update_check = connection.run_command(
        "test -f /media/fat/Scripts/update_all.sh && echo EXISTS"
    )
    update_all_installed = "EXISTS" in (update_check or "")

    zaparoo_check = connection.run_command(
        "test -f /media/fat/Scripts/zaparoo.sh && echo EXISTS"
    )
    zaparoo_installed = "EXISTS" in (zaparoo_check or "")

    zaparoo_service_check = connection.run_command(
        "grep 'mrext/zaparoo' /media/fat/linux/user-startup.sh 2>/dev/null"
    )
    zaparoo_service_enabled = bool(
        zaparoo_service_check and "mrext/zaparoo" in zaparoo_service_check
    )

    migrate_check = connection.run_command(
        "test -f /media/fat/Scripts/migrate_sd.sh && echo EXISTS"
    )
    migrate_sd_installed = "EXISTS" in (migrate_check or "")

    cifs_script_check = connection.run_command(
        "test -f /media/fat/Scripts/cifs_mount.sh && echo EXISTS"
    )
    cifs_ini_check = connection.run_command(
        "test -f /media/fat/Scripts/cifs_mount.ini && echo CONFIG"
    )

    cifs_installed = "EXISTS" in (cifs_script_check or "")
    cifs_configured = "CONFIG" in (cifs_ini_check or "")

    return ScriptsStatus(
        update_all_installed=update_all_installed,
        update_all_initialized=check_update_all_initialized(connection) if update_all_installed else False,
        zaparoo_installed=zaparoo_installed,
        zaparoo_service_enabled=zaparoo_service_enabled,
        migrate_sd_installed=migrate_sd_installed,
        cifs_installed=cifs_installed,
        cifs_configured=cifs_configured,
    )


def install_update_all(connection, log):
    log("Installing update_all...\n")
    api_data = requests.get(UPDATE_ALL_RELEASE_API, timeout=15).json()

    download_url = None
    asset_name = None
    for asset in api_data.get("assets", []):
        if asset["name"].endswith(".sh"):
            download_url = asset["browser_download_url"]
            asset_name = asset["name"]
            break

    if not download_url:
        raise RuntimeError("Could not find update_all script.")

    log(f"Found release: {asset_name}\n")
    log("Downloading release...\n")
    script_data = requests.get(download_url, timeout=30).content

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/update_all.sh", "wb") as remote_file:
            remote_file.write(script_data)
    finally:
        sftp.close()

    connection.run_command("chmod +x /media/fat/Scripts/update_all.sh")
    log("Installation complete.\n")


def uninstall_update_all(connection):
    connection.run_command("rm -f /media/fat/Scripts/update_all.sh")


def run_update_all_stream(connection, log):
    connection.run_command_stream("/media/fat/Scripts/update_all.sh", log)


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


def install_migrate_sd(connection, log):
    log("Installing migrate_sd...\n")
    script_data = requests.get(MIGRATE_SD_URL, timeout=30).content

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/migrate_sd.sh", "wb") as remote_file:
            remote_file.write(script_data)
    finally:
        sftp.close()

    connection.run_command("chmod +x /media/fat/Scripts/migrate_sd.sh")
    log("migrate_sd installed successfully.\n")
    log("Run it from the MiSTer Scripts menu.\n")


def uninstall_migrate_sd(connection):
    connection.run_command("rm -f /media/fat/Scripts/migrate_sd.sh")


def install_cifs_mount(connection, log):
    log("Installing cifs_mount scripts...\n")
    mount_script = requests.get(CIFS_MOUNT_URL, timeout=30).content
    umount_script = requests.get(CIFS_UMOUNT_URL, timeout=30).content

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/cifs_mount.sh", "wb") as remote_file:
            remote_file.write(mount_script)
        with sftp.open("/media/fat/Scripts/cifs_umount.sh", "wb") as remote_file:
            remote_file.write(umount_script)
    finally:
        sftp.close()

    connection.run_command("chmod +x /media/fat/Scripts/cifs_mount.sh")
    connection.run_command("chmod +x /media/fat/Scripts/cifs_umount.sh")
    log("CIFS scripts installed.\n")


def uninstall_cifs_mount(connection):
    connection.run_command("rm -f /media/fat/Scripts/cifs_mount.sh")
    connection.run_command("rm -f /media/fat/Scripts/cifs_umount.sh")


def run_cifs_mount(connection):
    return connection.run_command("/media/fat/Scripts/cifs_mount.sh")


def run_cifs_umount(connection):
    return connection.run_command("/media/fat/Scripts/cifs_umount.sh")


def remove_cifs_config(connection):
    connection.run_command("rm -f /media/fat/Scripts/cifs_mount.ini")


def load_cifs_config(connection):
    config = {}

    if not connection.is_connected():
        return config

    output = connection.run_command("cat /media/fat/Scripts/cifs_mount.ini 2>/dev/null")
    if not output:
        return config

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip()] = value.strip().strip('"')

    return config


def save_cifs_config(connection, server, share, username, password, mount_at_boot):
    ini = f'''SERVER="{server}"
SHARE="{share}"
USERNAME="{username}"
PASSWORD="{password}"
LOCAL_DIR="cifs/games"
WAIT_FOR_SERVER="true"
MOUNT_AT_BOOT="{str(mount_at_boot).lower()}"
SINGLE_CIFS_CONNECTION="true"
'''

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open("/media/fat/Scripts/cifs_mount.ini", "w") as remote_file:
            remote_file.write(ini)
    finally:
        sftp.close()


def test_cifs_connection(connection, server, share, username, password):
    test_cmd = (
        f'mount -t cifs //{server}/{share} /tmp/cifs_test '
        f'-o username="{username}",password="{password}"'
    )
    result = connection.run_command(
        f'mkdir -p /tmp/cifs_test && {test_cmd} && umount /tmp/cifs_test && echo SUCCESS'
    )
    return bool(result and "SUCCESS" in result)


def open_scripts_folder_on_host(ip, username="root", password="1"):
    if not ip:
        raise ValueError("No MiSTer IP address is available.")

    if sys.platform.startswith("win"):
        subprocess.Popen(f'explorer "\\\\{ip}\\sdcard\\Scripts"')
        return

    if sys.platform.startswith("linux"):
        env = os.environ.copy()
        subprocess.run(
            ["gio", "mount", f"smb://{ip}/"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.Popen(
            ["gio", "open", f"smb://{ip}/sdcard/Scripts"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    if sys.platform == "darwin":
        username = username or "root"
        password = password or "1"
        home = os.path.expanduser("~")
        mount_point = os.path.join(home, "MiSTer_sdcard")
        subprocess.run(["mkdir", "-p", mount_point], capture_output=True)
        subprocess.run(
            ["mount_smbfs", f"//{username}:{password}@{ip}/sdcard", mount_point],
            capture_output=True
        )
        subprocess.Popen(["open", os.path.join(mount_point, "Scripts")])
        return

    raise RuntimeError(f"Unsupported platform: {sys.platform}")
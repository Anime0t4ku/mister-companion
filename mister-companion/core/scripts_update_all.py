import requests

from core.scripts_common import (
    DOWNLOADER_INI_PATH,
    UPDATE_ALL_JSON_PATH,
    DEFAULT_DOWNLOADER_INI,
    DEFAULT_UPDATE_ALL_JSON,
    _remote_file_exists,
    ensure_remote_scripts_dir,
)


UPDATE_ALL_RELEASE_API = "https://api.github.com/repos/theypsilon/Update_All_MiSTer/releases/latest"


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
import requests

from core.scripts_common import (
    DOWNLOADER_INI_PATH,
    UPDATE_ALL_JSON_PATH,
    DEFAULT_DOWNLOADER_INI,
    DEFAULT_UPDATE_ALL_JSON,
    _chmod_local_executable,
    _local_path,
    _remote_file_exists,
    _write_local_bytes,
    ensure_local_scripts_dir,
    ensure_remote_scripts_dir,
)


UPDATE_ALL_RELEASE_API = "https://api.github.com/repos/theypsilon/Update_All_MiSTer/releases/latest"
UPDATE_ALL_SCRIPT_PATH = "/media/fat/Scripts/update_all.sh"


def _download_update_all_script(log):
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

    response = requests.get(download_url, timeout=30)
    response.raise_for_status()
    return response.content


def install_update_all(connection, log):
    log("Installing update_all...\n")
    script_data = _download_update_all_script(log)

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(UPDATE_ALL_SCRIPT_PATH, "wb") as remote_file:
            remote_file.write(script_data)
    finally:
        sftp.close()

    connection.run_command(f"chmod +x {UPDATE_ALL_SCRIPT_PATH}")
    log("Installation complete.\n")


def install_update_all_local(sd_root, log):
    log("Installing update_all to Offline SD Card...\n")
    script_data = _download_update_all_script(log)

    ensure_local_scripts_dir(sd_root)
    _write_local_bytes(sd_root, UPDATE_ALL_SCRIPT_PATH, script_data)
    _chmod_local_executable(sd_root, UPDATE_ALL_SCRIPT_PATH)

    log("Installation complete.\n")


def uninstall_update_all(connection):
    connection.run_command(f"rm -f {UPDATE_ALL_SCRIPT_PATH}")


def uninstall_update_all_local(sd_root):
    path = _local_path(sd_root, UPDATE_ALL_SCRIPT_PATH)
    if path.exists():
        path.unlink()


def run_update_all_stream(connection, log):
    connection.run_command_stream(UPDATE_ALL_SCRIPT_PATH, log)


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


def ensure_update_all_config_bootstrap_local(sd_root):
    ensure_local_scripts_dir(sd_root)

    created = {
        "update_all_json_created": False,
        "downloader_ini_created": False,
    }

    update_all_json_path = _local_path(sd_root, UPDATE_ALL_JSON_PATH)
    downloader_ini_path = _local_path(sd_root, DOWNLOADER_INI_PATH)

    if not update_all_json_path.exists():
        update_all_json_path.parent.mkdir(parents=True, exist_ok=True)
        update_all_json_path.write_text(DEFAULT_UPDATE_ALL_JSON, encoding="utf-8")
        created["update_all_json_created"] = True

    if not downloader_ini_path.exists():
        downloader_ini_path.parent.mkdir(parents=True, exist_ok=True)
        downloader_ini_path.write_text(DEFAULT_DOWNLOADER_INI, encoding="utf-8")
        created["downloader_ini_created"] = True

    return created
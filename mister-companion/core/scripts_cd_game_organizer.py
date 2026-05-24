import requests

from core.scripts_common import (
    _chmod_local_executable,
    _local_path,
    _write_local_bytes,
    ensure_local_scripts_dir,
    ensure_remote_scripts_dir,
)


CD_GAME_ORGANIZER_URL = "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/main/Scripts/cd_game_organizer.sh"
CD_GAME_ORGANIZER_SCRIPT_PATH = "/media/fat/Scripts/cd_game_organizer.sh"


def _download_cd_game_organizer_script():
    response = requests.get(CD_GAME_ORGANIZER_URL, timeout=30)
    response.raise_for_status()
    return response.content


def install_cd_game_organizer(connection, log):
    log("Installing cd_game_organizer...\n")
    script_data = _download_cd_game_organizer_script()

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(CD_GAME_ORGANIZER_SCRIPT_PATH, "wb") as remote_file:
            remote_file.write(script_data)
    finally:
        sftp.close()

    connection.run_command(f"chmod +x {CD_GAME_ORGANIZER_SCRIPT_PATH}")
    log("cd_game_organizer installed successfully.\n")


def install_cd_game_organizer_local(sd_root, log):
    log("Installing cd_game_organizer to Offline SD Card...\n")
    script_data = _download_cd_game_organizer_script()

    ensure_local_scripts_dir(sd_root)
    _write_local_bytes(sd_root, CD_GAME_ORGANIZER_SCRIPT_PATH, script_data)
    _chmod_local_executable(sd_root, CD_GAME_ORGANIZER_SCRIPT_PATH)

    log("cd_game_organizer installed successfully.\n")
    log("Run it from the MiSTer Scripts menu after booting this SD card.\n")


def uninstall_cd_game_organizer(connection):
    connection.run_command(f"rm -f {CD_GAME_ORGANIZER_SCRIPT_PATH}")


def uninstall_cd_game_organizer_local(sd_root):
    path = _local_path(sd_root, CD_GAME_ORGANIZER_SCRIPT_PATH)
    if path.exists():
        path.unlink()

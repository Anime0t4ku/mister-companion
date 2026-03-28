import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

from core.config import save_config
from core.profile_folder_sync import get_profile_or_ip_folder_name


SAVE_ROOT = Path("SaveManager")
BACKUP_ROOT = SAVE_ROOT / "backups"
SYNC_ROOT = SAVE_ROOT / "sync"

REMOTE_SAVES_DIR = "/media/fat/saves"
REMOTE_SAVESTATES_DIR = "/media/fat/savestates"


def ensure_savemanager_dirs():
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    SYNC_ROOT.mkdir(parents=True, exist_ok=True)


def ensure_remote_save_dirs(connection, log_callback=None):
    if not connection.is_connected():
        return

    if log_callback:
        log_callback("Checking MiSTer save folders...")

    connection.run_command(f'mkdir -p "{REMOTE_SAVES_DIR}"')
    connection.run_command(f'mkdir -p "{REMOTE_SAVESTATES_DIR}"')

    if log_callback:
        log_callback("MiSTer save folders are ready.")


def get_device_folder_name(profile_name: str = "", ip_address: str = "") -> str:
    return get_profile_or_ip_folder_name(profile_name=profile_name, ip_address=ip_address)


def get_device_backup_root(profile_name: str = "", ip_address: str = "") -> Path:
    device_name = get_device_folder_name(profile_name, ip_address)
    if not device_name:
        return BACKUP_ROOT
    return BACKUP_ROOT / device_name


def get_backup_count(profile_name: str = "", ip_address: str = "") -> int:
    device_root = get_device_backup_root(profile_name, ip_address)
    if not device_root.exists():
        return 0

    return len([p for p in device_root.iterdir() if p.is_dir()])


def list_backups_for_device(profile_name: str = "", ip_address: str = ""):
    device_root = get_device_backup_root(profile_name, ip_address)
    if not device_root.exists():
        return []

    backups = [p.name for p in device_root.iterdir() if p.is_dir()]
    backups.sort(reverse=True)
    return backups


def enforce_backup_retention(config_data, profile_name: str = "", ip_address: str = "", log_callback=None):
    retention = int(config_data.get("backup_retention", 10))
    if retention < 1:
        retention = 1

    device_root = get_device_backup_root(profile_name, ip_address)
    if not device_root.exists():
        return

    backups = sorted([p for p in device_root.iterdir() if p.is_dir()], key=lambda p: p.name)

    while len(backups) > retention:
        oldest = backups.pop(0)
        shutil.rmtree(oldest, ignore_errors=True)
        if log_callback:
            log_callback(f"Old backup removed: {oldest.name}")


def save_retention_setting(config_data, value: int):
    try:
        value = int(value)
    except Exception:
        value = 10

    if value < 1:
        value = 1

    config_data["backup_retention"] = value
    save_config(config_data)
    return value


def open_folder(path: Path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)

    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", str(path)])
    elif sys.platform.startswith("linux"):
        env = os.environ.copy()
        subprocess.Popen(
            ["gio", "open", str(path)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])


def _download_dir(sftp, remote_dir: str, local_dir: Path):
    local_dir.mkdir(parents=True, exist_ok=True)

    for item in sftp.listdir_attr(remote_dir):
        remote_path = f"{remote_dir}/{item.filename}"
        local_path = local_dir / item.filename

        if stat.S_ISDIR(item.st_mode):
            _download_dir(sftp, remote_path, local_path)
        else:
            sftp.get(remote_path, str(local_path))


def _upload_dir(connection, sftp, local_dir: Path, remote_dir: str):
    if not local_dir.exists():
        return

    try:
        connection.run_command(f'mkdir -p "{remote_dir}"')
    except Exception:
        pass

    for item in local_dir.iterdir():
        remote_path = f"{remote_dir}/{item.name}"

        if item.is_dir():
            _upload_dir(connection, sftp, item, remote_path)
        else:
            sftp.put(str(item), remote_path)


def _merge_remote_newer_into_local(sftp, remote_dir: str, local_dir: Path):
    local_dir.mkdir(parents=True, exist_ok=True)

    for item in sftp.listdir_attr(remote_dir):
        remote_path = f"{remote_dir}/{item.filename}"
        local_path = local_dir / item.filename

        if stat.S_ISDIR(item.st_mode):
            _merge_remote_newer_into_local(sftp, remote_path, local_path)
        else:
            remote_time = item.st_mtime

            if local_path.exists():
                try:
                    local_time = local_path.stat().st_mtime
                except Exception:
                    local_time = 0

                if remote_time > local_time:
                    shutil.copy2(local_path, local_path) if False else None
                    sftp.get(remote_path, str(local_path))
            else:
                sftp.get(remote_path, str(local_path))


def _merge_local_dir_newer_into_local(source_dir: Path, target_dir: Path):
    if not source_dir.exists():
        return

    target_dir.mkdir(parents=True, exist_ok=True)

    for item in source_dir.iterdir():
        target_path = target_dir / item.name

        if item.is_dir():
            _merge_local_dir_newer_into_local(item, target_path)
        else:
            source_time = item.stat().st_mtime

            if target_path.exists():
                try:
                    target_time = target_path.stat().st_mtime
                except Exception:
                    target_time = 0

                if source_time > target_time:
                    shutil.copy2(item, target_path)
            else:
                shutil.copy2(item, target_path)


def rebuild_sync_folder_from_latest_backups(log_callback=None):
    ensure_savemanager_dirs()

    sync_saves_path = SYNC_ROOT / "saves"
    sync_savestates_path = SYNC_ROOT / "savestates"

    if sync_saves_path.exists():
        shutil.rmtree(sync_saves_path, ignore_errors=True)
    if sync_savestates_path.exists():
        shutil.rmtree(sync_savestates_path, ignore_errors=True)

    sync_saves_path.mkdir(parents=True, exist_ok=True)
    sync_savestates_path.mkdir(parents=True, exist_ok=True)

    if not BACKUP_ROOT.exists():
        return

    device_folders = sorted([p for p in BACKUP_ROOT.iterdir() if p.is_dir()], key=lambda p: p.name.lower())

    for device_folder in device_folders:
        backups = sorted(
            [p for p in device_folder.iterdir() if p.is_dir()],
            key=lambda p: p.name,
            reverse=True
        )

        if not backups:
            continue

        latest_backup = backups[0]
        latest_saves = latest_backup / "saves"
        latest_savestates = latest_backup / "savestates"

        if log_callback:
            log_callback(f"Merging latest backup from {device_folder.name}: {latest_backup.name}")

        _merge_local_dir_newer_into_local(latest_saves, sync_saves_path)
        _merge_local_dir_newer_into_local(latest_savestates, sync_savestates_path)


def create_backup(connection, config_data, profile_name: str = "", ip_address: str = "", log_callback=None):
    ensure_savemanager_dirs()
    ensure_remote_save_dirs(connection, log_callback=log_callback)

    device_root = get_device_backup_root(profile_name, ip_address)
    if not device_root.name:
        raise RuntimeError("No device name or IP available.")

    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = device_root / timestamp
    saves_path = backup_path / "saves"
    savestates_path = backup_path / "savestates"

    backup_path.mkdir(parents=True, exist_ok=True)

    if log_callback:
        log_callback("Starting backup...")

    sftp = connection.client.open_sftp()
    try:
        _download_dir(sftp, REMOTE_SAVES_DIR, saves_path)
        _download_dir(sftp, REMOTE_SAVESTATES_DIR, savestates_path)
    finally:
        sftp.close()

    if log_callback:
        log_callback(f"Backup created: {backup_path}")

    enforce_backup_retention(config_data, profile_name, ip_address, log_callback=log_callback)

    if log_callback:
        log_callback("Rebuilding sync folder from latest backups...")

    rebuild_sync_folder_from_latest_backups(log_callback=log_callback)

    return backup_path


def restore_backup(connection, backup_name: str, profile_name: str = "", ip_address: str = "", log_callback=None):
    ensure_remote_save_dirs(connection, log_callback=log_callback)

    device_root = get_device_backup_root(profile_name, ip_address)
    backup_path = device_root / backup_name

    if not backup_path.exists():
        raise RuntimeError("Selected backup was not found.")

    saves_path = backup_path / "saves"
    savestates_path = backup_path / "savestates"

    if log_callback:
        log_callback(f"Restoring backup: {backup_name}")

    sftp = connection.client.open_sftp()
    try:
        _upload_dir(connection, sftp, saves_path, REMOTE_SAVES_DIR)
        _upload_dir(connection, sftp, savestates_path, REMOTE_SAVESTATES_DIR)
    finally:
        sftp.close()

    if log_callback:
        log_callback("Restore completed successfully.")


def sync_saves(connection, log_callback=None):
    ensure_savemanager_dirs()
    ensure_remote_save_dirs(connection, log_callback=log_callback)

    sync_saves_path = SYNC_ROOT / "saves"
    sync_savestates_path = SYNC_ROOT / "savestates"

    if not sync_saves_path.exists() or not sync_savestates_path.exists():
        if log_callback:
            log_callback("Sync folder missing, rebuilding from latest backups...")
        rebuild_sync_folder_from_latest_backups(log_callback=log_callback)

    if log_callback:
        log_callback("Downloading newest saves from MiSTer...")

    sftp = connection.client.open_sftp()
    try:
        _merge_remote_newer_into_local(sftp, REMOTE_SAVES_DIR, sync_saves_path)
        _merge_remote_newer_into_local(sftp, REMOTE_SAVESTATES_DIR, sync_savestates_path)

        if log_callback:
            log_callback("Uploading newest saves to MiSTer...")

        _upload_dir(connection, sftp, sync_saves_path, REMOTE_SAVES_DIR)
        _upload_dir(connection, sftp, sync_savestates_path, REMOTE_SAVESTATES_DIR)
    finally:
        sftp.close()

    if log_callback:
        log_callback("Sync completed successfully.")
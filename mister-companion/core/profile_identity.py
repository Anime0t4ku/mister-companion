from core.device_profiles import get_profile_sync_roots
from core.profile_folder_sync import profile_assigned_to_ip, profile_removed, profile_renamed
from core.zaplauncher_db import rename_db


def migrate_profile_identity(old_name: str, old_ip: str, new_name: str, new_ip: str) -> None:
    """Apply the same name/IP migration used by manual profile edits."""
    old_name = str(old_name or "").strip()
    old_ip = str(old_ip or "").strip()
    new_name = str(new_name or "").strip()
    new_ip = str(new_ip or "").strip()

    if not new_name:
        return

    roots = get_profile_sync_roots()
    if old_name and old_name != new_name:
        profile_renamed(roots, old_name, new_name)
        rename_db(old_name, new_name)
    elif old_ip and old_ip != new_ip:
        profile_assigned_to_ip(roots, new_ip, new_name)
        rename_db(old_ip, new_name)


def remove_profile_identity(profile_name: str, ip_address: str) -> None:
    """Apply the same backup/DB migration used by a manual profile removal."""
    profile_name = str(profile_name or "").strip()
    ip_address = str(ip_address or "").strip()
    if not profile_name:
        return

    profile_removed(get_profile_sync_roots(), profile_name, ip_address)
    rename_db(profile_name, ip_address)

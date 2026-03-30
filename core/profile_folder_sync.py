import os
import shutil


def sanitize_folder_name(name: str) -> str:
    if not name:
        return ""

    invalid_chars = '<>:"/\\|?*'
    cleaned = "".join("_" if c in invalid_chars else c for c in str(name).strip())
    return cleaned.rstrip(" .")


def ip_to_folder_name(ip_address: str) -> str:
    if not ip_address:
        return ""
    return sanitize_folder_name(str(ip_address).replace(".", "_").strip())


def get_profile_or_ip_folder_name(profile_name: str = "", ip_address: str = "") -> str:
    profile_name = sanitize_folder_name(profile_name)
    if profile_name and profile_name != "Select Device":
        return profile_name
    return ip_to_folder_name(ip_address)


def rename_device_folder(root_folder: str, old_name: str, new_name: str) -> bool:
    old_name = sanitize_folder_name(old_name)
    new_name = sanitize_folder_name(new_name)

    if not root_folder or not old_name or not new_name or old_name == new_name:
        return False

    old_path = os.path.join(root_folder, old_name)
    new_path = os.path.join(root_folder, new_name)

    if not os.path.exists(old_path):
        return False

    os.makedirs(root_folder, exist_ok=True)

    if not os.path.exists(new_path):
        os.rename(old_path, new_path)
        return True

    merge_device_folders(old_path, new_path)

    try:
        os.rmdir(old_path)
    except OSError:
        pass

    return True


def merge_device_folders(source_folder: str, target_folder: str) -> None:
    os.makedirs(target_folder, exist_ok=True)

    for entry in os.listdir(source_folder):
        src = os.path.join(source_folder, entry)
        dst = os.path.join(target_folder, entry)

        if os.path.isdir(src):
            if os.path.exists(dst):
                merge_device_folders(src, dst)
                try:
                    os.rmdir(src)
                except OSError:
                    pass
            else:
                shutil.move(src, dst)
        else:
            dst = get_non_conflicting_path(dst)
            shutil.move(src, dst)


def get_non_conflicting_path(path: str) -> str:
    if not os.path.exists(path):
        return path

    folder, filename = os.path.split(path)
    base, ext = os.path.splitext(filename)
    counter = 1

    while True:
        new_path = os.path.join(folder, f"{base}_{counter}{ext}")
        if not os.path.exists(new_path):
            return new_path
        counter += 1


def rename_device_folder_across_roots(root_folders, old_name: str, new_name: str) -> bool:
    changed = False

    for root_folder in root_folders:
        if rename_device_folder(root_folder, old_name, new_name):
            changed = True

    return changed


def profile_renamed(root_folders, old_profile_name: str, new_profile_name: str) -> bool:
    return rename_device_folder_across_roots(root_folders, old_profile_name, new_profile_name)


def profile_removed(root_folders, removed_profile_name: str, ip_address: str) -> bool:
    return rename_device_folder_across_roots(
        root_folders,
        removed_profile_name,
        ip_to_folder_name(ip_address)
    )


def profile_assigned_to_ip(root_folders, ip_address: str, profile_name: str) -> bool:
    return rename_device_folder_across_roots(
        root_folders,
        ip_to_folder_name(ip_address),
        profile_name
    )
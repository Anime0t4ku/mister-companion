import os
import posixpath
import stat
from pathlib import Path

SAFE_ROOTS = ["/media/fat", "/media/usb0"]
DEFAULT_ROOT = "/media/fat"
USB_ROOT = "/media/usb0"


def normalize_remote_path(path):
    path = str(path or DEFAULT_ROOT).replace("\\", "/").strip()
    if not path.startswith("/"):
        path = "/" + path
    normalized = posixpath.normpath(path)
    if normalized == ".":
        normalized = DEFAULT_ROOT
    return normalized


def root_for_path(path):
    path = normalize_remote_path(path)
    matches = [root for root in SAFE_ROOTS if path == root or path.startswith(root + "/")]
    if not matches:
        return ""
    return max(matches, key=len)


def is_safe_path(path):
    return bool(root_for_path(path))


def clamp_to_root(path, fallback=DEFAULT_ROOT):
    path = normalize_remote_path(path)
    if is_safe_path(path):
        return path
    return fallback


def parent_path(path):
    path = normalize_remote_path(path)
    root = root_for_path(path)
    if not root or path == root:
        return path
    parent = posixpath.dirname(path.rstrip("/"))
    if parent == "/":
        return root
    if not (parent == root or parent.startswith(root + "/")):
        return root
    return parent


def join_remote_path(base, name):
    base = normalize_remote_path(base)
    name = str(name or "").replace("\\", "/").strip("/")
    return normalize_remote_path(posixpath.join(base, name))


def format_size(size):
    try:
        size = int(size)
    except Exception:
        return ""

    if size < 1024:
        return f"{size} B"

    units = ["KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        value /= 1024.0
        if value < 1024.0 or unit == units[-1]:
            if value >= 100:
                return f"{value:.0f} {unit}"
            if value >= 10:
                return f"{value:.1f} {unit}"
            return f"{value:.2f} {unit}"

    return f"{size} B"


def sftp_exists(sftp, path):
    try:
        sftp.stat(path)
        return True
    except Exception:
        return False


def available_roots(connection):
    sftp = connection.client.open_sftp()
    try:
        roots = [{"name": "SD Card", "path": DEFAULT_ROOT, "available": sftp_exists(sftp, DEFAULT_ROOT)}]
        if sftp_exists(sftp, USB_ROOT):
            roots.append({"name": "USB Drive", "path": USB_ROOT, "available": True})
        return roots
    finally:
        sftp.close()


def list_directory(connection, remote_path):
    remote_path = clamp_to_root(remote_path)
    sftp = connection.client.open_sftp()
    try:
        entries = []
        for attr in sftp.listdir_attr(remote_path):
            name = attr.filename
            if name in {".", ".."}:
                continue

            is_dir = stat.S_ISDIR(attr.st_mode)
            item_path = join_remote_path(remote_path, name)
            entries.append(
                {
                    "name": name,
                    "path": item_path,
                    "is_dir": is_dir,
                    "type": "Folder" if is_dir else "File",
                    "size": int(attr.st_size or 0),
                    "mtime": int(attr.st_mtime or 0),
                }
            )

        entries.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
        return {"path": remote_path, "entries": entries}
    finally:
        sftp.close()


def ensure_remote_dir(sftp, remote_dir):
    remote_dir = normalize_remote_path(remote_dir)
    parts = [part for part in remote_dir.split("/") if part]
    current = ""
    for part in parts:
        current += "/" + part
        try:
            sftp.stat(current)
        except Exception:
            sftp.mkdir(current)


def upload_path(connection, local_path, remote_dir, progress_callback=None, message_callback=None):
    local_path = Path(local_path)
    remote_dir = clamp_to_root(remote_dir)
    sftp = connection.client.open_sftp()
    try:
        if local_path.is_dir():
            target_root = join_remote_path(remote_dir, local_path.name)
            upload_folder(sftp, local_path, target_root, progress_callback, message_callback)
            return target_root

        target_path = join_remote_path(remote_dir, local_path.name)
        if message_callback:
            message_callback(f"Uploading {local_path.name}...")
        sftp.put(str(local_path), target_path, callback=progress_callback)
        return target_path
    finally:
        sftp.close()


def upload_folder(sftp, local_folder, remote_folder, progress_callback=None, message_callback=None):
    ensure_remote_dir(sftp, remote_folder)
    for root, dirs, files in os.walk(local_folder):
        root_path = Path(root)
        relative = root_path.relative_to(local_folder)
        current_remote = remote_folder if str(relative) == "." else join_remote_path(remote_folder, str(relative).replace(os.sep, "/"))
        ensure_remote_dir(sftp, current_remote)

        for dirname in dirs:
            ensure_remote_dir(sftp, join_remote_path(current_remote, dirname))

        for filename in files:
            local_file = root_path / filename
            remote_file = join_remote_path(current_remote, filename)
            if message_callback:
                message_callback(f"Uploading {local_file.name}...")
            sftp.put(str(local_file), remote_file, callback=progress_callback)


def download_path(connection, remote_path, local_dir, progress_callback=None, message_callback=None):
    remote_path = clamp_to_root(remote_path)
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    sftp = connection.client.open_sftp()
    try:
        attr = sftp.stat(remote_path)
        name = posixpath.basename(remote_path.rstrip("/"))
        target = local_dir / name
        if stat.S_ISDIR(attr.st_mode):
            download_folder(sftp, remote_path, target, progress_callback, message_callback)
            return str(target)

        if message_callback:
            message_callback(f"Downloading {name}...")
        sftp.get(remote_path, str(target), callback=progress_callback)
        return str(target)
    finally:
        sftp.close()


def download_folder(sftp, remote_folder, local_folder, progress_callback=None, message_callback=None):
    local_folder = Path(local_folder)
    local_folder.mkdir(parents=True, exist_ok=True)
    for attr in sftp.listdir_attr(remote_folder):
        name = attr.filename
        if name in {".", ".."}:
            continue
        remote_item = join_remote_path(remote_folder, name)
        local_item = local_folder / name
        if stat.S_ISDIR(attr.st_mode):
            download_folder(sftp, remote_item, local_item, progress_callback, message_callback)
        else:
            if message_callback:
                message_callback(f"Downloading {name}...")
            sftp.get(remote_item, str(local_item), callback=progress_callback)


def make_directory(connection, remote_path):
    remote_path = clamp_to_root(remote_path)
    sftp = connection.client.open_sftp()
    try:
        sftp.mkdir(remote_path)
    finally:
        sftp.close()


def rename_path(connection, old_path, new_path):
    old_path = clamp_to_root(old_path)
    new_path = clamp_to_root(new_path)
    if root_for_path(old_path) != root_for_path(new_path):
        raise ValueError("Items cannot be moved outside the selected storage root.")
    sftp = connection.client.open_sftp()
    try:
        sftp.rename(old_path, new_path)
    finally:
        sftp.close()


def delete_path(connection, remote_path):
    remote_path = clamp_to_root(remote_path)
    root = root_for_path(remote_path)
    if not root or remote_path == root:
        raise ValueError("The storage root cannot be deleted.")
    sftp = connection.client.open_sftp()
    try:
        delete_path_with_sftp(sftp, remote_path)
    finally:
        sftp.close()


def delete_path_with_sftp(sftp, remote_path):
    attr = sftp.stat(remote_path)
    if stat.S_ISDIR(attr.st_mode):
        for child in sftp.listdir_attr(remote_path):
            if child.filename in {".", ".."}:
                continue
            delete_path_with_sftp(sftp, join_remote_path(remote_path, child.filename))
        sftp.rmdir(remote_path)
    else:
        sftp.remove(remote_path)

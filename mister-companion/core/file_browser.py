import os
import posixpath
import re
import shutil
import stat
from pathlib import Path

SAFE_ROOTS = ["/media/fat"]
DEFAULT_ROOT = "/media/fat"
USB_ROOT = "/media/usb0"
USB_ROOT_PATTERN = re.compile(r"^/media/usb(\d+)(?:/|$)")


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
    usb_match = USB_ROOT_PATTERN.match(path)
    if usb_match:
        matches.append(f"/media/usb{usb_match.group(1)}")
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


def remote_exists(connection, path):
    path = clamp_to_root(path)
    sftp = connection.client.open_sftp()
    try:
        return sftp_exists(sftp, path)
    finally:
        sftp.close()


def available_roots(connection):
    mount_output = connection.run_command("awk '{print $2}' /proc/mounts 2>/dev/null") or ""
    usb_roots = set()
    for raw_path in str(mount_output).splitlines():
        mount_path = (
            raw_path.strip()
            .replace("\\040", " ")
            .replace("\\011", "\t")
            .replace("\\134", "\\")
        )
        match = re.fullmatch(r"/media/usb(\d+)", mount_path)
        if match:
            usb_roots.add((int(match.group(1)), mount_path))

    sftp = connection.client.open_sftp()
    try:
        roots = [{"name": "SD Card", "path": DEFAULT_ROOT, "available": sftp_exists(sftp, DEFAULT_ROOT)}]
        for index, usb_root in sorted(usb_roots):
            if sftp_exists(sftp, usb_root):
                roots.append({
                    "name": f"USB Drive {index}",
                    "path": usb_root,
                    "available": True,
                })
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


def ensure_remote_dir(sftp, remote_dir, replace_files=False):
    remote_dir = normalize_remote_path(remote_dir)
    parts = [part for part in remote_dir.split("/") if part]
    current = ""
    for part in parts:
        current += "/" + part
        try:
            attr = sftp.stat(current)
            if not stat.S_ISDIR(attr.st_mode):
                if not replace_files:
                    raise NotADirectoryError(f"A file blocks the destination folder: {current}")
                delete_path_with_sftp(sftp, current)
                sftp.mkdir(current)
        except FileNotFoundError:
            sftp.mkdir(current)
        except OSError:
            # Paramiko servers do not all use FileNotFoundError consistently.
            try:
                attr = sftp.stat(current)
            except Exception:
                sftp.mkdir(current)
            else:
                if not stat.S_ISDIR(attr.st_mode):
                    if not replace_files:
                        raise NotADirectoryError(f"A file blocks the destination folder: {current}")
                    delete_path_with_sftp(sftp, current)
                    sftp.mkdir(current)


def ensure_target_available(sftp, target_path, overwrite=False):
    if not sftp_exists(sftp, target_path):
        return
    if not overwrite:
        raise FileExistsError(f"Target already exists: {target_path}")
    delete_path_with_sftp(sftp, target_path)


def unique_remote_target(sftp, target_path):
    directory = posixpath.dirname(target_path)
    name = posixpath.basename(target_path)
    stem, suffix = posixpath.splitext(name)
    if not stem:
        stem, suffix = name, ""
    for index in range(2, 10000):
        copy_name = f"{stem} copy" if index == 2 else f"{stem} copy {index - 1}"
        candidate = join_remote_path(directory, f"{copy_name}{suffix}")
        if not sftp_exists(sftp, candidate):
            return candidate
    return target_path


def upload_path(connection, local_path, remote_dir, progress_callback=None, message_callback=None, target_name=None, overwrite=False, skip_existing=False, merge_existing=False, conflict_callback=None):
    local_path = Path(local_path)
    remote_dir = clamp_to_root(remote_dir)
    sftp = connection.client.open_sftp()
    try:
        name = target_name or local_path.name
        target_path = join_remote_path(remote_dir, name)

        if local_path.is_dir():
            if sftp_exists(sftp, target_path):
                attr = sftp.stat(target_path)
                if skip_existing and not stat.S_ISDIR(attr.st_mode):
                    return target_path
                if not overwrite and not skip_existing and not (merge_existing and stat.S_ISDIR(attr.st_mode)):
                    raise FileExistsError(f"Target already exists: {target_path}")
                if overwrite and not stat.S_ISDIR(attr.st_mode):
                    delete_path_with_sftp(sftp, target_path)
            upload_folder(
                sftp,
                local_path,
                target_path,
                progress_callback,
                message_callback,
                merge_overwrite=overwrite,
                skip_existing=skip_existing,
                conflict_callback=conflict_callback,
            )
            return target_path

        if skip_existing and sftp_exists(sftp, target_path):
            return target_path
        ensure_target_available(sftp, target_path, overwrite=overwrite)
        if message_callback:
            message_callback(f"Uploading {local_path.name}...")
        sftp.put(str(local_path), target_path, callback=progress_callback)
        return target_path
    finally:
        sftp.close()


def upload_folder(sftp, local_folder, remote_folder, progress_callback=None, message_callback=None, merge_overwrite=False, skip_existing=False, conflict_callback=None):
    ensure_remote_dir(sftp, remote_folder, replace_files=merge_overwrite)
    for child in Path(local_folder).iterdir():
        remote_item = join_remote_path(remote_folder, child.name)
        exists = sftp_exists(sftp, remote_item)
        target_is_dir = False
        if exists:
            target_is_dir = stat.S_ISDIR(sftp.stat(remote_item).st_mode)
            if conflict_callback is not None:
                choice = conflict_callback(remote_item, bool(child.is_dir() and target_is_dir))
                if choice == "cancel":
                    raise InterruptedError("Transfer cancelled.")
                if choice == "keep_both":
                    remote_item = unique_remote_target(sftp, remote_item)
                    exists = False
                    target_is_dir = False
                elif choice == "skip":
                    if not (child.is_dir() and target_is_dir):
                        continue
                elif choice == "overwrite":
                    if child.is_dir() != target_is_dir:
                        delete_path_with_sftp(sftp, remote_item)
                        exists = False
                        target_is_dir = False
            elif skip_existing:
                if not (child.is_dir() and target_is_dir):
                    continue
            elif not merge_overwrite:
                raise FileExistsError(f"Target already exists: {remote_item}")
            elif child.is_dir() != target_is_dir:
                delete_path_with_sftp(sftp, remote_item)
                exists = False
                target_is_dir = False

        if child.is_dir():
            upload_folder(
                sftp,
                child,
                remote_item,
                progress_callback,
                message_callback,
                merge_overwrite=merge_overwrite,
                skip_existing=skip_existing,
                conflict_callback=conflict_callback,
            )
        else:
            if message_callback:
                message_callback(f"Uploading {child.name}...")
            sftp.put(str(child), remote_item, callback=progress_callback)

def download_path(connection, remote_path, local_dir, progress_callback=None, message_callback=None, target_name=None, overwrite=False, skip_existing=False):
    remote_path = clamp_to_root(remote_path)
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    sftp = connection.client.open_sftp()
    try:
        attr = sftp.stat(remote_path)
        source_is_dir = stat.S_ISDIR(attr.st_mode)
        name = target_name or posixpath.basename(remote_path.rstrip("/"))
        target = local_dir / name
        if target.exists():
            if skip_existing and not (source_is_dir and target.is_dir()):
                return str(target)
            if not overwrite and not skip_existing:
                raise FileExistsError(f"Target already exists: {target}")
            if overwrite and not (source_is_dir and target.is_dir()):
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()

        if source_is_dir:
            download_folder(
                sftp,
                remote_path,
                target,
                progress_callback,
                message_callback,
                merge_overwrite=overwrite,
                skip_existing=skip_existing,
            )
            return str(target)

        if message_callback:
            message_callback(f"Downloading {name}...")
        sftp.get(remote_path, str(target), callback=progress_callback)
        return str(target)
    finally:
        sftp.close()


def download_folder(sftp, remote_folder, local_folder, progress_callback=None, message_callback=None, merge_overwrite=False, skip_existing=False):
    local_folder = Path(local_folder)
    if local_folder.exists() and not local_folder.is_dir():
        if skip_existing:
            return
        if not merge_overwrite:
            raise FileExistsError(f"Target already exists: {local_folder}")
        local_folder.unlink()
    local_folder.mkdir(parents=True, exist_ok=True)
    for attr in sftp.listdir_attr(remote_folder):
        name = attr.filename
        if name in {".", ".."}:
            continue
        remote_item = join_remote_path(remote_folder, name)
        local_item = local_folder / name
        if stat.S_ISDIR(attr.st_mode):
            if local_item.exists() and not local_item.is_dir():
                if skip_existing:
                    continue
                if not merge_overwrite:
                    raise FileExistsError(f"Target already exists: {local_item}")
                local_item.unlink()
            download_folder(
                sftp,
                remote_item,
                local_item,
                progress_callback,
                message_callback,
                merge_overwrite=merge_overwrite,
                skip_existing=skip_existing,
            )
        else:
            if local_item.exists():
                if skip_existing:
                    continue
                if local_item.is_dir():
                    if not merge_overwrite:
                        raise FileExistsError(f"Target already exists: {local_item}")
                    shutil.rmtree(local_item)
                elif not merge_overwrite:
                    raise FileExistsError(f"Target already exists: {local_item}")
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


def rename_path(connection, old_path, new_path, overwrite=False):
    old_path = clamp_to_root(old_path)
    new_path = clamp_to_root(new_path)
    if root_for_path(old_path) != root_for_path(new_path):
        raise ValueError("Items cannot be moved outside the selected storage root.")
    sftp = connection.client.open_sftp()
    try:
        ensure_target_available(sftp, new_path, overwrite=overwrite)
        sftp.rename(old_path, new_path)
    finally:
        sftp.close()


def copy_path(connection, source_path, target_dir, target_name=None, overwrite=False, progress_callback=None, message_callback=None, skip_existing=False):
    source_path = clamp_to_root(source_path)
    target_dir = clamp_to_root(target_dir)
    source_root = root_for_path(source_path)
    target_root = root_for_path(target_dir)
    if not source_root or not target_root:
        raise ValueError("Source and destination must be inside MiSTer storage.")

    sftp = connection.client.open_sftp()
    try:
        attr = sftp.stat(source_path)
        source_is_dir = stat.S_ISDIR(attr.st_mode)
        name = target_name or posixpath.basename(source_path.rstrip("/"))
        target_path = join_remote_path(target_dir, name)
        if source_path == target_path:
            raise ValueError("Source and destination are the same.")
        if source_is_dir and (target_path == source_path or target_path.startswith(source_path.rstrip("/") + "/")):
            raise ValueError("A folder cannot be copied into itself.")

        if sftp_exists(sftp, target_path):
            target_attr = sftp.stat(target_path)
            target_is_dir = stat.S_ISDIR(target_attr.st_mode)
            if skip_existing and not (source_is_dir and target_is_dir):
                return target_path
            if not overwrite and not skip_existing:
                raise FileExistsError(f"Target already exists: {target_path}")
            if overwrite and not (source_is_dir and target_is_dir):
                delete_path_with_sftp(sftp, target_path)

        if source_is_dir:
            copy_folder_with_sftp(
                sftp,
                source_path,
                target_path,
                progress_callback,
                message_callback,
                merge_overwrite=overwrite,
                skip_existing=skip_existing,
            )
        else:
            copy_file_with_sftp(
                sftp,
                source_path,
                target_path,
                progress_callback,
                message_callback,
                overwrite=overwrite,
                skip_existing=skip_existing,
            )
        return target_path
    finally:
        sftp.close()


def _move_folder_with_sftp_skip_existing(sftp, source_folder, target_folder, progress_callback=None, message_callback=None):
    if sftp_exists(sftp, target_folder):
        target_attr = sftp.stat(target_folder)
        if not stat.S_ISDIR(target_attr.st_mode):
            return
    else:
        sftp.mkdir(target_folder)

    for attr in sftp.listdir_attr(source_folder):
        name = attr.filename
        if name in {".", ".."}:
            continue
        source_item = join_remote_path(source_folder, name)
        target_item = join_remote_path(target_folder, name)
        target_exists = sftp_exists(sftp, target_item)

        if stat.S_ISDIR(attr.st_mode):
            if target_exists and not stat.S_ISDIR(sftp.stat(target_item).st_mode):
                continue
            if not target_exists:
                try:
                    sftp.rename(source_item, target_item)
                    continue
                except Exception:
                    pass
            _move_folder_with_sftp_skip_existing(
                sftp,
                source_item,
                target_item,
                progress_callback,
                message_callback,
            )
            try:
                sftp.rmdir(source_item)
            except Exception:
                pass
        else:
            if target_exists:
                continue
            try:
                sftp.rename(source_item, target_item)
            except Exception:
                copy_file_with_sftp(
                    sftp,
                    source_item,
                    target_item,
                    progress_callback,
                    message_callback,
                    overwrite=False,
                )
                sftp.remove(source_item)

    try:
        sftp.rmdir(source_folder)
    except Exception:
        pass


def move_path(connection, source_path, target_dir, target_name=None, overwrite=False, progress_callback=None, message_callback=None, skip_existing=False):
    source_path = clamp_to_root(source_path)
    target_dir = clamp_to_root(target_dir)
    source_root = root_for_path(source_path)
    target_root = root_for_path(target_dir)
    if not source_root or not target_root:
        raise ValueError("Source and destination must be inside MiSTer storage.")
    if source_path == source_root:
        raise ValueError("The storage root cannot be moved.")

    sftp = connection.client.open_sftp()
    try:
        attr = sftp.stat(source_path)
        source_is_dir = stat.S_ISDIR(attr.st_mode)
        name = target_name or posixpath.basename(source_path.rstrip("/"))
        target_path = join_remote_path(target_dir, name)
        if source_path == target_path:
            raise ValueError("Source and destination are the same.")
        if source_is_dir and target_path.startswith(source_path.rstrip("/") + "/"):
            raise ValueError("A folder cannot be moved into itself.")

        target_exists = sftp_exists(sftp, target_path)
        target_is_dir = False
        if target_exists:
            target_is_dir = stat.S_ISDIR(sftp.stat(target_path).st_mode)
            if skip_existing:
                if source_is_dir and target_is_dir:
                    _move_folder_with_sftp_skip_existing(
                        sftp,
                        source_path,
                        target_path,
                        progress_callback,
                        message_callback,
                    )
                return target_path
            if not overwrite:
                raise FileExistsError(f"Target already exists: {target_path}")

        merge_folders = source_is_dir and target_exists and target_is_dir
        if target_exists and not merge_folders:
            delete_path_with_sftp(sftp, target_path)

        if not merge_folders:
            try:
                sftp.rename(source_path, target_path)
                return target_path
            except Exception:
                pass

        if source_is_dir:
            copy_folder_with_sftp(sftp, source_path, target_path, progress_callback, message_callback, merge_overwrite=overwrite)
        else:
            copy_file_with_sftp(sftp, source_path, target_path, progress_callback, message_callback, overwrite=overwrite)
        delete_path_with_sftp(sftp, source_path)
        return target_path
    finally:
        sftp.close()

def copy_file_with_sftp(sftp, source_path, target_path, progress_callback=None, message_callback=None, overwrite=True, skip_existing=False):
    if sftp_exists(sftp, target_path):
        if skip_existing:
            return
        attr = sftp.stat(target_path)
        if stat.S_ISDIR(attr.st_mode):
            if not overwrite:
                raise FileExistsError(f"Target already exists: {target_path}")
            delete_path_with_sftp(sftp, target_path)
        elif not overwrite:
            raise FileExistsError(f"Target already exists: {target_path}")
    if message_callback:
        message_callback(f"Copying {posixpath.basename(source_path)}...")
    attr = sftp.stat(source_path)
    total = int(attr.st_size or 0)
    transferred = 0
    with sftp.open(source_path, "rb") as source_file:
        with sftp.open(target_path, "wb") as target_file:
            while True:
                chunk = source_file.read(1024 * 1024)
                if not chunk:
                    break
                target_file.write(chunk)
                transferred += len(chunk)
                if progress_callback:
                    progress_callback(transferred, total)


def copy_folder_with_sftp(sftp, source_folder, target_folder, progress_callback=None, message_callback=None, merge_overwrite=True, skip_existing=False):
    if sftp_exists(sftp, target_folder):
        attr = sftp.stat(target_folder)
        if not stat.S_ISDIR(attr.st_mode):
            if skip_existing:
                return
            if not merge_overwrite:
                raise FileExistsError(f"Target already exists: {target_folder}")
            delete_path_with_sftp(sftp, target_folder)
    ensure_remote_dir(sftp, target_folder, replace_files=merge_overwrite)

    for attr in sftp.listdir_attr(source_folder):
        name = attr.filename
        if name in {".", ".."}:
            continue
        source_item = join_remote_path(source_folder, name)
        target_item = join_remote_path(target_folder, name)
        if stat.S_ISDIR(attr.st_mode):
            copy_folder_with_sftp(
                sftp,
                source_item,
                target_item,
                progress_callback,
                message_callback,
                merge_overwrite=merge_overwrite,
                skip_existing=skip_existing,
            )
        else:
            copy_file_with_sftp(
                sftp,
                source_item,
                target_item,
                progress_callback,
                message_callback,
                overwrite=merge_overwrite,
                skip_existing=skip_existing,
            )

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

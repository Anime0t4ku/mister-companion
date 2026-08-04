import io
import json
import os
import posixpath
import re
import zipfile
from datetime import datetime, timezone

import requests

from core.extras_common import (
    _ensure_local_dir,
    _ensure_remote_dir,
    _copy_local_file_to_sd,
    _local_path,
    _path_exists,
    _path_exists_local,
    _quote,
    _read_local_text,
    _read_remote_text,
    _remove_local_path,
    _write_local_bytes,
    _write_local_text,
    _write_remote_text,
)

DREAMSTER_REPO = "skmp/DreamSTer"
DREAMSTER_RELEASES_URL = f"https://api.github.com/repos/{DREAMSTER_REPO}/releases"
DREAMSTER_TITLE = "DreamSTer"
DREAMSTER_ASSET_PATTERN = re.compile(r"^DreamSTer-.*\.zip$", re.IGNORECASE)

REMOTE_SCRIPT = "/media/fat/Scripts/DreamSTer.sh"
REMOTE_RUNTIME_DIR = "/media/fat/minicast"
REMOTE_RUNTIME_BINARY = "/media/fat/minicast/minicast.elf"
REMOTE_MANIFEST = "/media/fat/minicast/.mister_companion_manifest.json"
REMOTE_GAME_DIR = "/media/fat/games/Dreamcast"
REMOTE_DC_BOOT = f"{REMOTE_GAME_DIR}/dc_boot.bin"
REMOTE_DC_FLASH = f"{REMOTE_GAME_DIR}/dc_flash.bin"


def _fetch_latest_dreamster_release() -> dict:
    response = requests.get(
        DREAMSTER_RELEASES_URL,
        headers={
            "User-Agent": "MiSTer-Companion",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    )
    response.raise_for_status()

    releases = response.json()
    if not isinstance(releases, list):
        raise RuntimeError("Unexpected response while checking DreamSTer releases.")

    for release in releases:
        if release.get("draft"):
            continue

        assets = release.get("assets") or []
        preferred = []
        fallback = []
        for asset in assets:
            name = str(asset.get("name") or "")
            url = str(asset.get("browser_download_url") or "")
            if not url.lower().startswith("https://") or not name.lower().endswith(".zip"):
                continue
            if DREAMSTER_ASSET_PATTERN.match(name):
                preferred.append((name, url))
            elif "dreamster" in name.lower():
                fallback.append((name, url))

        candidates = preferred or fallback
        if not candidates:
            continue

        candidates.sort(key=lambda item: item[0].lower())
        asset_name, zip_url = candidates[0]
        version = str(release.get("tag_name") or release.get("name") or "").strip()
        if not version:
            continue

        return {
            "version": version,
            "release_name": str(release.get("name") or version),
            "zip_url": zip_url,
            "asset_name": asset_name,
            "prerelease": bool(release.get("prerelease")),
            "published_at": str(release.get("published_at") or ""),
        }

    raise RuntimeError("Unable to find a DreamSTer ZIP asset in any published GitHub release.")


def _read_manifest_text(text: str) -> dict:
    try:
        value = json.loads(text or "")
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _read_manifest(connection) -> dict:
    return _read_manifest_text(_read_remote_text(connection, REMOTE_MANIFEST))


def _read_manifest_local(sd_root: str) -> dict:
    return _read_manifest_text(_read_local_text(sd_root, REMOTE_MANIFEST))


def _manifest_for_release(release: dict) -> dict:
    return {
        "schema_version": 1,
        "id": "dreamster",
        "name": DREAMSTER_TITLE,
        "repository": DREAMSTER_REPO,
        "installed_version": release["version"],
        "release_tag": release["version"],
        "release_name": release.get("release_name", release["version"]),
        "asset_name": release.get("asset_name", ""),
        "prerelease": bool(release.get("prerelease")),
        "published_at": release.get("published_at", ""),
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "managed_paths": ["Scripts/DreamSTer.sh", "minicast"],
    }


def _write_manifest(connection, release: dict):
    _ensure_remote_dir(connection, REMOTE_RUNTIME_DIR)
    _write_remote_text(connection, REMOTE_MANIFEST, json.dumps(_manifest_for_release(release), indent=2) + "\n")


def _write_manifest_local(sd_root: str, release: dict):
    _ensure_local_dir(sd_root, REMOTE_RUNTIME_DIR)
    _write_local_text(sd_root, REMOTE_MANIFEST, json.dumps(_manifest_for_release(release), indent=2) + "\n")


def _is_installed(connection) -> bool:
    return _path_exists(connection, REMOTE_SCRIPT) and _path_exists(connection, REMOTE_RUNTIME_BINARY)


def _is_installed_local(sd_root: str) -> bool:
    return _path_exists_local(sd_root, REMOTE_SCRIPT) and _path_exists_local(sd_root, REMOTE_RUNTIME_BINARY)


def _build_status(installed: bool, installed_version: str, latest_version: str, latest_error: str,
                  manifest_present: bool = False, bios_present: bool = False) -> dict:
    update_available = bool(
        installed
        and (
            not manifest_present
            or (latest_version and (not installed_version or installed_version != latest_version))
        )
    )
    if not installed:
        status_text, label, enabled = "✗ Not installed", "Install", True
    elif update_available:
        if not manifest_present:
            status_text = "▲ Update available (install manifest missing)"
        else:
            status_text = f"▲ Update available ({installed_version or 'unknown'} → {latest_version})"
        label, enabled = "Update", True
    else:
        status_text, label, enabled = f"✓ Installed ({installed_version or 'unknown'})", "Installed", False

    if latest_error:
        status_text += f" (update check failed: {latest_error})"

    return {
        "installed": installed,
        "installed_version": installed_version,
        "latest_version": latest_version,
        "latest_error": latest_error,
        "update_available": update_available,
        "status_text": status_text,
        "install_label": label,
        "install_enabled": enabled,
        "bios_present": bios_present,
        "upload_enabled": installed and not bios_present,
        "uninstall_enabled": installed,
    }


def get_dreamster_status(connection, check_latest: bool = False):
    if not connection.is_connected():
        status = _build_status(False, "", "", "")
        status["install_enabled"] = False
        return status

    latest_version = ""
    latest_error = ""
    if check_latest:
        try:
            latest_version = _fetch_latest_dreamster_release()["version"]
        except Exception as exc:
            latest_error = str(exc)

    installed = _is_installed(connection)
    manifest_present = installed and _path_exists(connection, REMOTE_MANIFEST)
    installed_version = str(_read_manifest(connection).get("installed_version") or "") if manifest_present else ""
    bios_present = (
        _path_exists(connection, REMOTE_DC_BOOT)
        and _path_exists(connection, REMOTE_DC_FLASH)
    ) if installed else False
    return _build_status(installed, installed_version, latest_version, latest_error, manifest_present, bios_present)


def get_dreamster_status_local(sd_root: str, check_latest: bool = False):
    latest_version = ""
    latest_error = ""
    if check_latest:
        try:
            latest_version = _fetch_latest_dreamster_release()["version"]
        except Exception as exc:
            latest_error = str(exc)

    installed = _is_installed_local(sd_root)
    manifest_present = installed and _path_exists_local(sd_root, REMOTE_MANIFEST)
    installed_version = str(_read_manifest_local(sd_root).get("installed_version") or "") if manifest_present else ""
    bios_present = (
        _path_exists_local(sd_root, REMOTE_DC_BOOT)
        and _path_exists_local(sd_root, REMOTE_DC_FLASH)
    ) if installed else False
    return _build_status(installed, installed_version, latest_version, latest_error, manifest_present, bios_present)


def _validate_bios_paths(local_paths):
    selected = {}
    for local_path in local_paths:
        if not os.path.isfile(local_path):
            raise RuntimeError(f"Selected BIOS file does not exist: {local_path}")
        name = os.path.basename(local_path).lower()
        if name not in {"dc_boot.bin", "dc_flash.bin"}:
            raise RuntimeError("Select only dc_boot.bin and dc_flash.bin.")
        selected[name] = local_path
    if not selected:
        raise RuntimeError("No Dreamcast BIOS files were selected.")
    return selected


def upload_dreamster_bios(connection, local_paths, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    if not _is_installed(connection):
        raise RuntimeError("DreamSTer is not installed.")

    selected = _validate_bios_paths(local_paths)
    _ensure_remote_dir(connection, REMOTE_GAME_DIR)
    sftp = connection.client.open_sftp()
    try:
        for name, local_path in selected.items():
            target = posixpath.join(REMOTE_GAME_DIR, name)
            log(f"Uploading {name} to {target}\n")
            sftp.put(local_path, target)
    finally:
        sftp.close()
    log("Dreamcast BIOS upload completed.\n")
    return {"bios_present": _path_exists(connection, REMOTE_DC_BOOT) and _path_exists(connection, REMOTE_DC_FLASH)}


def upload_dreamster_bios_local(sd_root: str, local_paths, log):
    if not _is_installed_local(sd_root):
        raise RuntimeError("DreamSTer is not installed.")

    selected = _validate_bios_paths(local_paths)
    _ensure_local_dir(sd_root, REMOTE_GAME_DIR)
    for name, local_path in selected.items():
        target = posixpath.join(REMOTE_GAME_DIR, name)
        log(f"Copying {name} to {target}\n")
        _copy_local_file_to_sd(sd_root, local_path, target)
    log("Dreamcast BIOS copy completed.\n")
    return {
        "bios_present": _path_exists_local(sd_root, REMOTE_DC_BOOT)
        and _path_exists_local(sd_root, REMOTE_DC_FLASH)
    }


def _archive_members(zf: zipfile.ZipFile):
    members = []
    for member in zf.infolist():
        if member.is_dir():
            continue
        name = member.filename.replace("\\", "/").lstrip("/")
        normalized = posixpath.normpath(name)
        if normalized in {"", "."} or normalized == ".." or normalized.startswith("../"):
            raise RuntimeError(f"Unsafe path in DreamSTer archive: {member.filename}")
        if normalized.startswith("__MACOSX/") or posixpath.basename(normalized).startswith("._"):
            continue
        members.append((member, normalized))

    names = {name.lower() for _, name in members}
    if "scripts/dreamster.sh" not in names or "minicast/minicast.elf" not in names:
        raise RuntimeError("The DreamSTer archive does not contain the expected Scripts and minicast files.")
    return members


def install_or_update_dreamster(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    release = _fetch_latest_dreamster_release()
    log(f"Latest version on GitHub: {release['version']}\n")
    if release.get("prerelease"):
        log("This DreamSTer release is marked as a pre-release.\n")
    log(f"Downloading: {release['zip_url']}\n")

    response = requests.get(release["zip_url"], headers={"User-Agent": "MiSTer-Companion"}, timeout=120)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        members = _archive_members(zf)
        sftp = connection.client.open_sftp()
        try:
            for member, name in members:
                remote_path = "/media/fat/" + name
                _ensure_remote_dir(connection, posixpath.dirname(remote_path))
                log(f"Installing {remote_path}\n")
                with sftp.open(remote_path, "wb") as remote_file:
                    remote_file.write(zf.read(member))
        finally:
            sftp.close()

    _ensure_remote_dir(connection, REMOTE_GAME_DIR)
    log(f"Ensured Dreamcast game folder exists: {REMOTE_GAME_DIR}\n")

    connection.run_command(
        f"chmod +x {_quote(REMOTE_SCRIPT)} "
        f"{_quote('/media/fat/minicast/load_fpga_bitstream')} "
        f"{_quote(REMOTE_RUNTIME_BINARY)} "
        f"{_quote('/media/fat/minicast/setup_hdmi')}"
    )
    _write_manifest(connection, release)
    log(f"Installed DreamSTer {release['version']}.\n")
    return {"installed_version": release["version"]}


def install_or_update_dreamster_local(sd_root: str, log):
    release = _fetch_latest_dreamster_release()
    log(f"Latest version on GitHub: {release['version']}\n")
    if release.get("prerelease"):
        log("This DreamSTer release is marked as a pre-release.\n")
    log(f"Downloading: {release['zip_url']}\n")

    response = requests.get(release["zip_url"], headers={"User-Agent": "MiSTer-Companion"}, timeout=120)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        for member, name in _archive_members(zf):
            remote_path = "/media/fat/" + name
            log(f"Installing {remote_path}\n")
            _write_local_bytes(sd_root, remote_path, zf.read(member))
            mode = (member.external_attr >> 16) & 0o777
            if mode:
                try:
                    _local_path(sd_root, remote_path).chmod(mode)
                except OSError:
                    pass

    _ensure_local_dir(sd_root, REMOTE_GAME_DIR)
    log(f"Ensured Dreamcast game folder exists: {REMOTE_GAME_DIR}\n")

    for remote_path in (
        REMOTE_SCRIPT,
        "/media/fat/minicast/load_fpga_bitstream",
        REMOTE_RUNTIME_BINARY,
        "/media/fat/minicast/setup_hdmi",
    ):
        try:
            path = _local_path(sd_root, remote_path)
            path.chmod(path.stat().st_mode | 0o111)
        except OSError:
            pass

    _write_manifest_local(sd_root, release)
    log(f"Installed DreamSTer {release['version']}.\n")
    return {"installed_version": release["version"]}


def uninstall_dreamster(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    log(f"Removing {REMOTE_SCRIPT}\n")
    connection.run_command(f"rm -f {_quote(REMOTE_SCRIPT)}")
    log(f"Removing {REMOTE_RUNTIME_DIR}\n")
    connection.run_command(f"rm -rf {_quote(REMOTE_RUNTIME_DIR)}")
    return {"uninstalled": True}


def uninstall_dreamster_local(sd_root: str, log):
    for path in (REMOTE_SCRIPT, REMOTE_RUNTIME_DIR):
        log(f"Removing {path}\n")
        _remove_local_path(sd_root, path)
    return {"uninstalled": True}


# Downloader-backed Install Center implementation.
from core.downloader_backend import (
    database_registered_local,
    database_registered_online,
    ensure_database_source_local,
    ensure_database_source_online,
    remove_database_source_local,
    remove_database_source_online,
    restore_local,
    restore_online,
    run_named_database_local,
    run_named_database_online,
    check_named_database_local,
    check_named_database_online,
    uninstall_named_database_local,
    uninstall_named_database_online,
)

DREAMSTER_DB_ID = "MultiDatabases/dreamster"
DREAMSTER_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/dreamster/db.json"
DREAMSTER_DB_FILES = (
    "/media/fat/Scripts/DreamSTer.sh",
    "/media/fat/minicast/load_fpga_bitstream",
    "/media/fat/minicast/mem_wc.ko",
    "/media/fat/minicast/minicast.elf",
    "/media/fat/minicast/polly2-rtl.rbf",
    "/media/fat/minicast/setup_hdmi",
)


def _manual_dreamster_install(connection) -> bool:
    return False

def _manual_dreamster_install_local(sd_root: str) -> bool:
    return False

def _prepare_manual_dreamster_for_downloader(connection, log, manual=None):
    if manual is None:
        manual = _manual_dreamster_install(connection)
    if not manual:
        return False
    log("Detected a manual Companion installation; preparing it for Downloader...\n")
    for path in DREAMSTER_DB_FILES:
        connection.run_command(f"rm -f {_quote(path)}")
        log(f"Removed legacy managed file: {path}\n")
    connection.run_command(f"rm -f {_quote(REMOTE_MANIFEST)}")
    log(f"Preserved Dreamcast game folder and BIOS files: {REMOTE_GAME_DIR}\n")
    return True


def _prepare_manual_dreamster_for_downloader_local(sd_root: str, log, manual=None):
    if manual is None:
        manual = _manual_dreamster_install_local(sd_root)
    if not manual:
        return False
    log("Detected a manual Companion installation; preparing it for Downloader...\n")
    for path in DREAMSTER_DB_FILES:
        _remove_local_path(sd_root, path)
        log(f"Removed legacy managed file: {path}\n")
    _remove_local_path(sd_root, REMOTE_MANIFEST)
    log(f"Preserved Dreamcast game folder and BIOS files: {REMOTE_GAME_DIR}\n")
    return True


_manual_get_dreamster_status = get_dreamster_status
_manual_get_dreamster_status_local = get_dreamster_status_local


def _apply_dreamster_downloader_status(status: dict, manual: bool, update_available: bool = False) -> dict:
    status = dict(status)
    if manual:
        status.update({
            "update_available": True,
            "status_text": "▲ Manual install found",
            "install_label": "Migrate / Update",
            "install_enabled": True,
        })
    elif status.get("installed"):
        status.update({
            "installed_version": "",
            "latest_version": "",
            "update_available": bool(update_available),
            "status_text": "▲ Update available" if update_available else "✓ Installed",
            "install_label": "Update" if update_available else "Installed",
            "install_enabled": bool(update_available),
        })
    return status


def get_dreamster_status(connection, check_latest: bool = False):
    status = _manual_get_dreamster_status(connection, check_latest=False)
    manual = _manual_dreamster_install(connection) if status.get("installed") else False
    update = False
    if check_latest and status.get("installed") and not manual:
        update = check_named_database_online(connection, DREAMSTER_DB_ID)
    return _apply_dreamster_downloader_status(status, manual, update)


def get_dreamster_status_local(sd_root: str, check_latest: bool = False):
    status = _manual_get_dreamster_status_local(sd_root, check_latest=False)
    manual = _manual_dreamster_install_local(sd_root) if status.get("installed") else False
    update = False
    if check_latest and status.get("installed") and not manual:
        update = check_named_database_local(sd_root, DREAMSTER_DB_ID)
    return _apply_dreamster_downloader_status(status, manual, update)


def _finish_dreamster_install_online(connection, log):
    _ensure_remote_dir(connection, REMOTE_GAME_DIR)
    connection.run_command(
        f"chmod +x {_quote(REMOTE_SCRIPT)} "
        f"{_quote('/media/fat/minicast/load_fpga_bitstream')} "
        f"{_quote(REMOTE_RUNTIME_BINARY)} "
        f"{_quote('/media/fat/minicast/setup_hdmi')}"
    )
    connection.run_command(f"rm -f {_quote(REMOTE_MANIFEST)}")
    log(f"Preserved Dreamcast game folder and BIOS files: {REMOTE_GAME_DIR}\n")


def _finish_dreamster_install_local(sd_root: str, log):
    _ensure_local_dir(sd_root, REMOTE_GAME_DIR)
    for remote_path in (
        REMOTE_SCRIPT,
        "/media/fat/minicast/load_fpga_bitstream",
        REMOTE_RUNTIME_BINARY,
        "/media/fat/minicast/setup_hdmi",
    ):
        try:
            path = _local_path(sd_root, remote_path)
            path.chmod(path.stat().st_mode | 0o111)
        except OSError:
            pass
    _remove_local_path(sd_root, REMOTE_MANIFEST)
    log(f"Preserved Dreamcast game folder and BIOS files: {REMOTE_GAME_DIR}\n")


def install_or_update_dreamster(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    manual = _manual_dreamster_install(connection)
    original = ensure_database_source_online(connection, DREAMSTER_DB_ID, DREAMSTER_DB_URL)
    try:
        _prepare_manual_dreamster_for_downloader(connection, log, manual=manual)
        run_named_database_online(connection, DREAMSTER_DB_ID, log=log)
        _finish_dreamster_install_online(connection, log)
    except Exception:
        restore_online(connection, original)
        raise


def install_or_update_dreamster_local(sd_root: str, log):
    manual = _manual_dreamster_install_local(sd_root)
    original = ensure_database_source_local(sd_root, DREAMSTER_DB_ID, DREAMSTER_DB_URL)
    try:
        _prepare_manual_dreamster_for_downloader_local(sd_root, log, manual=manual)
        run_named_database_local(sd_root, DREAMSTER_DB_ID, log=log)
        _finish_dreamster_install_local(sd_root, log)
    except Exception:
        restore_local(sd_root, original)
        raise


def uninstall_dreamster(connection, log, force=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    if _manual_dreamster_install(connection):
        _prepare_manual_dreamster_for_downloader(connection, log, manual=True)
        remove_database_source_online(connection, DREAMSTER_DB_ID)
        return {"uninstalled": True}
    original = ensure_database_source_online(connection, DREAMSTER_DB_ID, DREAMSTER_DB_URL)
    try:
        native = uninstall_named_database_online(connection, DREAMSTER_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(connection, DREAMSTER_DB_ID, DREAMSTER_DB_URL, filter_value="!all")
            run_named_database_online(connection, DREAMSTER_DB_ID, log=log)
            remove_database_source_online(connection, DREAMSTER_DB_ID)
        connection.run_command(f"rm -f {_quote(REMOTE_MANIFEST)}")
    except Exception:
        restore_online(connection, original)
        raise
    return {"uninstalled": True}


def uninstall_dreamster_local(sd_root: str, log, force=False):
    if _manual_dreamster_install_local(sd_root):
        _prepare_manual_dreamster_for_downloader_local(sd_root, log, manual=True)
        remove_database_source_local(sd_root, DREAMSTER_DB_ID)
        return {"uninstalled": True}
    original = ensure_database_source_local(sd_root, DREAMSTER_DB_ID, DREAMSTER_DB_URL)
    try:
        native = uninstall_named_database_local(sd_root, DREAMSTER_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(sd_root, DREAMSTER_DB_ID, DREAMSTER_DB_URL, filter_value="!all")
            run_named_database_local(sd_root, DREAMSTER_DB_ID, log=log)
            remove_database_source_local(sd_root, DREAMSTER_DB_ID)
        _remove_local_path(sd_root, REMOTE_MANIFEST)
    except Exception:
        restore_local(sd_root, original)
        raise
    return {"uninstalled": True}

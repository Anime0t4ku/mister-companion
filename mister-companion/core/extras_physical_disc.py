import re

from core.extras_common import (
    _path_exists, _path_exists_local, _quote, _read_local_text, _read_remote_text,
    _remove_local_path, _write_local_text, _write_remote_text,
)
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

PHYSICAL_DISC_DB_ID = "MultiDatabases/physical-disc"
PHYSICAL_DISC_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/physical-disc/db.json"
PHYSICAL_DISC_BINARY = "/media/fat/MiSTer_Physical-CD"
MISTER_INI_PATH = "/media/fat/MiSTer.ini"
PHYSICAL_DISC_FILES = (
    PHYSICAL_DISC_BINARY,
    "/media/fat/_Physical Disc Cores/3DO.mgl",
    "/media/fat/_Physical Disc Cores/CDi.mgl",
    "/media/fat/_Physical Disc Cores/Cores/3DO.rbf",
    "/media/fat/_Physical Disc Cores/MegaCD.mgl",
    "/media/fat/_Physical Disc Cores/NeoGeoCD.mgl",
    "/media/fat/_Physical Disc Cores/PSX.mgl",
    "/media/fat/_Physical Disc Cores/Saturn.mgl",
    "/media/fat/_Physical Disc Cores/SNES-MSU1.mgl",
    "/media/fat/_Physical Disc Cores/TurboGrafx16-CD.mgl",
)



def _normalize_ini_text(text):
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n")


def _menu_sections(text):
    normalized = _normalize_ini_text(text)
    return list(re.finditer(
        r"(?ims)^[ \t]*\[menu\][^\n]*(?:\n|$)(?P<body>.*?)(?=^[ \t]*\[|\Z)",
        normalized,
    ))


def _menu_section(text):
    sections = _menu_sections(text)
    return sections[0] if sections else None


def _main_setting(body):
    return re.search(r"(?mi)^[ \t]*main[ \t]*=[ \t]*(?P<value>[^\n;#]*?)[ \t]*(?:[;#].*)?$", body)


def _is_auto_disc_main(value):
    return str(value or "").strip().lower() == "mister_physical-cd"


def _auto_disc_detection_state_from_text(current):
    current_main = ""
    for section in _menu_sections(current):
        main_match = _main_setting(section.group("body"))
        if not main_match:
            continue
        line = main_match.group(0).strip()
        if not current_main:
            current_main = line
        if _is_auto_disc_main(main_match.group("value")):
            return {"enabled": True, "current_main": line}
    return {"enabled": False, "current_main": current_main}


def get_auto_disc_detection_state(connection):
    return _auto_disc_detection_state_from_text(_read_remote_text(connection, MISTER_INI_PATH))


def get_auto_disc_detection_state_local(sd_root):
    return _auto_disc_detection_state_from_text(_read_local_text(sd_root, MISTER_INI_PATH))


def _enable_auto_disc_detection_text(text, replace_existing=False):
    normalized = _normalize_ini_text(text)
    sections = _menu_sections(normalized)

    for section in sections:
        main_match = _main_setting(section.group("body"))
        if main_match and _is_auto_disc_main(main_match.group("value")):
            return normalized, ""

    if sections:
        section = sections[0]
        body = section.group("body")
        main_match = _main_setting(body)
        if main_match:
            if not replace_existing:
                return normalized, main_match.group(0).strip()
            new_body = body[:main_match.start()] + "main=MiSTer_Physical-CD" + body[main_match.end():]
        else:
            new_body = "main=MiSTer_Physical-CD\n" + body
        updated = normalized[:section.start("body")] + new_body + normalized[section.end("body"):]
    else:
        updated = normalized.rstrip()
        updated = (updated + "\n\n" if updated else "") + "[menu]\nmain=MiSTer_Physical-CD\n"
    return re.sub(r"\n{3,}", "\n\n", updated).rstrip("\n") + "\n", ""


def _disable_auto_disc_detection_text(text):
    normalized = _normalize_ini_text(text)
    sections = _menu_sections(normalized)
    if not sections:
        return normalized

    updated = normalized
    changed = False
    for section in reversed(sections):
        body = section.group("body")
        matches = list(re.finditer(
            r"(?mi)^[ \t]*main[ \t]*=[ \t]*MiSTer_Physical-CD[ \t]*(?:[;#].*)?(?:\n|$)",
            body,
        ))
        if not matches:
            continue
        new_body = body
        for match in reversed(matches):
            new_body = new_body[:match.start()] + new_body[match.end():]
        updated = updated[:section.start("body")] + new_body + updated[section.end("body"):]
        changed = True

    if not changed:
        return normalized
    return re.sub(r"\n{3,}", "\n\n", updated).rstrip("\n") + "\n"


def enable_auto_disc_detection(connection, replace_existing=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    current = _read_remote_text(connection, MISTER_INI_PATH)
    updated, conflict = _enable_auto_disc_detection_text(current, replace_existing=replace_existing)
    if conflict:
        return {"changed": False, "conflict": conflict}
    changed = updated != _normalize_ini_text(current)
    if changed:
        _write_remote_text(connection, MISTER_INI_PATH, updated)
    return {"changed": changed, "conflict": ""}


def enable_auto_disc_detection_local(sd_root, replace_existing=False):
    current = _read_local_text(sd_root, MISTER_INI_PATH)
    updated, conflict = _enable_auto_disc_detection_text(current, replace_existing=replace_existing)
    if conflict:
        return {"changed": False, "conflict": conflict}
    changed = updated != _normalize_ini_text(current)
    if changed:
        _write_local_text(sd_root, MISTER_INI_PATH, updated)
    return {"changed": changed, "conflict": ""}


def disable_auto_disc_detection_local(sd_root):
    current = _read_local_text(sd_root, MISTER_INI_PATH)
    updated = _disable_auto_disc_detection_text(current)
    changed = updated != _normalize_ini_text(current)
    if changed:
        _write_local_text(sd_root, MISTER_INI_PATH, updated)
    return {"changed": changed}


def disable_auto_disc_detection(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    current = _read_remote_text(connection, MISTER_INI_PATH)
    updated = _disable_auto_disc_detection_text(current)
    changed = updated != _normalize_ini_text(current)
    if changed:
        _write_remote_text(connection, MISTER_INI_PATH, updated)
    return {"changed": changed}


def _upsert_cd_ini_block(text):
    normalized = str(text or "").replace("\r\n", "\n")
    pattern = re.compile(r"(?ms)^(?P<header>[ \t]*\[CD-\*\][^\n]*\n)(?P<body>.*?)(?=^[ \t]*\[|\Z)")
    match = pattern.search(normalized)
    if match:
        lines = match.group("body").rstrip("\n").split("\n") if match.group("body") else []
        for index, line in enumerate(lines):
            if re.match(r"^\s*main\s*=", line, flags=re.IGNORECASE):
                lines[index] = "main=MiSTer_Physical-CD"
                break
        else:
            lines.append("main=MiSTer_Physical-CD")
        block = "[CD-*]\n" + "\n".join(lines).rstrip("\n") + "\n\n"
        normalized = normalized[:match.start()] + block + normalized[match.end():]
    else:
        normalized = normalized.rstrip()
        normalized = (normalized + "\n\n" if normalized else "") + "[CD-*]\nmain=MiSTer_Physical-CD\n"
    return re.sub(r"\n{3,}", "\n\n", normalized).rstrip("\n") + "\n"


def _remove_cd_ini_block_text(text):
    normalized = str(text or "").replace("\r\n", "\n")
    pattern = re.compile(r"(?ms)(?:^|\n)[ \t]*\[CD-\*\][^\n]*(?:\n|\Z).*?(?=\n[ \t]*\[|\Z)")
    normalized = pattern.sub("\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip("\n")
    return normalized + ("\n" if normalized else "")


def _has_cd_ini_entry(text):
    normalized = str(text or "").replace("\r\n", "\n")
    section = re.search(r"(?ms)^[ \t]*\[CD-\*\][^\n]*\n(?P<body>.*?)(?=^[ \t]*\[|\Z)", normalized)
    return bool(section and re.search(r"(?mi)^\s*main\s*=\s*MiSTer_Physical-CD\s*$", section.group("body")))


def _ensure_cd_ini_block(connection, log):
    current = _read_remote_text(connection, MISTER_INI_PATH)
    updated = _upsert_cd_ini_block(current)
    if updated != current.replace("\r\n", "\n"):
        _write_remote_text(connection, MISTER_INI_PATH, updated)
        log("Added/updated [CD-*] in MiSTer.ini.\n")


def _ensure_cd_ini_block_local(sd_root, log):
    current = _read_local_text(sd_root, MISTER_INI_PATH)
    updated = _upsert_cd_ini_block(current)
    if updated != current.replace("\r\n", "\n"):
        _write_local_text(sd_root, MISTER_INI_PATH, updated)
        log("Added/updated [CD-*] in MiSTer.ini.\n")


def _remove_cd_ini_block(connection, log):
    current = _read_remote_text(connection, MISTER_INI_PATH)
    updated = _remove_cd_ini_block_text(current)
    if updated != current.replace("\r\n", "\n"):
        _write_remote_text(connection, MISTER_INI_PATH, updated)
        log("Removed [CD-*] from MiSTer.ini.\n")


def _remove_cd_ini_block_local(sd_root, log):
    current = _read_local_text(sd_root, MISTER_INI_PATH)
    updated = _remove_cd_ini_block_text(current)
    if updated != current.replace("\r\n", "\n"):
        _write_local_text(sd_root, MISTER_INI_PATH, updated)
        log("Removed [CD-*] from MiSTer.ini.\n")


def _presence(exists):
    found = [path for path in PHYSICAL_DISC_FILES if exists(path)]
    return found, len(found) == len(PHYSICAL_DISC_FILES)


def _manual_physical_disc_install(connection):
    found, _complete = _presence(lambda path: _path_exists(connection, path))
    return bool(found and not database_registered_online(connection, PHYSICAL_DISC_DB_ID))


def _manual_physical_disc_install_local(sd_root):
    found, _complete = _presence(lambda path: _path_exists_local(sd_root, path))
    return bool(found and not database_registered_local(sd_root, PHYSICAL_DISC_DB_ID))


def _prepare_manual_physical_disc_for_downloader(connection, log, manual=None):
    if manual is None:
        manual = _manual_physical_disc_install(connection)
    if not manual:
        return False
    log("Detected a manual Physical Disc Cores installation; preparing it for Downloader...\n")
    for path in PHYSICAL_DISC_FILES:
        connection.run_command(f"rm -f {_quote(path)}")
        log(f"Removed legacy managed file: {path}\n")
    log("Preserved unknown files inside /media/fat/_Physical Disc Cores.\n")
    return True


def _prepare_manual_physical_disc_for_downloader_local(sd_root, log, manual=None):
    if manual is None:
        manual = _manual_physical_disc_install_local(sd_root)
    if not manual:
        return False
    log("Detected a manual Physical Disc Cores installation; preparing it for Downloader...\n")
    for path in PHYSICAL_DISC_FILES:
        _remove_local_path(sd_root, path)
        log(f"Removed legacy managed file: {path}\n")
    log("Preserved unknown files inside /media/fat/_Physical Disc Cores.\n")
    return True


def _status(found, complete, manual, update_available=False, connected=True, ini_entry_present=True):
    installed = bool(found)
    partial = bool(found and not complete)
    if not connected:
        return {"installed": False, "partial": False, "update_available": False, "status_text": "Unknown", "install_label": "Install", "install_enabled": False, "uninstall_enabled": False, "auto_disc_detection_enabled": False, "auto_disc_detection_current_main": ""}
    if manual:
        text, label, enabled, update = "▲ Manual install found", "Migrate / Update", True, True
    elif not installed:
        text, label, enabled, update = "✗ Not installed", "Install", True, False
    elif partial:
        text, label, enabled, update = "⚠ Missing files", "Install", True, False
    elif complete and not ini_entry_present:
        text, label, enabled, update = "⚠ MiSTer.ini entry missing", "Add INI Entry", True, False
    elif update_available:
        text, label, enabled, update = "▲ Update available", "Update", True, True
    else:
        text, label, enabled, update = "✓ Installed", "Installed", False, False
    return {"installed": installed, "partial": partial, "installed_version": "", "latest_version": "", "latest_error": "", "update_available": update, "status_text": text, "install_label": label, "install_enabled": enabled, "uninstall_enabled": installed, "repair_action": bool(installed and complete and not manual and not ini_entry_present)}


def get_physical_disc_status(connection, check_latest=False):
    if not connection.is_connected():
        return _status([], False, False, connected=False)
    found, complete = _presence(lambda path: _path_exists(connection, path))
    manual = bool(found and not database_registered_online(connection, PHYSICAL_DISC_DB_ID))
    ini_entry_present = _has_cd_ini_entry(_read_remote_text(connection, MISTER_INI_PATH))
    update = bool(check_latest and found and complete and not manual and check_named_database_online(connection, PHYSICAL_DISC_DB_ID))
    status = _status(found, complete, manual, update, ini_entry_present=ini_entry_present)
    auto_state = get_auto_disc_detection_state(connection)
    status["auto_disc_detection_enabled"] = auto_state["enabled"]
    status["auto_disc_detection_current_main"] = auto_state["current_main"]
    return status


def get_physical_disc_status_local(sd_root, check_latest=False):
    found, complete = _presence(lambda path: _path_exists_local(sd_root, path))
    manual = bool(found and not database_registered_local(sd_root, PHYSICAL_DISC_DB_ID))
    ini_entry_present = _has_cd_ini_entry(_read_local_text(sd_root, MISTER_INI_PATH))
    update = bool(check_latest and found and complete and not manual and check_named_database_local(sd_root, PHYSICAL_DISC_DB_ID))
    status = _status(found, complete, manual, update, ini_entry_present=ini_entry_present)
    auto_state = get_auto_disc_detection_state_local(sd_root)
    status["auto_disc_detection_enabled"] = auto_state["enabled"]
    status["auto_disc_detection_current_main"] = auto_state["current_main"]
    return status


def _reboot_result(uninstall=False):
    action = "uninstall changes" if uninstall else "installation"
    return {"soft_reboot_required": True, "soft_reboot_title": "Soft Reboot Required", "soft_reboot_message": f"A soft reboot is required to apply the Physical Disc Cores {action}.\n\nDo you want to soft reboot MiSTer now?"}


def install_or_update_physical_disc(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    found, complete = _presence(lambda path: _path_exists(connection, path))
    manual = bool(found and not database_registered_online(connection, PHYSICAL_DISC_DB_ID))
    if complete and not manual and not _has_cd_ini_entry(_read_remote_text(connection, MISTER_INI_PATH)):
        _ensure_cd_ini_block(connection, log)
        return _reboot_result()
    original = ensure_database_source_online(connection, PHYSICAL_DISC_DB_ID, PHYSICAL_DISC_DB_URL)
    try:
        _prepare_manual_physical_disc_for_downloader(connection, log, manual=manual)
        _ensure_cd_ini_block(connection, log)
        run_named_database_online(connection, PHYSICAL_DISC_DB_ID, log=log)
        connection.run_command(f"chmod +x {_quote(PHYSICAL_DISC_BINARY)}")
    except Exception:
        restore_online(connection, original)
        raise
    return _reboot_result()


def install_or_update_physical_disc_local(sd_root, log):
    found, complete = _presence(lambda path: _path_exists_local(sd_root, path))
    manual = bool(found and not database_registered_local(sd_root, PHYSICAL_DISC_DB_ID))
    if complete and not manual and not _has_cd_ini_entry(_read_local_text(sd_root, MISTER_INI_PATH)):
        _ensure_cd_ini_block_local(sd_root, log)
        return _reboot_result()
    original = ensure_database_source_local(sd_root, PHYSICAL_DISC_DB_ID, PHYSICAL_DISC_DB_URL)
    try:
        _prepare_manual_physical_disc_for_downloader_local(sd_root, log, manual=manual)
        _ensure_cd_ini_block_local(sd_root, log)
        run_named_database_local(sd_root, PHYSICAL_DISC_DB_ID, log=log)
    except Exception:
        restore_local(sd_root, original)
        raise
    return _reboot_result()


def uninstall_physical_disc(connection, log, force=False):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")
    if _manual_physical_disc_install(connection):
        _prepare_manual_physical_disc_for_downloader(connection, log, manual=True)
        remove_database_source_online(connection, PHYSICAL_DISC_DB_ID)
        _remove_cd_ini_block(connection, log)
        return _reboot_result(uninstall=True)
    original = ensure_database_source_online(connection, PHYSICAL_DISC_DB_ID, PHYSICAL_DISC_DB_URL)
    try:
        _remove_cd_ini_block(connection, log)
        native = uninstall_named_database_online(connection, PHYSICAL_DISC_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_online(connection, PHYSICAL_DISC_DB_ID, PHYSICAL_DISC_DB_URL, filter_value="!all")
            run_named_database_online(connection, PHYSICAL_DISC_DB_ID, log=log)
            remove_database_source_online(connection, PHYSICAL_DISC_DB_ID)
    except Exception:
        restore_online(connection, original)
        raise
    return _reboot_result(uninstall=True)


def uninstall_physical_disc_local(sd_root, log, force=False):
    if _manual_physical_disc_install_local(sd_root):
        _prepare_manual_physical_disc_for_downloader_local(sd_root, log, manual=True)
        remove_database_source_local(sd_root, PHYSICAL_DISC_DB_ID)
        _remove_cd_ini_block_local(sd_root, log)
        return _reboot_result(uninstall=True)
    original = ensure_database_source_local(sd_root, PHYSICAL_DISC_DB_ID, PHYSICAL_DISC_DB_URL)
    try:
        _remove_cd_ini_block_local(sd_root, log)
        native = uninstall_named_database_local(sd_root, PHYSICAL_DISC_DB_ID, log=log, force=force)
        if not native:
            ensure_database_source_local(sd_root, PHYSICAL_DISC_DB_ID, PHYSICAL_DISC_DB_URL, filter_value="!all")
            run_named_database_local(sd_root, PHYSICAL_DISC_DB_ID, log=log)
            remove_database_source_local(sd_root, PHYSICAL_DISC_DB_ID)
    except Exception:
        restore_local(sd_root, original)
        raise
    return _reboot_result(uninstall=True)

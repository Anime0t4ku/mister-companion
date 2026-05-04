import io
import re
import zipfile

import requests

from core.extras_common import (
    _ensure_remote_dir,
    _fetch_latest_zip_release,
    _path_exists,
    _quote,
    _read_remote_text,
    _write_remote_bytes,
    _write_remote_text,
)


ZAPAROO_LAUNCHER_GITHUB_REPO = "ZaparooProject/zaparoo-launcher"

ZAPAROO_LAUNCHER_REMOTE_DIR = "/media/fat/zaparoo"
ZAPAROO_LAUNCHER_MAIN_PATH = "/media/fat/zaparoo/MiSTer_Zaparoo"
ZAPAROO_LAUNCHER_UI_PATH = "/media/fat/zaparoo/launcher"

ZAPAROO_LAUNCHER_SCRIPT_PATH = "/media/fat/Scripts/zaparoo.sh"
ZAPAROO_LAUNCHER_BACKUP_SCRIPT_PATH = "/media/fat/Scripts/zaparoo.sh.companion"

ZAPAROO_LAUNCHER_CONFIG_DIR = "/media/fat/Scripts/.config/zaparoo_launcher"
ZAPAROO_LAUNCHER_VERSION_FILE = "/media/fat/Scripts/.config/zaparoo_launcher/version.txt"
ZAPAROO_LAUNCHER_SCRIPT_MARKER = (
    "/media/fat/Scripts/.config/zaparoo_launcher/installed_by_mister_companion"
)

MISTER_INI_PATH = "/media/fat/MiSTer.ini"
FALLBACK_MISTER_INI_URL = (
    "https://raw.githubusercontent.com/Anime0t4ku/mister-companion/main/assets/MiSTer_example.ini"
)

MISTER_MAIN_VALUE = "zaparoo/MiSTer_Zaparoo"
MISTER_ALT_LAUNCHER_VALUE = "zaparoo/launcher"

ZAPAROO_LAUNCHER_INI_BLOCK = """main=zaparoo/MiSTer_Zaparoo
alt_launcher=zaparoo/launcher"""


def _fetch_latest_zaparoo_launcher_release():
    return _fetch_latest_zip_release(
        ZAPAROO_LAUNCHER_GITHUB_REPO,
        "Zaparoo Launcher/UI Beta",
    )


def _download_bytes(url: str, timeout: int = 90) -> bytes:
    response = requests.get(
        url,
        headers={"User-Agent": "MiSTer-Companion"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.content


def _remove_remote_file(connection, path: str):
    connection.run_command(f"rm -f {_quote(path)}")


def _read_installed_zaparoo_launcher_version(connection) -> str:
    return _read_remote_text(connection, ZAPAROO_LAUNCHER_VERSION_FILE).strip()


def _write_installed_zaparoo_launcher_version(connection, version: str):
    _ensure_remote_dir(connection, ZAPAROO_LAUNCHER_CONFIG_DIR)
    _write_remote_text(
        connection,
        ZAPAROO_LAUNCHER_VERSION_FILE,
        version.strip() + "\n",
    )


def _extract_required_file(zf: zipfile.ZipFile, wanted_path: str) -> bytes:
    wanted = wanted_path.replace("\\", "/").strip("/").lower()

    for member in zf.infolist():
        if member.is_dir():
            continue

        name = member.filename.replace("\\", "/").strip("/")
        if name.lower() == wanted:
            return zf.read(member)

    raise RuntimeError(f"Required file missing from ZIP: {wanted_path}")


def _download_fallback_mister_ini() -> str:
    data = _download_bytes(FALLBACK_MISTER_INI_URL, timeout=30)
    return data.decode("utf-8", errors="replace")


def _ensure_mister_ini_exists(connection, log):
    if _path_exists(connection, MISTER_INI_PATH):
        return

    log("MiSTer.ini not found, downloading fallback MiSTer_example.ini...\n")
    fallback_ini = _download_fallback_mister_ini()
    _write_remote_text(connection, MISTER_INI_PATH, fallback_ini)
    log(f"Installed fallback ini as {MISTER_INI_PATH}\n")


def _find_mister_section(lines: list[str]) -> tuple[int, int]:
    start = -1

    for index, line in enumerate(lines):
        if line.strip().lower() == "[mister]":
            start = index
            break

    if start == -1:
        return -1, -1

    end = len(lines)
    section_pattern = re.compile(r"^\s*\[[^\]]+\]\s*$")

    for index in range(start + 1, len(lines)):
        if section_pattern.match(lines[index]):
            end = index
            break

    return start, end


def _line_key_value(line: str) -> tuple[str, str] | tuple[None, None]:
    if "=" not in line:
        return None, None

    key, value = line.split("=", 1)
    return key.strip().lower(), value.strip()


def _strip_zaparoo_launcher_entries_from_section_body(section_body: list[str]) -> list[str]:
    cleaned_body = []
    index = 0

    while index < len(section_body):
        line = section_body[index]
        stripped = line.strip()

        # Clean up earlier test versions that used markdown code fences.
        if stripped in {"```", "```ini"}:
            block_lines = [line]
            index += 1

            while index < len(section_body):
                block_lines.append(section_body[index])
                if section_body[index].strip() == "```":
                    index += 1
                    break
                index += 1

            block_text = "\n".join(block_lines)
            block_normalized = block_text.replace("\r\n", "\n").replace("\r", "\n")

            if (
                "main=zaparoo/MiSTer_Zaparoo" in block_normalized
                and "alt_launcher=zaparoo/launcher" in block_normalized
            ):
                continue

            cleaned_body.extend(block_lines)
            continue

        key, value = _line_key_value(line)

        if key == "main" and value == MISTER_MAIN_VALUE:
            index += 1
            continue

        if key == "alt_launcher" and value == MISTER_ALT_LAUNCHER_VALUE:
            index += 1
            continue

        cleaned_body.append(line)
        index += 1

    return cleaned_body


def _patch_mister_ini_for_zaparoo_launcher(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")

    if lines and lines[-1] == "":
        lines = lines[:-1]

    start, end = _find_mister_section(lines)

    if start == -1:
        patched_lines = [
            "[MiSTer]",
            *ZAPAROO_LAUNCHER_INI_BLOCK.splitlines(),
            "",
        ]
        patched_lines.extend(lines)
        return "\n".join(patched_lines).rstrip("\n") + "\n"

    before = lines[: start + 1]
    section_body = lines[start + 1:end]
    after = lines[end:]

    cleaned_body = _strip_zaparoo_launcher_entries_from_section_body(section_body)

    while cleaned_body and not cleaned_body[-1].strip():
        cleaned_body.pop()

    if cleaned_body:
        cleaned_body.append("")

    cleaned_body.extend(ZAPAROO_LAUNCHER_INI_BLOCK.splitlines())

    if after and after[0].strip():
        cleaned_body.append("")

    patched_lines = before + cleaned_body + after
    return "\n".join(patched_lines).rstrip("\n") + "\n"


def _remove_zaparoo_launcher_from_mister_ini(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")

    if lines and lines[-1] == "":
        lines = lines[:-1]

    start, end = _find_mister_section(lines)
    if start == -1:
        return normalized.rstrip("\n") + "\n"

    before = lines[: start + 1]
    section_body = lines[start + 1:end]
    after = lines[end:]

    cleaned_body = _strip_zaparoo_launcher_entries_from_section_body(section_body)

    while cleaned_body and not cleaned_body[-1].strip():
        cleaned_body.pop()

    if cleaned_body and after and after[0].strip():
        cleaned_body.append("")

    patched_lines = before + cleaned_body + after
    return "\n".join(patched_lines).rstrip("\n") + "\n"


def _mister_ini_has_zaparoo_launcher_entries(connection) -> bool:
    text = _read_remote_text(connection, MISTER_INI_PATH)
    if not text:
        return False

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")

    start, end = _find_mister_section(lines)
    if start == -1:
        return False

    section_text = "\n".join(lines[start + 1:end])

    # Accept earlier broken/test fenced formats so old installs still show as installed.
    fenced_block_present = (
        "```" in section_text
        and "main=zaparoo/MiSTer_Zaparoo" in section_text
        and "alt_launcher=zaparoo/launcher" in section_text
    )

    if fenced_block_present:
        return True

    has_main = False
    has_alt_launcher = False

    for line in lines[start + 1:end]:
        key, value = _line_key_value(line)

        if key == "main" and value == MISTER_MAIN_VALUE:
            has_main = True

        if key == "alt_launcher" and value == MISTER_ALT_LAUNCHER_VALUE:
            has_alt_launcher = True

    return has_main and has_alt_launcher


def _patch_remote_mister_ini(connection, log):
    _ensure_mister_ini_exists(connection, log)

    current = _read_remote_text(connection, MISTER_INI_PATH)
    current_normalized = current.replace("\r\n", "\n").replace("\r", "\n")
    patched = _patch_mister_ini_for_zaparoo_launcher(current)

    if patched != current_normalized:
        _write_remote_text(connection, MISTER_INI_PATH, patched)
        log("Updated [MiSTer] section in MiSTer.ini for Zaparoo Launcher/UI Beta.\n")
    else:
        log("MiSTer.ini already contains the Zaparoo Launcher/UI Beta entries.\n")


def _remove_remote_mister_ini_entries(connection, log):
    current = _read_remote_text(connection, MISTER_INI_PATH)
    if not current:
        log("MiSTer.ini not found, nothing to clean up.\n")
        return

    current_normalized = current.replace("\r\n", "\n").replace("\r", "\n")
    patched = _remove_zaparoo_launcher_from_mister_ini(current)

    if patched != current_normalized:
        _write_remote_text(connection, MISTER_INI_PATH, patched)
        log("Removed Zaparoo Launcher/UI Beta entries from MiSTer.ini.\n")
    else:
        log("No Zaparoo Launcher/UI Beta entries found in MiSTer.ini.\n")


def _is_zaparoo_launcher_installed(connection) -> bool:
    return (
        _path_exists(connection, ZAPAROO_LAUNCHER_MAIN_PATH)
        and _path_exists(connection, ZAPAROO_LAUNCHER_UI_PATH)
        and _path_exists(connection, ZAPAROO_LAUNCHER_SCRIPT_PATH)
        and _mister_ini_has_zaparoo_launcher_entries(connection)
    )


def get_zaparoo_launcher_status(connection, check_latest: bool = False):
    if not connection.is_connected():
        return {
            "installed": False,
            "installed_version": "",
            "latest_version": "",
            "latest_error": "",
            "update_available": False,
            "status_text": "Unknown",
            "install_label": "Install",
            "install_enabled": False,
            "uninstall_enabled": False,
        }

    latest_version = ""
    latest_error = ""

    if check_latest:
        try:
            latest = _fetch_latest_zaparoo_launcher_release()
            latest_version = latest["version"]
        except Exception as exc:
            latest_error = str(exc)

    installed = _is_zaparoo_launcher_installed(connection)
    installed_version = (
        _read_installed_zaparoo_launcher_version(connection)
        if installed
        else ""
    )

    update_available = False
    if check_latest:
        if installed and latest_version and installed_version:
            update_available = installed_version != latest_version
        elif installed and latest_version and not installed_version:
            update_available = True

    if not installed:
        status_text = "✗ Not installed"
        install_label = "Install"
        install_enabled = True
        uninstall_enabled = False
    elif update_available:
        status_text = f"▲ Update available ({installed_version or 'unknown'} → {latest_version})"
        install_label = "Update"
        install_enabled = True
        uninstall_enabled = True
    else:
        version_display = installed_version or "unknown"
        status_text = f"✓ Installed ({version_display})"
        install_label = "Installed"
        install_enabled = False
        uninstall_enabled = True

    if latest_error and check_latest:
        status_text = f"{status_text} (update check failed: {latest_error})"

    return {
        "installed": installed,
        "installed_version": installed_version,
        "latest_version": latest_version,
        "latest_error": latest_error,
        "update_available": update_available,
        "status_text": status_text,
        "install_label": install_label,
        "install_enabled": install_enabled,
        "uninstall_enabled": uninstall_enabled,
    }


def install_or_update_zaparoo_launcher(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    latest = _fetch_latest_zaparoo_launcher_release()
    version = latest["version"]
    zip_url = latest["zip_url"]

    log(f"Latest version on GitHub: {version}\n")
    log(f"Downloading: {zip_url}\n")

    archive_data = _download_bytes(zip_url, timeout=90)
    log(f"Downloaded {len(archive_data)} bytes.\n")

    with zipfile.ZipFile(io.BytesIO(archive_data)) as zf:
        zaparoo_script = _extract_required_file(zf, "Scripts/zaparoo.sh")
        mister_zaparoo = _extract_required_file(zf, "zaparoo/MiSTer_Zaparoo")
        launcher = _extract_required_file(zf, "zaparoo/launcher")

    # Make sure /media/fat/zaparoo is really a directory.
    connection.run_command(
        f"if [ -e {_quote(ZAPAROO_LAUNCHER_REMOTE_DIR)} ] "
        f"&& [ ! -d {_quote(ZAPAROO_LAUNCHER_REMOTE_DIR)} ]; then "
        f"mv {_quote(ZAPAROO_LAUNCHER_REMOTE_DIR)} "
        f"{_quote(ZAPAROO_LAUNCHER_REMOTE_DIR + '.backup')}; "
        f"fi"
    )

    _ensure_remote_dir(connection, "/media/fat/Scripts")
    _ensure_remote_dir(connection, ZAPAROO_LAUNCHER_REMOTE_DIR)
    _ensure_remote_dir(connection, ZAPAROO_LAUNCHER_CONFIG_DIR)

    backup_exists = _path_exists(connection, ZAPAROO_LAUNCHER_BACKUP_SCRIPT_PATH)
    script_exists = _path_exists(connection, ZAPAROO_LAUNCHER_SCRIPT_PATH)
    marker_exists = _path_exists(connection, ZAPAROO_LAUNCHER_SCRIPT_MARKER)

    if script_exists and not backup_exists and not marker_exists:
        log(
            "Existing zaparoo.sh found, backing it up to "
            "zaparoo.sh.companion...\n"
        )
        connection.run_command(
            f"mv {_quote(ZAPAROO_LAUNCHER_SCRIPT_PATH)} "
            f"{_quote(ZAPAROO_LAUNCHER_BACKUP_SCRIPT_PATH)}"
        )
    elif backup_exists:
        log("Existing zaparoo.sh.companion backup found, keeping it untouched.\n")
    elif marker_exists:
        log("Existing Zaparoo Launcher dev zaparoo.sh detected, replacing it.\n")

    log("Removing old Zaparoo Launcher/UI Beta files before upload...\n")
    _remove_remote_file(connection, ZAPAROO_LAUNCHER_MAIN_PATH)
    _remove_remote_file(connection, ZAPAROO_LAUNCHER_UI_PATH)
    _remove_remote_file(connection, ZAPAROO_LAUNCHER_SCRIPT_PATH)

    log(f"Uploading launcher dev script: {ZAPAROO_LAUNCHER_SCRIPT_PATH}\n")
    _write_remote_bytes(connection, ZAPAROO_LAUNCHER_SCRIPT_PATH, zaparoo_script)

    log(f"Uploading: {ZAPAROO_LAUNCHER_MAIN_PATH}\n")
    _write_remote_bytes(connection, ZAPAROO_LAUNCHER_MAIN_PATH, mister_zaparoo)

    log(f"Uploading: {ZAPAROO_LAUNCHER_UI_PATH}\n")
    _write_remote_bytes(connection, ZAPAROO_LAUNCHER_UI_PATH, launcher)

    connection.run_command(f"chmod +x {_quote(ZAPAROO_LAUNCHER_SCRIPT_PATH)}")
    connection.run_command(f"chmod +x {_quote(ZAPAROO_LAUNCHER_MAIN_PATH)}")
    connection.run_command(f"chmod +x {_quote(ZAPAROO_LAUNCHER_UI_PATH)}")

    _write_remote_text(connection, ZAPAROO_LAUNCHER_SCRIPT_MARKER, "1\n")

    _patch_remote_mister_ini(connection, log)

    _write_installed_zaparoo_launcher_version(connection, version)
    log(f"Stored installed version marker: {version}\n")

    return {
        "installed_version": version,
        "reboot_required": True,
    }


def uninstall_zaparoo_launcher(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log("Removing Zaparoo Launcher/UI Beta files...\n")

    marker_exists = _path_exists(connection, ZAPAROO_LAUNCHER_SCRIPT_MARKER)
    backup_exists = _path_exists(connection, ZAPAROO_LAUNCHER_BACKUP_SCRIPT_PATH)

    _remove_remote_file(connection, ZAPAROO_LAUNCHER_MAIN_PATH)
    _remove_remote_file(connection, ZAPAROO_LAUNCHER_UI_PATH)
    _remove_remote_file(connection, ZAPAROO_LAUNCHER_VERSION_FILE)

    _remove_remote_mister_ini_entries(connection, log)

    if backup_exists:
        log("Restoring original zaparoo.sh from zaparoo.sh.companion...\n")
        _remove_remote_file(connection, ZAPAROO_LAUNCHER_SCRIPT_PATH)
        connection.run_command(
            f"mv {_quote(ZAPAROO_LAUNCHER_BACKUP_SCRIPT_PATH)} "
            f"{_quote(ZAPAROO_LAUNCHER_SCRIPT_PATH)}"
        )
        connection.run_command(f"chmod +x {_quote(ZAPAROO_LAUNCHER_SCRIPT_PATH)}")
    elif marker_exists:
        log("No zaparoo.sh.companion backup found, removing launcher dev zaparoo.sh.\n")
        _remove_remote_file(connection, ZAPAROO_LAUNCHER_SCRIPT_PATH)
    else:
        log("No zaparoo.sh.companion backup or Companion marker found, leaving zaparoo.sh untouched.\n")

    _remove_remote_file(connection, ZAPAROO_LAUNCHER_SCRIPT_MARKER)
    connection.run_command(
        f"rmdir {_quote(ZAPAROO_LAUNCHER_CONFIG_DIR)} 2>/dev/null || true"
    )

    log("Zaparoo Launcher/UI Beta uninstalled.\n")

    return {
        "uninstalled": True,
        "reboot_required": True,
    }
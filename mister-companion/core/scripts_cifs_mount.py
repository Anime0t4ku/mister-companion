import shlex
import re
from pathlib import Path

import requests

from core.scripts_common import (
    _chmod_local_executable,
    _local_path,
    _write_local_bytes,
    ensure_local_scripts_dir,
    ensure_remote_scripts_dir,
)
from core.scripts_version_check import is_version_older, parse_script_version


CIFS_MOUNT_URL = "https://raw.githubusercontent.com/MiSTer-devel/Scripts_MiSTer/master/cifs_mount.sh"
CIFS_UMOUNT_URL = "https://raw.githubusercontent.com/MiSTer-devel/Scripts_MiSTer/master/cifs_umount.sh"
CIFS_MOUNT_SCRIPT_PATH = "/media/fat/Scripts/cifs_mount.sh"
CIFS_UMOUNT_SCRIPT_PATH = "/media/fat/Scripts/cifs_umount.sh"
CIFS_CONFIG_PATH = "/media/fat/Scripts/cifs_mount.ini"


CIFS_CONFIG_DEFAULTS = {
    "SERVER": "",
    "SHARE": "MiSTer",
    "SHARE_DIRECTORY": "",
    "USERNAME": "",
    "PASSWORD": "",
    "DOMAIN": "",
    "LOCAL_DIR": "cifs",
    "ADDITIONAL_MOUNT_OPTIONS": "",
    "WAIT_FOR_SERVER": "false",
    "MOUNT_AT_BOOT": "false",
    "BASE_PATH": "/media/fat",
    "SINGLE_CIFS_CONNECTION": "true",
    "SPECIAL_DIRECTORIES": "config|linux|System Volume Information",
}

_SCRIPT_ASSIGNMENT_RE = re.compile(
    r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^#\r\n]*))\s*(?:#.*)?$"
)


def _download_cifs_scripts():
    mount_response = requests.get(CIFS_MOUNT_URL, timeout=30)
    mount_response.raise_for_status()
    mount_script = mount_response.content

    umount_response = requests.get(CIFS_UMOUNT_URL, timeout=30)
    umount_response.raise_for_status()
    umount_script = umount_response.content

    return mount_script, umount_script


def _parse_embedded_cifs_config(text):
    config = {}
    for raw_line in str(text or "").splitlines():
        if "CODE STARTS HERE" in raw_line.upper():
            break
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SCRIPT_ASSIGNMENT_RE.match(raw_line)
        if not match:
            continue
        key = match.group(1)
        if key not in CIFS_CONFIG_DEFAULTS or key in config:
            continue
        value = next((group for group in match.groups()[1:] if group is not None), "")
        config[key] = value.strip() if match.group(4) is not None else value
    return config


def _embedded_cifs_config_is_custom(config):
    return any(
        str(config.get(key, default)) != str(default)
        for key, default in CIFS_CONFIG_DEFAULTS.items()
    )


def _remote_file_exists(connection, path):
    output = connection.run_command(f"test -f {shlex.quote(path)} && printf 1 || printf 0")
    return str(output or "").strip().endswith("1")


def get_cifs_migration_info(connection):
    if _remote_file_exists(connection, CIFS_CONFIG_PATH):
        return {"available": False, "config": {}}
    text = connection.run_command(f"cat {shlex.quote(CIFS_MOUNT_SCRIPT_PATH)} 2>/dev/null || true") or ""
    config = _parse_embedded_cifs_config(text)
    return {"available": _embedded_cifs_config_is_custom(config), "config": config}


def get_cifs_migration_info_local(sd_root):
    config_path = _local_path(sd_root, CIFS_CONFIG_PATH)
    if config_path.is_file():
        return {"available": False, "config": {}}
    script_path = _local_path(sd_root, CIFS_MOUNT_SCRIPT_PATH)
    try:
        text = script_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        text = ""
    config = _parse_embedded_cifs_config(text)
    return {"available": _embedded_cifs_config_is_custom(config), "config": config}


def _migration_ini(config):
    values = dict(CIFS_CONFIG_DEFAULTS)
    values.update(config or {})
    return _build_cifs_ini(
        values["SERVER"], values["SHARE"], values["USERNAME"], values["PASSWORD"],
        str(values["MOUNT_AT_BOOT"]).lower() == "true",
        share_directory=values["SHARE_DIRECTORY"], domain=values["DOMAIN"],
        local_dir=values["LOCAL_DIR"], additional_mount_options=values["ADDITIONAL_MOUNT_OPTIONS"],
        existing_config=values,
    )


def migrate_embedded_cifs_config(connection):
    info = get_cifs_migration_info(connection)
    if not info["available"]:
        return False
    ensure_remote_scripts_dir(connection)
    temp_path = CIFS_CONFIG_PATH + ".mister_companion_tmp"
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(temp_path, "w") as remote_file:
            remote_file.write(_migration_ini(info["config"]))
        try:
            sftp.remove(CIFS_CONFIG_PATH)
        except OSError:
            pass
        sftp.rename(temp_path, CIFS_CONFIG_PATH)
    finally:
        try:
            sftp.remove(temp_path)
        except OSError:
            pass
        sftp.close()
    return True


def migrate_embedded_cifs_config_local(sd_root):
    info = get_cifs_migration_info_local(sd_root)
    if not info["available"]:
        return False
    ensure_local_scripts_dir(sd_root)
    path = _local_path(sd_root, CIFS_CONFIG_PATH)
    temp_path = Path(str(path) + ".mister_companion_tmp")
    temp_path.write_text(_migration_ini(info["config"]), encoding="utf-8")
    temp_path.replace(path)
    return True


def _installed_cifs_texts(connection):
    command = (
        f"cat {shlex.quote(CIFS_MOUNT_SCRIPT_PATH)} 2>/dev/null || true; "
        "printf '\\n__MISTER_COMPANION_CIFS_SPLIT__\\n'; "
        f"cat {shlex.quote(CIFS_UMOUNT_SCRIPT_PATH)} 2>/dev/null || true"
    )
    output = connection.run_command(command) or ""
    mount_text, _, umount_text = output.partition("__MISTER_COMPANION_CIFS_SPLIT__")
    return mount_text, umount_text


def _installed_cifs_texts_local(sd_root):
    texts = []
    for remote_path in (CIFS_MOUNT_SCRIPT_PATH, CIFS_UMOUNT_SCRIPT_PATH):
        try:
            texts.append(_local_path(sd_root, remote_path).read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            texts.append("")
    return tuple(texts)


def get_cifs_update_status(base_status, *, connection=None, sd_root=None, offline=False, check_latest=False, log=None):
    status = dict(base_status or {})
    if not status.get("installed"):
        return status
    mount_text, umount_text = (
        _installed_cifs_texts_local(sd_root) if offline else _installed_cifs_texts(connection)
    )
    installed_versions = (parse_script_version(mount_text), parse_script_version(umount_text))
    update_available = not all(installed_versions)
    latest_error = ""
    if check_latest:
        try:
            if log:
                log("Checking latest cifs_mount.sh and cifs_umount.sh versions...\n")
            latest_scripts = _download_cifs_scripts()
            latest_versions = tuple(parse_script_version(data.decode("utf-8", errors="ignore")) for data in latest_scripts)
            update_available = update_available or any(
                is_version_older(installed, latest)
                for installed, latest in zip(installed_versions, latest_versions)
            )
        except Exception as exc:
            latest_error = str(exc)

    migration_info = (
        get_cifs_migration_info_local(sd_root) if offline else get_cifs_migration_info(connection)
    )
    migration_available = bool(migration_info.get("available"))
    status["cifs_migration_available"] = migration_available
    status["latest_error"] = latest_error
    status["update_available"] = update_available
    status["install_enabled"] = update_available
    status["install_label"] = "Update" if update_available else "Installed"
    if update_available and migration_available:
        status.update(state="update_available", status_text="Update available; configuration migration required")
    elif update_available:
        status.update(state="update_available", status_text="Update available")
    elif migration_available:
        status.update(state="installed", status_text="Configuration migration available")
    return status


def _parse_cifs_config_text(text):
    config = {}

    if not text:
        return config

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue

        key, value = line.split("=", 1)
        config[key.strip()] = value.strip().strip('"')

    return config


def _clean_config_value(value):
    if value is None:
        return ""

    return str(value).replace('"', '\\"')


def _build_cifs_ini(
    server,
    share,
    username,
    password,
    mount_at_boot,
    share_directory="",
    domain="",
    local_dir="cifs/games",
    additional_mount_options="",
    existing_config=None,
):
    config = dict(existing_config or {})

    config["SERVER"] = server
    config["SHARE"] = share
    config["SHARE_DIRECTORY"] = share_directory
    config["USERNAME"] = username
    config["PASSWORD"] = password
    config["DOMAIN"] = domain
    config["LOCAL_DIR"] = local_dir or "cifs/games"
    config["ADDITIONAL_MOUNT_OPTIONS"] = additional_mount_options
    config["WAIT_FOR_SERVER"] = config.get("WAIT_FOR_SERVER", "true") or "true"
    config["MOUNT_AT_BOOT"] = str(mount_at_boot).lower()
    config["SINGLE_CIFS_CONNECTION"] = config.get("SINGLE_CIFS_CONNECTION", "true") or "true"

    preferred_order = [
        "SERVER",
        "SHARE",
        "SHARE_DIRECTORY",
        "USERNAME",
        "PASSWORD",
        "DOMAIN",
        "LOCAL_DIR",
        "ADDITIONAL_MOUNT_OPTIONS",
        "WAIT_FOR_SERVER",
        "MOUNT_AT_BOOT",
        "SINGLE_CIFS_CONNECTION",
    ]

    lines = []
    written = set()

    for key in preferred_order:
        lines.append(f'{key}="{_clean_config_value(config.get(key, ""))}"')
        written.add(key)

    for key, value in config.items():
        if key not in written:
            lines.append(f'{key}="{_clean_config_value(value)}"')

    return "\n".join(lines) + "\n"

def install_cifs_mount(connection, log):
    log("Installing cifs_mount scripts...\n")
    mount_script, umount_script = _download_cifs_scripts()

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(CIFS_MOUNT_SCRIPT_PATH, "wb") as remote_file:
            remote_file.write(mount_script)
        with sftp.open(CIFS_UMOUNT_SCRIPT_PATH, "wb") as remote_file:
            remote_file.write(umount_script)
    finally:
        sftp.close()

    connection.run_command(f"chmod +x {CIFS_MOUNT_SCRIPT_PATH}")
    connection.run_command(f"chmod +x {CIFS_UMOUNT_SCRIPT_PATH}")
    log("CIFS scripts installed.\n")


def install_cifs_mount_local(sd_root, log):
    log("Installing cifs_mount scripts to Offline SD Card...\n")
    mount_script, umount_script = _download_cifs_scripts()

    ensure_local_scripts_dir(sd_root)

    _write_local_bytes(sd_root, CIFS_MOUNT_SCRIPT_PATH, mount_script)
    _write_local_bytes(sd_root, CIFS_UMOUNT_SCRIPT_PATH, umount_script)

    _chmod_local_executable(sd_root, CIFS_MOUNT_SCRIPT_PATH)
    _chmod_local_executable(sd_root, CIFS_UMOUNT_SCRIPT_PATH)

    log("CIFS scripts installed.\n")
    log("Mount and unmount actions require Online / SSH Mode because they execute on a running MiSTer.\n")


def uninstall_cifs_mount(connection):
    connection.run_command(f"rm -f {CIFS_MOUNT_SCRIPT_PATH}")
    connection.run_command(f"rm -f {CIFS_UMOUNT_SCRIPT_PATH}")
    connection.run_command("rm -f /media/fat/Scripts/cifs_common.sh")


def uninstall_cifs_mount_local(sd_root):
    for remote_path in [
        CIFS_MOUNT_SCRIPT_PATH,
        CIFS_UMOUNT_SCRIPT_PATH,
        "/media/fat/Scripts/cifs_common.sh",
    ]:
        path = _local_path(sd_root, remote_path)
        if path.exists():
            path.unlink()


def run_cifs_mount(connection):
    return connection.run_command(CIFS_MOUNT_SCRIPT_PATH)


def run_cifs_umount(connection):
    return connection.run_command(CIFS_UMOUNT_SCRIPT_PATH)


def remove_cifs_config(connection):
    connection.run_command(f"rm -f {CIFS_CONFIG_PATH}")


def remove_cifs_config_local(sd_root):
    path = _local_path(sd_root, CIFS_CONFIG_PATH)
    if path.exists():
        path.unlink()


def load_cifs_config(connection):
    if not connection.is_connected():
        return {}

    output = connection.run_command(f"cat {CIFS_CONFIG_PATH} 2>/dev/null")
    return _parse_cifs_config_text(output or "")


def load_cifs_config_local(sd_root):
    path = _local_path(sd_root, CIFS_CONFIG_PATH)
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8", errors="ignore")
    return _parse_cifs_config_text(text)


def save_cifs_config(
    connection,
    server,
    share,
    username,
    password,
    mount_at_boot,
    share_directory="",
    domain="",
    local_dir="cifs/games",
    additional_mount_options="",
):
    existing_config = load_cifs_config(connection)
    ini = _build_cifs_ini(
        server,
        share,
        username,
        password,
        mount_at_boot,
        share_directory=share_directory,
        domain=domain,
        local_dir=local_dir,
        additional_mount_options=additional_mount_options,
        existing_config=existing_config,
    )

    ensure_remote_scripts_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.open(CIFS_CONFIG_PATH, "w") as remote_file:
            remote_file.write(ini)
    finally:
        sftp.close()


def save_cifs_config_local(
    sd_root,
    server,
    share,
    username,
    password,
    mount_at_boot,
    share_directory="",
    domain="",
    local_dir="cifs/games",
    additional_mount_options="",
):
    existing_config = load_cifs_config_local(sd_root)
    ini = _build_cifs_ini(
        server,
        share,
        username,
        password,
        mount_at_boot,
        share_directory=share_directory,
        domain=domain,
        local_dir=local_dir,
        additional_mount_options=additional_mount_options,
        existing_config=existing_config,
    )

    ensure_local_scripts_dir(sd_root)

    path = _local_path(sd_root, CIFS_CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ini, encoding="utf-8")


def test_cifs_connection(
    connection,
    server,
    share,
    username,
    password,
    share_directory="",
    domain="",
    additional_mount_options="",
):
    remote_share = f"//{server}/{share}"
    clean_share_directory = share_directory.strip().strip("/")
    if clean_share_directory:
        remote_share = f"{remote_share}/{clean_share_directory}"

    mount_options = []
    if username:
        mount_options.append(f"username={username}")
    if password:
        mount_options.append(f"password={password}")
    if domain:
        mount_options.append(f"domain={domain}")
    if additional_mount_options:
        mount_options.append(additional_mount_options)

    options = ",".join(mount_options) if mount_options else "guest"
    test_cmd = (
        f"mount -t cifs {shlex.quote(remote_share)} /tmp/cifs_test "
        f"-o {shlex.quote(options)}"
    )
    result = connection.run_command(
        f"mkdir -p /tmp/cifs_test && {test_cmd} && umount /tmp/cifs_test && echo SUCCESS"
    )
    return bool(result and "SUCCESS" in result)

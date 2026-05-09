import configparser
import posixpath
import re
import shutil
from io import StringIO

import requests

from core.scripts_common import (
    _chmod_local_executable,
    _local_path,
    _write_local_text,
)


RA_VIEWER_SCRIPT_URL = (
    "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/main/Scripts/ra_viewer.sh"
)

RA_VIEWER_SCRIPT_PATH = "/media/fat/Scripts/ra_viewer.sh"

RA_VIEWER_BASE_DIR = "/media/fat/Scripts/.config/ra_viewer"
RA_VIEWER_HELPER_PATH = f"{RA_VIEWER_BASE_DIR}/ra_viewer.py"
RA_VIEWER_CONFIG_PATH = f"{RA_VIEWER_BASE_DIR}/config.ini"
RA_VIEWER_LOG_PATH = f"{RA_VIEWER_BASE_DIR}/ra_viewer.log"
RA_VIEWER_PY_LIB_DIR = f"{RA_VIEWER_BASE_DIR}/python_lib"
RA_VIEWER_PIP_BOOTSTRAP_DIR = f"{RA_VIEWER_BASE_DIR}/pip_bootstrap"
RA_VIEWER_LIB_DIR = f"{RA_VIEWER_BASE_DIR}/lib"
RA_VIEWER_DEB_DIR = f"{RA_VIEWER_BASE_DIR}/debs"
RA_VIEWER_TMP_DIR = f"{RA_VIEWER_BASE_DIR}/tmp"
RA_VIEWER_FONT_DIR = f"{RA_VIEWER_BASE_DIR}/fonts"

RA_VIEWER_DEFAULT_CONFIG = """[retroachievements]
username=
api_key=
"""


def _download_text(url: str, timeout: int = 60) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": "MiSTer-Companion"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def _quote(path: str) -> str:
    return "'" + path.replace("'", "'\"'\"'") + "'"


def _remote_path_exists(connection, path: str) -> bool:
    result = connection.run_command(f"test -e {_quote(path)} && echo EXISTS || echo MISSING")
    return "EXISTS" in (result or "")


def _remote_file_exists(connection, path: str) -> bool:
    result = connection.run_command(f"test -f {_quote(path)} && echo EXISTS || echo MISSING")
    return "EXISTS" in (result or "")


def _remote_executable_exists(connection, path: str) -> bool:
    result = connection.run_command(f"test -x {_quote(path)} && echo EXISTS || echo MISSING")
    return "EXISTS" in (result or "")


def _ensure_remote_dir(connection, remote_dir: str):
    connection.run_command(f"mkdir -p {_quote(remote_dir)}")


def _write_remote_bytes(connection, path: str, data: bytes):
    sftp = connection.client.open_sftp()
    try:
        remote_dir = posixpath.dirname(path)
        _ensure_remote_dir(connection, remote_dir)

        with sftp.open(path, "wb") as remote_file:
            remote_file.write(data)
    finally:
        sftp.close()


def _write_remote_text(connection, path: str, text: str):
    _write_remote_bytes(connection, path, text.encode("utf-8"))


def _read_remote_text(connection, path: str, default: str = "") -> str:
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "r") as remote_file:
            data = remote_file.read()
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="replace")
            return data
    except Exception:
        return default
    finally:
        sftp.close()


def _extract_heredoc(script_text: str, target_path_variable: str) -> str:
    escaped_target = re.escape(target_path_variable)

    pattern = re.compile(
        rf"""cat\s*>\s*["']?{escaped_target}["']?\s*<<\s*['"]?([A-Za-z0-9_]+)['"]?\n(.*?)\n\1""",
        re.DOTALL,
    )

    match = pattern.search(script_text)
    if not match:
        raise RuntimeError(f"Could not extract heredoc for {target_path_variable} from ra_viewer.sh.")

    return match.group(2).rstrip("\n") + "\n"


def _extract_helper_python(script_text: str) -> str:
    try:
        return _extract_heredoc(script_text, r"$HELPER")
    except Exception:
        pass

    pattern = re.compile(
        r"""cat\s*>\s*["']?\$BASE/ra_viewer\.py["']?\s*<<\s*['"]?([A-Za-z0-9_]+)['"]?\n(.*?)\n\1""",
        re.DOTALL,
    )
    match = pattern.search(script_text)
    if not match:
        raise RuntimeError("Could not extract embedded ra_viewer.py from ra_viewer.sh.")

    return match.group(2).rstrip("\n") + "\n"


def _parse_ra_viewer_config_text(text: str) -> dict:
    parser = configparser.ConfigParser()
    parser.read_file(StringIO(text or RA_VIEWER_DEFAULT_CONFIG))

    if not parser.has_section("retroachievements"):
        parser.add_section("retroachievements")

    return {
        "username": parser.get("retroachievements", "username", fallback=""),
        "api_key": parser.get("retroachievements", "api_key", fallback=""),
    }


def _build_ra_viewer_config_text(username: str, api_key: str) -> str:
    parser = configparser.ConfigParser()
    parser["retroachievements"] = {
        "username": username.strip(),
        "api_key": api_key.strip(),
    }

    output = StringIO()
    parser.write(output)
    return output.getvalue()


def _ensure_default_config(connection):
    if _remote_file_exists(connection, RA_VIEWER_CONFIG_PATH):
        return False

    _write_remote_text(connection, RA_VIEWER_CONFIG_PATH, RA_VIEWER_DEFAULT_CONFIG)
    return True


def _ensure_default_config_local(sd_root):
    config_path = _local_path(sd_root, RA_VIEWER_CONFIG_PATH)
    if config_path.exists():
        return False

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(RA_VIEWER_DEFAULT_CONFIG, encoding="utf-8")
    return True


def _ensure_ra_viewer_local_dirs(sd_root):
    for path in [
        "/media/fat/Scripts",
        RA_VIEWER_BASE_DIR,
        RA_VIEWER_PY_LIB_DIR,
        RA_VIEWER_PIP_BOOTSTRAP_DIR,
        RA_VIEWER_LIB_DIR,
        RA_VIEWER_DEB_DIR,
        RA_VIEWER_TMP_DIR,
        RA_VIEWER_FONT_DIR,
    ]:
        _local_path(sd_root, path).mkdir(parents=True, exist_ok=True)


def get_ra_viewer_status(connection):
    if not connection.is_connected():
        return {
            "installed": False,
            "configured": False,
            "status_text": "Unknown",
            "install_enabled": False,
            "edit_config_enabled": False,
            "uninstall_enabled": False,
        }

    script_installed = _remote_executable_exists(connection, RA_VIEWER_SCRIPT_PATH)
    helper_installed = _remote_file_exists(connection, RA_VIEWER_HELPER_PATH)
    config_exists = _remote_file_exists(connection, RA_VIEWER_CONFIG_PATH)

    installed = script_installed and helper_installed

    configured = False
    if config_exists:
        config = load_ra_viewer_config(connection)
        configured = bool(
            config.get("username", "").strip()
            and config.get("api_key", "").strip()
        )

    if not installed:
        status_text = "✗ Not installed"
        install_enabled = True
        edit_config_enabled = False
        uninstall_enabled = False
    elif installed and not configured:
        status_text = "⚙ Installed, not configured"
        install_enabled = False
        edit_config_enabled = True
        uninstall_enabled = True
    else:
        status_text = "✓ Installed, configured"
        install_enabled = False
        edit_config_enabled = True
        uninstall_enabled = True

    return {
        "installed": installed,
        "configured": configured,
        "status_text": status_text,
        "install_enabled": install_enabled,
        "edit_config_enabled": edit_config_enabled,
        "uninstall_enabled": uninstall_enabled,
    }


def get_ra_viewer_status_local(sd_root):
    script_path = _local_path(sd_root, RA_VIEWER_SCRIPT_PATH)
    helper_path = _local_path(sd_root, RA_VIEWER_HELPER_PATH)
    config_path = _local_path(sd_root, RA_VIEWER_CONFIG_PATH)

    installed = script_path.exists() and helper_path.exists()

    configured = False
    if config_path.exists():
        config = load_ra_viewer_config_local(sd_root)
        configured = bool(
            config.get("username", "").strip()
            and config.get("api_key", "").strip()
        )

    if not installed:
        status_text = "✗ Not installed"
        install_enabled = True
        edit_config_enabled = False
        uninstall_enabled = False
    elif installed and not configured:
        status_text = "⚙ Installed, not configured"
        install_enabled = False
        edit_config_enabled = True
        uninstall_enabled = True
    else:
        status_text = "✓ Installed, configured"
        install_enabled = False
        edit_config_enabled = True
        uninstall_enabled = True

    return {
        "installed": installed,
        "configured": configured,
        "status_text": status_text,
        "install_enabled": install_enabled,
        "edit_config_enabled": edit_config_enabled,
        "uninstall_enabled": uninstall_enabled,
    }


def install_ra_viewer(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log("Installing RA Viewer...\n")

    _ensure_remote_dir(connection, "/media/fat/Scripts")
    _ensure_remote_dir(connection, RA_VIEWER_BASE_DIR)
    _ensure_remote_dir(connection, RA_VIEWER_PY_LIB_DIR)
    _ensure_remote_dir(connection, RA_VIEWER_PIP_BOOTSTRAP_DIR)
    _ensure_remote_dir(connection, RA_VIEWER_LIB_DIR)
    _ensure_remote_dir(connection, RA_VIEWER_DEB_DIR)
    _ensure_remote_dir(connection, RA_VIEWER_TMP_DIR)
    _ensure_remote_dir(connection, RA_VIEWER_FONT_DIR)

    log("Downloading ra_viewer.sh...\n")
    script_text = _download_text(RA_VIEWER_SCRIPT_URL)

    log("Extracting embedded ra_viewer.py...\n")
    helper_python = _extract_helper_python(script_text)

    log(f"Uploading script: {RA_VIEWER_SCRIPT_PATH}\n")
    _write_remote_text(connection, RA_VIEWER_SCRIPT_PATH, script_text)
    connection.run_command(f"chmod +x {_quote(RA_VIEWER_SCRIPT_PATH)}")

    log(f"Uploading helper: {RA_VIEWER_HELPER_PATH}\n")
    _write_remote_text(connection, RA_VIEWER_HELPER_PATH, helper_python)
    connection.run_command(f"chmod +x {_quote(RA_VIEWER_HELPER_PATH)}")

    log("Preparing config files and folders...\n")
    created_config = _ensure_default_config(connection)

    if created_config:
        log(f"Created default config: {RA_VIEWER_CONFIG_PATH}\n")
    else:
        log("Existing config.ini found, keeping it.\n")

    connection.run_command(f"test -f {_quote(RA_VIEWER_LOG_PATH)} || : > {_quote(RA_VIEWER_LOG_PATH)}")

    log("RA Viewer installed successfully.\n")
    log("Open Edit Config and enter your RetroAchievements username and Web API key.\n")

    return {
        "installed": True,
    }


def install_ra_viewer_local(sd_root, log):
    log("Installing RA Viewer to Offline SD Card...\n")

    _ensure_ra_viewer_local_dirs(sd_root)

    log("Downloading ra_viewer.sh...\n")
    script_text = _download_text(RA_VIEWER_SCRIPT_URL)

    log("Extracting embedded ra_viewer.py...\n")
    helper_python = _extract_helper_python(script_text)

    log(f"Writing script: {RA_VIEWER_SCRIPT_PATH}\n")
    _write_local_text(sd_root, RA_VIEWER_SCRIPT_PATH, script_text)
    _chmod_local_executable(sd_root, RA_VIEWER_SCRIPT_PATH)

    log(f"Writing helper: {RA_VIEWER_HELPER_PATH}\n")
    _write_local_text(sd_root, RA_VIEWER_HELPER_PATH, helper_python)
    _chmod_local_executable(sd_root, RA_VIEWER_HELPER_PATH)

    log("Preparing config files and folders...\n")
    created_config = _ensure_default_config_local(sd_root)

    if created_config:
        log(f"Created default config: {RA_VIEWER_CONFIG_PATH}\n")
    else:
        log("Existing config.ini found, keeping it.\n")

    log_path = _local_path(sd_root, RA_VIEWER_LOG_PATH)
    if not log_path.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("", encoding="utf-8")

    log("RA Viewer installed successfully.\n")
    log("Open Edit Config and enter your RetroAchievements username and Web API key.\n")

    return {
        "installed": True,
    }


def uninstall_ra_viewer(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log("Removing RA Viewer...\n")

    log(f"Removing script: {RA_VIEWER_SCRIPT_PATH}\n")
    connection.run_command(f"rm -f {_quote(RA_VIEWER_SCRIPT_PATH)}")

    log(f"Removing config folder: {RA_VIEWER_BASE_DIR}\n")
    connection.run_command(f"rm -rf {_quote(RA_VIEWER_BASE_DIR)}")

    log("RA Viewer uninstalled successfully.\n")

    return {
        "uninstalled": True,
    }


def uninstall_ra_viewer_local(sd_root, log):
    log("Removing RA Viewer...\n")

    script_path = _local_path(sd_root, RA_VIEWER_SCRIPT_PATH)
    base_dir = _local_path(sd_root, RA_VIEWER_BASE_DIR)

    log(f"Removing script: {RA_VIEWER_SCRIPT_PATH}\n")
    if script_path.exists():
        script_path.unlink()

    log(f"Removing config folder: {RA_VIEWER_BASE_DIR}\n")
    if base_dir.exists():
        shutil.rmtree(base_dir)

    log("RA Viewer uninstalled successfully.\n")

    return {
        "uninstalled": True,
    }


def load_ra_viewer_config(connection) -> dict:
    if not connection.is_connected():
        return {
            "username": "",
            "api_key": "",
        }

    text = _read_remote_text(connection, RA_VIEWER_CONFIG_PATH, RA_VIEWER_DEFAULT_CONFIG)
    return _parse_ra_viewer_config_text(text)


def load_ra_viewer_config_local(sd_root) -> dict:
    config_path = _local_path(sd_root, RA_VIEWER_CONFIG_PATH)

    if not config_path.exists():
        return {
            "username": "",
            "api_key": "",
        }

    text = config_path.read_text(encoding="utf-8", errors="replace")
    return _parse_ra_viewer_config_text(text)


def save_ra_viewer_config(connection, username: str, api_key: str):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    _ensure_remote_dir(connection, RA_VIEWER_BASE_DIR)

    text = _build_ra_viewer_config_text(username, api_key)
    _write_remote_text(connection, RA_VIEWER_CONFIG_PATH, text)

    return {
        "configured": bool(username.strip() and api_key.strip()),
    }


def save_ra_viewer_config_local(sd_root, username: str, api_key: str):
    config_path = _local_path(sd_root, RA_VIEWER_CONFIG_PATH)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    text = _build_ra_viewer_config_text(username, api_key)
    config_path.write_text(text, encoding="utf-8")

    return {
        "configured": bool(username.strip() and api_key.strip()),
    }
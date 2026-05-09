import html as html_lib
import io
import json
import posixpath
import re
import shlex
import shutil
import zipfile
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests


RA_ROOT_DIR = "/media/fat"

RA_CORES_DIR = "/media/fat/_RA_Cores"
RA_CORE_RBF_DIR = "/media/fat/_RA_Cores/Cores"

RA_LEGACY_CORES_DIR = "/media/fat/_RA Cores"

RA_CONFIG_DIR = "/media/fat/Scripts/.config/ra_cores"
RA_VERSION_FILE = "/media/fat/Scripts/.config/ra_cores/versions.json"

RA_MAIN_BINARY_PATH = "/media/fat/MiSTer_RA"
RA_LEGACY_INI_PATH = "/media/fat/MiSTer_RA.ini"
RA_CONFIG_PATH = "/media/fat/retroachievements.cfg"
RA_SOUND_PATH = "/media/fat/achievement.wav"

MISTER_INI_PATH = "/media/fat/MiSTer.ini"
MISTER_EXAMPLE_INI_PATH = "/media/fat/MiSTer_Example.ini"
FALLBACK_MISTER_EXAMPLE_URL = (
    "https://raw.githubusercontent.com/Anime0t4ku/mister-companion/main/assets/MiSTer_example.ini"
)

RA_SOURCES = [
    {
        "key": "main",
        "title": "Main_MiSTer",
        "repo": "odelot/Main_MiSTer",
        "kind": "main_zip",
    },
    {"key": "nes", "title": "NES", "repo": "odelot/NES_MiSTer", "kind": "rbf"},
    {"key": "snes", "title": "SNES", "repo": "odelot/SNES_MiSTer", "kind": "rbf"},
    {"key": "gameboy", "title": "Gameboy", "repo": "odelot/Gameboy_MiSTer", "kind": "rbf"},
    {"key": "gba", "title": "GBA", "repo": "odelot/GBA_MiSTer", "kind": "rbf"},
    {"key": "n64", "title": "N64", "repo": "odelot/N64_MiSTer", "kind": "rbf"},
    {"key": "psx", "title": "PSX", "repo": "odelot/PSX_MiSTer", "kind": "rbf"},
    {
        "key": "megadrive",
        "title": "MegaDrive",
        "repo": "odelot/MegaDrive_MiSTer",
        "kind": "rbf",
    },
    {"key": "megacd", "title": "MegaCD", "repo": "odelot/MegaCD_MiSTer", "kind": "rbf"},
    {"key": "sms", "title": "SMS", "repo": "odelot/SMS_MiSTer", "kind": "rbf"},
    {"key": "neogeo", "title": "NeoGeo", "repo": "odelot/NeoGeo_MiSTer", "kind": "rbf"},
    {
        "key": "turbografx16",
        "title": "TurboGrafx16",
        "repo": "odelot/TurboGrafx16_MiSTer",
        "kind": "rbf",
    },
    {"key": "s32x", "title": "S32X", "repo": "odelot/S32X_MiSTer", "kind": "rbf"},
]

RA_INI_BLOCK = """[RA_*]
main=MiSTer_RA
"""

RA_CONFIG_DEFAULT = """username=odelot
password=

# Show popup when a challenge indicator appears (1=yes, 0=no)
show_challenge_show_popup=1

# Show popup when a challenge indicator disappears / is missed (1=yes, 0=no)
show_challenge_hide_popup=0

# Show popup for achievement progress updates (1=yes, 0=no)
show_progress_popups=1

# Include achievement name in progress popups (1=yes, 0=no)
show_progress_name=1

# Enable leaderboard events/tracker popups (1=yes, 0=no)
leaderboards-enabled=1

# Turn on debug logging (1=yes, 0=no)
debug=0

# Enable hardcore mode for supported cores (1=yes, 0=no)
hardcore=0
"""

RA_CONFIG_KEYS = [
    "username",
    "password",
    "show_challenge_show_popup",
    "show_challenge_hide_popup",
    "show_progress_popups",
    "show_progress_name",
    "leaderboards-enabled",
    "debug",
    "hardcore",
]


def _quote(value: str) -> str:
    return shlex.quote(value)


def _ensure_remote_dir(connection, remote_dir: str):
    connection.run_command(f"mkdir -p {_quote(remote_dir)}")


def _path_exists(connection, path: str) -> bool:
    result = connection.run_command(f"test -e {_quote(path)} && echo EXISTS || echo MISSING")
    return "EXISTS" in (result or "")


def _glob_exists(connection, pattern: str) -> bool:
    command = (
        f"for f in {pattern}; do "
        f'[ -e "$f" ] && echo EXISTS && exit 0; '
        f"done; echo MISSING"
    )
    result = connection.run_command(command)
    return "EXISTS" in (result or "")


def _remove_remote_file(connection, path: str):
    connection.run_command(f"rm -f {_quote(path)}")


def _remove_remote_dir(connection, path: str):
    connection.run_command(f"rm -rf {_quote(path)}")


def _write_remote_bytes(connection, path: str, data: bytes):
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "wb") as remote_file:
            remote_file.write(data)
    finally:
        sftp.close()


def _write_remote_text(connection, path: str, text: str):
    _write_remote_bytes(connection, path, text.encode("utf-8"))


def _read_remote_text(connection, path: str) -> str:
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "r") as remote_file:
            data = remote_file.read()
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="replace")
            return data
    except Exception:
        return ""
    finally:
        sftp.close()


def _local_root(sd_root: str) -> Path:
    return Path(str(sd_root or "")).expanduser()


def _local_path(sd_root: str, remote_path: str) -> Path:
    root = _local_root(sd_root)
    clean = str(remote_path or "").strip()

    if clean.startswith("/media/fat/"):
        clean = clean[len("/media/fat/"):]
    elif clean == "/media/fat":
        clean = ""
    else:
        clean = clean.lstrip("/")

    return root / clean


def _local_glob_pattern(remote_pattern: str) -> str:
    pattern = str(remote_pattern or "").strip()

    if pattern.startswith("/media/fat/"):
        pattern = pattern[len("/media/fat/"):]
    elif pattern == "/media/fat":
        pattern = ""
    else:
        pattern = pattern.lstrip("/")

    return pattern


def _ensure_local_dir(sd_root: str, remote_dir: str):
    _local_path(sd_root, remote_dir).mkdir(parents=True, exist_ok=True)


def _path_exists_local(sd_root: str, remote_path: str) -> bool:
    return _local_path(sd_root, remote_path).exists()


def _glob_exists_local(sd_root: str, remote_pattern: str) -> bool:
    root = _local_root(sd_root)
    pattern = _local_glob_pattern(remote_pattern)
    return any(root.glob(pattern))


def _remove_local_file(sd_root: str, remote_path: str):
    path = _local_path(sd_root, remote_path)
    try:
        if path.exists() or path.is_symlink():
            path.unlink()
    except FileNotFoundError:
        pass


def _remove_local_dir(sd_root: str, remote_path: str):
    path = _local_path(sd_root, remote_path)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _write_local_bytes(sd_root: str, remote_path: str, data: bytes):
    path = _local_path(sd_root, remote_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_local_text(sd_root: str, remote_path: str, text: str):
    _write_local_bytes(sd_root, remote_path, text.encode("utf-8"))


def _read_local_text(sd_root: str, remote_path: str) -> str:
    path = _local_path(sd_root, remote_path)
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _chmod_local_executable(sd_root: str, remote_path: str):
    path = _local_path(sd_root, remote_path)
    if not path.exists():
        return

    try:
        mode = path.stat().st_mode
        path.chmod(mode | 0o755)
    except Exception:
        pass


def _download_bytes(url: str, timeout: int = 90) -> bytes:
    response = requests.get(
        url,
        headers={"User-Agent": "MiSTer-Companion"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.content


def _fetch_latest_release(repo: str) -> dict:
    return _fetch_latest_release_from_html(repo)


def _fetch_latest_release_from_html(repo: str) -> dict:
    latest_url = f"https://github.com/{repo}/releases/latest"

    response = requests.get(
        latest_url,
        headers={"User-Agent": "MiSTer-Companion"},
        timeout=30,
        allow_redirects=True,
    )
    response.raise_for_status()

    final_url = response.url
    marker = "/releases/tag/"
    if marker not in final_url:
        raise RuntimeError(f"Unable to determine latest release tag for {repo}.")

    tag_name = unquote(final_url.split(marker, 1)[1].split("?", 1)[0].strip())
    if not tag_name:
        raise RuntimeError(f"Unable to determine latest release tag for {repo}.")

    assets_url = f"https://github.com/{repo}/releases/expanded_assets/{tag_name}"

    assets_response = requests.get(
        assets_url,
        headers={
            "User-Agent": "MiSTer-Companion",
            "Accept": "text/html",
        },
        timeout=30,
    )
    assets_response.raise_for_status()

    page = assets_response.text
    assets = []
    seen_urls = set()

    href_pattern = re.compile(r'href="([^"]+)"')

    for match in href_pattern.finditer(page):
        href = html_lib.unescape(match.group(1))

        if "/releases/download/" not in href:
            continue

        if f"/{repo}/releases/download/{tag_name}/" not in href:
            continue

        url = urljoin("https://github.com", href)

        if url in seen_urls:
            continue

        seen_urls.add(url)

        name = unquote(posixpath.basename(url.split("?", 1)[0]))
        if not name:
            continue

        lower_name = name.lower()

        if lower_name.startswith("source code"):
            continue

        if not (
            lower_name.endswith(".zip")
            or lower_name.endswith(".rbf")
            or lower_name.endswith(".mra")
            or lower_name.endswith(".txt")
        ):
            continue

        assets.append(
            {
                "name": name,
                "url": url,
                "size": 0,
            }
        )

    if not assets:
        raise RuntimeError(
            f"Unable to find downloadable release assets for {repo} {tag_name}."
        )

    return {
        "repo": repo,
        "version": tag_name,
        "release_name": tag_name,
        "assets": assets,
    }


def _fetch_all_latest_releases() -> dict:
    latest = {}
    for source in RA_SOURCES:
        latest[source["key"]] = _fetch_latest_release(source["repo"])
    return latest


def _select_zip_asset(release: dict, title: str) -> dict:
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        url = asset.get("url", "")
        if name.lower().endswith(".zip") or url.lower().endswith(".zip"):
            return asset
    raise RuntimeError(f"Unable to find a ZIP asset in the latest {title} release.")


def _select_rbf_asset(release: dict, title: str) -> dict:
    zip_asset = None
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        url = asset.get("url", "")
        lower_name = name.lower()
        lower_url = url.lower()

        if lower_name.endswith(".rbf") or lower_url.endswith(".rbf"):
            return asset

        if lower_name.endswith(".zip") or lower_url.endswith(".zip"):
            zip_asset = asset

    if zip_asset:
        return zip_asset

    raise RuntimeError(f"Unable to find an RBF or ZIP asset in the latest {title} release.")


def _safe_basename(path: str) -> str:
    name = posixpath.basename(path.replace("\\", "/")).strip()
    if not name or name in (".", ".."):
        raise RuntimeError(f"Invalid archive filename: {path}")
    return name


def _extract_file_from_zip(archive_data: bytes, wanted_names: list[str]) -> bytes:
    wanted_lower = {name.lower() for name in wanted_names}
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            if _safe_basename(member.filename).lower() in wanted_lower:
                return archive.read(member)
    raise RuntimeError(f"Unable to find {', '.join(wanted_names)} in ZIP asset.")


def _extract_first_rbf_from_zip(archive_data: bytes) -> tuple[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            if member.filename.lower().endswith(".rbf"):
                return _safe_basename(member.filename), archive.read(member)
    raise RuntimeError("Unable to find an .rbf file in ZIP asset.")


def _read_versions(connection) -> dict:
    text = _read_remote_text(connection, RA_VERSION_FILE).strip()
    if not text:
        return {"sources": {}}

    try:
        payload = json.loads(text)
    except Exception:
        return {"sources": {}}

    if not isinstance(payload, dict):
        return {"sources": {}}

    if not isinstance(payload.get("sources"), dict):
        payload["sources"] = {}

    return payload


def _write_versions(connection, versions: dict):
    _ensure_remote_dir(connection, RA_CONFIG_DIR)
    _write_remote_text(
        connection,
        RA_VERSION_FILE,
        json.dumps(versions, indent=2, sort_keys=True) + "\n",
    )


def _read_versions_local(sd_root: str) -> dict:
    text = _read_local_text(sd_root, RA_VERSION_FILE).strip()
    if not text:
        return {"sources": {}}

    try:
        payload = json.loads(text)
    except Exception:
        return {"sources": {}}

    if not isinstance(payload, dict):
        return {"sources": {}}

    if not isinstance(payload.get("sources"), dict):
        payload["sources"] = {}

    return payload


def _write_versions_local(sd_root: str, versions: dict):
    _ensure_local_dir(sd_root, RA_CONFIG_DIR)
    _write_local_text(
        sd_root,
        RA_VERSION_FILE,
        json.dumps(versions, indent=2, sort_keys=True) + "\n",
    )


def _mister_ini_has_ra_block(connection) -> bool:
    text = _read_remote_text(connection, MISTER_INI_PATH)
    normalized = text.replace("\r\n", "\n")
    return bool(
        re.search(
            r"(?m)^\[RA_\*\]\s*\nmain\s*=\s*MiSTer_RA\s*$",
            normalized,
        )
    )


def _mister_ini_has_ra_block_local(sd_root: str) -> bool:
    text = _read_local_text(sd_root, MISTER_INI_PATH)
    normalized = text.replace("\r\n", "\n")
    return bool(
        re.search(
            r"(?m)^\[RA_\*\]\s*\nmain\s*=\s*MiSTer_RA\s*$",
            normalized,
        )
    )


def _mgl_path_for_source(source: dict) -> str:
    return posixpath.join(RA_CORES_DIR, f"{source['title']}.mgl")


def _rbf_path_for_source(source: dict) -> str:
    return posixpath.join(RA_CORE_RBF_DIR, f"{source['title']}.rbf")


def _expected_core_files_present(connection) -> bool:
    for source in RA_SOURCES:
        if source["key"] == "main":
            continue

        if not _path_exists(connection, _rbf_path_for_source(source)):
            return False

        if not _path_exists(connection, _mgl_path_for_source(source)):
            return False

    return True


def _expected_core_files_present_local(sd_root: str) -> bool:
    for source in RA_SOURCES:
        if source["key"] == "main":
            continue

        if not _path_exists_local(sd_root, _rbf_path_for_source(source)):
            return False

        if not _path_exists_local(sd_root, _mgl_path_for_source(source)):
            return False

    return True


def _is_ra_cores_installed(connection) -> bool:
    return (
        _path_exists(connection, RA_MAIN_BINARY_PATH)
        and _path_exists(connection, RA_CONFIG_PATH)
        and _path_exists(connection, RA_SOUND_PATH)
        and _mister_ini_has_ra_block(connection)
        and _expected_core_files_present(connection)
    )


def _is_ra_cores_installed_local(sd_root: str) -> bool:
    return (
        _path_exists_local(sd_root, RA_MAIN_BINARY_PATH)
        and _path_exists_local(sd_root, RA_CONFIG_PATH)
        and _path_exists_local(sd_root, RA_SOUND_PATH)
        and _mister_ini_has_ra_block_local(sd_root)
        and _expected_core_files_present_local(sd_root)
    )


def _is_legacy_ra_cores_installed(connection) -> bool:
    return (
        _path_exists(connection, RA_MAIN_BINARY_PATH)
        and _path_exists(connection, RA_LEGACY_INI_PATH)
        and _glob_exists(connection, f"{_quote(RA_LEGACY_CORES_DIR)}/*.rbf")
    )


def _is_legacy_ra_cores_installed_local(sd_root: str) -> bool:
    return (
        _path_exists_local(sd_root, RA_MAIN_BINARY_PATH)
        and _path_exists_local(sd_root, RA_LEGACY_INI_PATH)
        and _glob_exists_local(sd_root, "_RA Cores/*.rbf")
    )


def _source_titles_by_key() -> dict:
    return {source["key"]: source["title"] for source in RA_SOURCES}


def _get_outdated_sources(installed_versions: dict, latest_versions: dict) -> list[str]:
    outdated = []
    installed_sources = installed_versions.get("sources", {})

    for source in RA_SOURCES:
        key = source["key"]
        latest_version = (latest_versions.get(key, {}) or {}).get("version", "")
        installed_version = (installed_sources.get(key, {}) or {}).get("version", "")

        if latest_version and installed_version != latest_version:
            outdated.append(key)

    return outdated


def get_ra_cores_status(connection, check_latest: bool = False):
    if not connection.is_connected():
        return {
            "installed": False,
            "legacy_installed": False,
            "installed_versions": {},
            "latest_versions": {},
            "latest_error": "",
            "update_available": False,
            "outdated_sources": [],
            "status_text": "Unknown",
            "install_label": "Install",
            "install_enabled": False,
            "uninstall_enabled": False,
            "edit_config_enabled": False,
        }

    installed = _is_ra_cores_installed(connection)
    legacy_installed = False if installed else _is_legacy_ra_cores_installed(connection)

    installed_versions = _read_versions(connection) if (installed or legacy_installed) else {"sources": {}}

    latest_versions = {}
    latest_error = ""
    outdated_sources = []
    update_available = False

    if check_latest:
        try:
            latest_versions = _fetch_all_latest_releases()
            if installed:
                outdated_sources = _get_outdated_sources(
                    installed_versions,
                    latest_versions,
                )
                update_available = bool(outdated_sources)
        except Exception as exc:
            latest_error = str(exc)

    if legacy_installed:
        status_text = "▲ Legacy install found"
        install_label = "Migrate"
        install_enabled = True
        uninstall_enabled = True
    elif not installed:
        status_text = "✗ Not installed"
        install_label = "Install"
        install_enabled = True
        uninstall_enabled = False
    elif update_available:
        titles = _source_titles_by_key()
        first_titles = [titles.get(key, key) for key in outdated_sources[:3]]
        suffix = ", ".join(first_titles)

        if len(outdated_sources) > 3:
            suffix += f", +{len(outdated_sources) - 3} more"

        status_text = f"▲ Update available ({suffix})"
        install_label = "Update"
        install_enabled = True
        uninstall_enabled = True
    else:
        status_text = "✓ Installed"
        install_label = "Installed"
        install_enabled = False
        uninstall_enabled = True

    if installed and latest_error:
        status_text = f"✓ Installed (update check failed: {latest_error})"

    return {
        "installed": installed,
        "legacy_installed": legacy_installed,
        "installed_versions": installed_versions,
        "latest_versions": latest_versions,
        "latest_error": latest_error,
        "update_available": update_available,
        "outdated_sources": outdated_sources,
        "status_text": status_text,
        "install_label": install_label,
        "install_enabled": install_enabled,
        "uninstall_enabled": uninstall_enabled,
        "edit_config_enabled": _path_exists(connection, RA_CONFIG_PATH),
    }


def get_ra_cores_status_local(sd_root: str, check_latest: bool = False):
    if not sd_root or not _local_root(sd_root).exists():
        return {
            "installed": False,
            "legacy_installed": False,
            "installed_versions": {},
            "latest_versions": {},
            "latest_error": "",
            "update_available": False,
            "outdated_sources": [],
            "status_text": "Unknown",
            "install_label": "Install",
            "install_enabled": False,
            "uninstall_enabled": False,
            "edit_config_enabled": False,
        }

    installed = _is_ra_cores_installed_local(sd_root)
    legacy_installed = False if installed else _is_legacy_ra_cores_installed_local(sd_root)

    installed_versions = _read_versions_local(sd_root) if (installed or legacy_installed) else {"sources": {}}

    latest_versions = {}
    latest_error = ""
    outdated_sources = []
    update_available = False

    if check_latest:
        try:
            latest_versions = _fetch_all_latest_releases()
            if installed:
                outdated_sources = _get_outdated_sources(
                    installed_versions,
                    latest_versions,
                )
                update_available = bool(outdated_sources)
        except Exception as exc:
            latest_error = str(exc)

    if legacy_installed:
        status_text = "▲ Legacy install found"
        install_label = "Migrate"
        install_enabled = True
        uninstall_enabled = True
    elif not installed:
        status_text = "✗ Not installed"
        install_label = "Install"
        install_enabled = True
        uninstall_enabled = False
    elif update_available:
        titles = _source_titles_by_key()
        first_titles = [titles.get(key, key) for key in outdated_sources[:3]]
        suffix = ", ".join(first_titles)

        if len(outdated_sources) > 3:
            suffix += f", +{len(outdated_sources) - 3} more"

        status_text = f"▲ Update available ({suffix})"
        install_label = "Update"
        install_enabled = True
        uninstall_enabled = True
    else:
        status_text = "✓ Installed"
        install_label = "Installed"
        install_enabled = False
        uninstall_enabled = True

    if installed and latest_error:
        status_text = f"✓ Installed (update check failed: {latest_error})"

    return {
        "installed": installed,
        "legacy_installed": legacy_installed,
        "installed_versions": installed_versions,
        "latest_versions": latest_versions,
        "latest_error": latest_error,
        "update_available": update_available,
        "outdated_sources": outdated_sources,
        "status_text": status_text,
        "install_label": install_label,
        "install_enabled": install_enabled,
        "uninstall_enabled": uninstall_enabled,
        "edit_config_enabled": _path_exists_local(sd_root, RA_CONFIG_PATH),
    }


def _install_main_package(connection, release: dict, existing_config_present: bool, log) -> dict:
    asset = _select_zip_asset(release, "Main_MiSTer")

    log(f"Downloading Main_MiSTer {release['version']}: {asset['name']}\n")
    archive_data = _download_bytes(asset["url"])
    log(f"Downloaded {len(archive_data)} bytes.\n")

    mister_binary = _extract_file_from_zip(archive_data, ["MiSTer"])
    achievement_wav = _extract_file_from_zip(archive_data, ["achievement.wav"])

    _write_remote_bytes(connection, RA_MAIN_BINARY_PATH, mister_binary)
    connection.run_command(f"chmod +x {_quote(RA_MAIN_BINARY_PATH)}")
    log(f"Installed MiSTer binary as {RA_MAIN_BINARY_PATH}\n")

    _write_remote_bytes(connection, RA_SOUND_PATH, achievement_wav)
    log(f"Installed {RA_SOUND_PATH}\n")

    if existing_config_present:
        log(f"Keeping existing {RA_CONFIG_PATH}\n")
    else:
        try:
            cfg_data = _extract_file_from_zip(archive_data, ["retroachievements.cfg"])
        except Exception:
            cfg_data = RA_CONFIG_DEFAULT.encode("utf-8")

        _write_remote_bytes(connection, RA_CONFIG_PATH, cfg_data)
        log(f"Installed {RA_CONFIG_PATH}\n")

    return {
        "version": release["version"],
        "files": [RA_MAIN_BINARY_PATH, RA_SOUND_PATH, RA_CONFIG_PATH],
        "asset": asset.get("name", ""),
    }


def _install_main_package_local(sd_root: str, release: dict, existing_config_present: bool, log) -> dict:
    asset = _select_zip_asset(release, "Main_MiSTer")

    log(f"Downloading Main_MiSTer {release['version']}: {asset['name']}\n")
    archive_data = _download_bytes(asset["url"])
    log(f"Downloaded {len(archive_data)} bytes.\n")

    mister_binary = _extract_file_from_zip(archive_data, ["MiSTer"])
    achievement_wav = _extract_file_from_zip(archive_data, ["achievement.wav"])

    _write_local_bytes(sd_root, RA_MAIN_BINARY_PATH, mister_binary)
    _chmod_local_executable(sd_root, RA_MAIN_BINARY_PATH)
    log(f"Installed MiSTer binary as {RA_MAIN_BINARY_PATH}\n")

    _write_local_bytes(sd_root, RA_SOUND_PATH, achievement_wav)
    log(f"Installed {RA_SOUND_PATH}\n")

    if existing_config_present:
        log(f"Keeping existing {RA_CONFIG_PATH}\n")
    else:
        try:
            cfg_data = _extract_file_from_zip(archive_data, ["retroachievements.cfg"])
        except Exception:
            cfg_data = RA_CONFIG_DEFAULT.encode("utf-8")

        _write_local_bytes(sd_root, RA_CONFIG_PATH, cfg_data)
        log(f"Installed {RA_CONFIG_PATH}\n")

    return {
        "version": release["version"],
        "files": [RA_MAIN_BINARY_PATH, RA_SOUND_PATH, RA_CONFIG_PATH],
        "asset": asset.get("name", ""),
    }


def _create_mister_ini_if_missing(connection, log):
    if _path_exists(connection, MISTER_INI_PATH):
        log(f"Found existing {MISTER_INI_PATH}\n")
        return

    if _path_exists(connection, MISTER_EXAMPLE_INI_PATH):
        connection.run_command(f"cp {_quote(MISTER_EXAMPLE_INI_PATH)} {_quote(MISTER_INI_PATH)}")
        log(f"Copied {MISTER_EXAMPLE_INI_PATH} to {MISTER_INI_PATH}\n")
        return

    log("MiSTer.ini and MiSTer_Example.ini were not found, downloading fallback MiSTer_example.ini.\n")
    fallback_data = _download_bytes(FALLBACK_MISTER_EXAMPLE_URL)
    _write_remote_bytes(connection, MISTER_INI_PATH, fallback_data)
    log(f"Installed fallback ini as {MISTER_INI_PATH}\n")


def _create_mister_ini_if_missing_local(sd_root: str, log):
    if _path_exists_local(sd_root, MISTER_INI_PATH):
        log(f"Found existing {MISTER_INI_PATH}\n")
        return

    if _path_exists_local(sd_root, MISTER_EXAMPLE_INI_PATH):
        source = _local_path(sd_root, MISTER_EXAMPLE_INI_PATH)
        target = _local_path(sd_root, MISTER_INI_PATH)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        log(f"Copied {MISTER_EXAMPLE_INI_PATH} to {MISTER_INI_PATH}\n")
        return

    log("MiSTer.ini and MiSTer_Example.ini were not found, downloading fallback MiSTer_example.ini.\n")
    fallback_data = _download_bytes(FALLBACK_MISTER_EXAMPLE_URL)
    _write_local_bytes(sd_root, MISTER_INI_PATH, fallback_data)
    log(f"Installed fallback ini as {MISTER_INI_PATH}\n")


def _normalize_ini_text_for_append(text: str) -> str:
    normalized = text.replace("\r\n", "\n").rstrip("\n")
    if normalized:
        normalized += "\n\n"
    return normalized


def _remove_ra_wildcard_blocks(text: str) -> str:
    normalized = text.replace("\r\n", "\n")
    lines = normalized.split("\n")
    output = []
    index = 0

    while index < len(lines):
        line = lines[index]

        if line.strip() == "[RA_*]":
            block = [line]
            next_index = index + 1

            while next_index < len(lines):
                next_line = lines[next_index]
                if re.match(r"^\s*\[[^\]]+\]\s*$", next_line):
                    break
                block.append(next_line)
                next_index += 1

            has_ra_main = any(
                re.match(r"^\s*main\s*=\s*MiSTer_RA\s*$", block_line)
                for block_line in block[1:]
            )

            if has_ra_main:
                index = next_index
                continue

        output.append(line)
        index += 1

    cleaned = "\n".join(output)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).rstrip("\n")

    if cleaned:
        cleaned += "\n"

    return cleaned


def _ensure_ra_mister_ini_block(connection, log) -> bool:
    _create_mister_ini_if_missing(connection, log)

    current = _read_remote_text(connection, MISTER_INI_PATH)
    normalized = current.replace("\r\n", "\n")

    if re.search(r"(?m)^\[RA_\*\]\s*\nmain\s*=\s*MiSTer_RA\s*$", normalized):
        log("RetroAchievement [RA_*] block already present in MiSTer.ini.\n")
        return False

    cleaned = _remove_ra_wildcard_blocks(normalized)
    updated = _normalize_ini_text_for_append(cleaned) + RA_INI_BLOCK
    _write_remote_text(connection, MISTER_INI_PATH, updated)
    log("Added [RA_*] main=MiSTer_RA block to MiSTer.ini.\n")
    return True


def _ensure_ra_mister_ini_block_local(sd_root: str, log) -> bool:
    _create_mister_ini_if_missing_local(sd_root, log)

    current = _read_local_text(sd_root, MISTER_INI_PATH)
    normalized = current.replace("\r\n", "\n")

    if re.search(r"(?m)^\[RA_\*\]\s*\nmain\s*=\s*MiSTer_RA\s*$", normalized):
        log("RetroAchievement [RA_*] block already present in MiSTer.ini.\n")
        return False

    cleaned = _remove_ra_wildcard_blocks(normalized)
    updated = _normalize_ini_text_for_append(cleaned) + RA_INI_BLOCK
    _write_local_text(sd_root, MISTER_INI_PATH, updated)
    log("Added [RA_*] main=MiSTer_RA block to MiSTer.ini.\n")
    return True


def _remove_ra_mister_ini_block(connection, log):
    if not _path_exists(connection, MISTER_INI_PATH):
        return

    current = _read_remote_text(connection, MISTER_INI_PATH)
    cleaned = _remove_ra_wildcard_blocks(current)

    if cleaned != current.replace("\r\n", "\n"):
        _write_remote_text(connection, MISTER_INI_PATH, cleaned)
        log("Removed [RA_*] block from MiSTer.ini.\n")


def _remove_ra_mister_ini_block_local(sd_root: str, log):
    if not _path_exists_local(sd_root, MISTER_INI_PATH):
        return

    current = _read_local_text(sd_root, MISTER_INI_PATH)
    cleaned = _remove_ra_wildcard_blocks(current)

    if cleaned != current.replace("\r\n", "\n"):
        _write_local_text(sd_root, MISTER_INI_PATH, cleaned)
        log("Removed [RA_*] block from MiSTer.ini.\n")


def _write_mgl_launcher(connection, source: dict, log):
    core_name = source["title"]
    mgl_path = _mgl_path_for_source(source)

    mgl_text = f"""<mistergamedescription>
    <rbf>_RA_Cores/Cores/{core_name}</rbf>
    <setname same_dir="1">RA_{core_name}</setname>
</mistergamedescription>
"""

    _write_remote_text(connection, mgl_path, mgl_text)
    log(f"Installed launcher {mgl_path}\n")


def _write_mgl_launcher_local(sd_root: str, source: dict, log):
    core_name = source["title"]
    mgl_path = _mgl_path_for_source(source)

    mgl_text = f"""<mistergamedescription>
    <rbf>_RA_Cores/Cores/{core_name}</rbf>
    <setname same_dir="1">RA_{core_name}</setname>
</mistergamedescription>
"""

    _write_local_text(sd_root, mgl_path, mgl_text)
    log(f"Installed launcher {mgl_path}\n")


def _write_all_mgl_launchers(connection, log):
    for source in RA_SOURCES:
        if source["key"] == "main":
            continue

        _write_mgl_launcher(connection, source, log)


def _write_all_mgl_launchers_local(sd_root: str, log):
    for source in RA_SOURCES:
        if source["key"] == "main":
            continue

        _write_mgl_launcher_local(sd_root, source, log)


def _migrate_legacy_layout(connection, log):
    legacy_ini_present = _path_exists(connection, RA_LEGACY_INI_PATH)
    legacy_root_rbf_present = _glob_exists(connection, f"{_quote(RA_LEGACY_CORES_DIR)}/*.rbf")

    if not legacy_ini_present and not legacy_root_rbf_present:
        return False

    log("Legacy RetroAchievement Cores install detected, migrating to MGL method...\n")

    _ensure_remote_dir(connection, RA_CORES_DIR)
    _ensure_remote_dir(connection, RA_CORE_RBF_DIR)

    if legacy_root_rbf_present:
        command = (
            f"find {_quote(RA_LEGACY_CORES_DIR)} -maxdepth 1 -type f -name '*.rbf' "
            f"-exec mv -f {{}} {_quote(RA_CORE_RBF_DIR)}/ \\;"
        )
        connection.run_command(command)
        log(f"Moved legacy .rbf files into {RA_CORE_RBF_DIR}\n")

    _write_all_mgl_launchers(connection, log)
    _ensure_ra_mister_ini_block(connection, log)

    if legacy_ini_present:
        _remove_remote_file(connection, RA_LEGACY_INI_PATH)
        log(f"Removed legacy {RA_LEGACY_INI_PATH}\n")

    if _path_exists(connection, RA_LEGACY_CORES_DIR):
        _remove_remote_dir(connection, RA_LEGACY_CORES_DIR)
        log(f"Removed legacy {RA_LEGACY_CORES_DIR}\n")

    log("Migration to MGL method complete.\n")
    return True


def _migrate_legacy_layout_local(sd_root: str, log):
    legacy_ini_present = _path_exists_local(sd_root, RA_LEGACY_INI_PATH)
    legacy_root = _local_path(sd_root, RA_LEGACY_CORES_DIR)
    legacy_root_rbf_present = any(legacy_root.glob("*.rbf")) if legacy_root.exists() else False

    if not legacy_ini_present and not legacy_root_rbf_present:
        return False

    log("Legacy RetroAchievement Cores install detected, migrating to MGL method...\n")

    _ensure_local_dir(sd_root, RA_CORES_DIR)
    _ensure_local_dir(sd_root, RA_CORE_RBF_DIR)

    if legacy_root_rbf_present:
        target_dir = _local_path(sd_root, RA_CORE_RBF_DIR)
        target_dir.mkdir(parents=True, exist_ok=True)

        for rbf_path in legacy_root.glob("*.rbf"):
            shutil.move(str(rbf_path), str(target_dir / rbf_path.name))

        log(f"Moved legacy .rbf files into {RA_CORE_RBF_DIR}\n")

    _write_all_mgl_launchers_local(sd_root, log)
    _ensure_ra_mister_ini_block_local(sd_root, log)

    if legacy_ini_present:
        _remove_local_file(sd_root, RA_LEGACY_INI_PATH)
        log(f"Removed legacy {RA_LEGACY_INI_PATH}\n")

    if _path_exists_local(sd_root, RA_LEGACY_CORES_DIR):
        _remove_local_dir(sd_root, RA_LEGACY_CORES_DIR)
        log(f"Removed legacy {RA_LEGACY_CORES_DIR}\n")

    log("Migration to MGL method complete.\n")
    return True


def _remove_previous_source_files(connection, source_key: str, versions: dict):
    source_info = (versions.get("sources", {}) or {}).get(source_key, {})

    for path in source_info.get("files", []) or []:
        if isinstance(path, str) and path.startswith("/media/fat/"):
            _remove_remote_file(connection, path)


def _remove_previous_source_files_local(sd_root: str, source_key: str, versions: dict):
    source_info = (versions.get("sources", {}) or {}).get(source_key, {})

    for path in source_info.get("files", []) or []:
        if isinstance(path, str) and path.startswith("/media/fat/"):
            _remove_local_file(sd_root, path)


def _install_core_source(connection, source: dict, release: dict, versions: dict, log) -> dict:
    asset = _select_rbf_asset(release, source["title"])

    log(f"Downloading {source['title']} {release['version']}: {asset['name']}\n")
    data = _download_bytes(asset["url"])
    log(f"Downloaded {len(data)} bytes.\n")

    asset_name = asset.get("name", "")
    if asset_name.lower().endswith(".zip") or asset.get("url", "").lower().endswith(".zip"):
        _rbf_name, rbf_data = _extract_first_rbf_from_zip(data)
    else:
        _rbf_name = _safe_basename(asset_name or asset.get("url", ""))
        rbf_data = data

    _remove_previous_source_files(connection, source["key"], versions)

    remote_rbf_path = _rbf_path_for_source(source)
    remote_mgl_path = _mgl_path_for_source(source)

    _write_remote_bytes(connection, remote_rbf_path, rbf_data)
    log(f"Installed {remote_rbf_path}\n")

    _write_mgl_launcher(connection, source, log)

    return {
        "version": release["version"],
        "files": [remote_rbf_path, remote_mgl_path],
        "asset": asset_name,
    }


def _install_core_source_local(sd_root: str, source: dict, release: dict, versions: dict, log) -> dict:
    asset = _select_rbf_asset(release, source["title"])

    log(f"Downloading {source['title']} {release['version']}: {asset['name']}\n")
    data = _download_bytes(asset["url"])
    log(f"Downloaded {len(data)} bytes.\n")

    asset_name = asset.get("name", "")
    if asset_name.lower().endswith(".zip") or asset.get("url", "").lower().endswith(".zip"):
        _rbf_name, rbf_data = _extract_first_rbf_from_zip(data)
    else:
        _rbf_name = _safe_basename(asset_name or asset.get("url", ""))
        rbf_data = data

    _remove_previous_source_files_local(sd_root, source["key"], versions)

    remote_rbf_path = _rbf_path_for_source(source)
    remote_mgl_path = _mgl_path_for_source(source)

    _write_local_bytes(sd_root, remote_rbf_path, rbf_data)
    log(f"Installed {remote_rbf_path}\n")

    _write_mgl_launcher_local(sd_root, source, log)

    return {
        "version": release["version"],
        "files": [remote_rbf_path, remote_mgl_path],
        "asset": asset_name,
    }


def install_or_update_ra_cores(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    _ensure_remote_dir(connection, RA_CORES_DIR)
    _ensure_remote_dir(connection, RA_CORE_RBF_DIR)
    _ensure_remote_dir(connection, RA_CONFIG_DIR)

    legacy_before = _is_legacy_ra_cores_installed(connection)

    if legacy_before:
        _migrate_legacy_layout(connection, log)

    installed = _is_ra_cores_installed(connection)
    versions = _read_versions(connection)
    versions.setdefault("sources", {})

    existing_config_present = _path_exists(connection, RA_CONFIG_PATH)

    log("Checking latest RetroAchievement Cores releases...\n")

    try:
        latest_versions = _fetch_all_latest_releases()
    except Exception:
        if legacy_before and installed:
            _write_versions(connection, versions)
            log("Migration completed, but update check failed.\n")
            log("RetroAchievement Cores were migrated to the MGL method.\n")
            log("Please refresh later to check for updates.\n")
            return True

        raise

    if installed:
        sources_to_install = _get_outdated_sources(
            versions,
            latest_versions,
        )

        if not sources_to_install:
            log("All RetroAchievement Cores sources are already up to date.\n")
    else:
        log("RetroAchievement Cores are not fully installed, installing all sources...\n")
        sources_to_install = [source["key"] for source in RA_SOURCES]

    source_lookup = {source["key"]: source for source in RA_SOURCES}
    title_lookup = _source_titles_by_key()

    if installed and sources_to_install:
        readable_sources = ", ".join(
            title_lookup.get(source_key, source_key)
            for source_key in sources_to_install
        )
        log(f"Sources needing update: {readable_sources}\n")

    main_source = RA_SOURCES[0]
    main_key = main_source["key"]

    if main_key in sources_to_install:
        main_release = latest_versions[main_key]
        versions["sources"][main_key] = _install_main_package(
            connection,
            main_release,
            existing_config_present,
            log,
        )
    else:
        log("Main_MiSTer is already up to date, skipping download.\n")

    _ensure_ra_mister_ini_block(connection, log)

    for source_key in sources_to_install:
        if source_key == main_key:
            continue

        source = source_lookup.get(source_key)
        if not source:
            continue

        release = latest_versions[source_key]
        versions["sources"][source_key] = _install_core_source(
            connection,
            source,
            release,
            versions,
            log,
        )

    skipped_sources = [
        source
        for source in RA_SOURCES
        if source["key"] not in sources_to_install
    ]

    for source in skipped_sources:
        if source["key"] == main_key:
            continue

        expected_rbf = _rbf_path_for_source(source)
        expected_mgl = _mgl_path_for_source(source)

        if _path_exists(connection, expected_rbf):
            if not _path_exists(connection, expected_mgl):
                _write_mgl_launcher(connection, source, log)
            else:
                log(f"{source['title']} is already up to date, skipping download.\n")

    if _path_exists(connection, RA_LEGACY_INI_PATH):
        _remove_remote_file(connection, RA_LEGACY_INI_PATH)
        log(f"Removed legacy {RA_LEGACY_INI_PATH}\n")

    if _path_exists(connection, RA_LEGACY_CORES_DIR):
        _remove_remote_dir(connection, RA_LEGACY_CORES_DIR)
        log(f"Removed legacy {RA_LEGACY_CORES_DIR}\n")

    _write_versions(connection, versions)
    log("Saved RetroAchievement Cores installed version information.\n")

    return True


def install_or_update_ra_cores_local(sd_root: str, log):
    if not sd_root or not _local_root(sd_root).exists():
        raise RuntimeError("Selected Offline SD Card folder does not exist.")

    _ensure_local_dir(sd_root, RA_CORES_DIR)
    _ensure_local_dir(sd_root, RA_CORE_RBF_DIR)
    _ensure_local_dir(sd_root, RA_CONFIG_DIR)

    legacy_before = _is_legacy_ra_cores_installed_local(sd_root)

    if legacy_before:
        _migrate_legacy_layout_local(sd_root, log)

    installed = _is_ra_cores_installed_local(sd_root)
    versions = _read_versions_local(sd_root)
    versions.setdefault("sources", {})

    existing_config_present = _path_exists_local(sd_root, RA_CONFIG_PATH)

    log("Checking latest RetroAchievement Cores releases...\n")

    try:
        latest_versions = _fetch_all_latest_releases()
    except Exception:
        if legacy_before and installed:
            _write_versions_local(sd_root, versions)
            log("Migration completed, but update check failed.\n")
            log("RetroAchievement Cores were migrated to the MGL method.\n")
            log("Please refresh later to check for updates.\n")
            return True

        raise

    if installed:
        sources_to_install = _get_outdated_sources(
            versions,
            latest_versions,
        )

        if not sources_to_install:
            log("All RetroAchievement Cores sources are already up to date.\n")
    else:
        log("RetroAchievement Cores are not fully installed, installing all sources...\n")
        sources_to_install = [source["key"] for source in RA_SOURCES]

    source_lookup = {source["key"]: source for source in RA_SOURCES}
    title_lookup = _source_titles_by_key()

    if installed and sources_to_install:
        readable_sources = ", ".join(
            title_lookup.get(source_key, source_key)
            for source_key in sources_to_install
        )
        log(f"Sources needing update: {readable_sources}\n")

    main_source = RA_SOURCES[0]
    main_key = main_source["key"]

    if main_key in sources_to_install:
        main_release = latest_versions[main_key]
        versions["sources"][main_key] = _install_main_package_local(
            sd_root,
            main_release,
            existing_config_present,
            log,
        )
    else:
        log("Main_MiSTer is already up to date, skipping download.\n")

    _ensure_ra_mister_ini_block_local(sd_root, log)

    for source_key in sources_to_install:
        if source_key == main_key:
            continue

        source = source_lookup.get(source_key)
        if not source:
            continue

        release = latest_versions[source_key]
        versions["sources"][source_key] = _install_core_source_local(
            sd_root,
            source,
            release,
            versions,
            log,
        )

    skipped_sources = [
        source
        for source in RA_SOURCES
        if source["key"] not in sources_to_install
    ]

    for source in skipped_sources:
        if source["key"] == main_key:
            continue

        expected_rbf = _rbf_path_for_source(source)
        expected_mgl = _mgl_path_for_source(source)

        if _path_exists_local(sd_root, expected_rbf):
            if not _path_exists_local(sd_root, expected_mgl):
                _write_mgl_launcher_local(sd_root, source, log)
            else:
                log(f"{source['title']} is already up to date, skipping download.\n")

    if _path_exists_local(sd_root, RA_LEGACY_INI_PATH):
        _remove_local_file(sd_root, RA_LEGACY_INI_PATH)
        log(f"Removed legacy {RA_LEGACY_INI_PATH}\n")

    if _path_exists_local(sd_root, RA_LEGACY_CORES_DIR):
        _remove_local_dir(sd_root, RA_LEGACY_CORES_DIR)
        log(f"Removed legacy {RA_LEGACY_CORES_DIR}\n")

    _write_versions_local(sd_root, versions)
    log("Saved RetroAchievement Cores installed version information.\n")

    return True


def uninstall_ra_cores(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log("Removing RetroAchievement Cores files...\n")

    _remove_remote_file(connection, RA_MAIN_BINARY_PATH)
    _remove_remote_file(connection, RA_LEGACY_INI_PATH)
    _remove_remote_file(connection, RA_SOUND_PATH)
    _remove_remote_file(connection, RA_VERSION_FILE)
    _remove_remote_dir(connection, RA_CORES_DIR)
    _remove_remote_dir(connection, RA_LEGACY_CORES_DIR)
    _remove_ra_mister_ini_block(connection, log)

    log(f"Removed {RA_MAIN_BINARY_PATH}\n")
    log(f"Removed legacy {RA_LEGACY_INI_PATH}\n")
    log(f"Removed {RA_SOUND_PATH}\n")
    log(f"Removed {RA_CORES_DIR}\n")
    log(f"Removed legacy {RA_LEGACY_CORES_DIR}\n")
    log(f"Removed {RA_VERSION_FILE}\n")
    log(f"Kept {RA_CONFIG_PATH}\n")

    return True


def uninstall_ra_cores_local(sd_root: str, log):
    if not sd_root or not _local_root(sd_root).exists():
        raise RuntimeError("Selected Offline SD Card folder does not exist.")

    log("Removing RetroAchievement Cores files...\n")

    _remove_local_file(sd_root, RA_MAIN_BINARY_PATH)
    _remove_local_file(sd_root, RA_LEGACY_INI_PATH)
    _remove_local_file(sd_root, RA_SOUND_PATH)
    _remove_local_file(sd_root, RA_VERSION_FILE)
    _remove_local_dir(sd_root, RA_CORES_DIR)
    _remove_local_dir(sd_root, RA_LEGACY_CORES_DIR)
    _remove_ra_mister_ini_block_local(sd_root, log)

    log(f"Removed {RA_MAIN_BINARY_PATH}\n")
    log(f"Removed legacy {RA_LEGACY_INI_PATH}\n")
    log(f"Removed {RA_SOUND_PATH}\n")
    log(f"Removed {RA_CORES_DIR}\n")
    log(f"Removed legacy {RA_LEGACY_CORES_DIR}\n")
    log(f"Removed {RA_VERSION_FILE}\n")
    log(f"Kept {RA_CONFIG_PATH}\n")

    return True


def read_ra_config(connection) -> dict:
    text = _read_remote_text(connection, RA_CONFIG_PATH)
    if not text:
        text = RA_CONFIG_DEFAULT

    values = {}
    for key in RA_CONFIG_KEYS:
        values[key] = ""

    for line in text.replace("\r\n", "\n").split("\n"):
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()

        if key in values:
            values[key] = value.strip()

    return values


def read_ra_config_local(sd_root: str) -> dict:
    text = _read_local_text(sd_root, RA_CONFIG_PATH)
    if not text:
        text = RA_CONFIG_DEFAULT

    values = {}
    for key in RA_CONFIG_KEYS:
        values[key] = ""

    for line in text.replace("\r\n", "\n").split("\n"):
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()

        if key in values:
            values[key] = value.strip()

    return values


def write_ra_config(connection, values: dict):
    current = _read_remote_text(connection, RA_CONFIG_PATH)
    if not current:
        current = RA_CONFIG_DEFAULT

    normalized = current.replace("\r\n", "\n")
    lines = normalized.split("\n")
    seen = set()
    updated_lines = []

    for line in lines:
        if "=" not in line:
            updated_lines.append(line)
            continue

        key, old_value = line.split("=", 1)
        stripped_key = key.strip()

        if stripped_key not in RA_CONFIG_KEYS:
            updated_lines.append(line)
            continue

        value = str(values.get(stripped_key, old_value)).strip()
        updated_lines.append(f"{stripped_key}={value}")
        seen.add(stripped_key)

    missing = [key for key in RA_CONFIG_KEYS if key not in seen]
    if missing:
        while updated_lines and updated_lines[-1] == "":
            updated_lines.pop()

        if updated_lines:
            updated_lines.append("")

        for key in missing:
            updated_lines.append(f"{key}={str(values.get(key, '')).strip()}")

    updated = "\n".join(updated_lines).rstrip("\n") + "\n"
    _write_remote_text(connection, RA_CONFIG_PATH, updated)
    return True


def write_ra_config_local(sd_root: str, values: dict):
    current = _read_local_text(sd_root, RA_CONFIG_PATH)
    if not current:
        current = RA_CONFIG_DEFAULT

    normalized = current.replace("\r\n", "\n")
    lines = normalized.split("\n")
    seen = set()
    updated_lines = []

    for line in lines:
        if "=" not in line:
            updated_lines.append(line)
            continue

        key, old_value = line.split("=", 1)
        stripped_key = key.strip()

        if stripped_key not in RA_CONFIG_KEYS:
            updated_lines.append(line)
            continue

        value = str(values.get(stripped_key, old_value)).strip()
        updated_lines.append(f"{stripped_key}={value}")
        seen.add(stripped_key)

    missing = [key for key in RA_CONFIG_KEYS if key not in seen]
    if missing:
        while updated_lines and updated_lines[-1] == "":
            updated_lines.pop()

        if updated_lines:
            updated_lines.append("")

        for key in missing:
            updated_lines.append(f"{key}={str(values.get(key, '')).strip()}")

    updated = "\n".join(updated_lines).rstrip("\n") + "\n"
    _write_local_text(sd_root, RA_CONFIG_PATH, updated)
    return True
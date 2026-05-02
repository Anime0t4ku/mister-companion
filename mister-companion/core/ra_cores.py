import html as html_lib
import io
import json
import posixpath
import re
import shlex
import zipfile
from urllib.parse import unquote, urljoin

import requests


RA_ROOT_DIR = "/media/fat"
RA_CORES_DIR = "/media/fat/_RA Cores"
RA_CONFIG_DIR = "/media/fat/Scripts/.config/ra_cores"
RA_VERSION_FILE = "/media/fat/Scripts/.config/ra_cores/versions.json"

RA_MAIN_BINARY_PATH = "/media/fat/MiSTer_RA"
RA_INI_PATH = "/media/fat/MiSTer_RA.ini"
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

RA_INI_BLOCK = """[NES]
main=MiSTer_RA

[SNES]
main=MiSTer_RA

[Gameboy]
main=MiSTer_RA

[GBA]
main=MiSTer_RA

[N64]
main=MiSTer_RA

[PSX]
main=MiSTer_RA

[MegaDrive]
main=MiSTer_RA

[MegaCD]
main=MiSTer_RA

[SMS]
main=MiSTer_RA

[NeoGeo]
main=MiSTer_RA

[TurboGrafx16]
main=MiSTer_RA

[S32X]
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

    # The expanded_assets page contains the actual asset hrefs, unlike the
    # normal release page where assets may be lazy-loaded.
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

        # Ignore GitHub autogenerated source archives.
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


def _is_ra_cores_installed(connection) -> bool:
    return (
        _path_exists(connection, RA_MAIN_BINARY_PATH)
        and _path_exists(connection, RA_INI_PATH)
        and _path_exists(connection, RA_CONFIG_PATH)
        and _path_exists(connection, RA_SOUND_PATH)
        and _glob_exists(connection, f"{_quote(RA_CORES_DIR)}/*.rbf")
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
    installed_versions = _read_versions(connection) if installed else {"sources": {}}

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

    if not installed:
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


def _create_ra_ini_if_missing(connection, log):
    if _path_exists(connection, RA_INI_PATH):
        log(f"Found existing {RA_INI_PATH}\n")
        return

    if _path_exists(connection, MISTER_INI_PATH):
        connection.run_command(f"cp {_quote(MISTER_INI_PATH)} {_quote(RA_INI_PATH)}")
        log(f"Copied {MISTER_INI_PATH} to {RA_INI_PATH}\n")
        return

    if _path_exists(connection, MISTER_EXAMPLE_INI_PATH):
        connection.run_command(f"cp {_quote(MISTER_EXAMPLE_INI_PATH)} {_quote(RA_INI_PATH)}")
        log(f"Copied {MISTER_EXAMPLE_INI_PATH} to {RA_INI_PATH}\n")
        return

    log("MiSTer.ini and MiSTer_Example.ini were not found, downloading fallback MiSTer_example.ini.\n")
    fallback_data = _download_bytes(FALLBACK_MISTER_EXAMPLE_URL)
    _write_remote_bytes(connection, RA_INI_PATH, fallback_data)
    log(f"Installed fallback ini as {RA_INI_PATH}\n")


def _normalize_ini_text_for_append(text: str) -> str:
    normalized = text.replace("\r\n", "\n").rstrip("\n")
    if normalized:
        normalized += "\n\n"
    return normalized


def _remove_exact_ra_ini_blocks(text: str) -> str:
    normalized = text.replace("\r\n", "\n")
    headers = [
        "NES",
        "SNES",
        "Gameboy",
        "GBA",
        "N64",
        "PSX",
        "MegaDrive",
        "MegaCD",
        "SMS",
        "NeoGeo",
        "TurboGrafx16",
        "S32X",
    ]

    for header in headers:
        pattern = re.compile(
            rf"(?:\n{{0,2}})\[{re.escape(header)}\]\nmain\s*=\s*MiSTer_RA\n?",
            re.MULTILINE,
        )
        normalized = re.sub(pattern, "\n", normalized)

    normalized = re.sub(r"\n{3,}", "\n\n", normalized).rstrip("\n")
    if normalized:
        normalized += "\n"
    return normalized


def _ensure_ra_ini_blocks(connection, log) -> bool:
    current = _read_remote_text(connection, RA_INI_PATH)
    normalized = current.replace("\r\n", "\n")
    wanted = RA_INI_BLOCK.rstrip("\n")

    if normalized.rstrip("\n").endswith(wanted):
        log("RetroAchievement core override blocks already present at the bottom of MiSTer_RA.ini.\n")
        return False

    cleaned = _remove_exact_ra_ini_blocks(normalized)
    updated = _normalize_ini_text_for_append(cleaned) + RA_INI_BLOCK
    _write_remote_text(connection, RA_INI_PATH, updated)
    log("Added RetroAchievement core override blocks to the bottom of MiSTer_RA.ini.\n")
    return True


def _remove_previous_source_files(connection, source_key: str, versions: dict):
    source_info = (versions.get("sources", {}) or {}).get(source_key, {})
    for path in source_info.get("files", []) or []:
        if isinstance(path, str) and path.startswith("/media/fat/"):
            _remove_remote_file(connection, path)


def _install_core_source(connection, source: dict, release: dict, versions: dict, log) -> dict:
    asset = _select_rbf_asset(release, source["title"])
    log(f"Downloading {source['title']} {release['version']}: {asset['name']}\n")
    data = _download_bytes(asset["url"])
    log(f"Downloaded {len(data)} bytes.\n")

    asset_name = asset.get("name", "")
    if asset_name.lower().endswith(".zip") or asset.get("url", "").lower().endswith(".zip"):
        rbf_name, rbf_data = _extract_first_rbf_from_zip(data)
    else:
        rbf_name = _safe_basename(asset_name or asset.get("url", ""))
        rbf_data = data

    _remove_previous_source_files(connection, source["key"], versions)

    remote_path = posixpath.join(RA_CORES_DIR, rbf_name)
    _write_remote_bytes(connection, remote_path, rbf_data)
    log(f"Installed {remote_path}\n")

    return {
        "version": release["version"],
        "files": [remote_path],
        "asset": asset_name,
    }


def install_or_update_ra_cores(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log("Checking latest RetroAchievement Cores releases...\n")
    latest_versions = _fetch_all_latest_releases()

    _ensure_remote_dir(connection, RA_CORES_DIR)
    _ensure_remote_dir(connection, RA_CONFIG_DIR)

    versions = _read_versions(connection)
    existing_config_present = _path_exists(connection, RA_CONFIG_PATH)

    main_source = RA_SOURCES[0]
    main_release = latest_versions[main_source["key"]]
    versions.setdefault("sources", {})[main_source["key"]] = _install_main_package(
        connection,
        main_release,
        existing_config_present,
        log,
    )

    _create_ra_ini_if_missing(connection, log)
    _ensure_ra_ini_blocks(connection, log)

    for source in RA_SOURCES[1:]:
        release = latest_versions[source["key"]]
        versions["sources"][source["key"]] = _install_core_source(
            connection,
            source,
            release,
            versions,
            log,
        )

    _write_versions(connection, versions)
    log("Saved RetroAchievement Cores installed version information.\n")

    return True


def uninstall_ra_cores(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log("Removing RetroAchievement Cores files...\n")

    _remove_remote_file(connection, RA_MAIN_BINARY_PATH)
    _remove_remote_file(connection, RA_INI_PATH)
    _remove_remote_file(connection, RA_SOUND_PATH)
    _remove_remote_file(connection, RA_VERSION_FILE)
    _remove_remote_dir(connection, RA_CORES_DIR)

    log(f"Removed {RA_MAIN_BINARY_PATH}\n")
    log(f"Removed {RA_INI_PATH}\n")
    log(f"Removed {RA_SOUND_PATH}\n")
    log(f"Removed {RA_CORES_DIR}\n")
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
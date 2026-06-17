import html
import os
import platform
import re
import shutil
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import requests

from core.config import CONFIG_PATH, save_config

MC_UPDATER_RELEASES_URL = "https://github.com/Anime0t4ku/MC-Updater/releases"
MC_UPDATER_LATEST_URL = "https://github.com/Anime0t4ku/MC-Updater/releases/latest"
MC_UPDATER_EXPANDED_ASSETS_URL = "https://github.com/Anime0t4ku/MC-Updater/releases/expanded_assets"


@dataclass
class MCUpdaterLocalStatus:
    supported: bool
    installed: bool
    installed_version: str
    executable_path: Path


@dataclass
class MCUpdaterReleaseInfo:
    version: str
    download_url: str
    filename: str


@dataclass
class MCUpdaterUpdateStatus:
    supported: bool
    installed: bool
    installed_version: str
    latest_version: str
    update_available: bool
    executable_path: Path


def current_platform_name() -> str:
    return platform.system().lower()


def is_windows() -> bool:
    return current_platform_name() == "windows"


def is_linux() -> bool:
    return current_platform_name() == "linux"


def updater_supported() -> bool:
    return is_windows() or is_linux()


def get_config_folder() -> Path:
    return CONFIG_PATH.resolve().parent


def get_executable_filename() -> str:
    if is_windows():
        return "MC-Updater.exe"
    return "MC-Updater"


def get_executable_path() -> Path:
    return get_config_folder() / get_executable_filename()


def get_expected_asset_filename() -> str:
    if is_windows():
        return "MC-Updater-Windows-x86_64.zip"
    return "MC-Updater-Linux-x86_64.tar.gz"


def _build_release_download_url(version: str, filename: str) -> str:
    return f"https://github.com/Anime0t4ku/MC-Updater/releases/download/{version}/{filename}"


def normalize_version_tuple(version: str) -> tuple[int, int, int]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", str(version or ""))
    if not match:
        return (0, 0, 0)
    return tuple(int(part) for part in match.groups())


def make_executable(path: Path):
    if not path.exists() or not is_linux():
        return
    current_mode = os.stat(path).st_mode
    os.chmod(path, current_mode | 0o100 | 0o010 | 0o001)


def get_local_status(config_data: dict) -> MCUpdaterLocalStatus:
    path = get_executable_path()
    installed = updater_supported() and path.exists()
    version = ""

    if installed:
        version = str(config_data.get("mc_updater_version", "") or "").strip()
        if is_linux():
            make_executable(path)

    return MCUpdaterLocalStatus(
        supported=updater_supported(),
        installed=installed,
        installed_version=version,
        executable_path=path,
    )


def format_local_status_text(config_data: dict) -> str:
    status = get_local_status(config_data)

    if not status.supported:
        return "Status: Unsupported platform"

    if not status.installed:
        return "Status: Not installed"

    if not status.installed_version:
        return "Status: Installed, unknown version"

    return f"Status: Installed, {status.installed_version}"


def _extract_latest_version_from_url(url: str) -> str:
    match = re.search(r"/releases/tag/([^/?#]+)", url)
    if match:
        return html.unescape(match.group(1))
    return ""


def _extract_latest_version_from_html(page: str) -> str:
    patterns = [
        r"/Anime0t4ku/MC-Updater/releases/tag/([^\"'<>]+)",
        r"/releases/tag/([^\"'<>]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, page)
        if match:
            return html.unescape(match.group(1))
    return ""


def _extract_download_links(page: str, version: str) -> list[str]:
    links = []
    pattern = r'href=["\']([^"\']*/Anime0t4ku/MC-Updater/releases/download/[^"\']+)["\']'

    for match in re.finditer(pattern, page):
        link = html.unescape(match.group(1))
        if version and f"/download/{version}/" not in link:
            continue
        full_link = urljoin("https://github.com", link)
        if full_link not in links:
            links.append(full_link)

    pattern = r'(https://github\.com/Anime0t4ku/MC-Updater/releases/download/[^"\'<>\s]+)'
    for match in re.finditer(pattern, page):
        link = html.unescape(match.group(1))
        if version and f"/download/{version}/" not in link:
            continue
        if link not in links:
            links.append(link)

    return links


def _fetch_release_asset_links(version: str, timeout: int) -> list[str]:
    asset_url = f"{MC_UPDATER_EXPANDED_ASSETS_URL}/{version}"
    response = requests.get(
        asset_url,
        timeout=timeout,
        headers={"User-Agent": "MiSTer-Companion-MC-Updater"},
    )
    response.raise_for_status()
    return _extract_download_links(response.text, version)

def _select_asset(download_links: list[str]) -> str:
    expected = get_expected_asset_filename().lower()

    for link in download_links:
        if link.rstrip("/").split("/")[-1].lower() == expected:
            return link

    candidates = []

    for link in download_links:
        lower = link.lower()
        filename = lower.rstrip("/").split("/")[-1]
        if is_windows() and filename.endswith(".zip"):
            score = 1
            if "windows" in filename or "win" in filename:
                score += 10
            if "x86_64" in filename or "amd64" in filename:
                score += 5
            candidates.append((score, link))
        elif is_linux() and filename.endswith(".tar.gz"):
            score = 1
            if "linux" in filename:
                score += 10
            if "x86_64" in filename or "amd64" in filename:
                score += 5
            candidates.append((score, link))

    if not candidates:
        return ""

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def check_latest_release(timeout: int = 15) -> MCUpdaterReleaseInfo:
    if not updater_supported():
        raise RuntimeError("MC-Updater is only supported on Windows and Linux.")

    latest_response = requests.get(
        MC_UPDATER_LATEST_URL,
        timeout=timeout,
        allow_redirects=True,
        headers={"User-Agent": "MiSTer-Companion-MC-Updater"},
    )
    latest_response.raise_for_status()

    latest_url = latest_response.url
    latest_page = latest_response.text
    version = _extract_latest_version_from_url(latest_url)

    if not version:
        version = _extract_latest_version_from_html(latest_page)

    if not version:
        releases_response = requests.get(
            MC_UPDATER_RELEASES_URL,
            timeout=timeout,
            headers={"User-Agent": "MiSTer-Companion-MC-Updater"},
        )
        releases_response.raise_for_status()
        latest_page = releases_response.text
        version = _extract_latest_version_from_html(latest_page)

    if not version:
        raise RuntimeError("Could not determine the latest MC-Updater version.")

    tag_url = f"https://github.com/Anime0t4ku/MC-Updater/releases/tag/{version}"
    tag_response = requests.get(
        tag_url,
        timeout=timeout,
        headers={"User-Agent": "MiSTer-Companion-MC-Updater"},
    )
    tag_response.raise_for_status()

    page = tag_response.text
    links = _extract_download_links(page, version)

    if not links:
        links = _extract_download_links(latest_page, version)

    try:
        expanded_links = _fetch_release_asset_links(version, timeout)
        for link in expanded_links:
            if link not in links:
                links.append(link)
    except Exception:
        pass

    download_url = _select_asset(links)
    if not download_url:
        expected_filename = get_expected_asset_filename()
        download_url = _build_release_download_url(version, expected_filename)

    filename = download_url.rstrip("/").split("/")[-1]
    return MCUpdaterReleaseInfo(version=version, download_url=download_url, filename=filename)


def check_update_status(config_data: dict, timeout: int = 15) -> MCUpdaterUpdateStatus:
    local = get_local_status(config_data)
    release = check_latest_release(timeout=timeout)

    update_available = False
    if local.installed:
        if not local.installed_version:
            update_available = True
        else:
            update_available = normalize_version_tuple(release.version) > normalize_version_tuple(local.installed_version)

    return MCUpdaterUpdateStatus(
        supported=local.supported,
        installed=local.installed,
        installed_version=local.installed_version,
        latest_version=release.version,
        update_available=update_available,
        executable_path=local.executable_path,
    )


def _download_file(url: str, target: Path, progress=None, timeout: int = 30):
    with requests.get(
        url,
        stream=True,
        timeout=timeout,
        headers={"User-Agent": "MiSTer-Companion-MC-Updater"},
    ) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", "0") or "0")
        downloaded = 0
        last_percent = -1

        with open(target, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)

                if progress and total:
                    percent = int(downloaded * 100 / total)
                    if percent != last_percent and percent % 10 == 0:
                        last_percent = percent
                        progress(f"Downloading package... {percent}%")


def _extract_package(package_path: Path, extract_dir: Path):
    lower = package_path.name.lower()

    if lower.endswith(".zip"):
        with zipfile.ZipFile(package_path, "r") as zip_file:
            zip_file.extractall(extract_dir)
        return

    if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        with tarfile.open(package_path, "r:gz") as tar_file:
            tar_file.extractall(extract_dir)
        return

    raise RuntimeError("Unsupported MC-Updater package format.")


def _find_extracted_executable(extract_dir: Path) -> Path:
    filename = get_executable_filename()
    for path in extract_dir.rglob(filename):
        if path.is_file():
            return path
    raise RuntimeError(f"Could not find {filename} in the downloaded package.")


def install_or_update(config_data: dict, progress=None) -> str:
    if not updater_supported():
        raise RuntimeError("MC-Updater is only supported on Windows and Linux.")

    if progress:
        progress("Checking latest release...")
    release = check_latest_release()

    with tempfile.TemporaryDirectory() as temp_root:
        temp_root_path = Path(temp_root)
        package_path = temp_root_path / release.filename
        extract_dir = temp_root_path / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)

        if progress:
            progress("Downloading package...")
        _download_file(release.download_url, package_path, progress=progress)

        if progress:
            progress("Extracting package...")
        _extract_package(package_path, extract_dir)

        extracted_executable = _find_extracted_executable(extract_dir)
        target_path = get_executable_path()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if progress:
            progress(f"Installing {target_path.name}...")
        shutil.copy2(extracted_executable, target_path)

        if is_linux():
            if progress:
                progress("Applying executable permissions...")
            make_executable(target_path)

    if progress:
        progress("Saving installed version...")
    config_data["mc_updater_version"] = release.version
    save_config(config_data)

    if progress:
        progress("Done.")

    return release.version


def remove(config_data: dict, progress=None):
    target_path = get_executable_path()

    if progress:
        progress("Removing executable...")

    if target_path.exists():
        target_path.unlink()

    if progress:
        progress("Clearing saved version...")

    config_data.pop("mc_updater_version", None)
    save_config(config_data)

    if progress:
        progress("Done.")

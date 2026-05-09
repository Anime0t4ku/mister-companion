import glob
import html as html_lib
import posixpath
import re
import shlex
import shutil
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests


MEDIA_FAT_PREFIX = "/media/fat"


def _quote(value: str) -> str:
    return shlex.quote(value)


def _remote_file_exists(sftp, path: str) -> bool:
    try:
        sftp.stat(path)
        return True
    except Exception:
        return False


def _write_remote_bytes(connection, path: str, data: bytes):
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "wb") as remote_file:
            remote_file.write(data)
    finally:
        sftp.close()


def _write_remote_text(connection, path: str, text: str):
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "wb") as remote_file:
            remote_file.write(text.encode("utf-8"))
    finally:
        sftp.close()


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


def _ensure_remote_dir(connection, remote_dir: str):
    connection.run_command(f"mkdir -p {_quote(remote_dir)}")


def _remote_command_success(connection, command: str) -> bool:
    result = connection.run_command(f"{command} >/dev/null 2>&1 && echo OK || echo FAIL")
    return "OK" in (result or "")


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


def _fetch_latest_release_from_html(repo: str, title: str) -> dict:
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
        raise RuntimeError(f"Unable to determine latest {title} version from GitHub.")

    tag_name = unquote(final_url.split(marker, 1)[1].split("?", 1)[0].strip())
    if not tag_name:
        raise RuntimeError(f"Unable to determine latest {title} version from GitHub.")

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

        assets.append(
            {
                "name": name,
                "url": url,
                "size": 0,
            }
        )

    if not assets:
        raise RuntimeError(f"Unable to find downloadable release assets for {title} {tag_name}.")

    return {
        "version": tag_name,
        "release_name": tag_name,
        "assets": assets,
    }


def _select_zip_asset(release: dict, title: str) -> str:
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        url = asset.get("url", "")
        lower_name = name.lower()
        lower_url = url.lower()

        if lower_name.endswith(".zip") or lower_url.endswith(".zip"):
            return url

    raise RuntimeError(f"Unable to find a ZIP asset in the latest {title} release.")


def _fetch_latest_zip_release(repo: str, title: str) -> dict:
    release = _fetch_latest_release_from_html(repo, title)
    zip_url = _select_zip_asset(release, title)

    return {
        "version": release["version"],
        "zip_url": zip_url,
        "release_name": release.get("release_name", release["version"]),
    }


def _normalize_ini_text_for_append(text: str) -> str:
    normalized = text.replace("\r\n", "\n").rstrip("\n")
    if normalized:
        normalized += "\n\n"
    return normalized


def _ensure_startup_line(connection, startup_path: str, line: str) -> bool:
    current = _read_remote_text(connection, startup_path)
    normalized = current.replace("\r\n", "\n")

    existing_lines = [entry.rstrip() for entry in normalized.split("\n") if entry.strip()]
    if line in existing_lines:
        return False

    updated = normalized.rstrip("\n")
    if updated:
        updated += "\n"
    updated += line + "\n"

    _ensure_remote_dir(connection, posixpath.dirname(startup_path))
    _write_remote_text(connection, startup_path, updated)
    return True


def _remove_startup_line(connection, startup_path: str, line: str) -> bool:
    current = _read_remote_text(connection, startup_path)
    if not current:
        return False

    normalized = current.replace("\r\n", "\n")
    original_lines = normalized.split("\n")
    kept_lines = [entry for entry in original_lines if entry.strip() != line]

    if kept_lines == original_lines:
        return False

    updated = "\n".join(kept_lines).rstrip("\n")
    if updated:
        updated += "\n"

    _write_remote_text(connection, startup_path, updated)
    return True


def _remove_if_empty_dir(connection, path: str):
    connection.run_command(
        f"if [ -d {_quote(path)} ] && [ -z \"$(ls -A {_quote(path)} 2>/dev/null)\" ]; then rmdir {_quote(path)}; fi"
    )


def _remove_glob(connection, pattern: str):
    command = (
        f"for f in {pattern}; do "
        f'[ -e "$f" ] && rm -f "$f"; '
        f"done"
    )
    connection.run_command(command)


def _local_path(sd_root: str, remote_path: str) -> Path:
    root = Path(str(sd_root or "")).expanduser()

    if not root.exists() or not root.is_dir():
        raise RuntimeError("Selected Offline SD Card folder does not exist.")

    if not remote_path.startswith(MEDIA_FAT_PREFIX):
        raise RuntimeError(f"Unsupported MiSTer path: {remote_path}")

    relative = remote_path[len(MEDIA_FAT_PREFIX):].lstrip("/")
    return root / relative


def _path_exists_local(sd_root: str, remote_path: str) -> bool:
    try:
        return _local_path(sd_root, remote_path).exists()
    except Exception:
        return False


def _glob_exists_local(sd_root: str, remote_pattern: str) -> bool:
    root = Path(str(sd_root or "")).expanduser()

    if not root.exists() or not root.is_dir():
        return False

    if not remote_pattern.startswith(MEDIA_FAT_PREFIX):
        return False

    relative_pattern = remote_pattern[len(MEDIA_FAT_PREFIX):].lstrip("/")
    local_pattern = str(root / relative_pattern)

    return any(Path(match).exists() for match in glob.glob(local_pattern))


def _ensure_local_dir(sd_root: str, remote_dir: str):
    _local_path(sd_root, remote_dir).mkdir(parents=True, exist_ok=True)


def _read_local_text(sd_root: str, remote_path: str) -> str:
    try:
        path = _local_path(sd_root, remote_path)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _write_local_text(sd_root: str, remote_path: str, text: str):
    path = _local_path(sd_root, remote_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_local_bytes(sd_root: str, remote_path: str, data: bytes):
    path = _local_path(sd_root, remote_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _remove_local_path(sd_root: str, remote_path: str):
    path = _local_path(sd_root, remote_path)

    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()


def _remove_local_glob(sd_root: str, remote_pattern: str):
    root = Path(str(sd_root or "")).expanduser()

    if not root.exists() or not root.is_dir():
        return

    if not remote_pattern.startswith(MEDIA_FAT_PREFIX):
        return

    relative_pattern = remote_pattern[len(MEDIA_FAT_PREFIX):].lstrip("/")
    local_pattern = str(root / relative_pattern)

    for match in glob.glob(local_pattern):
        path = Path(match)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()


def _remove_if_empty_dir_local(sd_root: str, remote_path: str):
    path = _local_path(sd_root, remote_path)

    try:
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    except Exception:
        pass


def _ensure_startup_line_local(sd_root: str, startup_path: str, line: str) -> bool:
    current = _read_local_text(sd_root, startup_path)
    normalized = current.replace("\r\n", "\n")

    existing_lines = [entry.rstrip() for entry in normalized.split("\n") if entry.strip()]
    if line in existing_lines:
        return False

    updated = normalized.rstrip("\n")
    if updated:
        updated += "\n"
    updated += line + "\n"

    _ensure_local_dir(sd_root, posixpath.dirname(startup_path))
    _write_local_text(sd_root, startup_path, updated)
    return True


def _remove_startup_line_local(sd_root: str, startup_path: str, line: str) -> bool:
    current = _read_local_text(sd_root, startup_path)
    if not current:
        return False

    normalized = current.replace("\r\n", "\n")
    original_lines = normalized.split("\n")
    kept_lines = [entry for entry in original_lines if entry.strip() != line]

    if kept_lines == original_lines:
        return False

    updated = "\n".join(kept_lines).rstrip("\n")
    if updated:
        updated += "\n"

    _write_local_text(sd_root, startup_path, updated)
    return True


def _copy_local_file_to_sd(sd_root: str, local_file: str, remote_path: str):
    source = Path(local_file)

    if not source.exists() or not source.is_file():
        raise RuntimeError(f"Selected file does not exist: {local_file}")

    target = _local_path(sd_root, remote_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
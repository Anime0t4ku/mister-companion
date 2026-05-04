import html as html_lib
import posixpath
import re
import shlex
from urllib.parse import unquote, urljoin

import requests


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
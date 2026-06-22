import json
from pathlib import Path

import requests

from core.custom_themes import load_custom_themes, normalize_theme_id, themes_dir, validate_theme_data


THEME_STORE_INDEX_URL = "https://raw.githubusercontent.com/Anime0t4ku/companion-themes/main/index.json"
STORE_MANIFEST_DIR = ".theme_store"
STORE_MANIFEST_FILE = "installed.json"
USER_AGENT = "MiSTer Companion Theme Downloader"


def _request_url(url: str, timeout: int = 15) -> bytes:
    url = str(url or "").strip()
    if not url:
        raise ValueError("No URL was provided.")

    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        response.raise_for_status()
        return response.content
    except requests.exceptions.SSLError as exc:
        raise RuntimeError(
            "Unable to verify the HTTPS certificate for the Theme Downloader. "
            "Please make sure your system certificates are up to date."
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Unable to download Theme Downloader data: {exc}") from exc


def _read_json_url(url: str, timeout: int = 15):
    data = _request_url(url, timeout=timeout)
    return json.loads(data.decode("utf-8"))


def load_store_index(index_url: str = THEME_STORE_INDEX_URL) -> list[dict]:
    data = _read_json_url(index_url)

    if not isinstance(data, dict):
        raise ValueError("Theme store index must contain a JSON object.")

    raw_themes = data.get("themes", [])
    if not isinstance(raw_themes, list):
        raise ValueError("Theme store index does not contain a valid themes list.")

    themes = []
    seen = set()

    for item in raw_themes:
        if not isinstance(item, dict):
            continue

        theme_id = normalize_theme_id(item.get("id"))
        if not theme_id or theme_id in seen:
            continue

        theme_url = str(item.get("theme_url", "")).strip()
        if not theme_url:
            continue

        preview_url = str(item.get("preview_url", "")).strip()
        category = str(item.get("category", "community") or "community").strip().lower()
        if category not in {"official", "community"}:
            category = "community"

        themes.append(
            {
                "id": theme_id,
                "name": str(item.get("name", theme_id)).strip() or theme_id,
                "author": str(item.get("author", "Unknown")).strip() or "Unknown",
                "category": category,
                "date_added": str(item.get("date_added", "")).strip(),
                "theme_url": theme_url,
                "preview_url": preview_url,
            }
        )
        seen.add(theme_id)

    return themes


def theme_store_manifest_path() -> Path:
    folder = themes_dir(create=True) / STORE_MANIFEST_DIR
    folder.mkdir(parents=True, exist_ok=True)
    return folder / STORE_MANIFEST_FILE


def load_store_manifest() -> dict:
    path = theme_store_manifest_path()
    if not path.exists():
        return {"installed": {}}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"installed": {}}

    if not isinstance(data, dict):
        return {"installed": {}}

    installed = data.get("installed", {})
    if not isinstance(installed, dict):
        installed = {}

    return {"installed": installed}


def save_store_manifest(manifest: dict) -> None:
    path = theme_store_manifest_path()
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def theme_file_path(theme_id: str) -> Path:
    return themes_dir(create=True) / f"{normalize_theme_id(theme_id)}.json"


def local_theme_for_id(theme_id: str):
    theme_id = normalize_theme_id(theme_id)
    if not theme_id:
        return None

    themes, _ = load_custom_themes()
    for theme in themes:
        if normalize_theme_id(theme.get("id")) == theme_id:
            return theme

    return None


def is_theme_installed(theme_id: str) -> bool:
    return local_theme_for_id(theme_id) is not None


def is_store_installed(theme_id: str) -> bool:
    theme_id = normalize_theme_id(theme_id)
    manifest = load_store_manifest()
    installed = manifest.get("installed", {})
    return theme_id in installed and is_theme_installed(theme_id)


def download_preview(preview_url: str) -> bytes:
    if not str(preview_url or "").strip():
        return b""
    return _request_url(preview_url, timeout=15)


def install_store_theme(entry: dict) -> Path:
    theme_id = normalize_theme_id(entry.get("id"))
    theme_url = str(entry.get("theme_url", "")).strip()

    if not theme_id:
        raise ValueError("Theme entry is missing an id.")
    if not theme_url:
        raise ValueError("Theme entry is missing a download URL.")
    if is_theme_installed(theme_id) and not is_store_installed(theme_id):
        raise ValueError("A local theme with this id already exists.")

    raw_data = _request_url(theme_url, timeout=20)
    data = json.loads(raw_data.decode("utf-8"))
    theme, error = validate_theme_data(data, Path(f"{theme_id}.json"))

    if error:
        raise ValueError(error)

    downloaded_id = normalize_theme_id(theme.get("id"))
    if downloaded_id != theme_id:
        raise ValueError("Downloaded theme id does not match the store index.")

    destination = theme_file_path(theme_id)
    destination.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest = load_store_manifest()
    installed = manifest.setdefault("installed", {})
    installed[theme_id] = {
        "name": str(entry.get("name", theme_id)).strip() or theme_id,
        "author": str(entry.get("author", "Unknown")).strip() or "Unknown",
        "category": str(entry.get("category", "community")).strip().lower() or "community",
        "date_added": str(entry.get("date_added", "")).strip(),
        "theme_url": theme_url,
        "preview_url": str(entry.get("preview_url", "")).strip(),
    }
    save_store_manifest(manifest)

    return destination


def uninstall_store_theme(theme_id: str) -> bool:
    theme_id = normalize_theme_id(theme_id)
    if not theme_id:
        return False

    manifest = load_store_manifest()
    installed = manifest.get("installed", {})

    if theme_id not in installed:
        raise ValueError("Only themes installed from the Theme Downloader can be uninstalled here.")

    local_theme = local_theme_for_id(theme_id)
    if local_theme:
        path = Path(str(local_theme.get("source", "")))
        if path.exists() and path.parent == themes_dir(create=True):
            path.unlink()

    installed.pop(theme_id, None)
    manifest["installed"] = installed
    save_store_manifest(manifest)
    return True

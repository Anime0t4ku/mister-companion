import json
import re
from pathlib import Path

from core.app_paths import app_base_dir, is_macos_packaged_app, macos_application_support_dir


REQUIRED_FIELDS = ("id", "name", "background", "surface", "accent", "text")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def themes_dir(create: bool = True) -> Path:
    if is_macos_packaged_app():
        path = macos_application_support_dir() / "themes"
    else:
        path = app_base_dir() / "themes"

    if create:
        path.mkdir(parents=True, exist_ok=True)

    return path


def normalize_theme_id(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9_\-]+", "_", value)
    value = value.strip("_")
    return value


def is_valid_color(value) -> bool:
    return bool(HEX_COLOR_RE.match(str(value or "").strip()))


def custom_theme_key(theme_id: str) -> str:
    return f"custom:{normalize_theme_id(theme_id)}"


def is_custom_theme_key(value: str) -> bool:
    return str(value or "").strip().lower().startswith("custom:")


def theme_id_from_key(value: str) -> str:
    value = str(value or "").strip()
    if value.lower().startswith("custom:"):
        value = value.split(":", 1)[1]
    return normalize_theme_id(value)


def validate_theme_data(data, source: Path):
    if not isinstance(data, dict):
        return None, "Theme file must contain a JSON object."

    missing = [field for field in REQUIRED_FIELDS if not str(data.get(field, "")).strip()]
    if missing:
        return None, "Missing required fields: " + ", ".join(missing)

    theme_id = normalize_theme_id(data.get("id"))
    if not theme_id:
        return None, "Theme id is invalid."

    for field in ("background", "surface", "accent", "text"):
        if not is_valid_color(data.get(field)):
            return None, f"{field} must be a #RRGGBB color."

    logo = str(data.get("logo", "")).strip().lower()
    if logo and logo not in {"black", "white"}:
        return None, "logo must be either black or white."

    theme = {
        "id": theme_id,
        "key": custom_theme_key(theme_id),
        "name": str(data.get("name", "")).strip(),
        "author": str(data.get("author", "Unknown")).strip() or "Unknown",
        "background": str(data.get("background")).strip(),
        "surface": str(data.get("surface")).strip(),
        "accent": str(data.get("accent")).strip(),
        "text": str(data.get("text")).strip(),
        "logo": logo,
        "source": str(source),
    }

    for field in ("success", "warning", "error"):
        value = str(data.get(field, "")).strip()
        if value and is_valid_color(value):
            theme[field] = value

    return theme, ""


def load_custom_themes() -> tuple[list[dict], list[dict]]:
    folder = themes_dir(create=True)
    themes = []
    invalid = []
    seen = set()

    for path in sorted(folder.glob("*.json"), key=lambda item: item.name.lower()):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            invalid.append({"file": path.name, "path": str(path), "error": str(e)})
            continue

        theme, error = validate_theme_data(data, path)
        if error:
            invalid.append({"file": path.name, "path": str(path), "error": error})
            continue

        if theme["id"] in seen:
            invalid.append({"file": path.name, "path": str(path), "error": "Duplicate theme id."})
            continue

        seen.add(theme["id"])
        themes.append(theme)

    return themes, invalid


def get_custom_theme(theme_key: str):
    wanted = theme_id_from_key(theme_key)
    if not wanted:
        return None

    themes, _ = load_custom_themes()
    for theme in themes:
        if theme.get("id") == wanted:
            return theme

    return None

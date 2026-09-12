import json
import re
import uuid
from pathlib import Path

from core.app_paths import app_base_dir, is_macos_packaged_app, macos_application_support_dir


REQUIRED_FIELDS = ("id", "name", "background", "surface", "accent", "text")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
THEME_CREATOR_CATEGORY = "theme_creator"
THEME_CREATOR_TYPE = "custom_theme"
THEME_CREATOR_SCHEMA_VERSION = 1
THEME_SYNC_ID_KEY = "sync_id"


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

    category = str(data.get("category", "community")).strip().lower()
    if category not in {"official", "community", THEME_CREATOR_CATEGORY}:
        category = "community"

    companion = data.get("companion") if isinstance(data.get("companion"), dict) else {}

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
        "category": category,
        "companion": dict(companion),
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


def is_theme_creator_theme_data(data) -> bool:
    if not isinstance(data, dict):
        return False
    companion = data.get("companion") if isinstance(data.get("companion"), dict) else {}
    return (
        str(data.get("category") or "").strip().lower() == THEME_CREATOR_CATEGORY
        and str(companion.get("type") or "").strip().lower() == THEME_CREATOR_TYPE
        and str(companion.get("created_with") or "").strip().lower() == "theme_creator"
        and int(companion.get("schema_version") or 0) == THEME_CREATOR_SCHEMA_VERSION
    )

def ensure_theme_creator_sync_id(data: dict) -> str:
    companion = data.setdefault("companion", {})
    value = str(companion.get(THEME_SYNC_ID_KEY) or "").strip().lower()
    try:
        value = str(uuid.UUID(value))
    except Exception:
        value = str(uuid.uuid4())
        companion[THEME_SYNC_ID_KEY] = value
    return value

def theme_creator_files() -> list[tuple[Path, dict]]:
    result = []
    for path in sorted(themes_dir(create=True).glob("*.json"), key=lambda item: item.name.lower()):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if is_theme_creator_theme_data(data):
            ensure_theme_creator_sync_id(data)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            result.append((path, data))
    return result

def save_theme_creator_theme(data: dict, previous_source: str | None = None) -> Path:
    payload = dict(data or {})
    payload["id"] = normalize_theme_id(payload.get("id") or payload.get("name"))
    payload["category"] = THEME_CREATOR_CATEGORY
    companion = payload.get("companion") if isinstance(payload.get("companion"), dict) else {}
    companion.update({
        "type": THEME_CREATOR_TYPE,
        "created_with": "theme_creator",
        "schema_version": THEME_CREATOR_SCHEMA_VERSION,
    })
    payload["companion"] = companion
    ensure_theme_creator_sync_id(payload)
    target = themes_dir(create=True) / f"{payload['id']}.json"
    theme, error = validate_theme_data(payload, target)
    if error:
        raise ValueError(error)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if previous_source:
        old = Path(previous_source)
        if old.exists() and old.resolve() != target.resolve():
            old.unlink()
    return target


def local_theme_ids() -> set[str]:
    """Return IDs claimed by local JSON themes, including legacy/manual files.

    This intentionally looks at the raw id even when the rest of a theme is invalid.
    Patreon delivery must never overwrite a user's existing file/theme by accident.
    """
    result: set[str] = set()
    for path in themes_dir(create=True).glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        theme_id = normalize_theme_id(data.get("id"))
        if theme_id:
            result.add(theme_id)
    return result


def install_patreon_theme(data: dict) -> bool:
    """Install one server-validated Patreon theme if its ID is not already local.

    Existing IDs are deliberately adopted as-is. This preserves themes that users
    previously installed manually from Patreon ZIP files and also avoids replacing
    locally edited copies.
    """
    if not isinstance(data, dict):
        raise ValueError("The Patreon theme payload is invalid.")

    theme_id = normalize_theme_id(data.get("id"))
    if not theme_id:
        raise ValueError("The Patreon theme id is invalid.")

    folder = themes_dir(create=True)
    target = folder / f"{theme_id}.json"
    if theme_id in local_theme_ids() or target.exists():
        return False

    payload = dict(data)
    payload["id"] = theme_id
    theme, error = validate_theme_data(payload, target)
    if error:
        raise ValueError(error)

    # Keep the distributed theme itself untouched apart from normalized id. There
    # is intentionally no local Patreon metadata/tracking file.
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True

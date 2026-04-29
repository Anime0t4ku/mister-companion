import json
import sys
from pathlib import Path


_CURRENT_LANGUAGE = "en"
_TRANSLATIONS = {}
_FALLBACK_TRANSLATIONS = {}


def app_base_path() -> Path:
    """
    Source mode:
        project root

    PyInstaller mode:
        folder of the compiled app/exe
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


def languages_dir() -> Path:
    return app_base_path() / "languages"


def language_file_path(language_code: str) -> Path:
    return languages_dir() / f"{language_code}.json"


def _load_json_file(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

    except Exception:
        pass

    return {}


def _lookup(data: dict, key: str):
    value = data

    for part in key.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None

    return value


def available_languages() -> list[dict]:
    """
    Returns available language files from /languages.

    Each language JSON can optionally contain:

    "_meta": {
        "code": "en",
        "name": "English"
    }

    If _meta is missing, the filename is used.
    """
    result = []

    folder = languages_dir()
    if not folder.exists():
        return [{"code": "en", "name": "English"}]

    for path in sorted(folder.glob("*.json")):
        code = path.stem
        name = code.upper()

        data = _load_json_file(path)
        meta = data.get("_meta", {}) if isinstance(data, dict) else {}

        if isinstance(meta, dict):
            code = meta.get("code", code)
            name = meta.get("name", name)

        result.append({
            "code": code,
            "name": name,
        })

    if not result:
        result.append({"code": "en", "name": "English"})

    return result


def load_language(language_code: str = "en") -> bool:
    """
    Loads a language JSON file from /languages.

    English is always loaded as fallback first.

    Returns:
        True  = requested language loaded
        False = requested language failed, English fallback is active
    """
    global _CURRENT_LANGUAGE, _TRANSLATIONS, _FALLBACK_TRANSLATIONS

    language_code = (language_code or "en").strip() or "en"

    _FALLBACK_TRANSLATIONS = _load_json_file(language_file_path("en"))

    if language_code == "en":
        _TRANSLATIONS = _FALLBACK_TRANSLATIONS.copy()
        _CURRENT_LANGUAGE = "en"
        return True

    requested_translations = _load_json_file(language_file_path(language_code))

    if requested_translations:
        _TRANSLATIONS = requested_translations
        _CURRENT_LANGUAGE = language_code
        return True

    _TRANSLATIONS = _FALLBACK_TRANSLATIONS.copy()
    _CURRENT_LANGUAGE = "en"
    return False


def current_language() -> str:
    return _CURRENT_LANGUAGE


def tr(key: str, default: str | None = None, **kwargs) -> str:
    """
    Translate a dotted key.

    Example:
        tr("tabs.connection")
        tr("status.connected_to", host="192.168.1.100")

    Lookup order:
        1. selected language
        2. English fallback
        3. provided default
        4. dotted key
    """
    value = _lookup(_TRANSLATIONS, key)

    if value is None:
        value = _lookup(_FALLBACK_TRANSLATIONS, key)

    if value is None:
        value = default if default is not None else key

    if not isinstance(value, str):
        value = default if default is not None else key

    if kwargs:
        try:
            value = value.format(**kwargs)
        except Exception:
            pass

    return value
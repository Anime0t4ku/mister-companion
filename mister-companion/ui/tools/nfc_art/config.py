import json
import re
import sys
from pathlib import Path

from core.app_paths import generated_path


PACKAGE_DIR = Path(__file__).resolve().parent
APP_DIR = PACKAGE_DIR.parents[2]
DATA_DIR = generated_path("nfc_art", default_root=APP_DIR)
CONFIG_FILE = DATA_DIR / "config.json"
WEB_IMAGE_DIR = DATA_DIR / "web-images"
WEB_POSTER_DIR = WEB_IMAGE_DIR / "posters"
WEB_LOGO_DIR = WEB_IMAGE_DIR / "logos"
TEMPLATE_DIR = DATA_DIR / "cassette-templates"
SYSTEM_LOGO_DIR = DATA_DIR / "systems_logos"
OUTPUT_DIR = DATA_DIR / "Output"
CARD_OUTPUT_DIR = OUTPUT_DIR / "NFC-Cards"
CASSETTE_OUTPUT_DIR = OUTPUT_DIR / "Cassette-Covers"


def resource_path(relative_path):
    relative = Path(relative_path)
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / "assets" / "nfc_art" / relative
        if bundled.exists():
            return str(bundled)
    return str(APP_DIR / "assets" / "nfc_art" / relative)


def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', '', name or '')
    return re.sub(r'\s+', ' ', name).strip() or 'nfc_art'


def load_config():
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def get_value(key, default=None):
    return load_config().get(key, default)


def set_value(key, value):
    data = load_config()
    if value is None:
        data.pop(key, None)
    else:
        data[key] = value
    save_config(data)


def load_api_key(service='steamgriddb'):
    return get_value(f'{service}_api_key')


def save_api_key(key, service='steamgriddb'):
    set_value(f'{service}_api_key', key or None)


def _configured_folder(key, default):
    value = get_value(key)
    return str(Path(value).expanduser()) if value else str(default)


def load_card_output_dir():
    return _configured_folder('card_output_directory', CARD_OUTPUT_DIR)


def save_card_output_dir(path):
    set_value('card_output_directory', path)


def load_cassette_output_dir():
    return _configured_folder('cassette_output_directory', CASSETTE_OUTPUT_DIR)


def save_cassette_output_dir(path):
    set_value('cassette_output_directory', path)


def output_images_dir(output_dir):
    return Path(output_dir) / 'Images'


def output_pdfs_dir(output_dir):
    return Path(output_dir) / 'Print-PDFs'


def load_output_dir():
    """Compatibility alias for older NFC Card integrations."""
    return load_card_output_dir()


def save_output_dir(path):
    save_card_output_dir(path)


def load_icon_pack_dir():
    path = Path(_configured_folder('icon_pack_directory', SYSTEM_LOGO_DIR))
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def save_icon_pack_dir(path):
    set_value('icon_pack_directory', path)


def load_cache_posters():
    return bool(get_value('cache_web_posters', False))


def save_cache_posters(value):
    set_value('cache_web_posters', bool(value))


def load_cache_logos():
    return bool(get_value('cache_web_logos', False))


def save_cache_logos(value):
    set_value('cache_web_logos', bool(value))


def load_search_cached_logos():
    return bool(get_value('search_cached_web_logos', False))


def save_search_cached_logos(value):
    set_value('search_cached_web_logos', bool(value))

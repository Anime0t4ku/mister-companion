import json
import re
import shutil
import sys
from pathlib import Path

from core.app_paths import app_base_dir, generated_path
from core.config import load_config as load_app_config, save_config as save_app_config


PACKAGE_DIR = Path(__file__).resolve().parent
APP_DIR = PACKAGE_DIR.parents[2]
DATA_DIR = generated_path("tools", "nfc_art")
WEB_IMAGE_DIR = DATA_DIR / "web-images"
WEB_POSTER_DIR = WEB_IMAGE_DIR / "posters"
WEB_LOGO_DIR = WEB_IMAGE_DIR / "logos"
TEMPLATE_DIR = DATA_DIR / "cassette-templates"
SYSTEM_LOGO_DIR = DATA_DIR / "systems_logos"
OUTPUT_DIR = DATA_DIR / "Output"
CARD_OUTPUT_DIR = OUTPUT_DIR / "NFC-Cards"
CASSETTE_OUTPUT_DIR = OUTPUT_DIR / "Cassette-Covers"

NFC_CONFIG_KEY = "nfc_art"
MIGRATION_VERSION = 1
MIGRATION_KEY = "_migration_version"


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


def _legacy_data_dirs():
    candidates = []

    # The integrated generator previously kept its own nfc_art folder at the
    # application root. Include both the normal persistent application root
    # and the historical module-derived root so source/older working layouts
    # can migrate cleanly.
    for path in (
        generated_path("nfc_art"),
        app_base_dir() / "nfc_art",
        generated_path("nfc_art", default_root=APP_DIR),
    ):
        path = Path(path)
        if path == DATA_DIR or path in candidates:
            continue
        candidates.append(path)

    return candidates


def _copy_missing_tree(source, destination):
    if not source.is_dir():
        return

    for source_path in source.rglob("*"):
        relative = source_path.relative_to(source)
        destination_path = destination / relative

        if source_path.is_dir():
            destination_path.mkdir(parents=True, exist_ok=True)
            continue

        if destination_path.exists():
            continue

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source_path, destination_path)
        except OSError:
            pass


def _remap_legacy_default_path(value, legacy_root):
    if not value:
        return value

    try:
        original = Path(value).expanduser()
        relative = original.resolve(strict=False).relative_to(legacy_root.resolve(strict=False))
    except (OSError, ValueError):
        return value

    return str(DATA_DIR / relative)


def _read_legacy_config(legacy_root):
    config_file = legacy_root / "config.json"
    try:
        with config_file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None

    return data if isinstance(data, dict) else None


def _migrate_legacy_state():
    app_config = load_app_config()
    current = app_config.get(NFC_CONFIG_KEY)
    if isinstance(current, dict) and int(current.get(MIGRATION_KEY, 0) or 0) >= MIGRATION_VERSION:
        return

    nfc_config = dict(current) if isinstance(current, dict) else {}
    legacy_dirs = _legacy_data_dirs()

    # Import legacy settings only when the new section does not already have
    # those keys. Custom paths remain untouched; paths that pointed into the
    # old default nfc_art folder are redirected to tools/nfc_art.
    for legacy_root in legacy_dirs:
        legacy_config = _read_legacy_config(legacy_root)
        if isinstance(legacy_config, dict):
            for key, value in legacy_config.items():
                if key in nfc_config:
                    continue
                if key in {
                    "card_output_directory",
                    "cassette_output_directory",
                    "icon_pack_directory",
                }:
                    value = _remap_legacy_default_path(value, legacy_root)
                nfc_config[key] = value

        # Preserve outputs, cached artwork, custom logos and cassette
        # templates without overwriting anything already in the new layout.
        _copy_missing_tree(legacy_root, DATA_DIR)

    nfc_config[MIGRATION_KEY] = MIGRATION_VERSION
    app_config[NFC_CONFIG_KEY] = nfc_config
    save_app_config(app_config)


def load_config():
    _migrate_legacy_state()
    data = load_app_config().get(NFC_CONFIG_KEY, {})
    return dict(data) if isinstance(data, dict) else {}


def save_config(data):
    _migrate_legacy_state()
    app_config = load_app_config()
    section = dict(data) if isinstance(data, dict) else {}
    section[MIGRATION_KEY] = MIGRATION_VERSION
    app_config[NFC_CONFIG_KEY] = section
    save_app_config(app_config)


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

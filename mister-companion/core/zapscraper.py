import binascii
import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from core.screenscraper_private import get_dev_credentials
from core.zapscraper_systems import (
    DISC_HELPER_EXTENSIONS,
    OUTPUT_FORMAT_RECALBOX,
    OUTPUT_FORMAT_ZAPAROO_COMPANION,
    REGION_TAGS,
    SUPPORTED_SYSTEMS,
    get_default_zaparoo_companion_media_names,
    get_image_source_folder,
    get_image_source_id,
    get_image_source_media_type,
    get_output_format_id,
    get_region_code,
    get_zaparoo_companion_media_folder,
    get_zaparoo_companion_media_names,
    get_zaparoo_companion_media_node,
    get_zaparoo_companion_media_type,
    is_supported_rom,
)


CACHE_FILENAME = ".zapscraper_cache.json"
GAMELIST_FILENAME = "gamelist.xml"
SCREENSCRAPER_API_BASE = "https://api.screenscraper.fr/api2"

REQUEST_TIMEOUT = 30
REQUEST_DELAY_SECONDS = 1.5


SCAN_CACHE_VERSION = 1


_last_screenscraper_request_at = 0.0


class ScreenScraperQuotaError(RuntimeError):
    pass


def _wait_for_screenscraper_rate_limit():
    global _last_screenscraper_request_at

    now = time.monotonic()
    elapsed = now - _last_screenscraper_request_at

    if elapsed < REQUEST_DELAY_SECONDS:
        time.sleep(REQUEST_DELAY_SECONDS - elapsed)

    _last_screenscraper_request_at = time.monotonic()


def _walk_values(value: Any):
    if isinstance(value, dict):
        yield value

        for item in value.values():
            yield from _walk_values(item)

    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item)


def _first_present_int(data: dict[str, Any], names: set[str]) -> int | None:
    wanted = {str(name).lower() for name in names}

    for container in _walk_values(data):
        for key, value in container.items():
            key_l = str(key).lower()

            if key_l not in wanted:
                continue

            try:
                text = str(value).strip()
                if not text:
                    continue

                digits = re.sub(r"[^\d-]", "", text)
                if not digits:
                    continue

                return int(digits)
            except Exception:
                continue

    return None


def _first_present_text(data: dict[str, Any], names: set[str]) -> str:
    wanted = {str(name).lower() for name in names}

    for container in _walk_values(data):
        for key, value in container.items():
            key_l = str(key).lower()

            if key_l not in wanted:
                continue

            text = str(value or "").strip()
            if text:
                return text

    return ""


def extract_screenscraper_quota_info(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}

    daily_used = _first_present_int(
        data,
        {
            "requeststoday",
            "requestsday",
            "request_today",
            "requests_today",
            "usedrequeststoday",
            "usedrequestsday",
            "usedtoday",
            "used_day",
            "apiusedtoday",
            "nbscrapetoday",
            "nbscrapeursjour",
        },
    )

    daily_limit = _first_present_int(
        data,
        {
            "maxrequestsperday",
            "maxrequestsday",
            "requestslimitday",
            "requestsdaymax",
            "dailymax",
            "daily_limit",
            "maxday",
            "maxrequetesjour",
            "maxrequests",
        },
    )

    daily_remaining = _first_present_int(
        data,
        {
            "requestsremaining",
            "requestsremainingday",
            "remainingrequests",
            "remainingrequestsday",
            "requestsleft",
            "requestsleftday",
            "remainingday",
            "quota_remaining",
            "dayremaining",
        },
    )

    minute_used = _first_present_int(
        data,
        {
            "requestsminute",
            "requestsperminute",
            "usedrequestsminute",
            "used_minute",
            "minuterequests",
        },
    )

    minute_limit = _first_present_int(
        data,
        {
            "maxrequestsperminute",
            "maxrequestsminute",
            "requestslimitminute",
            "minute_limit",
            "maxminute",
        },
    )

    threads = _first_present_int(
        data,
        {
            "maxthreads",
            "threads",
            "nbscrapeurs",
            "maxthread",
        },
    )

    username = _first_present_text(
        data,
        {
            "pseudo",
            "ssid",
            "username",
            "nom",
            "user",
        },
    )

    if daily_remaining is None and daily_used is not None and daily_limit is not None:
        daily_remaining = max(0, daily_limit - daily_used)

    quota = {}

    if username:
        quota["username"] = username

    if daily_used is not None:
        quota["daily_used"] = daily_used

    if daily_limit is not None:
        quota["daily_limit"] = daily_limit

    if daily_remaining is not None:
        quota["daily_remaining"] = daily_remaining

    if minute_used is not None:
        quota["minute_used"] = minute_used

    if minute_limit is not None:
        quota["minute_limit"] = minute_limit

    if threads is not None:
        quota["threads"] = threads

    if quota:
        quota["updated_at"] = datetime.now().isoformat(timespec="seconds")

    return quota


def format_screenscraper_quota_info(quota: dict[str, Any]) -> str:
    if not isinstance(quota, dict) or not quota:
        return "Quota: not reported by ScreenScraper."

    daily_used = quota.get("daily_used")
    daily_limit = quota.get("daily_limit")
    daily_remaining = quota.get("daily_remaining")
    minute_used = quota.get("minute_used")
    minute_limit = quota.get("minute_limit")
    parts = []

    if daily_used is not None and daily_limit is not None:
        parts.append(f"Daily quota: {daily_used} / {daily_limit} used")
    elif daily_remaining is not None:
        parts.append(f"Daily quota: {daily_remaining} requests remaining")
    elif daily_used is not None:
        parts.append(f"Daily quota: {daily_used} requests used today")
    elif daily_limit is not None:
        parts.append(f"Daily quota limit: {daily_limit}")

    if minute_used is not None and minute_limit is not None:
        parts.append(f"Minute quota: {minute_used} / {minute_limit} used")
    elif minute_limit is not None:
        parts.append(f"Minute quota limit: {minute_limit}")

    return " | ".join(parts) if parts else "Quota: not reported by ScreenScraper."


def _looks_like_quota_error(message: str) -> bool:
    text = str(message or "").lower()

    quota_terms = (
        "quota",
        "rate limit",
        "ratelimit",
        "too many",
        "trop de",
        "limite",
        "limit",
        "maximum",
        "max requests",
        "request limit",
        "daily",
        "minute",
        "overquota",
        "threads",
        "nbscrapeurs",
        "not allowed",
        "forbidden",
    )

    return any(term in text for term in quota_terms)



def get_application_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        executable = getattr(sys, "executable", "")
        if executable:
            return Path(executable).resolve().parent

    return Path(__file__).resolve().parent.parent


def get_scan_cache_dir() -> Path:
    cache_dir = get_application_base_dir() / "scrapecache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _normalize_source_mode(source_mode: str = "") -> str:
    return str(source_mode or "").strip()


def _source_is_custom_games_folder(source_mode: str = "") -> bool:
    value = _normalize_source_mode(source_mode).lower()
    return "custom" in value and "folder" in value


def scan_cache_games_location(source_mode: str, source_path: str | Path) -> str:
    source_path = str(source_path or "").strip()

    if not source_path:
        return ""

    try:
        path = Path(source_path).expanduser()
    except Exception:
        return source_path

    if _source_is_custom_games_folder(source_mode):
        return str(path)

    return str(path / "games")


def _normalized_cache_location_key(source_mode: str, source_path: str | Path) -> str:
    location = scan_cache_games_location(source_mode, source_path)

    if not location:
        return ""

    value = str(location).replace("\\", "/").rstrip("/").lower()
    return value


def get_scan_cache_key(source_mode: str, source_path: str | Path) -> str:
    key_source = _normalized_cache_location_key(source_mode, source_path)

    if not key_source:
        return ""

    return hashlib.sha1(key_source.encode("utf-8", errors="ignore")).hexdigest()


def get_scan_cache_path(source_mode: str, source_path: str | Path) -> Path:
    cache_key = get_scan_cache_key(source_mode, source_path)

    if not cache_key:
        raise RuntimeError("Cannot create scan cache path without a source location.")

    return get_scan_cache_dir() / f"{cache_key}.zapscraper_scan.json"


def scan_cache_exists(source_mode: str, source_path: str | Path) -> bool:
    try:
        return get_scan_cache_path(source_mode, source_path).exists()
    except Exception:
        return False


def load_scan_cache(source_mode: str, source_path: str | Path) -> dict[str, Any]:
    try:
        cache_path = get_scan_cache_path(source_mode, source_path)
    except Exception:
        return {}

    if not cache_path.exists():
        return {}

    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    expected_location = scan_cache_games_location(source_mode, source_path)
    cached_location = str(data.get("games_location", "")).strip()

    if expected_location and cached_location:
        expected_key = _normalized_cache_location_key(source_mode, source_path)
        cached_key = str(cached_location).replace("\\", "/").rstrip("/").lower()

        if expected_key != cached_key:
            return {}

    systems = data.get("systems")
    if not isinstance(systems, list):
        return {}

    return data


def load_scan_cache_systems(source_mode: str, source_path: str | Path) -> list[dict[str, Any]]:
    data = load_scan_cache(source_mode, source_path)

    systems = data.get("systems") if isinstance(data, dict) else None
    if not isinstance(systems, list):
        return []

    return [system for system in systems if isinstance(system, dict)]


def save_scan_cache(
    source_mode: str,
    source_path: str | Path,
    systems: list[dict[str, Any]],
) -> Path:
    cache_path = get_scan_cache_path(source_mode, source_path)
    games_location = scan_cache_games_location(source_mode, source_path)

    data = {
        "version": SCAN_CACHE_VERSION,
        "source_mode": _normalize_source_mode(source_mode),
        "source_path": str(source_path or "").strip(),
        "games_location": games_location,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "systems": systems or [],
    }

    with cache_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)

    return cache_path


def clear_scan_cache(source_mode: str, source_path: str | Path) -> bool:
    try:
        cache_path = get_scan_cache_path(source_mode, source_path)
    except Exception:
        return False

    if not cache_path.exists():
        return False

    try:
        cache_path.unlink()
        return True
    except Exception:
        return False




def normalize_output_format(output_format: str = "") -> str:
    value = str(output_format or "").strip()

    if value in {OUTPUT_FORMAT_RECALBOX, OUTPUT_FORMAT_ZAPAROO_COMPANION}:
        return value

    return get_output_format_id(value)


def normalize_zaparoo_media_source_names(media_source_names=None) -> list[str]:
    available = set(get_zaparoo_companion_media_names())

    if not media_source_names:
        return get_default_zaparoo_companion_media_names()

    result = []

    for name in media_source_names:
        name = str(name or "").strip()
        if name in available and name not in result:
            result.append(name)

    return result or get_default_zaparoo_companion_media_names()


@dataclass
class ZapScraperRom:
    path: Path
    relative_path: str
    filename: str
    stem: str
    size: int


@dataclass
class ZapScraperSystem:
    folder: str
    label: str
    path: Path
    screenscraper_id: int
    roms: list[ZapScraperRom] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.roms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "folder": self.folder,
            "label": self.label,
            "path": str(self.path),
            "screenscraper_id": self.screenscraper_id,
            "count": self.count,
            "roms": [
                {
                    "path": str(rom.path),
                    "relative_path": rom.relative_path,
                    "filename": rom.filename,
                    "stem": rom.stem,
                    "size": rom.size,
                }
                for rom in self.roms
            ],
        }


def scan_sd_card(
    sd_root: str | Path,
    progress_callback=None,
    stop_checker=None,
) -> list[dict[str, Any]]:
    sd_root = Path(sd_root)

    if not sd_root.exists():
        raise RuntimeError("Selected SD card path does not exist.")

    games_root = sd_root / "games"
    return scan_games_folder(
        games_root,
        progress_callback=progress_callback,
        stop_checker=stop_checker,
    )


def scan_games_folder(
    games_root: str | Path,
    progress_callback=None,
    stop_checker=None,
) -> list[dict[str, Any]]:
    games_root = Path(games_root)

    if not games_root.exists():
        raise RuntimeError("Selected games folder does not exist.")

    if not games_root.is_dir():
        raise RuntimeError("Selected games folder is not a folder.")

    systems: list[ZapScraperSystem] = []
    total_games_found = 0
    supported_items = list(SUPPORTED_SYSTEMS.items())

    if callable(progress_callback):
        progress_callback(
            "Starting scan...",
            0,
            len(supported_items),
            0,
        )

    for system_index, (folder_name, info) in enumerate(supported_items, start=1):
        if callable(stop_checker) and stop_checker():
            break

        system_path = games_root / folder_name
        label = info.get("label", folder_name)

        if callable(progress_callback):
            progress_callback(
                f"Checking {label}...",
                system_index,
                len(supported_items),
                total_games_found,
            )

        if not system_path.exists() or not system_path.is_dir():
            continue

        roms = scan_system_folder(
            system_path,
            folder_name,
            progress_callback=progress_callback,
            stop_checker=stop_checker,
            system_index=system_index,
            system_total=len(supported_items),
            games_found_before=total_games_found,
            system_label=label,
        )

        if callable(stop_checker) and stop_checker():
            break

        if not roms:
            continue

        total_games_found += len(roms)

        if callable(progress_callback):
            progress_callback(
                f"Found {len(roms)} games in {label}.",
                system_index,
                len(supported_items),
                total_games_found,
            )

        systems.append(
            ZapScraperSystem(
                folder=folder_name,
                label=label,
                path=system_path,
                screenscraper_id=int(info.get("screenscraper_id", 0)),
                roms=roms,
            )
        )

    if callable(progress_callback):
        progress_callback(
            "Scan complete.",
            len(supported_items),
            len(supported_items),
            total_games_found,
        )

    return [system.to_dict() for system in systems]


def scan_system_folder(
    system_path: Path,
    system_folder: str,
    progress_callback=None,
    stop_checker=None,
    system_index: int = 0,
    system_total: int = 0,
    games_found_before: int = 0,
    system_label: str = "",
) -> list[ZapScraperRom]:
    roms: list[ZapScraperRom] = []
    checked_files = 0
    last_reported_folder = ""

    for path in system_path.rglob("*"):
        if callable(stop_checker) and stop_checker():
            break

        if not path.is_file():
            continue

        checked_files += 1

        if checked_files == 1 or checked_files % 100 == 0:
            current_folder = str(path.parent)

            if current_folder != last_reported_folder or checked_files % 250 == 0:
                last_reported_folder = current_folder

                if callable(progress_callback):
                    total_games_found = games_found_before + len(roms)
                    label = system_label or system_folder
                    progress_callback(
                        f"Scanning {label}: {len(roms)} games found, {checked_files} files checked...",
                        system_index,
                        system_total,
                        total_games_found,
                    )

        if path.name == GAMELIST_FILENAME:
            continue

        if _is_inside_media_folder(path):
            continue

        if not is_supported_rom(system_folder, path):
            continue

        if path.suffix.lower() in DISC_HELPER_EXTENSIONS and _has_matching_cue(path):
            continue

        try:
            size = path.stat().st_size
        except Exception:
            size = 0

        roms.append(
            ZapScraperRom(
                path=path,
                relative_path=to_recalbox_relative_path(path, system_path),
                filename=path.name,
                stem=path.stem,
                size=size,
            )
        )

        if callable(progress_callback) and len(roms) % 25 == 0:
            total_games_found = games_found_before + len(roms)
            label = system_label or system_folder
            progress_callback(
                f"Scanning {label}: {len(roms)} games found...",
                system_index,
                system_total,
                total_games_found,
            )

    roms.sort(key=lambda item: item.relative_path.lower())
    return roms


def _is_inside_media_folder(path: Path) -> bool:
    return any(part.lower() == "media" for part in path.parts)


def _has_matching_cue(path: Path) -> bool:
    try:
        return path.with_suffix(".cue").exists()
    except Exception:
        return False


def to_recalbox_relative_path(path: Path, system_path: Path) -> str:
    try:
        rel = path.relative_to(system_path)
        value = rel.as_posix()
    except Exception:
        value = path.name

    return f"./{value}"


def detect_region_from_filename(filename: str, selected_region: str = "Auto") -> str:
    selected_code = get_region_code(selected_region)

    if selected_code != "auto":
        return selected_code

    upper_name = filename.upper()

    tags = re.findall(r"[\(\[\{]([^\)\]\}]+)[\)\]\}]", upper_name)

    for tag in tags:
        parts = re.split(r"[,/|+\-_\s]+", tag)

        for part in parts:
            clean = part.strip().upper()
            if clean in REGION_TAGS:
                return REGION_TAGS[clean]

    if "USA" in upper_name:
        return "us"

    if "JAPAN" in upper_name:
        return "jp"

    if "EUROPE" in upper_name:
        return "eu"

    return "auto"


def load_zapscraper_cache(system_path: str | Path) -> dict[str, Any]:
    cache_path = Path(system_path) / CACHE_FILENAME

    if not cache_path.exists():
        return {}

    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def save_zapscraper_cache(system_path: str | Path, cache: dict[str, Any]):
    cache_path = Path(system_path) / CACHE_FILENAME

    try:
        with cache_path.open("w", encoding="utf-8") as handle:
            json.dump(cache, handle, indent=2, ensure_ascii=False)
    except Exception:
        pass


def load_gamelist(system_path: str | Path) -> ET.ElementTree:
    gamelist_path = Path(system_path) / GAMELIST_FILENAME

    if gamelist_path.exists():
        try:
            tree = ET.parse(gamelist_path)
            root = tree.getroot()

            if root.tag != "gameList":
                raise RuntimeError("Invalid gamelist root.")

            return tree
        except Exception:
            pass

    root = ET.Element("gameList")
    return ET.ElementTree(root)


def save_gamelist(system_path: str | Path, tree: ET.ElementTree):
    gamelist_path = Path(system_path) / GAMELIST_FILENAME
    indent_xml(tree.getroot())

    tree.write(
        gamelist_path,
        encoding="utf-8",
        xml_declaration=True,
    )


def indent_xml(element: ET.Element, level: int = 0):
    indent = "\n" + level * "  "

    if len(element):
        if not element.text or not element.text.strip():
            element.text = indent + "  "

        last_child = None

        for child in element:
            indent_xml(child, level + 1)
            last_child = child

        if last_child is not None and (not last_child.tail or not last_child.tail.strip()):
            last_child.tail = indent
    else:
        if level and (not element.tail or not element.tail.strip()):
            element.tail = indent


def get_game_entries_by_path(tree: ET.ElementTree) -> dict[str, ET.Element]:
    root = tree.getroot()
    entries: dict[str, ET.Element] = {}

    for game in root.findall("game"):
        path_node = game.find("path")

        if path_node is None or not path_node.text:
            continue

        entries[path_node.text.strip()] = game

    return entries


def game_has_metadata(game: ET.Element | None) -> bool:
    if game is None:
        return False

    meaningful_fields = [
        "name",
        "desc",
        "developer",
        "publisher",
        "genre",
        "releasedate",
        "players",
        "rating",
    ]

    for field_name in meaningful_fields:
        node = game.find(field_name)
        if node is not None and node.text and node.text.strip():
            return True

    return False


def get_or_create_game_entry(tree: ET.ElementTree, relative_path: str) -> ET.Element:
    entries = get_game_entries_by_path(tree)

    if relative_path in entries:
        return entries[relative_path]

    root = tree.getroot()
    game = ET.SubElement(root, "game")
    set_child_text(game, "path", relative_path)
    return game


def set_child_text(parent: ET.Element, tag: str, value: Any):
    if value is None:
        return

    text = str(value).strip()

    if not text:
        return

    child = parent.find(tag)

    if child is None:
        child = ET.SubElement(parent, tag)

    child.text = text


def update_game_metadata(
    game: ET.Element,
    metadata: dict[str, Any],
    skip_existing_metadata: bool = True,
):
    if skip_existing_metadata and game_has_metadata(game):
        return

    game_id = metadata.get("id")
    if game_id:
        game.set("id", str(game_id))

    source = metadata.get("source") or "ScreenScraper"
    game.set("source", str(source))

    field_map = {
        "name": "name",
        "description": "desc",
        "desc": "desc",
        "rating": "rating",
        "releasedate": "releasedate",
        "developer": "developer",
        "publisher": "publisher",
        "genre": "genre",
        "players": "players",
        "region": "region",
    }

    for source_key, xml_key in field_map.items():
        if source_key in metadata:
            set_child_text(game, xml_key, metadata.get(source_key))


def build_local_image_path(
    system_path: str | Path,
    rom_filename: str,
    image_source_name: str,
    extension: str = ".png",
) -> tuple[Path, str]:
    system_path = Path(system_path)
    image_folder = get_image_source_folder(image_source_name)
    media_dir = system_path / image_folder
    safe_name = safe_media_filename(Path(rom_filename).stem)
    image_path = media_dir / f"{safe_name}{extension}"

    relative = f"./{image_folder}/{image_path.name}"
    return image_path, relative


def safe_media_filename(name: str) -> str:
    name = str(name or "").strip()
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name)
    name = name.strip(" .")

    if not name:
        name = "unknown"

    return name


def update_game_image(game: ET.Element, image_relative_path: str):
    set_child_text(game, "image", image_relative_path)


def cache_entry_needs_image_update(
    cache: dict[str, Any],
    relative_path: str,
    selected_image_source: str,
) -> bool:
    image_source_id = get_image_source_id(selected_image_source)
    entry = cache.get(relative_path)

    if not isinstance(entry, dict):
        return True

    return entry.get("image_source") != image_source_id


def update_cache_entry(
    cache: dict[str, Any],
    relative_path: str,
    *,
    screenscraper_id: str | int | None = None,
    metadata_scraped: bool = False,
    image_source_name: str = "",
    image_path: str = "",
    region: str = "",
):
    entry = cache.get(relative_path)

    if not isinstance(entry, dict):
        entry = {}

    if screenscraper_id:
        entry["screenscraper_id"] = str(screenscraper_id)

    if metadata_scraped:
        entry["metadata_scraped"] = True

    if image_source_name:
        entry["image_source"] = get_image_source_id(image_source_name)

    if image_path:
        entry["image_path"] = image_path

    if region:
        entry["region"] = region

    cache[relative_path] = entry


def plan_scrape_actions(
    system: dict[str, Any],
    image_source_name: str,
    skip_existing_metadata: bool = True,
    skip_existing_images: bool = True,
    update_changed_images: bool = True,
) -> list[dict[str, Any]]:
    system_path = Path(system["path"])
    tree = load_gamelist(system_path)
    entries = get_game_entries_by_path(tree)
    cache = load_zapscraper_cache(system_path)

    actions = []

    for rom in system.get("roms", []):
        relative_path = rom.get("relative_path") or to_recalbox_relative_path(
            Path(rom["path"]),
            system_path,
        )

        game = entries.get(relative_path)
        has_metadata = game_has_metadata(game)

        needs_metadata = not has_metadata or not skip_existing_metadata

        image_path, image_relative_path = build_local_image_path(
            system_path,
            rom.get("filename") or Path(rom["path"]).name,
            image_source_name,
        )

        image_exists = image_path.exists()
        image_source_changed = cache_entry_needs_image_update(
            cache,
            relative_path,
            image_source_name,
        )

        needs_image = True

        if skip_existing_images and image_exists and not image_source_changed:
            needs_image = False

        if image_source_changed and update_changed_images:
            needs_image = True

        if not needs_metadata and not needs_image:
            continue

        actions.append(
            {
                "system_folder": system.get("folder"),
                "system_label": system.get("label"),
                "system_path": str(system_path),
                "screenscraper_system_id": system.get("screenscraper_id"),
                "rom": rom,
                "relative_path": relative_path,
                "needs_metadata": needs_metadata,
                "needs_image": needs_image,
                "image_path": str(image_path),
                "image_relative_path": image_relative_path,
                "image_source_changed": image_source_changed,
            }
        )

    return actions


def apply_scrape_result(
    system_path: str | Path,
    relative_path: str,
    metadata: dict[str, Any],
    image_relative_path: str = "",
    image_source_name: str = "",
    region: str = "",
    skip_existing_metadata: bool = True,
):
    system_path = Path(system_path)
    tree = load_gamelist(system_path)
    cache = load_zapscraper_cache(system_path)

    game = get_or_create_game_entry(tree, relative_path)

    update_game_metadata(
        game,
        metadata,
        skip_existing_metadata=skip_existing_metadata,
    )

    if image_relative_path:
        update_game_image(game, image_relative_path)

    update_cache_entry(
        cache,
        relative_path,
        screenscraper_id=metadata.get("id"),
        metadata_scraped=True,
        image_source_name=image_source_name,
        image_path=image_relative_path,
        region=region,
    )

    save_gamelist(system_path, tree)
    save_zapscraper_cache(system_path, cache)


def create_placeholder_metadata_from_rom(rom: dict[str, Any], region: str = "") -> dict[str, Any]:
    name = Path(rom.get("filename", "")).stem
    name = clean_rom_display_name(name)

    metadata = {
        "source": "ZapScraper",
        "name": name,
    }

    if region and region != "auto":
        metadata["region"] = region

    return metadata


def clean_rom_display_name(name: str) -> str:
    value = str(name or "")

    value = re.sub(r"\([^)]*\)", "", value)
    value = re.sub(r"\[[^\]]*\]", "", value)
    value = re.sub(r"\{[^}]*\}", "", value)
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" -_.")

    return value or str(name or "Unknown Game")


def _common_screenscraper_params(username: str, password: str) -> dict[str, str]:
    dev_credentials = get_dev_credentials()

    if not dev_credentials:
        raise RuntimeError("ScreenScraper developer credentials are missing in this build.")

    username = str(username or "").strip()
    password = str(password or "")

    if not username or not password:
        raise RuntimeError("ScreenScraper username and password are required.")

    return {
        "devid": str(dev_credentials.get("devid", "")),
        "devpassword": str(dev_credentials.get("devpassword", "")),
        "softname": str(dev_credentials.get("softname", "mister-companion")),
        "ssid": username,
        "sspassword": password,
        "output": "json",
    }


def _screenscraper_get_json(
    endpoint: str,
    params: dict[str, Any],
    timeout: int = REQUEST_TIMEOUT,
    quota_callback=None,
) -> dict[str, Any]:
    url = f"{SCREENSCRAPER_API_BASE}/{endpoint}"

    _wait_for_screenscraper_rate_limit()

    response = requests.get(url, params=params, timeout=timeout)

    if response.status_code in {403, 429}:
        raise ScreenScraperQuotaError(
            "ScreenScraper quota or rate limit reached. Please wait before scraping again."
        )

    response.raise_for_status()

    try:
        data = response.json()
    except Exception as e:
        raise RuntimeError(f"ScreenScraper returned an invalid response: {e}")

    if not isinstance(data, dict):
        raise RuntimeError("ScreenScraper returned an unexpected response.")

    _raise_for_screenscraper_error(data)

    quota = extract_screenscraper_quota_info(data)
    if quota:
        data["_zapscraper_quota"] = quota
        if callable(quota_callback):
            quota_callback(quota)

    return data


def _raise_for_screenscraper_error(data: dict[str, Any]):
    header = data.get("header")

    if isinstance(header, dict):
        success = str(header.get("success", "")).lower()
        error = header.get("error") or header.get("message")

        if success in {"false", "0", "ko"}:
            message = str(error or "ScreenScraper request failed.")
            if _looks_like_quota_error(message):
                raise ScreenScraperQuotaError(message)
            raise RuntimeError(message)

    response = data.get("response")

    if isinstance(response, dict):
        error = response.get("erreur") or response.get("error")

        if error:
            message = str(error)
            if _looks_like_quota_error(message):
                raise ScreenScraperQuotaError(message)
            raise RuntimeError(message)


def test_screenscraper_login(username: str, password: str, quota_callback=None) -> dict[str, Any]:
    params = _common_screenscraper_params(username, password)
    data = _screenscraper_get_json("ssuserInfos.php", params, quota_callback=quota_callback)


    user_info = extract_user_info(data)
    quota = data.get("_zapscraper_quota") or extract_screenscraper_quota_info(data)

    return {
        "ok": True,
        "message": build_user_info_message(user_info, quota),
        "user": user_info,
        "quota": quota,
        "raw": data,
    }


def extract_user_info(data: dict[str, Any]) -> dict[str, Any]:
    response = data.get("response")

    if not isinstance(response, dict):
        return {}

    possible_keys = [
        "ssuser",
        "user",
        "joueur",
    ]

    for key in possible_keys:
        value = response.get(key)
        if isinstance(value, dict):
            return value

    return response


def build_user_info_message(user_info: dict[str, Any], quota: dict[str, Any] | None = None) -> str:
    if not user_info:
        return "Login OK."

    username = (
        user_info.get("pseudo")
        or user_info.get("ssid")
        or user_info.get("username")
        or user_info.get("nom")
        or ""
    )

    level = (
        user_info.get("niveau")
        or user_info.get("level")
        or user_info.get("niveauid")
        or ""
    )


    quota_day = (
        user_info.get("requeststoday")
        or user_info.get("requestsday")
        or user_info.get("maxrequestsperday")
        or ""
    )

    parts = ["Login OK"]

    if username:
        parts.append(f"User: {username}")

    if level:
        parts.append(f"Level: {level}")

    if quota_day:
        parts.append(f"Quota: {quota_day}")

    quota_message = format_screenscraper_quota_info(quota or {})
    if quota_message and "not reported" not in quota_message.lower():
        parts.append(quota_message)

    return " | ".join(parts)


def calculate_rom_hashes(path: str | Path) -> dict[str, str]:
    path = Path(path)

    crc = 0
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)

            if not chunk:
                break

            crc = binascii.crc32(chunk, crc)
            md5.update(chunk)
            sha1.update(chunk)

    return {
        "crc": f"{crc & 0xFFFFFFFF:08X}",
        "md5": md5.hexdigest(),
        "sha1": sha1.hexdigest(),
    }


def fetch_game_info(
    *,
    username: str,
    password: str,
    rom_path: str | Path,
    rom_filename: str,
    rom_size: int,
    system_id: int,
    quota_callback=None,
) -> dict[str, Any]:
    params = _common_screenscraper_params(username, password)

    hashes = calculate_rom_hashes(rom_path)

    params.update(
        {
            "systemeid": str(system_id),
            "romtype": "rom",
            "romnom": rom_filename,
            "romtaille": str(rom_size),
            "crc": hashes["crc"],
            "md5": hashes["md5"],
            "sha1": hashes["sha1"],
        }
    )

    return _screenscraper_get_json("jeuInfos.php", params, quota_callback=quota_callback)


def extract_game_from_response(data: dict[str, Any]) -> dict[str, Any]:
    response = data.get("response")

    if not isinstance(response, dict):
        return {}

    game = response.get("jeu")

    if isinstance(game, dict):
        return game

    game = response.get("game")

    if isinstance(game, dict):
        return game

    return response


def extract_metadata_from_game(
    game: dict[str, Any],
    *,
    region_code: str = "auto",
) -> dict[str, Any]:
    if not isinstance(game, dict):
        return {}

    game_id = game.get("id") or game.get("idjeu") or game.get("idGame")

    name = (
        pick_localized_text(game.get("noms"), region_code)
        or pick_localized_text(game.get("names"), region_code)
        or game.get("nom")
        or game.get("name")
        or ""
    )

    description = (
        pick_localized_text(game.get("synopsis"), region_code)
        or pick_localized_text(game.get("descriptions"), region_code)
        or game.get("synopsis")
        or game.get("desc")
        or ""
    )

    developer = pick_simple_text(game.get("developpeur")) or pick_simple_text(game.get("developer"))
    publisher = pick_simple_text(game.get("editeur")) or pick_simple_text(game.get("publisher"))
    genre = pick_localized_text(game.get("genres"), region_code) or pick_simple_text(game.get("genre"))
    players = pick_simple_text(game.get("joueurs")) or pick_simple_text(game.get("players"))
    rating = normalize_rating(game.get("note") or game.get("rating"))
    releasedate = normalize_recalbox_date(
        pick_localized_date(game.get("dates"), region_code)
        or game.get("date")
        or game.get("releasedate")
    )

    metadata = {
        "source": "ScreenScraper",
    }

    if game_id:
        metadata["id"] = game_id

    if name:
        metadata["name"] = name

    if description:
        metadata["description"] = description

    if developer:
        metadata["developer"] = developer

    if publisher:
        metadata["publisher"] = publisher

    if genre:
        metadata["genre"] = genre

    if players:
        metadata["players"] = players

    if rating:
        metadata["rating"] = rating

    if releasedate:
        metadata["releasedate"] = releasedate

    if region_code and region_code != "auto":
        metadata["region"] = region_code

    return metadata


def pick_simple_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, int | float):
        return str(value)

    if isinstance(value, dict):
        for key in ("text", "nom", "name", "value"):
            item = value.get(key)
            if item:
                return str(item).strip()

    if isinstance(value, list):
        for item in value:
            text = pick_simple_text(item)
            if text:
                return text

    return ""


def pick_localized_text(value: Any, region_code: str = "auto") -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        for key in ("text", "nom", "name", "value"):
            item = value.get(key)
            if item:
                return str(item).strip()

        for key in ("us", "eu", "jp", "wor", "ss", "default"):
            item = value.get(key)
            if item:
                return str(item).strip()

    if isinstance(value, list):
        preferred = _region_priority(region_code)

        for region in preferred:
            for item in value:
                if not isinstance(item, dict):
                    continue

                item_region = str(
                    item.get("region")
                    or item.get("regionshortname")
                    or item.get("zone")
                    or ""
                ).lower()

                if item_region == region:
                    text = pick_simple_text(item)
                    if text:
                        return text

        for item in value:
            text = pick_simple_text(item)
            if text:
                return text

    return ""


def pick_localized_date(value: Any, region_code: str = "auto") -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        for key in ("text", "date", "value"):
            item = value.get(key)
            if item:
                return str(item).strip()

    if isinstance(value, list):
        preferred = _region_priority(region_code)

        for region in preferred:
            for item in value:
                if not isinstance(item, dict):
                    continue

                item_region = str(
                    item.get("region")
                    or item.get("regionshortname")
                    or item.get("zone")
                    or ""
                ).lower()

                if item_region == region:
                    date = item.get("text") or item.get("date") or item.get("value")
                    if date:
                        return str(date).strip()

        for item in value:
            date = pick_localized_date(item, region_code)
            if date:
                return date

    return ""


def _region_priority(region_code: str) -> list[str]:
    region_code = str(region_code or "auto").lower()

    if region_code == "us":
        return ["us", "wor", "eu", "jp"]

    if region_code == "jp":
        return ["jp", "wor", "us", "eu"]

    if region_code == "eu":
        return ["eu", "wor", "us", "jp"]

    return ["wor", "us", "eu", "jp"]


def normalize_rating(value: Any) -> str:
    if value is None:
        return ""

    try:
        rating = float(str(value).replace(",", "."))
    except Exception:
        return ""

    if rating > 1:
        rating = rating / 20.0 if rating > 5 else rating / 5.0

    rating = max(0.0, min(1.0, rating))
    return f"{rating:.2f}"


def normalize_recalbox_date(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    digits = re.sub(r"\D", "", text)

    if len(digits) >= 8:
        return f"{digits[:8]}T000000"

    if len(digits) == 6:
        return f"{digits[:4]}{digits[4:6]}01T000000"

    if len(digits) == 4:
        return f"{digits}0101T000000"

    return ""


def select_media_url(
    game: dict[str, Any],
    *,
    image_source_name: str,
    region_code: str = "auto",
) -> str:
    media_type = get_image_source_media_type(image_source_name)
    medias = game.get("medias") or game.get("media")

    if not isinstance(medias, list):
        return ""

    preferred_regions = _region_priority(region_code)

    candidates = []

    for media in medias:
        if not isinstance(media, dict):
            continue

        item_type = str(media.get("type") or media.get("media_type") or "").strip()

        if item_type != media_type:
            continue

        url = (
            media.get("url")
            or media.get("urlmax")
            or media.get("urlzoom")
            or media.get("urlmed")
            or media.get("urlmin")
        )

        if not url:
            continue

        item_region = str(
            media.get("region")
            or media.get("regionshortname")
            or media.get("zone")
            or ""
        ).lower()

        candidates.append(
            {
                "url": str(url),
                "region": item_region,
            }
        )

    if not candidates:
        return ""

    for region in preferred_regions:
        for candidate in candidates:
            if candidate["region"] == region:
                return candidate["url"]

    return candidates[0]["url"]


def guess_image_extension(url: str, content_type: str = "") -> str:
    content_type = str(content_type or "").lower()

    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"

    if "png" in content_type:
        return ".png"

    if "webp" in content_type:
        return ".webp"

    parsed = urlparse(str(url or ""))
    suffix = Path(parsed.path).suffix.lower()

    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix

    return ".png"


def download_image(url: str, target_path: str | Path):
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    target_path.write_bytes(response.content)


def _media_type_candidates(media_type: str) -> set[str]:
    media_type = str(media_type or "").strip()

    if not media_type:
        return set()

    normalized = media_type.lower()
    candidates = {normalized}

    aliases = {
        "ss": {"ss", "screenshot", "screen", "snap"},
        "sstitle": {"sstitle", "ss-title", "ss_title", "titlescreen", "title-screen", "title_screen"},
        "box-2d": {"box-2d", "box-2D", "box2d", "box_2d", "box", "boxart2d", "boxart-2d"},
        "box-3d": {"box-3d", "box-3D", "box3d", "box_3d", "boxart3d", "boxart-3d"},
        "wheel": {"wheel", "logo", "logos"},
    }

    if normalized in aliases:
        candidates.update(item.lower() for item in aliases[normalized])

    for key, values in aliases.items():
        lowered = {item.lower() for item in values}
        if normalized in lowered:
            candidates.add(key)
            candidates.update(lowered)

    return candidates


def select_media_url_by_media_type(
    game: dict[str, Any],
    *,
    media_type: str,
    region_code: str = "auto",
) -> str:
    media_type_names = _media_type_candidates(media_type)

    if not media_type_names:
        return ""

    medias = game.get("medias") or game.get("media")

    if not isinstance(medias, list):
        return ""

    preferred_regions = _region_priority(region_code)
    candidates = []

    for media in medias:
        if not isinstance(media, dict):
            continue

        item_type = str(media.get("type") or media.get("media_type") or "").strip().lower()

        if item_type not in media_type_names:
            continue

        url = (
            media.get("url")
            or media.get("urlmax")
            or media.get("urlzoom")
            or media.get("urlmed")
            or media.get("urlmin")
        )

        if not url:
            continue

        item_region = str(
            media.get("region")
            or media.get("regionshortname")
            or media.get("zone")
            or ""
        ).lower()

        candidates.append(
            {
                "url": str(url),
                "region": item_region,
            }
        )

    if not candidates:
        return ""

    for region in preferred_regions:
        for candidate in candidates:
            if candidate["region"] == region:
                return candidate["url"]

    return candidates[0]["url"]



def build_zaparoo_companion_media_path(
    system_path: str | Path,
    screenscraper_id: str | int,
    media_source_name: str,
    extension: str = ".png",
) -> tuple[Path, str]:
    system_path = Path(system_path)
    media_folder = get_zaparoo_companion_media_folder(media_source_name)

    if not media_folder:
        media_folder = "media/zaparoo"

    safe_id = safe_media_filename(str(screenscraper_id or "unknown"))
    media_dir = system_path / media_folder
    media_path = media_dir / f"{safe_id}{extension}"

    return media_path, f"./{media_folder}/{media_path.name}"


def find_zaparoo_parent_entry(root: ET.Element, screenscraper_id: str | int) -> ET.Element | None:
    screenscraper_id = str(screenscraper_id or "").strip()

    if not screenscraper_id:
        return None

    for game in root.findall("game"):
        if game.get("id") == screenscraper_id and game.get("source") == "ZaparooCompanion":
            return game

    return None


def get_or_create_zaparoo_parent_entry(tree: ET.ElementTree, screenscraper_id: str | int) -> ET.Element:
    root = tree.getroot()
    parent = find_zaparoo_parent_entry(root, screenscraper_id)

    if parent is not None:
        return parent

    parent = ET.SubElement(root, "game")
    parent.set("id", str(screenscraper_id))
    parent.set("source", "ZaparooCompanion")
    return parent


def get_or_create_zaparoo_child_entry(
    tree: ET.ElementTree,
    relative_path: str,
    parent_id: str | int,
) -> ET.Element:
    entries = get_game_entries_by_path(tree)
    child = entries.get(relative_path)

    if child is None:
        child = ET.SubElement(tree.getroot(), "game")
        set_child_text(child, "path", relative_path)

    child.set("parentid", str(parent_id))
    child.set("source", "ZaparooCompanion")

    for tag in (
        "name",
        "desc",
        "rating",
        "releasedate",
        "developer",
        "publisher",
        "genre",
        "players",
        "image",
        "thumbnail",
        "marquee",
        "wheel",
        "screenshot",
        "titlescreen",
        "boxart2d",
        "boxart3d",
        "logo",
    ):
        node = child.find(tag)
        if node is not None:
            child.remove(node)

    return child


def update_zaparoo_parent_metadata(parent: ET.Element, metadata: dict[str, Any]):
    parent.set("source", "ZaparooCompanion")

    game_id = metadata.get("id")
    if game_id:
        parent.set("id", str(game_id))

    field_map = {
        "name": "name",
        "description": "desc",
        "desc": "desc",
        "rating": "rating",
        "releasedate": "releasedate",
        "developer": "developer",
        "publisher": "publisher",
        "genre": "genre",
        "players": "players",
    }

    for source_key, xml_key in field_map.items():
        if source_key in metadata:
            set_child_text(parent, xml_key, metadata.get(source_key))


def download_zaparoo_companion_media_assets(
    *,
    system_path: str | Path,
    parent: ET.Element,
    game: dict[str, Any],
    screenscraper_id: str | int,
    region_code: str,
    media_source_names=None,
) -> dict[str, str]:
    media_source_names = normalize_zaparoo_media_source_names(media_source_names)
    downloaded: dict[str, str] = {}

    for media_source_name in media_source_names:
        media_type = get_zaparoo_companion_media_type(media_source_name)
        xml_node = get_zaparoo_companion_media_node(media_source_name)

        if not media_type or not xml_node:
            continue

        media_url = select_media_url_by_media_type(
            game,
            media_type=media_type,
            region_code=region_code,
        )

        if not media_url:
            continue

        extension = guess_image_extension(media_url)
        media_path, media_relative_path = build_zaparoo_companion_media_path(
            system_path,
            screenscraper_id,
            media_source_name,
            extension=extension,
        )

        if not media_path.exists():
            download_image(media_url, media_path)

        set_child_text(parent, xml_node, media_relative_path)
        downloaded[xml_node] = media_relative_path

    return downloaded


def apply_zaparoo_companion_scrape_result(
    *,
    system_path: str | Path,
    relative_path: str,
    rom: dict[str, Any],
    game: dict[str, Any],
    metadata: dict[str, Any],
    region: str = "",
    media_source_names=None,
    quota_callback=None,
) -> dict[str, Any]:
    system_path = Path(system_path)
    tree = load_gamelist(system_path)
    cache = load_zapscraper_cache(system_path)

    screenscraper_id = metadata.get("id")

    if not screenscraper_id:
        screenscraper_id = rom.get("screenscraper_id") or safe_media_filename(relative_path)
        metadata["id"] = screenscraper_id

    parent = get_or_create_zaparoo_parent_entry(tree, screenscraper_id)
    update_zaparoo_parent_metadata(parent, metadata)

    media_paths = download_zaparoo_companion_media_assets(
        system_path=system_path,
        parent=parent,
        game=game,
        screenscraper_id=screenscraper_id,
        region_code=region,
        media_source_names=media_source_names,
    )

    child = get_or_create_zaparoo_child_entry(tree, relative_path, screenscraper_id)

    if region and region != "auto":
        set_child_text(child, "region", region)

        if region == "jp":
            set_child_text(child, "lang", "jp")
        elif region == "us":
            set_child_text(child, "lang", "en")
        elif region == "eu":
            set_child_text(child, "lang", "en")

    update_cache_entry(
        cache,
        relative_path,
        screenscraper_id=screenscraper_id,
        metadata_scraped=True,
        image_source_name="Zaparoo Companion",
        image_path=next(iter(media_paths.values()), ""),
        region=region,
    )

    save_gamelist(system_path, tree)
    save_zapscraper_cache(system_path, cache)

    return {
        "screenscraper_id": str(screenscraper_id),
        "media_paths": media_paths,
        "region": region,
    }


def process_scrape_action(
    action: dict[str, Any],
    *,
    username: str,
    password: str,
    image_source_name: str,
    selected_region: str,
    skip_existing_metadata: bool = True,
    output_format: str = OUTPUT_FORMAT_RECALBOX,
    zaparoo_media_source_names=None,
    quota_callback=None,
) -> dict[str, Any]:
    rom = action.get("rom") or {}
    rom_path = Path(rom.get("path", ""))
    rom_filename = rom.get("filename") or rom_path.name
    rom_size = int(rom.get("size") or 0)
    system_id = int(action.get("screenscraper_system_id") or 0)
    output_format = normalize_output_format(output_format)

    if not rom_path.exists():
        raise RuntimeError(f"ROM not found: {rom_filename}")

    if not system_id:
        raise RuntimeError(f"Missing ScreenScraper system ID for {rom_filename}")

    if output_format == OUTPUT_FORMAT_ZAPAROO_COMPANION:
        region_code = get_region_code(selected_region)
        if region_code == "auto":
            region_code = "us"
    else:
        region_code = detect_region_from_filename(rom_filename, selected_region)

    data = fetch_game_info(
        username=username,
        password=password,
        rom_path=rom_path,
        rom_filename=rom_filename,
        rom_size=rom_size,
        system_id=system_id,
        quota_callback=quota_callback,
    )

    game = extract_game_from_response(data)
    metadata = extract_metadata_from_game(game, region_code=region_code)

    if not metadata:
        metadata = create_placeholder_metadata_from_rom(rom, region_code)

    if output_format == OUTPUT_FORMAT_ZAPAROO_COMPANION:
        zaparoo_result = apply_zaparoo_companion_scrape_result(
            system_path=action.get("system_path"),
            relative_path=action.get("relative_path"),
            rom=rom,
            game=game,
            metadata=metadata,
            region=region_code,
            media_source_names=zaparoo_media_source_names,
        )

        return {
            "metadata": metadata,
            "image_relative_path": "",
            "region": region_code,
            "output_format": output_format,
            "zaparoo": zaparoo_result,
        }

    image_relative_path = ""

    if action.get("needs_image"):
        image_url = select_media_url(
            game,
            image_source_name=image_source_name,
            region_code=region_code,
        )

        if image_url:
            extension = guess_image_extension(image_url)
            image_path, image_relative_path = build_local_image_path(
                action.get("system_path"),
                rom_filename,
                image_source_name,
                extension=extension,
            )
            download_image(image_url, image_path)
        else:
            existing_image_relative = action.get("image_relative_path", "")
            image_relative_path = existing_image_relative if Path(action.get("image_path", "")).exists() else ""

    apply_scrape_result(
        action.get("system_path"),
        action.get("relative_path"),
        metadata,
        image_relative_path=image_relative_path,
        image_source_name=image_source_name,
        region=region_code,
        skip_existing_metadata=skip_existing_metadata,
    )

    return {
        "metadata": metadata,
        "image_relative_path": image_relative_path,
        "region": region_code,
        "output_format": output_format,
    }



def run_scrape_actions(
    actions: list[dict[str, Any]],
    *,
    username: str,
    password: str,
    image_source_name: str,
    selected_region: str,
    skip_existing_metadata: bool = True,
    output_format: str = OUTPUT_FORMAT_RECALBOX,
    zaparoo_media_source_names=None,
    progress_callback=None,
    log_callback=None,
    quota_callback=None,
    stop_checker=None,
):
    total = len(actions)
    output_format = normalize_output_format(output_format)

    if callable(log_callback):
        if output_format == OUTPUT_FORMAT_ZAPAROO_COMPANION:
            media_names = normalize_zaparoo_media_source_names(zaparoo_media_source_names)
            log_callback(
                "Output format: Zaparoo Companion Experimental. "
                f"Media: {', '.join(media_names)}. Requests are single-threaded and rate-limited."
            )
        else:
            log_callback("Output format: Recalbox Compatible. ScreenScraper requests are single-threaded and rate-limited.")

    for index, action in enumerate(actions, start=1):
        if callable(stop_checker) and stop_checker():
            if callable(log_callback):
                log_callback("Scrape stopped by user.")
            break

        rom = action.get("rom") or {}
        rom_filename = rom.get("filename") or Path(rom.get("path", "")).name
        system_label = action.get("system_label") or action.get("system_folder") or "Unknown"

        if callable(log_callback):
            log_callback(f"[{index}/{total}] {system_label}: {rom_filename}")

        try:
            process_scrape_action(
                action,
                username=username,
                password=password,
                image_source_name=image_source_name,
                selected_region=selected_region,
                skip_existing_metadata=skip_existing_metadata,
                output_format=output_format,
                zaparoo_media_source_names=zaparoo_media_source_names,
                quota_callback=quota_callback,
            )

            if callable(log_callback):
                log_callback(f"Done: {rom_filename}")
        except ScreenScraperQuotaError as e:
            if callable(log_callback):
                log_callback(f"ScreenScraper quota/rate limit reached: {e}")
                log_callback("Scrape stopped to avoid exceeding ScreenScraper limits.")
            break
        except Exception as e:
            if callable(log_callback):
                log_callback(f"Failed: {rom_filename} - {e}")

        if callable(progress_callback):
            progress_callback(index, total, rom_filename)

        time.sleep(REQUEST_DELAY_SECONDS)


def get_zaparoo_parent_entries_by_id(tree: ET.ElementTree) -> dict[str, ET.Element]:
    root = tree.getroot()
    parents: dict[str, ET.Element] = {}

    for game in root.findall("game"):
        if game.get("source") != "ZaparooCompanion":
            continue

        game_id = str(game.get("id") or "").strip()
        parent_id = str(game.get("parentid") or "").strip()

        if game_id and not parent_id:
            parents[game_id] = game

    return parents


def get_zaparoo_child_entries_by_path(tree: ET.ElementTree) -> dict[str, ET.Element]:
    root = tree.getroot()
    children: dict[str, ET.Element] = {}

    for game in root.findall("game"):
        if game.get("source") != "ZaparooCompanion":
            continue

        parent_id = str(game.get("parentid") or "").strip()
        if not parent_id:
            continue

        path_value = _child_text(game, "path")
        if not path_value:
            continue

        children[path_value] = game

    return children


def zaparoo_parent_entry_to_dict(parent: ET.Element | None, system_path: str | Path) -> dict[str, Any]:
    if parent is None:
        return {}

    media = {}
    media_paths = {}
    media_exists = {}

    for media_name in get_zaparoo_companion_media_names():
        xml_node = get_zaparoo_companion_media_node(media_name)
        if not xml_node:
            continue

        value = _child_text(parent, xml_node)
        resolved_path = _resolve_gamelist_image_path(system_path, value) if value else ""
        exists = bool(resolved_path and Path(resolved_path).exists())

        media[media_name] = value
        media_paths[media_name] = resolved_path
        media_exists[media_name] = exists

    return {
        "id": str(parent.get("id") or ""),
        "source": str(parent.get("source") or ""),
        "name": _child_text(parent, "name"),
        "desc": _child_text(parent, "desc"),
        "rating": _child_text(parent, "rating"),
        "releasedate": _child_text(parent, "releasedate"),
        "developer": _child_text(parent, "developer"),
        "publisher": _child_text(parent, "publisher"),
        "genre": _child_text(parent, "genre"),
        "players": _child_text(parent, "players"),
        "media": media,
        "media_paths": media_paths,
        "media_exists": media_exists,
        "has_metadata": game_has_metadata(parent),
    }


def zaparoo_child_entry_to_dict(child: ET.Element | None) -> dict[str, Any]:
    if child is None:
        return {}

    return {
        "path": _child_text(child, "path"),
        "parentid": str(child.get("parentid") or ""),
        "source": str(child.get("source") or ""),
        "region": _child_text(child, "region"),
        "lang": _child_text(child, "lang"),
    }


def _zaparoo_parent_missing_media(
    parent_data: dict[str, Any],
    media_source_names=None,
) -> list[str]:
    media_source_names = normalize_zaparoo_media_source_names(media_source_names)
    media_exists = parent_data.get("media_exists") if isinstance(parent_data, dict) else {}

    if not isinstance(media_exists, dict):
        media_exists = {}

    missing = []

    for media_name in media_source_names:
        if not media_exists.get(media_name):
            missing.append(media_name)

    return missing


def build_zaparoo_companion_review_items(
    system: dict[str, Any],
    media_source_names=None,
) -> list[dict[str, Any]]:
    system_path = Path(system.get("path", ""))
    tree = load_gamelist(system_path)

    parents = get_zaparoo_parent_entries_by_id(tree)
    children = get_zaparoo_child_entries_by_path(tree)
    media_source_names = normalize_zaparoo_media_source_names(media_source_names)

    items: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for rom in system.get("roms", []):
        relative_path = rom.get("relative_path") or to_recalbox_relative_path(
            Path(rom.get("path", "")),
            system_path,
        )

        child = children.get(relative_path)
        child_data = zaparoo_child_entry_to_dict(child)
        parent_id = child_data.get("parentid", "")
        parent = parents.get(parent_id)
        parent_data = zaparoo_parent_entry_to_dict(parent, system_path) if parent is not None else {}

        missing_media = _zaparoo_parent_missing_media(parent_data, media_source_names)

        if not child or not parent_id or parent is None:
            status = "unmatched"
            status_label = "Unmatched"
            display_name = clean_rom_display_name(Path(rom.get("filename", "")).stem) or rom.get("filename") or relative_path
            matched_name = ""
        elif missing_media:
            status = "missing_media"
            status_label = "Missing Media"
            display_name = parent_data.get("name") or clean_rom_display_name(Path(rom.get("filename", "")).stem) or rom.get("filename") or relative_path
            matched_name = parent_data.get("name", "")
        else:
            status = "matched"
            status_label = "Matched"
            display_name = parent_data.get("name") or clean_rom_display_name(Path(rom.get("filename", "")).stem) or rom.get("filename") or relative_path
            matched_name = parent_data.get("name", "")

        items.append(
            {
                "status": status,
                "status_label": status_label,
                "display_name": display_name,
                "matched_name": matched_name,
                "relative_path": relative_path,
                "rom": rom,
                "child": child_data,
                "parent": parent_data,
                "parent_id": parent_id,
                "missing_media": missing_media,
                "media_source_names": media_source_names,
                "system_path": str(system_path),
                "system_folder": system.get("folder", ""),
                "system_label": system.get("label", ""),
                "screenscraper_system_id": system.get("screenscraper_id", 0),
                "is_in_gamelist": child is not None,
            }
        )

        seen_paths.add(relative_path)

    for relative_path, child in children.items():
        if relative_path in seen_paths:
            continue

        child_data = zaparoo_child_entry_to_dict(child)
        parent_id = child_data.get("parentid", "")
        parent = parents.get(parent_id)
        parent_data = zaparoo_parent_entry_to_dict(parent, system_path) if parent is not None else {}
        missing_media = _zaparoo_parent_missing_media(parent_data, media_source_names)

        if not parent_id or parent is None:
            status = "unmatched"
            status_label = "Unmatched"
        elif missing_media:
            status = "missing_media"
            status_label = "Missing Media"
        else:
            status = "matched"
            status_label = "Matched"

        items.append(
            {
                "status": status,
                "status_label": status_label,
                "display_name": parent_data.get("name") or relative_path,
                "matched_name": parent_data.get("name", ""),
                "relative_path": relative_path,
                "rom": {},
                "child": child_data,
                "parent": parent_data,
                "parent_id": parent_id,
                "missing_media": missing_media,
                "media_source_names": media_source_names,
                "system_path": str(system_path),
                "system_folder": system.get("folder", ""),
                "system_label": system.get("label", ""),
                "screenscraper_system_id": system.get("screenscraper_id", 0),
                "is_in_gamelist": True,
            }
        )

    status_order = {
        "unmatched": 0,
        "missing_media": 1,
        "matched": 2,
    }

    items.sort(
        key=lambda item: (
            status_order.get(str(item.get("status", "")), 99),
            str(item.get("display_name", "")).lower(),
        )
    )

    return items


def default_zaparoo_manual_search_text(item: dict[str, Any]) -> str:
    parent = item.get("parent") if isinstance(item, dict) else {}
    rom = item.get("rom") if isinstance(item, dict) else {}

    if isinstance(parent, dict) and parent.get("name"):
        return str(parent.get("name") or "").strip()

    if isinstance(rom, dict):
        filename = rom.get("filename") or Path(str(rom.get("path") or "")).name
        if filename:
            return clean_rom_display_name(Path(filename).stem)

    return clean_rom_display_name(Path(str(item.get("relative_path", ""))).stem)


def apply_zaparoo_manual_match_result(
    *,
    system_path: str | Path,
    relative_path: str,
    rom: dict[str, Any],
    selected_result: dict[str, Any],
    username: str,
    password: str,
    selected_region: str,
    system_id: int,
    media_source_names=None,
    quota_callback=None,
) -> dict[str, Any]:
    raw_game = selected_result.get("raw") if isinstance(selected_result, dict) else {}
    game_id = selected_result.get("id") if isinstance(selected_result, dict) else ""

    game = raw_game if isinstance(raw_game, dict) else {}

    if game_id:
        try:
            data = fetch_game_info_by_id(
                username=username,
                password=password,
                game_id=game_id,
                system_id=system_id,
                quota_callback=quota_callback,
            )
            fetched_game = extract_game_from_response(data)
            if fetched_game:
                game = fetched_game
        except Exception:
            pass

    region_code = get_region_code(selected_region)
    if region_code == "auto":
        region_code = "us"

    metadata = extract_metadata_from_game(game, region_code=region_code)

    if not metadata and isinstance(selected_result, dict):
        metadata = dict(selected_result.get("metadata") or {})

    if not metadata:
        metadata = create_placeholder_metadata_from_rom(rom, region_code)

    if game_id and not metadata.get("id"):
        metadata["id"] = game_id

    if not metadata.get("source"):
        metadata["source"] = "ScreenScraper"

    result = apply_zaparoo_companion_scrape_result(
        system_path=system_path,
        relative_path=relative_path,
        rom=rom,
        game=game,
        metadata=metadata,
        region=region_code,
        media_source_names=media_source_names,
    )

    return {
        "metadata": metadata,
        "matched_name": metadata.get("name") or selected_result.get("name") or "",
        "screenscraper_id": result.get("screenscraper_id", ""),
        "media_paths": result.get("media_paths", {}),
        "region": region_code,
        "zaparoo": result,
    }



def _child_text(parent: ET.Element | None, tag: str) -> str:
    if parent is None:
        return ""

    child = parent.find(tag)

    if child is None or child.text is None:
        return ""

    return child.text.strip()


def _resolve_gamelist_image_path(system_path: str | Path, image_value: str) -> str:
    image_value = str(image_value or "").strip()

    if not image_value:
        return ""

    if image_value.startswith(("http://", "https://")):
        return image_value

    system_path = Path(system_path)

    if image_value.startswith("./"):
        return str(system_path / image_value[2:])

    image_path = Path(image_value)

    if image_path.is_absolute:
        return str(image_path)

    return str(system_path / image_value)


def gamelist_entry_to_dict(game: ET.Element, system_path: str | Path) -> dict[str, Any]:
    image_value = _child_text(game, "image")

    return {
        "path": _child_text(game, "path"),
        "name": _child_text(game, "name"),
        "desc": _child_text(game, "desc"),
        "image": image_value,
        "image_path": _resolve_gamelist_image_path(system_path, image_value),
        "rating": _child_text(game, "rating"),
        "releasedate": _child_text(game, "releasedate"),
        "developer": _child_text(game, "developer"),
        "publisher": _child_text(game, "publisher"),
        "genre": _child_text(game, "genre"),
        "players": _child_text(game, "players"),
        "region": _child_text(game, "region"),
        "id": game.get("id", ""),
        "source": game.get("source", ""),
        "has_metadata": game_has_metadata(game),
        "has_image": bool(image_value),
    }


def build_gamelist_review_items(system: dict[str, Any]) -> list[dict[str, Any]]:
    system_path = Path(system.get("path", ""))
    tree = load_gamelist(system_path)
    entries = get_game_entries_by_path(tree)

    items: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for rom in system.get("roms", []):
        relative_path = rom.get("relative_path") or to_recalbox_relative_path(
            Path(rom.get("path", "")),
            system_path,
        )

        game = entries.get(relative_path)
        entry = gamelist_entry_to_dict(game, system_path) if game is not None else {}

        has_metadata = bool(entry.get("has_metadata"))
        image_path = entry.get("image_path", "")
        has_image = bool(image_path and Path(image_path).exists())

        if has_metadata and has_image:
            status = "complete"
        elif has_metadata:
            status = "missing_image"
        else:
            status = "missing_metadata"

        display_name = (
            entry.get("name")
            or clean_rom_display_name(Path(rom.get("filename", "")).stem)
            or rom.get("filename")
            or relative_path
        )

        items.append(
            {
                "status": status,
                "display_name": display_name,
                "relative_path": relative_path,
                "rom": rom,
                "entry": entry,
                "metadata": entry,
                "image_path": image_path if has_image else "",
                "has_metadata": has_metadata,
                "has_image": has_image,
                "is_in_gamelist": game is not None,
                "system_path": str(system_path),
                "system_folder": system.get("folder", ""),
                "system_label": system.get("label", ""),
                "screenscraper_system_id": system.get("screenscraper_id", 0),
            }
        )

        seen_paths.add(relative_path)

    for relative_path, game in entries.items():
        if relative_path in seen_paths:
            continue

        entry = gamelist_entry_to_dict(game, system_path)
        image_path = entry.get("image_path", "")
        has_image = bool(image_path and Path(image_path).exists())
        has_metadata = bool(entry.get("has_metadata"))

        if has_metadata and has_image:
            status = "complete"
        elif has_metadata:
            status = "missing_image"
        else:
            status = "missing_metadata"

        items.append(
            {
                "status": status,
                "display_name": entry.get("name") or relative_path,
                "relative_path": relative_path,
                "rom": {},
                "entry": entry,
                "metadata": entry,
                "image_path": image_path if has_image else "",
                "has_metadata": has_metadata,
                "has_image": has_image,
                "is_in_gamelist": True,
                "system_path": str(system_path),
                "system_folder": system.get("folder", ""),
                "system_label": system.get("label", ""),
                "screenscraper_system_id": system.get("screenscraper_id", 0),
            }
        )

    items.sort(key=lambda item: str(item.get("display_name", "")).lower())
    return items


def default_manual_search_text(item: dict[str, Any]) -> str:
    entry = item.get("entry") or {}
    rom = item.get("rom") or {}

    return (
        entry.get("name")
        or clean_rom_display_name(Path(rom.get("filename", "")).stem)
        or clean_rom_display_name(Path(item.get("relative_path", "")).stem)
    )


def search_screenscraper_games(
    *,
    username: str,
    password: str,
    query: str,
    system_id: int,
    limit: int = 20,
    quota_callback=None,
) -> list[dict[str, Any]]:
    query = str(query or "").strip()

    if not query:
        raise RuntimeError("Search text is required.")

    params = _common_screenscraper_params(username, password)
    params.update(
        {
            "systemeid": str(system_id),
            "recherche": query,
        }
    )

    data = _screenscraper_get_json("jeuRecherche.php", params, quota_callback=quota_callback)
    return extract_search_results(data, limit=limit)


def extract_search_results(data: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    response = data.get("response")

    if not isinstance(response, dict):
        return []

    raw_results = (
        response.get("jeux")
        or response.get("games")
        or response.get("jeu")
        or response.get("game")
        or []
    )

    if isinstance(raw_results, dict):
        raw_results = [raw_results]

    if not isinstance(raw_results, list):
        return []

    results = []

    for game in raw_results:
        if not isinstance(game, dict):
            continue

        metadata = extract_metadata_from_game(game, region_code="auto")
        game_id = metadata.get("id") or game.get("id") or game.get("idjeu") or game.get("idGame")

        name = (
            metadata.get("name")
            or game.get("nom")
            or game.get("name")
            or pick_localized_text(game.get("noms"), "auto")
            or "Unknown Game"
        )

        system_name = (
            pick_simple_text(game.get("systeme"))
            or pick_simple_text(game.get("system"))
            or pick_simple_text(game.get("console"))
        )

        release_date = metadata.get("releasedate", "")
        developer = metadata.get("developer", "")
        publisher = metadata.get("publisher", "")

        results.append(
            {
                "id": str(game_id or ""),
                "name": str(name or "Unknown Game"),
                "system": system_name,
                "releasedate": release_date,
                "developer": developer,
                "publisher": publisher,
                "metadata": metadata,
                "raw": game,
            }
        )

        if len(results) >= limit:
            break

    return results


def fetch_game_info_by_id(
    *,
    username: str,
    password: str,
    game_id: str | int,
    system_id: int,
    quota_callback=None,
) -> dict[str, Any]:
    game_id = str(game_id or "").strip()

    if not game_id:
        raise RuntimeError("ScreenScraper game ID is required.")

    params = _common_screenscraper_params(username, password)
    params.update(
        {
            "systemeid": str(system_id),
            "gameid": game_id,
        }
    )

    return _screenscraper_get_json("jeuInfos.php", params, quota_callback=quota_callback)


def apply_manual_scrape_result(
    *,
    system_path: str | Path,
    relative_path: str,
    rom: dict[str, Any],
    selected_result: dict[str, Any],
    username: str,
    password: str,
    image_source_name: str,
    selected_region: str,
    system_id: int,
    quota_callback=None,
) -> dict[str, Any]:
    region_code = detect_region_from_filename(
        rom.get("filename") or Path(relative_path).name,
        selected_region,
    )

    raw_game = selected_result.get("raw") if isinstance(selected_result, dict) else {}
    game_id = selected_result.get("id") if isinstance(selected_result, dict) else ""

    game = raw_game if isinstance(raw_game, dict) else {}

    if game_id:
        try:
            data = fetch_game_info_by_id(
                username=username,
                password=password,
                game_id=game_id,
                system_id=system_id,
                quota_callback=quota_callback,
            )
            fetched_game = extract_game_from_response(data)
            if fetched_game:
                game = fetched_game
        except Exception:
            pass

    metadata = extract_metadata_from_game(game, region_code=region_code)

    if not metadata and isinstance(selected_result, dict):
        metadata = dict(selected_result.get("metadata") or {})

    if not metadata:
        metadata = create_placeholder_metadata_from_rom(rom, region_code)

    if game_id and not metadata.get("id"):
        metadata["id"] = game_id

    if not metadata.get("source"):
        metadata["source"] = "ScreenScraper"

    image_relative_path = ""

    image_url = select_media_url(
        game,
        image_source_name=image_source_name,
        region_code=region_code,
    )

    if image_url:
        extension = guess_image_extension(image_url)
        image_path, image_relative_path = build_local_image_path(
            system_path,
            rom.get("filename") or Path(relative_path).name,
            image_source_name,
            extension=extension,
        )
        download_image(image_url, image_path)

    apply_scrape_result(
        system_path,
        relative_path,
        metadata,
        image_relative_path=image_relative_path,
        image_source_name=image_source_name,
        region=region_code,
        skip_existing_metadata=False,
    )

    return {
        "metadata": metadata,
        "image_relative_path": image_relative_path,
        "region": region_code,
    }

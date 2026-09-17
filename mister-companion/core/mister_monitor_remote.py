from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import requests

from core.app_paths import generated_path
from core.zapscraper import (
    extract_game_from_response,
    extract_metadata_from_game,
    fetch_game_info_by_hashes,
    fetch_game_info_by_id,
    search_screenscraper_games,
    select_media_url,
)
from core.zapscraper_systems import SUPPORTED_SYSTEMS


CACHE_ROOT = generated_path("remote_display_cache")


def _normal(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _system_index() -> dict[str, int]:
    result = {}
    for folder, info in SUPPORTED_SYSTEMS.items():
        system_id = int(info.get("screenscraper_id") or 0)
        if not system_id:
            continue
        result[_normal(folder)] = system_id
        result[_normal(info.get("label"))] = system_id
    result.update(
        {
            "nes": 3, "nintendoentertainmentsystem": 3, "nintendonesfamicom": 3,
            "snes": 4, "supernintendo": 4, "supernintendoentertainmentsystem": 4,
            "supernintendosuperfamicom": 4, "n64": 14, "nintendo64": 14,
            "gameboy": 9, "nintendogameboy": 9, "gameboycolor": 10,
            "nintendogameboycolor": 10, "gameboyadvance": 12,
            "nintendogameboyadvance": 12, "virtualboy": 11,
            "nintendovirtualboy": 11, "gamewatch": 52, "nintendogamewatch": 52,
            "megadrive": 1, "genesis": 1, "segagenesismegadrive": 1,
            "mastersystem": 2, "segamastersystem": 2, "gamegear": 21,
            "segagamegear": 21, "segasaturn": 22, "saturn": 22,
            "megacd": 20, "segacdmegacd": 20, "segamegacd": 20,
            "playstation": 57, "sonyplaystation": 57, "psx": 57,
            "pcengine": 31, "turbografx16pcengine": 31,
            "neogeo": 142, "neogeocd": 70, "arcade": 75, "mame": 75,
            "commodoreamiga": 64, "amiga": 64, "minimig": 64,
            "commodore64": 66, "c64": 66, "pcdos": 135, "ao486": 135,
            "menu": 0, "main": 0,
        }
    )
    return result


SYSTEM_IDS = _system_index()


def screenscraper_system_id(core: str, core_raw: str = "", filename: str = "") -> int:
    extension = Path(str(filename or "")).suffix.lower()
    raw = _normal(core_raw.removeprefix("RA_").removeprefix("ra_"))
    friendly = _normal(core)
    system_id = SYSTEM_IDS.get(raw) or SYSTEM_IDS.get(friendly) or 0
    if system_id == 3 and extension == ".fds":
        return 106
    if system_id == 4 and extension == ".bs":
        return 107
    if system_id == 142 and extension in {".cue", ".chd", ".iso"}:
        return 70
    return system_id


def _cache_key(snapshot: dict, details: dict, system_id: int) -> str:
    identity = "|".join(
        str(value or "")
        for value in (
            system_id,
            details.get("crc32"),
            details.get("md5"),
            details.get("sha1"),
            snapshot.get("core_raw"),
            snapshot.get("game"),
        )
    )
    return hashlib.sha1(identity.encode("utf-8", errors="replace")).hexdigest()


def _read_cache(cache_dir: Path) -> dict | None:
    metadata_path = cache_dir / "metadata.json"
    if not metadata_path.exists():
        return None
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    for name in ("artwork.jpg", "artwork.png", "artwork.webp"):
        artwork_path = cache_dir / name
        if artwork_path.exists():
            try:
                payload["artwork"] = artwork_path.read_bytes()
            except OSError:
                pass
            break
    payload["cached"] = True
    return payload


def _write_cache(cache_dir: Path, payload: dict, artwork: bytes, extension: str):
    cache_dir.mkdir(parents=True, exist_ok=True)
    for old_artwork in cache_dir.glob("artwork.*"):
        try:
            old_artwork.unlink()
        except OSError:
            pass
    clean_payload = {key: value for key, value in payload.items() if key != "artwork"}
    temporary_json = cache_dir / "metadata.json.tmp"
    temporary_json.write_text(json.dumps(clean_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary_json.replace(cache_dir / "metadata.json")
    if artwork:
        extension = extension if extension in {".jpg", ".png", ".webp"} else ".jpg"
        temporary_art = cache_dir / f"artwork{extension}.tmp"
        temporary_art.write_bytes(artwork)
        temporary_art.replace(cache_dir / f"artwork{extension}")


def _download_artwork(url: str) -> tuple[bytes, str]:
    if not url:
        return b"", ".jpg"
    response = requests.get(url, timeout=20, headers={"User-Agent": "MiSTer-Companion"})
    response.raise_for_status()
    data = response.content
    if len(data) > 20 * 1024 * 1024:
        raise RuntimeError("ScreenScraper artwork is too large.")
    content_type = str(response.headers.get("Content-Type") or "").lower()
    extension = ".png" if "png" in content_type else ".webp" if "webp" in content_type else ".jpg"
    return data, extension


def resolve_screenscraper_content(
    snapshot: dict,
    details: dict,
    username: str,
    password: str,
    *,
    force_refresh: bool = False,
) -> dict:
    filename = str(details.get("filename") or snapshot.get("game") or "").strip()
    system_id = screenscraper_system_id(
        str(snapshot.get("core") or ""),
        str(snapshot.get("core_raw") or ""),
        filename,
    )
    if not system_id or not snapshot.get("game"):
        return {"metadata": {}, "artwork": b"", "system_id": system_id}

    cache_dir = CACHE_ROOT / _cache_key(snapshot, details, system_id)
    cached = None if force_refresh else _read_cache(cache_dir)
    if cached is not None:
        return cached
    if not username or not password:
        return {
            "metadata": {}, "artwork": b"", "system_id": system_id,
            "error": "ScreenScraper is not configured. Add credentials in Remote Display Settings.",
        }

    data = {}
    if any(details.get(key) for key in ("crc32", "md5", "sha1")):
        data = fetch_game_info_by_hashes(
            username=username,
            password=password,
            system_id=system_id,
            rom_filename=filename,
            rom_size=int(details.get("size") or 0),
            crc=str(details.get("crc32") or ""),
            md5=str(details.get("md5") or ""),
            sha1=str(details.get("sha1") or ""),
        )
    else:
        query = str(details.get("search_name") or snapshot.get("game") or "").strip()
        results = search_screenscraper_games(
            username=username,
            password=password,
            query=query,
            system_id=system_id,
            limit=1,
        )
        if results and results[0].get("id"):
            data = fetch_game_info_by_id(
                username=username,
                password=password,
                game_id=results[0]["id"],
                system_id=system_id,
            )

    game = extract_game_from_response(data) if data else {}
    metadata = extract_metadata_from_game(game, region_code="auto") if game else {}
    art_url = select_media_url(game, image_source_name="2D Boxart", region_code="auto") if game else ""
    artwork, extension = _download_artwork(art_url)
    if not metadata and not artwork:
        return {
            "metadata": {}, "artwork": b"", "system_id": system_id,
            "error": "No ScreenScraper match was found for this game.",
        }
    payload = {"metadata": metadata, "artwork": artwork, "system_id": system_id}
    _write_cache(cache_dir, payload, artwork, extension)
    return payload

import difflib
import html
import json
import re

import requests


BASE_URL = "https://retroachievements.org/API"
IMAGE_BASE_URL = "https://retroachievements.org"
_CONSOLE_GAME_LIST_CACHE = {}


class RetroAchievementsError(Exception):
    pass


def _normalize_image_url(path):
    path = str(path or "").strip()
    if not path:
        return ""

    if path.startswith("http://") or path.startswith("https://"):
        return path

    if path.startswith("/"):
        return f"{IMAGE_BASE_URL}{path}"

    return f"{IMAGE_BASE_URL}/{path}"


def get_user_summary(username, api_key, recent_games=5, recent_achievements=10):
    username = str(username or "").strip()
    api_key = str(api_key or "").strip()

    if not username:
        raise RetroAchievementsError("RetroAchievements username is required.")

    if not api_key:
        raise RetroAchievementsError("RetroAchievements Web API key is required.")

    params = {
        "y": api_key,
        "u": username,
        "g": int(recent_games),
        "a": int(recent_achievements),
    }

    try:
        response = requests.get(
            f"{BASE_URL}/API_GetUserSummary.php",
            params=params,
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise RetroAchievementsError(f"Failed to contact RetroAchievements:\n{e}") from e

    try:
        data = response.json()
    except ValueError as e:
        raise RetroAchievementsError("RetroAchievements returned an invalid response.") from e

    if isinstance(data, dict):
        error = data.get("Error") or data.get("error")
        if error:
            raise RetroAchievementsError(str(error))

    if not isinstance(data, dict):
        raise RetroAchievementsError("RetroAchievements returned an unexpected response.")

    return data


def flatten_recent_achievements(summary):
    recent = summary.get("RecentAchievements") or summary.get("recentAchievements") or {}
    achievements = []

    if not isinstance(recent, dict):
        return achievements

    for _game_id, game_achievements in recent.items():
        if not isinstance(game_achievements, dict):
            continue

        for _achievement_id, achievement in game_achievements.items():
            if not isinstance(achievement, dict):
                continue

            achievements.append(
                {
                    "title": achievement.get("Title") or achievement.get("title") or "",
                    "description": achievement.get("Description") or achievement.get("description") or "",
                    "game_title": achievement.get("GameTitle") or achievement.get("gameTitle") or "",
                    "points": achievement.get("Points") or achievement.get("points") or 0,
                    "date_awarded": achievement.get("DateAwarded") or achievement.get("dateAwarded") or "",
                    "hardcore": achievement.get("HardcoreAchieved") or achievement.get("hardcoreAchieved") or False,
                    "badge_url": _normalize_image_url(
                        f"/Badge/{achievement.get('BadgeName') or achievement.get('badgeName')}.png"
                        if achievement.get("BadgeName") or achievement.get("badgeName")
                        else ""
                    ),
                }
            )

    achievements.sort(key=lambda item: item.get("date_awarded", ""), reverse=True)
    return achievements


def normalize_recent_games(summary):
    games = summary.get("RecentlyPlayed") or summary.get("recentlyPlayed") or []
    normalized = []

    if not isinstance(games, list):
        return normalized

    awarded = summary.get("Awarded") or summary.get("awarded") or {}

    for game in games:
        if not isinstance(game, dict):
            continue

        game_id = str(game.get("GameID") or game.get("gameId") or "")
        award_info = {}

        if isinstance(awarded, dict):
            award_info = awarded.get(game_id) or awarded.get(int(game_id)) if game_id.isdigit() else awarded.get(game_id)
            if not isinstance(award_info, dict):
                award_info = {}

        achieved = (
            award_info.get("NumAchievedHardcore")
            or award_info.get("numAchievedHardcore")
            or award_info.get("NumAchieved")
            or award_info.get("numAchieved")
            or 0
        )
        total = (
            award_info.get("NumPossibleAchievements")
            or award_info.get("numPossibleAchievements")
            or game.get("AchievementsTotal")
            or game.get("achievementsTotal")
            or 0
        )

        normalized.append(
            {
                "title": game.get("Title") or game.get("title") or "",
                "console": game.get("ConsoleName") or game.get("consoleName") or "",
                "last_played": game.get("LastPlayed") or game.get("lastPlayed") or "",
                "achieved": achieved,
                "total": total,
                "box_art_url": _normalize_image_url(game.get("ImageBoxArt") or game.get("imageBoxArt") or ""),
            }
        )

    return normalized


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_page_json(html_text):
    match = re.search(r'data-page="([^"]+)"', html_text or "")
    if not match:
        return None

    try:
        return json.loads(html.unescape(match.group(1)))
    except Exception:
        return None


def _walk_values(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)


def _pick_first(data, keys):
    if not isinstance(data, dict):
        return ""

    for key in keys:
        if key in data and data.get(key) not in (None, ""):
            return data.get(key)

    return ""


def _normalize_set_type(value, title=""):
    text = str(value or title or "").strip().lower()

    if "bonus" in text:
        return "Bonus"
    if "challenge" in text:
        return "Challenge"
    if "special" in text:
        return "Specialty"
    if "exclusive" in text:
        return "Exclusive"
    if "base" in text:
        return "Base"

    return "Set"


def _normalize_set_title(value, set_type):
    title = str(value or "").strip()

    if not title:
        return f"{set_type} Set"

    return title


def _looks_like_set(data, base_game_id):
    if not isinstance(data, dict):
        return False

    game_id = _pick_first(data, [
        "GameID",
        "gameId",
        "game_id",
        "ID",
        "id",
    ])

    if not _safe_int(game_id):
        return False

    title = _pick_first(data, [
        "Title",
        "title",
        "Name",
        "name",
        "label",
    ])

    set_type = _pick_first(data, [
        "SetType",
        "setType",
        "type",
        "Type",
        "kind",
        "Kind",
    ])

    parent_id = _pick_first(data, [
        "ParentGameID",
        "parentGameId",
        "parent_game_id",
        "ParentID",
        "parentId",
    ])

    image = _pick_first(data, [
        "ImageIcon",
        "imageIcon",
        "Image",
        "image",
        "badgeUrl",
        "badge_url",
        "iconUrl",
        "icon_url",
        "src",
    ])

    joined = " ".join(str(v or "") for v in [title, set_type, image]).lower()

    if _safe_int(game_id) == _safe_int(base_game_id):
        return bool(title or image)

    if _safe_int(parent_id) == _safe_int(base_game_id):
        return True

    return any(word in joined for word in ["base set", "bonus", "challenge", "specialty", "exclusive"])


def _normalize_set_candidate(data, fallback_type="Set"):
    game_id = _pick_first(data, [
        "GameID",
        "gameId",
        "game_id",
        "ID",
        "id",
    ])

    title = _pick_first(data, [
        "Title",
        "title",
        "Name",
        "name",
        "label",
    ])

    raw_type = _pick_first(data, [
        "SetType",
        "setType",
        "type",
        "Type",
        "kind",
        "Kind",
    ])

    image = _pick_first(data, [
        "ImageIcon",
        "imageIcon",
        "Image",
        "image",
        "badgeUrl",
        "badge_url",
        "iconUrl",
        "icon_url",
        "src",
    ])

    set_type = _normalize_set_type(raw_type, title or fallback_type)

    return {
        "id": str(game_id or ""),
        "title": _normalize_set_title(title, set_type),
        "type": set_type,
        "image": _normalize_image_url(image),
    }





def _strip_subset_marker(value):
    text = html.unescape(str(value or "")).strip()
    text = re.sub(r"\s*\[\s*subset\s*-\s*[^\]]+\]\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\[\s*subset\s*\]\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*~\s*(bonus|challenge|specialty|exclusive|subset)\s*~\s*", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _match_title_key(value):
    text = _strip_subset_marker(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _has_set_hint(value):
    text = html.unescape(str(value or "")).lower()
    return any(part in text for part in [
        "[subset",
        "subset -",
        "~ bonus ~",
        "~ challenge ~",
        "~ specialty ~",
        "~ exclusive ~",
        " bonus]",
        " challenge]",
        " specialty]",
        " exclusive]",
    ])


def _extract_set_label(title, set_type):
    text = html.unescape(str(title or "")).strip()
    match = re.search(r"\[\s*subset\s*-\s*([^\]]+)\]", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip() or f"{set_type} Set"

    match = re.search(r"~\s*(bonus|challenge|specialty|exclusive|subset)\s*~\s*(.*)$", text, flags=re.IGNORECASE)
    if match:
        label = match.group(2).strip()
        return label or f"{set_type} Set"

    stripped = _strip_subset_marker(text)
    if stripped and stripped != text:
        return stripped

    return text or f"{set_type} Set"


def _get_console_game_list(api_key, console_id):
    console_id = _safe_int(console_id)
    if not console_id:
        return []

    cache_key = str(console_id)
    if cache_key in _CONSOLE_GAME_LIST_CACHE:
        return _CONSOLE_GAME_LIST_CACHE[cache_key]

    try:
        response = requests.get(
            f"{BASE_URL}/API_GetGameList.php",
            params={
                "y": api_key,
                "i": console_id,
                "f": 1,
                "h": 0,
            },
            timeout=25,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        _CONSOLE_GAME_LIST_CACHE[cache_key] = []
        return []

    if isinstance(data, list):
        games = data
    elif isinstance(data, dict):
        raw_games = data.get("Results") or data.get("results") or data.get("Games") or data.get("games")
        if isinstance(raw_games, list):
            games = raw_games
        elif isinstance(raw_games, dict):
            games = list(raw_games.values())
        else:
            games = [item for item in data.values() if isinstance(item, dict)]
    else:
        games = []

    _CONSOLE_GAME_LIST_CACHE[cache_key] = games
    return games


def _game_id_from_data(data):
    return str(_pick_first(data, ["GameID", "gameId", "game_id", "ID", "id"]) or "").strip()


def _game_title_from_data(data):
    return str(_pick_first(data, ["Title", "title", "GameTitle", "gameTitle", "Name", "name"]) or "").strip()


def _game_image_from_data(data):
    return _normalize_image_url(
        _pick_first(data, [
            "ImageIcon",
            "imageIcon",
            "GameIcon",
            "gameIcon",
            "ImageTitle",
            "imageTitle",
            "Image",
            "image",
        ])
    )


def _set_option_from_game(game, set_type=None):
    title = _game_title_from_data(game)
    normalized_type = set_type or _normalize_set_type(title)
    return {
        "id": _game_id_from_data(game),
        "title": _normalize_set_title(_extract_set_label(title, normalized_type), normalized_type),
        "type": normalized_type,
        "image": _game_image_from_data(game),
    }


def get_game_set_options(api_key, game_data):
    api_key = str(api_key or "").strip()
    game_data = game_data if isinstance(game_data, dict) else {}

    game_id = str(
        game_data.get("ID")
        or game_data.get("id")
        or game_data.get("GameID")
        or game_data.get("gameId")
        or ""
    ).strip()

    if not game_id:
        return []

    title = str(game_data.get("Title") or game_data.get("title") or "").strip()
    console_id = (
        game_data.get("ConsoleID")
        or game_data.get("consoleId")
        or game_data.get("ConsoleId")
        or ""
    )

    title_key = _match_title_key(title)
    console_games = _get_console_game_list(api_key, console_id)

    related_games = []
    base_game = None

    for candidate in console_games:
        if not isinstance(candidate, dict):
            continue

        candidate_id = _game_id_from_data(candidate)
        candidate_title = _game_title_from_data(candidate)
        if not candidate_id or not candidate_title:
            continue

        if _match_title_key(candidate_title) != title_key:
            continue

        related_games.append(candidate)

        if not _has_set_hint(candidate_title):
            base_game = candidate

    if not base_game:
        parent_game_id = str(
            game_data.get("ParentGameID")
            or game_data.get("parentGameId")
            or ""
        ).strip()
        if parent_game_id:
            for candidate in related_games:
                if _game_id_from_data(candidate) == parent_game_id:
                    base_game = candidate
                    break

    if not base_game and not _has_set_hint(title):
        base_game = game_data

    if not base_game:
        base_game = game_data

    base_id = _game_id_from_data(base_game) or game_id
    base_icon = _game_image_from_data(base_game) or _game_image_from_data(game_data)

    sets = [
        {
            "id": str(base_id),
            "title": "Base Set",
            "type": "Base",
            "image": base_icon,
        }
    ]
    seen = {str(base_id)}

    for candidate in related_games:
        candidate_id = _game_id_from_data(candidate)
        candidate_title = _game_title_from_data(candidate)

        if not candidate_id or candidate_id in seen:
            continue

        if not _has_set_hint(candidate_title):
            continue

        item = _set_option_from_game(candidate)
        item_id = str(item.get("id") or "").strip()
        if not item_id or item_id in seen:
            continue

        seen.add(item_id)
        sets.append(item)

    if game_id not in seen and _has_set_hint(title):
        item = _set_option_from_game(game_data)
        if item.get("id"):
            sets.append(item)

    type_order = {
        "Base": 0,
        "Bonus": 1,
        "Challenge": 2,
        "Specialty": 3,
        "Exclusive": 4,
        "Subset": 5,
        "Set": 6,
    }
    sets[1:] = sorted(
        sets[1:],
        key=lambda item: (
            type_order.get(str(item.get("type") or "Set"), 99),
            str(item.get("title") or "").lower(),
        ),
    )

    return sets

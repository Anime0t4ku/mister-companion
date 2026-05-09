import requests


BASE_URL = "https://retroachievements.org/API"
IMAGE_BASE_URL = "https://retroachievements.org"


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
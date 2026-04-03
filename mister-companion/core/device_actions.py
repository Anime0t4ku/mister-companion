import re
from pathlib import PurePosixPath


def run_remote_command(connection, command: str):
    if not connection.is_connected():
        return None
    return connection.run_command(command)


def progress_bar_style_for_percent(percent: int) -> str:
    if percent > 85:
        return "QProgressBar::chunk { background-color: #F44336; }"
    if percent > 70:
        return "QProgressBar::chunk { background-color: #FF9800; }"
    return "QProgressBar::chunk { background-color: #4CAF50; }"


def parse_df_line(df_line: str):
    if not df_line:
        return None

    parts = df_line.split()
    if len(parts) < 5:
        return None

    try:
        size = parts[1]
        avail = parts[3]
        percent = int(parts[4].replace("%", ""))
    except Exception:
        return None

    return {
        "size": size,
        "avail": avail,
        "percent": percent,
        "label": f"{avail} free of {size} ({percent}% used)",
        "style": progress_bar_style_for_percent(percent),
    }


def get_sd_storage_info(connection):
    df = run_remote_command(connection, "df -h /media/fat | tail -1")
    return parse_df_line(df)


def get_usb_storage_info(connection):
    usb = run_remote_command(connection, "df -h | grep /media/usb")
    if not usb:
        return {
            "present": False,
            "readable": False,
            "label": "No USB storage detected",
        }

    line = usb.splitlines()[0]
    parsed = parse_df_line(line)

    if not parsed:
        return {
            "present": True,
            "readable": False,
            "label": "USB detected (unable to read usage)",
        }

    parsed["present"] = True
    parsed["readable"] = True
    return parsed


def is_smb_enabled(connection):
    smb_check = run_remote_command(
        connection,
        "test -f /media/fat/linux/samba.sh && echo EXISTS"
    )
    return "EXISTS" in (smb_check or "")


def enable_smb_remote(connection):
    return run_remote_command(
        connection,
        "if [ -f /media/fat/linux/_samba.sh ]; then mv /media/fat/linux/_samba.sh /media/fat/linux/samba.sh; fi"
    )


def disable_smb_remote(connection):
    return run_remote_command(
        connection,
        "if [ -f /media/fat/linux/samba.sh ]; then mv /media/fat/linux/samba.sh /media/fat/linux/_samba.sh; fi"
    )


def return_to_menu_remote(connection):
    return run_remote_command(
        connection,
        'echo "load_core /media/fat/menu.rbf" > /dev/MiSTer_cmd'
    )


def normalize_core_name(core_name: str) -> str:
    value = (core_name or "").strip()
    if not value:
        return "Unknown"

    value = value.replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\bRELEASEDATE\b", "", value, flags=re.IGNORECASE).strip()
    value = re.sub(r"\b20\d{2}[-_]?\d{2}[-_]?\d{2}\b", "", value).strip()
    value = re.sub(r"\s+", " ", value).strip(" -_")

    aliases = {
        "TGFX16": "TurboGrafx-16",
        "PCECD": "PC Engine CD",
        "SMS": "Master System",
        "GENESIS": "Genesis",
        "MEGADRIVE": "Mega Drive",
        "NES": "NES",
        "SNES": "SNES",
        "GBA": "Game Boy Advance",
        "GBC": "Game Boy Color",
        "GB": "Game Boy",
        "PSX": "PlayStation",
        "AO486": "ao486",
    }

    compact = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    return aliases.get(compact, value)


def prettify_game_name(path_text: str) -> str:
    value = (path_text or "").strip()
    if not value:
        return "Unknown"

    value = value.rstrip("/")

    last_part = PurePosixPath(value).name if "/" in value else value
    name = PurePosixPath(last_part).stem if "." in last_part else last_part

    name = re.sub(r"\(Disc\s*\d+\)", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\b\[[^\]]+\]", "", name)
    name = re.sub(
        r"\([^\)]*(USA|Europe|Japan|World|En,?Fr,?De|Rev[^\)]*)[^\)]*\)",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = name.replace("_", " ").replace(".", " ")
    name = re.sub(r"\s+", " ", name).strip(" -_")

    return name or value


def shorten_path(path: str, max_length: int = 70) -> str:
    value = (path or "").strip()
    if not value:
        return ""

    if len(value) <= max_length:
        return value

    return "..." + value[-(max_length - 3):]


def get_now_playing(connection):
    core_raw = (run_remote_command(connection, "cat /tmp/CORENAME 2>/dev/null") or "").strip()
    active_game = (run_remote_command(connection, "cat /tmp/ACTIVEGAME 2>/dev/null") or "").strip()

    if not active_game:
        active_game = (run_remote_command(connection, "cat /tmp/FULLPATH 2>/dev/null") or "").strip()

    core_display = normalize_core_name(core_raw)
    game_display = prettify_game_name(active_game) if active_game else "Unknown"

    is_playing = bool(active_game) and core_display.upper() != "MENU"

    return {
        "playing": is_playing,
        "core_raw": core_raw,
        "core_display": core_display,
        "game_path": active_game,
        "game_display": game_display,
        "summary": f"{core_display}  |  {game_display}" if is_playing else "",
        "short_path": shorten_path(active_game) if is_playing else "",
    }
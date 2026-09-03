import json
import re
from pathlib import Path

from core.app_paths import generated_path
from core.extras_zaparoo_launcher import (
    MISTER_INI_PATH,
    _mister_ini_text_has_zaparoo_launcher_entries,
    _patch_mister_ini_for_zaparoo_launcher,
    _remove_zaparoo_launcher_from_mister_ini,
)


JSON_PATH = "/media/fat/Scripts/.config/update_all/update_all.json"
ARCADE_ORGANIZER_INI_PATH = "/media/fat/Scripts/update_arcade-organizer.ini"
CUSTOM_SOURCES_INI_PATH = "/media/fat/downloader_custom_sources.ini"
CUSTOM_SOURCES_METADATA_PATH = generated_path("update_all_extra_sources.json")

ZAPAROO_SECTION = "ZaparooProject/Zaparoo_MiSTer"
ZAPAROO_DB_URL = "https://raw.githubusercontent.com/ZaparooProject/Zaparoo_MiSTer/db/db.json.zip"

MISTER_FRONTIER_SECTION = "MiSTerOrganize/MiSTer_Frontier"
MISTER_FRONTIER_DB_URL = "https://raw.githubusercontent.com/MiSTerOrganize/MiSTer_Frontier/db/db.json.zip"

RETROACHIEVEMENTS_CORES_SECTION = "theypsilon/RetroAchievementsDB_MiSTer"
RETROACHIEVEMENTS_CORES_DB_URL = "https://raw.githubusercontent.com/theypsilon/RetroAchievementsDB_MiSTer/db/db.json.zip"

# Additional Update_All downloader databases mirrored from Install Center.
PHYSICAL_DISC_SECTION = "MultiDatabases/physical-disc"
PHYSICAL_DISC_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/physical-disc/db.json"
PAPRIUM_SECTION = "MultiDatabases/paprium"
PAPRIUM_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/paprium/db.json"
MMS2_GB_SECTION = "MultiDatabases/mms2-gb"
MMS2_GB_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/mms2-gb/db.json"
MEGAVGMD_SECTION = "MultiDatabases/megavgmdrive"
MEGAVGMD_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/megavgmdrive/db.json"

DREAMSTER_SECTION = "MultiDatabases/dreamster"
DREAMSTER_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/dreamster/db.json"
SONIC_MANIA_SECTION = "MultiDatabases/sonic-mania"
SONIC_MANIA_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/sonic-mania/db.json"
DUKE3D_SECTION = "MultiDatabases/duke3d"
DUKE3D_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/duke3d/db.json"
QUAKE_SECTION = "MultiDatabases/mister-quake"
QUAKE_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/mister-quake/db.json"
SOLARUS_SECTION = "MultiDatabases/solarus"
SOLARUS_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/solarus/db.json"
THREE_S_ARM_SECTION = "MultiDatabases/3s-arm"
THREE_S_ARM_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/3s-arm/db.json"

TEST_SUITE_240P_SECTION = "ajgowans/240p"
TEST_SUITE_240P_DB_URL = "https://raw.githubusercontent.com/ajgowans/240p/db/db.json.zip"
MISTER_HIFI_SECTION = "MultiDatabases/mister-hifi"
MISTER_HIFI_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/mister-hifi/db.json"
MISTERFIN_SECTION = "MultiDatabases/misterfin"
MISTERFIN_DB_URL = "https://raw.githubusercontent.com/theypsilon/MultiDatabases_MiSTer/db/misterfin/db.json.zip"

MANUALSDB_PATH = "/media/fat/downloader_ajgowans_manualsdb.ini"

MISTER_FRONTIER_FILTERS = {
    "All Frontier Cores": "",
    "PICO-8 only": "pico-8",
    "OpenBOR 4086 only": "openbor-4086",
    "OpenBOR 7533 only": "openbor-7533",
    "OpenBOR 4086 + 7533": "openbor-4086 openbor-7533",
    "PICO-8 + OpenBOR 4086": "pico-8 openbor-4086",
    "PICO-8 + OpenBOR 7533": "pico-8 openbor-7533",
}

MISTER_FRONTIER_FILTER_LABELS = {
    value: label
    for label, value in MISTER_FRONTIER_FILTERS.items()
}

MANUALSDB_SOURCES = [
    ("3do", "3DO"),
    ("arcadia2001", "Arcadia 2001"),
    ("atari2600", "Atari 2600"),
    ("atari5200", "Atari 5200"),
    ("atari7800", "Atari 7800"),
    ("atarilynx", "Atari Lynx"),
    ("atarixegs", "Atari XEGS"),
    ("avision", "Adventure Vision"),
    ("ballyastrocade", "Bally Astrocade"),
    ("bbcbridge", "BBC Bridge"),
    ("cdi", "CD-i"),
    ("channelf", "Channel F"),
    ("colecovision", "ColecoVision"),
    ("creativision", "CreatiVision"),
    ("fds", "Famicom Disk System"),
    ("gameandwatch", "Game & Watch"),
    ("gameboy", "Game Boy"),
    ("gamegear", "Game Gear"),
    ("gba", "Game Boy Advance"),
    ("gbc", "Game Boy Color"),
    ("intellivision", "Intellivision"),
    ("jaguar", "Jaguar"),
    ("jaguarcd", "Jaguar CD"),
    ("lcdhandhelds", "LCD Handhelds"),
    ("megadrive", "Mega Drive"),
    ("n64", "Nintendo 64"),
    ("neogeoaes", "Neo Geo AES"),
    ("neogeocd", "Neo Geo CD"),
    ("nes", "NES"),
    ("ngp", "Neo Geo Pocket"),
    ("ngpc", "Neo Geo Pocket Color"),
    ("odyssey2", "Odyssey 2"),
    ("pokemonmini", "Pokémon Mini"),
    ("psx", "PlayStation"),
    ("pyuutajr", "Pyuuta Jr."),
    ("sega32x", "Sega 32X"),
    ("segacd", "Sega CD"),
    ("segasaturn", "Sega Saturn"),
    ("segasg1000", "SG-1000"),
    ("sms", "Master System"),
    ("snes", "SNES"),
    ("supervision", "Supervision"),
    ("turbografx16", "TurboGrafx-16"),
    ("turbografxcd", "TurboGrafx-CD"),
    ("vc4000", "VC 4000"),
    ("vectrex", "Vectrex"),
    ("wonderswanc", "WonderSwan Color"),
]

MANUALSDB_IDS = [source_id for source_id, _label in MANUALSDB_SOURCES]


def split_downloader_paths():
    return {
        "main": "/media/fat/downloader.ini",
        "arcade": "/media/fat/downloader_arcade_roms_db.ini",
        "bios": "/media/fat/downloader_bios_db.ini",
        "manualsdb": MANUALSDB_PATH,
    }


def local_path(sd_root, remote_path):
    normalized = str(remote_path).replace("\\", "/")

    if normalized == "/media/fat":
        relative = ""
    elif normalized.startswith("/media/fat/"):
        relative = normalized[len("/media/fat/"):]
    else:
        relative = normalized.lstrip("/")

    return Path(sd_root).expanduser().resolve() / relative


def read_remote_text(sftp, path, default=""):
    try:
        with sftp.open(path, "r") as f:
            data = f.read()
            if isinstance(data, bytes):
                return data.decode()
            return data
    except Exception:
        return default


def write_remote_text(sftp, path, text):
    with sftp.open(path, "w") as f:
        f.write(text)


def remote_path_exists(sftp, path):
    try:
        sftp.stat(path)
        return True
    except Exception:
        return False


def remove_remote_file(sftp, path):
    try:
        sftp.remove(path)
    except Exception:
        pass


def read_local_text(sd_root, path, default=""):
    try:
        local = local_path(sd_root, path)
        if not local.exists():
            return default
        return local.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return default


def write_local_text(sd_root, path, text):
    local = local_path(sd_root, path)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(text, encoding="utf-8")


def local_path_exists(sd_root, path):
    try:
        return local_path(sd_root, path).exists()
    except Exception:
        return False


def remove_local_file(sd_root, path):
    try:
        local = local_path(sd_root, path)
        if local.exists() and local.is_file():
            local.unlink()
    except Exception:
        pass


def read_custom_sources_metadata():
    try:
        return CUSTOM_SOURCES_METADATA_PATH.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def write_custom_sources_metadata(text):
    if text:
        CUSTOM_SOURCES_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        CUSTOM_SOURCES_METADATA_PATH.write_text(text, encoding="utf-8")
    elif CUSTOM_SOURCES_METADATA_PATH.exists():
        CUSTOM_SOURCES_METADATA_PATH.unlink()


def normalize_database_id(database_id):
    value = str(database_id or "").strip()
    while value.startswith("["):
        value = value[1:].lstrip()
    while value.endswith("]"):
        value = value[:-1].rstrip()
    if not value or "[" in value or "]" in value or "\n" in value or "\r" in value:
        raise ValueError("Enter a valid database ID.")
    return f"[{value}]"


def _parse_custom_sources_ini(text):
    lines = str(text or "").splitlines(keepends=True)
    sections = []
    unmanaged = []
    current = []

    def finish(block):
        if not block:
            return
        header = block[0].strip()
        if not (header.startswith("[") and header.endswith("]")):
            unmanaged.extend(block)
            return
        try:
            database_id = normalize_database_id(header)
        except ValueError:
            unmanaged.extend(block)
            return
        db_url = ""
        for line in block[1:]:
            stripped = line.strip()
            if stripped.lower().startswith("db_url") and "=" in stripped:
                db_url = stripped.split("=", 1)[1].strip()
                break
        if not db_url:
            unmanaged.extend(block)
            return
        sections.append({
            "database_id": database_id,
            "db_url": db_url,
            "ini_block": "".join(block).rstrip("\r\n"),
        })

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            finish(current)
            current = [line]
        else:
            current.append(line)
    finish(current)
    return sections, "".join(unmanaged)


def parse_custom_source_entry(text):
    normalized_lines = []
    for line in str(text or "").replace("db\\_url", "db_url").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("db_url") and "=" in line:
            prefix, value = line.split("=", 1)
            value = value.strip()
            markdown_link = re.fullmatch(r"\[(https?://[^\]]+)\]\((https?://[^)]+)\)", value)
            if markdown_link:
                value = markdown_link.group(2)
            line = f"{prefix.rstrip()} = {value}"
        normalized_lines.append(line)

    sections, _unmanaged = _parse_custom_sources_ini("\n".join(normalized_lines))
    if len(sections) != 1:
        return None
    return sections[0]


def _load_custom_sources_data(ini_text, metadata_text):
    active_sections, unmanaged_text = _parse_custom_sources_ini(ini_text)
    try:
        raw_metadata = json.loads(metadata_text or "[]")
        if not isinstance(raw_metadata, list):
            raw_metadata = []
    except Exception:
        raw_metadata = []

    sources = []
    by_id = {}
    for item in raw_metadata:
        if not isinstance(item, dict):
            continue
        try:
            database_id = normalize_database_id(item.get("database_id", ""))
        except ValueError:
            continue
        source = {
            "display_name": str(item.get("display_name") or database_id[1:-1]).strip(),
            "database_id": database_id,
            "db_url": str(item.get("db_url") or "").strip(),
            "ini_block": str(item.get("ini_block") or "").rstrip("\r\n"),
            "enabled": False,
        }
        sources.append(source)
        by_id[database_id.lower()] = source

    for section in active_sections:
        key = section["database_id"].lower()
        source = by_id.get(key)
        if source is None:
            source = {
                "display_name": section["database_id"][1:-1],
                "database_id": section["database_id"],
                "db_url": section["db_url"],
                "ini_block": section["ini_block"],
                "enabled": True,
            }
            sources.append(source)
            by_id[key] = source
        else:
            source["ini_block"] = section["ini_block"]
            source["enabled"] = True

    return sources, unmanaged_text


def _replace_custom_source_header_and_url(source):
    database_id = normalize_database_id(source.get("database_id", ""))
    db_url = str(source.get("db_url") or "").strip()
    block = str(source.get("ini_block") or "").splitlines()
    if not block:
        return f"{database_id}\ndb_url = {db_url}"
    block[0] = database_id
    replaced = False
    for index in range(1, len(block)):
        stripped = block[index].strip()
        if stripped.lower().startswith("db_url") and "=" in stripped:
            indent = block[index][:len(block[index]) - len(block[index].lstrip())]
            block[index] = f"{indent}db_url = {db_url}"
            replaced = True
            break
    if not replaced:
        block.insert(1, f"db_url = {db_url}")
    return "\n".join(block).rstrip()


def _prepare_custom_sources_files(config):
    sources = config.get("custom_sources", [])
    metadata = []
    enabled_blocks = []
    for source in sources:
        block = _replace_custom_source_header_and_url(source)
        item = {
            "display_name": str(source.get("display_name") or "").strip(),
            "database_id": normalize_database_id(source.get("database_id", "")),
            "db_url": str(source.get("db_url") or "").strip(),
            "ini_block": block,
        }
        metadata.append(item)
        if source.get("enabled", False):
            enabled_blocks.append(block)

    unmanaged = str(config.get("custom_sources_unmanaged_text") or "").strip()
    ini_parts = ([unmanaged] if unmanaged else []) + enabled_blocks
    ini_text = "\n\n".join(part for part in ini_parts if part).rstrip()
    if ini_text:
        ini_text += "\n"
    metadata_text = json.dumps(metadata, indent=4) + "\n" if metadata else ""
    return ini_text, metadata_text


def read_downloader_files(sftp):
    paths = split_downloader_paths()
    return {
        "main": read_remote_text(sftp, paths["main"], ""),
        "arcade": read_remote_text(sftp, paths["arcade"], ""),
        "bios": read_remote_text(sftp, paths["bios"], ""),
        "manualsdb": read_remote_text(sftp, paths["manualsdb"], ""),
    }


def read_downloader_files_local(sd_root):
    paths = split_downloader_paths()
    return {
        "main": read_local_text(sd_root, paths["main"], ""),
        "arcade": read_local_text(sd_root, paths["arcade"], ""),
        "bios": read_local_text(sd_root, paths["bios"], ""),
        "manualsdb": read_local_text(sd_root, paths["manualsdb"], ""),
    }


def remove_section_from_lines(lines, section):
    new_lines = []
    skip = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            skip = stripped.strip("[]") == section

        if not skip:
            new_lines.append(line)

    return new_lines


def extract_section_from_lines(lines, section):
    section_lines = []
    capturing = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped.strip("[]")
            if current == section:
                capturing = True
                section_lines = [line]
                continue
            elif capturing:
                break

        if capturing:
            section_lines.append(line)

    return section_lines


def extract_section_value(ini_data, section, key):
    lines = ini_data.splitlines()
    section_lines = extract_section_from_lines(lines, section)

    for line in section_lines:
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue

        if "=" not in stripped:
            continue

        name, value = stripped.split("=", 1)
        if name.strip() == key:
            return value.strip()

    return ""


def upsert_section_lines(lines, section, new_section_lines):
    lines = remove_section_from_lines(lines, section)

    while lines and not lines[0].strip():
        lines.pop(0)

    while lines and not lines[-1].strip():
        lines.pop()

    lines.extend(new_section_lines)
    return lines


def section_enabled_in_text(text, section):
    return f"[{section}]" in text and f";[{section}]" not in text


def build_manualsdb_ini(selected_ids):
    selected = [source_id for source_id in selected_ids if source_id in MANUALSDB_IDS]
    lines = []

    for source_id in selected:
        if lines:
            lines.append("")

        section = f"ajgowans/manualsdb-{source_id}"
        url = f"https://raw.githubusercontent.com/ajgowans/manualsdb-{source_id}/db/db.json.zip"

        lines += [
            f"[{section}]",
            f"db_url = {url}",
        ]

    if not lines:
        return ""

    return "\n".join(lines).rstrip() + "\n"


def parse_manualsdb_ini(text):
    selected = []

    for source_id in MANUALSDB_IDS:
        section = f"ajgowans/manualsdb-{source_id}"

        if section_enabled_in_text(text, section):
            selected.append(source_id)

    return selected


def normalize_manualsdb_selected(selected_ids):
    selected = []

    for source_id in selected_ids or []:
        if source_id in MANUALSDB_IDS and source_id not in selected:
            selected.append(source_id)

    return selected


def ensure_split_downloader_configs(sftp):
    paths = split_downloader_paths()

    main_lines = read_remote_text(sftp, paths["main"], "").splitlines()
    arcade_lines = read_remote_text(sftp, paths["arcade"], "").splitlines()
    bios_lines = read_remote_text(sftp, paths["bios"], "").splitlines()

    changed_main = False
    changed_arcade = False
    changed_bios = False

    arcade_section = extract_section_from_lines(main_lines, "arcade_roms_db")
    if arcade_section:
        arcade_lines = upsert_section_lines(
            arcade_lines,
            "arcade_roms_db",
            arcade_section
        )
        main_lines = remove_section_from_lines(main_lines, "arcade_roms_db")
        changed_main = True
        changed_arcade = True

    bios_section = extract_section_from_lines(main_lines, "bios_db")
    if bios_section:
        bios_lines = upsert_section_lines(
            bios_lines,
            "bios_db",
            bios_section
        )
        main_lines = remove_section_from_lines(main_lines, "bios_db")
        changed_main = True
        changed_bios = True

    if changed_main:
        write_remote_text(sftp, paths["main"], "\n".join(main_lines).rstrip() + "\n")
    if changed_arcade:
        write_remote_text(sftp, paths["arcade"], "\n".join(arcade_lines).rstrip() + "\n")
    if changed_bios:
        write_remote_text(sftp, paths["bios"], "\n".join(bios_lines).rstrip() + "\n")


def ensure_split_downloader_configs_local(sd_root):
    paths = split_downloader_paths()

    main_lines = read_local_text(sd_root, paths["main"], "").splitlines()
    arcade_lines = read_local_text(sd_root, paths["arcade"], "").splitlines()
    bios_lines = read_local_text(sd_root, paths["bios"], "").splitlines()

    changed_main = False
    changed_arcade = False
    changed_bios = False

    arcade_section = extract_section_from_lines(main_lines, "arcade_roms_db")
    if arcade_section:
        arcade_lines = upsert_section_lines(
            arcade_lines,
            "arcade_roms_db",
            arcade_section
        )
        main_lines = remove_section_from_lines(main_lines, "arcade_roms_db")
        changed_main = True
        changed_arcade = True

    bios_section = extract_section_from_lines(main_lines, "bios_db")
    if bios_section:
        bios_lines = upsert_section_lines(
            bios_lines,
            "bios_db",
            bios_section
        )
        main_lines = remove_section_from_lines(main_lines, "bios_db")
        changed_main = True
        changed_bios = True

    if changed_main:
        write_local_text(sd_root, paths["main"], "\n".join(main_lines).rstrip() + "\n")
    if changed_arcade:
        write_local_text(sd_root, paths["arcade"], "\n".join(arcade_lines).rstrip() + "\n")
    if changed_bios:
        write_local_text(sd_root, paths["bios"], "\n".join(bios_lines).rstrip() + "\n")


def _build_config_data(ini_data, json_data, arcade_org_ini, manualsdb_ini="", mister_ini=""):
    def is_enabled(section):
        return section_enabled_in_text(ini_data, section)

    arcade_org_ini_enabled = "ARCADE_ORGANIZER=true" in arcade_org_ini
    manualsdb_selected = parse_manualsdb_ini(manualsdb_ini)

    data = {
        "main_cores": is_enabled("distribution_mister"),
        "main_source": "MiSTer-devel (Recommended)",
        "jtcores": is_enabled("jtcores"),
        "jt_beta": json_data.get("download_beta_cores", False),

        "coinop": is_enabled("Coin-OpCollection/Distribution-MiSTerFPGA"),
        "arcade_offset": is_enabled("arcade_offset_folder"),
        "llapi": is_enabled("llapi_folder"),
        "unofficial": is_enabled("theypsilon_unofficial_distribution"),
        "yc": is_enabled("MikeS11/YC_Builds-MiSTer"),
        "agg23": is_enabled("agg23_db"),
        "altcores": is_enabled("ajgowans/alt-cores"),
        "dualram": is_enabled("TheJesusFish/Dual-Ram-Console-Cores"),
        "retroachievements_cores": is_enabled(RETROACHIEVEMENTS_CORES_SECTION),

        "physical_disc": is_enabled(PHYSICAL_DISC_SECTION),
        "paprium_megadrive": is_enabled(PAPRIUM_SECTION),
        "mms2_gb_core": is_enabled(MMS2_GB_SECTION),
        "megavgmdrive": is_enabled(MEGAVGMD_SECTION),

        "dreamster": is_enabled(DREAMSTER_SECTION),
        "sonic_mania_mister": is_enabled(SONIC_MANIA_SECTION),
        "mister_duke3d": is_enabled(DUKE3D_SECTION),
        "mister_quake": is_enabled(QUAKE_SECTION),
        "solarus_mister": is_enabled(SOLARUS_SECTION),
        "three_s_arm": is_enabled(THREE_S_ARM_SECTION),
        "mister_frontier": is_enabled(MISTER_FRONTIER_SECTION),
        "mister_frontier_source": "All Frontier Cores",

        "arcade_org": arcade_org_ini_enabled or json_data.get("introduced_arcade_names_txt", False),

        "mrext": is_enabled("mrext/all"),
        "sam": is_enabled("MiSTer_SAM_files"),
        "tty2oled": is_enabled("tty2oled_files"),
        "i2c2oled": is_enabled("i2c2oled_files"),
        "retrospy": is_enabled("retrospy/retrospy-MiSTer"),
        "zaparoo": is_enabled(ZAPAROO_SECTION),
        "zaparoo_frontend": _mister_ini_text_has_zaparoo_launcher_entries(mister_ini),
        "test_suite_240p": is_enabled(TEST_SUITE_240P_SECTION),
        "mister_hifi": is_enabled(MISTER_HIFI_SECTION),
        "misterfin": is_enabled(MISTERFIN_SECTION),

        "bios": is_enabled("bios_db"),
        "arcade_roms": is_enabled("arcade_roms_db"),
        "bootroms": is_enabled("uberyoji_mister_boot_roms_mgl"),
        "gbaborders": is_enabled("Dinierto/MiSTer-GBA-Borders"),
        "anime0t4ku_wallpapers": is_enabled("anime0t4ku_wallpapers"),
        "pcn_challenge_wallpapers": is_enabled("pcn_challenge_wallpapers"),
        "anime0t4ku_mister_scripts": is_enabled("anime0t4ku_mister_scripts"),
        "manualsdb": bool(manualsdb_selected),
        "manualsdb_selected": manualsdb_selected,

        "ranny_wallpapers": is_enabled("Ranny-Snice/Ranny-Snice-Wallpapers"),
        "ranny_wallpapers_source": "All Wallpapers",
    }

    if "aitorgomez.net" in ini_data:
        data["main_source"] = "AitorGomez fork"
    elif "MiSTer-DB9" in ini_data:
        data["main_source"] = "DB9 / SNAC8 forks with ENCC"

    if data["mister_frontier"]:
        filter_value = extract_section_value(
            ini_data,
            MISTER_FRONTIER_SECTION,
            "filter",
        )
        data["mister_frontier_source"] = MISTER_FRONTIER_FILTER_LABELS.get(
            filter_value,
            "All Frontier Cores",
        )

    if data["ranny_wallpapers"]:
        if "filter = ar16-9" in ini_data:
            data["ranny_wallpapers_source"] = "16:9 Wallpapers"
        elif "filter = ar4-3" in ini_data:
            data["ranny_wallpapers_source"] = "4:3 Wallpapers"

    return data


def load_update_all_config(connection):
    sftp = connection.client.open_sftp()
    try:
        ensure_split_downloader_configs(sftp)

        files = read_downloader_files(sftp)
        ini_data = "\n".join([
            files["main"],
            files["arcade"],
            files["bios"],
        ])

        try:
            with sftp.open(JSON_PATH, "r") as f:
                raw = f.read()
                if isinstance(raw, bytes):
                    raw = raw.decode()
                json_data = json.loads(raw)
        except Exception:
            json_data = {}

        arcade_org_ini = read_remote_text(sftp, ARCADE_ORGANIZER_INI_PATH, "")
        mister_ini = read_remote_text(sftp, MISTER_INI_PATH, "")

        data = _build_config_data(
            ini_data,
            json_data,
            arcade_org_ini,
            files["manualsdb"],
            mister_ini,
        )
        data["custom_sources"], data["custom_sources_unmanaged_text"] = (
            _load_custom_sources_data(
                read_remote_text(sftp, CUSTOM_SOURCES_INI_PATH, ""),
                read_custom_sources_metadata(),
            )
        )
        return data
    finally:
        sftp.close()


def load_update_all_config_local(sd_root):
    ensure_split_downloader_configs_local(sd_root)

    files = read_downloader_files_local(sd_root)
    ini_data = "\n".join([
        files["main"],
        files["arcade"],
        files["bios"],
    ])

    try:
        json_data = json.loads(read_local_text(sd_root, JSON_PATH, "{}"))
    except Exception:
        json_data = {}

    arcade_org_ini = read_local_text(sd_root, ARCADE_ORGANIZER_INI_PATH, "")
    mister_ini = read_local_text(sd_root, MISTER_INI_PATH, "")

    data = _build_config_data(
        ini_data,
        json_data,
        arcade_org_ini,
        files["manualsdb"],
        mister_ini,
    )
    data["custom_sources"], data["custom_sources_unmanaged_text"] = (
        _load_custom_sources_data(
            read_local_text(sd_root, CUSTOM_SOURCES_INI_PATH, ""),
            read_custom_sources_metadata(),
        )
    )
    return data


def normalize_ini_lines(lines):
    lines = list(lines)

    while lines and not lines[0].strip():
        lines.pop(0)

    while lines and not lines[-1].strip():
        lines.pop()

    normalized = []
    previous_blank = False

    for line in lines:
        is_blank = not line.strip()
        if is_blank and previous_blank:
            continue
        normalized.append(line)
        previous_blank = is_blank

    return normalized


def handle_simple_section(section, enabled, lines, content_lines):
    lines = remove_section_from_lines(lines, section)

    while lines and not lines[0].strip():
        lines.pop(0)

    while lines and not lines[-1].strip():
        lines.pop()

    if enabled:
        if lines:
            lines += [""] + content_lines
        else:
            lines += content_lines

    return lines


def handle_mister_frontier_section(enabled, source, lines):
    lines = remove_section_from_lines(lines, MISTER_FRONTIER_SECTION)

    while lines and not lines[0].strip():
        lines.pop(0)

    while lines and not lines[-1].strip():
        lines.pop()

    if not enabled:
        return lines

    filter_value = MISTER_FRONTIER_FILTERS.get(source, "")

    content_lines = [
        f"[{MISTER_FRONTIER_SECTION}]",
        f"db_url = {MISTER_FRONTIER_DB_URL}",
    ]

    if filter_value:
        content_lines.append(f"filter = {filter_value}")

    if lines:
        lines += [""] + content_lines
    else:
        lines += content_lines

    return lines


def _prepare_config_lines_and_json(config, main_lines, arcade_lines, bios_lines, json_data):
    json_data["download_beta_cores"] = bool(config.get("jt_beta", False))
    json_data["introduced_arcade_names_txt"] = bool(config.get("arcade_org", False))

    main_lines = remove_section_from_lines(main_lines, "distribution_mister")
    if config.get("main_cores"):
        source = config.get("main_source", "MiSTer-devel (Recommended)")
        if "AitorGomez" in source:
            url = "https://www.aitorgomez.net/static/mistermain/db.json.zip"
        elif "DB9" in source:
            url = "https://raw.githubusercontent.com/MiSTer-DB9/Distribution_MiSTer/main/dbencc.json.zip"
        else:
            url = "https://raw.githubusercontent.com/MiSTer-devel/Distribution_MiSTer/main/db.json.zip"

        if main_lines and main_lines[-1].strip():
            main_lines += [""]

        main_lines += [
            "[distribution_mister]",
            f"db_url = {url}",
        ]

    main_lines = remove_section_from_lines(main_lines, "jtcores")
    if config.get("jtcores"):
        if main_lines and main_lines[-1].strip():
            main_lines += [""]

        main_lines += [
            "[jtcores]",
            "db_url = https://raw.githubusercontent.com/jotego/jtcores_mister/main/jtbindb.json.zip",
            "filter = [MiSTer]",
        ]

    main_lines = handle_simple_section(
        "Coin-OpCollection/Distribution-MiSTerFPGA",
        config.get("coinop", False),
        main_lines,
        [
            "[Coin-OpCollection/Distribution-MiSTerFPGA]",
            "db_url = https://raw.githubusercontent.com/Coin-OpCollection/Distribution-MiSTerFPGA/db/db.json.zip",
        ],
    )
    main_lines = handle_simple_section(
        "arcade_offset_folder",
        config.get("arcade_offset", False),
        main_lines,
        [
            "[arcade_offset_folder]",
            "db_url = https://raw.githubusercontent.com/Toryalai1/Arcade_Offset/db/arcadeoffsetdb.json.zip",
        ],
    )
    main_lines = handle_simple_section(
        "llapi_folder",
        config.get("llapi", False),
        main_lines,
        [
            "[llapi_folder]",
            "db_url = https://raw.githubusercontent.com/MiSTer-LLAPI/LLAPI_folder_MiSTer/main/llapidb.json.zip",
        ],
    )
    main_lines = handle_simple_section(
        "theypsilon_unofficial_distribution",
        config.get("unofficial", False),
        main_lines,
        [
            "[theypsilon_unofficial_distribution]",
            "db_url = https://raw.githubusercontent.com/theypsilon/Distribution_Unofficial_MiSTer/main/unofficialdb.json.zip",
        ],
    )
    main_lines = handle_simple_section(
        "MikeS11/YC_Builds-MiSTer",
        config.get("yc", False),
        main_lines,
        [
            "[MikeS11/YC_Builds-MiSTer]",
            "db_url = https://raw.githubusercontent.com/MikeS11/YC_Builds-MiSTer/db/db.json.zip",
        ],
    )
    main_lines = handle_simple_section(
        "agg23_db",
        config.get("agg23", False),
        main_lines,
        [
            "[agg23_db]",
            "db_url = https://raw.githubusercontent.com/agg23/mister-repository/db/manifest.json",
        ],
    )
    main_lines = handle_simple_section(
        "ajgowans/alt-cores",
        config.get("altcores", False),
        main_lines,
        [
            "[ajgowans/alt-cores]",
            "db_url = https://raw.githubusercontent.com/ajgowans/alt-cores/db/db.json.zip",
        ],
    )
    main_lines = handle_simple_section(
        "TheJesusFish/Dual-Ram-Console-Cores",
        config.get("dualram", False),
        main_lines,
        [
            "[TheJesusFish/Dual-Ram-Console-Cores]",
            "db_url = https://raw.githubusercontent.com/TheJesusFish/Dual-Ram-Console-Cores/db/db.json.zip",
        ],
    )

    for section, key, url in [
        (PHYSICAL_DISC_SECTION, "physical_disc", PHYSICAL_DISC_DB_URL),
        (PAPRIUM_SECTION, "paprium_megadrive", PAPRIUM_DB_URL),
        (MMS2_GB_SECTION, "mms2_gb_core", MMS2_GB_DB_URL),
        (MEGAVGMD_SECTION, "megavgmdrive", MEGAVGMD_DB_URL),
        (DREAMSTER_SECTION, "dreamster", DREAMSTER_DB_URL),
        (SONIC_MANIA_SECTION, "sonic_mania_mister", SONIC_MANIA_DB_URL),
        (DUKE3D_SECTION, "mister_duke3d", DUKE3D_DB_URL),
        (QUAKE_SECTION, "mister_quake", QUAKE_DB_URL),
        (SOLARUS_SECTION, "solarus_mister", SOLARUS_DB_URL),
        (THREE_S_ARM_SECTION, "three_s_arm", THREE_S_ARM_DB_URL),
    ]:
        main_lines = handle_simple_section(
            section,
            config.get(key, False),
            main_lines,
            [f"[{section}]", f"db_url = {url}"],
        )

    main_lines = handle_mister_frontier_section(
        config.get("mister_frontier", False),
        config.get("mister_frontier_source", "All Frontier Cores"),
        main_lines,
    )

    main_lines = handle_simple_section(
        RETROACHIEVEMENTS_CORES_SECTION,
        config.get("retroachievements_cores", False),
        main_lines,
        [
            f"[{RETROACHIEVEMENTS_CORES_SECTION}]",
            f"db_url = {RETROACHIEVEMENTS_CORES_DB_URL}",
        ],
    )

    main_lines = handle_simple_section(
        "mrext/all",
        config.get("mrext", False),
        main_lines,
        [
            "[mrext/all]",
            "db_url = https://raw.githubusercontent.com/wizzomafizzo/mrext/main/releases/all.json",
        ],
    )
    main_lines = handle_simple_section(
        "MiSTer_SAM_files",
        config.get("sam", False),
        main_lines,
        [
            "[MiSTer_SAM_files]",
            "db_url = https://raw.githubusercontent.com/mrchrisster/MiSTer_SAM/db/db.json.zip",
        ],
    )
    main_lines = handle_simple_section(
        "tty2oled_files",
        config.get("tty2oled", False),
        main_lines,
        [
            "[tty2oled_files]",
            "db_url = https://raw.githubusercontent.com/venice1200/MiSTer_tty2oled/main/tty2oleddb.json",
        ],
    )
    main_lines = handle_simple_section(
        "i2c2oled_files",
        config.get("i2c2oled", False),
        main_lines,
        [
            "[i2c2oled_files]",
            "db_url = https://raw.githubusercontent.com/venice1200/MiSTer_i2c2oled/main/i2c2oleddb.json",
        ],
    )
    main_lines = handle_simple_section(
        "retrospy/retrospy-MiSTer",
        config.get("retrospy", False),
        main_lines,
        [
            "[retrospy/retrospy-MiSTer]",
            "db_url = https://raw.githubusercontent.com/retrospy/retrospy-MiSTer/db/db.json.zip",
        ],
    )
    main_lines = handle_simple_section(
        ZAPAROO_SECTION,
        config.get("zaparoo", False),
        main_lines,
        [
            f"[{ZAPAROO_SECTION}]",
            f"db_url = {ZAPAROO_DB_URL}",
        ],
    )
    main_lines = handle_simple_section(
        "anime0t4ku_mister_scripts",
        config.get("anime0t4ku_mister_scripts", False),
        main_lines,
        [
            "[anime0t4ku_mister_scripts]",
            "db_url = https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/db/db/scripts.json.zip",
        ],
    )
    for section, key, url in [
        (TEST_SUITE_240P_SECTION, "test_suite_240p", TEST_SUITE_240P_DB_URL),
        (MISTER_HIFI_SECTION, "mister_hifi", MISTER_HIFI_DB_URL),
        (MISTERFIN_SECTION, "misterfin", MISTERFIN_DB_URL),
    ]:
        main_lines = handle_simple_section(
            section,
            config.get(key, False),
            main_lines,
            [f"[{section}]", f"db_url = {url}"],
        )

    bios_lines = remove_section_from_lines(bios_lines, "bios_db")
    if config.get("bios"):
        if bios_lines and bios_lines[-1].strip():
            bios_lines += [""]

        bios_lines += [
            "[bios_db]",
            "db_url = https://raw.githubusercontent.com/ajgowans/BiosDB_MiSTer/db/bios_db.json.zip",
        ]

    arcade_lines = remove_section_from_lines(arcade_lines, "arcade_roms_db")
    if config.get("arcade_roms"):
        if arcade_lines and arcade_lines[-1].strip():
            arcade_lines += [""]

        arcade_lines += [
            "[arcade_roms_db]",
            "db_url = https://raw.githubusercontent.com/zakk4223/ArcadeROMsDB_MiSTer/db/arcade_roms_db.json.zip",
        ]

    main_lines = remove_section_from_lines(main_lines, "bios_db")
    main_lines = remove_section_from_lines(main_lines, "arcade_roms_db")

    main_lines = handle_simple_section(
        "uberyoji_mister_boot_roms_mgl",
        config.get("bootroms", False),
        main_lines,
        [
            "[uberyoji_mister_boot_roms_mgl]",
            "db_url = https://raw.githubusercontent.com/uberyoji/mister-boot-roms/main/db/uberyoji_mister_boot_roms_mgl.json",
        ],
    )
    main_lines = handle_simple_section(
        "Dinierto/MiSTer-GBA-Borders",
        config.get("gbaborders", False),
        main_lines,
        [
            "[Dinierto/MiSTer-GBA-Borders]",
            "db_url = https://raw.githubusercontent.com/Dinierto/MiSTer-GBA-Borders/db/db.json.zip",
        ],
    )
    main_lines = handle_simple_section(
        "anime0t4ku_wallpapers",
        config.get("anime0t4ku_wallpapers", False),
        main_lines,
        [
            "[anime0t4ku_wallpapers]",
            "db_url = https://raw.githubusercontent.com/Anime0t4ku/MiSTerWallpapers/db/db/0t4kuwallpapers.json.zip",
        ],
    )
    main_lines = handle_simple_section(
        "pcn_challenge_wallpapers",
        config.get("pcn_challenge_wallpapers", False),
        main_lines,
        [
            "[pcn_challenge_wallpapers]",
            "db_url = https://raw.githubusercontent.com/Anime0t4ku/MiSTerWallpapers/db/db/pcnchallenge.json.zip",
        ],
    )

    main_lines = remove_section_from_lines(main_lines, "Ranny-Snice/Ranny-Snice-Wallpapers")
    if config.get("ranny_wallpapers"):
        source = config.get("ranny_wallpapers_source", "All Wallpapers")

        if "16:9" in source:
            filter_value = "ar16-9"
        elif "4:3" in source:
            filter_value = "ar4-3"
        else:
            filter_value = "all"

        if main_lines and main_lines[-1].strip():
            main_lines += [""]

        main_lines += [
            "[Ranny-Snice/Ranny-Snice-Wallpapers]",
            "db_url = https://raw.githubusercontent.com/Ranny-Snice/Ranny-Snice-Wallpapers/db/db.json.zip",
            f"filter = {filter_value}",
        ]

    main_lines = normalize_ini_lines(main_lines)
    arcade_lines = normalize_ini_lines(arcade_lines)
    bios_lines = normalize_ini_lines(bios_lines)

    return main_lines, arcade_lines, bios_lines, json_data


def _apply_zaparoo_frontend_mister_ini_text(text, enabled):
    if enabled:
        return _patch_mister_ini_for_zaparoo_launcher(text)
    return _remove_zaparoo_launcher_from_mister_ini(text)


def _save_remote_zaparoo_frontend_state(sftp, enabled):
    current = read_remote_text(sftp, MISTER_INI_PATH, "")

    if not current and not enabled:
        return

    patched = _apply_zaparoo_frontend_mister_ini_text(current, enabled)
    current_normalized = current.replace("\r\n", "\n").replace("\r", "\n")

    if patched != current_normalized:
        write_remote_text(sftp, MISTER_INI_PATH, patched)


def _save_local_zaparoo_frontend_state(sd_root, enabled):
    current = read_local_text(sd_root, MISTER_INI_PATH, "")

    if not current and not enabled:
        return

    patched = _apply_zaparoo_frontend_mister_ini_text(current, enabled)
    current_normalized = current.replace("\r\n", "\n").replace("\r", "\n")

    if patched != current_normalized:
        write_local_text(sd_root, MISTER_INI_PATH, patched)


def _prepare_manualsdb_ini(config):
    if not config.get("manualsdb", False):
        return ""

    selected = normalize_manualsdb_selected(config.get("manualsdb_selected", []))

    if not selected:
        selected = list(MANUALSDB_IDS)

    return build_manualsdb_ini(selected)


def save_update_all_config(connection, config):
    sftp = connection.client.open_sftp()
    try:
        ensure_split_downloader_configs(sftp)

        paths = split_downloader_paths()

        main_lines = read_remote_text(sftp, paths["main"], "").splitlines()
        arcade_lines = read_remote_text(sftp, paths["arcade"], "").splitlines()
        bios_lines = read_remote_text(sftp, paths["bios"], "").splitlines()

        try:
            with sftp.open(JSON_PATH, "r") as f:
                raw = f.read()
                if isinstance(raw, bytes):
                    raw = raw.decode()
                json_data = json.loads(raw)
        except Exception:
            json_data = {}

        if config.get("arcade_org", False):
            write_remote_text(
                sftp,
                ARCADE_ORGANIZER_INI_PATH,
                "ARCADE_ORGANIZER=true\nSKIPALTS=false\n"
            )
        else:
            remove_remote_file(sftp, ARCADE_ORGANIZER_INI_PATH)

        main_lines, arcade_lines, bios_lines, json_data = _prepare_config_lines_and_json(
            config,
            main_lines,
            arcade_lines,
            bios_lines,
            json_data,
        )

        paths = split_downloader_paths()
        write_remote_text(sftp, paths["main"], "\n".join(main_lines).rstrip() + "\n")
        write_remote_text(sftp, paths["arcade"], "\n".join(arcade_lines).rstrip() + "\n")
        write_remote_text(sftp, paths["bios"], "\n".join(bios_lines).rstrip() + "\n")

        manualsdb_ini = _prepare_manualsdb_ini(config)
        if manualsdb_ini:
            write_remote_text(sftp, paths["manualsdb"], manualsdb_ini)
        else:
            remove_remote_file(sftp, paths["manualsdb"])

        custom_ini, custom_metadata = _prepare_custom_sources_files(config)
        if custom_ini:
            write_remote_text(sftp, CUSTOM_SOURCES_INI_PATH, custom_ini)
        else:
            remove_remote_file(sftp, CUSTOM_SOURCES_INI_PATH)
        write_custom_sources_metadata(custom_metadata)

        _save_remote_zaparoo_frontend_state(
            sftp,
            bool(config.get("zaparoo_frontend", False)),
        )

        with sftp.open(JSON_PATH, "w") as f:
            f.write(json.dumps(json_data, indent=4))
    finally:
        sftp.close()


def save_update_all_config_local(sd_root, config):
    ensure_split_downloader_configs_local(sd_root)

    paths = split_downloader_paths()

    main_lines = read_local_text(sd_root, paths["main"], "").splitlines()
    arcade_lines = read_local_text(sd_root, paths["arcade"], "").splitlines()
    bios_lines = read_local_text(sd_root, paths["bios"], "").splitlines()

    try:
        json_data = json.loads(read_local_text(sd_root, JSON_PATH, "{}"))
    except Exception:
        json_data = {}

    if config.get("arcade_org", False):
        write_local_text(
            sd_root,
            ARCADE_ORGANIZER_INI_PATH,
            "ARCADE_ORGANIZER=true\nSKIPALTS=false\n"
        )
    else:
        remove_local_file(sd_root, ARCADE_ORGANIZER_INI_PATH)

    main_lines, arcade_lines, bios_lines, json_data = _prepare_config_lines_and_json(
        config,
        main_lines,
        arcade_lines,
        bios_lines,
        json_data,
    )

    write_local_text(sd_root, paths["main"], "\n".join(main_lines).rstrip() + "\n")
    write_local_text(sd_root, paths["arcade"], "\n".join(arcade_lines).rstrip() + "\n")
    write_local_text(sd_root, paths["bios"], "\n".join(bios_lines).rstrip() + "\n")

    manualsdb_ini = _prepare_manualsdb_ini(config)
    if manualsdb_ini:
        write_local_text(sd_root, paths["manualsdb"], manualsdb_ini)
    else:
        remove_local_file(sd_root, paths["manualsdb"])

    custom_ini, custom_metadata = _prepare_custom_sources_files(config)
    if custom_ini:
        write_local_text(sd_root, CUSTOM_SOURCES_INI_PATH, custom_ini)
    else:
        remove_local_file(sd_root, CUSTOM_SOURCES_INI_PATH)
    write_custom_sources_metadata(custom_metadata)

    _save_local_zaparoo_frontend_state(
        sd_root,
        bool(config.get("zaparoo_frontend", False)),
    )

    write_local_text(sd_root, JSON_PATH, json.dumps(json_data, indent=4))

from pathlib import Path


IMAGE_SOURCES = {
    "Titlescreen": {
        "id": "titlescreen",
        "screenscraper_media": "sstitle",
        "folder": "media/images",
    },
    "Screenshot": {
        "id": "screenshot",
        "screenscraper_media": "ss",
        "folder": "media/images",
    },
    "2D Boxart": {
        "id": "box2d",
        "screenscraper_media": "box-2D",
        "folder": "media/images",
    },
    "Game Logo": {
        "id": "logo",
        "screenscraper_media": "wheel",
        "folder": "media/images",
    },
    "3D Boxart": {
        "id": "box3d",
        "screenscraper_media": "box-3D",
        "folder": "media/images",
    },
}


OUTPUT_FORMAT_RECALBOX = "recalbox"
OUTPUT_FORMAT_ZAPAROO_COMPANION = "zaparoo_companion"


OUTPUT_FORMATS = {
    "Recalbox Compatible": OUTPUT_FORMAT_RECALBOX,
    "Zaparoo Companion": OUTPUT_FORMAT_ZAPAROO_COMPANION,
}


ZAPAROO_COMPANION_MEDIA_SOURCES = {
    "Screenshot": {
        "id": "screenshot",
        "screenscraper_media": "ss",
        "folder": "media/screenshot",
        "xml_node": "screenshot",
    },
    "Title Screen": {
        "id": "titlescreen",
        "screenscraper_media": "sstitle",
        "folder": "media/titlescreen",
        "xml_node": "titlescreen",
    },
    "2D Boxart": {
        "id": "box2d",
        "screenscraper_media": "box-2D",
        "folder": "media/box2d",
        "xml_node": "boxart2d",
    },
    "3D Boxart": {
        "id": "box3d",
        "screenscraper_media": "box-3D",
        "folder": "media/box3d",
        "xml_node": "boxart3d",
    },
    "Game Logo": {
        "id": "logo",
        "screenscraper_media": "wheel",
        "folder": "media/logo",
        "xml_node": "logo",
    },
}


DEFAULT_ZAPAROO_COMPANION_MEDIA_SOURCES = [
    "Screenshot",
    "2D Boxart",
    "Game Logo",
]


REGIONS = {
    "Auto": "auto",
    "USA": "us",
    "Japan": "jp",
    "Europe": "eu",
}


REGION_TAGS = {
    "USA": "us",
    "U": "us",
    "US": "us",
    "NTSC-U": "us",
    "JAPAN": "jp",
    "J": "jp",
    "JP": "jp",
    "NTSC-J": "jp",
    "EUROPE": "eu",
    "EUR": "eu",
    "E": "eu",
    "EU": "eu",
    "PAL": "eu",
}


SUPPORTED_SYSTEMS = {
    "3DO": {
        "label": "3DO",
        "screenscraper_id": 29,
        "extensions": [".iso", ".cue", ".chd", ".bin", ".zip", ".7z"],
    },
    "Arcadia": {
        "label": "Arcadia 2001",
        "screenscraper_id": 94,
        "extensions": [".bin", ".zip", ".7z"],
    },
    "Astrocade": {
        "label": "Bally Astrocade",
        "screenscraper_id": 44,
        "extensions": [".bin", ".zip", ".7z"],
    },
    "Atari2600": {
        "label": "Atari 2600",
        "screenscraper_id": 26,
        "extensions": [".a26", ".bin", ".rom", ".zip", ".7z"],
    },
    "Atari5200": {
        "label": "Atari 5200",
        "screenscraper_id": 40,
        "extensions": [".a52", ".bin", ".rom", ".zip", ".7z"],
    },
    "Atari7800": {
        "label": "Atari 7800",
        "screenscraper_id": 41,
        "extensions": [".a78", ".bin", ".rom", ".zip", ".7z"],
    },
    "AtariLynx": {
        "label": "Atari Lynx",
        "screenscraper_id": 28,
        "extensions": [".lnx", ".lyx", ".bin", ".zip", ".7z"],
    },
    "AY-3-8500": {
        "label": "AY-3-8500",
        "screenscraper_id": 0,
        "extensions": [".bin", ".rom", ".zip", ".7z"],
    },
    "CD-i": {
        "label": "CD-i",
        "screenscraper_id": 133,
        "extensions": [".cue", ".chd", ".iso", ".bin", ".zip", ".7z"],
    },
    "ChannelF": {
        "label": "Channel F",
        "screenscraper_id": 80,
        "extensions": [".bin", ".rom", ".zip", ".7z"],
    },
    "Coleco": {
        "label": "ColecoVision",
        "screenscraper_id": 48,
        "extensions": [".col", ".rom", ".bin", ".zip", ".7z"],
    },
    "CreatiVision": {
        "label": "CreatiVision",
        "screenscraper_id": 241,
        "extensions": [".bin", ".rom", ".zip", ".7z"],
    },
    "EpochGalaxyII": {
        "label": "Epoch Galaxy II",
        "screenscraper_id": 0,
        "extensions": [".bin", ".rom", ".zip", ".7z"],
    },
    "FDS": {
        "label": "Famicom Disk System",
        "screenscraper_id": 106,
        "extensions": [".fds", ".zip", ".7z"],
    },
    "GAMEBOY": {
        "label": "Game Boy",
        "screenscraper_id": 9,
        "extensions": [".gb", ".zip", ".7z"],
    },
    "GAMEBOY2P": {
        "label": "Game Boy 2P",
        "screenscraper_id": 9,
        "extensions": [".gb", ".zip", ".7z"],
    },
    "GameGear": {
        "label": "Game Gear",
        "screenscraper_id": 21,
        "extensions": [".gg", ".zip", ".7z"],
    },
    "GameNWatch": {
        "label": "Game & Watch",
        "screenscraper_id": 52,
        "extensions": [".gnw", ".zip", ".7z"],
    },
    "GBA": {
        "label": "Game Boy Advance",
        "screenscraper_id": 12,
        "extensions": [".gba", ".zip", ".7z"],
    },
    "GBA2P": {
        "label": "Game Boy Advance 2P",
        "screenscraper_id": 12,
        "extensions": [".gba", ".zip", ".7z"],
    },
    "GBC": {
        "label": "Game Boy Color",
        "screenscraper_id": 10,
        "extensions": [".gbc", ".zip", ".7z"],
    },
    "Genesis": {
        "label": "Genesis",
        "screenscraper_id": 1,
        "extensions": [".md", ".gen", ".bin", ".smd", ".zip", ".7z"],
    },
    "Intellivision": {
        "label": "Intellivision",
        "screenscraper_id": 115,
        "extensions": [".int", ".bin", ".rom", ".zip", ".7z"],
    },
    "Jaguar": {
        "label": "Atari Jaguar",
        "screenscraper_id": 27,
        "extensions": [".j64", ".jag", ".rom", ".bin", ".zip", ".7z"],
    },
    "Laser": {
        "label": "Laser",
        "screenscraper_id": 0,
        "extensions": [".bin", ".rom", ".zip", ".7z"],
    },
    "MegaCD": {
        "label": "Mega CD / Sega CD",
        "screenscraper_id": 20,
        "extensions": [".cue", ".chd", ".iso", ".m3u", ".bin", ".zip", ".7z"],
    },
    "MegaDrive": {
        "label": "Mega Drive",
        "screenscraper_id": 1,
        "extensions": [".md", ".gen", ".bin", ".smd", ".zip", ".7z"],
    },
    "MegaDuck": {
        "label": "Mega Duck",
        "screenscraper_id": 90,
        "extensions": [".bin", ".rom", ".zip", ".7z"],
    },
    "MyVision": {
        "label": "My Vision",
        "screenscraper_id": 305,
        "extensions": [".bin", ".rom", ".zip", ".7z"],
    },
    "N64": {
        "label": "Nintendo 64",
        "screenscraper_id": 14,
        "extensions": [".n64", ".z64", ".v64", ".zip", ".7z"],
    },
    "NEOGEO": {
        "label": "Neo Geo",
        "screenscraper_id": 142,
        "extensions": [".neo", ".zip", ".7z"],
    },
    "NeoGeo-CD": {
        "label": "Neo Geo CD",
        "screenscraper_id": 70,
        "extensions": [".cue", ".chd", ".iso", ".bin", ".zip", ".7z"],
    },
    "NeoGeoPocket": {
        "label": "Neo Geo Pocket",
        "screenscraper_id": 25,
        "extensions": [".ngp", ".ngc", ".zip", ".7z"],
    },
    "NES": {
        "label": "NES",
        "screenscraper_id": 3,
        "extensions": [".nes", ".fds", ".zip", ".7z"],
    },
    "ODYSSEY2": {
        "label": "Odyssey 2 / Videopac",
        "screenscraper_id": 104,
        "extensions": [".bin", ".rom", ".zip", ".7z"],
    },
    "PokemonMini": {
        "label": "Pokémon Mini",
        "screenscraper_id": 211,
        "extensions": [".min", ".bin", ".zip", ".7z"],
    },
    "PSX": {
        "label": "PlayStation",
        "screenscraper_id": 57,
        "extensions": [".cue", ".chd", ".pbp", ".iso", ".m3u", ".bin", ".zip", ".7z"],
    },
    "S32X": {
        "label": "32X",
        "screenscraper_id": 19,
        "extensions": [".32x", ".bin", ".md", ".zip", ".7z"],
    },
    "Saturn": {
        "label": "Saturn",
        "screenscraper_id": 22,
        "extensions": [".cue", ".chd", ".iso", ".m3u", ".bin", ".zip", ".7z"],
    },
    "SG1000": {
        "label": "SG-1000",
        "screenscraper_id": 109,
        "extensions": [".sg", ".sg1000", ".bin", ".rom", ".zip", ".7z"],
    },
    "SGB": {
        "label": "Super Game Boy",
        "screenscraper_id": 273,
        "extensions": [".gb", ".gbc", ".zip", ".7z"],
    },
    "SMS": {
        "label": "Master System",
        "screenscraper_id": 2,
        "extensions": [".sms", ".bin", ".rom", ".zip", ".7z"],
    },
    "SNES": {
        "label": "SNES",
        "screenscraper_id": 4,
        "extensions": [".sfc", ".smc", ".fig", ".bs", ".st", ".zip", ".7z"],
    },
    "SuperVision": {
        "label": "Watara Supervision",
        "screenscraper_id": 207,
        "extensions": [".sv", ".bin", ".rom", ".zip", ".7z"],
    },
    "SuperVision8000": {
        "label": "Super Vision 8000",
        "screenscraper_id": 0,
        "extensions": [".bin", ".rom", ".zip", ".7z"],
    },
    "TGFX16": {
        "label": "TurboGrafx-16 / PC Engine",
        "screenscraper_id": 31,
        "extensions": [".pce", ".zip", ".7z"],
    },
    "TGFX16-CD": {
        "label": "TurboGrafx-CD / PC Engine CD",
        "screenscraper_id": 114,
        "extensions": [".cue", ".chd", ".iso", ".m3u", ".bin", ".zip", ".7z"],
    },
    "VC4000": {
        "label": "VC 4000",
        "screenscraper_id": 281,
        "extensions": [".bin", ".rom", ".zip", ".7z"],
    },
    "Vectrex": {
        "label": "Vectrex",
        "screenscraper_id": 102,
        "extensions": [".vec", ".bin", ".rom", ".zip", ".7z"],
    },
    "Virtual Boy": {
        "label": "Virtual Boy",
        "screenscraper_id": 11,
        "extensions": [".vb", ".zip", ".7z"],
    },
    "WonderSwan": {
        "label": "WonderSwan",
        "screenscraper_id": 45,
        "extensions": [".ws", ".zip", ".7z"],
    },
    "WonderSwanColor": {
        "label": "WonderSwan Color",
        "screenscraper_id": 46,
        "extensions": [".wsc", ".ws", ".zip", ".7z"],
    },
}


DISC_HELPER_EXTENSIONS = {".bin", ".img", ".sub"}


def get_image_source_names():
    return list(IMAGE_SOURCES.keys())


def get_region_names():
    return list(REGIONS.keys())


def get_image_source_id(name: str) -> str:
    item = IMAGE_SOURCES.get(name)
    if not item:
        return IMAGE_SOURCES["2D Boxart"]["id"]
    return item["id"]


def get_image_source_media_type(name: str) -> str:
    item = IMAGE_SOURCES.get(name)
    if not item:
        return IMAGE_SOURCES["2D Boxart"]["screenscraper_media"]
    return item["screenscraper_media"]


def get_image_source_folder(name: str) -> str:
    item = IMAGE_SOURCES.get(name)
    if not item:
        return IMAGE_SOURCES["2D Boxart"]["folder"]
    return item["folder"]



def get_output_format_names():
    return list(OUTPUT_FORMATS.keys())


def get_output_format_id(name: str) -> str:
    return OUTPUT_FORMATS.get(name, OUTPUT_FORMAT_RECALBOX)


def get_output_format_name(format_id: str) -> str:
    for name, value in OUTPUT_FORMATS.items():
        if value == format_id:
            return name
    return "Recalbox Compatible"


def get_zaparoo_companion_media_names():
    return list(ZAPAROO_COMPANION_MEDIA_SOURCES.keys())


def get_default_zaparoo_companion_media_names():
    return list(DEFAULT_ZAPAROO_COMPANION_MEDIA_SOURCES)


def get_zaparoo_companion_media_info(name: str):
    return ZAPAROO_COMPANION_MEDIA_SOURCES.get(name)


def get_zaparoo_companion_media_id(name: str) -> str:
    item = get_zaparoo_companion_media_info(name)
    if not item:
        return ""
    return item["id"]


def get_zaparoo_companion_media_type(name: str) -> str:
    item = get_zaparoo_companion_media_info(name)
    if not item:
        return ""
    return item["screenscraper_media"]


def get_zaparoo_companion_media_folder(name: str) -> str:
    item = get_zaparoo_companion_media_info(name)
    if not item:
        return ""
    return item["folder"]


def get_zaparoo_companion_media_node(name: str) -> str:
    item = get_zaparoo_companion_media_info(name)
    if not item:
        return ""
    return item["xml_node"]


def get_region_code(name: str) -> str:
    return REGIONS.get(name, "auto")


def get_system_info(folder_name: str):
    return SUPPORTED_SYSTEMS.get(folder_name)


def get_supported_folder_names():
    return list(SUPPORTED_SYSTEMS.keys())


def is_supported_rom(system_folder: str, path: Path) -> bool:
    info = get_system_info(system_folder)
    if not info:
        return False

    if int(info.get("screenscraper_id") or 0) <= 0:
        return False

    suffix = path.suffix.lower()
    extensions = {ext.lower() for ext in info.get("extensions", [])}
    return suffix in extensions
"""RomM platform slug → MiSTer core folder mapping.

MiSTer stores game ROMs under ``/media/fat/games/<Core>/`` (per the MiSTer wiki:
https://mister-devel.github.io/MkDocs_MiSTer/setup/games/). Core folder names
don't match RomM's slugs, so we bundle a translation table.

Returns ``None`` for slugs with no known MiSTer core (Switch, PS3, GameCube,
Wii U, 3DS, etc.). The sync engine skips these with a warning; the browse UI
hides them behind a "Show unsupported" toggle.
"""
from __future__ import annotations

# The core folder name under /media/fat/games/. Multiple RomM slugs can map to
# the same MiSTer folder (e.g. TG-16 and PC Engine → TGFX16).
# Folder names cross-checked against a real MiSTer install (2026-07). Case is
# significant — MiSTer's paths are case-sensitive on the SD card's ext4.
_SLUG_TO_CORE: dict[str, str] = {
    # Nintendo
    "nes":              "NES",
    "famicom":          "NES",
    "fds":              "NES",             # Famicom Disk System uses the NES core
    "snes":             "SNES",
    "sfc":              "SNES",
    "super-famicom":    "SNES",
    "n64":              "N64",
    "gb":               "GAMEBOY",         # MiSTer folder is uppercase
    "gbc":              "GBC",             # dedicated folder on MiSTer
    "gba":              "GBA",
    "sgb":              "SGB",             # Super Game Boy
    "vb":               "VirtualBoy",
    "virtualboy":       "VirtualBoy",
    # Sega — MiSTer's core is named "MegaDrive" (international name), even for
    # RomM slugs that use "genesis" (US colloquial).
    "genesis-slash-megadrive": "MegaDrive",
    "genesis":          "MegaDrive",
    "megadrive":        "MegaDrive",
    "sms":              "SMS",
    "gg":               "GameGear",        # dedicated folder on MiSTer
    "gamegear":         "GameGear",
    "sg1000":           "SG-1000",
    "segacd":           "MegaCD",
    "sega-cd":          "MegaCD",
    "sega32x":          "S32X",
    "32x":              "S32X",
    "saturn":           "Saturn",
    # NEC
    "turbografx16-slash-pcengine": "TGFX16",
    "turbografx-16":    "TGFX16",
    "pcengine":         "TGFX16",
    "pce":              "TGFX16",
    "pcecd":            "TGFX16-CD",
    "turbografx-16-cd": "TGFX16-CD",
    # SNK
    "neogeoaes":        "NEOGEO",
    "neogeomvs":        "NEOGEO",
    "neogeocd":         "NeoGeo-CD",
    "neogeopocket":     "NeoGeoPocket",    # dedicated folder on MiSTer
    "ngp":              "NeoGeoPocket",
    "ngpc":             "NeoGeoPocket",
    # Sony
    "psx":              "PSX",
    "ps":               "PSX",
    "ps1":              "PSX",
    "playstation":      "PSX",
    # Atari
    "atari2600":        "Atari2600",       # dedicated standalone core folder
    "atari5200":        "ATARI5200",
    "atari7800":        "ATARI7800",
    "atari-lynx":       "AtariLynx",
    "lynx":             "AtariLynx",
    "atari8bit":        "ATARI800",
    "atari-8-bit":      "ATARI800",
    "jaguar":           "Jaguar",
    # Bandai
    "wonderswan":       "WonderSwan",
    "wonderswan-color": "WonderSwanColor",  # dedicated folder on MiSTer
    "wsc":              "WonderSwanColor",
    # Other consoles
    "colecovision":     "Coleco",
    "intellivision":    "Intellivision",
    "channel-f":        "ChannelF",
    "channelf":         "ChannelF",
    "odyssey--1":       "ODYSSEY2",
    "odyssey2":         "ODYSSEY2",
    "vectrex":          "VECTREX",
    "astrocade":        "Astrocade",
    "arcadia-2001":     "Arcadia",
    "arcadia":          "Arcadia",
    "megaduck":         "MegaDuck",
    "pokemon-mini":     "PokemonMini",
    "pokemonmini":      "PokemonMini",
    # Arcade — special (uses .mra files, mostly maintained via update_all)
    "arcade":           "_Arcade",
    "mame":             "_Arcade",
    # Home computers (RomM often lumps these under 'pc' etc.)
    "c64":              "C64",
    "commodore-c64":    "C64",
    "c128":             "C128",
    "vic-20":           "VIC20",
    "vic20":            "VIC20",
    "amiga":            "Amiga",
    "amstrad-cpc":      "Amstrad",
    "amstrad":          "Amstrad",
    "acorn-electron":   "AcornElectron",
    "bbc-micro":        "BBCMicro",
    "atari-st":         "AtariST",
    "atarist":          "AtariST",
    "msx":              "MSX",
    "msx2":             "MSX",              # MiSTer's MSX core plays MSX2
    "sinclair-zx81":    "ZX81",
    "zx81":             "ZX81",
    "sinclair-zx-spectrum": "Spectrum",
    "zxs":              "Spectrum",
    "zx-spectrum":      "Spectrum",
    "dos":              "AO486",             # DOS games via the ao486 core
    "pc-dos":           "AO486",
    "win3x":            "AO486",             # Windows 3.x runs on ao486
    "windows-3x":       "AO486",
    # NOTE: 'win' (Windows 95+) is intentionally NOT mapped — those releases
    # are too heavy for the ao486 core (limited RAM/CPU). RomM entries tagged
    # 'win' will show as unsupported.
    "coleco-adam":      "Adam",
    "adam":             "Adam",
    "trs-80":           "TRS-80",
}

# Slugs we deliberately mark unsupported (RomM has them; MiSTer has no core).
# Keeping this explicit — an unknown slug is silently unsupported too, but this
# list is what shows in "you have games for X platforms MiSTer can't run".
UNSUPPORTED_SLUGS: frozenset[str] = frozenset(
    {
        "3do", "3do-interactive-multiplayer",  # partial WIP, not usable
        "dc", "dreamcast",
        "gc", "ngc", "gamecube", "nintendo-gamecube",
        "wii", "nintendo-wii",
        "wiiu", "nintendo-wii-u",
        "switch", "nintendo-switch",
        "3ds", "nintendo-3ds", "new-nintendo-3ds",
        "nds", "nintendo-ds",
        "dsi", "nintendo-dsi",
        "ps2", "playstation-2",
        "ps3", "playstation-3",
        "ps4", "playstation-4",
        "ps5", "playstation-5",
        "psp", "playstation-portable",
        "psvita", "playstation-vita",
        "xbox",
        "xbox360", "xbox-360",
        "xboxone", "xbox-one",
        "series-x-s",
        "mac", "macintosh",
        "linux",
        "android",
        "ios",
        "browser",  # Flash / web games
        "mugen",
        "win",      # Windows 95+ is too heavy for ao486; deliberately unsupported.
        "windows",
    }
)


# User overrides applied at runtime via ``apply_overrides``. Keyed by lowercased
# slug; empty-string value explicitly disables a slug (renders unsupported).
_USER_OVERRIDES: dict[str, str] = {}


def apply_overrides(overrides: dict | None) -> None:
    """Replace the runtime override map. Call once at startup and after any edit."""
    global _USER_OVERRIDES
    if not isinstance(overrides, dict):
        _USER_OVERRIDES = {}
        return
    _USER_OVERRIDES = {
        str(k).lower().strip(): str(v or "").strip()
        for k, v in overrides.items()
        if k
    }


def core_folder_for_slug(slug: str | None) -> str | None:
    """Return the MiSTer /media/fat/games/<Core>/ folder name, or None if unsupported.

    User overrides take precedence over the built-in table. An override with an
    empty value disables the slug (returns None), useful for slugs whose default
    mapping is wrong for a specific MiSTer setup.
    """
    if not slug:
        return None
    key = slug.lower().strip()
    if key in _USER_OVERRIDES:
        return _USER_OVERRIDES[key] or None
    return _SLUG_TO_CORE.get(key)


def is_supported(slug: str | None) -> bool:
    return core_folder_for_slug(slug) is not None


def games_path(slug: str, filename: str = "", root: str = "/media/fat") -> str | None:
    """Full remote path for a ROM file, or None if slug is unsupported."""
    core = core_folder_for_slug(slug)
    if core is None:
        return None
    base = f"{root}/games/{core}"
    return f"{base}/{filename}" if filename else base


def saves_dir(slug: str, root: str = "/media/fat") -> str | None:
    """MiSTer SRAM save directory for a slug: /media/fat/saves/<Core>/."""
    core = core_folder_for_slug(slug)
    if core is None:
        return None
    return f"{root}/saves/{core}"


def states_dir(slug: str, root: str = "/media/fat") -> str | None:
    """MiSTer savestate directory for a slug: /media/fat/savestates/<Core>/."""
    core = core_folder_for_slug(slug)
    if core is None:
        return None
    return f"{root}/savestates/{core}"

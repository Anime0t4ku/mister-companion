import json


JSON_PATH = "/media/fat/Scripts/.config/update_all/update_all.json"


def split_downloader_paths():
    return {
        "main": "/media/fat/downloader.ini",
        "arcade": "/media/fat/downloader_arcade_roms_db.ini",
        "bios": "/media/fat/downloader_bios_db.ini",
    }


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


def read_downloader_files(sftp):
    paths = split_downloader_paths()
    return {
        "main": read_remote_text(sftp, paths["main"], ""),
        "arcade": read_remote_text(sftp, paths["arcade"], ""),
        "bios": read_remote_text(sftp, paths["bios"], ""),
    }


def remove_section_from_lines(lines, section):
    new_lines = []
    skip = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            skip = (stripped.strip("[]") == section)

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
                json_data = json.loads(f.read().decode())
        except Exception:
            json_data = {}

        def is_enabled(section):
            return section_enabled_in_text(ini_data, section)

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

            "arcade_org": json_data.get("introduced_arcade_names_txt", False),

            "mrext": is_enabled("mrext/all"),
            "sam": is_enabled("MiSTer_SAM_files"),
            "tty2oled": is_enabled("tty2oled_files"),
            "i2c2oled": is_enabled("i2c2oled_files"),
            "retrospy": is_enabled("retrospy/retrospy-MiSTer"),

            "bios": is_enabled("bios_db"),
            "arcade_roms": is_enabled("arcade_roms_db"),
            "bootroms": is_enabled("uberyoji_mister_boot_roms_mgl"),
            "gbaborders": is_enabled("Dinierto/MiSTer-GBA-Borders"),
            "insert_coin": is_enabled("funkycochise/Insert-Coin"),
            "anime0t4ku_wallpapers": is_enabled("anime0t4ku_wallpapers"),
            "pcn_challenge_wallpapers": is_enabled("pcn_challenge_wallpapers"),
            "anime0t4ku_mister_scripts": is_enabled("anime0t4ku_mister_scripts"),

            "ranny_wallpapers": is_enabled("Ranny-Snice/Ranny-Snice-Wallpapers"),
            "ranny_wallpapers_source": "All Wallpapers",
        }

        if "aitorgomez.net" in ini_data:
            data["main_source"] = "AitorGomez fork"
        elif "MiSTer-DB9" in ini_data:
            data["main_source"] = "DB9 / SNAC8 forks with ENCC"

        if data["ranny_wallpapers"]:
            if "filter = ar16-9" in ini_data:
                data["ranny_wallpapers_source"] = "16:9 Wallpapers"
            elif "filter = ar4-3" in ini_data:
                data["ranny_wallpapers_source"] = "4:3 Wallpapers"

        return data
    finally:
        sftp.close()


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
                json_data = json.loads(f.read().decode())
        except Exception:
            json_data = {}

        json_data["download_beta_cores"] = bool(config.get("jt_beta", False))
        json_data["introduced_arcade_names_txt"] = bool(config.get("arcade_org", False))

        # ===== main cores =====
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

        # ===== jtcores =====
        main_lines = remove_section_from_lines(main_lines, "jtcores")
        if config.get("jtcores"):
            if main_lines and main_lines[-1].strip():
                main_lines += [""]
            main_lines += [
                "[jtcores]",
                "db_url = https://raw.githubusercontent.com/jotego/jtcores_mister/main/jtbindb.json.zip",
                "filter = [MiSTer]",
            ]

        # ===== other cores =====
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

        # ===== tools & scripts =====
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

        # ===== extras in split files =====
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

        # never leave these in main
        main_lines = remove_section_from_lines(main_lines, "bios_db")
        main_lines = remove_section_from_lines(main_lines, "arcade_roms_db")

        # ===== other extras =====
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
            "funkycochise/Insert-Coin",
            config.get("insert_coin", False),
            main_lines,
            [
                "[funkycochise/Insert-Coin]",
                "db_url = https://raw.githubusercontent.com/funkycochise/Insert-Coin/db/db.json.zip",
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
        main_lines = handle_simple_section(
            "anime0t4ku_mister_scripts",
            config.get("anime0t4ku_mister_scripts", False),
            main_lines,
            [
                "[anime0t4ku_mister_scripts]",
                "db_url = https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/db/db/scripts.json.zip",
            ],
        )

        # ===== ranny wallpapers =====
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

        write_remote_text(sftp, paths["main"], "\n".join(main_lines).rstrip() + "\n")
        write_remote_text(sftp, paths["arcade"], "\n".join(arcade_lines).rstrip() + "\n")
        write_remote_text(sftp, paths["bios"], "\n".join(bios_lines).rstrip() + "\n")

        with sftp.open(JSON_PATH, "w") as f:
            f.write(json.dumps(json_data, indent=4))
    finally:
        sftp.close()
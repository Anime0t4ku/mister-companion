RESOLUTION_MAP = {
    "0": "1280x720@60",
    "1": "1024x768@60",
    "2": "720x480@60",
    "3": "720x576@50",
    "4": "1280x1024@60",
    "5": "800x600@60",
    "6": "640x480@60",
    "7": "1280x720@50",
    "8": "1920x1080@60",
    "9": "1920x1080@50",
    "10": "1366x768@60",
    "11": "1024x600@60",
    "12": "1920x1440@60",
    "13": "2048x1536@60",
    "14": "2560x1440@60",
}

RESOLUTION_REVERSE_MAP = {value: key for key, value in RESOLUTION_MAP.items()}

SCALING_MAP = {
    "0": "Disabled",
    "1": "Low Latency",
    "2": "Exact Refresh",
}

SCALING_REVERSE_MAP = {value: key for key, value in SCALING_MAP.items()}

DEFAULT_FONT_LINE = ";font=font/myfont.pf"

AMIGAVISION_PRESET_KEY = "__amigavision_preset"
MENU_CRT_PRESET_KEY = "__menu_crt_preset"

AMIGAVISION_PRESET_HEADER_LINES = [
    "[Amiga",
    "+Amiga500",
    "+Amiga500HD",
    "+Amiga600HD",
    "+AmigaCD32]",
]

AMIGAVISION_PRESET_BODY_LINES = [
    "video_mode_ntsc=8 ; These two use the recommended setting of 1080p60 and",
    "video_mode_pal=9  ; 1080p50, adjust if you want a different resolution",
    "vscale_mode=0",
    "vsync_adjust=1 ; You can set this to 2 if your display can handle it",
    "custom_aspect_ratio_1=40:27",
    "bootscreen=0",
]

AMIGAVISION_PRESET_BLOCK_LINES = (
    AMIGAVISION_PRESET_HEADER_LINES + AMIGAVISION_PRESET_BODY_LINES
)

MENU_CRT_PRESETS = {
    "NTSC, Large Text": [
        "[Menu]",
        "vga_scaler=1",
        "video_mode=384,16,37,63,224,10,3,24,7830",
    ],
    "NTSC, Small Text": [
        "[Menu]",
        "vga_scaler=1",
        "video_mode=640,30,60,70,240,4,4,14,12587",
    ],
    "PAL, Large Text": [
        "[Menu]",
        "vga_scaler=1",
        "video_mode=320,13,31,52,288,4,3,18,6510",
    ],
    "PAL, Small Text": [
        "[Menu]",
        "vga_scaler=1",
        "video_mode=640,30,60,70,288,6,4,14,12587",
    ],
}


def _normalized_line(line):
    return str(line or "").strip()


def _line_without_comment(line):
    line = str(line or "").strip()

    if ";" in line:
        line = line.split(";", 1)[0].strip()

    return line


def _is_section_start(line):
    stripped = _normalized_line(line)
    return stripped.startswith("[") and stripped != ""


def _is_single_line_section(line):
    stripped = _normalized_line(line)
    return stripped.startswith("[") and stripped.endswith("]")


def _is_mister_section_header(line):
    return _normalized_line(line) == "[MiSTer]"


def _is_menu_section_header(line):
    return _normalized_line(line) == "[Menu]"


def _is_amigavision_header_at(lines, index):
    if index < 0 or index >= len(lines):
        return False

    if index + len(AMIGAVISION_PRESET_HEADER_LINES) > len(lines):
        return False

    for offset, expected in enumerate(AMIGAVISION_PRESET_HEADER_LINES):
        if _normalized_line(lines[index + offset]) != expected:
            return False

    return True


def _amigavision_block_end_index(lines, start_index):
    index = start_index + len(AMIGAVISION_PRESET_HEADER_LINES)

    while index < len(lines):
        stripped = _normalized_line(lines[index])

        if index > start_index + len(AMIGAVISION_PRESET_HEADER_LINES) and _is_section_start(lines[index]):
            break

        index += 1

        if _line_without_comment(stripped) == "bootscreen=0":
            break

    return index


def _has_amigavision_preset(text):
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")

    index = 0
    while index < len(lines):
        if _is_amigavision_header_at(lines, index):
            block_end = _amigavision_block_end_index(lines, index)
            block_lines = lines[index:block_end]

            required_settings = {
                "video_mode_ntsc": "8",
                "video_mode_pal": "9",
                "vscale_mode": "0",
                "vsync_adjust": "1",
                "custom_aspect_ratio_1": "40:27",
                "bootscreen": "0",
            }

            found_settings = {}

            for line in block_lines:
                clean = _line_without_comment(line)
                if "=" not in clean:
                    continue

                key, value = clean.split("=", 1)
                found_settings[key.strip()] = value.strip()

            if all(found_settings.get(key) == value for key, value in required_settings.items()):
                return True

        index += 1

    return False


def _remove_existing_amigavision_preset_blocks(lines):
    cleaned_lines = []
    index = 0

    while index < len(lines):
        if _is_amigavision_header_at(lines, index):
            index = _amigavision_block_end_index(lines, index)

            while cleaned_lines and not cleaned_lines[-1].strip():
                cleaned_lines.pop()

            while index < len(lines) and not lines[index].strip():
                index += 1

            continue

        cleaned_lines.append(lines[index])
        index += 1

    return cleaned_lines


def _menu_section_bounds(lines):
    index = 0

    while index < len(lines):
        if _is_menu_section_header(lines[index]):
            start = index
            index += 1

            while index < len(lines):
                if _is_section_start(lines[index]):
                    break
                index += 1

            return start, index

        index += 1

    return None, None


def _read_section_settings(lines, start, end):
    settings = {}

    if start is None or end is None:
        return settings

    for line in lines[start + 1:end]:
        clean = _line_without_comment(line)

        if "=" not in clean:
            continue

        key, value = clean.split("=", 1)
        settings[key.strip()] = value.strip()

    return settings


def _detect_menu_crt_preset(text):
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    start, end = _menu_section_bounds(lines)

    if start is None:
        return "Disabled"

    settings = _read_section_settings(lines, start, end)

    if settings.get("vga_scaler") != "1":
        return "Disabled"

    video_mode = settings.get("video_mode", "")

    for preset_name, preset_lines in MENU_CRT_PRESETS.items():
        expected_video_mode = ""

        for line in preset_lines:
            clean = _line_without_comment(line)
            if clean.startswith("video_mode="):
                expected_video_mode = clean.split("=", 1)[1].strip()
                break

        if video_mode == expected_video_mode:
            return preset_name

    return "Disabled"


def _remove_existing_menu_section(lines):
    start, end = _menu_section_bounds(lines)

    if start is None or end is None:
        return lines

    cleaned_lines = lines[:start] + lines[end:]

    while cleaned_lines and not cleaned_lines[-1].strip():
        cleaned_lines.pop()

    return cleaned_lines


def parse_mister_ini(text):
    settings = {}
    text = str(text or "")

    settings["amigavision_preset"] = "Enabled" if _has_amigavision_preset(text) else "Disabled"
    settings["menu_crt_preset"] = _detect_menu_crt_preset(text)

    current_section = None

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if _is_section_start(line):
            if _is_mister_section_header(line):
                current_section = "MiSTer"
            elif _is_single_line_section(line):
                current_section = line[1:-1].strip()
            else:
                current_section = None
            continue

        if current_section != "MiSTer":
            continue

        if line.startswith(";"):
            comment_body = line[1:].strip()
            if "=" in comment_body:
                key, value = comment_body.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key == "font":
                    settings["font_commented"] = value
            continue

        if ";" in line:
            line = line.split(";", 1)[0].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        settings[key.strip()] = value.strip()

    return settings


def easy_mode_values_from_ini_settings(settings):
    values = {}

    direct_video = settings.get("direct_video", "0").strip()
    values["hdmi_mode"] = (
        "Direct Video (CRT / Scaler)"
        if direct_video in ("1", "2")
        else "HD Output (Default)"
    )

    video_mode = settings.get("video_mode", "").strip()
    values["resolution"] = RESOLUTION_MAP.get(video_mode, "1920x1080@60")

    values["scaling"] = SCALING_MAP.get(
        settings.get("vsync_adjust", "1").strip(),
        "Low Latency",
    )

    dvi = settings.get("dvi_mode", "0").strip()
    values["hdmi_audio"] = "Disabled (DVI Mode)" if dvi == "1" else "Enabled"

    hdr = settings.get("hdr", "0").strip()
    values["hdr"] = "Enabled" if hdr == "1" else "Disabled"

    limited = settings.get("hdmi_limited", "0").strip()
    values["hdmi_limited"] = "Limited Range" if limited == "1" else "Full Range"

    vga_mode = settings.get("vga_mode", "rgb").strip().lower()
    composite_sync = settings.get("composite_sync", "1").strip()
    vga_sog = settings.get("vga_sog", "0").strip()
    vga_scaler = settings.get("vga_scaler", "0").strip()
    forced_scandoubler = settings.get("forced_scandoubler", "0").strip()

    if (
        vga_mode == "rgb"
        and composite_sync == "1"
        and vga_sog == "0"
        and vga_scaler == "0"
        and forced_scandoubler == "0"
    ):
        values["analogue"] = "RGBS (SCART)"

    elif (
        vga_mode == "rgb"
        and composite_sync == "0"
        and vga_sog == "0"
        and vga_scaler == "0"
        and forced_scandoubler == "0"
    ):
        values["analogue"] = "RGBHV (VGA 15 kHz)"

    elif (
        vga_mode == "rgb"
        and composite_sync == "1"
        and vga_sog == "1"
        and vga_scaler == "0"
        and forced_scandoubler == "0"
    ):
        values["analogue"] = "RGsB (Sync-on-Green)"

    elif (
        vga_mode == "ypbpr"
        and composite_sync == "0"
        and vga_sog == "1"
        and vga_scaler == "0"
        and forced_scandoubler == "0"
    ):
        values["analogue"] = "YPbPr (Component)"

    elif (
        vga_mode == "svideo"
        and composite_sync == "1"
        and vga_sog == "0"
        and vga_scaler == "0"
        and forced_scandoubler == "0"
    ):
        values["analogue"] = "S-Video"

    elif (
        vga_mode == "cvbs"
        and composite_sync == "1"
        and vga_sog == "0"
        and vga_scaler == "0"
        and forced_scandoubler == "0"
    ):
        values["analogue"] = "Composite (CVBS)"

    elif (
        vga_mode == "rgb"
        and composite_sync == "0"
        and vga_sog == "0"
        and vga_scaler == "1"
        and forced_scandoubler == "0"
    ):
        values["analogue"] = "VGA Scaler (31 kHz+)"

    else:
        values["analogue"] = "Custom"

    logo = settings.get("logo", "1").strip()
    values["logo"] = "Disabled" if logo == "0" else "Enabled"

    font_value = settings.get("font", "").strip()
    if font_value.startswith("font/"):
        values["font"] = font_value.split("/", 1)[1].strip()
    else:
        values["font"] = "Default"

    values["amigavision_preset"] = settings.get("amigavision_preset", "Disabled")
    values["menu_crt_preset"] = settings.get("menu_crt_preset", "Disabled")

    return values


def build_easy_mode_settings(easy_values):
    settings = {}

    hdmi_mode = easy_values.get("hdmi_mode", "").strip()
    settings["direct_video"] = "1" if hdmi_mode == "Direct Video (CRT / Scaler)" else "0"

    resolution = easy_values.get("resolution", "").strip()
    if resolution in RESOLUTION_REVERSE_MAP:
        settings["video_mode"] = RESOLUTION_REVERSE_MAP[resolution]

    scaling = easy_values.get("scaling", "").strip()
    settings["vsync_adjust"] = SCALING_REVERSE_MAP.get(scaling, "1")

    audio = easy_values.get("hdmi_audio", "").strip()
    settings["dvi_mode"] = "0" if audio == "Enabled" else "1"

    hdr = easy_values.get("hdr", "").strip()
    settings["hdr"] = "1" if hdr == "Enabled" else "0"

    limited = easy_values.get("hdmi_limited", "").strip()
    settings["hdmi_limited"] = "1" if limited == "Limited Range" else "0"

    analogue = easy_values.get("analogue", "").strip()

    if analogue == "RGBS (SCART)":
        settings["vga_mode"] = "rgb"
        settings["composite_sync"] = "1"
        settings["vga_sog"] = "0"
        settings["vga_scaler"] = "0"
        settings["forced_scandoubler"] = "0"

    elif analogue == "RGBHV (VGA 15 kHz)":
        settings["vga_mode"] = "rgb"
        settings["composite_sync"] = "0"
        settings["vga_sog"] = "0"
        settings["vga_scaler"] = "0"
        settings["forced_scandoubler"] = "0"

    elif analogue == "RGsB (Sync-on-Green)":
        settings["vga_mode"] = "rgb"
        settings["composite_sync"] = "1"
        settings["vga_sog"] = "1"
        settings["vga_scaler"] = "0"
        settings["forced_scandoubler"] = "0"

    elif analogue == "YPbPr (Component)":
        settings["vga_mode"] = "ypbpr"
        settings["composite_sync"] = "0"
        settings["vga_sog"] = "1"
        settings["vga_scaler"] = "0"
        settings["forced_scandoubler"] = "0"

    elif analogue == "S-Video":
        settings["vga_mode"] = "svideo"
        settings["composite_sync"] = "1"
        settings["vga_sog"] = "0"
        settings["vga_scaler"] = "0"
        settings["forced_scandoubler"] = "0"

    elif analogue == "Composite (CVBS)":
        settings["vga_mode"] = "cvbs"
        settings["composite_sync"] = "1"
        settings["vga_sog"] = "0"
        settings["vga_scaler"] = "0"
        settings["forced_scandoubler"] = "0"

    elif analogue == "VGA Scaler (31 kHz+)":
        settings["vga_mode"] = "rgb"
        settings["composite_sync"] = "0"
        settings["vga_sog"] = "0"
        settings["vga_scaler"] = "1"
        settings["forced_scandoubler"] = "0"

    logo = easy_values.get("logo", "").strip()
    settings["logo"] = "1" if logo == "Enabled" else "0"

    font = easy_values.get("font", "").strip()
    if font and font != "Default":
        settings["font"] = f"font/{font}"
    else:
        settings["font_commented"] = "font/myfont.pf"

    amigavision_preset = easy_values.get("amigavision_preset", "Disabled").strip()
    settings[AMIGAVISION_PRESET_KEY] = (
        "Enabled" if amigavision_preset == "Enabled" else "Disabled"
    )

    menu_crt_preset = easy_values.get("menu_crt_preset", "Disabled").strip()
    settings[MENU_CRT_PRESET_KEY] = (
        menu_crt_preset if menu_crt_preset in MENU_CRT_PRESETS else "Disabled"
    )

    return settings


def _split_assignment_line(line):
    stripped = line.strip()
    commented = False

    if stripped.startswith(";"):
        commented = True
        stripped = stripped[1:].strip()

    if "=" not in stripped:
        return "", "", commented

    key, value = stripped.split("=", 1)
    return key.strip(), value.strip(), commented


def _line_indent(line):
    return line[: len(line) - len(line.lstrip())]


def _format_setting_line(existing_line, key, value, commented=False):
    indent = _line_indent(existing_line or "")
    prefix = ";" if commented else ""
    return f"{indent}{prefix}{key}={value}"


def _append_missing_settings(new_lines, updated_settings, replaced_keys):
    for key, value in updated_settings.items():
        if key.startswith("__"):
            continue

        if key in replaced_keys:
            continue

        if key == "font_commented":
            if "font" in replaced_keys or "font_commented" in replaced_keys:
                continue
            new_lines.append(DEFAULT_FONT_LINE)
            replaced_keys.add("font")
            replaced_keys.add("font_commented")
        else:
            new_lines.append(f"{key}={value}")
            replaced_keys.add(key)


def _append_amigavision_preset_block(new_lines, updated_settings):
    if updated_settings.get(AMIGAVISION_PRESET_KEY) != "Enabled":
        return

    if new_lines and new_lines[-1].strip():
        new_lines.append("")

    new_lines.extend(AMIGAVISION_PRESET_BLOCK_LINES)


def _append_menu_crt_preset_block(new_lines, updated_settings):
    preset_name = updated_settings.get(MENU_CRT_PRESET_KEY)

    if preset_name not in MENU_CRT_PRESETS:
        return

    if new_lines and new_lines[-1].strip():
        new_lines.append("")

    new_lines.extend(MENU_CRT_PRESETS[preset_name])


def update_mister_ini_text(ini_text, updated_settings):
    text = str(ini_text or "").replace("\r\n", "\n").replace("\r", "\n")
    had_trailing_newline = text.endswith("\n")

    lines = text.split("\n")

    if had_trailing_newline and lines and lines[-1] == "":
        lines = lines[:-1]

    if AMIGAVISION_PRESET_KEY in updated_settings:
        lines = _remove_existing_amigavision_preset_blocks(lines)

    if MENU_CRT_PRESET_KEY in updated_settings:
        lines = _remove_existing_menu_section(lines)

    new_lines = []
    in_mister_section = False
    found_mister_section = False
    replaced_keys = set()
    post_mister_blocks_inserted = False

    for line in lines:
        stripped = line.strip()

        if _is_section_start(stripped):
            if in_mister_section and not _is_mister_section_header(stripped):
                _append_missing_settings(new_lines, updated_settings, replaced_keys)

                if not post_mister_blocks_inserted:
                    _append_amigavision_preset_block(new_lines, updated_settings)
                    _append_menu_crt_preset_block(new_lines, updated_settings)
                    post_mister_blocks_inserted = True

                if new_lines and new_lines[-1].strip():
                    new_lines.append("")

            in_mister_section = _is_mister_section_header(stripped)

            if in_mister_section:
                found_mister_section = True

            new_lines.append(line)
            continue

        if in_mister_section:
            key, _value, commented = _split_assignment_line(line)

            if key:
                if key == "font":
                    if "font" in updated_settings:
                        new_lines.append(
                            _format_setting_line(
                                line,
                                "font",
                                updated_settings["font"],
                                commented=False,
                            )
                        )
                        replaced_keys.add("font")
                        replaced_keys.add("font_commented")
                        continue

                    if "font_commented" in updated_settings:
                        new_lines.append(DEFAULT_FONT_LINE)
                        replaced_keys.add("font")
                        replaced_keys.add("font_commented")
                        continue

                if key in updated_settings and key != "font_commented":
                    new_lines.append(
                        _format_setting_line(
                            line,
                            key,
                            updated_settings[key],
                            commented=False,
                        )
                    )
                    replaced_keys.add(key)
                    continue

        new_lines.append(line)

    if not found_mister_section:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")

        new_lines.append("[MiSTer]")
        _append_missing_settings(new_lines, updated_settings, replaced_keys)

        _append_amigavision_preset_block(new_lines, updated_settings)
        _append_menu_crt_preset_block(new_lines, updated_settings)

    elif in_mister_section:
        _append_missing_settings(new_lines, updated_settings, replaced_keys)

        if not post_mister_blocks_inserted:
            _append_amigavision_preset_block(new_lines, updated_settings)
            _append_menu_crt_preset_block(new_lines, updated_settings)

    return "\n".join(new_lines).rstrip("\n") + "\n"
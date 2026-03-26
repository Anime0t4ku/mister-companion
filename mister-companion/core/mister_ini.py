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


def parse_mister_ini(text):
    settings = {}
    current_section = None

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line or line.startswith(";"):
            continue

        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            continue

        if current_section != "MiSTer":
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
    composite_sync = settings.get("composite_sync", "0").strip()
    vga_sog = settings.get("vga_sog", "0").strip()

    if vga_mode == "ypbpr":
        values["analogue"] = "Component (YPbPr)"
    elif vga_mode == "svideo":
        values["analogue"] = "S-Video"
    elif vga_mode == "rgb":
        if vga_sog == "1":
            values["analogue"] = "RGB (PVM/BVM)"
        elif composite_sync == "1":
            values["analogue"] = "RGB (Consumer TV)"
        else:
            values["analogue"] = "VGA Monitor"
    else:
        values["analogue"] = "RGB (Consumer TV)"

    logo = settings.get("logo", "1").strip()
    values["logo"] = "Disabled" if logo == "0" else "Enabled"

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
    if analogue == "RGB (Consumer TV)":
        settings["vga_mode"] = "rgb"
        settings["composite_sync"] = "1"
        settings["vga_sog"] = "0"
    elif analogue == "RGB (PVM/BVM)":
        settings["vga_mode"] = "rgb"
        settings["composite_sync"] = "0"
        settings["vga_sog"] = "1"
    elif analogue == "Component (YPbPr)":
        settings["vga_mode"] = "ypbpr"
        settings["composite_sync"] = "0"
        settings["vga_sog"] = "0"
    elif analogue == "S-Video":
        settings["vga_mode"] = "svideo"
        settings["composite_sync"] = "0"
        settings["vga_sog"] = "0"
    elif analogue == "VGA Monitor":
        settings["vga_mode"] = "rgb"
        settings["composite_sync"] = "0"
        settings["vga_sog"] = "0"

    logo = easy_values.get("logo", "").strip()
    settings["logo"] = "1" if logo == "Enabled" else "0"

    return settings


def update_mister_ini_text(ini_text, updated_settings):
    lines = ini_text.splitlines()
    new_lines = []

    in_mister_section = False
    replaced_keys = set()
    found_mister_section = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            section_name = stripped[1:-1].strip()

            if in_mister_section and section_name != "MiSTer":
                for key, value in updated_settings.items():
                    if key not in replaced_keys:
                        new_lines.append(f"{key}={value}")

            in_mister_section = section_name == "MiSTer"
            if in_mister_section:
                found_mister_section = True

            new_lines.append(line)
            continue

        if in_mister_section:
            clean = stripped.lstrip(";").strip()

            if "=" in clean:
                key = clean.split("=", 1)[0].strip()
                if key in updated_settings:
                    new_lines.append(f"{key}={updated_settings[key]}")
                    replaced_keys.add(key)
                    continue

        new_lines.append(line)

    if not found_mister_section:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append("[MiSTer]")
        for key, value in updated_settings.items():
            new_lines.append(f"{key}={value}")
    elif in_mister_section:
        for key, value in updated_settings.items():
            if key not in replaced_keys:
                new_lines.append(f"{key}={value}")

    return "\n".join(new_lines) + "\n"
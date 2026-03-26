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
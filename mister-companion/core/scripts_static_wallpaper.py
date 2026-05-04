import os
import shlex

import requests

from core.scripts_common import (
    STATIC_WALLPAPER_CONFIG_DIR,
    STATIC_WALLPAPER_CONFIG_PATH,
    STATIC_WALLPAPER_DIR,
    STATIC_WALLPAPER_SCRIPT_PATH,
    STATIC_WALLPAPER_TARGET_JPG,
    STATIC_WALLPAPER_TARGET_PNG,
    _read_remote_bytes,
    _write_remote_bytes,
    ensure_remote_scripts_dir,
    reload_mister_menu,
)


STATIC_WALLPAPER_URL = "https://raw.githubusercontent.com/Anime0t4ku/0t4ku-mister-scripts/main/Scripts/static_wallpaper.sh"


def install_static_wallpaper(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log("Installing static_wallpaper...\n")
    script_data = requests.get(STATIC_WALLPAPER_URL, timeout=30).content

    ensure_remote_scripts_dir(connection)
    _write_remote_bytes(connection, STATIC_WALLPAPER_SCRIPT_PATH, script_data)

    connection.run_command(f"chmod +x {STATIC_WALLPAPER_SCRIPT_PATH}")
    connection.run_command(f"mkdir -p {STATIC_WALLPAPER_CONFIG_DIR}")
    log("static_wallpaper installed successfully.\n")


def uninstall_static_wallpaper(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    connection.run_command(f"rm -f {STATIC_WALLPAPER_SCRIPT_PATH}")
    connection.run_command(f"rm -rf {STATIC_WALLPAPER_CONFIG_DIR}")
    connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_JPG}")
    connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_PNG}")


def remove_static_wallpaper(connection, reload_menu=True):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_JPG}")
    connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_PNG}")
    connection.run_command("sync")

    if reload_menu:
        reload_mister_menu(connection)


def list_static_wallpapers(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    cmd = (
        f'find {STATIC_WALLPAPER_DIR} -maxdepth 1 -type f '
        r'\( -iname "*.png" -o -iname "*.jpg" -o -iname "*.jpeg" \) | sort'
    )
    output = connection.run_command(cmd)
    lines = [line.strip() for line in (output or "").splitlines() if line.strip()]

    wallpapers = []
    for path in lines:
        wallpapers.append(
            {
                "name": os.path.basename(path),
                "path": path,
            }
        )

    return wallpapers


def get_static_wallpaper_preview_bytes(connection, remote_path):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    if not remote_path:
        raise RuntimeError("No wallpaper path provided.")

    quoted_path = shlex.quote(remote_path)
    check = connection.run_command(f"test -f {quoted_path} && echo EXISTS")
    if "EXISTS" not in (check or ""):
        raise RuntimeError("Wallpaper file not found on MiSTer.")

    return _read_remote_bytes(connection, remote_path)


def apply_static_wallpaper(connection, wallpaper_path, reload_menu=True):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    if not wallpaper_path:
        raise RuntimeError("No wallpaper selected.")

    ext = os.path.splitext(wallpaper_path)[1].lower()
    quoted_src = shlex.quote(wallpaper_path)
    quoted_cfg = shlex.quote(STATIC_WALLPAPER_CONFIG_PATH)

    ensure_remote_scripts_dir(connection)

    exists_check = connection.run_command(f"test -f {quoted_src} && echo EXISTS")
    if "EXISTS" not in (exists_check or ""):
        raise RuntimeError("Selected wallpaper no longer exists on MiSTer.")

    if ext in {".jpg", ".jpeg"}:
        connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_PNG}")
        connection.run_command(f"cp {quoted_src} {STATIC_WALLPAPER_TARGET_JPG}")
        connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_PNG}")
    elif ext == ".png":
        connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_JPG}")
        connection.run_command(f"cp {quoted_src} {STATIC_WALLPAPER_TARGET_PNG}")
        connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_JPG}")
    else:
        raise RuntimeError("Unsupported wallpaper format. Use PNG, JPG, or JPEG.")

    connection.run_command(f"printf %s {quoted_src} > {quoted_cfg}")
    connection.run_command("sync")

    if reload_menu:
        reload_mister_menu(connection)
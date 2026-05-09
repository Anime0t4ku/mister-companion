import os
import shlex
import shutil
from pathlib import Path

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
MEDIA_FAT_PREFIX = "/media/fat"


def _local_sd_path(sd_root, remote_path: str) -> Path:
    sd_root = Path(sd_root)

    if not remote_path.startswith(MEDIA_FAT_PREFIX):
        raise RuntimeError(f"Unsupported MiSTer path: {remote_path}")

    relative = remote_path[len(MEDIA_FAT_PREFIX):].lstrip("/")
    return sd_root / relative


def _remote_style_path(local_path: Path, sd_root) -> str:
    sd_root = Path(sd_root)
    relative = local_path.relative_to(sd_root).as_posix()
    return f"{MEDIA_FAT_PREFIX}/{relative}"


def _ensure_local_static_wallpaper_dirs(sd_root):
    sd_root = Path(sd_root)
    _local_sd_path(sd_root, STATIC_WALLPAPER_CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    _local_sd_path(sd_root, STATIC_WALLPAPER_DIR).mkdir(parents=True, exist_ok=True)
    (sd_root / "Scripts").mkdir(parents=True, exist_ok=True)


def _download_static_wallpaper_script():
    response = requests.get(STATIC_WALLPAPER_URL, timeout=30)
    response.raise_for_status()
    return response.content


def _chmod_local_executable(path: Path):
    try:
        path.chmod(path.stat().st_mode | 0o755)
    except Exception:
        pass


def install_static_wallpaper(connection, log):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    log("Installing static_wallpaper...\n")
    script_data = _download_static_wallpaper_script()

    ensure_remote_scripts_dir(connection)
    _write_remote_bytes(connection, STATIC_WALLPAPER_SCRIPT_PATH, script_data)

    connection.run_command(f"chmod +x {STATIC_WALLPAPER_SCRIPT_PATH}")
    connection.run_command(f"mkdir -p {STATIC_WALLPAPER_CONFIG_DIR}")
    log("static_wallpaper installed successfully.\n")


def install_static_wallpaper_local(sd_root, log):
    log("Installing static_wallpaper to Offline SD Card...\n")
    script_data = _download_static_wallpaper_script()

    _ensure_local_static_wallpaper_dirs(sd_root)

    script_path = _local_sd_path(sd_root, STATIC_WALLPAPER_SCRIPT_PATH)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_bytes(script_data)
    _chmod_local_executable(script_path)

    log("static_wallpaper installed successfully.\n")
    log("Wallpaper selection is handled from the Wallpapers tab.\n")


def uninstall_static_wallpaper(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    connection.run_command(f"rm -f {STATIC_WALLPAPER_SCRIPT_PATH}")
    connection.run_command(f"rm -rf {STATIC_WALLPAPER_CONFIG_DIR}")
    connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_JPG}")
    connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_PNG}")


def uninstall_static_wallpaper_local(sd_root):
    script_path = _local_sd_path(sd_root, STATIC_WALLPAPER_SCRIPT_PATH)
    config_dir = _local_sd_path(sd_root, STATIC_WALLPAPER_CONFIG_DIR)
    jpg_path = _local_sd_path(sd_root, STATIC_WALLPAPER_TARGET_JPG)
    png_path = _local_sd_path(sd_root, STATIC_WALLPAPER_TARGET_PNG)

    if script_path.exists():
        script_path.unlink()

    if config_dir.exists():
        shutil.rmtree(config_dir)

    if jpg_path.exists():
        jpg_path.unlink()

    if png_path.exists():
        png_path.unlink()


def remove_static_wallpaper(connection, reload_menu=True):
    if not connection.is_connected():
        raise RuntimeError("Not connected to MiSTer.")

    connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_JPG}")
    connection.run_command(f"rm -f {STATIC_WALLPAPER_TARGET_PNG}")
    connection.run_command("sync")

    if reload_menu:
        reload_mister_menu(connection)


def remove_static_wallpaper_local(sd_root):
    jpg_path = _local_sd_path(sd_root, STATIC_WALLPAPER_TARGET_JPG)
    png_path = _local_sd_path(sd_root, STATIC_WALLPAPER_TARGET_PNG)

    if jpg_path.exists():
        jpg_path.unlink()

    if png_path.exists():
        png_path.unlink()


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


def list_static_wallpapers_local(sd_root):
    sd_root = Path(sd_root)
    wallpaper_dir = _local_sd_path(sd_root, STATIC_WALLPAPER_DIR)

    if not wallpaper_dir.exists():
        return []

    wallpapers = []

    for path in sorted(wallpaper_dir.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file():
            continue

        if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue

        wallpapers.append(
            {
                "name": path.name,
                "path": _remote_style_path(path, sd_root),
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


def get_static_wallpaper_preview_bytes_local(sd_root, remote_path):
    if not remote_path:
        raise RuntimeError("No wallpaper path provided.")

    path = _local_sd_path(sd_root, remote_path)

    if not path.exists():
        raise RuntimeError("Wallpaper file not found on local SD Card.")

    return path.read_bytes()


def get_static_wallpaper_state_local(sd_root) -> dict:
    script_path = _local_sd_path(sd_root, STATIC_WALLPAPER_SCRIPT_PATH)
    jpg_path = _local_sd_path(sd_root, STATIC_WALLPAPER_TARGET_JPG)
    png_path = _local_sd_path(sd_root, STATIC_WALLPAPER_TARGET_PNG)
    config_path = _local_sd_path(sd_root, STATIC_WALLPAPER_CONFIG_PATH)

    saved_path = ""
    if config_path.exists():
        try:
            saved_path = config_path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            saved_path = ""

    active_target = ""
    if jpg_path.exists():
        active_target = "menu.jpg"
    elif png_path.exists():
        active_target = "menu.png"

    return {
        "installed": script_path.exists(),
        "active": bool(active_target),
        "active_target": active_target,
        "saved": bool(saved_path),
        "saved_path": saved_path,
        "saved_name": os.path.basename(saved_path) if saved_path else "",
    }


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


def apply_static_wallpaper_local(sd_root, wallpaper_path):
    if not wallpaper_path:
        raise RuntimeError("No wallpaper selected.")

    _ensure_local_static_wallpaper_dirs(sd_root)

    source_path = _local_sd_path(sd_root, wallpaper_path)

    if not source_path.exists():
        raise RuntimeError("Selected wallpaper no longer exists on local SD Card.")

    ext = source_path.suffix.lower()

    target_jpg = _local_sd_path(sd_root, STATIC_WALLPAPER_TARGET_JPG)
    target_png = _local_sd_path(sd_root, STATIC_WALLPAPER_TARGET_PNG)
    config_path = _local_sd_path(sd_root, STATIC_WALLPAPER_CONFIG_PATH)

    target_jpg.parent.mkdir(parents=True, exist_ok=True)
    target_png.parent.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if ext in {".jpg", ".jpeg"}:
        if target_png.exists():
            target_png.unlink()
        shutil.copy2(source_path, target_jpg)
        if target_png.exists():
            target_png.unlink()
    elif ext == ".png":
        if target_jpg.exists():
            target_jpg.unlink()
        shutil.copy2(source_path, target_png)
        if target_jpg.exists():
            target_jpg.unlink()
    else:
        raise RuntimeError("Unsupported wallpaper format. Use PNG, JPG, or JPEG.")

    config_path.write_text(wallpaper_path, encoding="utf-8")
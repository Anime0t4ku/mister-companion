import os
import sys
from pathlib import Path


APP_SUPPORT_NAME = "MiSTer Companion"


def is_packaged_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_macos_packaged_app() -> bool:
    return sys.platform == "darwin" and is_packaged_app()


def is_appimage() -> bool:
    # APPIMAGE alone is not enough: it is inherited by every child process, so
    # a build launched from an AppImage-packaged terminal would see it too.
    # Confirm this executable really lives inside the AppImage mount.
    appdir = os.environ.get("APPDIR")
    if not os.environ.get("APPIMAGE") or not appdir:
        return False

    return Path(sys.executable).resolve().is_relative_to(Path(appdir).resolve())


def xdg_data_dir() -> Path:
    # The spec requires a relative XDG_DATA_HOME to be ignored. Honouring one
    # would make the data directory depend on the working directory, which
    # differs between a desktop launch and a terminal launch.
    xdg = Path(os.environ.get("XDG_DATA_HOME", ""))
    if not xdg.is_absolute():
        xdg = Path.home() / ".local" / "share"

    return xdg / APP_SUPPORT_NAME


def app_base_dir() -> Path:
    if is_packaged_app():
        # An AppImage mount is read-only, so sys.executable is not a usable
        # base. Use the standard user data directory, the same way the macOS
        # bundle uses Application Support.
        #
        # Writing beside the .AppImage instead would fight the format: the
        # AppImage runtime already provides portable mode, by redirecting
        # $HOME to a <name>.AppImage.home directory placed next to the file.
        # Honouring $HOME keeps that working and leaves the choice with the
        # user.
        if is_appimage():
            return xdg_data_dir()

        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent

    # A Linux distro package installs under a root-owned prefix such as
    # /usr/lib, /usr/share or /opt, where the portable layout cannot work.
    # Fall back rather than fail on the first write. A build extracted
    # somewhere writable keeps the portable behaviour unchanged.
    if sys.platform.startswith("linux") and not os.access(base, os.W_OK):
        return xdg_data_dir()

    return base


def macos_application_support_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / APP_SUPPORT_NAME


def generated_data_root(default_root=None, create: bool = True) -> Path:
    if is_macos_packaged_app():
        root = macos_application_support_dir()
    elif default_root is not None:
        root = Path(default_root)
    else:
        # Keep portable data beside the application. The process working
        # directory is not reliable, particularly when Windows launches the
        # packaged app from Start/Search.
        root = app_base_dir()

    if create:
        # Several modules build paths at import time, so raising here would
        # abort before there is a QApplication to report the failure with.
        # Let the first real write surface it instead.
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    return root


def generated_path(*parts, default_root=None) -> Path:
    return generated_data_root(default_root=default_root) / Path(*parts)


def install_center_cache_dir(create: bool = True) -> Path:
    if is_macos_packaged_app():
        root = macos_application_support_dir() / "ICCache"
    else:
        root = app_base_dir() / "ICCache"

    if create:
        root.mkdir(parents=True, exist_ok=True)

    return root

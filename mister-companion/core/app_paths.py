import sys
from pathlib import Path


APP_SUPPORT_NAME = "MiSTer Companion"


def is_packaged_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_macos_packaged_app() -> bool:
    return sys.platform == "darwin" and is_packaged_app()


def app_base_dir() -> Path:
    if is_packaged_app():
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


def macos_application_support_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / APP_SUPPORT_NAME


def generated_data_root(default_root=None, create: bool = True) -> Path:
    if is_macos_packaged_app():
        root = macos_application_support_dir()
    elif default_root is not None:
        root = Path(default_root)
    else:
        root = Path(".")

    if create:
        root.mkdir(parents=True, exist_ok=True)

    return root


def generated_path(*parts, default_root=None) -> Path:
    return generated_data_root(default_root=default_root) / Path(*parts)

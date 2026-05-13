import os
import shutil
import sys
from pathlib import Path
from shlex import quote


REMOTE_CIFS_DOCS_ROOT = "/media/fat/cifs/docs"
REMOTE_LOCAL_DOCS_ROOT = "/media/fat/docs"


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


def get_manuals_cache_root() -> Path:
    return app_base_dir() / "Manuals"


def ensure_manuals_cache_root() -> Path:
    root = get_manuals_cache_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def sanitize_name(name: str) -> str:
    value = (name or "").strip()
    value = value.replace("\\", "_").replace("/", "_").replace(":", "_")
    value = value.replace("*", "_").replace("?", "_").replace('"', "_")
    value = value.replace("<", "_").replace(">", "_").replace("|", "_")
    return value or "Unknown"


def is_pdf_name(filename: str) -> bool:
    return str(filename or "").lower().endswith(".pdf")


def scan_cached_systems():
    root = get_manuals_cache_root()

    if not root.exists():
        return []

    systems = []

    for system_dir in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not system_dir.is_dir():
            continue

        if system_dir.name.startswith("."):
            continue

        pdfs = scan_cached_pdfs(system_dir.name)

        if pdfs:
            systems.append(system_dir.name)

    return systems


def scan_cached_pdfs(system_name: str):
    system_dir = get_manuals_cache_root() / sanitize_name(system_name)

    if not system_dir.exists() or not system_dir.is_dir():
        return []

    pdfs = []

    for file_path in sorted(system_dir.iterdir(), key=lambda p: p.name.lower()):
        if file_path.is_file() and is_pdf_name(file_path.name):
            pdfs.append(
                {
                    "name": file_path.name,
                    "path": str(file_path),
                    "source": "cache",
                    "system": system_name,
                }
            )

    return pdfs


def has_cached_manuals() -> bool:
    return bool(scan_cached_systems())


def clear_manuals_cache():
    root = get_manuals_cache_root()

    if root.exists():
        shutil.rmtree(root)

    root.mkdir(parents=True, exist_ok=True)


def remove_cached_pdf(path):
    if not path:
        return

    try:
        file_path = Path(path)

        if file_path.exists() and file_path.is_file():
            file_path.unlink()

        parent = file_path.parent

        if parent.exists() and parent.is_dir():
            remaining_pdfs = [
                item
                for item in parent.iterdir()
                if item.is_file() and is_pdf_name(item.name)
            ]

            if not remaining_pdfs:
                try:
                    parent.rmdir()
                except OSError:
                    pass
    except Exception:
        pass


def open_cache_folder():
    root = ensure_manuals_cache_root()

    if sys.platform.startswith("win"):
        os.startfile(str(root))
        return

    if sys.platform == "darwin":
        os.system(f"open {quote(str(root))}")
        return

    os.system(f"xdg-open {quote(str(root))}")


def remote_path_exists(connection, path: str) -> bool:
    if not connection or not connection.is_connected():
        return False

    result = connection.run_command(
        f"test -d {quote(path)} && echo EXISTS || echo MISSING"
    )

    return "EXISTS" in result


def get_remote_docs_root(connection):
    if not connection or not connection.is_connected():
        return ""

    if remote_path_exists(connection, REMOTE_CIFS_DOCS_ROOT):
        return REMOTE_CIFS_DOCS_ROOT

    if remote_path_exists(connection, REMOTE_LOCAL_DOCS_ROOT):
        return REMOTE_LOCAL_DOCS_ROOT

    return ""


def scan_remote_systems(connection):
    root = get_remote_docs_root(connection)

    if not root:
        return []

    command = (
        f"find {quote(root)} -mindepth 2 -maxdepth 2 "
        f"-type d -name Manuals -printf '%h\\n' 2>/dev/null"
    )

    output = connection.run_command(command)
    systems = []

    for line in output.splitlines():
        line = line.strip()

        if not line:
            continue

        system_name = line.rstrip("/").split("/")[-1]

        if system_name and system_name not in systems:
            systems.append(system_name)

    return sorted(systems, key=str.lower)


def get_remote_manuals_dir(connection, system_name: str):
    root = get_remote_docs_root(connection)

    if not root:
        return ""

    manuals_dir = f"{root}/{system_name}/Manuals"

    if remote_path_exists(connection, manuals_dir):
        return manuals_dir

    return ""


def scan_remote_pdfs(connection, system_name: str):
    manuals_dir = get_remote_manuals_dir(connection, system_name)

    if not manuals_dir:
        return []

    command = (
        f"find {quote(manuals_dir)} -maxdepth 1 -type f "
        f"\\( -iname '*.pdf' \\) -printf '%f\\n' 2>/dev/null"
    )

    output = connection.run_command(command)
    pdfs = []

    for line in output.splitlines():
        filename = line.strip()

        if not filename or not is_pdf_name(filename):
            continue

        pdfs.append(
            {
                "name": filename,
                "path": f"{manuals_dir}/{filename}",
                "source": "remote",
                "system": system_name,
            }
        )

    return sorted(pdfs, key=lambda item: item["name"].lower())


def get_cached_pdf_path(system_name: str, filename: str):
    system_dir = ensure_manuals_cache_root() / sanitize_name(system_name)
    system_dir.mkdir(parents=True, exist_ok=True)
    return system_dir / sanitize_name(filename)


def get_temp_pdf_path(system_name: str, filename: str):
    system_dir = ensure_manuals_cache_root() / ".viewer_temp" / sanitize_name(system_name)
    system_dir.mkdir(parents=True, exist_ok=True)
    return system_dir / sanitize_name(filename)


def cache_remote_pdf(
    connection,
    system_name: str,
    remote_path: str,
    filename: str,
    keep_cached: bool = True,
):
    if not connection or not connection.is_connected():
        raise RuntimeError("Not connected")

    if keep_cached:
        local_path = get_cached_pdf_path(system_name, filename)
    else:
        local_path = get_temp_pdf_path(system_name, filename)

    temp_path = local_path.with_suffix(local_path.suffix + ".tmp")

    if temp_path.exists():
        try:
            temp_path.unlink()
        except Exception:
            pass

    sftp = connection.client.open_sftp()

    try:
        sftp.get(remote_path, str(temp_path))
    finally:
        sftp.close()

    if not temp_path.exists() or temp_path.stat().st_size <= 0:
        try:
            temp_path.unlink()
        except Exception:
            pass
        raise RuntimeError("Downloaded PDF is empty or missing.")

    temp_path.replace(local_path)

    return local_path


def merge_systems(remote_systems, cached_systems):
    systems = []

    for name in remote_systems + cached_systems:
        if name not in systems:
            systems.append(name)

    return sorted(systems, key=str.lower)


def merge_pdfs(remote_pdfs, cached_pdfs):
    merged = []
    seen = set()

    for item in remote_pdfs + cached_pdfs:
        key = item["name"].lower()

        if key in seen:
            continue

        seen.add(key)
        merged.append(item)

    return sorted(merged, key=lambda item: item["name"].lower())
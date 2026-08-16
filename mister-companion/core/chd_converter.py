from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests

from core.app_paths import generated_path

CHDMAN_VERSION = "0.289.0"
CHDMAN_DIR = generated_path("tools", "chdman", default_root=Path(__file__).resolve().parent.parent)


class ChdmanError(RuntimeError):
    pass


def _platform_package() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arm64 = machine in {"arm64", "aarch64"}
    if system == "windows":
        return "chdman-win32-arm64" if arm64 else "chdman-win32-x64"
    if system == "darwin":
        return "chdman-darwin-arm64" if arm64 else "chdman-darwin-x64"
    if system == "linux":
        return "chdman-linux-arm64" if arm64 else "chdman-linux-x64"
    raise ChdmanError(f"Unsupported platform: {platform.system()} {platform.machine()}")


def package_base_url() -> str:
    package = _platform_package()
    return f"https://raw.githubusercontent.com/emmercm/chdman-js/main/packages/{package}"


def chdman_executable() -> Path:
    return CHDMAN_DIR / ("chdman.exe" if os.name == "nt" else "chdman")


def has_chdman() -> bool:
    return chdman_executable().is_file()


def _download_file(url: str, target: Path, progress_callback=None, progress_base=0, progress_span=100):
    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()
    total = int(response.headers.get("content-length", 0) or 0)
    done = 0
    with target.open("wb") as handle:
        for chunk in response.iter_content(1024 * 256):
            if not chunk:
                continue
            handle.write(chunk)
            done += len(chunk)
            if progress_callback and total:
                progress_callback(progress_base + int((done / total) * progress_span), 100)


def download_chdman(progress_callback=None) -> Path:
    CHDMAN_DIR.mkdir(parents=True, exist_ok=True)
    base = package_base_url()

    metadata = requests.get(base + "/package.json", timeout=30)
    metadata.raise_for_status()
    published_version = str(metadata.json().get("version", ""))
    if published_version != CHDMAN_VERSION:
        raise ChdmanError(
            f"Expected CHDman package {CHDMAN_VERSION}, but chdman-js currently provides {published_version or 'an unknown version'}. "
            "MiSTer Companion will not silently download a different CHDman build."
        )

    wanted = ["chdman.exe" if os.name == "nt" else "chdman"]
    if platform.system().lower() == "darwin":
        wanted.append("libSDL3.0.dylib")

    for index, name in enumerate(wanted):
        span = max(1, 100 // len(wanted))
        _download_file(base + "/" + name, CHDMAN_DIR / name, progress_callback, index * span, span)

    # Keep the third-party license with the downloaded tool when possible.
    try:
        _download_file(
            "https://raw.githubusercontent.com/emmercm/chdman-js/main/LICENSE",
            CHDMAN_DIR / "LICENSE.chdman-js.txt",
        )
    except Exception:
        pass

    exe = chdman_executable()
    if not exe.exists():
        raise ChdmanError("CHDman executable was not found after download.")
    if os.name != "nt":
        exe.chmod(exe.stat().st_mode | 0o755)
    if progress_callback:
        progress_callback(100, 100)
    return exe


def remove_chdman() -> None:
    if CHDMAN_DIR.exists():
        shutil.rmtree(CHDMAN_DIR)


def descriptor_references(path: str | Path) -> list[str]:
    path = Path(path)
    ext = path.suffix.lower()
    text = path.read_text(encoding="utf-8", errors="ignore")
    refs: list[str] = []
    if ext == ".cue":
        for line in text.splitlines():
            match = re.match(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))', line, re.IGNORECASE)
            if match:
                refs.append(match.group(1) or match.group(2))
    elif ext == ".gdi":
        for line in text.splitlines()[1:]:
            match = re.match(r'^\s*\d+\s+\d+\s+\d+\s+\d+\s+(?:"([^"]+)"|(\S+))', line)
            if match:
                refs.append(match.group(1) or match.group(2))
    return refs


def default_output_name(input_path: str | Path) -> str:
    path = Path(str(input_path).replace("\\", "/"))
    return path.with_suffix(".chd").name


def conversion_kind(input_path: str | Path) -> str:
    ext = Path(str(input_path)).suffix.lower()
    if ext in {".cue", ".gdi"}:
        return "cd"
    if ext == ".iso":
        return "dvd"
    raise ChdmanError("Supported CHD inputs are CUE, GDI and ISO.")


def run_chdman(input_path: str | Path, output_path: str | Path, log_callback=None) -> list[Path]:
    exe = chdman_executable()
    if not exe.exists():
        raise ChdmanError("CHDman is not downloaded yet.")
    input_path = Path(input_path)
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(f"Output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    kind = conversion_kind(input_path)
    if kind == "cd":
        command = [str(exe), "createcd", "-i", str(input_path), "-o", str(output_path)]
    else:
        command = [str(exe), "createdvd", "-i", str(input_path), "-o", str(output_path)]
    outputs = [output_path]

    env = os.environ.copy()
    if platform.system().lower() == "darwin":
        # chdman-js rewrites its dylib references to @executable_path. Keeping cwd
        # and all dylibs in CHDMAN_DIR preserves that bundle layout.
        env["DYLD_LIBRARY_PATH"] = str(CHDMAN_DIR) + (os.pathsep + env["DYLD_LIBRARY_PATH"] if env.get("DYLD_LIBRARY_PATH") else "")
    proc = subprocess.Popen(
        command,
        cwd=str(CHDMAN_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        if log_callback:
            log_callback(line.rstrip())
    code = proc.wait()
    if code != 0:
        raise ChdmanError(f"CHDman exited with code {code}.")
    return outputs


def extract_chdman(input_path: str | Path, output_dir: str | Path, output_format: str, log_callback=None) -> list[Path]:
    """Extract a CHD to a user-selected supported disc-image format.

    output_format is one of: cue, gdi, iso.  Extraction always happens in
    output_dir; callers can then move/upload the complete output set.
    """
    exe = chdman_executable()
    if not exe.exists():
        raise ChdmanError("CHDman is not downloaded yet.")

    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fmt = output_format.strip().lower()
    if fmt not in {"cue", "gdi", "iso"}:
        raise ChdmanError("Supported CHD extraction formats are CUE/BIN, GDI and ISO.")

    stem = input_path.stem
    before = {p.resolve() for p in output_dir.iterdir()}
    if fmt == "cue":
        descriptor = output_dir / f"{stem}.cue"
        binary = output_dir / f"{stem}.bin"
        command = [str(exe), "extractcd", "-i", str(input_path), "-o", str(descriptor), "-ob", str(binary)]
    elif fmt == "gdi":
        descriptor = output_dir / f"{stem}.gdi"
        command = [str(exe), "extractcd", "-i", str(input_path), "-o", str(descriptor)]
    else:
        descriptor = output_dir / f"{stem}.iso"
        command = [str(exe), "extractdvd", "-i", str(input_path), "-o", str(descriptor)]

    if descriptor.exists():
        raise FileExistsError(f"Output already exists: {descriptor}")

    env = os.environ.copy()
    if platform.system().lower() == "darwin":
        env["DYLD_LIBRARY_PATH"] = str(CHDMAN_DIR) + (os.pathsep + env["DYLD_LIBRARY_PATH"] if env.get("DYLD_LIBRARY_PATH") else "")
    proc = subprocess.Popen(
        command, cwd=str(CHDMAN_DIR), env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        if log_callback:
            log_callback(line.rstrip())
    code = proc.wait()
    if code != 0:
        raise ChdmanError(f"CHDman exited with code {code}.")

    outputs = [p for p in output_dir.iterdir() if p.resolve() not in before and p.is_file()]
    if not outputs and descriptor.exists():
        outputs = [descriptor]
    return sorted(outputs, key=lambda path: path.name.lower())

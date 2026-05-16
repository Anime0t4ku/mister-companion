import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def clean_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()

    if platform.system() in {"Linux", "Darwin"}:
        original_ld_library_path = env.get("LD_LIBRARY_PATH_ORIG")

        if original_ld_library_path is not None:
            if original_ld_library_path:
                env["LD_LIBRARY_PATH"] = original_ld_library_path
            else:
                env.pop("LD_LIBRARY_PATH", None)
        else:
            env.pop("LD_LIBRARY_PATH", None)

        for key in (
            "LD_PRELOAD",
            "QT_PLUGIN_PATH",
            "QML2_IMPORT_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH",
            "QTWEBENGINEPROCESS_PATH",
            "QTWEBENGINE_RESOURCES_PATH",
            "QTWEBENGINE_LOCALES_PATH",
            "PYTHONHOME",
            "PYTHONPATH",
        ):
            env.pop(key, None)

    return env


def _run_open_command(command: list[str], timeout: int = 8) -> tuple[bool, str]:
    exe = command[0]

    if shutil.which(exe) is None:
        return False, f"{exe} is not installed."

    try:
        process = subprocess.Popen(
            command,
            env=clean_subprocess_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )

        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            return True, ""

        if process.returncode == 0:
            return True, ""

        error = (stderr or stdout or "").strip()
        return False, error or f"{exe} returned exit code {process.returncode}."

    except Exception as e:
        return False, str(e)


def open_local_folder(path):
    folder = Path(str(path or "")).expanduser().resolve()

    if not folder.exists() or not folder.is_dir():
        raise ValueError("The selected folder does not exist.")

    folder_path = str(folder)

    if sys.platform.startswith("win"):
        os.startfile(folder_path)
        return

    if sys.platform == "darwin":
        ok, error = _run_open_command(["open", folder_path])
        if not ok:
            raise RuntimeError(error)
        return

    if sys.platform.startswith("linux"):
        commands = [
            ["xdg-open", folder_path],
            ["gio", "open", folder_path],
            ["kde-open", folder_path],
            ["kde-open6", folder_path],
            ["kde-open5", folder_path],
            ["kioclient", "exec", folder_path],
            ["kioclient6", "exec", folder_path],
            ["kioclient5", "exec", folder_path],
        ]

        errors = []

        for command in commands:
            ok, error = _run_open_command(command)
            if ok:
                return
            if error:
                errors.append(f"{' '.join(command[:2])}: {error}")

        raise RuntimeError(
            "Unable to open the folder with the available Linux desktop helpers.\n\n"
            + "\n".join(errors)
        )

    raise RuntimeError(f"Unsupported platform: {sys.platform}")


def open_uri(uri: str):
    uri = str(uri or "").strip()

    if not uri:
        raise ValueError("No URI was provided.")

    if sys.platform.startswith("win"):
        if uri.startswith("smb://"):
            uri = uri.replace("smb://", "\\\\").replace("/", "\\")
        subprocess.Popen(["explorer", uri])
        return

    if sys.platform == "darwin":
        ok, error = _run_open_command(["open", uri])
        if not ok:
            raise RuntimeError(error)
        return

    if sys.platform.startswith("linux"):
        commands = [
            ["xdg-open", uri],
            ["gio", "open", uri],
            ["kde-open", uri],
            ["kde-open6", uri],
            ["kde-open5", uri],
            ["kioclient", "exec", uri],
            ["kioclient6", "exec", uri],
            ["kioclient5", "exec", uri],
        ]

        errors = []

        for command in commands:
            ok, error = _run_open_command(command)
            if ok:
                return
            if error:
                errors.append(f"{' '.join(command[:2])}: {error}")

        raise RuntimeError(
            "Unable to open the location with the available Linux desktop helpers.\n\n"
            + "\n".join(errors)
        )

    raise RuntimeError(f"Unsupported platform: {sys.platform}")


def open_smb_share(ip: str, share_path: str = ""):
    ip = str(ip or "").strip()
    share_path = str(share_path or "").strip("/")

    if not ip:
        raise ValueError("No MiSTer IP address is available.")

    if sys.platform.startswith("win"):
        path = f"\\\\{ip}\\"
        if share_path:
            path += share_path.replace("/", "\\")
        subprocess.Popen(["explorer", path])
        return

    if sys.platform.startswith("linux"):
        base_uri = f"smb://{ip}/"
        uri = base_uri + share_path if share_path else base_uri

        if shutil.which("gio") is not None:
            try:
                subprocess.run(
                    ["gio", "mount", base_uri],
                    env=clean_subprocess_env(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=8,
                )
            except Exception:
                pass

        open_uri(uri)
        return

    if sys.platform == "darwin":
        uri = f"smb://{ip}/"
        if share_path:
            uri += share_path
        open_uri(uri)
        return

    raise RuntimeError(f"Unsupported platform: {sys.platform}")

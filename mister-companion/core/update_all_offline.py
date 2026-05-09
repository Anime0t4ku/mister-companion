from __future__ import annotations

import contextlib
import json
import os
import re
import runpy
import shutil
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ProgressCallback = Callable[[str], None]


_DOWNLOADER_URL = "https://github.com/MiSTer-devel/Downloader_MiSTer/releases/download/latest/downloader.zip"


@dataclass
class OfflineUpdateResult:
    ok: bool = True
    databases_found: int = 0
    databases_processed: int = 0
    folders_created: int = 0
    files_downloaded: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    archives_downloaded: int = 0
    archives_skipped: int = 0
    errors: list[str] = field(default_factory=list)


def run_update_all_offline(
    sd_root: str | Path,
    progress: ProgressCallback | None = None,
) -> OfflineUpdateResult:
    runner = UpdateAllOfflineRunner(sd_root=sd_root, progress=progress)
    return runner.run()


class _ProgressStream:
    def __init__(
        self,
        line_callback: Callable[[str], None],
    ) -> None:
        self.line_callback = line_callback
        self.buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0

        self.buffer += str(text)

        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line:
                self.line_callback(line)

        if "\r" in self.buffer:
            parts = self.buffer.split("\r")
            for line in parts[:-1]:
                line = line.strip()
                if line:
                    self.line_callback(line)
            self.buffer = parts[-1]

        return len(text)

    def flush(self) -> None:
        if self.buffer.strip():
            self.line_callback(self.buffer.strip())
        self.buffer = ""


class _SignalPatch:
    def __init__(self) -> None:
        self.original_signal = signal.signal
        self.original_getsignal = signal.getsignal

    def __enter__(self):
        def safe_signal(signalnum, handler):
            try:
                return self.original_signal(signalnum, handler)
            except ValueError:
                return self.original_getsignal(signalnum)

        signal.signal = safe_signal
        return self

    def __exit__(self, exc_type, exc, tb):
        signal.signal = self.original_signal


class UpdateAllOfflineRunner:
    def __init__(
        self,
        sd_root: str | Path,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.sd_root = Path(sd_root).expanduser().resolve()
        self.progress = progress or (lambda message: None)
        self.result = OfflineUpdateResult()

        self.config_dir = self.sd_root / "Scripts" / ".config" / "mister_companion"
        self.cache_dir = self.config_dir / "offline_downloader_cache"
        self.state_path = self.config_dir / "offline_update_state.json"
        self.state: dict[str, Any] = {}

    def run(self) -> OfflineUpdateResult:
        try:
            self._validate_sd_root()
            self._prepare_dirs()
            self.state = self._load_state()

            self._log("Starting update_all offline via official Downloader PC flow...")
            self._run_official_downloader()

            self._run_arcade_organizer_if_enabled()

            self.state["last_successful_run"] = int(time.time())
            self._save_state()

            self._log("Offline update finished.")
        except Exception as exc:
            self.result.ok = False
            self.result.errors.append(str(exc))
            self._log(f"ERROR: {exc}")

        return self.result

    def _validate_sd_root(self) -> None:
        if not self.sd_root.exists():
            raise FileNotFoundError(f"SD root does not exist: {self.sd_root}")

        if not self.sd_root.is_dir():
            raise NotADirectoryError(f"SD root is not a folder: {self.sd_root}")

    def _prepare_dirs(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}

        try:
            with self.state_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)

            if isinstance(data, dict):
                return data
        except Exception:
            pass

        return {}

    def _save_state(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)

        with self.state_path.open("w", encoding="utf-8") as handle:
            json.dump(self.state, handle, indent=2, sort_keys=True)

    def _run_official_downloader(self) -> None:
        downloader_path = self._fetch_downloader_zip()
        launcher_path = self._ensure_pc_launcher_marker()

        self._log("")
        self._log("Official Downloader config check:")
        self._log(f"SD root: {self.sd_root}")
        self._log(f"PC_LAUNCHER: {launcher_path}")
        self._log(f"Downloader: {downloader_path}")

        self._log_downloader_ini_sections()

        self._log("")
        self._log("Running official Downloader inside MiSTer Companion runtime...")

        old_cwd = Path.cwd()
        old_argv = sys.argv[:]
        old_path = sys.path[:]

        old_env_values: dict[str, str | None] = {
            "PC_LAUNCHER": os.environ.get("PC_LAUNCHER"),
            "PC_LAUNCHER_NO_WAIT": os.environ.get("PC_LAUNCHER_NO_WAIT"),
            "DOWNLOADER_LAUNCHER": os.environ.get("DOWNLOADER_LAUNCHER"),
            "DOWNLOADER_SOURCE": os.environ.get("DOWNLOADER_SOURCE"),
        }

        os.environ["PC_LAUNCHER"] = str(launcher_path)
        os.environ["PC_LAUNCHER_NO_WAIT"] = "1"
        os.environ["DOWNLOADER_LAUNCHER"] = str(launcher_path)
        os.environ["DOWNLOADER_SOURCE"] = str(downloader_path)

        sys.argv = [str(downloader_path)]

        stdout_stream = _ProgressStream(self._handle_downloader_output_line)
        stderr_stream = _ProgressStream(self._handle_downloader_output_line)

        exit_code = 0

        self._purge_downloader_modules()

        try:
            os.chdir(self.sd_root)

            with (
                _SignalPatch(),
                contextlib.redirect_stdout(stdout_stream),
                contextlib.redirect_stderr(stderr_stream),
            ):
                try:
                    runpy.run_path(str(downloader_path), run_name="__main__")
                except SystemExit as exc:
                    code = exc.code

                    if code is None:
                        exit_code = 0
                    elif isinstance(code, int):
                        exit_code = code
                    else:
                        exit_code = 1
        finally:
            stdout_stream.flush()
            stderr_stream.flush()

            os.chdir(old_cwd)
            sys.argv = old_argv
            sys.path = old_path

            for key, value in old_env_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

            self._purge_downloader_modules()

        if exit_code != 0:
            self.result.files_failed += 1
            raise RuntimeError(f"Official Downloader exited with code {exit_code}")

        if self.result.databases_found == 0:
            self.result.databases_found = 1

        if self.result.databases_processed == 0:
            self.result.databases_processed = 1

        self._log("Official Downloader completed successfully.")

    def _fetch_downloader_zip(self) -> Path:
        target = self.cache_dir / "downloader.zip"

        self._log(f"Downloading official Downloader: {_DOWNLOADER_URL}")
        self._download_to_file(_DOWNLOADER_URL, target)

        if not target.exists() or target.stat().st_size <= 0:
            raise RuntimeError("Downloaded official Downloader is empty")

        return target

    def _ensure_pc_launcher_marker(self) -> Path:
        launcher_path = self.sd_root / "MiSTer_Companion_Offline_PC_Launcher.py"

        launcher_path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "# MiSTer Companion offline update_all launcher marker.",
                    "# This file exists so the official Downloader can detect PC launcher mode.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        return launcher_path

    def _purge_downloader_modules(self) -> None:
        for name in list(sys.modules):
            if (
                name == "downloader"
                or name.startswith("downloader.")
                or name == "update_all"
                or name.startswith("update_all.")
            ):
                sys.modules.pop(name, None)

    def _log_downloader_ini_sections(self) -> None:
        paths = [
            self.sd_root / "downloader.ini",
            self.sd_root / "downloader_arcade_roms_db.ini",
            self.sd_root / "downloader_bios_db.ini",
        ]

        downloader_dir = self.sd_root / "downloader"
        if downloader_dir.exists() and downloader_dir.is_dir():
            paths.extend(sorted(downloader_dir.glob("*.ini")))

        paths.extend(sorted(self.sd_root.glob("downloader_*.ini")))

        unique: list[Path] = []
        seen: set[Path] = set()

        for path in paths:
            try:
                resolved = path.resolve()
            except Exception:
                continue

            if resolved in seen:
                continue

            seen.add(resolved)
            unique.append(path)

        found_any = False

        for path in unique:
            if not path.exists() or not path.is_file():
                continue

            found_any = True
            self._log(f"{self._display_path(path)} exists: True")
            self._log(f"{self._display_path(path)} sections found:")

            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                self._log(f"  ERROR reading file: {exc}")
                continue

            found_section = False

            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("[") and stripped.endswith("]"):
                    found_section = True
                    self._log(f"  {stripped}")

            if not found_section:
                self._log("  No sections found.")

        if not found_any:
            self._log("No downloader.ini files found on selected SD root.")

    def _handle_downloader_output_line(self, line: str) -> None:
        line = str(line).rstrip()

        if not line:
            return

        self._log(line)
        self._parse_downloader_output_line(line)

    def _parse_downloader_output_line(self, line: str) -> None:
        lower = line.lower()

        if "downloading" in lower or "downloaded" in lower:
            if not any(word in lower for word in ("database", "db.json", "json.zip")):
                self.result.files_downloaded += 1

        if "skipping" in lower or "skipped" in lower or "already exists" in lower:
            self.result.files_skipped += 1

        if "extracting" in lower or "unzipping" in lower or "unpacking" in lower:
            self.result.archives_downloaded += 1

        if "using cached" in lower or "cached archive" in lower:
            self.result.archives_skipped += 1

        if "created folder" in lower or "creating folder" in lower or "created directory" in lower:
            self.result.folders_created += 1

        if "section:" in lower:
            self.result.databases_found = max(self.result.databases_found, 1)
            self.result.databases_processed += 1

        if "database" in lower and ("processing" in lower or "downloading" in lower):
            self.result.databases_found = max(self.result.databases_found, 1)

        if "error" in lower or "failed" in lower:
            if not self._is_non_fatal_output_line(lower):
                self.result.files_failed += 1

        match = re.search(r"found\s+(\d+)\s+database", lower)
        if match:
            self.result.databases_found = max(
                self.result.databases_found,
                self._int_or_zero(match.group(1)),
            )

        match = re.search(r"processed\s+(\d+)\s+database", lower)
        if match:
            self.result.databases_processed = max(
                self.result.databases_processed,
                self._int_or_zero(match.group(1)),
            )

    def _is_non_fatal_output_line(self, lower_line: str) -> bool:
        harmless_parts = (
            "0 failed",
            "failed: 0",
            "errors: 0",
            "no errors",
        )

        return any(part in lower_line for part in harmless_parts)

    def _run_arcade_organizer_if_enabled(self) -> None:
        try:
            from core.update_all_config import load_update_all_config_local
        except Exception as exc:
            self._log("")
            self._log(f"Arcade Organizer check skipped: could not load update_all config backend ({exc})")
            return

        try:
            config = load_update_all_config_local(self.sd_root)
        except Exception as exc:
            self._log("")
            self._log(f"Arcade Organizer check skipped: could not read update_all config ({exc})")
            return

        if not config.get("arcade_org", False):
            self._log("")
            self._log("Arcade Organizer is disabled, skipping.")
            return

        self._log("")
        self._log("Arcade Organizer is enabled.")
        self._log("Running Arcade Organizer offline...")

        try:
            from core.arcade_organizer_offline import run_arcade_organizer_offline
        except Exception as exc:
            self.result.ok = False
            message = f"Arcade Organizer backend is missing or could not be loaded: {exc}"
            self.result.errors.append(message)
            self._log(f"ERROR: {message}")
            return

        try:
            organizer_result = run_arcade_organizer_offline(
                sd_root=self.sd_root,
                progress=self.progress,
            )

            if organizer_result is None:
                self._log("Arcade Organizer finished.")
                return

            ok = getattr(organizer_result, "ok", None)
            if ok is False:
                self.result.ok = False

                organizer_errors = getattr(organizer_result, "errors", [])
                if organizer_errors:
                    for error in organizer_errors:
                        message = f"Arcade Organizer: {error}"
                        self.result.errors.append(message)
                        self._log(f"ERROR: {message}")
                else:
                    message = "Arcade Organizer finished with errors."
                    self.result.errors.append(message)
                    self._log(f"ERROR: {message}")
                return

            self._log("Arcade Organizer finished.")
        except Exception as exc:
            self.result.ok = False
            message = f"Arcade Organizer failed: {exc}"
            self.result.errors.append(message)
            self._log(f"ERROR: {message}")

    def _download_to_file(self, url: str, target: Path) -> None:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)

        request = Request(
            url,
            headers={
                "User-Agent": "MiSTer Companion Offline Downloader",
            },
        )

        temp_path = target.with_name(target.name + ".tmp")

        try:
            with urlopen(request, timeout=180) as response:
                with temp_path.open("wb") as handle:
                    shutil.copyfileobj(response, handle)

            temp_path.replace(target)
        except (HTTPError, URLError, TimeoutError) as exc:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

            raise RuntimeError(f"Download failed: {url} ({exc})") from exc

    def _int_or_zero(self, value: Any) -> int:
        try:
            return int(str(value).strip())
        except Exception:
            return 0

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.sd_root)).replace("\\", "/")
        except ValueError:
            return str(path)

    def _log(self, message: str) -> None:
        text = str(message)
        if not text.endswith("\n"):
            text += "\n"
        self.progress(text)
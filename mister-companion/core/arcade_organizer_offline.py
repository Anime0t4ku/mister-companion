from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ProgressCallback = Callable[[str], None]


_PYZ_URL = "https://github.com/theypsilon/Update_All_MiSTer/releases/latest/download/update_all.pyz"
_PYZ_SHA256_URL = "https://github.com/theypsilon/Update_All_MiSTer/releases/latest/download/update_all.pyz.sha256"

_MAD_DB_URL = "https://raw.githubusercontent.com/MiSTer-devel/ArcadeDatabase_MiSTer/refs/heads/db/mad_db.json.zip"
_MAD_DB_MD5_URL = "https://raw.githubusercontent.com/MiSTer-devel/ArcadeDatabase_MiSTer/refs/heads/db/mad_db.json.zip.md5"

_LOCAL_PYZ_RELATIVE_PATH = Path("Scripts") / ".config" / "update_all" / "update_all.pyz"
_LOCAL_PYZ_SHA256_RELATIVE_PATH = Path("Scripts") / ".config" / "update_all" / "update_all.pyz.sha256"

_LOCAL_MAD_DB_RELATIVE_PATH = Path("Scripts") / ".config" / "update_all" / "mad_db.json.zip"
_LOCAL_MAD_DB_MD5_RELATIVE_PATH = Path("Scripts") / ".config" / "update_all" / "mad_db.json.zip.md5"

_ARCADE_ORGANIZER_INI_RELATIVE_PATH = Path("Scripts") / "update_arcade-organizer.ini"


@dataclass
class ArcadeOrganizerOfflineResult:
    ok: bool = True
    pyz_downloaded: bool = False
    mad_db_downloaded: bool = False
    organized_path: str = ""
    organized_files: int = 0
    errors: list[str] = field(default_factory=list)


def run_arcade_organizer_offline(
    sd_root: str | Path,
    progress: ProgressCallback | None = None,
) -> ArcadeOrganizerOfflineResult:
    runner = ArcadeOrganizerOfflineRunner(sd_root=sd_root, progress=progress)
    return runner.run()


class _ProgressStream:
    def __init__(self, progress: ProgressCallback) -> None:
        self.progress = progress
        self.buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0

        self.buffer += text

        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.rstrip()
            if line:
                self.progress(line + "\n")

        return len(text)

    def flush(self) -> None:
        line = self.buffer.strip()
        if line:
            self.progress(line + "\n")
        self.buffer = ""


class ArcadeOrganizerOfflineRunner:
    def __init__(
        self,
        sd_root: str | Path,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.sd_root = Path(sd_root).expanduser().resolve()
        self.progress = progress or (lambda message: None)
        self.result = ArcadeOrganizerOfflineResult()

        self.update_all_dir = self.sd_root / "Scripts" / ".config" / "update_all"
        self.cache_dir = (
            self.sd_root
            / "Scripts"
            / ".config"
            / "mister_companion"
            / "offline_arcade_organizer_cache"
        )

    def run(self) -> ArcadeOrganizerOfflineResult:
        try:
            self._validate_sd_root()
            self._prepare_dirs()

            arcade_dir = self.sd_root / "_Arcade"
            if not arcade_dir.exists() or not arcade_dir.is_dir():
                self._log("Arcade Organizer skipped: _Arcade folder not found.")
                return self.result

            ini_path = self._ensure_arcade_organizer_ini()

            if not self._arcade_organizer_enabled(ini_path):
                self._log("Arcade Organizer skipped: disabled in update_arcade-organizer.ini.")
                return self.result

            pyz_path, mad_db_path = self._ensure_support_files()

            self._log("Starting upstream Arcade Organizer...")
            self._log(f"Base path: {self._display_path(self.sd_root)}")
            self._log(f"INI file: {self._display_path(ini_path)}")
            self._log(f"update_all.pyz: {self._display_path(pyz_path)}")
            self._log(f"MAD_DB: {self._display_path(mad_db_path)}")

            success = self._run_upstream_arcade_organizer(
                pyz_path=pyz_path,
                mad_db_path=mad_db_path,
                ini_path=ini_path,
            )

            organized = self.sd_root / "_Arcade" / "_Organized"
            self.result.organized_path = self._display_path(organized)
            self.result.organized_files = self._count_organized_files(organized)

            if success:
                self._log("Arcade Organizer completed successfully.")
            else:
                self.result.ok = False
                self.result.errors.append("Arcade Organizer returned failure.")
                self._log("ERROR: Arcade Organizer returned failure.")

            self._log(f"Arcade Organizer output: {self.result.organized_path}")
            self._log(f"Organized output file count: {self.result.organized_files}")

            if success and self.result.organized_files == 0:
                self._log(
                    "Arcade Organizer warning: output folder is empty. "
                    "The upstream runner finished, but no organized entries were found."
                )

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
        self.update_all_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_arcade_organizer_ini(self) -> Path:
        ini_path = self.sd_root / _ARCADE_ORGANIZER_INI_RELATIVE_PATH
        ini_path.parent.mkdir(parents=True, exist_ok=True)

        existing_text = ""
        if ini_path.exists():
            existing_text = ini_path.read_text(encoding="utf-8", errors="ignore")

        lines = existing_text.splitlines()
        values = self._parse_ini_key_values(existing_text)

        changed = False

        required_defaults = {
            "ARCADE_ORGANIZER": "true",
            "ORGDIR": "_Arcade/_Organized",
            "MRADIR": "_Arcade",
            "SKIPALTS": "false",
            "NO_SYMLINKS": "true",
        }

        if os.name == "nt":
            required_defaults["NO_SYMLINKS"] = "true"

        for key, value in required_defaults.items():
            if key not in values:
                lines.append(f"{key}={value}")
                changed = True

        if not ini_path.exists() or changed:
            text = "\n".join(lines).strip() + "\n"
            ini_path.write_text(text, encoding="utf-8")
            self._log(f"Updated Arcade Organizer config: {self._display_path(ini_path)}")

        return ini_path

    def _parse_ini_key_values(self, text: str) -> dict[str, str]:
        values: dict[str, str] = {}

        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line:
                continue

            if line.startswith("#") or line.startswith(";"):
                continue

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            values[key.strip().upper()] = value.strip()

        return values

    def _arcade_organizer_enabled(self, ini_path: Path) -> bool:
        text = ini_path.read_text(encoding="utf-8", errors="ignore")
        values = self._parse_ini_key_values(text)
        return self._parse_bool(values.get("ARCADE_ORGANIZER"), default=True)

    def _ensure_support_files(self) -> tuple[Path, Path]:
        pyz_path = self.sd_root / _LOCAL_PYZ_RELATIVE_PATH
        pyz_sha_path = self.sd_root / _LOCAL_PYZ_SHA256_RELATIVE_PATH

        mad_db_path = self.sd_root / _LOCAL_MAD_DB_RELATIVE_PATH
        mad_db_md5_path = self.sd_root / _LOCAL_MAD_DB_MD5_RELATIVE_PATH

        self._log("Checking Arcade Organizer support files...")

        expected_pyz_sha = self._download_text_optional(_PYZ_SHA256_URL)
        if expected_pyz_sha:
            expected_pyz_sha = self._clean_hash_text(expected_pyz_sha)

        if not pyz_path.exists() or not self._hash_matches_optional(
            pyz_path,
            "sha256",
            expected_pyz_sha,
        ):
            self._log("Downloading update_all.pyz...")
            self._download_to_file(_PYZ_URL, pyz_path)
            self.result.pyz_downloaded = True

        if expected_pyz_sha:
            actual_pyz_sha = self._hash_file(pyz_path, "sha256")
            if actual_pyz_sha.lower() != expected_pyz_sha.lower():
                raise RuntimeError("update_all.pyz SHA256 verification failed")

            pyz_sha_path.parent.mkdir(parents=True, exist_ok=True)
            pyz_sha_path.write_text(expected_pyz_sha + "\n", encoding="utf-8")

        expected_mad_md5 = self._download_text_optional(_MAD_DB_MD5_URL)
        if expected_mad_md5:
            expected_mad_md5 = self._clean_hash_text(expected_mad_md5)

        if not mad_db_path.exists() or not self._hash_matches_optional(
            mad_db_path,
            "md5",
            expected_mad_md5,
        ):
            self._log("Downloading mad_db.json.zip...")
            self._download_to_file(_MAD_DB_URL, mad_db_path)
            self.result.mad_db_downloaded = True

        if expected_mad_md5:
            actual_mad_md5 = self._hash_file(mad_db_path, "md5")
            if actual_mad_md5.lower() != expected_mad_md5.lower():
                raise RuntimeError("mad_db.json.zip MD5 verification failed")

            mad_db_md5_path.parent.mkdir(parents=True, exist_ok=True)
            mad_db_md5_path.write_text(expected_mad_md5 + "\n", encoding="utf-8")

        return pyz_path, mad_db_path

    def _run_upstream_arcade_organizer(
        self,
        pyz_path: Path,
        mad_db_path: Path,
        ini_path: Path,
    ) -> bool:
        old_cwd = Path.cwd()
        old_sys_path = list(sys.path)
        old_env = os.environ.copy()

        stream = _ProgressStream(self.progress)

        try:
            os.chdir(self.sd_root)

            os.environ["PC_LAUNCHER_NO_WAIT"] = "1"
            os.environ["INI_FILE"] = str(ini_path)
            os.environ["UPDATE_ALL_SOURCE"] = str(pyz_path)
            os.environ["MAD_DB"] = str(mad_db_path)

            sys.path.insert(0, str(pyz_path))

            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                from update_all.arcade_organizer.arcade_organizer import ArcadeOrganizerService
                from update_all.logger import PrintLogger

                logger = PrintLogger()
                ao_service = ArcadeOrganizerService(logger)

                config = ao_service.make_arcade_organizer_config(
                    str(ini_path),
                    str(self.sd_root),
                    "",
                )

                if os.name == "nt":
                    config["NO_SYMLINKS"] = True

                success = ao_service.run_arcade_organizer_organize_all_mras(config)

            stream.flush()
            return bool(success)

        finally:
            stream.flush()

            os.chdir(old_cwd)
            sys.path[:] = old_sys_path

            os.environ.clear()
            os.environ.update(old_env)

            self._remove_update_all_modules_from_cache()

    def _remove_update_all_modules_from_cache(self) -> None:
        for module_name in list(sys.modules):
            if module_name == "update_all" or module_name.startswith("update_all."):
                sys.modules.pop(module_name, None)

    def _count_organized_files(self, organized_dir: Path) -> int:
        if not organized_dir.exists() or not organized_dir.is_dir():
            return 0

        count = 0

        try:
            for path in organized_dir.rglob("*"):
                if path.is_file() or path.is_symlink():
                    count += 1
        except Exception:
            return count

        return count

    def _download_to_file(self, url: str, target: Path) -> None:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)

        request = Request(
            url,
            headers={
                "User-Agent": "MiSTer Companion Offline Arcade Organizer",
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

    def _download_text_optional(self, url: str) -> str:
        request = Request(
            url,
            headers={
                "User-Agent": "MiSTer Companion Offline Arcade Organizer",
            },
        )

        try:
            with urlopen(request, timeout=45) as response:
                return response.read().decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    def _clean_hash_text(self, text: str) -> str:
        first = str(text).strip().splitlines()[0].strip()

        if " " in first:
            first = first.split(" ")[0].strip()

        if "\t" in first:
            first = first.split("\t")[0].strip()

        return first.strip()

    def _hash_matches_optional(
        self,
        path: Path,
        algorithm: str,
        expected_hash: str | None,
    ) -> bool:
        if not path.exists() or not path.is_file():
            return False

        if not expected_hash:
            return True

        actual_hash = self._hash_file(path, algorithm)
        return actual_hash.lower() == expected_hash.lower()

    def _hash_file(self, path: Path, algorithm: str) -> str:
        hasher = hashlib.new(algorithm)

        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)

        return hasher.hexdigest()

    def _parse_bool(self, value: Any, default: bool = False) -> bool:
        if value is None:
            return default

        if isinstance(value, bool):
            return value

        text = str(value).strip().lower()

        if text in ("1", "yes", "true", "on", "enabled"):
            return True

        if text in ("0", "no", "false", "off", "disabled"):
            return False

        return default

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
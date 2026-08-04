from __future__ import annotations

import re
import shlex
import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from core.update_all_offline import run_downloader_offline

ZAPAROO_DB_ID = "ZaparooProject/Zaparoo_MiSTer"
ZAPAROO_DB_URL = "https://raw.githubusercontent.com/ZaparooProject/Zaparoo_MiSTer/db/db.json.zip"
RA_CORES_DB_ID = "theypsilon/RetroAchievementsDB_MiSTer"
RA_CORES_DB_URL = "https://raw.githubusercontent.com/theypsilon/RetroAchievementsDB_MiSTer/db/db.json.zip"
DOWNLOADER_INI = "/media/fat/downloader.ini"
UPDATE_SH = "/media/fat/Scripts/update.sh"
DOWNLOADER_SH = "/media/fat/Scripts/downloader.sh"
ROOT_DOWNLOADER_SH = "/media/fat/downloader.sh"

_batch_runs = threading.local()
_registration_cache = threading.local()


@contextmanager
def defer_named_database_runs():
    previous = getattr(_batch_runs, "ids", None)
    ids = []
    _batch_runs.ids = ids
    try:
        yield ids
    finally:
        _batch_runs.ids = previous

class DownloaderCommandError(RuntimeError):
    def __init__(self, message, output="", unsupported=False):
        super().__init__(message)
        self.output = output
        self.unsupported = unsupported


class DownloaderMissingDrivesError(DownloaderCommandError):
    """Downloader refused an uninstall because a previously used drive is absent."""


class DuplicateDatabaseSectionError(DownloaderCommandError):
    """The same Downloader database is registered more than once."""


@dataclass(frozen=True, order=True)
class DownloaderVersion:
    major: int
    minor: int
    patch: int = 0
    has_patch: bool = True


@dataclass
class DatabaseConfigSnapshot:
    files: dict[str, str]


def parse_downloader_version(output: str) -> DownloaderVersion | None:
    matches = list(re.finditer(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?(?!\d)", output or ""))
    if not matches:
        return None
    match = next((candidate for candidate in matches if candidate.group(3) is not None), matches[0])
    patch = match.group(3)
    return DownloaderVersion(int(match.group(1)), int(match.group(2)), int(patch or 0), patch is not None)


def _section_pattern(db_id: str):
    # Be tolerant of whitespace and comments after a section header. Downloader
    # itself treats duplicate sections as an error, so callers scan all config
    # files before using this expression to update anything.
    return re.compile(rf"(?ms)^[ \t]*\[{re.escape(db_id)}\][^\r\n]*(?:\r?\n|\Z).*?(?=^[ \t]*\[|\Z)")


def update_db_section(text: str, db_id: str, db_url: str, filter_value: str | None = None) -> str:
    lines = [f"[{db_id}]", f"db_url = {db_url}"]
    if filter_value is not None:
        lines.append(f"filter = {filter_value}")
    block = "\n".join(lines) + "\n"
    pattern = _section_pattern(db_id)
    if pattern.search(text or ""):
        return pattern.sub(block + "\n", text).rstrip() + "\n"
    base = (text or "").rstrip()
    return ((base + "\n\n") if base else "") + block


def remove_db_section(text: str, db_id: str) -> str:
    result = _section_pattern(db_id).sub("", text or "")
    return re.sub(r"\n{3,}", "\n\n", result).strip() + ("\n" if result.strip() else "")


def _unsupported(output: str) -> bool:
    low = (output or "").lower()
    command_options = ("--run-only", "run-only", "--check", "--version", "--uninstall", "--force")
    return any(token in low for token in (
        "unrecognized argument", "unknown option", "invalid option", "no such option",
        "unrecognized arguments", "not recognized",
    )) and any(option in low for option in command_options)


def _remote_downloader_command(*args: str) -> str:
    quoted_args = " ".join(shlex.quote(str(arg)) for arg in args)
    return (
        f'if [ -f {shlex.quote(UPDATE_SH)} ]; then {shlex.quote(UPDATE_SH)} {quoted_args}; '
        f'elif [ -f {shlex.quote(DOWNLOADER_SH)} ]; then {shlex.quote(DOWNLOADER_SH)} {quoted_args}; '
        f'else {shlex.quote(ROOT_DOWNLOADER_SH)} {quoted_args}; fi'
    )


def _read_remote(connection, path=DOWNLOADER_INI):
    return connection.run_command(f"cat {path} 2>/dev/null || true") or ""


def _write_remote(connection, text: str, path=DOWNLOADER_INI):
    sftp = connection.client.open_sftp()
    try:
        with sftp.open(path, "w") as handle:
            handle.write(text)
    finally:
        sftp.close()


def _local_ini(sd_root) -> Path:
    return Path(sd_root).expanduser().resolve() / "downloader.ini"


def _remote_ini_paths(connection) -> list[str]:
    sftp = connection.client.open_sftp()
    try:
        names = sftp.listdir("/media/fat")
    finally:
        sftp.close()
    matches = [name for name in names if name == "downloader.ini" or (name.startswith("downloader_") and name.endswith(".ini"))]
    if "downloader.ini" not in matches:
        matches.insert(0, "downloader.ini")
    return [f"/media/fat/{name}" for name in sorted(set(matches), key=lambda name: (name != "downloader.ini", name.lower()))]


def _local_ini_paths(sd_root) -> list[Path]:
    root = Path(sd_root).expanduser().resolve()
    paths = [root / "downloader.ini", *root.glob("downloader_*.ini")]
    return sorted(set(paths), key=lambda path: (path.name != "downloader.ini", path.name.lower()))


def _read_remote_ini_files(connection) -> dict[str, str]:
    return {path: _read_remote(connection, path) for path in _remote_ini_paths(connection)}


def _read_local_ini_files(sd_root) -> dict[str, str]:
    result = {}
    for path in _local_ini_paths(sd_root):
        result[str(path)] = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    return result


def _find_section_files(files: dict[str, str], db_id: str) -> list[str]:
    found = []
    pattern = _section_pattern(db_id)
    for path, text in files.items():
        found.extend([path] * len(pattern.findall(text or "")))
    return found


def database_registered_online(connection, db_id: str) -> bool:
    files = getattr(_registration_cache, "online_files", None)
    if files is None:
        files = _read_remote_ini_files(connection)
    return bool(_find_section_files(files, db_id))


def database_registered_local(sd_root, db_id: str) -> bool:
    files = getattr(_registration_cache, "local_files", None)
    if files is None:
        files = _read_local_ini_files(sd_root)
    return bool(_find_section_files(files, db_id))


def adopt_database_source_online(connection, db_id: str, db_url: str, filter_value=None) -> bool:
    """Register a missing database in the main downloader.ini without touching existing registrations."""
    files = _read_remote_ini_files(connection)
    found = _find_section_files(files, db_id)
    if len(found) > 1:
        locations = "\n".join(f"- {path}" for path in found)
        raise DuplicateDatabaseSectionError(
            f"The Downloader database '{db_id}' is registered more than once. "
            f"Remove the duplicate section before continuing:\n{locations}"
        )
    if found:
        return False
    main_text = files.get(DOWNLOADER_INI, "")
    _write_remote(connection, update_db_section(main_text, db_id, db_url, filter_value), DOWNLOADER_INI)
    return True


def adopt_database_source_local(sd_root, db_id: str, db_url: str, filter_value=None) -> bool:
    """Register a missing database in the main downloader.ini without touching existing registrations."""
    files = _read_local_ini_files(sd_root)
    found = _find_section_files(files, db_id)
    if len(found) > 1:
        locations = "\n".join(f"- {path}" for path in found)
        raise DuplicateDatabaseSectionError(
            f"The Downloader database '{db_id}' is registered more than once. "
            f"Remove the duplicate section before continuing:\n{locations}"
        )
    if found:
        return False
    target = _local_ini(sd_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    main_text = files.get(str(target), "")
    target.write_text(update_db_section(main_text, db_id, db_url, filter_value), encoding="utf-8")
    return True


@contextmanager
def cache_database_registration_online(connection):
    previous = getattr(_registration_cache, "online_files", None)
    _registration_cache.online_files = _read_remote_ini_files(connection)
    try:
        yield
    finally:
        _registration_cache.online_files = previous


@contextmanager
def cache_database_registration_local(sd_root):
    previous = getattr(_registration_cache, "local_files", None)
    _registration_cache.local_files = _read_local_ini_files(sd_root)
    try:
        yield
    finally:
        _registration_cache.local_files = previous


def _target_for_database(files: dict[str, str], db_id: str, default_path: str) -> str:
    found = _find_section_files(files, db_id)
    if len(found) > 1:
        locations = "\n".join(f"- {path}" for path in found)
        raise DuplicateDatabaseSectionError(
            f"The Downloader database '{db_id}' is registered more than once. "
            f"Remove the duplicate section before continuing:\n{locations}"
        )
    return found[0] if found else default_path


def _write_remote_snapshot(connection, snapshot: DatabaseConfigSnapshot):
    for path, text in snapshot.files.items():
        _write_remote(connection, text, path)


def _write_local_snapshot(snapshot: DatabaseConfigSnapshot):
    for path_string, text in snapshot.files.items():
        path = Path(path_string)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def ensure_source_online(connection, filter_value=None):
    return ensure_database_source_online(connection, ZAPAROO_DB_ID, ZAPAROO_DB_URL, filter_value)


def ensure_source_local(sd_root, filter_value=None):
    return ensure_database_source_local(sd_root, ZAPAROO_DB_ID, ZAPAROO_DB_URL, filter_value)


def restore_online(connection, original):
    if isinstance(original, DatabaseConfigSnapshot):
        _write_remote_snapshot(connection, original)
    else:
        _write_remote(connection, original)


def restore_local(sd_root, original):
    if isinstance(original, DatabaseConfigSnapshot):
        _write_local_snapshot(original)
    else:
        _local_ini(sd_root).write_text(original, encoding="utf-8")

def remove_source_online(connection): remove_database_source_online(connection, ZAPAROO_DB_ID)
def remove_source_local(sd_root): remove_database_source_local(sd_root, ZAPAROO_DB_ID)


def _run_remote_streaming_result(connection, command: str, log=None) -> tuple[str, int]:
    """Run Downloader with a PTY so its output is not block-buffered remotely."""
    if not connection.is_connected():
        raise RuntimeError("Not connected")

    output_parts: list[str] = []
    channel = None
    try:
        transport = connection.client.get_transport()
        if transport is None or not transport.is_active():
            raise RuntimeError("Not connected")

        channel = transport.open_session()
        channel.get_pty(term="xterm", width=160, height=40)
        channel.exec_command(command)

        while True:
            received = False
            while channel.recv_ready():
                data = channel.recv(4096)
                if not data:
                    break
                chunk = data.decode("utf-8", errors="ignore")
                if chunk:
                    output_parts.append(chunk)
                    if log:
                        log(chunk)
                received = True

            # A PTY merges stderr into stdout, so recv_stderr_ready is normally false.
            while channel.recv_stderr_ready():
                data = channel.recv_stderr(4096)
                if not data:
                    break
                chunk = data.decode("utf-8", errors="ignore")
                if chunk:
                    output_parts.append(chunk)
                    if log:
                        log(chunk)
                received = True

            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break

            if not received:
                time.sleep(0.03)

        exit_status = channel.recv_exit_status()
        return "".join(output_parts), exit_status
    except Exception:
        if not connection.is_connected():
            connection.mark_disconnected()
        raise
    finally:
        if channel is not None:
            try:
                channel.close()
            except Exception:
                pass


def _run_remote_streaming(connection, command: str, log=None) -> str:
    return _run_remote_streaming_result(connection, command, log=log)[0]


def ensure_database_source_online(connection, db_id: str, db_url: str, filter_value=None):
    files = _read_remote_ini_files(connection)
    target = _target_for_database(files, db_id, DOWNLOADER_INI)
    snapshot = DatabaseConfigSnapshot({target: files.get(target, "")})
    _write_remote(connection, update_db_section(files.get(target, ""), db_id, db_url, filter_value), target)
    return snapshot


def ensure_database_source_local(sd_root, db_id: str, db_url: str, filter_value=None):
    files = _read_local_ini_files(sd_root)
    default = str(_local_ini(sd_root))
    target = _target_for_database(files, db_id, default)
    snapshot = DatabaseConfigSnapshot({target: files.get(target, "")})
    path = Path(target)
    path.write_text(update_db_section(files.get(target, ""), db_id, db_url, filter_value), encoding="utf-8")
    return snapshot


def remove_database_source_online(connection, db_id: str):
    files = _read_remote_ini_files(connection)
    found = _find_section_files(files, db_id)
    for path in sorted(set(found)):
        _write_remote(connection, remove_db_section(files[path], db_id), path)


def remove_database_source_local(sd_root, db_id: str):
    files = _read_local_ini_files(sd_root)
    found = _find_section_files(files, db_id)
    for path_string in sorted(set(found)):
        Path(path_string).write_text(remove_db_section(files[path_string], db_id), encoding="utf-8")


def get_downloader_version_online(connection, log=None) -> DownloaderVersion | None:
    output = _run_remote_streaming(connection, _remote_downloader_command("--version") + " 2>&1", log=log)
    if _unsupported(output):
        raise DownloaderCommandError("Installed Downloader does not support --version.", output, unsupported=True)
    return parse_downloader_version(output)


def get_downloader_version_local(sd_root, log=None) -> DownloaderVersion | None:
    result = run_downloader_offline(sd_root, args=["--version"], progress=log)
    output = "\n".join(result.output_lines)
    if _unsupported(output):
        raise DownloaderCommandError("Installed Downloader does not support --version.", output, unsupported=True)
    return parse_downloader_version(output)


def _supports_filtered_check(version: DownloaderVersion | None) -> bool:
    # theypsilon's compatibility indicator: legacy builds return major.minor,
    # while builds supporting filtered checks return major.minor.patch.
    return bool(version and version.has_patch)


def _supports_native_uninstall(version: DownloaderVersion | None) -> bool:
    return bool(version and (version.major, version.minor, version.patch) >= (2, 4, 3))


def _missing_drives(output: str) -> bool:
    low = (output or "").lower().replace("_", " ").replace("-", " ")
    missing = any(phrase in low for phrase in (
        "unconnected drive", "unconnected storage", "disconnected drive",
        "drive is not connected", "drives are not connected", "missing drive",
        "unavailable drive", "not currently connected",
    ))
    return missing and any(word in low for word in ("drive", "storage", "usb", "external"))


def uninstall_named_database_online(connection, db_id: str, log=None, force: bool = False):
    version = get_downloader_version_online(connection)
    if not _supports_native_uninstall(version):
        return False
    args = ["--uninstall", db_id]
    if force:
        args.append("--force")
    output, exit_status = _run_remote_streaming_result(
        connection, _remote_downloader_command(*args) + " 2>&1", log=log
    )
    if _unsupported(output):
        raise DownloaderCommandError("Installed Downloader does not support this uninstall command.", output, unsupported=True)
    if _missing_drives(output) and not force:
        raise DownloaderMissingDrivesError(
            "Downloader found files on a drive that is not currently connected.", output
        )
    if exit_status != 0 or any(x in output.lower() for x in ("traceback", "fatal error")):
        raise DownloaderCommandError(f"Downloader failed to uninstall {db_id}.", output)
    return True


def uninstall_named_database_local(sd_root, db_id: str, log=None, force: bool = False):
    version = get_downloader_version_local(sd_root)
    if not _supports_native_uninstall(version):
        return False
    args = ["--uninstall", db_id]
    if force:
        args.append("--force")
    result = run_downloader_offline(sd_root, args=args, progress=log)
    output = "\n".join(result.output_lines)
    if _unsupported(output):
        raise DownloaderCommandError("Installed Downloader does not support this uninstall command.", output, unsupported=True)
    if _missing_drives(output) and not force:
        raise DownloaderMissingDrivesError(
            "Downloader found files on a drive that is not currently connected.", output
        )
    if not result.ok:
        raise DownloaderCommandError(result.errors[-1] if result.errors else f"Downloader failed to uninstall {db_id}.", output)
    return True


def run_named_database_online(connection, db_id: str, log=None):
    pending = getattr(_batch_runs, "ids", None)
    if pending is not None:
        if db_id not in pending:
            pending.append(db_id)
        return ""
    output = _run_remote_streaming(connection, _remote_downloader_command("--run-only", db_id) + " 2>&1", log=log)
    if _unsupported(output):
        raise DownloaderCommandError("Installed update.sh does not support --run-only.", output, unsupported=True)
    if any(x in output.lower() for x in ("traceback", "fatal error")):
        raise DownloaderCommandError(f"Downloader failed while processing {db_id}.", output)
    return output


def run_named_database_local(sd_root, db_id: str, log=None):
    pending = getattr(_batch_runs, "ids", None)
    if pending is not None:
        if db_id not in pending:
            pending.append(db_id)
        return ""
    result = run_downloader_offline(sd_root, args=["--run-only", db_id], progress=log)
    output = "\n".join(result.output_lines)
    if not result.ok:
        raise DownloaderCommandError(result.errors[-1] if result.errors else "Offline Downloader failed.", output, unsupported=_unsupported(output))
    return output


def run_named_databases_online(connection, db_ids, log=None):
    ids = list(dict.fromkeys(str(db_id).strip() for db_id in db_ids if str(db_id).strip()))
    if not ids:
        return ""
    output = _run_remote_streaming(connection, _remote_downloader_command("--run-only", *ids) + " 2>&1", log=log)
    if _unsupported(output):
        raise DownloaderCommandError("Installed update.sh does not support --run-only.", output, unsupported=True)
    if any(x in output.lower() for x in ("traceback", "fatal error")):
        raise DownloaderCommandError("Downloader failed while processing the selected databases.", output)
    return output


def run_named_databases_local(sd_root, db_ids, log=None):
    ids = list(dict.fromkeys(str(db_id).strip() for db_id in db_ids if str(db_id).strip()))
    if not ids:
        return ""
    result = run_downloader_offline(sd_root, args=["--run-only", *ids], progress=log)
    output = "\n".join(result.output_lines)
    if not result.ok:
        raise DownloaderCommandError(result.errors[-1] if result.errors else "Offline Downloader failed.", output, unsupported=_unsupported(output))
    return output


def check_named_database_online(connection, db_id: str, log=None):
    version = get_downloader_version_online(connection)
    args = ["--check", db_id] if _supports_filtered_check(version) else ["--check"]
    output = _run_remote_streaming(connection, _remote_downloader_command(*args) + " 2>&1", log=log)
    if _unsupported(output):
        raise DownloaderCommandError("Installed update.sh does not support --check.", output, unsupported=True)
    return parse_named_check(output, db_id)


def check_named_database_local(sd_root, db_id: str, log=None):
    version = get_downloader_version_local(sd_root)
    args = ["--check", db_id] if _supports_filtered_check(version) else ["--check"]
    result = run_downloader_offline(sd_root, args=args, progress=log)
    output = "\n".join(result.output_lines)
    if not result.ok:
        raise DownloaderCommandError(result.errors[-1] if result.errors else "Offline Downloader check failed.", output, unsupported=_unsupported(output))
    return parse_named_check(output, db_id)


def _inspect_single_database_online(connection, db_id: str, version, log=None):
    args = ["--check", db_id] if _supports_filtered_check(version) else ["--check"]
    output = _run_remote_streaming(connection, _remote_downloader_command(*args) + " 2>&1", log=log)
    if _unsupported(output):
        raise DownloaderCommandError("Installed update.sh does not support --check.", output, unsupported=True)
    return parse_named_check_state(output, db_id, allow_unscoped=_supports_filtered_check(version))


def _inspect_single_database_local(sd_root, db_id: str, version, log=None):
    args = ["--check", db_id] if _supports_filtered_check(version) else ["--check"]
    result = run_downloader_offline(sd_root, args=args, progress=log)
    output = "\n".join(result.output_lines)
    if not result.ok:
        raise DownloaderCommandError(result.errors[-1] if result.errors else "Offline Downloader check failed.", output, unsupported=_unsupported(output))
    return parse_named_check_state(output, db_id, allow_unscoped=_supports_filtered_check(version))


def inspect_named_databases_online(connection, db_ids, log=None):
    """Inspect several databases with one Downloader invocation, retrying only ambiguous results individually."""
    ids = list(dict.fromkeys(str(db_id).strip() for db_id in db_ids if str(db_id).strip()))
    if not ids:
        return {}
    version = get_downloader_version_online(connection)
    args = ["--check", *ids] if _supports_filtered_check(version) else ["--check"]
    output = _run_remote_streaming(connection, _remote_downloader_command(*args) + " 2>&1", log=log)
    if _unsupported(output):
        raise DownloaderCommandError("Installed update.sh does not support --check.", output, unsupported=True)
    states = {db_id: parse_named_check_state(output, db_id) for db_id in ids}
    if _supports_filtered_check(version):
        for db_id, state in list(states.items()):
            if not state.get("recognized"):
                states[db_id] = _inspect_single_database_online(connection, db_id, version, log=None)
    return states


def inspect_named_databases_local(sd_root, db_ids, log=None):
    """Inspect several databases with one offline Downloader invocation, retrying only ambiguous results individually."""
    ids = list(dict.fromkeys(str(db_id).strip() for db_id in db_ids if str(db_id).strip()))
    if not ids:
        return {}
    version = get_downloader_version_local(sd_root)
    args = ["--check", *ids] if _supports_filtered_check(version) else ["--check"]
    result = run_downloader_offline(sd_root, args=args, progress=log)
    output = "\n".join(result.output_lines)
    if not result.ok:
        raise DownloaderCommandError(result.errors[-1] if result.errors else "Offline Downloader check failed.", output, unsupported=_unsupported(output))
    states = {db_id: parse_named_check_state(output, db_id) for db_id in ids}
    if _supports_filtered_check(version):
        for db_id, state in list(states.items()):
            if not state.get("recognized"):
                states[db_id] = _inspect_single_database_local(sd_root, db_id, version, log=None)
    return states


def check_named_databases_online(connection, db_ids, log=None):
    return {db_id: bool(state.get("update_available")) for db_id, state in inspect_named_databases_online(connection, db_ids, log=log).items()}


def check_named_databases_local(sd_root, db_ids, log=None):
    return {db_id: bool(state.get("update_available")) for db_id, state in inspect_named_databases_local(sd_root, db_ids, log=log).items()}


def parse_named_check_state(output: str, db_id: str, allow_unscoped: bool = False) -> dict:
    aliases = {db_id.lower()}
    short_id = db_id.rsplit("/", 1)[-1].strip().lower()
    if short_id:
        aliases.add(short_id)
    normalized_short = re.sub(r"[^a-z0-9]+", "", short_id)

    lines = [(line or "").lower() for line in (output or "").splitlines()]
    relevant = []
    for lowered in lines:
        normalized_line = re.sub(r"[^a-z0-9]+", "", lowered)
        if any(alias in lowered for alias in aliases) or (normalized_short and normalized_short in normalized_line):
            relevant.append(lowered)
    if not relevant and allow_unscoped:
        relevant = lines
    text = "\n".join(relevant)
    not_installed = any(x in text for x in (
        "not installed", "isn't installed", "is not installed", "missing installation",
        "no installed files", "installation missing",
    ))
    update_available = any(x in text for x in (
        "update available", "update_available", "outdated", "not up to date", "needs update",
        "needs to be updated", "need to be updated", "files to update",
    ))
    installed = not not_installed and any(x in text for x in (
        "installed", "up to date", "up-to-date", "up_to_date", "current", "update available",
        "update_available", "outdated", "not up to date", "needs update", "needs to be updated",
        "need to be updated", "files to update", "nothing to update",
        "no updates needed", "no files to update", "all files are up to date",
        "everything is up to date",
    ))
    return {
        "installed": installed,
        "update_available": update_available,
        "recognized": bool(text) and (installed or not_installed),
    }


def parse_named_check(output: str, db_id: str) -> bool:
    return bool(parse_named_check_state(output, db_id).get("update_available"))


def run_database_online(connection, log=None):
    return run_named_database_online(connection, ZAPAROO_DB_ID, log=log)


def run_database_local(sd_root, log=None):
    return run_named_database_local(sd_root, ZAPAROO_DB_ID, log=log)


def check_database_online(connection, log=None):
    return check_named_database_online(connection, ZAPAROO_DB_ID, log=log)


def check_database_local(sd_root, log=None):
    return check_named_database_local(sd_root, ZAPAROO_DB_ID, log=log)


def parse_check(output: str) -> bool:
    return parse_named_check(output, ZAPAROO_DB_ID)

from __future__ import annotations

import re
import time
from pathlib import Path

from core.update_all_offline import run_downloader_offline

ZAPAROO_DB_ID = "ZaparooProject/Zaparoo_MiSTer"
ZAPAROO_DB_URL = "https://raw.githubusercontent.com/ZaparooProject/Zaparoo_MiSTer/db/db.json.zip"
RA_CORES_DB_ID = "theypsilon/RetroAchievementsDB_MiSTer"
RA_CORES_DB_URL = "https://raw.githubusercontent.com/theypsilon/RetroAchievementsDB_MiSTer/db/db.json.zip"
DOWNLOADER_INI = "/media/fat/downloader.ini"
UPDATE_SH = "/media/fat/Scripts/update.sh"

class DownloaderCommandError(RuntimeError):
    def __init__(self, message, output="", unsupported=False):
        super().__init__(message)
        self.output = output
        self.unsupported = unsupported


def _section_pattern(db_id: str):
    return re.compile(rf"(?ms)^\[{re.escape(db_id)}\]\s*\n.*?(?=^\[|\Z)")


def update_db_section(text: str, db_id: str, db_url: str, filter_value: str | None = None) -> str:
    lines = [f"[{db_id}]", f"db_url = {db_url}"]
    if filter_value is not None:
        lines.append(f"filter = {filter_value}")
    block = "\n".join(lines) + "\n"
    pattern = _section_pattern(db_id)
    if pattern.search(text or ""):
        return pattern.sub(block + "\n", text, count=1).rstrip() + "\n"
    base = (text or "").rstrip()
    return ((base + "\n\n") if base else "") + block


def remove_db_section(text: str, db_id: str) -> str:
    result = _section_pattern(db_id).sub("", text or "", count=1)
    return re.sub(r"\n{3,}", "\n\n", result).strip() + ("\n" if result.strip() else "")


def _unsupported(output: str) -> bool:
    low = (output or "").lower()
    return any(token in low for token in ("unrecognized argument", "unknown option", "invalid option", "no such option", "unrecognized arguments")) and ("run-only" in low or "--check" in low)


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


def ensure_source_online(connection, filter_value=None):
    old = _read_remote(connection)
    _write_remote(connection, update_db_section(old, ZAPAROO_DB_ID, ZAPAROO_DB_URL, filter_value))
    return old


def ensure_source_local(sd_root, filter_value=None):
    path = _local_ini(sd_root)
    old = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    path.write_text(update_db_section(old, ZAPAROO_DB_ID, ZAPAROO_DB_URL, filter_value), encoding="utf-8")
    return old


def restore_online(connection, original): _write_remote(connection, original)
def restore_local(sd_root, original): _local_ini(sd_root).write_text(original, encoding="utf-8")

def remove_source_online(connection): _write_remote(connection, remove_db_section(_read_remote(connection), ZAPAROO_DB_ID))
def remove_source_local(sd_root):
    path = _local_ini(sd_root)
    path.write_text(remove_db_section(path.read_text(encoding="utf-8", errors="ignore") if path.exists() else "", ZAPAROO_DB_ID), encoding="utf-8")


def _run_remote_streaming(connection, command: str, log=None) -> str:
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

        channel.recv_exit_status()
        return "".join(output_parts)
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


def ensure_database_source_online(connection, db_id: str, db_url: str, filter_value=None):
    old = _read_remote(connection)
    _write_remote(connection, update_db_section(old, db_id, db_url, filter_value))
    return old


def ensure_database_source_local(sd_root, db_id: str, db_url: str, filter_value=None):
    path = _local_ini(sd_root)
    old = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    path.write_text(update_db_section(old, db_id, db_url, filter_value), encoding="utf-8")
    return old


def remove_database_source_online(connection, db_id: str):
    _write_remote(connection, remove_db_section(_read_remote(connection), db_id))


def remove_database_source_local(sd_root, db_id: str):
    path = _local_ini(sd_root)
    text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    path.write_text(remove_db_section(text, db_id), encoding="utf-8")


def run_named_database_online(connection, db_id: str, log=None):
    output = _run_remote_streaming(connection, f"{UPDATE_SH} --run-only {db_id} 2>&1", log=log)
    if _unsupported(output):
        raise DownloaderCommandError("Installed update.sh does not support --run-only.", output, unsupported=True)
    if any(x in output.lower() for x in ("traceback", "fatal error")):
        raise DownloaderCommandError(f"Downloader failed while processing {db_id}.", output)
    return output


def run_named_database_local(sd_root, db_id: str, log=None):
    result = run_downloader_offline(sd_root, args=["--run-only", db_id], progress=log)
    output = "\n".join(result.output_lines)
    if not result.ok:
        raise DownloaderCommandError(result.errors[-1] if result.errors else "Offline Downloader failed.", output, unsupported=_unsupported(output))
    return output


def check_named_database_online(connection, db_id: str, log=None):
    output = _run_remote_streaming(connection, f"{UPDATE_SH} --check 2>&1", log=log)
    if _unsupported(output):
        raise DownloaderCommandError("Installed update.sh does not support --check.", output, unsupported=True)
    return parse_named_check(output, db_id)


def check_named_database_local(sd_root, db_id: str, log=None):
    result = run_downloader_offline(sd_root, args=["--check"], progress=log)
    output = "\n".join(result.output_lines)
    if not result.ok:
        raise DownloaderCommandError(result.errors[-1] if result.errors else "Offline Downloader check failed.", output, unsupported=_unsupported(output))
    return parse_named_check(output, db_id)


def parse_named_check(output: str, db_id: str) -> bool:
    relevant = [line.lower() for line in (output or "").splitlines() if db_id.lower() in line.lower()]
    text = "\n".join(relevant)
    if any(x in text for x in ("update available", "outdated", "not up to date", "needs update")):
        return True
    if any(x in text for x in ("up to date", "up-to-date", "current")):
        return False
    return False


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

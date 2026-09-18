import json
import re
import shlex
import sqlite3
import time
import unicodedata
from pathlib import Path

from websocket import create_connection

from core.zaparoo_crypto import (
    ZaparooCryptoError,
    create_encrypted_session,
    load_pairing_credentials,
)


REMOTE_MEDIA_DB_PATH = "/media/fat/zaparoo/media.db"
REMOTE_MEDIA_DB_SNAPSHOT_PREFIX = "/media/fat/zaparoo/.companion_media_snapshot"
ZAPAROO_TITLE_COLLATION = "ZAPAROO_TITLE_V1"


class ZaparooApiError(RuntimeError):
    pass


class ZaparooPairingRequired(ZaparooApiError):
    pass


def _safe_text(value) -> str:
    if value is None:
        return ""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    return str(value)


def _build_ws_url(connection) -> str:
    host = getattr(connection, "host", "").strip()
    if not host:
        raise ZaparooApiError("No MiSTer IP is available.")

    return f"ws://{host}:7497/api/v0.1"


def _response_error(response):
    if not isinstance(response, dict) or not response.get("error"):
        return None, ""

    error = response["error"]
    if isinstance(error, dict):
        return error.get("code"), error.get("message") or str(error)
    return None, str(error)


def _plain_ws_payload(ws_url: str, payload: dict, timeout: int):
    ws = None
    try:
        ws = create_connection(ws_url, timeout=timeout, suppress_origin=True)
        ws.send(json.dumps(payload))
        response_raw = ws.recv()
        try:
            return json.loads(response_raw)
        except Exception:
            return {"raw": response_raw}
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


def _encrypted_ws_payload(ws_url: str, payload: dict, credentials, timeout: int):
    ws = None
    session = create_encrypted_session(credentials)
    try:
        ws = create_connection(ws_url, timeout=timeout, suppress_origin=True)
        ws.send(json.dumps(session.encrypt_payload(payload), separators=(",", ":")))
        response_raw = ws.recv()
        try:
            response_frame = json.loads(response_raw)
        except Exception as exc:
            raise ZaparooCryptoError("Zaparoo returned an invalid encrypted response.") from exc

        # Protocol/setup failures may be returned as plaintext JSON-RPC errors.
        if isinstance(response_frame, dict) and response_frame.get("error") and not response_frame.get("e"):
            return response_frame

        return session.decrypt_frame(response_frame)
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


def _send_ws_payload(connection, payload: dict, timeout: int = 5):
    ws_url = _build_ws_url(connection)
    host = getattr(connection, "host", "").strip()

    credentials = None
    credential_error = None
    try:
        credentials = load_pairing_credentials(host)
    except ZaparooCryptoError as exc:
        credential_error = exc

    if credentials is not None:
        try:
            response = _encrypted_ws_payload(ws_url, payload, credentials, timeout)
            code, message = _response_error(response)
            if not message:
                return response
            if code not in (-32001, -32002):
                raise ZaparooApiError(message)
        except ZaparooApiError:
            raise
        except Exception:
            # A stale/revoked credential can make the encrypted first frame fail.
            # Probe plaintext once so we can distinguish optional encryption from
            # a server that requires a fresh pairing.
            pass

    try:
        response = _plain_ws_payload(ws_url, payload, timeout)
        code, message = _response_error(response)
        if message:
            if code == -32002:
                if credential_error is not None:
                    raise ZaparooApiError(str(credential_error))
                raise ZaparooPairingRequired(
                    "Zaparoo pairing is required before this MiSTer can accept remote commands."
                )
            raise ZaparooApiError(message)
        return response
    except Exception as e:
        if isinstance(e, ZaparooApiError):
            raise
        raise ZaparooApiError(str(e)) from e


def run_zaparoo_command(connection, command: str, timeout: int = 5):
    if not command:
        raise ValueError("Command is required.")

    payload = {
        "jsonrpc": "2.0",
        "method": "run",
        "params": command,
        "id": 1,
    }

    return _send_ws_payload(connection, payload, timeout=timeout)


def run_script(connection, script_name: str, timeout: int = 5):
    script_name = (script_name or "").strip()

    if not script_name:
        raise ValueError("Script name is required.")

    if script_name.endswith(".sh"):
        script_name = script_name[:-3]

    return run_zaparoo_command(
        connection,
        f"**mister.script:{script_name}.sh",
        timeout=timeout,
    )


def send_input_command(connection, command: str, timeout: int = 5):
    return run_zaparoo_command(connection, command, timeout=timeout)


def get_active_media(connection, timeout: int = 3) -> dict:
    """Return Zaparoo Core's currently active primary (now playing) media.

    This intentionally uses only the documented ``media.active`` API. MiSTer
    game tracking for titles launched outside Zaparoo depends on ``recents=1``
    in MiSTer.ini; Companion does not infer now-playing state from MiSTer files.
    """
    payload = {
        "jsonrpc": "2.0",
        "method": "media.active",
        "params": {"slot": "primary"},
        "id": "mister-companion-now-playing",
    }

    response = _send_ws_payload(connection, payload, timeout=timeout)
    if not isinstance(response, dict):
        return {}

    result = response.get("result")
    if result is None:
        return {}
    if not isinstance(result, dict):
        raise ZaparooApiError("Zaparoo media.active returned an unexpected response.")

    # ActiveMedia's required fields are launcherId, systemId, systemName,
    # mediaPath, mediaName, started, and zapScript. Keep optional fields intact.
    return result


def get_media_database_status(connection, timeout: int = 5) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "method": "media",
        "id": 1,
    }

    response = _send_ws_payload(connection, payload, timeout=timeout)
    result = response.get("result", {}) if isinstance(response, dict) else {}
    database = result.get("database", {}) if isinstance(result, dict) else {}

    return {
        "exists": bool(database.get("exists", False)),
        "indexing": bool(database.get("indexing", False)),
        "optimizing": bool(database.get("optimizing", False)),
        "total_media": database.get("totalMedia", 0),
        "current_step": database.get("currentStep"),
        "total_steps": database.get("totalSteps"),
        "current_step_display": database.get("currentStepDisplay"),
        "total_files": database.get("totalFiles"),
    }


def _open_sftp(connection):
    """
    Open an SFTP session using the existing MiSTer Companion connection object.
    """
    if not connection or not connection.is_connected():
        raise ZaparooApiError("Not connected to MiSTer.")

    for method_name in ("open_sftp", "get_sftp", "create_sftp"):
        method = getattr(connection, method_name, None)
        if callable(method):
            sftp = method()
            if sftp:
                return sftp, True

    for attr_name in ("sftp", "sftp_client"):
        sftp = getattr(connection, attr_name, None)
        if sftp:
            return sftp, False

    for attr_name in ("ssh", "client", "ssh_client"):
        ssh = getattr(connection, attr_name, None)
        if ssh and hasattr(ssh, "open_sftp"):
            return ssh.open_sftp(), True

    raise ZaparooApiError(
        "Could not open SFTP session from the active MiSTer connection."
    )


def _create_remote_media_db_snapshot(connection) -> str | None:
    """Create a consistent SQLite snapshot on the MiSTer when possible.

    Newer Zaparoo builds keep media.db in WAL mode. Copying only media.db while
    Zaparoo is running can therefore miss committed WAL pages or capture an
    inconsistent point in time. Python's SQLite backup API reads the live DB
    together with its WAL and produces a standalone snapshot for SFTP.

    Older MiSTer installations that do not have python3 simply fall back to the
    legacy direct-file download path.
    """
    run_command = getattr(connection, "run_command", None)
    if not callable(run_command):
        return None

    snapshot_path = f"{REMOTE_MEDIA_DB_SNAPSHOT_PREFIX}_{int(time.time() * 1000)}.db"
    marker = "__COMPANION_MEDIA_SNAPSHOT_OK__"
    script = "\n".join(
        [
            "import os, sqlite3",
            f"src = {REMOTE_MEDIA_DB_PATH!r}",
            f"dst = {snapshot_path!r}",
            "try:",
            "    os.remove(dst)",
            "except FileNotFoundError:",
            "    pass",
            'source = sqlite3.connect("file:" + src + "?mode=ro", uri=True, timeout=15)',
            "target = sqlite3.connect(dst, timeout=15)",
            "try:",
            "    source.backup(target)",
            "finally:",
            "    target.close()",
            "    source.close()",
            f"print({marker!r})",
        ]
    )

    try:
        output = run_command(f"python3 -c {shlex.quote(script)} 2>&1") or ""
        if marker in str(output):
            return snapshot_path
    except Exception:
        pass

    try:
        run_command(f"rm -f {shlex.quote(snapshot_path)}")
    except Exception:
        pass
    return None


def _remove_remote_media_db_snapshot(connection, snapshot_path: str | None):
    if not snapshot_path:
        return

    run_command = getattr(connection, "run_command", None)
    if not callable(run_command):
        return

    try:
        quoted = shlex.quote(snapshot_path)
        run_command(f"rm -f {quoted} {quoted}-wal {quoted}-shm")
    except Exception:
        pass


def download_media_db(connection, local_path: Path) -> Path:
    """
    Download Zaparoo's media.db from the MiSTer.

    New Zaparoo databases use WAL mode, so Companion first tries to create a
    consistent SQLite backup on the MiSTer and downloads that standalone file.
    If snapshot creation is unavailable (for example on an older installation),
    the original direct media.db download remains as a compatibility fallback.
    """
    if not local_path:
        raise ZaparooApiError("No local media.db path was provided.")

    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = local_path.with_suffix(local_path.suffix + ".tmp")

    snapshot_path = _create_remote_media_db_snapshot(connection)
    remote_path = snapshot_path or REMOTE_MEDIA_DB_PATH

    sftp = None
    should_close = False

    try:
        sftp, should_close = _open_sftp(connection)

        try:
            sftp.get(remote_path, str(tmp_path))
        except FileNotFoundError:
            if snapshot_path:
                raise ZaparooApiError(
                    "Zaparoo media database snapshot disappeared before it could be downloaded."
                )
            raise ZaparooApiError(
                f"Zaparoo media database was not found:\n{REMOTE_MEDIA_DB_PATH}"
            )
        except OSError as e:
            raise ZaparooApiError(
                f"Could not download Zaparoo media database:\n{e}"
            ) from e

        tmp_path.replace(local_path)
        return local_path

    finally:
        try:
            if should_close and sftp:
                sftp.close()
        except Exception:
            pass

        _remove_remote_media_db_snapshot(connection, snapshot_path)

        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def _zaparoo_title_sort_key(value):
    """Stable fallback key for Zaparoo's custom SQLite title collation."""
    text = unicodedata.normalize("NFKD", _safe_text(value)).casefold()
    parts = re.split(r"(\d+)", text)
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in parts
        if part != ""
    )


def _zaparoo_title_compare(left, right) -> int:
    left_key = _zaparoo_title_sort_key(left)
    right_key = _zaparoo_title_sort_key(right)
    return (left_key > right_key) - (left_key < right_key)


def _configure_media_db_connection(db: sqlite3.Connection):
    # New Zaparoo databases reference this application-specific collation in
    # idx_media_browse_sort. Companion does not rely on Zaparoo's exact browse
    # ordering, but registering the name prevents Python sqlite3 from failing
    # while inspecting or querying the newer schema.
    db.create_collation(ZAPAROO_TITLE_COLLATION, _zaparoo_title_compare)
    try:
        db.execute("PRAGMA query_only = ON")
    except sqlite3.DatabaseError:
        pass


def _detect_media_db_compatibility(cursor) -> str:
    """Detect newer Zaparoo DBs by schema/config instead of app version."""
    try:
        has_config = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='DBConfig'"
        ).fetchone()
        if has_config:
            config = dict(
                cursor.execute(
                    "SELECT Name, Value FROM DBConfig "
                    "WHERE Name IN ('BrowseSortCollation', 'BrowseIndexVersion')"
                ).fetchall()
            )
            if str(config.get("BrowseSortCollation", "")).lower() == "zaparoo_title_v1":
                return "wal-title-v1"
    except sqlite3.DatabaseError:
        pass

    try:
        if cursor.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE sql IS NOT NULL AND UPPER(sql) LIKE '%ZAPAROO_TITLE_V1%' LIMIT 1"
        ).fetchone():
            return "wal-title-v1"
    except sqlite3.DatabaseError:
        pass

    return "legacy"

def _get_table_columns(cursor, table_name: str) -> set[str]:
    cursor.execute(f'PRAGMA table_info("{table_name}")')
    return {str(row[1]) for row in cursor.fetchall()}


def _make_filename(path: str, parent_dir: str | None = None) -> str:
    path = _safe_text(path)
    parent_dir = _safe_text(parent_dir)

    if parent_dir and path.startswith(parent_dir):
        filename = path[len(parent_dir):].lstrip("/")
        if filename:
            return filename

    stripped = path.rstrip("/")
    if not stripped:
        return ""

    return Path(stripped).name


_CD_TRACK_RE = re.compile(
    r"""
    (?:
        [\s._-]*
        \(?
        track
        [\s._-]*
        \d+
        \)?
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _path_ext(path: str) -> str:
    filename = Path(_safe_text(path).rstrip("/").split("/")[-1]).name
    return Path(filename).suffix.lower()


def _filename_stem_from_path(path: str) -> str:
    filename = Path(_safe_text(path).rstrip("/").split("/")[-1]).name
    return Path(filename).stem.strip()


def _normalize_cd_set_name(name: str) -> str:
    name = _safe_text(name)
    name = Path(name).stem
    name = _CD_TRACK_RE.sub("", name)
    name = re.sub(r"\s+", " ", name)
    name = name.strip(" ._-")
    return name.lower()


def _cue_matches_bin(cue_path: str, bin_path: str) -> bool:
    cue_name = _normalize_cd_set_name(_filename_stem_from_path(cue_path))
    bin_name = _normalize_cd_set_name(_filename_stem_from_path(bin_path))

    if not cue_name or not bin_name:
        return False

    if cue_name == bin_name:
        return True

    if bin_name.startswith(cue_name):
        return True

    if cue_name.startswith(bin_name):
        return True

    return False


def _looks_like_cd_track_bin(path: str) -> bool:
    filename = Path(_safe_text(path).rstrip("/").split("/")[-1]).name

    if not filename.lower().endswith(".bin"):
        return False

    return bool(_CD_TRACK_RE.search(Path(filename).stem))


def _build_cue_lookup(rows: list[sqlite3.Row]) -> dict[str, list[str]]:
    cue_lookup = {}

    for row in rows:
        path = _safe_text(row["FullPath"])
        parent_dir = _safe_text(row["ParentDir"])

        if _path_ext(path) != ".cue":
            continue

        cue_lookup.setdefault(parent_dir, []).append(path)

    return cue_lookup


def _should_hide_bin_entry(path: str, parent_dir: str, cue_lookup: dict[str, list[str]]) -> bool:
    if _path_ext(path) != ".bin":
        return False

    matching_cues = cue_lookup.get(parent_dir, [])

    for cue_path in matching_cues:
        if _cue_matches_bin(cue_path, path):
            return True

    if _looks_like_cd_track_bin(path):
        return True

    return False


def read_media_db_entries(
    local_path: Path,
    progress_callback=None,
    include_missing: bool = True,
) -> list[dict]:
    """
    Read a downloaded Zaparoo media.db and return ZapScripts-compatible entries.
    """
    local_path = Path(local_path)

    if not local_path.exists():
        raise ZaparooApiError(f"Local media.db not found:\n{local_path}")

    entries = []

    try:
        db = sqlite3.connect(str(local_path))
        _configure_media_db_connection(db)

        db.text_factory = lambda value: value.decode("utf-8", errors="replace")

        db.row_factory = sqlite3.Row
    except Exception as e:
        raise ZaparooApiError(f"Could not open media.db:\n{e}") from e

    try:
        cursor = db.cursor()
        _compatibility_mode = _detect_media_db_compatibility(cursor)

        media_columns = _get_table_columns(cursor, "Media")
        title_columns = _get_table_columns(cursor, "MediaTitles")
        system_columns = _get_table_columns(cursor, "Systems")

        required_media = {"Path", "ParentDir", "MediaTitleDBID", "SystemDBID"}
        required_titles = {"DBID", "Name"}
        required_systems = {"DBID", "SystemID", "Name"}

        missing = []
        if not required_media.issubset(media_columns):
            missing.append("Media")
        if not required_titles.issubset(title_columns):
            missing.append("MediaTitles")
        if not required_systems.issubset(system_columns):
            missing.append("Systems")

        if missing:
            raise ZaparooApiError(
                "media.db does not have the expected Zaparoo schema. "
                f"Problem table(s): {', '.join(missing)}"
            )

        where = ""
        if not include_missing and "IsMissing" in media_columns:
            where = "WHERE COALESCE(m.IsMissing, 0) = 0"

        cursor.execute(f"SELECT COUNT(*) FROM Media m {where}")
        total = int(cursor.fetchone()[0] or 0)

        query = f"""
            SELECT
                m.DBID AS MediaDBID,
                m.Path AS FullPath,
                m.ParentDir AS ParentDir,
                {"m.IsMissing AS IsMissing," if "IsMissing" in media_columns else "0 AS IsMissing,"}
                mt.Name AS TitleName,
                s.SystemID AS SystemID,
                s.Name AS SystemName
            FROM Media m
            LEFT JOIN MediaTitles mt ON mt.DBID = m.MediaTitleDBID
            LEFT JOIN Systems s ON s.DBID = m.SystemDBID
            {where}
            ORDER BY s.SystemID, mt.Name, m.Path
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        cue_lookup = _build_cue_lookup(rows)

        scanned = 0

        for row in rows:
            scanned += 1

            path = _safe_text(row["FullPath"])
            parent_dir = _safe_text(row["ParentDir"])

            if _should_hide_bin_entry(path, parent_dir, cue_lookup):
                if progress_callback and (scanned % 500 == 0 or scanned == total):
                    try:
                        progress_callback(1, scanned, {"total": total})
                    except TypeError:
                        progress_callback(scanned)
                continue

            filename = _make_filename(path, parent_dir)

            title_name = _safe_text(row["TitleName"])
            system_id = _safe_text(row["SystemID"]) or "Unknown"
            system_name = _safe_text(row["SystemName"]) or system_id or "Unknown"

            display_name = filename or title_name or path

            entries.append(
                {
                    "name": display_name,
                    "filename": filename or display_name,
                    "title_name": title_name,
                    "path": path,
                    "parent_dir": parent_dir,
                    "directory": parent_dir,
                    "type": "game",
                    "system": system_name,
                    "system_id": system_id,
                    "system_name": system_name,
                    "zapScript": None,
                    "is_missing": bool(row["IsMissing"]),
                    "media_dbid": row["MediaDBID"],
                }
            )

            if progress_callback and (scanned % 500 == 0 or scanned == total):
                try:
                    progress_callback(1, scanned, {"total": total})
                except TypeError:
                    progress_callback(scanned)

        return entries

    except ZaparooApiError:
        raise
    except Exception as e:
        raise ZaparooApiError(f"Could not read media.db:\n{e}") from e
    finally:
        try:
            db.close()
        except Exception:
            pass



def _fast_basename(path: str) -> str:
    path = _safe_text(path).rstrip("/")
    if not path:
        return ""
    return path.rsplit("/", 1)[-1]


def _fast_suffix(path: str) -> str:
    filename = _fast_basename(path)
    dot = filename.rfind(".")
    if dot <= 0:
        return ""
    return filename[dot:].lower()


def _fast_stem(path: str) -> str:
    filename = _fast_basename(path)
    dot = filename.rfind(".")
    if dot <= 0:
        return filename.strip()
    return filename[:dot].strip()


def _normalize_cd_set_name_fast(name: str) -> str:
    name = _safe_text(name)
    name = _fast_stem(name)
    name = _CD_TRACK_RE.sub("", name)
    name = re.sub(r"\s+", " ", name)
    name = name.strip(" ._-")
    return name.lower()


def _cue_matches_bin_fast(cue_path: str, bin_path: str) -> bool:
    cue_name = _normalize_cd_set_name_fast(cue_path)
    bin_name = _normalize_cd_set_name_fast(bin_path)

    if not cue_name or not bin_name:
        return False

    return cue_name == bin_name or bin_name.startswith(cue_name) or cue_name.startswith(bin_name)


def _looks_like_cd_track_bin_fast(path: str) -> bool:
    filename = _fast_basename(path)
    return filename.lower().endswith(".bin") and bool(_CD_TRACK_RE.search(_fast_stem(filename)))


def _should_hide_bin_entry_fast(path: str, parent_dir: str, cue_lookup: dict[str, list[str]]) -> bool:
    if _fast_suffix(path) != ".bin":
        return False

    for cue_path in cue_lookup.get(parent_dir, []):
        if _cue_matches_bin_fast(cue_path, path):
            return True

    return _looks_like_cd_track_bin_fast(path)


def _make_filename_fast(path: str, parent_dir: str | None = None) -> str:
    path = _safe_text(path)
    parent_dir = _safe_text(parent_dir)

    if parent_dir and path.startswith(parent_dir):
        filename = path[len(parent_dir):].lstrip("/")
        if filename:
            return filename

    return _fast_basename(path)


def _raise_if_cancelled(cancel_callback):
    if callable(cancel_callback) and cancel_callback():
        raise RuntimeError("__LOAD_CANCELLED__")


def read_media_db_entries_macos_fast(
    local_path: Path,
    progress_callback=None,
    include_missing: bool = True,
    cancel_callback=None,
) -> list[dict]:
    local_path = Path(local_path)

    if not local_path.exists():
        raise ZaparooApiError(f"Local media.db not found:\n{local_path}")

    entries = []

    try:
        db = sqlite3.connect(str(local_path))
        _configure_media_db_connection(db)
        db.text_factory = lambda value: value.decode("utf-8", errors="replace")
        db.row_factory = sqlite3.Row
    except Exception as e:
        raise ZaparooApiError(f"Could not open media.db:\n{e}") from e

    try:
        cursor = db.cursor()
        _compatibility_mode = _detect_media_db_compatibility(cursor)
        media_columns = _get_table_columns(cursor, "Media")
        title_columns = _get_table_columns(cursor, "MediaTitles")
        system_columns = _get_table_columns(cursor, "Systems")

        required_media = {"Path", "ParentDir", "MediaTitleDBID", "SystemDBID"}
        required_titles = {"DBID", "Name"}
        required_systems = {"DBID", "SystemID", "Name"}

        missing = []
        if not required_media.issubset(media_columns):
            missing.append("Media")
        if not required_titles.issubset(title_columns):
            missing.append("MediaTitles")
        if not required_systems.issubset(system_columns):
            missing.append("Systems")

        if missing:
            raise ZaparooApiError(
                "media.db does not have the expected Zaparoo schema. "
                f"Problem table(s): {', '.join(missing)}"
            )

        where = ""
        if not include_missing and "IsMissing" in media_columns:
            where = "WHERE COALESCE(m.IsMissing, 0) = 0"

        cursor.execute(f"SELECT COUNT(*) FROM Media m {where}")
        total = int(cursor.fetchone()[0] or 0)

        _raise_if_cancelled(cancel_callback)

        cue_lookup = {}
        cue_where = "AND" if where else "WHERE"
        cue_query = f'''
            SELECT m.Path AS FullPath, m.ParentDir AS ParentDir
            FROM Media m
            {where}
            {cue_where} LOWER(m.Path) LIKE '%.cue'
        '''
        for row in cursor.execute(cue_query):
            _raise_if_cancelled(cancel_callback)
            parent_dir = _safe_text(row["ParentDir"])
            path = _safe_text(row["FullPath"])
            cue_lookup.setdefault(parent_dir, []).append(path)

        _raise_if_cancelled(cancel_callback)

        query = f'''
            SELECT
                m.DBID AS MediaDBID,
                m.Path AS FullPath,
                m.ParentDir AS ParentDir,
                {"m.IsMissing AS IsMissing," if "IsMissing" in media_columns else "0 AS IsMissing,"}
                mt.Name AS TitleName,
                s.SystemID AS SystemID,
                s.Name AS SystemName
            FROM Media m
            LEFT JOIN MediaTitles mt ON mt.DBID = m.MediaTitleDBID
            LEFT JOIN Systems s ON s.DBID = m.SystemDBID
            {where}
        '''

        scanned = 0
        for row in cursor.execute(query):
            scanned += 1

            if scanned % 1000 == 0:
                _raise_if_cancelled(cancel_callback)

            path = _safe_text(row["FullPath"])
            parent_dir = _safe_text(row["ParentDir"])

            if _should_hide_bin_entry_fast(path, parent_dir, cue_lookup):
                if progress_callback and (scanned % 500 == 0 or scanned == total):
                    progress_callback(scanned)
                continue

            filename = _make_filename_fast(path, parent_dir)
            title_name = _safe_text(row["TitleName"])
            system_id = _safe_text(row["SystemID"]) or "Unknown"
            system_name = _safe_text(row["SystemName"]) or system_id or "Unknown"
            display_name = filename or title_name or path

            entries.append(
                {
                    "name": display_name,
                    "filename": filename or display_name,
                    "title_name": title_name,
                    "path": path,
                    "parent_dir": parent_dir,
                    "directory": parent_dir,
                    "type": "game",
                    "system": system_name,
                    "system_id": system_id,
                    "system_name": system_name,
                    "zapScript": None,
                    "is_missing": bool(row["IsMissing"]),
                    "media_dbid": row["MediaDBID"],
                }
            )

            if progress_callback and (scanned % 500 == 0 or scanned == total):
                progress_callback(scanned)

        return entries

    except ZaparooApiError:
        raise
    except RuntimeError as e:
        if str(e) == "__LOAD_CANCELLED__":
            raise
        raise ZaparooApiError(f"Could not read media.db:\n{e}") from e
    except Exception as e:
        raise ZaparooApiError(f"Could not read media.db:\n{e}") from e
    finally:
        try:
            db.close()
        except Exception:
            pass

def fetch_media_from_db_cache(
    connection,
    local_path: Path,
    progress_callback=None,
) -> list[dict]:
    """
    Download media.db from MiSTer and read it into ZapScripts-compatible entries.
    """
    download_media_db(connection, local_path)
    return read_media_db_entries(
        local_path,
        progress_callback=progress_callback,
        include_missing=False,
    )


def list_scripts(connection) -> list[dict]:
    """
    Return all .sh files in /media/fat/Scripts as launcher entries.
    """
    if not connection.is_connected():
        return []

    output = connection.run_command(
        r'find /media/fat/Scripts -maxdepth 1 -type f -name "*.sh" | sort'
    )

    scripts = []
    for line in (output or "").splitlines():
        path = line.strip()
        if not path:
            continue

        filename = Path(path).name
        scripts.append(
            {
                "name": filename,
                "filename": filename,
                "path": path,
                "system": "Scripts",
                "type": "script",
            }
        )

    return scripts


def launch_media(connection, item: dict, timeout: int = 5):
    """
    Launch a cached media item or script item.

    For scripts:
    - launch via **mister.script:<name>.sh

    For games:
    - prefer launching by path
    - ignore zapScript if a path exists
    """
    item_type = (item or {}).get("type", "").strip().lower()

    if item_type == "script":
        script_name = (
            item.get("filename")
            or item.get("name")
            or Path(item.get("path", "")).name
        )
        return run_script(connection, script_name, timeout=timeout)

    path = item.get("path")
    if path:
        return run_zaparoo_command(connection, path, timeout=timeout)

    zap_script = item.get("zapScript") or item.get("zap_script")
    if zap_script:
        return run_zaparoo_command(connection, zap_script, timeout=timeout)

    raise ZaparooApiError("Selected item does not contain launchable data.")


def get_zapscripts_state(connection) -> dict:
    if not connection.is_connected():
        return {
            "zaparoo_installed": False,
            "zaparoo_service_enabled": False,
        }

    zaparoo_check = connection.run_command(
        "test -f /media/fat/Scripts/zaparoo.sh && echo EXISTS"
    )
    zaparoo_installed = "EXISTS" in (zaparoo_check or "")

    service_check = connection.run_command(
        "grep 'mrext/zaparoo' /media/fat/linux/user-startup.sh 2>/dev/null"
    )
    zaparoo_service_enabled = bool(
        service_check and "mrext/zaparoo" in service_check
    )

    return {
        "zaparoo_installed": zaparoo_installed,
        "zaparoo_service_enabled": zaparoo_service_enabled,
    }

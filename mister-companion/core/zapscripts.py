import json
import sqlite3
from pathlib import Path

from websocket import create_connection


REMOTE_MEDIA_DB_PATH = "/media/fat/zaparoo/media.db"


class ZaparooApiError(RuntimeError):
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


def _send_ws_payload(connection, payload: dict, timeout: int = 5):
    ws_url = _build_ws_url(connection)

    ws = None
    try:
        ws = create_connection(ws_url, timeout=timeout)
        ws.send(json.dumps(payload))
        response_raw = ws.recv()

        try:
            response = json.loads(response_raw)
        except Exception:
            response = {"raw": response_raw}

        if isinstance(response, dict) and response.get("error"):
            error = response["error"]
            if isinstance(error, dict):
                message = error.get("message") or str(error)
            else:
                message = str(error)
            raise ZaparooApiError(message)

        return response

    except Exception as e:
        if isinstance(e, ZaparooApiError):
            raise
        raise ZaparooApiError(str(e)) from e
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


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


def download_media_db(connection, local_path: Path) -> Path:
    """
    Download Zaparoo's media.db from the MiSTer.

    Remote:
        /media/fat/zaparoo/media.db

    Local:
        zaplauncher/<profile_or_ip>_media.db
    """
    if not local_path:
        raise ZaparooApiError("No local media.db path was provided.")

    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = local_path.with_suffix(local_path.suffix + ".tmp")

    sftp = None
    should_close = False

    try:
        sftp, should_close = _open_sftp(connection)

        try:
            sftp.get(REMOTE_MEDIA_DB_PATH, str(tmp_path))
        except FileNotFoundError:
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

        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


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

        # Some ROM/listing names can contain malformed or legacy encoded bytes.
        # Without this, one bad filename can crash the entire scan.
        db.text_factory = lambda value: value.decode("utf-8", errors="replace")

        db.row_factory = sqlite3.Row
    except Exception as e:
        raise ZaparooApiError(f"Could not open media.db:\n{e}") from e

    try:
        cursor = db.cursor()

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

        scanned = 0

        for row in cursor:
            scanned += 1

            path = _safe_text(row["FullPath"])
            parent_dir = _safe_text(row["ParentDir"])
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


def fetch_media_from_db_cache(
    connection,
    local_path: Path,
    progress_callback=None,
) -> list[dict]:
    """
    Download media.db from MiSTer and read it into ZapScripts-compatible entries.
    """
    download_media_db(connection, local_path)
    return read_media_db_entries(local_path, progress_callback=progress_callback)


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
        return run_zaparoo_command(connection, f"**launch:{path}", timeout=timeout)

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
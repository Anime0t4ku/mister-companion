import json
import time
from pathlib import Path

from websocket import create_connection


class ZaparooApiError(RuntimeError):
    pass


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


def fetch_all_media(connection, progress_callback=None, timeout: int = 10) -> list[dict]:
    """
    Fetch all indexed media from Zaparoo Core API using pagination.

    Uses a single persistent WebSocket for the whole scan to avoid
    repeated connection handshakes causing HTTP 429 errors.
    """
    ws_url = _build_ws_url(connection)

    all_items = []
    cursor = None
    page = 0

    max_results = 25
    inter_request_delay = 0.75
    max_retries = 8
    initial_backoff = 2.0

    ws = None
    try:
        ws = create_connection(ws_url, timeout=timeout)

        while True:
            params = {"maxResults": max_results}
            if cursor:
                params["cursor"] = cursor

            payload = {
                "jsonrpc": "2.0",
                "method": "media.search",
                "params": params,
                "id": page + 1,
            }

            attempt = 0
            while True:
                try:
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

                        if "rate limit" in message.lower():
                            if attempt >= max_retries:
                                raise ZaparooApiError(message)

                            backoff = initial_backoff * (2 ** attempt)
                            print(
                                f"Rate limit hit on page {page + 1}, "
                                f"retry {attempt + 1}/{max_retries}, sleeping {backoff:.1f}s"
                            )
                            time.sleep(backoff)
                            attempt += 1
                            continue

                        raise ZaparooApiError(message)

                    break

                except Exception as e:
                    message = str(e).lower()

                    if "429" in message or "too many requests" in message or "rate limit" in message:
                        if attempt >= max_retries:
                            raise ZaparooApiError(str(e))

                        backoff = initial_backoff * (2 ** attempt)
                        print(
                            f"Transport/API rate limit on page {page + 1}, "
                            f"retry {attempt + 1}/{max_retries}, sleeping {backoff:.1f}s"
                        )
                        time.sleep(backoff)
                        attempt += 1
                        continue

                    raise

            result = response.get("result", {}) if isinstance(response, dict) else {}

            items = result.get("results", []) if isinstance(result, dict) else []
            pagination = result.get("pagination", {}) if isinstance(result, dict) else {}

            print(
                f"Fetched page {page + 1}: {len(items)} items "
                f"(total so far: {len(all_items) + len(items)})"
            )

            for item in items:
                path = item.get("path", "") or ""
                filename = Path(path).name if path else (item.get("name", "") or "")

                system_obj = item.get("system") or {}
                if isinstance(system_obj, dict):
                    system_id = system_obj.get("id") or system_obj.get("name") or "Unknown"
                    system_name = system_obj.get("name") or system_obj.get("id") or "Unknown"
                else:
                    system_id = str(system_obj) if system_obj else "Unknown"
                    system_name = system_id

                normalized = dict(item)
                normalized["filename"] = filename
                normalized["type"] = "game"
                normalized["system_id"] = system_id
                normalized["system_name"] = system_name
                all_items.append(normalized)

            page += 1
            if progress_callback:
                try:
                    progress_callback(page, len(all_items), pagination)
                except TypeError:
                    progress_callback(page)

            has_next = pagination.get("hasNextPage")
            next_cursor = pagination.get("nextCursor")

            if not has_next or not next_cursor:
                break

            cursor = next_cursor
            time.sleep(inter_request_delay)

    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    return all_items


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
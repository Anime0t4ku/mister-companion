import json

from websocket import create_connection


class ZaparooApiError(RuntimeError):
    pass


def _build_ws_url(connection) -> str:
    host = getattr(connection, "host", "").strip()
    if not host:
        raise ZaparooApiError("No MiSTer IP is available.")

    return f"ws://{host}:7497/api/v0.1"


def run_zaparoo_command(connection, command: str, timeout: int = 5):
    if not command:
        raise ValueError("Command is required.")

    ws_url = _build_ws_url(connection)

    payload = {
        "jsonrpc": "2.0",
        "method": "run",
        "params": command,
        "id": 1,
    }

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


def get_zapscripts_state(connection) -> dict:
    if not connection.is_connected():
        return {
            "zaparoo_installed": False,
            "zaparoo_service_enabled": False,
            "update_all_installed": False,
            "migrate_sd_installed": False,
            "insertcoin_installed": False,
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

    update_check = connection.run_command(
        "test -f /media/fat/Scripts/update_all.sh && echo EXISTS"
    )
    update_all_installed = "EXISTS" in (update_check or "")

    migrate_check = connection.run_command(
        "test -f /media/fat/Scripts/migrate_sd.sh && echo EXISTS"
    )
    migrate_sd_installed = "EXISTS" in (migrate_check or "")

    insertcoin_check = connection.run_command(
        "test -f /media/fat/Scripts/update_all_insertcoin.sh && echo EXISTS"
    )
    insertcoin_installed = "EXISTS" in (insertcoin_check or "")

    return {
        "zaparoo_installed": zaparoo_installed,
        "zaparoo_service_enabled": zaparoo_service_enabled,
        "update_all_installed": update_all_installed,
        "migrate_sd_installed": migrate_sd_installed,
        "insertcoin_installed": insertcoin_installed,
    }
import json

import requests


RETROACCOUNT_BASE_URL = "https://retroaccount.com"
RETROACCOUNT_CLIENT_ID = "mister-companion"

RETROACCOUNT_CONFIG_DIR = "/media/fat/Scripts/.config/retroaccount"
RETROACCOUNT_USER_JSON_PATH = f"{RETROACCOUNT_CONFIG_DIR}/user.json"
RETROACCOUNT_DEVICE_ID_PATH = f"{RETROACCOUNT_CONFIG_DIR}/device.id"


def _extract_code(payload):
    for key in ("code", "device_code", "user_code"):
        value = payload.get(key)
        if value:
            return str(value)
    raise RuntimeError("RetroAccount response did not include a login code.")


def _api_post(path, payload):
    url = f"{RETROACCOUNT_BASE_URL}{path}"
    return requests.post(url, json=payload, timeout=20)


def _ensure_remote_dir(connection):
    connection.run_command(f'mkdir -p "{RETROACCOUNT_CONFIG_DIR}"')


def _write_remote_text(connection, path, text):
    if not connection.is_connected():
        raise RuntimeError("Not connected")

    _ensure_remote_dir(connection)

    sftp = connection.client.open_sftp()
    try:
        with sftp.file(path, "w") as f:
            f.write(text)
    finally:
        sftp.close()


def _read_remote_text(connection, path):
    if not connection.is_connected():
        raise RuntimeError("Not connected")

    sftp = connection.client.open_sftp()
    try:
        with sftp.file(path, "r") as f:
            return f.read().decode("utf-8", errors="ignore")
    finally:
        sftp.close()


def _remote_exists(connection, path):
    if not connection.is_connected():
        raise RuntimeError("Not connected")

    sftp = connection.client.open_sftp()
    try:
        try:
            sftp.stat(path)
            return True
        except (FileNotFoundError, OSError):
            return False
    finally:
        sftp.close()


def get_retroaccount_status(connection):
    user_exists = _remote_exists(connection, RETROACCOUNT_USER_JSON_PATH)
    device_id_exists = _remote_exists(connection, RETROACCOUNT_DEVICE_ID_PATH)

    if not user_exists or not device_id_exists:
        return {
            "logged_in": False,
            "device_id": "",
        }

    device_id = _read_remote_text(connection, RETROACCOUNT_DEVICE_ID_PATH).strip()

    return {
        "logged_in": True,
        "device_id": device_id,
    }


def start_retroaccount_login(connection):
    if not connection.is_connected():
        raise RuntimeError("Not connected")

    response = _api_post(
        "/api/auth/device/code",
        {"client_id": RETROACCOUNT_CLIENT_ID},
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"RetroAccount code request failed with status {response.status_code}."
        )

    payload = response.json()
    code = _extract_code(payload)
    url = f"{RETROACCOUNT_BASE_URL}/code?c={code}&from={RETROACCOUNT_CLIENT_ID}"

    return {
        "code": code,
        "url": url,
    }


def poll_retroaccount_login(connection, device_code):
    if not connection.is_connected():
        raise RuntimeError("Not connected")

    response = _api_post(
        "/api/auth/token",
        {
            "device_code": device_code,
            "client_id": RETROACCOUNT_CLIENT_ID,
        },
    )

    if response.status_code == 428:
        return {
            "status": "pending",
        }

    if response.status_code != 200:
        raise RuntimeError(
            f"RetroAccount token request failed with status {response.status_code}."
        )

    payload = response.json()
    credentials = payload.get("credentials")
    if not isinstance(credentials, dict):
        raise RuntimeError("RetroAccount response did not include a credentials object.")

    device_id = credentials.get("device_id")
    if not device_id:
        raise RuntimeError("RetroAccount credentials did not include device_id.")

    credentials_json = json.dumps(credentials, indent=2, ensure_ascii=False)

    _write_remote_text(connection, RETROACCOUNT_USER_JSON_PATH, credentials_json)
    _write_remote_text(connection, RETROACCOUNT_DEVICE_ID_PATH, str(device_id).strip())

    return {
        "status": "logged_in",
        "device_id": str(device_id).strip(),
    }
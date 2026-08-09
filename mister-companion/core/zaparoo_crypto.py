import base64
import ctypes
import hashlib
import hmac
import json
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.app_paths import generated_path


PAIRING_SERVICE = "MiSTer Companion Zaparoo"
CLIENT_NAME = "MiSTer Companion"
PAIR_START_PATH = "/api/pair/start"
PAIR_FINISH_PATH = "/api/pair/finish"
PAIRING_FILE = generated_path("zaparoo_pairing.json")
_PAIRING_LOCKS_GUARD = threading.Lock()
_PAIRING_LOCKS: dict[str, threading.Lock] = {}

# NIST P-256 / secp256r1 parameters.
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = (_P - 3) % _P
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_G = (
    0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
    0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5,
)
_U = (
    793136080485469241208656611513609866400481671852,
    59748757929350367369315811184980635230185250460108398961713395032485227207304,
)
_V = (
    1086685267857089638167386722555472967068468061489,
    9157340230202296554417312816309453883742349874205386245733062928888341584123,
)


class ZaparooCryptoError(RuntimeError):
    pass


@dataclass(frozen=True)
class PairingCredentials:
    auth_token: str
    pairing_key: bytes
    client_id: str = ""


@dataclass
class EncryptedSession:
    auth_token: str
    session_salt: bytes
    c2s_key: bytes
    s2c_key: bytes
    c2s_nonce_base: bytes
    s2c_nonce_base: bytes
    send_counter: int = 0
    recv_counter: int = 0

    @property
    def aad(self) -> bytes:
        return f"{self.auth_token}:ws".encode("utf-8")

    def encrypt_payload(self, payload: dict) -> dict:
        plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        nonce = _counter_nonce(self.c2s_nonce_base, self.send_counter)
        ciphertext = AESGCM(self.c2s_key).encrypt(nonce, plaintext, self.aad)
        frame = {"e": base64.b64encode(ciphertext).decode("ascii")}
        if self.send_counter == 0:
            frame.update(
                {
                    "v": 1,
                    "t": self.auth_token,
                    "s": base64.b64encode(self.session_salt).decode("ascii"),
                }
            )
        self.send_counter += 1
        return frame

    def decrypt_frame(self, frame: dict) -> dict:
        if not isinstance(frame, dict) or not frame.get("e"):
            raise ZaparooCryptoError("Invalid encrypted response from Zaparoo.")
        try:
            ciphertext = base64.b64decode(frame["e"], validate=True)
            nonce = _counter_nonce(self.s2c_nonce_base, self.recv_counter)
            plaintext = AESGCM(self.s2c_key).decrypt(nonce, ciphertext, self.aad)
            response = json.loads(plaintext.decode("utf-8"))
        except Exception as exc:
            raise ZaparooCryptoError("Could not decrypt the Zaparoo response.") from exc
        self.recv_counter += 1
        return response


def _credential_name(host: str) -> str:
    host = str(host or "").strip().lower()
    if not host:
        raise ZaparooCryptoError("No MiSTer IP is available.")
    return host


def _load_store() -> dict:
    if not PAIRING_FILE.exists():
        return {}
    try:
        data = json.loads(PAIRING_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_store(data: dict) -> None:
    PAIRING_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PAIRING_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    tmp.replace(PAIRING_FILE)
    try:
        os.chmod(PAIRING_FILE, 0o600)
    except Exception:
        pass


def _windows_dpapi_encrypt(data: bytes) -> bytes:
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    buf = ctypes.create_string_buffer(data)
    in_blob = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _windows_dpapi_decrypt(data: bytes) -> bytes:
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    buf = ctypes.create_string_buffer(data)
    in_blob = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _mac_keychain_get(account: str) -> str | None:
    result = subprocess.run(
        ["security", "find-generic-password", "-s", PAIRING_SERVICE, "-a", account, "-w"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _mac_keychain_set(account: str, secret: str) -> None:
    result = subprocess.run(
        ["security", "add-generic-password", "-U", "-s", PAIRING_SERVICE, "-a", account, "-w", secret],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ZaparooCryptoError(result.stderr.strip() or "Could not save Zaparoo credentials in macOS Keychain.")


def _mac_keychain_delete(account: str) -> None:
    subprocess.run(
        ["security", "delete-generic-password", "-s", PAIRING_SERVICE, "-a", account],
        capture_output=True,
        text=True,
        check=False,
    )


def _linux_secret_get(account: str) -> str | None:
    if not shutil.which("secret-tool"):
        return None
    result = subprocess.run(
        ["secret-tool", "lookup", "application", PAIRING_SERVICE, "host", account],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def _linux_secret_set(account: str, secret: str) -> bool:
    if not shutil.which("secret-tool"):
        return False
    result = subprocess.run(
        ["secret-tool", "store", "--label", f"{PAIRING_SERVICE} ({account})", "application", PAIRING_SERVICE, "host", account],
        input=secret,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _linux_secret_delete(account: str) -> None:
    if shutil.which("secret-tool"):
        subprocess.run(
            ["secret-tool", "clear", "application", PAIRING_SERVICE, "host", account],
            capture_output=True,
            text=True,
            check=False,
        )


def _encode_credentials(credentials: PairingCredentials) -> str:
    return json.dumps(
        {
            "auth_token": credentials.auth_token,
            "pairing_key": base64.b64encode(credentials.pairing_key).decode("ascii"),
            "client_id": credentials.client_id,
        },
        separators=(",", ":"),
    )


def _decode_credentials(raw: str) -> PairingCredentials:
    try:
        data = json.loads(raw)
        token = str(data.get("auth_token", "")).strip()
        key = base64.b64decode(data.get("pairing_key", ""), validate=True)
        client_id = str(data.get("client_id", "") or "").strip()
        if not token or len(key) != 32:
            raise ValueError
        return PairingCredentials(token, key, client_id)
    except Exception as exc:
        raise ZaparooCryptoError("Saved Zaparoo pairing credentials are invalid.") from exc


def load_pairing_credentials(host: str) -> PairingCredentials | None:
    account = _credential_name(host)
    try:
        if sys.platform == "win32":
            entry = _load_store().get(account)
            if not entry:
                return None
            blob = base64.b64decode(entry.get("dpapi", ""), validate=True)
            return _decode_credentials(_windows_dpapi_decrypt(blob).decode("utf-8"))
        if sys.platform == "darwin":
            raw = _mac_keychain_get(account)
            return _decode_credentials(raw) if raw else None

        raw = _linux_secret_get(account)
        if raw:
            return _decode_credentials(raw)
        # Official Zaparoo guidance for CLI-style clients is a 0600 config file.
        raw = _load_store().get(account, {}).get("credentials")
        return _decode_credentials(raw) if raw else None
    except ZaparooCryptoError:
        raise
    except Exception as exc:
        raise ZaparooCryptoError("Could not access the saved Zaparoo pairing credential.") from exc



def has_pairing_credentials(host: str) -> bool:
    try:
        return load_pairing_credentials(host) is not None
    except ZaparooCryptoError:
        return False


def _pairing_lock(host: str) -> threading.Lock:
    account = _credential_name(host)
    with _PAIRING_LOCKS_GUARD:
        lock = _PAIRING_LOCKS.get(account)
        if lock is None:
            lock = threading.Lock()
            _PAIRING_LOCKS[account] = lock
        return lock

def save_pairing_credentials(host: str, credentials: PairingCredentials) -> None:
    account = _credential_name(host)
    raw = _encode_credentials(credentials)
    try:
        if sys.platform == "win32":
            store = _load_store()
            encrypted = _windows_dpapi_encrypt(raw.encode("utf-8"))
            store[account] = {"dpapi": base64.b64encode(encrypted).decode("ascii")}
            _save_store(store)
            return
        if sys.platform == "darwin":
            _mac_keychain_set(account, raw)
            return
        if _linux_secret_set(account, raw):
            return
        store = _load_store()
        store[account] = {"credentials": raw}
        _save_store(store)
    except ZaparooCryptoError:
        raise
    except Exception as exc:
        raise ZaparooCryptoError("Pairing succeeded, but the credential could not be saved securely.") from exc


def clear_pairing_credentials(host: str) -> None:
    account = _credential_name(host)
    if sys.platform == "darwin":
        _mac_keychain_delete(account)
        return
    if sys.platform != "win32":
        _linux_secret_delete(account)
    store = _load_store()
    if account in store:
        store.pop(account, None)
        _save_store(store)


def create_encrypted_session(credentials: PairingCredentials) -> EncryptedSession:
    session_salt = os.urandom(16)
    prk = _hkdf_extract(credentials.pairing_key, session_salt)
    return EncryptedSession(
        credentials.auth_token,
        session_salt,
        _hkdf_expand(prk, b"zaparoo-c2s-v1", 32),
        _hkdf_expand(prk, b"zaparoo-s2c-v1", 32),
        _hkdf_expand(prk, b"zaparoo-c2s-nonce-v1", 12),
        _hkdf_expand(prk, b"zaparoo-s2c-nonce-v1", 12),
    )


def pair_with_pin(host: str, pin: str, timeout: int = 8) -> PairingCredentials:
    host = str(host or "").strip()
    pin = str(pin or "").strip()
    if not host:
        raise ZaparooCryptoError("No MiSTer IP is available.")
    if len(pin) != 6 or not pin.isdigit():
        raise ZaparooCryptoError("The Zaparoo pairing PIN must contain exactly 6 digits.")

    lock = _pairing_lock(host)
    if not lock.acquire(blocking=False):
        raise ZaparooCryptoError("A Zaparoo pairing attempt is already in progress for this MiSTer.")

    try:
        return _pair_with_pin_locked(host, pin, timeout)
    finally:
        lock.release()


def _pair_with_pin_locked(host: str, pin: str, timeout: int) -> PairingCredentials:
    pake = _PakeClient(pin.encode("ascii"))
    msg_a = pake.wire_bytes()
    start = _post_pairing_json(
        f"http://{host}:7497{PAIR_START_PATH}",
        {"pake": base64.b64encode(msg_a).decode("ascii"), "name": CLIENT_NAME},
        timeout,
    )
    session_id = str(start.get("session", "") or "").strip()
    try:
        msg_b = base64.b64decode(start.get("pake", ""), validate=True)
    except Exception as exc:
        raise ZaparooCryptoError("Zaparoo returned an invalid PAKE response.") from exc
    if not session_id or not msg_b:
        raise ZaparooCryptoError("Zaparoo returned an incomplete pairing response.")

    session_key = pake.update(msg_b)
    prk = _hkdf_extract(session_key, msg_a + msg_b)
    confirm_key_a = _hkdf_expand(prk, b"zaparoo-confirm-A", 32)
    confirm_key_b = _hkdf_expand(prk, b"zaparoo-confirm-B", 32)
    pairing_key = _hkdf_expand(prk, b"zaparoo-pairing-v1", 32)
    client_confirm = hmac.new(
        confirm_key_a,
        _confirm_transcript("client", CLIENT_NAME, msg_a, msg_b),
        hashlib.sha256,
    ).digest()

    # Zaparoo rate-limits all /api/pair/* requests to one request per second
    # per client IP. /pair/start and /pair/finish are two separate requests, so
    # finishing immediately after the start response reliably triggers HTTP 429.
    # Leave a small margin above one second before sending /pair/finish.
    time.sleep(1.1)

    finish = _post_pairing_json(
        f"http://{host}:7497{PAIR_FINISH_PATH}",
        {"session": session_id, "confirm": base64.b64encode(client_confirm).decode("ascii")},
        timeout,
    )
    auth_token = str(finish.get("authToken", "") or "").strip()
    client_id = str(finish.get("clientId", "") or "").strip()
    try:
        server_confirm = base64.b64decode(finish.get("confirm", ""), validate=True)
    except Exception as exc:
        raise ZaparooCryptoError("Zaparoo returned an invalid pairing confirmation.") from exc
    expected = hmac.new(
        confirm_key_b,
        _confirm_transcript("server", CLIENT_NAME, msg_a, msg_b),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(server_confirm, expected):
        raise ZaparooCryptoError("Zaparoo pairing confirmation could not be verified.")
    if not auth_token:
        raise ZaparooCryptoError("Zaparoo did not return an authentication token.")

    credentials = PairingCredentials(auth_token, pairing_key, client_id)
    save_pairing_credentials(host, credentials)
    return credentials


def _post_pairing_json(url: str, payload: dict, timeout: int) -> dict:
    try:
        response = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise ZaparooCryptoError(f"Could not contact Zaparoo for pairing: {exc}") from exc
    if response.status_code >= 400:
        message = {
            400: "Zaparoo rejected the pairing request.",
            401: "The Zaparoo pairing PIN is incorrect.",
            403: "Zaparoo cannot accept another pairing or the pairing attempts were exhausted.",
            404: "The Zaparoo pairing session is no longer available.",
            410: "The Zaparoo pairing PIN has expired. Generate a new PIN and try again.",
            429: "Zaparoo pairing was rate-limited. Wait a moment and try again.",
        }.get(response.status_code, f"Zaparoo pairing failed with HTTP status {response.status_code}.")
        raise ZaparooCryptoError(message)
    try:
        body = response.json()
    except Exception as exc:
        raise ZaparooCryptoError("Zaparoo returned an invalid pairing response.") from exc
    return body if isinstance(body, dict) else {}


def _hkdf_extract(ikm: bytes, salt: bytes) -> bytes:
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    output = b""
    previous = b""
    counter = 1
    while len(output) < length:
        previous = hmac.new(prk, previous + info + bytes([counter]), hashlib.sha256).digest()
        output += previous
        counter += 1
    return output[:length]


def _counter_nonce(base: bytes, counter: int) -> bytes:
    if len(base) != 12 or counter < 0 or counter >= (1 << 64):
        raise ZaparooCryptoError("Invalid Zaparoo encrypted-session nonce state.")
    return base[:4] + bytes(a ^ b for a, b in zip(base[4:], counter.to_bytes(8, "big")))


def _lp(value: bytes) -> bytes:
    return struct.pack(">I", len(value)) + value


def _confirm_transcript(role: str, client_name: str, msg_a: bytes, msg_b: bytes) -> bytes:
    return b"".join(
        (
            _lp(b"zaparoo-v1"), _lp(b"p256"), _lp(role.encode()),
            _lp(client_name.encode()), _lp(msg_a), _lp(msg_b),
        )
    )


def _int_bytes(value: int) -> bytes:
    return value.to_bytes((value.bit_length() + 7) // 8, "big") if value else b""


def _is_on_curve(point) -> bool:
    if point is None:
        return True
    x, y = point
    return (y * y - (x * x * x + _A * x + _B)) % _P == 0


def _point_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % _P == 0:
        return None
    if p1 == p2:
        slope = ((3 * x1 * x1 + _A) * pow(2 * y1, -1, _P)) % _P
    else:
        slope = ((y2 - y1) * pow((x2 - x1) % _P, -1, _P)) % _P
    x3 = (slope * slope - x1 - x2) % _P
    y3 = (slope * (x1 - x3) - y1) % _P
    return x3, y3


def _scalar_mult(point, scalar: int):
    scalar %= _N
    result = None
    addend = point
    while scalar:
        if scalar & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        scalar >>= 1
    return result


def _point_dict(role: int, x_point, y_point) -> dict:
    return {
        "role": role,
        "ux": str(_U[0]), "uy": str(_U[1]),
        "vx": str(_V[0]), "vy": str(_V[1]),
        "xx": str(x_point[0] if x_point else 0),
        "xy": str(x_point[1] if x_point else 0),
        "yx": str(y_point[0] if y_point else 0),
        "yy": str(y_point[1] if y_point else 0),
    }


class _PakeClient:
    def __init__(self, password: bytes):
        self.password = password
        pw_scalar = int.from_bytes(password, "big")
        self.vpw = _scalar_mult(_V, pw_scalar)
        self.upw = _scalar_mult(_U, pw_scalar)
        self.secret = int.from_bytes(os.urandom(32), "big") % _N or 1
        self.x_point = _point_add(self.upw, _scalar_mult(_G, self.secret))
        self.y_point = None

    def wire_bytes(self) -> bytes:
        return json.dumps(_point_dict(0, self.x_point, self.y_point), separators=(",", ":")).encode()

    def update(self, peer_wire: bytes) -> bytes:
        try:
            peer = json.loads(peer_wire.decode())
            if int(peer.get("role", -1)) != 1:
                raise ValueError
            self.y_point = (int(peer["yx"]), int(peer["yy"]))
            if not _is_on_curve(self.y_point):
                raise ValueError
        except Exception as exc:
            raise ZaparooCryptoError("Zaparoo returned an invalid PAKE point.") from exc
        neg_vpw = (self.vpw[0], (-self.vpw[1]) % _P)
        z_point = _scalar_mult(_point_add(self.y_point, neg_vpw), self.secret)
        digest = hashlib.sha256()
        digest.update(self.password)
        for value in (*self.x_point, *self.y_point, *z_point):
            digest.update(_int_bytes(value))
        return digest.digest()

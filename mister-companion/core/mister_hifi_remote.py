import json
import threading
import time
from urllib.parse import quote

import requests
from websocket import create_connection


DEFAULT_PORT = 8182


def _host(connection):
    return str(getattr(connection, "host", "") or "").strip()


def base_url(connection, port=DEFAULT_PORT):
    host = _host(connection)
    return f"http://{host}:{port}" if host else ""


def ws_url(connection, port=DEFAULT_PORT):
    host = _host(connection)
    return f"ws://{host}:{port}/ws" if host else ""


def _request(connection, method, path, *, params=None, payload=None, timeout=3):
    base = base_url(connection)
    if not base:
        raise RuntimeError("No MiSTer host is connected.")
    response = requests.request(method, base + path, params=params, json=payload, timeout=timeout)
    response.raise_for_status()
    ctype = response.headers.get("content-type", "")
    if "json" in ctype:
        return response.json()
    return response.content


def get_sources(connection, timeout=3):
    data = _request(connection, "GET", "/api/sources", timeout=timeout)
    return data if isinstance(data, list) else []


def browse(connection, source, path="", timeout=4):
    data = _request(connection, "GET", "/api/browse", params={"source": source, "path": path or ""}, timeout=timeout)
    return data if isinstance(data, dict) else {}


def play(connection, source, path, timeout=4):
    return _request(connection, "POST", "/api/play", payload={"source": source, "path": path}, timeout=timeout)


def control(connection, action, timeout=3):
    return _request(connection, "POST", "/api/control", payload={"action": action}, timeout=timeout)


def seek(connection, position, timeout=3):
    return _request(connection, "POST", "/api/seek", payload={"position": float(position)}, timeout=timeout)


def artwork(connection, art_key, timeout=4):
    if not art_key:
        return b""
    data = _request(connection, "GET", "/api/art", params={"k": art_key}, timeout=timeout)
    return data if isinstance(data, (bytes, bytearray)) else b""


class HiFiWebSocketListener:
    """Small websocket listener used by the dashboard; callbacks run on its worker thread."""

    def __init__(self, connection, on_state, on_connected=None, on_disconnected=None):
        self.connection = connection
        self.on_state = on_state
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self._stop = threading.Event()
        self._thread = None
        self._ws = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="MiSTerHiFiWebSocket", daemon=True)
        self._thread.start()

    def stop(self, join_timeout=0.0):
        """Stop the listener and optionally wait briefly for its worker thread.

        Closing the websocket wakes a blocking recv() so the thread can unwind
        promptly.  The bounded join is used during UI teardown to avoid leaving
        a native websocket thread racing Qt object destruction.
        """
        self._stop.set()
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

        thread = self._thread
        if (
            join_timeout
            and thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(max(0.0, float(join_timeout)))

        if thread is not None and not thread.is_alive():
            self._thread = None

    def _run(self):
        was_connected = False
        while not self._stop.is_set():
            url = ws_url(self.connection)
            if not url:
                break
            try:
                ws = create_connection(url, timeout=3)
                ws.settimeout(2)
                self._ws = ws
                was_connected = True
                if self.on_connected:
                    self.on_connected()
                while not self._stop.is_set():
                    try:
                        raw = ws.recv()
                    except Exception:
                        break
                    if not raw:
                        break
                    try:
                        state = json.loads(raw)
                    except Exception:
                        continue
                    if isinstance(state, dict) and self.on_state:
                        self.on_state(state)
            except Exception:
                pass
            finally:
                ws = self._ws
                self._ws = None
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass
                if was_connected and self.on_disconnected:
                    self.on_disconnected()
                was_connected = False
            if not self._stop.wait(1.5):
                continue

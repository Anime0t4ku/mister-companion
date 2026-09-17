"""Small HTTP client for an unmodified MiSTer Monitor server."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class MiSTerMonitorError(RuntimeError):
    pass


class MiSTerMonitorClient:
    PORT = 8081
    USER_AGENT = "MiSTer-Companion"

    def __init__(self, host: str, timeout: float = 1.5):
        self.host = (host or "").strip()
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        host = self.host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"http://{host}:{self.PORT}"

    def _request(self, path: str, timeout: float | None = None) -> bytes:
        if not self.host:
            raise MiSTerMonitorError("MiSTer address is unavailable.")
        request = Request(
            f"{self.base_url}{path}",
            headers={"User-Agent": self.USER_AGENT, "Accept": "application/json, image/*"},
        )
        try:
            with urlopen(request, timeout=timeout or self.timeout) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise MiSTerMonitorError(str(exc)) from exc

    def get_json(self, path: str, timeout: float | None = None) -> dict:
        try:
            payload = json.loads(self._request(path, timeout=timeout).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MiSTerMonitorError("MiSTer Monitor returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise MiSTerMonitorError("MiSTer Monitor returned an unexpected response.")
        return payload

    def snapshot(self) -> dict:
        payload = self.get_json("/status/snapshot")
        if "core" not in payload:
            raise MiSTerMonitorError("MiSTer Monitor snapshot is missing the core field.")
        return payload

    def artwork(self) -> bytes:
        data = self._request("/media/artwork", timeout=4.0)
        if len(data) > 20 * 1024 * 1024:
            raise MiSTerMonitorError("MiSTer Monitor artwork is too large.")
        return data


def probe_mister_monitor(host: str, timeout: float = 0.8) -> dict | None:
    """Return the live snapshot only when the Monitor server is reachable."""
    try:
        return MiSTerMonitorClient(host, timeout=timeout).snapshot()
    except MiSTerMonitorError:
        return None


def probe_mister_monitor_retroachievements(host: str, timeout: float = 0.8) -> dict | None:
    try:
        return MiSTerMonitorClient(host, timeout=timeout).get_json("/status/retroachievements")
    except MiSTerMonitorError:
        return None

"""Minimal RomM (romm.app) REST client — pairing-code auth.

Auth flow (mirrors decky-romm-sync):
  1. User generates a short-lived (60s) 8-char pairing code in the RomM web UI
     (Settings → API Tokens → Pair Device).
  2. Client does ``POST /api/client-tokens/exchange`` with ``{"code": "..."}`` —
     public/unauthenticated, one-shot. Response is a ``ClientTokenCreateSchema``
     whose ``raw_token`` is a long-lived bearer used on every subsequent call.
  3. Store ``raw_token`` in config; reuse across app launches until revoked in
     RomM's UI. No username/password ever handled.

Covers the read-only surface the v0 RomM tab needs: whoami, list platforms,
list ROMs by platform id. Downloads / save sync are out of scope for v0.
"""
from __future__ import annotations

import re

import requests

DEFAULT_TIMEOUT = 15
LIST_TIMEOUT = 60  # /api/roms can be slow on large libraries (thousands of ROMs)
_PAIR_CODE_RE = re.compile(r"[^A-Za-z0-9]")


class RomMError(Exception):
    pass


class RomMPairingError(RomMError):
    """Pairing-code exchange rejected. ``reason`` is a short machine tag."""

    def __init__(self, message: str, reason: str = "invalid"):
        super().__init__(message)
        self.reason = reason


def normalize_pairing_code(code: str) -> str:
    """Strip whitespace/dashes, uppercase, alphanumerics only."""
    return _PAIR_CODE_RE.sub("", (code or "")).upper()


class RomMClient:
    def __init__(self, base_url: str, token: str = "", verify_tls: bool = True):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.verify_tls = verify_tls
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self._token = token or ""
        if self._token:
            self.session.headers["Authorization"] = f"Bearer {self._token}"

    # ── URL helpers ───────────────────────────────────────────────────────
    def _url(self, path: str) -> str:
        if not self.base_url:
            raise RomMError("RomM URL is empty")
        return f"{self.base_url}{path}"

    @property
    def token(self) -> str:
        return self._token

    def set_token(self, token: str) -> None:
        self._token = token or ""
        if self._token:
            self.session.headers["Authorization"] = f"Bearer {self._token}"
        else:
            self.session.headers.pop("Authorization", None)

    # ── public / unauthenticated ──────────────────────────────────────────
    def heartbeat(self) -> dict:
        r = self.session.get(self._url("/api/heartbeat"), timeout=DEFAULT_TIMEOUT, verify=self.verify_tls)
        if r.status_code >= 400:
            raise RomMError(f"Heartbeat failed ({r.status_code}): {r.text[:200]}")
        return r.json()

    def exchange_pairing_code(self, code: str) -> dict:
        """One-shot exchange of a 60s pairing code for a Client API Token.

        Public endpoint — the code is itself the credential; no Authorization
        header is sent. Returns the ClientTokenCreateSchema; ``raw_token`` is
        the freshly rotated bearer. The client's Bearer header is set as a
        side effect so subsequent calls are authenticated.
        """
        normalized = normalize_pairing_code(code)
        if not normalized:
            raise RomMPairingError("Enter a pairing code", reason="empty")

        # Never carry a stale bearer on the exchange call.
        prior = self.session.headers.pop("Authorization", None)
        try:
            r = self.session.post(
                self._url("/api/client-tokens/exchange"),
                json={"code": normalized},
                timeout=DEFAULT_TIMEOUT,
                verify=self.verify_tls,
            )
        except requests.RequestException as exc:
            if prior:
                self.session.headers["Authorization"] = prior
            raise RomMError(f"Cannot reach RomM: {exc}") from exc

        if r.status_code == 404:
            raise RomMPairingError("Pairing code is invalid or expired", reason="invalid")
        if r.status_code == 403:
            raise RomMPairingError("Pairing token owner is disabled", reason="forbidden")
        if r.status_code == 429:
            raise RomMPairingError("Too many pairing attempts — wait a minute", reason="rate_limited")
        if r.status_code >= 400:
            raise RomMPairingError(f"Exchange failed ({r.status_code}): {r.text[:200]}", reason="server_error")

        payload = r.json()
        raw = payload.get("raw_token")
        if not raw:
            raise RomMPairingError("RomM returned no raw_token", reason="server_error")

        self.set_token(raw)
        return payload

    # ── authenticated ─────────────────────────────────────────────────────
    def _authed_get(self, path: str, params: dict | None = None, timeout: int = DEFAULT_TIMEOUT) -> dict | list:
        if not self._token:
            raise RomMError("No API token — pair the client first")
        r = self.session.get(
            self._url(path),
            params=params or {},
            timeout=timeout,
            verify=self.verify_tls,
        )
        if r.status_code == 401:
            raise RomMError("Token was revoked or is invalid — pair again")
        if r.status_code == 403:
            raise RomMError(f"Token lacks the required scope for {path}")
        if r.status_code >= 400:
            raise RomMError(f"{path} → HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    def whoami(self) -> dict:
        """Validate the bearer and return the current user."""
        return self._authed_get("/api/users/me")

    def get_platforms(self) -> list[dict]:
        data = self._authed_get("/api/platforms")
        return data if isinstance(data, list) else data.get("items", [])

    def get_collections(self) -> list[dict]:
        data = self._authed_get("/api/collections")
        return data if isinstance(data, list) else data.get("items", [])

    def get_firmware(self, platform_id: int) -> list[dict]:
        """List firmware/BIOS files registered for a platform."""
        data = self._authed_get("/api/firmware", params={"platform_id": platform_id})
        return data if isinstance(data, list) else data.get("items", [])

    def stream_firmware(self, firmware_id: int, file_name: str):
        """Stream a firmware file's raw bytes from RomM."""
        from urllib.parse import quote

        if not self._token:
            raise RomMError("No API token — pair the client first")
        url = self._url(f"/api/firmware/{firmware_id}/content/{quote(file_name, safe='')}")
        r = self.session.get(url, stream=True, timeout=LIST_TIMEOUT, verify=self.verify_tls)
        if r.status_code == 401:
            raise RomMError("Token was revoked or is invalid — pair again")
        if r.status_code >= 400:
            raise RomMError(f"Download firmware {file_name} → HTTP {r.status_code}: {r.text[:200]}")
        return r

    def stream_rom(self, rom_id: int, file_name: str, chunk_size: int = 1024 * 1024):
        """Stream a ROM file's raw bytes from RomM.

        Returns an iterator of bytes chunks. Caller writes them to a destination
        (SFTP put file / local file). Uses ``GET /api/roms/{id}/content/{name}``.
        """
        from urllib.parse import quote

        if not self._token:
            raise RomMError("No API token — pair the client first")
        url = self._url(f"/api/roms/{rom_id}/content/{quote(file_name, safe='')}")
        r = self.session.get(
            url,
            stream=True,
            timeout=LIST_TIMEOUT,
            verify=self.verify_tls,
        )
        if r.status_code == 401:
            raise RomMError("Token was revoked or is invalid — pair again")
        if r.status_code >= 400:
            raise RomMError(f"Download {file_name} → HTTP {r.status_code}: {r.text[:200]}")
        return r

    # ── saves / states ────────────────────────────────────────────────────
    def get_saves(self, rom_id: int) -> list[dict]:
        data = self._authed_get("/api/saves", params={"rom_id": rom_id})
        return data if isinstance(data, list) else data.get("items", [])

    def get_states(self, rom_id: int) -> list[dict]:
        data = self._authed_get("/api/states", params={"rom_id": rom_id})
        return data if isinstance(data, list) else data.get("items", [])

    def stream_asset(self, asset_kind: str, asset_id: int):
        """Stream a save (asset_kind='save') or state ('state') file."""
        if asset_kind not in ("save", "state"):
            raise RomMError(f"unknown asset_kind {asset_kind!r}")
        path = f"/api/{asset_kind}s/{asset_id}/content"
        if not self._token:
            raise RomMError("No API token — pair the client first")
        r = self.session.get(self._url(path), stream=True, timeout=LIST_TIMEOUT, verify=self.verify_tls)
        if r.status_code == 401:
            raise RomMError("Token was revoked or is invalid — pair again")
        if r.status_code >= 400:
            raise RomMError(f"Download {asset_kind} #{asset_id} → HTTP {r.status_code}: {r.text[:200]}")
        return r

    def upload_asset(
        self,
        asset_kind: str,
        rom_id: int,
        file_name: str,
        payload: bytes,
        emulator: str = "mister",
        slot: str | None = None,
    ) -> dict:
        """POST a new save/state for a ROM. asset_kind: 'save' | 'state'."""
        if asset_kind not in ("save", "state"):
            raise RomMError(f"unknown asset_kind {asset_kind!r}")
        if not self._token:
            raise RomMError("No API token — pair the client first")
        params: dict = {"rom_id": rom_id, "emulator": emulator}
        if slot is not None and asset_kind == "save":
            params["slot"] = slot
        field = "saveFile" if asset_kind == "save" else "stateFile"
        r = self.session.post(
            self._url(f"/api/{asset_kind}s"),
            params=params,
            files={field: (file_name, payload, "application/octet-stream")},
            timeout=LIST_TIMEOUT,
            verify=self.verify_tls,
        )
        if r.status_code == 401:
            raise RomMError("Token was revoked or is invalid — pair again")
        if r.status_code >= 400:
            raise RomMError(f"Upload {asset_kind} → HTTP {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}

    def update_asset(self, asset_kind: str, asset_id: int, file_name: str, payload: bytes) -> dict:
        """PUT updated content for an existing save/state."""
        if asset_kind not in ("save", "state"):
            raise RomMError(f"unknown asset_kind {asset_kind!r}")
        if not self._token:
            raise RomMError("No API token — pair the client first")
        field = "saveFile" if asset_kind == "save" else "stateFile"
        r = self.session.put(
            self._url(f"/api/{asset_kind}s/{asset_id}"),
            files={field: (file_name, payload, "application/octet-stream")},
            timeout=LIST_TIMEOUT,
            verify=self.verify_tls,
        )
        if r.status_code == 401:
            raise RomMError("Token was revoked or is invalid — pair again")
        if r.status_code >= 400:
            raise RomMError(f"Update {asset_kind} #{asset_id} → HTTP {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}

    def get_roms(
        self,
        *,
        platform_id: int | None = None,
        collection_id: int | None = None,
        limit: int = 5000,
        offset: int = 0,
        with_files: bool = False,
    ) -> list[dict]:
        """List ROMs filtered by platform or collection.

        RomM's ``/api/roms`` uses ``platform_ids`` (plural) — the singular form is
        silently ignored, so a bad name returns the whole library and can time out.
        """
        params: dict = {
            "limit": limit,
            "offset": offset,
            "order_by": "name",
            "with_files": "true" if with_files else "false",
            "with_char_index": "false",
            "with_filter_values": "false",
        }
        if platform_id is not None:
            params["platform_ids"] = platform_id
        if collection_id is not None:
            params["collection_id"] = collection_id
        data = self._authed_get("/api/roms", params=params, timeout=LIST_TIMEOUT)
        return data.get("items", data) if isinstance(data, dict) else data

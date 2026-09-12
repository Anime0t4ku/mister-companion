import hashlib
import hmac
import json
import platform
import uuid
import secrets
import time
from typing import Any
from urllib.parse import urlparse

import requests

from core.app_info import APP_VERSION
from core.config import save_config
from core.device_profiles import (
    PROFILE_SYNC_ID_KEY,
    ensure_profile_sync_ids,
    get_devices,
    profile_sync_state,
)
from core.profile_identity import migrate_profile_identity, remove_profile_identity
from core.custom_themes import (
    THEME_SYNC_ID_KEY,
    ensure_theme_creator_sync_id,
    is_theme_creator_theme_data,
    normalize_theme_id,
    theme_creator_files,
    themes_dir,
    local_theme_ids,
    install_patreon_theme,
)
from core.update_all_config import (
    CUSTOM_SOURCE_SYNC_ID_KEY,
    clear_custom_source_pending_deletions,
    read_custom_source_pending_deletions,
    read_custom_source_sync_entries,
    write_custom_source_sync_entries,
)


CLOUD_API_BASE_URL = "https://api.mistercompanion.org"
CLOUD_DASHBOARD_URL = f"{CLOUD_API_BASE_URL}/account/"

OFFICIAL_API_SECRET = ""

REQUEST_TIMEOUT = 15
CLIENT_TYPE = "desktop"


class CloudApiError(RuntimeError):
    def __init__(self, status_code: int, payload: Any = None, message: str | None = None):
        self.status_code = status_code
        self.payload = payload
        detail = message or _error_message(payload) or f"Cloud API request failed ({status_code})."
        super().__init__(detail)


def _error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        message = str(payload.get("message") or "").strip()
        if message:
            return message
        error = str(payload.get("error") or "").strip()
        if error:
            return error.replace("_", " ").strip().capitalize()
    return ""


def current_platform() -> tuple[str, str]:
    system = platform.system().strip().lower()
    if system == "darwin":
        system = "macos"

    machine = platform.machine().strip().lower()
    if machine in {"amd64", "x64", "x86_64"}:
        machine = "x64"
    elif machine in {"arm64", "aarch64"}:
        machine = "arm64"

    return system or "unknown", machine or "unknown"


def platform_display_name(platform_name: str, architecture: str) -> str:
    platform_labels = {
        "windows": "Windows",
        "linux": "Linux",
        "macos": "macOS",
    }
    arch_labels = {
        "x64": "x64",
        "x86_64": "x64",
        "arm64": "ARM64",
    }
    return f"MiSTer Companion {platform_labels.get(platform_name, platform_name.title())} {arch_labels.get(architecture, architecture)}".strip()


class CloudAccountClient:
    def __init__(self, config_data: dict):
        self.config_data = config_data

    @property
    def cloud_data(self) -> dict:
        data = self.config_data.get("cloud_account")
        if not isinstance(data, dict):
            data = {}
            self.config_data["cloud_account"] = data
        return data

    def has_session(self) -> bool:
        return bool(str(self.cloud_data.get("refresh_token") or "").strip())

    def linked_device(self) -> dict:
        device = self.cloud_data.get("device")
        return device if isinstance(device, dict) else {}

    def entitlement(self) -> dict:
        value = self.cloud_data.get("entitlement")
        return value if isinstance(value, dict) else {}

    def start_link(self, friendly_name: str) -> dict:
        system, architecture = current_platform()
        return self._request(
            "POST",
            "/devices/link/start",
            {
                "friendly_name": friendly_name.strip(),
                "client_type": CLIENT_TYPE,
                "platform": system,
                "architecture": architecture,
                "app_version": APP_VERSION,
            },
            authenticated=False,
        )

    def poll_link(self, pairing_id: str, device_secret: str) -> dict:
        result = self._request(
            "POST",
            "/devices/link/status",
            {
                "pairing_id": pairing_id,
                "device_secret": device_secret,
            },
            authenticated=False,
        )
        if result.get("status") == "linked" and isinstance(result.get("session"), dict):
            self.store_session(result["session"])
            if isinstance(result.get("device"), dict):
                self.cloud_data["device"] = result["device"]
        return result

    def connect(self) -> dict:
        result = self._authenticated_request("POST", "/device/connect", {})
        if isinstance(result.get("device"), dict):
            self.cloud_data["device"] = result["device"]
        if isinstance(result.get("entitlement"), dict):
            self.cloud_data["entitlement"] = result["entitlement"]
        self.cloud_data["last_connect_at"] = int(time.time())
        return result

    def sync_revisions(self) -> dict:
        return self._authenticated_request("POST", "/sync/revisions", {})

    def remote_sync_available(self, revision_payload: dict) -> bool:
        revisions = revision_payload.get("revisions") if isinstance(revision_payload, dict) else None
        if not isinstance(revisions, dict):
            return False

        profile_state = profile_sync_state(self.config_data)
        source_state = self.update_all_source_sync_state()
        theme_state = self.custom_theme_sync_state()
        local = {
            "profile": int(profile_state.get("last_revision") or 0),
            "update_all_source": int(source_state.get("last_revision") or 0),
            "custom_theme": int(theme_state.get("last_revision") or 0),
        }
        return any(
            int(revisions.get(category) or 0) > revision
            for category, revision in local.items()
        )

    def unlink(self) -> dict:
        result = self._authenticated_request("POST", "/device/unlink", {})
        self.clear_session()
        return result

    def connect_and_sync_profiles(self) -> dict:
        result = self.connect()

        # Patreon-exclusive themes are convenience content rather than sync data.
        # Install missing themes silently, but never make core cloud sync inactive
        # just because theme delivery is temporarily unavailable.
        try:
            result["patreon_themes"] = self.install_missing_patreon_themes()
        except Exception as exc:
            result["patreon_themes"] = {"status": "unavailable", "message": str(exc)}

        try:
            profile_sync = self.sync_profiles()
        except Exception:
            self.set_cloud_sync_status(False, "Profile sync failed. Companion Cloud will retry later.")
            raise

        result["profile_sync"] = profile_sync
        profile_status = str(profile_sync.get("status") or "").strip() if isinstance(profile_sync, dict) else ""
        if profile_status == "paused":
            self.set_cloud_sync_status(
                False,
                "Profile sync is paused after cloud-data deletion. Resume it from the Companion Cloud dashboard.",
            )
        elif profile_status == "resolution_required":
            self.set_cloud_sync_status(False, "Profile sync needs attention before it can continue.")

        try:
            update_all_source_sync = self.sync_update_all_custom_sources()
        except Exception:
            self.set_cloud_sync_status(False, "Update_All custom source sync failed. Companion Cloud will retry later.")
            raise

        result["update_all_source_sync"] = update_all_source_sync
        update_all_status = (
            str(update_all_source_sync.get("status") or "").strip()
            if isinstance(update_all_source_sync, dict)
            else ""
        )
        if update_all_status == "paused":
            self.set_cloud_sync_status(
                False,
                "Update_All custom source sync is paused after cloud-data deletion. Resume it from the Companion Cloud dashboard.",
            )
        elif update_all_status == "resolution_required":
            self.set_cloud_sync_status(False, "Update_All custom source sync needs attention before it can continue.")

        try:
            theme_sync = self.sync_custom_themes()
        except Exception:
            self.set_cloud_sync_status(False, "Custom theme sync failed. Companion Cloud will retry later.")
            raise
        result["custom_theme_sync"] = theme_sync
        theme_status = str(theme_sync.get("status") or "").strip() if isinstance(theme_sync, dict) else ""
        if theme_status == "paused":
            self.set_cloud_sync_status(
                False,
                "Custom theme sync is paused after cloud-data deletion. Resume it from the Companion Cloud dashboard.",
            )
        elif theme_status == "resolution_required":
            self.set_cloud_sync_status(False, "Custom theme sync needs attention before it can continue.")
        elif (
            profile_status not in {"paused", "resolution_required"}
            and update_all_status not in {"paused", "resolution_required"}
        ):
            self.set_cloud_sync_status(True)

        return result

    def install_missing_patreon_themes(self) -> dict:
        entitlement = self.entitlement()
        if not bool(entitlement.get("eligible")):
            return {"status": "not_eligible", "installed": 0}

        catalog = self._authenticated_request("POST", "/patreon-themes/catalog", {})
        entries = catalog.get("themes") if isinstance(catalog.get("themes"), list) else []
        local_ids = local_theme_ids()
        installed = 0
        skipped = 0

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            theme_id = normalize_theme_id(entry.get("id"))
            if not theme_id:
                continue
            if theme_id in local_ids:
                skipped += 1
                continue

            response = self._authenticated_request(
                "POST",
                "/patreon-themes/download",
                {"id": theme_id},
            )
            theme = response.get("theme") if isinstance(response.get("theme"), dict) else None
            if not isinstance(theme, dict):
                continue
            if install_patreon_theme(theme):
                installed += 1
                local_ids.add(theme_id)
            else:
                skipped += 1

        return {
            "status": "ok",
            "available": len(entries),
            "installed": installed,
            "already_present": skipped,
        }

    def update_all_source_sync_state(self) -> dict:
        cloud = self.config_data.setdefault("cloud_account", {})
        state = cloud.get("update_all_source_sync")
        if not isinstance(state, dict):
            state = {}
            cloud["update_all_source_sync"] = state
        state["last_revision"] = max(0, int(state.get("last_revision") or 0))
        known = state.get("known_item_ids")
        if not isinstance(known, list):
            state["known_item_ids"] = []
        if not isinstance(state.get("last_synced_items"), dict):
            state["last_synced_items"] = {}
        if not isinstance(state.get("pending_deletions"), list):
            state["pending_deletions"] = []
        return state

    def sync_update_all_custom_sources(self) -> dict:
        state = self.update_all_source_sync_state()
        entries = self._ensure_custom_source_sync_ids(read_custom_source_sync_entries())

        if int(state.get("last_revision") or 0) == 0:
            preview = self._authenticated_request(
                "POST",
                "/sync/update-all-sources",
                {"since_revision": 0, "sources": [], "deletions": []},
            )
            plan = self._prepare_initial_custom_source_sync(
                entries,
                preview.get("changes", []),
                int(preview.get("current_revision") or 0),
            )
            plan["mode"] = "initial"
            if plan.get("conflicts"):
                return {
                    "status": "resolution_required",
                    "conflicts": plan["conflicts"],
                    "initial_plan": plan,
                }
            self._apply_initial_custom_source_plan(plan, [])
        else:
            prepared = self._prepare_incremental_custom_source_sync(entries)
            if prepared is not None:
                return prepared

        return self._sync_update_all_custom_sources_normal()

    def resolve_initial_update_all_source_sync(self, plan: dict, resolutions: list[dict]) -> dict:
        if str(plan.get("mode") or "initial") == "incremental":
            self._apply_incremental_custom_source_plan(plan, resolutions)
        else:
            self._apply_initial_custom_source_plan(plan, resolutions)
        return self._sync_update_all_custom_sources_normal()

    def _prepare_incremental_custom_source_sync(self, entries: list) -> dict | None:
        state = self.update_all_source_sync_state()
        baseline = state.get("last_synced_items") if isinstance(state.get("last_synced_items"), dict) else {}
        if not baseline:
            return None

        preview = self._authenticated_request(
            "POST",
            "/sync/update-all-sources",
            {"since_revision": int(state.get("last_revision") or 0), "sources": [], "deletions": []},
        )
        changes = preview.get("changes") if isinstance(preview.get("changes"), list) else []
        local_by_id = {
            str(item.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower(): item
            for item in entries
            if str(item.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip()
        }
        conflicts = []
        consumed_local = set()
        consumed_cloud = set()

        # First detect concurrent edits of the same stable cloud item.
        for idx, change in enumerate(changes):
            if not isinstance(change, dict) or bool(change.get("deleted")):
                continue
            cloud = self._custom_source_from_change(change)
            if cloud is None:
                continue
            item_id = str(cloud.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower()
            local = local_by_id.get(item_id)
            previous = baseline.get(item_id) if isinstance(baseline.get(item_id), dict) else None
            if local is None or previous is None:
                continue
            local_changed = self._custom_source_compare_key(local) != self._custom_source_compare_key(previous)
            cloud_changed = self._custom_source_compare_key(cloud) != self._custom_source_compare_key(previous)
            if local_changed and cloud_changed and self._custom_source_compare_key(local) != self._custom_source_compare_key(cloud):
                conflicts.append({
                    "local": dict(local),
                    "cloud": dict(cloud),
                    "reason": "This custom source was changed locally and in the cloud since the last sync",
                })
                consumed_local.add(item_id)
                consumed_cloud.add(idx)

        # Also catch independently-created entries that collide on database ID.
        new_locals = [item for item in entries if str(item.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower() not in baseline]
        for idx, change in enumerate(changes):
            if idx in consumed_cloud or not isinstance(change, dict) or bool(change.get("deleted")):
                continue
            cloud = self._custom_source_from_change(change)
            if cloud is None:
                continue
            cloud_id = str(cloud.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower()
            if cloud_id in baseline:
                continue
            cloud_db = str(cloud.get("database_id") or "").strip().casefold()
            for local in new_locals:
                local_id = str(local.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower()
                if local_id in consumed_local or local_id == cloud_id:
                    continue
                if str(local.get("database_id") or "").strip().casefold() != cloud_db:
                    continue
                if self._custom_source_compare_key(local) == self._custom_source_compare_key(cloud):
                    local[CUSTOM_SOURCE_SYNC_ID_KEY] = cloud_id
                else:
                    conflicts.append({
                        "local": dict(local),
                        "cloud": dict(cloud),
                        "reason": "Same database ID, different custom source details",
                    })
                consumed_local.add(local_id)
                consumed_cloud.add(idx)
                break

        # Apply previewed cloud changes that are not part of an unresolved
        # conflict before uploading local state. This prevents an unchanged
        # stale local copy from being submitted against the newer cloud
        # revision and being treated by the backend as a concurrent edit.
        non_conflicting_changes = [
            change for idx, change in enumerate(changes)
            if idx not in consumed_cloud
            and isinstance(change, dict)
            and not bool(change.get("deleted"))
        ]

        if not conflicts:
            if non_conflicting_changes:
                entries = self._apply_custom_source_changes(entries, non_conflicting_changes)
            write_custom_source_sync_entries(entries)
            return None

        return {
            "status": "resolution_required",
            "conflicts": conflicts,
            "initial_plan": {
                "mode": "incremental",
                "conflicts": conflicts,
                "non_conflicting_changes": non_conflicting_changes,
            },
        }

    def _apply_incremental_custom_source_plan(self, plan: dict, resolutions: list[dict]):
        entries = self._ensure_custom_source_sync_ids(read_custom_source_sync_entries())
        by_id = {
            str(item.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower(): item
            for item in entries
        }
        resolution_by_local_id = {
            str(item.get("local_id") or "").strip().lower(): item
            for item in resolutions if isinstance(item, dict)
        }
        for conflict in plan.get("conflicts", []):
            local = conflict.get("local") if isinstance(conflict, dict) else None
            cloud = conflict.get("cloud") if isinstance(conflict, dict) else None
            if not isinstance(local, dict) or not isinstance(cloud, dict):
                continue
            local_id = str(local.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower()
            cloud_id = str(cloud.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower()
            current = by_id.get(local_id)
            resolution = resolution_by_local_id.get(local_id)
            if current is None or not resolution:
                raise RuntimeError("A custom source sync conflict was not resolved.")
            action = str(resolution.get("action") or "").strip().lower()
            if action == "keep_local":
                if local_id != cloud_id:
                    current[CUSTOM_SOURCE_SYNC_ID_KEY] = cloud_id
            elif action == "keep_cloud":
                index = entries.index(current)
                entries[index] = dict(cloud)
                by_id.pop(local_id, None)
                by_id[cloud_id] = entries[index]
            else:
                raise RuntimeError("Unknown custom source sync conflict resolution.")
        non_conflicting_changes = plan.get("non_conflicting_changes")
        if isinstance(non_conflicting_changes, list) and non_conflicting_changes:
            entries = self._apply_custom_source_changes(entries, non_conflicting_changes)
        write_custom_source_sync_entries(entries)
        save_config(self.config_data)

    def _sync_update_all_custom_sources_normal(self) -> dict:
        state = self.update_all_source_sync_state()
        entries = self._ensure_custom_source_sync_ids(read_custom_source_sync_entries())
        deletions = read_custom_source_pending_deletions()

        payload_sources = []
        for source in entries:
            item_id = str(source.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower()
            try:
                item_id = str(uuid.UUID(item_id))
            except Exception:
                continue
            payload_sources.append({
                "item_id": item_id,
                "content": self._custom_source_content(source),
            })

        result = self._authenticated_request(
            "POST",
            "/sync/update-all-sources",
            {
                "since_revision": int(state.get("last_revision") or 0),
                "sources": payload_sources,
                "deletions": deletions,
            },
        )

        aliases = result.get("aliases") if isinstance(result.get("aliases"), dict) else {}
        for source in entries:
            item_id = str(source.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower()
            replacement = str(aliases.get(item_id) or "").strip().lower()
            if replacement:
                source[CUSTOM_SOURCE_SYNC_ID_KEY] = replacement

        entries = self._apply_custom_source_changes(entries, result.get("changes", []))
        write_custom_source_sync_entries(entries)
        state["last_revision"] = max(0, int(result.get("current_revision") or state.get("last_revision") or 0))
        state["known_item_ids"] = sorted({
            str(item.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower()
            for item in entries
            if str(item.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip()
        })
        state["last_synced_items"] = {
            str(item.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower(): self._custom_source_content(item)
            for item in entries
            if str(item.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip()
        }
        clear_custom_source_pending_deletions()
        save_config(self.config_data)
        return result

    def queue_update_all_source_deletions(self, item_ids) -> None:
        from core.update_all_config import queue_custom_source_pending_deletions
        queue_custom_source_pending_deletions(item_ids)

    def _ensure_custom_source_sync_ids(self, entries: list) -> list:
        changed = False
        for source in entries:
            value = str(source.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower()
            try:
                valid = str(uuid.UUID(value)) == value and uuid.UUID(value).version == 4
            except Exception:
                valid = False
            if not valid:
                source[CUSTOM_SOURCE_SYNC_ID_KEY] = str(uuid.uuid4())
                changed = True
        if changed:
            write_custom_source_sync_entries(entries)
        return entries

    @staticmethod
    def _normalize_ini_block(value: object) -> str:
        text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.strip() for line in text.split("\n")]
        return "\n".join(line for line in lines if line).strip()

    @staticmethod
    def _custom_source_content(source: dict) -> dict:
        return {
            "display_name": str(source.get("display_name") or "").strip(),
            "database_id": str(source.get("database_id") or "").strip(),
            "db_url": str(source.get("db_url") or "").strip(),
            "ini_block": str(source.get("ini_block") or "").rstrip("\r\n"),
        }

    @classmethod
    def _custom_source_compare_key(cls, source: dict) -> tuple[str, str, str, str]:
        content = cls._custom_source_content(source)
        return (
            content["display_name"].casefold(),
            content["database_id"].casefold(),
            content["db_url"],
            cls._normalize_ini_block(content["ini_block"]),
        )

    def _custom_source_from_change(self, change: dict) -> dict | None:
        if not isinstance(change, dict) or bool(change.get("deleted")):
            return None
        content = change.get("content")
        item_id = str(change.get("item_id") or "").strip().lower()
        if not isinstance(content, dict) or not item_id:
            return None
        source = self._custom_source_content(content)
        source[CUSTOM_SOURCE_SYNC_ID_KEY] = item_id
        return source

    def _prepare_initial_custom_source_sync(self, local_entries: list, changes: list, current_revision: int) -> dict:
        cloud_entries = []
        deleted_ids = set()
        for change in changes if isinstance(changes, list) else []:
            if not isinstance(change, dict):
                continue
            item_id = str(change.get("item_id") or "").strip().lower()
            if bool(change.get("deleted")):
                if item_id:
                    deleted_ids.add(item_id)
                continue
            source = self._custom_source_from_change(change)
            if source is not None:
                cloud_entries.append(source)

        local_entries = [
            dict(item) for item in local_entries
            if str(item.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower() not in deleted_ids
        ]
        unmatched_cloud = set(range(len(cloud_entries)))
        conflicts = []

        # Exact matches are safe and never ask the user. They simply adopt the
        # existing cloud identity.
        for local in local_entries:
            exact_index = next((
                index for index in sorted(unmatched_cloud)
                if self._custom_source_compare_key(cloud_entries[index]) == self._custom_source_compare_key(local)
            ), None)
            if exact_index is not None:
                local[CUSTOM_SOURCE_SYNC_ID_KEY] = cloud_entries[exact_index][CUSTOM_SOURCE_SYNC_ID_KEY]
                unmatched_cloud.remove(exact_index)

        # Only unmatched entries with the same database ID are ambiguous.
        # Nothing is chosen automatically here.
        for local in local_entries:
            local_id = str(local.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower()
            local_db = str(local.get("database_id") or "").strip().casefold()
            if not local_db:
                continue
            cloud_index = next((
                index for index in sorted(unmatched_cloud)
                if str(cloud_entries[index].get("database_id") or "").strip().casefold() == local_db
            ), None)
            if cloud_index is None:
                continue
            cloud = cloud_entries[cloud_index]
            # If this became an exact match above, the cloud entry was already consumed.
            if self._custom_source_compare_key(local) == self._custom_source_compare_key(cloud):
                continue
            conflicts.append({
                "local": dict(local),
                "cloud": dict(cloud),
                "reason": "Same database ID, different custom source details",
            })
            unmatched_cloud.remove(cloud_index)

        return {
            "local_entries": local_entries,
            "cloud_only": [dict(cloud_entries[index]) for index in sorted(unmatched_cloud)],
            "conflicts": conflicts,
            "current_revision": max(0, int(current_revision or 0)),
        }

    def _apply_initial_custom_source_plan(self, plan: dict, resolutions: list[dict]):
        entries = [dict(item) for item in plan.get("local_entries", []) if isinstance(item, dict)]
        resolution_by_local_id = {
            str(item.get("local_id") or "").strip().lower(): item
            for item in resolutions if isinstance(item, dict)
        }

        for conflict in plan.get("conflicts", []):
            if not isinstance(conflict, dict):
                continue
            local = conflict.get("local") if isinstance(conflict.get("local"), dict) else {}
            cloud = conflict.get("cloud") if isinstance(conflict.get("cloud"), dict) else {}
            local_id = str(local.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower()
            cloud_id = str(cloud.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower()
            resolution = resolution_by_local_id.get(local_id)
            if not resolution:
                raise RuntimeError("A custom source sync conflict was not resolved.")

            index = next((
                i for i, item in enumerate(entries)
                if str(item.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower() == local_id
            ), None)
            if index is None:
                raise RuntimeError("The local custom source changed while resolving cloud sync.")

            action = str(resolution.get("action") or "").strip().lower()
            if action == "keep_local":
                entries[index][CUSTOM_SOURCE_SYNC_ID_KEY] = cloud_id
            elif action == "keep_cloud":
                entries[index] = dict(cloud)
            else:
                raise RuntimeError("Unknown custom source sync conflict resolution.")

        known_ids = {str(item.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower() for item in entries}
        for cloud in plan.get("cloud_only", []):
            if not isinstance(cloud, dict):
                continue
            cloud_id = str(cloud.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower()
            if cloud_id and cloud_id not in known_ids:
                entries.append(dict(cloud))
                known_ids.add(cloud_id)

        database_ids = [str(item.get("database_id") or "").strip().casefold() for item in entries]
        if len(database_ids) != len(set(database_ids)):
            raise RuntimeError("Custom source database IDs must be unique after resolving cloud sync conflicts.")

        write_custom_source_sync_entries(entries)
        state = self.update_all_source_sync_state()
        state["last_revision"] = max(0, int(plan.get("current_revision") or 0))
        state["known_item_ids"] = sorted({
            str(item.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower()
            for item in entries
            if str(item.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip()
        })
        save_config(self.config_data)

    def _apply_custom_source_changes(self, entries: list, changes: list) -> list:
        result = [dict(item) for item in entries]
        for change in changes if isinstance(changes, list) else []:
            if not isinstance(change, dict):
                continue
            item_id = str(change.get("item_id") or "").strip().lower()
            if not item_id:
                continue
            existing_index = next((
                index for index, item in enumerate(result)
                if str(item.get(CUSTOM_SOURCE_SYNC_ID_KEY) or "").strip().lower() == item_id
            ), None)

            if bool(change.get("deleted")):
                if existing_index is not None:
                    result.pop(existing_index)
                continue

            incoming = self._custom_source_from_change(change)
            if incoming is None:
                continue
            if existing_index is not None:
                result[existing_index] = incoming
                continue

            database_id = str(incoming.get("database_id") or "").strip().casefold()
            same_db_index = next((
                index for index, item in enumerate(result)
                if str(item.get("database_id") or "").strip().casefold() == database_id
            ), None)
            if same_db_index is not None:
                result[same_db_index] = incoming
            else:
                result.append(incoming)
        return result

    def custom_theme_sync_state(self) -> dict:
        cloud = self.config_data.setdefault("cloud_account", {})
        state = cloud.get("custom_theme_sync")
        if not isinstance(state, dict):
            state = {}
            cloud["custom_theme_sync"] = state
        state["last_revision"] = max(0, int(state.get("last_revision") or 0))
        if not isinstance(state.get("known_item_ids"), list):
            state["known_item_ids"] = []
        if not isinstance(state.get("last_synced_items"), dict):
            state["last_synced_items"] = {}
        if not isinstance(state.get("pending_deletions"), list):
            state["pending_deletions"] = []
        return state

    @staticmethod
    def _theme_sync_content(data: dict) -> dict:
        content = {
            "id": normalize_theme_id(data.get("id")),
            "name": str(data.get("name") or "").strip(),
            "author": str(data.get("author") or "Unknown").strip() or "Unknown",
            "background": str(data.get("background") or "").strip(),
            "surface": str(data.get("surface") or "").strip(),
            "accent": str(data.get("accent") or "").strip(),
            "text": str(data.get("text") or "").strip(),
            "category": "theme_creator",
            "companion": {
                "type": "custom_theme",
                "created_with": "theme_creator",
                "schema_version": 1,
            },
        }
        return content

    def sync_custom_themes(self) -> dict:
        state = self.custom_theme_sync_state()
        local = theme_creator_files()

        prepared = self._prepare_custom_theme_sync(local)
        if prepared is not None:
            return prepared

        return self._sync_custom_themes_normal()

    def _prepare_custom_theme_sync(self, local: list[tuple]) -> dict | None:
        state = self.custom_theme_sync_state()
        since_revision = int(state.get("last_revision") or 0)
        baseline = state.get("last_synced_items") if isinstance(state.get("last_synced_items"), dict) else {}

        preview = self._authenticated_request(
            "POST",
            "/sync/custom-themes",
            {"since_revision": since_revision, "themes": [], "deletions": []},
        )
        if str(preview.get("status") or "").strip() == "paused":
            return preview

        changes = preview.get("changes") if isinstance(preview.get("changes"), list) else []
        local_by_sync_id = {}
        local_by_theme_id = {}
        for path, data in local:
            item_id = ensure_theme_creator_sync_id(data)
            local_by_sync_id[item_id] = (path, data)
            theme_id = normalize_theme_id(data.get("id"))
            if theme_id:
                local_by_theme_id[theme_id] = (path, data)

        conflicts = []
        consumed_cloud = set()
        consumed_local = set()

        # Detect edits to the same stable theme identity. On an established sync,
        # use the last successful snapshot to distinguish a cloud-only update from
        # a true concurrent edit. During first reconciliation, differing content
        # for the same stable identity also requires an explicit choice.
        for idx, change in enumerate(changes):
            if not isinstance(change, dict) or bool(change.get("deleted")):
                continue
            item_id = str(change.get("item_id") or "").strip().lower()
            content = change.get("content")
            if not item_id or not isinstance(content, dict):
                continue
            current = local_by_sync_id.get(item_id)
            if current is None:
                continue
            _path, local_data = current
            local_content = self._theme_sync_content(local_data)
            cloud_content = self._theme_sync_content(content)
            previous = baseline.get(item_id) if isinstance(baseline.get(item_id), dict) else None

            if previous is not None:
                local_changed = local_content != self._theme_sync_content(previous)
                cloud_changed = cloud_content != self._theme_sync_content(previous)
                is_conflict = local_changed and cloud_changed and local_content != cloud_content
            else:
                is_conflict = local_content != cloud_content

            if is_conflict:
                conflicts.append({
                    "reason": "This theme was changed locally and in the cloud since the last sync"
                    if previous is not None else
                    "The local and cloud copies of this Theme Creator theme are different",
                    "local": dict(local_data),
                    "cloud": dict(content),
                    "local_id": item_id,
                    "cloud_id": item_id,
                })
                consumed_local.add(item_id)
                consumed_cloud.add(idx)

        # Also detect independently-created Theme Creator themes that claim the
        # same visible theme id. Exact copies are silently associated with the
        # cloud identity; genuinely different copies require resolution.
        for idx, change in enumerate(changes):
            if idx in consumed_cloud or not isinstance(change, dict) or bool(change.get("deleted")):
                continue
            cloud_id = str(change.get("item_id") or "").strip().lower()
            content = change.get("content")
            if not cloud_id or not isinstance(content, dict):
                continue
            cloud_theme_id = normalize_theme_id(content.get("id"))
            if not cloud_theme_id:
                continue
            current = local_by_theme_id.get(cloud_theme_id)
            if current is None:
                continue
            path, local_data = current
            local_id = str(local_data.get("companion", {}).get(THEME_SYNC_ID_KEY) or "").strip().lower()
            if not local_id or local_id == cloud_id or local_id in consumed_local:
                continue

            local_content = self._theme_sync_content(local_data)
            cloud_content = self._theme_sync_content(content)
            if local_content == cloud_content:
                local_data.setdefault("companion", {})[THEME_SYNC_ID_KEY] = cloud_id
                path.write_text(json.dumps(local_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            else:
                conflicts.append({
                    "reason": "Same Theme ID, different Theme Creator content",
                    "local": dict(local_data),
                    "cloud": dict(content),
                    "local_id": local_id,
                    "cloud_id": cloud_id,
                })
            consumed_local.add(local_id)
            consumed_cloud.add(idx)

        # Apply non-conflicting cloud updates before uploading local state. This
        # prevents an unchanged stale local copy from racing a newer cloud revision.
        non_conflicting_changes = [
            change for idx, change in enumerate(changes)
            if idx not in consumed_cloud
            and isinstance(change, dict)
            and not bool(change.get("deleted"))
        ]

        if not conflicts:
            if non_conflicting_changes:
                self._apply_custom_theme_changes(non_conflicting_changes)
            save_config(self.config_data)
            return None

        reserved_theme_ids = {
            normalize_theme_id(data.get("id"))
            for _path, data in theme_creator_files()
            if normalize_theme_id(data.get("id"))
            and str(data.get("companion", {}).get(THEME_SYNC_ID_KEY) or "").strip().lower() not in consumed_local
        }
        return {
            "status": "resolution_required",
            "category": "custom_theme",
            "conflicts": conflicts,
            "initial_plan": {
                "mode": "theme",
                "conflicts": conflicts,
                "non_conflicting_changes": non_conflicting_changes,
                "reserved_theme_ids": sorted(reserved_theme_ids),
            },
        }

    def resolve_custom_theme_sync(self, plan: dict, resolutions: list[dict]) -> dict:
        self._apply_custom_theme_conflict_plan(plan, resolutions)
        return self._sync_custom_themes_normal()

    def _apply_custom_theme_conflict_plan(self, plan: dict, resolutions: list[dict]):
        files = theme_creator_files()
        by_sync_id = {
            str(data.get("companion", {}).get(THEME_SYNC_ID_KEY) or "").strip().lower(): (path, data)
            for path, data in files
            if str(data.get("companion", {}).get(THEME_SYNC_ID_KEY) or "").strip()
        }
        resolution_by_local = {
            str(item.get("local_id") or "").strip().lower(): item
            for item in resolutions if isinstance(item, dict)
        }

        for conflict in plan.get("conflicts", []):
            if not isinstance(conflict, dict):
                continue
            local_id = str(conflict.get("local_id") or "").strip().lower()
            cloud_id = str(conflict.get("cloud_id") or "").strip().lower()
            cloud = conflict.get("cloud") if isinstance(conflict.get("cloud"), dict) else None
            current = by_sync_id.get(local_id)
            resolution = resolution_by_local.get(local_id)
            if current is None or cloud is None or not resolution:
                raise RuntimeError("A custom theme sync conflict was not resolved.")

            path, local_data = current
            action = str(resolution.get("action") or "").strip().lower()
            if action == "use_local":
                # The local copy becomes the canonical cloud item.
                if local_id != cloud_id:
                    local_data.setdefault("companion", {})[THEME_SYNC_ID_KEY] = cloud_id
                    path.write_text(json.dumps(local_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    by_sync_id.pop(local_id, None)
                    by_sync_id[cloud_id] = (path, local_data)
            elif action == "use_cloud":
                self._write_cloud_theme_over_local(path, local_data, cloud, cloud_id)
            elif action == "keep_both":
                local_name = str(resolution.get("local_name") or local_data.get("name") or "").strip()
                cloud_name = str(resolution.get("cloud_name") or cloud.get("name") or "").strip()
                local_theme_id = normalize_theme_id(local_name)
                cloud_theme_id = normalize_theme_id(cloud_name)
                if not local_theme_id or not cloud_theme_id or local_theme_id == cloud_theme_id:
                    raise RuntimeError("Themes kept separately must use different names.")

                # Keep the local copy as a new cloud item and keep the existing
                # cloud identity on the cloud copy.
                old_local_key = f"custom:{normalize_theme_id(local_data.get('id'))}"
                local_data = dict(local_data)
                local_data["name"] = local_name
                local_data["id"] = local_theme_id
                local_companion = dict(local_data.get("companion") or {})
                local_companion[THEME_SYNC_ID_KEY] = str(uuid.uuid4())
                local_data["companion"] = local_companion
                local_target = themes_dir(create=True) / f"{local_theme_id}.json"

                cloud_data = self._theme_sync_content(cloud)
                cloud_data["name"] = cloud_name
                cloud_data["id"] = cloud_theme_id
                cloud_companion = dict(cloud_data.get("companion") or {})
                cloud_companion[THEME_SYNC_ID_KEY] = cloud_id
                cloud_data["companion"] = cloud_companion
                cloud_target = themes_dir(create=True) / f"{cloud_theme_id}.json"

                if path.exists() and path.resolve() not in {local_target.resolve(), cloud_target.resolve()}:
                    path.unlink()
                local_target.write_text(json.dumps(local_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                cloud_target.write_text(json.dumps(cloud_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                if str(self.config_data.get("theme_mode") or "").strip().lower() == old_local_key:
                    self.config_data["theme_mode"] = f"custom:{local_theme_id}"
            else:
                raise RuntimeError("Unknown custom theme sync conflict resolution.")

        non_conflicting_changes = plan.get("non_conflicting_changes")
        if isinstance(non_conflicting_changes, list) and non_conflicting_changes:
            self._apply_custom_theme_changes(non_conflicting_changes)
        save_config(self.config_data)

    def _write_cloud_theme_over_local(self, old_path, old_data: dict, cloud: dict, cloud_id: str):
        old_key = f"custom:{normalize_theme_id(old_data.get('id'))}"
        data = self._theme_sync_content(cloud)
        companion = dict(data.get("companion") or {})
        companion[THEME_SYNC_ID_KEY] = cloud_id
        data["companion"] = companion
        theme_id = normalize_theme_id(data.get("id"))
        if not theme_id:
            raise RuntimeError("Cloud theme id is invalid.")
        target = themes_dir(create=True) / f"{theme_id}.json"
        if old_path.exists() and old_path.resolve() != target.resolve():
            old_path.unlink()
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if str(self.config_data.get("theme_mode") or "").strip().lower() == old_key:
            self.config_data["theme_mode"] = f"custom:{theme_id}"

    def queue_custom_theme_deletion(self, item_id: str) -> None:
        state = self.custom_theme_sync_state()
        pending = {
            str(value).strip().lower()
            for value in state.get("pending_deletions", [])
            if str(value).strip()
        }
        value = str(item_id or "").strip().lower()
        try:
            value = str(uuid.UUID(value))
        except Exception:
            return
        pending.add(value)
        state["pending_deletions"] = sorted(pending)
        save_config(self.config_data)

    def _sync_custom_themes_normal(self) -> dict:
        state = self.custom_theme_sync_state()
        local = theme_creator_files()
        current_ids = set()
        payload = []
        by_id = {}
        for path, data in local:
            item_id = ensure_theme_creator_sync_id(data)
            current_ids.add(item_id)
            by_id[item_id] = (path, data)
            payload.append({"item_id": item_id, "content": self._theme_sync_content(data)})

        deletions = sorted({
            str(value).strip().lower()
            for value in state.get("pending_deletions", [])
            if str(value).strip()
        })
        result = self._authenticated_request(
            "POST",
            "/sync/custom-themes",
            {
                "since_revision": int(state.get("last_revision") or 0),
                "themes": payload,
                "deletions": deletions,
            },
        )
        aliases = result.get("aliases") if isinstance(result.get("aliases"), dict) else {}
        for old_id, replacement in aliases.items():
            if old_id not in by_id:
                continue
            path, data = by_id[old_id]
            data.setdefault("companion", {})[THEME_SYNC_ID_KEY] = str(replacement).strip().lower()
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        self._apply_custom_theme_changes(result.get("changes", []))
        local_after = theme_creator_files()
        state["known_item_ids"] = sorted({
            str(data.get("companion", {}).get(THEME_SYNC_ID_KEY) or "").strip().lower()
            for _path, data in local_after
            if str(data.get("companion", {}).get(THEME_SYNC_ID_KEY) or "").strip()
        })
        state["last_synced_items"] = {
            str(data.get("companion", {}).get(THEME_SYNC_ID_KEY) or "").strip().lower(): self._theme_sync_content(data)
            for _path, data in local_after
            if str(data.get("companion", {}).get(THEME_SYNC_ID_KEY) or "").strip()
        }
        state["last_revision"] = max(0, int(result.get("current_revision") or state.get("last_revision") or 0))
        state["pending_deletions"] = []
        save_config(self.config_data)
        return result

    def _apply_custom_theme_changes(self, changes: list):
        existing = {}
        for path, data in theme_creator_files():
            item_id = str(data.get("companion", {}).get(THEME_SYNC_ID_KEY) or "").strip().lower()
            if item_id:
                existing[item_id] = (path, data)

        for change in changes if isinstance(changes, list) else []:
            if not isinstance(change, dict):
                continue
            item_id = str(change.get("item_id") or "").strip().lower()
            if not item_id:
                continue
            current = existing.get(item_id)
            if bool(change.get("deleted")):
                if current is not None:
                    path, data = current
                    deleted_key = f"custom:{normalize_theme_id(data.get('id'))}"
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                    if str(self.config_data.get("theme_mode") or "").strip().lower() == deleted_key:
                        self.config_data["theme_mode"] = "auto"
                continue

            content = change.get("content")
            if not isinstance(content, dict) or not is_theme_creator_theme_data(content):
                continue
            data = self._theme_sync_content(content)
            companion = dict(data.get("companion") or {})
            companion[THEME_SYNC_ID_KEY] = item_id
            data["companion"] = companion
            theme_id = normalize_theme_id(data.get("id"))
            if not theme_id:
                continue
            target = themes_dir(create=True) / f"{theme_id}.json"
            if current is not None:
                old_path, old_data = current
                old_key = f"custom:{normalize_theme_id(old_data.get('id'))}"
                if old_path.resolve() != target.resolve() and old_path.exists():
                    old_path.unlink()
                if str(self.config_data.get("theme_mode") or "").strip().lower() == old_key:
                    self.config_data["theme_mode"] = f"custom:{theme_id}"
            target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def sync_profiles(self) -> dict:
        if ensure_profile_sync_ids(self.config_data):
            save_config(self.config_data)

        state = profile_sync_state(self.config_data)
        if not isinstance(state.get("last_synced_items"), dict):
            state["last_synced_items"] = {}
        if int(state.get("last_revision") or 0) == 0:
            prepared = self._prepare_initial_profile_sync()
            if prepared is not None:
                return prepared
        else:
            prepared = self._prepare_incremental_profile_sync()
            if prepared is not None:
                return prepared

        return self._sync_profiles_normal()

    def _prepare_initial_profile_sync(self) -> dict | None:
        preview = self._authenticated_request(
            "POST",
            "/sync/profiles",
            {"since_revision": 0, "profiles": [], "deletions": []},
        )
        changes = preview.get("changes") if isinstance(preview.get("changes"), list) else []
        cloud_profiles = []
        for change in changes:
            if not isinstance(change, dict) or bool(change.get("deleted")):
                continue
            content = change.get("content")
            item_id = str(change.get("item_id") or "").strip().lower()
            if not item_id or not isinstance(content, dict):
                continue
            profile = self._device_from_content(content, item_id)
            if profile is not None:
                cloud_profiles.append(profile)

        if not cloud_profiles:
            return None

        devices = get_devices(self.config_data)
        unmatched_local = set(range(len(devices)))
        unmatched_cloud = set(range(len(cloud_profiles)))
        exact_matches = []

        for local_index, local in enumerate(devices):
            for cloud_index, cloud in enumerate(cloud_profiles):
                if cloud_index not in unmatched_cloud:
                    continue
                if self._profile_content(local) == self._profile_content(cloud):
                    exact_matches.append({
                        "local_id": str(local.get(PROFILE_SYNC_ID_KEY) or "").strip().lower(),
                        "cloud_id": str(cloud.get(PROFILE_SYNC_ID_KEY) or "").strip().lower(),
                    })
                    unmatched_local.discard(local_index)
                    unmatched_cloud.discard(cloud_index)
                    break

        candidates = []
        for local_index in unmatched_local:
            local = devices[local_index]
            for cloud_index in unmatched_cloud:
                cloud = cloud_profiles[cloud_index]
                same_target = self._profile_target(local) == self._profile_target(cloud)
                same_name = str(local.get("name") or "").strip().casefold() == str(cloud.get("name") or "").strip().casefold()
                if same_target and not same_name:
                    candidates.append((2, local_index, cloud_index, "Same connection, different profile names"))
                elif same_name and self._profile_content(local) != self._profile_content(cloud):
                    candidates.append((1, local_index, cloud_index, "Same profile name, different connection details"))

        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        conflicts = []
        used_local = set()
        used_cloud = set()
        for _score, local_index, cloud_index, reason in candidates:
            if local_index in used_local or cloud_index in used_cloud:
                continue
            used_local.add(local_index)
            used_cloud.add(cloud_index)
            unmatched_local.discard(local_index)
            unmatched_cloud.discard(cloud_index)
            conflicts.append({
                "reason": reason,
                "local": dict(devices[local_index]),
                "cloud": dict(cloud_profiles[cloud_index]),
            })

        reserved_names = []
        for index in sorted(unmatched_local):
            reserved_names.append(str(devices[index].get("name") or "").strip())
        for match in exact_matches:
            local_id = str(match.get("local_id") or "").strip().lower()
            local = next((
                device for device in devices
                if str(device.get(PROFILE_SYNC_ID_KEY) or "").strip().lower() == local_id
            ), None)
            if local is not None:
                reserved_names.append(str(local.get("name") or "").strip())
        for index in sorted(unmatched_cloud):
            reserved_names.append(str(cloud_profiles[index].get("name") or "").strip())

        plan = {
            "mode": "initial",
            "current_revision": max(0, int(preview.get("current_revision") or 0)),
            "exact_matches": exact_matches,
            "conflicts": conflicts,
            "cloud_only": [dict(cloud_profiles[index]) for index in sorted(unmatched_cloud)],
            "reserved_names": [name for name in reserved_names if name],
        }

        if conflicts:
            return {
                "status": "resolution_required",
                "category": "profile",
                "current_revision": plan["current_revision"],
                "conflicts": conflicts,
                "initial_plan": plan,
            }

        self._apply_initial_profile_plan(plan, [])
        return self._sync_profiles_normal()

    def resolve_initial_profile_sync(self, plan: dict, resolutions: list[dict]) -> dict:
        if str(plan.get("mode") or "initial") == "incremental":
            self._apply_incremental_profile_plan(plan, resolutions)
        else:
            self._apply_initial_profile_plan(plan, resolutions)
        return self._sync_profiles_normal()

    def _apply_initial_profile_plan(self, plan: dict, resolutions: list[dict]):
        devices = get_devices(self.config_data)

        for match in plan.get("exact_matches", []):
            local_id = str(match.get("local_id") or "").strip().lower()
            cloud_id = str(match.get("cloud_id") or "").strip().lower()
            for device in devices:
                if str(device.get(PROFILE_SYNC_ID_KEY) or "").strip().lower() == local_id:
                    device[PROFILE_SYNC_ID_KEY] = cloud_id
                    break

        resolution_by_local = {
            str(item.get("local_id") or "").strip().lower(): item
            for item in resolutions
            if isinstance(item, dict)
        }

        for conflict in plan.get("conflicts", []):
            local = conflict.get("local") if isinstance(conflict, dict) else None
            cloud = conflict.get("cloud") if isinstance(conflict, dict) else None
            if not isinstance(local, dict) or not isinstance(cloud, dict):
                continue
            local_id = str(local.get(PROFILE_SYNC_ID_KEY) or "").strip().lower()
            cloud_id = str(cloud.get(PROFILE_SYNC_ID_KEY) or "").strip().lower()
            resolution = resolution_by_local.get(local_id)
            if not resolution:
                raise RuntimeError("A profile sync conflict was not resolved.")

            action = str(resolution.get("action") or "").strip().lower()
            local_name = str(resolution.get("local_name") or local.get("name") or "").strip()
            cloud_name = str(resolution.get("cloud_name") or cloud.get("name") or "").strip()
            local_index = next((
                index for index, device in enumerate(devices)
                if str(device.get(PROFILE_SYNC_ID_KEY) or "").strip().lower() == local_id
            ), None)
            if local_index is None:
                continue

            current_local = devices[local_index]
            if action == "use_local":
                if local_name != str(current_local.get("name") or "").strip():
                    migrate_profile_identity(
                        current_local.get("name", ""), current_local.get("ip", ""),
                        local_name, current_local.get("ip", ""),
                    )
                    if self.config_data.get("last_connected") == current_local.get("name"):
                        self.config_data["last_connected"] = local_name
                    current_local["name"] = local_name
                current_local[PROFILE_SYNC_ID_KEY] = cloud_id

            elif action == "use_cloud":
                replacement = dict(cloud)
                replacement["name"] = cloud_name
                migrate_profile_identity(
                    current_local.get("name", ""), current_local.get("ip", ""),
                    replacement.get("name", ""), replacement.get("ip", ""),
                )
                if self.config_data.get("last_connected") == current_local.get("name"):
                    self.config_data["last_connected"] = replacement["name"]
                devices[local_index] = replacement

            elif action == "keep_both":
                if local_name != str(current_local.get("name") or "").strip():
                    migrate_profile_identity(
                        current_local.get("name", ""), current_local.get("ip", ""),
                        local_name, current_local.get("ip", ""),
                    )
                    if self.config_data.get("last_connected") == current_local.get("name"):
                        self.config_data["last_connected"] = local_name
                    current_local["name"] = local_name
                cloud_copy = dict(cloud)
                cloud_copy["name"] = cloud_name
                devices.append(cloud_copy)
            else:
                raise RuntimeError("Unknown profile sync conflict resolution.")

        known_ids = {str(device.get(PROFILE_SYNC_ID_KEY) or "").strip().lower() for device in devices}
        for cloud in plan.get("cloud_only", []):
            if not isinstance(cloud, dict):
                continue
            cloud_id = str(cloud.get(PROFILE_SYNC_ID_KEY) or "").strip().lower()
            if cloud_id and cloud_id not in known_ids:
                devices.append(dict(cloud))
                known_ids.add(cloud_id)

        names = [str(device.get("name") or "").strip().casefold() for device in devices]
        if len(names) != len(set(names)):
            raise RuntimeError("Profile names must be unique after resolving cloud sync conflicts.")

        self.config_data["devices"] = devices
        state = profile_sync_state(self.config_data)
        state["last_revision"] = max(0, int(plan.get("current_revision") or 0))
        save_config(self.config_data)

    def _prepare_incremental_profile_sync(self) -> dict | None:
        state = profile_sync_state(self.config_data)
        baseline = state.get("last_synced_items") if isinstance(state.get("last_synced_items"), dict) else {}
        if not baseline:
            return None

        preview = self._authenticated_request(
            "POST",
            "/sync/profiles",
            {"since_revision": int(state.get("last_revision") or 0), "profiles": [], "deletions": []},
        )
        changes = preview.get("changes") if isinstance(preview.get("changes"), list) else []
        devices = get_devices(self.config_data)
        local_by_id = {
            str(device.get(PROFILE_SYNC_ID_KEY) or "").strip().lower(): device
            for device in devices
            if str(device.get(PROFILE_SYNC_ID_KEY) or "").strip()
        }
        conflicts = []
        consumed_local = set()
        consumed_cloud = set()

        # Concurrent edits of the same stable profile identity.
        for idx, change in enumerate(changes):
            if not isinstance(change, dict) or bool(change.get("deleted")):
                continue
            item_id = str(change.get("item_id") or "").strip().lower()
            content = change.get("content")
            if not item_id or not isinstance(content, dict):
                continue
            cloud = self._device_from_content(content, item_id)
            local = local_by_id.get(item_id)
            previous_content = baseline.get(item_id) if isinstance(baseline.get(item_id), dict) else None
            previous = self._device_from_content(previous_content, item_id) if previous_content is not None else None
            if cloud is None or local is None or previous is None:
                continue
            local_changed = self._profile_content(local) != self._profile_content(previous)
            cloud_changed = self._profile_content(cloud) != self._profile_content(previous)
            if local_changed and cloud_changed and self._profile_content(local) != self._profile_content(cloud):
                conflicts.append({
                    "reason": "This profile was changed locally and in the cloud since the last sync",
                    "local": dict(local),
                    "cloud": dict(cloud),
                })
                consumed_local.add(item_id)
                consumed_cloud.add(idx)

        # Independently-created profiles can still collide after the first sync.
        new_locals = [
            device for device in devices
            if str(device.get(PROFILE_SYNC_ID_KEY) or "").strip().lower() not in baseline
        ]
        for idx, change in enumerate(changes):
            if idx in consumed_cloud or not isinstance(change, dict) or bool(change.get("deleted")):
                continue
            item_id = str(change.get("item_id") or "").strip().lower()
            content = change.get("content")
            if not item_id or item_id in baseline or not isinstance(content, dict):
                continue
            cloud = self._device_from_content(content, item_id)
            if cloud is None:
                continue
            for local in new_locals:
                local_id = str(local.get(PROFILE_SYNC_ID_KEY) or "").strip().lower()
                if local_id in consumed_local or local_id == item_id:
                    continue
                if self._profile_content(local) == self._profile_content(cloud):
                    local[PROFILE_SYNC_ID_KEY] = item_id
                    consumed_local.add(local_id)
                    consumed_cloud.add(idx)
                    break
                same_target = self._profile_target(local) == self._profile_target(cloud)
                same_name = str(local.get("name") or "").strip().casefold() == str(cloud.get("name") or "").strip().casefold()
                if same_target or same_name:
                    conflicts.append({
                        "reason": "Same connection, different profile names" if same_target else "Same profile name, different connection details",
                        "local": dict(local),
                        "cloud": dict(cloud),
                    })
                    consumed_local.add(local_id)
                    consumed_cloud.add(idx)
                    break

        # Apply previewed cloud changes that are not part of an unresolved
        # conflict before the normal upload pass. Otherwise an unchanged local
        # copy can be uploaded against a newer cloud revision and the backend
        # will correctly interpret that stale upload as a concurrent edit.
        non_conflicting_changes = [
            change for idx, change in enumerate(changes)
            if idx not in consumed_cloud
            and isinstance(change, dict)
            and not bool(change.get("deleted"))
        ]

        if not conflicts:
            if non_conflicting_changes:
                self._apply_profile_changes(non_conflicting_changes)
            save_config(self.config_data)
            return None

        conflict_local_ids = {
            str(item.get("local", {}).get(PROFILE_SYNC_ID_KEY) or "").strip().lower()
            for item in conflicts if isinstance(item, dict)
        }
        reserved_names = [
            str(device.get("name") or "").strip()
            for device in devices
            if str(device.get(PROFILE_SYNC_ID_KEY) or "").strip().lower() not in conflict_local_ids
            and str(device.get("name") or "").strip()
        ]
        return {
            "status": "resolution_required",
            "category": "profile",
            "conflicts": conflicts,
            "initial_plan": {
                "mode": "incremental",
                "conflicts": conflicts,
                "reserved_names": reserved_names,
                "non_conflicting_changes": non_conflicting_changes,
            },
        }

    def _apply_incremental_profile_plan(self, plan: dict, resolutions: list[dict]):
        devices = get_devices(self.config_data)
        resolution_by_local = {
            str(item.get("local_id") or "").strip().lower(): item
            for item in resolutions if isinstance(item, dict)
        }
        for conflict in plan.get("conflicts", []):
            local = conflict.get("local") if isinstance(conflict, dict) else None
            cloud = conflict.get("cloud") if isinstance(conflict, dict) else None
            if not isinstance(local, dict) or not isinstance(cloud, dict):
                continue
            local_id = str(local.get(PROFILE_SYNC_ID_KEY) or "").strip().lower()
            cloud_id = str(cloud.get(PROFILE_SYNC_ID_KEY) or "").strip().lower()
            resolution = resolution_by_local.get(local_id)
            if not resolution:
                raise RuntimeError("A profile sync conflict was not resolved.")
            local_index = next((
                index for index, device in enumerate(devices)
                if str(device.get(PROFILE_SYNC_ID_KEY) or "").strip().lower() == local_id
            ), None)
            if local_index is None:
                raise RuntimeError("The local profile changed while resolving cloud sync.")
            current_local = devices[local_index]
            action = str(resolution.get("action") or "").strip().lower()
            local_name = str(resolution.get("local_name") or current_local.get("name") or "").strip()
            cloud_name = str(resolution.get("cloud_name") or cloud.get("name") or "").strip()

            if action == "use_local":
                if local_name != str(current_local.get("name") or "").strip():
                    migrate_profile_identity(current_local.get("name", ""), current_local.get("ip", ""), local_name, current_local.get("ip", ""))
                    if self.config_data.get("last_connected") == current_local.get("name"):
                        self.config_data["last_connected"] = local_name
                    current_local["name"] = local_name
                current_local[PROFILE_SYNC_ID_KEY] = cloud_id
            elif action == "use_cloud":
                replacement = dict(cloud)
                replacement["name"] = cloud_name
                migrate_profile_identity(current_local.get("name", ""), current_local.get("ip", ""), replacement.get("name", ""), replacement.get("ip", ""))
                if self.config_data.get("last_connected") == current_local.get("name"):
                    self.config_data["last_connected"] = replacement["name"]
                devices[local_index] = replacement
            elif action == "keep_both":
                # The cloud copy keeps the existing shared identity. The local copy
                # becomes a new item so both can sync independently afterwards.
                if local_name != str(current_local.get("name") or "").strip():
                    migrate_profile_identity(current_local.get("name", ""), current_local.get("ip", ""), local_name, current_local.get("ip", ""))
                    if self.config_data.get("last_connected") == current_local.get("name"):
                        self.config_data["last_connected"] = local_name
                    current_local["name"] = local_name
                current_local[PROFILE_SYNC_ID_KEY] = str(uuid.uuid4())
                cloud_copy = dict(cloud)
                cloud_copy["name"] = cloud_name
                devices.append(cloud_copy)
            else:
                raise RuntimeError("Unknown profile sync conflict resolution.")

        names = [str(device.get("name") or "").strip().casefold() for device in devices]
        if len(names) != len(set(names)):
            raise RuntimeError("Profile names must be unique after resolving cloud sync conflicts.")
        self.config_data["devices"] = devices

        non_conflicting_changes = plan.get("non_conflicting_changes")
        if isinstance(non_conflicting_changes, list) and non_conflicting_changes:
            self._apply_profile_changes(non_conflicting_changes)
        save_config(self.config_data)

    def _sync_profiles_normal(self) -> dict:
        state = profile_sync_state(self.config_data)
        profiles = []
        for device in get_devices(self.config_data):
            item_id = str(device.get(PROFILE_SYNC_ID_KEY) or "").strip().lower()
            try:
                item_id = str(uuid.UUID(item_id))
            except Exception:
                continue
            profiles.append({
                "item_id": item_id,
                "content": {
                    "name": str(device.get("name") or "").strip(),
                    "ip": str(device.get("ip") or "").strip(),
                    "username": str(device.get("username") or "root").strip() or "root",
                    "password": str(device.get("password") if device.get("password") is not None else "1"),
                },
            })

        pending_deletions = [str(value).strip().lower() for value in state.get("pending_deletions", []) if str(value).strip()]
        result = self._authenticated_request(
            "POST",
            "/sync/profiles",
            {
                "since_revision": int(state.get("last_revision") or 0),
                "profiles": profiles,
                "deletions": pending_deletions,
            },
        )

        aliases = result.get("aliases") if isinstance(result.get("aliases"), dict) else {}
        conflicts = result.get("conflicts") if isinstance(result.get("conflicts"), dict) else {}
        for device in get_devices(self.config_data):
            item_id = str(device.get(PROFILE_SYNC_ID_KEY) or "").strip().lower()
            replacement = str(aliases.get(item_id) or conflicts.get(item_id) or "").strip().lower()
            if replacement:
                device[PROFILE_SYNC_ID_KEY] = replacement

        changes = result.get("changes") if isinstance(result.get("changes"), list) else []
        self._apply_profile_changes(changes)
        state["pending_deletions"] = []
        state["last_revision"] = max(0, int(result.get("current_revision") or state.get("last_revision") or 0))
        state["last_synced_items"] = {
            str(device.get(PROFILE_SYNC_ID_KEY) or "").strip().lower(): {
                "name": str(device.get("name") or "").strip(),
                "ip": str(device.get("ip") or "").strip(),
                "username": str(device.get("username") or "root").strip() or "root",
                "password": str(device.get("password") if device.get("password") is not None else "1"),
            }
            for device in get_devices(self.config_data)
            if str(device.get(PROFILE_SYNC_ID_KEY) or "").strip()
        }
        save_config(self.config_data)
        return result

    def _apply_profile_changes(self, changes: list):
        devices = get_devices(self.config_data)

        for change in changes:
            if not isinstance(change, dict):
                continue
            item_id = str(change.get("item_id") or "").strip().lower()
            if not item_id:
                continue

            existing_index = next((
                index for index, device in enumerate(devices)
                if str(device.get(PROFILE_SYNC_ID_KEY) or "").strip().lower() == item_id
            ), None)

            if bool(change.get("deleted")):
                if existing_index is not None:
                    deleted = devices[existing_index]
                    remove_profile_identity(deleted.get("name", ""), deleted.get("ip", ""))
                    deleted_name = str(deleted.get("name") or "")
                    del devices[existing_index]
                    if self.config_data.get("last_connected") == deleted_name:
                        self.config_data["last_connected"] = None
                continue

            content = change.get("content")
            if not isinstance(content, dict):
                continue

            synced_device = self._device_from_content(content, item_id)
            if synced_device is None:
                continue

            if existing_index is not None:
                old_device = devices[existing_index]
                old_name = str(old_device.get("name") or "")
                migrate_profile_identity(
                    old_name, old_device.get("ip", ""),
                    synced_device.get("name", ""), synced_device.get("ip", ""),
                )
                devices[existing_index] = synced_device
                if self.config_data.get("last_connected") == old_name:
                    self.config_data["last_connected"] = synced_device["name"]
                continue

            duplicate_index = next((
                index for index, device in enumerate(devices)
                if self._profile_content(device) == self._profile_content(synced_device)
            ), None)
            if duplicate_index is not None:
                devices[duplicate_index][PROFILE_SYNC_ID_KEY] = item_id
                continue

            devices.append(synced_device)

        self.config_data["devices"] = devices

    @staticmethod
    def _device_from_content(content: dict, item_id: str) -> dict | None:
        device = {
            "name": str(content.get("name") or "").strip(),
            "ip": str(content.get("ip") or "").strip(),
            "username": str(content.get("username") or "root").strip() or "root",
            "password": str(content.get("password") if content.get("password") is not None else "1"),
            PROFILE_SYNC_ID_KEY: item_id,
        }
        if not device["name"] or not device["ip"]:
            return None
        return device

    @staticmethod
    def _profile_target(device: dict) -> tuple[str, str, str]:
        return (
            str(device.get("ip") or "").strip().casefold(),
            str(device.get("username") or "root").strip().casefold() or "root",
            str(device.get("password") if device.get("password") is not None else "1").strip(),
        )

    @staticmethod
    def _profile_content(device: dict) -> tuple[str, str, str, str]:
        return (
            str(device.get("name") or "").strip().casefold(),
            str(device.get("ip") or "").strip().casefold(),
            str(device.get("username") or "root").strip().casefold() or "root",
            str(device.get("password") if device.get("password") is not None else "1").strip(),
        )

    def cloud_sync_status(self) -> tuple[bool, str]:
        if not (self.has_session() and self.linked_device()):
            return False, ""
        active = bool(self.cloud_data.get("sync_active", True))
        return active, str(self.cloud_data.get("sync_inactive_reason") or "").strip()

    def set_cloud_sync_status(self, active: bool, reason: str = ""):
        self.cloud_data["sync_active"] = bool(active)
        if active:
            self.cloud_data.pop("sync_inactive_reason", None)
        else:
            self.cloud_data["sync_inactive_reason"] = str(reason or "Cloud sync is currently unavailable.").strip()

    def store_session(self, session: dict):
        for key in (
            "access_token",
            "refresh_token",
            "access_token_expires_at",
            "refresh_token_expires_at",
        ):
            if key in session:
                self.cloud_data[key] = session[key]

    def clear_session(self):
        for key in (
            "access_token",
            "refresh_token",
            "access_token_expires_at",
            "refresh_token_expires_at",
            "device",
            "entitlement",
            "last_connect_at",
        ):
            self.cloud_data.pop(key, None)

    def _authenticated_request(self, method: str, path: str, payload: dict) -> dict:
        token = str(self.cloud_data.get("access_token") or "").strip()
        if token:
            try:
                return self._request(method, path, payload, access_token=token)
            except CloudApiError as exc:
                if exc.status_code != 401:
                    raise

        self._refresh_session()
        token = str(self.cloud_data.get("access_token") or "").strip()
        if not token:
            raise CloudApiError(401, {"error": "session_expired"}, "This device needs to be linked again.")
        return self._request(method, path, payload, access_token=token)

    def _refresh_session(self):
        refresh_token = str(self.cloud_data.get("refresh_token") or "").strip()
        if not refresh_token:
            raise CloudApiError(401, {"error": "missing_refresh_token"}, "This device needs to be linked again.")

        try:
            result = self._request(
                "POST",
                "/auth/refresh",
                {"refresh_token": refresh_token},
                authenticated=False,
            )
        except CloudApiError as exc:
            if exc.status_code == 401:
                self.clear_session()
            raise

        session = result.get("session") if isinstance(result, dict) else None
        if not isinstance(session, dict):
            raise CloudApiError(500, result, "The server did not return a refreshed session.")
        self.store_session(session)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        authenticated: bool = True,
        access_token: str | None = None,
    ) -> dict:
        method = method.upper()
        body = b""
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

        headers = {
            "Accept": "application/json",
            "User-Agent": f"MiSTer-Companion/{APP_VERSION}",
            "X-MC-Client-Type": CLIENT_TYPE,
            "X-MC-App-Version": APP_VERSION,
        }
        if body:
            headers["Content-Type"] = "application/json"

        headers.update(self._official_client_headers(method, path, body))

        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        elif authenticated:
            stored = str(self.cloud_data.get("access_token") or "").strip()
            if stored:
                headers["Authorization"] = f"Bearer {stored}"

        response = requests.request(
            method,
            f"{CLOUD_API_BASE_URL}{path}",
            data=body if body else None,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

        try:
            data = response.json()
        except ValueError:
            data = {"message": response.text.strip()} if response.text.strip() else {}

        if response.status_code < 200 or response.status_code >= 300:
            raise CloudApiError(response.status_code, data)

        if not isinstance(data, dict):
            raise CloudApiError(response.status_code, data, "The cloud API returned an invalid response.")
        return data

    def _official_client_headers(self, method: str, path: str, body: bytes) -> dict:
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        body_hash = hashlib.sha256(body).hexdigest()
        canonical = "\n".join([
            timestamp,
            nonce,
            method.upper(),
            urlparse(path).path,
            CLIENT_TYPE,
            APP_VERSION,
            body_hash,
        ])

        secret = OFFICIAL_API_SECRET.encode("utf-8")
        signature = hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        return {
            "X-MC-Signature-Version": "1",
            "X-MC-Timestamp": timestamp,
            "X-MC-Nonce": nonce,
            "X-MC-Signature": signature,
        }

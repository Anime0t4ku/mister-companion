from pathlib import Path
import uuid

from core.app_paths import generated_path
from core.config import save_config


PROFILE_SYNC_ID_KEY = "_cloud_id"


def _new_profile_sync_id():
    return str(uuid.uuid4())


def ensure_profile_sync_ids(config_data):
    changed = False
    for device in get_devices(config_data):
        value = str(device.get(PROFILE_SYNC_ID_KEY) or "").strip().lower()
        try:
            valid = str(uuid.UUID(value)) == value and uuid.UUID(value).version == 4
        except Exception:
            valid = False
        if not valid:
            device[PROFILE_SYNC_ID_KEY] = _new_profile_sync_id()
            changed = True
    if changed:
        config_data["devices"] = get_devices(config_data)
    return changed


def profile_sync_state(config_data):
    cloud = config_data.setdefault("cloud_account", {})
    state = cloud.get("profile_sync")
    if not isinstance(state, dict):
        state = {}
        cloud["profile_sync"] = state
    pending = state.get("pending_deletions")
    if not isinstance(pending, list):
        state["pending_deletions"] = []
    state["last_revision"] = max(0, int(state.get("last_revision") or 0))
    return state


def queue_profile_deletion(config_data, item_id):
    item_id = str(item_id or "").strip().lower()
    if not item_id:
        return
    state = profile_sync_state(config_data)
    pending = state["pending_deletions"]
    if item_id not in pending:
        pending.append(item_id)


def get_profile_sync_roots():
    roots = [str(generated_path("MiSTerSettings"))]

    save_root = generated_path("SaveManager")
    roots.append(str(save_root / "backups"))
    roots.append(str(save_root / "sync"))

    return roots


def get_devices(config_data):
    return config_data.get("devices", [])


def get_device_by_index(config_data, index):
    devices = get_devices(config_data)

    if index < 0 or index >= len(devices):
        return None

    return devices[index]


def get_device_by_name(config_data, name):
    if not name:
        return None

    for device in get_devices(config_data):
        if device.get("name") == name:
            return device

    return None


def add_device(config_data, device):
    devices = get_devices(config_data)

    for existing_device in devices:
        if existing_device.get("name", "").lower() == device["name"].lower():
            return False, "Device name already exists."

    device.setdefault(PROFILE_SYNC_ID_KEY, _new_profile_sync_id())
    devices.append(device)
    config_data["devices"] = devices
    config_data["last_connected"] = device["name"]
    save_config(config_data)

    return True, device


def update_device(config_data, index, updated_device):
    devices = get_devices(config_data)

    if index < 0 or index >= len(devices):
        return False, "Select a device first.", None

    old_device = devices[index]
    old_name = old_device.get("name", "")
    old_ip = old_device.get("ip", "")
    old_sync_id = str(old_device.get(PROFILE_SYNC_ID_KEY) or "").strip()
    if old_sync_id:
        updated_device[PROFILE_SYNC_ID_KEY] = old_sync_id
    else:
        updated_device[PROFILE_SYNC_ID_KEY] = _new_profile_sync_id()

    for i, existing_device in enumerate(devices):
        if i != index and existing_device.get("name", "").lower() == updated_device["name"].lower():
            return False, "Device name already exists.", None

    devices[index] = updated_device
    config_data["devices"] = devices

    if config_data.get("last_connected") == old_name:
        config_data["last_connected"] = updated_device["name"]

    save_config(config_data)

    return True, {
        "old_name": old_name,
        "old_ip": old_ip,
        "updated_device": updated_device,
    }, None


def delete_device(config_data, index):
    devices = get_devices(config_data)

    if index < 0 or index >= len(devices):
        return False, "Select a device first.", None

    device_to_delete = devices[index]
    device_name = device_to_delete.get("name", "")
    device_ip = device_to_delete.get("ip", "")
    queue_profile_deletion(config_data, device_to_delete.get(PROFILE_SYNC_ID_KEY))

    del devices[index]

    config_data["devices"] = devices

    if config_data.get("last_connected") == device_name:
        config_data["last_connected"] = None

    save_config(config_data)

    return True, {
        "device_name": device_name,
        "device_ip": device_ip,
    }, None
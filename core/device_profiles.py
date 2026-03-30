from pathlib import Path

from core.config import save_config


def get_profile_sync_roots():
    roots = ["MiSTerSettings"]

    save_root = Path("SaveManager")
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

    del devices[index]

    config_data["devices"] = devices

    if config_data.get("last_connected") == device_name:
        config_data["last_connected"] = None

    save_config(config_data)

    return True, {
        "device_name": device_name,
        "device_ip": device_ip,
    }, None
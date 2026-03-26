import json
from pathlib import Path

CONFIG_PATH = Path("config.json")


def load_config():
    if not CONFIG_PATH.exists():
        return {"devices": [], "last_connected": None}

    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {"devices": [], "last_connected": None}


def save_config(data):
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=4)
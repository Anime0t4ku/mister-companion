"""Opt-in network check against the public release, using only a temporary card.

Run: python tests/verify_misterzine_downloader.py
"""

import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mister-companion"))
from core import extras_misterzine as mz


def main():
    console = sys.stdout
    with urllib.request.urlopen(mz.DB_URL, timeout=60) as response:
        with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
            database = json.loads(archive.read("misterzine.json"))
    with tempfile.TemporaryDirectory(prefix="companion-misterzine-") as directory:
        card = Path(directory)
        (card / "downloader.ini").write_text("[MiSTer]\nfilter = arcade\n", encoding="utf-8")
        (card / "downloader_misterzine.ini").write_text(f"[misterzine]\ndb_url = {mz.DB_URL}\nfilter =\n", encoding="utf-8")
        logs = []
        def log(message):
            logs.append(message)
            print(message, end="", flush=True, file=console)
        mz.install_or_update_misterzine_local(card, log)
        for relative, metadata in database["files"].items():
            data = (card / relative).read_bytes()
            assert len(data) == metadata["size"], relative
            assert hashlib.md5(data).hexdigest() == metadata["hash"], relative
        status = mz.get_misterzine_status_local(card, check_latest=True)
        assert status["installed"] and not status["update_available"], status
        assert "update check failed" not in status["status_text"], status
        assert "MisterZine-Setup" in status["status_text"], status
        saved = card / "misterzine/favorites.json"
        saved.write_text('{"test":"preserve"}', encoding="utf-8")
        (card / "linux").mkdir(exist_ok=True)
        startup = card / "linux/user-startup.sh"
        other_hook = b"#!/bin/sh\nother-service &\n"
        startup.write_bytes(other_hook + b"# misterzine\n" + mz.STARTUP_LINE.encode() + b"\n")
        (card / "MisterZine.mgl").write_text("fixture", encoding="utf-8")
        mz.install_or_update_misterzine_local(card, log)
        assert saved.read_text() == '{"test":"preserve"}'
        mz.uninstall_misterzine_local(card, log)
        assert not (card / "misterzine/misterzine").exists()
        assert not (card / "MisterZine.mgl").exists()
        assert startup.read_bytes() == other_hook
        assert saved.read_text() == '{"test":"preserve"}'
        assert not mz.downloader.database_registered_local(card, mz.DB_ID)
        mz.install_or_update_misterzine_local(card, log)
        assert (card / "misterzine/misterzine").exists()
        assert saved.read_text() == '{"test":"preserve"}'
        assert (card / "downloader.ini").read_text().count("[misterzine]") == 1
        print(f"PASS: {len(database['files'])} public file hashes; install, update, removal, and same-version reinstall")


if __name__ == "__main__":
    main()

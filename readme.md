# MiSTer Companion

MiSTer Companion is a lightweight Windows GUI utility for managing and maintaining your MiSTer FPGA system over SSH.

It provides a simple interface for common maintenance tasks without needing to use a terminal.

Supports:

- Device management (save multiple MiSTer systems)
- Storage usage monitoring
- update_all installation and execution
- SMB enable / disable
- Open MiSTer share in Windows Explorer
- Remote reboot

Clean, safe, and easy MiSTer management from Windows.

![Screenshot](assets/screenshot.png)

---

## Requirements

Before using MiSTer Companion, make sure:

- Your MiSTer SD card is flashed with **MiSTerFusion**
- You used **Rufus** (or similar) to flash the image
- Your MiSTer is connected to your local network
- Your MiSTer has an active internet connection

Default credentials are `root / 1` (unless changed)

MiSTerFusion download:  
https://github.com/MiSTer-devel/mr-fusion/releases

Rufus download:  
https://rufus.ie/

---

## Download (Windows)

Download the latest automatic build:

| Platform | Status | Download |
|----------|--------|----------|
| Windows | ![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg) | [Download Pre-release](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Windows-x86_64.zip) |

---

## Python Requirements (Running From Source)

If running the script directly:

- Python 3.10+
- Tkinter (usually included)
- paramiko
- requests

Install dependencies:

    pip install paramiko requests

Run with:

    python mister-companion.py

---

## License

This project is licensed under the **GNU General Public License v2.0 (GPL-2.0)**.

See the `LICENSE` file for full details.

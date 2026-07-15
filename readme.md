# MiSTer Companion

MiSTer Companion is a cross-platform GUI utility for managing and maintaining your MiSTer FPGA system over SSH or directly from a selected SD card using Offline Mode.

It provides a simple interface for common maintenance tasks without needing to use a terminal.

---

![Screenshot](assets/screenshot.png)

---

## Features

For a complete overview of MiSTer Companion Desktop features, supported platforms, downloads, updates, and support options, visit the official website:

**[mistercompanion.org](https://mistercompanion.org)**

---

### Pre-Releases

| Name | Platform | Status | File |
|------|----------|--------|------|
| MiSTer Companion | Windows x86-64 | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Windows-x86_64.zip) |
| MiSTer Companion | Windows ARM64 | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Windows-ARM64.zip) |
| MiSTer Companion | Linux x86-64 | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Linux-x86_64.tar.gz) |
| MiSTer Companion | Linux ARM64 | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Linux-ARM64.tar.gz) |
| MiSTer Companion | macOS Apple Silicon | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-macOS-Apple-Silicon.dmg) |
| MiSTer Companion | macOS Intel | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-macOS-Intel.dmg) |

---

## Linux Notes

After extracting, make the application executable:

    chmod +x MiSTer-Companion

---

## macOS Notes

MiSTer Companion for macOS is signed with an Apple Developer ID certificate and notarized by Apple.

---

## Running From Source

Requirements:

- Python 3.10+
- PyQt6
- paramiko
- requests
- websocket-client
- psutil

Install:

    pip install -r requirements.txt

Run:

    python main.py

---

## License

This project is licensed under the GNU General Public License v2.0 (GPL-2.0).

See the LICENSE file for full details.
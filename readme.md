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
| MiSTer Companion | Linux x86-64 (AppImage) | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Linux-x86_64.AppImage) |
| MiSTer Companion | Linux ARM64 (AppImage) | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Linux-ARM64.AppImage) |
| MiSTer Companion | Linux x86-64 (tar.gz) | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Linux-x86_64.tar.gz) |
| MiSTer Companion | Linux ARM64 (tar.gz) | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Linux-ARM64.tar.gz) |
| MiSTer Companion | macOS Apple Silicon | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-macOS-Apple-Silicon.dmg) |
| MiSTer Companion | macOS Intel | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-macOS-Intel.dmg) |

---

## Linux Notes

Two Linux builds are published. The AppImage is a single file that needs no
extraction and carries a desktop entry. The tar.gz is the portable build, and
is the one MC-Updater can update in place.

To run the AppImage:

    chmod +x MiSTer-Companion-Linux-x86_64.AppImage
    ./MiSTer-Companion-Linux-x86_64.AppImage

Settings, saves and downloaded tools are kept in
`~/.local/share/MiSTer Companion`, or in `$XDG_DATA_HOME` if you set it.

To keep everything on a USB stick instead, create a directory named after the
AppImage with a `.home` suffix next to it. The AppImage runtime then uses it as
your home directory and all data stays inside:

    mkdir MiSTer-Companion-Linux-x86_64.AppImage.home

That redirects the whole home directory, not just this app's data, so SSH keys
in `~/.ssh` are no longer found. If you connect with a key instead of a
password, copy your `.ssh` directory into the `.home` directory as well.

Moving from the tar.gz build? Run this once, from the folder you extracted it
into:

    DEST="${XDG_DATA_HOME:-$HOME/.local/share}/MiSTer Companion"
    mkdir -p "$DEST"
    for item in config.json zaparoo_pairing.json update_all_extra_sources.json \
                SaveManager MiSTerSettings themes tools; do
        [ -e "$item" ] && cp -r "$item" "$DEST"/
    done

MC-Updater does not manage AppImage builds. Download a new AppImage to update.

For the tar.gz build, make the application executable after extracting:

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
- pyserial
- Pillow
- certifi
- cryptography


Install:

    pip install -r requirements.txt

Run:

    python main.py

---

## License

This project is licensed under the GNU General Public License v2.0 (GPL-2.0).

See the LICENSE file for full details.
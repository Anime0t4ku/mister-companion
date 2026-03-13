# MiSTer Companion

MiSTer Companion is a lightweight cross-platform GUI utility for managing and maintaining your MiSTer FPGA system over SSH.

It provides a simple interface for common maintenance tasks without needing to use a terminal.

Supports:

- Device management (save multiple MiSTer systems)
- Storage usage monitoring (SD and USB)
- update_all installation and execution
- Zaparoo installation and setup
- ZapScripts launcher via Zaparoo Core API
- SD migration tool (migrate_sd) installer
- cifs_mount installer and config
- SMB enable / disable
- Open MiSTer share directly in the system file manager
- Remote reboot
- SSH console output for script execution
- Save Manager to backup and sync saves between multiple MiSTer devices

Clean, safe, and easy MiSTer management from Windows and Linux.

![Screenshot](assets/screenshot.png)

---

## Features

MiSTer Companion uses a **tabbed interface** to organize functionality.

### Connection
- Connect to your MiSTer over SSH
- Save and manage multiple devices
- Automatic reconnect after reboot

### Device
- View **SD card storage usage**
- Detect **USB storage usage**
- Enable or disable **SMB file sharing**
- Open the MiSTer network share directly in the system file manager
- Reboot MiSTer remotely

### MiSTerSettings
- Easy Mode for simplified configuration of common MiSTer.ini settings
- Advanced Mode editor for the [MiSTer] section of MiSTer.ini
- Switch between Easy Mode and Advanced Mode
- Automatic backups before applying configuration changes
- Restore MiSTer.ini from backups or defaults
- Configure HDMI Mode (HD Output or Direct Video)
- Select HDMI video resolution
- Configure HDMI Sync Mode (vsync_adjust)
- Enable or disable HDMI Audio (DVI mode)
- Enable or disable HDR output
- Enable or disable HDMI Limited Range
- Configure analogue video output (RGB, Component, S-Video, VGA)
- Automatically disable unsupported settings when Direct Video is selected

### Scripts
- Install and run **update_all**
- Install **Zaparoo**
- Install **migrate_sd** (SD card migration utility)
- Install **cifs_mount / cifs_umount** (add network location to MiSTer)
- View **live SSH output** when running scripts

### ZapScripts
- Run **update_all** via the Zaparoo Core API
- Run **migrate_sd** via the Zaparoo Core API
- Open **Bluetooth menu**
- Open **MiSTer OSD menu**
- Cycle **wallpaper**
- Return to **MiSTer home**

### SaveManager
- Create **timestamped backups** of MiSTer saves
- Optional **savestate backups**
- **Automatic backup retention** per device
- Restore backups to any connected MiSTer
- **Sync saves between multiple MiSTer systems**
- Local **Sync Folder** used to merge the newest save files
- Safety backup option before restore or sync
- Built-in **status log** for operations

---

## Requirements

Before using MiSTer Companion, make sure:

- Your MiSTer SD card is flashed with **MiSTerFusion**
- You used **Rufus**, **balenaEtcher**, or a similar flashing tool
- Your MiSTer is connected to your local network
- Your MiSTer has an active internet connection

Default credentials are:

    root / 1

(unless you changed them)

MiSTerFusion download:  
https://github.com/MiSTer-devel/mr-fusion/releases

Rufus download:  
https://rufus.ie/

balenaEtcher download:  
https://etcher.balena.io/

---

## Download

Pre-built binaries are generated automatically via GitHub Actions.

| Platform | Status | Download |
|----------|--------|----------|
| Windows | ![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg) | [Download Windows Build](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Windows-x86_64.zip) |
| Linux | ![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg) | [Download Linux Build](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Linux-x86_64.zip) |

---

## Linux Notes

Opening the MiSTer network share requires **GVFS SMB support**.

Most desktop distributions already include this, but if needed install:

Ubuntu / Debian / Linux Mint

    sudo apt install gvfs-backends

Fedora

    sudo dnf install gvfs-smb

Arch Linux

    sudo pacman -S gvfs gvfs-smb

---

## Python Requirements (Running From Source)

If running the script directly:

- Python 3.10+
- Tkinter (usually included)
- paramiko
- requests
- websocket-client

Install dependencies:

    pip install paramiko requests websocket-client

Run with:

    python mister-companion.py

---

## License

This project is licensed under the **GNU General Public License v2.0 (GPL-2.0)**.

See the `LICENSE` file for full details.

# MiSTer Companion

MiSTer Companion is a cross-platform GUI utility for managing and maintaining your MiSTer FPGA system over SSH.

It provides a simple interface for common maintenance tasks without needing to use a terminal.

---

![Screenshot](assets/screenshot.png)

---

## Features

MiSTer Companion uses a tabbed interface to organize functionality.

### Flash SD
- Download the latest Mr. Fusion release directly from within the app
- Download the latest SuperStationONE SD Installer release directly from within the app
- Detect removable drives (Windows and Linux)
- Flash SD cards without requiring external tools
- Simplifies initial MiSTer setup

### Connection
- Connect to your MiSTer over SSH
- Save and manage multiple devices
- Scan for MiSTer devices on your local network
- Automatic reconnect after reboot

### Device
- View SD card storage usage
- Detect USB storage usage
- Enable or disable SMB file sharing
- Open the MiSTer network share directly in the system file manager
- Reboot MiSTer remotely

### MiSTer Settings
- Easy Mode for simplified configuration of common MiSTer.ini settings
- Advanced Mode editor for the MiSTer.ini configuration
- Switch between Easy Mode and Advanced Mode
- Automatic backups before applying configuration changes
- Restore MiSTer.ini from backups or defaults

### Scripts
- Install, configure and run update_all
- Install zaparoo
- Install migrate_sd (SD card migration utility)
- Install cifs_mount / cifs_umount
- Install auto_time
- Install and configure dav_browser
- Install and configure ftp_save_sync
- Install and Set static_wallpaper
- View live SSH output when running scripts

### ZapScripts
- Run update_all via the Zaparoo Core API
- Run migrate_sd via the Zaparoo Core API
- Run Insert-Coin via the Zaparoo Core API
- Open Bluetooth menu
- Open MiSTer OSD menu
- Cycle wallpaper
- Return to MiSTer home

### SaveManager
- Create timestamped backups of MiSTer saves
- Optional savestate backups
- Automatic backup retention per device
- Restore backups to any connected MiSTer
- Sync saves between multiple MiSTer systems
- Local Sync Folder for merging newest save files

### Wallpapers
- Install wallpaper packs using a JSON database system
- Multiple wallpaper sources supported
- Automatic update detection
- Remove installed wallpapers
- Built-in SSH output log
- Quick access via SMB

---

### Pre-Releases

| Name | Platform | Status | File |
|------|----------|--------|------|
| MiSTer Companion | Windows | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yml) | [Download Windows](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Windows-x86_64.zip) |
| MiSTer Companion | Linux | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yml) | [Download Linux](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Linux-x86_64.tar.gz) |

---

## Linux Notes

After extracting, make the application executable:

    chmod +x MiSTer-Companion

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

    pip install PyQt6 paramiko requests websocket-client psutil

Run:

    python main.py

---

## Legacy Version

MiSTer Companion v2.x is now considered **Legacy Edition** and will no longer receive updates.  
The source code will remain available for reference and community use.

---

## License

This project is licensed under the GNU General Public License v2.0 (GPL-2.0).

See the LICENSE file for full details.

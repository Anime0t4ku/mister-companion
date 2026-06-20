# MiSTer Companion

MiSTer Companion is a cross-platform GUI utility for managing and maintaining your MiSTer FPGA system over SSH or directly from a selected SD card using Offline Mode.

It provides a simple interface for common maintenance tasks without needing to use a terminal.

---

![Screenshot](assets/screenshot.png)

---

## Features

MiSTer Companion uses a tabbed interface to organize functionality.

### Flash SD

- Download the latest Mr. Fusion release directly from within the app
- Download the latest SuperStationONE SD Installer release directly from within the app
- Detect removable drives on supported platforms
- Flash SD cards without requiring external tools
- Simplifies initial MiSTer setup

### Connection

- Connect to your MiSTer over SSH
- Save and manage multiple devices
- Scan for MiSTer devices on your local network
- Automatic reconnect after reboot
- Switch between Online / SSH Mode and Offline / SD Card Mode
- Select a local MiSTer SD card for Offline Mode actions

### Device

- View SD card storage usage
- Detect USB storage usage
- Enable or disable SMB file sharing
- Open the MiSTer network share directly in the system file manager
- Open the selected SD card directly in Offline Mode
- Reboot MiSTer remotely

### MiSTer Settings

- Easy Mode for simplified configuration of common MiSTer.ini settings
- Advanced Mode editor for MiSTer.ini configuration
- Switch between Easy Mode and Advanced Mode
- Automatic backups before applying configuration changes
- Restore MiSTer.ini from backups or defaults
- Edit multiple MiSTer INI files, including MiSTer.ini and MiSTer_*.ini
- Offline Mode support for editing INI files directly from a selected SD card
- Improved Easy Mode and Advanced Mode synchronization
- Fixed an issue where extra empty lines could be created when switching between Easy Mode and Advanced Mode
- Added AmigaVision Preset
- Added Menu CRT presets for NTSC and PAL setups

### Scripts

- Install, configure and run update_all
- Run update_all directly against a selected SD card in Offline Mode
- Configure update_all sources
- Added MiSTer Frontier as an update_all source
- Install Zaparoo
- Install migrate_sd, the SD card migration utility
- Install cifs_mount / cifs_umount
- Install auto_time
- Install and configure dav_browser
- Install and configure ftp_save_sync
- Install and set static_wallpaper
- View live SSH output when running scripts

### ZapScripts

- Launch scripts and games directly on the MiSTer
- Open the Bluetooth menu
- Open the MiSTer OSD menu
- Cycle wallpaper
- Return to the MiSTer home screen

### ZapScraper

- Scrape artwork for use with the Zaparoo Frontend
- Recalbox Compatibility mode for Recalbox-style artwork layouts
- Zaparoo Companion mode, specifically made for the Zaparoo Frontend
- Helps prepare artwork and metadata for a cleaner Zaparoo Frontend experience
- Supports MiSTer game folders and Zaparoo-related artwork setups

### SaveManager

- Create timestamped backups of MiSTer saves
- Optional savestate backups
- Automatic backup retention per device
- Restore backups to any connected MiSTer
- Sync saves between multiple MiSTer systems
- Local Merge Folder for merging newest save files
- Offline Mode support for working with saves directly from a selected SD card

### Wallpapers

- Install wallpaper packs using a JSON database system
- Multiple wallpaper sources supported
- Automatic update detection
- Remove installed wallpapers
- Built-in SSH output log
- Quick access via SMB
- Offline Mode support for managing wallpapers directly from a selected SD card

### Extras

- Install, update and uninstall supported MiSTer extras
- Offline Mode support for managing supported extras directly from a selected SD card
- Install and manage Zaparoo Frontend
- Install and manage RetroAchievement Cores
- Configure RetroAchievement Cores directly from MiSTer Companion
- Install and manage MMS2 Game Boy Core
- Install and manage 3S-ARM
- Install and manage Sonic Mania
- Pico-8 and OpenBOR have moved from Extras to MiSTer Frontier through update_all, because their previous GitHub sources were archived

### Remote

- Control your MiSTer remotely from inside MiSTer Companion
- Send MiSTer navigation commands without needing a physical controller
- Use keyboard passthrough to send keyboard input from your computer to the MiSTer
- Useful for basic menu navigation, text input and quick remote control actions

### Manuals Reader

- Browse manuals stored on your MiSTer
- Open PDF manuals directly from MiSTer Companion
- Supports manuals stored in MiSTer documentation folders
- Useful for quickly checking game manuals from your computer

### RetroAchievements Viewer

- View RetroAchievements progress directly inside MiSTer Companion
- Configure RetroAchievements user details from within the app
- Quickly check achievement progress without leaving MiSTer Companion

### Offline Mode

- Use many MiSTer Companion actions directly on a selected SD card
- No active SSH connection or powered-on MiSTer required for supported actions
- Edit MiSTer Settings directly from the SD card
- Manage wallpapers directly from the SD card
- Manage supported Extras directly from the SD card
- Run update_all directly against the selected SD card
- Useful for preparing, maintaining or updating a MiSTer SD card from your computer

---

### Pre-Releases

| Name | Platform | Status | File |
|------|----------|--------|------|
| MiSTer Companion | Windows x86-64 | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Windows-x86_64.zip) |
| MiSTer Companion | Linux x86-64 | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-Linux-x86_64.tar.gz) |
| MiSTer Companion | macOS Apple Silicon | [![Build Status](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml/badge.svg)](https://github.com/Anime0t4ku/mister-companion/actions/workflows/build.yaml) | [Download](https://github.com/Anime0t4ku/mister-companion/releases/download/Pre-release/MiSTer-Companion-macOS-Apple-Silicon.dmg) |

---

## Linux Notes

After extracting, make the application executable:

    chmod +x MiSTer-Companion

---

## macOS Notes

MiSTer Companion for macOS is currently unsigned.

Because of this, macOS may show a warning saying the app cannot be opened because Apple cannot check it for malicious software.

To open it anyway:

1. Open **System Settings**
2. Go to **Privacy & Security**
3. Scroll down to the **Security** section
4. Find the message about **MiSTer Companion** being blocked
5. Click **Open Anyway**
6. Confirm by clicking **Open**

You should only need to do this the first time you launch the app.

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
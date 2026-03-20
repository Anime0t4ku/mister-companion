import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import paramiko
import requests
import psutil
from websocket import create_connection
import threading
import subprocess
import json
import os
import base64
import time
import socket
import webbrowser
import sys
import stat
from io import StringIO

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

CONFIG_FILE = "config.json"

# SaveManager folders
SAVE_ROOT = "SaveManager"
BACKUP_ROOT = os.path.join(SAVE_ROOT, "backups")
SYNC_ROOT = os.path.join(SAVE_ROOT, "sync")

# MiSTer Settings folders
MISTER_SETTINGS_ROOT = "MiSTerSettings"

DEFAULT_CONFIG = {
    "devices": [],
    "last_connected": None,
    "update_all_installed": False,
    "smb_enabled": False,
    "hide_setup_notice": False,
    "backup_retention": 10,
    "mister_settings_retention": 10
}

# =========================
# Utilities
# =========================

def encode_password(password: str) -> str:
    return base64.b64encode(password.encode()).decode()

def decode_password(encoded: str) -> str:
    try:
        return base64.b64decode(encoded.encode()).decode()
    except Exception:
        return ""

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

# =========================
# SSH Connection
# =========================

class MiSTerConnection:

    def __init__(self):
        self.client = None
        self.connected = False
        self.ip = None
        self.username = None
        self.password = None

    def connect(self, ip, username, password):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            self.client.connect(
                hostname=ip,
                username=username,
                password=password,
                timeout=5
            )
            self.connected = True
            self.ip = ip
            self.username = username
            self.password = password
            return True, "Connected"
        except paramiko.AuthenticationException:
            return False, "Authentication failed"
        except socket.error:
            return False, "Unable to reach MiSTer"
        except Exception as e:
            return False, str(e)

    def run_command(self, command):
        if not self.connected:
            return None
        try:
            stdin, stdout, stderr = self.client.exec_command(command)
            return stdout.read().decode()
        except Exception:
            self.connected = False
            return None

    def run_command_stream(self, command, callback):
        if not self.connected:
            return
        try:
            stdin, stdout, stderr = self.client.exec_command(command)
            for line in stdout:
                callback(line)
        except Exception:
            self.connected = False

    def reboot(self):
        if self.connected:
            self.client.exec_command("nohup /sbin/reboot >/dev/null 2>&1 &")

# =========================
# Main App
# =========================

class MiSTerApp:

    def __init__(self, root):
        self.root = root
        self.root.title("MiSTer Companion v2.7.6 by Anime0t4ku")
        self.root.geometry("900x900")

        # ===== App Icon =====
        try:
            icon = tk.PhotoImage(file=resource_path("icon.png"))
            self.root.iconphoto(True, icon)
        except Exception:
            pass

        self.connection = MiSTerConnection()
        self.config_data = load_config()

        # Create feature folders
        os.makedirs(BACKUP_ROOT, exist_ok=True)
        os.makedirs(SYNC_ROOT, exist_ok=True)
        os.makedirs(MISTER_SETTINGS_ROOT, exist_ok=True)

        self.console_visible = False

        self.connection_monitor_running = False
        self.connection_monitor_thread = None
        self.connection_monitor_failures = 0
        self.connection_monitor_suspended = False

        self.build_ui()
        self.load_devices()
        self.load_last_device()

        self.disable_controls()
        self.set_mister_settings_enabled(False)

        self.root.after(300, self.show_setup_notice)

    # =========================
    # Setup Notice Popup
    # =========================

    def show_setup_notice(self):
        if self.config_data.get("hide_setup_notice"):
            return

        popup = tk.Toplevel(self.root)
        popup.title("MiSTer Setup Required")
        popup.geometry("540x360")
        popup.minsize(540, 360)
        popup.resizable(False, False)
        popup.grab_set()
        popup.transient(self.root)

        wrapper = ttk.Frame(popup, padding=20)
        wrapper.pack(fill="both", expand=True)

        # Detect flashing tool depending on platform
        if sys.platform.startswith("win"):
            flash_tool_name = "Rufus"
            flash_tool_url = "https://rufus.ie/en/"
        else:
            flash_tool_name = "balenaEtcher"
            flash_tool_url = "https://etcher.balena.io/"

        ttk.Label(wrapper,
                  text="MiSTer Companion Setup",
                  font=("Segoe UI", 13, "bold")).pack(pady=(5, 15))

        ttk.Label(wrapper,
                  text="This application assumes you have already flashed\n"
                       "MiSTerFusion to your SD card.\n\n"
                       "If you have not done so yet, download MiSTerFusion\n"
                       f"and flash it using {flash_tool_name} before continuing.",
                  justify="center").pack(pady=10)

        button_frame = ttk.Frame(wrapper)
        button_frame.pack(pady=15)

        ttk.Button(button_frame,
                   text="Download MiSTerFusion",
                   width=22,
                   command=lambda: webbrowser.open(
                       "https://github.com/MiSTer-devel/mr-fusion/releases"
                   )).pack(side="left", padx=15)

        ttk.Button(button_frame,
                   text=f"Download {flash_tool_name}",
                   width=22,
                   command=lambda: webbrowser.open(
                       flash_tool_url
                   )).pack(side="left", padx=15)

        hide_var = tk.BooleanVar()

        ttk.Checkbutton(wrapper,
                        text="Don't show this again",
                        variable=hide_var).pack(pady=(15, 10))

        def close_popup():
            if hide_var.get():
                self.config_data["hide_setup_notice"] = True
                save_config(self.config_data)
            popup.destroy()

        ttk.Button(wrapper,
                   text="Continue",
                   width=18,
                   command=close_popup).pack(pady=10)

        popup.update_idletasks()
        x = (popup.winfo_screenwidth() // 2) - (540 // 2)
        y = (popup.winfo_screenheight() // 2) - (340 // 2)
        popup.geometry(f"+{x}+{y}")

    # =========================
    # UI
    # =========================

    def build_ui(self):

        style = ttk.Style()

        try:
            if sys.platform.startswith("win"):
                style.theme_use("vista")
            else:
                style.theme_use("clam")
        except Exception:
            pass

        style.configure("green.Horizontal.TProgressbar",
                        troughcolor="#e0e0e0",
                        background="#4CAF50")
        style.configure("orange.Horizontal.TProgressbar",
                        troughcolor="#e0e0e0",
                        background="#FF9800")
        style.configure("red.Horizontal.TProgressbar",
                        troughcolor="#e0e0e0",
                        background="#F44336")

        # ===== Header =====

        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill="x", padx=20, pady=(10, 5))

        ttk.Label(top_frame,
                  text="MiSTer Companion",
                  font=("Segoe UI", 14, "bold")).pack(side="left")

        self.status_label = ttk.Label(top_frame,
                                      text="Disconnected",
                                      foreground="red")
        self.status_label.pack(side="right")

        # ===== Notebook Layout =====

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.connection_tab = ttk.Frame(self.notebook)
        self.device_tab = ttk.Frame(self.notebook)
        self.mister_settings_tab = ttk.Frame(self.notebook)
        self.scripts_tab = ttk.Frame(self.notebook)
        self.zapscripts_tab = ttk.Frame(self.notebook)
        self.savemanager_tab = ttk.Frame(self.notebook)
        self.wallpapers_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.connection_tab, text="Connection")
        self.notebook.add(self.device_tab, text="Device")
        self.notebook.add(self.mister_settings_tab, text="MiSTer Settings")
        self.notebook.add(self.scripts_tab, text="Scripts")
        self.notebook.add(self.zapscripts_tab, text="ZapScripts")
        self.notebook.add(self.savemanager_tab, text="SaveManager")
        self.notebook.add(self.wallpapers_tab, text="Wallpapers")

        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # ===== Device Section =====

        device_frame = ttk.LabelFrame(self.connection_tab, text="Saved Devices")
        device_frame.pack(fill="x", padx=20, pady=10)

        device_inner = ttk.Frame(device_frame)
        device_inner.pack(pady=10)

        self.device_combo = ttk.Combobox(device_inner,
                                         width=30,
                                         state="readonly")
        self.device_combo.pack(side="left", padx=10)
        self.device_combo.bind("<<ComboboxSelected>>",
                               self.load_selected_device)

        ttk.Button(device_inner,
                   text="Save Device",
                   command=self.save_current_device).pack(side="left", padx=5)

        ttk.Button(device_inner,
                   text="Edit Device",
                   command=self.edit_selected_device).pack(side="left", padx=5)

        ttk.Button(device_inner,
                   text="Delete Device",
                   command=self.delete_selected_device).pack(side="left", padx=5)

        # ===== Connection Bar =====

        conn_outer = ttk.Frame(self.connection_tab)
        conn_outer.pack(fill="x", padx=20, pady=15)

        conn_frame = ttk.Frame(conn_outer)
        conn_frame.pack()

        ttk.Label(conn_frame, text="IP:").pack(side="left", padx=(0, 5))
        self.ip_entry = ttk.Entry(conn_frame, width=18)
        self.ip_entry.pack(side="left", padx=5)
        self.ip_entry.bind("<KeyRelease>", self.on_connection_field_change)

        ttk.Label(conn_frame, text="User:").pack(side="left", padx=(10, 5))
        self.username_entry = ttk.Entry(conn_frame, width=12)
        self.username_entry.pack(side="left", padx=5)
        self.username_entry.insert(0, "root")
        self.username_entry.bind("<KeyRelease>", self.on_connection_field_change)

        ttk.Label(conn_frame, text="Pass:").pack(side="left", padx=(10, 5))
        self.password_entry = ttk.Entry(conn_frame, show="*", width=12)
        self.password_entry.pack(side="left", padx=5)
        self.password_entry.insert(0, "1")
        self.password_entry.bind("<KeyRelease>", self.on_connection_field_change)

        self.password_default = True

        def clear_default_password(event):
            if self.password_default:
                self.password_entry.delete(0, tk.END)
                self.password_default = False

        def restore_default_password(event):
            if not self.password_entry.get():
                self.password_entry.insert(0, "1")
                self.password_default = True

        self.password_entry.bind("<FocusIn>", clear_default_password)
        self.password_entry.bind("<FocusOut>", restore_default_password)

        self.scan_button = ttk.Button(conn_frame,
                                      text="Scan Network",
                                      width=14,
                                      command=self.open_network_scanner)
        self.scan_button.pack(side="left", padx=5)

        self.connect_button = ttk.Button(conn_frame,
                                         text="Connect",
                                         width=12,
                                         command=self.connect)
        self.connect_button.pack(side="left", padx=5)

        self.disconnect_button = ttk.Button(conn_frame,
                                            text="Disconnect",
                                            width=12,
                                            command=self.disconnect,
                                            state="disabled")
        self.disconnect_button.pack(side="left", padx=5)

        ttk.Label(conn_frame,
                  text="(Defaults: root / 1)",
                  foreground="gray").pack(side="left", padx=10)

        # ===== Storage =====

        storage_frame = ttk.LabelFrame(self.device_tab, text="Storage")
        storage_frame.pack(fill="x", padx=20, pady=15)

        storage_inner = ttk.Frame(storage_frame)
        storage_inner.pack(pady=20)

        # SD storage
        ttk.Label(storage_inner, text="SD Card").pack()

        self.storage_bar = ttk.Progressbar(storage_inner,
                                           length=500,
                                           style="green.Horizontal.TProgressbar")
        self.storage_bar.pack()

        self.storage_label = ttk.Label(storage_inner, text="--")
        self.storage_label.pack(pady=(5, 10))

        # USB storage
        ttk.Label(storage_inner, text="USB Storage").pack()

        self.usb_bar = ttk.Progressbar(storage_inner,
                                       length=500,
                                       style="green.Horizontal.TProgressbar")
        self.usb_bar.pack()

        self.usb_label = ttk.Label(storage_inner, text="Checking...")
        self.usb_label.pack(pady=(5, 0))

        # ===== Maintenance =====

        maintenance_frame = ttk.LabelFrame(self.scripts_tab, text="update_all")
        maintenance_frame.pack(fill="x", padx=20, pady=15)

        self.update_status_label = ttk.Label(maintenance_frame,
                                             text="update_all: Unknown",
                                             foreground="gray")
        self.update_status_label.pack()

        button_row = ttk.Frame(maintenance_frame)
        button_row.pack(pady=15)

        self.install_button = ttk.Button(button_row,
                                         text="Install update_all",
                                         width=18,
                                         command=self.install_update_all)
        self.install_button.pack(side="left", padx=8)

        self.uninstall_button = ttk.Button(button_row,
                                           text="Uninstall update_all",
                                           width=18,
                                           command=self.uninstall_update_all)
        self.uninstall_button.pack(side="left", padx=8)

        self.configure_button = ttk.Button(
            button_row,
            text="Configure update_all",
            width=20,
            command=self.open_update_all_configurator,
            state="disabled"
        )
        self.configure_button.pack(side="left", padx=8)

        self.run_button = ttk.Button(button_row,
                                     text="Run update_all",
                                     width=18,
                                     command=self.run_update_all)
        self.run_button.pack(side="left", padx=8)

        # ===== Zaparoo =====

        zaparoo_frame = ttk.LabelFrame(self.scripts_tab, text="Zaparoo")
        zaparoo_frame.pack(fill="x", padx=20, pady=15)

        self.zaparoo_status_label = ttk.Label(
            zaparoo_frame,
            text="Zaparoo: Unknown",
            foreground="gray"
        )
        self.zaparoo_status_label.pack()

        zaparoo_buttons = ttk.Frame(zaparoo_frame)
        zaparoo_buttons.pack(pady=15)

        self.install_zaparoo_button = ttk.Button(
            zaparoo_buttons,
            text="Install Zaparoo",
            width=18,
            command=self.install_zaparoo
        )
        self.install_zaparoo_button.pack(side="left", padx=8)

        self.run_zaparoo_button = ttk.Button(
            zaparoo_buttons,
            text="Enable Zaparoo Service",
            width=22,
            command=self.run_zaparoo
        )
        self.run_zaparoo_button.pack(side="left", padx=8)

        self.uninstall_zaparoo_button = ttk.Button(
            zaparoo_buttons,
            text="Uninstall Zaparoo",
            width=18,
            command=self.uninstall_zaparoo
        )
        self.uninstall_zaparoo_button.pack(side="left", padx=8)

        # ===== SD Migration =====

        migrate_frame = ttk.LabelFrame(self.scripts_tab, text="SD Migration")
        migrate_frame.pack(fill="x", padx=20, pady=15)

        self.migrate_status_label = ttk.Label(
            migrate_frame,
            text="migrate_sd: Unknown",
            foreground="gray"
        )
        self.migrate_status_label.pack(pady=(5, 5))

        migrate_buttons = ttk.Frame(migrate_frame)
        migrate_buttons.pack(pady=10)

        self.install_migrate_button = ttk.Button(
            migrate_buttons,
            text="Install migrate_sd",
            width=20,
            command=self.install_migrate_sd
        )
        self.install_migrate_button.pack(side="left", padx=8)

        self.uninstall_migrate_button = ttk.Button(
            migrate_buttons,
            text="Uninstall migrate_sd",
            width=20,
            command=self.uninstall_migrate_sd
        )
        self.uninstall_migrate_button.pack(side="left", padx=8)

        # ===== CIFS Network Share =====

        cifs_frame = ttk.LabelFrame(self.scripts_tab, text="CIFS Network Share")
        cifs_frame.pack(fill="x", padx=20, pady=15)

        self.cifs_status_label = ttk.Label(
            cifs_frame,
            text="cifs_mount: Unknown",
            foreground="gray"
        )
        self.cifs_status_label.pack(pady=(5,5))

        cifs_buttons = ttk.Frame(cifs_frame)
        cifs_buttons.pack(pady=10)

        self.install_cifs_button = ttk.Button(
            cifs_buttons,
            text="Install",
            width=14,
            command=self.install_cifs_mount
        )
        self.install_cifs_button.pack(side="left", padx=6)

        self.configure_cifs_button = ttk.Button(
            cifs_buttons,
            text="Configure",
            width=14,
            command=self.configure_cifs
        )
        self.configure_cifs_button.pack(side="left", padx=6)

        self.mount_cifs_button = ttk.Button(
            cifs_buttons,
            text="Mount",
            width=14,
            command=self.run_cifs_mount
        )
        self.mount_cifs_button.pack(side="left", padx=6)

        self.unmount_cifs_button = ttk.Button(
            cifs_buttons,
            text="Unmount",
            width=14,
            command=self.run_cifs_umount
        )
        self.unmount_cifs_button.pack(side="left", padx=6)

        self.remove_cifs_config_button = ttk.Button(
            cifs_buttons,
            text="Remove Config",
            width=14,
            command=self.remove_cifs_config
        )
        self.remove_cifs_config_button.pack(side="left", padx=6)

        self.uninstall_cifs_button = ttk.Button(
            cifs_buttons,
            text="Uninstall",
            width=14,
            command=self.uninstall_cifs_mount
        )
        self.uninstall_cifs_button.pack(side="left", padx=6)

        # ===== Open Scripts Folder Button =====

        self.open_scripts_folder_button = ttk.Button(
            self.scripts_tab,
            text="Open Scripts Folder",
            width=22,
            command=self.open_scripts_folder,
            state="disabled"
        )

        self.open_scripts_folder_button.pack(pady=(10, 5))

        # ===== SSH Output =====

        self.console_frame = ttk.LabelFrame(self.scripts_tab, text="SSH Output")

        console_header = ttk.Frame(self.console_frame)
        console_header.pack(fill="x")

        ttk.Button(console_header,
                   text="Hide",
                   width=8,
                   command=self.toggle_console).pack(side="right", padx=5)

        console_container = ttk.Frame(self.console_frame)
        console_container.pack(fill="both", padx=20, pady=10)

        scrollbar = ttk.Scrollbar(console_container)
        scrollbar.pack(side="right", fill="y")

        self.console = tk.Text(console_container,
                               height=12,
                               yscrollcommand=scrollbar.set)

        self.console.pack(side="left", fill="both", expand=True)

        scrollbar.config(command=self.console.yview)

        # ===== File Sharing =====

        files_frame = ttk.LabelFrame(self.device_tab, text="File Sharing")
        files_frame.pack(fill="x", padx=20, pady=15)

        self.smb_status_label = ttk.Label(files_frame,
                                          text="SMB: Unknown",
                                          foreground="gray")
        self.smb_status_label.pack()

        files_inner = ttk.Frame(files_frame)
        files_inner.pack(pady=20)

        self.enable_smb_button = ttk.Button(files_inner,
                                            text="Enable SMB",
                                            width=18,
                                            command=self.enable_smb)
        self.enable_smb_button.pack(side="left", padx=10)

        self.disable_smb_button = ttk.Button(files_inner,
                                             text="Disable SMB",
                                             width=18,
                                             command=self.disable_smb)
        self.disable_smb_button.pack(side="left", padx=10)

        self.explorer_button = ttk.Button(files_inner,
                                          text="Open in Explorer",
                                          width=22,
                                          command=self.open_explorer)
        self.explorer_button.pack(side="left", padx=20)

        # ===== Power =====

        power_frame = ttk.LabelFrame(self.device_tab, text="Power")
        power_frame.pack(fill="x", padx=20, pady=15)

        self.reboot_button = ttk.Button(power_frame,
                                        text="Reboot MiSTer",
                                        width=25,
                                        command=self.reboot)
        self.reboot_button.pack(pady=20)

        # ===== Zapscripts =====

        self.zapscripts_wrapper = ttk.Frame(self.zapscripts_tab)
        self.zapscripts_wrapper.pack(fill="both", expand=True, padx=20, pady=20)

        self.zapscripts_message = ttk.Label(
            self.zapscripts_wrapper,
            text="Connect to a MiSTer device to load Zaparoo scripts.",
            foreground="gray"
        )

        self.zapscripts_message.pack()

        # ===== SaveManager =====

        savemanager_frame = ttk.Frame(self.savemanager_tab)
        savemanager_frame.pack(fill="both", expand=True, padx=20, pady=20)

        self.savemanager_info = ttk.Label(
            savemanager_frame,
            text="SaveManager allows you to backup, restore and sync MiSTer saves and savestates.\n\n"
                 "Backups are stored locally on your PC and are never modified.\n"
                 "The Sync folder is used to merge saves between devices.",
            justify="center",
            foreground="gray"
        )

        self.savemanager_info.pack(pady=(0, 20))

        button_row = ttk.Frame(savemanager_frame)
        button_row.pack(pady=10)

        self.backup_count_label = ttk.Label(
            savemanager_frame,
            text="Current backups for this device: 0",
            foreground="gray"
        )
        self.backup_count_label.pack(pady=(5, 10))

        retention_row = ttk.Frame(savemanager_frame)
        retention_row.pack(pady=(0, 10))

        self.retention_label = ttk.Label(
            retention_row,
            text="Backups to keep per device:",
            foreground="gray"
        )
        self.retention_label.pack(side="left", padx=5)

        self.retention_var = tk.IntVar(
            value=self.config_data.get("backup_retention", 10)
        )

        self.retention_spin = ttk.Spinbox(
            retention_row,
            from_=1,
            to=100,
            width=5,
            textvariable=self.retention_var,
            command=self.save_retention_setting
        )

        self.retention_spin.pack(side="left", padx=5)

        self.backup_button = ttk.Button(
            button_row,
            text="Backup Saves",
            width=18,
            command=self.backup_saves
        )
        self.backup_button.pack(side="left", padx=10)

        self.restore_button = ttk.Button(
            button_row,
            text="Restore Backup",
            width=18,
            command=self.restore_saves
        )
        self.restore_button.pack(side="left", padx=10)

        self.sync_button = ttk.Button(
            button_row,
            text="Sync Saves",
            width=18,
            command=self.sync_saves
        )
        self.sync_button.pack(side="left", padx=10)

        folder_row = ttk.Frame(savemanager_frame)
        folder_row.pack(pady=15)

        self.open_backup_folder_button = ttk.Button(
            folder_row,
            text="Browse Backups",
            width=18,
            command=self.open_backup_folder
        )
        self.open_backup_folder_button.pack(side="left", padx=10)

        self.open_sync_folder_button = ttk.Button(
            folder_row,
            text="Browse Sync Folder",
            width=18,
            command=self.open_sync_folder
        )
        self.open_sync_folder_button.pack(side="left", padx=10)

        self.savemanager_log_frame = ttk.LabelFrame(savemanager_frame, text="Status")

        log_header = ttk.Frame(self.savemanager_log_frame)
        log_header.pack(fill="x")

        self.hide_log_button = ttk.Button(
            log_header,
            text="Hide",
            width=8,
            command=self.hide_savemanager_log
        )
        self.hide_log_button.pack(side="right", padx=5, pady=5)

        self.savemanager_log = tk.Text(self.savemanager_log_frame, height=10)
        self.savemanager_log.pack(fill="both", expand=True, padx=10, pady=10)

        # ===== Wallpapers =====

        wallpapers_frame = ttk.Frame(self.wallpapers_tab)
        wallpapers_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # ===== Ranny Snice Wallpapers =====

        ranny_frame = ttk.LabelFrame(
            wallpapers_frame,
            text="Ranny Snice Wallpapers"
        )
        ranny_frame.pack(fill="x", pady=10)

        ranny_buttons = ttk.Frame(ranny_frame)
        ranny_buttons.pack(pady=15)

        self.install_169_wallpapers_button = ttk.Button(
            ranny_buttons,
            text="Install 16:9 Wallpapers",
            width=22,
            command=self.install_169_wallpapers,
            state="disabled"
        )
        self.install_169_wallpapers_button.pack(side="left", padx=8)

        self.install_43_wallpapers_button = ttk.Button(
            ranny_buttons,
            text="Install 4:3 Wallpapers",
            width=22,
            command=self.install_43_wallpapers,
            state="disabled"
        )
        self.install_43_wallpapers_button.pack(side="left", padx=8)

        self.remove_wallpapers_button = ttk.Button(
            ranny_buttons,
            text="Remove Installed Wallpapers",
            width=26,
            command=self.remove_ranny_wallpapers,
            state="disabled"
        )
        self.remove_wallpapers_button.pack(side="left", padx=8)
        # Open wallpaper folder button (below wallpaper sources)

        self.open_wallpaper_folder_button = ttk.Button(
            wallpapers_frame,
            text="Open Wallpaper Folder",
            width=24,
            command=self.open_wallpaper_folder,
            state="disabled"
        )
        self.open_wallpaper_folder_button.pack(pady=(12, 10))

        # ===== Wallpapers Console =====

        self.wallpaper_console_visible = False

        self.wallpaper_console_frame = ttk.LabelFrame(
            wallpapers_frame,
            text="SSH Output"
        )

        console_header = ttk.Frame(self.wallpaper_console_frame)
        console_header.pack(fill="x")

        ttk.Button(
            console_header,
            text="Hide",
            width=8,
            command=self.toggle_wallpaper_console
        ).pack(side="right", padx=5)

        console_container = ttk.Frame(self.wallpaper_console_frame)
        console_container.pack(fill="both", padx=20, pady=10)

        scrollbar = ttk.Scrollbar(console_container)
        scrollbar.pack(side="right", fill="y")

        self.wallpaper_console = tk.Text(
            console_container,
            height=12,
            yscrollcommand=scrollbar.set
        )

        self.wallpaper_console.pack(side="left", fill="both", expand=True)

        scrollbar.config(command=self.wallpaper_console.yview)

        # ===== MiSTer Settings =====

        mister_settings_frame = ttk.Frame(self.mister_settings_tab)
        mister_settings_frame.pack(fill="both", expand=True, padx=20, pady=20)

        self.mister_settings_info = ttk.Label(
            mister_settings_frame,
            text="MiSTer Settings allows you to edit MiSTer.ini with an Easy and Advanced mode.\n"
                 "Backups are stored locally on your PC in a separate MiSTerSettings folder.\n"
                 "Settings are only applied when you press Save.",
            justify="center",
            foreground="black"
        )
        self.mister_settings_info.pack(pady=(0, 12))

        mode_row = ttk.Frame(mister_settings_frame)
        mode_row.pack(pady=(0, 10))

        ttk.Label(mode_row, text="Mode:").pack(side="left", padx=(0, 8))

        self.mister_settings_mode_var = tk.StringVar(value="easy")

        self.easy_mode_radio = ttk.Radiobutton(
            mode_row,
            text="Easy",
            value="easy",
            variable=self.mister_settings_mode_var,
            command=self.update_settings_mode
        )
        self.easy_mode_radio.pack(side="left", padx=5)

        self.advanced_mode_radio = ttk.Radiobutton(
            mode_row,
            text="Advanced",
            value="advanced",
            variable=self.mister_settings_mode_var,
            command=self.update_settings_mode
        )
        self.advanced_mode_radio.pack(side="left", padx=5)

        self.mister_settings_notice_label = ttk.Label(
            mister_settings_frame,
            text="",
            foreground="orange",
            justify="center"
        )
        self.mister_settings_notice_label.pack(pady=(0, 10))

        self.mister_settings_content = ttk.Frame(mister_settings_frame)
        self.mister_settings_content.pack(fill="both", expand=True, pady=(0, 15))

        content_inner = ttk.Frame(self.mister_settings_content)
        content_inner.pack(fill="both", expand=True)

        # Easy Mode preview / placeholders
        self.easy_frame = ttk.LabelFrame(content_inner, text="Easy Mode")
        self.easy_frame.pack(pady=(0, 10))

        easy_grid = ttk.Frame(self.easy_frame)
        easy_grid.pack(padx=18, pady=14)

        ttk.Label(easy_grid, text="HDMI Mode").grid(row=0, column=0, sticky="w", padx=5, pady=5)

        self.easy_hdmi_mode_combo = ttk.Combobox(
            easy_grid,
            state="readonly",
            values=[
                "HD Output (Default)",
                "Direct Video (CRT / Scaler)"
            ],
            width=28
        )

        self.easy_hdmi_mode_combo.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        self.easy_hdmi_mode_combo.bind("<<ComboboxSelected>>", self.on_easy_hdmi_mode_changed)
        self.easy_hdmi_mode_combo.set("HD Output (Default)")

        # Resolution
        ttk.Label(easy_grid, text="Resolution").grid(row=1, column=0, sticky="w", padx=5, pady=5)

        self.easy_resolution_combo = ttk.Combobox(
            easy_grid,
            state="readonly",
            values=[
                "1280x720@60",
                "1024x768@60",
                "720x480@60",
                "720x576@50",
                "1280x1024@60",
                "800x600@60",
                "640x480@60",
                "1280x720@50",
                "1920x1080@60",
                "1920x1080@50",
                "1366x768@60",
                "1024x600@60",
                "1920x1440@60",
                "2048x1536@60",
                "2560x1440@60"
            ],
            width=28
        )

        self.easy_resolution_combo.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        self.easy_resolution_combo.set("1920x1080@60")

        # HDMI Scaling Mode
        ttk.Label(easy_grid, text="HDMI Scaling Mode").grid(row=3, column=0, sticky="w", padx=5, pady=5)

        self.easy_scaling_combo = ttk.Combobox(
            easy_grid,
            state="readonly",
            values=[
                "Disabled",
                "Low Latency",
                "Exact Refresh"
            ],
            width=28
        )

        self.easy_scaling_combo.grid(row=3, column=1, sticky="w", padx=5, pady=5)
        self.easy_scaling_combo.set("Low Latency")

        # HDMI Audio
        ttk.Label(easy_grid, text="HDMI Audio").grid(row=4, column=0, sticky="w", padx=5, pady=5)

        self.easy_hdmi_audio_combo = ttk.Combobox(
            easy_grid,
            state="readonly",
            values=[
                "Enabled",
                "Disabled (DVI Mode)"
            ],
            width=28
        )

        self.easy_hdmi_audio_combo.grid(row=4, column=1, sticky="w", padx=5, pady=5)
        self.easy_hdmi_audio_combo.set("Enabled")

        # HDR
        ttk.Label(easy_grid, text="HDR").grid(row=5, column=0, sticky="w", padx=5, pady=5)

        self.easy_hdr_combo = ttk.Combobox(
            easy_grid,
            state="readonly",
            values=[
                "Disabled",
                "Enabled"
            ],
            width=28
        )

        self.easy_hdr_combo.grid(row=5, column=1, sticky="w", padx=5, pady=5)
        self.easy_hdr_combo.set("Disabled")

        # HDMI Limited Range
        ttk.Label(easy_grid, text="HDMI Range").grid(row=6, column=0, sticky="w", padx=5, pady=5)

        self.easy_hdmi_limited_combo = ttk.Combobox(
            easy_grid,
            state="readonly",
            values=[
                "Full Range",
                "Limited Range"
            ],
            width=28
        )

        self.easy_hdmi_limited_combo.grid(row=6, column=1, sticky="w", padx=5, pady=5)
        self.easy_hdmi_limited_combo.set("Disabled")

        # Analogue Output
        ttk.Label(easy_grid, text="Analogue Output").grid(row=7, column=0, sticky="w", padx=5, pady=5)

        self.easy_analogue_combo = ttk.Combobox(
            easy_grid,
            state="readonly",
            values=[
                "RGB (Consumer TV)",
                "RGB (PVM/BVM)",
                "Component (YPbPr)",
                "S-Video",
                "VGA Monitor"
            ],
            width=28
        )

        self.easy_analogue_combo.grid(row=7, column=1, sticky="w", padx=5, pady=5)
        self.easy_analogue_combo.set("RGB (Consumer TV)")

        # MiSTer Logo
        ttk.Label(easy_grid, text="MiSTer Logo").grid(row=8, column=0, sticky="w", padx=5, pady=5)

        self.easy_logo_combo = ttk.Combobox(
            easy_grid,
            state="readonly",
            values=[
                "Enabled",
                "Disabled"
            ],
            width=28
        )

        self.easy_logo_combo.grid(row=8, column=1, sticky="w", padx=5, pady=5)
        self.easy_logo_combo.set("Enabled")

        # Advanced Mode editor
        self.advanced_frame = ttk.LabelFrame(content_inner, text="Advanced Mode")
        self.advanced_frame.pack(fill="both", expand=True, pady=(0, 10))

        advanced_inner = ttk.Frame(self.advanced_frame)
        advanced_inner.pack(fill="both", expand=True, padx=12, pady=12)

        advanced_scroll = ttk.Scrollbar(advanced_inner)
        advanced_scroll.pack(side="right", fill="y")

        self.advanced_text = tk.Text(
            advanced_inner,
            height=16,
            wrap="none",
            font=("Consolas", 10),
            padx=6,
            pady=6,
            yscrollcommand=advanced_scroll.set
        )

        self.advanced_text.pack(fill="both", expand=True)

        advanced_scroll.config(command=self.advanced_text.yview)

        # Buttons
        mister_settings_button_row = ttk.Frame(mister_settings_frame)
        mister_settings_button_row.pack(pady=10)

        self.mister_settings_save_button = ttk.Button(
            mister_settings_button_row,
            text="Save",
            width=16,
            command=self.save_mister_settings,
            state="disabled"
        )
        self.mister_settings_save_button.pack(side="left", padx=8)

        self.mister_settings_backup_button = ttk.Button(
            mister_settings_button_row,
            text="Backup",
            width=16,
            command=self.backup_mister_settings,
            state="disabled"
        )
        self.mister_settings_backup_button.pack(side="left", padx=8)

        self.mister_settings_restore_button = ttk.Button(
            mister_settings_button_row,
            text="Restore Backup",
            width=16,
            command=self.restore_mister_settings,
            state="disabled"
        )
        self.mister_settings_restore_button.pack(side="left", padx=8)

        self.mister_settings_defaults_button = ttk.Button(
            mister_settings_button_row,
            text="Restore Defaults",
            width=16,
            command=self.restore_default_mister_settings,
            state="disabled"
        )
        self.mister_settings_defaults_button.pack(side="left", padx=8)

        retention_row = ttk.Frame(mister_settings_frame)
        retention_row.pack(pady=(10, 0))

        self.mister_settings_retention_label = ttk.Label(
            retention_row,
            text="Backups to keep per device:",
            foreground="gray"
        )
        self.mister_settings_retention_label.pack(side="left", padx=5)

        self.mister_settings_retention_var = tk.IntVar(
            value=self.config_data.get("mister_settings_retention", 10)
        )

        self.mister_settings_retention_spin = ttk.Spinbox(
            retention_row,
            from_=1,
            to=100,
            width=5,
            textvariable=self.mister_settings_retention_var,
            command=self.save_mister_settings_retention_setting,
            state="disabled"
        )
        self.mister_settings_retention_spin.pack(side="left", padx=5)
        self.mister_settings_retention_spin.bind(
            "<FocusOut>",
            lambda event: self.save_mister_settings_retention_setting()
        )

        self.mister_settings_open_folder_button = ttk.Button(
            retention_row,
            text="Open Backup Folder",
            width=18,
            command=self.open_mister_settings_folder,
            state="disabled"
        )
        self.mister_settings_open_folder_button.pack(side="left", padx=15)
        self.update_easy_mode_state()
        self.update_settings_mode()

    # =========================
    # Device Management
    # =========================

    def load_devices(self):
        names = [d["name"] for d in self.config_data.get("devices", [])]
        self.device_combo["values"] = names

    def save_current_device(self):
        name = simpledialog.askstring("Device Name",
                                      "Enter a name for this device:")
        if not name:
            return

        device = {
            "name": name,
            "ip": self.ip_entry.get().strip(),
            "username": self.username_entry.get().strip(),
            "password": encode_password(self.password_entry.get().strip())
        }

        for d in self.config_data["devices"]:
            if d["name"].lower() == name.lower():
                messagebox.showerror("Error", "Device name already exists.")
                return

        self.config_data["devices"].append(device)
        self.config_data["last_connected"] = name
        save_config(self.config_data)

        self.load_devices()

        # Automatically select the newly added device
        self.device_combo.set(name)
        self.load_selected_device()

    def delete_selected_device(self):

        selected = self.device_combo.get()

        if not selected:
            return

        confirm = messagebox.askyesno(
            "Delete Device",
            f'Delete device "{selected}"?\n\nThis will remove the saved profile.'
        )

        if not confirm:
            return

        device_path = os.path.join(BACKUP_ROOT, selected)

        if os.path.exists(device_path):

            delete_backups = messagebox.askyesno(
                "Delete Backups",
                f'Do you want to delete the saved backups for "{selected}"?\n\n'
                "Yes = permanently delete backups\n"
                "No = keep backups and rename folder"
            )

            try:

                if delete_backups:

                    import shutil
                    shutil.rmtree(device_path)


                else:

                    base_name = f"removed_{selected}"

                    new_name = base_name

                    counter = 2

                    new_path = os.path.join(BACKUP_ROOT, new_name)

                    # Find available folder name

                    while os.path.exists(new_path):
                        new_name = f"{base_name}_{counter}"

                        new_path = os.path.join(BACKUP_ROOT, new_name)

                        counter += 1

                    os.rename(device_path, new_path)

            except Exception as e:
                messagebox.showerror(
                    "Backup Operation Failed",
                    f"Unable to modify backup folder:\n{str(e)}"
                )

        # Remove device from config
        self.config_data["devices"] = [
            d for d in self.config_data["devices"]
            if d["name"] != selected
        ]

        save_config(self.config_data)

        self.load_devices()

        # Clear selection and input fields
        self.device_combo.set("")
        self.ip_entry.delete(0, tk.END)
        self.username_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)

    def edit_selected_device(self):

        selected = self.device_combo.get()

        if not selected:
            messagebox.showerror("Error", "Select a device first.")
            return

        device = None
        for d in self.config_data["devices"]:
            if d["name"] == selected:
                device = d
                break

        if not device:
            return

        popup = tk.Toplevel(self.root)
        popup.title("Edit Device")
        popup.geometry("320x260")
        popup.resizable(False, False)

        frame = ttk.Frame(popup, padding=15)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Device Name").pack(anchor="w")
        name_entry = ttk.Entry(frame)
        name_entry.pack(fill="x", pady=3)
        name_entry.insert(0, device["name"])

        ttk.Label(frame, text="IP Address").pack(anchor="w")
        ip_entry = ttk.Entry(frame)
        ip_entry.pack(fill="x", pady=3)
        ip_entry.insert(0, device["ip"])

        ttk.Label(frame, text="Username").pack(anchor="w")
        user_entry = ttk.Entry(frame)
        user_entry.pack(fill="x", pady=3)
        user_entry.insert(0, device["username"])

        ttk.Label(frame, text="Password").pack(anchor="w")
        pass_entry = ttk.Entry(frame, show="*")
        pass_entry.pack(fill="x", pady=3)
        pass_entry.insert(0, decode_password(device["password"]))

        def save_changes():

            new_name = name_entry.get().strip()
            new_ip = ip_entry.get().strip()
            new_user = user_entry.get().strip()
            new_pass = pass_entry.get().strip()

            if not new_name:
                messagebox.showerror("Error", "Device name cannot be empty.")
                return

            old_name = device["name"]

            # Update device info
            device["name"] = new_name
            device["ip"] = new_ip
            device["username"] = new_user
            device["password"] = encode_password(new_pass)

            save_config(self.config_data)

            # Rename backup folder if device name changed
            if old_name != new_name:

                old_path = os.path.join(BACKUP_ROOT, old_name)
                new_path = os.path.join(BACKUP_ROOT, new_name)

                if os.path.exists(old_path):

                    try:
                        os.rename(old_path, new_path)
                    except Exception as e:
                        messagebox.showerror(
                            "Backup Rename Failed",
                            f"Unable to rename backup folder:\n{str(e)}"
                        )

            self.load_devices()
            self.device_combo.set(new_name)
            self.load_selected_device()

            popup.destroy()

        button_row = ttk.Frame(frame)
        button_row.pack(pady=10)

        ttk.Button(button_row,
                   text="Save",
                   width=12,
                   command=save_changes).pack(side="left", padx=5)

        ttk.Button(button_row,
                   text="Cancel",
                   width=12,
                   command=popup.destroy).pack(side="left", padx=5)

    def load_selected_device(self, event=None):
        selected = self.device_combo.get()
        for d in self.config_data.get("devices", []):
            if d["name"] == selected:
                self.ip_entry.delete(0, tk.END)
                self.username_entry.delete(0, tk.END)
                self.password_entry.delete(0, tk.END)

                self.ip_entry.insert(0, d["ip"])
                self.username_entry.insert(0, d["username"])
                self.password_entry.insert(0, decode_password(d["password"]))

    def load_last_device(self):
        last = self.config_data.get("last_connected")
        if not last:
            return
        for d in self.config_data.get("devices", []):
            if d["name"] == last:
                self.device_combo.set(last)
                self.load_selected_device()
                break

    # =========================
    # Core Logic
    # =========================

    def start_connection_monitor(self):
        if self.connection_monitor_running:
            return

        self.connection_monitor_running = True
        self.connection_monitor_failures = 0
        self.connection_monitor_suspended = False

        self.connection_monitor_thread = threading.Thread(
            target=self._connection_monitor_loop,
            daemon=True
        )
        self.connection_monitor_thread.start()

    def stop_connection_monitor(self):
        self.connection_monitor_running = False

    def suspend_connection_monitor(self):
        self.connection_monitor_suspended = True

    def resume_connection_monitor(self):
        if self.connection.connected:
            self.connection_monitor_failures = 0
            self.connection_monitor_suspended = False

    def _connection_monitor_loop(self):
        while self.connection_monitor_running:
            time.sleep(4)

            if not self.connection_monitor_running:
                break

            if self.connection_monitor_suspended:
                continue

            if not self.connection.connected or not self.connection.ip:
                break

            ip = self.connection.ip

            try:
                test_sock = socket.create_connection((ip, 22), timeout=1.5)
                test_sock.close()
                self.connection_monitor_failures = 0
            except Exception:
                self.connection_monitor_failures += 1

                if self.connection_monitor_failures >= 3:
                    self.connection_monitor_running = False
                    self.root.after(0, self.handle_connection_lost)
                    break

    def handle_connection_lost(self):
        try:
            if self.connection.client:
                self.connection.client.close()
        except Exception:
            pass

        self.connection.client = None
        self.connection.connected = False
        self.connection.ip = None
        self.connection.username = None
        self.connection.password = None

        self.update_all_installed = False
        self.update_all_initialized = False

        self.set_status("DISCONNECTED")
        self.status_label.config(
            text="Disconnected, MiSTer no longer reachable",
            foreground="red"
        )

        self.enable_connection_fields()
        self.disable_controls()

        self.connect_button.config(state="normal")
        self.disconnect_button.config(state="disabled")
        self.scan_button.config(state="normal")

        self.update_wallpaper_tab_state()

    def set_mister_settings_enabled(self, enabled):

        combo_state = "readonly" if enabled else "disabled"
        radio_state = "normal" if enabled else "disabled"

        # Mode selector
        self.easy_mode_radio.config(state=radio_state)
        self.advanced_mode_radio.config(state=radio_state)

        # Easy mode controls
        self.easy_hdmi_mode_combo.config(state=combo_state)
        self.easy_resolution_combo.config(state=combo_state if enabled else "disabled")
        self.easy_scaling_combo.config(state=combo_state)
        self.easy_hdmi_audio_combo.config(state=combo_state)
        self.easy_hdr_combo.config(state=combo_state)
        self.easy_hdmi_limited_combo.config(state=combo_state)
        self.easy_analogue_combo.config(state=combo_state)
        self.easy_logo_combo.config(state=combo_state)
        
        # Advanced editor
        if enabled:
            self.advanced_text.config(state="normal")
        else:
            self.advanced_text.config(state="disabled")

        # Grey/black text depending on connection
        if enabled:
            self.mister_settings_info.config(foreground="black")
            self.mister_settings_retention_label.config(foreground="black")
        else:
            self.mister_settings_info.config(foreground="gray")
            self.mister_settings_retention_label.config(foreground="gray")

        # Apply HDMI mode logic
        if enabled:
            self.update_easy_mode_state()

    def populate_zapscripts(self):

        for widget in self.zapscripts_wrapper.winfo_children():
            widget.destroy()

        # ===== Launch Scripts =====

        launch_frame = ttk.LabelFrame(self.zapscripts_wrapper, text="Launch Scripts")
        launch_frame.pack(fill="x", pady=10)

        button_row = ttk.Frame(launch_frame)
        button_row.pack(pady=10)

        # ===== Run update_all =====
        run_update_button = ttk.Button(
            button_row,
            text="Run update_all",
            width=22,
            command=lambda: self.run_zaparoo_api("update_all")
        )
        run_update_button.pack(side="left", padx=6)

        if not getattr(self, "update_all_installed", False):
            run_update_button.config(state="disabled")

        # ===== Run migrate_sd =====
        run_migrate_button = ttk.Button(
            button_row,
            text="Run migrate_sd",
            width=22,
            command=lambda: self.run_zaparoo_api("migrate_sd")
        )
        run_migrate_button.pack(side="left", padx=6)

        if not getattr(self, "migrate_sd_installed", False):
            run_migrate_button.config(state="disabled")

        # ===== Run update_all_insertcoin =====
        run_insertcoin_button = ttk.Button(
            button_row,
            text="Run update_all_insertcoin",
            width=26,
            command=lambda: self.run_zaparoo_api("update_all_insertcoin")
        )
        run_insertcoin_button.pack(side="left", padx=6)

        # Check if script exists on MiSTer
        insertcoin_check = self.connection.run_command(
            "test -f /media/fat/Scripts/update_all_insertcoin.sh && echo EXISTS"
        )

        insertcoin_installed = "EXISTS" in (insertcoin_check or "")

        if not insertcoin_installed:
            run_insertcoin_button.config(state="disabled")

        # ===== Launch Misc =====

        misc_frame = ttk.LabelFrame(self.zapscripts_wrapper, text="Launch Misc.")
        misc_frame.pack(fill="x", pady=10)

        misc_buttons = ttk.Frame(misc_frame)
        misc_buttons.pack(pady=10)

        # Row 1
        row1 = ttk.Frame(misc_buttons)
        row1.pack(pady=5)

        ttk.Button(
            row1,
            text="Open Bluetooth Menu",
            width=24,
            command=lambda: self.send_zaparoo_input("**input.keyboard:{f11}")
        ).pack(side="left", padx=6)

        ttk.Button(
            row1,
            text="Open OSD Menu",
            width=24,
            command=lambda: self.send_zaparoo_input("**input.keyboard:{f12}")
        ).pack(side="left", padx=6)

        # Row 2
        row2 = ttk.Frame(misc_buttons)
        row2.pack(pady=5)

        ttk.Button(
            row2,
            text="Cycle Wallpaper",
            width=24,
            command=lambda: self.send_zaparoo_input("**input.keyboard:{f1}")
        ).pack(side="left", padx=6)

        ttk.Button(
            row2,
            text="Return to MiSTer Home",
            width=24,
            command=lambda: self.send_zaparoo_input("**stop")
        ).pack(side="left", padx=6)

    def run_zaparoo_api(self, script):

        if not self.connection.ip:
            messagebox.showerror("Error", "No MiSTer connected.")
            return

        ws_url = f"ws://{self.connection.ip}:7497/api/v0.1"

        payload = {
            "jsonrpc": "2.0",
            "method": "run",
            "params": f"**mister.script:{script}.sh",
            "id": 1
        }

        def worker():
            try:
                ws = create_connection(ws_url, timeout=5)

                ws.send(json.dumps(payload))

                response = ws.recv()
                print("Zaparoo response:", response)

                ws.close()

            except Exception as e:
                error_msg = str(e)
                self.root.after(
                    0,
                    lambda: messagebox.showerror("API Error", error_msg)
                )

        threading.Thread(target=worker, daemon=True).start()

    def send_zaparoo_input(self, command):

        if not self.connection.ip:
            messagebox.showerror("Error", "No MiSTer connected.")
            return

        ws_url = f"ws://{self.connection.ip}:7497/api/v0.1"

        payload = {
            "jsonrpc": "2.0",
            "method": "run",
            "params": command,
            "id": 1
        }

        def worker():
            try:
                ws = create_connection(ws_url, timeout=5)

                ws.send(json.dumps(payload))

                response = ws.recv()
                print("Zaparoo response:", response)

                ws.close()

            except Exception as e:
                error_msg = str(e)
                self.root.after(
                    0,
                    lambda: messagebox.showerror("API Error", error_msg)
                )

        threading.Thread(target=worker, daemon=True).start()

    def connect(self):
        ip = self.ip_entry.get().strip()
        username = self.username_entry.get().strip() or "root"
        password = self.password_entry.get().strip() or "1"

        self.set_status("CONNECTING")

        success, message = self.connection.connect(ip, username, password)

        if success:

            selected_device = self.device_combo.get()

            if selected_device:
                self.config_data["last_connected"] = selected_device
                save_config(self.config_data)

            self.set_status("CONNECTED")
            self.status_label.config(text=f"Connected ({ip})", foreground="green")

            self.disable_connection_fields()
            self.scan_button.config(state="disabled")
            self.connect_button.config(state="disabled")
            self.disconnect_button.config(state="normal")

            self.enable_controls()
            self.refresh_storage()
            self.check_services_status()
            self.update_wallpaper_tab_state()
            self.update_backup_count()
            self.load_mister_ini_into_ui(silent=True)

            self.start_connection_monitor()
        else:
            self.stop_connection_monitor()
            self.set_status("DISCONNECTED")
            self.disable_controls()
            self.enable_connection_fields()
            messagebox.showerror("Connection Error", message)

    def disconnect(self):

        self.stop_connection_monitor()

        if self.connection.client:
            try:
                self.connection.client.close()
            except:
                pass

        self.connection.client = None
        self.connection.connected = False
        self.connection.ip = None
        self.connection.username = None
        self.connection.password = None

        self.update_all_installed = False
        self.update_all_initialized = False

        self.set_status("DISCONNECTED")
        self.status_label.config(text="Disconnected", foreground="red")

        self.enable_connection_fields()
        self.disable_controls()

        self.connect_button.config(state="normal")
        self.disconnect_button.config(state="disabled")
        self.scan_button.config(state="normal")

        self.update_wallpaper_tab_state()

    def disable_connection_fields(self):
        self.ip_entry.config(state="disabled")
        self.username_entry.config(state="disabled")
        self.password_entry.config(state="disabled")

    def enable_connection_fields(self):
        self.ip_entry.config(state="normal")
        self.username_entry.config(state="normal")
        self.password_entry.config(state="normal")

    def enable_controls(self):
        self.run_button.config(state="normal")
        self.explorer_button.config(state="normal")
        self.reboot_button.config(state="normal")

        self.open_scripts_folder_button.config(state="normal")

        # Enable SaveManager
        self.enable_savemanager_buttons()

        # SaveManager text active color
        self.savemanager_info.config(foreground="black")
        self.backup_count_label.config(foreground="black")
        self.retention_label.config(foreground="black")

        # Enable MiSTer Settings
        self.mister_settings_save_button.config(state="normal")
        self.mister_settings_backup_button.config(state="normal")
        self.mister_settings_restore_button.config(state="normal")
        self.mister_settings_defaults_button.config(state="normal")
        self.mister_settings_retention_spin.config(state="normal")
        self.mister_settings_open_folder_button.config(state="normal")
        self.mister_settings_info.config(foreground="black")
        self.mister_settings_retention_label.config(foreground="black")

        self.set_mister_settings_enabled(True)

    def disable_controls(self):
        self.install_button.config(state="disabled")
        self.uninstall_button.config(state="disabled")
        self.run_button.config(state="disabled")
        self.configure_button.config(state="disabled")

        self.open_scripts_folder_button.config(state="disabled")
        
        self.enable_smb_button.config(state="disabled")
        self.disable_smb_button.config(state="disabled")
        self.explorer_button.config(state="disabled")
        self.reboot_button.config(state="disabled")

        # Disable SaveManager controls
        self.disable_savemanager_buttons()

        # SaveManager text inactive color
        self.savemanager_info.config(foreground="gray")
        self.backup_count_label.config(foreground="gray")
        self.retention_label.config(foreground="gray")

        # Disable MiSTer Settings
        self.mister_settings_save_button.config(state="disabled")
        self.mister_settings_backup_button.config(state="disabled")
        self.mister_settings_restore_button.config(state="disabled")
        self.mister_settings_defaults_button.config(state="disabled")
        self.mister_settings_retention_spin.config(state="disabled")
        self.mister_settings_open_folder_button.config(state="disabled")
        self.mister_settings_info.config(foreground="gray")
        self.mister_settings_retention_label.config(foreground="gray")

        self.set_mister_settings_enabled(False)

        # Disable script buttons
        self.install_zaparoo_button.config(state="disabled")
        self.run_zaparoo_button.config(state="disabled")
        self.uninstall_zaparoo_button.config(state="disabled")

        self.install_migrate_button.config(state="disabled")
        self.uninstall_migrate_button.config(state="disabled")

        self.install_cifs_button.config(state="disabled")
        self.configure_cifs_button.config(state="disabled")
        self.mount_cifs_button.config(state="disabled")
        self.unmount_cifs_button.config(state="disabled")
        self.remove_cifs_config_button.config(state="disabled")
        self.uninstall_cifs_button.config(state="disabled")

        # Reset storage UI
        self.storage_bar["value"] = 0
        self.storage_label.config(text="--")

        self.usb_bar["value"] = 0
        self.usb_label.config(text="--")

    def update_settings_mode(self):

        mode = self.mister_settings_mode_var.get()

        if mode == "easy":

            if self.connection.connected:
                self.apply_advanced_to_easy()

            self.advanced_frame.pack_forget()
            self.easy_frame.pack(fill="x", pady=(0, 10))

        else:

            if self.connection.connected:

                # Load full MiSTer.ini first
                if not self.advanced_text.get("1.0", "end").strip():
                    self.load_mister_ini_advanced()

                # Apply Easy Mode changes to the full file
                settings = self.build_easy_mode_settings()

                current_text = self.advanced_text.get("1.0", "end")

                updated_text = self.update_mister_ini_text(current_text, settings)

                self.advanced_text.delete("1.0", tk.END)
                self.advanced_text.insert("1.0", updated_text)

            self.easy_frame.pack_forget()
            self.advanced_frame.pack(fill="both", expand=True)

    def on_tab_changed(self, event=None):

        try:
            selected_tab = self.notebook.select()
            selected_text = self.notebook.tab(selected_tab, "text")
        except Exception:
            return

        if selected_text == "MiSTer Settings" and self.connection.connected:
            self.load_mister_ini_into_ui(silent=True)

        if selected_text == "Wallpapers" and self.connection.connected:
            threading.Thread(
                target=self.check_ranny_wallpapers,
                daemon=True
            ).start()

    def on_easy_hdmi_mode_changed(self, event=None):
        self.update_easy_mode_state()

    def update_easy_mode_state(self):

        hdmi_mode = self.easy_hdmi_mode_combo.get().strip()

        if hdmi_mode == "Direct Video (CRT / Scaler)":

            self.easy_resolution_combo.config(state="disabled")
            self.easy_scaling_combo.config(state="disabled")
            self.easy_hdr_combo.config(state="disabled")
            self.easy_hdmi_limited_combo.config(state="disabled")
            self.easy_logo_combo.config(state="disabled")

        else:

            self.easy_resolution_combo.config(state="readonly")
            self.easy_scaling_combo.config(state="readonly")
            self.easy_hdr_combo.config(state="readonly")
            self.easy_hdmi_limited_combo.config(state="readonly")
            self.easy_logo_combo.config(state="readonly")

    def set_status(self, state):
        colors = {
            "CONNECTED": "green",
            "CONNECTING": "orange",
            "REBOOTING": "blue",
            "DISCONNECTED": "red"
        }
        texts = {
            "CONNECTED": "Connected",
            "CONNECTING": "Connecting...",
            "REBOOTING": "Rebooting...",
            "DISCONNECTED": "Disconnected"
        }
        if state == "CONNECTED":
            self.status_label.config(foreground=colors[state])
        else:
            self.status_label.config(text=texts[state],
                                     foreground=colors[state])

    def on_connection_field_change(self, event=None):

        if self.connection.connected:
            return

        current_profile = self.device_combo.get()

        if not current_profile:
            return

        # Check if fields still match the profile
        for d in self.config_data.get("devices", []):
            if d["name"] == current_profile:

                saved_ip = d["ip"]
                saved_user = d["username"]
                saved_pass = decode_password(d["password"])

                if (
                        self.ip_entry.get().strip() != saved_ip
                        or self.username_entry.get().strip() != saved_user
                        or self.password_entry.get().strip() != saved_pass
                ):
                    self.device_combo.set("")
                return

    def refresh_storage(self):

        # SD card
        df = self.connection.run_command("df -h /media/fat | tail -1")

        if df:
            try:
                parts = df.split()
                size = parts[1]
                avail = parts[3]
                percent = int(parts[4].replace("%", ""))

                self.storage_bar["value"] = percent
                self.storage_label.config(
                    text=f"{avail} free of {size} ({percent}% used)"
                )

                if percent > 85:
                    self.storage_bar.configure(style="red.Horizontal.TProgressbar")
                elif percent > 70:
                    self.storage_bar.configure(style="orange.Horizontal.TProgressbar")
                else:
                    self.storage_bar.configure(style="green.Horizontal.TProgressbar")

            except Exception:
                pass

        # USB storage
        usb = self.connection.run_command("df -h | grep /media/usb")

        if usb:

            try:
                line = usb.splitlines()[0]
                parts = line.split()

                size = parts[1]
                avail = parts[3]
                percent = int(parts[4].replace("%", ""))

                self.usb_bar["value"] = percent
                self.usb_label.config(
                    text=f"{avail} free of {size} ({percent}% used)"
                )

                if percent > 85:
                    self.usb_bar.configure(style="red.Horizontal.TProgressbar")
                elif percent > 70:
                    self.usb_bar.configure(style="orange.Horizontal.TProgressbar")
                else:
                    self.usb_bar.configure(style="green.Horizontal.TProgressbar")

            except Exception:
                self.usb_label.config(text="USB detected (unable to read usage)")

        else:
            self.usb_bar["value"] = 0
            self.usb_label.config(text="No USB storage detected")

    def check_services_status(self):
        update_check = self.connection.run_command(
            "test -f /media/fat/Scripts/update_all.sh && echo EXISTS"
        )

        update_installed = "EXISTS" in (update_check or "")
        self.update_all_installed = update_installed

        if update_installed:
            self.update_status_label.config(
                text="update_all: Installed ✓",
                foreground="green"
            )
        else:
            self.update_status_label.config(
                text="update_all: Not Installed",
                foreground="red"
            )

        smb_check = self.connection.run_command(
            "test -f /media/fat/linux/samba.sh && echo EXISTS"
        )

        smb_enabled = "EXISTS" in (smb_check or "")

        if smb_enabled:
            self.smb_status_label.config(
                text="SMB: Enabled ✓",
                foreground="green"
            )
        else:
            self.smb_status_label.config(
                text="SMB: Disabled",
                foreground="red"
            )

        self.update_button_states(update_installed, smb_enabled)

        # ===== migrate_sd -detection =====

        migrate_check = self.connection.run_command(
            "test -f /media/fat/Scripts/migrate_sd.sh && echo EXISTS"
        )

        migrate_installed = "EXISTS" in (migrate_check or "")
        self.migrate_sd_installed = migrate_installed

        if migrate_installed:

            self.migrate_status_label.config(
                text="migrate_sd: Installed ✓",
                foreground="green"
            )

            self.install_migrate_button.config(state="disabled")
            self.uninstall_migrate_button.config(state="normal")

        else:

            self.migrate_status_label.config(
                text="migrate_sd: Not Installed",
                foreground="red"
            )

            self.install_migrate_button.config(state="normal")
            self.uninstall_migrate_button.config(state="disabled")

        # ===== Zaparoo detection =====

        zaparoo_check = self.connection.run_command(
            "test -f /media/fat/Scripts/zaparoo.sh && echo EXISTS"
        )

        zaparoo_installed = "EXISTS" in (zaparoo_check or "")

        service_check = self.connection.run_command(
            "grep 'mrext/zaparoo' /media/fat/linux/user-startup.sh 2>/dev/null"
        )

        service_enabled = service_check and "mrext/zaparoo" in service_check

        if not zaparoo_installed:

            self.zaparoo_status_label.config(
                text="Zaparoo: Not Installed",
                foreground="red"
            )

            self.install_zaparoo_button.config(state="normal")
            self.run_zaparoo_button.config(state="disabled")
            self.uninstall_zaparoo_button.config(state="disabled")

            for widget in self.zapscripts_wrapper.winfo_children():
                widget.destroy()

            ttk.Label(
                self.zapscripts_wrapper,
                text="ZapScripts require Zaparoo to be installed.\n\nPlease install Zaparoo from the Scripts tab.",
                foreground="red",
                justify="center"
            ).pack(pady=40)


        elif zaparoo_installed and not service_enabled:

            self.zaparoo_status_label.config(
                text="Zaparoo: Installed (Service Disabled)",
                foreground="orange"
            )

            self.install_zaparoo_button.config(state="disabled")
            self.run_zaparoo_button.config(state="normal")
            self.uninstall_zaparoo_button.config(state="normal")

            for widget in self.zapscripts_wrapper.winfo_children():
                widget.destroy()

            ttk.Label(
                self.zapscripts_wrapper,
                text="Zaparoo is installed but the boot service is not enabled.\n\nClick 'Enable Zaparoo Service' in the Scripts tab.",
                foreground="orange",
                justify="center"
            ).pack(pady=40)


        else:

            self.zaparoo_status_label.config(
                text="Zaparoo: Installed ✓",
                foreground="green"
            )

            self.install_zaparoo_button.config(state="disabled")
            self.run_zaparoo_button.config(state="disabled")
            self.uninstall_zaparoo_button.config(state="normal")

            self.populate_zapscripts()

        # ===== CIFS detection =====

        cifs_script_check = self.connection.run_command(
            "test -f /media/fat/Scripts/cifs_mount.sh && echo EXISTS"
        )

        cifs_ini_check = self.connection.run_command(
            "test -f /media/fat/Scripts/cifs_mount.ini && echo CONFIG"
        )

        script_installed = "EXISTS" in (cifs_script_check or "")
        ini_present = "CONFIG" in (cifs_ini_check or "")

        if not script_installed:

            self.cifs_status_label.config(
                text="cifs_mount: Not Installed",
                foreground="red"
            )

            self.install_cifs_button.config(state="normal")
            self.configure_cifs_button.config(state="disabled")
            self.mount_cifs_button.config(state="disabled")
            self.unmount_cifs_button.config(state="disabled")
            self.remove_cifs_config_button.config(state="disabled")
            self.uninstall_cifs_button.config(state="disabled")

        elif script_installed and not ini_present:

            self.cifs_status_label.config(
                text="cifs_mount: Installed (Not Configured)",
                foreground="orange"
            )

            self.install_cifs_button.config(state="disabled")
            self.configure_cifs_button.config(text="Configure", state="normal")
            self.mount_cifs_button.config(state="disabled")
            self.unmount_cifs_button.config(state="disabled")
            self.remove_cifs_config_button.config(state="disabled")
            self.uninstall_cifs_button.config(state="normal")

        else:

            self.cifs_status_label.config(
                text="cifs_mount: Configured ✓",
                foreground="green"
            )

            self.install_cifs_button.config(state="disabled")
            self.configure_cifs_button.config(text="Reconfigure", state="normal")
            self.mount_cifs_button.config(state="normal")
            self.unmount_cifs_button.config(state="normal")
            self.remove_cifs_config_button.config(state="normal")
            self.uninstall_cifs_button.config(state="normal")

    def check_update_all_initialized(self):
        if not self.connection.connected:
            return False

        try:
            sftp = self.connection.client.open_sftp()
            sftp.stat("/media/fat/Scripts/.config/update_all/update_all.json")
            sftp.close()
            return True
        except Exception:
            return False

    def update_button_states(self, update_installed=False, smb_enabled=False):

        # Track install / init state
        self.update_all_installed = update_installed
        self.update_all_initialized = (
            self.check_update_all_initialized() if update_installed else False
        )

        # =========================
        # update_all buttons
        # =========================

        if not self.connection.connected:
            self.install_button.config(state="disabled")
            self.uninstall_button.config(state="disabled")
            self.run_button.config(state="disabled")
            self.configure_button.config(state="disabled")

        else:
            if update_installed:
                self.install_button.config(state="disabled")
                self.uninstall_button.config(state="normal")
                self.run_button.config(state="normal")

                self.configure_button.config(state="normal")
            else:
                self.install_button.config(state="normal")
                self.uninstall_button.config(state="disabled")
                self.run_button.config(state="disabled")
                self.configure_button.config(state="disabled")

        # =========================
        # SMB buttons
        # =========================

        if smb_enabled:
            self.enable_smb_button.config(state="disabled")
            self.disable_smb_button.config(state="normal")
        else:
            self.enable_smb_button.config(state="normal")
            self.disable_smb_button.config(state="disabled")

    def uninstall_update_all(self):
        if not self.connection.connected:
            return

        if messagebox.askyesno("Uninstall update_all",
                               "Are you sure you want to remove update_all?"):
            self.connection.run_command(
                "rm -f /media/fat/Scripts/update_all.sh"
            )
            self.check_services_status()

    def uninstall_zaparoo(self):

        if not self.connection.connected:
            return

        if messagebox.askyesno(
                "Uninstall Zaparoo",
                "Are you sure you want to remove Zaparoo?"
        ):
            self.connection.run_command(
                "rm -f /media/fat/Scripts/zaparoo.sh"
            )

            self.connection.run_command(
                "rm -rf /media/fat/zaparoo"
            )

            self.check_services_status()

    def uninstall_migrate_sd(self):

        if not self.connection.connected:
            return

        if messagebox.askyesno(
                "Uninstall migrate_sd",
                "Are you sure you want to remove migrate_sd?"
        ):
            self.connection.run_command(
                "rm -f /media/fat/Scripts/migrate_sd.sh"
            )

            self.log("migrate_sd removed.\n")
            self.check_services_status()

    def disable_smb(self):
        if not self.connection.connected:
            return

        self.connection.run_command(
            "if [ -f /media/fat/linux/samba.sh ]; then mv /media/fat/linux/samba.sh /media/fat/linux/_samba.sh; fi"
        )

        if messagebox.askyesno("SMB Disabled",
                               "SMB has been disabled.\n\nA reboot is required.\n\nReboot now?"):
            self.reboot()

        self.check_services_status()

    def toggle_console(self):
        if self.console_visible:
            self.console_frame.pack_forget()
            self.console_visible = False
        else:
            self.console_frame.pack(fill="x", padx=20, pady=10)
            self.console_visible = True

    def load_cifs_config(self):

        config = {}

        try:
            output = self.connection.run_command(
                "cat /media/fat/Scripts/cifs_mount.ini"
            )

            if not output:
                return config

            for line in output.splitlines():

                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                config[key.strip()] = value.strip().strip('"')

        except Exception:
            pass

        return config

    def configure_cifs(self):

            popup = tk.Toplevel(self.root)
            popup.title("Configure CIFS Mount")
            popup.geometry("360x360")
            popup.resizable(False, False)

            frame = ttk.Frame(popup, padding=15)
            frame.pack(fill="both", expand=True)

            ttk.Label(frame, text="Server IP").pack(anchor="w")
            server_entry = ttk.Entry(frame)
            server_entry.pack(fill="x", pady=3)

            ttk.Label(frame, text="Share Name").pack(anchor="w")
            share_entry = ttk.Entry(frame)
            share_entry.pack(fill="x", pady=3)

            ttk.Label(frame, text="Username").pack(anchor="w")
            user_entry = ttk.Entry(frame)
            user_entry.pack(fill="x", pady=3)

            ttk.Label(frame, text="Password").pack(anchor="w")
            pass_entry = ttk.Entry(frame, show="*")
            pass_entry.pack(fill="x", pady=3)

            boot_var = tk.BooleanVar(value=True)

            ttk.Checkbutton(
                frame,
                text="Mount at boot",
                variable=boot_var
            ).pack(anchor="w", pady=(8, 5))

            # ===== Load existing config =====

            config = self.load_cifs_config()

            if "SERVER" in config:
                server_entry.insert(0, config["SERVER"])

            if "SHARE" in config:
                share_entry.insert(0, config["SHARE"])

            if "USERNAME" in config:
                user_entry.insert(0, config["USERNAME"])

            if "PASSWORD" in config:
                pass_entry.insert(0, config["PASSWORD"])

            if config.get("MOUNT_AT_BOOT") == "false":
                boot_var.set(False)

            # ===== Test connection =====

            def test_connection():

                server = server_entry.get().strip()
                share = share_entry.get().strip()
                username = user_entry.get().strip()
                password = pass_entry.get().strip()

                if not server or not share:
                    messagebox.showerror(
                        "Missing Information",
                        "Server IP and Share Name are required."
                    )
                    return

                test_cmd = f'mount -t cifs //{server}/{share} /tmp/cifs_test -o username="{username}",password="{password}"'

                result = self.connection.run_command(
                    f'mkdir -p /tmp/cifs_test && {test_cmd} && umount /tmp/cifs_test && echo SUCCESS'
                )

                if result and "SUCCESS" in result:
                    messagebox.showinfo("Success", "Connection successful.")
                else:
                    messagebox.showerror(
                        "Connection Failed",
                        "Unable to connect to the network share."
                    )

            # ===== Save config =====

            def save_cifs_config():

                server = server_entry.get().strip()
                share = share_entry.get().strip()
                username = user_entry.get().strip()
                password = pass_entry.get().strip()

                if not server:
                    messagebox.showerror("Missing Information", "Server IP is required.")
                    return

                if not share:
                    messagebox.showerror("Missing Information", "Share name is required.")
                    return

                ini = f'''SERVER="{server}"
    SHARE="{share}"
    USERNAME="{username}"
    PASSWORD="{password}"
    LOCAL_DIR="cifs/games"
    WAIT_FOR_SERVER="true"
    MOUNT_AT_BOOT="{str(boot_var.get()).lower()}"
    SINGLE_CIFS_CONNECTION="true"
    '''

                try:

                    sftp = self.connection.client.open_sftp()

                    with sftp.open("/media/fat/Scripts/cifs_mount.ini", "w") as f:
                        f.write(ini)

                    sftp.close()

                    self.check_services_status()

                    popup.destroy()

                except Exception as e:
                    messagebox.showerror("Error", str(e))

            # ===== Buttons =====

            button_row = ttk.Frame(frame)
            button_row.pack(pady=12)

            ttk.Button(
                button_row,
                text="Test Connection",
                width=16,
                command=test_connection
            ).pack(side="left", padx=6)

            ttk.Button(
                button_row,
                text="Save",
                width=10,
                command=save_cifs_config
            ).pack(side="left", padx=6)

    # ===== Thread-safe logging =====

    def log(self, text):
        self.root.after(0, lambda: self._log_ui(text))

    def _log_ui(self, text):
        self.console.insert(tk.END, text)
        self.console.see(tk.END)

    def run_update_all(self):

        if not self.connection.connected:
            return

        proceed = messagebox.askyesno(
            "Run update_all",
            "update_all will run through SSH.\n\n"
            "The output will NOT appear on the MiSTer TV screen.\n"
            "It will only be visible inside MiSTer Companion.\n\n"
            "If you want the output to appear on the TV screen, run update_all from:\n"
            "• ZapScripts in MiSTer Companion\n"
            "• The Scripts menu on the MiSTer itself\n\n"
            "Continue?"
        )

        if not proceed:
            return

        if not self.console_visible:
            self.console_frame.pack(fill="x", padx=20, pady=10)
            self.console_visible = True

        self.console.delete("1.0", tk.END)
        self.log("Running update_all...\n\n")

        def worker():
            self.connection.run_command_stream(
                "/media/fat/Scripts/update_all.sh",
                self.log
            )

            self.log("\nupdate_all finished.\n")

            # Refresh install/init/button state after completion
            self.root.after(0, self.check_services_status)

        threading.Thread(target=worker, daemon=True).start()

    def run_zaparoo(self):

        if not self.connection.connected:
            return

        confirm = messagebox.askyesno(
            "Enable Zaparoo Service",
            "This will enable the Zaparoo service so it starts automatically on boot.\n\nContinue?"
        )

        if not confirm:
            return

        try:

            # Check if user-startup.sh exists
            exists = self.connection.run_command(
                "test -f /media/fat/linux/user-startup.sh && echo EXISTS"
            )

            if "EXISTS" not in (exists or ""):

                # Create full startup file
                script = """#!/bin/sh

    # mrext/zaparoo
    [[ -e /media/fat/Scripts/zaparoo.sh ]] && /media/fat/Scripts/zaparoo.sh -service $1
    """

                sftp = self.connection.client.open_sftp()

                with sftp.open("/media/fat/linux/user-startup.sh", "w") as f:
                    f.write(script)

                sftp.close()

            else:

                # Check if zaparoo already configured
                check = self.connection.run_command(
                    "grep 'mrext/zaparoo' /media/fat/linux/user-startup.sh"
                )

                if not check:
                    self.connection.run_command(
                        'echo "" >> /media/fat/linux/user-startup.sh'
                    )

                    self.connection.run_command(
                        'echo "# mrext/zaparoo" >> /media/fat/linux/user-startup.sh'
                    )

                    self.connection.run_command(
                        'echo "[[ -e /media/fat/Scripts/zaparoo.sh ]] && /media/fat/Scripts/zaparoo.sh -service $1" >> /media/fat/linux/user-startup.sh'
                    )

            messagebox.showinfo(
                "Zaparoo Enabled",
                "Zaparoo service enabled.\n\nPlease reboot your MiSTer."
            )

            self.check_services_status()

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def install_update_all(self):
        if not self.connection.connected:
            return

        if not self.console_visible:
            self.console_frame.pack(fill="x", padx=20, pady=10)
            self.console_visible = True

        self.console.delete("1.0", tk.END)
        self.log("Installing update_all...\n")

        def worker():
            try:
                api_url = "https://api.github.com/repos/theypsilon/Update_All_MiSTer/releases/latest"
                r = requests.get(api_url, timeout=10)
                data = r.json()

                download_url = None
                for asset in data.get("assets", []):
                    if asset["name"].endswith(".sh"):
                        download_url = asset["browser_download_url"]
                        break

                if not download_url:
                    self.log("Could not find update_all script.\n")
                    return

                file_data = requests.get(download_url).content

                sftp = self.connection.client.open_sftp()
                try:
                    sftp.mkdir("/media/fat/Scripts")
                except IOError:
                    pass

                with sftp.open("/media/fat/Scripts/update_all.sh", "wb") as f:
                    f.write(file_data)

                sftp.close()

                self.connection.run_command("chmod +x /media/fat/Scripts/update_all.sh")
                self.log("Installation complete.\n")
                self.check_services_status()

            except Exception as e:
                self.log(f"ERROR: {str(e)}\n")

        threading.Thread(target=worker).start()

    def install_zaparoo(self):

        if not self.connection.connected:
            return

        if not self.console_visible:
            self.console_frame.pack(fill="x", padx=20, pady=10)
            self.console_visible = True

        self.console.delete("1.0", tk.END)
        self.log("Installing Zaparoo...\n")

        def worker():
            try:

                api_url = "https://api.github.com/repos/ZaparooProject/zaparoo-core/releases/latest"
                r = requests.get(api_url, timeout=10)
                data = r.json()

                download_url = None
                asset_name = None

                for asset in data.get("assets", []):
                    name = asset["name"].lower()

                    if "mister_arm" in name and name.endswith(".zip"):
                        download_url = asset["browser_download_url"]
                        asset_name = asset["name"]
                        break

                if not download_url:
                    self.log("Could not find MiSTer Zaparoo release.\n")
                    return

                self.log(f"Found release: {asset_name}\n")
                self.log("Downloading release...\n")

                zip_data = requests.get(download_url).content

                import zipfile
                from io import BytesIO

                zip_file = zipfile.ZipFile(BytesIO(zip_data))

                sftp = self.connection.client.open_sftp()

                try:
                    sftp.mkdir("/media/fat/Scripts")
                except IOError:
                    pass

                for file in zip_file.namelist():

                    if file.endswith("zaparoo.sh"):
                        self.log("Uploading zaparoo.sh\n")

                        file_data = zip_file.read(file)

                        with sftp.open("/media/fat/Scripts/zaparoo.sh", "wb") as remote_file:
                            remote_file.write(file_data)

                        break

                sftp.close()

                self.connection.run_command(
                    "chmod +x /media/fat/Scripts/zaparoo.sh"
                )

                self.log("Zaparoo installation complete.\n")
                self.log("Next step: Enable the Zaparoo service from the Scripts tab.\n")

                self.root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Zaparoo Installed",
                        "Zaparoo has been installed successfully.\n\n"
                        "Next step:\n"
                        "Click 'Enable Zaparoo Service' to start Zaparoo automatically at boot."
                    )
                )

                self.check_services_status()

            except Exception as e:
                self.log(f"ERROR: {str(e)}\n")

        threading.Thread(target=worker).start()

    def install_migrate_sd(self):

        if not self.connection.connected:
            return

        proceed = messagebox.askyesno(
            "Install migrate_sd",
            "This tool installs the 'migrate_sd' script on your MiSTer.\n\n"
            "Important:\n"
            "The migration process MUST be started directly on the MiSTer\n"
            "from the Scripts menu.\n\n"
            "Or Run it from the ZapScripts Tab.\n\n"
            "Install the script now?"
        )

        if not proceed:
            return

        if not self.console_visible:
            self.console_frame.pack(fill="x", padx=20, pady=10)
            self.console_visible = True

        self.console.delete("1.0", tk.END)
        self.log("Installing migrate_sd...\n")

        def worker():

            try:

                url = "https://raw.githubusercontent.com/Natrox/MiSTer_Utils_Natrox/main/scripts/migrate_sd.sh"

                script_data = requests.get(url).content

                sftp = self.connection.client.open_sftp()

                try:
                    sftp.mkdir("/media/fat/Scripts")
                except IOError:
                    pass

                with sftp.open("/media/fat/Scripts/migrate_sd.sh", "wb") as f:
                    f.write(script_data)

                sftp.close()

                self.connection.run_command(
                    "chmod +x /media/fat/Scripts/migrate_sd.sh"
                )

                self.log("migrate_sd installed successfully.\n")
                self.log("Run it from the MiSTer Scripts menu.\n")
                self.check_services_status()

            except Exception as e:
                self.log(f"ERROR: {str(e)}\n")

        threading.Thread(target=worker).start()

    def install_cifs_mount(self):

        if not self.connection.connected:
            return

        if not self.console_visible:
            self.console_frame.pack(fill="x", padx=20, pady=10)
            self.console_visible = True

        self.console.delete("1.0", tk.END)
        self.log("Installing cifs_mount scripts...\n")

        def worker():

            try:

                base = "https://raw.githubusercontent.com/MiSTer-devel/Scripts_MiSTer/master/"

                mount_script = requests.get(base + "cifs_mount.sh").content
                umount_script = requests.get(base + "cifs_umount.sh").content

                sftp = self.connection.client.open_sftp()

                try:
                    sftp.mkdir("/media/fat/Scripts")
                except IOError:
                    pass

                with sftp.open("/media/fat/Scripts/cifs_mount.sh", "wb") as f:
                    f.write(mount_script)

                with sftp.open("/media/fat/Scripts/cifs_umount.sh", "wb") as f:
                    f.write(umount_script)

                sftp.close()

                self.connection.run_command("chmod +x /media/fat/Scripts/cifs_mount.sh")
                self.connection.run_command("chmod +x /media/fat/Scripts/cifs_umount.sh")

                self.log("CIFS scripts installed.\n")

                self.check_services_status()

            except Exception as e:
                self.log(f"ERROR: {str(e)}\n")

        threading.Thread(target=worker).start()

    def run_cifs_mount(self):

        if not self.connection.connected:
            return

        self.connection.run_command("/media/fat/Scripts/cifs_mount.sh")

    def run_cifs_umount(self):

        if not self.connection.connected:
            return

        self.connection.run_command("/media/fat/Scripts/cifs_umount.sh")

    def remove_cifs_config(self):

        if not self.connection.connected:
            return

        if messagebox.askyesno("Remove Config", "Delete CIFS configuration?"):
            self.connection.run_command(
                "rm -f /media/fat/Scripts/cifs_mount.ini"
            )

            self.check_services_status()

    def uninstall_cifs_mount(self):

        if not self.connection.connected:
            return

        if messagebox.askyesno("Uninstall", "Remove CIFS scripts?"):
            self.connection.run_command(
                "rm -f /media/fat/Scripts/cifs_mount.sh"
            )

            self.connection.run_command(
                "rm -f /media/fat/Scripts/cifs_umount.sh"
            )

            self.check_services_status()
        
    def enable_smb(self):
        self.connection.run_command(
            "if [ -f /media/fat/linux/_samba.sh ]; then mv /media/fat/linux/_samba.sh /media/fat/linux/samba.sh; fi"
        )

        if messagebox.askyesno("SMB Enabled",
                               "SMB has been enabled.\n\nA reboot is required.\n\nReboot now?"):
            self.reboot()

        self.check_services_status()

    def open_explorer(self):

        if not self.connection.ip:
            return

        ip = self.connection.ip

        try:

            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", f"\\\\{ip}\\"])

            elif sys.platform.startswith("linux"):

                env = os.environ.copy()

                # Force mount first
                subprocess.run(
                    ["gio", "mount", f"smb://{ip}/"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                # Then open
                subprocess.Popen(
                    ["gio", "open", f"smb://{ip}/"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            elif sys.platform == "darwin":
                subprocess.Popen(["open", f"smb://{ip}/"])

        except Exception as e:
            messagebox.showerror(
                "SMB Error",
                f"Unable to open SMB share:\n\n{str(e)}"
            )

    def open_network_scanner(self):

        popup = tk.Toplevel(self.root)
        popup.title("Scan Network for MiSTer")
        popup.geometry("420x360")
        popup.resizable(False, False)
        popup.transient(self.root)

        frame = ttk.Frame(popup, padding=10)
        frame.pack(fill="both", expand=True)

        listbox = tk.Listbox(frame)
        listbox.pack(fill="both", expand=True, pady=10)

        status = ttk.Label(frame, text="Idle")
        status.pack(pady=(0, 10))

        select_button = ttk.Button(frame, text="Use Selected IP", state="disabled")
        select_button.pack()

        found_ips = []

        # ---------------------------------

        def get_local_subnets():

            subnets = []
            interfaces = psutil.net_if_addrs()

            for interface_name, addresses in interfaces.items():

                lowered = interface_name.lower()

                if any(v in lowered for v in [
                    "vpn", "docker", "virtual", "vmware", "loopback", "hamachi", "tailscale"
                ]):
                    continue

                for addr in addresses:
                    if addr.family == socket.AF_INET:

                        ip = addr.address

                        if ip.startswith("127."):
                            continue

                        parts = ip.split(".")
                        if len(parts) != 4:
                            continue

                        subnet = ".".join(parts[:3])
                        subnets.append(subnet)

            return list(set(subnets))

        # ---------------------------------

        def is_port_open(ip, port=22):

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.35)
                result = sock.connect_ex((ip, port))
                sock.close()
                return result == 0
            except Exception:
                return False

        # ---------------------------------

        def verify_mister(ip):

            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                ssh.connect(
                    ip,
                    username="root",
                    password="1",
                    timeout=0.5,
                    banner_timeout=0.5,
                    auth_timeout=0.5
                )

                stdin, stdout, stderr = ssh.exec_command("test -d /media/fat && echo OK")
                result = stdout.read().decode().strip()

                ssh.close()

                if result == "OK":

                    def add_result():
                        if not popup.winfo_exists():
                            return
                        if ip not in found_ips:
                            found_ips.append(ip)
                            listbox.insert(tk.END, ip)

                    self.root.after(0, add_result)

            except Exception:
                pass

        # ---------------------------------

        def check_device(ip):
            if is_port_open(ip):
                verify_mister(ip)

        # ---------------------------------

        def scan_network():

            try:
                subnets = get_local_subnets()

                if not subnets:
                    self.root.after(
                        0,
                        lambda: status.winfo_exists() and status.config(text="No valid network detected")
                    )
                    return

                self.root.after(
                    0,
                    lambda: status.winfo_exists() and status.config(text="Scanning network...")
                )

                threads = []

                for subnet in subnets:
                    for i in range(1, 255):
                        ip = f"{subnet}.{i}"

                        t = threading.Thread(target=check_device, args=(ip,), daemon=True)
                        t.start()
                        threads.append(t)

                for t in threads:
                    t.join()

                def finish_scan():
                    if not popup.winfo_exists():
                        return
                    if found_ips:
                        status.config(text=f"Scan complete, found {len(found_ips)} device(s)")
                    else:
                        status.config(text="Scan complete, no MiSTer found")

                self.root.after(0, finish_scan)

            except Exception as e:
                self.root.after(
                    0,
                    lambda: status.winfo_exists() and status.config(text=f"Scan failed: {str(e)}")
                )

        # ---------------------------------

        def start_scan():

            if not popup.winfo_exists():
                return

            listbox.delete(0, tk.END)
            found_ips.clear()
            select_button.config(state="disabled")
            status.config(text="Starting scan...")

            threading.Thread(target=scan_network, daemon=True).start()

        # ---------------------------------

        def on_select(event=None):

            if not listbox.curselection():
                select_button.config(state="disabled")
                return

            select_button.config(state="normal")

        listbox.bind("<<ListboxSelect>>", on_select)

        # ---------------------------------

        def use_selected():

            if not listbox.curselection():
                return

            ip = listbox.get(listbox.curselection()[0])

            self.ip_entry.delete(0, tk.END)
            self.ip_entry.insert(0, ip)

            # Unload current saved profile when scanned IP is chosen
            self.device_combo.set("")

            popup.destroy()

        select_button.config(command=use_selected)

        popup.update_idletasks()
        popup.after(200, start_scan)

    def reboot(self):

        if not self.connection.connected:
            return

        ip = self.connection.ip
        username = self.connection.username
        password = self.connection.password

        self.set_status("REBOOTING")

        self.connection.reboot()

        threading.Thread(
            target=self._wait_for_reboot,
            args=(ip, username, password),
            daemon=True
        ).start()

    def _wait_for_reboot(self, ip, username, password):

        # give MiSTer time to shut down
        time.sleep(10)

        for _ in range(30):  # try for ~60 seconds

            try:
                test = paramiko.SSHClient()
                test.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                test.connect(
                    hostname=ip,
                    username=username,
                    password=password,
                    timeout=3
                )

                test.close()

                # reconnect through the normal method
                self.root.after(0, self.connect)

                return

            except Exception:
                time.sleep(2)

        # failed to reconnect
        self.root.after(0, lambda: self.set_status("DISCONNECTED"))

    # =========================
    # SaveManager Functions
    # =========================

    def save_retention_setting(self):

        try:
            value = int(self.retention_var.get())

            if value < 1:
                value = 1

            self.config_data["backup_retention"] = value
            save_config(self.config_data)

        except Exception:
            pass

    def save_mister_settings_retention_setting(self):

        try:
            value = int(self.mister_settings_retention_var.get())

            if value < 1:
                value = 1

            self.config_data["mister_settings_retention"] = value
            save_config(self.config_data)

        except Exception:
            pass

    def get_mister_settings_device_name(self):

        device_name = self.device_combo.get().strip()

        if device_name:
            return device_name

        if self.connection.ip:
            return self.connection.ip.replace(".", "_")

        return ""

    def get_mister_settings_device_path(self):

        device_name = self.get_mister_settings_device_name()

        if not device_name:
            return os.path.abspath(MISTER_SETTINGS_ROOT)

        return os.path.abspath(os.path.join(MISTER_SETTINGS_ROOT, device_name))

    def ensure_mister_ini_exists(self):

        if not self.connection.connected:
            return False, "Not connected"

        ini_exists = self.connection.run_command(
            'test -f /media/fat/MiSTer.ini && echo EXISTS'
        )

        if "EXISTS" in (ini_exists or ""):
            return True, "MiSTer.ini exists"

        example_exists = self.connection.run_command(
            'test -f /media/fat/MiSTer_example.ini && echo EXISTS'
        )

        if "EXISTS" not in (example_exists or ""):
            return False, "Neither MiSTer.ini nor MiSTer_example.ini exists."

        result = self.connection.run_command(
            'cp /media/fat/MiSTer_example.ini /media/fat/MiSTer.ini && echo COPIED'
        )

        if "COPIED" in (result or ""):
            return True, "MiSTer.ini created from MiSTer_example.ini"

        return False, "Unable to create MiSTer.ini from MiSTer_example.ini"

    def parse_mister_ini(self, text):

        settings = {}

        current_section = None

        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line:
                continue

            if line.startswith(";"):
                continue

            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip()
                continue

            if current_section != "MiSTer":
                continue

            if ";" in line:
                line = line.split(";", 1)[0].strip()

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            settings[key.strip()] = value.strip()

        return settings

    def apply_advanced_to_easy(self):

        text = self.advanced_text.get("1.0", tk.END)

        settings = {}

        for line in text.splitlines():

            line = line.strip()

            if not line:
                continue

            if line.startswith(";"):
                continue

            if "=" not in line:
                continue

            key, value = line.split("=", 1)

            settings[key.strip()] = value.strip()

        self.map_ini_to_easy_mode(settings)

    def map_ini_to_easy_mode(self, settings):

        # HDMI Mode
        direct_video = settings.get("direct_video", "0").strip()
        if direct_video in ("1", "2"):
            self.easy_hdmi_mode_combo.set("Direct Video (CRT / Scaler)")
        else:
            self.easy_hdmi_mode_combo.set("HD Output (Default)")

        # Resolution
        video_mode = settings.get("video_mode", "").strip()

        resolution_map = {
            "0": "1280x720@60",
            "1": "1024x768@60",
            "2": "720x480@60",
            "3": "720x576@50",
            "4": "1280x1024@60",
            "5": "800x600@60",
            "6": "640x480@60",
            "7": "1280x720@50",
            "8": "1920x1080@60",
            "9": "1920x1080@50",
            "10": "1366x768@60",
            "11": "1024x600@60",
            "12": "1920x1440@60",
            "13": "2048x1536@60",
            "14": "2560x1440@60",
        }

        if video_mode in resolution_map:
            self.easy_resolution_combo.set(resolution_map[video_mode])
        elif self.easy_hdmi_mode_combo.get() == "HD Output (Default)":
            self.easy_resolution_combo.set("1920x1080@60")

        # HDMI Scaling Mode
        vsync = settings.get("vsync_adjust", "1").strip()

        scaling_map = {
            "0": "Disabled",
            "1": "Low Latency",
            "2": "Exact Refresh"
        }

        self.easy_scaling_combo.set(scaling_map.get(vsync, "Low Latency"))

        # HDMI Audio (DVI Mode)
        dvi = settings.get("dvi_mode", "0").strip()

        if dvi == "1":
            self.easy_hdmi_audio_combo.set("Disabled (DVI Mode)")
        else:
            self.easy_hdmi_audio_combo.set("Enabled")

        # HDR
        hdr = settings.get("hdr", "0").strip()
        if hdr == "1":
            self.easy_hdr_combo.set("Enabled")
        else:
            self.easy_hdr_combo.set("Disabled")

        # HDMI Limited Range
        limited = settings.get("hdmi_limited", "0").strip()
        if limited == "1":
            self.easy_hdmi_limited_combo.set("Limited Range")
        else:
            self.easy_hdmi_limited_combo.set("Full Range")

        # Analogue Output
        vga_mode = settings.get("vga_mode", "rgb").strip().lower()
        composite_sync = settings.get("composite_sync", "0").strip()
        vga_sog = settings.get("vga_sog", "0").strip()

        if vga_mode == "ypbpr":
            self.easy_analogue_combo.set("Component (YPbPr)")
        elif vga_mode == "svideo":
            self.easy_analogue_combo.set("S-Video")
        elif vga_mode == "rgb":
            if vga_sog == "1":
                self.easy_analogue_combo.set("RGB (PVM/BVM)")
            elif composite_sync == "1":
                self.easy_analogue_combo.set("RGB (Consumer TV)")
            else:
                self.easy_analogue_combo.set("VGA Monitor")
        else:
            self.easy_analogue_combo.set("RGB (Consumer TV)")

        # MiSTer Logo
        logo = settings.get("logo", "1").strip()

        if logo == "0":
            self.easy_logo_combo.set("Disabled")
        else:
            self.easy_logo_combo.set("Enabled")
            
        self.update_easy_mode_state()

    def load_mister_ini_into_ui(self, silent=True):

        if not self.connection.connected:
            return False

        ok, message = self.ensure_mister_ini_exists()

        if not ok:
            if not silent:
                messagebox.showerror("MiSTer.ini Error", message)
            return False

        ini_text = self.connection.run_command("cat /media/fat/MiSTer.ini")

        if not ini_text:
            if not silent:
                messagebox.showerror("MiSTer.ini Error", "Unable to read /media/fat/MiSTer.ini")
            return False

        settings = self.parse_mister_ini(ini_text)
        self.map_ini_to_easy_mode(settings)
        return True

    def load_mister_ini_advanced(self):

        if not self.connection.connected:
            return

        ini_text = self.connection.run_command("cat /media/fat/MiSTer.ini")

        if not ini_text:
            return

        self.advanced_text.delete("1.0", tk.END)
        self.advanced_text.insert("1.0", ini_text)

    def build_easy_mode_settings(self):

        settings = {}

        # HDMI Mode
        hdmi_mode = self.easy_hdmi_mode_combo.get().strip()
        if hdmi_mode == "Direct Video (CRT / Scaler)":
            settings["direct_video"] = "1"
        else:
            settings["direct_video"] = "0"

        # Resolution
        resolution_reverse_map = {
            "1280x720@60": "0",
            "1024x768@60": "1",
            "720x480@60": "2",
            "720x576@50": "3",
            "1280x1024@60": "4",
            "800x600@60": "5",
            "640x480@60": "6",
            "1280x720@50": "7",
            "1920x1080@60": "8",
            "1920x1080@50": "9",
            "1366x768@60": "10",
            "1024x600@60": "11",
            "1920x1440@60": "12",
            "2048x1536@60": "13",
            "2560x1440@60": "14",
        }

        resolution = self.easy_resolution_combo.get().strip()
        if resolution in resolution_reverse_map:
            settings["video_mode"] = resolution_reverse_map[resolution]

        # HDMI Scaling Mode
        scaling = self.easy_scaling_combo.get().strip()

        scaling_map = {
            "Disabled": "0",
            "Low Latency": "1",
            "Exact Refresh": "2"
        }

        settings["vsync_adjust"] = scaling_map.get(scaling, "1")

        # HDMI Audio (DVI Mode)
        audio = self.easy_hdmi_audio_combo.get().strip()

        if audio == "Enabled":
            settings["dvi_mode"] = "0"
        else:
            settings["dvi_mode"] = "1"

        # HDR
        hdr = self.easy_hdr_combo.get().strip()
        settings["hdr"] = "1" if hdr == "Enabled" else "0"

        # HDMI Limited Range
        limited = self.easy_hdmi_limited_combo.get().strip()
        settings["hdmi_limited"] = "1" if limited == "Enabled" else "0"

        # Analogue Output
        analogue = self.easy_analogue_combo.get().strip()

        if analogue == "RGB (Consumer TV)":
            settings["vga_mode"] = "rgb"
            settings["composite_sync"] = "1"
            settings["vga_sog"] = "0"

        elif analogue == "RGB (PVM/BVM)":
            settings["vga_mode"] = "rgb"
            settings["composite_sync"] = "0"
            settings["vga_sog"] = "1"

        elif analogue == "Component (YPbPr)":
            settings["vga_mode"] = "ypbpr"
            settings["composite_sync"] = "0"
            settings["vga_sog"] = "0"

        elif analogue == "S-Video":
            settings["vga_mode"] = "svideo"
            settings["composite_sync"] = "0"
            settings["vga_sog"] = "0"

        elif analogue == "VGA Monitor":
            settings["vga_mode"] = "rgb"
            settings["composite_sync"] = "0"
            settings["vga_sog"] = "0"

        # MiSTer Logo
        logo = self.easy_logo_combo.get().strip()
        settings["logo"] = "1" if logo == "Enabled" else "0"

        return settings

    def update_mister_ini_text(self, ini_text, updated_settings):

        lines = ini_text.splitlines()
        new_lines = []

        in_mister_section = False
        replaced_keys = set()

        for line in lines:

            stripped = line.strip()

            # Detect section start
            if stripped.startswith("[") and stripped.endswith("]"):

                section_name = stripped[1:-1].strip()

                # Leaving MiSTer section
                if in_mister_section and section_name != "MiSTer":
                    for key, value in updated_settings.items():
                        if key not in replaced_keys:
                            new_lines.append(f"{key}={value}")

                in_mister_section = (section_name == "MiSTer")

                new_lines.append(line)
                continue

            if in_mister_section:

                clean = stripped.lstrip(";").strip()

                if "=" in clean:

                    key = clean.split("=", 1)[0].strip()

                    if key in updated_settings:
                        new_lines.append(f"{key}={updated_settings[key]}")
                        replaced_keys.add(key)
                        continue

            new_lines.append(line)

        # If MiSTer section was at end of file
        if in_mister_section:
            for key, value in updated_settings.items():
                if key not in replaced_keys:
                    new_lines.append(f"{key}={value}")

        return "\n".join(new_lines) + "\n"

    def enforce_mister_settings_retention(self, device_name):

        retention = self.config_data.get("mister_settings_retention", 10)

        device_path = os.path.join(MISTER_SETTINGS_ROOT, device_name)

        if not os.path.exists(device_path):
            return

        backups = sorted([
            f for f in os.listdir(device_path)
            if os.path.isfile(os.path.join(device_path, f))
        ])

        while len(backups) > retention:
            oldest = backups.pop(0)
            try:
                os.remove(os.path.join(device_path, oldest))
            except Exception:
                pass

    def backup_mister_settings(self, silent=False):

        if not self.connection.connected:
            if not silent:
                messagebox.showerror("Error", "Connect to a MiSTer first.")
            return False

        device_name = self.get_mister_settings_device_name()

        if not device_name:
            if not silent:
                messagebox.showerror("Error", "No device name or IP available.")
            return False

        device_path = os.path.join(MISTER_SETTINGS_ROOT, device_name)
        os.makedirs(device_path, exist_ok=True)

        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        backup_file = os.path.join(device_path, f"MiSTer.ini.{timestamp}.bak")

        try:
            sftp = self.connection.client.open_sftp()
            sftp.get("/media/fat/MiSTer.ini", backup_file)
            sftp.close()

            self.enforce_mister_settings_retention(device_name)

            if not silent:
                messagebox.showinfo(
                    "Backup Created",
                    f"MiSTer.ini backup created successfully.\n\n{backup_file}"
                )

            return True

        except Exception as e:
            if not silent:
                messagebox.showerror(
                    "Backup Failed",
                    f"Unable to create MiSTer.ini backup:\n{str(e)}"
                )
            return False

    def save_mister_settings(self):

        if not self.connection.connected:
            messagebox.showerror("Error", "Connect to a MiSTer first.")
            return

        ok, message = self.ensure_mister_ini_exists()
        if not ok:
            messagebox.showerror("MiSTer.ini Error", message)
            return

        choice = messagebox.askyesnocancel(
            "Backup Before Apply",
            "Do you want to create a backup of the current MiSTer.ini before applying settings?\n\n"
            "Yes = Continue with Backup\n"
            "No = Continue Without Backup\n"
            "Cancel = Cancel"
        )

        if choice is None:
            return

        if choice is True:
            backup_ok = self.backup_mister_settings(silent=True)
            if not backup_ok:
                proceed = messagebox.askyesno(
                    "Backup Failed",
                    "Unable to create backup before applying settings.\n\nContinue anyway?"
                )
                if not proceed:
                    return

        try:
            ini_text = self.connection.run_command("cat /media/fat/MiSTer.ini")

            if not ini_text:
                messagebox.showerror("MiSTer.ini Error", "Unable to read /media/fat/MiSTer.ini")
                return

            mode = self.mister_settings_mode_var.get()

            if mode == "easy":

                updated_settings = self.build_easy_mode_settings()
                new_ini_text = self.update_mister_ini_text(ini_text, updated_settings)

            else:

                advanced_text = self.advanced_text.get("1.0", tk.END).strip()

                new_ini_text = self.update_mister_ini_text(
                    ini_text,
                    {}
                )

                # Replace MiSTer section with advanced content
                lines = new_ini_text.splitlines()

                output = []
                in_mister = False
                replaced = False

                for line in lines:

                    stripped = line.strip()

                    if stripped == "[MiSTer]":
                        output.append(line)
                        output.append(advanced_text)
                        in_mister = True
                        replaced = True
                        continue

                    if in_mister and stripped.startswith("[") and stripped.endswith("]"):
                        in_mister = False

                    if not in_mister:
                        output.append(line)

                if not replaced:
                    output.append("")
                    output.append("[MiSTer]")
                    output.append(advanced_text)

                new_ini_text = "\n".join(output) + "\n"

            sftp = self.connection.client.open_sftp()
            with sftp.open("/media/fat/MiSTer.ini", "w") as f:
                f.write(new_ini_text)
            sftp.close()

            self.load_mister_ini_into_ui(silent=True)
            self.load_mister_ini_advanced()

            reboot_now = messagebox.askyesno(
                "Settings Applied",
                "MiSTer settings were applied successfully.\n\nA reboot is recommended.\n\nReboot now?"
            )

            if reboot_now:
                self.reboot()

        except Exception as e:
            messagebox.showerror(
                "Save Failed",
                f"Unable to save MiSTer settings:\n{str(e)}"
            )

    def restore_default_mister_settings(self):

        if not self.connection.connected:
            messagebox.showerror("Error", "Connect to a MiSTer first.")
            return

        confirm = messagebox.askyesno(
            "Restore Default Settings",
            "This will replace the current MiSTer.ini with the default settings from MiSTer_example.ini.\n\nContinue?"
        )

        if not confirm:
            return

        example_exists = self.connection.run_command(
            'test -f /media/fat/MiSTer_example.ini && echo EXISTS'
        )

        if "EXISTS" not in (example_exists or ""):
            messagebox.showerror(
                "Restore Defaults Failed",
                "MiSTer_example.ini was not found on the MiSTer."
            )
            return

        choice = messagebox.askyesnocancel(
            "Backup Current Settings",
            "Do you want to create a backup of the current MiSTer.ini before restoring defaults?\n\n"
            "Yes = Continue with Backup\n"
            "No = Continue Without Backup\n"
            "Cancel = Cancel"
        )

        if choice is None:
            return

        if choice is True:
            backup_ok = self.backup_mister_settings(silent=True)
            if not backup_ok:
                proceed = messagebox.askyesno(
                    "Backup Failed",
                    "Unable to create backup before restoring defaults.\n\nContinue anyway?"
                )
                if not proceed:
                    return

        result = self.connection.run_command(
            'cp /media/fat/MiSTer_example.ini /media/fat/MiSTer.ini && echo RESTORED'
        )

        if "RESTORED" not in (result or ""):
            messagebox.showerror(
                "Restore Defaults Failed",
                "Unable to restore MiSTer.ini from MiSTer_example.ini."
            )
            return

        self.load_mister_ini_into_ui(silent=True)

        reboot_now = messagebox.askyesno(
            "Defaults Restored",
            "Default MiSTer settings were restored successfully.\n\nA reboot is recommended.\n\nReboot now?"
        )

        if reboot_now:
            self.reboot()

    def show_savemanager_log(self):

        if not self.savemanager_log_frame.winfo_ismapped():
            self.savemanager_log_frame.pack(fill="both", expand=True, pady=10)

    def hide_savemanager_log(self):

        if self.hide_log_button["state"] == "disabled":
            return

        self.savemanager_log_frame.pack_forget()

    def update_backup_count(self):

        device_name = self.device_combo.get().strip()

        if not device_name:
            if not self.connection.ip:
                self.backup_count_label.config(text="Current backups for this device: 0")
                return

            device_name = self.connection.ip.replace(".", "_")

        device_path = os.path.join(BACKUP_ROOT, device_name)

        if not os.path.exists(device_path):
            count = 0
        else:
            count = len([
                d for d in os.listdir(device_path)
                if os.path.isdir(os.path.join(device_path, d))
            ])

        self.backup_count_label.config(
            text=f"Current backups for this device: {count}"
        )

    def enforce_backup_retention(self, device_name):

        retention = self.config_data.get("backup_retention", 10)

        device_path = os.path.join(BACKUP_ROOT, device_name)

        if not os.path.exists(device_path):
            return

        backups = sorted([
            d for d in os.listdir(device_path)
            if os.path.isdir(os.path.join(device_path, d))
        ])

        while len(backups) > retention:
            oldest = backups.pop(0)

            import shutil
            shutil.rmtree(os.path.join(device_path, oldest))

            self.savemanager_log_msg(f"Old backup removed: {oldest}")

    def disable_savemanager_buttons(self):
        self.backup_button.config(state="disabled")
        self.restore_button.config(state="disabled")
        self.sync_button.config(state="disabled")
        self.open_backup_folder_button.config(state="disabled")
        self.open_sync_folder_button.config(state="disabled")
        self.retention_spin.config(state="disabled")

    def enable_savemanager_buttons(self):
        self.backup_button.config(state="normal")
        self.restore_button.config(state="normal")
        self.sync_button.config(state="normal")
        self.open_backup_folder_button.config(state="normal")
        self.open_sync_folder_button.config(state="normal")
        self.retention_spin.config(state="normal")

    def savemanager_log_msg(self, text):
        self.savemanager_log.insert(tk.END, text + "\n")
        self.savemanager_log.see(tk.END)

    def backup_saves(self, internal_call=False):

        if not self.connection.connected:
            messagebox.showerror("Error", "Connect to a MiSTer first.")
            return

        def worker():

            self.root.after(0, self.disable_savemanager_buttons)
            self.root.after(0, self.show_savemanager_log)
            self.root.after(0, lambda: self.savemanager_log.delete("1.0", tk.END))
            self.root.after(0, lambda: self.hide_log_button.config(state="disabled"))
            self.root.after(0, lambda: self.savemanager_log_msg("Starting backup..."))

            device_name = self.device_combo.get().strip()

            if not device_name:
                device_name = self.connection.ip.replace(".", "_")

            timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
            backup_path = os.path.join(BACKUP_ROOT, device_name, timestamp)

            os.makedirs(backup_path, exist_ok=True)

            try:

                sftp = self.connection.client.open_sftp()

                def download_dir(remote_dir, local_dir):

                    os.makedirs(local_dir, exist_ok=True)

                    for item in sftp.listdir_attr(remote_dir):

                        remote_path = f"{remote_dir}/{item.filename}"
                        local_path = os.path.join(local_dir, item.filename)

                        if stat.S_ISDIR(item.st_mode):
                            download_dir(remote_path, local_path)
                        else:
                            sftp.get(remote_path, local_path)

                self.root.after(0, lambda: self.savemanager_log_msg("Downloading /media/fat/Saves ..."))

                download_dir("/media/fat/Saves", backup_path + "/Saves")

                try:
                    download_dir("/media/fat/savestates", backup_path + "/savestates")
                except IOError:
                    pass

                sftp.close()

                self.root.after(0, lambda: self.savemanager_log_msg("Updating sync folder..."))

                import shutil

                def merge_to_sync(local_dir, sync_dir):

                    os.makedirs(sync_dir, exist_ok=True)

                    for item in os.listdir(local_dir):

                        local_path = os.path.join(local_dir, item)
                        sync_path = os.path.join(sync_dir, item)

                        if os.path.isdir(local_path):
                            merge_to_sync(local_path, sync_path)
                        else:
                            if not os.path.exists(sync_path):
                                shutil.copy2(local_path, sync_path)
                            else:
                                if os.path.getmtime(local_path) > os.path.getmtime(sync_path):
                                    shutil.copy2(local_path, sync_path)

                merge_to_sync(backup_path, SYNC_ROOT)

                self.enforce_backup_retention(device_name)

                self.root.after(0, lambda: self.savemanager_log_msg(f"Backup completed: {backup_path}"))
                self.root.after(0, self.update_backup_count)
                self.root.after(0, lambda: self.hide_log_button.config(state="normal"))

                if not internal_call:
                    self.root.after(0, self.enable_savemanager_buttons)

            except Exception as e:

                self.root.after(0, lambda: self.savemanager_log_msg(f"Backup failed: {str(e)}"))
                self.root.after(0, lambda: self.hide_log_button.config(state="normal"))

                if not internal_call:
                    self.root.after(0, self.enable_savemanager_buttons)

        threading.Thread(target=worker, daemon=True).start()

    def restore_saves(self):

        if not self.connection.connected:
            messagebox.showerror("Error", "Connect to a MiSTer first.")
            return

        device_root = BACKUP_ROOT

        if not os.path.exists(device_root):
            messagebox.showerror("Error", "No backups available.")
            return

        devices = os.listdir(device_root)

        if not devices:
            messagebox.showerror("Error", "No backups available.")
            return

        popup = tk.Toplevel(self.root)
        popup.title("Restore Backup")
        popup.geometry("360x300")
        popup.resizable(False, False)

        frame = ttk.Frame(popup, padding=15)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Choose a backup device and version to restore to the currently connected MiSTer.",
            foreground="black",
            justify="center",
            wraplength=320
        ).pack(pady=(0, 10))

        ttk.Label(frame, text="Backup Device").pack(anchor="w")
        device_combo = ttk.Combobox(frame, values=devices, state="readonly")
        device_combo.pack(fill="x", pady=5)

        ttk.Label(frame, text="Backup Version").pack(anchor="w")
        backup_combo = ttk.Combobox(frame, state="readonly")
        backup_combo.pack(fill="x", pady=5)

        backup_before_restore = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            frame,
            text="Backup current device before restore",
            variable=backup_before_restore
        ).pack(anchor="w", pady=10)

        def load_backups(event=None):

            device = device_combo.get()

            path = os.path.join(device_root, device)

            if os.path.exists(path):
                backups = sorted(os.listdir(path), reverse=True)
                backup_combo["values"] = backups

        device_combo.bind("<<ComboboxSelected>>", load_backups)

        if devices:
            device_combo.current(0)
            load_backups()

        def run_restore():

            device = device_combo.get()
            backup = backup_combo.get()

            if not device or not backup:
                messagebox.showerror("Error", "Select a backup.")
                return

            backup_path = os.path.join(device_root, device, backup)

            popup.destroy()

            def worker():

                self.root.after(0, self.disable_savemanager_buttons)
                self.root.after(0, self.show_savemanager_log)
                self.root.after(0, lambda: self.hide_log_button.config(state="disabled"))
                self.root.after(0, lambda: self.savemanager_log.delete("1.0", tk.END))
                self.root.after(0, lambda: self.savemanager_log_msg("Starting restore..."))

                try:

                    if backup_before_restore.get():
                        self.root.after(0, lambda: self.savemanager_log_msg("Creating safety backup..."))
                        self.backup_saves(internal_call=True)

                    sftp = self.connection.client.open_sftp()

                    def upload_dir(local_dir, remote_dir):

                        try:
                            self.connection.run_command(f'mkdir -p "{remote_dir}"')
                        except:
                            pass

                        for item in os.listdir(local_dir):

                            local_path = os.path.join(local_dir, item)
                            remote_path = f"{remote_dir}/{item}"

                            if os.path.isdir(local_path):
                                upload_dir(local_path, remote_path)
                            else:
                                sftp.put(local_path, remote_path)

                    upload_dir(os.path.join(backup_path, "Saves"), "/media/fat/Saves")

                    savestate_path = os.path.join(backup_path, "savestates")
                    if os.path.exists(savestate_path):
                        upload_dir(savestate_path, "/media/fat/savestates")

                    sftp.close()

                    self.root.after(0, lambda: self.savemanager_log_msg("Restore completed."))
                    self.root.after(0, lambda: self.hide_log_button.config(state="normal"))
                    self.root.after(0, self.enable_savemanager_buttons)

                except Exception as e:

                    self.root.after(0, lambda: self.savemanager_log_msg(f"Restore failed: {str(e)}"))
                    self.root.after(0, lambda: self.hide_log_button.config(state="normal"))
                    self.root.after(0, self.enable_savemanager_buttons)

            threading.Thread(target=worker, daemon=True).start()

        # ===== Restore popup buttons  =====

        button_row = ttk.Frame(frame)
        button_row.pack(pady=12)

        ttk.Button(
            button_row,
            text="Restore",
            width=12,
            command=run_restore
        ).pack(side="left", padx=6)

        ttk.Button(
            button_row,
            text="Cancel",
            width=12,
            command=popup.destroy
        ).pack(side="left", padx=6)

    def sync_saves(self):

        if not self.connection.connected:
            messagebox.showerror("Error", "Connect to a MiSTer first.")
            return

        popup = tk.Toplevel(self.root)
        popup.title("Sync Saves")
        popup.geometry("420x260")
        popup.resizable(False, False)

        frame = ttk.Frame(popup, padding=15)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="This will synchronize the connected MiSTer\n"
                 "with the local Sync Folder.\n\n"
                 "The newest saves from all devices will be\n"
                 "applied to this MiSTer.",
            justify="center"
        ).pack(pady=10)

        backup_var = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            frame,
            text="Backup current device before syncing",
            variable=backup_var
        ).pack(anchor="w", pady=10)

        def run_sync():

            popup.destroy()

            def worker():

                self.root.after(0, self.disable_savemanager_buttons)
                self.root.after(0, self.show_savemanager_log)
                self.root.after(0, lambda: self.hide_log_button.config(state="disabled"))
                self.root.after(0, lambda: self.savemanager_log.delete("1.0", tk.END))
                self.root.after(0, lambda: self.savemanager_log_msg("Sync started..."))

                try:

                    if backup_var.get():
                        self.root.after(0, lambda: self.savemanager_log_msg("Creating device backup..."))
                        self.backup_saves(internal_call=True)

                    sftp = self.connection.client.open_sftp()

                    # -----------------------------
                    # Download device saves
                    # -----------------------------

                    self.root.after(0, lambda: self.savemanager_log_msg("Updating sync folder..."))

                    def download_dir(remote_dir, local_dir):

                        os.makedirs(local_dir, exist_ok=True)

                        for item in sftp.listdir_attr(remote_dir):

                            remote_path = f"{remote_dir}/{item.filename}"
                            local_path = os.path.join(local_dir, item.filename)

                            if stat.S_ISDIR(item.st_mode):

                                download_dir(remote_path, local_path)

                            else:

                                remote_time = item.st_mtime

                                if os.path.exists(local_path):

                                    try:
                                        local_time = os.path.getmtime(local_path)
                                    except:
                                        local_time = 0

                                    if remote_time > local_time:

                                        try:
                                            os.remove(local_path)
                                            time.sleep(0.01)
                                        except:
                                            pass

                                        sftp.get(remote_path, local_path)

                                else:

                                    sftp.get(remote_path, local_path)

                    download_dir("/media/fat/Saves", os.path.join(SYNC_ROOT, "Saves"))
                    download_dir("/media/fat/savestates", os.path.join(SYNC_ROOT, "savestates"))

                    # -----------------------------
                    # Upload merged saves
                    # -----------------------------

                    self.root.after(0, lambda: self.savemanager_log_msg("Uploading newest saves to MiSTer..."))

                    def upload_dir(local_dir, remote_dir):

                        try:
                            self.connection.run_command(f'mkdir -p "{remote_dir}"')
                        except:
                            pass

                        for item in os.listdir(local_dir):

                            local_path = os.path.join(local_dir, item)
                            remote_path = f"{remote_dir}/{item}"

                            if os.path.isdir(local_path):
                                upload_dir(local_path, remote_path)
                            else:
                                sftp.put(local_path, remote_path)

                    upload_dir(os.path.join(SYNC_ROOT, "Saves"), "/media/fat/Saves")
                    upload_dir(os.path.join(SYNC_ROOT, "savestates"), "/media/fat/savestates")

                    sftp.close()

                    self.root.after(0, lambda: self.savemanager_log_msg("Sync completed successfully."))
                    self.root.after(0, lambda: self.hide_log_button.config(state="normal"))
                    self.root.after(0, self.enable_savemanager_buttons)

                except Exception as e:

                    self.root.after(0, lambda: self.savemanager_log_msg(f"Sync failed: {str(e)}"))
                    self.root.after(0, lambda: self.hide_log_button.config(state="normal"))
                    self.root.after(0, self.enable_savemanager_buttons)

            threading.Thread(target=worker, daemon=True).start()

        button_row = ttk.Frame(frame)
        button_row.pack(pady=10)

        ttk.Button(
            button_row,
            text="Sync",
            width=12,
            command=run_sync
        ).pack(side="left", padx=6)

        ttk.Button(
            button_row,
            text="Cancel",
            width=12,
            command=popup.destroy
        ).pack(side="left", padx=6)


    def open_backup_folder(self):

        path = os.path.abspath(BACKUP_ROOT)

        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", path])

        elif sys.platform.startswith("linux"):
            env = os.environ.copy()
            subprocess.Popen(
                ["gio", "open", path],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])


    def open_sync_folder(self):

        path = os.path.abspath(SYNC_ROOT)

        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", path])

        elif sys.platform.startswith("linux"):
            env = os.environ.copy()
            subprocess.Popen(
                ["gio", "open", path],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])

    def open_mister_settings_folder(self):

        path = self.get_mister_settings_device_path()

        os.makedirs(path, exist_ok=True)

        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", path])

        elif sys.platform.startswith("linux"):
            env = os.environ.copy()
            subprocess.Popen(
                ["gio", "open", path],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])

    def restore_mister_settings(self):

        if not self.connection.connected:
            messagebox.showerror("Error", "Connect to a MiSTer first.")
            return

        device_name = self.get_mister_settings_device_name()

        if not device_name:
            messagebox.showerror("Error", "No device name or IP available.")
            return

        device_path = os.path.join(MISTER_SETTINGS_ROOT, device_name)

        if not os.path.exists(device_path):
            messagebox.showerror("Error", "No MiSTer.ini backups found for this device.")
            return

        backups = sorted([
            f for f in os.listdir(device_path)
            if os.path.isfile(os.path.join(device_path, f))
        ], reverse=True)

        if not backups:
            messagebox.showerror("Error", "No MiSTer.ini backups found for this device.")
            return

        popup = tk.Toplevel(self.root)
        popup.title("Restore MiSTer Settings Backup")
        popup.geometry("400x260")
        popup.resizable(False, False)

        frame = ttk.Frame(popup, padding=15)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Select a MiSTer.ini backup to restore to the currently connected device.",
            justify="center",
            wraplength=340
        ).pack(pady=(0, 10))

        ttk.Label(frame, text="Backup Version").pack(anchor="w")
        backup_combo = ttk.Combobox(frame, values=backups, state="readonly")
        backup_combo.pack(fill="x", pady=5)

        if backups:
            backup_combo.current(0)

        backup_before_restore = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            frame,
            text="Backup current MiSTer.ini before restore",
            variable=backup_before_restore
        ).pack(anchor="w", pady=10)

        def run_restore():

            backup_name = backup_combo.get().strip()

            if not backup_name:
                messagebox.showerror("Error", "Select a backup.")
                return

            backup_path = os.path.join(device_path, backup_name)

            try:
                if backup_before_restore.get():
                    ok = self.backup_mister_settings(silent=True)
                    if not ok:
                        proceed = messagebox.askyesno(
                            "Backup Failed",
                            "Unable to create a safety backup before restore.\n\nContinue anyway?"
                        )
                        if not proceed:
                            return

                sftp = self.connection.client.open_sftp()
                sftp.put(backup_path, "/media/fat/MiSTer.ini")
                sftp.close()

                popup.destroy()
                self.load_mister_ini_into_ui(silent=True)

                reboot_now = messagebox.askyesno(
                    "Restore Complete",
                    "MiSTer.ini backup restored successfully.\n\nA reboot is recommended.\n\nReboot now?"
                )

                if reboot_now:
                    self.reboot()

            except Exception as e:
                messagebox.showerror(
                    "Restore Failed",
                    f"Unable to restore MiSTer.ini backup:\n{str(e)}"
                )

        button_row = ttk.Frame(frame)
        button_row.pack(pady=12)

        ttk.Button(
            button_row,
            text="Restore",
            width=12,
            command=run_restore
        ).pack(side="left", padx=6)

        ttk.Button(
            button_row,
            text="Cancel",
            width=12,
            command=popup.destroy
        ).pack(side="left", padx=6)

    # =========================
    # Wallpapers Functions
    # =========================

    def fetch_ranny_wallpapers(self):

        try:

            url = "https://api.github.com/repos/Ranny-Snice/Ranny-Snice-Wallpapers/contents/Wallpapers"

            r = requests.get(url, timeout=10)

            if r.status_code != 200:
                return [], []

            data = r.json()

            w169 = []
            w43 = []

            for item in data:

                if item["type"] != "file":
                    continue

                name = item["name"]

                if "4x3" in name.lower():
                    w43.append(item)
                else:
                    w169.append(item)

            return w169, w43

        except:
            return [], []

    def get_installed_wallpapers(self):

        if not self.connection.connected:
            return []

        try:
            result = self.connection.run_command(
                "ls -1 /media/fat/wallpapers 2>/dev/null"
            )

            if not result:
                return []

            files = [
                f.strip().replace("\r", "")
                for f in result.splitlines()
                if f.strip()
            ]

            return files  # ← KEEP ORIGINAL CASE

        except:
            return []

    def check_ranny_wallpapers(self):

        if not self.connection.connected:
            return

        gh_169, gh_43 = self.fetch_ranny_wallpapers()
        installed = self.get_installed_wallpapers()

        installed_set = {f.lower() for f in installed}

        gh169_names = {item["name"].lower() for item in gh_169}
        gh43_names = {item["name"].lower() for item in gh_43}

        installed_169 = gh169_names & installed_set
        installed_43 = gh43_names & installed_set

        missing_169 = gh169_names - installed_set
        missing_43 = gh43_names - installed_set

        # ---- 16:9 button ----

        if not installed_169:
            self.install_169_wallpapers_button.config(
                text="Install 16:9 Wallpapers",
                state="normal"
            )

        elif missing_169:
            self.install_169_wallpapers_button.config(
                text="Update 16:9 Wallpapers",
                state="normal"
            )

        else:
            self.install_169_wallpapers_button.config(
                text="Install 16:9 Wallpapers",
                state="disabled"
            )

        # ---- 4:3 button ----

        if not installed_43:
            self.install_43_wallpapers_button.config(
                text="Install 4:3 Wallpapers",
                state="normal"
            )

        elif missing_43:
            self.install_43_wallpapers_button.config(
                text="Update 4:3 Wallpapers",
                state="normal"
            )

        else:
            self.install_43_wallpapers_button.config(
                text="Install 4:3 Wallpapers",
                state="disabled"
            )

        # ---- Remove button ----

        if installed_169 or installed_43:
            self.remove_wallpapers_button.config(state="normal")
        else:
            self.remove_wallpapers_button.config(state="disabled")

    def download_wallpaper(self, url):

        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                return r.content
        except:
            pass

        return None


    def upload_wallpaper(self, name, data):

        try:

            sftp = self.connection.client.open_sftp()

            path = f"/media/fat/wallpapers/{name}"

            with sftp.file(path, "wb") as f:
                f.write(data)

            sftp.close()

            return True

        except Exception as e:

            self.wallpaper_log(f"Upload failed: {name}\n")
            self.wallpaper_log(str(e) + "\n")

            return False


    def install_ranny_wallpapers(self, mode):

        if not self.connection.connected:
            return

        # show wallpaper console automatically
        if not self.wallpaper_console_visible:
            self.wallpaper_console_frame.pack(fill="x", pady=10)
            self.wallpaper_console_visible = True

        self.wallpaper_log("Fetching wallpaper list...\n")

        gh_169, gh_43 = self.fetch_ranny_wallpapers()

        wallpapers = gh_169 if mode == "169" else gh_43

        if not wallpapers:
            self.wallpaper_log("No wallpapers found.\n")
            return

        self.ensure_wallpaper_folder()

        installed = self.get_installed_wallpapers()

        new_count = 0

        for item in wallpapers:

            name = item["name"]

            if any(name.lower() == f.lower() for f in installed):
                continue

            self.wallpaper_log(f"Downloading {name}...\n")

            data = self.download_wallpaper(item["download_url"])

            if not data:
                self.wallpaper_log("Download failed\n")
                continue

            self.wallpaper_log(f"Uploading {name}...\n")

            ok = self.upload_wallpaper(name, data)

            if ok:
                new_count += 1
                self.wallpaper_log(f"Installed {name}\n")

        self.wallpaper_log(f"\nFinished. {new_count} wallpapers installed.\n")

        self.check_ranny_wallpapers()


    def install_169_wallpapers(self):

        threading.Thread(
            target=lambda: self.install_ranny_wallpapers("169"),
            daemon=True
        ).start()


    def install_43_wallpapers(self):

        threading.Thread(
            target=lambda: self.install_ranny_wallpapers("43"),
            daemon=True
        ).start()

    def remove_ranny_wallpapers(self):

        if not self.connection.connected:
            return

        confirm = messagebox.askyesno(
            "Remove Wallpapers",
            "Remove all Ranny Snice wallpapers from the MiSTer?"
        )

        if not confirm:
            return

        # show wallpaper console automatically
        if not self.wallpaper_console_visible:
            self.wallpaper_console_frame.pack(fill="x", pady=10)
            self.wallpaper_console_visible = True

        self.wallpaper_console.delete("1.0", tk.END)

        def worker():

            self.wallpaper_log("Removing Ranny Snice wallpapers...\n")

            gh_169, gh_43 = self.fetch_ranny_wallpapers()
            repo_files = {item["name"] for item in gh_169 + gh_43}

            installed = self.get_installed_wallpapers()

            removed = 0

            for name in installed:

                if name in repo_files:
                    self.connection.run_command(
                        f'rm "/media/fat/wallpapers/{name}"'
                    )

                    removed += 1
                    self.wallpaper_log(f"Removed {name}\n")

            self.wallpaper_log(f"\nFinished. {removed} wallpapers removed.\n")

            self.root.after(0, self.check_ranny_wallpapers)

        threading.Thread(target=worker, daemon=True).start()

    def wallpaper_folder_exists(self):

        if not self.connection.connected:
            return False

        try:
            result = self.connection.run_command("test -d /media/fat/wallpapers && echo EXISTS")
            return result and "EXISTS" in result
        except:
            return False

    def ensure_wallpaper_folder(self):

        if not self.connection.connected:
            return

        try:
            self.connection.run_command("mkdir -p /media/fat/wallpapers")
        except:
            pass

    def update_wallpaper_tab_state(self):

        connected = self.connection.connected

        try:

            if not connected:
                self.install_169_wallpapers_button.config(state="disabled")
                self.install_43_wallpapers_button.config(state="disabled")
                self.remove_wallpapers_button.config(state="disabled")
                self.open_wallpaper_folder_button.config(state="disabled")

                return

            self.install_169_wallpapers_button.config(state="normal")
            self.install_43_wallpapers_button.config(state="normal")

            if self.wallpaper_folder_exists():
                self.open_wallpaper_folder_button.config(state="normal")
            else:
                self.open_wallpaper_folder_button.config(state="disabled")

        except:
            pass

    def toggle_wallpaper_console(self):

        if self.wallpaper_console_visible:
            self.wallpaper_console_frame.pack_forget()
            self.wallpaper_console_visible = False
        else:
            self.wallpaper_console_frame.pack(fill="x", pady=10)
            self.wallpaper_console_visible = True


    def wallpaper_log(self, text):
        self.root.after(0, lambda: self._wallpaper_log_ui(text))


    def _wallpaper_log_ui(self, text):
        self.wallpaper_console.insert(tk.END, text)
        self.wallpaper_console.see(tk.END)

    def open_wallpaper_folder(self):

        if not self.connection.ip:
            return

        ip = self.connection.ip

        try:

            # Windows
            if sys.platform.startswith("win"):
                subprocess.Popen(f'explorer "\\\\{ip}\\sdcard\\wallpapers"')

            # Linux
            elif sys.platform.startswith("linux"):

                env = os.environ.copy()

                subprocess.run(
                    ["gio", "mount", f"smb://{ip}/"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                subprocess.Popen(
                    ["gio", "open", f"smb://{ip}/sdcard/wallpapers"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            # macOS
            elif sys.platform == "darwin":
                subprocess.Popen(["open", f"smb://{ip}/sdcard/wallpapers"])

        except Exception as e:
            messagebox.showerror("SMB Error", str(e))

    def open_scripts_folder(self):

        if not self.connection.ip:
            return

        ip = self.connection.ip

        try:

            # Windows
            if sys.platform.startswith("win"):
                subprocess.Popen(f'explorer "\\\\{ip}\\sdcard\\Scripts"')

            # Linux
            elif sys.platform.startswith("linux"):

                env = os.environ.copy()

                subprocess.run(
                    ["gio", "mount", f"smb://{ip}/"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                subprocess.Popen(
                    ["gio", "open", f"smb://{ip}/sdcard/Scripts"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            # macOS
            elif sys.platform == "darwin":
                subprocess.Popen(["open", f"smb://{ip}/sdcard/Scripts"])

        except Exception as e:
            messagebox.showerror("SMB Error", str(e))

    def open_update_all_configurator(self):

        if not self.connection.connected:
            messagebox.showerror("Error", "Connect to a MiSTer first.")
            return

        if not getattr(self, "update_all_installed", False):
            messagebox.showerror(
                "update_all not installed",
                "Install update_all first before opening the configurator."
            )
            return

        initialized = self.check_update_all_initialized()
        self.update_all_initialized = initialized

        if not initialized:
            popup = tk.Toplevel(self.root)
            popup.title("update_all not initialized")
            popup.geometry("420x180")
            popup.resizable(False, False)
            popup.transient(self.root)
            popup.grab_set()

            frame = ttk.Frame(popup, padding=15)
            frame.pack(fill="both", expand=True)

            ttk.Label(
                frame,
                text="update_all needs to run at least once before you can configure it.",
                justify="center",
                wraplength=360
            ).pack(pady=(10, 20))

            button_row = ttk.Frame(frame)
            button_row.pack()

            def run_and_close():
                popup.destroy()
                self.run_update_all()

            ttk.Button(
                button_row,
                text="Run Update All",
                width=16,
                command=run_and_close
            ).pack(side="left", padx=6)

            ttk.Button(
                button_row,
                text="Close",
                width=12,
                command=popup.destroy
            ).pack(side="left", padx=6)

            return

        popup = tk.Toplevel(self.root)
        popup.title("Update_All Configuration")
        popup.transient(self.root)
        popup.grab_set()

        screen_w = popup.winfo_screenwidth()
        screen_h = popup.winfo_screenheight()

        popup_width = min(500, max(460, screen_w - 80))
        popup_height = min(900, max(500, screen_h - 80))

        x = max((screen_w // 2) - (popup_width // 2), 20)
        y = max((screen_h // 2) - (popup_height // 2), 20)

        popup.geometry(f"{popup_width}x{popup_height}+{x}+{y}")
        popup.minsize(460, 500)

        outer = ttk.Frame(popup, padding=15)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="top", fill="both", expand=True)

        frame = ttk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=frame, anchor="nw")

        def _on_frame_configure(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfigure(canvas_window, width=event.width)

        frame.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            try:
                widget = popup.winfo_containing(event.x_root, event.y_root)
                if widget is None:
                    return

                current = widget
                while current is not None:
                    if current == popup:
                        break
                    current = current.master

                if current != popup:
                    return

                if hasattr(event, "delta") and event.delta:
                    if sys.platform == "darwin":
                        canvas.yview_scroll(int(-1 * event.delta), "units")
                    else:
                        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        def _on_mousewheel_linux_up(event):
            try:
                widget = popup.winfo_containing(event.x_root, event.y_root)
                if widget is None:
                    return

                current = widget
                while current is not None:
                    if current == popup:
                        break
                    current = current.master

                if current == popup:
                    canvas.yview_scroll(-1, "units")
            except Exception:
                pass

        def _on_mousewheel_linux_down(event):
            try:
                widget = popup.winfo_containing(event.x_root, event.y_root)
                if widget is None:
                    return

                current = widget
                while current is not None:
                    if current == popup:
                        break
                    current = current.master

                if current == popup:
                    canvas.yview_scroll(1, "units")
            except Exception:
                pass

        def _bind_mousewheel_global():
            popup.bind_all("<MouseWheel>", _on_mousewheel)
            popup.bind_all("<Button-4>", _on_mousewheel_linux_up)
            popup.bind_all("<Button-5>", _on_mousewheel_linux_down)

        def _unbind_mousewheel_global():
            popup.unbind_all("<MouseWheel>")
            popup.unbind_all("<Button-4>")
            popup.unbind_all("<Button-5>")

        def _close_popup():
            _unbind_mousewheel_global()
            popup.destroy()

        _bind_mousewheel_global()
        popup.protocol("WM_DELETE_WINDOW", _close_popup)

        ttk.Label(
            frame,
            text="Update_All Configuration",
            font=("Segoe UI", 12, "bold")
        ).pack(pady=(0, 10))

        # ===== Main Cores =====
        main_frame = ttk.LabelFrame(frame, text="Main Cores")
        main_frame.pack(fill="x", pady=8)

        self.main_cores_var = tk.BooleanVar()

        ttk.Checkbutton(
            main_frame,
            text="Enable Main Cores",
            variable=self.main_cores_var
        ).pack(anchor="w", padx=10, pady=5)

        source_frame = ttk.Frame(main_frame)
        source_frame.pack(fill="x", padx=20, pady=5)

        ttk.Label(source_frame, text="Source:").pack(side="left")

        self.main_source_var = tk.StringVar()

        self.main_source_combo = ttk.Combobox(
            source_frame,
            textvariable=self.main_source_var,
            state="readonly",
            values=[
                "MiSTer-devel (Recommended)",
                "DB9 / SNAC8 forks with ENCC",
                "AitorGomez fork"
            ],
            width=30
        )
        self.main_source_combo.pack(side="left", padx=10)
        self.main_source_combo.set("MiSTer-devel (Recommended)")

        # ===== JTCores =====
        jt_frame = ttk.LabelFrame(frame, text="JTCores")
        jt_frame.pack(fill="x", pady=8)

        self.jtcores_var = tk.BooleanVar()
        self.jtbeta_var = tk.BooleanVar()

        ttk.Checkbutton(
            jt_frame,
            text="Enable JTCores",
            variable=self.jtcores_var,
            command=self.update_jt_beta_state
        ).pack(anchor="w", padx=10, pady=5)

        self.jtbeta_check = ttk.Checkbutton(
            jt_frame,
            text="Enable Beta Cores",
            variable=self.jtbeta_var
        )
        self.jtbeta_check.pack(anchor="w", padx=30, pady=5)

        # ===== Other Cores =====
        other_frame = ttk.LabelFrame(frame, text="Other Cores")
        other_frame.pack(fill="x", pady=8)

        self.coinop_var = tk.BooleanVar()
        self.arcade_offset_var = tk.BooleanVar()
        self.llapi_var = tk.BooleanVar()
        self.unofficial_var = tk.BooleanVar()
        self.yc_var = tk.BooleanVar()
        self.agg23_var = tk.BooleanVar()
        self.altcores_var = tk.BooleanVar()
        self.dualram_var = tk.BooleanVar()

        ttk.Checkbutton(other_frame, text="Coin-Op Collection", variable=self.coinop_var).pack(anchor="w", padx=10,
                                                                                               pady=2)
        ttk.Checkbutton(other_frame, text="Arcade Offset", variable=self.arcade_offset_var).pack(anchor="w", padx=10,
                                                                                                 pady=2)
        ttk.Checkbutton(other_frame, text="LLAPI Forks Folder", variable=self.llapi_var).pack(anchor="w", padx=10,
                                                                                              pady=2)
        ttk.Checkbutton(other_frame, text="Unofficial Distribution", variable=self.unofficial_var).pack(anchor="w",
                                                                                                        padx=10, pady=2)
        ttk.Checkbutton(other_frame, text="Y/C Builds (Special VGA Cable Required)", variable=self.yc_var).pack(
            anchor="w", padx=10, pady=2)
        ttk.Checkbutton(other_frame, text="agg23’s MiSTer Cores", variable=self.agg23_var).pack(anchor="w", padx=10,
                                                                                                pady=2)
        ttk.Checkbutton(other_frame, text="Alt Cores", variable=self.altcores_var).pack(anchor="w", padx=10, pady=2)
        ttk.Checkbutton(other_frame, text="Dual RAM Console Cores", variable=self.dualram_var).pack(anchor="w", padx=10,
                                                                                                    pady=2)

        # ===== Tools & Scripts =====
        tools_frame = ttk.LabelFrame(frame, text="Tools & Scripts")
        tools_frame.pack(fill="x", pady=8)

        self.arcade_org_var = tk.BooleanVar()
        self.mrext_var = tk.BooleanVar()
        self.sam_var = tk.BooleanVar()
        self.tty2oled_var = tk.BooleanVar()
        self.i2c2oled_var = tk.BooleanVar()
        self.retrospy_var = tk.BooleanVar()

        ttk.Checkbutton(
            tools_frame,
            text="Arcade Organizer (folder structure)",
            variable=self.arcade_org_var
        ).pack(anchor="w", padx=10, pady=2)

        ttk.Checkbutton(
            tools_frame,
            text="MiSTer Extensions (Wizzo Scripts)",
            variable=self.mrext_var
        ).pack(anchor="w", padx=10, pady=2)

        ttk.Checkbutton(
            tools_frame,
            text="MiSTer Super Attract Mode",
            variable=self.sam_var
        ).pack(anchor="w", padx=10, pady=2)

        ttk.Checkbutton(
            tools_frame,
            text="tty2oled Add-on Script",
            variable=self.tty2oled_var
        ).pack(anchor="w", padx=10, pady=2)

        ttk.Checkbutton(
            tools_frame,
            text="i2c2oled Add-on Script",
            variable=self.i2c2oled_var
        ).pack(anchor="w", padx=10, pady=2)

        ttk.Checkbutton(
            tools_frame,
            text="RetroSpy Utility",
            variable=self.retrospy_var
        ).pack(anchor="w", padx=10, pady=2)

        # ===== Extra Content =====
        extra_frame = ttk.LabelFrame(frame, text="Extra Content")
        extra_frame.pack(fill="x", pady=8)

        self.bios_var = tk.BooleanVar()
        self.arcade_roms_var = tk.BooleanVar()
        self.bootroms_var = tk.BooleanVar()
        self.gbaborders_var = tk.BooleanVar()
        self.insert_coin_var = tk.BooleanVar()

        ttk.Checkbutton(
            extra_frame,
            text="BIOS Database",
            variable=self.bios_var
        ).pack(anchor="w", padx=10, pady=2)

        ttk.Checkbutton(
            extra_frame,
            text="Arcade ROMs Database",
            variable=self.arcade_roms_var
        ).pack(anchor="w", padx=10, pady=2)

        ttk.Checkbutton(
            extra_frame,
            text="Uberyoji Boot ROMs",
            variable=self.bootroms_var
        ).pack(anchor="w", padx=10, pady=2)

        ttk.Checkbutton(
            extra_frame,
            text="Dinierto GBA Borders",
            variable=self.gbaborders_var
        ).pack(anchor="w", padx=10, pady=2)

        ttk.Checkbutton(
            extra_frame,
            text="Insert-Coin",
            variable=self.insert_coin_var
        ).pack(anchor="w", padx=10, pady=2)

        # ===== Wallpapers =====
        self.wallpapers_var = tk.BooleanVar()
        self.wallpapers_source_var = tk.StringVar()

        ttk.Checkbutton(
            extra_frame,
            text="Ranny Snice Wallpapers",
            variable=self.wallpapers_var,
            command=self.update_wallpaper_state
        ).pack(anchor="w", padx=10, pady=2)

        wallpaper_frame = ttk.Frame(extra_frame)
        wallpaper_frame.pack(fill="x", padx=25, pady=2)

        ttk.Label(wallpaper_frame, text="Source:").pack(side="left")

        self.wallpaper_combo = ttk.Combobox(
            wallpaper_frame,
            textvariable=self.wallpapers_source_var,
            state="readonly",
            values=[
                "16:9 Wallpapers",
                "4:3 Wallpapers",
                "All Wallpapers"
            ],
            width=20
        )
        self.wallpaper_combo.pack(side="left", padx=10)

        self.wallpaper_combo.set("All Wallpapers")

        # Spacer so last section is not glued to bottom bar
        ttk.Frame(frame, height=8).pack()

        # ===== Fixed bottom buttons =====
        button_bar = ttk.Frame(outer)
        button_bar.pack(fill="x", side="bottom", pady=(10, 0))

        ttk.Separator(button_bar, orient="horizontal").pack(fill="x", pady=(0, 10))

        button_row = ttk.Frame(button_bar)
        button_row.pack()

        ttk.Button(
            button_row,
            text="Save",
            width=12,
            command=self.save_update_all_config
        ).pack(side="left", padx=5)

        ttk.Button(
            button_row,
            text="Close",
            width=12,
            command=_close_popup
        ).pack(side="left", padx=5)

        # Load current configuration AFTER UI is built
        self.load_update_all_config()
        self.update_jt_beta_state()
        self.update_wallpaper_state()
        canvas.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _read_remote_text(self, sftp, path, default=""):
        try:
            with sftp.open(path, "r") as f:
                data = f.read()
                if isinstance(data, bytes):
                    return data.decode()
                return data
        except Exception:
            return default

    def _write_remote_text(self, sftp, path, text):
        with sftp.open(path, "w") as f:
            f.write(text)

    def _split_downloader_paths(self):
        return {
            "main": "/media/fat/downloader.ini",
            "arcade": "/media/fat/downloader_arcade_roms_db.ini",
            "bios": "/media/fat/downloader_bios_db.ini",
        }

    def _read_downloader_files(self, sftp):
        paths = self._split_downloader_paths()
        return {
            "main": self._read_remote_text(sftp, paths["main"], ""),
            "arcade": self._read_remote_text(sftp, paths["arcade"], ""),
            "bios": self._read_remote_text(sftp, paths["bios"], ""),
        }

    def _remove_section_from_lines(self, lines, section):
        new_lines = []
        skip = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("[") and stripped.endswith("]"):
                skip = (stripped.strip("[]") == section)

            if not skip:
                new_lines.append(line)

        return new_lines

    def _extract_section_from_lines(self, lines, section):
        section_lines = []
        capturing = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("[") and stripped.endswith("]"):
                current = stripped.strip("[]")
                if current == section:
                    capturing = True
                    section_lines = [line]
                    continue
                elif capturing:
                    break

            if capturing:
                section_lines.append(line)

        return section_lines

    def _upsert_section_lines(self, lines, section, new_section_lines):
        lines = self._remove_section_from_lines(lines, section)

        while lines and not lines[0].strip():
            lines.pop(0)

        while lines and not lines[-1].strip():
            lines.pop()

        lines.extend(new_section_lines)
        return lines

    def _section_enabled_in_text(self, text, section):
        return f"[{section}]" in text and f";[{section}]" not in text

    def ensure_split_downloader_configs(self, sftp):
        paths = self._split_downloader_paths()

        main_lines = self._read_remote_text(sftp, paths["main"], "").splitlines()
        arcade_lines = self._read_remote_text(sftp, paths["arcade"], "").splitlines()
        bios_lines = self._read_remote_text(sftp, paths["bios"], "").splitlines()

        changed_main = False
        changed_arcade = False
        changed_bios = False

        arcade_section = self._extract_section_from_lines(main_lines, "arcade_roms_db")
        if arcade_section:
            arcade_lines = self._upsert_section_lines(
                arcade_lines,
                "arcade_roms_db",
                arcade_section
            )
            main_lines = self._remove_section_from_lines(main_lines, "arcade_roms_db")
            changed_main = True
            changed_arcade = True

        bios_section = self._extract_section_from_lines(main_lines, "bios_db")
        if bios_section:
            bios_lines = self._upsert_section_lines(
                bios_lines,
                "bios_db",
                bios_section
            )
            main_lines = self._remove_section_from_lines(main_lines, "bios_db")
            changed_main = True
            changed_bios = True

        if changed_main:
            self._write_remote_text(sftp, paths["main"], "\n".join(main_lines).rstrip() + "\n")
        if changed_arcade:
            self._write_remote_text(sftp, paths["arcade"], "\n".join(arcade_lines).rstrip() + "\n")
        if changed_bios:
            self._write_remote_text(sftp, paths["bios"], "\n".join(bios_lines).rstrip() + "\n")

    def load_update_all_config(self):

        try:
            sftp = self.connection.client.open_sftp()

            # Migrate old entries from downloader.ini if needed
            self.ensure_split_downloader_configs(sftp)

            files = self._read_downloader_files(sftp)
            ini_data = "\n".join([
                files["main"],
                files["arcade"],
                files["bios"]
            ])

            # === Read update_all.json ===
            json_path = "/media/fat/Scripts/.config/update_all/update_all.json"
            try:
                with sftp.open(json_path, "r") as f:
                    json_data = json.loads(f.read().decode())
            except Exception:
                json_data = {}

            sftp.close()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load config:\n{e}")
            return

        def is_enabled(section):
            return self._section_enabled_in_text(ini_data, section)

        # === Main Cores ===
        self.main_cores_var.set(is_enabled("distribution_mister"))

        if "aitorgomez.net" in ini_data:
            self.main_source_var.set("AitorGomez fork")
        elif "MiSTer-DB9" in ini_data:
            self.main_source_var.set("DB9 / SNAC8 forks with ENCC")
        else:
            self.main_source_var.set("MiSTer-devel (Recommended)")

        # === JTCores ===
        self.jtcores_var.set(is_enabled("jtcores"))

        # === Other Cores ===
        self.coinop_var.set(is_enabled("Coin-OpCollection/Distribution-MiSTerFPGA"))
        self.arcade_offset_var.set(is_enabled("arcade_offset_folder"))
        self.llapi_var.set(is_enabled("llapi_folder"))
        self.unofficial_var.set(is_enabled("theypsilon_unofficial_distribution"))
        self.yc_var.set(is_enabled("MikeS11/YC_Builds-MiSTer"))
        self.agg23_var.set(is_enabled("agg23_db"))
        self.altcores_var.set(is_enabled("ajgowans/alt-cores"))
        self.dualram_var.set(is_enabled("TheJesusFish/Dual-Ram-Console-Cores"))

        # === JSON ===
        self.jtbeta_var.set(json_data.get("download_beta_cores", False))
        self.arcade_org_var.set(json_data.get("introduced_arcade_names_txt", False))

        # === Tools & Scripts (INI) ===
        self.mrext_var.set(is_enabled("mrext/all"))
        self.sam_var.set(is_enabled("MiSTer_SAM_files"))
        self.tty2oled_var.set(is_enabled("tty2oled_files"))
        self.i2c2oled_var.set(is_enabled("i2c2oled_files"))
        self.retrospy_var.set(is_enabled("retrospy/retrospy-MiSTer"))

        # === Extra Content ===
        self.bios_var.set(is_enabled("bios_db"))
        self.arcade_roms_var.set(is_enabled("arcade_roms_db"))
        self.bootroms_var.set(is_enabled("uberyoji_mister_boot_roms_mgl"))
        self.gbaborders_var.set(is_enabled("Dinierto/MiSTer-GBA-Borders"))
        self.insert_coin_var.set(is_enabled("funkycochise/Insert-Coin"))

        # === Wallpapers ===
        wallpaper_enabled = is_enabled("Ranny-Snice/Ranny-Snice-Wallpapers")
        self.wallpapers_var.set(wallpaper_enabled)

        if wallpaper_enabled:
            if "filter = ar16-9" in ini_data:
                self.wallpapers_source_var.set("16:9 Wallpapers")
            elif "filter = ar4-3" in ini_data:
                self.wallpapers_source_var.set("4:3 Wallpapers")
            else:
                self.wallpapers_source_var.set("All Wallpapers")
        else:
            self.wallpapers_source_var.set("All Wallpapers")

        self.update_wallpaper_state()
        self.update_jt_beta_state()

    def update_jt_beta_state(self):
        if self.jtcores_var.get():
            self.jtbeta_check.config(state="normal")
        else:
            self.jtbeta_check.config(state="disabled")

    def update_wallpaper_state(self):
        if self.wallpapers_var.get():
            self.wallpaper_combo.config(state="readonly")
        else:
            self.wallpaper_combo.config(state="disabled")

    def save_update_all_config(self):

        try:
            sftp = self.connection.client.open_sftp()

            # Migrate old entries first
            self.ensure_split_downloader_configs(sftp)

            paths = self._split_downloader_paths()
            json_path = "/media/fat/Scripts/.config/update_all/update_all.json"

            main_lines = self._read_remote_text(sftp, paths["main"], "").splitlines()
            arcade_lines = self._read_remote_text(sftp, paths["arcade"], "").splitlines()
            bios_lines = self._read_remote_text(sftp, paths["bios"], "").splitlines()

            try:
                with sftp.open(json_path, "r") as f:
                    json_data = json.loads(f.read().decode())
            except Exception:
                json_data = {}

            # =========================
            # UPDATE JSON
            # =========================

            json_data["download_beta_cores"] = self.jtbeta_var.get()

            # =========================
            # HELPER: REMOVE SECTION
            # =========================

            def remove_section(lines, section):
                new_lines = []
                skip = False

                for line in lines:
                    stripped = line.strip()

                    if stripped.startswith("[") and stripped.endswith("]"):
                        skip = (stripped.strip("[]") == section)

                    if not skip:
                        new_lines.append(line)

                return new_lines

            # =========================
            # OTHER HELPER
            # =========================

            def handle_simple_section(section, enabled, lines, content_lines):
                lines = remove_section(lines, section)

                while lines and not lines[0].strip():
                    lines.pop(0)

                while lines and not lines[-1].strip():
                    lines.pop()

                if enabled:
                    if lines:
                        lines += [""] + content_lines
                    else:
                        lines += content_lines

                return lines

            # =========================
            # MAIN CORES (distribution_mister)
            # =========================

            main_lines = remove_section(main_lines, "distribution_mister")

            if self.main_cores_var.get():

                source = self.main_source_var.get()

                if "AitorGomez" in source:
                    url = "https://www.aitorgomez.net/static/mistermain/db.json.zip"
                elif "DB9" in source:
                    url = "https://raw.githubusercontent.com/MiSTer-DB9/Distribution_MiSTer/main/dbencc.json.zip"
                else:
                    url = "https://raw.githubusercontent.com/MiSTer-devel/Distribution_MiSTer/main/db.json.zip"

                if main_lines and main_lines[-1].strip():
                    main_lines += [""]

                main_lines += [
                    "[distribution_mister]",
                    f"db_url = {url}"
                ]

            # =========================
            # JTCORES
            # =========================

            main_lines = remove_section(main_lines, "jtcores")

            if self.jtcores_var.get():
                if main_lines and main_lines[-1].strip():
                    main_lines += [""]

                main_lines += [
                    "[jtcores]",
                    "db_url = https://raw.githubusercontent.com/jotego/jtcores_mister/main/jtbindb.json.zip",
                    "filter = [MiSTer]"
                ]

            # =========================
            # OTHER CORES
            # =========================

            main_lines = handle_simple_section(
                "Coin-OpCollection/Distribution-MiSTerFPGA",
                self.coinop_var.get(),
                main_lines,
                [
                    "[Coin-OpCollection/Distribution-MiSTerFPGA]",
                    "db_url = https://raw.githubusercontent.com/Coin-OpCollection/Distribution-MiSTerFPGA/db/db.json.zip"
                ]
            )

            main_lines = handle_simple_section(
                "arcade_offset_folder",
                self.arcade_offset_var.get(),
                main_lines,
                [
                    "[arcade_offset_folder]",
                    "db_url = https://raw.githubusercontent.com/Toryalai1/Arcade_Offset/db/arcadeoffsetdb.json.zip"
                ]
            )

            main_lines = handle_simple_section(
                "llapi_folder",
                self.llapi_var.get(),
                main_lines,
                [
                    "[llapi_folder]",
                    "db_url = https://raw.githubusercontent.com/MiSTer-LLAPI/LLAPI_folder_MiSTer/main/llapidb.json.zip"
                ]
            )

            main_lines = handle_simple_section(
                "theypsilon_unofficial_distribution",
                self.unofficial_var.get(),
                main_lines,
                [
                    "[theypsilon_unofficial_distribution]",
                    "db_url = https://raw.githubusercontent.com/theypsilon/Distribution_Unofficial_MiSTer/main/unofficialdb.json.zip"
                ]
            )

            main_lines = handle_simple_section(
                "MikeS11/YC_Builds-MiSTer",
                self.yc_var.get(),
                main_lines,
                [
                    "[MikeS11/YC_Builds-MiSTer]",
                    "db_url = https://raw.githubusercontent.com/MikeS11/YC_Builds-MiSTer/db/db.json.zip"
                ]
            )

            main_lines = handle_simple_section(
                "agg23_db",
                self.agg23_var.get(),
                main_lines,
                [
                    "[agg23_db]",
                    "db_url = https://raw.githubusercontent.com/agg23/mister-repository/db/manifest.json"
                ]
            )

            main_lines = handle_simple_section(
                "ajgowans/alt-cores",
                self.altcores_var.get(),
                main_lines,
                [
                    "[ajgowans/alt-cores]",
                    "db_url = https://raw.githubusercontent.com/ajgowans/alt-cores/db/db.json.zip"
                ]
            )

            main_lines = handle_simple_section(
                "TheJesusFish/Dual-Ram-Console-Cores",
                self.dualram_var.get(),
                main_lines,
                [
                    "[TheJesusFish/Dual-Ram-Console-Cores]",
                    "db_url = https://raw.githubusercontent.com/TheJesusFish/Dual-Ram-Console-Cores/db/db.json.zip"
                ]
            )

            # =========================
            # TOOLS & SCRIPTS
            # =========================

            json_data["introduced_arcade_names_txt"] = self.arcade_org_var.get()

            main_lines = handle_simple_section(
                "mrext/all",
                self.mrext_var.get(),
                main_lines,
                [
                    "[mrext/all]",
                    "db_url = https://raw.githubusercontent.com/wizzomafizzo/mrext/main/releases/all.json"
                ]
            )

            main_lines = handle_simple_section(
                "MiSTer_SAM_files",
                self.sam_var.get(),
                main_lines,
                [
                    "[MiSTer_SAM_files]",
                    "db_url = https://raw.githubusercontent.com/mrchrisster/MiSTer_SAM/db/db.json.zip"
                ]
            )

            main_lines = handle_simple_section(
                "tty2oled_files",
                self.tty2oled_var.get(),
                main_lines,
                [
                    "[tty2oled_files]",
                    "db_url = https://raw.githubusercontent.com/venice1200/MiSTer_tty2oled/main/tty2oleddb.json"
                ]
            )

            main_lines = handle_simple_section(
                "i2c2oled_files",
                self.i2c2oled_var.get(),
                main_lines,
                [
                    "[i2c2oled_files]",
                    "db_url = https://raw.githubusercontent.com/venice1200/MiSTer_i2c2oled/main/i2c2oleddb.json"
                ]
            )

            main_lines = handle_simple_section(
                "retrospy/retrospy-MiSTer",
                self.retrospy_var.get(),
                main_lines,
                [
                    "[retrospy/retrospy-MiSTer]",
                    "db_url = https://raw.githubusercontent.com/retrospy/retrospy-MiSTer/db/db.json.zip"
                ]
            )

            # =========================
            # EXTRA CONTENT
            # =========================

            # bios_db goes into downloader_bios_db.ini
            bios_lines = handle_simple_section(
                "bios_db",
                self.bios_var.get(),
                bios_lines,
                [
                    "[bios_db]",
                    "db_url = https://raw.githubusercontent.com/ajgowans/BiosDB_MiSTer/db/bios_db.json.zip"
                ]
            )

            # arcade_roms_db goes into downloader_arcade_roms_db.ini
            arcade_lines = handle_simple_section(
                "arcade_roms_db",
                self.arcade_roms_var.get(),
                arcade_lines,
                [
                    "[arcade_roms_db]",
                    "db_url = https://raw.githubusercontent.com/zakk4223/ArcadeROMsDB_MiSTer/db/arcade_roms_db.json.zip"
                ]
            )

            # Safety cleanup, never leave these in downloader.ini
            main_lines = remove_section(main_lines, "bios_db")
            main_lines = remove_section(main_lines, "arcade_roms_db")

            # These still stay in downloader.ini
            main_lines = handle_simple_section(
                "uberyoji_mister_boot_roms_mgl",
                self.bootroms_var.get(),
                main_lines,
                [
                    "[uberyoji_mister_boot_roms_mgl]",
                    "db_url = https://raw.githubusercontent.com/uberyoji/mister-boot-roms/main/db/uberyoji_mister_boot_roms_mgl.json"
                ]
            )

            main_lines = handle_simple_section(
                "Dinierto/MiSTer-GBA-Borders",
                self.gbaborders_var.get(),
                main_lines,
                [
                    "[Dinierto/MiSTer-GBA-Borders]",
                    "db_url = https://raw.githubusercontent.com/Dinierto/MiSTer-GBA-Borders/db/db.json.zip"
                ]
            )

            main_lines = handle_simple_section(
                "funkycochise/Insert-Coin",
                self.insert_coin_var.get(),
                main_lines,
                [
                    "[funkycochise/Insert-Coin]",
                    "db_url = https://raw.githubusercontent.com/funkycochise/Insert-Coin/db/db.json.zip"
                ]
            )

            # =========================
            # WALLPAPERS
            # =========================

            main_lines = remove_section(
                main_lines,
                "Ranny-Snice/Ranny-Snice-Wallpapers"
            )

            if self.wallpapers_var.get():

                source = self.wallpapers_source_var.get()

                if "16:9" in source:
                    filter_value = "ar16-9"
                elif "4:3" in source:
                    filter_value = "ar4-3"
                else:
                    filter_value = "all"

                if main_lines and main_lines[-1].strip():
                    main_lines += [""]

                main_lines += [
                    "[Ranny-Snice/Ranny-Snice-Wallpapers]",
                    "db_url = https://raw.githubusercontent.com/Ranny-Snice/Ranny-Snice-Wallpapers/db/db.json.zip",
                    f"filter = {filter_value}"
                ]

            # =========================
            # WRITE FILES BACK
            # =========================

            def normalize_ini_lines(lines):
                lines = list(lines)

                while lines and not lines[0].strip():
                    lines.pop(0)

                while lines and not lines[-1].strip():
                    lines.pop()

                return lines

            self.connection.run_command(
                "mkdir -p /media/fat/Scripts/.config/update_all"
            )

            main_lines = normalize_ini_lines(main_lines)
            arcade_lines = normalize_ini_lines(arcade_lines)
            bios_lines = normalize_ini_lines(bios_lines)

            self._write_remote_text(
                sftp,
                paths["main"],
                "\n".join(main_lines).rstrip() + "\n"
            )

            self._write_remote_text(
                sftp,
                paths["arcade"],
                "\n".join(arcade_lines).rstrip() + "\n"
            )

            self._write_remote_text(
                sftp,
                paths["bios"],
                "\n".join(bios_lines).rstrip() + "\n"
            )

            with sftp.open(json_path, "w") as f:
                f.write(json.dumps(json_data, indent=4))

            sftp.close()

            messagebox.showinfo("Success", "Configuration saved successfully.")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config:\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = MiSTerApp(root)
    root.mainloop()

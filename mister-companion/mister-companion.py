import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import paramiko
import requests
import threading
import subprocess
import json
import os
import base64
import time
import socket
import webbrowser
import sys

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "devices": [],
    "last_connected": None,
    "update_all_installed": False,
    "smb_enabled": False,
    "hide_setup_notice": False
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
        self.root.title("MiSTer Companion v2.0.0 by Anime0t4ku")
        self.root.geometry("900x760")

        # ===== App Icon =====
        try:
            icon = tk.PhotoImage(file=resource_path("icon.png"))
            self.root.iconphoto(True, icon)
        except Exception:
            pass

        self.connection = MiSTerConnection()
        self.config_data = load_config()

        self.console_visible = False

        self.build_ui()
        self.load_devices()
        self.load_last_device()

        self.disable_controls()

        self.root.after(300, self.show_setup_notice)

    # =========================
    # Setup Notice Popup
    # =========================

    def show_setup_notice(self):
        if self.config_data.get("hide_setup_notice"):
            return

        popup = tk.Toplevel(self.root)
        popup.title("MiSTer Setup Required")
        popup.geometry("540x340")
        popup.resizable(False, False)
        popup.grab_set()
        popup.transient(self.root)

        wrapper = ttk.Frame(popup, padding=20)
        wrapper.pack(fill="both", expand=True)

        ttk.Label(wrapper,
                  text="MiSTer Companion Setup",
                  font=("Segoe UI", 13, "bold")).pack(pady=(5, 15))

        ttk.Label(wrapper,
                  text="This application assumes you have already flashed\n"
                       "MiSTerFusion to your SD card.\n\n"
                       "If you have not done so yet, download MiSTerFusion\n"
                       "and flash it using Rufus before continuing.",
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
                   text="Download Rufus",
                   width=18,
                   command=lambda: webbrowser.open(
                       "https://rufus.ie/en/"
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

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.connection_tab = ttk.Frame(notebook)
        self.device_tab = ttk.Frame(notebook)
        self.scripts_tab = ttk.Frame(notebook)
        self.launchers_tab = ttk.Frame(notebook)

        notebook.add(self.connection_tab, text="Connection")
        notebook.add(self.device_tab, text="Device")
        notebook.add(self.scripts_tab, text="Scripts")

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
                   text="Delete Device",
                   command=self.delete_selected_device).pack(side="left", padx=5)

        # ===== Connection Bar =====

        conn_outer = ttk.Frame(self.connection_tab)
        conn_outer.pack(fill="x", padx=20, pady=15)

        conn_frame = ttk.Frame(conn_outer)
        conn_frame.pack()

        ttk.Label(conn_frame, text="IP:").pack(side="left", padx=(0,5))
        self.ip_entry = ttk.Entry(conn_frame, width=18)
        self.ip_entry.pack(side="left", padx=5)

        ttk.Label(conn_frame, text="User:").pack(side="left", padx=(10,5))
        self.username_entry = ttk.Entry(conn_frame, width=12)
        self.username_entry.pack(side="left", padx=5)

        ttk.Label(conn_frame, text="Pass:").pack(side="left", padx=(10,5))
        self.password_entry = ttk.Entry(conn_frame, show="*", width=12)
        self.password_entry.pack(side="left", padx=5)

        self.connect_button = ttk.Button(conn_frame,
                                         text="Connect",
                                         width=12,
                                         command=self.connect)
        self.connect_button.pack(side="left", padx=10)

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
            text="Run Zaparoo",
            width=18,
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

        self.config_data["devices"].append(device)
        self.config_data["last_connected"] = name
        save_config(self.config_data)
        self.load_devices()

    def delete_selected_device(self):
        selected = self.device_combo.get()
        if not selected:
            return

        self.config_data["devices"] = [
            d for d in self.config_data["devices"]
            if d["name"] != selected
        ]
        save_config(self.config_data)
        self.load_devices()

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

    def connect(self):
        ip = self.ip_entry.get().strip()
        username = self.username_entry.get().strip() or "root"
        password = self.password_entry.get().strip() or "1"

        self.set_status("CONNECTING")

        success, message = self.connection.connect(ip, username, password)

        if success:
            self.set_status("CONNECTED")
            self.status_label.config(text=f"Connected ({ip})", foreground="green")
            self.enable_controls()
            self.refresh_storage()
            self.check_services_status()
        else:
            self.set_status("DISCONNECTED")
            self.disable_controls()
            messagebox.showerror("Connection Error", message)

    def enable_controls(self):
        self.run_button.config(state="normal")
        self.explorer_button.config(state="normal")
        self.reboot_button.config(state="normal")

    def disable_controls(self):
        self.install_button.config(state="disabled")
        self.uninstall_button.config(state="disabled")
        self.run_button.config(state="disabled")
        self.enable_smb_button.config(state="disabled")
        self.disable_smb_button.config(state="disabled")
        self.explorer_button.config(state="disabled")
        self.reboot_button.config(state="disabled")

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
        usb = self.connection.run_command("df -h /media/usb* 2>/dev/null | tail -1")

        if usb and "/media/usb" in usb:

            try:
                parts = usb.split()
                size = parts[1]
                avail = parts[3]
                percent = int(parts[4].replace("%", ""))

                self.usb_bar["value"] = percent
                self.usb_label.config(
                    text=f"{avail} free of {size} ({percent}% used)"
                )

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

        # ===== Zaparoo detection =====

        zaparoo_check = self.connection.run_command(
            "test -f /media/fat/Scripts/zaparoo.sh && echo EXISTS"
        )

        zaparoo_installed = "EXISTS" in (zaparoo_check or "")

        first_run_check = self.connection.run_command(
            "test -d /media/fat/zaparoo && echo CONFIG"
        )

        zaparoo_initialized = "CONFIG" in (first_run_check or "")

        if not zaparoo_installed:

            self.zaparoo_status_label.config(
                text="Zaparoo: Not Installed",
                foreground="red"
            )

            self.install_zaparoo_button.config(state="normal")
            self.run_zaparoo_button.config(state="disabled")
            self.uninstall_zaparoo_button.config(state="disabled")

        elif zaparoo_installed and not zaparoo_initialized:

            self.zaparoo_status_label.config(
                text="Zaparoo: First launch required",
                foreground="orange"
            )

            self.install_zaparoo_button.config(state="disabled")
            self.run_zaparoo_button.config(state="normal")
            self.uninstall_zaparoo_button.config(state="normal")

        else:

            self.zaparoo_status_label.config(
                text="Zaparoo: Installed ✓",
                foreground="green"
            )

            self.install_zaparoo_button.config(state="disabled")
            self.run_zaparoo_button.config(state="disabled")
            self.uninstall_zaparoo_button.config(state="normal")

        # ===== migrate_sd detection =====

        migrate_check = self.connection.run_command(
            "test -f /media/fat/Scripts/migrate_sd.sh && echo EXISTS"
        )

        migrate_installed = "EXISTS" in (migrate_check or "")

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

    def update_button_states(self, update_installed=False, smb_enabled=False):

        # update_all buttons
        if update_installed:
            self.install_button.config(state="disabled")
            self.uninstall_button.config(state="normal")
            self.run_button.config(state="normal")
        else:
            self.install_button.config(state="normal")
            self.uninstall_button.config(state="disabled")
            self.run_button.config(state="disabled")

        # SMB buttons
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
            "Continue?"
        )

        if not proceed:
            return

        if not self.console_visible:
            self.console_frame.pack(fill="x", padx=20, pady=10)
            self.console_visible = True

        self.console.delete("1.0", tk.END)

        threading.Thread(
            target=lambda: self.connection.run_command_stream(
                "/media/fat/Scripts/update_all.sh",
                self.log
            )
        ).start()

    def run_zaparoo(self):

        if not self.connection.connected:
            return

        if not self.console_visible:
            self.console_frame.pack(fill="x", padx=20, pady=10)
            self.console_visible = True

        self.console.delete("1.0", tk.END)

        self.log("Starting Zaparoo...\n")

        def worker():

            self.connection.run_command_stream(
                "/media/fat/Scripts/zaparoo.sh",
                self.log
            )

            self.log("\nZaparoo finished.\n")

            self.root.after(
                0,
                lambda: messagebox.askyesno(
                    "Reboot Recommended",
                    "Zaparoo initial setup may require a reboot.\n\nReboot MiSTer now?"
                ) and self.reboot()
            )

        threading.Thread(target=worker).start()

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
                r = requests.get(api_url)
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
                r = requests.get(api_url)
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
            "It cannot be executed from MiSTer Companion.\n\n"
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
                subprocess.Popen(["xdg-open", f"smb://{ip}/"])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", f"smb://{ip}/"])
        except Exception as e:
            messagebox.showerror("Error", f"Unable to open file share:\n{str(e)}")

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


if __name__ == "__main__":
    root = tk.Tk()
    app = MiSTerApp(root)
    root.mainloop()

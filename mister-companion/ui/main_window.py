from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel, QMessageBox

from core.config import load_config, save_config
from core.connection import MiSTerConnection
from core.connection_monitor import ConnectionCheckWorker
from core.device_profiles import (
    add_device,
    delete_device,
    get_device_by_index,
    get_device_by_name,
    get_devices,
    get_profile_sync_roots,
    update_device,
)
from core.profile_folder_sync import profile_assigned_to_ip, profile_removed, profile_renamed
from ui.dialogs.device_dialog import DeviceDialog
from ui.dialogs.network_scanner_dialog import NetworkScannerDialog
from ui.dialogs.setup_notice_dialog import SetupNoticeDialog
from ui.tabs.connection_tab import ConnectionTab
from ui.tabs.device_tab import DeviceTab
from ui.tabs.mister_settings_tab import MiSTerSettingsTab
from ui.tabs.savemanager_tab import SaveManagerTab
from ui.tabs.scripts_tab import ScriptsTab
from ui.tabs.wallpapers_tab import WallpapersTab
from ui.tabs.zapscripts_tab import ZapScriptsTab


BASE_DIR = Path(__file__).resolve().parent.parent
ICON_PATH = BASE_DIR / "assets" / "icon.png"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.connection = MiSTerConnection()
        self.config_data = load_config()

        self.connection_check_worker = None
        self.connection_fail_count = 0
        self.connection_fail_threshold = 3

        self.reboot_reconnect_worker = None
        self.reboot_reconnect_attempts = 0
        self.reboot_reconnect_max_attempts = 24
        self.reboot_reconnect_host = ""
        self.reboot_reconnect_username = ""
        self.reboot_reconnect_password = ""

        self.setWindowTitle("MiSTer Companion v3.0.0-Beta-2 By Anime0t4ku")
        self.resize(900, 900)

        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(8, 8, 8, 8)
        central_layout.setSpacing(6)

        self.tabs = QTabWidget()
        central_layout.addWidget(self.tabs)

        self.connection_status_label = QLabel("Status: Disconnected")
        central_layout.addWidget(self.connection_status_label)
        self.set_connection_status("Status: Disconnected")

        self.setCentralWidget(central_widget)

        self.connection_tab = ConnectionTab(self)
        self.tabs.addTab(self.connection_tab, "Connection")

        self.device_tab = DeviceTab(self)
        self.tabs.addTab(self.device_tab, "Device")

        self.mister_settings_tab = MiSTerSettingsTab(self)
        self.tabs.addTab(self.mister_settings_tab, "MiSTer Settings")

        self.scripts_tab = ScriptsTab(self)
        self.tabs.addTab(self.scripts_tab, "Scripts")

        self.zapscripts_tab = ZapScriptsTab(self)
        self.tabs.addTab(self.zapscripts_tab, "ZapScripts")

        self.savemanager_tab = SaveManagerTab(self)
        self.tabs.addTab(self.savemanager_tab, "SaveManager")

        self.wallpapers_tab = WallpapersTab(self)
        self.tabs.addTab(self.wallpapers_tab, "Wallpapers")

        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.load_devices()
        self.load_last_device()

        self.connection_monitor_timer = QTimer(self)
        self.connection_monitor_timer.timeout.connect(self.check_connection_status)
        self.connection_monitor_timer.start(5000)

        self.reboot_reconnect_timer = QTimer(self)
        self.reboot_reconnect_timer.timeout.connect(self.try_reconnect_after_reboot)

        self.update_all_tab_states()

        QTimer.singleShot(300, self.show_setup_notice)

    def show_setup_notice(self):
        if self.config_data.get("hide_setup_notice"):
            return

        dialog = SetupNoticeDialog(self)

        if dialog.exec() == dialog.DialogCode.Accepted:
            if dialog.dont_show_again:
                self.config_data["hide_setup_notice"] = True
                save_config(self.config_data)

    def set_connection_status(self, text: str):
        self.connection_status_label.setText(text)

        if "Connected" in text:
            self.connection_status_label.setStyleSheet("color: #2ecc71; font-weight: bold;")
        elif "Disconnected" in text:
            self.connection_status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        elif "Connecting" in text:
            self.connection_status_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        elif "Lost" in text:
            self.connection_status_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        elif "Rebooting" in text:
            self.connection_status_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        elif "Waiting" in text:
            self.connection_status_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        else:
            self.connection_status_label.setStyleSheet("")

    def update_all_tab_states(self):
        if hasattr(self, "device_tab"):
            self.device_tab.update_connection_state()

        if hasattr(self, "mister_settings_tab"):
            self.mister_settings_tab.update_connection_state()

        if hasattr(self, "scripts_tab"):
            self.scripts_tab.update_connection_state()

        if hasattr(self, "zapscripts_tab"):
            self.zapscripts_tab.update_connection_state()

        if hasattr(self, "savemanager_tab"):
            self.savemanager_tab.update_connection_state()

        if hasattr(self, "wallpapers_tab"):
            self.wallpapers_tab.update_connection_state()

    def on_tab_changed(self, index):
        current_widget = self.tabs.widget(index)

        if hasattr(self, "mister_settings_tab"):
            if current_widget is self.mister_settings_tab and self.connection.is_connected():
                self.mister_settings_tab.load_mister_ini_into_ui(silent=True)
                self.mister_settings_tab.load_mister_ini_advanced()
                return

        if hasattr(self, "device_tab"):
            if current_widget is self.device_tab and self.connection.is_connected():
                self.device_tab.refresh_info()
                return

        if hasattr(self, "scripts_tab"):
            if current_widget is self.scripts_tab and self.connection.is_connected():
                self.scripts_tab.refresh_status()
                return

        if hasattr(self, "zapscripts_tab"):
            if current_widget is self.zapscripts_tab and self.connection.is_connected():
                self.zapscripts_tab.refresh_status()
                return

        if hasattr(self, "savemanager_tab"):
            if current_widget is self.savemanager_tab:
                self.savemanager_tab.update_connection_state()

        if hasattr(self, "wallpapers_tab"):
            if current_widget is self.wallpapers_tab and self.connection.is_connected():
                self.wallpapers_tab.refresh_status()
                return

    def check_connection_status(self):
        if not self.connection.is_connected():
            return

        if self.reboot_reconnect_timer.isActive():
            return

        if self.connection_check_worker is not None and self.connection_check_worker.isRunning():
            return

        host = self.connection.host
        if not host:
            return

        self.connection_check_worker = ConnectionCheckWorker(host, port=22, timeout=2)
        self.connection_check_worker.result.connect(self.on_connection_check_result)
        self.connection_check_worker.finished.connect(self.on_connection_check_worker_finished)
        self.connection_check_worker.start()

    def on_connection_check_worker_finished(self):
        self.connection_check_worker = None

    def on_connection_check_result(self, ok: bool):
        if self.reboot_reconnect_timer.isActive():
            self.connection_fail_count = 0
            return

        if ok:
            self.connection_fail_count = 0
            return

        self.connection_fail_count += 1

        if self.connection_fail_count < self.connection_fail_threshold:
            return

        self.handle_connection_lost()

    def handle_connection_lost(self):
        self.connection_fail_count = 0

        try:
            self.connection.disconnect()
        except Exception:
            self.connection.mark_disconnected()

        self.set_connection_status("Status: Connection Lost")
        self.connection_tab.apply_disconnected_state()
        self.update_all_tab_states()

        QMessageBox.warning(
            self,
            "Connection Lost",
            "Connection to MiSTer was lost."
        )

    def start_reboot_reconnect_polling(self):
        host = self.connection.host
        username = self.connection.username
        password = self.connection.password

        if not host or not username:
            self.set_connection_status("Status: Disconnected")
            self.connection_tab.apply_disconnected_state()
            self.update_all_tab_states()
            return

        self.reboot_reconnect_host = host
        self.reboot_reconnect_username = username
        self.reboot_reconnect_password = password

        self.connection_fail_count = 0
        self.connection.mark_disconnected()
        self.connection_tab.apply_disconnected_state()
        self.update_all_tab_states()

        self.reboot_reconnect_attempts = 0
        self.set_connection_status("Status: Rebooting...")
        self.reboot_reconnect_timer.start(5000)

    def try_reconnect_after_reboot(self):
        if self.reboot_reconnect_worker is not None and self.reboot_reconnect_worker.isRunning():
            return

        host = self.reboot_reconnect_host
        if not host:
            self.reboot_reconnect_timer.stop()
            self.set_connection_status("Status: Disconnected")
            return

        self.set_connection_status("Status: Waiting for MiSTer...")

        self.reboot_reconnect_worker = ConnectionCheckWorker(host, port=22, timeout=2)
        self.reboot_reconnect_worker.result.connect(self.on_reboot_port_check_result)
        self.reboot_reconnect_worker.finished.connect(self.on_reboot_reconnect_worker_finished)
        self.reboot_reconnect_worker.start()

    def on_reboot_reconnect_worker_finished(self):
        self.reboot_reconnect_worker = None

    def on_reboot_port_check_result(self, ok: bool):
        if not ok:
            self.reboot_reconnect_attempts += 1

            if self.reboot_reconnect_attempts >= self.reboot_reconnect_max_attempts:
                self.reboot_reconnect_timer.stop()
                self.set_connection_status("Status: Disconnected")
                QMessageBox.warning(
                    self,
                    "Reconnect Failed",
                    "MiSTer did not come back online in time."
                )
            return

        host = self.reboot_reconnect_host
        username = self.reboot_reconnect_username
        password = self.reboot_reconnect_password

        try:
            success = self.connection.connect(host, username, password)
        except Exception:
            success = False

        if success:
            self.reboot_reconnect_timer.stop()
            self.reboot_reconnect_attempts = 0
            self.connection_fail_count = 0
            self.reboot_reconnect_host = ""
            self.reboot_reconnect_username = ""
            self.reboot_reconnect_password = ""

            self.set_connection_status(f"Status: Connected to {host}")
            self.connection_tab.apply_connected_state()
            self.update_all_tab_states()
        else:
            self.reboot_reconnect_attempts += 1

            if self.reboot_reconnect_attempts >= self.reboot_reconnect_max_attempts:
                self.reboot_reconnect_timer.stop()
                self.set_connection_status("Status: Disconnected")
                QMessageBox.warning(
                    self,
                    "Reconnect Failed",
                    "MiSTer is reachable again, but automatic reconnect failed."
                )

    def connect_to_mister(self):
        host = self.connection_tab.ip_input.text().strip()
        username = self.connection_tab.user_input.text().strip() or "root"
        password = self.connection_tab.pass_input.text() or "1"

        if not host:
            QMessageBox.warning(self, "Error", "IP Address is required.")
            return

        self.set_connection_status("Status: Connecting...")

        try:
            success = self.connection.connect(host, username, password)
        except Exception as e:
            success = False
            error_message = str(e)
        else:
            error_message = "Unable to connect to MiSTer."

        if not success:
            self.set_connection_status("Status: Disconnected")
            self.connection_tab.apply_disconnected_state()
            self.update_all_tab_states()
            QMessageBox.warning(self, "Connection Failed", error_message)
            return

        selected_name = self.connection_tab.get_selected_profile_name()
        if selected_name:
            self.config_data["last_connected"] = selected_name
            save_config(self.config_data)

        self.set_connection_status(f"Status: Connected to {host}")
        self.connection_tab.apply_connected_state()
        self.update_all_tab_states()

    def disconnect_from_mister(self):
        try:
            self.connection.disconnect()
        except Exception:
            self.connection.mark_disconnected()

        self.reboot_reconnect_timer.stop()
        self.reboot_reconnect_attempts = 0
        self.reboot_reconnect_host = ""
        self.reboot_reconnect_username = ""
        self.reboot_reconnect_password = ""

        self.connection_fail_count = 0
        self.set_connection_status("Status: Disconnected")
        self.connection_tab.apply_disconnected_state()
        self.update_all_tab_states()

    def open_network_scanner(self):
        dialog = NetworkScannerDialog(self)
        dialog.exec()

    def get_profile_sync_roots(self):
        return get_profile_sync_roots()

    def load_devices(self):
        devices = get_devices(self.config_data)
        self.connection_tab.set_profiles(devices)

    def load_last_device(self):
        last = self.config_data.get("last_connected")
        if not last:
            return

        device = get_device_by_name(self.config_data, last)
        if not device:
            return

        devices = get_devices(self.config_data)

        self.connection_tab.set_connection_fields(
            device.get("ip", ""),
            device.get("username", "root"),
            device.get("password", "1")
        )
        self.connection_tab.set_profiles(devices, selected_name=last)

    def load_selected_device(self, index):
        device = get_device_by_index(self.config_data, index)
        if not device:
            return

        self.connection_tab.set_connection_fields(
            device.get("ip", ""),
            device.get("username", "root"),
            device.get("password", "1")
        )

    def save_device(self):
        dialog = DeviceDialog(
            self,
            title="Save Device",
            device={
                "name": "",
                "ip": self.connection_tab.ip_input.text().strip(),
                "username": self.connection_tab.user_input.text().strip() or "root",
                "password": self.connection_tab.pass_input.text() or "1"
            }
        )

        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        device = dialog.get_device_data()

        if not device["name"]:
            QMessageBox.warning(self, "Error", "Device name is required.")
            return

        if not device["ip"]:
            QMessageBox.warning(self, "Error", "IP Address is required.")
            return

        ok, result = add_device(self.config_data, device)
        if not ok:
            QMessageBox.warning(self, "Error", result)
            return

        profile_assigned_to_ip(
            self.get_profile_sync_roots(),
            device["ip"],
            device["name"]
        )

        devices = get_devices(self.config_data)
        self.load_devices()
        self.connection_tab.set_profiles(devices, selected_name=device["name"])
        self.connection_tab.set_connection_fields(
            device["ip"],
            device["username"],
            device["password"]
        )

    def edit_device(self):
        index = self.connection_tab.profile_selector.currentIndex()
        current_device = get_device_by_index(self.config_data, index)

        if not current_device:
            QMessageBox.warning(self, "Error", "Select a device first.")
            return

        dialog = DeviceDialog(
            self,
            title="Edit Device",
            device=current_device
        )

        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        updated_device_data = dialog.get_device_data()

        if not updated_device_data["name"]:
            QMessageBox.warning(self, "Error", "Device name is required.")
            return

        if not updated_device_data["ip"]:
            QMessageBox.warning(self, "Error", "IP Address is required.")
            return

        ok, result, _ = update_device(self.config_data, index, updated_device_data)
        if not ok:
            QMessageBox.warning(self, "Error", result)
            return

        old_name = result["old_name"]
        old_ip = result["old_ip"]
        updated_device = result["updated_device"]

        if old_name != updated_device["name"]:
            profile_renamed(
                self.get_profile_sync_roots(),
                old_name,
                updated_device["name"]
            )
        elif old_ip != updated_device["ip"]:
            profile_assigned_to_ip(
                self.get_profile_sync_roots(),
                updated_device["ip"],
                updated_device["name"]
            )

        devices = get_devices(self.config_data)
        self.load_devices()
        self.connection_tab.set_profiles(devices, selected_name=updated_device["name"])
        self.connection_tab.set_connection_fields(
            updated_device["ip"],
            updated_device["username"],
            updated_device["password"]
        )

    def delete_device(self):
        index = self.connection_tab.profile_selector.currentIndex()

        ok, result, _ = delete_device(self.config_data, index)
        if not ok:
            QMessageBox.warning(self, "Error", result)
            return

        device_name = result["device_name"]
        device_ip = result["device_ip"]

        if self.config_data.get("last_connected") == device_name:
            self.config_data["last_connected"] = None
            save_config(self.config_data)

        if self.connection.is_connected() and self.connection.host == device_ip:
            self.disconnect_from_mister()

        profile_removed(
            self.get_profile_sync_roots(),
            device_name,
            device_ip
        )

        devices = get_devices(self.config_data)
        self.connection_tab.set_profiles(devices)
        self.connection_tab.profile_selector.setCurrentIndex(-1)
        self.connection_tab.set_connection_fields("", "root", "1")
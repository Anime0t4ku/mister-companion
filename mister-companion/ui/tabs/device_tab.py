import sys

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QMessageBox, QProgressBar
)

from core.device_actions import (
    disable_smb_offline,
    disable_smb_remote,
    enable_smb_offline,
    enable_smb_remote,
    get_now_playing,
    get_sd_storage_info,
    get_sd_storage_info_offline,
    get_usb_storage_info,
    is_smb_enabled,
    is_smb_enabled_offline,
    return_to_menu_remote,
)
from core.share_opener import open_local_folder, open_mister_share


class DeviceStatusWorker(QThread):
    result = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, connection, offline_mode=False, sd_root=""):
        super().__init__()
        self.connection = connection
        self.offline_mode = offline_mode
        self.sd_root = sd_root

    def run(self):
        try:
            if self.offline_mode:
                sd_info = None
                smb_enabled = None
                smb_error = ""

                if self.sd_root:
                    sd_info = get_sd_storage_info_offline(self.sd_root)

                    try:
                        smb_enabled = is_smb_enabled_offline(self.sd_root)
                    except Exception as e:
                        smb_error = str(e)

                self.result.emit(
                    {
                        "offline": True,
                        "sd_info": sd_info,
                        "smb_enabled": smb_enabled,
                        "smb_error": smb_error,
                    }
                )
                return

            sd_info = get_sd_storage_info(self.connection)
            usb_info = get_usb_storage_info(self.connection)
            smb_enabled = is_smb_enabled(self.connection)
            now_playing = get_now_playing(self.connection)

            self.result.emit(
                {
                    "offline": False,
                    "sd_info": sd_info,
                    "usb_info": usb_info,
                    "smb_enabled": smb_enabled,
                    "now_playing": now_playing,
                }
            )

        except Exception as e:
            self.error.emit(str(e))


class DeviceTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection
        self.status_worker = None

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(2000)

        self.build_ui()
        self.apply_disconnected_state()

    def build_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(18)

        storage_group = QGroupBox("Storage")
        storage_layout = QVBoxLayout()
        storage_layout.setContentsMargins(16, 18, 16, 18)
        storage_layout.setSpacing(10)

        self.sd_title_label = QLabel("SD Card")
        self.sd_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.storage_bar = QProgressBar()
        self.storage_bar.setRange(0, 100)
        self.storage_bar.setValue(0)
        self.storage_bar.setTextVisible(False)
        self.storage_bar.setFixedWidth(500)

        self.storage_label = QLabel("--")
        self.storage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.usb_title_label = QLabel("USB Storage")
        self.usb_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.usb_bar = QProgressBar()
        self.usb_bar.setRange(0, 100)
        self.usb_bar.setValue(0)
        self.usb_bar.setTextVisible(False)
        self.usb_bar.setFixedWidth(500)

        self.usb_label = QLabel("Checking...")
        self.usb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setFixedWidth(120)

        storage_layout.addWidget(self.sd_title_label)

        sd_bar_row = QHBoxLayout()
        sd_bar_row.addStretch()
        sd_bar_row.addWidget(self.storage_bar)
        sd_bar_row.addStretch()
        storage_layout.addLayout(sd_bar_row)

        storage_layout.addWidget(self.storage_label)
        storage_layout.addSpacing(8)
        storage_layout.addWidget(self.usb_title_label)

        usb_bar_row = QHBoxLayout()
        usb_bar_row.addStretch()
        usb_bar_row.addWidget(self.usb_bar)
        usb_bar_row.addStretch()
        storage_layout.addLayout(usb_bar_row)

        storage_layout.addWidget(self.usb_label)

        refresh_row = QHBoxLayout()
        refresh_row.addStretch()
        refresh_row.addWidget(self.refresh_button)
        refresh_row.addStretch()
        storage_layout.addLayout(refresh_row)

        storage_group.setLayout(storage_layout)

        sharing_group = QGroupBox("File Sharing")
        sharing_layout = QVBoxLayout()
        sharing_layout.setContentsMargins(16, 18, 16, 18)
        sharing_layout.setSpacing(14)

        self.smb_status_label = QLabel(
            "Remote Access: Unknown" if sys.platform == "darwin" else "SMB: Unknown"
        )
        self.smb_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sharing_buttons_row = QHBoxLayout()
        sharing_buttons_row.setSpacing(24)

        self.enable_smb_button = QPushButton(
            "Enable Access" if sys.platform == "darwin" else "Enable SMB"
        )
        self.disable_smb_button = QPushButton(
            "Disable Access" if sys.platform == "darwin" else "Disable SMB"
        )
        self.open_share_button = QPushButton(self.open_share_button_text())

        self.enable_smb_button.setFixedWidth(170)
        self.disable_smb_button.setFixedWidth(170)
        self.open_share_button.setFixedWidth(170)

        sharing_buttons_row.addStretch()
        sharing_buttons_row.addWidget(self.enable_smb_button)
        sharing_buttons_row.addWidget(self.disable_smb_button)
        sharing_buttons_row.addWidget(self.open_share_button)
        sharing_buttons_row.addStretch()

        sharing_layout.addWidget(self.smb_status_label)
        sharing_layout.addLayout(sharing_buttons_row)

        sharing_group.setLayout(sharing_layout)

        power_group = QGroupBox("Power")
        power_layout = QVBoxLayout()
        power_layout.setContentsMargins(16, 18, 16, 18)

        reboot_row = QHBoxLayout()
        reboot_row.setSpacing(16)

        self.return_to_menu_button = QPushButton("Return to Menu")
        self.return_to_menu_button.setFixedWidth(160)

        self.reboot_button = QPushButton("Reboot MiSTer")
        self.reboot_button.setFixedWidth(160)

        reboot_row.addStretch()
        reboot_row.addWidget(self.return_to_menu_button)
        reboot_row.addWidget(self.reboot_button)
        reboot_row.addStretch()

        power_layout.addLayout(reboot_row)
        power_group.setLayout(power_layout)

        self.now_playing_group = QGroupBox("Now Playing")
        now_playing_layout = QVBoxLayout()
        now_playing_layout.setContentsMargins(16, 18, 16, 18)
        now_playing_layout.setSpacing(8)

        self.now_playing_summary_label = QLabel("")
        self.now_playing_summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.now_playing_summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.now_playing_summary_label.setStyleSheet("font-weight: bold;")

        now_playing_layout.addWidget(self.now_playing_summary_label)

        self.now_playing_group.setLayout(now_playing_layout)
        self.now_playing_group.setVisible(False)

        main_layout.addWidget(storage_group)
        main_layout.addWidget(sharing_group)
        main_layout.addWidget(power_group)
        main_layout.addWidget(self.now_playing_group)
        main_layout.addStretch()

        self.setLayout(main_layout)

        self.refresh_button.clicked.connect(self.refresh_info)
        self.enable_smb_button.clicked.connect(self.enable_smb)
        self.disable_smb_button.clicked.connect(self.disable_smb)
        self.open_share_button.clicked.connect(self.open_share)
        self.return_to_menu_button.clicked.connect(self.return_to_menu)
        self.reboot_button.clicked.connect(self.reboot_device)

    def open_share_button_text(self):
        if sys.platform == "darwin":
            return "Open in Finder"

        if sys.platform.startswith("linux"):
            return "Open in File Browser"

        return "Open in Explorer"

    def show_usb_storage(self, visible: bool):
        self.usb_title_label.setVisible(visible)
        self.usb_bar.setVisible(visible)
        self.usb_label.setVisible(visible)

        if not visible:
            self.usb_bar.setValue(0)
            self.usb_bar.setStyleSheet("")
            self.usb_label.setText("")
            self.usb_label.setStyleSheet("")

    def show_refreshing_state(self):
        if self.status_worker is not None and self.status_worker.isRunning():
            return

        if self.is_offline_mode():
            if not self.get_offline_sd_root():
                return
        elif not self.connection.is_connected():
            return

        self.refresh_button.setEnabled(False)

        self.storage_label.setText("Refreshing...")
        self.storage_label.setStyleSheet("color: #1e88e5; font-weight: bold;")

        if not self.is_offline_mode():
            self.show_usb_storage(True)
            self.usb_label.setText("Refreshing...")
            self.usb_label.setStyleSheet("color: #1e88e5; font-weight: bold;")

        self.smb_status_label.setText(
            "Remote Access: Refreshing..."
            if sys.platform == "darwin"
            else "SMB: Refreshing..."
        )
        self.smb_status_label.setStyleSheet("color: #1e88e5; font-weight: bold;")

        self.now_playing_summary_label.setText("")
        self.now_playing_group.setVisible(False)

    def showEvent(self, event):
        super().showEvent(event)

        self.refresh_timer.stop()

        if self.is_offline_mode():
            self.apply_offline_state(lightweight=True)
            self.refresh_info()
            return

        if self.connection.is_connected():
            self.refresh_info()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.refresh_timer.stop()

    def is_offline_mode(self):
        return hasattr(self.main_window, "is_offline_mode") and self.main_window.is_offline_mode()

    def get_offline_sd_root(self):
        if hasattr(self.main_window, "get_offline_sd_root"):
            return self.main_window.get_offline_sd_root()
        return ""

    def update_connection_state(self, lightweight=True):
        self.refresh_timer.stop()

        if self.is_offline_mode():
            self.apply_offline_state(lightweight=lightweight)

            if not lightweight and self.isVisible():
                self.refresh_info()

            return

        if self.connection.is_connected():
            self.apply_connected_state()

            if not lightweight and self.isVisible():
                self.refresh_info()
        else:
            self.apply_disconnected_state()

    def refresh_status(self):
        self.update_connection_state(lightweight=False)

    def apply_connected_state(self):
        self.refresh_button.setEnabled(True)
        self.return_to_menu_button.setEnabled(True)
        self.reboot_button.setEnabled(True)
        self.enable_smb_button.setEnabled(True)
        self.disable_smb_button.setEnabled(True)
        self.open_share_button.setEnabled(False)

        self.enable_smb_button.setText(
            "Enable Access" if sys.platform == "darwin" else "Enable SMB"
        )
        self.disable_smb_button.setText(
            "Disable Access" if sys.platform == "darwin" else "Disable SMB"
        )
        self.open_share_button.setText(self.open_share_button_text())

        self.refresh_button.setToolTip("")
        self.return_to_menu_button.setToolTip("")
        self.reboot_button.setToolTip("")
        self.enable_smb_button.setToolTip("")
        self.disable_smb_button.setToolTip("")
        self.open_share_button.setToolTip("")

        self.show_usb_storage(True)

    def apply_disconnected_state(self):
        self.refresh_timer.stop()

        self.refresh_button.setEnabled(False)
        self.return_to_menu_button.setEnabled(False)
        self.enable_smb_button.setEnabled(False)
        self.disable_smb_button.setEnabled(False)
        self.open_share_button.setEnabled(False)
        self.reboot_button.setEnabled(False)

        self.enable_smb_button.setText(
            "Enable Access" if sys.platform == "darwin" else "Enable SMB"
        )
        self.disable_smb_button.setText(
            "Disable Access" if sys.platform == "darwin" else "Disable SMB"
        )
        self.open_share_button.setText(self.open_share_button_text())

        self.refresh_button.setToolTip("")
        self.return_to_menu_button.setToolTip("")
        self.reboot_button.setToolTip("")
        self.enable_smb_button.setToolTip("")
        self.disable_smb_button.setToolTip("")
        self.open_share_button.setToolTip("")

        self.show_usb_storage(True)

        self.storage_bar.setValue(0)
        self.usb_bar.setValue(0)
        self.storage_bar.setStyleSheet("")
        self.usb_bar.setStyleSheet("")

        self.storage_label.setText("--")
        self.storage_label.setStyleSheet("")
        self.usb_label.setText("--")
        self.usb_label.setStyleSheet("")
        self.smb_status_label.setText(
            "Remote Access: Unknown" if sys.platform == "darwin" else "SMB: Unknown"
        )
        self.smb_status_label.setStyleSheet("")

        self.now_playing_summary_label.setText("")
        self.now_playing_group.setVisible(False)

    def apply_offline_state(self, lightweight=True):
        self.refresh_timer.stop()

        self.refresh_button.setEnabled(True)
        self.return_to_menu_button.setEnabled(False)
        self.reboot_button.setEnabled(False)

        self.refresh_button.setToolTip("")
        self.return_to_menu_button.setToolTip("Unavailable in Offline Mode because it requires a running MiSTer.")
        self.reboot_button.setToolTip("Unavailable in Offline Mode because it requires a running MiSTer.")

        self.enable_smb_button.setText(
            "Enable Access on Boot" if sys.platform == "darwin" else "Enable SMB on Boot"
        )
        self.disable_smb_button.setText(
            "Disable Access on Boot" if sys.platform == "darwin" else "Disable SMB on Boot"
        )
        self.open_share_button.setText("Open SD Card")

        self.enable_smb_button.setToolTip(
            "Changes the SD card startup setting. It will apply the next time MiSTer boots."
        )
        self.disable_smb_button.setToolTip(
            "Changes the SD card startup setting. It will apply the next time MiSTer boots."
        )
        self.open_share_button.setToolTip("Open the selected SD card folder.")

        sd_root = self.get_offline_sd_root()
        has_sd_root = bool(sd_root)

        self.open_share_button.setEnabled(has_sd_root)
        self.enable_smb_button.setEnabled(has_sd_root)
        self.disable_smb_button.setEnabled(has_sd_root)

        self.show_usb_storage(False)

        self.now_playing_summary_label.setText("")
        self.now_playing_group.setVisible(False)

        if lightweight:
            if not sd_root:
                self.storage_bar.setValue(0)
                self.storage_bar.setStyleSheet("")
                self.storage_label.setText("Offline Mode: No SD card selected")
                self.storage_label.setStyleSheet("")
                self.smb_status_label.setText(
                    "Remote Access Startup: No SD card selected"
                    if sys.platform == "darwin"
                    else "SMB Startup: No SD card selected"
                )
                self.smb_status_label.setStyleSheet("color: #f39c12;")
                self.enable_smb_button.setEnabled(False)
                self.disable_smb_button.setEnabled(False)
                self.open_share_button.setEnabled(False)
            return

        self.refresh_info()

    def refresh_info(self):
        self.refresh_timer.stop()

        if self.status_worker is not None and self.status_worker.isRunning():
            return

        if self.is_offline_mode():
            sd_root = self.get_offline_sd_root()

            if not sd_root:
                self.apply_offline_state(lightweight=True)
                return

            self.apply_offline_state(lightweight=True)
            self.show_refreshing_state()

            self.status_worker = DeviceStatusWorker(
                self.connection,
                offline_mode=True,
                sd_root=sd_root,
            )
            self.status_worker.result.connect(self.on_status_refresh_result)
            self.status_worker.error.connect(self.on_status_refresh_error)
            self.status_worker.finished.connect(self.on_status_refresh_finished)
            self.status_worker.start()
            return

        if not self.connection.is_connected():
            self.apply_disconnected_state()
            return

        self.apply_connected_state()
        self.show_refreshing_state()

        self.status_worker = DeviceStatusWorker(
            self.connection,
            offline_mode=False,
            sd_root="",
        )
        self.status_worker.result.connect(self.on_status_refresh_result)
        self.status_worker.error.connect(self.on_status_refresh_error)
        self.status_worker.finished.connect(self.on_status_refresh_finished)
        self.status_worker.start()

    def on_status_refresh_result(self, result):
        if result.get("offline"):
            self.apply_offline_state(lightweight=True)
            self.apply_offline_status_result(result)
            return

        if not self.connection.is_connected():
            self.apply_disconnected_state()
            return

        self.apply_connected_state()
        self.apply_online_status_result(result)

    def on_status_refresh_error(self, message):
        self.refresh_timer.stop()

        if self.is_offline_mode():
            self.storage_bar.setValue(0)
            self.storage_bar.setStyleSheet("")
            self.storage_label.setText("Unable to read selected SD card storage")
            self.storage_label.setStyleSheet("")
            self.smb_status_label.setText(
                "Remote Access Startup: Unknown"
                if sys.platform == "darwin"
                else "SMB Startup: Unknown"
            )
            self.smb_status_label.setStyleSheet("color: #f39c12;")
            self.refresh_button.setEnabled(True)
            return

        try:
            self.connection.mark_disconnected()
        except Exception:
            pass

        self.apply_disconnected_state()

    def on_status_refresh_finished(self):
        self.status_worker = None
        self.refresh_timer.stop()

    def apply_offline_status_result(self, result):
        sd_info = result.get("sd_info")

        if sd_info:
            self.storage_bar.setValue(sd_info["percent"])
            self.storage_bar.setStyleSheet(sd_info["style"])
            self.storage_label.setText(sd_info["label"])
            self.storage_label.setStyleSheet("")
        else:
            self.storage_bar.setValue(0)
            self.storage_bar.setStyleSheet("")
            self.storage_label.setText("Unable to read selected SD card storage")
            self.storage_label.setStyleSheet("")

        smb_enabled = result.get("smb_enabled")
        smb_error = result.get("smb_error", "")

        self.refresh_button.setEnabled(True)
        self.open_share_button.setEnabled(bool(self.get_offline_sd_root()))

        if smb_error:
            self.smb_status_label.setText(
                "Remote Access Startup: Unknown"
                if sys.platform == "darwin"
                else "SMB Startup: Unknown"
            )
            self.smb_status_label.setStyleSheet("color: #f39c12;")
            self.enable_smb_button.setEnabled(True)
            self.disable_smb_button.setEnabled(True)
            return

        if smb_enabled:
            self.smb_status_label.setText(
                "Remote Access Startup: Enabled ✓"
                if sys.platform == "darwin"
                else "SMB Startup: Enabled ✓"
            )
            self.smb_status_label.setStyleSheet("color: #00aa00;")
            self.enable_smb_button.setEnabled(False)
            self.disable_smb_button.setEnabled(True)
        else:
            self.smb_status_label.setText(
                "Remote Access Startup: Disabled"
                if sys.platform == "darwin"
                else "SMB Startup: Disabled"
            )
            self.smb_status_label.setStyleSheet("color: #cc0000;")
            self.enable_smb_button.setEnabled(True)
            self.disable_smb_button.setEnabled(False)

    def apply_online_status_result(self, result):
        sd_info = result.get("sd_info")

        self.refresh_button.setEnabled(True)

        if sd_info:
            self.storage_bar.setValue(sd_info["percent"])
            self.storage_bar.setStyleSheet(sd_info["style"])
            self.storage_label.setText(sd_info["label"])
            self.storage_label.setStyleSheet("")
        else:
            self.storage_bar.setValue(0)
            self.storage_bar.setStyleSheet("")
            self.storage_label.setText("--")
            self.storage_label.setStyleSheet("")

        usb_info = result.get("usb_info") or {}

        if not usb_info.get("present"):
            self.show_usb_storage(False)
        else:
            self.show_usb_storage(True)

            if not usb_info.get("readable"):
                self.usb_bar.setValue(0)
                self.usb_bar.setStyleSheet("")
                self.usb_label.setText(usb_info.get("label", "--"))
                self.usb_label.setStyleSheet("")
            else:
                self.usb_bar.setValue(usb_info["percent"])
                self.usb_bar.setStyleSheet(usb_info["style"])
                self.usb_label.setText(usb_info["label"])
                self.usb_label.setStyleSheet("")

        smb_enabled = bool(result.get("smb_enabled"))

        if smb_enabled:
            self.smb_status_label.setText(
                "Remote Access: Enabled ✓"
                if sys.platform == "darwin"
                else "SMB: Enabled ✓"
            )
            self.smb_status_label.setStyleSheet("color: #00aa00;")
            self.enable_smb_button.setEnabled(False)
            self.disable_smb_button.setEnabled(True)
            self.open_share_button.setEnabled(True)
        else:
            self.smb_status_label.setText(
                "Remote Access: Disabled"
                if sys.platform == "darwin"
                else "SMB: Disabled"
            )
            self.smb_status_label.setStyleSheet("color: #cc0000;")
            self.enable_smb_button.setEnabled(True)
            self.disable_smb_button.setEnabled(False)
            self.open_share_button.setEnabled(False)

        now_playing = result.get("now_playing") or {}

        if not now_playing.get("playing"):
            self.now_playing_summary_label.setText("")
            self.now_playing_group.setVisible(False)
        else:
            self.now_playing_summary_label.setText(now_playing.get("summary", ""))
            self.now_playing_group.setVisible(True)

    def refresh_offline_storage(self):
        sd_root = self.get_offline_sd_root()

        if not sd_root:
            self.storage_bar.setValue(0)
            self.storage_bar.setStyleSheet("")
            self.storage_label.setText("Offline Mode: No SD card selected")
            self.storage_label.setStyleSheet("")
            return

        sd_info = get_sd_storage_info_offline(sd_root)

        if sd_info:
            self.storage_bar.setValue(sd_info["percent"])
            self.storage_bar.setStyleSheet(sd_info["style"])
            self.storage_label.setText(sd_info["label"])
            self.storage_label.setStyleSheet("")
        else:
            self.storage_bar.setValue(0)
            self.storage_bar.setStyleSheet("")
            self.storage_label.setText("Unable to read selected SD card storage")
            self.storage_label.setStyleSheet("")

    def refresh_offline_smb_status(self):
        sd_root = self.get_offline_sd_root()

        if not sd_root:
            self.smb_status_label.setText(
                "Remote Access Startup: No SD card selected"
                if sys.platform == "darwin"
                else "SMB Startup: No SD card selected"
            )
            self.smb_status_label.setStyleSheet("color: #f39c12;")
            self.enable_smb_button.setEnabled(False)
            self.disable_smb_button.setEnabled(False)
            self.open_share_button.setEnabled(False)
            return

        self.open_share_button.setEnabled(True)

        try:
            smb_enabled = is_smb_enabled_offline(sd_root)
        except Exception:
            self.smb_status_label.setText(
                "Remote Access Startup: Unknown"
                if sys.platform == "darwin"
                else "SMB Startup: Unknown"
            )
            self.smb_status_label.setStyleSheet("color: #f39c12;")
            self.enable_smb_button.setEnabled(True)
            self.disable_smb_button.setEnabled(True)
            return

        if smb_enabled:
            self.smb_status_label.setText(
                "Remote Access Startup: Enabled ✓"
                if sys.platform == "darwin"
                else "SMB Startup: Enabled ✓"
            )
            self.smb_status_label.setStyleSheet("color: #00aa00;")
            self.enable_smb_button.setEnabled(False)
            self.disable_smb_button.setEnabled(True)
        else:
            self.smb_status_label.setText(
                "Remote Access Startup: Disabled"
                if sys.platform == "darwin"
                else "SMB Startup: Disabled"
            )
            self.smb_status_label.setStyleSheet("color: #cc0000;")
            self.enable_smb_button.setEnabled(True)
            self.disable_smb_button.setEnabled(False)

    def refresh_storage(self):
        if self.is_offline_mode():
            self.refresh_offline_storage()
            return

        sd_info = get_sd_storage_info(self.connection)

        if sd_info:
            self.storage_bar.setValue(sd_info["percent"])
            self.storage_bar.setStyleSheet(sd_info["style"])
            self.storage_label.setText(sd_info["label"])
            self.storage_label.setStyleSheet("")
        else:
            self.storage_bar.setValue(0)
            self.storage_bar.setStyleSheet("")
            self.storage_label.setText("--")
            self.storage_label.setStyleSheet("")

        usb_info = get_usb_storage_info(self.connection)

        if not usb_info["present"]:
            self.show_usb_storage(False)
            return

        self.show_usb_storage(True)

        if not usb_info["readable"]:
            self.usb_bar.setValue(0)
            self.usb_bar.setStyleSheet("")
            self.usb_label.setText(usb_info["label"])
            self.usb_label.setStyleSheet("")
            return

        self.usb_bar.setValue(usb_info["percent"])
        self.usb_bar.setStyleSheet(usb_info["style"])
        self.usb_label.setText(usb_info["label"])
        self.usb_label.setStyleSheet("")

    def refresh_smb_status(self):
        if self.is_offline_mode():
            self.refresh_offline_smb_status()
            return

        smb_enabled = is_smb_enabled(self.connection)

        if smb_enabled:
            self.smb_status_label.setText(
                "Remote Access: Enabled ✓" if sys.platform == "darwin" else "SMB: Enabled ✓"
            )
            self.smb_status_label.setStyleSheet("color: #00aa00;")
            self.enable_smb_button.setEnabled(False)
            self.disable_smb_button.setEnabled(True)
            self.open_share_button.setEnabled(True)
        else:
            self.smb_status_label.setText(
                "Remote Access: Disabled" if sys.platform == "darwin" else "SMB: Disabled"
            )
            self.smb_status_label.setStyleSheet("color: #cc0000;")
            self.enable_smb_button.setEnabled(True)
            self.disable_smb_button.setEnabled(False)
            self.open_share_button.setEnabled(False)

    def refresh_now_playing(self):
        if self.is_offline_mode():
            self.now_playing_summary_label.setText("")
            self.now_playing_group.setVisible(False)
            return

        now_playing = get_now_playing(self.connection)

        if not now_playing.get("playing"):
            self.now_playing_summary_label.setText("")
            self.now_playing_group.setVisible(False)
            return

        self.now_playing_summary_label.setText(now_playing.get("summary", ""))
        self.now_playing_group.setVisible(True)

    def enable_smb(self):
        if self.is_offline_mode():
            self.enable_smb_offline()
            return

        if not self.connection.is_connected():
            QMessageBox.warning(self, "Not Connected", "Connect to a MiSTer first.")
            return

        enable_smb_remote(self.connection)

        reboot_now = QMessageBox.question(
            self,
            "Remote Access Enabled" if sys.platform == "darwin" else "SMB Enabled",
            (
                "Remote Access has been enabled.\n\nA reboot is required.\n\nReboot now?"
                if sys.platform == "darwin"
                else "SMB has been enabled.\n\nA reboot is required.\n\nReboot now?"
            ),
        )

        if reboot_now == QMessageBox.StandardButton.Yes:
            self.reboot_device(skip_confirm=True)
            return

        self.refresh_info()

    def disable_smb(self):
        if self.is_offline_mode():
            self.disable_smb_offline()
            return

        if not self.connection.is_connected():
            QMessageBox.warning(self, "Not Connected", "Connect to a MiSTer first.")
            return

        disable_smb_remote(self.connection)

        reboot_now = QMessageBox.question(
            self,
            "Remote Access Disabled" if sys.platform == "darwin" else "SMB Disabled",
            (
                "Remote Access has been disabled.\n\nA reboot is required.\n\nReboot now?"
                if sys.platform == "darwin"
                else "SMB has been disabled.\n\nA reboot is required.\n\nReboot now?"
            ),
        )

        if reboot_now == QMessageBox.StandardButton.Yes:
            self.reboot_device(skip_confirm=True)
            return

        self.refresh_info()

    def enable_smb_offline(self):
        sd_root = self.get_offline_sd_root()

        if not sd_root:
            QMessageBox.warning(self, "No SD Card Selected", "Select a MiSTer SD card first.")
            return

        try:
            enable_smb_offline(sd_root)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Enable Failed",
                f"Unable to enable SMB on boot:\n\n{str(e)}",
            )
            self.refresh_info()
            return

        QMessageBox.information(
            self,
            "Remote Access Enabled on Boot" if sys.platform == "darwin" else "SMB Enabled on Boot",
            (
                "Remote Access has been enabled on the selected SD card.\n\n"
                "It will apply the next time MiSTer boots."
                if sys.platform == "darwin"
                else "SMB has been enabled on the selected SD card.\n\n"
                "It will apply the next time MiSTer boots."
            ),
        )

        self.refresh_info()

    def disable_smb_offline(self):
        sd_root = self.get_offline_sd_root()

        if not sd_root:
            QMessageBox.warning(self, "No SD Card Selected", "Select a MiSTer SD card first.")
            return

        try:
            disable_smb_offline(sd_root)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Disable Failed",
                f"Unable to disable SMB on boot:\n\n{str(e)}",
            )
            self.refresh_info()
            return

        QMessageBox.information(
            self,
            "Remote Access Disabled on Boot" if sys.platform == "darwin" else "SMB Disabled on Boot",
            (
                "Remote Access has been disabled on the selected SD card.\n\n"
                "It will apply the next time MiSTer boots."
                if sys.platform == "darwin"
                else "SMB has been disabled on the selected SD card.\n\n"
                "It will apply the next time MiSTer boots."
            ),
        )

        self.refresh_info()

    def open_share(self):
        if self.is_offline_mode():
            sd_root = self.get_offline_sd_root()

            if not sd_root:
                QMessageBox.warning(self, "No SD Card Selected", "Select a MiSTer SD card first.")
                return

            try:
                open_local_folder(sd_root)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Open SD Card Failed",
                    f"Unable to open the selected SD card folder:\n\n{str(e)}",
                )
            return

        if not self.connection.host:
            QMessageBox.warning(self, self.open_share_button_text(), "No MiSTer IP address is available.")
            return

        try:
            open_mister_share(
                ip=self.connection.host,
                username=self.connection.username,
                password=self.connection.password,
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Unable to open share:\n\n{str(e)}",
            )

    def return_to_menu(self):
        if self.is_offline_mode():
            QMessageBox.information(
                self,
                "Offline Mode Active",
                "Return to Menu requires a running MiSTer and is only available in Online Mode."
            )
            return

        if not self.connection.is_connected():
            QMessageBox.warning(self, "Not Connected", "Connect to a MiSTer first.")
            return

        try:
            return_to_menu_remote(self.connection)
        except Exception as e:
            QMessageBox.critical(self, "Return to Menu Failed", str(e))
            return

    def reboot_device(self, skip_confirm=False):
        if self.is_offline_mode():
            QMessageBox.information(
                self,
                "Offline Mode Active",
                "Reboot requires a running MiSTer and is only available in Online Mode."
            )
            return

        if not self.connection.is_connected():
            QMessageBox.warning(self, "Not Connected", "Connect to a MiSTer first.")
            return

        if not skip_confirm:
            reply = QMessageBox.question(
                self,
                "Confirm Reboot",
                "Are you sure you want to reboot the MiSTer?",
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

        self.apply_disconnected_state()
        self.refresh_timer.stop()

        try:
            self.main_window.set_connection_status("Status: Rebooting...")
        except Exception:
            pass

        try:
            self.connection.reboot()
            QTimer.singleShot(7000, self.main_window.start_reboot_reconnect_polling)
        except Exception as e:
            QMessageBox.critical(self, "Reboot Failed", str(e))
            return
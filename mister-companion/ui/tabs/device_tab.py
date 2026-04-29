import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QMessageBox, QProgressBar
)

from core.device_actions import (
    disable_smb_remote,
    enable_smb_remote,
    get_now_playing,
    get_sd_storage_info,
    get_usb_storage_info,
    is_smb_enabled,
    return_to_menu_remote,
)
from core.language import tr
from core.share_opener import open_mister_share


class DeviceTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(2000)
        self.refresh_timer.timeout.connect(self.refresh_info)

        self.build_ui()
        self.apply_disconnected_state()

    def build_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(18)

        # =========================
        # Storage Group
        # =========================
        storage_group = QGroupBox(tr("device_tab.storage"))
        storage_layout = QVBoxLayout()
        storage_layout.setContentsMargins(16, 18, 16, 18)
        storage_layout.setSpacing(10)

        self.sd_title_label = QLabel(tr("device_tab.sd_card"))
        self.sd_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.storage_bar = QProgressBar()
        self.storage_bar.setRange(0, 100)
        self.storage_bar.setValue(0)
        self.storage_bar.setTextVisible(False)
        self.storage_bar.setFixedWidth(500)

        self.storage_label = QLabel("--")
        self.storage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.usb_title_label = QLabel(tr("device_tab.usb_storage"))
        self.usb_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.usb_bar = QProgressBar()
        self.usb_bar.setRange(0, 100)
        self.usb_bar.setValue(0)
        self.usb_bar.setTextVisible(False)
        self.usb_bar.setFixedWidth(500)

        self.usb_label = QLabel(tr("device_tab.checking"))
        self.usb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.refresh_button = QPushButton(tr("device_tab.refresh"))
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

        # =========================
        # File Sharing Group
        # =========================
        sharing_group = QGroupBox(tr("device_tab.file_sharing"))
        sharing_layout = QVBoxLayout()
        sharing_layout.setContentsMargins(16, 18, 16, 18)
        sharing_layout.setSpacing(14)

        self.smb_status_label = QLabel(
            tr("device_tab.remote_access_unknown")
            if sys.platform == "darwin"
            else tr("device_tab.smb_unknown")
        )
        self.smb_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sharing_buttons_row = QHBoxLayout()
        sharing_buttons_row.setSpacing(24)

        self.enable_smb_button = QPushButton(
            tr("device_tab.enable_access")
            if sys.platform == "darwin"
            else tr("device_tab.enable_smb")
        )
        self.disable_smb_button = QPushButton(
            tr("device_tab.disable_access")
            if sys.platform == "darwin"
            else tr("device_tab.disable_smb")
        )
        self.open_share_button = QPushButton(
            tr("device_tab.open_in_finder")
            if sys.platform == "darwin"
            else tr("device_tab.open_in_explorer")
        )

        self.enable_smb_button.setFixedWidth(130)
        self.disable_smb_button.setFixedWidth(130)
        self.open_share_button.setFixedWidth(140)

        sharing_buttons_row.addStretch()
        sharing_buttons_row.addWidget(self.enable_smb_button)
        sharing_buttons_row.addWidget(self.disable_smb_button)
        sharing_buttons_row.addWidget(self.open_share_button)
        sharing_buttons_row.addStretch()

        sharing_layout.addWidget(self.smb_status_label)
        sharing_layout.addLayout(sharing_buttons_row)

        sharing_group.setLayout(sharing_layout)

        # =========================
        # Power Group
        # =========================
        power_group = QGroupBox(tr("device_tab.power"))
        power_layout = QVBoxLayout()
        power_layout.setContentsMargins(16, 18, 16, 18)

        reboot_row = QHBoxLayout()
        reboot_row.setSpacing(16)

        self.return_to_menu_button = QPushButton(tr("device_tab.return_to_menu"))
        self.return_to_menu_button.setFixedWidth(160)

        self.reboot_button = QPushButton(tr("device_tab.reboot_mister"))
        self.reboot_button.setFixedWidth(160)

        reboot_row.addStretch()
        reboot_row.addWidget(self.return_to_menu_button)
        reboot_row.addWidget(self.reboot_button)
        reboot_row.addStretch()

        power_layout.addLayout(reboot_row)
        power_group.setLayout(power_layout)

        # =========================
        # Now Playing Group
        # =========================
        self.now_playing_group = QGroupBox(tr("device_tab.now_playing"))
        now_playing_layout = QVBoxLayout()
        now_playing_layout.setContentsMargins(16, 18, 16, 18)
        now_playing_layout.setSpacing(8)

        self.now_playing_summary_label = QLabel("")
        self.now_playing_summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.now_playing_summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.now_playing_summary_label.setStyleSheet("font-weight: bold;")

        now_playing_layout.addWidget(self.now_playing_summary_label)

        self.now_playing_group.setLayout(now_playing_layout)
        self.now_playing_group.setVisible(False)

        # =========================
        # Final Layout
        # =========================
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

    def showEvent(self, event):
        super().showEvent(event)
        if self.connection.is_connected():
            self.refresh_info()
            self.refresh_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.refresh_timer.stop()

    def update_connection_state(self):
        if self.connection.is_connected():
            self.apply_connected_state()
            if self.isVisible():
                self.refresh_timer.start()
            else:
                self.refresh_timer.stop()
        else:
            self.apply_disconnected_state()
            self.refresh_timer.stop()

    def apply_connected_state(self):
        self.refresh_button.setEnabled(True)
        self.return_to_menu_button.setEnabled(True)
        self.reboot_button.setEnabled(True)
        self.enable_smb_button.setEnabled(True)
        self.disable_smb_button.setEnabled(True)

    def apply_disconnected_state(self):
        self.refresh_button.setEnabled(False)
        self.return_to_menu_button.setEnabled(False)
        self.enable_smb_button.setEnabled(False)
        self.disable_smb_button.setEnabled(False)
        self.open_share_button.setEnabled(False)
        self.reboot_button.setEnabled(False)

        self.storage_bar.setValue(0)
        self.usb_bar.setValue(0)
        self.storage_bar.setStyleSheet("")
        self.usb_bar.setStyleSheet("")

        self.storage_label.setText("--")
        self.usb_label.setText("--")
        self.smb_status_label.setText(
            tr("device_tab.remote_access_unknown")
            if sys.platform == "darwin"
            else tr("device_tab.smb_unknown")
        )
        self.smb_status_label.setStyleSheet("")

        self.now_playing_summary_label.setText("")
        self.now_playing_group.setVisible(False)

    def refresh_info(self):
        if not self.connection.is_connected():
            self.apply_disconnected_state()
            self.refresh_timer.stop()
            return

        self.apply_connected_state()
        self.refresh_storage()
        self.refresh_smb_status()
        self.refresh_now_playing()

    def refresh_storage(self):
        sd_info = get_sd_storage_info(self.connection)

        if sd_info:
            self.storage_bar.setValue(sd_info["percent"])
            self.storage_bar.setStyleSheet(sd_info["style"])
            self.storage_label.setText(sd_info["label"])
        else:
            self.storage_bar.setValue(0)
            self.storage_bar.setStyleSheet("")
            self.storage_label.setText("--")

        usb_info = get_usb_storage_info(self.connection)

        if not usb_info["present"]:
            self.usb_bar.setValue(0)
            self.usb_bar.setStyleSheet("")
            self.usb_label.setText(usb_info["label"])
            return

        if not usb_info["readable"]:
            self.usb_bar.setValue(0)
            self.usb_bar.setStyleSheet("")
            self.usb_label.setText(usb_info["label"])
            return

        self.usb_bar.setValue(usb_info["percent"])
        self.usb_bar.setStyleSheet(usb_info["style"])
        self.usb_label.setText(usb_info["label"])

    def refresh_smb_status(self):
        smb_enabled = is_smb_enabled(self.connection)

        if smb_enabled:
            self.smb_status_label.setText(
                tr("device_tab.remote_access_enabled")
                if sys.platform == "darwin"
                else tr("device_tab.smb_enabled")
            )
            self.smb_status_label.setStyleSheet("color: #00aa00;")
            self.enable_smb_button.setEnabled(False)
            self.disable_smb_button.setEnabled(True)
            self.open_share_button.setEnabled(True)
        else:
            self.smb_status_label.setText(
                tr("device_tab.remote_access_disabled")
                if sys.platform == "darwin"
                else tr("device_tab.smb_disabled")
            )
            self.smb_status_label.setStyleSheet("color: #cc0000;")
            self.enable_smb_button.setEnabled(True)
            self.disable_smb_button.setEnabled(False)
            self.open_share_button.setEnabled(False)

    def refresh_now_playing(self):
        now_playing = get_now_playing(self.connection)

        if not now_playing.get("playing"):
            self.now_playing_summary_label.setText("")
            self.now_playing_group.setVisible(False)
            return

        self.now_playing_summary_label.setText(now_playing.get("summary", ""))
        self.now_playing_group.setVisible(True)

    def enable_smb(self):
        if not self.connection.is_connected():
            QMessageBox.warning(
                self,
                tr("device_tab.not_connected_title"),
                tr("device_tab.not_connected_message"),
            )
            return

        enable_smb_remote(self.connection)

        reboot_now = QMessageBox.question(
            self,
            tr("device_tab.remote_access_enabled_title")
            if sys.platform == "darwin"
            else tr("device_tab.smb_enabled_title"),
            tr("device_tab.remote_access_enabled_message")
            if sys.platform == "darwin"
            else tr("device_tab.smb_enabled_message"),
        )

        if reboot_now == QMessageBox.StandardButton.Yes:
            self.reboot_device(skip_confirm=True)
            return

        self.refresh_smb_status()

    def disable_smb(self):
        if not self.connection.is_connected():
            QMessageBox.warning(
                self,
                tr("device_tab.not_connected_title"),
                tr("device_tab.not_connected_message"),
            )
            return

        disable_smb_remote(self.connection)

        reboot_now = QMessageBox.question(
            self,
            tr("device_tab.remote_access_disabled_title")
            if sys.platform == "darwin"
            else tr("device_tab.smb_disabled_title"),
            tr("device_tab.remote_access_disabled_message")
            if sys.platform == "darwin"
            else tr("device_tab.smb_disabled_message"),
        )

        if reboot_now == QMessageBox.StandardButton.Yes:
            self.reboot_device(skip_confirm=True)
            return

        self.refresh_smb_status()

    def open_share(self):
        if not self.connection.host:
            QMessageBox.warning(
                self,
                tr("device_tab.open_in_explorer"),
                tr("device_tab.no_mister_ip"),
            )
            return

        try:
            open_mister_share(
                ip=self.connection.host,
                username=self.connection.username,
                password=self.connection.password
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("common.error"),
                tr("device_tab.unable_to_open_share", error=str(e)),
            )

    def return_to_menu(self):
        if not self.connection.is_connected():
            QMessageBox.warning(
                self,
                tr("device_tab.not_connected_title"),
                tr("device_tab.not_connected_message"),
            )
            return

        try:
            return_to_menu_remote(self.connection)
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("device_tab.return_to_menu_failed"),
                str(e),
            )
            return

    def reboot_device(self, skip_confirm=False):
        if not self.connection.is_connected():
            QMessageBox.warning(
                self,
                tr("device_tab.not_connected_title"),
                tr("device_tab.not_connected_message"),
            )
            return

        if not skip_confirm:
            reply = QMessageBox.question(
                self,
                tr("device_tab.confirm_reboot_title"),
                tr("device_tab.confirm_reboot_message"),
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

        self.apply_disconnected_state()
        self.refresh_timer.stop()

        try:
            self.main_window.set_connection_status(tr("status.rebooting"))
        except Exception:
            pass

        try:
            self.connection.reboot()
            self.main_window.start_reboot_reconnect_polling()
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("device_tab.reboot_failed"),
                str(e),
            )
            return
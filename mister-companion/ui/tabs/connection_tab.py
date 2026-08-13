from pathlib import Path

from core.open_helpers import open_uri, open_local_folder
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.scaling import set_text_button_min_width
from ui.tabs.device_tab import DeviceTab
from core.config import save_config
from core.sd_eject import eject_sd_card_path

PATREON_URL = "https://www.patreon.com/Anime0t4ku"
CONFIG_SHOW_SUPPORT_MESSAGE = "show_support_message"


class ConnectionTab(QWidget):
    def __init__(self, main_window):
        super().__init__()

        self.main_window = main_window
        self.connection = main_window.connection

        self.support_message_hidden = False

        self.save_after_next_connect = False
        self.mode_switch_in_progress = False

        self.init_ui()
        self.connect_signals()
        self.update_mode_state()
        self.update_connection_state()

        self.apply_support_message_preference()

    def init_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.state_stack = QStackedWidget()
        outer_layout.addWidget(self.state_stack)

        self.connection_page = QWidget()
        main_layout = QVBoxLayout(self.connection_page)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        self.state_stack.addWidget(self.connection_page)

        self.device_dashboard = DeviceTab(self.main_window)
        self.state_stack.addWidget(self.device_dashboard)
        self.state_stack.setCurrentWidget(self.connection_page)

        self.connection_status_label = QLabel("Status: Disconnected")
        self.connection_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_status_label.setStyleSheet("font-weight: bold;")
        main_layout.addWidget(self.connection_status_label)

        self.content_row = QHBoxLayout()
        self.content_row.setSpacing(12)
        main_layout.addLayout(self.content_row, stretch=1)

        self.connection_group = QGroupBox("Connection")
        self.connection_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        connection_layout = QVBoxLayout()
        connection_layout.setContentsMargins(12, 14, 12, 12)
        connection_layout.setSpacing(12)
        self.connection_group.setLayout(connection_layout)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        header_text_layout = QVBoxLayout()
        header_text_layout.setContentsMargins(0, 0, 0, 0)
        header_text_layout.setSpacing(2)

        header_title = QLabel("Connection")
        header_title.setStyleSheet("font-weight: bold; font-size: 15px;")
        header_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.mode_hint_label = QLabel("Choose Online / SSH or Offline / SD Card mode.")
        self.mode_hint_label.setStyleSheet("color: gray;")
        self.mode_hint_label.setWordWrap(True)
        self.mode_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header_text_layout.addWidget(header_title)
        header_text_layout.addWidget(self.mode_hint_label)

        self.show_support_button = QPushButton("Show Message")
        set_text_button_min_width(self.show_support_button, 100)
        self.show_support_button.hide()

        show_support_button_width = self.show_support_button.minimumWidth()

        self.show_support_button_placeholder = QWidget()
        self.show_support_button_placeholder.setMinimumWidth(show_support_button_width)
        self.show_support_button_placeholder.setSizePolicy(
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )

        self.show_support_button_container = QWidget()
        self.show_support_button_container.setMinimumWidth(show_support_button_width)
        self.show_support_button_container.setSizePolicy(
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )

        show_support_button_layout = QHBoxLayout(self.show_support_button_container)
        show_support_button_layout.setContentsMargins(0, 0, 0, 0)
        show_support_button_layout.setSpacing(0)
        show_support_button_layout.addWidget(self.show_support_button)

        header_row.addWidget(self.show_support_button_placeholder)
        header_row.addStretch()
        header_row.addLayout(header_text_layout)
        header_row.addStretch()
        header_row.addWidget(self.show_support_button_container)

        connection_layout.addLayout(header_row)

        self.mode_frame = QFrame()
        mode_layout = QHBoxLayout()
        mode_layout.setContentsMargins(10, 10, 10, 10)
        mode_layout.setSpacing(12)
        self.mode_frame.setLayout(mode_layout)

        self.online_mode_radio = QRadioButton("Online / SSH")
        self.offline_mode_radio = QRadioButton("Offline / SD Card")
        self.online_mode_radio.setChecked(True)

        mode_label = QLabel("Mode:")
        mode_layout.addStretch()
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.online_mode_radio)
        mode_layout.addWidget(self.offline_mode_radio)
        mode_layout.addStretch()

        connection_layout.addWidget(self.mode_frame)

        self.online_controls_widget = QWidget()
        online_layout = QVBoxLayout()
        online_layout.setContentsMargins(0, 0, 0, 0)
        online_layout.setSpacing(12)
        self.online_controls_widget.setLayout(online_layout)

        self.saved_group = QGroupBox("Saved Device Profiles")
        saved_layout = QGridLayout()
        saved_layout.setContentsMargins(10, 12, 10, 10)
        saved_layout.setHorizontalSpacing(8)
        saved_layout.setVerticalSpacing(8)

        self.profile_selector = QComboBox()
        self.profile_selector.setPlaceholderText("Select Device")
        self.profile_selector.setCurrentIndex(-1)
        self.profile_selector.setMinimumWidth(260)
        self.profile_selector.setMaximumWidth(360)
        self.profile_selector.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

        self.edit_profile_btn = QPushButton("Edit")
        set_text_button_min_width(self.edit_profile_btn, 80)
        self.delete_profile_btn = QPushButton("Delete")
        set_text_button_min_width(self.delete_profile_btn, 80)
        saved_center_row = QHBoxLayout()
        saved_center_row.setSpacing(8)
        saved_center_row.addStretch()
        saved_center_row.addWidget(QLabel("Profile:"))
        saved_center_row.addWidget(self.profile_selector)
        saved_center_row.addWidget(self.edit_profile_btn)
        saved_center_row.addWidget(self.delete_profile_btn)
        saved_center_row.addStretch()

        saved_layout.addLayout(saved_center_row, 0, 0)

        self.saved_group.setLayout(saved_layout)
        online_layout.addWidget(self.saved_group)

        self.details_group = QGroupBox("Connection Details")
        details_layout = QGridLayout()
        details_layout.setContentsMargins(10, 12, 10, 10)
        details_layout.setHorizontalSpacing(8)
        details_layout.setVerticalSpacing(8)

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("MiSTer IP")
        self.ip_input.setMinimumWidth(100)
        self.ip_input.setMaximumWidth(140)

        self.user_input = QLineEdit()
        self.user_input.setText("root")
        self.user_input.setMinimumWidth(100)
        self.user_input.setMaximumWidth(140)

        self.pass_input = QLineEdit()
        self.pass_input.setText("1")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setMinimumWidth(100)
        self.pass_input.setMaximumWidth(140)

        self.scan_btn = QPushButton("Scan Network")
        self.scan_btn.setMinimumWidth(150)

        details_center_layout = QVBoxLayout()
        details_center_layout.setContentsMargins(0, 0, 0, 0)
        details_center_layout.setSpacing(8)

        details_row = QHBoxLayout()
        details_row.setSpacing(8)
        details_row.addStretch()
        details_row.addWidget(QLabel("IP Address:"))
        details_row.addWidget(self.ip_input)
        details_row.addWidget(QLabel("Username:"))
        details_row.addWidget(self.user_input)
        details_row.addWidget(QLabel("Password:"))
        details_row.addWidget(self.pass_input)
        details_row.addStretch()

        scan_row = QHBoxLayout()
        scan_row.setContentsMargins(0, 4, 0, 0)
        scan_row.addStretch()
        scan_row.addWidget(self.scan_btn)
        scan_row.addStretch()

        details_center_layout.addLayout(details_row)
        details_center_layout.addLayout(scan_row)

        details_layout.addLayout(details_center_layout, 0, 0)

        self.details_group.setLayout(details_layout)
        online_layout.addWidget(self.details_group)

        self.actions_group = QGroupBox("Actions")
        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(10, 12, 10, 10)
        actions_layout.setSpacing(8)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setMinimumWidth(120)

        self.connect_save_btn = QPushButton("Connect && Save")
        self.connect_save_btn.setMinimumWidth(130)

        self.save_profile_btn = QPushButton("Save Only")
        self.save_profile_btn.setMinimumWidth(110)

        actions_layout.addStretch()
        actions_layout.addWidget(self.connect_btn)
        actions_layout.addWidget(self.connect_save_btn)
        actions_layout.addWidget(self.save_profile_btn)
        actions_layout.addStretch()

        self.actions_group.setLayout(actions_layout)
        online_layout.addWidget(self.actions_group)

        self.advanced_group = QGroupBox("Advanced SSH Options")
        advanced_layout = QVBoxLayout()
        advanced_layout.setContentsMargins(10, 12, 10, 10)
        advanced_layout.setSpacing(8)

        self.advanced_ssh_warning_label = QLabel(
            "Only enable these if you know you need them."
        )
        self.advanced_ssh_warning_label.setStyleSheet("color: #f39c12;")
        self.advanced_ssh_warning_label.setWordWrap(True)
        self.advanced_ssh_warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.use_ssh_agent_checkbox = QCheckBox("Use OS SSH Agent")
        self.use_ssh_agent_checkbox.setChecked(
            self.main_window.config_data.get("use_ssh_agent", False)
        )
        self.use_ssh_agent_checkbox.setToolTip(
            "Uses your operating system SSH agent for authentication."
        )

        self.look_for_ssh_keys_checkbox = QCheckBox("Use local SSH key files")
        self.look_for_ssh_keys_checkbox.setChecked(
            self.main_window.config_data.get("look_for_ssh_keys", False)
        )
        self.look_for_ssh_keys_checkbox.setToolTip(
            "Searches your local ~/.ssh folder for private keys."
        )

        ssh_options_row = QHBoxLayout()
        ssh_options_row.setSpacing(12)
        ssh_options_row.addStretch()
        ssh_options_row.addWidget(self.use_ssh_agent_checkbox)
        ssh_options_row.addWidget(self.look_for_ssh_keys_checkbox)
        ssh_options_row.addStretch()

        advanced_layout.addWidget(self.advanced_ssh_warning_label)
        advanced_layout.addLayout(ssh_options_row)

        self.advanced_group.setLayout(advanced_layout)
        online_layout.addWidget(self.advanced_group)

        connection_layout.addWidget(self.online_controls_widget)

        self.offline_group = QGroupBox("Offline SD Card")
        offline_layout = QVBoxLayout()
        offline_layout.setContentsMargins(10, 12, 10, 10)
        offline_layout.setSpacing(10)

        offline_info_label = QLabel(
            "Offline Mode works directly on the selected MiSTer SD card. "
            "Enable Remember SD location to keep the latest selected path after closing MiSTer Companion."
        )
        offline_info_label.setWordWrap(True)
        offline_info_label.setStyleSheet("color: gray;")
        offline_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        offline_row = QHBoxLayout()
        offline_row.setSpacing(8)
        offline_row.addStretch()

        self.offline_sd_input = QLineEdit()
        self.offline_sd_input.setPlaceholderText("MiSTer SD card root")
        self.offline_sd_input.setText(self.selected_sd_root())
        self.offline_sd_input.setMinimumWidth(320)
        self.offline_sd_input.setMaximumWidth(520)

        self.browse_sd_btn = QPushButton("Browse...")
        set_text_button_min_width(self.browse_sd_btn, 100)
        offline_row.addWidget(self.offline_sd_input)
        offline_row.addWidget(self.browse_sd_btn)
        offline_row.addStretch()

        remember_sd_row = QHBoxLayout()
        remember_sd_row.setSpacing(8)
        remember_sd_row.addStretch()

        self.remember_sd_location_checkbox = QCheckBox("Remember SD location")
        self.remember_sd_location_checkbox.setChecked(
            self.main_window.should_remember_offline_sd_root()
            if hasattr(self.main_window, "should_remember_offline_sd_root")
            else False
        )
        self.remember_sd_location_checkbox.setToolTip(
            "When enabled, MiSTer Companion remembers the latest selected Offline Mode SD card path after closing."
        )

        remember_sd_row.addWidget(self.remember_sd_location_checkbox)
        remember_sd_row.addStretch()

        offline_actions_row = QHBoxLayout()
        offline_actions_row.setSpacing(8)

        self.open_sd_btn = QPushButton("Open SD Card")
        self.open_sd_btn.setMinimumWidth(120)

        self.eject_sd_btn = QPushButton("Eject SD Card")
        self.eject_sd_btn.setMinimumWidth(120)

        self.load_sd_btn = QPushButton("Load SD Card")
        self.load_sd_btn.setMinimumWidth(120)

        offline_actions_row.addStretch()
        offline_actions_row.addWidget(self.open_sd_btn)
        offline_actions_row.addWidget(self.eject_sd_btn)
        offline_actions_row.addWidget(self.load_sd_btn)
        offline_actions_row.addStretch()

        self.offline_sd_status_label = QLabel("")
        self.offline_sd_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        offline_layout.addWidget(offline_info_label)
        offline_layout.addLayout(offline_row)
        offline_layout.addLayout(remember_sd_row)
        offline_layout.addLayout(offline_actions_row)
        offline_layout.addWidget(self.offline_sd_status_label)

        self.offline_group.setLayout(offline_layout)
        connection_layout.addWidget(self.offline_group)

        connection_layout.addStretch()

        self.content_row.addWidget(self.connection_group, stretch=1)

        self.support_group = QGroupBox("Thank You")
        self.support_group.setMinimumWidth(320)
        self.support_group.setMaximumWidth(380)
        self.support_group.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )

        support_layout = QVBoxLayout()
        support_layout.setContentsMargins(16, 16, 16, 16)
        support_layout.setSpacing(12)

        support_header_row = QHBoxLayout()
        support_header_row.setSpacing(8)

        self.hide_support_button = QPushButton("Hide")
        set_text_button_min_width(self.hide_support_button, 70)
        support_header_row.addStretch()
        support_header_row.addWidget(self.hide_support_button)
        support_header_row.addStretch()

        self.support_headline_label = QLabel("Thank you for using MiSTer Companion!")
        self.support_headline_label.setWordWrap(True)
        self.support_headline_label.setTextFormat(Qt.TextFormat.PlainText)
        self.support_headline_label.setStyleSheet("font-size: 15px; font-weight: bold;")

        self.support_message_label = QLabel(
            "I really appreciate everyone who uses Companion and the other MiSTer "
            "projects I work on.\n\n"
            "I build these tools because I enjoy creating useful things for the MiSTer "
            "community, whether that is improving Companion, maintaining projects like "
            "MiSTer Hi-Fi and CollectionLauncher, or experimenting with new ideas.\n\n"
            "If you enjoy these projects and would like to support their continued "
            "development, Patreon is an optional way to contribute. It helps with "
            "development costs and gives me more room to spend time on updates, fixes, "
            "and new projects."
        )
        self.support_message_label.setWordWrap(True)
        self.support_message_label.setTextFormat(Qt.TextFormat.PlainText)

        self.patreon_button = QPushButton("Patreon")
        set_text_button_min_width(self.patreon_button, 120)

        self.dismiss_support_button = QPushButton("Don't show this again")
        set_text_button_min_width(self.dismiss_support_button, 170)

        support_button_row = QHBoxLayout()
        support_button_row.setSpacing(8)
        support_button_row.addStretch()
        support_button_row.addWidget(self.patreon_button)
        support_button_row.addStretch()

        dismiss_row = QHBoxLayout()
        dismiss_row.addStretch()
        dismiss_row.addWidget(self.dismiss_support_button)
        dismiss_row.addStretch()

        support_layout.addLayout(support_header_row)
        support_layout.addWidget(self.support_headline_label)
        support_layout.addWidget(self.support_message_label)
        support_layout.addLayout(support_button_row)
        support_layout.addStretch()
        support_layout.addLayout(dismiss_row)

        self.support_group.setLayout(support_layout)
        self.support_group.hide()

        self.content_row.addWidget(self.support_group)

    def connect_signals(self):
        self.online_mode_radio.toggled.connect(self.handle_mode_changed)
        self.offline_mode_radio.toggled.connect(self.handle_mode_changed)

        self.browse_sd_btn.clicked.connect(self.handle_browse_sd_card)
        self.open_sd_btn.clicked.connect(self.handle_open_sd_card)
        self.eject_sd_btn.clicked.connect(self.handle_eject_sd_card)
        self.load_sd_btn.clicked.connect(self.handle_load_sd_card)
        self.remember_sd_location_checkbox.toggled.connect(
            self.handle_remember_sd_location_changed
        )

        self.connect_btn.clicked.connect(self.handle_connect_toggle)
        self.connect_save_btn.clicked.connect(self.handle_connect_and_save)
        self.save_profile_btn.clicked.connect(self.handle_save_profile)
        self.scan_btn.clicked.connect(self.handle_scan)

        self.profile_selector.currentIndexChanged.connect(self.handle_profile_selected)
        self.edit_profile_btn.clicked.connect(self.handle_edit_profile)
        self.delete_profile_btn.clicked.connect(self.handle_delete_profile)

        self.ip_input.textEdited.connect(self.on_connection_field_change)
        self.user_input.textEdited.connect(self.on_connection_field_change)
        self.pass_input.textEdited.connect(self.on_connection_field_change)

        self.use_ssh_agent_checkbox.toggled.connect(self.handle_ssh_option_changed)
        self.look_for_ssh_keys_checkbox.toggled.connect(self.handle_ssh_option_changed)

        self.show_support_button.clicked.connect(self.show_support_message)
        self.hide_support_button.clicked.connect(self.hide_support_message)
        self.dismiss_support_button.clicked.connect(self.disable_support_message)
        self.patreon_button.clicked.connect(lambda: open_uri(PATREON_URL))

    def sync_status_from_main_window(self):
        if hasattr(self.main_window, "connection_status_label"):
            self.connection_status_label.setText(
                self.main_window.connection_status_label.text()
            )
            self.connection_status_label.setStyleSheet(
                self.main_window.connection_status_label.styleSheet()
            )

    def is_support_message_enabled(self):
        return bool(self.main_window.config_data.get(CONFIG_SHOW_SUPPORT_MESSAGE, True))

    def apply_support_message_preference(self):
        if not self.is_support_message_enabled():
            self.support_message_hidden = False
            self.support_group.hide()
            self.show_support_button.hide()
            return

        if self.support_message_hidden:
            self.support_group.hide()
            self.show_support_button.show()
        else:
            self.support_group.show()
            self.show_support_button.hide()

    def show_support_message(self):
        if not self.is_support_message_enabled():
            return
        self.support_message_hidden = False
        self.support_group.show()
        self.show_support_button.hide()

    def hide_support_message(self):
        if not self.is_support_message_enabled():
            return
        self.support_message_hidden = True
        self.support_group.hide()
        self.show_support_button.show()

    def disable_support_message(self):
        self.main_window.config_data[CONFIG_SHOW_SUPPORT_MESSAGE] = False
        save_config(self.main_window.config_data)
        self.support_message_hidden = False
        self.support_group.hide()
        self.show_support_button.hide()

    def handle_mode_changed(self):
        if self.mode_switch_in_progress:
            return

        sender = self.sender()

        if sender is not None and hasattr(sender, "isChecked"):
            if not sender.isChecked():
                return

        target_offline = self.offline_mode_radio.isChecked()
        current_offline = self.main_window.is_offline_mode()

        if target_offline == current_offline:
            self.update_mode_state()
            return

        if target_offline and self.connection.is_connected():
            reply = QMessageBox.question(
                self,
                "Switch to Offline Mode",
                (
                    "Switching to Offline Mode will disconnect from the current MiSTer.\n\n"
                    "Continue?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if reply != QMessageBox.StandardButton.Yes:
                self.online_mode_radio.blockSignals(True)
                self.offline_mode_radio.blockSignals(True)
                self.online_mode_radio.setChecked(True)
                self.offline_mode_radio.setChecked(False)
                self.online_mode_radio.blockSignals(False)
                self.offline_mode_radio.blockSignals(False)
                return

        self.mode_switch_in_progress = True
        self.apply_mode_switching_state(target_offline)

        QTimer.singleShot(
            0,
            lambda: self.finish_mode_switch(target_offline),
        )

    def apply_mode_switching_state(self, target_offline: bool):
        self.online_mode_radio.blockSignals(True)
        self.offline_mode_radio.blockSignals(True)
        self.online_mode_radio.setChecked(not target_offline)
        self.offline_mode_radio.setChecked(target_offline)
        self.online_mode_radio.blockSignals(False)
        self.offline_mode_radio.blockSignals(False)

        self.online_controls_widget.setVisible(not target_offline)
        self.offline_group.setVisible(target_offline)

        self.online_mode_radio.setEnabled(False)
        self.offline_mode_radio.setEnabled(False)

        self.mode_hint_label.setStyleSheet("color: #1e88e5; font-weight: bold;")

        if target_offline:
            self.mode_hint_label.setText("Switching to Offline Mode...")
            self.offline_sd_status_label.setText("Refreshing Offline Mode...")
            self.offline_sd_status_label.setStyleSheet(
                "color: #1e88e5; font-weight: bold;"
            )
            self.open_sd_btn.setEnabled(False)
            self.eject_sd_btn.setEnabled(False)
            self.load_sd_btn.setEnabled(False)
        else:
            self.mode_hint_label.setText("Switching to Online Mode...")

    def finish_mode_switch(self, target_offline: bool):
        try:
            if target_offline:
                self.main_window.switch_to_offline_mode(
                    self.offline_sd_input.text().strip()
                )
            else:
                self.main_window.switch_to_online_mode()
        finally:
            self.mode_switch_in_progress = False
            self.online_mode_radio.setEnabled(True)
            self.offline_mode_radio.setEnabled(True)
            self.mode_hint_label.setStyleSheet("color: gray;")
            self.update_mode_state()

    def update_mode_state(self):
        if self.mode_switch_in_progress:
            return

        is_offline = self.main_window.is_offline_mode()

        self.online_mode_radio.blockSignals(True)
        self.offline_mode_radio.blockSignals(True)
        self.online_mode_radio.setChecked(not is_offline)
        self.offline_mode_radio.setChecked(is_offline)
        self.online_mode_radio.blockSignals(False)
        self.offline_mode_radio.blockSignals(False)

        if self.selected_sd_root():
            self.offline_sd_input.setText(self.selected_sd_root())

        self.online_controls_widget.setVisible(not is_offline)
        self.offline_group.setVisible(is_offline)

        if is_offline:
            self.mode_hint_label.setText("Offline Mode works directly on a selected MiSTer SD card.")
            self.mode_hint_label.setStyleSheet("color: gray;")
            self.apply_offline_state()
        else:
            self.mode_hint_label.setText("Online Mode connects to a live MiSTer over SSH.")
            self.mode_hint_label.setStyleSheet("color: gray;")
            self.update_connection_state()

    def apply_offline_state(self):
        self.sync_status_from_main_window()

        if hasattr(self.main_window, "is_offline_sd_loaded") and self.main_window.is_offline_sd_loaded():
            self.state_stack.setCurrentWidget(self.device_dashboard)
            self.device_dashboard.apply_offline_state(lightweight=True)
            QTimer.singleShot(0, self.device_dashboard.refresh_info)
            return

        self.device_dashboard.apply_disconnected_state()
        self.state_stack.setCurrentWidget(self.connection_page)

        sd_root = self.selected_sd_root()
        if sd_root:
            self.offline_sd_status_label.setText(f"Selected SD Card: {sd_root}")
            self.offline_sd_status_label.setStyleSheet(
                "color: #8b5cf6; font-weight: bold;"
            )
            self.open_sd_btn.setEnabled(True)
            self.eject_sd_btn.setEnabled(True)
            self.load_sd_btn.setEnabled(True)
        else:
            self.offline_sd_status_label.setText("No SD card selected.")
            self.offline_sd_status_label.setStyleSheet(
                "color: #f39c12; font-weight: bold;"
            )
            self.open_sd_btn.setEnabled(False)
            self.eject_sd_btn.setEnabled(False)
            self.load_sd_btn.setEnabled(False)

        self.online_mode_radio.setEnabled(True)
        self.offline_mode_radio.setEnabled(True)
        self.show_support_button.setEnabled(True)
        self.hide_support_button.setEnabled(True)

    def selected_sd_root(self) -> str:
        if hasattr(self.main_window, "get_offline_sd_selection"):
            return self.main_window.get_offline_sd_selection()
        return self.main_window.get_offline_sd_root()

    def validate_sd_root(self, path_text: str) -> bool:
        path_text = str(path_text or "").strip()

        if not path_text:
            QMessageBox.warning(
                self,
                "No SD Card Selected",
                "Select the root of your MiSTer SD card first.",
            )
            return False

        root = Path(path_text).expanduser()

        if not root.exists() or not root.is_dir():
            QMessageBox.warning(
                self,
                "Invalid Folder",
                "The selected path does not exist or is not a folder.",
            )
            return False

        strong_markers = [
            "MiSTer",
            "MiSTer.ini",
            "MiSTer_Example.ini",
        ]

        folder_markers = [
            "Scripts",
            "games",
            "_Console",
            "_Computer",
            "_Arcade",
            "_Other",
        ]

        strong_match = any((root / marker).exists() for marker in strong_markers)
        folder_match_count = sum(
            1 for marker in folder_markers if (root / marker).exists()
        )

        if strong_match or folder_match_count >= 2:
            return True

        reply = QMessageBox.question(
            self,
            "Confirm SD Card Folder",
            (
                "This folder does not look like the root of a MiSTer SD card.\n\n"
                "Are you sure you want to use it?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        return reply == QMessageBox.StandardButton.Yes

    def handle_browse_sd_card(self):
        start_dir = (
            self.offline_sd_input.text().strip()
            or self.selected_sd_root()
            or str(Path.home())
        )

        selected = QFileDialog.getExistingDirectory(
            self,
            "Select MiSTer SD Card Root",
            start_dir,
        )

        if not selected:
            return

        self.offline_sd_input.setText(selected)

        if self.validate_sd_root(selected):
            self.main_window.set_offline_sd_root(selected)
            self.main_window.apply_app_mode_state()
            self.update_mode_state()

    def handle_load_sd_card(self):
        sd_root = self.offline_sd_input.text().strip() or self.selected_sd_root()
        if not self.validate_sd_root(sd_root):
            return

        self.main_window.set_offline_sd_root(sd_root)
        if hasattr(self.main_window, "load_offline_sd_card"):
            self.main_window.load_offline_sd_card(sd_root)
        self.update_mode_state()

    def handle_open_sd_card(self):
        sd_root = self.selected_sd_root()
        if not sd_root:
            return

        path = Path(sd_root)
        if not path.exists():
            QMessageBox.warning(
                self,
                "SD Card Not Found",
                "The selected SD card folder no longer exists.",
            )
            return

        open_local_folder(path)

    def handle_eject_sd_card(self):
        sd_root = self.selected_sd_root()
        if not sd_root:
            QMessageBox.warning(
                self,
                "No SD Card Selected",
                "Select an Offline Mode SD card first.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Eject SD Card",
            (
                "This will safely eject the selected Offline Mode SD card.\n\n"
                "Make sure no other MiSTer Companion action is currently writing to it.\n\n"
                "Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.eject_sd_btn.setEnabled(False)
        self.open_sd_btn.setEnabled(False)
        self.load_sd_btn.setEnabled(False)
        self.offline_sd_status_label.setText("Ejecting SD card...")
        self.offline_sd_status_label.setStyleSheet(
            "color: #1e88e5; font-weight: bold;"
        )

        messages = []

        def collect_message(message: str):
            text = str(message or "").strip()
            if text:
                messages.append(text)

        success = eject_sd_card_path(sd_root, collect_message)

        if success:
            self.offline_sd_input.clear()
            self.main_window.set_offline_sd_root("")
            self.main_window.apply_app_mode_state()
            self.update_mode_state()
            QMessageBox.information(
                self,
                "SD Card Ejected",
                "The selected SD card was safely ejected.",
            )
        else:
            details = "\n".join(messages[-6:]).strip()
            message = "MiSTer Companion could not eject the selected SD card automatically."
            if details:
                message += f"\n\nDetails:\n{details}"
            QMessageBox.warning(
                self,
                "Eject Failed",
                message,
            )
            self.update_mode_state()

    def handle_remember_sd_location_changed(self, checked: bool):
        if hasattr(self.main_window, "set_remember_offline_sd_root"):
            current_path = (
                self.selected_sd_root()
                or self.offline_sd_input.text().strip()
            )
            if checked and current_path:
                self.main_window.set_offline_sd_root(current_path)
            self.main_window.set_remember_offline_sd_root(bool(checked))

    def handle_connect_toggle(self):
        if self.connection.is_connected():
            self.save_after_next_connect = False
            self.main_window.disconnect_from_mister()
        else:
            self.save_after_next_connect = False
            self.main_window.connect_to_mister()

    def handle_connect_and_save(self):
        if self.connection.is_connected():
            return

        if self.profile_selector.currentIndex() >= 0:
            return

        self.save_after_next_connect = True
        self.main_window.connect_to_mister()

    def _save_after_successful_connect(self):
        if not self.save_after_next_connect:
            return

        if not self.connection.is_connected():
            return

        self.save_after_next_connect = False
        self.main_window.save_device()

    def handle_scan(self):
        self.main_window.open_network_scanner()

    def update_save_buttons_state(self):
        if self.connection.is_connected():
            self.connect_save_btn.setEnabled(False)
            self.save_profile_btn.setEnabled(False)
            return

        profile_loaded = self.profile_selector.currentIndex() >= 0

        self.connect_save_btn.setEnabled(not profile_loaded)
        self.save_profile_btn.setEnabled(not profile_loaded)

    def apply_connected_state(self):
        self.sync_status_from_main_window()
        self.state_stack.setCurrentWidget(self.device_dashboard)
        self.device_dashboard.apply_connected_state()
        QTimer.singleShot(0, self.device_dashboard.refresh_info)

        self.connect_btn.setText("Disconnect")
        self.connect_btn.setEnabled(True)

        self.online_mode_radio.setEnabled(True)
        self.offline_mode_radio.setEnabled(True)

        self.ip_input.setEnabled(False)
        self.user_input.setEnabled(False)
        self.pass_input.setEnabled(False)

        self.scan_btn.setEnabled(False)
        self.connect_save_btn.setEnabled(False)
        self.save_profile_btn.setEnabled(False)

        self.profile_selector.setEnabled(False)
        self.edit_profile_btn.setEnabled(False)
        self.delete_profile_btn.setEnabled(False)

        self.use_ssh_agent_checkbox.setEnabled(False)
        self.look_for_ssh_keys_checkbox.setEnabled(False)

        self.show_support_button.setEnabled(True)
        self.hide_support_button.setEnabled(True)

        if self.save_after_next_connect:
            QTimer.singleShot(0, self._save_after_successful_connect)

    def apply_disconnected_state(self):
        self.sync_status_from_main_window()
        self.device_dashboard.apply_disconnected_state()
        self.state_stack.setCurrentWidget(self.connection_page)

        self.connect_btn.setText("Connect")
        self.connect_btn.setEnabled(True)

        self.online_mode_radio.setEnabled(True)
        self.offline_mode_radio.setEnabled(True)

        self.ip_input.setEnabled(True)
        self.user_input.setEnabled(True)
        self.pass_input.setEnabled(True)

        self.scan_btn.setEnabled(True)

        self.profile_selector.setEnabled(True)
        self.edit_profile_btn.setEnabled(True)
        self.delete_profile_btn.setEnabled(True)

        self.use_ssh_agent_checkbox.setEnabled(True)
        self.look_for_ssh_keys_checkbox.setEnabled(True)

        self.show_support_button.setEnabled(True)
        self.hide_support_button.setEnabled(True)

        self.save_after_next_connect = False
        self.update_save_buttons_state()

    def update_connection_state(self, lightweight=True):
        del lightweight

        if self.mode_switch_in_progress:
            return

        self.sync_status_from_main_window()

        if hasattr(self.main_window, "is_offline_mode") and self.main_window.is_offline_mode():
            self.apply_offline_state()
            return

        if self.connection.is_connected():
            self.apply_connected_state()
        else:
            self.apply_disconnected_state()

    def handle_profile_selected(self, index):
        if index < 0:
            self.update_save_buttons_state()
            return

        if self.connection.is_connected():
            return

        self.main_window.load_selected_device(index)
        self.update_save_buttons_state()

    def handle_save_profile(self):
        if self.connection.is_connected():
            return

        if self.profile_selector.currentIndex() >= 0:
            return

        self.main_window.save_device()

    def handle_edit_profile(self):
        if self.connection.is_connected():
            return

        self.main_window.edit_device()

    def handle_delete_profile(self):
        if self.connection.is_connected():
            return

        self.main_window.delete_device()

    def on_connection_field_change(self):
        if self.connection.is_connected():
            return

        if self.profile_selector.currentIndex() >= 0:
            self.profile_selector.blockSignals(True)
            self.profile_selector.setCurrentIndex(-1)
            self.profile_selector.blockSignals(False)

        self.update_save_buttons_state()

    def handle_ssh_option_changed(self, _checked=False):
        self.main_window.config_data["use_ssh_agent"] = (
            self.use_ssh_agent_checkbox.isChecked()
        )
        self.main_window.config_data["look_for_ssh_keys"] = (
            self.look_for_ssh_keys_checkbox.isChecked()
        )
        save_config(self.main_window.config_data)

    def set_connection_fields(self, ip="", username="root", password="1"):
        self.ip_input.setText(ip)
        self.user_input.setText(username)
        self.pass_input.setText(password)

    def set_profiles(self, profiles, selected_name=None):
        self.profile_selector.blockSignals(True)
        self.profile_selector.clear()

        selected_index = -1

        for i, profile in enumerate(profiles):
            name = profile.get("name", f"Device {i + 1}")
            self.profile_selector.addItem(name, profile)

            if selected_name and name == selected_name:
                selected_index = i

        self.profile_selector.setCurrentIndex(selected_index)
        self.profile_selector.blockSignals(False)
        self.update_save_buttons_state()

    def get_selected_profile_name(self):
        if self.profile_selector.currentIndex() < 0:
            return ""

        return self.profile_selector.currentText()
    def refresh_theme(self):
        if hasattr(self, "device_dashboard") and hasattr(self.device_dashboard, "refresh_theme"):
            self.device_dashboard.refresh_theme()


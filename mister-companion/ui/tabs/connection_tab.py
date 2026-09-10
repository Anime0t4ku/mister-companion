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
        self.state_stack.setObjectName("ConnectionStateStack")
        outer_layout.addWidget(self.state_stack)

        self.connection_page = QWidget()
        self.connection_page.setObjectName("ConnectionPage")
        main_layout = QVBoxLayout(self.connection_page)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)
        self.state_stack.addWidget(self.connection_page)

        self.device_dashboard = DeviceTab(self.main_window)
        self.state_stack.addWidget(self.device_dashboard)
        self.state_stack.setCurrentWidget(self.connection_page)

        self.connection_page.setStyleSheet(
            """
            QStackedWidget#ConnectionStateStack,
            QWidget#ConnectionPage {
                background: transparent;
            }

            QWidget#ConnectionPage QFrame#StatusBanner,
            QWidget#ConnectionPage QFrame#ModeCard {
                background-color: palette(alternate-base);
                border: 1px solid palette(button);
                border-radius: 10px;
            }

            QWidget#ConnectionPage QGroupBox#ConnectionShell {
                background: transparent;
                border: none;
                margin: 0px;
                padding: 0px;
            }

            QWidget#ConnectionPage QGroupBox#ConnectionShell::title {
                color: transparent;
                background: transparent;
                padding: 0px;
            }

            QWidget#ConnectionPage QGroupBox#ConnectionCard,
            QWidget#ConnectionPage QGroupBox#SupportCard {
                background-color: palette(alternate-base);
                border: 1px solid palette(button);
                border-radius: 12px;
                margin-top: 18px;
                padding: 14px;
                font-weight: 700;
            }

            QWidget#ConnectionPage QGroupBox#ConnectionCard::title,
            QWidget#ConnectionPage QGroupBox#SupportCard::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                padding: 0px 7px;
                background: transparent;
                color: palette(highlight);
            }

            QWidget#ConnectionPage QLabel#SectionHint {
                color: palette(text);
            }

            """
        )

        header_row = QHBoxLayout()
        header_row.setContentsMargins(2, 0, 2, 0)
        header_row.setSpacing(12)

        header_text_layout = QVBoxLayout()
        header_text_layout.setContentsMargins(0, 0, 0, 0)
        header_text_layout.setSpacing(3)

        header_title = QLabel("Connection")
        header_title.setStyleSheet("font-weight: 700; font-size: 19px;")

        self.mode_hint_label = QLabel("Choose Online / SSH or Offline / SD Card mode.")
        self.mode_hint_label.setObjectName("SectionHint")
        self.mode_hint_label.setWordWrap(True)

        header_text_layout.addWidget(header_title)
        header_text_layout.addWidget(self.mode_hint_label)

        self.show_support_button = QPushButton("Show Message")
        set_text_button_min_width(self.show_support_button, 100)
        self.show_support_button.hide()

        header_row.addLayout(header_text_layout, stretch=1)
        header_row.addWidget(self.show_support_button, alignment=Qt.AlignmentFlag.AlignTop)
        main_layout.addLayout(header_row)

        self.status_banner = QFrame()
        self.status_banner.setObjectName("StatusBanner")
        status_layout = QHBoxLayout(self.status_banner)
        status_layout.setContentsMargins(14, 9, 14, 9)
        status_layout.setSpacing(8)

        status_caption = QLabel("Connection status")
        status_caption.setStyleSheet("font-weight: 600;")
        self.connection_status_label = QLabel("Status: Disconnected")
        self.connection_status_label.setStyleSheet("font-weight: 700;")
        self.connection_status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        status_layout.addWidget(status_caption)
        status_layout.addStretch()
        status_layout.addWidget(self.connection_status_label)
        self.status_banner.setMaximumWidth(820)
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.addStretch(1)
        status_row.addWidget(self.status_banner)
        status_row.addStretch(1)
        main_layout.addLayout(status_row)

        self.content_row = QHBoxLayout()
        self.content_row.setSpacing(24)
        main_layout.addLayout(self.content_row, stretch=1)

        self.connection_group = QGroupBox("")
        self.connection_group.setObjectName("ConnectionShell")
        self.connection_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.connection_group.setMaximumWidth(820)

        connection_layout = QVBoxLayout()
        connection_layout.setContentsMargins(0, 0, 0, 0)
        connection_layout.setSpacing(12)
        self.connection_group.setLayout(connection_layout)

        self.mode_frame = QFrame()
        self.mode_frame.setObjectName("ModeCard")
        mode_layout = QHBoxLayout(self.mode_frame)
        mode_layout.setContentsMargins(14, 11, 14, 11)
        mode_layout.setSpacing(14)

        mode_label = QLabel("Mode")
        mode_label.setStyleSheet("font-weight: 700;")
        self.online_mode_radio = QRadioButton("Online / SSH")
        self.offline_mode_radio = QRadioButton("Offline / SD Card")
        self.online_mode_radio.setChecked(True)

        mode_layout.addWidget(mode_label)
        mode_layout.addStretch()
        mode_layout.addWidget(self.online_mode_radio)
        mode_layout.addWidget(self.offline_mode_radio)
        connection_layout.addWidget(self.mode_frame)

        self.online_controls_widget = QWidget()
        online_layout = QVBoxLayout(self.online_controls_widget)
        online_layout.setContentsMargins(0, 0, 0, 0)
        online_layout.setSpacing(12)

        self.saved_group = QGroupBox("Saved Device Profiles")
        self.saved_group.setObjectName("ConnectionCard")
        saved_layout = QHBoxLayout(self.saved_group)
        saved_layout.setContentsMargins(16, 18, 16, 14)
        saved_layout.setSpacing(10)

        profile_label = QLabel("Profile")
        profile_label.setStyleSheet("font-weight: 600;")
        self.profile_selector = QComboBox()
        self.profile_selector.setPlaceholderText("Select Device")
        self.profile_selector.setCurrentIndex(-1)
        self.profile_selector.setMinimumWidth(260)
        self.profile_selector.setMaximumWidth(420)
        self.profile_selector.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.edit_profile_btn = QPushButton("Edit")
        set_text_button_min_width(self.edit_profile_btn, 80)
        self.delete_profile_btn = QPushButton("Delete")
        set_text_button_min_width(self.delete_profile_btn, 80)

        saved_layout.addStretch(1)
        saved_layout.addWidget(profile_label)
        saved_layout.addWidget(self.profile_selector, stretch=1)
        saved_layout.addWidget(self.edit_profile_btn)
        saved_layout.addWidget(self.delete_profile_btn)
        saved_layout.addStretch(1)
        online_layout.addWidget(self.saved_group)

        self.details_group = QGroupBox("Connection Details")
        self.details_group.setObjectName("ConnectionCard")
        details_layout = QGridLayout(self.details_group)
        details_layout.setContentsMargins(16, 20, 16, 14)
        details_layout.setHorizontalSpacing(10)
        details_layout.setVerticalSpacing(6)

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("MiSTer IP")
        self.ip_input.setMinimumWidth(150)

        self.user_input = QLineEdit()
        self.user_input.setText("root")
        self.user_input.setMinimumWidth(130)

        self.pass_input = QLineEdit()
        self.pass_input.setText("1")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setMinimumWidth(130)

        self.scan_btn = QPushButton("Scan Network")
        self.scan_btn.setMinimumWidth(150)

        ip_label = QLabel("IP Address")
        user_label = QLabel("Username")
        pass_label = QLabel("Password")
        for label in (ip_label, user_label, pass_label):
            label.setStyleSheet("font-weight: 600;")

        details_layout.addWidget(ip_label, 0, 0)
        details_layout.addWidget(user_label, 0, 1)
        details_layout.addWidget(pass_label, 0, 2)
        details_layout.addWidget(self.ip_input, 1, 0)
        details_layout.addWidget(self.user_input, 1, 1)
        details_layout.addWidget(self.pass_input, 1, 2)
        details_layout.addWidget(
            self.scan_btn,
            1,
            3,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        details_layout.setColumnStretch(0, 2)
        details_layout.setColumnStretch(1, 1)
        details_layout.setColumnStretch(2, 1)
        online_layout.addWidget(self.details_group)

        self.actions_group = QGroupBox("Actions")
        self.actions_group.setObjectName("ConnectionCard")
        actions_layout = QHBoxLayout(self.actions_group)
        actions_layout.setContentsMargins(16, 20, 16, 14)
        actions_layout.setSpacing(10)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("PrimaryAction")
        self.connect_btn.setMinimumWidth(120)

        self.connect_save_btn = QPushButton("Connect && Save")
        self.connect_save_btn.setMinimumWidth(130)

        self.save_profile_btn = QPushButton("Save Only")
        self.save_profile_btn.setMinimumWidth(110)

        actions_layout.addStretch(1)
        actions_layout.addWidget(self.connect_btn)
        actions_layout.addWidget(self.connect_save_btn)
        actions_layout.addWidget(self.save_profile_btn)
        actions_layout.addStretch(1)
        online_layout.addWidget(self.actions_group)

        self.advanced_group = QGroupBox("Advanced SSH Options")
        self.advanced_group.setObjectName("ConnectionCard")
        advanced_layout = QVBoxLayout(self.advanced_group)
        advanced_layout.setContentsMargins(16, 20, 16, 14)
        advanced_layout.setSpacing(10)

        self.advanced_ssh_warning_label = QLabel(
            "Only enable these if you know you need them."
        )
        self.advanced_ssh_warning_label.setStyleSheet("color: #f39c12;")
        self.advanced_ssh_warning_label.setWordWrap(True)

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
        ssh_options_row.setSpacing(18)
        ssh_options_row.addWidget(self.use_ssh_agent_checkbox)
        ssh_options_row.addWidget(self.look_for_ssh_keys_checkbox)
        ssh_options_row.addStretch()

        advanced_layout.addWidget(self.advanced_ssh_warning_label)
        advanced_layout.addLayout(ssh_options_row)
        online_layout.addWidget(self.advanced_group)

        connection_layout.addWidget(self.online_controls_widget)

        self.offline_group = QGroupBox("Offline SD Card")
        self.offline_group.setObjectName("ConnectionCard")
        offline_layout = QVBoxLayout(self.offline_group)
        offline_layout.setContentsMargins(16, 20, 16, 14)
        offline_layout.setSpacing(12)

        offline_info_label = QLabel(
            "Offline Mode works directly on the selected MiSTer SD card. "
            "Enable Remember SD location to keep the latest selected path after closing MiSTer Companion."
        )
        offline_info_label.setWordWrap(True)
        offline_info_label.setObjectName("SectionHint")

        offline_row = QHBoxLayout()
        offline_row.setSpacing(10)

        self.offline_sd_input = QLineEdit()
        self.offline_sd_input.setPlaceholderText("MiSTer SD card root")
        self.offline_sd_input.setText(self.selected_sd_root())
        self.offline_sd_input.setMinimumWidth(320)
        self.offline_sd_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.browse_sd_btn = QPushButton("Browse...")
        set_text_button_min_width(self.browse_sd_btn, 100)
        offline_row.addStretch(1)
        offline_row.addWidget(self.offline_sd_input, stretch=1)
        offline_row.addWidget(self.browse_sd_btn)
        offline_row.addStretch(1)

        self.remember_sd_location_checkbox = QCheckBox("Remember SD location")
        self.remember_sd_location_checkbox.setChecked(
            self.main_window.should_remember_offline_sd_root()
            if hasattr(self.main_window, "should_remember_offline_sd_root")
            else False
        )
        self.remember_sd_location_checkbox.setToolTip(
            "When enabled, MiSTer Companion remembers the latest selected Offline Mode SD card path after closing."
        )

        offline_actions_row = QHBoxLayout()
        offline_actions_row.setSpacing(10)

        self.open_sd_btn = QPushButton("Open SD Card")
        self.open_sd_btn.setMinimumWidth(120)

        self.eject_sd_btn = QPushButton("Eject SD Card")
        self.eject_sd_btn.setMinimumWidth(120)

        self.load_sd_btn = QPushButton("Load SD Card")
        self.load_sd_btn.setObjectName("PrimaryAction")
        self.load_sd_btn.setMinimumWidth(120)

        offline_actions_row.addStretch(1)
        offline_actions_row.addWidget(self.open_sd_btn)
        offline_actions_row.addWidget(self.eject_sd_btn)
        offline_actions_row.addWidget(self.load_sd_btn)
        offline_actions_row.addStretch(1)

        self.offline_sd_status_label = QLabel("")

        offline_layout.addWidget(offline_info_label)
        offline_layout.addLayout(offline_row)
        offline_layout.addWidget(self.remember_sd_location_checkbox)
        offline_layout.addLayout(offline_actions_row)
        offline_layout.addWidget(self.offline_sd_status_label)

        connection_layout.addWidget(self.offline_group)
        connection_layout.addStretch()

        self.content_row.addStretch(1)
        self.content_row.addWidget(
            self.connection_group,
            alignment=Qt.AlignmentFlag.AlignTop,
        )

        self.support_group = QGroupBox("Thank You")
        self.support_group.setObjectName("SupportCard")
        self.support_group.setMinimumWidth(320)
        self.support_group.setMaximumWidth(380)
        self.support_group.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

        support_layout = QVBoxLayout(self.support_group)
        support_layout.setContentsMargins(18, 22, 18, 18)
        support_layout.setSpacing(12)

        support_header_row = QHBoxLayout()
        support_header_row.setSpacing(8)

        self.hide_support_button = QPushButton("Hide")
        set_text_button_min_width(self.hide_support_button, 70)
        support_header_row.addStretch()
        support_header_row.addWidget(self.hide_support_button)

        self.support_headline_label = QLabel("Thank you for using MiSTer Companion!")
        self.support_headline_label.setWordWrap(True)
        self.support_headline_label.setTextFormat(Qt.TextFormat.PlainText)
        self.support_headline_label.setStyleSheet("font-size: 15px; font-weight: 700;")

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
        self.patreon_button.setObjectName("PrimaryAction")
        set_text_button_min_width(self.patreon_button, 120)

        self.dismiss_support_button = QPushButton("Don't show this again")
        set_text_button_min_width(self.dismiss_support_button, 170)

        support_button_row = QHBoxLayout()
        support_button_row.addStretch(1)
        support_button_row.addWidget(self.patreon_button)
        support_button_row.addStretch(1)

        dismiss_row = QHBoxLayout()
        dismiss_row.addStretch(1)
        dismiss_row.addWidget(self.dismiss_support_button)
        dismiss_row.addStretch(1)

        support_layout.addLayout(support_header_row)
        support_layout.addWidget(self.support_headline_label)
        support_layout.addWidget(self.support_message_label)
        support_layout.addLayout(support_button_row)
        support_layout.addStretch()
        support_layout.addLayout(dismiss_row)

        self.support_group.hide()
        self.content_row.addWidget(
            self.support_group,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        self.content_row.addStretch(1)

        QTimer.singleShot(0, self.sync_support_height)

    def sync_support_height(self):
        if not hasattr(self, "support_group") or not hasattr(self, "connection_group"):
            return
        self.connection_group.adjustSize()
        target_height = self.connection_group.sizeHint().height()
        if target_height > 0:
            self.support_group.setFixedHeight(target_height)

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
            QTimer.singleShot(0, self.sync_support_height)

    def show_support_message(self):
        if not self.is_support_message_enabled():
            return
        self.support_message_hidden = False
        self.support_group.show()
        self.show_support_button.hide()
        QTimer.singleShot(0, self.sync_support_height)

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
        QTimer.singleShot(0, self.sync_support_height)

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


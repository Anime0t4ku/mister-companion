import time
from pathlib import Path

import requests
from core.open_helpers import open_uri, open_local_folder
from PyQt6.QtCore import QEvent, QTimer, Qt
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
    QVBoxLayout,
    QWidget,
)

from ui.scaling import set_text_button_min_width
from core.config import save_config

NEWSWIDGET_URL = "https://raw.githubusercontent.com/Anime0t4ku/mister-companion/main/newsfeed.json"
NEWS_ROTATION_INTERVAL_MS = 10000
CONFIG_SHOW_NEWS_WIDGET = "show_news_widget"


class ConnectionTab(QWidget):
    def __init__(self, main_window):
        super().__init__()

        self.main_window = main_window
        self.connection = main_window.connection

        self.news_items = []
        self.current_news_index = 0
        self.news_url = ""
        self.news_hovered = False

        self.save_after_next_connect = False
        self.mode_switch_in_progress = False

        self.news_timer = QTimer(self)
        self.news_timer.timeout.connect(self.show_next_news)

        self.init_ui()
        self.connect_signals()
        self.update_mode_state()
        self.update_connection_state()

        if self.is_news_widget_enabled():
            self.load_news_widget()
        else:
            self.hide_news_widget(update_config=False)

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        self.setLayout(main_layout)

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

        self.show_news_button = QPushButton("Show News")
        self.show_news_button.hide()

        show_news_button_width = self.show_news_button.sizeHint().width()

        self.show_news_button_placeholder = QWidget()
        self.show_news_button_placeholder.setFixedWidth(show_news_button_width)

        self.show_news_button_container = QWidget()
        self.show_news_button_container.setFixedWidth(show_news_button_width)

        show_news_button_layout = QHBoxLayout(self.show_news_button_container)
        show_news_button_layout.setContentsMargins(0, 0, 0, 0)
        show_news_button_layout.setSpacing(0)
        show_news_button_layout.addWidget(self.show_news_button)

        header_row.addWidget(self.show_news_button_placeholder)
        header_row.addStretch()
        header_row.addLayout(header_text_layout)
        header_row.addStretch()
        header_row.addWidget(self.show_news_button_container)

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
            "The selected path is only kept while MiSTer Companion is open."
        )
        offline_info_label.setWordWrap(True)
        offline_info_label.setStyleSheet("color: gray;")
        offline_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        offline_row = QHBoxLayout()
        offline_row.setSpacing(8)
        offline_row.addStretch()

        self.offline_sd_input = QLineEdit()
        self.offline_sd_input.setPlaceholderText("MiSTer SD card root")
        self.offline_sd_input.setText(self.main_window.get_offline_sd_root())
        self.offline_sd_input.setMinimumWidth(320)
        self.offline_sd_input.setMaximumWidth(520)

        self.browse_sd_btn = QPushButton("Browse...")
        set_text_button_min_width(self.browse_sd_btn, 100)
        offline_row.addWidget(self.offline_sd_input)
        offline_row.addWidget(self.browse_sd_btn)
        offline_row.addStretch()

        offline_actions_row = QHBoxLayout()
        offline_actions_row.setSpacing(8)

        self.open_sd_btn = QPushButton("Open SD Card")
        self.open_sd_btn.setMinimumWidth(120)

        self.clear_sd_btn = QPushButton("Clear Selection")
        self.clear_sd_btn.setMinimumWidth(120)

        offline_actions_row.addStretch()
        offline_actions_row.addWidget(self.open_sd_btn)
        offline_actions_row.addWidget(self.clear_sd_btn)
        offline_actions_row.addStretch()

        self.offline_sd_status_label = QLabel("")
        self.offline_sd_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        offline_layout.addWidget(offline_info_label)
        offline_layout.addLayout(offline_row)
        offline_layout.addLayout(offline_actions_row)
        offline_layout.addWidget(self.offline_sd_status_label)

        self.offline_group.setLayout(offline_layout)
        connection_layout.addWidget(self.offline_group)

        connection_layout.addStretch()

        self.content_row.addWidget(self.connection_group, stretch=1)

        self.news_group = QGroupBox("Newsfeed")
        self.news_group.installEventFilter(self)
        self.news_group.setMinimumWidth(320)
        self.news_group.setMaximumWidth(380)
        self.news_group.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )

        news_layout = QVBoxLayout()
        news_layout.setContentsMargins(16, 16, 16, 16)
        news_layout.setSpacing(10)

        news_header_row = QHBoxLayout()
        news_header_row.setSpacing(8)

        self.hide_news_button = QPushButton("Hide")
        set_text_button_min_width(self.hide_news_button, 70)
        news_header_row.addStretch()
        news_header_row.addWidget(self.hide_news_button)
        news_header_row.addStretch()

        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)

        self.news_prev_button = QPushButton("◀")
        set_text_button_min_width(self.news_prev_button, 36)
        self.news_prev_button.hide()

        self.news_next_button = QPushButton("▶")
        set_text_button_min_width(self.news_next_button, 36)
        self.news_next_button.hide()

        self.news_counter_label = QLabel("")
        self.news_counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        nav_row.addWidget(self.news_prev_button)
        nav_row.addStretch()
        nav_row.addWidget(self.news_counter_label)
        nav_row.addStretch()
        nav_row.addWidget(self.news_next_button)

        self.news_headline_label = QLabel("")
        self.news_headline_label.setWordWrap(True)
        self.news_headline_label.setTextFormat(Qt.TextFormat.PlainText)
        self.news_headline_label.setStyleSheet("font-size: 15px; font-weight: bold;")

        self.news_message_label = QLabel("")
        self.news_message_label.setWordWrap(True)
        self.news_message_label.setTextFormat(Qt.TextFormat.PlainText)

        self.news_button = QPushButton("")
        self.news_button.setVisible(False)
        set_text_button_min_width(self.news_button, 160)
        self.news_date_label = QLabel("")
        self.news_date_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.news_date_label.setStyleSheet("color: gray;")

        button_row = QHBoxLayout()
        button_row.addWidget(self.news_button)
        button_row.addStretch()

        news_layout.addLayout(news_header_row)
        news_layout.addLayout(nav_row)
        news_layout.addWidget(self.news_headline_label)
        news_layout.addWidget(self.news_message_label)
        news_layout.addLayout(button_row)
        news_layout.addStretch()
        news_layout.addWidget(self.news_date_label)

        self.news_group.setLayout(news_layout)
        self.news_group.hide()

        self.content_row.addWidget(self.news_group)

    def connect_signals(self):
        self.online_mode_radio.toggled.connect(self.handle_mode_changed)
        self.offline_mode_radio.toggled.connect(self.handle_mode_changed)

        self.browse_sd_btn.clicked.connect(self.handle_browse_sd_card)
        self.open_sd_btn.clicked.connect(self.handle_open_sd_card)
        self.clear_sd_btn.clicked.connect(self.handle_clear_sd_card)

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

        self.show_news_button.clicked.connect(lambda: self.show_news_widget())
        self.hide_news_button.clicked.connect(lambda: self.hide_news_widget())

        self.news_button.clicked.connect(self.open_news_link)
        self.news_prev_button.clicked.connect(self.show_previous_news)
        self.news_next_button.clicked.connect(self.show_next_news)

    def sync_status_from_main_window(self):
        if hasattr(self.main_window, "connection_status_label"):
            self.connection_status_label.setText(
                self.main_window.connection_status_label.text()
            )
            self.connection_status_label.setStyleSheet(
                self.main_window.connection_status_label.styleSheet()
            )

    def is_news_widget_enabled(self):
        return self.main_window.config_data.get(CONFIG_SHOW_NEWS_WIDGET, True)

    def show_news_widget(self):
        self.main_window.config_data[CONFIG_SHOW_NEWS_WIDGET] = True
        save_config(self.main_window.config_data)
        self.show_news_button.hide()
        self.load_news_widget()

    def hide_news_widget(self, update_config=True):
        if update_config:
            self.main_window.config_data[CONFIG_SHOW_NEWS_WIDGET] = False
            save_config(self.main_window.config_data)

        self.news_group.hide()
        self.show_news_button.show()
        self.news_items = []
        self.current_news_index = 0
        self.news_url = ""
        self.stop_news_rotation()

    def eventFilter(self, watched, event):
        if watched is self.news_group:
            if event.type() == QEvent.Type.Enter:
                self.news_hovered = True
                self.update_news_nav_visibility()
                self.stop_news_rotation()
            elif event.type() == QEvent.Type.Leave:
                self.news_hovered = False
                self.update_news_nav_visibility()
                self.start_news_rotation_if_needed()

        return super().eventFilter(watched, event)

    def load_news_widget(self):
        if not self.is_news_widget_enabled():
            self.hide_news_widget(update_config=False)
            return

        self.news_group.hide()
        self.show_news_button.hide()
        self.news_items = []
        self.current_news_index = 0
        self.news_url = ""
        self.stop_news_rotation()

        try:
            url = f"{NEWSWIDGET_URL}?t={int(time.time())}"
            response = requests.get(url, timeout=5)
            response.raise_for_status()

            data = response.json()
            items = data.get("items", [])

            valid_items = []
            for item in items:
                headline = str(item.get("headline", "")).strip()
                message = str(item.get("message", "")).strip()
                if headline or message:
                    valid_items.append(item)

            if not valid_items:
                self.show_news_button.show()
                return

            self.news_items = valid_items
            self.current_news_index = 0
            self.show_news_item(self.current_news_index)
            self.news_group.show()
            self.start_news_rotation_if_needed()

        except Exception:
            self.news_group.hide()
            self.show_news_button.show()

    def show_news_item(self, index):
        if not self.is_news_widget_enabled():
            self.hide_news_widget(update_config=False)
            return

        if not self.news_items:
            self.news_group.hide()
            self.show_news_button.show()
            return

        index %= len(self.news_items)
        self.current_news_index = index

        item = self.news_items[index]

        headline = str(item.get("headline", "")).strip()
        message = str(item.get("message", "")).strip()
        news_type = str(item.get("type", "info")).strip().lower()
        date_text = str(item.get("date", "")).strip()
        url = str(item.get("url", "")).strip()
        url_label = str(item.get("url_label", "")).strip() or "Open"

        color_map = {
            "info": "#4da3ff",
            "update": "#00aa00",
            "warning": "#ff8800",
        }
        headline_color = color_map.get(news_type, "#4da3ff")

        self.news_headline_label.setText(headline)
        self.news_headline_label.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {headline_color};"
        )

        self.news_message_label.setText(message)

        if url:
            self.news_url = url
            self.news_button.setText(url_label)
            self.news_button.setVisible(True)
        else:
            self.news_url = ""
            self.news_button.setVisible(False)

        if date_text:
            self.news_date_label.setText(f"Posted: {date_text}")
            self.news_date_label.show()
        else:
            self.news_date_label.hide()

        if len(self.news_items) > 1:
            self.news_counter_label.setText(f"{index + 1} / {len(self.news_items)}")
            self.news_counter_label.show()
        else:
            self.news_counter_label.hide()

        self.update_news_nav_visibility()

    def show_next_news(self):
        if len(self.news_items) <= 1:
            return

        self.show_news_item(self.current_news_index + 1)

    def show_previous_news(self):
        if len(self.news_items) <= 1:
            return

        self.show_news_item(self.current_news_index - 1)

    def update_news_nav_visibility(self):
        show_nav = (
            self.is_news_widget_enabled()
            and self.news_hovered
            and len(self.news_items) > 1
        )
        self.news_prev_button.setVisible(show_nav)
        self.news_next_button.setVisible(show_nav)

    def start_news_rotation_if_needed(self):
        if (
            self.is_news_widget_enabled()
            and len(self.news_items) > 1
            and not self.news_hovered
        ):
            if not self.news_timer.isActive():
                self.news_timer.start(NEWS_ROTATION_INTERVAL_MS)

    def stop_news_rotation(self):
        if self.news_timer.isActive():
            self.news_timer.stop()

    def open_news_link(self):
        if self.news_url:
            open_uri(self.news_url)

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
            self.clear_sd_btn.setEnabled(False)
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

        if self.main_window.get_offline_sd_root():
            self.offline_sd_input.setText(self.main_window.get_offline_sd_root())

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

        sd_root = self.main_window.get_offline_sd_root()
        if sd_root:
            self.offline_sd_status_label.setText(f"Selected SD Card: {sd_root}")
            self.offline_sd_status_label.setStyleSheet(
                "color: #8b5cf6; font-weight: bold;"
            )
            self.open_sd_btn.setEnabled(True)
            self.clear_sd_btn.setEnabled(True)
        else:
            self.offline_sd_status_label.setText("No SD card selected.")
            self.offline_sd_status_label.setStyleSheet(
                "color: #f39c12; font-weight: bold;"
            )
            self.open_sd_btn.setEnabled(False)
            self.clear_sd_btn.setEnabled(False)

        self.online_mode_radio.setEnabled(True)
        self.offline_mode_radio.setEnabled(True)
        self.show_news_button.setEnabled(True)
        self.hide_news_button.setEnabled(True)

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
            or self.main_window.get_offline_sd_root()
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
            self.mode_switch_in_progress = True
            self.apply_mode_switching_state(True)

            QTimer.singleShot(
                0,
                lambda: self.finish_mode_switch(True),
            )

    def handle_open_sd_card(self):
        sd_root = self.main_window.get_offline_sd_root()
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

    def handle_clear_sd_card(self):
        self.offline_sd_input.clear()
        self.main_window.set_offline_sd_root("")
        self.main_window.apply_app_mode_state()
        self.update_mode_state()

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

        self.show_news_button.setEnabled(True)
        self.hide_news_button.setEnabled(True)

        if self.save_after_next_connect:
            QTimer.singleShot(0, self._save_after_successful_connect)

    def apply_disconnected_state(self):
        self.sync_status_from_main_window()

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

        self.show_news_button.setEnabled(True)
        self.hide_news_button.setEnabled(True)

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
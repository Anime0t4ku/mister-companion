import json
import time
import webbrowser

import requests
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QGroupBox,
    QSizePolicy,
)


NEWSWIDGET_URL = "https://raw.githubusercontent.com/Anime0t4ku/mister-companion/main/newswidget.json"


class ConnectionTab(QWidget):
    def __init__(self, main_window):
        super().__init__()

        self.main_window = main_window
        self.connection = main_window.connection

        self.news_url = ""

        self.init_ui()
        self.connect_signals()
        self.apply_disconnected_state()
        self.sync_status_from_main_window()
        self.load_news_widget()

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(14)

        # =========================
        # Connection Status
        # =========================
        self.connection_status_label = QLabel("Status: Disconnected")
        self.connection_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.connection_status_label)

        # =========================
        # Saved Devices
        # =========================
        saved_group = QGroupBox("Saved Devices")
        saved_layout = QHBoxLayout()
        saved_layout.setContentsMargins(12, 14, 12, 12)
        saved_layout.setSpacing(10)

        self.profile_selector = QComboBox()
        self.profile_selector.setMinimumWidth(200)
        self.profile_selector.setMaximumWidth(260)
        self.profile_selector.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.profile_selector.setPlaceholderText("Select Device")
        self.profile_selector.setCurrentIndex(-1)

        self.save_profile_btn = QPushButton("Save Device")
        self.edit_profile_btn = QPushButton("Edit Device")
        self.delete_profile_btn = QPushButton("Delete Device")

        saved_layout.addStretch()
        saved_layout.addWidget(self.profile_selector)
        saved_layout.addWidget(self.save_profile_btn)
        saved_layout.addWidget(self.edit_profile_btn)
        saved_layout.addWidget(self.delete_profile_btn)
        saved_layout.addStretch()

        saved_group.setLayout(saved_layout)

        # =========================
        # Connection Row
        # =========================
        self.ip_label = QLabel("IP:")
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("MiSTer IP")
        self.ip_input.setFixedWidth(110)

        self.user_label = QLabel("User:")
        self.user_input = QLineEdit()
        self.user_input.setText("root")
        self.user_input.setFixedWidth(80)

        self.pass_label = QLabel("Pass:")
        self.pass_input = QLineEdit()
        self.pass_input.setText("1")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setFixedWidth(80)

        self.scan_btn = QPushButton("Scan Network")
        self.connect_btn = QPushButton("Connect")
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setEnabled(False)

        self.defaults_label = QLabel("(Defaults: root / 1)")
        self.defaults_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        connection_row = QHBoxLayout()
        connection_row.setSpacing(6)

        center_wrapper = QHBoxLayout()
        center_wrapper.setSpacing(6)

        center_wrapper.addWidget(self.ip_label)
        center_wrapper.addWidget(self.ip_input)

        center_wrapper.addWidget(self.user_label)
        center_wrapper.addWidget(self.user_input)

        center_wrapper.addWidget(self.pass_label)
        center_wrapper.addWidget(self.pass_input)

        center_wrapper.addWidget(self.scan_btn)
        center_wrapper.addWidget(self.connect_btn)
        center_wrapper.addWidget(self.disconnect_btn)
        center_wrapper.addWidget(self.defaults_label)

        connection_row.addStretch()
        connection_row.addLayout(center_wrapper)
        connection_row.addStretch()

        # =========================
        # News Widget
        # =========================
        self.news_group = QGroupBox("MiSTer Companion News")
        news_layout = QVBoxLayout()
        news_layout.setContentsMargins(16, 16, 16, 16)
        news_layout.setSpacing(10)

        self.news_headline_label = QLabel("")
        self.news_headline_label.setWordWrap(True)
        self.news_headline_label.setTextFormat(Qt.TextFormat.PlainText)
        self.news_headline_label.setStyleSheet("font-size: 15px; font-weight: bold;")

        self.news_message_label = QLabel("")
        self.news_message_label.setWordWrap(True)
        self.news_message_label.setTextFormat(Qt.TextFormat.PlainText)

        self.news_button = QPushButton("")
        self.news_button.setVisible(False)
        self.news_button.setFixedWidth(140)

        self.news_date_label = QLabel("")
        self.news_date_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.news_date_label.setStyleSheet("color: gray;")

        button_row = QHBoxLayout()
        button_row.addWidget(self.news_button)
        button_row.addStretch()

        news_layout.addWidget(self.news_headline_label)
        news_layout.addWidget(self.news_message_label)
        news_layout.addLayout(button_row)
        news_layout.addWidget(self.news_date_label)

        self.news_group.setLayout(news_layout)
        self.news_group.hide()

        main_layout.addWidget(saved_group)
        main_layout.addLayout(connection_row)

        main_layout.addStretch()

        main_layout.addWidget(self.news_group)

        self.setLayout(main_layout)

    def connect_signals(self):
        self.connect_btn.clicked.connect(self.handle_connect)
        self.disconnect_btn.clicked.connect(self.handle_disconnect)
        self.scan_btn.clicked.connect(self.handle_scan)

        self.profile_selector.currentIndexChanged.connect(self.handle_profile_selected)

        self.save_profile_btn.clicked.connect(self.handle_save_profile)
        self.edit_profile_btn.clicked.connect(self.handle_edit_profile)
        self.delete_profile_btn.clicked.connect(self.handle_delete_profile)

        self.ip_input.textEdited.connect(self.on_connection_field_change)
        self.user_input.textEdited.connect(self.on_connection_field_change)
        self.pass_input.textEdited.connect(self.on_connection_field_change)

        self.news_button.clicked.connect(self.open_news_link)

    # =============================
    # Status Sync
    # =============================

    def sync_status_from_main_window(self):
        if hasattr(self.main_window, "connection_status_label"):
            self.connection_status_label.setText(self.main_window.connection_status_label.text())
            self.connection_status_label.setStyleSheet(self.main_window.connection_status_label.styleSheet())

    # =============================
    # News Widget
    # =============================

    def load_news_widget(self):
        self.news_group.hide()
        self.news_url = ""

        try:
            url = f"{NEWSWIDGET_URL}?t={int(time.time())}"
            response = requests.get(url, timeout=5)
            response.raise_for_status()

            data = response.json()
            items = data.get("items", [])

            if not items:
                return

            item = items[0]
            headline = item.get("headline", "").strip()
            message = item.get("message", "").strip()

            if not headline and not message:
                return

            news_type = item.get("type", "info").strip().lower()
            date_text = item.get("date", "").strip()
            url = item.get("url", "").strip()
            url_label = item.get("url_label", "").strip() or "Open"

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

            self.news_group.show()

        except Exception:
            self.news_group.hide()

    def open_news_link(self):
        if self.news_url:
            webbrowser.open(self.news_url)

    # =============================
    # Connection Logic
    # =============================

    def handle_connect(self):
        self.main_window.connect_to_mister()

    def handle_disconnect(self):
        self.main_window.disconnect_from_mister()

    def handle_scan(self):
        self.main_window.open_network_scanner()

    def apply_connected_state(self):
        self.sync_status_from_main_window()

        self.ip_input.setEnabled(False)
        self.user_input.setEnabled(False)
        self.pass_input.setEnabled(False)

        self.scan_btn.setEnabled(False)
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)

        self.profile_selector.setEnabled(False)
        self.save_profile_btn.setEnabled(False)
        self.edit_profile_btn.setEnabled(False)
        self.delete_profile_btn.setEnabled(False)

    def apply_disconnected_state(self):
        self.sync_status_from_main_window()

        self.ip_input.setEnabled(True)
        self.user_input.setEnabled(True)
        self.pass_input.setEnabled(True)

        self.scan_btn.setEnabled(True)
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)

        self.profile_selector.setEnabled(True)
        self.save_profile_btn.setEnabled(True)
        self.edit_profile_btn.setEnabled(True)
        self.delete_profile_btn.setEnabled(True)

    def update_connection_state(self):
        self.sync_status_from_main_window()

        if self.connection.is_connected():
            self.apply_connected_state()
        else:
            self.apply_disconnected_state()

    # =============================
    # Profile Actions
    # =============================

    def handle_profile_selected(self, index):
        if index < 0:
            return

        self.main_window.load_selected_device(index)

    def handle_save_profile(self):
        self.main_window.save_device()

    def handle_edit_profile(self):
        self.main_window.edit_device()

    def handle_delete_profile(self):
        self.main_window.delete_device()

    def on_connection_field_change(self):
        if self.connection.is_connected():
            return

        if self.profile_selector.currentIndex() >= 0:
            self.profile_selector.blockSignals(True)
            self.profile_selector.setCurrentIndex(-1)
            self.profile_selector.blockSignals(False)

    # =============================
    # Helpers
    # =============================

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

    def get_selected_profile_name(self):
        if self.profile_selector.currentIndex() < 0:
            return ""

        return self.profile_selector.currentText()
from core.open_helpers import open_uri

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config import load_config
from core.scripts_mister_monitor import (
    load_mister_monitor_ra_config,
    save_mister_monitor_ra_config,
)
from ui.scaling import set_text_button_min_width


RA_SETTINGS_URL = "https://retroachievements.org/settings"
CONFIG_RA_USERNAME = "retroachievements_username"
CONFIG_RA_API_KEY = "retroachievements_api_key"


class MiSTerMonitorConfigWidget(QWidget):
    saved = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, connection, main_window=None, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.main_window = main_window
        self.build_ui()

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 8)
        outer.addStretch(1)

        centered = QHBoxLayout()
        centered.addStretch(1)

        card = QGroupBox("RetroAchievements Settings")
        card.setMaximumWidth(720)
        card.setMaximumHeight(320)
        card.setStyleSheet(
            "QGroupBox { background-color: palette(alternate-base); "
            "border: 1px solid palette(button); border-radius: 12px; "
            "margin-top: 18px; padding: 14px; font-weight: 700; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 14px; "
            "padding: 0px 7px; color: palette(highlight); }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 24, 18, 18)
        layout.setSpacing(14)

        info = QLabel(
            "Enter the RetroAchievements username and Web API key that MiSTer Monitor "
            "should use. You can open your RetroAchievements settings or copy the login "
            "already saved in MiSTer Companion."
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-weight: normal;")
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(10)
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("RetroAchievements username")
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("RetroAchievements Web API key")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Username:", self.username_edit)
        form.addRow("API Key:", self.api_key_edit)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.open_settings_button = QPushButton("Open in Browser")
        self.use_saved_login_button = QPushButton("Use Saved Login")
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")
        set_text_button_min_width(self.open_settings_button, 150)
        set_text_button_min_width(self.use_saved_login_button, 140)
        set_text_button_min_width(self.save_button, 100)
        set_text_button_min_width(self.cancel_button, 100)
        buttons.addWidget(self.open_settings_button)
        buttons.addWidget(self.use_saved_login_button)
        buttons.addStretch()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.open_settings_button.clicked.connect(lambda: open_uri(RA_SETTINGS_URL))
        self.use_saved_login_button.clicked.connect(self.use_saved_login)
        self.save_button.clicked.connect(self.save_config)
        self.cancel_button.clicked.connect(self.cancelled.emit)

        centered.addWidget(card, 1)
        centered.addStretch(1)
        outer.addLayout(centered)
        outer.addStretch(1)

    def get_stored_ra_credentials(self):
        config = getattr(self.main_window, "config_data", {}) or {}
        if not config:
            try:
                config = load_config()
            except Exception:
                config = {}
        return (
            str(config.get(CONFIG_RA_USERNAME, "") or "").strip(),
            str(config.get(CONFIG_RA_API_KEY, "") or "").strip(),
        )

    def update_use_saved_login_button_state(self):
        username, api_key = self.get_stored_ra_credentials()
        available = bool(username and api_key)
        self.use_saved_login_button.setEnabled(available)
        self.use_saved_login_button.setToolTip(
            "Fill in the RetroAchievements login saved in MiSTer Companion."
            if available
            else "No saved RetroAchievements login was found in MiSTer Companion."
        )

    def use_saved_login(self):
        username, api_key = self.get_stored_ra_credentials()
        if not username or not api_key:
            self.update_use_saved_login_button_state()
            QMessageBox.information(
                self,
                "No Saved Login",
                "No saved RetroAchievements login was found in MiSTer Companion.",
            )
            return
        self.username_edit.setText(username)
        self.api_key_edit.setText(api_key)

    def load_remote_config(self):
        self.update_use_saved_login_button_state()
        try:
            config = load_mister_monitor_ra_config(self.connection)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "MiSTer Monitor RetroAchievements",
                f"Failed to load the MiSTer Monitor configuration:\n\n{exc}",
            )
            return False
        self.username_edit.setText(config.get("username", ""))
        self.api_key_edit.setText(config.get("api_key", ""))
        return True

    def save_config(self):
        username = self.username_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        if not username:
            QMessageBox.warning(self, "Missing Username", "Please enter your RetroAchievements username.")
            return
        if not api_key:
            QMessageBox.warning(self, "Missing API Key", "Please enter your RetroAchievements Web API key.")
            return

        self.save_button.setEnabled(False)
        self.save_button.setText("Saving…")
        try:
            save_mister_monitor_ra_config(self.connection, username, api_key)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "MiSTer Monitor RetroAchievements",
                f"Failed to save the MiSTer Monitor configuration:\n\n{exc}",
            )
            self.save_button.setEnabled(True)
            self.save_button.setText("Save")
            return

        self.save_button.setEnabled(True)
        self.save_button.setText("Save")
        QMessageBox.information(
            self,
            "Saved",
            "MiSTer Monitor RetroAchievements settings were saved successfully.\n\n"
            "The MiSTer Monitor server has been restarted.",
        )
        self.saved.emit()

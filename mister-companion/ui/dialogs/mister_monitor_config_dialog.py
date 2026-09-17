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

from core.config import load_config, save_config
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
    screenscraper_saved = pyqtSignal(str, str)
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

        cards = QWidget()
        cards.setMaximumWidth(720)
        cards_layout = QVBoxLayout(cards)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(12)

        card = QGroupBox("RetroAchievements Settings")
        card.setMaximumHeight(320)
        card_style = (
            "QGroupBox { background-color: palette(alternate-base); "
            "border: 1px solid palette(button); border-radius: 12px; "
            "margin-top: 18px; padding: 14px; font-weight: 700; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 14px; "
            "padding: 0px 7px; color: palette(highlight); }"
        )
        card.setStyleSheet(card_style)
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

        screenscraper_card = QGroupBox("ScreenScraper Settings")
        screenscraper_card.setStyleSheet(card_style)
        ss_layout = QVBoxLayout(screenscraper_card)
        ss_layout.setContentsMargins(18, 24, 18, 18)
        ss_layout.setSpacing(12)
        ss_info = QLabel(
            "Remote Display uses these credentials for its own artwork and metadata cache. "
            "ZapScraper output and scraped items are not reused."
        )
        ss_info.setWordWrap(True)
        ss_info.setStyleSheet("font-weight: normal;")
        ss_layout.addWidget(ss_info)
        ss_form = QFormLayout()
        ss_form.setSpacing(10)
        self.ss_username_edit = QLineEdit()
        self.ss_username_edit.setPlaceholderText("ScreenScraper username")
        self.ss_password_edit = QLineEdit()
        self.ss_password_edit.setPlaceholderText("ScreenScraper password")
        self.ss_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        ss_form.addRow("Username:", self.ss_username_edit)
        ss_form.addRow("Password:", self.ss_password_edit)
        ss_layout.addLayout(ss_form)
        ss_buttons = QHBoxLayout()
        self.use_zapscraper_login_button = QPushButton("Use ZapScraper Login")
        self.save_screenscraper_button = QPushButton("Save")
        set_text_button_min_width(self.use_zapscraper_login_button, 170)
        set_text_button_min_width(self.save_screenscraper_button, 100)
        ss_buttons.addWidget(self.use_zapscraper_login_button)
        ss_buttons.addStretch()
        ss_buttons.addWidget(self.save_screenscraper_button)
        ss_layout.addLayout(ss_buttons)
        self.use_zapscraper_login_button.clicked.connect(self.use_zapscraper_login)
        self.save_screenscraper_button.clicked.connect(self.save_screenscraper_config)

        cards_layout.addWidget(card)
        cards_layout.addWidget(screenscraper_card)
        centered.addWidget(cards, 1)
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
        ss_username, ss_password = self.get_zapscraper_credentials()
        self.ss_username_edit.setText(ss_username)
        self.ss_password_edit.setText(ss_password)
        self.update_use_zapscraper_login_button_state()
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

    def get_zapscraper_credentials(self):
        config = getattr(self.main_window, "config_data", {}) or {}
        if not config:
            try:
                config = load_config()
            except Exception:
                config = {}
        scraper = config.get("zapscraper", {})
        if not isinstance(scraper, dict):
            scraper = {}
        return (
            str(scraper.get("username", "") or "").strip(),
            str(scraper.get("password", "") or ""),
        )

    def update_use_zapscraper_login_button_state(self):
        username, password = self.get_zapscraper_credentials()
        available = bool(username and password)
        self.use_zapscraper_login_button.setEnabled(available)
        self.use_zapscraper_login_button.setToolTip(
            "Fill in the ScreenScraper login saved by ZapScraper."
            if available
            else "No ScreenScraper login was found in ZapScraper."
        )

    def use_zapscraper_login(self):
        username, password = self.get_zapscraper_credentials()
        if not username or not password:
            self.update_use_zapscraper_login_button_state()
            QMessageBox.information(
                self,
                "No ZapScraper Login",
                "No ScreenScraper login was found in ZapScraper.",
            )
            return
        self.ss_username_edit.setText(username)
        self.ss_password_edit.setText(password)

    def save_screenscraper_config(self):
        username = self.ss_username_edit.text().strip()
        password = self.ss_password_edit.text()
        if not username:
            QMessageBox.warning(self, "Missing Username", "Please enter your ScreenScraper username.")
            return
        if not password:
            QMessageBox.warning(self, "Missing Password", "Please enter your ScreenScraper password.")
            return
        config = getattr(self.main_window, "config_data", None)
        if not isinstance(config, dict):
            config = load_config()
        scraper = config.get("zapscraper", {})
        if not isinstance(scraper, dict):
            scraper = {}
        scraper["username"] = username
        scraper["password"] = password
        scraper["logged_in"] = False
        config["zapscraper"] = scraper
        save_config(config)
        if self.main_window is not None and hasattr(self.main_window, "config_data"):
            self.main_window.config_data["zapscraper"] = dict(scraper)
        QMessageBox.information(self, "Saved", "ScreenScraper settings were saved successfully.")
        self.screenscraper_saved.emit(username, password)

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

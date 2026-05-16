from core.open_helpers import open_uri

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ui.scaling import set_text_button_min_width
from core.config import load_config
from core.scripts_actions import (
    load_ra_viewer_config,
    load_ra_viewer_config_local,
    save_ra_viewer_config,
    save_ra_viewer_config_local,
)


RA_SETTINGS_URL = "https://retroachievements.org/settings"

CONFIG_RA_USERNAME = "retroachievements_username"
CONFIG_RA_API_KEY = "retroachievements_api_key"


class RAViewerConfigDialog(QDialog):
    def __init__(self, connection=None, parent=None, sd_root=None):
        super().__init__(parent)
        self.connection = connection
        self.sd_root = sd_root
        self.offline_mode = bool(sd_root)
        self.main_window = parent

        self.setWindowTitle("RA Viewer Configuration")
        self.setMinimumWidth(500)

        self.build_ui()
        self.load_config()
        self.update_use_saved_login_button_state()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        if self.offline_mode:
            info_text = (
                "Enter your RetroAchievements username and Web API key.\n\n"
                "Offline Mode: this configuration will be saved directly to the selected SD card.\n\n"
                "You can find your Web API key on the RetroAchievements website. "
                "Click 'Open in Browser' below to open your account settings page."
            )
        else:
            info_text = (
                "Enter your RetroAchievements username and Web API key.\n\n"
                "You can find your Web API key on the RetroAchievements website. "
                "Click 'Open in Browser' below to open your account settings page."
            )

        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("RetroAchievements username")

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("RetroAchievements Web API key")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

        form_layout.addRow("Username:", self.username_edit)
        form_layout.addRow("API Key:", self.api_key_edit)

        main_layout.addLayout(form_layout)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        self.open_settings_button = QPushButton("Open in Browser")
        set_text_button_min_width(self.open_settings_button, 150)
        self.use_saved_login_button = QPushButton("Use Saved Login")
        set_text_button_min_width(self.use_saved_login_button, 140)
        button_row.addWidget(self.open_settings_button)
        button_row.addWidget(self.use_saved_login_button)
        button_row.addStretch()

        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")

        set_text_button_min_width(self.save_button, 100)
        set_text_button_min_width(self.cancel_button, 100)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.cancel_button)

        main_layout.addLayout(button_row)

        self.open_settings_button.clicked.connect(self.open_ra_settings)
        self.use_saved_login_button.clicked.connect(self.use_saved_login)
        self.save_button.clicked.connect(self.save_config)
        self.cancel_button.clicked.connect(self.reject)

    def open_ra_settings(self):
        open_uri(RA_SETTINGS_URL)

    def get_stored_ra_credentials(self):
        config_data = {}

        if self.main_window is not None:
            config_data = getattr(self.main_window, "config_data", {}) or {}

        if not config_data:
            try:
                config_data = load_config()
            except Exception:
                config_data = {}

        username = str(config_data.get(CONFIG_RA_USERNAME, "") or "").strip()
        api_key = str(config_data.get(CONFIG_RA_API_KEY, "") or "").strip()

        return username, api_key

    def has_stored_ra_credentials(self):
        username, api_key = self.get_stored_ra_credentials()
        return bool(username and api_key)

    def update_use_saved_login_button_state(self):
        if not hasattr(self, "use_saved_login_button"):
            return

        has_credentials = self.has_stored_ra_credentials()
        self.use_saved_login_button.setEnabled(has_credentials)

        if has_credentials:
            self.use_saved_login_button.setToolTip(
                "Fill in the RetroAchievements login saved in MiSTer Companion."
            )
        else:
            self.use_saved_login_button.setToolTip(
                "No saved RetroAchievements login was found in MiSTer Companion."
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

    def load_config(self):
        try:
            if self.offline_mode:
                config = load_ra_viewer_config_local(self.sd_root)
            else:
                config = load_ra_viewer_config(self.connection)
        except Exception as e:
            QMessageBox.critical(
                self,
                "RA Viewer Configuration",
                f"Failed to load RA Viewer configuration:\n\n{e}",
            )
            self.reject()
            return

        self.username_edit.setText(config.get("username", ""))
        self.api_key_edit.setText(config.get("api_key", ""))

        self.update_use_saved_login_button_state()

    def save_config(self):
        username = self.username_edit.text().strip()
        api_key = self.api_key_edit.text().strip()

        if not username:
            QMessageBox.warning(
                self,
                "Missing Username",
                "Please enter your RetroAchievements username.",
            )
            return

        if not api_key:
            QMessageBox.warning(
                self,
                "Missing API Key",
                "Please enter your RetroAchievements Web API key.",
            )
            return

        try:
            if self.offline_mode:
                save_ra_viewer_config_local(
                    self.sd_root,
                    username=username,
                    api_key=api_key,
                )
            else:
                save_ra_viewer_config(
                    self.connection,
                    username=username,
                    api_key=api_key,
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "RA Viewer Configuration",
                f"Failed to save RA Viewer configuration:\n\n{e}",
            )
            return

        QMessageBox.information(
            self,
            "Saved",
            "RA Viewer configuration saved successfully.",
        )
        self.accept()
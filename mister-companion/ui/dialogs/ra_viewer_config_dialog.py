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

from core.scripts_actions import (
    load_ra_viewer_config,
    save_ra_viewer_config,
)


class RAViewerConfigDialog(QDialog):
    def __init__(self, connection, parent=None):
        super().__init__(parent)
        self.connection = connection

        self.setWindowTitle("RA Viewer Configuration")
        self.setMinimumWidth(460)

        self.build_ui()
        self.load_config()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        info_label = QLabel(
            "Enter your RetroAchievements username and Web API key.\n\n"
            "You can find your Web API key on the RetroAchievements website "
            "under your account settings."
        )
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
        button_row.addStretch()

        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")

        self.save_button.setFixedWidth(100)
        self.cancel_button.setFixedWidth(100)

        button_row.addWidget(self.save_button)
        button_row.addWidget(self.cancel_button)

        main_layout.addLayout(button_row)

        self.save_button.clicked.connect(self.save_config)
        self.cancel_button.clicked.connect(self.reject)

    def load_config(self):
        try:
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
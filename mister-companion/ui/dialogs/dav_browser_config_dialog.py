from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.scripts_actions import load_dav_browser_config, save_dav_browser_config


class DavBrowserConfigDialog(QDialog):
    def __init__(self, connection, parent=None):
        super().__init__(parent)
        self.connection = connection

        self.setWindowTitle("Configure DAV Browser")
        self.setModal(True)
        self.resize(460, 260)

        self.build_ui()
        self.load_existing_config()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        info_label = QLabel(
            "Configure the WebDAV connection used by DAV Browser.\n"
            "Leave Remote Path empty to browse from the server root."
        )
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)

        self.server_url_edit = QLineEdit()
        self.server_url_edit.setPlaceholderText("https://example.com/webdav")

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Username")

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Password")

        self.remote_path_edit = QLineEdit()
        self.remote_path_edit.setPlaceholderText("Optional, e.g. /roms")

        self.skip_tls_verify_checkbox = QCheckBox("Skip TLS certificate verification")

        form_layout.addRow("Server URL:", self.server_url_edit)
        form_layout.addRow("Username:", self.username_edit)
        form_layout.addRow("Password:", self.password_edit)
        form_layout.addRow("Remote Path:", self.remote_path_edit)
        form_layout.addRow("", self.skip_tls_verify_checkbox)

        main_layout.addLayout(form_layout)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()

        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")

        buttons_row.addWidget(self.save_button)
        buttons_row.addWidget(self.cancel_button)

        main_layout.addLayout(buttons_row)

        self.save_button.clicked.connect(self.save_config)
        self.cancel_button.clicked.connect(self.reject)

    def load_existing_config(self):
        try:
            config = load_dav_browser_config(self.connection)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Could not load DAV Browser configuration.\n\n{e}",
            )
            return

        self.server_url_edit.setText(config.get("SERVER_URL", ""))
        self.username_edit.setText(config.get("USERNAME", ""))
        self.password_edit.setText(config.get("PASSWORD", ""))
        self.remote_path_edit.setText(config.get("REMOTE_PATH", ""))

        skip_tls_verify = config.get("SKIP_TLS_VERIFY", "true").strip().lower() == "true"
        self.skip_tls_verify_checkbox.setChecked(skip_tls_verify)

    def save_config(self):
        server_url = self.server_url_edit.text().strip()
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        remote_path = self.remote_path_edit.text().strip()
        skip_tls_verify = self.skip_tls_verify_checkbox.isChecked()

        if not server_url:
            QMessageBox.warning(self, "Missing Server URL", "Please enter a Server URL.")
            return

        if not username:
            QMessageBox.warning(self, "Missing Username", "Please enter a Username.")
            return

        if not password:
            QMessageBox.warning(self, "Missing Password", "Please enter a Password.")
            return

        try:
            save_dav_browser_config(
                self.connection,
                server_url=server_url,
                username=username,
                password=password,
                remote_path=remote_path,
                skip_tls_verify=skip_tls_verify,
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Could not save DAV Browser configuration.\n\n{e}",
            )
            return

        QMessageBox.information(self, "Saved", "DAV Browser configuration saved.")
        self.accept()
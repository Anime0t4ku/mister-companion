from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.language import tr
from core.scripts_actions import load_dav_browser_config, save_dav_browser_config


class DavBrowserConfigDialog(QDialog):
    def __init__(self, connection, parent=None):
        super().__init__(parent)
        self.connection = connection

        self.setWindowTitle(tr("dav_browser_config_dialog.window_title"))
        self.setModal(True)
        self.resize(460, 260)

        self.build_ui()
        self.load_existing_config()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        info_label = QLabel(tr("dav_browser_config_dialog.info"))
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)

        self.server_url_edit = QLineEdit()
        self.server_url_edit.setPlaceholderText(
            tr("dav_browser_config_dialog.server_url_placeholder")
        )

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText(tr("device_dialog.username"))

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText(tr("device_dialog.password"))

        self.remote_path_edit = QLineEdit()
        self.remote_path_edit.setPlaceholderText(
            tr("dav_browser_config_dialog.remote_path_placeholder")
        )

        self.skip_tls_verify_checkbox = QCheckBox(
            tr("dav_browser_config_dialog.skip_tls_verify")
        )

        form_layout.addRow(tr("dav_browser_config_dialog.server_url"), self.server_url_edit)
        form_layout.addRow(tr("device_dialog.username") + ":", self.username_edit)
        form_layout.addRow(tr("device_dialog.password") + ":", self.password_edit)
        form_layout.addRow(tr("dav_browser_config_dialog.remote_path"), self.remote_path_edit)
        form_layout.addRow("", self.skip_tls_verify_checkbox)

        main_layout.addLayout(form_layout)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()

        self.save_button = QPushButton(tr("dav_browser_config_dialog.save"))
        self.cancel_button = QPushButton(tr("common.cancel"))

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
                tr("common.error"),
                tr("dav_browser_config_dialog.load_failed", error=e),
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
            QMessageBox.warning(
                self,
                tr("dav_browser_config_dialog.missing_server_url_title"),
                tr("dav_browser_config_dialog.missing_server_url_message"),
            )
            return

        if not username:
            QMessageBox.warning(
                self,
                tr("dav_browser_config_dialog.missing_username_title"),
                tr("dav_browser_config_dialog.missing_username_message"),
            )
            return

        if not password:
            QMessageBox.warning(
                self,
                tr("dav_browser_config_dialog.missing_password_title"),
                tr("dav_browser_config_dialog.missing_password_message"),
            )
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
                tr("common.error"),
                tr("dav_browser_config_dialog.save_failed", error=e),
            )
            return

        QMessageBox.information(
            self,
            tr("dav_browser_config_dialog.saved_title"),
            tr("dav_browser_config_dialog.saved_message"),
        )
        self.accept()
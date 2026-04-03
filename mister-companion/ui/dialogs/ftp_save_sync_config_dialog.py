from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
    load_ftp_save_sync_config,
    save_ftp_save_sync_config,
)


class FtpSaveSyncConfigDialog(QDialog):
    def __init__(self, connection, main_window, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.main_window = main_window

        self.setWindowTitle("Configure ftp_save_sync")
        self.setModal(True)
        self.resize(500, 340)

        self.build_ui()
        self.load_existing_config()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        info_label = QLabel(
            "Configure the remote sync connection used by ftp_save_sync.\n"
            "Remote Base is the working directory on the remote server."
        )
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItem("FTP", "ftp")
        self.protocol_combo.addItem("SFTP (recommended)", "sftp")

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("example.com or 192.168.1.10")

        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("21 or 22")

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Username")

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Password")

        self.remote_base_edit = QLineEdit()
        self.remote_base_edit.setPlaceholderText("/")
        self.remote_base_edit.setText("/")

        self.device_name_edit = QLineEdit()
        self.device_name_edit.setPlaceholderText("Device name")

        self.sync_savestates_checkbox = QCheckBox("Sync savestates")
        self.sync_savestates_warning_label = QLabel(
            "Warning: syncing savestates may cause issues depending on the core or game."
        )
        self.sync_savestates_warning_label.setWordWrap(True)
        self.sync_savestates_warning_label.setStyleSheet("color: #cc8400;")

        form_layout.addRow("Protocol:", self.protocol_combo)
        form_layout.addRow("Host:", self.host_edit)
        form_layout.addRow("Port:", self.port_edit)
        form_layout.addRow("Username:", self.username_edit)
        form_layout.addRow("Password:", self.password_edit)
        form_layout.addRow("Remote Base:", self.remote_base_edit)
        form_layout.addRow("Device Name:", self.device_name_edit)
        form_layout.addRow("", self.sync_savestates_checkbox)
        form_layout.addRow("", self.sync_savestates_warning_label)

        main_layout.addLayout(form_layout)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()

        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")

        buttons_row.addWidget(self.save_button)
        buttons_row.addWidget(self.cancel_button)

        main_layout.addLayout(buttons_row)

        self.protocol_combo.currentIndexChanged.connect(self.on_protocol_changed)
        self.save_button.clicked.connect(self.save_config)
        self.cancel_button.clicked.connect(self.reject)

    def get_selected_profile_name(self):
        try:
            connection_tab = getattr(self.main_window, "connection_tab", None)
            if connection_tab and hasattr(connection_tab, "get_selected_profile_name"):
                return connection_tab.get_selected_profile_name().strip()
        except Exception:
            pass
        return ""

    def load_existing_config(self):
        try:
            config = load_ftp_save_sync_config(self.connection)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Could not load ftp_save_sync configuration.\n\n{e}",
            )
            return

        if config:
            protocol = config.get("PROTOCOL", "sftp").strip().lower()
            protocol_index = 1 if protocol == "sftp" else 0
            self.protocol_combo.setCurrentIndex(protocol_index)

            self.host_edit.setText(config.get("HOST", ""))
            self.port_edit.setText(config.get("PORT", ""))
            self.username_edit.setText(config.get("USERNAME", ""))
            self.password_edit.setText(config.get("PASSWORD", ""))
            self.remote_base_edit.setText(config.get("REMOTE_BASE", "/") or "/")
            self.device_name_edit.setText(config.get("DEVICE_NAME", ""))

            sync_savestates = config.get("SYNC_SAVESTATES", "false").strip().lower() == "true"
            self.sync_savestates_checkbox.setChecked(sync_savestates)
        else:
            self.protocol_combo.setCurrentIndex(1)  # default to SFTP
            self.on_protocol_changed()

            profile_name = self.get_selected_profile_name()
            if profile_name:
                self.device_name_edit.setText(profile_name)

    def on_protocol_changed(self):
        current_protocol = self.protocol_combo.currentData()

        if current_protocol == "sftp":
            if not self.port_edit.text().strip():
                self.port_edit.setText("22")
        else:
            if not self.port_edit.text().strip():
                self.port_edit.setText("21")

    def save_config(self):
        protocol = self.protocol_combo.currentData()
        host = self.host_edit.text().strip()
        port = self.port_edit.text().strip()
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        remote_base = self.remote_base_edit.text().strip() or "/"
        device_name = self.device_name_edit.text().strip()
        sync_savestates = self.sync_savestates_checkbox.isChecked()

        if not host:
            QMessageBox.warning(self, "Missing Host", "Please enter a Host.")
            return

        if not port:
            QMessageBox.warning(self, "Missing Port", "Please enter a Port.")
            return

        if not port.isdigit():
            QMessageBox.warning(self, "Invalid Port", "Port must be a number.")
            return

        if not username:
            QMessageBox.warning(self, "Missing Username", "Please enter a Username.")
            return

        if not password:
            QMessageBox.warning(self, "Missing Password", "Please enter a Password.")
            return

        if not device_name:
            QMessageBox.warning(self, "Missing Device Name", "Please enter a Device Name.")
            return

        if not remote_base.startswith("/"):
            remote_base = f"/{remote_base}"

        try:
            save_ftp_save_sync_config(
                self.connection,
                protocol=protocol,
                host=host,
                port=port,
                username=username,
                password=password,
                remote_base=remote_base,
                device_name=device_name,
                sync_savestates=sync_savestates,
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Could not save ftp_save_sync configuration.\n\n{e}",
            )
            return

        QMessageBox.information(self, "Saved", "ftp_save_sync configuration saved.")
        self.accept()
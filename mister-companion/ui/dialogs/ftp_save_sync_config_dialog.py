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

from core.language import tr
from core.scripts_actions import (
    load_ftp_save_sync_config,
    save_ftp_save_sync_config,
)


class FtpSaveSyncConfigDialog(QDialog):
    def __init__(self, connection, main_window, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.main_window = main_window

        self.setWindowTitle(tr("ftp_save_sync_config_dialog.window_title"))
        self.setModal(True)
        self.resize(500, 340)

        self.build_ui()
        self.load_existing_config()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        info_label = QLabel(tr("ftp_save_sync_config_dialog.info"))
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItem(tr("ftp_save_sync_config_dialog.protocol_ftp"), "ftp")
        self.protocol_combo.addItem(tr("ftp_save_sync_config_dialog.protocol_sftp"), "sftp")

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText(tr("ftp_save_sync_config_dialog.host_placeholder"))

        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText(tr("ftp_save_sync_config_dialog.port_placeholder"))

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText(tr("device_dialog.username"))

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText(tr("device_dialog.password"))

        self.remote_base_edit = QLineEdit()
        self.remote_base_edit.setPlaceholderText("/")
        self.remote_base_edit.setText("/")

        self.device_name_edit = QLineEdit()
        self.device_name_edit.setPlaceholderText(tr("ftp_save_sync_config_dialog.device_name_placeholder"))

        self.sync_savestates_checkbox = QCheckBox(tr("ftp_save_sync_config_dialog.sync_savestates"))
        self.sync_savestates_warning_label = QLabel(
            tr("ftp_save_sync_config_dialog.sync_savestates_warning")
        )
        self.sync_savestates_warning_label.setWordWrap(True)
        self.sync_savestates_warning_label.setStyleSheet("color: #cc8400;")

        form_layout.addRow(tr("ftp_save_sync_config_dialog.protocol"), self.protocol_combo)
        form_layout.addRow(tr("ftp_save_sync_config_dialog.host"), self.host_edit)
        form_layout.addRow(tr("ftp_save_sync_config_dialog.port"), self.port_edit)
        form_layout.addRow(tr("device_dialog.username") + ":", self.username_edit)
        form_layout.addRow(tr("device_dialog.password") + ":", self.password_edit)
        form_layout.addRow(tr("ftp_save_sync_config_dialog.remote_base"), self.remote_base_edit)
        form_layout.addRow(tr("ftp_save_sync_config_dialog.device_name"), self.device_name_edit)
        form_layout.addRow("", self.sync_savestates_checkbox)
        form_layout.addRow("", self.sync_savestates_warning_label)

        main_layout.addLayout(form_layout)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()

        self.save_button = QPushButton(tr("ftp_save_sync_config_dialog.save"))
        self.cancel_button = QPushButton(tr("common.cancel"))

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
                tr("common.error"),
                tr("ftp_save_sync_config_dialog.load_failed", error=e),
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
            self.protocol_combo.setCurrentIndex(1)
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
            QMessageBox.warning(
                self,
                tr("ftp_save_sync_config_dialog.missing_host_title"),
                tr("ftp_save_sync_config_dialog.missing_host_message"),
            )
            return

        if not port:
            QMessageBox.warning(
                self,
                tr("ftp_save_sync_config_dialog.missing_port_title"),
                tr("ftp_save_sync_config_dialog.missing_port_message"),
            )
            return

        if not port.isdigit():
            QMessageBox.warning(
                self,
                tr("ftp_save_sync_config_dialog.invalid_port_title"),
                tr("ftp_save_sync_config_dialog.invalid_port_message"),
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

        if not device_name:
            QMessageBox.warning(
                self,
                tr("ftp_save_sync_config_dialog.missing_device_name_title"),
                tr("ftp_save_sync_config_dialog.missing_device_name_message"),
            )
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
                tr("common.error"),
                tr("ftp_save_sync_config_dialog.save_failed", error=e),
            )
            return

        QMessageBox.information(
            self,
            tr("ftp_save_sync_config_dialog.saved_title"),
            tr("ftp_save_sync_config_dialog.saved_message"),
        )
        self.accept()
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
from core.scripts_actions import load_cifs_config, save_cifs_config, test_cifs_connection


class CifsConfigDialog(QDialog):
    def __init__(self, connection, parent=None):
        super().__init__(parent)
        self.connection = connection

        self.setWindowTitle(tr("cifs_config_dialog.window_title"))
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)

        info = QLabel(tr("cifs_config_dialog.info"))
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.server_input = QLineEdit()
        self.share_input = QLineEdit()
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.mount_at_boot_check = QCheckBox(tr("cifs_config_dialog.mount_at_boot"))

        self.mount_at_boot_check.setChecked(True)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow(tr("cifs_config_dialog.server_ip"), self.server_input)
        form.addRow(tr("cifs_config_dialog.share_name"), self.share_input)
        form.addRow(tr("device_dialog.username"), self.username_input)
        form.addRow(tr("device_dialog.password"), self.password_input)
        form.addRow("", self.mount_at_boot_check)

        layout.addLayout(form)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.test_button = QPushButton(tr("cifs_config_dialog.test_connection"))
        self.save_button = QPushButton(tr("cifs_config_dialog.save"))
        self.cancel_button = QPushButton(tr("common.cancel"))

        button_row.addWidget(self.test_button)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        self.test_button.clicked.connect(self.on_test_connection)
        self.save_button.clicked.connect(self.on_save)
        self.cancel_button.clicked.connect(self.reject)

        self.load_existing_config()

    def load_existing_config(self):
        config = load_cifs_config(self.connection)

        self.server_input.setText(config.get("SERVER", ""))
        self.share_input.setText(config.get("SHARE", ""))
        self.username_input.setText(config.get("USERNAME", ""))
        self.password_input.setText(config.get("PASSWORD", ""))

        if config.get("MOUNT_AT_BOOT", "true").lower() == "false":
            self.mount_at_boot_check.setChecked(False)

    def on_test_connection(self):
        server = self.server_input.text().strip()
        share = self.share_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not server or not share:
            QMessageBox.critical(
                self,
                tr("cifs_config_dialog.missing_information_title"),
                tr("cifs_config_dialog.server_and_share_required"),
            )
            return

        ok = test_cifs_connection(
            self.connection,
            server,
            share,
            username,
            password,
        )

        if ok:
            QMessageBox.information(
                self,
                tr("cifs_config_dialog.success_title"),
                tr("cifs_config_dialog.connection_successful"),
            )
        else:
            QMessageBox.critical(
                self,
                tr("messages.connection_failed_title"),
                tr("cifs_config_dialog.connection_failed"),
            )

    def on_save(self):
        server = self.server_input.text().strip()
        share = self.share_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        mount_at_boot = self.mount_at_boot_check.isChecked()

        if not server:
            QMessageBox.critical(
                self,
                tr("cifs_config_dialog.missing_information_title"),
                tr("cifs_config_dialog.server_ip_required"),
            )
            return

        if not share:
            QMessageBox.critical(
                self,
                tr("cifs_config_dialog.missing_information_title"),
                tr("cifs_config_dialog.share_name_required"),
            )
            return

        try:
            save_cifs_config(
                self.connection,
                server=server,
                share=share,
                username=username,
                password=password,
                mount_at_boot=mount_at_boot,
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, tr("common.error"), str(e))
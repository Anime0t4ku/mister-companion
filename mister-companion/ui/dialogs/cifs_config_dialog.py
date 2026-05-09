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

from core.scripts_actions import (
    load_cifs_config,
    load_cifs_config_local,
    save_cifs_config,
    save_cifs_config_local,
    test_cifs_connection,
)


class CifsConfigDialog(QDialog):
    def __init__(self, connection=None, parent=None, sd_root=None):
        super().__init__(parent)
        self.connection = connection
        self.sd_root = sd_root
        self.offline_mode = bool(sd_root)

        self.setWindowTitle("Configure CIFS Network Share")
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)

        if self.offline_mode:
            info_text = (
                "Configure your network share for cifs_mount.\n"
                "Offline Mode: this configuration will be saved directly to the selected SD card.\n\n"
                "Test Connection is only available in Online / SSH Mode because it must run from the MiSTer."
            )
        else:
            info_text = (
                "Configure your network share for cifs_mount.\n"
                "Only Server IP and Share Name are required."
            )

        info = QLabel(info_text)
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.server_input = QLineEdit()
        self.share_input = QLineEdit()
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.mount_at_boot_check = QCheckBox("Mount at boot")

        self.mount_at_boot_check.setChecked(True)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("Server IP", self.server_input)
        form.addRow("Share Name", self.share_input)
        form.addRow("Username", self.username_input)
        form.addRow("Password", self.password_input)
        form.addRow("", self.mount_at_boot_check)

        layout.addLayout(form)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.test_button = QPushButton("Test Connection")
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")

        button_row.addWidget(self.test_button)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        self.test_button.clicked.connect(self.on_test_connection)
        self.save_button.clicked.connect(self.on_save)
        self.cancel_button.clicked.connect(self.reject)

        if self.offline_mode:
            self.test_button.setEnabled(False)
            self.test_button.setToolTip(
                "Testing the CIFS connection requires Online / SSH Mode."
            )

        self.load_existing_config()

    def load_existing_config(self):
        try:
            if self.offline_mode:
                config = load_cifs_config_local(self.sd_root)
            else:
                config = load_cifs_config(self.connection)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load CIFS config:\n{e}")
            return

        self.server_input.setText(config.get("SERVER", ""))
        self.share_input.setText(config.get("SHARE", ""))
        self.username_input.setText(config.get("USERNAME", ""))
        self.password_input.setText(config.get("PASSWORD", ""))

        if config.get("MOUNT_AT_BOOT", "true").lower() == "false":
            self.mount_at_boot_check.setChecked(False)
        else:
            self.mount_at_boot_check.setChecked(True)

    def on_test_connection(self):
        if self.offline_mode:
            QMessageBox.information(
                self,
                "Test Connection",
                "Testing the CIFS connection requires Online / SSH Mode because the test must run from the MiSTer.",
            )
            return

        server = self.server_input.text().strip()
        share = self.share_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not server or not share:
            QMessageBox.critical(
                self,
                "Missing Information",
                "Server IP and Share Name are required.",
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
            QMessageBox.information(self, "Success", "Connection successful.")
        else:
            QMessageBox.critical(
                self,
                "Connection Failed",
                "Unable to connect to the network share.",
            )

    def on_save(self):
        server = self.server_input.text().strip()
        share = self.share_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        mount_at_boot = self.mount_at_boot_check.isChecked()

        if not server:
            QMessageBox.critical(self, "Missing Information", "Server IP is required.")
            return

        if not share:
            QMessageBox.critical(self, "Missing Information", "Share name is required.")
            return

        try:
            if self.offline_mode:
                save_cifs_config_local(
                    self.sd_root,
                    server=server,
                    share=share,
                    username=username,
                    password=password,
                    mount_at_boot=mount_at_boot,
                )
            else:
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
            QMessageBox.critical(self, "Error", str(e))
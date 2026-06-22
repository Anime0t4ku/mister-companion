from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QWidget,
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
        self.advanced_check = QCheckBox("Advanced options")

        self.mount_at_boot_check.setChecked(True)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("Server IP", self.server_input)
        form.addRow("Share Name", self.share_input)
        form.addRow("Username", self.username_input)
        form.addRow("Password", self.password_input)
        form.addRow("", self.mount_at_boot_check)
        form.addRow("", self.advanced_check)

        layout.addLayout(form)

        self.advanced_widget = QWidget()
        advanced_layout = QFormLayout(self.advanced_widget)
        advanced_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.share_directory_input = QLineEdit()
        self.domain_input = QLineEdit()
        self.local_dir_input = QLineEdit()
        self.additional_mount_options_input = QLineEdit()

        self.local_dir_input.setText("cifs/games")
        self.local_dir_input.setPlaceholderText("cifs/games")
        self.additional_mount_options_input.setPlaceholderText("Example: vers=3.0")

        advanced_layout.addRow("Share Directory", self.share_directory_input)
        advanced_layout.addRow("Domain", self.domain_input)
        advanced_layout.addRow("Local Mount Folder", self.local_dir_input)
        advanced_layout.addRow("Additional Mount Options", self.additional_mount_options_input)

        advanced_help = QLabel(
            "Local Mount Folder is relative to /media/fat. "
            "Default: cifs/games. Example: cifs, cifs/games, cifs/docs. "
            "Leave additional mount options empty unless your NAS requires them."
        )
        advanced_help.setWordWrap(True)
        advanced_layout.addRow("", advanced_help)

        layout.addWidget(self.advanced_widget)
        self.advanced_widget.setVisible(False)

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
        self.advanced_check.toggled.connect(self.advanced_widget.setVisible)

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
        self.share_directory_input.setText(config.get("SHARE_DIRECTORY", ""))
        self.domain_input.setText(config.get("DOMAIN", ""))
        self.local_dir_input.setText(config.get("LOCAL_DIR", "cifs/games") or "cifs/games")
        self.additional_mount_options_input.setText(config.get("ADDITIONAL_MOUNT_OPTIONS", ""))

        use_advanced = self._config_uses_advanced_values(config)
        self.advanced_check.setChecked(use_advanced)
        self.advanced_widget.setVisible(use_advanced)

        if config.get("MOUNT_AT_BOOT", "true").lower() == "false":
            self.mount_at_boot_check.setChecked(False)
        else:
            self.mount_at_boot_check.setChecked(True)


    def _config_uses_advanced_values(self, config):
        if not config:
            return False

        local_dir = config.get("LOCAL_DIR", "cifs/games") or "cifs/games"
        advanced_values = [
            config.get("SHARE_DIRECTORY", ""),
            config.get("DOMAIN", ""),
            config.get("ADDITIONAL_MOUNT_OPTIONS", ""),
        ]

        return local_dir != "cifs/games" or any(value for value in advanced_values)

    def _validated_local_dir(self):
        local_dir = self.local_dir_input.text().strip() or "cifs/games"
        local_dir = local_dir.replace("\\", "/").strip("/")

        blocked_names = {
            "linux",
            "config",
            "scripts",
            "system volume information",
        }

        parts = [part for part in local_dir.split("/") if part]
        if not parts:
            return "cifs/games"

        if any(part in {".", ".."} for part in parts):
            raise ValueError("Local Mount Folder cannot contain . or ...")

        if parts[0].lower() in blocked_names:
            raise ValueError("Local Mount Folder cannot point to a protected MiSTer folder.")

        return "/".join(parts)

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

        if self.advanced_check.isChecked():
            share_directory = self.share_directory_input.text().strip()
            domain = self.domain_input.text().strip()
            additional_mount_options = self.additional_mount_options_input.text().strip()
        else:
            share_directory = ""
            domain = ""
            additional_mount_options = ""

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
            share_directory=share_directory,
            domain=domain,
            additional_mount_options=additional_mount_options,
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

        if self.advanced_check.isChecked():
            share_directory = self.share_directory_input.text().strip()
            domain = self.domain_input.text().strip()
            additional_mount_options = self.additional_mount_options_input.text().strip()
            try:
                local_dir = self._validated_local_dir()
            except ValueError as e:
                QMessageBox.critical(self, "Invalid Local Mount Folder", str(e))
                return
        else:
            share_directory = ""
            domain = ""
            local_dir = "cifs/games"
            additional_mount_options = ""

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
                    share_directory=share_directory,
                    domain=domain,
                    local_dir=local_dir,
                    additional_mount_options=additional_mount_options,
                )
            else:
                save_cifs_config(
                    self.connection,
                    server=server,
                    share=share,
                    username=username,
                    password=password,
                    mount_at_boot=mount_at_boot,
                    share_directory=share_directory,
                    domain=domain,
                    local_dir=local_dir,
                    additional_mount_options=additional_mount_options,
                )

            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
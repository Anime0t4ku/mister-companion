from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QPushButton, QMessageBox, QComboBox, QTextEdit,
    QRadioButton, QButtonGroup, QSpinBox, QSizePolicy, QDialog
)

from core.mister_ini import (
    build_easy_mode_settings,
    easy_mode_values_from_ini_settings,
    parse_mister_ini,
    update_mister_ini_text,
)
from core.mister_settings_backup import (
    create_mister_settings_backup,
    ensure_mister_ini_exists,
    ensure_settings_root_exists,
    get_mister_settings_device_name,
    get_mister_settings_device_path,
    list_mister_settings_backups,
    open_mister_settings_folder,
    restore_default_mister_settings,
    restore_mister_settings_backup,
    save_mister_settings_retention_setting,
)
from ui.dialogs.restore_backup_dialog import RestoreBackupDialog


class MiSTerSettingsTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection
        self.config_data = main_window.config_data

        ensure_settings_root_exists()

        self.build_ui()
        self.apply_disconnected_state()

    def build_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 8, 12, 12)
        main_layout.setSpacing(8)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(main_layout)

        self.info_label = QLabel(
            "MiSTer Settings allows you to edit MiSTer.ini with an Easy and Advanced mode.\n"
            "Backups are stored locally on your PC in a separate MiSTerSettings folder.\n"
            "Settings are only applied when you press Save."
        )
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        main_layout.addWidget(self.info_label)

        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(10)
        mode_row.addStretch()

        mode_label = QLabel("Mode:")
        mode_row.addWidget(mode_label)

        self.easy_mode_radio = QRadioButton("Easy")
        self.advanced_mode_radio = QRadioButton("Advanced")
        self.easy_mode_radio.setChecked(True)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.easy_mode_radio)
        self.mode_group.addButton(self.advanced_mode_radio)

        mode_row.addWidget(self.easy_mode_radio)
        mode_row.addWidget(self.advanced_mode_radio)
        mode_row.addStretch()

        main_layout.addLayout(mode_row)

        self.notice_label = QLabel("")
        self.notice_label.setWordWrap(True)
        self.notice_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.notice_label.setStyleSheet("color: orange;")
        self.notice_label.hide()
        main_layout.addWidget(self.notice_label)

        self.easy_group = QGroupBox("Easy Mode")
        easy_layout = QGridLayout()
        easy_layout.setContentsMargins(12, 10, 12, 10)
        easy_layout.setHorizontalSpacing(10)
        easy_layout.setVerticalSpacing(8)

        self.easy_hdmi_mode_combo = QComboBox()
        self.easy_hdmi_mode_combo.addItems([
            "HD Output (Default)",
            "Direct Video (CRT / Scaler)"
        ])

        self.easy_resolution_combo = QComboBox()
        self.easy_resolution_combo.addItems([
            "1280x720@60",
            "1024x768@60",
            "720x480@60",
            "720x576@50",
            "1280x1024@60",
            "800x600@60",
            "640x480@60",
            "1280x720@50",
            "1920x1080@60",
            "1920x1080@50",
            "1366x768@60",
            "1024x600@60",
            "1920x1440@60",
            "2048x1536@60",
            "2560x1440@60"
        ])

        self.easy_scaling_combo = QComboBox()
        self.easy_scaling_combo.addItems([
            "Disabled",
            "Low Latency",
            "Exact Refresh"
        ])

        self.easy_hdmi_audio_combo = QComboBox()
        self.easy_hdmi_audio_combo.addItems([
            "Enabled",
            "Disabled (DVI Mode)"
        ])

        self.easy_hdr_combo = QComboBox()
        self.easy_hdr_combo.addItems([
            "Disabled",
            "Enabled"
        ])

        self.easy_hdmi_limited_combo = QComboBox()
        self.easy_hdmi_limited_combo.addItems([
            "Full Range",
            "Limited Range"
        ])

        self.easy_analogue_combo = QComboBox()
        self.easy_analogue_combo.addItems([
            "RGB (Consumer TV)",
            "RGB (PVM/BVM)",
            "Component (YPbPr)",
            "S-Video",
            "VGA Monitor"
        ])

        self.easy_logo_combo = QComboBox()
        self.easy_logo_combo.addItems([
            "Enabled",
            "Disabled"
        ])

        easy_layout.addWidget(QLabel("HDMI Mode"), 0, 0)
        easy_layout.addWidget(self.easy_hdmi_mode_combo, 0, 1)
        easy_layout.addWidget(QLabel("Resolution"), 1, 0)
        easy_layout.addWidget(self.easy_resolution_combo, 1, 1)
        easy_layout.addWidget(QLabel("HDMI Scaling Mode"), 2, 0)
        easy_layout.addWidget(self.easy_scaling_combo, 2, 1)
        easy_layout.addWidget(QLabel("HDMI Audio"), 3, 0)
        easy_layout.addWidget(self.easy_hdmi_audio_combo, 3, 1)
        easy_layout.addWidget(QLabel("HDR"), 4, 0)
        easy_layout.addWidget(self.easy_hdr_combo, 4, 1)
        easy_layout.addWidget(QLabel("HDMI Range"), 5, 0)
        easy_layout.addWidget(self.easy_hdmi_limited_combo, 5, 1)
        easy_layout.addWidget(QLabel("Analogue Output"), 6, 0)
        easy_layout.addWidget(self.easy_analogue_combo, 6, 1)
        easy_layout.addWidget(QLabel("MiSTer Logo"), 7, 0)
        easy_layout.addWidget(self.easy_logo_combo, 7, 1)

        self.easy_group.setLayout(easy_layout)
        main_layout.addWidget(self.easy_group)

        self.advanced_group = QGroupBox("Advanced Mode")
        advanced_layout = QVBoxLayout()
        advanced_layout.setContentsMargins(10, 10, 10, 10)

        self.advanced_text = QTextEdit()
        self.advanced_text.setAcceptRichText(False)
        self.advanced_text.setFontFamily("Consolas")
        self.advanced_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.advanced_text.setStyleSheet("")
        self.advanced_text.setMinimumHeight(0)
        self.advanced_text.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        advanced_layout.addWidget(self.advanced_text)
        self.advanced_group.setLayout(advanced_layout)
        main_layout.addWidget(self.advanced_group)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.save_button = QPushButton("Save")
        self.backup_button = QPushButton("Backup")
        self.restore_button = QPushButton("Restore Backup")
        self.defaults_button = QPushButton("Restore Defaults")

        button_row.addWidget(self.save_button)
        button_row.addWidget(self.backup_button)
        button_row.addWidget(self.restore_button)
        button_row.addWidget(self.defaults_button)

        button_row.addStretch()
        main_layout.addLayout(button_row)

        retention_row = QHBoxLayout()
        retention_row.addStretch()

        self.retention_label = QLabel("Backups to keep per device:")
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 100)
        self.retention_spin.setValue(self.config_data.get("mister_settings_retention", 10))

        self.open_backup_folder_button = QPushButton("Open Backup Folder")

        retention_row.addWidget(self.retention_label)
        retention_row.addWidget(self.retention_spin)
        retention_row.addWidget(self.open_backup_folder_button)
        retention_row.addStretch()

        main_layout.addLayout(retention_row)

        self.easy_hdmi_mode_combo.currentIndexChanged.connect(self.update_easy_mode_state)
        self.easy_mode_radio.toggled.connect(self.update_settings_mode)
        self.advanced_mode_radio.toggled.connect(self.update_settings_mode)

        self.save_button.clicked.connect(self.save_mister_settings)
        self.backup_button.clicked.connect(self.backup_mister_settings)
        self.restore_button.clicked.connect(self.restore_mister_settings)
        self.defaults_button.clicked.connect(self.restore_default_mister_settings)
        self.retention_spin.valueChanged.connect(self.save_mister_settings_retention_setting)
        self.open_backup_folder_button.clicked.connect(self.open_mister_settings_folder)

        self.easy_resolution_combo.setCurrentText("1920x1080@60")
        self.easy_scaling_combo.setCurrentText("Low Latency")
        self.easy_hdmi_audio_combo.setCurrentText("Enabled")
        self.easy_hdr_combo.setCurrentText("Disabled")
        self.easy_hdmi_limited_combo.setCurrentText("Full Range")
        self.easy_analogue_combo.setCurrentText("RGB (Consumer TV)")
        self.easy_logo_combo.setCurrentText("Enabled")

        self.update_easy_mode_state()
        self.update_settings_mode()

    def set_notice(self, text=""):
        text = (text or "").strip()
        self.notice_label.setText(text)
        self.notice_label.setVisible(bool(text))

    def apply_connected_state(self):
        self.easy_mode_radio.setEnabled(True)
        self.advanced_mode_radio.setEnabled(True)
        self.save_button.setEnabled(True)
        self.backup_button.setEnabled(True)
        self.restore_button.setEnabled(True)
        self.defaults_button.setEnabled(True)
        self.retention_spin.setEnabled(True)
        self.open_backup_folder_button.setEnabled(True)
        self.info_label.setStyleSheet("")
        self.retention_label.setStyleSheet("")
        self.set_mister_settings_enabled(True)

    def apply_disconnected_state(self):
        self.easy_mode_radio.setEnabled(False)
        self.advanced_mode_radio.setEnabled(False)
        self.save_button.setEnabled(False)
        self.backup_button.setEnabled(False)
        self.restore_button.setEnabled(False)
        self.defaults_button.setEnabled(False)
        self.retention_spin.setEnabled(False)
        self.open_backup_folder_button.setEnabled(False)
        self.info_label.setStyleSheet("")
        self.retention_label.setStyleSheet("")
        self.set_notice("")
        self.set_mister_settings_enabled(False)

    def update_connection_state(self):
        if self.connection.is_connected():
            self.apply_connected_state()
            self.load_mister_ini_into_ui(silent=True)
            self.load_mister_ini_advanced()
        else:
            self.apply_disconnected_state()

    def set_mister_settings_enabled(self, enabled):
        easy_enabled = enabled and self.easy_mode_radio.isChecked()
        advanced_enabled = enabled and self.advanced_mode_radio.isChecked()

        self.easy_hdmi_mode_combo.setEnabled(easy_enabled)
        self.easy_resolution_combo.setEnabled(easy_enabled)
        self.easy_scaling_combo.setEnabled(easy_enabled)
        self.easy_hdmi_audio_combo.setEnabled(easy_enabled)
        self.easy_hdr_combo.setEnabled(easy_enabled)
        self.easy_hdmi_limited_combo.setEnabled(easy_enabled)
        self.easy_analogue_combo.setEnabled(easy_enabled)
        self.easy_logo_combo.setEnabled(easy_enabled)

        self.advanced_text.setReadOnly(not advanced_enabled)

        if enabled:
            self.update_easy_mode_state()

    def update_settings_mode(self):
        connected = self.connection.is_connected()

        if self.easy_mode_radio.isChecked():
            if connected:
                self.apply_advanced_to_easy()

            self.advanced_text.setMinimumHeight(0)
            self.easy_group.show()
            self.advanced_group.hide()
        else:
            if connected:
                current_text = self.advanced_text.toPlainText().strip()

                if current_text:
                    new_ini_text = current_text + "\n"
                else:
                    new_ini_text = "[MiSTer]\n"

                updated_settings = self.build_easy_mode_settings()
                new_ini_text = update_mister_ini_text(new_ini_text, updated_settings)
                self.advanced_text.setPlainText(new_ini_text)

            self.advanced_text.setMinimumHeight(420)
            self.easy_group.hide()
            self.advanced_group.show()

        self.set_mister_settings_enabled(connected)

    def update_easy_mode_state(self):
        hdmi_mode = self.easy_hdmi_mode_combo.currentText().strip()
        direct_video = hdmi_mode == "Direct Video (CRT / Scaler)"

        self.easy_resolution_combo.setEnabled(
            not direct_video and self.connection.is_connected() and self.easy_mode_radio.isChecked()
        )
        self.easy_scaling_combo.setEnabled(
            not direct_video and self.connection.is_connected() and self.easy_mode_radio.isChecked()
        )
        self.easy_hdr_combo.setEnabled(
            not direct_video and self.connection.is_connected() and self.easy_mode_radio.isChecked()
        )
        self.easy_hdmi_limited_combo.setEnabled(
            not direct_video and self.connection.is_connected() and self.easy_mode_radio.isChecked()
        )
        self.easy_logo_combo.setEnabled(
            not direct_video and self.connection.is_connected() and self.easy_mode_radio.isChecked()
        )

    def get_current_profile_name(self):
        return self.main_window.connection_tab.profile_selector.currentText().strip()

    def get_mister_settings_device_name(self):
        return get_mister_settings_device_name(self.get_current_profile_name(), self.connection.host)

    def get_mister_settings_device_path(self):
        return get_mister_settings_device_path(self.get_current_profile_name(), self.connection.host)

    def save_mister_settings_retention_setting(self):
        try:
            value = int(self.retention_spin.value())
            save_mister_settings_retention_setting(self.main_window.config_data, value)
            self.config_data["mister_settings_retention"] = value
        except Exception:
            pass

    def open_mister_settings_folder(self):
        open_mister_settings_folder(self.get_mister_settings_device_path())

    def collect_easy_mode_values(self):
        return {
            "hdmi_mode": self.easy_hdmi_mode_combo.currentText().strip(),
            "resolution": self.easy_resolution_combo.currentText().strip(),
            "scaling": self.easy_scaling_combo.currentText().strip(),
            "hdmi_audio": self.easy_hdmi_audio_combo.currentText().strip(),
            "hdr": self.easy_hdr_combo.currentText().strip(),
            "hdmi_limited": self.easy_hdmi_limited_combo.currentText().strip(),
            "analogue": self.easy_analogue_combo.currentText().strip(),
            "logo": self.easy_logo_combo.currentText().strip(),
        }

    def apply_easy_mode_values(self, values):
        self.easy_hdmi_mode_combo.setCurrentText(values.get("hdmi_mode", "HD Output (Default)"))
        self.easy_resolution_combo.setCurrentText(values.get("resolution", "1920x1080@60"))
        self.easy_scaling_combo.setCurrentText(values.get("scaling", "Low Latency"))
        self.easy_hdmi_audio_combo.setCurrentText(values.get("hdmi_audio", "Enabled"))
        self.easy_hdr_combo.setCurrentText(values.get("hdr", "Disabled"))
        self.easy_hdmi_limited_combo.setCurrentText(values.get("hdmi_limited", "Full Range"))
        self.easy_analogue_combo.setCurrentText(values.get("analogue", "RGB (Consumer TV)"))
        self.easy_logo_combo.setCurrentText(values.get("logo", "Enabled"))
        self.update_easy_mode_state()

    def apply_advanced_to_easy(self):
        text = self.advanced_text.toPlainText()
        settings = parse_mister_ini(text)
        values = easy_mode_values_from_ini_settings(settings)
        self.apply_easy_mode_values(values)

    def load_mister_ini_into_ui(self, silent=True):
        if not self.connection.is_connected():
            return False

        ok, message = ensure_mister_ini_exists(self.connection)
        if not ok:
            if not silent:
                QMessageBox.critical(self, "MiSTer.ini Error", message)
            return False

        ini_text = self.connection.run_command("cat /media/fat/MiSTer.ini")
        if not ini_text:
            if not silent:
                QMessageBox.critical(self, "MiSTer.ini Error", "Unable to read /media/fat/MiSTer.ini")
            return False

        settings = parse_mister_ini(ini_text)
        values = easy_mode_values_from_ini_settings(settings)
        self.apply_easy_mode_values(values)
        return True

    def load_mister_ini_advanced(self):
        if not self.connection.is_connected():
            return

        ok, _ = ensure_mister_ini_exists(self.connection)
        if not ok:
            return

        ini_text = self.connection.run_command("cat /media/fat/MiSTer.ini")
        if not ini_text:
            return

        self.advanced_text.setPlainText(ini_text)

    def build_easy_mode_settings(self):
        return build_easy_mode_settings(self.collect_easy_mode_values())

    def backup_mister_settings(self, silent=False):
        if not self.connection.is_connected():
            if not silent:
                QMessageBox.critical(self, "Error", "Connect to a MiSTer first.")
            return False

        device_name = self.get_mister_settings_device_name()
        if not device_name:
            if not silent:
                QMessageBox.critical(self, "Error", "No device name or IP available.")
            return False

        device_path = self.get_mister_settings_device_path()
        retention = self.main_window.config_data.get("mister_settings_retention", 10)

        try:
            ok, message, backup_file = create_mister_settings_backup(
                self.connection,
                device_path,
                retention,
            )
            if not ok:
                if not silent:
                    QMessageBox.critical(self, "MiSTer.ini Error", message)
                return False

            if not silent:
                QMessageBox.information(
                    self,
                    "Backup Created",
                    f"MiSTer.ini backup created successfully.\n\n{backup_file}"
                )
            return True

        except Exception as e:
            if not silent:
                QMessageBox.critical(
                    self,
                    "Backup Failed",
                    f"Unable to create MiSTer.ini backup:\n{str(e)}"
                )
            return False

    def save_mister_settings(self):
        if not self.connection.is_connected():
            QMessageBox.critical(self, "Error", "Connect to a MiSTer first.")
            return

        ok, message = ensure_mister_ini_exists(self.connection)
        if not ok:
            QMessageBox.critical(self, "MiSTer.ini Error", message)
            return

        choice = QMessageBox.question(
            self,
            "Backup Before Apply",
            "Do you want to create a backup of the current MiSTer.ini before applying settings?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes
        )

        if choice == QMessageBox.StandardButton.Cancel:
            return

        if choice == QMessageBox.StandardButton.Yes:
            backup_ok = self.backup_mister_settings(silent=True)
            if not backup_ok:
                proceed = QMessageBox.question(
                    self,
                    "Backup Failed",
                    "Unable to create backup before applying settings.\n\nContinue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if proceed != QMessageBox.StandardButton.Yes:
                    return

        try:
            ini_text = self.connection.run_command("cat /media/fat/MiSTer.ini")
            if not ini_text:
                QMessageBox.critical(self, "MiSTer.ini Error", "Unable to read /media/fat/MiSTer.ini")
                return

            if self.easy_mode_radio.isChecked():
                updated_settings = self.build_easy_mode_settings()
                new_ini_text = update_mister_ini_text(ini_text, updated_settings)
            else:
                advanced_text = self.advanced_text.toPlainText().strip()
                if not advanced_text:
                    QMessageBox.critical(self, "MiSTer.ini Error", "Advanced editor is empty.")
                    return
                new_ini_text = advanced_text + "\n"

            sftp = self.connection.client.open_sftp()
            with sftp.open("/media/fat/MiSTer.ini", "w") as f:
                f.write(new_ini_text)
            sftp.close()

            self.load_mister_ini_into_ui(silent=True)
            self.load_mister_ini_advanced()

            reboot_now = QMessageBox.question(
                self,
                "Settings Applied",
                "MiSTer settings were applied successfully.\n\nA reboot is recommended.\n\nReboot now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reboot_now == QMessageBox.StandardButton.Yes:
                self.main_window.device_tab.reboot_device(skip_confirm=True)

        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Unable to save MiSTer settings:\n{str(e)}")

    def restore_default_mister_settings(self):
        if not self.connection.is_connected():
            QMessageBox.critical(self, "Error", "Connect to a MiSTer first.")
            return

        confirm = QMessageBox.question(
            self,
            "Restore Default Settings",
            "This will replace the current MiSTer.ini with the default settings from MiSTer_example.ini.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        example_exists = self.connection.run_command(
            'test -f /media/fat/MiSTer_example.ini && echo EXISTS'
        )

        if "EXISTS" not in (example_exists or ""):
            QMessageBox.critical(self, "Restore Defaults Failed", "MiSTer_example.ini was not found on the MiSTer.")
            return

        choice = QMessageBox.question(
            self,
            "Backup Current Settings",
            "Do you want to create a backup of the current MiSTer.ini before restoring defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes
        )

        if choice == QMessageBox.StandardButton.Cancel:
            return

        if choice == QMessageBox.StandardButton.Yes:
            backup_ok = self.backup_mister_settings(silent=True)
            if not backup_ok:
                proceed = QMessageBox.question(
                    self,
                    "Backup Failed",
                    "Unable to create backup before restoring defaults.\n\nContinue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if proceed != QMessageBox.StandardButton.Yes:
                    return

        result = restore_default_mister_settings(self.connection)
        if "RESTORED" not in (result or ""):
            QMessageBox.critical(self, "Restore Defaults Failed", "Unable to restore MiSTer.ini from MiSTer_example.ini.")
            return

        self.load_mister_ini_into_ui(silent=True)
        self.load_mister_ini_advanced()

        reboot_now = QMessageBox.question(
            self,
            "Defaults Restored",
            "Default MiSTer settings were restored successfully.\n\nA reboot is recommended.\n\nReboot now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reboot_now == QMessageBox.StandardButton.Yes:
            self.main_window.device_tab.reboot_device(skip_confirm=True)

    def restore_mister_settings(self):
        if not self.connection.is_connected():
            QMessageBox.critical(self, "Error", "Connect to a MiSTer first.")
            return

        device_name = self.get_mister_settings_device_name()
        if not device_name:
            QMessageBox.critical(self, "Error", "No device name or IP available.")
            return

        device_path = self.get_mister_settings_device_path()
        backup_files = list_mister_settings_backups(device_path)

        if not backup_files:
            QMessageBox.critical(self, "Error", "No MiSTer.ini backups found for this device.")
            return

        dialog = RestoreBackupDialog(backup_files, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_backup = dialog.selected_backup()
        if not selected_backup:
            return

        backup_path = f"{device_path}/{selected_backup}"

        try:
            restore_mister_settings_backup(self.connection, backup_path)
            self.load_mister_ini_into_ui(silent=True)
            self.load_mister_ini_advanced()

            reboot_now = QMessageBox.question(
                self,
                "Backup Restored",
                "MiSTer.ini backup restored successfully.\n\nA reboot is recommended.\n\nReboot now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reboot_now == QMessageBox.StandardButton.Yes:
                self.main_window.device_tab.reboot_device(skip_confirm=True)

        except Exception as e:
            QMessageBox.critical(self, "Restore Failed", f"Unable to restore MiSTer.ini backup:\n{str(e)}")
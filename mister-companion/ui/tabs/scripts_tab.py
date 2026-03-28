import traceback

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.config import save_config
from core.scripts_actions import (
    check_update_all_initialized,
    enable_zaparoo_service,
    ensure_update_all_config_bootstrap,
    get_scripts_status,
    install_cifs_mount,
    install_migrate_sd,
    install_update_all,
    install_zaparoo,
    open_scripts_folder_on_host,
    remove_cifs_config,
    run_cifs_mount,
    run_cifs_umount,
    run_update_all_stream,
    uninstall_cifs_mount,
    uninstall_migrate_sd,
    uninstall_update_all,
    uninstall_zaparoo,
)
from ui.dialogs.cifs_config_dialog import CifsConfigDialog
from ui.dialogs.update_all_config_dialog import UpdateAllConfigDialog


class ScriptTaskWorker(QThread):
    log_line = pyqtSignal(str)
    success = pyqtSignal(str)
    error = pyqtSignal(str)
    finished_task = pyqtSignal()
    task_result = pyqtSignal(object)

    def __init__(self, task_fn, success_message=""):
        super().__init__()
        self.task_fn = task_fn
        self.success_message = success_message

    def log(self, text):
        self.log_line.emit(text)

    def run(self):
        try:
            result = self.task_fn(self.log)

            if self.success_message:
                self.success.emit(self.success_message)

            self.task_result.emit(result)

        except Exception as e:
            detail = traceback.format_exc()
            self.error.emit(f"{str(e)}\n\n{detail}")
        finally:
            self.finished_task.emit()


class ScriptsTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection

        self.console_visible = False
        self.current_worker = None
        self.update_all_installed = False
        self.update_all_initialized = False
        self.waiting_for_reboot_reconnect = False

        self.build_ui()
        self.apply_disconnected_state()

    def build_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(14)
        self.setLayout(main_layout)

        # ===== update_all =====
        update_group = QGroupBox("update_all")
        update_layout = QVBoxLayout()
        update_layout.setContentsMargins(16, 18, 16, 18)
        update_layout.setSpacing(12)

        self.update_status_label = QLabel("update_all: Unknown")
        self.update_status_label.setStyleSheet("color: gray;")
        self.update_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        update_layout.addWidget(self.update_status_label)

        update_buttons = QHBoxLayout()
        update_buttons.setSpacing(10)

        self.install_update_button = QPushButton("Install update_all")
        self.install_update_button.setFixedWidth(160)

        self.uninstall_update_button = QPushButton("Uninstall update_all")
        self.uninstall_update_button.setFixedWidth(160)

        self.configure_update_button = QPushButton("Configure update_all")
        self.configure_update_button.setFixedWidth(180)

        self.run_update_button = QPushButton("Run update_all")
        self.run_update_button.setFixedWidth(160)

        update_buttons.addStretch()
        update_buttons.addWidget(self.install_update_button)
        update_buttons.addWidget(self.uninstall_update_button)
        update_buttons.addWidget(self.configure_update_button)
        update_buttons.addWidget(self.run_update_button)
        update_buttons.addStretch()

        update_layout.addLayout(update_buttons)
        update_group.setLayout(update_layout)
        main_layout.addWidget(update_group)

        # ===== Zaparoo =====
        zaparoo_group = QGroupBox("Zaparoo")
        zaparoo_layout = QVBoxLayout()
        zaparoo_layout.setContentsMargins(16, 18, 16, 18)
        zaparoo_layout.setSpacing(12)

        self.zaparoo_status_label = QLabel("Zaparoo: Unknown")
        self.zaparoo_status_label.setStyleSheet("color: gray;")
        self.zaparoo_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zaparoo_layout.addWidget(self.zaparoo_status_label)

        zaparoo_buttons = QHBoxLayout()
        zaparoo_buttons.setSpacing(10)

        self.install_zaparoo_button = QPushButton("Install Zaparoo")
        self.install_zaparoo_button.setFixedWidth(160)

        self.enable_zaparoo_service_button = QPushButton("Enable Zaparoo Service")
        self.enable_zaparoo_service_button.setFixedWidth(190)

        self.uninstall_zaparoo_button = QPushButton("Uninstall Zaparoo")
        self.uninstall_zaparoo_button.setFixedWidth(160)

        zaparoo_buttons.addStretch()
        zaparoo_buttons.addWidget(self.install_zaparoo_button)
        zaparoo_buttons.addWidget(self.enable_zaparoo_service_button)
        zaparoo_buttons.addWidget(self.uninstall_zaparoo_button)
        zaparoo_buttons.addStretch()

        zaparoo_layout.addLayout(zaparoo_buttons)
        zaparoo_group.setLayout(zaparoo_layout)
        main_layout.addWidget(zaparoo_group)

        # ===== SD Migration =====
        migrate_group = QGroupBox("SD Migration")
        migrate_layout = QVBoxLayout()
        migrate_layout.setContentsMargins(16, 18, 16, 18)
        migrate_layout.setSpacing(12)

        self.migrate_status_label = QLabel("migrate_sd: Unknown")
        self.migrate_status_label.setStyleSheet("color: gray;")
        self.migrate_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        migrate_layout.addWidget(self.migrate_status_label)

        migrate_buttons = QHBoxLayout()
        migrate_buttons.setSpacing(10)

        self.install_migrate_button = QPushButton("Install migrate_sd")
        self.install_migrate_button.setFixedWidth(180)

        self.uninstall_migrate_button = QPushButton("Uninstall migrate_sd")
        self.uninstall_migrate_button.setFixedWidth(180)

        migrate_buttons.addStretch()
        migrate_buttons.addWidget(self.install_migrate_button)
        migrate_buttons.addWidget(self.uninstall_migrate_button)
        migrate_buttons.addStretch()

        migrate_layout.addLayout(migrate_buttons)
        migrate_group.setLayout(migrate_layout)
        main_layout.addWidget(migrate_group)

        # ===== CIFS =====
        cifs_group = QGroupBox("CIFS Network Share")
        cifs_layout = QVBoxLayout()
        cifs_layout.setContentsMargins(16, 18, 16, 18)
        cifs_layout.setSpacing(12)

        self.cifs_status_label = QLabel("cifs_mount: Unknown")
        self.cifs_status_label.setStyleSheet("color: gray;")
        self.cifs_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cifs_layout.addWidget(self.cifs_status_label)

        cifs_buttons = QHBoxLayout()
        cifs_buttons.setSpacing(8)

        self.install_cifs_button = QPushButton("Install")
        self.install_cifs_button.setFixedWidth(110)

        self.configure_cifs_button = QPushButton("Configure")
        self.configure_cifs_button.setFixedWidth(110)

        self.mount_cifs_button = QPushButton("Mount")
        self.mount_cifs_button.setFixedWidth(110)

        self.unmount_cifs_button = QPushButton("Unmount")
        self.unmount_cifs_button.setFixedWidth(110)

        self.remove_cifs_config_button = QPushButton("Remove Config")
        self.remove_cifs_config_button.setFixedWidth(120)

        self.uninstall_cifs_button = QPushButton("Uninstall")
        self.uninstall_cifs_button.setFixedWidth(110)

        cifs_buttons.addStretch()
        cifs_buttons.addWidget(self.install_cifs_button)
        cifs_buttons.addWidget(self.configure_cifs_button)
        cifs_buttons.addWidget(self.mount_cifs_button)
        cifs_buttons.addWidget(self.unmount_cifs_button)
        cifs_buttons.addWidget(self.remove_cifs_config_button)
        cifs_buttons.addWidget(self.uninstall_cifs_button)
        cifs_buttons.addStretch()

        cifs_layout.addLayout(cifs_buttons)
        cifs_group.setLayout(cifs_layout)
        main_layout.addWidget(cifs_group)

        # ===== Open Scripts Folder =====
        scripts_folder_row = QHBoxLayout()
        scripts_folder_row.addStretch()

        self.open_scripts_folder_button = QPushButton("Open Scripts Folder")
        self.open_scripts_folder_button.setFixedWidth(180)
        scripts_folder_row.addWidget(self.open_scripts_folder_button)

        scripts_folder_row.addStretch()
        main_layout.addLayout(scripts_folder_row)

        # ===== SSH Output =====
        self.console_group = QGroupBox("SSH Output")
        console_layout = QVBoxLayout()
        console_layout.setContentsMargins(10, 10, 10, 10)
        console_layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.addStretch()

        self.hide_console_button = QPushButton("Hide")
        self.hide_console_button.setFixedWidth(70)
        header_row.addWidget(self.hide_console_button)
        console_layout.addLayout(header_row)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(230)
        console_layout.addWidget(self.console)

        self.console_group.setLayout(console_layout)
        self.console_group.hide()
        main_layout.addWidget(self.console_group)

        main_layout.addStretch()

        self.install_update_button.clicked.connect(self.install_update_all)
        self.uninstall_update_button.clicked.connect(self.uninstall_update_all)
        self.configure_update_button.clicked.connect(self.configure_update_all)
        self.run_update_button.clicked.connect(self.run_update_all)

        self.install_zaparoo_button.clicked.connect(self.install_zaparoo)
        self.enable_zaparoo_service_button.clicked.connect(self.enable_zaparoo_service)
        self.uninstall_zaparoo_button.clicked.connect(self.uninstall_zaparoo)

        self.install_migrate_button.clicked.connect(self.install_migrate_sd)
        self.uninstall_migrate_button.clicked.connect(self.uninstall_migrate_sd)

        self.install_cifs_button.clicked.connect(self.install_cifs_mount)
        self.configure_cifs_button.clicked.connect(self.configure_cifs)
        self.mount_cifs_button.clicked.connect(self.run_cifs_mount)
        self.unmount_cifs_button.clicked.connect(self.run_cifs_umount)
        self.remove_cifs_config_button.clicked.connect(self.remove_cifs_config)
        self.uninstall_cifs_button.clicked.connect(self.uninstall_cifs_mount)

        self.open_scripts_folder_button.clicked.connect(self.open_scripts_folder)
        self.hide_console_button.clicked.connect(self.toggle_console)

    def update_connection_state(self):
        if self.connection.is_connected():
            self.apply_connected_state()
            self.refresh_status()
        else:
            self.apply_disconnected_state()

    def apply_connected_state(self):
        self.refresh_status()

    def apply_disconnected_state(self):
        for button in [
            self.install_update_button,
            self.uninstall_update_button,
            self.configure_update_button,
            self.run_update_button,
            self.install_zaparoo_button,
            self.enable_zaparoo_service_button,
            self.uninstall_zaparoo_button,
            self.install_migrate_button,
            self.uninstall_migrate_button,
            self.install_cifs_button,
            self.configure_cifs_button,
            self.mount_cifs_button,
            self.unmount_cifs_button,
            self.remove_cifs_config_button,
            self.uninstall_cifs_button,
            self.open_scripts_folder_button,
        ]:
            button.setEnabled(False)

        self.update_status_label.setText("update_all: Unknown")
        self.update_status_label.setStyleSheet("color: gray;")

        self.zaparoo_status_label.setText("Zaparoo: Unknown")
        self.zaparoo_status_label.setStyleSheet("color: gray;")

        self.migrate_status_label.setText("migrate_sd: Unknown")
        self.migrate_status_label.setStyleSheet("color: gray;")

        self.cifs_status_label.setText("cifs_mount: Unknown")
        self.cifs_status_label.setStyleSheet("color: gray;")

    def refresh_status(self):
        if not self.connection.is_connected():
            self.apply_disconnected_state()
            return

        try:
            status = get_scripts_status(self.connection)
        except Exception:
            self.connection.mark_disconnected()
            self.apply_disconnected_state()
            return

        self.update_all_installed = status.update_all_installed
        self.update_all_initialized = status.update_all_initialized

        if status.update_all_installed:
            self.update_status_label.setText("update_all: Installed ✓")
            self.update_status_label.setStyleSheet("color: #00aa00;")
            self.install_update_button.setEnabled(False)
            self.uninstall_update_button.setEnabled(True)
            self.run_update_button.setEnabled(True)
            self.configure_update_button.setEnabled(True)
            self.update_all_initialized = status.update_all_initialized
        else:
            self.update_status_label.setText("update_all: Not Installed")
            self.update_status_label.setStyleSheet("color: #cc0000;")
            self.install_update_button.setEnabled(True)
            self.uninstall_update_button.setEnabled(False)
            self.run_update_button.setEnabled(False)
            self.configure_update_button.setEnabled(False)

        if not status.zaparoo_installed:
            self.zaparoo_status_label.setText("Zaparoo: Not Installed")
            self.zaparoo_status_label.setStyleSheet("color: #cc0000;")
            self.install_zaparoo_button.setEnabled(True)
            self.enable_zaparoo_service_button.setEnabled(False)
            self.uninstall_zaparoo_button.setEnabled(False)
        elif status.zaparoo_installed and not status.zaparoo_service_enabled:
            self.zaparoo_status_label.setText("Zaparoo: Installed (Service Disabled)")
            self.zaparoo_status_label.setStyleSheet("color: #cc8400;")
            self.install_zaparoo_button.setEnabled(False)
            self.enable_zaparoo_service_button.setEnabled(True)
            self.uninstall_zaparoo_button.setEnabled(True)
        else:
            self.zaparoo_status_label.setText("Zaparoo: Installed ✓")
            self.zaparoo_status_label.setStyleSheet("color: #00aa00;")
            self.install_zaparoo_button.setEnabled(False)
            self.enable_zaparoo_service_button.setEnabled(False)
            self.uninstall_zaparoo_button.setEnabled(True)

        if status.migrate_sd_installed:
            self.migrate_status_label.setText("migrate_sd: Installed ✓")
            self.migrate_status_label.setStyleSheet("color: #00aa00;")
            self.install_migrate_button.setEnabled(False)
            self.uninstall_migrate_button.setEnabled(True)
        else:
            self.migrate_status_label.setText("migrate_sd: Not Installed")
            self.migrate_status_label.setStyleSheet("color: #cc0000;")
            self.install_migrate_button.setEnabled(True)
            self.uninstall_migrate_button.setEnabled(False)

        if not status.cifs_installed:
            self.cifs_status_label.setText("cifs_mount: Not Installed")
            self.cifs_status_label.setStyleSheet("color: #cc0000;")
            self.install_cifs_button.setEnabled(True)
            self.configure_cifs_button.setEnabled(False)
            self.configure_cifs_button.setText("Configure")
            self.mount_cifs_button.setEnabled(False)
            self.unmount_cifs_button.setEnabled(False)
            self.remove_cifs_config_button.setEnabled(False)
            self.uninstall_cifs_button.setEnabled(False)
        elif status.cifs_installed and not status.cifs_configured:
            self.cifs_status_label.setText("cifs_mount: Installed (Not Configured)")
            self.cifs_status_label.setStyleSheet("color: #cc8400;")
            self.install_cifs_button.setEnabled(False)
            self.configure_cifs_button.setEnabled(True)
            self.configure_cifs_button.setText("Configure")
            self.mount_cifs_button.setEnabled(False)
            self.unmount_cifs_button.setEnabled(False)
            self.remove_cifs_config_button.setEnabled(False)
            self.uninstall_cifs_button.setEnabled(True)
        else:
            self.cifs_status_label.setText("cifs_mount: Configured ✓")
            self.cifs_status_label.setStyleSheet("color: #00aa00;")
            self.install_cifs_button.setEnabled(False)
            self.configure_cifs_button.setEnabled(True)
            self.configure_cifs_button.setText("Reconfigure")
            self.mount_cifs_button.setEnabled(True)
            self.unmount_cifs_button.setEnabled(True)
            self.remove_cifs_config_button.setEnabled(True)
            self.uninstall_cifs_button.setEnabled(True)

        self.open_scripts_folder_button.setEnabled(True)

    def show_console(self):
        if not self.console_visible:
            self.console_group.show()
            self.console_visible = True

    def toggle_console(self):
        if self.console_visible:
            self.console_group.hide()
            self.console_visible = False
        else:
            self.console_group.show()
            self.console_visible = True

    def clear_console(self):
        self.console.clear()

    def log(self, text):
        self.console.moveCursor(self.console.textCursor().MoveOperation.End)
        self.console.insertPlainText(text)
        self.console.ensureCursorVisible()

    def start_worker(self, task_fn, success_message=""):
        if self.current_worker is not None and self.current_worker.isRunning():
            QMessageBox.warning(self, "Busy", "Another script task is still running.")
            return

        self.show_console()
        self.clear_console()

        self.current_worker = ScriptTaskWorker(task_fn, success_message=success_message)
        self.current_worker.log_line.connect(self.log)
        self.current_worker.success.connect(self.on_worker_success)
        self.current_worker.error.connect(self.on_worker_error)
        self.current_worker.task_result.connect(self.on_worker_result)
        self.current_worker.finished_task.connect(self.on_worker_finished)
        self.current_worker.start()

    def on_worker_success(self, message):
        if message:
            QMessageBox.information(self, "Done", message)

    def on_worker_error(self, message):
        self.log(f"\nERROR:\n{message}\n")
        QMessageBox.critical(self, "Error", message.split("\n\n", 1)[0])

    def on_worker_result(self, result):
        if not result:
            return

        if isinstance(result, dict):
            if result.get("action") == "reboot_reconnect":
                self.connection.mark_disconnected()
                self.waiting_for_reboot_reconnect = True
                self.main_window.start_reboot_reconnect_polling()

    def on_worker_finished(self):
        self.current_worker = None

        if self.waiting_for_reboot_reconnect:
            return

        try:
            if self.connection.is_connected():
                self.refresh_status()
            else:
                self.apply_disconnected_state()
        except Exception:
            self.connection.mark_disconnected()
            self.apply_disconnected_state()

    def install_update_all(self):
        if not self.connection.is_connected():
            return

        def task(log):
            install_update_all(self.connection, log)

        self.start_worker(task, "update_all installed successfully.")

    def uninstall_update_all(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            "Uninstall update_all",
            "Are you sure you want to remove update_all?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        uninstall_update_all(self.connection)
        self.refresh_status()

    def configure_update_all(self):
        if not self.connection.is_connected():
            QMessageBox.critical(self, "Error", "Connect to a MiSTer first.")
            return

        if not self.update_all_installed:
            QMessageBox.critical(
                self,
                "update_all not installed",
                "Install update_all first before opening the configurator.",
            )
            return

        try:
            ensure_update_all_config_bootstrap(self.connection)
            self.update_all_initialized = check_update_all_initialized(self.connection)
        except Exception as e:
            QMessageBox.critical(
                self,
                "update_all configuration error",
                f"Could not prepare update_all configuration files.\n\n{e}",
            )
            return

        dialog = UpdateAllConfigDialog(self.connection, self)
        if dialog.exec():
            self.refresh_status()

    def run_update_all(self):
        if not self.connection.is_connected():
            return

        if not self.main_window.config_data.get("hide_update_all_warning", False):
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Question)
            msg.setWindowTitle("Run update_all")
            msg.setText(
                "update_all will run through SSH.\n\n"
                "The output will NOT appear on the MiSTer TV screen.\n"
                "It will only be visible inside MiSTer Companion.\n\n"
                "If you want the output to appear on the TV screen, run update_all from:\n"
                "• ZapScripts in MiSTer Companion\n"
                "• The Scripts menu on the MiSTer itself\n\n"
                "Continue?"
            )
            msg.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            msg.setDefaultButton(QMessageBox.StandardButton.Yes)

            dont_show_checkbox = QCheckBox("Don't show this again")
            msg.setCheckBox(dont_show_checkbox)

            msg.exec()

            if msg.result() != QMessageBox.StandardButton.Yes:
                return

            if dont_show_checkbox.isChecked():
                self.main_window.config_data["hide_update_all_warning"] = True
                save_config(self.main_window.config_data)

        def task(log):
            import time

            log("Running update_all...\n\n")
            run_update_all_stream(self.connection, log)
            log("\nupdate_all finished.\n")

            time.sleep(7)

            still_connected = False
            try:
                still_connected = self.connection.is_connected()
                if still_connected and self.connection.client:
                    transport = self.connection.client.get_transport()
                    still_connected = bool(transport and transport.is_active())
            except Exception:
                still_connected = False

            if still_connected:
                log("No reboot detected.\n")
                return {"action": "completed"}

            self.connection.mark_disconnected()
            log("MiSTer disconnected after update_all, likely due to reboot.\n")
            log("Starting automatic reconnect...\n")
            return {"action": "reboot_reconnect"}

        self.start_worker(task)

    def install_zaparoo(self):
        if not self.connection.is_connected():
            return

        def task(log):
            install_zaparoo(self.connection, log)

        self.start_worker(
            task,
            "Zaparoo has been installed successfully.\n\nNext step:\nClick 'Enable Zaparoo Service' to start Zaparoo automatically at boot.",
        )

    def enable_zaparoo_service(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            "Enable Zaparoo Service",
            "This will enable the Zaparoo service so it starts automatically on boot.\n\nContinue?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            enable_zaparoo_service(self.connection)
            QMessageBox.information(
                self,
                "Zaparoo Enabled",
                "Zaparoo service enabled.\n\nPlease reboot your MiSTer.",
            )
            self.refresh_status()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def uninstall_zaparoo(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            "Uninstall Zaparoo",
            "Are you sure you want to remove Zaparoo?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        uninstall_zaparoo(self.connection)
        self.refresh_status()

    def install_migrate_sd(self):
        if not self.connection.is_connected():
            return

        proceed = QMessageBox.question(
            self,
            "Install migrate_sd",
            "This tool installs the 'migrate_sd' script on your MiSTer.\n\n"
            "Important:\n"
            "The migration process MUST be started directly on the MiSTer\n"
            "from the Scripts menu.\n\n"
            "Or run it from the ZapScripts tab.\n\n"
            "Install the script now?",
        )
        if proceed != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            install_migrate_sd(self.connection, log)

        self.start_worker(task, "migrate_sd installed successfully.")

    def uninstall_migrate_sd(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            "Uninstall migrate_sd",
            "Are you sure you want to remove migrate_sd?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        uninstall_migrate_sd(self.connection)
        self.show_console()
        self.clear_console()
        self.log("migrate_sd removed.\n")
        self.refresh_status()

    def install_cifs_mount(self):
        if not self.connection.is_connected():
            return

        def task(log):
            install_cifs_mount(self.connection, log)

        self.start_worker(task, "CIFS scripts installed successfully.")

    def configure_cifs(self):
        if not self.connection.is_connected():
            return

        dialog = CifsConfigDialog(self.connection, self)
        if dialog.exec():
            self.refresh_status()

    def run_cifs_mount(self):
        if not self.connection.is_connected():
            return

        result = run_cifs_mount(self.connection)
        QMessageBox.information(self, "Mount", result or "Mount command sent.")

    def run_cifs_umount(self):
        if not self.connection.is_connected():
            return

        result = run_cifs_umount(self.connection)
        QMessageBox.information(self, "Unmount", result or "Unmount command sent.")

    def remove_cifs_config(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(self, "Remove Config", "Delete CIFS configuration?")
        if confirm != QMessageBox.StandardButton.Yes:
            return

        remove_cifs_config(self.connection)
        self.refresh_status()

    def uninstall_cifs_mount(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(self, "Uninstall", "Remove CIFS scripts?")
        if confirm != QMessageBox.StandardButton.Yes:
            return

        uninstall_cifs_mount(self.connection)
        self.refresh_status()

    def open_scripts_folder(self):
        host = self.connection.host
        if not host:
            QMessageBox.warning(self, "Open Scripts Folder", "No MiSTer IP address is available.")
            return

        try:
            open_scripts_folder_on_host(
                ip=host,
                username=self.connection.username,
                password=self.connection.password,
            )
        except Exception as e:
            QMessageBox.critical(self, "SMB Error", str(e))
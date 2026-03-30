import platform
import traceback

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.flasher import (
    ensure_balena_cli,
    ensure_mr_fusion_image,
    flash_image,
    get_mr_fusion_image,
    has_balena_cli,
    has_mr_fusion_image,
    is_flash_supported,
    list_available_drives,
)


class FlashWorker(QThread):
    log_line = pyqtSignal(str)
    success = pyqtSignal(str)
    error = pyqtSignal(str)
    finished_task = pyqtSignal()
    drives_loaded = pyqtSignal(list)

    def __init__(self, task_fn, success_message="", emit_drives=False):
        super().__init__()
        self.task_fn = task_fn
        self.success_message = success_message
        self.emit_drives = emit_drives

    def log(self, text):
        self.log_line.emit(text)

    def run(self):
        try:
            result = self.task_fn(self.log)

            if self.emit_drives:
                self.drives_loaded.emit(result or [])

            if self.success_message:
                self.success.emit(self.success_message)

        except Exception as e:
            detail = traceback.format_exc()
            self.error.emit(f"{str(e)}\n\n{detail}")
        finally:
            self.finished_task.emit()


class FlashTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection
        self.current_worker = None
        self.drive_map = {}

        self.build_ui()
        self.refresh_status()
        self.update_connection_state()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.main_group = QGroupBox("Flash Mr. Fusion")
        group_layout = QVBoxLayout(self.main_group)
        group_layout.setContentsMargins(12, 12, 12, 12)
        group_layout.setSpacing(12)

        self.info_label = QLabel(
            "Follow the steps below to prepare and flash an Mr. Fusion SD card for MiSTer."
        )
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        group_layout.addWidget(self.info_label)

        system = platform.system()
        if system == "Windows":
            privilege_text = "Important: Run MiSTer Companion as Administrator to flash SD cards."
        elif system == "Linux":
            privilege_text = "Important: Run MiSTer Companion with sudo or root privileges to flash SD cards."
        else:
            privilege_text = "Flashing is not supported on this platform."

        self.privileges_label = QLabel(privilege_text)
        self.privileges_label.setWordWrap(True)
        self.privileges_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.privileges_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        group_layout.addWidget(self.privileges_label)

        self.macos_label = QLabel("Flash Mr. Fusion is not available on macOS yet.")
        self.macos_label.setWordWrap(True)
        self.macos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.macos_label.setStyleSheet("color: orange; font-weight: bold;")
        self.macos_label.setVisible(platform.system() == "Darwin")
        group_layout.addWidget(self.macos_label)

        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(12, 12, 12, 12)
        status_layout.setSpacing(8)

        status_row = QHBoxLayout()
        status_row.setSpacing(24)
        status_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.mr_fusion_status_title = QLabel("Mr. Fusion image:")
        self.mr_fusion_status_label = QLabel("Not downloaded")
        self.mr_fusion_status_label.setWordWrap(True)

        self.balena_status_title = QLabel("balena CLI:")
        self.balena_status_label = QLabel("Not downloaded")
        self.balena_status_label.setWordWrap(True)

        status_row.addWidget(self.mr_fusion_status_title)
        status_row.addWidget(self.mr_fusion_status_label)
        status_row.addSpacing(24)
        status_row.addWidget(self.balena_status_title)
        status_row.addWidget(self.balena_status_label)

        status_layout.addLayout(status_row)
        group_layout.addWidget(status_group)

        downloads_group = QGroupBox("Downloads")
        downloads_layout = QHBoxLayout(downloads_group)
        downloads_layout.setContentsMargins(12, 12, 12, 12)
        downloads_layout.setSpacing(12)
        downloads_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.download_mr_fusion_button = QPushButton("Download Mr. Fusion")
        self.download_balena_button = QPushButton("Download balena CLI")

        downloads_layout.addWidget(self.download_mr_fusion_button)
        downloads_layout.addWidget(self.download_balena_button)

        group_layout.addWidget(downloads_group)

        drive_group = QGroupBox("Target Drive")
        drive_layout = QVBoxLayout(drive_group)
        drive_layout.setContentsMargins(12, 12, 12, 12)
        drive_layout.setSpacing(12)

        drive_row = QHBoxLayout()
        drive_row.setSpacing(8)
        drive_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.drive_combo = QComboBox()
        self.drive_combo.setMinimumWidth(450)
        self.drive_combo.addItem("Click 'Refresh Drives' to load available drives")

        self.refresh_drives_button = QPushButton("Refresh Drives")

        drive_row.addWidget(self.drive_combo, 1)
        drive_row.addWidget(self.refresh_drives_button)
        drive_layout.addLayout(drive_row)

        self.drive_warning_label = QLabel(
            "Warning: The selected drive will be fully erased."
        )
        self.drive_warning_label.setWordWrap(True)
        self.drive_warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drive_warning_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        drive_layout.addWidget(self.drive_warning_label)

        flash_row = QHBoxLayout()
        flash_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.flash_button = QPushButton("Flash SD Card")
        self.flash_button.setMinimumWidth(180)
        flash_row.addWidget(self.flash_button)

        drive_layout.addLayout(flash_row)

        group_layout.addWidget(drive_group)
        main_layout.addWidget(self.main_group)

        self.log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(self.log_group)
        log_layout.setContentsMargins(12, 12, 12, 12)
        log_layout.setSpacing(8)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(220)
        self.log_output.setMinimumWidth(750)
        log_layout.addWidget(self.log_output)

        main_layout.addWidget(self.log_group)
        self.log_group.hide()

        log_button_row = QHBoxLayout()
        log_button_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.toggle_log_button = QPushButton("Show Log")
        self.toggle_log_button.setFixedWidth(100)
        log_button_row.addWidget(self.toggle_log_button)

        main_layout.addLayout(log_button_row)
        main_layout.addStretch()

        self.download_mr_fusion_button.clicked.connect(self.download_mr_fusion)
        self.download_balena_button.clicked.connect(self.download_balena)
        self.refresh_drives_button.clicked.connect(self.refresh_drives)
        self.flash_button.clicked.connect(self.start_flash)
        self.toggle_log_button.clicked.connect(self.toggle_log)
        self.drive_combo.currentIndexChanged.connect(self.update_connection_state)

        if not is_flash_supported():
            self.download_mr_fusion_button.setEnabled(False)
            self.download_balena_button.setEnabled(False)
            self.refresh_drives_button.setEnabled(False)
            self.flash_button.setEnabled(False)
            self.drive_combo.setEnabled(False)

    def _set_ready_status(self, label, text="Ready"):
        label.setText(text)
        label.setStyleSheet("color: #2ecc71; font-weight: bold;")

    def _set_not_downloaded_status(self, label):
        label.setText("Not downloaded")
        label.setStyleSheet("color: #e74c3c; font-weight: bold;")

    def refresh_status(self):
        if has_mr_fusion_image():
            try:
                image_path = get_mr_fusion_image()
                self._set_ready_status(
                    self.mr_fusion_status_label,
                    f"Ready ({image_path.name})",
                )
            except Exception:
                self._set_ready_status(self.mr_fusion_status_label)
            self.download_mr_fusion_button.setEnabled(False)
        else:
            self._set_not_downloaded_status(self.mr_fusion_status_label)
            if is_flash_supported() and self.current_worker is None:
                self.download_mr_fusion_button.setEnabled(True)

        if has_balena_cli():
            self._set_ready_status(self.balena_status_label)
            self.download_balena_button.setEnabled(False)
        else:
            self._set_not_downloaded_status(self.balena_status_label)
            if is_flash_supported() and self.current_worker is None:
                self.download_balena_button.setEnabled(True)

    def update_connection_state(self):
        if not is_flash_supported():
            self.download_mr_fusion_button.setEnabled(False)
            self.download_balena_button.setEnabled(False)
            self.refresh_drives_button.setEnabled(False)
            self.flash_button.setEnabled(False)
            self.drive_combo.setEnabled(False)
            return

        if self.current_worker is not None:
            return

        self.refresh_status()

        self.refresh_drives_button.setEnabled(True)
        self.drive_combo.setEnabled(True)

        can_flash = (
            bool(self.get_selected_drive())
            and has_mr_fusion_image()
            and has_balena_cli()
        )
        self.flash_button.setEnabled(can_flash)

    def show_log(self):
        self.log_group.show()
        self.toggle_log_button.setText("Hide Log")

    def hide_log(self):
        self.log_group.hide()
        self.toggle_log_button.setText("Show Log")

    def toggle_log(self):
        if self.log_group.isVisible():
            self.hide_log()
        else:
            self.show_log()

    def append_log(self, text):
        self.show_log()
        self.log_output.append(text)

    def set_busy(self, busy):
        if not is_flash_supported():
            return

        self.download_mr_fusion_button.setEnabled(
            False if busy else not has_mr_fusion_image()
        )
        self.download_balena_button.setEnabled(
            False if busy else not has_balena_cli()
        )
        self.refresh_drives_button.setEnabled(not busy)
        self.flash_button.setEnabled(
            False
            if busy
            else (
                bool(self.get_selected_drive())
                and has_mr_fusion_image()
                and has_balena_cli()
            )
        )
        self.drive_combo.setEnabled(not busy)

    def on_task_success(self, message):
        if message:
            self.append_log(message)

    def on_task_error(self, message):
        self.append_log(message)
        QMessageBox.critical(self, "Error", message)

    def on_task_finished(self):
        self.current_worker = None
        self.refresh_status()
        self.update_connection_state()

    def start_worker(self, task_fn, success_message="", emit_drives=False):
        if self.current_worker is not None:
            return

        self.set_busy(True)
        self.show_log()

        self.current_worker = FlashWorker(
            task_fn,
            success_message=success_message,
            emit_drives=emit_drives,
        )
        self.current_worker.log_line.connect(self.append_log)
        self.current_worker.success.connect(self.on_task_success)
        self.current_worker.error.connect(self.on_task_error)
        self.current_worker.finished_task.connect(self.on_task_finished)

        if emit_drives:
            self.current_worker.drives_loaded.connect(self.populate_drives)

        self.current_worker.start()

    def populate_drives(self, drives):
        self.drive_combo.clear()
        self.drive_map.clear()

        if not drives:
            self.drive_combo.addItem("No drives found")
            self.flash_button.setEnabled(False)
            return

        for drive in drives:
            device = str(drive.get("device", "")).strip()
            display_text = str(drive.get("display_name", "")).strip() or device or "Unknown drive"

            self.drive_combo.addItem(display_text)
            self.drive_map[display_text] = device

        self.update_connection_state()

    def get_selected_drive(self):
        text = self.drive_combo.currentText().strip()
        return self.drive_map.get(text, "")

    def download_mr_fusion(self):
        def task(log):
            ensure_mr_fusion_image(force_download=True, log_callback=log)

        self.start_worker(task, success_message="Mr. Fusion download complete.")

    def download_balena(self):
        def task(log):
            ensure_balena_cli(force_download=True, log_callback=log)

        self.start_worker(task, success_message="balena CLI download complete.")

    def refresh_drives(self, silent=False):
        if not is_flash_supported():
            return

        def task(log):
            return list_available_drives(log_callback=log)

        self.start_worker(
            task,
            success_message="Drive refresh complete.",
            emit_drives=True,
        )

    def start_flash(self):
        if not is_flash_supported():
            return

        if not has_mr_fusion_image():
            QMessageBox.warning(
                self,
                "Mr. Fusion image missing",
                "Download the latest Mr. Fusion image first.",
            )
            return

        if not has_balena_cli():
            QMessageBox.warning(
                self,
                "balena CLI missing",
                "Download balena CLI first.",
            )
            return

        try:
            image_path = get_mr_fusion_image()
        except Exception:
            QMessageBox.warning(
                self,
                "Mr. Fusion image missing",
                "Download the latest Mr. Fusion image first.",
            )
            return

        drive = self.get_selected_drive()
        if not drive:
            QMessageBox.warning(
                self,
                "No drive selected",
                "Select a target drive first.",
            )
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Flash",
            f"This will erase all data on:\n\n{drive}\n\nDo you want to continue?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            flash_image(image_path, drive, log_callback=log)

        self.start_worker(task)
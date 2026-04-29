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
    ensure_superstation_image,
    flash_image,
    get_mr_fusion_image,
    get_superstation_image,
    get_superstation_image_status,
    has_balena_cli,
    has_mr_fusion_image,
    has_superstation_image,
    is_flash_supported,
    list_available_drives,
    remove_balena_cli,
    remove_mr_fusion_image,
    remove_superstation_image,
)
from core.language import tr


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
    MODE_MR_FUSION = "mr_fusion"
    MODE_SUPERSTATION = "superstation"

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

        self.main_group = QGroupBox(tr("flash_tab.title"))
        group_layout = QVBoxLayout(self.main_group)
        group_layout.setContentsMargins(12, 12, 12, 12)
        group_layout.setSpacing(12)

        mode_group = QGroupBox(tr("flash_tab.installer"))
        mode_layout = QHBoxLayout(mode_group)
        mode_layout.setContentsMargins(12, 12, 12, 12)
        mode_layout.setSpacing(12)
        mode_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        mode_label = QLabel(tr("flash_tab.select_installer"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Mr. Fusion", self.MODE_MR_FUSION)
        self.mode_combo.addItem("SuperStationOne SD Card Installer", self.MODE_SUPERSTATION)
        self.mode_combo.setMinimumWidth(300)

        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo)

        group_layout.addWidget(mode_group)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        group_layout.addWidget(self.info_label)

        system = platform.system()
        if system == "Windows":
            privilege_text = tr("flash_tab.privilege_windows")
        elif system == "Linux":
            privilege_text = tr("flash_tab.privilege_linux")
        elif system == "Darwin":
            privilege_text = tr("flash_tab.privilege_macos")
        else:
            privilege_text = tr("flash_tab.flash_not_supported")

        self.privileges_label = QLabel(privilege_text)
        self.privileges_label.setWordWrap(True)
        self.privileges_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.privileges_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        group_layout.addWidget(self.privileges_label)

        status_group = QGroupBox(tr("flash_tab.status"))
        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(12, 12, 12, 12)
        status_layout.setSpacing(8)

        status_row = QHBoxLayout()
        status_row.setSpacing(24)
        status_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.image_status_title = QLabel(tr("flash_tab.installer_image"))
        self.image_status_label = QLabel(tr("flash_tab.not_downloaded"))
        self.image_status_label.setWordWrap(True)

        self.balena_status_title = QLabel(tr("flash_tab.balena_cli"))
        self.balena_status_label = QLabel(tr("flash_tab.not_downloaded"))
        self.balena_status_label.setWordWrap(True)

        status_row.addWidget(self.image_status_title)
        status_row.addWidget(self.image_status_label)
        status_row.addSpacing(24)
        status_row.addWidget(self.balena_status_title)
        status_row.addWidget(self.balena_status_label)

        status_layout.addLayout(status_row)
        group_layout.addWidget(status_group)

        downloads_group = QGroupBox(tr("flash_tab.downloads"))
        downloads_layout = QHBoxLayout(downloads_group)
        downloads_layout.setContentsMargins(12, 12, 12, 12)
        downloads_layout.setSpacing(12)
        downloads_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.download_image_button = QPushButton(tr("flash_tab.download_image"))
        self.remove_image_button = QPushButton(tr("flash_tab.remove_image"))
        self.download_balena_button = QPushButton(tr("flash_tab.download_balena_cli"))
        self.remove_balena_button = QPushButton(tr("flash_tab.remove_balena_cli"))

        downloads_layout.addWidget(self.download_image_button)
        downloads_layout.addWidget(self.remove_image_button)
        downloads_layout.addSpacing(16)
        downloads_layout.addWidget(self.download_balena_button)
        downloads_layout.addWidget(self.remove_balena_button)

        group_layout.addWidget(downloads_group)

        drive_group = QGroupBox(tr("flash_tab.target_drive"))
        drive_layout = QVBoxLayout(drive_group)
        drive_layout.setContentsMargins(12, 12, 12, 12)
        drive_layout.setSpacing(12)

        drive_row = QHBoxLayout()
        drive_row.setSpacing(8)
        drive_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.drive_combo = QComboBox()
        self.drive_combo.setMinimumWidth(450)
        self.drive_combo.addItem(tr("flash_tab.refresh_drives_placeholder"))

        self.refresh_drives_button = QPushButton(tr("flash_tab.refresh_drives"))

        drive_row.addWidget(self.drive_combo, 1)
        drive_row.addWidget(self.refresh_drives_button)
        drive_layout.addLayout(drive_row)

        self.drive_warning_label = QLabel(
            tr("flash_tab.drive_warning")
        )
        self.drive_warning_label.setWordWrap(True)
        self.drive_warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drive_warning_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        drive_layout.addWidget(self.drive_warning_label)

        flash_row = QHBoxLayout()
        flash_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.flash_button = QPushButton(tr("flash_tab.flash_sd_card"))
        self.flash_button.setMinimumWidth(180)
        flash_row.addWidget(self.flash_button)

        drive_layout.addLayout(flash_row)

        group_layout.addWidget(drive_group)
        main_layout.addWidget(self.main_group)

        self.log_group = QGroupBox(tr("flash_tab.log"))
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

        self.toggle_log_button = QPushButton(tr("flash_tab.show_log"))
        self.toggle_log_button.setFixedWidth(100)
        log_button_row.addWidget(self.toggle_log_button)

        main_layout.addLayout(log_button_row)
        main_layout.addStretch()

        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        self.download_image_button.clicked.connect(self.download_selected_image)
        self.remove_image_button.clicked.connect(self.remove_selected_image)
        self.download_balena_button.clicked.connect(self.download_balena)
        self.remove_balena_button.clicked.connect(self.remove_balena)
        self.refresh_drives_button.clicked.connect(self.refresh_drives)
        self.flash_button.clicked.connect(self.start_flash)
        self.toggle_log_button.clicked.connect(self.toggle_log)
        self.drive_combo.currentIndexChanged.connect(self.update_connection_state)

        if not is_flash_supported():
            self.download_image_button.setEnabled(False)
            self.remove_image_button.setEnabled(False)
            self.download_balena_button.setEnabled(False)
            self.remove_balena_button.setEnabled(False)
            self.refresh_drives_button.setEnabled(False)
            self.flash_button.setEnabled(False)
            self.drive_combo.setEnabled(False)

        self.update_mode_ui()

    def current_mode(self):
        return self.mode_combo.currentData()

    def is_mr_fusion_mode(self):
        return self.current_mode() == self.MODE_MR_FUSION

    def is_superstation_mode(self):
        return self.current_mode() == self.MODE_SUPERSTATION

    def _set_ready_status(self, label, text=None):
        label.setText(text or tr("flash_tab.ready"))
        label.setStyleSheet("color: #2ecc71; font-weight: bold;")

    def _set_not_downloaded_status(self, label):
        label.setText(tr("flash_tab.not_downloaded"))
        label.setStyleSheet("color: #e74c3c; font-weight: bold;")

    def _set_warning_status(self, label, text):
        label.setText(text)
        label.setStyleSheet("color: #f39c12; font-weight: bold;")

    def update_mode_ui(self):
        if self.is_mr_fusion_mode():
            self.info_label.setText(
                tr("flash_tab.mr_fusion_info")
            )
            self.image_status_title.setText(tr("flash_tab.mr_fusion_image"))
            self.download_image_button.setText(tr("flash_tab.download_mr_fusion"))
            self.remove_image_button.setText(tr("flash_tab.remove_mr_fusion"))
        else:
            self.info_label.setText(
                tr("flash_tab.superstation_info")
            )
            self.image_status_title.setText(tr("flash_tab.superstation_image"))
            self.download_image_button.setText(tr("flash_tab.download_superstation"))
            self.remove_image_button.setText(tr("flash_tab.remove_superstation"))

    def refresh_status(self):
        self.update_mode_ui()

        if self.is_mr_fusion_mode():
            if has_mr_fusion_image():
                try:
                    image_path = get_mr_fusion_image()
                    self._set_ready_status(
                        self.image_status_label,
                        tr("flash_tab.ready_with_name", name=image_path.name),
                    )
                except Exception:
                    self._set_ready_status(self.image_status_label)

                self.download_image_button.setText(tr("flash_tab.download_mr_fusion"))
                self.download_image_button.setEnabled(False)
                self.remove_image_button.setEnabled(
                    is_flash_supported() and self.current_worker is None and has_mr_fusion_image()
                )
            else:
                self._set_not_downloaded_status(self.image_status_label)
                self.download_image_button.setText(tr("flash_tab.download_mr_fusion"))
                if is_flash_supported() and self.current_worker is None:
                    self.download_image_button.setEnabled(True)
                self.remove_image_button.setEnabled(False)

        else:
            try:
                status = get_superstation_image_status()
            except Exception:
                status = {
                    "installed": False,
                    "up_to_date": None,
                    "local_name": None,
                    "latest_name": None,
                    "update_available": False,
                }

            installed = bool(status.get("installed"))
            up_to_date = status.get("up_to_date")
            local_name = status.get("local_name")
            latest_name = status.get("latest_name")
            update_available = bool(status.get("update_available"))

            if not installed:
                self._set_not_downloaded_status(self.image_status_label)
                self.download_image_button.setText(tr("flash_tab.download_superstation"))
                if is_flash_supported() and self.current_worker is None:
                    self.download_image_button.setEnabled(True)
                self.remove_image_button.setEnabled(False)
            else:
                if update_available:
                    label_text = tr("flash_tab.update_available")
                    if local_name and latest_name:
                        label_text = tr(
                            "flash_tab.update_available_from_to",
                            local_name=local_name,
                            latest_name=latest_name,
                        )
                    elif latest_name:
                        label_text = tr(
                            "flash_tab.update_available_name",
                            latest_name=latest_name,
                        )

                    self._set_warning_status(self.image_status_label, label_text)
                    self.download_image_button.setText(tr("flash_tab.update"))
                    if is_flash_supported() and self.current_worker is None:
                        self.download_image_button.setEnabled(True)
                    self.remove_image_button.setEnabled(
                        is_flash_supported() and self.current_worker is None
                    )
                else:
                    ready_text = (
                        tr("flash_tab.ready_with_name", name=local_name)
                        if local_name
                        else tr("flash_tab.ready")
                    )

                    if up_to_date is False:
                        self._set_warning_status(self.image_status_label, ready_text)
                    else:
                        self._set_ready_status(self.image_status_label, ready_text)

                    self.download_image_button.setText(tr("flash_tab.download_superstation"))
                    self.download_image_button.setEnabled(False)
                    self.remove_image_button.setEnabled(
                        is_flash_supported() and self.current_worker is None and has_superstation_image()
                    )

        if has_balena_cli():
            self._set_ready_status(self.balena_status_label)
            self.download_balena_button.setEnabled(False)
            self.remove_balena_button.setEnabled(
                is_flash_supported() and self.current_worker is None
            )
        else:
            self._set_not_downloaded_status(self.balena_status_label)
            if is_flash_supported() and self.current_worker is None:
                self.download_balena_button.setEnabled(True)
            self.remove_balena_button.setEnabled(False)

    def selected_image_ready(self):
        if self.is_mr_fusion_mode():
            return has_mr_fusion_image()

        try:
            return get_superstation_image() is not None
        except Exception:
            return False

    def get_selected_image_path(self):
        if self.is_mr_fusion_mode():
            return get_mr_fusion_image()
        return get_superstation_image()

    def get_selected_image_name(self):
        if self.is_mr_fusion_mode():
            return "Mr. Fusion"
        return tr("flash_tab.superstation_image_name")

    def update_connection_state(self):
        if not is_flash_supported():
            self.download_image_button.setEnabled(False)
            self.remove_image_button.setEnabled(False)
            self.download_balena_button.setEnabled(False)
            self.remove_balena_button.setEnabled(False)
            self.refresh_drives_button.setEnabled(False)
            self.flash_button.setEnabled(False)
            self.drive_combo.setEnabled(False)
            return

        if self.current_worker is not None:
            return

        self.refresh_status()

        self.refresh_drives_button.setEnabled(True)
        self.drive_combo.setEnabled(True)
        self.mode_combo.setEnabled(True)

        can_flash = (
            bool(self.get_selected_drive())
            and self.selected_image_ready()
            and has_balena_cli()
        )
        self.flash_button.setEnabled(can_flash)

    def on_mode_changed(self):
        self.refresh_status()
        self.update_connection_state()

    def show_log(self):
        self.log_group.show()
        self.toggle_log_button.setText(tr("flash_tab.hide_log"))

    def hide_log(self):
        self.log_group.hide()
        self.toggle_log_button.setText(tr("flash_tab.show_log"))

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

        self.mode_combo.setEnabled(not busy)
        self.refresh_drives_button.setEnabled(not busy)
        self.drive_combo.setEnabled(not busy)

        if busy:
            self.download_image_button.setEnabled(False)
            self.remove_image_button.setEnabled(False)
            self.download_balena_button.setEnabled(False)
            self.remove_balena_button.setEnabled(False)
            self.flash_button.setEnabled(False)
            return

        self.refresh_status()
        self.flash_button.setEnabled(
            bool(self.get_selected_drive())
            and self.selected_image_ready()
            and has_balena_cli()
        )

    def on_task_success(self, message):
        if message:
            self.append_log(message)

    def on_task_error(self, message):
        self.append_log(message)
        QMessageBox.critical(self, tr("common.error"), message)

    def on_task_finished(self):
        self.current_worker = None
        self.set_busy(False)

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
            self.drive_combo.addItem(tr("flash_tab.no_drives_found"))
            self.flash_button.setEnabled(False)
            return

        for drive in drives:
            device = str(drive.get("device", "")).strip()
            display_text = str(drive.get("display_name", "")).strip() or device or tr("flash_tab.unknown_drive")

            self.drive_combo.addItem(display_text)
            self.drive_map[display_text] = device

        self.update_connection_state()

    def get_selected_drive(self):
        text = self.drive_combo.currentText().strip()
        return self.drive_map.get(text, "")

    def download_selected_image(self):
        if self.is_mr_fusion_mode():
            self.download_mr_fusion()
        else:
            self.download_superstation()

    def download_mr_fusion(self):
        def task(log):
            ensure_mr_fusion_image(force_download=True, log_callback=log)

        self.start_worker(task, success_message=tr("flash_tab.mr_fusion_download_complete"))

    def download_superstation(self):
        def task(log):
            ensure_superstation_image(force_download=True, log_callback=log)

        button_text = self.download_image_button.text().strip().lower()
        success_message = (
            tr("flash_tab.superstation_update_complete")
            if button_text == tr("flash_tab.update").lower()
            else tr("flash_tab.superstation_download_complete")
        )
        self.start_worker(task, success_message=success_message)

    def download_balena(self):
        def task(log):
            ensure_balena_cli(force_download=True, log_callback=log)

        self.start_worker(task, success_message=tr("flash_tab.balena_download_complete"))

    def remove_selected_image(self):
        if self.is_mr_fusion_mode():
            title = tr("flash_tab.remove_mr_fusion")
            text = tr("flash_tab.remove_mr_fusion_confirm")
        else:
            title = tr("flash_tab.remove_superstation_image_title")
            text = tr("flash_tab.remove_superstation_confirm")

        confirm = QMessageBox.question(self, title, text)
        if confirm != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            if self.is_mr_fusion_mode():
                remove_mr_fusion_image(log_callback=log)
            else:
                remove_superstation_image(log_callback=log)

        success_message = (
            tr("flash_tab.mr_fusion_files_removed")
            if self.is_mr_fusion_mode()
            else tr("flash_tab.superstation_files_removed")
        )
        self.start_worker(task, success_message=success_message)

    def remove_balena(self):
        confirm = QMessageBox.question(
            self,
            tr("flash_tab.remove_balena_cli"),
            tr("flash_tab.remove_balena_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            remove_balena_cli(log_callback=log)

        self.start_worker(task, success_message=tr("flash_tab.balena_files_removed"))

    def refresh_drives(self, silent=False):
        if not is_flash_supported():
            return

        def task(log):
            return list_available_drives(log_callback=log)

        self.start_worker(
            task,
            success_message=tr("flash_tab.drive_refresh_complete"),
            emit_drives=True,
        )

    def start_flash(self):
        if not is_flash_supported():
            return

        if not self.selected_image_ready():
            image_name = self.get_selected_image_name()
            QMessageBox.warning(
                self,
                tr("flash_tab.image_missing_title", image_name=image_name),
                tr("flash_tab.download_latest_image_first", image_name=image_name),
            )
            return

        if not has_balena_cli():
            QMessageBox.warning(
                self,
                tr("flash_tab.balena_missing_title"),
                tr("flash_tab.download_balena_first"),
            )
            return

        try:
            image_path = self.get_selected_image_path()
        except Exception:
            image_name = self.get_selected_image_name()
            QMessageBox.warning(
                self,
                tr("flash_tab.image_missing_title", image_name=image_name),
                tr("flash_tab.download_latest_image_first", image_name=image_name),
            )
            return

        drive = self.get_selected_drive()
        if not drive:
            QMessageBox.warning(
                self,
                tr("flash_tab.no_drive_selected_title"),
                tr("flash_tab.select_target_drive_first"),
            )
            return

        confirm = QMessageBox.question(
            self,
            tr("flash_tab.confirm_flash_title"),
            tr("flash_tab.confirm_flash_message", drive=drive),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        if platform.system() == "Darwin":
            from PyQt6.QtWidgets import QInputDialog, QLineEdit
            password, ok = QInputDialog.getText(
                self,
                tr("flash_tab.admin_password_title"),
                tr("flash_tab.admin_password_message"),
                QLineEdit.EchoMode.Password
            )
            if not ok or not password:
                return
        else:
            password = None

        def task(log):
            flash_image(image_path, drive, log_callback=log, password=password)

        self.start_worker(task)
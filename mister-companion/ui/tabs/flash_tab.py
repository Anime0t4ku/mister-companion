import platform
import traceback
import time

from PyQt6.QtCore import QThread, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.scaling import set_text_button_min_width
from core.flasher import (
    ensure_balena_cli,
    ensure_mc_fusion_image,
    ensure_mr_fusion_image,
    flash_image,
    get_mc_fusion_image,
    get_mc_fusion_image_status,
    get_mr_fusion_image,
    has_balena_cli,
    has_mc_fusion_image,
    has_mr_fusion_image,
    is_flash_supported,
    list_available_drives,
    remove_balena_cli,
    remove_mc_fusion_image,
    remove_mr_fusion_image,
)


class FlashStatusWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, mode):
        super().__init__()
        self.mode = mode

    def run(self):
        try:
            balena_ready = has_balena_cli()

            status = {
                "mode": self.mode,
                "balena_ready": balena_ready,
                "mc_fusion_status": {
                    "installed": False,
                    "up_to_date": None,
                    "local_name": None,
                    "latest_name": None,
                    "update_available": False,
                },
                "mr_fusion_installed": False,
                "mr_fusion_name": "",
            }

            if self.mode == FlashTab.MODE_MC_FUSION:
                try:
                    status["mc_fusion_status"] = get_mc_fusion_image_status()
                except Exception:
                    status["mc_fusion_status"] = {
                        "installed": False,
                        "up_to_date": None,
                        "local_name": None,
                        "latest_name": None,
                        "update_available": False,
                    }

            elif self.mode == FlashTab.MODE_MR_FUSION:
                installed = has_mr_fusion_image()
                status["mr_fusion_installed"] = installed

                if installed:
                    try:
                        image_path = get_mr_fusion_image()
                        status["mr_fusion_name"] = image_path.name
                    except Exception:
                        status["mr_fusion_name"] = ""

            self.result.emit(status)

        except Exception as e:
            self.error.emit(str(e))


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
            self.log_line.emit(traceback.format_exc())
            self.error.emit(str(e))
        finally:
            self.finished_task.emit()


class FlashTab(QWidget):
    MODE_MC_FUSION = "mc_fusion"
    MODE_MR_FUSION = "mr_fusion"

    STATUS_CACHE_TTL_SECONDS = 300

    SUCCESS_FLASH_COMPLETE = "Flash complete."

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection
        self.current_worker = None
        self.status_worker = None
        self.drive_map = {}
        self.status_cache = {}
        self._first_show_done = False

        self.build_ui()
        self.update_connection_state(lightweight=True)

    def build_ui(self):
        self.setObjectName("FlashPage")
        self.setStyleSheet(
            """
            QWidget#FlashPage QGroupBox#FlashShell {
                background: transparent;
                border: none;
                margin: 0px;
                padding: 0px;
            }

            QWidget#FlashPage QGroupBox#FlashShell::title {
                color: transparent;
                background: transparent;
                padding: 0px;
            }

            QWidget#FlashPage QGroupBox#FlashCard {
                background-color: palette(alternate-base);
                border: 1px solid palette(button);
                border-radius: 12px;
                margin-top: 18px;
                padding: 14px;
                font-weight: 700;
            }

            QWidget#FlashPage QGroupBox#FlashCard::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                padding: 0px 7px;
                background: transparent;
                color: palette(highlight);
            }

            QWidget#FlashPage QPushButton#PrimaryAction {
                background-color: palette(highlight);
                color: palette(highlighted-text);
                border-color: palette(highlight);
                font-weight: 700;
            }
            """
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        self.main_group = QGroupBox("")
        self.main_group.setObjectName("FlashShell")
        self.main_group.setMaximumWidth(1100)
        self.main_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        group_layout = QVBoxLayout(self.main_group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(12)

        header_title = QLabel("Flash SD")
        header_title.setStyleSheet("font-weight: 700; font-size: 19px;")
        group_layout.addWidget(header_title)

        installer_group = QGroupBox("Installer")
        installer_group.setObjectName("FlashCard")
        installer_layout = QVBoxLayout(installer_group)
        installer_layout.setContentsMargins(16, 20, 16, 14)
        installer_layout.setSpacing(10)

        installer_row = QHBoxLayout()
        installer_row.setSpacing(10)
        installer_row.addStretch(1)

        mode_label = QLabel("Select installer:")
        mode_label.setStyleSheet("font-weight: 600;")
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("MC-Fusion", self.MODE_MC_FUSION)
        self.mode_combo.addItem("Mr. Fusion", self.MODE_MR_FUSION)
        self.mode_combo.setMinimumWidth(300)

        installer_row.addWidget(mode_label)
        installer_row.addWidget(self.mode_combo)
        installer_row.addStretch(1)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        system = platform.system()
        if system == "Windows":
            privilege_text = "Important: Run MiSTer Companion as Administrator to flash SD cards."
        elif system == "Linux":
            privilege_text = "Important: Run MiSTer Companion with sudo or root privileges to flash SD cards."
        elif system == "Darwin":
            privilege_text = "balena CLI may prompt for your password to write to the SD card."
        else:
            privilege_text = "Flashing is not supported on this platform."

        self.privileges_label = QLabel(privilege_text)
        self.privileges_label.setWordWrap(True)
        self.privileges_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.privileges_label.setStyleSheet("color: #f39c12; font-weight: bold;")

        installer_layout.addLayout(installer_row)
        installer_layout.addWidget(self.info_label)
        installer_layout.addWidget(self.privileges_label)
        group_layout.addWidget(installer_group)

        middle_row = QHBoxLayout()
        middle_row.setSpacing(12)

        requirements_group = QGroupBox("Requirements")
        requirements_group.setObjectName("FlashCard")
        requirements_layout = QVBoxLayout(requirements_group)
        requirements_layout.setContentsMargins(16, 20, 16, 14)
        requirements_layout.setSpacing(16)

        image_block = QVBoxLayout()
        image_block.setSpacing(8)

        self.image_status_title = QLabel("Installer image:")
        self.image_status_title.setStyleSheet("font-weight: 600;")
        self.image_status_label = QLabel("Not downloaded")
        self.image_status_label.setWordWrap(True)

        image_status_row = QHBoxLayout()
        image_status_row.setSpacing(8)
        image_status_row.addWidget(self.image_status_title)
        image_status_row.addWidget(self.image_status_label, 1)

        image_buttons_row = QHBoxLayout()
        image_buttons_row.setSpacing(8)
        image_buttons_row.addStretch(1)

        self.download_image_button = QPushButton("Download Image")
        self.remove_image_button = QPushButton("Remove Image")

        set_text_button_min_width(self.download_image_button, 150)
        set_text_button_min_width(self.remove_image_button, 130)

        image_buttons_row.addWidget(self.download_image_button)
        image_buttons_row.addWidget(self.remove_image_button)
        image_buttons_row.addStretch(1)

        image_block.addLayout(image_status_row)
        image_block.addLayout(image_buttons_row)

        balena_block = QVBoxLayout()
        balena_block.setSpacing(8)

        self.balena_status_title = QLabel("balena CLI:")
        self.balena_status_title.setStyleSheet("font-weight: 600;")
        self.balena_status_label = QLabel("Not downloaded")
        self.balena_status_label.setWordWrap(True)

        balena_status_row = QHBoxLayout()
        balena_status_row.setSpacing(8)
        balena_status_row.addWidget(self.balena_status_title)
        balena_status_row.addWidget(self.balena_status_label, 1)

        balena_buttons_row = QHBoxLayout()
        balena_buttons_row.setSpacing(8)
        balena_buttons_row.addStretch(1)

        self.download_balena_button = QPushButton("Download balena CLI")
        self.remove_balena_button = QPushButton("Remove balena CLI")

        set_text_button_min_width(self.download_balena_button, 150)
        set_text_button_min_width(self.remove_balena_button, 130)

        balena_buttons_row.addWidget(self.download_balena_button)
        balena_buttons_row.addWidget(self.remove_balena_button)
        balena_buttons_row.addStretch(1)

        balena_block.addLayout(balena_status_row)
        balena_block.addLayout(balena_buttons_row)

        requirements_layout.addLayout(image_block)
        requirements_layout.addLayout(balena_block)
        requirements_layout.addStretch()

        target_group = QGroupBox("Target Drive")
        target_group.setObjectName("FlashCard")
        target_layout = QVBoxLayout(target_group)
        target_layout.setContentsMargins(16, 20, 16, 14)
        target_layout.setSpacing(12)

        drive_row = QHBoxLayout()
        drive_row.setSpacing(8)

        self.drive_combo = QComboBox()
        self.drive_combo.setMinimumWidth(420)
        self.drive_combo.addItem("Click 'Refresh Drives' to load available drives")

        self.refresh_drives_button = QPushButton("Refresh Drives")
        set_text_button_min_width(self.refresh_drives_button, 120)

        target_group.setMinimumWidth(
            self.drive_combo.minimumWidth()
            + self.refresh_drives_button.minimumWidth()
            + drive_row.spacing()
            + 32
        )

        drive_row.addWidget(self.drive_combo, 1)
        drive_row.addWidget(self.refresh_drives_button)

        self.drive_warning_label = QLabel(
            "Warning: The selected drive will be fully erased."
        )
        self.drive_warning_label.setWordWrap(True)
        self.drive_warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drive_warning_label.setStyleSheet("color: #f39c12; font-weight: bold;")

        flash_row = QHBoxLayout()
        flash_row.addStretch(1)

        self.flash_button = QPushButton("Flash SD Card")
        self.flash_button.setObjectName("PrimaryAction")
        set_text_button_min_width(self.flash_button, 190, height=34)

        flash_row.addWidget(self.flash_button)
        flash_row.addStretch(1)

        target_layout.addLayout(drive_row)
        target_layout.addWidget(self.drive_warning_label)
        target_layout.addLayout(flash_row)
        target_layout.addStretch()

        requirements_group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        target_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        middle_row.addWidget(requirements_group, 1)
        middle_row.addWidget(target_group, 2)
        group_layout.addLayout(middle_row)

        self.log_group = QGroupBox("Log")
        self.log_group.setObjectName("FlashCard")
        log_layout = QVBoxLayout(self.log_group)
        log_layout.setContentsMargins(16, 20, 16, 14)
        log_layout.setSpacing(8)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(110)
        self.log_output.setMaximumHeight(140)
        self.log_output.setMinimumWidth(750)
        log_layout.addWidget(self.log_output)

        group_layout.addWidget(self.log_group)
        self.log_group.hide()

        log_button_row = QHBoxLayout()
        log_button_row.addStretch(1)

        self.toggle_log_button = QPushButton("Show Log")
        set_text_button_min_width(self.toggle_log_button, 100)
        log_button_row.addWidget(self.toggle_log_button)
        log_button_row.addStretch(1)
        group_layout.addLayout(log_button_row)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.addStretch(1)
        content_row.addWidget(self.main_group)
        content_row.addStretch(1)
        main_layout.addLayout(content_row)
        main_layout.addStretch(1)

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

    def showEvent(self, event):
        super().showEvent(event)

        if not self._first_show_done:
            self._first_show_done = True
            QTimer.singleShot(0, lambda: self.refresh_status(force=True))

    def current_mode(self):
        return self.mode_combo.currentData()

    def is_mc_fusion_mode(self):
        return self.current_mode() == self.MODE_MC_FUSION

    def is_mr_fusion_mode(self):
        return self.current_mode() == self.MODE_MR_FUSION

    def _set_ready_status(self, label, text="Ready"):
        label.setText(text)
        label.setStyleSheet("color: #2ecc71; font-weight: bold;")

    def _set_not_downloaded_status(self, label):
        label.setText("Not downloaded")
        label.setStyleSheet("color: #e74c3c; font-weight: bold;")

    def _set_warning_status(self, label, text):
        label.setText(text)
        label.setStyleSheet("color: #f39c12; font-weight: bold;")

    def _set_refreshing_status(self, label, text="Checking..."):
        label.setText(text)
        label.setStyleSheet("color: #1e88e5; font-weight: bold;")

    def update_mode_ui(self):
        if self.is_mc_fusion_mode():
            self.info_label.setText(
                "Follow the steps below to prepare and flash an MC-Fusion SD card for MiSTer. "
                "MC-Fusion is a MiSTer Companion focused fork of Mr. Fusion."
            )
            self.image_status_title.setText("MC-Fusion image:")
            self.download_image_button.setText("Download MC-Fusion")
            self.remove_image_button.setText("Remove MC-Fusion")
        elif self.is_mr_fusion_mode():
            self.info_label.setText(
                "Follow the steps below to prepare and flash a Mr. Fusion SD card for MiSTer."
            )
            self.image_status_title.setText("Mr. Fusion image:")
            self.download_image_button.setText("Download Mr. Fusion")
            self.remove_image_button.setText("Remove Mr. Fusion")

    def show_refreshing_state(self):
        if not is_flash_supported():
            return

        if self.current_worker is not None:
            return

        if self.status_worker is not None and self.status_worker.isRunning():
            return

        self.update_mode_ui()
        self._set_refreshing_status(self.image_status_label, "Checking image...")
        self._set_refreshing_status(self.balena_status_label, "Checking balena CLI...")

        self.download_image_button.setEnabled(False)
        self.remove_image_button.setEnabled(False)
        self.download_balena_button.setEnabled(False)
        self.remove_balena_button.setEnabled(False)

    def _cache_is_fresh(self, mode):
        cached = self.status_cache.get(mode)
        if not cached:
            return False

        timestamp = cached.get("timestamp", 0)
        return (time.monotonic() - timestamp) <= self.STATUS_CACHE_TTL_SECONDS

    def _store_status_cache(self, status):
        mode = status.get("mode")
        if not mode:
            return

        self.status_cache[mode] = {
            "timestamp": time.monotonic(),
            "status": status,
        }

    def _cached_status(self, mode):
        cached = self.status_cache.get(mode) or {}
        return cached.get("status")

    def refresh_status(self, force=False):
        self.update_mode_ui()

        if not is_flash_supported():
            self.apply_unsupported_state()
            return

        if self.current_worker is not None:
            return

        mode = self.current_mode()

        if not force and self._cache_is_fresh(mode):
            cached_status = self._cached_status(mode)
            if cached_status:
                self.apply_status_result(cached_status)
                return

        if self.status_worker is not None and self.status_worker.isRunning():
            return

        self.show_refreshing_state()

        worker = FlashStatusWorker(mode)
        self.status_worker = worker
        worker.result.connect(self.on_status_result)
        worker.error.connect(self.on_status_error)
        worker.finished.connect(self.on_status_finished)
        worker.start()

    def apply_unsupported_state(self):
        self.download_image_button.setEnabled(False)
        self.remove_image_button.setEnabled(False)
        self.download_balena_button.setEnabled(False)
        self.remove_balena_button.setEnabled(False)
        self.refresh_drives_button.setEnabled(False)
        self.flash_button.setEnabled(False)
        self.drive_combo.setEnabled(False)

    def on_status_result(self, status):
        if not isinstance(status, dict):
            return

        self._store_status_cache(status)

        if status.get("mode") == self.current_mode():
            self.apply_status_result(status)

    def on_status_error(self, message):
        self._set_warning_status(self.image_status_label, f"Unable to check status: {message}")
        self._set_warning_status(self.balena_status_label, "Unable to check status")
        self.update_connection_state(lightweight=True)

    def on_status_finished(self):
        worker = self.status_worker
        self.status_worker = None

        if worker is not None:
            worker.deleteLater()

    def apply_status_result(self, status):
        if not is_flash_supported():
            self.apply_unsupported_state()
            return

        mode = status.get("mode", self.current_mode())
        balena_ready = bool(status.get("balena_ready"))

        if mode == self.MODE_MC_FUSION:
            mc_fusion_status = status.get("mc_fusion_status") or {}

            installed = bool(mc_fusion_status.get("installed"))
            up_to_date = mc_fusion_status.get("up_to_date")
            local_name = mc_fusion_status.get("local_name")
            latest_name = mc_fusion_status.get("latest_name")
            update_available = bool(mc_fusion_status.get("update_available"))

            if not installed:
                self._set_not_downloaded_status(self.image_status_label)
                self.download_image_button.setText("Download MC-Fusion")
                self.download_image_button.setEnabled(
                    is_flash_supported() and self.current_worker is None
                )
                self.remove_image_button.setEnabled(False)
            else:
                if update_available:
                    label_text = "Update available"
                    if local_name and latest_name:
                        label_text = f"Update available ({local_name} -> {latest_name})"
                    elif latest_name:
                        label_text = f"Update available ({latest_name})"

                    self._set_warning_status(self.image_status_label, label_text)
                    self.download_image_button.setText("Update")
                    self.download_image_button.setEnabled(
                        is_flash_supported() and self.current_worker is None
                    )
                    self.remove_image_button.setEnabled(
                        is_flash_supported() and self.current_worker is None
                    )
                else:
                    ready_text = f"Ready ({local_name})" if local_name else "Ready"

                    if up_to_date is False:
                        self._set_warning_status(self.image_status_label, ready_text)
                    else:
                        self._set_ready_status(self.image_status_label, ready_text)

                    self.download_image_button.setText("Download MC-Fusion")
                    self.download_image_button.setEnabled(False)
                    self.remove_image_button.setEnabled(
                        is_flash_supported() and self.current_worker is None
                    )

        elif mode == self.MODE_MR_FUSION:
            installed = bool(status.get("mr_fusion_installed"))
            name = status.get("mr_fusion_name", "")

            if installed:
                ready_text = f"Ready ({name})" if name else "Ready"
                self._set_ready_status(self.image_status_label, ready_text)
                self.download_image_button.setText("Download Mr. Fusion")
                self.download_image_button.setEnabled(False)
                self.remove_image_button.setEnabled(
                    is_flash_supported() and self.current_worker is None
                )
            else:
                self._set_not_downloaded_status(self.image_status_label)
                self.download_image_button.setText("Download Mr. Fusion")
                self.download_image_button.setEnabled(
                    is_flash_supported() and self.current_worker is None
                )
                self.remove_image_button.setEnabled(False)

        if balena_ready:
            self._set_ready_status(self.balena_status_label)
            self.download_balena_button.setEnabled(False)
            self.remove_balena_button.setEnabled(
                is_flash_supported() and self.current_worker is None
            )
        else:
            self._set_not_downloaded_status(self.balena_status_label)
            self.download_balena_button.setEnabled(
                is_flash_supported() and self.current_worker is None
            )
            self.remove_balena_button.setEnabled(False)

        self.update_connection_state(lightweight=True)

    def selected_image_ready(self):
        if self.is_mc_fusion_mode():
            cached = self._cached_status(self.MODE_MC_FUSION)
            if cached is not None:
                mc_fusion_status = cached.get("mc_fusion_status") or {}
                return bool(mc_fusion_status.get("installed"))
            return has_mc_fusion_image()

        if self.is_mr_fusion_mode():
            cached = self._cached_status(self.MODE_MR_FUSION)
            if cached is not None:
                return bool(cached.get("mr_fusion_installed"))
            return has_mr_fusion_image()

        return False

    def get_selected_image_path(self):
        if self.is_mc_fusion_mode():
            return get_mc_fusion_image()
        return get_mr_fusion_image()

    def get_selected_image_name(self):
        if self.is_mc_fusion_mode():
            return "MC-Fusion"
        return "Mr. Fusion"

    def update_connection_state(self, lightweight=True):
        if not is_flash_supported():
            self.apply_unsupported_state()
            return

        if self.current_worker is not None:
            return

        if not lightweight:
            self.refresh_status(force=True)

        self.refresh_drives_button.setEnabled(True)
        self.drive_combo.setEnabled(True)
        self.mode_combo.setEnabled(True)

        can_flash = (
            bool(self.get_selected_drive())
            and self.selected_image_ready()
            and self.balena_ready_cached()
        )
        self.flash_button.setEnabled(can_flash)

    def balena_ready_cached(self):
        mode = self.current_mode()
        cached = self._cached_status(mode)

        if cached is not None:
            return bool(cached.get("balena_ready"))

        return has_balena_cli()

    def on_mode_changed(self):
        self.update_mode_ui()

        mode = self.current_mode()
        cached_status = self._cached_status(mode)

        if cached_status:
            self.apply_status_result(cached_status)
        else:
            self.show_refreshing_state()

        self.refresh_status()
        self.update_connection_state(lightweight=True)

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

        self.invalidate_status_cache()
        self.update_connection_state(lightweight=True)
        QTimer.singleShot(0, lambda: self.refresh_status(force=True))

    def invalidate_status_cache(self):
        self.status_cache.clear()

    def invalidate_current_status_cache(self):
        self.status_cache.pop(self.current_mode(), None)

    def show_flash_complete_dialog(self):
        QMessageBox.information(
            self,
            "Flash Complete",
            (
                "Flash complete.\n\n"
                "MiSTer Companion has attempted to safely eject the SD card. "
                "Check the log before removing the card if you want to confirm the eject result.\n\n"
                "Please continue the automated installation process by inserting the SD card "
                "into your MiSTer before using any other MiSTer Companion features for this SD card."
            ),
        )

    def on_task_success(self, message):
        if message:
            self.append_log(message)

        if message == self.SUCCESS_FLASH_COMPLETE:
            self.show_flash_complete_dialog()

    def on_task_error(self, message):
        self.append_log(message)
        QMessageBox.critical(self, "Error", message)

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
            self.drive_combo.addItem("No drives found")
            self.flash_button.setEnabled(False)
            return

        for drive in drives:
            device = str(drive.get("device", "")).strip()
            display_text = str(drive.get("display_name", "")).strip() or device or "Unknown drive"

            self.drive_combo.addItem(display_text)
            self.drive_map[display_text] = device

        self.update_connection_state(lightweight=True)

    def get_selected_drive(self):
        text = self.drive_combo.currentText().strip()
        return self.drive_map.get(text, "")

    def download_selected_image(self):
        if self.is_mc_fusion_mode():
            self.download_mc_fusion()
        else:
            self.download_mr_fusion()

    def download_mc_fusion(self):
        def task(log):
            ensure_mc_fusion_image(force_download=True, log_callback=log)

        button_text = self.download_image_button.text().strip().lower()
        success_message = (
            "MC-Fusion image update complete."
            if button_text == "update"
            else "MC-Fusion image download complete."
        )
        self.start_worker(task, success_message=success_message)

    def download_mr_fusion(self):
        def task(log):
            ensure_mr_fusion_image(force_download=True, log_callback=log)

        self.start_worker(task, success_message="Mr. Fusion download complete.")

    def download_balena(self):
        def task(log):
            ensure_balena_cli(force_download=True, log_callback=log)

        self.start_worker(task, success_message="balena CLI download complete.")

    def remove_selected_image(self):
        if self.is_mc_fusion_mode():
            title = "Remove MC-Fusion"
            text = (
                "This will remove the downloaded MC-Fusion image files from the tools folder.\n\n"
                "Do you want to continue?"
            )
        elif self.is_mr_fusion_mode():
            title = "Remove Mr. Fusion"
            text = (
                "This will remove the downloaded Mr. Fusion image files from the tools folder.\n\n"
                "Do you want to continue?"
            )

        confirm = QMessageBox.question(self, title, text)
        if confirm != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            if self.is_mc_fusion_mode():
                remove_mc_fusion_image(log_callback=log)
            else:
                remove_mr_fusion_image(log_callback=log)

        if self.is_mc_fusion_mode():
            success_message = "MC-Fusion files removed."
        else:
            success_message = "Mr. Fusion files removed."
        self.start_worker(task, success_message=success_message)

    def remove_balena(self):
        confirm = QMessageBox.question(
            self,
            "Remove balena CLI",
            "This will remove the downloaded balena CLI files from the tools folder.\n\nDo you want to continue?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            remove_balena_cli(log_callback=log)

        self.start_worker(task, success_message="balena CLI files removed.")

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

        if not self.selected_image_ready():
            QMessageBox.warning(
                self,
                f"{self.get_selected_image_name()} missing",
                f"Download the latest {self.get_selected_image_name()} first.",
            )
            return

        if not self.balena_ready_cached():
            QMessageBox.warning(
                self,
                "balena CLI missing",
                "Download balena CLI first.",
            )
            return

        try:
            image_path = self.get_selected_image_path()
        except Exception:
            QMessageBox.warning(
                self,
                f"{self.get_selected_image_name()} missing",
                f"Download the latest {self.get_selected_image_name()} first.",
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

        if platform.system() == "Darwin":
            from PyQt6.QtWidgets import QInputDialog, QLineEdit

            password, ok = QInputDialog.getText(
                self,
                "Administrator Password Required",
                "Enter your password to flash the SD card:",
                QLineEdit.EchoMode.Password,
            )
            if not ok or not password:
                return
        else:
            password = None

        def task(log):
            flash_image(image_path, drive, log_callback=log, password=password)

        self.start_worker(task, success_message=self.SUCCESS_FLASH_COMPLETE)
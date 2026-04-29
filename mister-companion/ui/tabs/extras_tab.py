import traceback

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.extras_actions import (
    get_3sx_status,
    get_pico8_status,
    get_sonic_mania_status,
    install_or_update_3sx as backend_install_or_update_3sx,
    install_or_update_pico8 as backend_install_or_update_pico8,
    install_or_update_sonic_mania as backend_install_or_update_sonic_mania,
    uninstall_3sx as backend_uninstall_3sx,
    uninstall_pico8 as backend_uninstall_pico8,
    uninstall_sonic_mania as backend_uninstall_sonic_mania,
    upload_3sx_afs as backend_upload_3sx_afs,
    upload_sonic_mania_data_rsdk as backend_upload_sonic_mania_data_rsdk,
)
from core.language import tr


class ExtraTaskWorker(QThread):
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


class ExtrasTab(QWidget):
    EXTRA_3SX = "3sx_mister"
    EXTRA_PICO8 = "mister_pico8"
    EXTRA_SONIC_MANIA = "sonic_mania_mister"

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection

        self.console_visible = False
        self.current_worker = None

        self.extra_display_order = [
            self.EXTRA_3SX,
            self.EXTRA_PICO8,
            self.EXTRA_SONIC_MANIA,
        ]

        self.extra_titles = {
            self.EXTRA_3SX: "3S-ARM",
            self.EXTRA_PICO8: "MiSTer Pico-8",
            self.EXTRA_SONIC_MANIA: "Sonic Mania MiSTer",
        }

        self.extra_descriptions = {
            self.EXTRA_3SX: tr("extras_tab.description_3sx"),
            self.EXTRA_PICO8: tr("extras_tab.description_pico8"),
            self.EXTRA_SONIC_MANIA: tr("extras_tab.description_sonic_mania"),
        }

        self.extra_status_texts = {
            self.EXTRA_3SX: tr("extras_tab.status_unknown"),
            self.EXTRA_PICO8: tr("extras_tab.status_unknown"),
            self.EXTRA_SONIC_MANIA: tr("extras_tab.status_unknown"),
        }

        self.selected_extra_key = self.EXTRA_3SX

        self.build_ui()
        self.apply_disconnected_state()

    def build_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        self.setLayout(main_layout)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        main_layout.addLayout(top_row, stretch=1)

        list_group = QGroupBox(tr("extras_tab.extras"))
        list_layout = QVBoxLayout()
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)

        self.extra_list = QListWidget()
        self.extra_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.extra_list.setAlternatingRowColors(False)
        self.extra_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.extra_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.extra_list.setMinimumWidth(290)
        self.extra_list.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.extra_list.setStyleSheet(
            """
            QListWidget {
                border: 1px solid palette(mid);
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget::item {
                border-radius: 6px;
                padding: 8px 10px;
                margin: 2px 0px;
            }
            QListWidget::item:selected {
                background-color: palette(highlight);
                color: palette(highlighted-text);
                border-left: 4px solid #7c4dff;
            }
            """
        )
        list_layout.addWidget(self.extra_list)

        list_group.setLayout(list_layout)
        top_row.addWidget(list_group, 1)

        details_group = QGroupBox(tr("extras_tab.details"))
        details_layout = QVBoxLayout()
        details_layout.setContentsMargins(14, 14, 14, 14)
        details_layout.setSpacing(10)

        self.extra_name_label = QLabel(tr("extras_tab.select_extra"))
        font = self.extra_name_label.font()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        self.extra_name_label.setFont(font)
        details_layout.addWidget(self.extra_name_label)

        self.extra_status_label = QLabel(tr("extras_tab.status_unknown_full"))
        self.extra_status_label.setStyleSheet("color: gray;")
        details_layout.addWidget(self.extra_status_label)

        self.extra_description_label = QLabel("")
        self.extra_description_label.setWordWrap(True)
        self.extra_description_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.extra_description_label.setMinimumHeight(54)
        details_layout.addWidget(self.extra_description_label)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        details_layout.addWidget(divider)

        self.action_buttons_container = QWidget()
        self.action_buttons_layout = QVBoxLayout()
        self.action_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.action_buttons_layout.setSpacing(10)
        self.action_buttons_container.setLayout(self.action_buttons_layout)
        details_layout.addWidget(self.action_buttons_container)

        self.threesx_actions_widget = self._build_3sx_actions()
        self.pico8_actions_widget = self._build_pico8_actions()
        self.sonic_mania_actions_widget = self._build_sonic_mania_actions()

        self.extra_action_widgets = {
            self.EXTRA_3SX: self.threesx_actions_widget,
            self.EXTRA_PICO8: self.pico8_actions_widget,
            self.EXTRA_SONIC_MANIA: self.sonic_mania_actions_widget,
        }

        for widget in self.extra_action_widgets.values():
            widget.hide()
            self.action_buttons_layout.addWidget(widget)

        self.action_buttons_layout.addStretch()

        details_group.setLayout(details_layout)
        top_row.addWidget(details_group, 2)

        self.console_group = QGroupBox(tr("extras_tab.ssh_output"))
        console_layout = QVBoxLayout()
        console_layout.setContentsMargins(10, 10, 10, 10)
        console_layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.addStretch()

        self.hide_console_button = QPushButton(tr("extras_tab.hide"))
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

        self._populate_extra_list()
        self._select_initial_extra()

        self.extra_list.currentItemChanged.connect(self.on_extra_selection_changed)
        self.install_update_3sx_button.clicked.connect(self.install_or_update_3sx)
        self.upload_afs_button.clicked.connect(self.upload_sf33rd_afs)
        self.uninstall_3sx_button.clicked.connect(self.uninstall_3sx)
        self.install_update_pico8_button.clicked.connect(self.install_or_update_pico8)
        self.uninstall_pico8_button.clicked.connect(self.uninstall_pico8)
        self.install_update_sonic_mania_button.clicked.connect(
            self.install_or_update_sonic_mania
        )
        self.upload_data_rsdk_button.clicked.connect(self.upload_sonic_mania_data_rsdk)
        self.uninstall_sonic_mania_button.clicked.connect(self.uninstall_sonic_mania)
        self.hide_console_button.clicked.connect(self.toggle_console)

    def _build_button_row(self, *buttons):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch()
        for button in buttons:
            row.addWidget(button)
        row.addStretch()
        return row

    def _build_3sx_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_update_3sx_button = QPushButton(tr("extras_tab.install"))
        self.install_update_3sx_button.setFixedWidth(170)

        self.upload_afs_button = QPushButton(tr("extras_tab.upload_sf33rd_afs"))
        self.upload_afs_button.setFixedWidth(190)

        self.uninstall_3sx_button = QPushButton(tr("extras_tab.uninstall"))
        self.uninstall_3sx_button.setFixedWidth(170)

        layout.addLayout(
            self._build_button_row(
                self.install_update_3sx_button,
                self.upload_afs_button,
            )
        )
        layout.addLayout(
            self._build_button_row(
                self.uninstall_3sx_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_pico8_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_update_pico8_button = QPushButton(tr("extras_tab.install"))
        self.install_update_pico8_button.setFixedWidth(170)

        self.uninstall_pico8_button = QPushButton(tr("extras_tab.uninstall"))
        self.uninstall_pico8_button.setFixedWidth(170)

        layout.addLayout(
            self._build_button_row(
                self.install_update_pico8_button,
                self.uninstall_pico8_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_sonic_mania_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_update_sonic_mania_button = QPushButton(tr("extras_tab.install"))
        self.install_update_sonic_mania_button.setFixedWidth(170)

        self.upload_data_rsdk_button = QPushButton(tr("extras_tab.upload_data_rsdk"))
        self.upload_data_rsdk_button.setFixedWidth(190)

        self.uninstall_sonic_mania_button = QPushButton(tr("extras_tab.uninstall"))
        self.uninstall_sonic_mania_button.setFixedWidth(170)

        layout.addLayout(
            self._build_button_row(
                self.install_update_sonic_mania_button,
                self.upload_data_rsdk_button,
            )
        )
        layout.addLayout(
            self._build_button_row(
                self.uninstall_sonic_mania_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _populate_extra_list(self):
        self.extra_list.clear()
        for extra_key in self.extra_display_order:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, extra_key)
            self.extra_list.addItem(item)
        self.update_extra_list_labels()

    def _select_initial_extra(self):
        if self.extra_list.count() > 0:
            self.extra_list.setCurrentRow(0)

    def _get_current_extra_key(self):
        item = self.extra_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def on_extra_selection_changed(self, current, previous):
        del previous
        if current is None:
            return

        extra_key = current.data(Qt.ItemDataRole.UserRole)
        self.selected_extra_key = extra_key
        self.update_details_panel()

    def update_details_panel(self):
        extra_key = self.selected_extra_key
        if not extra_key:
            self.extra_name_label.setText(tr("extras_tab.select_extra"))
            self.extra_status_label.setText(tr("extras_tab.status_unknown_full"))
            self.extra_status_label.setStyleSheet("color: gray;")
            self.extra_description_label.setText("")
            for widget in self.extra_action_widgets.values():
                widget.hide()
            return

        self.extra_name_label.setText(self.extra_titles.get(extra_key, extra_key))
        self.extra_description_label.setText(self.extra_descriptions.get(extra_key, ""))

        status_text = self.extra_status_texts.get(extra_key, tr("extras_tab.status_unknown"))
        self.extra_status_label.setText(tr("extras_tab.status_label", status=status_text))

        lowered = status_text.lower()
        if "update available" in lowered:
            self.extra_status_label.setStyleSheet("color: #cc8400;")
        elif "legacy" in lowered or "missing" in lowered:
            self.extra_status_label.setStyleSheet("color: #cc8400;")
        elif "installed" in lowered and "not" not in lowered:
            self.extra_status_label.setStyleSheet("color: #00aa00;")
        elif "not installed" in lowered:
            self.extra_status_label.setStyleSheet("color: #cc0000;")
        else:
            self.extra_status_label.setStyleSheet("color: gray;")

        for key, widget in self.extra_action_widgets.items():
            widget.setVisible(key == extra_key)

    def update_extra_list_labels(self):
        for index in range(self.extra_list.count()):
            item = self.extra_list.item(index)
            extra_key = item.data(Qt.ItemDataRole.UserRole)
            title = self.extra_titles.get(extra_key, extra_key)
            status = self.extra_status_texts.get(extra_key, tr("extras_tab.status_unknown"))
            item.setText(f"{title}    {status}")

    def update_connection_state(self):
        if self.connection.is_connected():
            self.apply_connected_state()
        else:
            self.apply_disconnected_state()

    def apply_connected_state(self):
        if self.current_worker is not None and self.current_worker.isRunning():
            return
        self.refresh_status()

    def apply_disconnected_state(self):
        for button in [
            self.install_update_3sx_button,
            self.upload_afs_button,
            self.uninstall_3sx_button,
            self.install_update_pico8_button,
            self.uninstall_pico8_button,
            self.install_update_sonic_mania_button,
            self.upload_data_rsdk_button,
            self.uninstall_sonic_mania_button,
        ]:
            button.setEnabled(False)

        self.install_update_3sx_button.setText(tr("extras_tab.install"))
        self.install_update_pico8_button.setText(tr("extras_tab.install"))
        self.install_update_sonic_mania_button.setText(tr("extras_tab.install"))

        self.extra_status_texts[self.EXTRA_3SX] = tr("extras_tab.status_unknown")
        self.extra_status_texts[self.EXTRA_PICO8] = tr("extras_tab.status_unknown")
        self.extra_status_texts[self.EXTRA_SONIC_MANIA] = tr("extras_tab.status_unknown")

        self.update_extra_list_labels()
        self.update_details_panel()

    def refresh_status(self):
        if not self.connection.is_connected():
            self.apply_disconnected_state()
            return

        try:
            status_3sx = get_3sx_status(self.connection)
        except Exception as e:
            self.extra_status_texts[self.EXTRA_3SX] = tr("extras_tab.status_unknown_with_error", error=e)
            self.install_update_3sx_button.setText(tr("extras_tab.install"))
            self.install_update_3sx_button.setEnabled(False)
            self.upload_afs_button.setEnabled(False)
            self.uninstall_3sx_button.setEnabled(False)
        else:
            self.extra_status_texts[self.EXTRA_3SX] = status_3sx["status_text"]
            self.install_update_3sx_button.setText(status_3sx["install_label"])
            self.install_update_3sx_button.setEnabled(status_3sx["install_enabled"])
            self.upload_afs_button.setEnabled(status_3sx["upload_enabled"])
            self.uninstall_3sx_button.setEnabled(status_3sx["uninstall_enabled"])

        try:
            status_pico8 = get_pico8_status(self.connection)
        except Exception as e:
            self.extra_status_texts[self.EXTRA_PICO8] = tr("extras_tab.status_unknown_with_error", error=e)
            self.install_update_pico8_button.setText(tr("extras_tab.install"))
            self.install_update_pico8_button.setEnabled(False)
            self.uninstall_pico8_button.setEnabled(False)
        else:
            self.extra_status_texts[self.EXTRA_PICO8] = status_pico8["status_text"]
            self.install_update_pico8_button.setText(status_pico8["install_label"])
            self.install_update_pico8_button.setEnabled(status_pico8["install_enabled"])
            self.uninstall_pico8_button.setEnabled(status_pico8["uninstall_enabled"])

        try:
            status_sonic_mania = get_sonic_mania_status(self.connection)
        except Exception as e:
            self.extra_status_texts[self.EXTRA_SONIC_MANIA] = tr("extras_tab.status_unknown_with_error", error=e)
            self.install_update_sonic_mania_button.setText(tr("extras_tab.install"))
            self.install_update_sonic_mania_button.setEnabled(False)
            self.upload_data_rsdk_button.setEnabled(False)
            self.uninstall_sonic_mania_button.setEnabled(False)
        else:
            self.extra_status_texts[self.EXTRA_SONIC_MANIA] = status_sonic_mania[
                "status_text"
            ]
            self.install_update_sonic_mania_button.setText(
                status_sonic_mania["install_label"]
            )
            self.install_update_sonic_mania_button.setEnabled(
                status_sonic_mania["install_enabled"]
            )
            self.upload_data_rsdk_button.setEnabled(
                status_sonic_mania["upload_enabled"]
            )
            self.uninstall_sonic_mania_button.setEnabled(
                status_sonic_mania["uninstall_enabled"]
            )

        self.update_extra_list_labels()
        self.update_details_panel()

    def append_console_line(self, text):
        if text.startswith("[PROGRESS] "):
            progress_text = text[len("[PROGRESS] "):]

            lines = self.console.toPlainText().splitlines()

            if lines:
                if lines[-1].startswith(tr("extras_tab.upload_progress_prefix")):
                    lines[-1] = tr("extras_tab.upload_progress", progress=progress_text)
                else:
                    lines.append(tr("extras_tab.upload_progress", progress=progress_text))
            else:
                lines = [tr("extras_tab.upload_progress", progress=progress_text)]

            self.console.setPlainText("\n".join(lines))
        else:
            self.console.append(text)

        self.console.ensureCursorVisible()

    def show_console(self):
        if not self.console_visible:
            self.console_group.show()
            self.console_visible = True

    def hide_console(self):
        if self.console_visible:
            self.console_group.hide()
            self.console_visible = False

    def toggle_console(self):
        if self.console_visible:
            self.hide_console()
        else:
            self.show_console()

    def _run_worker(self, task_fn, success_message=""):
        if self.current_worker is not None and self.current_worker.isRunning():
            return

        self.show_console()
        self.console.clear()

        self.current_worker = ExtraTaskWorker(task_fn, success_message)
        self.current_worker.log_line.connect(self.append_console_line)
        self.current_worker.success.connect(self.on_worker_success)
        self.current_worker.error.connect(self.on_worker_error)
        self.current_worker.finished_task.connect(self.on_worker_finished)
        self.current_worker.task_result.connect(self.on_worker_result)

        self.extra_list.setEnabled(False)

        self.install_update_3sx_button.setEnabled(False)
        self.upload_afs_button.setEnabled(False)
        self.uninstall_3sx_button.setEnabled(False)

        self.install_update_pico8_button.setEnabled(False)
        self.uninstall_pico8_button.setEnabled(False)

        self.install_update_sonic_mania_button.setEnabled(False)
        self.upload_data_rsdk_button.setEnabled(False)
        self.uninstall_sonic_mania_button.setEnabled(False)

        self.current_worker.start()

    def on_worker_success(self, message):
        if message:
            self.append_console_line("")
            self.append_console_line(message)

    def on_worker_error(self, message):
        self.append_console_line("")
        self.append_console_line(tr("extras_tab.error_label"))
        self.append_console_line(message)
        QMessageBox.warning(self, tr("extras_tab.extras"), message)

    def on_worker_finished(self):
        self.current_worker = None
        self.extra_list.setEnabled(True)
        self.refresh_status()

    def on_worker_result(self, result):
        del result

    def install_or_update_3sx(self):
        if not self.connection.is_connected():
            return

        button_text = self.install_update_3sx_button.text().strip()
        success_message = tr("extras_tab.threesx_installed")

        if button_text == tr("extras_tab.update"):
            success_message = tr("extras_tab.threesx_updated")
        elif button_text == tr("extras_tab.migrate_install"):
            success_message = tr("extras_tab.threesx_migrated")

        def task(log):
            return backend_install_or_update_3sx(self.connection, log)

        self._run_worker(task, success_message)

    def upload_sf33rd_afs(self):
        if not self.connection.is_connected():
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("extras_tab.select_sf33rd_afs"),
            "",
            tr("extras_tab.afs_file_filter"),
        )
        if not file_path:
            return

        def task(log):
            log(tr("extras_tab.selected_file", file_path=file_path))
            return backend_upload_3sx_afs(self.connection, file_path, log)

        self._run_worker(task, tr("extras_tab.sf33rd_uploaded"))

    def uninstall_3sx(self):
        if not self.connection.is_connected():
            return

        reply = QMessageBox.question(
            self,
            tr("extras_tab.uninstall_3sx_title"),
            tr("extras_tab.uninstall_3sx_message"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            return backend_uninstall_3sx(self.connection, log)

        self._run_worker(task, tr("extras_tab.threesx_uninstalled"))

    def install_or_update_pico8(self):
        if not self.connection.is_connected():
            return

        button_text = self.install_update_pico8_button.text().strip()
        success_message = tr("extras_tab.pico8_installed")

        if button_text == tr("extras_tab.update"):
            success_message = tr("extras_tab.pico8_updated")

        def task(log):
            return backend_install_or_update_pico8(self.connection, log)

        self._run_worker(task, success_message)

    def uninstall_pico8(self):
        if not self.connection.is_connected():
            return

        reply = QMessageBox.question(
            self,
            tr("extras_tab.uninstall_pico8_title"),
            tr("extras_tab.uninstall_pico8_message"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            return backend_uninstall_pico8(self.connection, log)

        self._run_worker(task, tr("extras_tab.pico8_uninstalled"))

    def install_or_update_sonic_mania(self):
        if not self.connection.is_connected():
            return

        button_text = self.install_update_sonic_mania_button.text().strip()
        success_message = tr("extras_tab.sonic_mania_installed")

        if button_text == tr("extras_tab.update"):
            success_message = tr("extras_tab.sonic_mania_updated")

        def task(log):
            return backend_install_or_update_sonic_mania(self.connection, log)

        self._run_worker(task, success_message)

    def upload_sonic_mania_data_rsdk(self):
        if not self.connection.is_connected():
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("extras_tab.select_data_rsdk"),
            "",
            tr("extras_tab.rsdk_file_filter"),
        )
        if not file_path:
            return

        def task(log):
            log(tr("extras_tab.selected_file", file_path=file_path))
            return backend_upload_sonic_mania_data_rsdk(
                self.connection,
                file_path,
                log,
            )

        self._run_worker(task, tr("extras_tab.data_rsdk_uploaded"))

    def uninstall_sonic_mania(self):
        if not self.connection.is_connected():
            return

        reply = QMessageBox.question(
            self,
            tr("extras_tab.uninstall_sonic_mania_title"),
            tr("extras_tab.uninstall_sonic_mania_message"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            return backend_uninstall_sonic_mania(self.connection, log)

        self._run_worker(task, tr("extras_tab.sonic_mania_uninstalled"))
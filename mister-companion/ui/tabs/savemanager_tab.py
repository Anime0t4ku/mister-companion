from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.language import tr
from core.savemanager import (
    SYNC_ROOT,
    create_backup,
    ensure_remote_save_dirs,
    ensure_savemanager_dirs,
    get_backup_count,
    get_device_backup_root,
    list_backups_for_device,
    open_folder,
    restore_backup,
    save_retention_setting,
    sync_saves,
)


class SaveManagerWorker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool, str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.fn(self.log.emit)
            self.done.emit(True, "")
        except Exception as e:
            self.done.emit(False, str(e))


class RestoreBackupDialog(QDialog):
    def __init__(self, backups, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("savemanager_tab.restore_backup_title"))
        self.setMinimumSize(520, 360)

        layout = QVBoxLayout(self)

        info = QLabel(tr("savemanager_tab.select_backup_to_restore"))
        layout.addWidget(info)

        self.list_widget = QListWidget()
        self.list_widget.addItems(backups)
        if backups:
            self.list_widget.setCurrentRow(0)
        layout.addWidget(self.list_widget)

        self.backup_before_restore_checkbox = QCheckBox(
            tr("savemanager_tab.backup_before_restore")
        )
        self.backup_before_restore_checkbox.setChecked(True)
        layout.addWidget(self.backup_before_restore_checkbox)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.restore_button = QPushButton(tr("savemanager_tab.restore"))
        self.cancel_button = QPushButton(tr("common.cancel"))

        button_row.addWidget(self.restore_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        self.restore_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def selected_backup(self):
        item = self.list_widget.currentItem()
        return item.text().strip() if item else ""

    def backup_before_restore(self):
        return self.backup_before_restore_checkbox.isChecked()


class SyncConfirmDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("savemanager_tab.sync_saves_title"))
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        info = QLabel(tr("savemanager_tab.sync_info"))
        info.setWordWrap(True)
        layout.addWidget(info)

        self.backup_checkbox = QCheckBox(tr("savemanager_tab.backup_before_sync"))
        self.backup_checkbox.setChecked(True)
        layout.addWidget(self.backup_checkbox)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.sync_button = QPushButton(tr("savemanager_tab.sync"))
        self.cancel_button = QPushButton(tr("common.cancel"))

        button_row.addWidget(self.sync_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        self.sync_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def backup_before_sync(self):
        return self.backup_checkbox.isChecked()


class SaveManagerTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection
        self.worker = None

        ensure_savemanager_dirs()
        self.build_ui()
        self.update_connection_state()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        main_group = QGroupBox(tr("savemanager_tab.title"))
        main_group_layout = QVBoxLayout(main_group)
        main_group_layout.setContentsMargins(12, 12, 12, 12)
        main_group_layout.setSpacing(12)

        self.info_label = QLabel(tr("savemanager_tab.info"))
        self.info_label.setWordWrap(True)
        self.info_label.setMaximumWidth(520)
        self.info_label.setAlignment(pyqt_alignment_center())

        info_row = QHBoxLayout()
        info_row.addStretch()
        info_row.addWidget(self.info_label)
        info_row.addStretch()
        main_group_layout.addLayout(info_row)

        button_row = QHBoxLayout()
        button_row.setSpacing(12)

        self.backup_button = QPushButton(tr("savemanager_tab.backup_saves"))
        self.restore_button = QPushButton(tr("savemanager_tab.restore_backup"))
        self.sync_button = QPushButton(tr("savemanager_tab.sync_saves"))

        self.backup_button.setFixedWidth(115)
        self.restore_button.setFixedWidth(115)
        self.sync_button.setFixedWidth(115)

        button_row.addStretch()
        button_row.addWidget(self.backup_button)
        button_row.addWidget(self.restore_button)
        button_row.addWidget(self.sync_button)
        button_row.addStretch()
        main_group_layout.addLayout(button_row)

        self.backup_count_label = QLabel(
            tr("savemanager_tab.current_backups", count=0)
        )
        self.backup_count_label.setAlignment(pyqt_alignment_center())

        backup_count_row = QHBoxLayout()
        backup_count_row.addStretch()
        backup_count_row.addWidget(self.backup_count_label)
        backup_count_row.addStretch()
        main_group_layout.addLayout(backup_count_row)

        retention_row = QHBoxLayout()
        retention_row.setSpacing(8)

        self.retention_label = QLabel(tr("savemanager_tab.backups_to_keep"))
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 100)
        self.retention_spin.setFixedWidth(80)
        self.retention_spin.setValue(int(self.main_window.config_data.get("backup_retention", 10)))
        self.retention_spin.valueChanged.connect(self.on_retention_changed)

        retention_row.addStretch()
        retention_row.addWidget(self.retention_label)
        retention_row.addWidget(self.retention_spin)
        retention_row.addStretch()
        main_group_layout.addLayout(retention_row)

        main_layout.addWidget(main_group)

        folder_group = QGroupBox(tr("savemanager_tab.folders"))
        folder_group_layout = QVBoxLayout(folder_group)
        folder_group_layout.setContentsMargins(12, 12, 12, 12)
        folder_group_layout.setSpacing(12)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(12)

        self.open_backup_folder_button = QPushButton(tr("savemanager_tab.browse_backups"))
        self.open_sync_folder_button = QPushButton(tr("savemanager_tab.browse_sync_folder"))

        self.open_backup_folder_button.setFixedWidth(115)
        self.open_sync_folder_button.setFixedWidth(132)

        folder_row.addStretch()
        folder_row.addWidget(self.open_backup_folder_button)
        folder_row.addWidget(self.open_sync_folder_button)
        folder_row.addStretch()
        folder_group_layout.addLayout(folder_row)

        main_layout.addWidget(folder_group)

        self.log_group = QGroupBox(tr("savemanager_tab.log"))
        log_group_layout = QVBoxLayout(self.log_group)
        log_group_layout.setContentsMargins(12, 12, 12, 12)
        log_group_layout.setSpacing(8)

        log_header_row = QHBoxLayout()
        log_header_row.addStretch()
        self.hide_log_button = QPushButton(tr("savemanager_tab.hide"))
        self.hide_log_button.setFixedWidth(80)
        log_header_row.addWidget(self.hide_log_button)
        log_group_layout.addLayout(log_header_row)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(180)
        self.log_output.setMinimumWidth(750)
        log_group_layout.addWidget(self.log_output)

        main_layout.addWidget(self.log_group)
        self.log_group.hide()

        main_layout.addStretch()

        self.backup_button.clicked.connect(self.backup_saves)
        self.restore_button.clicked.connect(self.restore_saves)
        self.sync_button.clicked.connect(self.sync_saves_action)
        self.open_backup_folder_button.clicked.connect(self.open_backup_folder)
        self.open_sync_folder_button.clicked.connect(self.open_sync_folder)
        self.hide_log_button.clicked.connect(self.hide_log)

    def get_current_profile_name(self):
        if hasattr(self.main_window.connection_tab, "get_selected_profile_name"):
            return self.main_window.connection_tab.get_selected_profile_name()
        return ""

    def get_current_ip(self):
        return getattr(self.connection, "host", "") or ""

    def update_backup_count(self):
        count = get_backup_count(
            profile_name=self.get_current_profile_name(),
            ip_address=self.get_current_ip(),
        )
        self.backup_count_label.setText(
            tr("savemanager_tab.current_backups", count=count)
        )

    def update_connection_state(self):
        connected = self.connection.is_connected()

        if connected and self.isVisible():
            try:
                ensure_remote_save_dirs(self.connection)
            except Exception as e:
                QMessageBox.warning(
                    self,
                    tr("savemanager_tab.title"),
                    tr("savemanager_tab.prepare_save_folders_failed", error=e),
                )
                connected = False

        self.backup_button.setEnabled(connected)
        self.restore_button.setEnabled(connected)
        self.sync_button.setEnabled(connected)
        self.retention_spin.setEnabled(connected)
        self.open_backup_folder_button.setEnabled(connected)
        self.open_sync_folder_button.setEnabled(connected)

        self.update_backup_count()

    def on_retention_changed(self, value):
        value = save_retention_setting(self.main_window.config_data, value)
        self.retention_spin.blockSignals(True)
        self.retention_spin.setValue(value)
        self.retention_spin.blockSignals(False)

    def show_log(self):
        if not self.log_group.isVisible():
            self.log_group.show()

    def hide_log(self):
        if self.hide_log_button.isEnabled():
            self.log_group.hide()

    def clear_log(self):
        self.log_output.clear()

    def log_message(self, text):
        self.log_output.append(text)

    def set_busy(self, busy: bool):
        enabled = not busy and self.connection.is_connected()
        self.backup_button.setEnabled(enabled)
        self.restore_button.setEnabled(enabled)
        self.sync_button.setEnabled(enabled)
        self.retention_spin.setEnabled(enabled)
        self.open_backup_folder_button.setEnabled(enabled)
        self.open_sync_folder_button.setEnabled(enabled)
        self.hide_log_button.setEnabled(not busy)

    def start_worker(self, fn):
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.warning(
                self,
                tr("savemanager_tab.busy_title"),
                tr("savemanager_tab.task_already_running"),
            )
            return

        self.show_log()
        self.clear_log()
        self.set_busy(True)

        self.worker = SaveManagerWorker(fn)
        self.worker.log.connect(self.log_message)
        self.worker.done.connect(self.on_worker_done)
        self.worker.start()

    def on_worker_done(self, ok: bool, error_message: str):
        self.set_busy(False)
        self.worker = None
        self.update_backup_count()

        if not ok:
            self.log_message(
                tr("savemanager_tab.operation_failed", error=error_message)
            )
            QMessageBox.warning(self, tr("savemanager_tab.title"), error_message)

    def backup_saves(self):
        if not self.connection.is_connected():
            QMessageBox.warning(
                self,
                tr("common.error"),
                tr("device_tab.not_connected_message"),
            )
            return

        profile_name = self.get_current_profile_name()
        ip_address = self.get_current_ip()

        def task(log):
            create_backup(
                self.connection,
                self.main_window.config_data,
                profile_name=profile_name,
                ip_address=ip_address,
                log_callback=log,
            )

        self.start_worker(task)

    def restore_saves(self):
        if not self.connection.is_connected():
            QMessageBox.warning(
                self,
                tr("common.error"),
                tr("device_tab.not_connected_message"),
            )
            return

        profile_name = self.get_current_profile_name()
        ip_address = self.get_current_ip()

        backups = list_backups_for_device(profile_name=profile_name, ip_address=ip_address)
        if not backups:
            QMessageBox.warning(
                self,
                tr("savemanager_tab.restore_backup_title"),
                tr("savemanager_tab.no_backups_found"),
            )
            return

        dialog = RestoreBackupDialog(backups, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_backup = dialog.selected_backup()
        if not selected_backup:
            QMessageBox.warning(
                self,
                tr("savemanager_tab.restore_backup_title"),
                tr("savemanager_tab.select_backup_first"),
            )
            return

        backup_before_restore = dialog.backup_before_restore()

        def task(log):
            if backup_before_restore:
                log(tr("savemanager_tab.creating_safety_backup_before_restore"))
                create_backup(
                    self.connection,
                    self.main_window.config_data,
                    profile_name=profile_name,
                    ip_address=ip_address,
                    log_callback=log,
                )
            restore_backup(
                self.connection,
                selected_backup,
                profile_name=profile_name,
                ip_address=ip_address,
                log_callback=log,
            )

        self.start_worker(task)

    def sync_saves_action(self):
        if not self.connection.is_connected():
            QMessageBox.warning(
                self,
                tr("common.error"),
                tr("device_tab.not_connected_message"),
            )
            return

        dialog = SyncConfirmDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        backup_before_sync = dialog.backup_before_sync()
        profile_name = self.get_current_profile_name()
        ip_address = self.get_current_ip()

        def task(log):
            if backup_before_sync:
                log(tr("savemanager_tab.creating_safety_backup_before_sync"))
                create_backup(
                    self.connection,
                    self.main_window.config_data,
                    profile_name=profile_name,
                    ip_address=ip_address,
                    log_callback=log,
                )
            sync_saves(
                self.connection,
                log_callback=log,
            )

        self.start_worker(task)

    def open_backup_folder(self):
        profile_name = self.get_current_profile_name()
        ip_address = self.get_current_ip()

        target = get_device_backup_root(profile_name=profile_name, ip_address=ip_address)
        open_folder(target)

    def open_sync_folder(self):
        open_folder(SYNC_ROOT)


def pyqt_alignment_center():
    from PyQt6.QtCore import Qt
    return Qt.AlignmentFlag.AlignCenter
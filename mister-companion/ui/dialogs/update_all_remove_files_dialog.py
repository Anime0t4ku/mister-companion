from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
)

from core.downloader_backend import (
    DownloaderCommandError,
    DownloaderMissingDrivesError,
    remove_database_source_local,
    remove_database_source_online,
    uninstall_named_database_local,
    uninstall_named_database_online,
)
from core.update_all_config import (
    list_removable_update_all_databases,
    list_removable_update_all_databases_local,
)


class _RemoveDatabaseWorker(QThread):
    success = pyqtSignal()
    failed = pyqtSignal(object)

    def __init__(self, *, connection=None, sd_root=None, database_id="", force=False, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.sd_root = sd_root
        self.database_id = database_id
        self.force = force

    def run(self):
        try:
            if self.sd_root:
                ok = uninstall_named_database_local(
                    self.sd_root,
                    self.database_id,
                    force=self.force,
                )
                if not ok:
                    raise DownloaderCommandError(
                        "The installed Downloader is too old to uninstall databases.",
                        unsupported=True,
                    )
                remove_database_source_local(self.sd_root, self.database_id)
            else:
                ok = uninstall_named_database_online(
                    self.connection,
                    self.database_id,
                    force=self.force,
                )
                if not ok:
                    raise DownloaderCommandError(
                        "The installed Downloader is too old to uninstall databases.",
                        unsupported=True,
                    )
                remove_database_source_online(self.connection, self.database_id)
            self.success.emit()
        except Exception as exc:
            self.failed.emit(exc)


class UpdateAllRemoveFilesDialog(QDialog):
    def __init__(self, *, connection=None, sd_root=None, custom_sources=None, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.sd_root = sd_root
        self.custom_sources = list(custom_sources or [])
        self.worker = None
        self.progress = None
        self.pending_force_retry = None
        self.removed_database_ids = []

        self.setWindowTitle("Remove Installed Files")
        self.resize(620, 470)
        self.setMinimumSize(520, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)

        title = QLabel("Remove Installed Files")
        title.setStyleSheet("font-weight: 700; font-size: 18px;")
        layout.addWidget(title)

        info = QLabel(
            "Only databases currently present in this Update_All configuration are shown. "
            "Removing an entry uninstalls the files managed by that database and removes its INI entry."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self._update_remove_state)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.on_remove())
        layout.addWidget(self.list_widget, 1)

        self.empty_label = QLabel("No removable Update_All databases were found.")
        self.empty_label.setWordWrap(True)
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.remove_button = QPushButton("Remove")
        self.close_button = QPushButton("Close")
        buttons.addWidget(self.remove_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.remove_button.clicked.connect(self.on_remove)
        self.close_button.clicked.connect(self.accept)

        self.reload_entries()

    def reload_entries(self):
        self.list_widget.clear()
        try:
            if self.sd_root:
                entries = list_removable_update_all_databases_local(
                    self.sd_root,
                    self.custom_sources,
                )
            else:
                entries = list_removable_update_all_databases(
                    self.connection,
                    self.custom_sources,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Remove Installed Files", f"Could not read Update_All databases.\n\n{exc}")
            entries = []

        for entry in entries:
            item = QListWidgetItem(f"{entry['display_name']}\n{entry['database_id']}")
            item.setData(256, entry)
            self.list_widget.addItem(item)

        has_entries = self.list_widget.count() > 0
        self.list_widget.setVisible(has_entries)
        self.empty_label.setVisible(not has_entries)
        self._update_remove_state()

    def _update_remove_state(self):
        self.remove_button.setEnabled(bool(self.list_widget.currentItem()) and self.worker is None)

    def on_remove(self):
        item = self.list_widget.currentItem()
        if item is None or self.worker is not None:
            return
        entry = item.data(256) or {}
        database_id = str(entry.get("database_id") or "").strip()
        display_name = str(entry.get("display_name") or database_id).strip()
        if not database_id:
            return

        answer = QMessageBox.question(
            self,
            "Remove Installed Files",
            f"Remove the files installed by {display_name}?\n\n"
            "This will also remove the database from the Update_All INI configuration.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._start_remove(database_id, display_name, force=False)

    def _start_remove(self, database_id, display_name, *, force):
        self.setEnabled(False)
        self.progress = QProgressDialog(
            f"Removing {display_name}...",
            "",
            0,
            0,
            self,
        )
        self.progress.setWindowTitle("Remove Installed Files")
        self.progress.setCancelButton(None)
        self.progress.setMinimumDuration(0)
        self.progress.setAutoClose(False)
        self.progress.show()

        worker = _RemoveDatabaseWorker(
            connection=self.connection,
            sd_root=self.sd_root,
            database_id=database_id,
            force=force,
            parent=self,
        )
        self.worker = worker
        worker.success.connect(lambda: self._on_remove_success(display_name))
        worker.failed.connect(lambda exc: self._on_remove_failed(exc, database_id, display_name))
        worker.finished.connect(self._on_worker_finished)
        worker.start()

    def _finish_progress(self):
        if self.progress is not None:
            self.progress.close()
            self.progress.deleteLater()
            self.progress = None
        self.setEnabled(True)

    def _on_remove_success(self, display_name):
        self._finish_progress()
        if self.worker is not None and self.worker.database_id not in self.removed_database_ids:
            self.removed_database_ids.append(self.worker.database_id)
        QMessageBox.information(
            self,
            "Remove Installed Files",
            f"{display_name} was removed successfully.",
        )
        self.reload_entries()

    def _on_remove_failed(self, error, database_id, display_name):
        self._finish_progress()
        if isinstance(error, DownloaderMissingDrivesError):
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("External drive not connected")
            msg.setText(
                "Some files installed by this database are on a drive that is not currently connected."
            )
            msg.setInformativeText(
                "Reconnect the drive and retry to remove everything, or uninstall anyway to remove only "
                "the files available on currently connected storage."
            )
            if getattr(error, "output", ""):
                msg.setDetailedText(error.output)
            force_button = msg.addButton("Uninstall Anyway", QMessageBox.ButtonRole.DestructiveRole)
            msg.addButton("Cancel and Reconnect Drive", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            if msg.clickedButton() is force_button:
                self.pending_force_retry = (database_id, display_name)
            return

        if isinstance(error, DownloaderCommandError) and error.unsupported:
            QMessageBox.warning(
                self,
                "Downloader update required",
                "The installed Downloader does not support database uninstall. Run Update_All once to update Downloader, then try again.",
            )
            return

        details = getattr(error, "output", "")
        message = str(error)
        if details:
            message += f"\n\n{details}"
        QMessageBox.critical(self, "Remove Installed Files", message)

    def _on_worker_finished(self):
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()
        retry = self.pending_force_retry
        self.pending_force_retry = None
        if retry is not None:
            database_id, display_name = retry
            self._start_remove(database_id, display_name, force=True)
            return
        self._update_remove_state()

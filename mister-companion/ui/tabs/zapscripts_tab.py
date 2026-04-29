from datetime import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QLineEdit,
    QLabel,
    QProgressBar,
    QSplitter,
    QListWidgetItem,
    QMessageBox,
)

from core.config import load_config, save_config
from core.language import tr
from core.zapscripts import (
    fetch_all_media,
    list_scripts,
    launch_media,
    send_input_command,
    get_media_database_status,
    get_zapscripts_state,
)
from core.zaplauncher_db import get_db_path, load_db, save_db, get_last_scan_time
from ui.dialogs.zapscripts_controls_dialog import ZapScriptsControlsDialog
from ui.dialogs.zapscripts_scan_notice_dialog import ZapScriptsScanNoticeDialog


class ScanWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    aborted = pyqtSignal()

    def __init__(self, connection):
        super().__init__()
        self.connection = connection
        self._abort_requested = False

    def request_abort(self):
        self._abort_requested = True

    def run(self):
        try:
            def progress_cb(*args):
                if self._abort_requested:
                    raise RuntimeError("__SCAN_ABORTED__")

                if len(args) >= 2:
                    self.progress.emit(int(args[1]))
                elif args:
                    self.progress.emit(int(args[0]))

            data = fetch_all_media(self.connection, progress_cb)

            if self._abort_requested:
                self.aborted.emit()
                return

            self.finished.emit(data)
        except Exception as e:
            if str(e) == "__SCAN_ABORTED__":
                self.aborted.emit()
            else:
                self.error.emit(str(e))


class ZapScriptsTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        self.db_path = None
        self.entries = []
        self.filtered_entries = []
        self.worker = None
        self.expected_total = 0

        self._build_ui()
        self._load_db()

    @property
    def connection(self):
        return self.main_window.connection

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)

        self.scan_btn = QPushButton(tr("zapscripts_tab.scan"))
        self.scan_btn.clicked.connect(self._handle_scan_button)
        self.scan_btn.setFixedWidth(80)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)

        self.status = QLabel(tr("zapscripts_tab.no_library_found"))
        self.status.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        top.addWidget(self.scan_btn)
        top.addWidget(self.progress, 1)
        top.addWidget(self.status)

        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.systems = QListWidget()
        self.systems.addItems([tr("zapscripts_tab.all"), tr("zapscripts_tab.scripts")])
        self.systems.currentTextChanged.connect(self._filter)
        self.systems.setMinimumWidth(180)
        self.systems.setMaximumWidth(240)
        splitter.addWidget(self.systems)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("zapscripts_tab.search_placeholder"))
        self.search.textChanged.connect(self._filter)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self._launch())

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self.launch_btn = QPushButton(tr("zapscripts_tab.launch_selected"))
        self.launch_btn.clicked.connect(self._launch)

        self.controls_btn = QPushButton(tr("zapscripts_tab.controls"))
        self.controls_btn.clicked.connect(self._open_controls)

        buttons.addWidget(self.launch_btn)
        buttons.addWidget(self.controls_btn)

        right_layout.addWidget(self.search)
        right_layout.addWidget(self.list, 1)
        right_layout.addLayout(buttons)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 700])

        layout.addWidget(splitter, 1)

    def _handle_scan_button(self):
        if self.worker is not None:
            self.abort_scan()
        else:
            self.start_scan()

    def _should_show_scan_notice(self) -> bool:
        config = load_config()
        return not config.get("hide_zapscripts_scan_notice", False)

    def _set_scan_notice_hidden(self, hidden: bool):
        config = load_config()
        config["hide_zapscripts_scan_notice"] = hidden
        save_config(config)

    def _show_scan_notice_dialog(self) -> bool:
        if not self._should_show_scan_notice():
            return True

        dlg = ZapScriptsScanNoticeDialog(self)
        result = dlg.exec()

        if dlg.should_skip_next_time():
            self._set_scan_notice_hidden(True)

        return result == QDialog.DialogCode.Accepted

    def _get_profile_name_for_current_host(self):
        host = getattr(self.connection, "host", "") or ""
        if not host:
            return None

        devices = self.main_window.config_data.get("devices", [])
        for device in devices:
            if device.get("ip", "") == host:
                name = (device.get("name") or "").strip()
                return name or None

        return None

    def _get_db_path(self):
        host = getattr(self.connection, "host", "") or ""
        profile_name = self._get_profile_name_for_current_host()
        return get_db_path(profile_name, host) if host else None

    def _update_idle_status(self):
        if not self.connection.is_connected():
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.status.setText(tr("zapscripts_tab.no_library_found"))
            return

        try:
            state = get_zapscripts_state(self.connection)
        except Exception:
            state = None

        if state:
            if not state.get("zaparoo_installed", False):
                self.progress.setRange(0, 100)
                self.progress.setValue(0)
                self.status.setText(tr("zapscripts_tab.zaparoo_not_installed"))
                return

            if not state.get("zaparoo_service_enabled", False):
                self.progress.setRange(0, 100)
                self.progress.setValue(0)
                self.status.setText(tr("zapscripts_tab.zaparoo_service_not_enabled"))
                return

        ts = get_last_scan_time(self.db_path) if self.db_path else None
        self.progress.setRange(0, 100)
        if ts:
            dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            self.progress.setValue(100)
            self.status.setText(tr("zapscripts_tab.last_scan", datetime=dt))
        else:
            self.progress.setValue(0)
            self.status.setText(tr("zapscripts_tab.no_scan_run_yet"))

    def _load_db(self):
        self.db_path = self._get_db_path()

        if not self.db_path:
            self.entries = []
            self.filtered_entries = []
            self._rebuild_systems([])
            self._refresh_list()
            self._update_idle_status()
            return

        data = load_db(self.db_path)
        self.entries = data.get("entries", [])
        self.filtered_entries = []

        systems = sorted(
            {
                item.get("system", tr("common.unknown"))
                for item in self.entries
                if item.get("type") == "game"
            },
            key=str.casefold,
        )
        self._rebuild_systems(systems)
        self._filter()
        self._update_idle_status()

    def _rebuild_systems(self, systems):
        all_label = tr("zapscripts_tab.all")
        scripts_label = tr("zapscripts_tab.scripts")
        current = self.systems.currentItem().text() if self.systems.currentItem() else all_label

        self.systems.blockSignals(True)
        self.systems.clear()
        self.systems.addItems([all_label, scripts_label] + list(systems))

        matches = self.systems.findItems(current, Qt.MatchFlag.MatchExactly)
        if matches:
            self.systems.setCurrentItem(matches[0])
        elif self.systems.count() > 0:
            self.systems.setCurrentRow(0)

        self.systems.blockSignals(False)

    def start_scan(self):
        if not self.connection.is_connected():
            QMessageBox.warning(
                self,
                tr("zapscripts_tab.not_connected_title"),
                tr("zapscripts_tab.connect_first"),
            )
            return

        try:
            state = get_zapscripts_state(self.connection)
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("zapscripts_tab.zaparoo_check_failed"),
                str(e),
            )
            return

        if not state.get("zaparoo_installed", False):
            self._update_idle_status()
            return

        if not state.get("zaparoo_service_enabled", False):
            self._update_idle_status()
            return

        if not self._show_scan_notice_dialog():
            return

        self.db_path = self._get_db_path()
        if not self.db_path:
            QMessageBox.warning(
                self,
                tr("zapscripts_tab.no_mister_ip_title"),
                tr("zapscripts_tab.no_mister_ip_message"),
            )
            return

        try:
            media_status = get_media_database_status(self.connection)
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("zapscripts_tab.media_status_failed"),
                str(e),
            )
            return

        if not media_status.get("exists"):
            QMessageBox.warning(
                self,
                tr("zapscripts_tab.no_media_database_title"),
                tr("zapscripts_tab.no_media_database_message"),
            )
            self.status.setText(tr("zapscripts_tab.no_media_database_found"))
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            return

        if media_status.get("indexing"):
            step_label = media_status.get("current_step_display") or tr("zapscripts_tab.indexing")
            QMessageBox.information(
                self,
                tr("zapscripts_tab.media_indexing_title"),
                tr("zapscripts_tab.media_indexing_message", step=step_label),
            )
            self.status.setText(tr("zapscripts_tab.indexing_status", step=step_label))
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            return

        if media_status.get("optimizing"):
            step_label = media_status.get("current_step_display") or tr("zapscripts_tab.optimizing")
            QMessageBox.information(
                self,
                tr("zapscripts_tab.media_optimizing_title"),
                tr("zapscripts_tab.media_optimizing_message", step=step_label),
            )
            self.status.setText(tr("zapscripts_tab.optimizing_status", step=step_label))
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            return

        self.expected_total = int(media_status.get("total_media") or 0)

        self.scan_btn.setText(tr("zapscripts_tab.abort"))
        self.scan_btn.setEnabled(True)
        self.launch_btn.setEnabled(False)
        self.controls_btn.setEnabled(False)

        if self.expected_total > 0:
            self.progress.setRange(0, self.expected_total)
            self.progress.setValue(0)
        else:
            self.progress.setRange(0, 0)

        self.status.setText(tr("zapscripts_tab.items_scanned", count=0))

        self.worker = ScanWorker(self.connection)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.aborted.connect(self._on_aborted)
        self.worker.start()

    def abort_scan(self):
        if self.worker is None:
            return

        self.scan_btn.setEnabled(False)
        self.status.setText(tr("zapscripts_tab.aborting_scan"))
        self.worker.request_abort()

    def _on_progress(self, scanned_count):
        if self.expected_total > 0:
            self.progress.setRange(0, self.expected_total)
            self.progress.setValue(min(scanned_count, self.expected_total))
        self.status.setText(tr("zapscripts_tab.items_scanned", count=scanned_count))

    def _on_finished(self, data):
        self.progress.setRange(0, 100)
        self.progress.setValue(100)

        entries = []
        systems = set()

        for item in data:
            filename = item.get("filename") or item.get("name") or ""
            system_name = item.get("system_name") or tr("common.unknown")
            system_id = item.get("system_id") or system_name

            entries.append(
                {
                    "name": filename,
                    "filename": filename,
                    "system": system_name,
                    "system_id": system_id,
                    "type": "game",
                    "path": item.get("path"),
                    "zapScript": item.get("zapScript"),
                }
            )

            if system_name:
                systems.add(system_name)

        save_db(self.db_path, {"entries": entries})
        self.entries = entries

        self._rebuild_systems(sorted(systems, key=str.casefold))
        self._filter()

        self.scan_btn.setText(tr("zapscripts_tab.scan"))
        self.scan_btn.setEnabled(True)
        self.launch_btn.setEnabled(self.connection.is_connected())
        self.controls_btn.setEnabled(self.connection.is_connected())
        self.worker = None
        self.expected_total = 0
        self._update_idle_status()

    def _on_aborted(self):
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(tr("zapscripts_tab.scan_aborted"))
        self.scan_btn.setText(tr("zapscripts_tab.scan"))
        self.scan_btn.setEnabled(True)
        self.launch_btn.setEnabled(self.connection.is_connected())
        self.controls_btn.setEnabled(self.connection.is_connected())
        self.worker = None
        self.expected_total = 0

    def _on_error(self, message):
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(tr("zapscripts_tab.scan_failed_status", error=message))
        self.scan_btn.setText(tr("zapscripts_tab.scan"))
        self.scan_btn.setEnabled(True)
        self.launch_btn.setEnabled(self.connection.is_connected())
        self.controls_btn.setEnabled(self.connection.is_connected())
        self.worker = None
        self.expected_total = 0
        QMessageBox.critical(self, tr("zapscripts_tab.scan_failed_title"), message)

    def _get_combined_entries(self):
        scripts = list_scripts(self.connection) if self.connection.is_connected() else []
        return self.entries + scripts

    def _format_display_name(self, item, selected_system):
        name = item.get("name", "")

        if selected_system != tr("zapscripts_tab.all"):
            return name

        if item.get("type") == "script":
            return tr("zapscripts_tab.script_display", name=name)

        system_name = item.get("system", tr("common.unknown"))
        return tr("zapscripts_tab.game_display", system=system_name, name=name)

    def _refresh_list(self):
        self.list.clear()

        current_item = self.systems.currentItem()
        selected_system = current_item.text() if current_item else tr("zapscripts_tab.all")

        for item in self.filtered_entries:
            display_name = self._format_display_name(item, selected_system)
            list_item = QListWidgetItem(display_name)
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.list.addItem(list_item)

    def _filter(self):
        query = self.search.text().strip().lower()
        current_item = self.systems.currentItem()
        system = current_item.text() if current_item else tr("zapscripts_tab.all")

        all_label = tr("zapscripts_tab.all")
        scripts_label = tr("zapscripts_tab.scripts")

        combined = self._get_combined_entries()
        filtered = []

        for item in combined:
            name = item.get("name", "")

            if query and query not in name.lower():
                continue

            if system == scripts_label:
                if item.get("type") != "script":
                    continue
            elif system != all_label:
                if item.get("system") != system:
                    continue

            filtered.append(item)

        filtered.sort(key=lambda x: (x.get("name") or "").casefold())

        self.filtered_entries = filtered
        self._refresh_list()

    def _launch(self):
        if not self.connection.is_connected():
            QMessageBox.warning(
                self,
                tr("zapscripts_tab.not_connected_title"),
                tr("zapscripts_tab.connect_first"),
            )
            return

        current_item = self.list.currentItem()
        if not current_item:
            return

        entry = current_item.data(Qt.ItemDataRole.UserRole)
        if not entry:
            return

        try:
            launch_media(self.connection, entry)
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("zapscripts_tab.launch_failed"),
                str(e),
            )

    def _open_controls(self):
        if not self.connection.is_connected():
            QMessageBox.warning(
                self,
                tr("zapscripts_tab.not_connected_title"),
                tr("zapscripts_tab.connect_first"),
            )
            return

        dlg = ZapScriptsControlsDialog(
            self,
            callbacks={
                "bluetooth": lambda: self._run_control("**input.keyboard:{f11}"),
                "osd": lambda: self._run_control("**input.keyboard:{f12}"),
                "wallpaper": lambda: self._run_control("**input.keyboard:{f1}"),
                "home": lambda: self._run_control("**stop"),
            },
        )
        dlg.exec()

    def _run_control(self, command: str):
        try:
            send_input_command(self.connection, command)
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("zapscripts_tab.control_failed"),
                str(e),
            )

    def refresh_status(self):
        self.update_connection_state()

    def update_connection_state(self):
        connected = self.connection.is_connected()

        self.scan_btn.setEnabled(True if self.worker is not None else connected)
        self.launch_btn.setEnabled(connected and self.worker is None)
        self.controls_btn.setEnabled(connected and self.worker is None)

        self.search.setEnabled(True)
        self.systems.setEnabled(True)
        self.list.setEnabled(True)

        if connected and self.worker is None:
            self._load_db()
        elif not connected:
            self.db_path = self._get_db_path()

            if self.db_path:
                data = load_db(self.db_path)
                self.entries = data.get("entries", [])
            else:
                self.entries = []

            systems = sorted(
                {
                    item.get("system", tr("common.unknown"))
                    for item in self.entries
                    if item.get("type") == "game"
                },
                key=str.casefold,
            )
            self._rebuild_systems(systems)
            self._filter()

            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.status.setText(tr("zapscripts_tab.no_library_found"))
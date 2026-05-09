from datetime import datetime

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
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
from core.zapscripts import (
    fetch_media_from_db_cache,
    read_media_db_entries,
    list_scripts,
    launch_media,
    send_input_command,
    get_zapscripts_state,
)
from core.zaplauncher_db import get_media_db_path, get_last_scan_time
from ui.dialogs.zapscripts_controls_dialog import ZapScriptsControlsDialog
from ui.dialogs.zapscripts_scan_notice_dialog import ZapScriptsScanNoticeDialog


REMOTE_MEDIA_DB_PATH = "/media/fat/zaparoo/media.db"


class ZapScriptsLoadWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self,
        connection,
        db_path,
        connected=False,
        check_zaparoo_state=True,
        load_scripts=True,
    ):
        super().__init__()
        self.connection = connection
        self.db_path = db_path
        self.connected = bool(connected)
        self.check_zaparoo_state = bool(check_zaparoo_state)
        self.load_scripts = bool(load_scripts)

    def run(self):
        try:
            entries = []
            scripts = []
            state = None
            db_exists = bool(self.db_path and self.db_path.exists())
            read_error = ""

            if self.isInterruptionRequested():
                return

            if db_exists:
                try:
                    try:
                        entries = read_media_db_entries(
                            self.db_path,
                            cancel_callback=self.isInterruptionRequested,
                        )
                    except TypeError:
                        entries = read_media_db_entries(self.db_path)
                except Exception as e:
                    if str(e) in {"__LOAD_CANCELLED__", "__SCAN_ABORTED__"}:
                        return
                    entries = []
                    read_error = str(e)

            if self.isInterruptionRequested():
                return

            if self.connected and self.check_zaparoo_state:
                try:
                    state = get_zapscripts_state(self.connection)
                except Exception:
                    state = None

            if self.isInterruptionRequested():
                return

            if self.connected and self.load_scripts:
                try:
                    scripts = list_scripts(self.connection)
                except Exception:
                    scripts = []

            if self.isInterruptionRequested():
                return

            last_scan_time = get_last_scan_time(self.db_path) if self.db_path else None

            if self.isInterruptionRequested():
                return

            self.result.emit(
                {
                    "entries": entries,
                    "scripts": scripts,
                    "state": state,
                    "db_exists": db_exists,
                    "read_error": read_error,
                    "last_scan_time": last_scan_time,
                    "connected": self.connected,
                }
            )
        except Exception as e:
            if not self.isInterruptionRequested():
                self.error.emit(str(e))


class ScanWorker(QThread):
    progress = pyqtSignal(int)
    finished_scan = pyqtSignal(list)
    error = pyqtSignal(str)
    aborted = pyqtSignal()

    def __init__(self, connection, media_db_path):
        super().__init__()
        self.connection = connection
        self.media_db_path = media_db_path
        self._abort_requested = False

    def request_abort(self):
        self._abort_requested = True
        self.requestInterruption()

    def run(self):
        try:
            def progress_cb(*args):
                if self._abort_requested or self.isInterruptionRequested():
                    raise RuntimeError("__SCAN_ABORTED__")

                if len(args) >= 2:
                    self.progress.emit(int(args[1]))
                elif args:
                    self.progress.emit(int(args[0]))

            data = fetch_media_from_db_cache(
                self.connection,
                self.media_db_path,
                progress_callback=progress_cb,
            )

            if self._abort_requested or self.isInterruptionRequested():
                self.aborted.emit()
                return

            self.finished_scan.emit(data)

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
        self.scripts = []
        self.filtered_entries = []

        self.worker = None
        self.load_worker = None

        self.expected_total = 0
        self._db_loaded_once = False
        self._loading_db = False
        self._ignore_next_load_result = False
        self._refresh_after_scan = False
        self._suspended = False

        self._build_ui()
        QTimer.singleShot(0, lambda: self.update_connection_state(lightweight=True))

    @property
    def connection(self):
        return self.main_window.connection

    def _is_offline_mode(self):
        checker = getattr(self.main_window, "is_offline_mode", None)
        return bool(checker()) if callable(checker) else False

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        self.offline_message = QLabel("ZapScripts is not available in Offline Mode.")
        self.offline_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.offline_message.setWordWrap(True)
        self.offline_message.hide()

        self.online_widget = QWidget()
        online_layout = QVBoxLayout(self.online_widget)
        online_layout.setContentsMargins(0, 0, 0, 0)
        online_layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)

        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self._handle_scan_button)
        self.scan_btn.setFixedWidth(80)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)

        self.status = QLabel("No library found")
        self.status.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        top.addWidget(self.scan_btn)
        top.addWidget(self.progress, 1)
        top.addWidget(self.status)

        online_layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.systems = QListWidget()
        self.systems.addItems(["All", "Scripts"])
        self.systems.currentTextChanged.connect(self._filter)
        self.systems.setMinimumWidth(180)
        self.systems.setMaximumWidth(240)
        splitter.addWidget(self.systems)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self._launch())

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self.launch_btn = QPushButton("Launch Selected")
        self.launch_btn.clicked.connect(self._launch)

        self.controls_btn = QPushButton("Controls")
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

        online_layout.addWidget(splitter, 1)

        layout.addWidget(self.offline_message, 1)
        layout.addWidget(self.online_widget, 1)

    def showEvent(self, event):
        super().showEvent(event)
        self._suspended = False

    def hideEvent(self, event):
        super().hideEvent(event)
        self.suspend_background_work(wait=False)

    def closeEvent(self, event):
        self.suspend_background_work(wait=True)
        super().closeEvent(event)

    def suspend_background_work(self, wait=False):
        self._suspended = True
        self._ignore_next_load_result = True
        self._refresh_after_scan = False

        self._request_scan_worker_stop()
        self._request_load_worker_stop()

        if wait:
            for worker in (self.worker, self.load_worker):
                try:
                    if worker is not None and worker.isRunning():
                        worker.wait(1500)
                except Exception:
                    pass

        self.progress.setRange(0, 100)

        if self.connection.is_connected() and not self._is_offline_mode():
            self.scan_btn.setText("Scan")
            self.scan_btn.setEnabled(True)
            self.launch_btn.setEnabled(True)
            self.controls_btn.setEnabled(True)
        else:
            self.scan_btn.setText("Scan")
            self.scan_btn.setEnabled(False)
            self.launch_btn.setEnabled(False)
            self.controls_btn.setEnabled(False)

        self._clear_refreshing_status_style()

    def show_refreshing_state(self):
        if self._is_offline_mode():
            return

        if self.worker is not None:
            return

        if self.load_worker is not None and self.load_worker.isRunning():
            return

        self._apply_online_state()
        self.progress.setRange(0, 0)
        self.status.setText("Refreshing ZapScripts...")
        self.status.setStyleSheet("color: #1e88e5; font-weight: bold;")

        self.scan_btn.setEnabled(False)
        self.launch_btn.setEnabled(False)
        self.controls_btn.setEnabled(False)

    def _clear_refreshing_status_style(self):
        self.status.setStyleSheet("")

    def _request_load_worker_stop(self):
        if self.load_worker is None:
            return

        try:
            if self.load_worker.isRunning():
                self._ignore_next_load_result = True
                self.load_worker.requestInterruption()
        except Exception:
            pass

    def _request_scan_worker_stop(self):
        if self.worker is None:
            return

        try:
            if self.worker.isRunning():
                self.worker.request_abort()
        except Exception:
            pass

    def _apply_offline_state(self):
        self._request_scan_worker_stop()
        self._request_load_worker_stop()

        self.online_widget.hide()
        self.offline_message.show()

        self.entries = []
        self.scripts = []
        self.filtered_entries = []
        self.db_path = None
        self._db_loaded_once = False
        self._loading_db = False

        self.scan_btn.setText("Scan")
        self.scan_btn.setEnabled(False)
        self.launch_btn.setEnabled(False)
        self.controls_btn.setEnabled(False)
        self.search.setEnabled(False)
        self.systems.setEnabled(False)
        self.list.setEnabled(False)

        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText("ZapScripts is not available in Offline Mode.")
        self._clear_refreshing_status_style()

    def _apply_online_state(self):
        self.offline_message.hide()
        self.online_widget.show()

        self.search.setEnabled(True)
        self.systems.setEnabled(True)
        self.list.setEnabled(True)

    def _handle_scan_button(self):
        if self._is_offline_mode():
            return

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
        return get_media_db_path(profile_name, host) if host else None

    def _remote_media_db_exists(self) -> bool:
        if not self.connection.is_connected():
            return False

        output = self.connection.run_command(
            f'test -f "{REMOTE_MEDIA_DB_PATH}" && echo EXISTS'
        )

        return "EXISTS" in (output or "")

    def _get_remote_media_count_estimate(self) -> int:
        return 0

    def _update_idle_status(self, check_zaparoo_state=True):
        if self._is_offline_mode():
            self._apply_offline_state()
            return

        if not self.connection.is_connected():
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.status.setText("No library found")
            self._clear_refreshing_status_style()
            return

        if check_zaparoo_state:
            try:
                state = get_zapscripts_state(self.connection)
            except Exception:
                state = None

            if state:
                if not state.get("zaparoo_installed", False):
                    self.progress.setRange(0, 100)
                    self.progress.setValue(0)
                    self.status.setText("Zaparoo is not installed")
                    self._clear_refreshing_status_style()
                    return

                if not state.get("zaparoo_service_enabled", False):
                    self.progress.setRange(0, 100)
                    self.progress.setValue(0)
                    self.status.setText("Zaparoo service is not enabled")
                    self._clear_refreshing_status_style()
                    return

        ts = get_last_scan_time(self.db_path) if self.db_path else None
        self.progress.setRange(0, 100)

        if ts:
            dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            self.progress.setValue(100)
            self.status.setText(f"Last scan: {dt}")
        else:
            self.progress.setValue(0)
            self.status.setText("No scan has been run yet")

        self._clear_refreshing_status_style()

    def _load_db(self, check_zaparoo_state=True):
        self.start_load_db(check_zaparoo_state=check_zaparoo_state)

    def start_load_db(self, check_zaparoo_state=True):
        if self._is_offline_mode():
            self._apply_offline_state()
            return

        if not self.isVisible():
            return

        if self.worker is not None:
            return

        if self.load_worker is not None and self.load_worker.isRunning():
            return

        self._suspended = False
        self._apply_online_state()
        self.db_path = self._get_db_path()
        connected = self.connection.is_connected()

        self.show_refreshing_state()

        self._ignore_next_load_result = False

        worker = ZapScriptsLoadWorker(
            self.connection,
            self.db_path,
            connected=connected,
            check_zaparoo_state=check_zaparoo_state,
            load_scripts=connected,
        )
        self.load_worker = worker
        worker.result.connect(self._on_load_finished)
        worker.error.connect(self._on_load_error)
        worker.finished.connect(lambda: self._on_load_worker_finished(worker))
        worker.start()

    def _on_load_finished(self, result):
        if self._ignore_next_load_result or self._suspended:
            return

        if self._is_offline_mode():
            return

        if not isinstance(result, dict):
            result = {}

        self.entries = result.get("entries") or []
        self.scripts = result.get("scripts") or []
        self._db_loaded_once = True
        self.filtered_entries = []

        read_error = result.get("read_error") or ""
        state = result.get("state")
        last_scan_time = result.get("last_scan_time")

        systems = sorted(
            {
                item.get("system", "Unknown")
                for item in self.entries
                if item.get("type") == "game"
            },
            key=str.casefold,
        )

        self._rebuild_systems(systems)
        self._filter()

        self.progress.setRange(0, 100)

        if read_error:
            self.progress.setValue(0)
            self.status.setText(f"Could not read media.db: {read_error}")
            self._clear_refreshing_status_style()
        elif state and not state.get("zaparoo_installed", False):
            self.progress.setValue(0)
            self.status.setText("Zaparoo is not installed")
            self._clear_refreshing_status_style()
        elif state and not state.get("zaparoo_service_enabled", False):
            self.progress.setValue(0)
            self.status.setText("Zaparoo service is not enabled")
            self._clear_refreshing_status_style()
        elif last_scan_time:
            dt = datetime.fromtimestamp(last_scan_time).strftime("%Y-%m-%d %H:%M")
            self.progress.setValue(100)
            self.status.setText(f"Last scan: {dt}")
            self._clear_refreshing_status_style()
        else:
            self.progress.setValue(0)
            self.status.setText("No scan has been run yet")
            self._clear_refreshing_status_style()

        connected = self.connection.is_connected() and not self._is_offline_mode()

        self.scan_btn.setText("Scan")
        self.scan_btn.setEnabled(connected)
        self.launch_btn.setEnabled(connected)
        self.controls_btn.setEnabled(connected)

    def _on_load_error(self, message):
        if self._ignore_next_load_result or self._suspended:
            return

        if self._is_offline_mode():
            return

        self.entries = []
        self.scripts = []
        self.filtered_entries = []
        self._db_loaded_once = True
        self._rebuild_systems([])
        self._refresh_list()

        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(f"Could not load ZapScripts: {message}")
        self._clear_refreshing_status_style()

        connected = self.connection.is_connected() and not self._is_offline_mode()
        self.scan_btn.setEnabled(connected)
        self.launch_btn.setEnabled(connected)
        self.controls_btn.setEnabled(connected)

    def _on_load_worker_finished(self, worker):
        if self.load_worker is worker:
            self.load_worker = None

        try:
            worker.deleteLater()
        except Exception:
            pass

        if self._ignore_next_load_result:
            self._ignore_next_load_result = False

    def _rebuild_systems(self, systems):
        current = self.systems.currentItem().text() if self.systems.currentItem() else "All"

        self.systems.blockSignals(True)
        self.systems.clear()
        self.systems.addItems(["All", "Scripts"] + list(systems))

        matches = self.systems.findItems(current, Qt.MatchFlag.MatchExactly)
        if matches:
            self.systems.setCurrentItem(matches[0])
        elif self.systems.count() > 0:
            self.systems.setCurrentRow(0)

        self.systems.blockSignals(False)

    def start_scan(self):
        if self._is_offline_mode():
            return

        if not self.connection.is_connected():
            QMessageBox.warning(self, "Not connected", "Please connect to your MiSTer first.")
            return

        try:
            state = get_zapscripts_state(self.connection)
        except Exception as e:
            QMessageBox.critical(self, "Zaparoo check failed", str(e))
            return

        if not state.get("zaparoo_installed", False):
            self._update_idle_status(check_zaparoo_state=False)
            return

        if not state.get("zaparoo_service_enabled", False):
            self._update_idle_status(check_zaparoo_state=False)
            return

        if not self._show_scan_notice_dialog():
            return

        self.db_path = self._get_db_path()
        if not self.db_path:
            QMessageBox.warning(self, "No MiSTer IP", "No MiSTer IP is available.")
            return

        try:
            if not self._remote_media_db_exists():
                QMessageBox.warning(
                    self,
                    "No media database",
                    f"Zaparoo media database was not found on this MiSTer:\n\n{REMOTE_MEDIA_DB_PATH}",
                )
                self.status.setText("No media database found")
                self.progress.setRange(0, 100)
                self.progress.setValue(0)
                return
        except Exception as e:
            QMessageBox.critical(
                self,
                "Media database check failed",
                f"Could not check for Zaparoo media database:\n\n{e}",
            )
            return

        self.expected_total = self._get_remote_media_count_estimate()

        self.scan_btn.setText("Abort")
        self.scan_btn.setEnabled(True)
        self.launch_btn.setEnabled(False)
        self.controls_btn.setEnabled(False)

        self.progress.setRange(0, 0)
        self.status.setText("Downloading media.db...")
        self._clear_refreshing_status_style()

        worker = ScanWorker(self.connection, self.db_path)
        self.worker = worker
        worker.progress.connect(self._on_progress)
        worker.finished_scan.connect(self._on_finished)
        worker.error.connect(self._on_error)
        worker.aborted.connect(self._on_aborted)
        worker.finished.connect(lambda: self._on_scan_worker_finished(worker))
        worker.start()

    def abort_scan(self):
        if self.worker is None:
            return

        self.scan_btn.setEnabled(False)
        self.status.setText("Aborting scan...")
        self.worker.request_abort()

    def _on_progress(self, scanned_count):
        if self._suspended:
            return

        if self.progress.minimum() == 0 and self.progress.maximum() == 0:
            self.progress.setRange(0, 0)

        self.status.setText(f"Items scanned: {scanned_count}")

    def _on_finished(self, data):
        if self._suspended:
            return

        self.progress.setRange(0, 100)
        self.progress.setValue(100)

        self.entries = data or []
        self._db_loaded_once = True

        systems = sorted(
            {
                item.get("system", "Unknown")
                for item in self.entries
                if item.get("type") == "game"
            },
            key=str.casefold,
        )

        self._rebuild_systems(systems)
        self._filter()

        self.scan_btn.setText("Scan")
        self.scan_btn.setEnabled(not self._is_offline_mode() and self.connection.is_connected())
        self.launch_btn.setEnabled(not self._is_offline_mode() and self.connection.is_connected())
        self.controls_btn.setEnabled(not self._is_offline_mode() and self.connection.is_connected())
        self.expected_total = 0
        self._update_idle_status(check_zaparoo_state=False)

        self._refresh_after_scan = True

    def _on_aborted(self):
        if self._suspended:
            return

        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText("Scan aborted")
        self.scan_btn.setText("Scan")
        self.scan_btn.setEnabled(not self._is_offline_mode() and self.connection.is_connected())
        self.launch_btn.setEnabled(not self._is_offline_mode() and self.connection.is_connected())
        self.controls_btn.setEnabled(not self._is_offline_mode() and self.connection.is_connected())
        self.expected_total = 0
        self._refresh_after_scan = False

        if self._is_offline_mode():
            self._apply_offline_state()

    def _on_error(self, message):
        if self._suspended:
            return

        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(f"Scan failed: {message}")
        self.scan_btn.setText("Scan")
        self.scan_btn.setEnabled(not self._is_offline_mode() and self.connection.is_connected())
        self.launch_btn.setEnabled(not self._is_offline_mode() and self.connection.is_connected())
        self.controls_btn.setEnabled(not self._is_offline_mode() and self.connection.is_connected())
        self.expected_total = 0
        self._refresh_after_scan = False

        if self._is_offline_mode():
            self._apply_offline_state()
            return

        QMessageBox.critical(self, "Scan failed", message)

    def _on_scan_worker_finished(self, worker):
        if self.worker is worker:
            self.worker = None

        try:
            worker.deleteLater()
        except Exception:
            pass

        if self._refresh_after_scan and not self._suspended and self.isVisible():
            self._refresh_after_scan = False
            QTimer.singleShot(0, lambda: self.start_load_db(check_zaparoo_state=False))

    def _get_combined_entries(self):
        if self._is_offline_mode():
            return []

        return self.entries + self.scripts

    def _format_display_name(self, item, selected_system):
        name = item.get("name", "")

        if selected_system != "All":
            return name

        if item.get("type") == "script":
            return f"(SCRIPT) {name}"

        system_name = item.get("system", "Unknown")
        return f"({system_name}) {name}"

    def _refresh_list(self):
        self.list.clear()

        current_item = self.systems.currentItem()
        selected_system = current_item.text() if current_item else "All"

        for item in self.filtered_entries:
            display_name = self._format_display_name(item, selected_system)
            list_item = QListWidgetItem(display_name)
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.list.addItem(list_item)

    def _filter(self):
        if self._is_offline_mode():
            self.filtered_entries = []
            self._refresh_list()
            return

        query = self.search.text().strip().lower()
        current_item = self.systems.currentItem()
        system = current_item.text() if current_item else "All"

        combined = self._get_combined_entries()
        filtered = []

        for item in combined:
            name = item.get("name", "")

            if query and query not in name.lower():
                continue

            if system == "Scripts":
                if item.get("type") != "script":
                    continue
            elif system != "All":
                if item.get("system") != system:
                    continue

            filtered.append(item)

        filtered.sort(key=lambda x: (x.get("name") or "").casefold())

        self.filtered_entries = filtered
        self._refresh_list()

    def _launch(self):
        if self._is_offline_mode():
            return

        if not self.connection.is_connected():
            QMessageBox.warning(self, "Not connected", "Please connect to your MiSTer first.")
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
            QMessageBox.critical(self, "Launch failed", str(e))

    def _open_controls(self):
        if self._is_offline_mode():
            return

        if not self.connection.is_connected():
            QMessageBox.warning(self, "Not connected", "Please connect to your MiSTer first.")
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
        if self._is_offline_mode():
            return

        try:
            send_input_command(self.connection, command)
        except Exception as e:
            QMessageBox.critical(self, "Control failed", str(e))

    def refresh_status(self):
        self.update_connection_state(lightweight=False)

    def update_connection_state(self, lightweight=True):
        if self._is_offline_mode():
            self._apply_offline_state()
            return

        self._apply_online_state()

        connected = self.connection.is_connected()

        self.scan_btn.setEnabled(True if self.worker is not None else connected)
        self.launch_btn.setEnabled(connected and self.worker is None)
        self.controls_btn.setEnabled(connected and self.worker is None)

        self.search.setEnabled(True)
        self.systems.setEnabled(True)
        self.list.setEnabled(True)

        if connected:
            if self.worker is not None:
                return

            if not lightweight:
                self.start_load_db(check_zaparoo_state=True)
            elif not self._db_loaded_once:
                self.start_load_db(check_zaparoo_state=False)
            return

        self.db_path = self._get_db_path()

        if self.load_worker is not None and self.load_worker.isRunning():
            return

        if self.db_path and self.db_path.exists():
            try:
                try:
                    self.entries = read_media_db_entries(
                        self.db_path,
                        cancel_callback=lambda: False,
                    )
                except TypeError:
                    self.entries = read_media_db_entries(self.db_path)
            except Exception:
                self.entries = []
        else:
            self.entries = []

        self.scripts = []
        self._db_loaded_once = True

        systems = sorted(
            {
                item.get("system", "Unknown")
                for item in self.entries
                if item.get("type") == "game"
            },
            key=str.casefold,
        )

        self._rebuild_systems(systems)
        self._filter()

        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText("No library found")
        self._clear_refreshing_status_style()
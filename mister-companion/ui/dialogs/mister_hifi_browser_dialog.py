import posixpath

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout
)

from core.mister_hifi_remote import browse, get_sources, play


class _RequestSignals(QObject):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()


class _RequestRunnable(QRunnable):
    def __init__(self, fn, *args):
        super().__init__()
        self.fn = fn
        self.args = args
        self.signals = _RequestSignals()
        self.setAutoDelete(True)

    def run(self):
        try:
            self.signals.done.emit(self.fn(*self.args))
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        finally:
            self.signals.finished.emit()


class MiSTerHiFiBrowserDialog(QDialog):
    def __init__(self, connection, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.current_source = ""
        self.current_path = ""
        self.root_path = ""
        self._request_active = False
        self._pending_request = None
        self._request_refs = []

        self.setWindowTitle("Browse MiSTer Hi-Fi")
        self.resize(620, 520)

        layout = QVBoxLayout(self)
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Source:"))
        self.source_combo = QComboBox()
        self.source_combo.setEnabled(False)
        source_row.addWidget(self.source_combo, 1)
        self.up_button = QPushButton("Up")
        self.up_button.setEnabled(False)
        source_row.addWidget(self.up_button)
        layout.addLayout(source_row)

        self.path_label = QLabel("Loading sources...")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.path_label)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setEnabled(False)
        loading_item = QListWidgetItem("Loading MiSTer Hi-Fi sources...")
        loading_item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.list_widget.addItem(loading_item)
        layout.addWidget(self.list_widget, 1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

        self.source_combo.currentIndexChanged.connect(self.source_changed)
        self.up_button.clicked.connect(self.go_up)
        self.list_widget.itemDoubleClicked.connect(self.activate_item)

        # Let the dialog finish constructing and become visible before doing
        # any network I/O. Population happens entirely in the worker pool.
        QTimer.singleShot(0, self.load_sources)

    def run_request(self, fn, args, callback):
        request = (fn, args, callback)
        if self._request_active:
            # Keep only the newest navigation request. This prevents a source
            # change from racing the source-list request that just completed.
            self._pending_request = request
            return

        self._request_active = True
        worker = _RequestRunnable(fn, *args)
        self._request_refs.append(worker)
        worker.signals.done.connect(callback)
        worker.signals.failed.connect(self.request_failed)
        worker.signals.finished.connect(lambda w=worker: self.request_finished(w))
        QThreadPool.globalInstance().start(worker)

    def request_finished(self, worker):
        try:
            self._request_refs.remove(worker)
        except ValueError:
            pass
        self._request_active = False

        pending = self._pending_request
        self._pending_request = None
        if pending is not None and self.isVisible():
            fn, args, callback = pending
            QTimer.singleShot(0, lambda: self.run_request(fn, args, callback))

    def request_failed(self, message):
        if not self.isVisible():
            return
        self.path_label.setText("Unable to browse MiSTer Hi-Fi")
        self.list_widget.setEnabled(True)
        self.list_widget.clear()
        item = QListWidgetItem("Unable to load this location.")
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.list_widget.addItem(item)
        QMessageBox.warning(self, "MiSTer Hi-Fi", message)

    def load_sources(self):
        if not self.isVisible():
            return
        self.path_label.setText("Loading sources...")
        self.run_request(get_sources, (self.connection,), self.apply_sources)

    def apply_sources(self, sources):
        if not self.isVisible():
            return

        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for source in sources or []:
            if isinstance(source, dict):
                source_id = str(source.get("id") or "")
                if source_id:
                    self.source_combo.addItem(str(source.get("name") or source_id), source_id)
        self.source_combo.blockSignals(False)

        self.source_combo.setEnabled(self.source_combo.count() > 0)
        self.list_widget.setEnabled(self.source_combo.count() > 0)

        if self.source_combo.count():
            self.source_combo.setCurrentIndex(0)
            self.source_changed(0)
        else:
            self.path_label.setText("No MiSTer Hi-Fi sources available")
            self.list_widget.clear()
            item = QListWidgetItem("No MiSTer Hi-Fi sources available.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(item)

    def source_changed(self, index):
        source = self.source_combo.itemData(index) if index >= 0 else ""
        if not source:
            return
        self.current_source = str(source)
        self.current_path = ""
        self.root_path = ""
        self.load_path("")

    def load_path(self, path):
        if not self.current_source:
            return
        self.path_label.setText("Loading...")
        self.list_widget.setEnabled(False)
        self.list_widget.clear()
        item = QListWidgetItem("Loading...")
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.list_widget.addItem(item)
        self.run_request(browse, (self.connection, self.current_source, path), self.apply_browse)

    def apply_browse(self, data):
        if not self.isVisible():
            return
        self.current_path = str((data or {}).get("path") or "")
        self.root_path = str((data or {}).get("root") or "")
        self.path_label.setText(self.current_path or self.source_combo.currentText() or self.current_source)
        self.up_button.setEnabled(bool(self.current_path and self.root_path and self.current_path != self.root_path))
        self.list_widget.setEnabled(True)
        self.list_widget.clear()
        for entry in (data or {}).get("entries", []) or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "")
            item = QListWidgetItem(("📁  " if entry.get("is_dir") else "♫  ") + name)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.list_widget.addItem(item)
        if self.list_widget.count() == 0:
            item = QListWidgetItem("No playable items found.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(item)

    def go_up(self):
        if not self.current_path or not self.root_path or self.current_path == self.root_path:
            return
        parent = posixpath.dirname(self.current_path.rstrip("/")) or self.root_path
        if len(parent) < len(self.root_path):
            parent = self.root_path
        self.load_path(parent)

    def activate_item(self, item):
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, dict):
            return
        path = str(entry.get("path") or "")
        if entry.get("is_dir"):
            self.load_path(path)
            return
        self.run_request(play, (self.connection, self.current_source, path), lambda _result: None)

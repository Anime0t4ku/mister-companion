from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.file_browser import (
    DEFAULT_ROOT,
    USB_ROOT,
    available_roots,
    clamp_to_root,
    delete_path,
    download_path,
    format_size,
    is_safe_path,
    join_remote_path,
    list_directory,
    make_directory,
    parent_path,
    rename_path,
    upload_path,
)


class FileBrowserWorker(QThread):
    result = pyqtSignal(str, object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)
    transfer_progress = pyqtSignal(int, int)

    def __init__(self, connection, action, **kwargs):
        super().__init__()
        self.connection = connection
        self.action = action
        self.kwargs = kwargs

    def run(self):
        try:
            if self.action == "roots":
                self.result.emit(self.action, available_roots(self.connection))
                return

            if self.action == "list":
                self.result.emit(self.action, list_directory(self.connection, self.kwargs.get("path", DEFAULT_ROOT)))
                return

            if self.action == "upload":
                local_paths = self.kwargs.get("local_paths", [])
                remote_dir = self.kwargs.get("remote_dir", DEFAULT_ROOT)
                uploaded = []
                for local_path in local_paths:
                    target = upload_path(
                        self.connection,
                        local_path,
                        remote_dir,
                        progress_callback=self.on_transfer_progress,
                        message_callback=self.progress.emit,
                    )
                    uploaded.append(target)
                self.result.emit(self.action, uploaded)
                return

            if self.action == "download":
                target = download_path(
                    self.connection,
                    self.kwargs.get("remote_path"),
                    self.kwargs.get("local_dir"),
                    progress_callback=self.on_transfer_progress,
                    message_callback=self.progress.emit,
                )
                self.result.emit(self.action, target)
                return

            if self.action == "mkdir":
                make_directory(self.connection, self.kwargs.get("path"))
                self.result.emit(self.action, self.kwargs.get("path"))
                return

            if self.action == "rename":
                rename_path(
                    self.connection,
                    self.kwargs.get("old_path"),
                    self.kwargs.get("new_path"),
                )
                self.result.emit(self.action, self.kwargs.get("new_path"))
                return

            if self.action == "delete":
                delete_path(self.connection, self.kwargs.get("path"))
                self.result.emit(self.action, self.kwargs.get("path"))
                return

            raise ValueError(f"Unknown file browser action: {self.action}")
        except Exception as e:
            self.error.emit(str(e))

    def on_transfer_progress(self, transferred, total):
        self.transfer_progress.emit(int(transferred or 0), int(total or 0))


class FileTreeWidget(QTreeWidget):
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setDropIndicatorShown(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            super().dropEvent(event)
            return

        paths = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if path:
                    paths.append(path)

        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return

        super().dropEvent(event)


class FileBrowserDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.connection = getattr(parent, "connection", None)
        self.worker = None
        self.current_path = DEFAULT_ROOT
        self.current_root = DEFAULT_ROOT
        self.roots = []
        self.entries = []
        self.busy = False
        self.pending_load_path = None
        self.last_transfer_percent = -1

        self.setWindowTitle("MiSTer File Browser")
        self.resize(980, 720)
        self.setMinimumSize(820, 560)

        self.build_ui()
        self.bind_shortcuts()
        self.append_output("Ready")
        self.refresh_roots()

    def build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        toolbar.addWidget(QLabel("Storage:"))
        self.storage_combo = QComboBox()
        self.storage_combo.setMinimumWidth(210)
        self.storage_combo.currentIndexChanged.connect(self.on_storage_changed)
        toolbar.addWidget(self.storage_combo)

        self.up_button = QPushButton("Up")
        self.refresh_button = QPushButton("Refresh")
        self.upload_button = QPushButton("Upload Files")
        self.upload_folder_button = QPushButton("Upload Folder")
        self.new_folder_button = QPushButton("New Folder")

        self.up_button.clicked.connect(self.go_up)
        self.refresh_button.clicked.connect(self.refresh_current_path)
        self.upload_button.clicked.connect(self.upload_files_dialog)
        self.upload_folder_button.clicked.connect(self.upload_folder_dialog)
        self.new_folder_button.clicked.connect(self.create_folder)

        toolbar.addWidget(self.up_button)
        toolbar.addWidget(self.refresh_button)
        toolbar.addStretch()
        toolbar.addWidget(self.upload_button)
        toolbar.addWidget(self.upload_folder_button)
        toolbar.addWidget(self.new_folder_button)
        root_layout.addLayout(toolbar)

        quick_bar = QHBoxLayout()
        quick_bar.setSpacing(6)
        self.quick_buttons = []
        for label, folder in (
            ("Root", ""),
            ("Games", "games"),
            ("Scripts", "Scripts"),
            ("Docs", "docs"),
            ("Saves", "saves"),
            ("Savestates", "savestates"),
            ("Wallpapers", "wallpapers"),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, folder=folder: self.open_quick_folder(folder))
            self.quick_buttons.append(button)
            quick_bar.addWidget(button)
        quick_bar.addStretch()
        root_layout.addLayout(quick_bar)

        path_panel = QFrame()
        path_panel.setFrameShape(QFrame.Shape.StyledPanel)
        path_layout = QHBoxLayout(path_panel)
        path_layout.setContentsMargins(8, 6, 8, 6)
        path_layout.addWidget(QLabel("Path:"))
        self.path_label = QLabel(DEFAULT_ROOT)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_layout.addWidget(self.path_label, 1)
        root_layout.addWidget(path_panel)

        self.file_tree = FileTreeWidget()
        self.file_tree.setColumnCount(4)
        self.file_tree.setHeaderLabels(["Name", "Size", "Modified", "Type"])
        self.file_tree.setRootIsDecorated(False)
        self.file_tree.setAlternatingRowColors(True)
        self.file_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.file_tree.customContextMenuRequested.connect(self.open_context_menu)
        self.file_tree.files_dropped.connect(self.upload_dropped_paths)
        self.file_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.file_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.file_tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        root_layout.addWidget(self.file_tree, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.download_button = QPushButton("Download")
        self.rename_button = QPushButton("Rename")
        self.delete_button = QPushButton("Delete")
        self.copy_path_button = QPushButton("Copy Path")
        self.close_button = QPushButton("Close")

        self.download_button.clicked.connect(self.download_selected)
        self.rename_button.clicked.connect(self.rename_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.copy_path_button.clicked.connect(self.copy_selected_path)
        self.close_button.clicked.connect(self.close)

        actions.addWidget(self.download_button)
        actions.addWidget(self.rename_button)
        actions.addWidget(self.delete_button)
        actions.addWidget(self.copy_path_button)
        actions.addStretch()
        actions.addWidget(self.close_button)
        root_layout.addLayout(actions)

        output_label = QLabel("Output / Transfers")
        output_label.setStyleSheet("font-weight: bold;")
        root_layout.addWidget(output_label)

        self.output_edit = QTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setMinimumHeight(105)
        self.output_edit.setMaximumHeight(150)
        self.output_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root_layout.addWidget(self.output_edit)

    def bind_shortcuts(self):
        QShortcut(QKeySequence.StandardKey.Refresh, self, activated=self.refresh_current_path)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self, activated=self.go_up)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self.delete_selected)
        QShortcut(QKeySequence(Qt.Key.Key_F2), self, activated=self.rename_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self.open_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, activated=self.open_selected)

    def append_output(self, message):
        if message and (message.startswith("Uploading ") or message.startswith("Downloading ")):
            self.last_transfer_percent = -1
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output_edit.append(f"[{timestamp}] {message}")
        self.output_edit.verticalScrollBar().setValue(self.output_edit.verticalScrollBar().maximum())

    def set_busy(self, busy):
        self.busy = bool(busy)
        for widget in (
            self.storage_combo,
            self.up_button,
            self.refresh_button,
            self.upload_button,
            self.upload_folder_button,
            self.new_folder_button,
            self.download_button,
            self.rename_button,
            self.delete_button,
            self.copy_path_button,
            self.file_tree,
        ):
            widget.setEnabled(not self.busy)

    def start_worker(self, action, **kwargs):
        if self.busy:
            return
        if not self.connection or not self.connection.is_connected():
            QMessageBox.information(self, "Files", "Connect to a MiSTer first before using Files.")
            return

        self.set_busy(True)
        self.worker = FileBrowserWorker(self.connection, action, **kwargs)
        self.worker.result.connect(self.on_worker_result)
        self.worker.error.connect(self.on_worker_error)
        self.worker.progress.connect(self.append_output)
        self.worker.transfer_progress.connect(self.on_transfer_progress)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def refresh_roots(self):
        self.append_output("Checking storage...")
        self.start_worker("roots")

    def refresh_current_path(self):
        self.load_path(self.current_path)

    def load_path(self, path):
        path = clamp_to_root(path, self.current_root or DEFAULT_ROOT)
        if not is_safe_path(path):
            path = DEFAULT_ROOT
        self.append_output(f"Loading {path}...")
        self.start_worker("list", path=path)

    def on_worker_result(self, action, data):
        if action == "roots":
            self.apply_roots(data)
            return

        if action == "list":
            self.apply_listing(data)
            return

        if action == "upload":
            count = len(data or [])
            self.append_output(f"Upload completed: {count} item{'s' if count != 1 else ''}.")
            self.pending_load_path = self.current_path
            return

        if action == "download":
            self.append_output(f"Download completed: {data}")
            return

        if action == "mkdir":
            self.append_output(f"Created folder: {data}")
            self.pending_load_path = self.current_path
            return

        if action == "rename":
            self.append_output(f"Renamed to: {data}")
            self.pending_load_path = self.current_path
            return

        if action == "delete":
            self.append_output(f"Deleted: {data}")
            self.pending_load_path = self.current_path

    def on_worker_error(self, message):
        self.append_output(f"Error: {message}")
        QMessageBox.warning(self, "Files", message)

    def on_worker_finished(self):
        self.set_busy(False)
        self.worker = None
        pending_path = self.pending_load_path
        self.pending_load_path = None
        if pending_path:
            self.load_path(pending_path)

    def on_transfer_progress(self, transferred, total):
        if total > 0:
            percent = int((transferred / total) * 100)
            if percent == 100 or percent - self.last_transfer_percent >= 10:
                self.last_transfer_percent = percent
                self.append_output(f"Progress: {percent}% ({format_size(transferred)} / {format_size(total)})")

    def apply_roots(self, roots):
        self.roots = roots or [{"name": "SD Card", "path": DEFAULT_ROOT, "available": True}]
        self.storage_combo.blockSignals(True)
        self.storage_combo.clear()
        for root in self.roots:
            label = f"{root.get('name', 'Storage')} ({root.get('path', '')})"
            self.storage_combo.addItem(label, root.get("path", DEFAULT_ROOT))
        self.storage_combo.blockSignals(False)

        sd_index = self.storage_combo.findData(DEFAULT_ROOT)
        if sd_index < 0:
            sd_index = 0
        self.storage_combo.setCurrentIndex(sd_index)
        self.current_root = self.storage_combo.currentData() or DEFAULT_ROOT
        self.current_path = self.current_root
        self.pending_load_path = self.current_path

    def apply_listing(self, data):
        self.current_path = data.get("path", self.current_path)
        self.current_root = self.storage_combo.currentData() or DEFAULT_ROOT
        self.entries = data.get("entries", [])
        self.path_label.setText(self.current_path)
        self.file_tree.clear()

        if self.current_path != self.current_root:
            up_item = QTreeWidgetItem(["..", "", "", "Folder"])
            up_item.setData(0, Qt.ItemDataRole.UserRole, {"up": True, "path": parent_path(self.current_path), "is_dir": True})
            self.file_tree.addTopLevelItem(up_item)

        for entry in self.entries:
            mtime = ""
            if entry.get("mtime"):
                mtime = datetime.fromtimestamp(entry["mtime"]).strftime("%Y-%m-%d %H:%M")

            size = "" if entry.get("is_dir") else format_size(entry.get("size", 0))
            icon_name = "📁 " if entry.get("is_dir") else "📄 "
            item = QTreeWidgetItem([f"{icon_name}{entry.get('name', '')}", size, mtime, entry.get("type", "")])
            item.setData(0, Qt.ItemDataRole.UserRole, entry)
            self.file_tree.addTopLevelItem(item)

        self.append_output(f"Loaded {self.current_path}")

    def on_storage_changed(self):
        root = self.storage_combo.currentData() or DEFAULT_ROOT
        self.current_root = root
        self.current_path = root
        self.load_path(root)

    def open_quick_folder(self, folder):
        root = self.storage_combo.currentData() or DEFAULT_ROOT
        path = root if not folder else join_remote_path(root, folder)
        self.load_path(path)

    def selected_entry(self):
        items = self.file_tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.ItemDataRole.UserRole)

    def open_selected(self):
        entry = self.selected_entry()
        if not entry:
            return
        if entry.get("up"):
            self.load_path(entry.get("path"))
            return
        if entry.get("is_dir"):
            self.load_path(entry.get("path"))

    def on_item_double_clicked(self, item, column):
        self.open_selected()

    def go_up(self):
        if self.current_path == self.current_root:
            return
        self.load_path(parent_path(self.current_path))

    def upload_files_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Upload Files")
        if files:
            self.upload_paths(files)

    def upload_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Upload Folder")
        if folder:
            self.upload_paths([folder])

    def upload_dropped_paths(self, paths):
        self.upload_paths(paths)

    def upload_paths(self, paths):
        valid_paths = [path for path in paths if Path(path).exists()]
        if not valid_paths:
            return
        self.append_output(f"Uploading {len(valid_paths)} item{'s' if len(valid_paths) != 1 else ''} to {self.current_path}...")
        self.start_worker("upload", local_paths=valid_paths, remote_dir=self.current_path)

    def download_selected(self):
        entry = self.selected_entry()
        if not entry or entry.get("up"):
            QMessageBox.information(self, "Files", "Select a file or folder to download.")
            return

        local_dir = QFileDialog.getExistingDirectory(self, "Choose Download Folder")
        if not local_dir:
            return

        self.append_output(f"Downloading {entry.get('name')}...")
        self.start_worker("download", remote_path=entry.get("path"), local_dir=local_dir)

    def create_folder(self):
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        name = name.strip()
        if not ok or not name:
            return
        if "/" in name or "\\" in name:
            QMessageBox.warning(self, "Files", "Folder name cannot contain slashes.")
            return
        path = join_remote_path(self.current_path, name)
        self.start_worker("mkdir", path=path)

    def rename_selected(self):
        entry = self.selected_entry()
        if not entry or entry.get("up"):
            QMessageBox.information(self, "Files", "Select a file or folder to rename.")
            return

        old_name = entry.get("name", "")
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old_name)
        new_name = new_name.strip()
        if not ok or not new_name or new_name == old_name:
            return
        if "/" in new_name or "\\" in new_name:
            QMessageBox.warning(self, "Files", "Name cannot contain slashes.")
            return

        new_path = join_remote_path(self.current_path, new_name)
        self.start_worker("rename", old_path=entry.get("path"), new_path=new_path)

    def delete_selected(self):
        entry = self.selected_entry()
        if not entry or entry.get("up"):
            QMessageBox.information(self, "Files", "Select a file or folder to delete.")
            return

        name = entry.get("name", "")
        reply = QMessageBox.question(
            self,
            "Delete",
            f"Delete '{name}' from the MiSTer?\n\nThis cannot be undone from MiSTer Companion.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.start_worker("delete", path=entry.get("path"))

    def copy_selected_path(self):
        entry = self.selected_entry()
        path = self.current_path
        if entry and not entry.get("up"):
            path = entry.get("path", path)
        self.window().clipboard().setText(path) if hasattr(self.window(), "clipboard") else None
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(path)
        except Exception:
            pass
        self.append_output(f"Copied path: {path}")

    def open_context_menu(self, position):
        menu = QMenu(self)
        entry = self.selected_entry()

        open_action = QAction("Open", self)
        download_action = QAction("Download", self)
        rename_action = QAction("Rename", self)
        delete_action = QAction("Delete", self)
        new_folder_action = QAction("New Folder", self)
        upload_action = QAction("Upload Here", self)
        copy_path_action = QAction("Copy Remote Path", self)
        refresh_action = QAction("Refresh", self)

        open_action.triggered.connect(self.open_selected)
        download_action.triggered.connect(self.download_selected)
        rename_action.triggered.connect(self.rename_selected)
        delete_action.triggered.connect(self.delete_selected)
        new_folder_action.triggered.connect(self.create_folder)
        upload_action.triggered.connect(self.upload_files_dialog)
        copy_path_action.triggered.connect(self.copy_selected_path)
        refresh_action.triggered.connect(self.refresh_current_path)

        if entry and entry.get("is_dir"):
            menu.addAction(open_action)
        menu.addAction(download_action)
        menu.addSeparator()
        menu.addAction(upload_action)
        menu.addAction(new_folder_action)
        menu.addSeparator()
        menu.addAction(rename_action)
        menu.addAction(delete_action)
        menu.addSeparator()
        menu.addAction(copy_path_action)
        menu.addAction(refresh_action)

        if not entry or entry.get("up"):
            download_action.setEnabled(False)
            rename_action.setEnabled(False)
            delete_action.setEnabled(False)

        menu.exec(self.file_tree.viewport().mapToGlobal(position))

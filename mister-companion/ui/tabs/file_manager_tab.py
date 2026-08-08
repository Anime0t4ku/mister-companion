from datetime import datetime
import os
import shutil
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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

from core.config import load_config, save_config
from core.file_browser import (
    DEFAULT_ROOT,
    available_roots,
    clamp_to_root,
    copy_path,
    delete_path,
    download_path,
    format_size,
    is_safe_path,
    join_remote_path,
    list_directory,
    make_directory,
    move_path,
    parent_path,
    rename_path,
    upload_path,
)


def _offline_local_path(sd_root, virtual_path):
    root = Path(str(sd_root or "")).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError("Select a valid Offline SD Card folder first.")
    virtual_path = clamp_to_root(virtual_path or DEFAULT_ROOT, DEFAULT_ROOT)
    rel = virtual_path[len(DEFAULT_ROOT):].lstrip("/")
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Path is outside the selected SD Card root.") from exc
    return target


def _offline_virtual_path(sd_root, local_path):
    root = Path(str(sd_root or "")).expanduser().resolve()
    target = Path(local_path).resolve()
    rel = target.relative_to(root)
    if not rel.parts:
        return DEFAULT_ROOT
    return join_remote_path(DEFAULT_ROOT, rel.as_posix())


def _offline_list_directory(sd_root, virtual_path):
    local_dir = _offline_local_path(sd_root, virtual_path)
    if not local_dir.exists() or not local_dir.is_dir():
        raise FileNotFoundError(f"Folder not found: {virtual_path}")
    entries = []
    for child in local_dir.iterdir():
        try:
            info = child.stat()
        except OSError:
            continue
        is_dir = child.is_dir()
        entries.append({
            "name": child.name,
            "path": _offline_virtual_path(sd_root, child),
            "is_dir": is_dir,
            "type": "Folder" if is_dir else "File",
            "size": 0 if is_dir else int(info.st_size or 0),
            "mtime": int(info.st_mtime or 0),
        })
    entries.sort(key=lambda item: (not item["is_dir"], item["name"].casefold()))
    return {"path": clamp_to_root(virtual_path or DEFAULT_ROOT, DEFAULT_ROOT), "entries": entries}


def _remove_local_target(path):
    path = Path(path)
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _copy_local_file(source, target, progress_callback=None, message_callback=None):
    source = Path(source)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    total = int(source.stat().st_size or 0)
    done = 0
    if message_callback:
        message_callback(f"Copying {source.name}...")
    with source.open("rb") as src, target.open("wb") as dst:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)
            done += len(chunk)
            if progress_callback:
                progress_callback(done, total)
    try:
        shutil.copystat(source, target)
    except OSError:
        pass


def _copy_local_item(source, target, progress_callback=None, message_callback=None):
    source = Path(source)
    target = Path(target)
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for root, dirs, files in os.walk(source):
            root_path = Path(root)
            rel = root_path.relative_to(source)
            dst_root = target if str(rel) == "." else target / rel
            dst_root.mkdir(parents=True, exist_ok=True)
            for dirname in dirs:
                (dst_root / dirname).mkdir(parents=True, exist_ok=True)
            for filename in files:
                _copy_local_file(root_path / filename, dst_root / filename, progress_callback, message_callback)
    else:
        _copy_local_file(source, target, progress_callback, message_callback)


def _offline_target(sd_root, virtual_dir, target_name):
    directory = _offline_local_path(sd_root, virtual_dir)
    return directory / str(target_name or "")


class FileManagerWorker(QThread):
    result = pyqtSignal(str, object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)
    transfer_progress = pyqtSignal(object, object)

    def __init__(self, connection, action, offline_mode=False, sd_root="", **kwargs):
        super().__init__()
        self.connection = connection
        self.action = action
        self.offline_mode = bool(offline_mode)
        self.sd_root = str(sd_root or "")
        self.kwargs = kwargs

    def run(self):
        try:
            if self.offline_mode:
                self.run_offline()
                return
            if self.action == "roots":
                self.result.emit(self.action, available_roots(self.connection))
                return

            if self.action == "list":
                self.result.emit(self.action, list_directory(self.connection, self.kwargs.get("path", DEFAULT_ROOT)))
                return

            if self.action == "upload":
                upload_items = self.kwargs.get("upload_items", [])
                uploaded = []
                for item in upload_items:
                    target = upload_path(
                        self.connection,
                        item.get("local_path"),
                        item.get("remote_dir", DEFAULT_ROOT),
                        progress_callback=self.on_transfer_progress,
                        message_callback=self.progress.emit,
                        target_name=item.get("target_name"),
                        overwrite=item.get("overwrite", False),
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
                    target_name=self.kwargs.get("target_name"),
                    overwrite=self.kwargs.get("overwrite", False),
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
                    overwrite=self.kwargs.get("overwrite", False),
                )
                self.result.emit(self.action, self.kwargs.get("new_path"))
                return

            if self.action == "copy":
                target = copy_path(
                    self.connection,
                    self.kwargs.get("source_path"),
                    self.kwargs.get("target_dir"),
                    target_name=self.kwargs.get("target_name"),
                    overwrite=self.kwargs.get("overwrite", False),
                    progress_callback=self.on_transfer_progress,
                    message_callback=self.progress.emit,
                )
                self.result.emit(self.action, target)
                return

            if self.action == "move":
                target = move_path(
                    self.connection,
                    self.kwargs.get("source_path"),
                    self.kwargs.get("target_dir"),
                    target_name=self.kwargs.get("target_name"),
                    overwrite=self.kwargs.get("overwrite", False),
                    progress_callback=self.on_transfer_progress,
                    message_callback=self.progress.emit,
                )
                self.result.emit(self.action, target)
                return

            if self.action == "delete":
                delete_path(self.connection, self.kwargs.get("path"))
                self.result.emit(self.action, self.kwargs.get("path"))
                return

            raise ValueError(f"Unknown file browser action: {self.action}")
        except Exception as e:
            self.error.emit(str(e))

    def run_offline(self):
        action = self.action
        if action == "roots":
            _offline_local_path(self.sd_root, DEFAULT_ROOT)
            self.result.emit(action, [{"name": "SD Card", "path": DEFAULT_ROOT, "available": True}])
            return
        if action == "list":
            self.result.emit(action, _offline_list_directory(self.sd_root, self.kwargs.get("path", DEFAULT_ROOT)))
            return
        if action == "upload":
            uploaded = []
            for item in self.kwargs.get("upload_items", []):
                source = Path(item.get("local_path"))
                target = _offline_target(self.sd_root, item.get("remote_dir", DEFAULT_ROOT), item.get("target_name") or source.name)
                if target.exists():
                    if not item.get("overwrite", False):
                        raise FileExistsError(f"Target already exists: {target}")
                    _remove_local_target(target)
                _copy_local_item(source, target, self.on_transfer_progress, self.progress.emit)
                uploaded.append(_offline_virtual_path(self.sd_root, target))
            self.result.emit(action, uploaded)
            return
        if action == "download":
            source = _offline_local_path(self.sd_root, self.kwargs.get("remote_path"))
            local_dir = Path(self.kwargs.get("local_dir"))
            local_dir.mkdir(parents=True, exist_ok=True)
            target = local_dir / (self.kwargs.get("target_name") or source.name)
            if target.exists():
                if not self.kwargs.get("overwrite", False):
                    raise FileExistsError(f"Target already exists: {target}")
                _remove_local_target(target)
            _copy_local_item(source, target, self.on_transfer_progress, self.progress.emit)
            self.result.emit(action, str(target))
            return
        if action == "mkdir":
            target = _offline_local_path(self.sd_root, self.kwargs.get("path"))
            target.mkdir()
            self.result.emit(action, self.kwargs.get("path"))
            return
        if action == "rename":
            old_path = _offline_local_path(self.sd_root, self.kwargs.get("old_path"))
            new_path = _offline_local_path(self.sd_root, self.kwargs.get("new_path"))
            if new_path.exists():
                if not self.kwargs.get("overwrite", False):
                    raise FileExistsError(f"Target already exists: {new_path}")
                _remove_local_target(new_path)
            old_path.rename(new_path)
            self.result.emit(action, self.kwargs.get("new_path"))
            return
        if action in {"copy", "move"}:
            source = _offline_local_path(self.sd_root, self.kwargs.get("source_path"))
            target_dir = _offline_local_path(self.sd_root, self.kwargs.get("target_dir"))
            target = target_dir / (self.kwargs.get("target_name") or source.name)
            if source.resolve() == target.resolve():
                raise ValueError("Source and destination are the same.")
            if target.exists():
                if not self.kwargs.get("overwrite", False):
                    raise FileExistsError(f"Target already exists: {target}")
                _remove_local_target(target)
            if action == "move":
                try:
                    shutil.move(str(source), str(target))
                except Exception:
                    _copy_local_item(source, target, self.on_transfer_progress, self.progress.emit)
                    _remove_local_target(source)
            else:
                _copy_local_item(source, target, self.on_transfer_progress, self.progress.emit)
            self.result.emit(action, _offline_virtual_path(self.sd_root, target))
            return
        if action == "delete":
            target = _offline_local_path(self.sd_root, self.kwargs.get("path"))
            if target.resolve() == Path(self.sd_root).expanduser().resolve():
                raise ValueError("The SD Card root cannot be deleted.")
            _remove_local_target(target)
            self.result.emit(action, self.kwargs.get("path"))
            return
        raise ValueError(f"Unknown file manager action: {action}")

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


class FileManagerTab(QWidget):
    CONFLICT_OVERWRITE = "overwrite"
    CONFLICT_KEEP_BOTH = "keep_both"
    CONFLICT_CANCEL = "cancel"
    SORT_COLUMNS = {0: "name", 1: "size", 2: "modified"}
    DEFAULT_FILE_MANAGER_CONFIG = {
        "columns": {
            "name": 520,
            "size": 120,
            "modified": 180,
        },
        "sort_column": "name",
        "sort_descending": False,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.connection = getattr(parent, "connection", None)
        self.config_data = load_config()
        self.file_manager_config = self.load_file_manager_config()
        self.worker = None
        self.current_path = DEFAULT_ROOT
        self.current_root = DEFAULT_ROOT
        self.roots = []
        self.entries = []
        self.busy = False
        self.pending_load_path = None
        self.last_transfer_percent = -1
        self.clipboard_entry = None
        self.clipboard_action = ""
        self.sort_column = self.file_manager_config.get("sort_column", "name")
        self.sort_descending = bool(self.file_manager_config.get("sort_descending", False))
        self._restoring_columns = False
        self._save_columns_timer = QTimer(self)
        self._save_columns_timer.setSingleShot(True)
        self._save_columns_timer.timeout.connect(self.save_file_manager_config)
        self._mode_signature = None
        self._initialized = False
        self._reset_after_worker = False

        self.build_ui()
        self.bind_shortcuts()
        self.update_action_buttons()
        self.append_output("Ready")

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
        self.file_tree.setColumnCount(3)
        self.file_tree.setHeaderLabels(["Name", "Size", "Modified"])
        self.file_tree.setRootIsDecorated(False)
        self.file_tree.setAlternatingRowColors(True)
        self.file_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.file_tree.customContextMenuRequested.connect(self.open_context_menu)
        self.file_tree.itemSelectionChanged.connect(self.update_action_buttons)
        self.file_tree.files_dropped.connect(self.upload_dropped_paths)
        header = self.file_tree.header()
        header.setSectionsClickable(True)
        header.setStretchLastSection(False)
        for column in range(3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        header.sectionClicked.connect(self.on_header_clicked)
        header.sectionResized.connect(self.on_header_resized)
        self.restore_file_tree_columns()
        self.update_sort_indicator()
        root_layout.addWidget(self.file_tree, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.download_button = QPushButton("Download")
        self.copy_button = QPushButton("Copy")
        self.paste_button = QPushButton("Paste")
        self.move_button = QPushButton("Move")
        self.rename_button = QPushButton("Rename")
        self.delete_button = QPushButton("Delete")

        self.download_button.clicked.connect(self.download_selected)
        self.copy_button.clicked.connect(self.copy_selected)
        self.paste_button.clicked.connect(self.paste_clipboard)
        self.move_button.clicked.connect(self.move_selected)
        self.rename_button.clicked.connect(self.rename_selected)
        self.delete_button.clicked.connect(self.delete_selected)

        actions.addWidget(self.download_button)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.paste_button)
        actions.addWidget(self.move_button)
        actions.addWidget(self.rename_button)
        actions.addWidget(self.delete_button)
        actions.addStretch()
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

    def load_file_manager_config(self):
        config = dict(self.DEFAULT_FILE_MANAGER_CONFIG)
        stored = self.config_data.get("file_manager")
        if not isinstance(stored, dict):
            stored = self.config_data.get("file_browser")

        if isinstance(stored, dict):
            config.update({key: value for key, value in stored.items() if key != "columns"})
            stored_columns = stored.get("columns")
            if isinstance(stored_columns, dict):
                columns = dict(self.DEFAULT_FILE_MANAGER_CONFIG["columns"])
                columns.update(stored_columns)
                config["columns"] = columns

        if config.get("sort_column") not in {"name", "size", "modified"}:
            config["sort_column"] = "name"

        config["sort_descending"] = bool(config.get("sort_descending", False))
        return config

    def save_file_manager_config(self):
        if not hasattr(self, "file_tree"):
            return

        columns = self.file_manager_config.get("columns", {})
        header = self.file_tree.header()
        for column, name in self.SORT_COLUMNS.items():
            columns[name] = max(40, int(header.sectionSize(column)))

        self.file_manager_config["columns"] = columns
        self.file_manager_config["sort_column"] = self.sort_column
        self.file_manager_config["sort_descending"] = bool(self.sort_descending)

        config = load_config()
        config["file_manager"] = self.file_manager_config
        config.pop("file_browser", None)
        save_config(config)
        self.config_data = config

    def restore_file_tree_columns(self):
        self._restoring_columns = True
        columns = self.file_manager_config.get("columns", {})
        defaults = self.DEFAULT_FILE_MANAGER_CONFIG["columns"]
        for column, name in self.SORT_COLUMNS.items():
            try:
                width = int(columns.get(name, defaults.get(name, 120)))
            except Exception:
                width = int(defaults.get(name, 120))
            self.file_tree.setColumnWidth(column, max(40, width))
        self._restoring_columns = False

    def shutdown(self):
        self.save_file_manager_config()
        self.reset_session(clear_output=False)
        worker = self.worker
        if worker is not None and worker.isRunning():
            try:
                worker.requestInterruption()
                worker.wait(1500)
            except Exception:
                pass

    def bind_shortcuts(self):
        QShortcut(QKeySequence.StandardKey.Refresh, self, activated=self.refresh_current_path)
        QShortcut(QKeySequence.StandardKey.Copy, self, activated=self.copy_selected)
        QShortcut(QKeySequence.StandardKey.Paste, self, activated=self.paste_clipboard)
        QShortcut(QKeySequence.StandardKey.Cut, self, activated=self.move_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self, activated=self.go_up)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self.delete_selected)
        QShortcut(QKeySequence(Qt.Key.Key_F2), self, activated=self.rename_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self.open_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, activated=self.open_selected)

    def append_output(self, message):
        if message and (message.startswith("Uploading ") or message.startswith("Downloading ") or message.startswith("Copying ")):
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
            self.file_tree,
        ):
            widget.setEnabled(not self.busy)

        self.update_action_buttons()

    def update_action_buttons(self):
        selected = self.selected_entry() if hasattr(self, "file_tree") else None
        has_selection = bool(selected and not selected.get("up"))
        has_clipboard = bool(self.clipboard_entry and self.clipboard_action in {"copy", "move"})
        enabled = not self.busy

        for button in (
            self.download_button,
            self.copy_button,
            self.move_button,
            self.rename_button,
            self.delete_button,
        ):
            button.setEnabled(enabled and has_selection)

        self.paste_button.setEnabled(enabled and has_clipboard)

    def is_offline_mode(self):
        return bool(self.main_window and hasattr(self.main_window, "is_offline_mode") and self.main_window.is_offline_mode())

    def offline_sd_root(self):
        if self.main_window and hasattr(self.main_window, "get_offline_sd_root"):
            return str(self.main_window.get_offline_sd_root() or "")
        return ""

    def mode_available(self):
        if self.is_offline_mode():
            root = self.offline_sd_root()
            return bool(root and Path(root).exists() and Path(root).is_dir())
        return bool(self.connection and self.connection.is_connected())

    def current_mode_signature(self):
        if self.is_offline_mode():
            return ("offline", self.offline_sd_root())
        if self.connection and self.connection.is_connected():
            return ("online", str(getattr(self.connection, "host", "") or ""))
        return ("online", "")

    def start_worker(self, action, **kwargs):
        if self.busy:
            return
        if not self.mode_available():
            if self.is_offline_mode():
                QMessageBox.information(self, "File Manager", "Select an Offline SD Card folder first.")
            else:
                QMessageBox.information(self, "File Manager", "Connect to a MiSTer first before using File Manager.")
            return

        self.set_busy(True)
        self.worker = FileManagerWorker(
            self.connection,
            action,
            offline_mode=self.is_offline_mode(),
            sd_root=self.offline_sd_root(),
            **kwargs,
        )
        self.worker.result.connect(self.on_worker_result)
        self.worker.error.connect(self.on_worker_error)
        self.worker.progress.connect(self.append_output)
        self.worker.transfer_progress.connect(self.on_transfer_progress)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def refresh_roots(self):
        if not self.mode_available():
            self.show_unavailable_state()
            return
        self.append_output("Checking storage...")
        self.start_worker("roots")

    def refresh(self, force=False):
        signature = self.current_mode_signature()
        if signature != self._mode_signature:
            self.reset_session(clear_output=False)
            self._mode_signature = signature
        if not self.mode_available():
            self.show_unavailable_state()
            return
        if not self._initialized or force:
            self.refresh_roots()

    def update_connection_state(self, lightweight=True):
        signature = self.current_mode_signature()
        if signature != self._mode_signature:
            self.reset_session(clear_output=False)
            self._mode_signature = signature
        available = self.mode_available()
        if not available and not self.busy:
            self.show_unavailable_state()
        self.update_action_buttons()

    def show_unavailable_state(self):
        if self.busy:
            return
        self._initialized = False
        self.roots = []
        self.entries = []
        self.storage_combo.blockSignals(True)
        self.storage_combo.clear()
        self.storage_combo.blockSignals(False)
        self.file_tree.clear()
        self.current_root = DEFAULT_ROOT
        self.current_path = DEFAULT_ROOT
        self.path_label.setText(DEFAULT_ROOT)
        self.up_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.upload_button.setEnabled(False)
        self.upload_folder_button.setEnabled(False)
        self.new_folder_button.setEnabled(False)
        for button in self.quick_buttons:
            button.setEnabled(False)
        self.update_action_buttons()

    def reset_session(self, clear_output=False):
        self.current_path = DEFAULT_ROOT
        self.current_root = DEFAULT_ROOT
        self.roots = []
        self.entries = []
        self.pending_load_path = None
        self.clipboard_entry = None
        self.clipboard_action = ""
        self._initialized = False
        if self.worker is not None and self.worker.isRunning():
            self._reset_after_worker = True
        else:
            self._reset_after_worker = False
            if hasattr(self, "storage_combo"):
                self.storage_combo.blockSignals(True)
                self.storage_combo.clear()
                self.storage_combo.blockSignals(False)
            if hasattr(self, "file_tree"):
                self.file_tree.clear()
            if hasattr(self, "path_label"):
                self.path_label.setText(DEFAULT_ROOT)
        if clear_output and hasattr(self, "output_edit"):
            self.output_edit.clear()
            self.append_output("Ready")
        self.update_action_buttons()

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

        if action == "copy":
            self.append_output(f"Copied to: {data}")
            self.pending_load_path = self.current_path
            return

        if action == "move":
            self.append_output(f"Moved to: {data}")
            self.clipboard_entry = None
            self.clipboard_action = ""
            self.update_action_buttons()
            self.pending_load_path = self.current_path
            return

        if action == "delete":
            self.append_output(f"Deleted: {data}")
            self.pending_load_path = self.current_path

    def on_worker_error(self, message):
        self.append_output(f"Error: {message}")
        QMessageBox.warning(self, "File Manager", message)

    def on_worker_finished(self):
        self.set_busy(False)
        self.worker = None
        if self._reset_after_worker:
            self._reset_after_worker = False
            self.reset_session(clear_output=False)
            self.update_connection_state(lightweight=True)
            return
        pending_path = self.pending_load_path
        self.pending_load_path = None
        if pending_path and self.mode_available():
            self.load_path(pending_path)

    def on_transfer_progress(self, transferred, total):
        transferred = max(0, int(transferred or 0))
        total = max(0, int(total or 0))
        if total > 0:
            percent = min(100, int((transferred / total) * 100))
            if percent == 100 or percent - self.last_transfer_percent >= 10:
                self.last_transfer_percent = percent
                self.append_output(f"Progress: {percent}% ({format_size(transferred)} / {format_size(total)})")

    def apply_roots(self, roots):
        self._initialized = True
        self.roots = roots or [{"name": "SD Card", "path": DEFAULT_ROOT, "available": True}]
        for button in self.quick_buttons:
            button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.upload_button.setEnabled(True)
        self.upload_folder_button.setEnabled(True)
        self.new_folder_button.setEnabled(True)
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
        self.populate_file_tree()
        self.append_output(f"Loaded {self.current_path}")
        self.update_action_buttons()

    def populate_file_tree(self):
        self.file_tree.clear()

        if self.current_path != self.current_root:
            up_item = QTreeWidgetItem(["..", "", ""])
            up_item.setData(0, Qt.ItemDataRole.UserRole, {"up": True, "path": parent_path(self.current_path), "is_dir": True})
            self.file_tree.addTopLevelItem(up_item)

        for entry in self.sorted_entries():
            mtime = ""
            if entry.get("mtime"):
                mtime = datetime.fromtimestamp(entry["mtime"]).strftime("%Y-%m-%d %H:%M")

            size = "" if entry.get("is_dir") else format_size(entry.get("size", 0))
            icon_name = "📁 " if entry.get("is_dir") else "📄 "
            item = QTreeWidgetItem([f"{icon_name}{entry.get('name', '')}", size, mtime])
            item.setData(0, Qt.ItemDataRole.UserRole, entry)
            self.file_tree.addTopLevelItem(item)

        self.update_action_buttons()

    def sorted_entries(self):
        entries = list(self.entries or [])
        reverse = bool(self.sort_descending)

        def name_bucket(value):
            name = str(value or "").strip()
            if not name:
                return 0
            first = name[0]
            if first.isdigit():
                return 1
            if first.isalpha():
                return 2
            return 0

        def name_key(entry):
            name = str(entry.get("name", ""))
            return (name_bucket(name), name.casefold())

        def sort_key(entry):
            if self.sort_column == "size":
                return int(entry.get("size", 0) or 0)
            if self.sort_column == "modified":
                return int(entry.get("mtime", 0) or 0)
            return name_key(entry)

        folders = [entry for entry in entries if entry.get("is_dir")]
        files = [entry for entry in entries if not entry.get("is_dir")]
        folders.sort(key=sort_key, reverse=reverse)
        files.sort(key=sort_key, reverse=reverse)
        return folders + files

    def on_header_clicked(self, column):
        sort_column = self.SORT_COLUMNS.get(column)
        if not sort_column:
            return

        if self.sort_column == sort_column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = sort_column
            self.sort_descending = False

        self.update_sort_indicator()
        self.populate_file_tree()
        self.save_file_manager_config()

    def update_sort_indicator(self):
        if not hasattr(self, "file_tree"):
            return
        column = 0
        for index, name in self.SORT_COLUMNS.items():
            if name == self.sort_column:
                column = index
                break
        order = Qt.SortOrder.DescendingOrder if self.sort_descending else Qt.SortOrder.AscendingOrder
        self.file_tree.header().setSortIndicator(column, order)
        self.file_tree.header().setSortIndicatorShown(True)

    def on_header_resized(self, *_):
        if self._restoring_columns:
            return
        self._save_columns_timer.start(400)

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

    def existing_names(self):
        return {entry.get("name", "") for entry in self.entries}

    def unique_name(self, name, existing_names=None):
        existing = set(existing_names or self.existing_names())
        if name not in existing:
            return name

        path = Path(name)
        stem = path.stem if path.suffix else name
        suffix = path.suffix if path.suffix else ""
        for index in range(2, 10000):
            candidate = f"{stem} copy" if index == 2 else f"{stem} copy {index - 1}"
            candidate = f"{candidate}{suffix}"
            if candidate not in existing:
                return candidate
        return name

    def conflict_choice(self, title, message, overwrite_label="Overwrite"):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        box.setText(message)
        overwrite_button = box.addButton(overwrite_label, QMessageBox.ButtonRole.AcceptRole)
        keep_both_button = box.addButton("Keep Both", QMessageBox.ButtonRole.ActionRole)
        cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked == overwrite_button:
            return self.CONFLICT_OVERWRITE
        if clicked == keep_both_button:
            return self.CONFLICT_KEEP_BOTH
        return self.CONFLICT_CANCEL

    def confirm_overwrite(self, target_path, action_name):
        return self.conflict_choice(
            "File Exists",
            f"An item already exists at:\n\n{target_path}\n\nWhat do you want to do?",
            overwrite_label="Overwrite",
        )

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

        upload_items = []
        existing = self.existing_names()
        planned = set(existing)
        for path in valid_paths:
            local_path = Path(path)
            target_name = local_path.name
            overwrite = False
            target_path = join_remote_path(self.current_path, target_name)
            if target_name in planned:
                choice = self.confirm_overwrite(target_path, "upload")
                if choice == self.CONFLICT_CANCEL:
                    return
                if choice == self.CONFLICT_OVERWRITE:
                    overwrite = True
                elif choice == self.CONFLICT_KEEP_BOTH:
                    target_name = self.unique_name(target_name, planned)
            planned.add(target_name)
            upload_items.append(
                {
                    "local_path": str(local_path),
                    "remote_dir": self.current_path,
                    "target_name": target_name,
                    "overwrite": overwrite,
                }
            )

        self.append_output(f"Uploading {len(upload_items)} item{'s' if len(upload_items) != 1 else ''} to {self.current_path}...")
        self.start_worker("upload", upload_items=upload_items)

    def download_selected(self):
        entry = self.selected_entry()
        if not entry or entry.get("up"):
            QMessageBox.information(self, "File Manager", "Select a file or folder to download.")
            return

        local_dir = QFileDialog.getExistingDirectory(self, "Choose Download Folder")
        if not local_dir:
            return

        target_name = entry.get("name", "")
        overwrite = False
        local_target = Path(local_dir) / target_name
        if local_target.exists():
            choice = self.conflict_choice(
                "File Exists",
                f"An item already exists at:\n\n{local_target}\n\nWhat do you want to do?",
                overwrite_label="Overwrite",
            )
            if choice == self.CONFLICT_CANCEL:
                return
            if choice == self.CONFLICT_OVERWRITE:
                overwrite = True
            elif choice == self.CONFLICT_KEEP_BOTH:
                target_name = self.unique_local_name(local_dir, target_name)

        self.append_output(f"Downloading {entry.get('name')}...")
        self.start_worker(
            "download",
            remote_path=entry.get("path"),
            local_dir=local_dir,
            target_name=target_name,
            overwrite=overwrite,
        )

    def unique_local_name(self, local_dir, name):
        local_dir = Path(local_dir)
        if not (local_dir / name).exists():
            return name
        path = Path(name)
        stem = path.stem if path.suffix else name
        suffix = path.suffix if path.suffix else ""
        for index in range(2, 10000):
            candidate = f"{stem} copy" if index == 2 else f"{stem} copy {index - 1}"
            candidate = f"{candidate}{suffix}"
            if not (local_dir / candidate).exists():
                return candidate
        return name

    def create_folder(self):
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        name = name.strip()
        if not ok or not name:
            return
        if "/" in name or "\\" in name:
            QMessageBox.warning(self, "File Manager", "Folder name cannot contain slashes.")
            return
        if name in self.existing_names():
            QMessageBox.warning(self, "File Manager", "A file or folder with that name already exists.")
            return
        path = join_remote_path(self.current_path, name)
        self.start_worker("mkdir", path=path)

    def rename_selected(self):
        entry = self.selected_entry()
        if not entry or entry.get("up"):
            QMessageBox.information(self, "File Manager", "Select a file or folder to rename.")
            return

        old_name = entry.get("name", "")
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old_name)
        new_name = new_name.strip()
        if not ok or not new_name or new_name == old_name:
            return
        if "/" in new_name or "\\" in new_name:
            QMessageBox.warning(self, "File Manager", "Name cannot contain slashes.")
            return

        overwrite = False
        if new_name in self.existing_names():
            choice = self.conflict_choice(
                "File Exists",
                f"An item named '{new_name}' already exists.\n\nWhat do you want to do?",
                overwrite_label="Overwrite",
            )
            if choice == self.CONFLICT_CANCEL:
                return
            if choice == self.CONFLICT_OVERWRITE:
                overwrite = True
            elif choice == self.CONFLICT_KEEP_BOTH:
                new_name = self.unique_name(new_name)

        new_path = join_remote_path(self.current_path, new_name)
        self.start_worker("rename", old_path=entry.get("path"), new_path=new_path, overwrite=overwrite)

    def copy_selected(self):
        entry = self.selected_entry()
        if not entry or entry.get("up"):
            QMessageBox.information(self, "File Manager", "Select a file or folder to copy.")
            return
        self.clipboard_entry = dict(entry)
        self.clipboard_action = "copy"
        self.append_output(f"Copied to clipboard: {entry.get('name')}")
        self.update_action_buttons()

    def move_selected(self):
        entry = self.selected_entry()
        if not entry or entry.get("up"):
            QMessageBox.information(self, "File Manager", "Select a file or folder to move.")
            return
        self.clipboard_entry = dict(entry)
        self.clipboard_action = "move"
        self.append_output(f"Ready to move: {entry.get('name')}. Open the destination folder and choose Paste.")
        self.update_action_buttons()

    def paste_clipboard(self):
        if not self.clipboard_entry or self.clipboard_action not in {"copy", "move"}:
            QMessageBox.information(self, "File Manager", "Copy or move a file or folder first.")
            return

        source_path = self.clipboard_entry.get("path")
        source_name = self.clipboard_entry.get("name", "")
        if not source_path or not source_name:
            return

        target_name = source_name
        overwrite = False
        if target_name in self.existing_names():
            target_path = join_remote_path(self.current_path, target_name)
            choice = self.confirm_overwrite(target_path, "paste")
            if choice == self.CONFLICT_CANCEL:
                return
            if choice == self.CONFLICT_OVERWRITE:
                overwrite = True
            elif choice == self.CONFLICT_KEEP_BOTH:
                target_name = self.unique_name(target_name)

        action = self.clipboard_action
        self.append_output(f"{'Moving' if action == 'move' else 'Copying'} {source_name} to {self.current_path}...")
        self.start_worker(
            action,
            source_path=source_path,
            target_dir=self.current_path,
            target_name=target_name,
            overwrite=overwrite,
        )

    def delete_selected(self):
        entry = self.selected_entry()
        if not entry or entry.get("up"):
            QMessageBox.information(self, "File Manager", "Select a file or folder to delete.")
            return

        name = entry.get("name", "")
        path = entry.get("path", "")
        reply = QMessageBox.question(
            self,
            "Delete",
            f"Delete '{name}' from the {'SD Card' if self.is_offline_mode() else 'MiSTer'}?\n\n{path}\n\nThis cannot be undone from MiSTer Companion.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.start_worker("delete", path=path)

    def open_context_menu(self, position):
        menu = QMenu(self)
        entry = self.selected_entry()

        open_action = QAction("Open", self)
        download_action = QAction("Download", self)
        copy_action = QAction("Copy", self)
        paste_action = QAction("Paste", self)
        move_action = QAction("Move", self)
        rename_action = QAction("Rename", self)
        delete_action = QAction("Delete", self)
        new_folder_action = QAction("New Folder", self)
        upload_action = QAction("Upload Here", self)
        refresh_action = QAction("Refresh", self)

        open_action.triggered.connect(self.open_selected)
        download_action.triggered.connect(self.download_selected)
        copy_action.triggered.connect(self.copy_selected)
        paste_action.triggered.connect(self.paste_clipboard)
        move_action.triggered.connect(self.move_selected)
        rename_action.triggered.connect(self.rename_selected)
        delete_action.triggered.connect(self.delete_selected)
        new_folder_action.triggered.connect(self.create_folder)
        upload_action.triggered.connect(self.upload_files_dialog)
        refresh_action.triggered.connect(self.refresh_current_path)

        if entry and entry.get("is_dir"):
            menu.addAction(open_action)
        menu.addAction(download_action)
        menu.addSeparator()
        menu.addAction(copy_action)
        menu.addAction(paste_action)
        menu.addAction(move_action)
        menu.addSeparator()
        menu.addAction(upload_action)
        menu.addAction(new_folder_action)
        menu.addSeparator()
        menu.addAction(rename_action)
        menu.addAction(delete_action)
        menu.addSeparator()
        menu.addAction(refresh_action)

        has_selection = bool(entry and not entry.get("up"))
        has_clipboard = bool(self.clipboard_entry and self.clipboard_action in {"copy", "move"})
        enabled = not self.busy

        download_action.setEnabled(enabled and has_selection)
        copy_action.setEnabled(enabled and has_selection)
        move_action.setEnabled(enabled and has_selection)
        rename_action.setEnabled(enabled and has_selection)
        delete_action.setEnabled(enabled and has_selection)
        paste_action.setEnabled(enabled and has_clipboard)
        upload_action.setEnabled(enabled)
        new_folder_action.setEnabled(enabled)
        refresh_action.setEnabled(enabled)

        menu.exec(self.file_tree.viewport().mapToGlobal(position))

from __future__ import annotations

import posixpath
from pathlib import PurePosixPath

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.file_browser import available_roots, clamp_to_root, list_directory, parent_path


class RemoteFilePickerDialog(QDialog):
    MODE_OPEN_FILE = "open_file"
    MODE_OPEN_FILES = "open_files"
    MODE_DIRECTORY = "directory"
    MODE_SAVE_FILE = "save_file"

    def __init__(self, connection, parent=None, *, mode=MODE_OPEN_FILE, title="Browse MiSTer", start_path="/media/fat", filters=None, default_name=""):
        super().__init__(parent)
        self.connection = connection
        self.mode = mode
        self.filters = {ext.lower() for ext in (filters or [])}
        self.current_path = clamp_to_root(start_path)
        self.selected_paths: list[str] = []
        self.setWindowTitle(title)
        self.resize(760, 520)

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Storage:"))
        self.root_combo = QComboBox()
        top.addWidget(self.root_combo)
        self.up_button = QPushButton("Up")
        top.addWidget(self.up_button)
        top.addStretch(1)
        layout.addLayout(top)

        self.path_label = QLabel(self.current_path)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.path_label)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
            if mode == self.MODE_OPEN_FILES
            else QAbstractItemView.SelectionMode.SingleSelection
        )
        layout.addWidget(self.list_widget, 1)

        self.name_edit = None
        if mode == self.MODE_SAVE_FILE:
            row = QHBoxLayout()
            row.addWidget(QLabel("File name:"))
            self.name_edit = QLineEdit(default_name)
            row.addWidget(self.name_edit, 1)
            layout.addLayout(row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save" if mode == self.MODE_SAVE_FILE else "Select")
        layout.addWidget(self.buttons)

        self.root_combo.currentIndexChanged.connect(self._root_changed)
        self.up_button.clicked.connect(self._go_up)
        self.list_widget.itemDoubleClicked.connect(self._activate_item)
        self.buttons.accepted.connect(self._accept_selection)
        self.buttons.rejected.connect(self.reject)

        self._populate_roots()
        self._load_directory(self.current_path)

    def _populate_roots(self):
        self.root_combo.blockSignals(True)
        self.root_combo.clear()
        try:
            roots = available_roots(self.connection)
        except Exception as exc:
            QMessageBox.critical(self, "MiSTer Browser", str(exc))
            roots = [{"name": "SD Card", "path": "/media/fat", "available": True}]
        for root in roots:
            if root.get("available"):
                self.root_combo.addItem(root["name"], root["path"])
        for i in range(self.root_combo.count()):
            root = self.root_combo.itemData(i)
            if self.current_path == root or self.current_path.startswith(root + "/"):
                self.root_combo.setCurrentIndex(i)
                break
        self.root_combo.blockSignals(False)

    def _root_changed(self, index):
        if index >= 0:
            self._load_directory(self.root_combo.itemData(index))

    def _load_directory(self, path):
        try:
            result = list_directory(self.connection, path)
        except Exception as exc:
            QMessageBox.critical(self, "MiSTer Browser", f"Could not browse the MiSTer:\n\n{exc}")
            return
        self.current_path = result["path"]
        self.path_label.setText(self.current_path)
        self.list_widget.clear()
        for entry in result["entries"]:
            if not entry["is_dir"] and self.filters:
                if PurePosixPath(entry["name"]).suffix.lower() not in self.filters:
                    continue
            text = f"📁  {entry['name']}" if entry["is_dir"] else entry["name"]
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.list_widget.addItem(item)

    def _go_up(self):
        self._load_directory(parent_path(self.current_path))

    def _activate_item(self, item):
        entry = item.data(Qt.ItemDataRole.UserRole)
        if entry and entry["is_dir"]:
            self._load_directory(entry["path"])
        elif self.mode in {self.MODE_OPEN_FILE, self.MODE_OPEN_FILES}:
            self._accept_selection()

    def _accept_selection(self):
        if self.mode == self.MODE_DIRECTORY:
            items = self.list_widget.selectedItems()
            if items:
                entry = items[0].data(Qt.ItemDataRole.UserRole)
                if entry and entry["is_dir"]:
                    self.selected_paths = [entry["path"]]
                else:
                    self.selected_paths = [self.current_path]
            else:
                self.selected_paths = [self.current_path]
            self.accept()
            return

        if self.mode == self.MODE_SAVE_FILE:
            name = (self.name_edit.text() if self.name_edit else "").strip()
            if not name or "/" in name or "\\" in name or name in {".", ".."}:
                QMessageBox.warning(self, "MiSTer Browser", "Enter a valid file name.")
                return
            self.selected_paths = [posixpath.join(self.current_path.rstrip("/"), name)]
            self.accept()
            return

        selected = []
        for item in self.list_widget.selectedItems():
            entry = item.data(Qt.ItemDataRole.UserRole)
            if entry and not entry["is_dir"]:
                selected.append(entry["path"])
        if not selected:
            QMessageBox.warning(self, "MiSTer Browser", "Select a file.")
            return
        self.selected_paths = selected
        self.accept()

    @classmethod
    def get_open_file(cls, connection, parent=None, **kwargs):
        dlg = cls(connection, parent, mode=cls.MODE_OPEN_FILE, **kwargs)
        return dlg.selected_paths[0] if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_paths else ""

    @classmethod
    def get_open_files(cls, connection, parent=None, **kwargs):
        dlg = cls(connection, parent, mode=cls.MODE_OPEN_FILES, **kwargs)
        return dlg.selected_paths if dlg.exec() == QDialog.DialogCode.Accepted else []

    @classmethod
    def get_directory(cls, connection, parent=None, **kwargs):
        dlg = cls(connection, parent, mode=cls.MODE_DIRECTORY, **kwargs)
        return dlg.selected_paths[0] if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_paths else ""

    @classmethod
    def get_save_file(cls, connection, parent=None, **kwargs):
        dlg = cls(connection, parent, mode=cls.MODE_SAVE_FILE, **kwargs)
        return dlg.selected_paths[0] if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_paths else ""

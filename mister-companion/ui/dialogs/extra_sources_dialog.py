from copy import deepcopy

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from core.update_all_config import normalize_database_id, parse_custom_source_entry


class ExtraSourceEditorDialog(QDialog):
    def __init__(self, source=None, existing_ids=None, parent=None):
        super().__init__(parent)
        self.original_id = str((source or {}).get("database_id") or "").lower()
        self.existing_ids = {str(value).lower() for value in (existing_ids or [])}
        self.source = deepcopy(source or {})

        self.setWindowTitle("Edit Extra Source" if source else "Add Extra Source")
        self.setMinimumWidth(540)

        layout = QVBoxLayout(self)
        description = QLabel(
            "Enter the name shown in the source list and the Downloader database details."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QFormLayout()
        self.name_edit = QLineEdit(str(self.source.get("display_name") or ""))
        self.id_edit = QLineEdit(str(self.source.get("database_id") or ""))
        self.url_edit = QLineEdit(str(self.source.get("db_url") or ""))
        self.id_edit.setPlaceholderText("[owner/database]")
        self.url_edit.setPlaceholderText("https://example.com/db.json.zip")
        form.addRow("Display Name:", self.name_edit)
        if source is None:
            self.paste_edit = QTextEdit()
            self.paste_edit.setPlaceholderText(
                "[owner/database]\n"
                "db_url = https://example.com/db.json.zip"
            )
            self.paste_edit.setMaximumHeight(100)
            form.addRow("Paste INI Entry (Optional):", self.paste_edit)
            self.paste_edit.textChanged.connect(self._parse_pasted_entry)
        else:
            self.paste_edit = None
        form.addRow("Database ID:", self.id_edit)
        form.addRow("Database URL:", self.url_edit)
        layout.addLayout(form)

        hint = QLabel("Square brackets are added to the database ID automatically when needed.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch()
        save_button = QPushButton("Save")
        cancel_button = QPushButton("Cancel")
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

        save_button.clicked.connect(self._save)
        cancel_button.clicked.connect(self.reject)

    def _parse_pasted_entry(self):
        if self.paste_edit is None:
            return
        parsed = parse_custom_source_entry(self.paste_edit.toPlainText())
        if parsed is None:
            return
        self.id_edit.setText(parsed["database_id"])
        self.url_edit.setText(parsed["db_url"])
        self.source["ini_block"] = parsed["ini_block"]

    def _save(self):
        display_name = self.name_edit.text().strip()
        if not display_name:
            QMessageBox.warning(self, "Extra Source", "Enter a display name.")
            return
        try:
            database_id = normalize_database_id(self.id_edit.text())
        except ValueError as error:
            QMessageBox.warning(self, "Extra Source", str(error))
            return
        if database_id.lower() in self.existing_ids and database_id.lower() != self.original_id:
            QMessageBox.warning(self, "Extra Source", "That database ID is already in use.")
            return

        db_url = self.url_edit.text().strip()
        parsed_url = QUrl(db_url)
        if not db_url or not parsed_url.isValid() or parsed_url.scheme().lower() not in ("http", "https") or not parsed_url.host():
            QMessageBox.warning(self, "Extra Source", "Enter a valid HTTP or HTTPS database URL.")
            return

        self.source.update({
            "display_name": display_name,
            "database_id": database_id,
            "db_url": db_url,
        })
        self.accept()

    def get_source(self):
        return deepcopy(self.source)


class ManageExtraSourcesDialog(QDialog):
    def __init__(self, sources, parent=None):
        super().__init__(parent)
        self.sources = deepcopy(sources)
        self.setWindowTitle("Manage Extra Sources")
        self.resize(820, 430)
        self.setMinimumSize(650, 320)

        layout = QVBoxLayout(self)
        description = QLabel(
            "Rename, edit, or remove sources. Enable or disable them from the main Update_All configuration window."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.list = QTreeWidget()
        self.list.setColumnCount(3)
        self.list.setHeaderLabels(["Display Name", "Database ID", "Database URL"])
        self.list.setRootIsDecorated(False)
        self.list.setAlternatingRowColors(True)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.list.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.list)

        buttons = QHBoxLayout()
        edit_button = QPushButton("Edit Selected")
        remove_button = QPushButton("Remove Selected")
        close_button = QPushButton("Close")
        buttons.addWidget(edit_button)
        buttons.addWidget(remove_button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        edit_button.clicked.connect(self._edit_selected)
        remove_button.clicked.connect(self._remove_selected)
        close_button.clicked.connect(self.accept)
        self.list.itemDoubleClicked.connect(lambda *_: self._edit_selected())
        self._refresh()

    def _refresh(self, selected_index=None):
        self.list.clear()
        for index, source in enumerate(self.sources):
            item = QTreeWidgetItem([
                str(source.get("display_name") or ""),
                str(source.get("database_id") or ""),
                str(source.get("db_url") or ""),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, index)
            self.list.addTopLevelItem(item)
        if selected_index is not None and 0 <= selected_index < self.list.topLevelItemCount():
            self.list.setCurrentItem(self.list.topLevelItem(selected_index))

    def _selected_index(self):
        item = self.list.currentItem()
        return None if item is None else int(item.data(0, Qt.ItemDataRole.UserRole))

    def _edit_selected(self):
        index = self._selected_index()
        if index is None:
            QMessageBox.information(self, "Manage Extra Sources", "Select a source to edit.")
            return
        dialog = ExtraSourceEditorDialog(
            self.sources[index],
            [source.get("database_id", "") for source in self.sources],
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.sources[index] = dialog.get_source()
            self._refresh(index)

    def _remove_selected(self):
        index = self._selected_index()
        if index is None:
            QMessageBox.information(self, "Manage Extra Sources", "Select a source to remove.")
            return
        name = self.sources[index].get("display_name") or self.sources[index].get("database_id")
        answer = QMessageBox.question(
            self,
            "Remove Extra Source",
            f'Remove "{name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            del self.sources[index]
            self._refresh(min(index, len(self.sources) - 1))

    def get_sources(self):
        return deepcopy(self.sources)

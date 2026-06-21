from core.custom_themes import load_custom_themes, themes_dir
from core.open_helpers import open_local_folder

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)


class ThemePickerDialog(QDialog):
    theme_applied = pyqtSignal(str)

    def __init__(self, current_theme="auto", parent=None):
        super().__init__(parent)

        self.current_theme = str(current_theme or "auto").strip().lower()
        self.selected_theme = self.current_theme
        self.custom_themes = []
        self.invalid_themes = []
        self._syncing_selection = False

        self.setWindowTitle("Theme Picker")
        self.setMinimumSize(560, 420)

        self.build_ui()
        self.load_themes()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        built_in_label = QLabel("Built-in Themes")
        built_in_label.setStyleSheet("font-weight: bold;")
        main_layout.addWidget(built_in_label)

        self.built_in_list = self.create_theme_list()
        self.built_in_list.itemSelectionChanged.connect(self.on_built_in_selection_changed)
        self.built_in_list.itemDoubleClicked.connect(self.apply_selected)
        self.built_in_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main_layout.addWidget(self.built_in_list)

        custom_label = QLabel("Custom Themes")
        custom_label.setStyleSheet("font-weight: bold;")
        main_layout.addWidget(custom_label)

        self.custom_list = self.create_theme_list()
        self.custom_list.itemSelectionChanged.connect(self.on_custom_selection_changed)
        self.custom_list.itemDoubleClicked.connect(self.apply_selected)
        self.custom_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        main_layout.addWidget(self.custom_list, 1)

        self.invalid_label = QLabel("Invalid Themes")
        self.invalid_label.setStyleSheet("font-weight: bold;")
        main_layout.addWidget(self.invalid_label)

        self.invalid_text = QTextEdit()
        self.invalid_text.setReadOnly(True)
        self.invalid_text.setMaximumHeight(100)
        main_layout.addWidget(self.invalid_text)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        self.open_folder_button = QPushButton("Open Themes Folder")
        self.refresh_button = QPushButton("Refresh Themes")
        self.apply_button = QPushButton("Apply")
        button_row.addWidget(self.open_folder_button)
        button_row.addWidget(self.refresh_button)
        button_row.addStretch()
        button_row.addWidget(self.apply_button)

        main_layout.addLayout(button_row)

        self.open_folder_button.clicked.connect(self.open_themes_folder)
        self.refresh_button.clicked.connect(self.load_themes)
        self.apply_button.clicked.connect(self.apply_selected)

    def create_theme_list(self):
        widget = QTreeWidget()
        widget.setColumnCount(2)
        widget.setHeaderHidden(True)
        widget.setRootIsDecorated(False)
        widget.setItemsExpandable(False)
        widget.setUniformRowHeights(True)
        widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        widget.setAlternatingRowColors(True)
        widget.setIndentation(0)
        widget.setColumnWidth(0, 180)
        return widget

    def add_theme_item(self, widget, label, theme_key, detail=""):
        item = QTreeWidgetItem([label, detail])
        item.setData(0, Qt.ItemDataRole.UserRole, theme_key)
        widget.addTopLevelItem(item)

        if theme_key == self.current_theme:
            widget.setCurrentItem(item)
            item.setSelected(True)

        return item

    def add_disabled_item(self, widget, label, detail=""):
        item = QTreeWidgetItem([label, detail])
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setData(0, Qt.ItemDataRole.UserRole, None)
        widget.addTopLevelItem(item)
        return item

    def load_themes(self):
        self.custom_themes, self.invalid_themes = load_custom_themes()
        self.built_in_list.clear()
        self.custom_list.clear()

        self.add_theme_item(
            self.built_in_list,
            "Auto",
            "auto",
            "Follow the system appearance",
        )
        self.add_theme_item(
            self.built_in_list,
            "Light",
            "light",
            "Built-in light theme",
        )
        self.add_theme_item(
            self.built_in_list,
            "Dark",
            "dark",
            "Built-in dark theme",
        )

        if self.custom_themes:
            for theme in self.custom_themes:
                self.add_theme_item(
                    self.custom_list,
                    theme.get("name", theme.get("id", "Custom Theme")),
                    theme.get("key"),
                    f"by {theme.get('author', 'Unknown')}",
                )
        else:
            self.add_disabled_item(
                self.custom_list,
                "No custom themes found",
                "Add JSON themes to the themes folder and click Refresh Themes",
            )

        self.resize_theme_columns(self.built_in_list)
        self.resize_theme_columns(self.custom_list)
        self.update_built_in_list_height()
        self.update_invalid_themes()
        self.on_selection_changed()

    def resize_theme_columns(self, widget):
        widget.resizeColumnToContents(0)
        width = max(widget.columnWidth(0), 180)
        widget.setColumnWidth(0, width)

    def update_built_in_list_height(self):
        rows = max(1, self.built_in_list.topLevelItemCount())
        row_height = self.built_in_list.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 24

        frame = self.built_in_list.frameWidth() * 2
        margins = 8
        height = (row_height * rows) + frame + margins
        self.built_in_list.setMinimumHeight(height)
        self.built_in_list.setMaximumHeight(height)

    def update_invalid_themes(self):
        if not self.invalid_themes:
            self.invalid_label.hide()
            self.invalid_text.hide()
            self.invalid_text.clear()
            return

        self.invalid_label.show()
        self.invalid_text.show()
        lines = []
        for item in self.invalid_themes:
            lines.append(f"{item.get('file', 'theme.json')}: {item.get('error', 'Invalid theme')}")
        self.invalid_text.setPlainText("\n".join(lines))

    def on_built_in_selection_changed(self):
        if self._syncing_selection:
            return

        self._syncing_selection = True
        if self.built_in_list.currentItem() is not None:
            self.custom_list.clearSelection()
            self.custom_list.setCurrentItem(None)
        self._syncing_selection = False
        self.on_selection_changed()

    def on_custom_selection_changed(self):
        if self._syncing_selection:
            return

        self._syncing_selection = True
        if self.custom_list.currentItem() is not None:
            self.built_in_list.clearSelection()
            self.built_in_list.setCurrentItem(None)
        self._syncing_selection = False
        self.on_selection_changed()

    def active_item(self):
        item = self.custom_list.currentItem()
        if item is not None and item.isSelected():
            return item

        item = self.built_in_list.currentItem()
        if item is not None and item.isSelected():
            return item

        return None

    def on_selection_changed(self):
        item = self.active_item()
        theme_key = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        self.apply_button.setEnabled(bool(theme_key))

    def apply_selected(self):
        item = self.active_item()
        if item is None:
            return

        theme_key = item.data(0, Qt.ItemDataRole.UserRole)
        if not theme_key:
            return

        self.selected_theme = str(theme_key).strip().lower()
        self.current_theme = self.selected_theme
        self.theme_applied.emit(self.selected_theme)

    def open_themes_folder(self):
        try:
            open_local_folder(themes_dir(create=True))
        except Exception as e:
            QMessageBox.warning(self, "Open Themes Folder", str(e))

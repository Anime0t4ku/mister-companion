from core.custom_themes import load_custom_themes, themes_dir
from core.open_helpers import open_local_folder
from core.theme_store import (
    download_preview,
    install_store_theme,
    is_store_installed,
    is_theme_installed,
    load_store_index,
    uninstall_store_theme,
)

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class StoreIndexWorker(QThread):
    loaded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def run(self):
        try:
            self.loaded.emit(load_store_index())
        except Exception as e:
            self.failed.emit(str(e))


class PreviewLoaderWorker(QThread):
    preview_loaded = pyqtSignal(str, bytes)

    def __init__(self, entries, cached_ids=None, parent=None):
        super().__init__(parent)
        self.entries = list(entries or [])
        self.cached_ids = set(cached_ids or [])
        self._stopped = False

    def stop(self):
        self._stopped = True

    def run(self):
        for entry in self.entries:
            if self._stopped:
                return

            theme_id = str(entry.get("id", "")).strip()
            preview_url = str(entry.get("preview_url", "")).strip()

            if not theme_id or not preview_url or theme_id in self.cached_ids:
                continue

            try:
                data = download_preview(preview_url)
            except Exception:
                continue

            if self._stopped:
                return

            if data:
                self.preview_loaded.emit(theme_id, data)


class ClickablePreviewLabel(QLabel):
    clicked = pyqtSignal()

    NORMAL_STYLE = "border: 1px solid palette(mid); border-radius: 6px; padding: 1px;"
    HOVER_STYLE = "border: 2px solid palette(highlight); border-radius: 6px; padding: 0px;"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(self.NORMAL_STYLE)

    def enterEvent(self, event):
        if self.isEnabled():
            self.setStyleSheet(self.HOVER_STYLE)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(self.NORMAL_STYLE)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class PreviewDialog(QDialog):
    def __init__(self, title, pixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(720, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if pixmap is not None and not pixmap.isNull():
            image_label.setPixmap(
                pixmap.scaled(
                    1100,
                    700,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        layout.addWidget(image_label, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)


class ThemePickerDialog(QDialog):
    theme_applied = pyqtSignal(str)

    def __init__(self, current_theme="auto", parent=None):
        super().__init__(parent)

        self.current_theme = str(current_theme or "auto").strip().lower()
        self.selected_theme = self.current_theme
        self.custom_themes = []
        self.invalid_themes = []
        self.store_themes = []
        self.store_loaded = False
        self.store_loading = False
        self.store_error = ""
        self.preview_cache = {}
        self.preview_labels = {}
        self.preview_worker = None
        self.store_worker = None
        self._syncing_selection = False

        self.setWindowTitle("Theme Picker")
        self.setMinimumSize(760, 580)

        self.build_ui()
        self.load_themes()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.installed_tab = QWidget()
        self.store_tab = QWidget()
        self.tabs.addTab(self.installed_tab, "Installed Themes")
        self.tabs.addTab(self.store_tab, "Theme Downloader")
        main_layout.addWidget(self.tabs, 1)

        self.build_installed_tab()
        self.build_store_tab()

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
        self.refresh_button.clicked.connect(self.refresh_current_tab)
        self.apply_button.clicked.connect(self.apply_selected)
        self.tabs.currentChanged.connect(self.on_tab_changed)

    def build_installed_tab(self):
        main_layout = QVBoxLayout(self.installed_tab)
        main_layout.setContentsMargins(0, 0, 0, 0)
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

    def build_store_tab(self):
        main_layout = QVBoxLayout(self.store_tab)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        store_label = QLabel("Theme Downloader")
        store_label.setStyleSheet("font-weight: bold;")
        header_row.addWidget(store_label)
        header_row.addStretch()

        header_row.addWidget(QLabel("Show:"))
        self.store_filter_combo = QComboBox()
        self.store_filter_combo.addItem("Official & Community", "both")
        self.store_filter_combo.addItem("Official", "official")
        self.store_filter_combo.addItem("Community", "community")
        self.store_filter_combo.currentIndexChanged.connect(self.render_store_cards)
        header_row.addWidget(self.store_filter_combo)

        header_row.addWidget(QLabel("Sort:"))
        self.store_sort_combo = QComboBox()
        self.store_sort_combo.addItem("Name", "name")
        self.store_sort_combo.addItem("Date Added", "date")
        self.store_sort_combo.currentIndexChanged.connect(self.render_store_cards)
        header_row.addWidget(self.store_sort_combo)

        main_layout.addLayout(header_row)

        self.store_status_label = QLabel("Open the Theme Downloader to load official and community themes from GitHub.")
        self.store_status_label.setWordWrap(True)
        main_layout.addWidget(self.store_status_label)

        self.store_scroll = QScrollArea()
        self.store_scroll.setWidgetResizable(True)
        self.store_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.store_container = QWidget()
        self.store_layout = QVBoxLayout(self.store_container)
        self.store_layout.setContentsMargins(0, 0, 0, 0)
        self.store_layout.setSpacing(10)
        self.store_scroll.setWidget(self.store_container)

        main_layout.addWidget(self.store_scroll, 1)

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
                "Add JSON themes to the themes folder or install themes from the Theme Downloader",
            )

        self.resize_theme_columns(self.built_in_list)
        self.resize_theme_columns(self.custom_list)
        self.update_built_in_list_height()
        self.update_invalid_themes()
        self.on_selection_changed()

        if self.store_loaded:
            self.render_store_cards()

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

    def load_store(self, force=False):
        if self.store_loading:
            return
        if self.store_loaded and not force:
            return

        self.store_loading = True
        self.store_error = ""
        self.store_status_label.setText("Loading Theme Downloader...")
        self.set_store_controls_enabled(False)

        if force:
            self.store_loaded = False
            self.store_themes = []
            self.preview_cache = {}
            self.render_store_cards()

        self.store_worker = StoreIndexWorker(self)
        self.store_worker.loaded.connect(self.on_store_loaded)
        self.store_worker.failed.connect(self.on_store_failed)
        self.store_worker.finished.connect(self.on_store_worker_finished)
        self.store_worker.start()

    def on_store_loaded(self, themes):
        self.store_themes = list(themes or [])
        self.store_loaded = True
        self.store_error = ""
        self.render_store_cards()
        self.start_preview_loader()

    def on_store_failed(self, message):
        self.store_themes = []
        self.store_loaded = False
        self.store_error = message
        self.store_status_label.setText(f"Unable to load the Theme Downloader.\n{message}")
        self.render_store_cards()

    def on_store_worker_finished(self):
        self.store_loading = False
        self.set_store_controls_enabled(True)
        self.update_refresh_button_text()
        self.store_worker = None

    def set_store_controls_enabled(self, enabled):
        self.store_filter_combo.setEnabled(enabled)
        self.store_sort_combo.setEnabled(enabled)
        self.refresh_button.setEnabled(enabled)

    def filtered_store_themes(self):
        entries = list(self.store_themes or [])
        category_filter = self.store_filter_combo.currentData() or "both"

        if category_filter in {"official", "community"}:
            entries = [entry for entry in entries if entry.get("category") == category_filter]

        sort_mode = self.store_sort_combo.currentData() or "name"
        if sort_mode == "date":
            entries.sort(
                key=lambda entry: (
                    str(entry.get("date_added", "")),
                    str(entry.get("name", "")).lower(),
                ),
                reverse=True,
            )
        else:
            entries.sort(key=lambda entry: str(entry.get("name", entry.get("id", ""))).lower())

        return entries

    def render_store_cards(self):
        self.clear_store_cards()
        self.preview_labels = {}

        if self.store_loading and not self.store_themes:
            self.store_status_label.setText("Loading Theme Downloader...")
            self.store_layout.addStretch()
            return

        if self.store_error:
            self.store_layout.addStretch()
            return

        if not self.store_loaded:
            self.store_status_label.setText("Open the Theme Downloader to load official and community themes from GitHub.")
            self.store_layout.addStretch()
            return

        entries = self.filtered_store_themes()

        if not self.store_themes:
            self.store_status_label.setText("No themes are currently available in the Theme Downloader.")
            self.store_layout.addStretch()
            return

        if not entries:
            self.store_status_label.setText("No themes match the current filter.")
            self.store_layout.addStretch()
            return

        self.store_status_label.setText("Install official and community themes directly from GitHub.")

        for entry in entries:
            self.add_store_card(entry)

        self.store_layout.addStretch()

    def clear_store_cards(self):
        while self.store_layout.count():
            item = self.store_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def add_store_card(self, entry):
        card = QFrame()
        card.setObjectName("ThemeStoreCard")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(card)
        row.setContentsMargins(10, 10, 10, 10)
        row.setSpacing(12)

        preview = ClickablePreviewLabel()
        preview.setFixedSize(180, 100)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.clicked.connect(lambda item=entry: self.open_preview_dialog(item))

        theme_id = str(entry.get("id", "")).strip()
        if theme_id in self.preview_cache:
            self.set_preview_pixmap(preview, self.preview_cache[theme_id])
        elif str(entry.get("preview_url", "")).strip():
            preview.setText("Loading Preview")
            preview.setToolTip("Preview is loading")
        else:
            preview.setText("No Preview")
            preview.setToolTip("")

        self.preview_labels[theme_id] = preview
        row.addWidget(preview)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        name_label = QLabel(entry.get("name", entry.get("id", "Theme")))
        name_label.setStyleSheet("font-weight: bold;")
        author_label = QLabel(f"by {entry.get('author', 'Unknown')}")
        category_label = QLabel("Official" if entry.get("category") == "official" else "Community")

        date_added = str(entry.get("date_added", "")).strip()
        date_label = QLabel(f"Date added: {date_added}" if date_added else "Date added: Unknown")

        installed = is_theme_installed(entry.get("id"))
        store_installed = is_store_installed(entry.get("id"))
        if store_installed:
            source_label = QLabel("Installed from Theme Downloader")
        elif installed:
            source_label = QLabel("Installed locally")
        else:
            source_label = QLabel("Not installed")

        info_layout.addWidget(name_label)
        info_layout.addWidget(author_label)
        info_layout.addWidget(category_label)
        info_layout.addWidget(date_label)
        info_layout.addWidget(source_label)
        info_layout.addStretch()
        row.addLayout(info_layout, 1)

        if store_installed:
            button_text = "Uninstall"
            button_enabled = True
        elif installed:
            button_text = "Installed"
            button_enabled = False
        else:
            button_text = "Install"
            button_enabled = True

        action_button = QPushButton(button_text)
        action_button.setMinimumWidth(110)
        action_button.setEnabled(button_enabled)
        action_button.clicked.connect(lambda checked=False, item=entry: self.handle_store_action(item))
        row.addWidget(action_button)

        self.store_layout.addWidget(card)

    def set_preview_pixmap(self, label, pixmap):
        if pixmap is None or pixmap.isNull():
            label.setText("No Preview")
            label.setPixmap(QPixmap())
            label.setToolTip("")
            return

        label.setPixmap(
            pixmap.scaled(
                label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        label.setText("")
        label.setToolTip("Click to view larger preview")

    def start_preview_loader(self):
        if self.preview_worker is not None and self.preview_worker.isRunning():
            self.preview_worker.stop()
            self.preview_worker.wait(1000)

        entries = [entry for entry in self.store_themes if str(entry.get("preview_url", "")).strip()]
        if not entries:
            return

        self.preview_worker = PreviewLoaderWorker(entries, self.preview_cache.keys(), self)
        self.preview_worker.preview_loaded.connect(self.on_preview_loaded)
        self.preview_worker.finished.connect(self.on_preview_worker_finished)
        self.preview_worker.start()

    def on_preview_loaded(self, theme_id, data):
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return

        self.preview_cache[theme_id] = pixmap
        label = self.preview_labels.get(theme_id)
        if label is not None:
            self.set_preview_pixmap(label, pixmap)

    def on_preview_worker_finished(self):
        self.preview_worker = None

    def open_preview_dialog(self, entry):
        theme_id = str(entry.get("id", "")).strip()
        pixmap = self.preview_cache.get(theme_id)
        if pixmap is None or pixmap.isNull():
            return

        title = entry.get("name", "Theme Preview")
        dialog = PreviewDialog(title, pixmap, self)
        dialog.exec()

    def handle_store_action(self, entry):
        theme_id = entry.get("id", "")

        if is_theme_installed(theme_id):
            self.uninstall_store_theme(entry)
        else:
            self.install_store_theme(entry)

    def install_store_theme(self, entry):
        try:
            install_store_theme(entry)
        except Exception as e:
            QMessageBox.warning(self, "Install Theme", str(e))
            return

        self.load_themes()

        theme_id = str(entry.get("id", "")).strip().lower()
        theme_name = str(entry.get("name", "Theme")).strip() or "Theme"

        reply = QMessageBox.question(
            self,
            "Theme Installed",
            f"{theme_name} has been installed. Would you like to apply it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply == QMessageBox.StandardButton.Yes and theme_id:
            self.selected_theme = f"custom:{theme_id}"
            self.current_theme = self.selected_theme
            self.theme_applied.emit(self.selected_theme)

    def uninstall_store_theme(self, entry):
        theme_id = str(entry.get("id", "")).strip().lower()

        if not is_store_installed(theme_id):
            QMessageBox.warning(
                self,
                "Uninstall Theme",
                "This theme exists locally but was not installed from the Theme Downloader. It will not be removed here.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Uninstall Theme",
            "Remove this Theme Downloader theme from your local themes folder?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            uninstall_store_theme(theme_id)
        except Exception as e:
            QMessageBox.warning(self, "Uninstall Theme", str(e))
            return

        if self.current_theme == f"custom:{theme_id}":
            self.current_theme = "auto"
            self.selected_theme = "auto"
            self.theme_applied.emit("auto")

        self.load_themes()

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

    def on_tab_changed(self):
        self.update_refresh_button_text()
        if self.tabs.currentWidget() == self.store_tab and not self.store_loaded:
            self.load_store()
        self.on_selection_changed()

    def update_refresh_button_text(self):
        if self.tabs.currentWidget() == self.store_tab:
            self.refresh_button.setText("Refresh Store")
        else:
            self.refresh_button.setText("Refresh Themes")

    def refresh_current_tab(self):
        if self.tabs.currentWidget() == self.store_tab:
            self.load_store(force=True)
        else:
            self.load_themes()

    def on_selection_changed(self):
        if self.tabs.currentWidget() != self.installed_tab:
            self.apply_button.setEnabled(False)
            return

        item = self.active_item()
        theme_key = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        self.apply_button.setEnabled(bool(theme_key))

    def apply_selected(self):
        if self.tabs.currentWidget() != self.installed_tab:
            return

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

    def closeEvent(self, event):
        if self.preview_worker is not None and self.preview_worker.isRunning():
            self.preview_worker.stop()
            self.preview_worker.wait(1000)
        if self.store_worker is not None and self.store_worker.isRunning():
            self.store_worker.quit()
            self.store_worker.wait(1000)
        super().closeEvent(event)

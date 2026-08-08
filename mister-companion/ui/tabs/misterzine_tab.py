import html
import threading

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config import save_config
from core.misterzine import (
    cached_catalog,
    cached_image_path,
    entry_deep_link,
    entry_image_slots,
    entry_repo_link,
    entry_type_text,
    entry_zaparoo_command,
    fetch_image,
    preferred_image_slot,
    refresh_catalog,
)
from core.open_helpers import open_uri
from core.zapscripts import run_zaparoo_command


TABLE_COLUMNS = [
    ("Title", "title"),
    ("Core Type", "_type"),
    ("FPGA Core", "core"),
    ("Last Updated", "updated"),
    ("MiSTer Debut", "date"),
    ("Original Year", "year"),
    ("Manufacturer", "manufacturer"),
]

DETAIL_FIELDS = [
    ("Type", "_type"),
    ("Core", "core"),
    ("ROM Name", "sn"),
    ("Manufacturer", "manufacturer"),
    ("Year", "year"),
    ("Genre", "genre"),
    ("Resolution", "res"),
    ("Rotation", "rot"),
    ("Players", "plr"),
    ("Controls", "ctl"),
    ("Flip", "flip"),
    ("Region", "reg"),
    ("MiSTer Debut", "date"),
    ("Latest Update", "updated"),
    ("Latest Commit", "act"),
    ("MRA", "mra"),
]


class MiSTerZineRefreshWorker(QThread):
    loaded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, force=False, parent=None):
        super().__init__(parent)
        self.force = force

    def run(self):
        try:
            self.loaded.emit(refresh_catalog(force=self.force))
        except Exception as exc:
            self.failed.emit(str(exc))


class MiSTerZineImageHelper(QThread):
    """Single background image helper. Only the latest requested selection is kept."""

    loaded = pyqtSignal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._condition = threading.Condition()
        self._pending = None
        self._stopping = False

    def request(self, generation, entry, slot):
        with self._condition:
            # Replace any queued request with the newest selected game/image slot.
            self._pending = (generation, dict(entry or {}), str(slot or ""))
            self._condition.notify()

    def stop(self):
        with self._condition:
            self._stopping = True
            self._pending = None
            self._condition.notify()

    def run(self):
        while True:
            with self._condition:
                while self._pending is None and not self._stopping:
                    self._condition.wait()
                if self._stopping:
                    return
                generation, entry, slot = self._pending
                self._pending = None

            # fetch_image is cache-first, so previously viewed games return
            # immediately without another network request.
            path = fetch_image(entry, slot)
            self.loaded.emit(generation, path)


class MiSTerZineTab(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.entries = []
        self.filtered_entries = []
        self.current_entry = None
        self.current_image_slot = ""
        self.refresh_worker = None
        self._image_generation = 0
        self._restoring_view_state = True
        self._view_save_timer = QTimer(self)
        self._view_save_timer.setSingleShot(True)
        self._view_save_timer.setInterval(250)
        self._view_save_timer.timeout.connect(self._save_view_state)
        self._view_state = self._load_view_state()
        self.image_helper = MiSTerZineImageHelper(parent=self)
        self.image_helper.loaded.connect(self._image_loaded)
        self.image_helper.start()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._save_view_state)
            app.aboutToQuit.connect(self._stop_image_helper)
        self._build_ui()
        QTimer.singleShot(0, self._restore_view_state)

        cached = cached_catalog()
        if cached:
            self.set_entries(cached)
            self.status_label.setText(f"Loaded {len(cached)} cached MiSTerZine entries.")

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        controls = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Find anything")
        self.search_edit.textChanged.connect(self.apply_filters)
        controls.addWidget(self.search_edit, 1)

        self.type_combo = QComboBox()
        self.type_combo.addItem("Type", "")
        self.type_combo.currentIndexChanged.connect(self.apply_filters)
        controls.addWidget(self.type_combo)

        self.genre_combo = QComboBox()
        self.genre_combo.addItem("Genre", "")
        self.genre_combo.currentIndexChanged.connect(self.apply_filters)
        controls.addWidget(self.genre_combo)

        self.year_combo = QComboBox()
        self.year_combo.addItem("Year", "")
        self.year_combo.currentIndexChanged.connect(self.apply_filters)
        controls.addWidget(self.year_combo)

        self.clear_button = QPushButton("Clear filters")
        self.clear_button.clicked.connect(self.clear_filters)
        controls.addWidget(self.clear_button)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(lambda: self.refresh(force=True))
        controls.addWidget(self.refresh_button)
        root.addLayout(controls)

        self.status_label = QLabel("MiSTerZine data has not been loaded yet.")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        self.table = QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels([label for label, _ in TABLE_COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        # ResizeToContents is very expensive with MiSTerZine's 1000+ live rows and
        # can make selection/sorting appear to freeze. Keep all columns interactive
        # so their user-selected widths can be restored from Companion's config.
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        default_widths = (280, 95, 190, 110, 110, 95, 170)
        saved_widths = self._view_state.get("column_widths", [])
        for column, default_width in enumerate(default_widths):
            width = default_width
            if column < len(saved_widths):
                try:
                    width = max(55, int(saved_widths[column]))
                except (TypeError, ValueError):
                    pass
            self.table.setColumnWidth(column, width)
        self.table.setMinimumWidth(700)
        self.splitter.addWidget(self.table)

        detail_frame = QFrame()
        detail_layout = QVBoxLayout(detail_frame)
        detail_layout.setContentsMargins(12, 8, 8, 8)
        detail_layout.setSpacing(8)

        self.title_label = QLabel("MiSTerZine")
        self.title_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.title_label.setWordWrap(True)
        detail_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel("Select an entry to view its details.")
        self.subtitle_label.setWordWrap(True)
        detail_layout.addWidget(self.subtitle_label)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(220)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        detail_layout.addWidget(self.image_label, 1)

        self.image_buttons_layout = QHBoxLayout()
        self.image_buttons = {}
        for slot, label in (("title", "Title"), ("snap", "Snapshot"), ("ingame", "In-game"), ("system", "Hardware")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, s=slot: self.select_image_slot(s))
            button.hide()
            self.image_buttons[slot] = button
            self.image_buttons_layout.addWidget(button)
        self.image_buttons_layout.addStretch()
        detail_layout.addLayout(self.image_buttons_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_layout.addWidget(self.info_label)
        info_layout.addStretch()
        scroll.setWidget(info_widget)
        detail_layout.addWidget(scroll, 1)

        actions = QHBoxLayout()
        self.launch_button = QPushButton("Launch on MiSTer")
        self.launch_button.clicked.connect(self.launch_current)
        actions.addWidget(self.launch_button)

        self.zine_button = QPushButton("View on MiSTerZine")
        self.zine_button.clicked.connect(self.open_zine)
        actions.addWidget(self.zine_button)

        self.repo_button = QPushButton("Repository")
        self.repo_button.clicked.connect(self.open_repo)
        actions.addWidget(self.repo_button)
        actions.addStretch()
        detail_layout.addLayout(actions)

        self.splitter.addWidget(detail_frame)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 3)
        root.addWidget(self.splitter, 1)

        self.splitter.splitterMoved.connect(self._schedule_view_state_save)
        header.sectionResized.connect(self._schedule_view_state_save)
        header.sortIndicatorChanged.connect(self._sort_changed)

        attribution = QLabel("Powered by MiSTerZine — core release data maintained by Matija Erceg.")
        attribution.setAlignment(Qt.AlignmentFlag.AlignCenter)
        attribution.setStyleSheet("color: gray;")
        root.addWidget(attribution)

        self.update_connection_state()

    def _load_view_state(self):
        state = self.main_window.config_data.get("misterzine_view", {})
        return dict(state) if isinstance(state, dict) else {}

    def _restore_view_state(self):
        sizes = self._view_state.get("splitter_sizes", [])
        restored = False
        if isinstance(sizes, (list, tuple)) and len(sizes) == 2:
            try:
                left, right = int(sizes[0]), int(sizes[1])
                if left > 0 and right > 0:
                    self.splitter.setSizes([left, right])
                    restored = True
            except (TypeError, ValueError):
                pass

        if not restored:
            # First-run layout: favor the release table so full titles are useful
            # immediately, while keeping the detail pane comfortably visible.
            total = max(self.splitter.width(), 1000)
            left = int(total * 0.68)
            self.splitter.setSizes([left, total - left])

        self._apply_saved_sort()
        self._restoring_view_state = False

    def _apply_saved_sort(self):
        try:
            column = int(self._view_state.get("sort_column", 3))
        except (TypeError, ValueError):
            column = 3
        if not 0 <= column < len(TABLE_COLUMNS):
            column = 3

        order_name = str(self._view_state.get("sort_order", "desc") or "desc").lower()
        order = Qt.SortOrder.AscendingOrder if order_name == "asc" else Qt.SortOrder.DescendingOrder
        self.table.sortItems(column, order)

    def _sort_changed(self, column, order):
        self._view_state["sort_column"] = int(column)
        self._view_state["sort_order"] = "asc" if order == Qt.SortOrder.AscendingOrder else "desc"
        self._schedule_view_state_save()

    def _schedule_view_state_save(self, *args):
        if self._restoring_view_state:
            return
        self._view_save_timer.start()

    def _save_view_state(self):
        if not hasattr(self, "splitter") or not hasattr(self, "table"):
            return
        header = self.table.horizontalHeader()
        state = {
            "splitter_sizes": [int(value) for value in self.splitter.sizes()],
            "column_widths": [int(self.table.columnWidth(column)) for column in range(len(TABLE_COLUMNS))],
            "sort_column": int(header.sortIndicatorSection()),
            "sort_order": "asc" if header.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder else "desc",
        }
        self._view_state = state
        self.main_window.config_data["misterzine_view"] = state
        save_config(self.main_window.config_data)

    def refresh(self, force=False):
        if self.refresh_worker and self.refresh_worker.isRunning():
            return
        self.refresh_button.setEnabled(False)
        self.status_label.setText("Checking MiSTerZine for live data...")
        self.refresh_worker = MiSTerZineRefreshWorker(force=force, parent=self)
        self.refresh_worker.loaded.connect(self._refresh_loaded)
        self.refresh_worker.failed.connect(self._refresh_failed)
        self.refresh_worker.finished.connect(self._refresh_finished)
        self.refresh_worker.start()

    def _refresh_loaded(self, result):
        entries = result.get("entries", []) if isinstance(result, dict) else []
        self.set_entries(entries)
        meta = result.get("meta", {}) if isinstance(result, dict) else {}
        updated = str(meta.get("updated", "") or "")
        cache_note = " (cached; live check failed)" if result.get("error") else ""
        self.status_label.setText(f"{len(entries)} entries • MiSTerZine updated {updated or 'unknown'}{cache_note}")

    def _refresh_failed(self, message):
        self.status_label.setText(f"Could not load MiSTerZine: {message}")

    def _refresh_finished(self):
        self.refresh_button.setEnabled(True)
        self.refresh_worker = None

    @staticmethod
    def _value(entry, key):
        if key == "_type":
            return entry_type_text(entry)
        return str(entry.get(key, "") or "").strip()

    def set_entries(self, entries):
        self.entries = [entry for entry in (entries or []) if isinstance(entry, dict)]
        self._populate_filter(self.type_combo, "Type", sorted({str(e.get("base", "") or "").strip() for e in self.entries if e.get("base")}))
        self._populate_filter(self.genre_combo, "Genre", sorted({str(e.get("genre", "") or "").strip() for e in self.entries if e.get("genre")}))
        years = {str(e.get("year", "") or "").strip() for e in self.entries if e.get("year")}
        self._populate_filter(self.year_combo, "Year", sorted(years, reverse=True))
        self.apply_filters()
        self._apply_saved_sort()

    @staticmethod
    def _populate_filter(combo, label, values):
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(label, "")
        for value in values:
            combo.addItem(value, value)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def clear_filters(self):
        self.search_edit.clear()
        for combo in (self.type_combo, self.genre_combo, self.year_combo):
            combo.setCurrentIndex(0)
        self.apply_filters()

    def apply_filters(self):
        query = self.search_edit.text().strip().lower()
        type_filter = str(self.type_combo.currentData() or "")
        genre_filter = str(self.genre_combo.currentData() or "")
        year_filter = str(self.year_combo.currentData() or "")
        filtered = []
        for entry in self.entries:
            if type_filter and str(entry.get("base", "") or "") != type_filter:
                continue
            if genre_filter and str(entry.get("genre", "") or "") != genre_filter:
                continue
            if year_filter and str(entry.get("year", "") or "") != year_filter:
                continue
            if query:
                haystack = " ".join(str(entry.get(k, "") or "") for k in entry.keys()).lower()
                if query not in haystack:
                    continue
            filtered.append(entry)
        self.filtered_entries = filtered
        self._fill_table(filtered)
        total = len(self.entries)
        self.status_label.setText(f"Showing {len(filtered)} of {total} MiSTerZine entries.")

    def _fill_table(self, entries):
        sorting = self.table.isSortingEnabled()
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            for col, (_, key) in enumerate(TABLE_COLUMNS):
                value = self._value(entry, key)
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, entry)
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(sorting)
        self.table.setUpdatesEnabled(True)
        if entries:
            self.table.selectRow(0)
        else:
            self.show_entry(None)

    def _selection_changed(self):
        items = self.table.selectedItems()
        if not items:
            self.show_entry(None)
            return
        row = items[0].row()
        title_item = self.table.item(row, 0)
        self.show_entry(title_item.data(Qt.ItemDataRole.UserRole) if title_item else None)

    def show_entry(self, entry):
        self.current_entry = entry if isinstance(entry, dict) else None
        self._image_generation += 1
        self.image_label.clear()
        self._update_image_buttons([])

        if not self.current_entry:
            self.title_label.setText("MiSTerZine")
            self.subtitle_label.setText("Select an entry to view its details.")
            self.info_label.clear()
            self.zine_button.setEnabled(False)
            self.repo_button.setEnabled(False)
            self.update_connection_state()
            return

        entry = self.current_entry
        title = str(entry.get("title", "Untitled") or "Untitled")
        core = str(entry.get("core", "") or "")
        self.title_label.setText(title)
        self.subtitle_label.setText(" • ".join(part for part in (entry_type_text(entry), core) if part))

        lines = []
        for label, key in DETAIL_FIELDS:
            value = self._value(entry, key)
            if value:
                lines.append(f"<b>{html.escape(label)}:</b> {html.escape(value)}")

        notes = str(entry.get("notes", "") or entry.get("note", "") or "").strip()
        if notes:
            lines.append(f"<br><b>Notes</b><br>{html.escape(notes).replace(chr(10), '<br>')}")
        self.info_label.setText("<br>".join(lines))

        self.zine_button.setEnabled(True)
        self.repo_button.setEnabled(bool(entry_repo_link(entry)))
        self.update_connection_state()

        slots = entry_image_slots(entry)
        self._update_image_buttons(slots)
        slot = preferred_image_slot(entry)
        if slot:
            self.select_image_slot(slot)
        else:
            self.image_label.setText("No image available")

    def _update_image_buttons(self, slots):
        for slot, button in self.image_buttons.items():
            button.setVisible(slot in slots)
            button.setChecked(False)

    def select_image_slot(self, slot):
        if not self.current_entry or slot not in entry_image_slots(self.current_entry):
            return
        self.current_image_slot = slot
        for key, button in self.image_buttons.items():
            button.setChecked(key == slot)
        self._image_generation += 1
        generation = self._image_generation
        existing = cached_image_path(self.current_entry, slot)
        if existing:
            self._set_image(existing)
            return
        self.image_label.setPixmap(QPixmap())
        self.image_label.setText("Loading image...")
        self.image_helper.request(generation, self.current_entry, slot)

    def _image_loaded(self, generation, path):
        if generation != self._image_generation:
            return
        if path:
            self._set_image(path)
        else:
            self.image_label.setText("No image available")

    def _set_image(self, path):
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.image_label.setText("No image available")
            return
        target = self.image_label.size()
        target.setWidth(max(240, target.width() - 12))
        target.setHeight(max(180, target.height() - 12))
        self.image_label.setText("")
        self.image_label.setPixmap(pixmap.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_entry and self.current_image_slot:
            existing = cached_image_path(self.current_entry, self.current_image_slot)
            if existing:
                self._set_image(existing)

    def _stop_image_helper(self):
        if self.image_helper and self.image_helper.isRunning():
            self.image_helper.stop()
            self.image_helper.wait(1500)

    def closeEvent(self, event):
        if self._view_save_timer.isActive():
            self._view_save_timer.stop()
        self._save_view_state()
        self._stop_image_helper()
        super().closeEvent(event)

    def update_connection_state(self, lightweight=True):
        offline = bool(self.main_window.is_offline_mode())
        connected = bool(getattr(self.main_window, "connection", None) and self.main_window.connection.is_connected())
        command = entry_zaparoo_command(self.current_entry or {})
        enabled = bool(self.current_entry and command and connected and not offline)
        self.launch_button.setEnabled(enabled)
        if offline:
            self.launch_button.setToolTip("Launch on MiSTer is not available in Offline Mode.")
        elif not connected:
            self.launch_button.setToolTip("Connect to your MiSTer to launch this entry.")
        elif not command:
            self.launch_button.setToolTip("This MiSTerZine entry does not contain a launch target.")
        else:
            self.launch_button.setToolTip("Launch this entry through Zaparoo.")

    def launch_current(self):
        if not self.current_entry or self.main_window.is_offline_mode():
            return
        command = entry_zaparoo_command(self.current_entry)
        if not command:
            self.status_label.setText("This MiSTerZine entry does not contain a launch target.")
            return
        try:
            run_zaparoo_command(self.main_window.connection, command, timeout=5)
            self.status_label.setText(f"Launch sent to Zaparoo: {self.current_entry.get('title', '')}")
        except Exception as exc:
            self.status_label.setText(f"Could not launch through Zaparoo: {exc}")

    def open_zine(self):
        if self.current_entry:
            open_uri(entry_deep_link(self.current_entry))

    def open_repo(self):
        if not self.current_entry:
            return
        url = entry_repo_link(self.current_entry)
        if url:
            open_uri(url)

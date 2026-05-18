from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.zapscraper import (
    apply_manual_scrape_result,
    build_gamelist_review_items,
    default_manual_search_text,
    search_screenscraper_games,
)
from ui.scaling import set_text_button_min_width


class ZapScraperManualSearchWorker(QThread):
    result = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, username, password, query, system_id):
        super().__init__()
        self.username = str(username or "").strip()
        self.password = str(password or "")
        self.query = str(query or "").strip()
        self.system_id = int(system_id or 0)

    def run(self):
        try:
            results = search_screenscraper_games(
                username=self.username,
                password=self.password,
                query=self.query,
                system_id=self.system_id,
            )

            if self.isInterruptionRequested():
                return

            self.result.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class ZapScraperManualApplyWorker(QThread):
    result = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(
        self,
        *,
        system_path,
        relative_path,
        rom,
        selected_result,
        username,
        password,
        image_source_name,
        selected_region,
        system_id,
    ):
        super().__init__()
        self.system_path = str(system_path or "")
        self.relative_path = str(relative_path or "")
        self.rom = rom or {}
        self.selected_result = selected_result or {}
        self.username = str(username or "").strip()
        self.password = str(password or "")
        self.image_source_name = str(image_source_name or "")
        self.selected_region = str(selected_region or "Auto")
        self.system_id = int(system_id or 0)

    def run(self):
        try:
            result = apply_manual_scrape_result(
                system_path=self.system_path,
                relative_path=self.relative_path,
                rom=self.rom,
                selected_result=self.selected_result,
                username=self.username,
                password=self.password,
                image_source_name=self.image_source_name,
                selected_region=self.selected_region,
                system_id=self.system_id,
            )

            if self.isInterruptionRequested():
                return

            self.result.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ZapScraperGamelistDialog(QDialog):
    def __init__(
        self,
        *,
        system,
        username,
        password,
        image_source_name,
        selected_region,
        parent=None,
    ):
        super().__init__(parent)

        self.system = system or {}
        self.username = str(username or "").strip()
        self.password = str(password or "")
        self.image_source_name = str(image_source_name or "")
        self.selected_region = str(selected_region or "Auto")
        self.system_path = Path(self.system.get("path", ""))
        self.system_id = int(self.system.get("screenscraper_id") or 0)
        self.items = []
        self.search_results = []
        self.search_worker = None
        self.apply_worker = None
        self.current_pixmap = QPixmap()

        title = self.system.get("label") or self.system.get("folder") or "Gamelist"
        self.setWindowTitle(f"Review Gamelist - {title}")
        self.resize(1050, 720)

        self._build_ui()
        self.load_items()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        self.title_label = QLabel(self.windowTitle())
        self.title_label.setObjectName("PageTitle")
        header_row.addWidget(self.title_label, 1)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.load_items)
        header_row.addWidget(self.refresh_button)
        layout.addLayout(header_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        left_layout.addWidget(QLabel("Games"))
        self.games_list = QListWidget()
        self.games_list.currentRowChanged.connect(self.on_game_selected)
        left_layout.addWidget(self.games_list, 1)

        self.games_summary_label = QLabel("No games loaded.")
        self.games_summary_label.setWordWrap(True)
        left_layout.addWidget(self.games_summary_label)

        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        preview_splitter = QSplitter(Qt.Orientation.Vertical)
        right_layout.addWidget(preview_splitter, 1)

        preview_widget = QWidget()
        preview_layout = QHBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)

        artwork_frame = QFrame()
        artwork_frame.setFrameShape(QFrame.Shape.StyledPanel)
        artwork_layout = QVBoxLayout(artwork_frame)
        artwork_layout.setContentsMargins(8, 8, 8, 8)
        artwork_layout.setSpacing(6)

        artwork_layout.addWidget(QLabel("Artwork"))
        self.artwork_label = QLabel("No artwork")
        self.artwork_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artwork_label.setFixedSize(190, 140)
        self.artwork_label.setFrameShape(QFrame.Shape.StyledPanel)
        artwork_layout.addWidget(
            self.artwork_label,
            0,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        )

        preview_layout.addWidget(artwork_frame, 0)

        metadata_frame = QFrame()
        metadata_frame.setFrameShape(QFrame.Shape.StyledPanel)
        metadata_layout = QVBoxLayout(metadata_frame)
        metadata_layout.setContentsMargins(8, 8, 8, 8)
        metadata_layout.setSpacing(6)

        metadata_layout.addWidget(QLabel("Metadata"))
        self.metadata_view = QTextEdit()
        self.metadata_view.setReadOnly(True)
        metadata_layout.addWidget(self.metadata_view, 1)

        preview_layout.addWidget(metadata_frame, 2)
        preview_splitter.addWidget(preview_widget)

        manual_widget = QWidget()
        manual_layout = QVBoxLayout(manual_widget)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        manual_layout.setSpacing(6)

        manual_layout.addWidget(QLabel("Manual Scrape"))

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search ScreenScraper for this game")
        self.search_edit.returnPressed.connect(self.search_manual)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_manual)
        set_text_button_min_width(self.search_button, 100)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.search_button)
        manual_layout.addLayout(search_row)

        self.results_list = QListWidget()
        manual_layout.addWidget(self.results_list, 1)

        manual_buttons = QHBoxLayout()
        self.apply_button = QPushButton("Use Selected Result")
        self.apply_button.clicked.connect(self.apply_selected_result)
        self.apply_button.setEnabled(False)
        self.status_label = QLabel("Select a game to search manually.")
        self.status_label.setWordWrap(True)
        manual_buttons.addWidget(self.apply_button)
        manual_buttons.addWidget(self.status_label, 1)
        manual_layout.addLayout(manual_buttons)

        preview_splitter.addWidget(manual_widget)
        preview_splitter.setStretchFactor(0, 2)
        preview_splitter.setStretchFactor(1, 1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    def load_items(self):
        try:
            self.items = build_gamelist_review_items(self.system)
        except Exception as e:
            QMessageBox.warning(self, "Review Gamelist", str(e))
            self.items = []

        self.games_list.blockSignals(True)
        self.games_list.clear()

        complete = 0
        missing_image = 0
        missing_metadata = 0

        for item in self.items:
            status = item.get("status", "")
            display_name = item.get("display_name") or item.get("relative_path") or "Unknown Game"

            if status == "complete":
                prefix = "[OK]"
                complete += 1
            elif status == "missing_image":
                prefix = "[Missing image]"
                missing_image += 1
            else:
                prefix = "[Missing metadata]"
                missing_metadata += 1

            list_item = QListWidgetItem(f"{prefix} {display_name}")
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.games_list.addItem(list_item)

        self.games_list.blockSignals(False)

        total = len(self.items)
        self.games_summary_label.setText(
            f"{total} games. Complete: {complete}. Missing image: {missing_image}. Missing metadata: {missing_metadata}."
        )

        if total:
            self.games_list.setCurrentRow(0)
        else:
            self.clear_preview()

    def current_item(self):
        item = self.games_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def current_search_result(self):
        item = self.results_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def on_game_selected(self, *_):
        item = self.current_item()

        if not item:
            self.clear_preview()
            return

        self.update_preview(item)
        self.search_edit.setText(default_manual_search_text(item))
        self.results_list.clear()
        self.search_results = []
        self.apply_button.setEnabled(False)
        self.status_label.setText("Edit the search text if needed, then press Search.")

    def clear_preview(self):
        self.current_pixmap = QPixmap()
        self.artwork_label.setText("No artwork")
        self.artwork_label.setPixmap(QPixmap())
        self.metadata_view.clear()
        self.search_edit.clear()
        self.results_list.clear()
        self.apply_button.setEnabled(False)
        self.status_label.setText("No game selected.")

    def update_preview(self, item):
        entry = item.get("entry") or {}
        rom = item.get("rom") or {}

        image_path = entry.get("image_path") or ""
        self.show_artwork(image_path)

        lines = []
        lines.append(f"Path: {item.get('relative_path', '')}")
        lines.append(f"ROM: {rom.get('filename', '')}")
        lines.append(f"Status: {item.get('status', '')}")
        lines.append("")
        lines.append(f"Name: {entry.get('name', '')}")
        lines.append(f"Description: {entry.get('desc', '')}")
        lines.append(f"Image: {entry.get('image', '')}")
        lines.append(f"Developer: {entry.get('developer', '')}")
        lines.append(f"Publisher: {entry.get('publisher', '')}")
        lines.append(f"Genre: {entry.get('genre', '')}")
        lines.append(f"Players: {entry.get('players', '')}")
        lines.append(f"Released: {entry.get('releasedate', '')}")
        lines.append(f"Rating: {entry.get('rating', '')}")
        lines.append(f"Region: {entry.get('region', '')}")
        lines.append(f"Source: {entry.get('source', '')}")
        lines.append(f"ScreenScraper ID: {entry.get('id', '')}")

        self.metadata_view.setPlainText("\n".join(lines))

    def show_artwork(self, image_path):
        image_path = str(image_path or "").strip()

        if not image_path or not Path(image_path).exists():
            self.current_pixmap = QPixmap()
            self.artwork_label.setPixmap(QPixmap())
            self.artwork_label.setText("No artwork")
            return

        pixmap = QPixmap(image_path)

        if pixmap.isNull():
            self.current_pixmap = QPixmap()
            self.artwork_label.setPixmap(QPixmap())
            self.artwork_label.setText("Unable to load artwork")
            return

        self.current_pixmap = pixmap
        self.update_artwork_pixmap()

    def update_artwork_pixmap(self):
        if self.current_pixmap.isNull():
            return

        scaled = self.current_pixmap.scaled(
            self.artwork_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.artwork_label.setText("")
        self.artwork_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_artwork_pixmap()

    def search_manual(self):
        item = self.current_item()

        if not item:
            QMessageBox.information(self, "Manual Scrape", "Select a game first.")
            return

        query = self.search_edit.text().strip()

        if not query:
            QMessageBox.information(self, "Manual Scrape", "Enter search text first.")
            return

        if not self.username or not self.password:
            QMessageBox.information(self, "Manual Scrape", "ScreenScraper credentials are missing.")
            return

        if not self.system_id:
            QMessageBox.warning(self, "Manual Scrape", "This system is missing a ScreenScraper system ID.")
            return

        if self.search_worker is not None and self.search_worker.isRunning():
            return

        self.results_list.clear()
        self.search_results = []
        self.apply_button.setEnabled(False)
        self.status_label.setText("Searching ScreenScraper...")
        self.set_busy(True)

        self.search_worker = ZapScraperManualSearchWorker(
            self.username,
            self.password,
            query,
            self.system_id,
        )
        self.search_worker.result.connect(self.on_search_finished)
        self.search_worker.error.connect(self.on_search_error)
        self.search_worker.finished.connect(self.on_search_worker_finished)
        self.search_worker.start()

    def on_search_finished(self, results):
        self.search_results = results or []
        self.results_list.clear()

        for result in self.search_results:
            name = result.get("name") or "Unknown Game"
            developer = result.get("developer") or ""
            publisher = result.get("publisher") or ""
            releasedate = result.get("releasedate") or ""

            details = " | ".join(part for part in (developer, publisher, releasedate) if part)
            text = name if not details else f"{name} - {details}"

            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, result)
            self.results_list.addItem(item)

        if self.search_results:
            self.results_list.setCurrentRow(0)
            self.apply_button.setEnabled(True)
            self.status_label.setText(f"Found {len(self.search_results)} result(s). Select the best match.")
        else:
            self.apply_button.setEnabled(False)
            self.status_label.setText("No matching ScreenScraper results found.")

    def on_search_error(self, message):
        self.status_label.setText("Search failed.")
        QMessageBox.warning(self, "Manual Scrape", message)

    def on_search_worker_finished(self):
        self.search_worker = None
        self.set_busy(False)

    def apply_selected_result(self):
        item = self.current_item()
        selected_result = self.current_search_result()

        if not item:
            QMessageBox.information(self, "Manual Scrape", "Select a game first.")
            return

        if not selected_result:
            QMessageBox.information(self, "Manual Scrape", "Select a ScreenScraper result first.")
            return

        rom = item.get("rom") or {}
        relative_path = item.get("relative_path") or ""

        if not relative_path:
            QMessageBox.warning(self, "Manual Scrape", "Selected game is missing a gamelist path.")
            return

        if self.apply_worker is not None and self.apply_worker.isRunning():
            return

        self.status_label.setText("Applying selected result...")
        self.set_busy(True)

        self.apply_worker = ZapScraperManualApplyWorker(
            system_path=str(self.system_path),
            relative_path=relative_path,
            rom=rom,
            selected_result=selected_result,
            username=self.username,
            password=self.password,
            image_source_name=self.image_source_name,
            selected_region=self.selected_region,
            system_id=self.system_id,
        )
        self.apply_worker.result.connect(self.on_apply_finished)
        self.apply_worker.error.connect(self.on_apply_error)
        self.apply_worker.finished.connect(self.on_apply_worker_finished)
        self.apply_worker.start()

    def on_apply_finished(self, result):
        self.status_label.setText("Manual scrape applied.")
        row = self.games_list.currentRow()
        self.load_items()

        if 0 <= row < self.games_list.count():
            self.games_list.setCurrentRow(row)

    def on_apply_error(self, message):
        self.status_label.setText("Apply failed.")
        QMessageBox.warning(self, "Manual Scrape", message)

    def on_apply_worker_finished(self):
        self.apply_worker = None
        self.set_busy(False)

    def set_busy(self, busy):
        busy = bool(busy)
        self.refresh_button.setEnabled(not busy)
        self.games_list.setEnabled(not busy)
        self.search_edit.setEnabled(not busy)
        self.search_button.setEnabled(not busy)
        self.results_list.setEnabled(not busy)
        self.apply_button.setEnabled(not busy and self.results_list.currentItem() is not None)

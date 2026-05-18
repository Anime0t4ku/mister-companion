from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
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
    apply_zaparoo_manual_match_result,
    build_zaparoo_companion_review_items,
    default_zaparoo_manual_search_text,
    search_screenscraper_games,
)
from ui.scaling import set_text_button_min_width


class ZapScraperMode1ManualSearchWorker(QThread):
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


class ZapScraperMode1ManualApplyWorker(QThread):
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
        selected_region,
        system_id,
        media_source_names,
    ):
        super().__init__()
        self.system_path = str(system_path or "")
        self.relative_path = str(relative_path or "")
        self.rom = rom or {}
        self.selected_result = selected_result or {}
        self.username = str(username or "").strip()
        self.password = str(password or "")
        self.selected_region = str(selected_region or "USA")
        self.system_id = int(system_id or 0)
        self.media_source_names = list(media_source_names or [])

    def run(self):
        try:
            result = apply_zaparoo_manual_match_result(
                system_path=self.system_path,
                relative_path=self.relative_path,
                rom=self.rom,
                selected_result=self.selected_result,
                username=self.username,
                password=self.password,
                selected_region=self.selected_region,
                system_id=self.system_id,
                media_source_names=self.media_source_names,
            )

            if self.isInterruptionRequested():
                return

            self.result.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ZapScraperGamelistDialogMode1(QDialog):
    def __init__(
        self,
        *,
        system,
        username,
        password,
        selected_region,
        media_source_names,
        parent=None,
    ):
        super().__init__(parent)

        self.system = system or {}
        self.username = str(username or "").strip()
        self.password = str(password or "")
        self.selected_region = str(selected_region or "USA")
        self.media_source_names = list(media_source_names or [])
        self.system_path = Path(self.system.get("path", ""))
        self.system_id = int(self.system.get("screenscraper_id") or 0)
        self.items = []
        self.search_results = []
        self.search_worker = None
        self.apply_worker = None

        title = self.system.get("label") or self.system.get("folder") or "Gamelist"
        self.setWindowTitle(f"Review Zaparoo Gamelist - {title}")
        self.resize(1050, 680)

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
        set_text_button_min_width(self.refresh_button, 100)
        header_row.addWidget(self.refresh_button)
        layout.addLayout(header_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        left_layout.addWidget(QLabel("ROMs"))
        self.roms_list = QListWidget()
        self.roms_list.currentRowChanged.connect(self.on_rom_selected)
        left_layout.addWidget(self.roms_list, 1)

        self.summary_label = QLabel("No ROMs loaded.")
        self.summary_label.setWordWrap(True)
        left_layout.addWidget(self.summary_label)

        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        selected_frame = QFrame()
        selected_frame.setFrameShape(QFrame.Shape.StyledPanel)
        selected_layout = QVBoxLayout(selected_frame)
        selected_layout.setContentsMargins(8, 8, 8, 8)
        selected_layout.setSpacing(5)

        selected_layout.addWidget(QLabel("Selected ROM"))
        self.selected_view = QTextEdit()
        self.selected_view.setReadOnly(True)
        self.selected_view.setMaximumHeight(115)
        selected_layout.addWidget(self.selected_view)

        right_layout.addWidget(selected_frame)

        manual_frame = QFrame()
        manual_frame.setFrameShape(QFrame.Shape.StyledPanel)
        manual_layout = QVBoxLayout(manual_frame)
        manual_layout.setContentsMargins(8, 8, 8, 8)
        manual_layout.setSpacing(6)

        manual_layout.addWidget(QLabel("Manual Match"))

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search ScreenScraper by game title")
        self.search_edit.returnPressed.connect(self.search_manual)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_manual)
        set_text_button_min_width(self.search_button, 100)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.search_button)
        manual_layout.addLayout(search_row)

        self.results_list = QListWidget()
        self.results_list.currentRowChanged.connect(self.on_result_selected)
        manual_layout.addWidget(self.results_list, 1)

        manual_buttons = QHBoxLayout()
        self.apply_button = QPushButton("Use Selected Match")
        self.apply_button.clicked.connect(self.apply_selected_result)
        self.apply_button.setEnabled(False)
        set_text_button_min_width(self.apply_button, 160)
        self.status_label = QLabel("Select a ROM to review or match manually.")
        self.status_label.setWordWrap(True)
        manual_buttons.addWidget(self.apply_button)
        manual_buttons.addWidget(self.status_label, 1)
        manual_layout.addLayout(manual_buttons)

        right_layout.addWidget(manual_frame, 1)

        preview_frame = QFrame()
        preview_frame.setFrameShape(QFrame.Shape.StyledPanel)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.setSpacing(5)

        preview_layout.addWidget(QLabel("Preview"))
        self.preview_view = QTextEdit()
        self.preview_view.setReadOnly(True)
        self.preview_view.setMaximumHeight(150)
        preview_layout.addWidget(self.preview_view)

        right_layout.addWidget(preview_frame)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    def load_items(self):
        try:
            self.items = build_zaparoo_companion_review_items(
                self.system,
                media_source_names=self.media_source_names,
            )
        except Exception as e:
            QMessageBox.warning(self, "Review Zaparoo Gamelist", str(e))
            self.items = []

        self.roms_list.blockSignals(True)
        self.roms_list.clear()

        matched = 0
        unmatched = 0
        missing_media = 0

        for item in self.items:
            status = str(item.get("status", ""))
            display_name = item.get("display_name") or item.get("relative_path") or "Unknown ROM"

            if status == "matched":
                prefix = "[Matched]"
                matched += 1
            elif status == "missing_media":
                prefix = "[Missing Media]"
                missing_media += 1
            else:
                prefix = "[Unmatched]"
                unmatched += 1

            list_item = QListWidgetItem(f"{prefix} {display_name}")
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.roms_list.addItem(list_item)

        self.roms_list.blockSignals(False)

        total = len(self.items)
        self.summary_label.setText(
            f"{total} ROMs. Matched: {matched}. Missing media: {missing_media}. Unmatched: {unmatched}."
        )

        if total:
            self.roms_list.setCurrentRow(0)
        else:
            self.clear_preview()

    def current_item(self):
        item = self.roms_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def current_search_result(self):
        item = self.results_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def on_rom_selected(self, *_):
        item = self.current_item()

        if not item:
            self.clear_preview()
            return

        self.update_preview(item)
        self.search_edit.setText(default_zaparoo_manual_search_text(item))
        self.results_list.clear()
        self.search_results = []
        self.apply_button.setEnabled(False)

        if item.get("status") == "unmatched":
            self.status_label.setText("This ROM is not matched yet. Search for the correct game title.")
        elif item.get("status") == "missing_media":
            self.status_label.setText("This ROM is matched, but some selected media is missing. Search again to refresh the match if needed.")
        else:
            self.status_label.setText("This ROM is already matched. You can search again to change the match.")

    def on_result_selected(self, *_):
        selected_result = self.current_search_result()
        current_item = self.current_item()
        self.apply_button.setEnabled(bool(selected_result and current_item and not self._is_busy()))

        if selected_result:
            self.update_result_preview(selected_result)

    def clear_preview(self):
        self.selected_view.clear()
        self.preview_view.clear()
        self.search_edit.clear()
        self.results_list.clear()
        self.apply_button.setEnabled(False)
        self.status_label.setText("No ROM selected.")

    def update_preview(self, item):
        rom = item.get("rom") or {}
        parent = item.get("parent") or {}
        child = item.get("child") or {}
        missing_media = item.get("missing_media") or []

        selected_lines = []
        selected_lines.append(f"File: {item.get('relative_path', '')}")
        selected_lines.append(f"Status: {item.get('status_label', item.get('status', ''))}")
        selected_lines.append(f"Current match: {item.get('matched_name') or 'None'}")
        if rom.get("filename"):
            selected_lines.append(f"ROM filename: {rom.get('filename')}")
        if child.get("region"):
            selected_lines.append(f"Region: {child.get('region')}")

        self.selected_view.setPlainText("\n".join(selected_lines))

        preview_lines = []

        if parent:
            preview_lines.append(f"Matched to: {parent.get('name') or 'Unknown Game'}")
            preview_lines.append(f"Developer: {parent.get('developer', '')}")
            preview_lines.append(f"Publisher: {parent.get('publisher', '')}")
            preview_lines.append(f"Released: {parent.get('releasedate', '')}")
            preview_lines.append(f"Players: {parent.get('players', '')}")
            preview_lines.append("")
            preview_lines.append("Selected media:")

            media_exists = parent.get("media_exists") if isinstance(parent, dict) else {}
            if not isinstance(media_exists, dict):
                media_exists = {}

            for media_name in item.get("media_source_names") or self.media_source_names:
                state = "OK" if media_exists.get(media_name) else "Missing"
                preview_lines.append(f"{state}: {media_name}")

            if missing_media:
                preview_lines.append("")
                preview_lines.append(f"Missing media: {', '.join(missing_media)}")
        else:
            preview_lines.append("This ROM is not matched yet.")
            preview_lines.append("Search for the correct game title above.")
            preview_lines.append("")
            preview_lines.append("Using a selected match will create or reuse the game entry and link this ROM to it.")

        self.preview_view.setPlainText("\n".join(preview_lines))

    def update_result_preview(self, result):
        name = result.get("name") or "Unknown Game"
        system = result.get("system") or ""
        developer = result.get("developer") or ""
        publisher = result.get("publisher") or ""
        releasedate = result.get("releasedate") or ""

        lines = []
        lines.append(f"Selected match: {name}")
        if system:
            lines.append(f"System: {system}")
        if developer:
            lines.append(f"Developer: {developer}")
        if publisher:
            lines.append(f"Publisher: {publisher}")
        if releasedate:
            lines.append(f"Released: {releasedate}")
        lines.append("")
        lines.append("Press Use Selected Match to create or reuse this game entry and link the selected ROM to it.")

        self.preview_view.setPlainText("\n".join(lines))

    def search_manual(self):
        item = self.current_item()

        if not item:
            QMessageBox.information(self, "Manual Match", "Select a ROM first.")
            return

        query = self.search_edit.text().strip()

        if not query:
            QMessageBox.information(self, "Manual Match", "Enter search text first.")
            return

        if not self.username or not self.password:
            QMessageBox.information(self, "Manual Match", "ScreenScraper credentials are missing.")
            return

        if not self.system_id:
            QMessageBox.warning(self, "Manual Match", "This system is missing a ScreenScraper system ID.")
            return

        if self.search_worker is not None and self.search_worker.isRunning():
            return

        self.results_list.clear()
        self.search_results = []
        self.apply_button.setEnabled(False)
        self.status_label.setText("Searching ScreenScraper...")
        self.set_busy(True)

        self.search_worker = ZapScraperMode1ManualSearchWorker(
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
            system = result.get("system") or ""
            developer = result.get("developer") or ""
            publisher = result.get("publisher") or ""
            releasedate = result.get("releasedate") or ""

            detail_parts = [part for part in (system, developer or publisher, releasedate) if part]
            text = name if not detail_parts else f"{name} - {' | '.join(detail_parts)}"

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
        QMessageBox.warning(self, "Manual Match", message)

    def on_search_worker_finished(self):
        self.search_worker = None
        self.set_busy(False)

    def apply_selected_result(self):
        item = self.current_item()
        selected_result = self.current_search_result()

        if not item:
            QMessageBox.information(self, "Manual Match", "Select a ROM first.")
            return

        if not selected_result:
            QMessageBox.information(self, "Manual Match", "Select a ScreenScraper result first.")
            return

        relative_path = item.get("relative_path") or ""
        rom = item.get("rom") or {}

        if not relative_path:
            QMessageBox.warning(self, "Manual Match", "Selected ROM is missing a gamelist path.")
            return

        if self.apply_worker is not None and self.apply_worker.isRunning():
            return

        self.status_label.setText("Applying selected match...")
        self.set_busy(True)

        self.apply_worker = ZapScraperMode1ManualApplyWorker(
            system_path=str(self.system_path),
            relative_path=relative_path,
            rom=rom,
            selected_result=selected_result,
            username=self.username,
            password=self.password,
            selected_region=self.selected_region,
            system_id=self.system_id,
            media_source_names=self.media_source_names,
        )
        self.apply_worker.result.connect(self.on_apply_finished)
        self.apply_worker.error.connect(self.on_apply_error)
        self.apply_worker.finished.connect(self.on_apply_worker_finished)
        self.apply_worker.start()

    def on_apply_finished(self, result):
        matched_name = result.get("matched_name") or "selected game"
        self.status_label.setText(f"Matched ROM to {matched_name}.")
        row = self.roms_list.currentRow()
        self.load_items()

        if 0 <= row < self.roms_list.count():
            self.roms_list.setCurrentRow(row)

    def on_apply_error(self, message):
        self.status_label.setText("Apply failed.")
        QMessageBox.warning(self, "Manual Match", message)

    def on_apply_worker_finished(self):
        self.apply_worker = None
        self.set_busy(False)

    def _is_busy(self):
        return bool(
            (self.search_worker is not None and self.search_worker.isRunning())
            or (self.apply_worker is not None and self.apply_worker.isRunning())
        )

    def set_busy(self, busy):
        busy = bool(busy)
        self.refresh_button.setEnabled(not busy)
        self.roms_list.setEnabled(not busy)
        self.search_edit.setEnabled(not busy)
        self.search_button.setEnabled(not busy)
        self.results_list.setEnabled(not busy)
        self.apply_button.setEnabled(not busy and self.results_list.currentItem() is not None)

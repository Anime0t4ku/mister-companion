from __future__ import annotations

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.scripts_actions import (
    apply_static_wallpaper,
    get_static_wallpaper_preview_bytes,
    get_static_wallpaper_state,
    list_static_wallpapers,
)


class _WallpaperListWorker(QThread):
    success = pyqtSignal(list, dict)
    error = pyqtSignal(str)

    def __init__(self, connection):
        super().__init__()
        self.connection = connection

    def run(self):
        try:
            wallpapers = list_static_wallpapers(self.connection)
            state = get_static_wallpaper_state(self.connection)
            self.success.emit(wallpapers, state)
        except Exception as e:
            self.error.emit(str(e))


class _WallpaperPreviewWorker(QThread):
    success = pyqtSignal(bytes, str)
    error = pyqtSignal(str, str)

    def __init__(self, connection, remote_path: str):
        super().__init__()
        self.connection = connection
        self.remote_path = remote_path

    def run(self):
        try:
            data = get_static_wallpaper_preview_bytes(self.connection, self.remote_path)
            self.success.emit(data, self.remote_path)
        except Exception as e:
            self.error.emit(str(e), self.remote_path)


class _WallpaperApplyWorker(QThread):
    success = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, connection, remote_path: str):
        super().__init__()
        self.connection = connection
        self.remote_path = remote_path

    def run(self):
        try:
            apply_static_wallpaper(self.connection, self.remote_path, reload_menu=True)
            self.success.emit(self.remote_path)
        except Exception as e:
            self.error.emit(str(e))


class StaticWallpaperDialog(QDialog):
    def __init__(self, connection, parent=None):
        super().__init__(parent)
        self.connection = connection

        self.wallpapers = []
        self.current_preview_path = ""
        self.current_preview_pixmap = None

        self.list_worker = None
        self.apply_worker = None

        # Keep preview workers alive until they finish.
        self.preview_workers = set()
        self.preview_request_id = 0

        self._closing = False

        self.setWindowTitle("Set Static Wallpaper")
        self.setModal(True)
        self.resize(980, 620)
        self.setMinimumSize(860, 540)

        self.build_ui()
        self.refresh_wallpapers()

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        title = QLabel("Static Wallpaper")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        outer.addWidget(title)

        subtitle = QLabel(
            "Choose a wallpaper from /media/fat/wallpapers. "
            "The selected wallpaper will be applied and the MiSTer menu will reload."
        )
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(subtitle)

        content_row = QHBoxLayout()
        content_row.setSpacing(12)

        # Left column
        left_panel = QVBoxLayout()
        left_panel.setSpacing(8)

        self.status_label = QLabel("Loading wallpapers...")
        self.status_label.setWordWrap(True)
        left_panel.addWidget(self.status_label)

        self.wallpaper_list = QListWidget()
        self.wallpaper_list.setMinimumWidth(300)
        self.wallpaper_list.currentItemChanged.connect(self.on_selection_changed)
        left_panel.addWidget(self.wallpaper_list, 1)

        left_button_row = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.apply_button = QPushButton("Apply Wallpaper")
        self.apply_button.setEnabled(False)

        self.refresh_button.clicked.connect(self.refresh_wallpapers)
        self.apply_button.clicked.connect(self.apply_selected_wallpaper)

        left_button_row.addWidget(self.refresh_button)
        left_button_row.addWidget(self.apply_button)
        left_panel.addLayout(left_button_row)

        left_container = QWidget()
        left_container.setLayout(left_panel)
        content_row.addWidget(left_container, 0)

        # Right column
        right_panel = QVBoxLayout()
        right_panel.setSpacing(8)

        self.preview_title = QLabel("Preview")
        self.preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_title.setStyleSheet("font-weight: bold;")
        right_panel.addWidget(self.preview_title)

        self.preview_name_label = QLabel("No wallpaper selected")
        self.preview_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_name_label.setWordWrap(True)
        right_panel.addWidget(self.preview_name_label)

        self.preview_label = QLabel("No preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(520, 360)
        self.preview_label.setStyleSheet(
            "border: 1px solid #555; background-color: #111; padding: 8px;"
        )
        right_panel.addWidget(self.preview_label, 1)

        self.saved_label = QLabel("")
        self.saved_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.saved_label.setWordWrap(True)
        right_panel.addWidget(self.saved_label)

        right_container = QWidget()
        right_container.setLayout(right_panel)
        content_row.addWidget(right_container, 1)

        outer.addLayout(content_row, 1)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        bottom_row.addWidget(self.close_button)

        outer.addLayout(bottom_row)

    def closeEvent(self, event):
        self._closing = True

        # Prevent more UI-triggered actions during shutdown.
        self.refresh_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.wallpaper_list.setEnabled(False)
        self.close_button.setEnabled(False)

        # Wait for list/apply workers if still active.
        if self.list_worker is not None and self.list_worker.isRunning():
            self.list_worker.wait(3000)

        if self.apply_worker is not None and self.apply_worker.isRunning():
            self.apply_worker.wait(3000)

        # Wait for any preview workers still running.
        for worker in list(self.preview_workers):
            if worker.isRunning():
                worker.wait(3000)

        super().closeEvent(event)

    def set_busy(self, busy: bool):
        self.refresh_button.setEnabled(not busy)
        self.wallpaper_list.setEnabled(not busy)
        self.close_button.setEnabled(not busy)

        if busy:
            self.apply_button.setEnabled(False)
        else:
            self.apply_button.setEnabled(self.get_selected_wallpaper_path() != "")

    def refresh_wallpapers(self):
        if self._closing:
            return

        if self.list_worker is not None and self.list_worker.isRunning():
            return

        self.set_busy(True)
        self.status_label.setText("Loading wallpapers...")
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText("Loading...")
        self.preview_name_label.setText("No wallpaper selected")
        self.saved_label.setText("")
        self.wallpaper_list.clear()
        self.wallpapers = []
        self.current_preview_path = ""
        self.current_preview_pixmap = None

        # Invalidate any previous preview requests.
        self.preview_request_id += 1

        self.list_worker = _WallpaperListWorker(self.connection)
        self.list_worker.success.connect(self.on_wallpapers_loaded)
        self.list_worker.error.connect(self.on_wallpapers_error)
        self.list_worker.finished.connect(self.on_list_worker_finished)
        self.list_worker.start()

    def on_list_worker_finished(self):
        self.list_worker = None
        if not self._closing:
            self.set_busy(False)

    def on_wallpapers_loaded(self, wallpapers: list, state: dict):
        if self._closing:
            return

        self.wallpapers = wallpapers or []

        active_target = state.get("active_target", "")
        saved_name = state.get("saved_name", "")
        saved_path = state.get("saved_path", "")

        if saved_name:
            saved_text = f"Saved selection: {saved_name}"
            if active_target:
                saved_text += f" | Active target: {active_target}"
            self.saved_label.setText(saved_text)
        elif active_target:
            self.saved_label.setText(f"Active target: {active_target}")
        else:
            self.saved_label.setText("No saved wallpaper selection")

        if not self.wallpapers:
            self.status_label.setText("No wallpapers found in /media/fat/wallpapers.")
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("No wallpapers found")
            self.preview_name_label.setText("No wallpaper selected")
            self.apply_button.setEnabled(False)
            return

        self.status_label.setText(f"Found {len(self.wallpapers)} wallpaper(s).")

        selected_row = 0
        if saved_path:
            for index, wallpaper in enumerate(self.wallpapers):
                if wallpaper.get("path") == saved_path:
                    selected_row = index
                    break

        for wallpaper in self.wallpapers:
            item = QListWidgetItem(wallpaper.get("name", "Unknown"))
            item.setData(Qt.ItemDataRole.UserRole, wallpaper.get("path", ""))
            self.wallpaper_list.addItem(item)

        self.wallpaper_list.setCurrentRow(selected_row)

    def on_wallpapers_error(self, message: str):
        if self._closing:
            return

        self.status_label.setText("Failed to load wallpapers.")
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText("Load failed")
        self.preview_name_label.setText("No wallpaper selected")
        self.saved_label.setText("")
        self.apply_button.setEnabled(False)
        QMessageBox.critical(self, "Error", message)

    def get_selected_wallpaper_path(self) -> str:
        item = self.wallpaper_list.currentItem()
        if not item:
            return ""
        return item.data(Qt.ItemDataRole.UserRole) or ""

    def on_selection_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None):
        del previous

        if self._closing:
            return

        if current is None:
            self.preview_name_label.setText("No wallpaper selected")
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("No preview")
            self.current_preview_path = ""
            self.current_preview_pixmap = None
            self.apply_button.setEnabled(False)

            # Invalidate previous preview requests.
            self.preview_request_id += 1
            return

        remote_path = current.data(Qt.ItemDataRole.UserRole) or ""
        name = current.text().strip() or "Unknown"

        self.preview_name_label.setText(name)
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText("Loading preview...")
        self.current_preview_pixmap = None
        self.current_preview_path = remote_path
        self.apply_button.setEnabled(bool(remote_path))

        self.load_preview(remote_path)

    def load_preview(self, remote_path: str):
        if self._closing or not remote_path:
            return

        # Create a new request id. Older results will be ignored.
        self.preview_request_id += 1
        request_id = self.preview_request_id

        worker = _WallpaperPreviewWorker(self.connection, remote_path)
        self.preview_workers.add(worker)

        worker.success.connect(
            lambda data, path, req=request_id: self.on_preview_loaded_for_request(data, path, req)
        )
        worker.error.connect(
            lambda message, path, req=request_id: self.on_preview_error_for_request(message, path, req)
        )
        worker.finished.connect(lambda w=worker: self.on_preview_worker_finished(w))
        worker.start()

    def on_preview_worker_finished(self, worker):
        self.preview_workers.discard(worker)
        worker.deleteLater()

    def on_preview_loaded_for_request(self, data: bytes, remote_path: str, request_id: int):
        if self._closing:
            return

        if request_id != self.preview_request_id:
            return

        if remote_path != self.current_preview_path:
            return

        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("Preview could not be loaded")
            self.current_preview_pixmap = None
            return

        self.current_preview_pixmap = pixmap
        self.update_preview_pixmap()

    def on_preview_error_for_request(self, message: str, remote_path: str, request_id: int):
        del message

        if self._closing:
            return

        if request_id != self.preview_request_id:
            return

        if remote_path != self.current_preview_path:
            return

        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText("Preview could not be loaded")
        self.current_preview_pixmap = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_preview_pixmap()

    def update_preview_pixmap(self):
        if self.current_preview_pixmap is None:
            return

        target_size = self.preview_label.size()
        scaled = self.current_preview_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setText("")
        self.preview_label.setPixmap(scaled)

    def apply_selected_wallpaper(self):
        if self._closing:
            return

        remote_path = self.get_selected_wallpaper_path()
        if not remote_path:
            QMessageBox.warning(self, "No Wallpaper Selected", "Select a wallpaper first.")
            return

        item = self.wallpaper_list.currentItem()
        name = item.text().strip() if item else "selected wallpaper"

        confirm = QMessageBox.question(
            self,
            "Apply Static Wallpaper",
            f"Apply '{name}' as the static wallpaper?\n\nThe MiSTer menu will be reloaded.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        if self.apply_worker is not None and self.apply_worker.isRunning():
            return

        self.set_busy(True)
        self.status_label.setText(f"Applying {name}...")

        self.apply_worker = _WallpaperApplyWorker(self.connection, remote_path)
        self.apply_worker.success.connect(self.on_apply_success)
        self.apply_worker.error.connect(self.on_apply_error)
        self.apply_worker.finished.connect(self.on_apply_finished)
        self.apply_worker.start()

    def on_apply_finished(self):
        self.apply_worker = None
        if not self._closing:
            self.set_busy(False)

    def on_apply_success(self, remote_path: str):
        if self._closing:
            return

        name = ""
        for wallpaper in self.wallpapers:
            if wallpaper.get("path") == remote_path:
                name = wallpaper.get("name", "")
                break

        self.status_label.setText(f"Applied: {name or remote_path}")
        QMessageBox.information(
            self,
            "Static Wallpaper Applied",
            f"{name or 'Wallpaper'} has been applied.\n\nThe MiSTer menu has been reloaded.",
        )
        self.accept()

    def on_apply_error(self, message: str):
        if self._closing:
            return

        self.status_label.setText("Failed to apply wallpaper.")
        QMessageBox.critical(self, "Error", message)
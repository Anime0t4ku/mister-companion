import shutil
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtPdf import QPdfDocument
except Exception:
    QPdfDocument = None

from core.config import save_config
from core.manuals import (
    cache_remote_pdf,
    clear_manuals_cache,
    get_manuals_cache_root,
    has_cached_manuals,
    merge_pdfs,
    merge_systems,
    open_cache_folder,
    remove_cached_pdf,
    scan_cached_pdfs,
    scan_cached_systems,
    scan_remote_pdfs,
    scan_remote_systems,
)


class ManualsScanWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, connection):
        super().__init__()
        self.connection = connection

    def run(self):
        try:
            cached_systems = scan_cached_systems()
            remote_systems = []

            if self.connection and self.connection.is_connected():
                remote_systems = scan_remote_systems(self.connection)

            self.result.emit(
                {
                    "cached_systems": cached_systems,
                    "remote_systems": remote_systems,
                    "systems": merge_systems(remote_systems, cached_systems),
                    "has_persistent_cached_manuals": bool(cached_systems),
                }
            )
        except Exception as e:
            self.error.emit(str(e))


class ManualsPdfScanWorker(QThread):
    result = pyqtSignal(str, object)
    error = pyqtSignal(str)

    def __init__(self, connection, system_name):
        super().__init__()
        self.connection = connection
        self.system_name = system_name

    def run(self):
        try:
            cached_pdfs = scan_cached_pdfs(self.system_name)
            remote_pdfs = []

            if self.connection and self.connection.is_connected():
                remote_pdfs = scan_remote_pdfs(self.connection, self.system_name)

            self.result.emit(
                self.system_name,
                merge_pdfs(remote_pdfs, cached_pdfs),
            )
        except Exception as e:
            self.error.emit(str(e))


class ManualsCacheWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, connection, system_name, remote_path, filename, keep_cached):
        super().__init__()
        self.connection = connection
        self.system_name = system_name
        self.remote_path = remote_path
        self.filename = filename
        self.keep_cached = bool(keep_cached)

    def run(self):
        try:
            local_path = cache_remote_pdf(
                self.connection,
                self.system_name,
                self.remote_path,
                self.filename,
                keep_cached=self.keep_cached,
            )
            self.result.emit(
                {
                    "system": self.system_name,
                    "name": self.filename,
                    "path": str(local_path),
                    "source": "cache" if self.keep_cached else "temp",
                    "keep_cached": self.keep_cached,
                }
            )
        except Exception as e:
            self.error.emit(str(e))


class ManualsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.clear_viewer_temp_cache_on_startup()

        self.main_window = parent
        self.connection = getattr(parent, "connection", None)

        self.scan_worker = None
        self.pdf_scan_worker = None
        self.cache_worker = None

        self.current_system = ""
        self.current_pdf_item = None
        self.current_cached_pdf_path = None
        self.current_pdf_is_temp = False
        self.has_persistent_cached_manuals = has_cached_manuals()
        self._temp_cleanup_running = False

        self.pdf_document = None
        self.pdf_buffer = None
        self.current_page = 0
        self.page_count = 0

        self.setWindowTitle("Manuals")
        self.resize(1200, 760)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(8)
        root_layout.addLayout(content_layout, 1)

        self.systems_list = QListWidget()
        self.systems_list.setMinimumWidth(190)
        self.systems_list.setMaximumWidth(260)
        content_layout.addWidget(self.wrap_panel("Systems", self.systems_list), 1)

        self.pdfs_list = QListWidget()
        self.pdfs_list.setMinimumWidth(260)
        self.pdfs_list.setMaximumWidth(360)
        content_layout.addWidget(self.wrap_panel("PDF Manuals", self.pdfs_list), 1)

        viewer_panel = QFrame()
        viewer_panel.setFrameShape(QFrame.Shape.StyledPanel)
        viewer_layout = QVBoxLayout(viewer_panel)
        viewer_layout.setContentsMargins(8, 8, 8, 8)
        viewer_layout.setSpacing(8)

        viewer_title = QLabel("PDF Viewer")
        viewer_title.setStyleSheet("font-weight: bold;")
        viewer_layout.addWidget(viewer_title)

        self.viewer_status_label = QLabel("Select a manual to view it.")
        self.viewer_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewer_status_label.setWordWrap(True)

        self.page_label = QLabel()
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.page_image_label = QLabel()
        self.page_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)

        viewer_holder = QWidget()
        viewer_holder_layout = QVBoxLayout(viewer_holder)
        viewer_holder_layout.setContentsMargins(0, 0, 0, 0)
        viewer_holder_layout.addWidget(self.viewer_status_label)
        viewer_holder_layout.addWidget(self.page_image_label, 1)

        self.scroll_area.setWidget(viewer_holder)
        viewer_layout.addWidget(self.scroll_area, 1)

        navigation_layout = QHBoxLayout()
        navigation_layout.setSpacing(8)

        self.previous_page_button = QPushButton("Back")
        self.previous_page_button.clicked.connect(self.previous_page)

        self.next_page_button = QPushButton("Next")
        self.next_page_button.clicked.connect(self.next_page)

        navigation_layout.addStretch()
        navigation_layout.addWidget(self.previous_page_button)
        navigation_layout.addWidget(self.page_label)
        navigation_layout.addWidget(self.next_page_button)
        navigation_layout.addStretch()

        viewer_layout.addLayout(navigation_layout)

        options_layout = QHBoxLayout()
        options_layout.setSpacing(8)

        self.keep_cached_checkbox = QCheckBox("Keep cached PDF")
        self.keep_cached_checkbox.setChecked(self.get_keep_cached_pdf_setting())
        self.keep_cached_checkbox.toggled.connect(self.on_keep_cached_pdf_changed)

        self.remove_cache_button = QPushButton("Remove cached manuals")
        self.remove_cache_button.clicked.connect(self.remove_cached_manuals)

        self.open_cache_folder_button = QPushButton("Open cached manuals folder")
        self.open_cache_folder_button.clicked.connect(self.open_cached_manuals_folder)

        options_layout.addWidget(self.keep_cached_checkbox)
        options_layout.addStretch()
        options_layout.addWidget(self.remove_cache_button)
        options_layout.addWidget(self.open_cache_folder_button)

        viewer_layout.addLayout(options_layout)

        content_layout.addWidget(viewer_panel, 3)

        self.systems_list.currentItemChanged.connect(self.on_system_selected)
        self.pdfs_list.currentItemChanged.connect(self.on_pdf_selected)
        self.finished.connect(self.on_dialog_finished)

        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=self.previous_page)
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, activated=self.previous_page)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=self.next_page)
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, activated=self.next_page)

        self.update_cache_buttons()
        self.update_page_buttons()
        self.refresh_systems()

    def wrap_panel(self, title, widget):
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        label = QLabel(title)
        label.setStyleSheet("font-weight: bold;")

        layout.addWidget(label)
        layout.addWidget(widget, 1)

        return panel

    def get_keep_cached_pdf_setting(self) -> bool:
        config_data = getattr(self.main_window, "config_data", {})

        if not isinstance(config_data, dict):
            return False

        return bool(config_data.get("manuals_keep_cached_pdf", False))

    def on_keep_cached_pdf_changed(self, checked: bool):
        config_data = getattr(self.main_window, "config_data", None)

        if not isinstance(config_data, dict):
            return

        config_data["manuals_keep_cached_pdf"] = bool(checked)
        save_config(config_data)

    def refresh_systems(self):
        self.systems_list.clear()
        self.pdfs_list.clear()
        self.set_viewer_message("Scanning manuals...")

        self.scan_worker = ManualsScanWorker(self.connection)
        self.scan_worker.result.connect(self.on_systems_loaded)
        self.scan_worker.error.connect(self.on_scan_error)
        self.scan_worker.finished.connect(self.cleanup_scan_worker)
        self.scan_worker.start()

    def on_systems_loaded(self, result):
        self.systems_list.clear()
        self.pdfs_list.clear()

        self.has_persistent_cached_manuals = bool(
            result.get("has_persistent_cached_manuals", False)
        )
        self.update_cache_buttons()

        systems = result.get("systems", [])

        for system_name in systems:
            item = QListWidgetItem(system_name)
            item.setData(Qt.ItemDataRole.UserRole, system_name)
            self.systems_list.addItem(item)

        if systems:
            self.set_viewer_message("Select a manual to view it.")
            self.systems_list.setCurrentRow(0)
        else:
            self.set_viewer_message("No manuals found.")

    def on_scan_error(self, message):
        self.systems_list.clear()
        self.pdfs_list.clear()
        self.set_viewer_message(f"Could not scan manuals:\n{message}")

    def cleanup_scan_worker(self):
        self.scan_worker = None

    def on_system_selected(self, current, previous):
        if current is None:
            return

        system_name = current.data(Qt.ItemDataRole.UserRole)

        if not system_name:
            return

        self.current_system = system_name
        self.pdfs_list.clear()
        self.set_viewer_message("Scanning PDF manuals...")

        self.pdf_scan_worker = ManualsPdfScanWorker(self.connection, system_name)
        self.pdf_scan_worker.result.connect(self.on_pdfs_loaded)
        self.pdf_scan_worker.error.connect(self.on_pdf_scan_error)
        self.pdf_scan_worker.finished.connect(self.cleanup_pdf_scan_worker)
        self.pdf_scan_worker.start()

    def on_pdfs_loaded(self, system_name, pdfs):
        if system_name != self.current_system:
            return

        self.pdfs_list.clear()

        for pdf in pdfs:
            item = QListWidgetItem(pdf["name"])
            item.setData(Qt.ItemDataRole.UserRole, pdf)
            self.pdfs_list.addItem(item)

        if pdfs:
            self.set_viewer_message("Select a manual to view it.")
        else:
            self.set_viewer_message("No PDF manuals found for this system.")

    def on_pdf_scan_error(self, message):
        self.pdfs_list.clear()
        self.set_viewer_message(f"Could not scan PDF manuals:\n{message}")

    def cleanup_pdf_scan_worker(self):
        self.pdf_scan_worker = None

    def on_pdf_selected(self, current, previous):
        if current is None:
            return

        pdf = current.data(Qt.ItemDataRole.UserRole)

        if not pdf:
            return

        self.current_pdf_item = pdf

        if pdf.get("source") == "cache":
            self.open_cached_pdf(Path(pdf["path"]), is_temp=False)
            return

        if not self.connection or not self.connection.is_connected():
            self.set_viewer_message("This manual is not cached and MiSTer is not connected.")
            return

        self.set_viewer_message("Caching manual for viewing...")

        self.cache_worker = ManualsCacheWorker(
            self.connection,
            pdf["system"],
            pdf["path"],
            pdf["name"],
            self.keep_cached_checkbox.isChecked(),
        )
        self.cache_worker.result.connect(self.on_pdf_cached)
        self.cache_worker.error.connect(self.on_cache_error)
        self.cache_worker.finished.connect(self.cleanup_cache_worker)
        self.cache_worker.start()

    def on_pdf_cached(self, cached_pdf):
        new_path = Path(cached_pdf["path"])
        keep_cached = bool(cached_pdf.get("keep_cached", False))
        is_temp = not keep_cached

        old_path = self.current_cached_pdf_path
        old_was_temp = self.current_pdf_is_temp

        if old_path and Path(old_path) != new_path and old_was_temp:
            remove_cached_pdf(old_path)

        self.open_cached_pdf(new_path, is_temp=is_temp)

        if keep_cached:
            self.has_persistent_cached_manuals = True
            self.update_cache_buttons()

    def on_cache_error(self, message):
        self.set_viewer_message(f"Could not cache manual:\n{message}")

    def cleanup_cache_worker(self):
        self.cache_worker = None

    def open_cached_pdf(self, path: Path, is_temp: bool = False):
        if not path.exists():
            self.set_viewer_message("Cached PDF file was not found.")
            return

        self.close_current_pdf_document()

        self.current_cached_pdf_path = path
        self.current_pdf_is_temp = bool(is_temp)

        if QPdfDocument is None:
            self.set_viewer_message(
                "PDF viewing is not available in this PyQt6 build.\n\n"
                f"Cached file:\n{path}"
            )
            self.page_count = 0
            self.current_page = 0
            self.update_page_buttons()
            return

        self.pdf_document = QPdfDocument(self)

        if is_temp:
            try:
                pdf_bytes = path.read_bytes()
            except Exception as e:
                self.set_viewer_message(f"Could not read temporary PDF:\n{e}")
                return

            byte_array = QByteArray(pdf_bytes)
            self.pdf_buffer = QBuffer(self)
            self.pdf_buffer.setData(byte_array)

            if not self.pdf_buffer.open(QIODevice.OpenModeFlag.ReadOnly):
                self.set_viewer_message("Could not open temporary PDF buffer.")
                return

            load_error = self.pdf_document.load(self.pdf_buffer)

            try:
                path.unlink()
            except Exception:
                pass
        else:
            load_error = self.pdf_document.load(str(path))

        if load_error is not None and load_error != QPdfDocument.Error.None_:
            error_name = getattr(load_error, "name", str(load_error))

            self.set_viewer_message(
                "Could not open PDF.\n\n"
                f"Error: {error_name}\n\n"
                f"File:\n{path}"
            )
            self.pdf_document = None
            self.pdf_buffer = None
            self.page_count = 0
            self.current_page = 0
            self.update_page_buttons()
            return

        status = self.pdf_document.status()

        if status != QPdfDocument.Status.Ready:
            status_name = getattr(status, "name", str(status))

            self.set_viewer_message(
                "PDF did not become ready after loading.\n\n"
                f"Status: {status_name}\n\n"
                f"File:\n{path}"
            )
            self.pdf_document = None
            self.pdf_buffer = None
            self.page_count = 0
            self.current_page = 0
            self.update_page_buttons()
            return

        self.page_count = self.pdf_document.pageCount()
        self.current_page = 0

        if self.page_count <= 0:
            self.set_viewer_message("PDF has no pages.")
            self.update_page_buttons()
            return

        if is_temp:
            self.current_cached_pdf_path = None
            self.current_pdf_is_temp = False

        self.render_current_page()

    def close_current_pdf_document(self):
        try:
            self.page_image_label.clear()
            self.page_image_label.setPixmap(QPixmap())
        except Exception:
            pass

        document = self.pdf_document
        buffer = self.pdf_buffer

        self.pdf_document = None
        self.pdf_buffer = None
        self.page_count = 0
        self.current_page = 0
        self.page_label.setText("")
        self.update_page_buttons()

        if document is not None:
            try:
                document.close()
            except Exception:
                pass

            try:
                document.deleteLater()
            except Exception:
                pass

        if buffer is not None:
            try:
                buffer.close()
            except Exception:
                pass

            try:
                buffer.deleteLater()
            except Exception:
                pass

        try:
            QApplication.processEvents()
        except Exception:
            pass

    def render_current_page(self):
        if not self.pdf_document or self.page_count <= 0:
            self.update_page_buttons()
            return

        page_size = self.pdf_document.pagePointSize(self.current_page).toSize()
        target_width = max(600, self.scroll_area.viewport().width() - 40)

        if page_size.width() > 0:
            scale = target_width / page_size.width()
        else:
            scale = 1.0

        target_height = int(page_size.height() * scale)
        target_size = QSize(int(target_width), max(1, target_height))

        image = self.pdf_document.render(
            self.current_page,
            target_size,
        )

        if image.isNull():
            self.set_viewer_message("Could not render PDF page.")
            return

        if image.format() != QImage.Format.Format_ARGB32:
            image = image.convertToFormat(QImage.Format.Format_ARGB32)

        pixmap = QPixmap.fromImage(image)

        self.viewer_status_label.clear()
        self.page_image_label.setPixmap(pixmap)
        self.page_label.setText(f"Page {self.current_page + 1} / {self.page_count}")
        self.update_page_buttons()

    def previous_page(self):
        if not self.pdf_document or self.page_count <= 0:
            return

        if self.current_page <= 0:
            return

        self.current_page -= 1
        self.render_current_page()

    def next_page(self):
        if not self.pdf_document or self.page_count <= 0:
            return

        if self.current_page >= self.page_count - 1:
            return

        self.current_page += 1
        self.render_current_page()

    def update_page_buttons(self):
        has_pdf = bool(self.pdf_document and self.page_count > 0)

        self.previous_page_button.setEnabled(has_pdf and self.current_page > 0)
        self.next_page_button.setEnabled(has_pdf and self.current_page < self.page_count - 1)

        if not has_pdf:
            self.page_label.setText("")

    def update_cache_buttons(self):
        enabled = bool(self.has_persistent_cached_manuals)

        self.remove_cache_button.setEnabled(enabled)
        self.open_cache_folder_button.setEnabled(enabled)

    def set_viewer_message(self, message):
        self.close_current_pdf_document()
        self.current_pdf_is_temp = False
        self.page_image_label.clear()
        self.viewer_status_label.setText(message)
        self.page_label.setText("")
        self.update_page_buttons()

    def remove_cached_manuals(self):
        if not self.has_persistent_cached_manuals:
            return

        result = QMessageBox.question(
            self,
            "Remove cached manuals",
            "Remove all cached manuals from your PC?\n\n"
            "Manuals stored on your MiSTer will not be affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        self.close_current_pdf_document()
        clear_manuals_cache()

        self.current_cached_pdf_path = None
        self.current_pdf_is_temp = False
        self.has_persistent_cached_manuals = False
        self.update_cache_buttons()
        self.set_viewer_message("Cached manuals removed.")
        self.refresh_systems()

    def open_cached_manuals_folder(self):
        if not self.has_persistent_cached_manuals:
            return

        root = get_manuals_cache_root()

        if not root.exists():
            self.has_persistent_cached_manuals = False
            self.update_cache_buttons()
            return

        open_cache_folder()

    def clear_viewer_temp_cache_on_startup(self):
        temp_root = get_manuals_cache_root() / ".viewer_temp"

        if temp_root.exists():
            try:
                shutil.rmtree(temp_root)
            except Exception:
                pass

    def clear_viewer_temp_cache(self):
        if getattr(self, "_temp_cleanup_running", False):
            return

        self._temp_cleanup_running = True

        try:
            temp_root = get_manuals_cache_root() / ".viewer_temp"

            self.close_current_pdf_document()

            if not temp_root.exists():
                return

            try:
                shutil.rmtree(temp_root)
                return
            except Exception:
                pass

            for child in list(temp_root.glob("**/*")):
                try:
                    if child.is_file():
                        child.unlink()
                except Exception:
                    pass

            for child in sorted(temp_root.glob("**/*"), reverse=True):
                try:
                    if child.is_dir():
                        child.rmdir()
                except Exception:
                    pass

            try:
                temp_root.rmdir()
                return
            except Exception:
                pass

            self.schedule_temp_cache_cleanup(temp_root)
        finally:
            self._temp_cleanup_running = False

    def schedule_temp_cache_cleanup(self, temp_root: Path):
        try:
            temp_root = temp_root.resolve()
        except Exception:
            return

        if not temp_root.exists():
            return

        try:
            if sys.platform.startswith("win"):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                command = (
                    f'ping 127.0.0.1 -n 3 > nul '
                    f'& rmdir /s /q "{temp_root}"'
                )

                subprocess.Popen(
                    ["cmd", "/c", command],
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                return

            subprocess.Popen(
                ["sh", "-c", f'sleep 2; rm -rf "{temp_root}"'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def on_dialog_finished(self, *_):
        self.clear_viewer_temp_cache()

    def closeEvent(self, event):
        self.clear_viewer_temp_cache()
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if self.pdf_document and self.page_count > 0:
            self.render_current_page()
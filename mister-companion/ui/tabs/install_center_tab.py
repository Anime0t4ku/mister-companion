import hashlib
import ssl
import time
import traceback
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, Qt, QSize, QTimer, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap, QPalette
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.scaling import set_text_button_min_width
from ui.update_all_runner import handle_update_all_result, prepare_update_all_task
from core.app_paths import app_base_dir, install_center_cache_dir
from core.install_center import (
    action_supported,
    build_context,
    check_all_status,
    check_item_status,
    context_ready,
    load_catalog,
    normalize_mister_relative_path,
    run_install_or_update,
    run_uninstall,
    install_wallpaper_pack,
    uninstall_wallpaper_pack,
    open_wallpaper_folder,
)
from core.file_browser import list_directory, join_remote_path, parent_path, DEFAULT_ROOT


HUB_RAW_BASE_URL = "https://raw.githubusercontent.com/Anime0t4ku/mister-companion-hub/main/"


def resolve_hub_asset_url(path):
    if not path:
        return ""
    path = str(path).strip()
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return HUB_RAW_BASE_URL + path.lstrip("/")


def thumbnail_candidates(catalog, item):
    candidates = []
    category_defaults = {
        category.get("id"): category.get("default_thumbnail")
        for category in catalog.get("categories", [])
        if isinstance(category, dict)
    }

    for value in (
        item.get("resolved_thumbnail"),
        item.get("thumbnail"),
        category_defaults.get(item.get("category")),
        f"assets/defaults/{item.get('category')}.png" if item.get("category") else "",
    ):
        if value and value not in candidates:
            candidates.append(value)

    return candidates


def local_asset_bytes(path):
    if not path:
        return None
    path = str(path).strip().lstrip("/")
    candidates = [
        app_base_dir() / path,
        app_base_dir() / "assets" / "install_center" / path,
    ]
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate.read_bytes()
        except Exception:
            continue
    return None


def thumbnail_cache_path(item_id, candidate):
    safe_id = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(item_id or "item"))
    candidate_text = str(candidate or "")
    suffix = Path(candidate_text.split("?", 1)[0]).suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        suffix = ".img"
    digest = hashlib.sha1(candidate_text.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return install_center_cache_dir() / "thumbnails" / f"{safe_id}_{digest}{suffix}"


def read_cached_thumbnail_bytes(catalog):
    image_bytes = {}
    for item in catalog.get("items", []):
        item_id = item.get("id")
        if not item_id:
            continue
        for candidate in thumbnail_candidates(catalog, item):
            cache_path = thumbnail_cache_path(item_id, candidate)
            try:
                if cache_path.exists() and cache_path.is_file():
                    data = cache_path.read_bytes()
                    if data:
                        image_bytes[item_id] = data
                        break
            except Exception:
                continue
    return image_bytes


def read_url_bytes(url, timeout=15, force_reload=False):
    final_url = url
    if force_reload:
        separator = "&" if "?" in final_url else "?"
        final_url = f"{final_url}{separator}_mc_cache_bust={int(time.time())}"

    request = urllib.request.Request(
        final_url,
        headers={
            "User-Agent": "MiSTer-Companion/Install-Center",
            "Accept": "image/png,image/jpeg,image/webp,*/*",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except Exception:
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return response.read()


def download_thumbnail_bytes(catalog, force_reload=False):
    image_bytes = {}
    url_cache = {}

    for item in catalog.get("items", []):
        item_id = item.get("id")
        if not item_id:
            continue

        for candidate in thumbnail_candidates(catalog, item):
            local_data = local_asset_bytes(candidate)
            if local_data:
                image_bytes[item_id] = local_data
                break

            cache_path = thumbnail_cache_path(item_id, candidate)
            url = resolve_hub_asset_url(candidate)
            if not url:
                continue
            try:
                cache_key = url if not force_reload else f"{url}::{int(time.time())}"
                if cache_key not in url_cache:
                    url_cache[cache_key] = read_url_bytes(url, force_reload=force_reload)

                data = url_cache.get(cache_key)
                if data:
                    try:
                        cache_path.parent.mkdir(parents=True, exist_ok=True)
                        cache_path.write_bytes(data)
                    except Exception:
                        pass
                    image_bytes[item_id] = data
                    break
            except Exception:
                try:
                    if cache_path.exists() and cache_path.is_file():
                        data = cache_path.read_bytes()
                        if data:
                            image_bytes[item_id] = data
                            break
                except Exception:
                    pass
                continue

    return image_bytes

class InstallCenterLoadWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, main_window, check_latest=False, force_images=False):
        super().__init__()
        self.main_window = main_window
        self.check_latest = check_latest
        self.force_images = force_images

    def run(self):
        try:
            catalog = load_catalog()
            context = build_context(self.main_window)
            statuses = check_all_status(catalog, context, check_latest=self.check_latest)
            cached_image_bytes = read_cached_thumbnail_bytes(catalog)
            self.result.emit({"catalog": catalog, "statuses": statuses, "image_bytes": cached_image_bytes, "check_latest": self.check_latest, "images_loading": True})
            image_bytes = download_thumbnail_bytes(catalog, force_reload=self.force_images)
            self.result.emit({"catalog": catalog, "statuses": statuses, "image_bytes": image_bytes, "check_latest": self.check_latest, "images_loading": False})
        except Exception as e:
            self.error.emit(f"{e}\n\n{traceback.format_exc()}")


class InstallCenterItemStatusWorker(QThread):
    result = pyqtSignal(str, object)
    error = pyqtSignal(str)

    def __init__(self, main_window, item):
        super().__init__()
        self.main_window = main_window
        self.item = item

    def run(self):
        try:
            context = build_context(self.main_window)
            status = check_item_status(self.item, context, check_latest=True)
            self.result.emit(self.item.get("id", ""), status)
        except Exception as e:
            self.error.emit(f"{e}\n\n{traceback.format_exc()}")


class InstallCenterTaskWorker(QThread):
    log_line = pyqtSignal(str)
    success = pyqtSignal(str)
    error = pyqtSignal(str)
    task_result = pyqtSignal(object)
    finished_task = pyqtSignal()

    def __init__(self, task_fn, success_message):
        super().__init__()
        self.task_fn = task_fn
        self.success_message = success_message

    def log(self, text):
        self.log_line.emit(str(text))

    def run(self):
        try:
            result = self.task_fn(self.log)
            self.success.emit(self.success_message)
            self.task_result.emit(result)
        except Exception as e:
            self.error.emit(f"{e}\n\n{traceback.format_exc()}")
        finally:
            self.finished_task.emit()


def clean_status_text(status):
    key = status_filter_key(status)
    if key == "update_available":
        return "Update Available"
    if key == "installed":
        return "Installed"
    if key == "not_installed":
        return "Not Installed"
    return "Unknown"


def status_filter_key(status):
    status = status or {}
    state = str(status.get("state") or "unknown")
    text = str(status.get("status_text") or "").lower()
    if status.get("update_available") or state == "update_available":
        return "update_available"
    if status.get("installed") or state == "installed":
        return "installed"
    if state == "not_installed":
        return "not_installed"
    if state == "detected":
        return "detected"
    if state == "needs_connection" or "needs connection" in text:
        return "needs_connection"
    if state == "needs_sd_card" or "needs sd card" in text:
        return "needs_sd_card"
    return "unknown"


def parse_date_value(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(text[:10])
    except Exception:
        return None


def category_label(item):
    value = str(item.get("type") or item.get("category") or "Item").replace("_", " ").strip()
    return value.title() if value else "Item"




class InstallCenterFolderDialog(QDialog):
    def __init__(self, connection, start_path="/media/fat/games", parent=None):
        super().__init__(parent)
        self.connection = connection
        self.current_path = start_path or "/media/fat/games"
        self.selected_path = ""
        self.entries = []
        self.setWindowTitle("Choose Install Folder")
        self.resize(620, 460)
        self.build_ui()
        self.load_path(self.current_path)

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        self.path_label = QLabel(self.current_path)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.path_label)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Search:"))
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Filter folders...")
        self.search_field.textChanged.connect(self.populate_folders)
        filter_row.addWidget(self.search_field, 1)
        layout.addLayout(filter_row)

        self.folder_list = QListWidget()
        self.folder_list.itemDoubleClicked.connect(self.open_selected_folder)
        layout.addWidget(self.folder_list, 1)

        buttons = QHBoxLayout()
        self.up_button = QPushButton("Up")
        self.games_button = QPushButton("Games")
        self.select_button = QPushButton("Use This Folder")
        self.cancel_button = QPushButton("Cancel")
        self.up_button.clicked.connect(self.go_up)
        self.games_button.clicked.connect(lambda: self.load_path("/media/fat/games"))
        self.select_button.clicked.connect(self.accept_current_folder)
        self.cancel_button.clicked.connect(self.reject)
        for button in (self.up_button, self.games_button, self.select_button, self.cancel_button):
            set_text_button_min_width(button, 120)
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)

    def load_path(self, path):
        self.current_path = path or "/media/fat/games"
        self.path_label.setText(self.current_path)
        try:
            data = list_directory(self.connection, self.current_path)
            self.current_path = data.get("path", self.current_path)
            self.path_label.setText(self.current_path)
            self.entries = [entry for entry in data.get("entries", []) if entry.get("is_dir")]
        except Exception as e:
            QMessageBox.warning(self, "Choose Install Folder", f"Could not load folder:\n{e}")
            self.entries = []
        self.populate_folders()

    def populate_folders(self):
        search = self.search_field.text().strip().lower()
        self.folder_list.clear()
        for entry in self.entries:
            name = str(entry.get("name") or "")
            if search and search not in name.lower():
                continue
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, entry.get("path"))
            self.folder_list.addItem(item)

    def open_selected_folder(self):
        item = self.folder_list.currentItem()
        if item:
            self.load_path(item.data(Qt.ItemDataRole.UserRole))

    def go_up(self):
        self.load_path(parent_path(self.current_path))

    def accept_current_folder(self):
        self.selected_path = self.current_path
        self.accept()
class InstallCenterDetailsDialog(QDialog):
    def __init__(self, tab, item, status, parent=None):
        super().__init__(parent or tab)
        self.tab = tab
        self.item = item
        self.status = status or {}
        self.rom_install_path = normalize_mister_relative_path(item.get("default_install_path") or "/games")
        self.setWindowTitle(item.get("name", "Install Center"))
        self.resize(820, 520)
        self.build_ui()

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 12)
        layout.setSpacing(6)

        header_container = QWidget()
        header_container.setMinimumHeight(150)
        header_container.setMaximumHeight(150)
        content_row = QHBoxLayout(header_container)
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(18)

        image_frame = QFrame()
        image_frame.setFrameShape(QFrame.Shape.StyledPanel)
        image_frame.setMinimumSize(190, 150)
        image_frame.setMaximumSize(190, 150)
        image_layout = QVBoxLayout(image_frame)
        image_layout.setContentsMargins(8, 8, 8, 8)
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = self.tab.pixmap_for_item(self.item.get("id"), 170, 120)
        if not pixmap.isNull():
            image_label.setPixmap(pixmap)
        image_layout.addWidget(image_label, 1)
        content_row.addWidget(image_frame, 0, Qt.AlignmentFlag.AlignVCenter)

        right_container = QWidget()
        right_container.setMinimumHeight(150)
        right_outer = QVBoxLayout(right_container)
        right_outer.setContentsMargins(0, 0, 0, 0)
        right_outer.setSpacing(0)
        right_outer.addStretch(1)

        right_panel = QVBoxLayout()
        right_panel.setSpacing(7)

        title = QLabel(self.item.get("name", self.item.get("id", "")))
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 5)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setWordWrap(True)
        right_panel.addWidget(title)

        meta_parts = []
        if self.item.get("author"):
            meta_parts.append(f"Author: {self.item.get('author')}")
        meta_parts.append(category_label(self.item))
        if self.item.get("version"):
            meta_parts.append(f"Version: {self.item.get('version')}")
        if self.item.get("release_date"):
            meta_parts.append(f"Released: {str(self.item.get('release_date'))[:10]}")
        if self.item.get("date_added"):
            meta_parts.append(f"Added: {str(self.item.get('date_added'))[:10]}")
        meta = QLabel("  •  ".join(meta_parts))
        meta.setStyleSheet("color: gray;")
        meta.setWordWrap(True)
        right_panel.addWidget(meta)

        rom_meta_text = self.rom_metadata_text()
        if rom_meta_text:
            self.rom_meta_label = QLabel(rom_meta_text)
            self.rom_meta_label.setStyleSheet("color: gray;")
            self.rom_meta_label.setWordWrap(True)
            right_panel.addWidget(self.rom_meta_label)

        self.status_label = QLabel(self.full_status_text())
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setStyleSheet(self.tab.status_style_for(self.status, pill=True))
        right_panel.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignLeft)

        self.rom_path_label = QLabel("")
        self.rom_path_label.setStyleSheet("color: gray;")
        self.rom_path_label.setVisible(False)
        right_panel.addWidget(self.rom_path_label)
        self.update_rom_path_label()

        self.actions_layout = QHBoxLayout()
        self.actions_layout.setSpacing(8)
        self.add_action_buttons(self.actions_layout)
        self.actions_layout.addStretch(1)
        right_panel.addLayout(self.actions_layout)

        right_outer.addLayout(right_panel)
        right_outer.addStretch(1)
        content_row.addWidget(right_container, 1)
        layout.addWidget(header_container, 0)

        body_container = QWidget()
        body_layout = QVBoxLayout(body_container)
        body_layout.setContentsMargins(16, 0, 0, 0)
        body_layout.setSpacing(0)

        description_title = QLabel("Description:")
        description_title_font = description_title.font()
        description_title_font.setBold(True)
        description_title.setFont(description_title_font)
        description_title.setContentsMargins(0, 0, 0, 2)
        body_layout.addWidget(description_title)

        self.description_label = QLabel(self.item.get("description", ""))
        self.description_label.setWordWrap(True)
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.description_label.setMinimumHeight(0)
        self.description_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.description_label.setContentsMargins(0, 0, 0, 0)
        body_layout.addWidget(self.description_label, 0)

        body_layout.addSpacing(14)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(120)
        self.output.setPlaceholderText("Output will appear here while installing, updating, or removing this entry.")
        body_layout.addWidget(self.output, 1)

        layout.addWidget(body_container, 1)

    def rom_metadata_text(self):
        if self.item.get("category") != "roms" and self.item.get("type") != "rom":
            return ""
        parts = []
        system = self.item.get("system")
        genres = self.item.get("genres") or []
        if system:
            parts.append(f"System: {system}")
        if isinstance(genres, str):
            genres = [genres]
        genres = [str(genre) for genre in genres if str(genre).strip()]
        if genres:
            label = "Genre" if len(genres) == 1 else "Genres"
            parts.append(f"{label}: {', '.join(genres)}")
        return "  •  ".join(parts)

    def update_rom_path_label(self):
        if not hasattr(self, "rom_path_label"):
            return
        is_rom = self.item.get("category") == "roms" or self.item.get("type") == "rom"
        if not is_rom:
            self.rom_path_label.setVisible(False)
            return
        if self.status.get("install_path"):
            self.rom_install_path = normalize_mister_relative_path(self.status.get("install_path"))
        self.rom_path_label.setText(f"Install location: {self.rom_install_path}")
        self.rom_path_label.setVisible(True)

    def prepare_action_button(self, button, minimum=88, maximum=180):
        metrics = button.fontMetrics()
        width = metrics.horizontalAdvance(button.text()) + 34
        width = max(minimum, min(width, maximum))
        button.setFixedWidth(width)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return button

    def add_compact_button(self, layout, text, callback, enabled=True, minimum=88, maximum=180):
        button = QPushButton(text)
        self.prepare_action_button(button, min(minimum, 88), maximum)
        button.setEnabled(bool(enabled))
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def full_status_text(self):
        text = str(self.status.get("status_text") or clean_status_text(self.status))
        installed_version = self.status.get("installed_version")
        latest_version = self.status.get("latest_version")
        details = []
        if installed_version:
            details.append(f"Installed: {installed_version}")
        if latest_version:
            details.append(f"Latest: {latest_version}")
        return f"{text}  ({' / '.join(details)})" if details else text

    def clear_actions_layout(self):
        if not hasattr(self, "actions_layout"):
            return
        while self.actions_layout.count():
            layout_item = self.actions_layout.takeAt(0)
            if layout_item is None:
                continue
            widget = layout_item.widget()
            if widget is not None:
                widget.deleteLater()

    def refresh_from_current_status(self):
        self.status = self.tab.statuses.get(self.item.get("id"), {}) or {}
        self.status_label.setText(self.full_status_text())
        self.status_label.setStyleSheet(self.tab.status_style_for(self.status, pill=True))
        self.update_rom_path_label()
        self.clear_actions_layout()
        self.add_action_buttons(self.actions_layout)
        self.actions_layout.addStretch(1)

    def mark_active(self):
        self.tab.active_details_dialog = self

    def add_action_buttons(self, actions):
        context_ready = self.tab.has_ready_context()
        is_wallpaper = self.item.get("category") == "wallpaper_packs" or self.item.get("type") == "wallpaper_pack"

        if self.item.get("category") == "roms" or self.item.get("type") == "rom":
            self.add_rom_action_buttons(actions, context_ready)
            return

        if is_wallpaper:
            self.add_wallpaper_action_buttons(actions, context_ready)
            return

        if self.item.get("category") == "scripts" or self.item.get("type") == "script":
            self.add_script_action_buttons(actions, context_ready)
            return

        if self.item.get("category") in {"extras", "cores"} or self.item.get("type") in {"extra", "core"}:
            self.add_extra_action_buttons(actions, context_ready)
            return

        self.install_update_button = QPushButton("Update" if self.status.get("update_available") else "Install")
        uninstall_button = QPushButton("Uninstall")
        official_button = QPushButton("Official Page")
        close_button = QPushButton("Close")

        for button in (self.install_update_button, uninstall_button, official_button, close_button):
            self.prepare_action_button(button)

        self.install_update_button.setVisible(action_supported(self.item, self.status, "install_update") and context_ready)
        uninstall_button.setVisible(action_supported(self.item, self.status, "uninstall") and context_ready)
        official_button.setVisible(bool(self.item.get("official_url")))

        self.install_update_button.clicked.connect(self.install_or_update)
        uninstall_button.clicked.connect(self.uninstall)
        official_button.clicked.connect(self.open_official_page)
        close_button.clicked.connect(self.accept)

        for button in (self.install_update_button, uninstall_button, official_button, close_button):
            actions.addWidget(button)

    def add_rom_action_buttons(self, actions, context_ready):
        installed = bool(self.status.get("installed"))
        update_available = bool(self.status.get("update_available"))
        allow_custom = bool(self.item.get("allow_custom_install_path", False)) and not installed

        if self.status.get("install_path"):
            self.rom_install_path = normalize_mister_relative_path(self.status.get("install_path"))

        self.update_rom_path_label()

        def add_button(text, callback, enabled=True, min_width=96):
            return self.add_compact_button(actions, text, callback, enabled=(context_ready and enabled), minimum=min_width)

        if allow_custom:
            add_button("Choose Install Folder", self.choose_rom_install_folder, enabled=True, min_width=150)
        add_button("Update" if update_available else "Install", self.install_or_update, enabled=(not installed or update_available), min_width=88)
        add_button("Uninstall", self.uninstall, enabled=installed, min_width=88)

        official_button = QPushButton("Official Page")
        self.prepare_action_button(official_button)
        official_button.setVisible(bool(self.item.get("official_url")))
        official_button.clicked.connect(self.open_official_page)
        actions.addWidget(official_button)

        close_button = QPushButton("Close")
        self.prepare_action_button(close_button)
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)

    def choose_rom_install_folder(self):
        default_path = self.rom_install_path or self.item.get("default_install_path") or "/games"
        if self.tab.is_offline_mode():
            sd_root = self.tab.main_window.get_offline_sd_root() if hasattr(self.tab.main_window, "get_offline_sd_root") else ""
            start = str((Path(sd_root) / default_path.strip("/")).resolve()) if sd_root else ""
            folder = QFileDialog.getExistingDirectory(self, "Choose Install Folder", start or sd_root)
            if not folder or not sd_root:
                return
            try:
                relative = Path(folder).resolve().relative_to(Path(sd_root).expanduser().resolve())
                self.rom_install_path = normalize_mister_relative_path("/" + str(relative).replace("\\", "/"))
            except Exception:
                QMessageBox.warning(self, "Choose Install Folder", "Please choose a folder inside the selected Offline SD card.")
                return
        else:
            remote_start = "/media/fat" + normalize_mister_relative_path(default_path)
            dialog = InstallCenterFolderDialog(self.tab.connection, remote_start, self)
            if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selected_path:
                return
            self.rom_install_path = normalize_mister_relative_path(dialog.selected_path)

        if hasattr(self, "rom_path_label"):
            self.rom_path_label.setText(f"Install location: {self.rom_install_path}")

    def add_wallpaper_action_buttons(self, actions, context_ready):
        handler = self.item.get("handler") or self.item.get("id")
        if handler == "wallpaper_pack":
            handler = self.item.get("id")

        def add_button(text, callback, enabled=True, min_width=96):
            return self.add_compact_button(actions, text, callback, enabled=(context_ready and enabled), minimum=min_width)

        if handler == "ranny_snice_wallpapers":
            installed_169 = bool(self.status.get("ranny_169_installed"))
            missing_169 = bool(self.status.get("ranny_169_missing"))
            installed_43 = bool(self.status.get("ranny_43_installed"))
            missing_43 = bool(self.status.get("ranny_43_missing"))
            text_169 = "Update 16:9 Wallpapers" if installed_169 and missing_169 else "Install 16:9 Wallpapers"
            text_43 = "Update 4:3 Wallpapers" if installed_43 and missing_43 else "Install 4:3 Wallpapers"
            add_button(text_169, lambda: self.install_wallpaper_variant("169"), enabled=(not installed_169 or missing_169), min_width=150)
            add_button(text_43, lambda: self.install_wallpaper_variant("43"), enabled=(not installed_43 or missing_43), min_width=150)
            remove_enabled = installed_169 or installed_43
        else:
            installed = bool(self.status.get("wallpaper_installed", self.status.get("installed")))
            missing = bool(self.status.get("wallpaper_missing", self.status.get("update_available")))
            text = "Update Wallpapers" if installed and missing else "Install Wallpapers"
            add_button(text, lambda: self.install_wallpaper_variant(None), enabled=(not installed or missing), min_width=150)
            remove_enabled = installed

        add_button("Remove Installed Wallpapers", self.remove_wallpapers, enabled=remove_enabled, min_width=170)
        add_button("Open Folder", self.open_wallpaper_folder, enabled=(self.tab.is_offline_mode() or bool(self.status.get("folder_available", True))), min_width=100)
        official_button = QPushButton("Official Page")
        self.prepare_action_button(official_button)
        official_button.setVisible(bool(self.item.get("official_url")))
        official_button.clicked.connect(self.open_official_page)
        actions.addWidget(official_button)
        close_button = QPushButton("Close")
        self.prepare_action_button(close_button)
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)

    def add_script_action_buttons(self, actions, context_ready):
        handler = self.item.get("handler") or self.item.get("id")
        installed = bool(self.status.get("installed"))
        online_mode = not self.tab.is_offline_mode()
        status_text = str(self.status.get("status_text") or "")
        status_lower = status_text.lower()
        configured = "configured" in status_lower and "not configured" not in status_lower
        service_enabled = "service enabled" in status_lower or "start on boot enabled" in status_lower

        def add_button(text, callback, enabled=True, min_width=96):
            return self.add_compact_button(actions, text, callback, enabled=(context_ready and enabled), minimum=min_width)

        add_button("Install", self.install_or_update, enabled=not installed)

        if handler == "update_all":
            add_button("Uninstall", self.uninstall, enabled=installed)
            add_button("Configure", self.configure, enabled=installed, min_width=190)
            add_button("Run Offline" if self.tab.is_offline_mode() else "Run", self.run_item, enabled=installed, min_width=170)
        elif handler == "zaparoo":
            add_button("Enable Start on Boot", lambda: self.call_scripts_tab_action("enable_zaparoo_service"), enabled=installed and "service disabled" in status_lower, min_width=190)
            add_button("Open Web Interface", lambda: self.call_scripts_tab_action("open_zaparoo_web_interface"), enabled=installed and online_mode, min_width=190)
            add_button("Uninstall", self.uninstall, enabled=installed, min_width=170)
        elif handler == "migrate_sd":
            add_button("Uninstall", self.uninstall, enabled=installed, min_width=180)
        elif handler == "cifs_mount":
            add_button("Reconfigure" if configured else "Configure", self.configure, enabled=installed, min_width=120)
            add_button("Mount", lambda: self.call_scripts_tab_action("run_cifs_mount"), enabled=installed and configured and online_mode, min_width=120)
            add_button("Unmount", lambda: self.call_scripts_tab_action("run_cifs_umount"), enabled=installed and configured and online_mode, min_width=120)
            add_button("Remove Config", lambda: self.call_scripts_tab_action("remove_cifs_config"), enabled=installed and configured, min_width=130)
            add_button("Uninstall", self.uninstall, enabled=installed, min_width=120)
        elif handler == "auto_time":
            add_button("Uninstall", self.uninstall, enabled=installed, min_width=140)
        elif handler == "cd_game_organizer":
            add_button("Uninstall", self.uninstall, enabled=installed, min_width=140)
        elif handler == "dav_browser":
            add_button("Reconfigure" if configured else "Configure", self.configure, enabled=installed, min_width=140)
            add_button("Remove Config", lambda: self.call_scripts_tab_action("remove_dav_browser_config"), enabled=installed and configured, min_width=140)
            add_button("Uninstall", self.uninstall, enabled=installed, min_width=140)
        elif handler == "ftp_save_sync":
            add_button("Reconfigure" if configured else "Configure", self.configure, enabled=installed, min_width=140)
            add_button("Enable Start on Boot", lambda: self.call_scripts_tab_action("enable_ftp_save_sync_service"), enabled=installed and configured and not service_enabled, min_width=170)
            add_button("Disable Start on Boot", lambda: self.call_scripts_tab_action("disable_ftp_save_sync_service"), enabled=installed and configured and service_enabled, min_width=175)
            add_button("Remove Config", lambda: self.call_scripts_tab_action("remove_ftp_save_sync_config"), enabled=installed and configured, min_width=140)
            add_button("Uninstall", self.uninstall, enabled=installed, min_width=140)
        elif handler == "static_wallpaper":
            add_button("Uninstall", self.uninstall, enabled=installed, min_width=150)
        elif handler == "syncthing":
            boot_text = self.status.get("boot_label") or ("Disable Start on Boot" if service_enabled else "Enable Start on Boot")
            boot_enabled = self.status.get("boot_enabled") if "boot_enabled" in self.status else installed
            running = bool(self.status.get("running"))
            add_button(boot_text, lambda: self.call_scripts_tab_action("toggle_syncthing_start_on_boot"), enabled=boot_enabled, min_width=190)
            add_button("Open Web Config", lambda: self.call_scripts_tab_action("open_syncthing_web_config"), enabled=installed and online_mode and running, min_width=190)
            add_button("Uninstall", self.uninstall, enabled=installed, min_width=170)
        elif handler == "ra_viewer":
            edit_enabled = self.status.get("edit_config_enabled") if "edit_config_enabled" in self.status else installed
            add_button("Edit Config", self.configure, enabled=edit_enabled, min_width=170)
            add_button("Uninstall", self.uninstall, enabled=installed, min_width=170)
        else:
            add_button("Uninstall", self.uninstall, enabled=installed)

        official_button = QPushButton("Official Page")
        self.prepare_action_button(official_button)
        official_button.setVisible(bool(self.item.get("official_url")))
        official_button.clicked.connect(self.open_official_page)
        actions.addWidget(official_button)

        close_button = QPushButton("Close")
        self.prepare_action_button(close_button)
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)

    def add_extra_action_buttons(self, actions, context_ready):
        handler = self.item.get("handler") or self.item.get("id")
        installed = bool(self.status.get("installed"))
        update_available = bool(self.status.get("update_available"))

        def add_button(text, callback, enabled=True, min_width=96):
            return self.add_compact_button(actions, text, callback, enabled=(context_ready and enabled), minimum=min_width)

        install_text = self.status.get("install_label") or ("Update" if update_available else "Install")
        install_enabled = self.status.get("install_enabled")
        if install_enabled is None:
            install_enabled = not installed or update_available
        add_button(install_text, self.install_or_update, enabled=install_enabled, min_width=170)
        add_button("Check for Updates", self.check_for_updates, enabled=installed, min_width=170)

        if handler == "3s_arm":
            add_button("Upload SF33RD.AFS", lambda: self.call_extras_tab_action("upload_sf33rd_afs"), enabled=self.status.get("upload_enabled", context_ready), min_width=190)
        elif handler == "sonic_mania_mister":
            add_button("Upload Data.rsdk", lambda: self.call_extras_tab_action("upload_sonic_mania_data_rsdk"), enabled=self.status.get("upload_enabled", context_ready), min_width=190)
        elif handler == "paprium_megadrive":
            add_button("Open Game Folder", lambda: self.call_extras_tab_action("open_paprium_game_folder"), enabled=self.status.get("folder_open_enabled", installed), min_width=170)
        elif handler == "retroachievement_cores":
            add_button("Edit Config", self.configure, enabled=self.status.get("edit_config_enabled", installed), min_width=170)

        add_button("Uninstall", self.uninstall, enabled=self.status.get("uninstall_enabled", installed), min_width=170)

        official_button = QPushButton("Official Page")
        self.prepare_action_button(official_button)
        official_button.setVisible(bool(self.item.get("official_url")))
        official_button.clicked.connect(self.open_official_page)
        actions.addWidget(official_button)

        close_button = QPushButton("Close")
        self.prepare_action_button(close_button)
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)

    def call_scripts_tab_action(self, method_name):
        scripts_tab = getattr(self.tab.main_window, "scripts_tab", None)
        method = getattr(scripts_tab, method_name, None)
        if not callable(method):
            QMessageBox.information(self, "Install Center", "This action is not available yet.")
            return
        method()
        self.tab.refresh_existing_tabs()
        self.tab.refresh_status()

    def call_extras_tab_action(self, method_name):
        extras_tab = getattr(self.tab.main_window, "extras_tab", None)
        method = getattr(extras_tab, method_name, None)
        if not callable(method):
            QMessageBox.information(self, "Install Center", "This action is not available yet.")
            return
        method()
        self.tab.refresh_existing_tabs()
        self.tab.refresh_status()

    def append_output(self, text):
        self.output.append(str(text).rstrip())

    def install_or_update(self):
        self.mark_active()
        self.tab.current_item_id = self.item.get("id", "")
        if self.item.get("category") == "roms" or self.item.get("type") == "rom":
            self.item["_selected_install_path"] = self.rom_install_path
        self.tab.install_or_update_selected(output_widget=self.output)

    def configure(self):
        self.mark_active()
        self.tab.current_item_id = self.item.get("id", "")
        self.tab.configure_selected()

    def run_item(self):
        self.mark_active()
        self.tab.current_item_id = self.item.get("id", "")
        self.tab.run_selected(output_widget=self.output)

    def uninstall(self):
        self.mark_active()
        self.tab.current_item_id = self.item.get("id", "")
        self.tab.uninstall_selected(output_widget=self.output)

    def install_wallpaper_variant(self, variant):
        self.mark_active()
        self.tab.current_item_id = self.item.get("id", "")
        self.tab.install_wallpaper_selected(variant, output_widget=self.output)

    def remove_wallpapers(self):
        self.mark_active()
        self.tab.current_item_id = self.item.get("id", "")
        self.tab.uninstall_selected(output_widget=self.output)

    def open_wallpaper_folder(self):
        self.tab.open_wallpaper_folder_selected()

    def check_for_updates(self):
        self.tab.check_item_for_updates(self.item, self.on_update_check_finished)

    def on_update_check_finished(self, status):
        self.status = status or {}
        self.status_label.setText(self.full_status_text())
        self.status_label.setStyleSheet(self.tab.status_style_for(self.status, pill=True))
        if hasattr(self, "install_update_button"):
            self.install_update_button.setText("Update" if self.status.get("update_available") else "Install")
            self.install_update_button.setVisible(action_supported(self.item, self.status, "install_update") and self.tab.has_ready_context())

    def open_official_page(self):
        url = str(self.item.get("official_url") or "").strip()
        if url:
            webbrowser.open(url)


class InstallCenterUpdatesDialog(QDialog):
    def __init__(self, tab, updates, parent=None):
        super().__init__(parent or tab)
        self.tab = tab
        self.updates = list(updates or [])
        self.worker = None
        self.setWindowTitle("Install Center Updates")
        self.resize(760, 520)
        self.build_ui()

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel(f"{len(self.updates)} update(s) available")
        font = title.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        self.list_widget = QListWidget()
        for item in self.updates:
            status = self.tab.statuses.get(item.get("id"), {})
            list_item = QListWidgetItem(f"{item.get('name', item.get('id'))}  —  {status.get('status_text') or clean_status_text(status)}")
            list_item.setData(Qt.ItemDataRole.UserRole, item.get("id"))
            icon = self.tab.icon_for_item(item.get("id"))
            if not icon.isNull():
                list_item.setIcon(icon)
            self.list_widget.addItem(list_item)
        layout.addWidget(self.list_widget, 1)

        buttons = QHBoxLayout()
        self.update_selected_button = QPushButton("Update Selected")
        self.update_all_button = QPushButton("Update All")
        self.close_button = QPushButton("Close")
        for button in (self.update_selected_button, self.update_all_button, self.close_button):
            set_text_button_min_width(button, 130)
        self.update_selected_button.clicked.connect(self.update_selected)
        self.update_all_button.clicked.connect(self.update_all)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.update_selected_button)
        buttons.addWidget(self.update_all_button)
        buttons.addStretch()
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(150)
        self.output.setPlaceholderText("Update output will appear here.")
        layout.addWidget(self.output)

    def set_busy(self, busy):
        self.update_selected_button.setEnabled(not busy)
        self.update_all_button.setEnabled(not busy)
        self.close_button.setEnabled(not busy)

    def selected_update_items(self):
        current = self.list_widget.currentItem()
        if not current:
            QMessageBox.warning(self, "Install Center Updates", "Select an update first.")
            return []
        item_id = current.data(Qt.ItemDataRole.UserRole)
        item = self.tab.item_by_id(item_id)
        return [item] if item else []

    def update_selected(self):
        self.run_updates(self.selected_update_items())

    def update_all(self):
        self.run_updates(list(self.updates))

    def run_updates(self, items):
        items = [item for item in items if item]
        if not items or self.worker is not None:
            return
        context = build_context(self.tab.main_window)
        ready, reason = context_ready(context)
        if not ready:
            QMessageBox.warning(self, "Install Center Updates", reason)
            return

        def task(log):
            for item in items:
                log(f"Updating {item.get('name', item.get('id'))}...\n")
                run_install_or_update(item, context, log)
                log("\n")

        self.set_busy(True)
        self.worker = InstallCenterTaskWorker(task, "Updates finished.")
        self.worker.log_line.connect(self.output.append)
        self.worker.success.connect(lambda message: self.output.append(message))
        self.worker.error.connect(lambda message: self.output.append(message))
        self.worker.finished_task.connect(self.on_updates_finished)
        self.worker.start()

    def on_updates_finished(self):
        self.worker = None
        self.set_busy(False)
        self.tab.refresh_status()


class InstallCenterTab(QWidget):
    BASE_STATUS_FILTERS = [
        ("all", "All"),
        ("installed", "Installed"),
        ("not_installed", "Not Installed"),
    ]

    SORT_OPTIONS = [
        ("name_az", "Name A-Z"),
        ("name_za", "Name Z-A"),
        ("type_az", "Type A-Z"),
        ("release_new", "Release Date, Newest First"),
        ("release_old", "Release Date, Oldest First"),
        ("added_new", "Date Added, Newest First"),
        ("added_old", "Date Added, Oldest First"),
    ]

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection
        self.catalog = {"categories": [], "items": []}
        self.statuses = {}
        self.thumbnail_bytes = {}
        self.current_item_id = ""
        self.hovered_item_id = ""
        self.load_worker = None
        self.task_worker = None
        self.item_status_worker = None
        self.active_details_dialog = None
        self.category_buttons = []
        self.current_category = "all"
        self.update_filter_available = False

        self.build_ui()
        self.refresh_status(lightweight=True)

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        title = QLabel("Install Center")
        font = title.font()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        title.setFont(font)
        header_row.addWidget(title)
        header_row.addStretch()

        self.global_check_button = QPushButton("Check for Updates")
        set_text_button_min_width(self.global_check_button, 170)
        self.global_check_button.clicked.connect(self.global_check_for_updates)
        header_row.addWidget(self.global_check_button)

        self.refresh_button = QPushButton("Refresh")
        set_text_button_min_width(self.refresh_button, 110)
        self.refresh_button.clicked.connect(lambda: self.refresh_status(force_images=True))
        header_row.addWidget(self.refresh_button)

        main_layout.addLayout(header_row)

        self.status_label = QLabel("Opening Install Center...")
        self.status_label.setStyleSheet("color: #1e88e5; font-weight: bold;")
        main_layout.addWidget(self.status_label)

        search_sort_row = QHBoxLayout()
        search_sort_row.setSpacing(8)

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search Install Center...")
        self.search_field.textChanged.connect(self.populate_items)
        search_sort_row.addWidget(self.search_field, 2)

        self.status_filter = QComboBox()
        self.rebuild_status_filter()
        self.status_filter.currentIndexChanged.connect(self.populate_items)
        search_sort_row.addWidget(self.status_filter)

        self.sort_combo = QComboBox()
        for key, label in self.SORT_OPTIONS:
            self.sort_combo.addItem(label, key)
        self.sort_combo.currentIndexChanged.connect(self.populate_items)
        search_sort_row.addWidget(self.sort_combo)

        main_layout.addLayout(search_sort_row)

        category_row = QHBoxLayout()
        category_row.setSpacing(6)
        self.filter_container = QWidget()
        self.filter_container.setAutoFillBackground(False)
        self.filter_container.setStyleSheet("background: transparent; border: none;")
        self.filter_layout = QHBoxLayout(self.filter_container)
        self.filter_layout.setContentsMargins(0, 0, 0, 0)
        self.filter_layout.setSpacing(6)
        category_row.addWidget(self.filter_container)
        main_layout.addLayout(category_row)

        self.item_list = QListWidget()
        self.item_list.setMouseTracking(True)
        self.item_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.item_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.item_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.item_list.setMovement(QListWidget.Movement.Static)
        self.item_list.setWrapping(True)
        self.item_list.setWordWrap(True)
        self.item_list.setUniformItemSizes(True)
        self.item_list.setSpacing(8)
        self.item_list.setIconSize(QSize(184, 208))
        self.item_list.setGridSize(QSize(198, 222))
        self.item_list.itemClicked.connect(self.open_item_details)
        self.item_list.itemActivated.connect(self.open_item_details)
        self.item_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.item_list.setStyleSheet(
            "QListWidget { border: none; background: transparent; } "
            "QListWidget::item { background: transparent; border: 1px solid transparent; border-radius: 8px; } "
            "QListWidget::item:hover { background: rgba(255, 255, 255, 18); border: 1px solid palette(highlight); }"
        )
        main_layout.addWidget(self.item_list, 1)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setVisible(False)
        main_layout.addWidget(self.output)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.catalog.get("items"):
            self.refresh_status(lightweight=True)
        else:
            QTimer.singleShot(0, self.populate_items)

    def is_offline_mode(self):
        return hasattr(self.main_window, "is_offline_mode") and self.main_window.is_offline_mode()

    def mode_text(self):
        if self.is_offline_mode():
            root = self.main_window.get_offline_sd_root() if hasattr(self.main_window, "get_offline_sd_root") else ""
            return "Offline Mode" if root else "Offline Mode, no SD selected"
        return "Online Mode" if self.connection.is_connected() else "Online Mode, not connected"

    def refresh_status(self, lightweight=False, force_images=False):
        if self.load_worker is not None and self.load_worker.isRunning():
            return

        self.status_label.setText("Loading Install Center in the background...")
        self.status_label.setStyleSheet("color: #1e88e5; font-weight: bold;")
        self.refresh_button.setEnabled(False)
        self.global_check_button.setEnabled(False)

        self.load_worker = InstallCenterLoadWorker(self.main_window, check_latest=False, force_images=force_images)
        self.load_worker.result.connect(self.on_load_result)
        self.load_worker.error.connect(self.on_load_error)
        self.load_worker.finished.connect(self.on_load_finished)
        self.load_worker.start()

    def global_check_for_updates(self):
        if self.load_worker is not None and self.load_worker.isRunning():
            return

        self.status_label.setText("Checking every Install Center entry for updates...")
        self.status_label.setStyleSheet("color: #1e88e5; font-weight: bold;")
        self.refresh_button.setEnabled(False)
        self.global_check_button.setEnabled(False)

        self.load_worker = InstallCenterLoadWorker(self.main_window, check_latest=True, force_images=True)
        self.load_worker.result.connect(self.on_load_result)
        self.load_worker.error.connect(self.on_load_error)
        self.load_worker.finished.connect(self.on_load_finished)
        self.load_worker.start()

    def on_load_result(self, payload):
        self.catalog = payload.get("catalog") or {"categories": [], "items": []}
        self.statuses = payload.get("statuses") or {}
        incoming_images = payload.get("image_bytes") or {}
        if incoming_images or not payload.get("images_loading"):
            self.thumbnail_bytes = incoming_images
        update_count = sum(1 for status in self.statuses.values() if status.get("update_available"))
        self.update_filter_available = bool(payload.get("check_latest") and update_count)
        self.rebuild_status_filter()
        self.rebuild_category_filters()
        self.populate_items()
        if self.active_details_dialog is not None and self.active_details_dialog.isVisible():
            try:
                self.active_details_dialog.refresh_from_current_status()
            except Exception:
                pass

        item_count = len(self.catalog.get("items", []))
        visible_count = self.item_list.count()
        if payload.get("images_loading"):
            self.status_label.setText(f"Showing {visible_count}/{item_count} item(s). Refreshing images..." if item_count else "Loading Install Center images...")
            self.status_label.setStyleSheet("color: gray;")
            return

        if payload.get("check_latest") and update_count:
            self.status_label.setText(f"{update_count} update(s) available.")
            self.status_label.setStyleSheet("color: #00aa00; font-weight: bold;")
            self.open_updates_dialog()
        elif payload.get("check_latest"):
            self.status_label.setText("No updates available.")
            self.status_label.setStyleSheet("color: #00aa00; font-weight: bold;")
        else:
            self.status_label.setText(f"Showing {visible_count}/{item_count} item(s)." if item_count else "No Install Center entries found.")
            self.status_label.setStyleSheet("color: gray;")

    def on_load_error(self, message):
        self.catalog = {"categories": [], "items": []}
        self.statuses = {}
        self.thumbnail_bytes = {}
        self.populate_items()
        self.status_label.setText("Install Center could not be loaded from GitHub.")
        self.status_label.setStyleSheet("color: #cc0000; font-weight: bold;")

    def on_load_finished(self):
        self.load_worker = None
        self.refresh_button.setEnabled(True)
        self.global_check_button.setEnabled(True)


    def rebuild_status_filter(self):
        current = self.status_filter.currentData() if hasattr(self, "status_filter") else "all"
        self.status_filter.blockSignals(True)
        self.status_filter.clear()
        filters = list(self.BASE_STATUS_FILTERS)
        if self.update_filter_available:
            filters.append(("update_available", "Update Available"))
        allowed = {key for key, _label in filters}
        for key, label in filters:
            self.status_filter.addItem(label, key)
        if current not in allowed:
            current = "all"
        index = self.status_filter.findData(current)
        self.status_filter.setCurrentIndex(index if index >= 0 else 0)
        self.status_filter.blockSignals(False)

    def rebuild_category_filters(self):
        visible_category_ids = {category.get("id") for category in self.catalog.get("categories", []) if isinstance(category, dict)}
        if self.current_category != "all" and self.current_category not in visible_category_ids:
            self.current_category = "all"

        while self.filter_layout.count():
            item = self.filter_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.category_buttons = []
        all_button = self.create_category_button("All", "all")
        self.filter_layout.addWidget(all_button)
        self.category_buttons.append(("all", all_button))

        for category in self.catalog.get("categories", []):
            category_id = category.get("id")
            if not category_id:
                continue
            button = self.create_category_button(category.get("name", category_id), category_id)
            self.filter_layout.addWidget(button)
            self.category_buttons.append((category_id, button))

        self.filter_layout.addStretch()

    def create_category_button(self, label, category_id):
        button = QPushButton(label)
        button.setCheckable(True)
        button.setChecked(category_id == self.current_category)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(30)
        set_text_button_min_width(button, max(70, button.fontMetrics().horizontalAdvance(label) + 26))
        button.setStyleSheet(self.category_button_style())
        button.clicked.connect(lambda checked=False, cid=category_id: self.set_category_filter(cid))
        return button

    def category_button_style(self):
        palette = self.palette()
        button_bg = palette.color(QPalette.ColorRole.Button)
        text = palette.color(QPalette.ColorRole.ButtonText)
        border = palette.color(QPalette.ColorRole.Mid)
        accent = palette.color(QPalette.ColorRole.Highlight)
        accent_text = palette.color(QPalette.ColorRole.HighlightedText)
        hover = button_bg.lighter(112) if button_bg.lightness() < 128 else button_bg.darker(105)
        return (
            "QPushButton { "
            f"background-color: {button_bg.name()}; "
            f"color: {text.name()}; "
            f"border: 1px solid {border.name()}; "
            "border-radius: 8px; "
            "padding: 5px 12px; "
            "font-weight: bold; "
            "} "
            "QPushButton:hover { "
            f"background-color: {hover.name()}; "
            f"border-color: {accent.name()}; "
            "} "
            "QPushButton:checked { "
            f"background-color: {accent.name()}; "
            f"color: {accent_text.name()}; "
            f"border-color: {accent.name()}; "
            "}"
        )

    def set_category_filter(self, category_id):
        self.current_category = category_id or "all"
        for cid, button in self.category_buttons:
            button.setChecked(cid == self.current_category)
        self.populate_items()

    def visible_items(self):
        items = list(self.catalog.get("items", []))
        status_filter = self.status_filter.currentData() or "all"
        search = self.search_field.text().strip().lower() if hasattr(self, "search_field") else ""
        visible = []

        for item in items:
            item_id = item.get("id")
            if self.current_category != "all" and item.get("category") != self.current_category:
                continue

            status = self.statuses.get(item_id, {})
            if status_filter != "all" and status_filter_key(status) != status_filter:
                continue

            if search:
                haystack = " ".join(str(item.get(key, "")) for key in ("name", "description", "author", "category", "type", "handler", "id")).lower()
                tags = item.get("tags") or []
                if isinstance(tags, list):
                    haystack += " " + " ".join(str(tag) for tag in tags).lower()
                if search not in haystack:
                    continue

            visible.append(item)

        return self.sorted_items(visible)

    def sorted_items(self, items):
        sort_key = self.sort_combo.currentData() if hasattr(self, "sort_combo") else "name_az"
        if sort_key == "name_za":
            return sorted(items, key=lambda item: str(item.get("name", "")).lower(), reverse=True)
        if sort_key == "type_az":
            return sorted(items, key=lambda item: (category_label(item).lower(), str(item.get("name", "")).lower()))
        if sort_key == "release_new":
            return self.sort_by_date(items, "release_date", newest=True)
        if sort_key == "release_old":
            return self.sort_by_date(items, "release_date", newest=False)
        if sort_key == "added_new":
            return self.sort_by_date(items, "date_added", newest=True)
        if sort_key == "added_old":
            return self.sort_by_date(items, "date_added", newest=False)
        return sorted(items, key=lambda item: str(item.get("name", "")).lower())

    def sort_by_date(self, items, field, newest=True):
        dated = []
        missing = []
        for item in items:
            parsed = parse_date_value(item.get(field))
            if parsed is None:
                missing.append(item)
            else:
                dated.append((parsed, item))
        dated.sort(key=lambda pair: pair[0], reverse=newest)
        missing.sort(key=lambda item: str(item.get("name", "")).lower())
        return [item for _, item in dated] + missing

    def status_style_for(self, status, pill=False):
        key = status_filter_key(status)
        colors = {
            "installed": ("#1b7f3a", "#e7f6ec"),
            "update_available": ("#0b6fcc", "#e8f2ff"),
            "not_installed": ("#666666", "#f0f0f0"),
            "detected": ("#6f42c1", "#f2eafb"),
            "needs_connection": ("#b26a00", "#fff4df"),
            "needs_sd_card": ("#b26a00", "#fff4df"),
            "unknown": ("#666666", "#f0f0f0"),
        }
        fg, bg = colors.get(key, colors["unknown"])
        if pill:
            return f"color: {fg}; background: {bg}; border: 1px solid {fg}; border-radius: 8px; padding: 2px 8px; font-weight: bold;"
        return f"color: {fg}; font-weight: bold;"

    def card_colors(self, hovered=False):
        palette = self.palette()
        surface = palette.color(QPalette.ColorRole.Button)
        surface_alt = palette.color(QPalette.ColorRole.Base)
        text = palette.color(QPalette.ColorRole.Text)
        muted = palette.color(QPalette.ColorRole.PlaceholderText)
        border = palette.color(QPalette.ColorRole.Mid)
        accent = palette.color(QPalette.ColorRole.Highlight)
        if not surface.isValid():
            surface = QColor("#f7f7f7")
        if not surface_alt.isValid():
            surface_alt = QColor("#ffffff")
        if not text.isValid():
            text = QColor("#202020")
        if not muted.isValid():
            muted = QColor("#666666")
        if not border.isValid():
            border = QColor("#cfcfcf")
        if not accent.isValid():
            accent = QColor("#7c3aed")
        if hovered:
            bg = surface.lighter(115) if surface.lightness() < 128 else surface.darker(105)
        else:
            bg = surface
        return bg, text, muted, accent if hovered else border, accent

    def placeholder_pixmap_for_item(self, item, width=150, height=84):
        pixmap = QPixmap(width, height)
        bg, text, muted, border, accent = self.card_colors(False)
        pixmap.fill(bg)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(border)
        painter.drawRect(0, 0, width - 1, height - 1)

        category = str(item.get("category", "item")).replace("_", " ").title()
        painter.setPen(muted)
        font = painter.font()
        font.setBold(True)
        font.setPointSize(max(8, font.pointSize() - 1))
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, category)
        painter.end()
        return pixmap

    def pixmap_for_item(self, item_id, width=150, height=84):
        data = self.thumbnail_bytes.get(item_id)
        if data:
            image = QImage.fromData(data)
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
                if not pixmap.isNull():
                    return pixmap.scaled(
                        width,
                        height,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )

        item = self.item_by_id(item_id) or {"category": "item"}
        return self.placeholder_pixmap_for_item(item, width, height)

    def icon_for_item(self, item_id):
        pixmap = self.pixmap_for_item(item_id)
        return QIcon(pixmap) if not pixmap.isNull() else QIcon()

    def grid_card_pixmap_for_item(self, item, status, width=184, height=208, hovered=False):
        base = QPixmap(width, height)
        base.fill(QColor("transparent"))
        bg, text_color, muted_color, border_color, accent_color = self.card_colors(hovered)

        painter = QPainter(base)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(border_color)
        painter.setBrush(bg)
        painter.drawRoundedRect(1, 1, width - 3, height - 3, 9, 9)

        image = self.pixmap_for_item(item.get("id"), width - 20, 100)
        image_x = int((width - image.width()) / 2)
        painter.drawPixmap(image_x, 8, image)

        title_font = painter.font()
        title_font.setBold(True)
        title_font.setPointSize(max(9, title_font.pointSize()))
        painter.setFont(title_font)
        painter.setPen(text_color)
        metrics = painter.fontMetrics()
        title = metrics.elidedText(str(item.get("name", item.get("id", ""))), Qt.TextElideMode.ElideRight, width - 24)
        painter.drawText(QRect(10, 113, width - 20, 24), Qt.AlignmentFlag.AlignCenter, title)

        type_font = painter.font()
        type_font.setBold(False)
        type_font.setPointSize(max(8, type_font.pointSize()))
        painter.setFont(type_font)
        painter.setPen(muted_color)
        type_text = painter.fontMetrics().elidedText(category_label(item), Qt.TextElideMode.ElideRight, width - 24)
        painter.drawText(QRect(10, 139, width - 20, 19), Qt.AlignmentFlag.AlignCenter, type_text)

        status_text = clean_status_text(status)
        key = status_filter_key(status)
        colors = {
            "installed": (QColor("#1b7f3a"), QColor("#e7f6ec")),
            "update_available": (QColor("#0b6fcc"), QColor("#e8f2ff")),
            "not_installed": (QColor("#666666"), QColor("#f0f0f0")),
            "unknown": (QColor("#666666"), QColor("#f0f0f0")),
        }
        fg, pill_bg = colors.get(key, colors["unknown"])
        status_font = painter.font()
        status_font.setBold(True)
        status_font.setPointSize(max(8, status_font.pointSize()))
        painter.setFont(status_font)
        metrics = painter.fontMetrics()
        pill_w = min(width - 28, metrics.horizontalAdvance(status_text) + 18)
        pill_h = 18
        pill_x = int((width - pill_w) / 2)
        pill_y = height - pill_h - 12
        painter.setPen(fg)
        painter.setBrush(pill_bg)
        painter.drawRoundedRect(pill_x, pill_y, pill_w, pill_h, 8, 8)
        painter.drawText(pill_x, pill_y, pill_w, pill_h, Qt.AlignmentFlag.AlignCenter, status_text)
        painter.end()
        return base

    def grid_icon_for_item(self, item, status):
        hovered = item.get("id") == self.hovered_item_id
        pixmap = self.grid_card_pixmap_for_item(item, status, hovered=hovered)
        return QIcon(pixmap) if not pixmap.isNull() else QIcon()

    def on_item_hovered(self, list_item):
        item_id = list_item.data(Qt.ItemDataRole.UserRole) if list_item else ""
        if item_id and item_id != self.hovered_item_id:
            self.hovered_item_id = item_id
            self.populate_items()

    def on_viewport_left_items(self):
        if self.hovered_item_id:
            self.hovered_item_id = ""
            self.populate_items()

    def populate_items(self):
        previous_scroll = self.item_list.verticalScrollBar().value()
        self.item_list.blockSignals(True)
        self.item_list.clear()

        for item in self.visible_items():
            item_id = item.get("id")
            status = self.statuses.get(item_id, {})
            status_text = clean_status_text(status)
            list_item = QListWidgetItem("")
            list_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            list_item.setData(Qt.ItemDataRole.UserRole, item_id)
            list_item.setToolTip(f"{item.get('name', item_id)}\n{status_text}")
            icon = self.grid_icon_for_item(item, status)
            if not icon.isNull():
                list_item.setIcon(icon)
            self.item_list.addItem(list_item)

        self.item_list.clearSelection()
        self.item_list.setCurrentItem(None)
        self.item_list.blockSignals(False)
        self.item_list.verticalScrollBar().setValue(min(previous_scroll, self.item_list.verticalScrollBar().maximum()))
        self.update_count_status()

    def update_count_status(self):
        item_count = len(self.catalog.get("items", []))
        visible_count = self.item_list.count()
        if item_count and self.load_worker is None:
            self.status_label.setText(f"Showing {visible_count}/{item_count} item(s).")
            self.status_label.setStyleSheet("color: gray;")

    def item_by_id(self, item_id):
        for item in self.catalog.get("items", []):
            if item.get("id") == item_id:
                return item
        return None

    def open_item_details(self, list_item):
        if list_item is None:
            return
        item_id = list_item.data(Qt.ItemDataRole.UserRole) or ""
        self.current_item_id = item_id
        item = self.item_by_id(item_id)
        if not item:
            return
        status = self.statuses.get(item_id, {})
        dialog = InstallCenterDetailsDialog(self, item, status, self)
        self.active_details_dialog = dialog
        dialog.exec()
        if self.active_details_dialog is dialog:
            self.active_details_dialog = None


    def open_updates_dialog(self):
        updates = [
            item for item in self.catalog.get("items", [])
            if (self.statuses.get(item.get("id"), {}) or {}).get("update_available")
        ]
        if not updates:
            return
        dialog = InstallCenterUpdatesDialog(self, updates, self)
        dialog.exec()
        self.populate_items()

    def has_ready_context(self):
        context = build_context(self.main_window)
        ready, _ = context_ready(context)
        return ready

    def selected_item(self):
        item = self.item_by_id(self.current_item_id)
        if not item:
            QMessageBox.warning(self, "Install Center", "Select an item first.")
            return None
        return item

    def check_item_for_updates(self, item, callback=None):
        if self.item_status_worker is not None and self.item_status_worker.isRunning():
            QMessageBox.warning(self, "Busy", "Install Center is already checking an item.")
            return
        context = build_context(self.main_window)
        ready, reason = context_ready(context)
        if not ready:
            QMessageBox.warning(self, "Install Center", reason)
            return
        self.status_label.setText(f"Checking {item.get('name', 'item')} for updates...")
        self.status_label.setStyleSheet("color: #1e88e5; font-weight: bold;")
        self.item_status_worker = InstallCenterItemStatusWorker(self.main_window, item)

        def handle_result(item_id, status):
            self.statuses[item_id] = status or {}
            if (status or {}).get("update_available"):
                self.update_filter_available = True
                self.rebuild_status_filter()
            self.populate_items()
            self.status_label.setText(f"{item.get('name', 'Item')}: {clean_status_text(status or {})}")
            self.status_label.setStyleSheet("color: gray;")
            if callback:
                callback(status or {})

        def handle_error(message):
            QMessageBox.critical(self, "Install Center Error", message)

        def handle_finished():
            self.item_status_worker = None

        self.item_status_worker.result.connect(handle_result)
        self.item_status_worker.error.connect(handle_error)
        self.item_status_worker.finished.connect(handle_finished)
        self.item_status_worker.start()

    def start_task(self, label, task_fn, success_message, output_widget=None, result_handler=None):
        if self.task_worker is not None and self.task_worker.isRunning():
            QMessageBox.warning(self, "Busy", "Install Center is already running a task.")
            return

        target_output = output_widget or self.output
        target_output.setVisible(True)
        target_output.append(f"{label}\n")
        self.refresh_button.setEnabled(False)
        self.global_check_button.setEnabled(False)

        self.task_worker = InstallCenterTaskWorker(task_fn, success_message)
        self.task_worker.log_line.connect(target_output.append)
        self.task_worker.success.connect(lambda message: self.on_task_success(message, target_output))
        self.task_worker.error.connect(lambda message: self.on_task_error(message, target_output))
        if result_handler is not None:
            self.task_worker.task_result.connect(result_handler)
        self.task_worker.finished_task.connect(self.on_task_finished)
        self.task_worker.start()

    def on_task_success(self, message, output_widget=None):
        if message and output_widget is not None:
            output_widget.append(message)

    def on_task_error(self, message, output_widget=None):
        if output_widget is not None:
            output_widget.append(message)
        else:
            QMessageBox.critical(self, "Install Center Error", message)

    def on_task_finished(self):
        self.task_worker = None
        self.refresh_button.setEnabled(True)
        self.global_check_button.setEnabled(True)
        self.refresh_status()
        self.refresh_existing_tabs()

    def install_or_update_selected(self, output_widget=None):
        item = self.selected_item()
        if not item:
            return
        context = build_context(self.main_window)
        ready, reason = context_ready(context)
        if not ready:
            QMessageBox.warning(self, "Install Center", reason)
            return
        self.start_task(
            f"Installing/updating {item.get('name')}...",
            lambda log: run_install_or_update(item, context, log),
            f"{item.get('name')} finished successfully.",
            output_widget=output_widget,
        )

    def uninstall_selected(self, output_widget=None):
        item = self.selected_item()
        if not item:
            return
        confirm = QMessageBox.question(self, "Uninstall", f"Uninstall {item.get('name')}?")
        if confirm != QMessageBox.StandardButton.Yes:
            return
        context = build_context(self.main_window)
        ready, reason = context_ready(context)
        if not ready:
            QMessageBox.warning(self, "Install Center", reason)
            return
        self.start_task(
            f"Uninstalling {item.get('name')}...",
            lambda log: run_uninstall(item, context, log),
            f"{item.get('name')} was uninstalled.",
            output_widget=output_widget,
        )

    def configure_selected(self):
        item = self.selected_item()
        if not item:
            return
        handler = item.get("handler") or item.get("id")
        status = self.statuses.get(item.get("id"), {})
        if handler == "update_all" and hasattr(self.main_window, "scripts_tab"):
            self.main_window.scripts_tab.update_all_installed = bool(status.get("installed"))
            self.main_window.scripts_tab.configure_update_all()
        elif handler == "cifs_mount" and hasattr(self.main_window, "scripts_tab"):
            self.main_window.scripts_tab.configure_cifs()
        elif handler == "dav_browser" and hasattr(self.main_window, "scripts_tab"):
            self.main_window.scripts_tab.configure_dav_browser()
        elif handler == "ftp_save_sync" and hasattr(self.main_window, "scripts_tab"):
            self.main_window.scripts_tab.configure_ftp_save_sync()
        elif handler == "ra_viewer" and hasattr(self.main_window, "scripts_tab"):
            self.main_window.scripts_tab.edit_ra_viewer_config()
        elif handler == "retroachievement_cores" and hasattr(self.main_window, "extras_tab"):
            self.main_window.extras_tab.edit_ra_cores_config()
        else:
            QMessageBox.information(self, "Install Center", "Configuration is not available for this item yet.")
        self.refresh_status()

    def run_selected(self, output_widget=None):
        item = self.selected_item()
        if not item:
            return
        handler = item.get("handler") or item.get("id")
        status = self.statuses.get(item.get("id"), {})
        if handler == "update_all" and hasattr(self.main_window, "scripts_tab"):
            self.main_window.scripts_tab.update_all_installed = bool(status.get("installed"))
            task = prepare_update_all_task(self.main_window, parent=self)
            if task is None:
                return
            self.start_task(
                "Running update_all...",
                task,
                "update_all finished.",
                output_widget=output_widget,
                result_handler=lambda result: handle_update_all_result(self.main_window, result),
            )
            return
        QMessageBox.information(self, "Install Center", "Run is not available for this item.")

    def install_wallpaper_selected(self, variant=None, output_widget=None):
        item = self.selected_item()
        if not item:
            return
        context = build_context(self.main_window)
        ready, reason = context_ready(context)
        if not ready:
            QMessageBox.warning(self, "Install Center", reason)
            return
        label = item.get("name", "Wallpaper Pack")
        if variant == "169":
            label += " 16:9"
        elif variant == "43":
            label += " 4:3"
        self.start_task(
            f"Installing {label}...",
            lambda log: install_wallpaper_pack(item, context, log, variant=variant),
            f"{label} finished successfully.",
            output_widget=output_widget,
        )

    def open_wallpaper_folder_selected(self):
        context = build_context(self.main_window)
        ready, reason = context_ready(context)
        if not ready:
            QMessageBox.warning(self, "Install Center", reason)
            return
        try:
            open_wallpaper_folder(context)
        except Exception as e:
            QMessageBox.critical(self, "Install Center", str(e))

    def refresh_existing_tabs(self):
        for attr in ("scripts_tab", "extras_tab", "wallpapers_tab", "device_tab"):
            tab = getattr(self.main_window, attr, None)
            if tab is not None and hasattr(tab, "refresh_status"):
                try:
                    tab.refresh_status()
                except Exception:
                    pass

    def update_connection_state(self, lightweight=True):
        if not lightweight:
            self.refresh_status()
        else:
            self.populate_items()

import json
import os
from datetime import datetime

import requests
from PIL import Image
from PyQt6.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QFileDialog, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMenu, QMessageBox,
    QPushButton, QRadioButton, QSlider, QTextEdit, QVBoxLayout,
    QWidget, QColorDialog, QInputDialog, QSizePolicy,
)

from .cassette_renderer import CassetteRendererMixin, fit_fill
from . import services
from .card_renderer import (
    load_image_from_bytes, load_image_from_file, load_image_from_url,
    maybe_cache_web_image,
)
from .card_widget import SelectDialog, pil_to_pixmap
from .config import (
    TEMPLATE_DIR, get_value, set_value, load_api_key, load_icon_pack_dir,
    load_cassette_output_dir, load_search_cached_logos, output_images_dir,
    output_pdfs_dir, resource_path, sanitize_filename,
)


IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp)"


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class CassetteArtworkWorker(QThread):
    item = pyqtSignal(object)
    done = pyqtSignal(object)
    error = pyqtSignal(object)

    def __init__(self, mode, payload, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.payload = payload

    def run(self):
        count = 0
        search_id = self.payload["search_id"]
        try:
            if self.mode == "system":
                paths, total = services.search_system_logos(
                    self.payload["query"], self.payload["folder"],
                    self.payload["search_cached"], {},
                )
                for path in paths:
                    if self.isInterruptionRequested():
                        return
                    try:
                        with open(path, "rb") as handle:
                            self.item.emit({"search_id": search_id, "data": handle.read(), "name": os.path.basename(path), "source": path})
                        count += 1
                    except OSError:
                        continue
                self.done.emit({"search_id": search_id, "count": count, "total": total})
                return

            source = self.payload["source"]
            artwork_kind = self.payload["artwork_kind"]
            entry = self.payload["entry"]
            if source == "steam":
                images = services.get_grids(entry["id"]) if artwork_kind == "poster" else services.get_steam_logos(entry["id"])
                name = entry.get("name") or "Artwork"
                candidates = [item for item in images if artwork_kind != "poster" or item.get("width", 0) < item.get("height", 0)]
                urls = [item.get("url") for item in candidates]
            else:
                images = services.tmdb_get_posters(entry) if artwork_kind == "poster" else services.tmdb_get_logos(entry)
                name = entry.get("title") or "Artwork"
                urls = [services.TMDB_IMG_BASE + item["file_path"] for item in images if item.get("file_path")]

            for url in urls:
                if self.isInterruptionRequested():
                    return
                try:
                    response = requests.get(url, timeout=15)
                    response.raise_for_status()
                    self.item.emit({"search_id": search_id, "data": response.content, "name": name, "source": url})
                    count += 1
                except Exception:
                    continue
            self.done.emit({"search_id": search_id, "count": count, "total": count})
        except Exception as exc:
            self.error.emit({"search_id": search_id, "message": str(exc)})
            self.done.emit({"search_id": search_id, "count": count, "total": count})


class ArtworkSearchDialog(QDialog):
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.kind_label = {
            "poster": "Poster",
            "title_logo": "Title Logo",
            "system_logo": "System Logo",
        }.get(kind, "Artwork")
        self.selected_image = None
        self.selected_name = None
        self.worker = None
        self.workers = []
        self.search_id = 0
        self.setWindowTitle(f"Search {self.kind_label}")
        self.resize(920, 680)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        type_label = QLabel(f"Type: {self.kind_label}")
        type_label.setStyleSheet("font-weight: 700;")
        row.addWidget(type_label)
        self.steam_source = None
        self.tmdb_source = None
        if kind in ("poster", "title_logo"):
            self.steam_source = QCheckBox("SteamGridDB")
            self.steam_source.setChecked(bool(load_api_key("steamgriddb")))
            self.steam_source.setEnabled(bool(load_api_key("steamgriddb")))
            self.tmdb_source = QCheckBox("TMDB")
            self.tmdb_source.setChecked(bool(load_api_key("tmdb")))
            self.tmdb_source.setEnabled(bool(load_api_key("tmdb")))
            row.addWidget(self.steam_source)
            row.addWidget(self.tmdb_source)
        else:
            row.addWidget(QLabel("System Logo Pack"))
        self.query = QLineEdit()
        if kind == "system_logo":
            self.query.setPlaceholderText("Search by platform or logo name")
        else:
            self.query.setPlaceholderText(f"Search for a game, movie or TV show {self.kind_label.lower()}")
        button = QPushButton("Search")
        row.addWidget(self.query, 1)
        row.addWidget(button)
        layout.addLayout(row)
        self.results = QListWidget()
        self.results.setViewMode(QListWidget.ViewMode.IconMode)
        self.results.setIconSize(pil_to_pixmap(Image.new("RGBA", (150, 220))).size())
        self.results.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.results.setSpacing(8)
        layout.addWidget(self.results, 1)
        status_row = QHBoxLayout()
        self.status = QLabel("")
        choose = QPushButton("Use Selected")
        close = QPushButton("Cancel")
        status_row.addWidget(self.status, 1)
        status_row.addWidget(choose)
        status_row.addWidget(close)
        layout.addLayout(status_row)
        button.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)
        choose.clicked.connect(self.choose)
        close.clicked.connect(self.reject)
        self.results.itemDoubleClicked.connect(lambda *_: self.choose())

    def _add(self, image, name):
        from PyQt6.QtGui import QIcon
        thumb = image.copy()
        thumb.thumbnail((150, 220), Image.LANCZOS)
        from PyQt6.QtWidgets import QListWidgetItem
        item = QListWidgetItem(QIcon(pil_to_pixmap(thumb)), name or "Artwork")
        item.setData(Qt.ItemDataRole.UserRole, image)
        self.results.addItem(item)

    def search(self):
        query = self.query.text().strip()
        if not query:
            return
        self.results.clear()
        self.status.setText("Searching…")
        try:
            if self.kind == "system_logo":
                self._start_worker("system", {
                    "query": query,
                    "folder": load_icon_pack_dir(),
                    "search_cached": load_search_cached_logos(),
                })
                return
            use_steam = self.steam_source and self.steam_source.isChecked()
            use_tmdb = self.tmdb_source and self.tmdb_source.isChecked()
            if not use_steam and not use_tmdb:
                raise RuntimeError("Select at least one configured source.")
            titles = []
            if use_steam:
                titles.extend(("steam", game) for game in services.search_games(query))
            if use_tmdb:
                titles.extend(("tmdb", entry) for entry in services.tmdb_search_multi(query))
            if not titles:
                self.status.setText("No titles found")
                return
            labels = []
            for source, entry in titles:
                name = entry.get("name") if source == "steam" else entry.get("title")
                labels.append(f"{name or 'Unknown'}  [{ 'SteamGridDB' if source == 'steam' else 'TMDB' }]")
            select = SelectDialog("Select Title", labels, self)
            select.list_widget.itemClicked.connect(lambda *_: select.accept_selection())
            if select.exec() != QDialog.DialogCode.Accepted:
                self.status.clear()
                return
            if select.result_index is None:
                self.status.clear()
                return
            source, entry = titles[select.result_index]
            select.deleteLater()
            self._start_worker("web", {
                "source": source,
                "entry": entry,
                "artwork_kind": "poster" if self.kind == "poster" else "logo",
            })
        except Exception as exc:
            self.status.setText(str(exc))

    def _start_worker(self, mode, payload):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
        self.results.clear()
        self.status.setText("Loading images…")
        self.search_id += 1
        payload = dict(payload, search_id=self.search_id)
        worker = CassetteArtworkWorker(mode, payload, self)
        worker.item.connect(self._worker_item)
        worker.done.connect(self._worker_done)
        worker.error.connect(self._worker_error)
        worker.finished.connect(lambda current=worker: self._cleanup_worker(current))
        self.worker = worker
        self.workers.append(worker)
        worker.start()

    def _worker_item(self, item):
        if item.get("search_id") != self.search_id:
            return
        try:
            image = load_image_from_bytes(item["data"])
            if self.kind != "system_logo":
                cache_kind = "poster" if self.kind == "poster" else "logo"
                image = maybe_cache_web_image(image, item["source"], cache_kind)
            self._add(image, item["name"])
            self.status.setText(f"Loading images… {self.results.count()} loaded")
        except Exception:
            pass

    def _worker_done(self, info):
        if info.get("search_id") != self.search_id:
            return
        count = info.get("count", 0)
        total = info.get("total", count)
        if total > count:
            self.status.setText(f"Showing first {count} of {total} matching logos")
        else:
            self.status.setText(f"{count} image{'s' if count != 1 else ''} found" if count else "No images found")

    def _worker_error(self, info):
        if info.get("search_id") == self.search_id:
            self.status.setText(info.get("message", "Artwork search failed"))

    def _cleanup_worker(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)
        if self.worker is worker:
            self.worker = None

    def closeEvent(self, event):
        self._stop_workers()
        super().closeEvent(event)

    def accept(self):
        self._stop_workers()
        super().accept()

    def reject(self):
        self._stop_workers()
        super().reject()

    def _stop_workers(self):
        for worker in self.workers:
            if worker.isRunning():
                worker.requestInterruption()

    def choose(self):
        item = self.results.currentItem()
        if item:
            self.selected_image = item.data(Qt.ItemDataRole.UserRole)
            self.selected_name = item.text()
            self.accept()


class PosterEditorDialog(QDialog):
    def __init__(self, poster, overlays, parent=None):
        super().__init__(parent)
        self.poster = poster
        self.overlays = [dict(item) for item in overlays]
        self.editor_h = 600
        self.editor_w = int(self.editor_h * 1027 / 1435)
        self.setWindowTitle("Poster Editor")
        self.resize(760, 720)
        layout = QHBoxLayout(self)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview, 1)
        side = QVBoxLayout()
        self.list = QListWidget()
        side.addWidget(QLabel("Overlays"))
        side.addWidget(self.list, 1)
        add = QPushButton("Add Overlay (File)")
        add_url = QPushButton("Add Overlay (URL)")
        remove = QPushButton("Delete Overlay")
        up = QPushButton("Layer Up")
        down = QPushButton("Layer Down")
        clear = QPushButton("Clear Overlays")
        side.addWidget(add)
        side.addWidget(add_url)
        side.addWidget(remove)
        side.addWidget(up)
        side.addWidget(down)
        side.addWidget(clear)
        form = QFormLayout()
        self.x = QSlider(Qt.Orientation.Horizontal); self.x.setRange(0, self.editor_w)
        self.y = QSlider(Qt.Orientation.Horizontal); self.y.setRange(0, self.editor_h)
        self.scale = QSlider(Qt.Orientation.Horizontal); self.scale.setRange(10, 300); self.scale.setValue(100)
        form.addRow("Horizontal", self.x)
        form.addRow("Vertical", self.y)
        form.addRow("Scale", self.scale)
        side.addLayout(form)
        buttons = QHBoxLayout()
        apply_btn = QPushButton("Apply To Cover")
        cancel = QPushButton("Cancel")
        buttons.addWidget(apply_btn); buttons.addWidget(cancel)
        side.addLayout(buttons)
        layout.addLayout(side)
        add.clicked.connect(self.add_overlay)
        add_url.clicked.connect(self.add_overlay_url)
        remove.clicked.connect(self.remove_overlay)
        up.clicked.connect(lambda: self.move_overlay(1))
        down.clicked.connect(lambda: self.move_overlay(-1))
        clear.clicked.connect(lambda: (self.overlays.clear(), self.rebuild_list(), self.refresh()))
        self.list.currentRowChanged.connect(self.load_selected)
        self.x.valueChanged.connect(self.update_selected)
        self.y.valueChanged.connect(self.update_selected)
        self.scale.valueChanged.connect(self.update_selected)
        apply_btn.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        self.rebuild_list()
        self.refresh()

    def add_overlay(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Overlay", "", IMAGE_FILTER)
        if not path:
            return
        image = load_image_from_file(path)
        initial_scale = min(1.0, 500 / max(image.size))
        self.overlays.append({"image": image, "name": os.path.basename(path), "x": self.editor_w // 2, "y": self.editor_h // 2, "scale": initial_scale})
        self.rebuild_list(len(self.overlays) - 1)

    def add_overlay_url(self):
        url, ok = QInputDialog.getText(self, "Add Overlay from URL", "Image URL:")
        if ok and url.strip():
            try:
                image = load_image_from_url(url.strip())
                initial_scale = min(1.0, 500 / max(image.size))
                self.overlays.append({"image": image, "name": "Web overlay", "x": self.editor_w // 2, "y": self.editor_h // 2, "scale": initial_scale})
                self.rebuild_list(len(self.overlays) - 1)
            except Exception as exc:
                QMessageBox.critical(self, "Poster Editor", str(exc))

    def remove_overlay(self):
        row = self.list.currentRow()
        if row >= 0:
            self.overlays.pop(row)
            self.rebuild_list(min(row, len(self.overlays) - 1))

    def move_overlay(self, direction):
        row = self.list.currentRow(); target = row + direction
        if row >= 0 and 0 <= target < len(self.overlays):
            self.overlays[row], self.overlays[target] = self.overlays[target], self.overlays[row]
            self.rebuild_list(target)

    def rebuild_list(self, row=0):
        self.list.blockSignals(True); self.list.clear()
        self.list.addItems([item.get("name", "Overlay") for item in self.overlays])
        self.list.blockSignals(False)
        if self.overlays:
            self.list.setCurrentRow(max(0, row))

    def load_selected(self, row):
        if 0 <= row < len(self.overlays):
            item = self.overlays[row]
            for control, value in ((self.x, item["x"]), (self.y, item["y"]), (self.scale, int(item["scale"] * 100))):
                control.blockSignals(True); control.setValue(int(value)); control.blockSignals(False)
        self.refresh()

    def update_selected(self):
        row = self.list.currentRow()
        if 0 <= row < len(self.overlays):
            self.overlays[row].update(x=self.x.value(), y=self.y.value(), scale=self.scale.value() / 100)
        self.refresh()

    def refresh(self):
        image = fit_fill(self.poster.convert("RGBA"), self.editor_w, self.editor_h)
        for item in self.overlays:
            overlay = item["image"].copy()
            overlay = overlay.resize((max(1, int(overlay.width * item["scale"])), max(1, int(overlay.height * item["scale"]))), Image.LANCZOS)
            image.paste(overlay, (int(item["x"] - overlay.width / 2), int(item["y"] - overlay.height / 2)), overlay)
        self.preview.setPixmap(pil_to_pixmap(image))


class NFCCassetteWidget(CassetteRendererMixin, QWidget):
    ASSET_LABELS = {
        "poster": "Poster", "title_logo_default": "Title Logo",
        "title_logo_spine": "Title Logo (Spine)", "title_logo_back": "Title Logo (Back)",
        "system_logo_default": "System Logo", "system_logo_front": "System Logo (Front)",
        "system_logo_spine": "System Logo (Spine)", "system_logo_back": "System Logo (Back)",
        "original_cover_back": "Original Cover", "screenshot": "Screenshot",
    }

    def __init__(self, settings_callback=None, parent=None):
        super().__init__(parent)
        self.settings_callback = settings_callback
        saved = get_value("cassette", {})
        default_colors = {"back": (20, 20, 20), "spine": (30, 30, 30), "banner": (200, 30, 30), "text": (255, 255, 255)}
        self.colors = {key: tuple(saved.get("colors", {}).get(key, value)) for key, value in default_colors.items()}
        default_nfc = {"front": "white", "spine": "white", "back": "white"}
        self.nfc_logo_colors = {key: saved.get("nfc_logo", {}).get(key, value) for key, value in default_nfc.items()}
        self.assets = {key: None for key in self.ASSET_LABELS}
        self.assets["summary"] = ""
        self.asset_paths = {}
        self.system_logo_paths = {"default": None, "front": None, "spine": None, "back": None}
        self.poster_orientation = "portrait"
        self.poster_overlays = []
        self.editor_h = 600
        self.editor_w = int(self.editor_h * 1027 / 1435)
        self.crop_mode_var = _Value("center")
        self.crop_offset_var = _Value(0)
        self.nfc_logos = {
            "white": load_image_from_file(resource_path("nfc_logo_white.png")),
            "black": load_image_from_file(resource_path("nfc_logo_black.png")),
        }
        self._build_ui()
        self.update_preview()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.addStretch(1)

        colors = QGroupBox("Cover Colors")
        color_layout = QGridLayout(colors)
        self.color_edits = {}
        self.color_swatches = {}
        for row, key in enumerate(("back", "spine", "banner", "text")):
            color_layout.addWidget(QLabel(key.capitalize()), row, 0)
            swatch = QLabel()
            swatch.setFixedSize(24, 20)
            self.color_swatches[key] = swatch
            color_layout.addWidget(swatch, row, 1)
            edit = QLineEdit(self.rgb_to_hex(self.colors[key]))
            edit.setFixedWidth(82)
            edit.textChanged.connect(lambda value, k=key: self.hex_color_changed(k, value))
            self.color_edits[key] = edit
            color_layout.addWidget(edit, row, 2)
            picker = QPushButton("🎨")
            picker.setFixedWidth(34)
            picker.clicked.connect(lambda _, k=key: self.pick_color(k))
            color_layout.addWidget(picker, row, 3)
            self.update_color_swatch(key)
        top.addWidget(colors)

        nfc = QGroupBox("NFC Logo Color")
        nfc_layout = QGridLayout(nfc)
        self.nfc_groups = {}
        for row, side in enumerate(("front", "spine", "back")):
            nfc_layout.addWidget(QLabel(side.capitalize()), row, 0)
            group = QButtonGroup(self)
            group.setExclusive(True)
            self.nfc_groups[side] = group
            for column, value in enumerate(("white", "black", "none"), 1):
                button = QPushButton(value.capitalize())
                button.setCheckable(True)
                button.setChecked(self.nfc_logo_colors[side] == value)
                button.clicked.connect(lambda _, s=side, v=value: self.nfc_changed(s, v))
                group.addButton(button)
                nfc_layout.addWidget(button, row, column)
        top.addWidget(nfc)

        summary_group = QGroupBox("Back Summary")
        summary_layout = QVBoxLayout(summary_group)
        self.summary = QTextEdit()
        self.summary.setFixedSize(300, 104)
        self.summary.textChanged.connect(self.summary_changed)
        summary_layout.addWidget(self.summary)
        top.addWidget(summary_group)
        top.addStretch(1)
        root.addLayout(top)

        assets_outer = QHBoxLayout()
        assets_outer.addStretch(1)
        assets = QGroupBox("Assets")
        asset_layout = QHBoxLayout(assets)
        self.poster_button = self.asset_button("Poster", "poster", searchable=True)
        asset_layout.addWidget(self.poster_button)
        asset_layout.addWidget(self.asset_button("Screenshot", "screenshot"))
        asset_layout.addWidget(self.asset_button("Original Cover", "original_cover_back"))
        self.title_button = self.logo_button("Title Logo", "title", ("spine", "back"), web_search=True)
        asset_layout.addWidget(self.title_button)
        self.system_button = self.logo_button("System Logo", "system", ("front", "spine", "back"), folder_search=True)
        asset_layout.addWidget(self.system_button)
        self.poster_editor_button = QPushButton("Poster Editor")
        self.poster_editor_button.clicked.connect(self.open_editor)
        asset_layout.addWidget(self.poster_editor_button)
        assets_outer.addWidget(assets)

        self.crop_group = QGroupBox("Poster Crop")
        crop_layout = QVBoxLayout(self.crop_group)
        crop_buttons = QHBoxLayout()
        self.crop_button_group = QButtonGroup(self)
        self.crop_buttons = {}
        for value, label in (("center", "Center"), ("top", "Top"), ("bottom", "Bottom"), ("manual", "Manual")):
            button = QRadioButton(label)
            button.setChecked(value == "center")
            button.toggled.connect(lambda checked, v=value: checked and self.set_crop_mode(v))
            self.crop_button_group.addButton(button)
            self.crop_buttons[value] = button
            crop_buttons.addWidget(button)
        crop_layout.addLayout(crop_buttons)
        self.crop_slider = QSlider(Qt.Orientation.Horizontal)
        self.crop_slider.setRange(0, 1000)
        self.crop_slider.valueChanged.connect(self.crop_slider_changed)
        crop_layout.addWidget(self.crop_slider)
        assets_outer.addWidget(self.crop_group)
        assets_outer.addStretch(1)
        root.addLayout(assets_outer)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(1, 1)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        root.addWidget(self.preview, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        for text, callback in (
            ("Export", self.export), ("Export As...", self.export_as),
            ("Create Print PDF", self.print_pdf), ("Load Template", self.load_template),
            ("Save Template", self.save_template), ("Open Output Folder", self.open_output),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            if text == "Open Output Folder":
                self.open_output_button = button
            footer.addWidget(button)
        footer.addStretch(1)
        root.addLayout(footer)
        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status)
        self.update_ui_state()

    def asset_button(self, label, key, searchable=False):
        button = QPushButton(f"{label} ▼")
        menu = QMenu(button)
        menu.addAction("Import from file", lambda: self.load_file(key))
        menu.addAction("Import from URL", lambda: self.load_url(key))
        if searchable:
            menu.addSeparator()
            action = menu.addAction("Search...", lambda: self.search_art(key))
            self.poster_search_action = action
        menu.addSeparator()
        menu.addAction("Clear", lambda: self.clear_asset(key))
        button.setMenu(menu)
        return button

    def logo_button(self, label, family, overrides, web_search=False, folder_search=False):
        button = QPushButton(f"{label} ▼")
        menu = QMenu(button)
        all_sides = self.logo_target_menu(family, "default", web_search, folder_search)
        menu.addMenu(all_sides).setText("All Sides")
        menu.addSeparator()
        override_actions = []
        for side in overrides:
            submenu = self.logo_target_menu(family, side, web_search, folder_search)
            action = menu.addMenu(submenu)
            action.setText(f"Override {side.capitalize()}")
            override_actions.append(action)
        if family == "title":
            self.title_override_actions = override_actions
        else:
            self.system_override_actions = override_actions
        button.setMenu(menu)
        return button

    def logo_target_menu(self, family, target, web_search, folder_search):
        menu = QMenu(self)
        key = f"{family}_logo_default" if target == "default" else f"{family}_logo_{target}"
        menu.addAction("Import from file", lambda: self.load_logo(family, target, "file"))
        menu.addAction("Import from URL", lambda: self.load_logo(family, target, "url"))
        menu.addSeparator()
        if web_search:
            action = menu.addAction("Search...", lambda: self.search_art(key))
            if not hasattr(self, "title_search_actions"):
                self.title_search_actions = []
            self.title_search_actions.append((target, action))
        if folder_search:
            action = menu.addAction("Search Folder...", lambda: self.search_art(key))
            if not hasattr(self, "system_search_actions"):
                self.system_search_actions = []
            self.system_search_actions.append(action)
        menu.addSeparator()
        menu.addAction("Clear", lambda: self.clear_logo(family, target))
        return menu

    def render(self):
        return super().render()

    def crop_poster(self, image, width, height):
        return super().crop_poster(image, width, height)

    def update_preview(self):
        try:
            image = self.render()
            available_w = max(140, self.preview.width() - 12)
            available_h = max(120, self.preview.height() - 12)
            image.thumbnail((available_w, available_h), Image.LANCZOS)
            self.preview.setPixmap(pil_to_pixmap(image))
        except Exception as exc:
            self.status.setText(str(exc))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.update_preview)

    def changed(self):
        QTimer.singleShot(0, self.update_preview)

    def load_file(self, key):
        path, _ = QFileDialog.getOpenFileName(self, f"Select {self.ASSET_LABELS[key]}", "", IMAGE_FILTER)
        if path:
            try:
                self.set_asset(key, load_image_from_file(path), path)
            except Exception as exc:
                QMessageBox.critical(self, "NFC Cassette Cover", str(exc))

    def load_url(self, key):
        url, ok = QInputDialog.getText(self, "Load from URL", "Image URL:")
        if ok and url.strip():
            try:
                kind = "poster" if key == "poster" else "logo"
                image = maybe_cache_web_image(load_image_from_url(url.strip()), url.strip(), kind)
                self.set_asset(key, image, url.strip())
            except Exception as exc:
                QMessageBox.critical(self, "NFC Cassette Cover", str(exc))

    def search_art(self, key):
        if key == "poster":
            kind = "poster"
        elif key.startswith("title_logo"):
            kind = "title_logo"
        else:
            kind = "system_logo"
        dialog = ArtworkSearchDialog(kind, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_asset(key, dialog.selected_image, dialog.selected_name)

    def set_asset(self, key, image, source=None):
        if key.startswith("title_logo_") and key != "title_logo_default" and not self.assets["title_logo_default"]:
            return
        if key.startswith("system_logo_") and key != "system_logo_default" and not self.assets["system_logo_default"]:
            return
        if key == "title_logo_default":
            self.assets["title_logo_spine"] = None
            self.assets["title_logo_back"] = None
        elif key == "system_logo_default":
            for side in ("front", "spine", "back"):
                self.assets[f"system_logo_{side}"] = None
                self.asset_paths.pop(f"system_logo_{side}", None)
                self.system_logo_paths[side] = None
        self.assets[key] = image
        self.asset_paths[key] = source
        if key.startswith("system_logo_"):
            target = key.removeprefix("system_logo_")
            self.system_logo_paths[target] = source
        if key == "poster":
            self.poster_orientation = "landscape" if image.width > image.height else "portrait"
        self.update_ui_state()
        self.changed()

    def clear_asset(self, key):
        self.assets[key] = None
        self.asset_paths.pop(key, None)
        self.update_ui_state()
        self.changed()

    def load_logo(self, family, target, source):
        key = f"{family}_logo_default" if target == "default" else f"{family}_logo_{target}"
        if source == "file":
            self.load_file(key)
        else:
            self.load_url(key)

    def clear_logo(self, family, target):
        key = f"{family}_logo_default" if target == "default" else f"{family}_logo_{target}"
        self.assets[key] = None
        self.asset_paths.pop(key, None)
        if family == "system":
            self.system_logo_paths[target] = None
        if target == "default":
            sides = ("spine", "back") if family == "title" else ("front", "spine", "back")
            for side in sides:
                override_key = f"{family}_logo_{side}"
                self.assets[override_key] = None
                self.asset_paths.pop(override_key, None)
                if family == "system":
                    self.system_logo_paths[side] = None
        self.update_ui_state()
        self.changed()

    def set_crop_mode(self, mode):
        self.crop_mode_var.value = mode
        self.crop_slider.setVisible(mode == "manual")
        self.changed()

    def crop_slider_changed(self):
        self.crop_offset_var.value = self.crop_slider.value()
        self.changed()

    @staticmethod
    def rgb_to_hex(rgb):
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def update_color_swatch(self, key):
        self.color_swatches[key].setStyleSheet(
            f"background-color: {self.rgb_to_hex(self.colors[key])}; border: 1px solid palette(mid);"
        )

    def hex_color_changed(self, key, value):
        value = value.strip()
        if not value.startswith("#"):
            value = "#" + value
        if len(value) != 7:
            return
        try:
            self.colors[key] = tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))
        except ValueError:
            return
        self.update_color_swatch(key)
        self.save_appearance()
        self.changed()

    def pick_color(self, key):
        color = QColorDialog.getColor(QColor(*self.colors[key]), self, f"Choose {key} color")
        if color.isValid():
            self.colors[key] = (color.red(), color.green(), color.blue())
            self.color_edits[key].setText(self.rgb_to_hex(self.colors[key]))
            self.update_color_swatch(key)
            self.save_appearance()
            self.changed()

    def nfc_changed(self, side, value):
        self.nfc_logo_colors[side] = value.lower()
        self.save_appearance()
        self.changed()

    def save_appearance(self):
        set_value("cassette", {
            "colors": {key: list(value) for key, value in self.colors.items()},
            "nfc_logo": dict(self.nfc_logo_colors),
        })

    def summary_changed(self):
        self.assets["summary"] = self.summary.toPlainText(); self.changed()

    def open_editor(self):
        if not self.assets["poster"]:
            QMessageBox.information(self, "Poster Editor", "Load a poster first."); return
        dialog = PosterEditorDialog(self.assets["poster"], self.poster_overlays, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.poster_overlays = dialog.overlays; self.changed()

    def open_settings(self):
        if self.settings_callback:
            self.settings_callback()
            self.update_ui_state()

    def update_ui_state(self):
        has_poster = self.assets["poster"] is not None
        if hasattr(self, "crop_group"):
            self.crop_group.setVisible(has_poster)
            self.poster_editor_button.setVisible(has_poster)
            landscape = has_poster and self.poster_orientation == "landscape"
            self.crop_buttons["top"].setText("Left" if landscape else "Top")
            self.crop_buttons["bottom"].setText("Right" if landscape else "Bottom")
            self.crop_slider.setVisible(has_poster and self.crop_mode_var.get() == "manual")
        has_title = self.assets["title_logo_default"] is not None
        for action in getattr(self, "title_override_actions", []):
            action.setEnabled(has_title)
        has_system = self.assets["system_logo_default"] is not None
        for action in getattr(self, "system_override_actions", []):
            action.setEnabled(has_system)
        has_api = bool(load_api_key("steamgriddb") or load_api_key("tmdb"))
        if hasattr(self, "poster_search_action"):
            self.poster_search_action.setEnabled(has_api)
        for target, action in getattr(self, "title_search_actions", []):
            action.setEnabled(has_api and (target == "default" or has_title))
        folder = load_icon_pack_dir()
        folder_ready = bool(folder and os.path.isdir(folder))
        for action in getattr(self, "system_search_actions", []):
            action.setEnabled(folder_ready)
        if hasattr(self, "open_output_button"):
            self.open_output_button.setEnabled(bool(load_cassette_output_dir()))

    def export(self):
        folder = output_images_dir(load_cassette_output_dir())
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"cassette_cover_{datetime.now():%Y-%m-%d_%H-%M-%S}.png"
        self.render().save(path, "PNG", dpi=(300, 300)); self.status.setText(f"Saved: {path}")
        self.update_ui_state()

    def export_as(self):
        folder = output_images_dir(load_cassette_output_dir())
        folder.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Cassette Cover", str(folder / "cassette_cover.png"), "PNG Image (*.png)"
        )
        if path:
            self.render().save(path, "PNG", dpi=(300, 300)); self.status.setText(f"Saved: {path}")

    def open_output(self):
        folder = load_cassette_output_dir()
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def save_template(self):
        name, ok = QInputDialog.getText(self, "Save Template", "Template name:")
        if not ok or not name.strip():
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Template Options")
        dialog.setFixedSize(300, 230)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Include in template:"))
        colors = QCheckBox("Colors"); colors.setChecked(True)
        nfc = QCheckBox("NFC Logo Modes"); nfc.setChecked(True)
        system = QCheckBox("System Logo"); system.setChecked(True)
        layout.addWidget(colors); layout.addWidget(nfc); layout.addWidget(system)
        layout.addStretch(1)
        save = QPushButton("Save Template")
        save.clicked.connect(dialog.accept)
        layout.addWidget(save)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = {"version": 1}
        if colors.isChecked():
            data["colors"] = {key: list(value) for key, value in self.colors.items()}
        if nfc.isChecked():
            data["nfc_logo"] = dict(self.nfc_logo_colors)
        if system.isChecked():
            paths = {key: value for key, value in self.system_logo_paths.items() if value}
            if paths:
                data["system_logo_paths"] = paths
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        path = TEMPLATE_DIR / f"{sanitize_filename(name)}.json"
        try:
            with path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
            QMessageBox.information(self, "Template Saved", f"Template '{name}' saved.")
        except Exception as exc:
            QMessageBox.critical(self, "Save Template", str(exc))

    def load_template(self):
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(TEMPLATE_DIR.glob("*.json"), key=lambda path: path.name.lower())
        if not files:
            QMessageBox.information(self, "Templates", "No templates found.")
            return
        choose = SelectDialog("Load Template", [path.name for path in files], self)
        if choose.exec() != QDialog.DialogCode.Accepted:
            return
        path = files[choose.result_index]
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.colors.update({k: tuple(v) for k, v in data.get("colors", {}).items()})
            self.nfc_logo_colors.update(data.get("nfc_logo", {}))
            for target, source in data.get("system_logo_paths", {}).items():
                try:
                    image = load_image_from_url(source) if source.startswith(("http://", "https://")) else load_image_from_file(source)
                    key = "system_logo_default" if target == "default" else f"system_logo_{target}"
                    self.assets[key] = image
                    self.asset_paths[key] = source
                    self.system_logo_paths[target] = source
                except Exception:
                    continue
            for key in self.colors:
                self.color_edits[key].setText(self.rgb_to_hex(self.colors[key]))
                self.update_color_swatch(key)
            for side, group in self.nfc_groups.items():
                for button in group.buttons():
                    button.setChecked(button.text().lower() == self.nfc_logo_colors[side])
            self.save_appearance()
            self.update_ui_state()
            self.changed()
        except Exception as exc: QMessageBox.critical(self, "Load Template", str(exc))

    def print_pdf(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Print PDF Template")
        dialog.resize(950, 900)
        layout = QVBoxLayout(dialog)
        preview = QLabel()
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(preview, 1)
        status = QLabel()
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(status)
        slots = [None, None]

        def render_page():
            page = Image.new("RGB", (2480, 3508), "white")
            cover_w = round((104 / 25.4) * 300)
            cover_h = round((101.5 / 25.4) * 300)
            gap = round((8 / 25.4) * 300)
            y = (3508 - cover_h * 2 - gap) // 2
            x = (2480 - cover_w) // 2
            from PIL import ImageDraw
            draw = ImageDraw.Draw(page)
            for image in slots:
                if image is not None:
                    page.paste(fit_fill(image.convert("RGB"), cover_w, cover_h), (x, y))
                if cutlines_check.isChecked():
                    draw.rectangle(
                        (x, y, x + cover_w - 1, y + cover_h - 1),
                        outline=(0, 0, 0), width=2,
                    )
                y += cover_h + gap
            return page

        def refresh():
            if slots[0] is None and slots[1] is not None:
                slots[0], slots[1] = slots[1], None
            status.setText(
                f"Cover 1: {'Loaded' if slots[0] is not None else 'Empty'}    "
                f"Cover 2: {'Loaded' if slots[1] is not None else 'Empty'}"
            )
            page = render_page()
            page.thumbnail((450, 640), Image.LANCZOS)
            preview.setPixmap(pil_to_pixmap(page))

        def load_slot(index):
            path, _ = QFileDialog.getOpenFileName(dialog, "Select Cover Image", "", IMAGE_FILTER)
            if path:
                slots[index] = load_image_from_file(path)
                refresh()

        def load_multiple():
            paths, _ = QFileDialog.getOpenFileNames(dialog, "Select Cover Images", "", IMAGE_FILTER)
            for index, path in enumerate(paths[:2]):
                slots[index] = load_image_from_file(path)
            if len(paths) == 1:
                slots[1] = None
            refresh()

        controls = QGridLayout()
        actions = (
            ("Load Cover 1", lambda: load_slot(0)), ("Load Cover 2", lambda: load_slot(1)),
            ("Load Covers", load_multiple), ("Clear Cover 1", lambda: (slots.__setitem__(0, None), refresh())),
            ("Clear Cover 2", lambda: (slots.__setitem__(1, None), refresh())),
            ("Clear All", lambda: (slots.__setitem__(0, None), slots.__setitem__(1, None), refresh())),
        )
        for index, (text, callback) in enumerate(actions):
            button = QPushButton(text)
            button.clicked.connect(callback)
            controls.addWidget(button, index // 3, index % 3)
        layout.addLayout(controls)
        cutlines_check = QCheckBox("Show cutlines / borders")
        cutlines_check.setChecked(False)
        cutlines_check.toggled.connect(lambda *_: refresh())
        cutlines_row = QHBoxLayout()
        cutlines_row.addStretch(1)
        cutlines_row.addWidget(cutlines_check)
        cutlines_row.addStretch(1)
        layout.addLayout(cutlines_row)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        export = QPushButton("Export PDF")
        close = QPushButton("Close")
        bottom.addWidget(export); bottom.addWidget(close); bottom.addStretch(1)
        layout.addLayout(bottom)

        def export_pdf():
            if slots[0] is None and slots[1] is None:
                QMessageBox.warning(dialog, "Print PDF", "Load at least one cover first.")
                return
            pdf_dir = output_pdfs_dir(load_cassette_output_dir())
            pdf_dir.mkdir(parents=True, exist_ok=True)
            path, _ = QFileDialog.getSaveFileName(
                dialog, "Save Print PDF", str(pdf_dir / "cassette_print_sheet.pdf"), "PDF File (*.pdf)"
            )
            if path:
                render_page().save(path, "PDF", resolution=300.0)
                QMessageBox.information(dialog, "Export Complete", f"Print PDF saved to:\n{path}")

        export.clicked.connect(export_pdf)
        close.clicked.connect(dialog.accept)
        refresh()
        dialog.exec()

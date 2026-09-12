from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.cloud_account import CLOUD_DASHBOARD_URL, CloudAccountClient
from core.custom_themes import (
    is_valid_color,
    load_custom_themes,
    normalize_theme_id,
    save_theme_creator_theme,
)
from core.open_helpers import open_uri
from ui.dialogs.theme_sync_conflicts_dialog import ThemeSyncConflictsDialog

PATREON_URL = "https://www.patreon.com/Anime0t4ku"


class ColorField(QWidget):
    changed = pyqtSignal()

    def __init__(self, value="#000000", parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.swatch = QPushButton()
        self.swatch.setFixedWidth(42)
        self.swatch.setToolTip("Choose color")
        self.swatch.clicked.connect(self.choose_color)
        row.addWidget(self.swatch)

        self.edit = QLineEdit()
        self.edit.setMaxLength(7)
        self.edit.setPlaceholderText("#RRGGBB")
        self.edit.textChanged.connect(self._text_changed)
        row.addWidget(self.edit, 1)

        self.set_value(value)

    def _text_changed(self):
        self._update_swatch()
        self.changed.emit()

    def _update_swatch(self):
        value = self.value()
        if is_valid_color(value):
            self.swatch.setStyleSheet(f"background-color: {value}; border: 1px solid palette(mid); border-radius: 4px;")
        else:
            self.swatch.setStyleSheet("border: 1px solid palette(mid); border-radius: 4px;")

    def choose_color(self):
        start = QColor(self.value() if is_valid_color(self.value()) else "#000000")
        dialog = QColorDialog(start, self)
        dialog.setWindowTitle("Choose Theme Color")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        if dialog.exec():
            color = dialog.currentColor()
            if color.isValid():
                self.edit.setText(color.name(QColor.NameFormat.HexRgb))

    def value(self):
        return self.edit.text().strip()

    def set_value(self, value):
        self.edit.setText(str(value or "").strip() or "#000000")
        self._update_swatch()


class ThemeCreatorWidget(QWidget):
    preview_requested = pyqtSignal(dict)
    saved = pyqtSignal(str)

    def __init__(self, config_data: dict, parent=None):
        super().__init__(parent)
        self.config_data = config_data
        self.cloud_client = CloudAccountClient(config_data)
        self.creator_themes = []
        self.current_source = None
        self.current_theme_id = ""
        self.current_companion = {}
        self.build_ui()
        self.refresh_access()

    def build_ui(self):
        self.layout_root = QVBoxLayout(self)
        self.layout_root.setContentsMargins(0, 0, 0, 0)
        self.layout_root.setSpacing(12)

        self.locked_widget = QWidget()
        locked = QVBoxLayout(self.locked_widget)
        locked.setContentsMargins(18, 24, 18, 24)
        locked.setSpacing(12)
        locked.addStretch()
        title = QLabel("Theme Creator is available to Patreon supporters.")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        locked.addWidget(title)
        info = QLabel(
            "Link Companion with RetroAccount and make sure you have an active eligible Patreon membership to create custom themes."
        )
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        locked.addWidget(info)
        links = QHBoxLayout()
        links.addStretch()
        support = QPushButton("Become a supporter")
        support.clicked.connect(lambda: self._open_url(PATREON_URL))
        portal = QPushButton("Open Companion Cloud")
        portal.clicked.connect(lambda: self._open_url(CLOUD_DASHBOARD_URL))
        links.addWidget(support)
        links.addWidget(portal)
        links.addStretch()
        locked.addLayout(links)
        locked.addStretch()
        self.layout_root.addWidget(self.locked_widget)

        self.editor_widget = QWidget()
        editor = QVBoxLayout(self.editor_widget)
        editor.setContentsMargins(0, 0, 0, 0)
        editor.setSpacing(10)

        top = QHBoxLayout()
        top.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.currentIndexChanged.connect(self.load_selected_theme)
        top.addWidget(self.theme_combo, 1)
        new_button = QPushButton("New Theme")
        new_button.clicked.connect(self.new_theme)
        top.addWidget(new_button)
        editor.addLayout(top)

        form = QFormLayout()
        form.setSpacing(8)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("My Theme")
        self.name_edit.textChanged.connect(self._name_changed)
        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("my_theme")
        self.id_edit.setReadOnly(True)
        self.id_edit.setToolTip("Generated automatically from the theme name.")
        self.author_edit = QLineEdit()
        self.author_edit.setPlaceholderText("Your name")
        self.author_edit.textChanged.connect(self.update_buttons)
        self.colors = {
            "background": ColorField("#17121f"),
            "surface": ColorField("#241b30"),
            "accent": ColorField("#8f62ff"),
            "text": ColorField("#f2ecff"),
        }
        for field in self.colors.values():
            field.changed.connect(self.update_buttons)

        form.addRow("Name", self.name_edit)
        form.addRow("Theme ID (automatic)", self.id_edit)
        form.addRow("Author", self.author_edit)
        form.addRow("Background", self.colors["background"])
        form.addRow("Surface", self.colors["surface"])
        form.addRow("Accent", self.colors["accent"])
        form.addRow("Text", self.colors["text"])
        editor.addLayout(form)

        note = QLabel("Test Theme applies the current draft temporarily. Nothing is saved until you choose Save Theme.")
        note.setWordWrap(True)
        editor.addWidget(note)

        actions = QHBoxLayout()
        actions.addStretch()
        self.test_button = QPushButton("Test Theme")
        self.test_button.clicked.connect(self.test_theme)
        self.save_button = QPushButton("Save Theme")
        self.save_button.clicked.connect(self.save_theme)
        actions.addWidget(self.test_button)
        actions.addWidget(self.save_button)
        editor.addLayout(actions)
        self.layout_root.addWidget(self.editor_widget)

    def _open_url(self, url):
        try:
            open_uri(url)
        except Exception as e:
            QMessageBox.warning(self, "Open Link", str(e))

    def has_access(self):
        if not (self.cloud_client.has_session() and self.cloud_client.linked_device()):
            return False
        entitlement = self.cloud_client.entitlement()
        features = entitlement.get("features") if isinstance(entitlement.get("features"), dict) else {}
        return bool(entitlement.get("eligible")) and bool(features.get("theme_creator"))

    def refresh_access(self):
        access = self.has_access()
        self.locked_widget.setVisible(not access)
        self.editor_widget.setVisible(access)
        if access:
            self.reload_creator_themes()
            self.new_theme()

    def reload_creator_themes(self):
        self.creator_themes = [
            theme for theme in load_custom_themes()[0]
            if str(theme.get("category") or "").strip().lower() == "theme_creator"
            and str((theme.get("companion") or {}).get("created_with") or "").strip().lower() == "theme_creator"
        ]
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItem("New Theme", None)
        for theme in self.creator_themes:
            self.theme_combo.addItem(theme.get("name", theme.get("id", "Theme")), theme)
        self.theme_combo.blockSignals(False)

    @staticmethod
    def _generated_id(name: str) -> str:
        return normalize_theme_id(name).replace("-", "_")

    def _name_changed(self):
        if not self.current_source:
            self.id_edit.setText(self._generated_id(self.name_edit.text()))
        self.update_buttons()

    def new_theme(self):
        self.current_source = None
        self.current_theme_id = ""
        self.current_companion = {}
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(0)
        self.theme_combo.blockSignals(False)
        self.name_edit.setText("")
        self.id_edit.setText("")
        self.author_edit.setText("")
        self.colors["background"].set_value("#17121f")
        self.colors["surface"].set_value("#241b30")
        self.colors["accent"].set_value("#8f62ff")
        self.colors["text"].set_value("#f2ecff")
        self.update_buttons()

    def load_selected_theme(self):
        theme = self.theme_combo.currentData()
        if not isinstance(theme, dict):
            self.new_theme()
            return
        self.current_source = theme.get("source")
        self.current_theme_id = normalize_theme_id(theme.get("id"))
        self.current_companion = dict(theme.get("companion") or {})
        self.name_edit.setText(str(theme.get("name") or ""))
        self.id_edit.setText(str(theme.get("id") or ""))
        self.author_edit.setText(str(theme.get("author") or ""))
        for field in self.colors:
            self.colors[field].set_value(str(theme.get(field) or ""))
        self.update_buttons()

    def draft(self):
        data = {
            "id": self.current_theme_id or self._generated_id(self.name_edit.text()),
            "name": self.name_edit.text().strip(),
            "author": self.author_edit.text().strip() or "Unknown",
            "background": self.colors["background"].value(),
            "surface": self.colors["surface"].value(),
            "accent": self.colors["accent"].value(),
            "text": self.colors["text"].value(),
            "category": "theme_creator",
            "companion": dict(self.current_companion),
        }
        data["companion"].update({"type": "custom_theme", "created_with": "theme_creator", "schema_version": 1})
        return data

    def valid_draft(self):
        data = self.draft()
        if not data["id"] or not data["name"]:
            return False
        return all(is_valid_color(data[field]) for field in ("background", "surface", "accent", "text"))

    def update_buttons(self):
        valid = self.valid_draft()
        self.test_button.setEnabled(valid)
        self.save_button.setEnabled(valid)

    def test_theme(self):
        if self.valid_draft():
            self.preview_requested.emit(self.draft())

    def save_theme(self):
        if not self.valid_draft():
            return
        data = self.draft()
        try:
            target = save_theme_creator_theme(data, self.current_source)
            self.current_source = str(target)
            self.current_theme_id = data["id"]
            self.current_companion = dict(data.get("companion") or {})
            try:
                sync_result = self.cloud_client.sync_custom_themes()
                if isinstance(sync_result, dict) and sync_result.get("status") == "resolution_required":
                    plan = sync_result.get("initial_plan") if isinstance(sync_result.get("initial_plan"), dict) else {}
                    conflicts = sync_result.get("conflicts") if isinstance(sync_result.get("conflicts"), list) else []
                    dialog = ThemeSyncConflictsDialog(
                        conflicts,
                        reserved_theme_ids=plan.get("reserved_theme_ids") if isinstance(plan.get("reserved_theme_ids"), list) else [],
                        parent=self,
                    )
                    if dialog.exec() == dialog.DialogCode.Accepted:
                        self.cloud_client.resolve_custom_theme_sync(plan, dialog.resolutions())
            except Exception as sync_error:
                QMessageBox.warning(
                    self,
                    "Theme Saved",
                    f"The theme was saved locally, but Companion Cloud sync failed. It will retry later.\n\n{sync_error}",
                )
            self.reload_creator_themes()
            idx = next((i for i in range(self.theme_combo.count()) if isinstance(self.theme_combo.itemData(i), dict) and self.theme_combo.itemData(i).get("source") == str(target)), 0)
            self.theme_combo.setCurrentIndex(idx)
            self.saved.emit(f"custom:{data['id']}")
        except Exception as e:
            QMessageBox.warning(self, "Save Theme", str(e))

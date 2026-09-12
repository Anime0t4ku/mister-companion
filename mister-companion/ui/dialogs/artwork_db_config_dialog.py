from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.update_all_config import ARTWORKDB_SOURCES


class ArtworkDbConfigDialog(QDialog):
    def __init__(self, selected_ids=None, parent=None):
        super().__init__(parent)

        self.selected_ids = set(selected_ids or [])
        self.checkboxes = {}

        self.setWindowTitle("Game Artwork DB's")
        self.resize(520, 650)
        self.setMinimumSize(420, 450)

        self.build_ui()
        self.load_selected()

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        title = QLabel("Game Artwork DB's")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        outer.addWidget(title)

        description = QLabel(
            "Select which game artwork databases should be added to update_all."
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(description)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search systems...")
        outer.addWidget(self.search_edit)

        button_row = QHBoxLayout()
        self.select_all_button = QPushButton("Select All")
        self.select_none_button = QPushButton("Select None")
        button_row.addWidget(self.select_all_button)
        button_row.addWidget(self.select_none_button)
        outer.addLayout(button_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        content = QWidget()
        self.list_layout = QVBoxLayout(content)
        self.list_layout.setContentsMargins(6, 6, 6, 6)
        self.list_layout.setSpacing(4)
        scroll.setWidget(content)

        for source_id, label, _url in ARTWORKDB_SOURCES:
            checkbox = QCheckBox(label)
            checkbox.setProperty("source_id", source_id)
            checkbox.setProperty("search_text", f"{source_id} {label}".lower())
            self.checkboxes[source_id] = checkbox
            self.list_layout.addWidget(checkbox)

        self.list_layout.addStretch()

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(line)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        self.ok_button = QPushButton("OK")
        self.cancel_button = QPushButton("Cancel")
        bottom_row.addWidget(self.ok_button)
        bottom_row.addWidget(self.cancel_button)
        bottom_row.addStretch()
        outer.addLayout(bottom_row)

        self.search_edit.textChanged.connect(self.apply_filter)
        self.select_all_button.clicked.connect(self.select_all_visible)
        self.select_none_button.clicked.connect(self.select_none_visible)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def load_selected(self):
        for source_id, checkbox in self.checkboxes.items():
            checkbox.setChecked(source_id in self.selected_ids)

    def apply_filter(self):
        query = self.search_edit.text().strip().lower()
        for checkbox in self.checkboxes.values():
            search_text = checkbox.property("search_text") or ""
            checkbox.setVisible(not query or query in search_text)

    def select_all_visible(self):
        for checkbox in self.checkboxes.values():
            if checkbox.isVisible():
                checkbox.setChecked(True)

    def select_none_visible(self):
        for checkbox in self.checkboxes.values():
            if checkbox.isVisible():
                checkbox.setChecked(False)

    def get_selected_ids(self):
        return [
            source_id
            for source_id, _label, _url in ARTWORKDB_SOURCES
            if self.checkboxes[source_id].isChecked()
        ]

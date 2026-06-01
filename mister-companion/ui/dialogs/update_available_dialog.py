from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class UpdateAvailableDialog(QDialog):
    ACTION_CANCEL = "cancel"
    ACTION_SHOW_CHANGELOG = "show_changelog"
    ACTION_UPDATE = "update"

    def __init__(self, info, update_button_text: str, update_message: str, parent=None):
        super().__init__(parent)

        self.info = info
        self.update_button_text = update_button_text
        self.update_message = update_message
        self.selected_action = self.ACTION_CANCEL

        self.setWindowTitle("Update Available")
        self.setMinimumWidth(480)

        self.build_ui()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        title_label = QLabel("A new version of MiSTer Companion is available.")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        main_layout.addWidget(title_label)

        message_label = QLabel(
            f"Current version: {self.info.current_version}\n"
            f"Latest version: {self.info.latest_version}\n\n"
            f"{self.update_message}"
        )
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(message_label)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        self.changelog_button = QPushButton("Show Changelog")
        self.changelog_button.setMinimumWidth(130)
        button_row.addWidget(self.changelog_button)

        button_row.addStretch()

        self.update_button = QPushButton(self.update_button_text)
        self.update_button.setMinimumWidth(130)
        button_row.addWidget(self.update_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setMinimumWidth(100)
        button_row.addWidget(self.cancel_button)

        main_layout.addLayout(button_row)

        self.changelog_button.clicked.connect(self.show_changelog_selected)
        self.update_button.clicked.connect(self.update_selected)
        self.cancel_button.clicked.connect(self.reject)

    def show_changelog_selected(self):
        self.selected_action = self.ACTION_SHOW_CHANGELOG
        self.accept()

    def update_selected(self):
        self.selected_action = self.ACTION_UPDATE
        self.accept()

    def reject(self):
        self.selected_action = self.ACTION_CANCEL
        super().reject()

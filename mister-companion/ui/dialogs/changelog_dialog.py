from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class ChangelogDialog(QDialog):
    def __init__(self, release_name: str, release_body: str, parent=None):
        super().__init__(parent)

        self.release_name = release_name or "Latest Release"
        self.release_body = release_body or "No changelog text is available for this release."

        self.setWindowTitle("Release Changelog")
        self.setMinimumSize(680, 520)

        self.build_ui()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        title_label = QLabel(self.release_name)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        main_layout.addWidget(title_label)

        self.changelog_view = QTextEdit()
        self.changelog_view.setReadOnly(True)
        self.changelog_view.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.set_changelog_text()
        main_layout.addWidget(self.changelog_view, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()

        close_button = QPushButton("Close")
        close_button.setMinimumWidth(100)
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)

        main_layout.addLayout(button_row)

    def set_changelog_text(self):
        if hasattr(self.changelog_view, "setMarkdown"):
            self.changelog_view.setMarkdown(self.release_body)
        else:
            self.changelog_view.setPlainText(self.release_body)

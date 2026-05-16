from core.open_helpers import open_uri

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


KOFI_URL = "https://ko-fi.com/anime0t4ku"
BUYMEACOFFEE_URL = "https://www.buymeacoffee.com/anime0t4ku"


class SupportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Support MiSTer Companion")
        self.setMinimumWidth(460)

        self.build_ui()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        title_label = QLabel("Support MiSTer Companion")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        main_layout.addWidget(title_label)

        message_label = QLabel(
            "Thank you for using MiSTer Companion!\n\n"
            "I build and maintain this app in my free time. If it has been useful "
            "to you and you would like to support continued development, you can "
            "leave a small donation through Ko-fi or Buy Me a Coffee.\n\n"
            "No pressure at all, just knowing people use the app already means a lot."
        )
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(message_label)

        support_row = QHBoxLayout()
        support_row.setSpacing(8)
        support_row.addStretch()

        self.kofi_button = QPushButton("Ko-fi")
        self.kofi_button.setMinimumWidth(120)

        self.buymeacoffee_button = QPushButton("Buy Me a Coffee")
        self.buymeacoffee_button.setMinimumWidth(150)

        support_row.addWidget(self.kofi_button)
        support_row.addWidget(self.buymeacoffee_button)
        support_row.addStretch()

        main_layout.addLayout(support_row)

        self.kofi_button.clicked.connect(self.open_kofi)
        self.buymeacoffee_button.clicked.connect(self.open_buymeacoffee)

    def open_kofi(self):
        open_uri(KOFI_URL)

    def open_buymeacoffee(self):
        open_uri(BUYMEACOFFEE_URL)
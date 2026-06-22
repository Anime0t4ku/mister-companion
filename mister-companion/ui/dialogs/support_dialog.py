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
PATREON_URL = "https://www.patreon.com/Anime0t4ku"


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
            "MiSTer Companion is free, and support is completely optional.\n\n"
            "Ko-fi and Buy Me a Coffee are available for one-time donations if "
            "you would like to support continued development.\n\n"
            "You can also become a Patreon member for added benefits, including "
            "the exclusive MiSTer Companion theme pack and more benefits planned "
            "for the future."
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

        self.patreon_button = QPushButton("Patreon")
        self.patreon_button.setMinimumWidth(120)

        support_row.addWidget(self.kofi_button)
        support_row.addWidget(self.buymeacoffee_button)
        support_row.addWidget(self.patreon_button)
        support_row.addStretch()

        main_layout.addLayout(support_row)

        self.kofi_button.clicked.connect(self.open_kofi)
        self.buymeacoffee_button.clicked.connect(self.open_buymeacoffee)
        self.patreon_button.clicked.connect(self.open_patreon)

    def open_kofi(self):
        open_uri(KOFI_URL)

    def open_buymeacoffee(self):
        open_uri(BUYMEACOFFEE_URL)

    def open_patreon(self):
        open_uri(PATREON_URL)

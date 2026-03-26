import sys
import webbrowser

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class SetupNoticeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("MiSTer Setup Required")
        self.setModal(True)
        self.setFixedSize(540, 360)

        self.dont_show_again = False

        if sys.platform.startswith("win"):
            tool_name = "Rufus"
            tool_url = "https://rufus.ie/en/"
        else:
            tool_name = "balenaEtcher"
            tool_url = "https://etcher.balena.io/"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("MiSTer Companion Setup")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        message = QLabel(
            "This application assumes you have already flashed\n"
            "MiSTerFusion to your SD card.\n\n"
            "If you have not done so yet, download MiSTerFusion\n"
            f"and flash it using {tool_name} before continuing."
        )
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setWordWrap(True)
        layout.addWidget(message)

        button_row = QHBoxLayout()
        self.misterfusion_button = QPushButton("Download MiSTerFusion")
        self.flash_tool_button = QPushButton(f"Download {tool_name}")

        self.misterfusion_button.clicked.connect(
            lambda: webbrowser.open("https://github.com/MiSTer-devel/mr-fusion/releases")
        )
        self.flash_tool_button.clicked.connect(
            lambda: webbrowser.open(tool_url)
        )

        button_row.addStretch()
        button_row.addWidget(self.misterfusion_button)
        button_row.addWidget(self.flash_tool_button)
        button_row.addStretch()
        layout.addLayout(button_row)

        self.hide_checkbox = QCheckBox("Don't show this again")
        checkbox_row = QHBoxLayout()
        checkbox_row.addStretch()
        checkbox_row.addWidget(self.hide_checkbox)
        checkbox_row.addStretch()
        layout.addLayout(checkbox_row)

        layout.addStretch()

        continue_row = QHBoxLayout()
        self.continue_button = QPushButton("Continue")
        self.continue_button.clicked.connect(self.handle_continue)

        continue_row.addStretch()
        continue_row.addWidget(self.continue_button)
        continue_row.addStretch()
        layout.addLayout(continue_row)

    def handle_continue(self):
        self.dont_show_again = self.hide_checkbox.isChecked()
        self.accept()
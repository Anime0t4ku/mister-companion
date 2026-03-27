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

        self.parent_window = parent
        self.dont_show_again = False

        self.setWindowTitle("MiSTer Setup Required")
        self.setModal(True)
        self.setFixedSize(540, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("MiSTer Companion Setup")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        if sys.platform == "darwin":
            self.build_macos_layout(layout)
        else:
            self.build_windows_linux_layout(layout)

        self.hide_checkbox = QCheckBox("Don't show this again")
        checkbox_row = QHBoxLayout()
        checkbox_row.addStretch()
        checkbox_row.addWidget(self.hide_checkbox)
        checkbox_row.addStretch()
        layout.addLayout(checkbox_row)

        layout.addStretch()

        continue_row = QHBoxLayout()
        continue_row.addStretch()
        self.continue_button = QPushButton("Close")
        self.continue_button.clicked.connect(self.handle_continue)
        continue_row.addWidget(self.continue_button)
        continue_row.addStretch()
        layout.addLayout(continue_row)

    def build_macos_layout(self, layout):
        tool_name = "balenaEtcher"
        tool_url = "https://etcher.balena.io/"

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

    def build_windows_linux_layout(self, layout):
        if sys.platform.startswith("win"):
            privilege_text = "Run MiSTer Companion as Administrator before flashing."
        else:
            privilege_text = "Run MiSTer Companion with sudo or root privileges before flashing."

        message = QLabel(
            "MiSTer Companion can now handle Mr. Fusion setup directly from the\n"
            "Flash Mr. Fusion tab.\n\n"
            "From there, you can download the latest Mr. Fusion image and balena CLI,\n"
            "select your SD card, and flash it directly from inside the app.\n\n"
            f"{privilege_text}"
        )
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setWordWrap(True)
        layout.addWidget(message)

        button_row = QHBoxLayout()
        self.open_flash_tab_button = QPushButton("Open Flash Mr. Fusion Tab")
        self.open_flash_tab_button.clicked.connect(self.open_flash_tab)

        button_row.addStretch()
        button_row.addWidget(self.open_flash_tab_button)
        button_row.addStretch()
        layout.addLayout(button_row)

    def open_flash_tab(self):
        if self.parent_window and hasattr(self.parent_window, "tabs") and hasattr(self.parent_window, "flash_tab"):
            self.parent_window.tabs.setCurrentWidget(self.parent_window.flash_tab)
        self.handle_continue()

    def handle_continue(self):
        self.dont_show_again = self.hide_checkbox.isChecked()
        self.accept()
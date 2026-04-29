from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)


class ZapScriptsScanNoticeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Before scanning")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        text = QLabel(
            "Scanning in MiSTer Companion requires a populated Zaparoo media database.\n\n"
            "You can build that database using the Zaparoo mobile app or the Zaparoo script on your MiSTer.\n\n"
            "Fetching your game list in MiSTer Companion can take a while, especially with large libraries.\n\n"
            "If you add new games and want them to appear here, you will need to rescan in Zaparoo first, "
            "and then rescan in MiSTer Companion."
        )
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(text)

        self.dont_show_again = QCheckBox("Don’t show this again")
        layout.addWidget(self.dont_show_again)

        buttons = QDialogButtonBox()
        self.continue_btn = buttons.addButton("Continue", QDialogButtonBox.ButtonRole.AcceptRole)
        self.exit_btn = buttons.addButton("Exit", QDialogButtonBox.ButtonRole.RejectRole)

        self.continue_btn.clicked.connect(self.accept)
        self.exit_btn.clicked.connect(self.reject)

        layout.addWidget(buttons)

    def should_skip_next_time(self) -> bool:
        return self.dont_show_again.isChecked()
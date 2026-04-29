from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from core.language import tr


class ZapScriptsScanNoticeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("zapscripts_scan_notice_dialog.window_title"))
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        text = QLabel(tr("zapscripts_scan_notice_dialog.message"))
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(text)

        self.dont_show_again = QCheckBox(tr("zapscripts_scan_notice_dialog.dont_show_again"))
        layout.addWidget(self.dont_show_again)

        buttons = QDialogButtonBox()
        self.continue_btn = buttons.addButton(
            tr("zapscripts_scan_notice_dialog.continue"),
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self.exit_btn = buttons.addButton(
            tr("zapscripts_scan_notice_dialog.exit"),
            QDialogButtonBox.ButtonRole.RejectRole,
        )

        self.continue_btn.clicked.connect(self.accept)
        self.exit_btn.clicked.connect(self.reject)

        layout.addWidget(buttons)

    def should_skip_next_time(self) -> bool:
        return self.dont_show_again.isChecked()
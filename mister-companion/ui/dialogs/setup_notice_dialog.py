import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.config import save_config
from core.language import available_languages, current_language, tr


class SetupNoticeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.parent_window = parent
        self.dont_show_again = False

        self.setWindowTitle(tr("setup_notice_dialog.window_title"))
        self.setModal(True)
        self.setFixedSize(540, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel(tr("setup_notice_dialog.title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self.build_flash_sd_layout(layout)
        self.build_language_selector(layout)

        self.hide_checkbox = QCheckBox(tr("setup_notice_dialog.dont_show_again"))
        checkbox_row = QHBoxLayout()
        checkbox_row.addStretch()
        checkbox_row.addWidget(self.hide_checkbox)
        checkbox_row.addStretch()
        layout.addLayout(checkbox_row)

        layout.addStretch()

        continue_row = QHBoxLayout()
        continue_row.addStretch()
        self.continue_button = QPushButton(tr("common.close"))
        self.continue_button.clicked.connect(self.handle_continue)
        continue_row.addWidget(self.continue_button)
        continue_row.addStretch()
        layout.addLayout(continue_row)

    def build_flash_sd_layout(self, layout):
        if sys.platform.startswith("win"):
            privilege_text = tr("setup_notice_dialog.privilege_windows")
        elif sys.platform == "darwin":
            privilege_text = tr("setup_notice_dialog.privilege_macos")
        else:
            privilege_text = tr("setup_notice_dialog.privilege_linux")

        message = QLabel(
            tr("setup_notice_dialog.message", privilege_text=privilege_text)
        )
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setWordWrap(True)
        layout.addWidget(message)

        button_row = QHBoxLayout()

        self.open_flash_tab_button = QPushButton(tr("setup_notice_dialog.open_flash_sd_tab"))
        self.open_flash_tab_button.clicked.connect(self.open_flash_tab)

        button_row.addStretch()
        button_row.addWidget(self.open_flash_tab_button)
        button_row.addStretch()
        layout.addLayout(button_row)

    def build_language_selector(self, layout):
        language_row = QHBoxLayout()
        language_row.setSpacing(8)

        self.language_label = QLabel(tr("language.label"))

        self.language_combo = QComboBox()

        for language in available_languages():
            self.language_combo.addItem(
                language.get("name", language.get("code", "en")),
                language.get("code", "en"),
            )

        saved_language = current_language()

        if self.parent_window and hasattr(self.parent_window, "config_data"):
            saved_language = self.parent_window.config_data.get("language", current_language())

        saved_language_index = self.language_combo.findData(saved_language)
        self.language_combo.setCurrentIndex(saved_language_index if saved_language_index >= 0 else 0)
        self.language_combo.currentIndexChanged.connect(self.on_language_changed)

        language_row.addStretch()
        language_row.addWidget(self.language_label)
        language_row.addWidget(self.language_combo)
        language_row.addStretch()

        layout.addLayout(language_row)

    def on_language_changed(self):
        language_code = self.language_combo.currentData() or "en"

        if not self.parent_window or not hasattr(self.parent_window, "config_data"):
            return

        if language_code == self.parent_window.config_data.get("language", "en"):
            return

        self.parent_window.config_data["language"] = language_code
        save_config(self.parent_window.config_data)

        QMessageBox.information(
            self,
            tr("language.restart_title"),
            tr("language.restart_message"),
        )

    def open_flash_tab(self):
        if self.parent_window and hasattr(self.parent_window, "tabs") and hasattr(self.parent_window, "flash_tab"):
            self.parent_window.tabs.setCurrentWidget(self.parent_window.flash_tab)
        self.handle_continue()

    def handle_continue(self):
        self.dont_show_again = self.hide_checkbox.isChecked()
        self.accept()
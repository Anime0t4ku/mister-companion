from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from core.config import save_config


class AppSettingsDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)

        self.main_window = main_window
        self.config_data = main_window.config_data

        self.setWindowTitle("App Settings")
        self.setMinimumWidth(480)

        self.build_ui()
        self.load_values()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        title_label = QLabel("App Settings")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        main_layout.addWidget(title_label)

        updates_group = QGroupBox("Updates")
        updates_layout = QVBoxLayout(updates_group)
        updates_layout.setSpacing(8)

        self.check_updates_on_startup_check = QCheckBox("Check for updates on startup")
        updates_layout.addWidget(self.check_updates_on_startup_check)

        update_row = QHBoxLayout()
        update_row.addStretch()
        self.check_updates_now_button = QPushButton("Check for Updates Now")
        self.check_updates_now_button.setMinimumWidth(180)
        self.check_updates_now_button.clicked.connect(self.check_for_updates_now)
        update_row.addWidget(self.check_updates_now_button)
        update_row.addStretch()
        updates_layout.addLayout(update_row)

        main_layout.addWidget(updates_group)

        notices_group = QGroupBox("Notices")
        notices_layout = QVBoxLayout(notices_group)
        notices_layout.setSpacing(8)

        self.show_setup_notice_check = QCheckBox("Show setup notice")
        self.show_update_all_warning_check = QCheckBox("Show Update All warning")
        self.show_zapscripts_scan_notice_check = QCheckBox("Show ZapScripts scan notice")

        notices_layout.addWidget(self.show_setup_notice_check)
        notices_layout.addWidget(self.show_update_all_warning_check)
        notices_layout.addWidget(self.show_zapscripts_scan_notice_check)

        main_layout.addWidget(notices_group)

        community_group = QGroupBox("Community")
        community_layout = QVBoxLayout(community_group)
        community_layout.setSpacing(8)

        community_text = QLabel(
            "Support continued development, report bugs, request features, or ask general questions."
        )
        community_text.setWordWrap(True)
        community_layout.addWidget(community_text)

        community_row = QHBoxLayout()
        community_row.addStretch()

        self.support_button = QPushButton("Support the App")
        self.support_button.setMinimumWidth(150)
        self.support_button.clicked.connect(self.open_support)
        community_row.addWidget(self.support_button)

        self.feedback_button = QPushButton("Report a Bug / Request Feature")
        self.feedback_button.setMinimumWidth(210)
        self.feedback_button.clicked.connect(self.open_feedback)
        community_row.addWidget(self.feedback_button)

        community_row.addStretch()
        community_layout.addLayout(community_row)

        main_layout.addWidget(community_group)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.save_and_accept)
        self.buttons.rejected.connect(self.reject)
        main_layout.addWidget(self.buttons)

    def load_values(self):
        self.check_updates_on_startup_check.setChecked(
            bool(self.config_data.get("check_updates_on_startup", True))
        )
        self.show_setup_notice_check.setChecked(
            not bool(self.config_data.get("hide_setup_notice", False))
        )
        self.show_update_all_warning_check.setChecked(
            not bool(self.config_data.get("hide_update_all_warning", False))
        )
        self.show_zapscripts_scan_notice_check.setChecked(
            not bool(self.config_data.get("hide_zapscripts_scan_notice", False))
        )

    def save_and_accept(self):
        self.config_data["check_updates_on_startup"] = self.check_updates_on_startup_check.isChecked()
        self.config_data["hide_setup_notice"] = not self.show_setup_notice_check.isChecked()
        self.config_data["hide_update_all_warning"] = not self.show_update_all_warning_check.isChecked()
        self.config_data["hide_zapscripts_scan_notice"] = not self.show_zapscripts_scan_notice_check.isChecked()
        save_config(self.config_data)
        self.accept()

    def check_for_updates_now(self):
        self.save_current_values()
        self.main_window.check_for_updates_manual()

    def open_support(self):
        self.main_window.open_support_dialog()

    def open_feedback(self):
        self.main_window.open_feedback()

    def save_current_values(self):
        self.config_data["check_updates_on_startup"] = self.check_updates_on_startup_check.isChecked()
        self.config_data["hide_setup_notice"] = not self.show_setup_notice_check.isChecked()
        self.config_data["hide_update_all_warning"] = not self.show_update_all_warning_check.isChecked()
        self.config_data["hide_zapscripts_scan_notice"] = not self.show_zapscripts_scan_notice_check.isChecked()
        save_config(self.config_data)

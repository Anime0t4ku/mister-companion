import sys

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QButtonGroup,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from core import mc_updater
from core.config import save_config
from ui.dialogs.mc_updater_progress_dialog import MCUpdaterProgressDialog


class MCUpdaterCheckWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, config_data: dict):
        super().__init__()
        self.config_data = config_data

    def run(self):
        try:
            self.result.emit(mc_updater.check_update_status(self.config_data))
        except Exception as e:
            self.error.emit(str(e))


class AppSettingsDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)

        self.main_window = main_window
        self.config_data = main_window.config_data
        self.mc_updater_check_worker = None
        self.mc_updater_latest_version = ""
        self.mc_updater_update_available = False
        self.show_mc_updater_settings = sys.platform != "darwin"

        self.setWindowTitle("App Settings")
        self.setMinimumWidth(520)

        self.build_ui()
        self.load_values()
        if self.show_mc_updater_settings:
            self.refresh_mc_updater_state()

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

        if self.show_mc_updater_settings:
            mc_updater_group = QGroupBox("MC-Updater")
            mc_updater_layout = QVBoxLayout(mc_updater_group)
            mc_updater_layout.setSpacing(8)

            mc_updater_text = QLabel("MC-Updater enables automatic updates for MiSTer Companion.")
            mc_updater_text.setWordWrap(True)
            mc_updater_layout.addWidget(mc_updater_text)

            self.mc_updater_status_label = QLabel("Status: Checking...")
            self.mc_updater_status_label.setWordWrap(True)
            mc_updater_layout.addWidget(self.mc_updater_status_label)

            mc_updater_check_row = QHBoxLayout()
            mc_updater_check_row.addStretch()
            self.mc_updater_check_button = QPushButton("Check for MC-Updater Updates")
            self.mc_updater_check_button.setMinimumWidth(230)
            self.mc_updater_check_button.clicked.connect(self.check_mc_updater_updates)
            mc_updater_check_row.addWidget(self.mc_updater_check_button)
            mc_updater_check_row.addStretch()
            mc_updater_layout.addLayout(mc_updater_check_row)

            mc_updater_action_row = QHBoxLayout()
            mc_updater_action_row.addStretch()

            self.mc_updater_install_button = QPushButton("Install MC-Updater")
            self.mc_updater_install_button.setMinimumWidth(170)
            self.mc_updater_install_button.clicked.connect(self.install_or_update_mc_updater)
            mc_updater_action_row.addWidget(self.mc_updater_install_button)

            self.mc_updater_remove_button = QPushButton("Remove MC-Updater")
            self.mc_updater_remove_button.setMinimumWidth(170)
            self.mc_updater_remove_button.clicked.connect(self.remove_mc_updater)
            mc_updater_action_row.addWidget(self.mc_updater_remove_button)

            mc_updater_action_row.addStretch()
            mc_updater_layout.addLayout(mc_updater_action_row)

            updates_layout.addWidget(mc_updater_group)
        main_layout.addWidget(updates_group)

        menu_style_group = QGroupBox("Menu style")
        menu_style_layout = QVBoxLayout(menu_style_group)
        menu_style_layout.setSpacing(8)

        menu_style_row = QHBoxLayout()
        self.menu_style_group = QButtonGroup(self)
        self.menu_style_side_menu_radio = QRadioButton("Side menu")
        self.menu_style_tabs_radio = QRadioButton("Tabs")
        self.menu_style_group.addButton(self.menu_style_side_menu_radio)
        self.menu_style_group.addButton(self.menu_style_tabs_radio)
        menu_style_row.addWidget(self.menu_style_side_menu_radio)
        menu_style_row.addWidget(self.menu_style_tabs_radio)
        menu_style_row.addStretch()
        menu_style_layout.addLayout(menu_style_row)

        main_layout.addWidget(menu_style_group)

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

        menu_style = str(self.config_data.get("menu_style", "side_menu") or "side_menu").strip().lower()
        if menu_style == "overlay":
            menu_style = "side_menu"
        if menu_style == "tabs":
            self.menu_style_tabs_radio.setChecked(True)
        else:
            self.menu_style_side_menu_radio.setChecked(True)

    def get_selected_menu_style(self):
        if self.menu_style_tabs_radio.isChecked():
            return "tabs"
        return "side_menu"

    def refresh_mc_updater_state(self, latest_status=None):
        local_status = mc_updater.get_local_status(self.config_data)

        self.mc_updater_latest_version = ""
        self.mc_updater_update_available = False

        if latest_status is not None:
            self.mc_updater_latest_version = latest_status.latest_version
            self.mc_updater_update_available = latest_status.update_available

        if not local_status.supported:
            self.mc_updater_status_label.setText("Status: Unsupported platform")
            self.mc_updater_check_button.setEnabled(False)
            self.mc_updater_install_button.setText("Install MC-Updater")
            self.mc_updater_install_button.setEnabled(False)
            self.mc_updater_remove_button.setEnabled(False)
            return

        self.mc_updater_check_button.setEnabled(local_status.installed)
        self.mc_updater_remove_button.setEnabled(local_status.installed)

        if not local_status.installed:
            if self.mc_updater_latest_version:
                self.mc_updater_status_label.setText(
                    f"Status: Not installed, latest {self.mc_updater_latest_version}"
                )
            else:
                self.mc_updater_status_label.setText("Status: Not installed")

            self.mc_updater_install_button.setText("Install MC-Updater")
            self.mc_updater_install_button.setEnabled(True)
            return

        if not local_status.installed_version:
            if self.mc_updater_latest_version:
                self.mc_updater_status_label.setText(
                    f"Status: Installed, unknown version, latest {self.mc_updater_latest_version}"
                )
            else:
                self.mc_updater_status_label.setText("Status: Installed, unknown version")

            self.mc_updater_install_button.setText("Update MC-Updater")
            self.mc_updater_install_button.setEnabled(True)
            return

        if self.mc_updater_update_available:
            self.mc_updater_status_label.setText(
                "Status: Update available, "
                f"installed {local_status.installed_version}, "
                f"latest {self.mc_updater_latest_version}"
            )
            self.mc_updater_install_button.setText("Update MC-Updater")
            self.mc_updater_install_button.setEnabled(True)
            return

        if self.mc_updater_latest_version:
            self.mc_updater_status_label.setText(
                f"Status: Installed, up to date, {local_status.installed_version}"
            )
        else:
            self.mc_updater_status_label.setText(
                f"Status: Installed, {local_status.installed_version}"
            )

        self.mc_updater_install_button.setText("Install MC-Updater")
        self.mc_updater_install_button.setEnabled(False)

    def save_and_accept(self):
        self.config_data["check_updates_on_startup"] = self.check_updates_on_startup_check.isChecked()
        self.config_data["hide_setup_notice"] = not self.show_setup_notice_check.isChecked()
        self.config_data["hide_update_all_warning"] = not self.show_update_all_warning_check.isChecked()
        self.config_data["hide_zapscripts_scan_notice"] = not self.show_zapscripts_scan_notice_check.isChecked()
        self.config_data["menu_style"] = self.get_selected_menu_style()
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        if hasattr(self.main_window, "apply_menu_style"):
            self.main_window.apply_menu_style()
        self.accept()

    def check_for_updates_now(self):
        self.save_current_values()
        self.main_window.check_for_updates_manual()

    def check_mc_updater_updates(self):
        if self.mc_updater_check_worker is not None and self.mc_updater_check_worker.isRunning():
            return

        self.save_current_values()
        self.mc_updater_check_button.setEnabled(False)
        self.mc_updater_check_button.setText("Checking...")

        self.mc_updater_check_worker = MCUpdaterCheckWorker(self.config_data)
        self.mc_updater_check_worker.result.connect(self.on_mc_updater_check_result)
        self.mc_updater_check_worker.error.connect(self.on_mc_updater_check_error)
        self.mc_updater_check_worker.finished.connect(self.on_mc_updater_check_finished)
        self.mc_updater_check_worker.start()

    def on_mc_updater_check_result(self, status):
        self.refresh_mc_updater_state(status)

    def on_mc_updater_check_error(self, message: str):
        QMessageBox.warning(
            self,
            "MC-Updater Check Failed",
            f"Could not check MC-Updater updates.\n\n{message}",
        )
        self.refresh_mc_updater_state()

    def on_mc_updater_check_finished(self):
        self.mc_updater_check_button.setText("Check for MC-Updater Updates")
        local_status = mc_updater.get_local_status(self.config_data)
        self.mc_updater_check_button.setEnabled(local_status.supported and local_status.installed)

    def install_or_update_mc_updater(self):
        self.save_current_values()
        local_status = mc_updater.get_local_status(self.config_data)
        action = "install"

        if local_status.installed:
            action = "update"

        dialog = MCUpdaterProgressDialog(self, action, self.config_data)
        dialog.exec()

        self.mc_updater_latest_version = ""
        self.mc_updater_update_available = False
        self.refresh_mc_updater_state()

    def remove_mc_updater(self):
        local_status = mc_updater.get_local_status(self.config_data)
        if not local_status.installed:
            self.refresh_mc_updater_state()
            return

        answer = QMessageBox.question(
            self,
            "Remove MC-Updater",
            "Remove MC-Updater from MiSTer Companion?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.save_current_values()
        dialog = MCUpdaterProgressDialog(self, "remove", self.config_data)
        dialog.exec()

        self.mc_updater_latest_version = ""
        self.mc_updater_update_available = False
        self.refresh_mc_updater_state()

    def open_support(self):
        self.main_window.open_support_dialog()

    def open_feedback(self):
        self.main_window.open_feedback()

    def save_current_values(self):
        self.config_data["check_updates_on_startup"] = self.check_updates_on_startup_check.isChecked()
        self.config_data["hide_setup_notice"] = not self.show_setup_notice_check.isChecked()
        self.config_data["hide_update_all_warning"] = not self.show_update_all_warning_check.isChecked()
        self.config_data["hide_zapscripts_scan_notice"] = not self.show_zapscripts_scan_notice_check.isChecked()
        self.config_data["menu_style"] = self.get_selected_menu_style()
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        if hasattr(self.main_window, "apply_menu_style"):
            self.main_window.apply_menu_style()

from PyQt6.QtCore import QEvent, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core import mc_updater
from core.config import save_config
from ui.tab_header import create_tab_header
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


class AppSettingsTab(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)

        self.main_window = main_window
        self.config_data = main_window.config_data
        self.mc_updater_check_worker = None
        self.mc_updater_latest_version = ""
        self.mc_updater_update_available = False
        self.show_mc_updater_settings = mc_updater.updater_supported()

        self.build_ui()
        self.load_values()
        if self.show_mc_updater_settings:
            self.refresh_mc_updater_state()

    def build_ui(self):
        self.setObjectName("AppSettingsPage")
        self.setStyleSheet(
            """
            QWidget#AppSettingsPage QWidget#AppSettingsTransparent,
            QWidget#AppSettingsPage QWidget#AppSettingsPanel,
            QWidget#AppSettingsPage QWidget#AppSettingsInline {
                background: transparent;
            }

            QWidget#AppSettingsPage QGroupBox#AppSettingsCard {
                background-color: palette(alternate-base);
                border: 1px solid palette(button);
                border-radius: 12px;
                margin-top: 18px;
                padding: 10px;
                font-weight: 700;
            }

            QWidget#AppSettingsPage QGroupBox#AppSettingsCard::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                padding: 0px 7px;
                background: transparent;
                color: palette(highlight);
            }

            QWidget#AppSettingsPage QLabel#AppSettingsSectionTitle {
                color: palette(highlight);
                font-weight: 700;
                background: transparent;
            }
            """
        )

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(10)

        root_layout.addWidget(create_tab_header(self.main_window, "App Settings", "settings"))

        body = QWidget()
        body.setObjectName("AppSettingsTransparent")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(28)
        root_layout.addWidget(body, 1)

        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        settings_scroll.setObjectName("AppSettingsTransparent")

        settings_panel = QWidget()
        settings_panel.setObjectName("AppSettingsPanel")
        self.settings_panel = settings_panel
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(8)
        settings_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        updates_group = QGroupBox("Updates")
        updates_group.setObjectName("AppSettingsCard")
        updates_layout = QVBoxLayout(updates_group)
        updates_layout.setContentsMargins(14, 18, 14, 10)
        updates_layout.setSpacing(7)

        updates_top_row = QHBoxLayout()
        updates_top_row.setSpacing(10)
        self.check_updates_on_startup_check = QCheckBox("Check for updates on startup")
        updates_top_row.addWidget(self.check_updates_on_startup_check)
        updates_top_row.addStretch(1)
        self.check_updates_now_button = QPushButton("Check for Updates Now")
        self.check_updates_now_button.setMinimumWidth(180)
        self.check_updates_now_button.clicked.connect(self.check_for_updates_now)
        updates_top_row.addWidget(self.check_updates_now_button)
        updates_layout.addLayout(updates_top_row)

        if self.show_mc_updater_settings:
            mc_updater_widget = QWidget()
            mc_updater_widget.setObjectName("AppSettingsInline")
            mc_updater_layout = QVBoxLayout(mc_updater_widget)
            mc_updater_layout.setContentsMargins(0, 2, 0, 0)
            mc_updater_layout.setSpacing(6)

            mc_updater_title = QLabel("MC-Updater")
            mc_updater_title.setObjectName("AppSettingsSectionTitle")
            mc_updater_layout.addWidget(mc_updater_title)

            mc_status_row = QHBoxLayout()
            mc_status_row.setSpacing(10)
            self.mc_updater_status_label = QLabel("Status: Checking...")
            self.mc_updater_status_label.setWordWrap(True)
            mc_status_row.addWidget(self.mc_updater_status_label, 1)
            self.mc_updater_check_button = QPushButton("Check for MC-Updater Updates")
            self.prepare_mc_updater_button(self.mc_updater_check_button, 210)
            self.mc_updater_check_button.clicked.connect(self.check_mc_updater_updates)
            mc_status_row.addWidget(self.mc_updater_check_button)
            mc_updater_layout.addLayout(mc_status_row)

            mc_action_row = QHBoxLayout()
            mc_action_row.setSpacing(8)
            mc_updater_text = QLabel("Automatic updates for MiSTer Companion")
            mc_updater_text.setWordWrap(True)
            mc_action_row.addWidget(mc_updater_text, 1)
            self.mc_updater_install_button = QPushButton("Install MC-Updater")
            self.prepare_mc_updater_button(self.mc_updater_install_button, 150)
            self.mc_updater_install_button.clicked.connect(self.install_or_update_mc_updater)
            mc_action_row.addWidget(self.mc_updater_install_button)
            self.mc_updater_remove_button = QPushButton("Remove MC-Updater")
            self.prepare_mc_updater_button(self.mc_updater_remove_button, 150)
            self.mc_updater_remove_button.clicked.connect(self.remove_mc_updater)
            mc_action_row.addWidget(self.mc_updater_remove_button)
            mc_updater_layout.addLayout(mc_action_row)
            updates_layout.addWidget(mc_updater_widget)
        settings_layout.addWidget(updates_group)

        notices_group = QGroupBox("Notices")
        notices_group.setObjectName("AppSettingsCard")
        notices_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        notices_layout = QGridLayout(notices_group)
        notices_layout.setContentsMargins(14, 18, 14, 10)
        notices_layout.setHorizontalSpacing(20)
        notices_layout.setVerticalSpacing(5)

        self.show_setup_notice_check = QCheckBox("Show setup notice")
        self.show_update_all_warning_check = QCheckBox("Show Update All warning")
        self.show_zapscripts_scan_notice_check = QCheckBox("Show ZapScripts scan notice")
        self.show_support_message_check = QCheckBox("Show support message")

        notices_layout.addWidget(self.show_setup_notice_check, 0, 0)
        notices_layout.addWidget(self.show_update_all_warning_check, 0, 1)
        notices_layout.addWidget(self.show_zapscripts_scan_notice_check, 1, 0)
        notices_layout.addWidget(self.show_support_message_check, 1, 1)
        settings_layout.addWidget(notices_group)

        community_group = QGroupBox("Community")
        community_group.setObjectName("AppSettingsCard")
        community_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        community_layout = QHBoxLayout(community_group)
        community_layout.setContentsMargins(14, 18, 14, 10)
        community_layout.setSpacing(10)

        community_text = QLabel("Support development, report bugs, request features, or ask questions.")
        community_text.setWordWrap(True)
        community_layout.addWidget(community_text, 1)

        self.support_button = QPushButton("Support the App")
        self.support_button.setMinimumWidth(140)
        self.support_button.clicked.connect(self.open_support)
        community_layout.addWidget(self.support_button)

        self.feedback_button = QPushButton("Report a Bug / Request Feature")
        self.feedback_button.setMinimumWidth(200)
        self.feedback_button.clicked.connect(self.open_feedback)
        community_layout.addWidget(self.feedback_button)
        settings_layout.addWidget(community_group)

        actions_group = QGroupBox("Actions")
        actions_group.setObjectName("AppSettingsCard")
        actions_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        actions_layout = QHBoxLayout(actions_group)
        actions_layout.setContentsMargins(14, 18, 14, 10)
        actions_layout.setSpacing(10)
        actions_layout.addStretch(1)

        self.reset_button = QPushButton("Reset Changes")
        self.reset_button.clicked.connect(self.load_values)
        actions_layout.addWidget(self.reset_button)

        self.save_button = QPushButton("Save Settings")
        self.save_button.clicked.connect(self.save_settings)
        actions_layout.addWidget(self.save_button)
        actions_layout.addStretch(1)
        settings_layout.addWidget(actions_group)
        self.actions_group = actions_group

        settings_scroll.setWidget(settings_panel)
        settings_scroll.setAlignment(Qt.AlignmentFlag.AlignTop)
        body_layout.addWidget(settings_scroll, 3)

        patreon_panel = QGroupBox("Patreon")
        patreon_panel.setObjectName("AppSettingsCard")
        self.patreon_panel = patreon_panel
        patreon_layout = QVBoxLayout(patreon_panel)
        patreon_layout.setContentsMargins(18, 22, 18, 18)
        patreon_layout.addStretch(1)

        patreon_placeholder = QLabel("Patreon options will be available here.")
        patreon_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        patreon_placeholder.setWordWrap(True)
        patreon_layout.addWidget(patreon_placeholder)

        patreon_layout.addStretch(1)
        body_layout.addWidget(patreon_panel, 2, Qt.AlignmentFlag.AlignTop)

        self.settings_panel.installEventFilter(self)
        QTimer.singleShot(0, self.sync_patreon_height)


    def eventFilter(self, obj, event):
        if obj is getattr(self, "settings_panel", None) and event.type() in (
            QEvent.Type.LayoutRequest,
            QEvent.Type.Resize,
        ):
            QTimer.singleShot(0, self.sync_patreon_height)
        return super().eventFilter(obj, event)

    def sync_patreon_height(self):
        settings_panel = getattr(self, "settings_panel", None)
        actions_group = getattr(self, "actions_group", None)
        patreon_panel = getattr(self, "patreon_panel", None)
        if settings_panel is None or actions_group is None or patreon_panel is None:
            return
        bottom = actions_group.mapTo(settings_panel, actions_group.rect().bottomLeft()).y() + 1
        top = settings_panel.layout().contentsMargins().top() if settings_panel.layout() else 0
        target_height = max(0, bottom + top)
        if target_height > 0 and patreon_panel.height() != target_height:
            patreon_panel.setFixedHeight(target_height)

    def prepare_mc_updater_button(self, button: QPushButton, minimum_width: int):
        button.setMinimumWidth(minimum_width)
        button.setMinimumHeight(max(34, button.fontMetrics().height() + 16))

    def load_values(self):
        self.config_data = self.main_window.config_data
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
        self.show_support_message_check.setChecked(
            bool(self.config_data.get("show_support_message", True))
        )

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

    def save_settings(self):
        self.save_current_values()
        connection_tab = getattr(self.main_window, "connection_tab", None)
        if connection_tab is not None and hasattr(connection_tab, "apply_support_message_preference"):
            connection_tab.apply_support_message_preference()

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
        self.config_data["show_support_message"] = self.show_support_message_check.isChecked()
        save_config(self.config_data)
        self.main_window.config_data = self.config_data

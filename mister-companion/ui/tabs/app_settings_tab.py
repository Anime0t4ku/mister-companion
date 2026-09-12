import time
from PyQt6.QtCore import QEvent, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core import mc_updater
from core.cloud_account import (
    CLOUD_DASHBOARD_URL,
    CloudAccountClient,
    CloudApiError,
    current_platform,
    platform_display_name,
)
from core.config import save_config
from core.open_helpers import open_uri
from ui.tab_header import create_tab_header
from ui.dialogs.mc_updater_progress_dialog import MCUpdaterProgressDialog
from ui.dialogs.profile_sync_conflicts_dialog import ProfileSyncConflictsDialog
from ui.dialogs.update_all_source_sync_conflicts_dialog import UpdateAllSourceSyncConflictsDialog
from ui.dialogs.theme_sync_conflicts_dialog import ThemeSyncConflictsDialog

PATREON_URL = "https://www.patreon.com/Anime0t4ku"


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


class CloudAccountWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(object)

    def __init__(self, operation):
        super().__init__()
        self.operation = operation

    def run(self):
        try:
            self.result.emit(self.operation())
        except Exception as e:
            self.error.emit(e)


class AppSettingsTab(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)

        self.main_window = main_window
        self.config_data = main_window.config_data
        self.mc_updater_check_worker = None
        self.mc_updater_latest_version = ""
        self.mc_updater_update_available = False
        self.show_mc_updater_settings = mc_updater.updater_supported()
        self.cloud_client = CloudAccountClient(self.config_data)
        self.cloud_worker = None
        self.cloud_pairing = None
        self.cloud_poll_timer = QTimer(self)
        self.cloud_poll_timer.setInterval(2500)
        self.cloud_poll_timer.timeout.connect(self.poll_cloud_link)
        self.cloud_link_countdown_timer = QTimer(self)
        self.cloud_link_countdown_timer.setInterval(1000)
        self.cloud_link_countdown_timer.timeout.connect(self.update_cloud_link_countdown)
        self.cloud_revision_timer = QTimer(self)
        self.cloud_revision_timer.setInterval(15000)
        self.cloud_revision_timer.timeout.connect(self.check_cloud_revisions)
        self.cloud_link_deadline = 0.0

        self.build_ui()
        self.load_values()
        if self.show_mc_updater_settings:
            self.refresh_mc_updater_state()
        QTimer.singleShot(0, self.refresh_cloud_account)

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
        # Keep one consistent gap between cards and send all surplus viewport
        # height to a stretch below the final card. Without the trailing stretch,
        # Qt can distribute extra vertical space between Maximum-height group boxes,
        # which makes the visual gaps differ even when layout spacing is identical.
        settings_layout.setSpacing(14)
        settings_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        updates_group = QGroupBox("Updates")
        updates_group.setObjectName("AppSettingsCard")
        updates_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.updates_group = updates_group
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
        settings_layout.addStretch(1)

        settings_scroll.setWidget(settings_panel)
        settings_scroll.setAlignment(Qt.AlignmentFlag.AlignTop)
        body_layout.addWidget(settings_scroll, 3)

        patreon_panel = QGroupBox("Companion Cloud (Patreon Supporters)")
        patreon_panel.setObjectName("AppSettingsCard")
        self.patreon_panel = patreon_panel
        patreon_layout = QVBoxLayout(patreon_panel)
        patreon_layout.setContentsMargins(18, 22, 18, 18)
        patreon_layout.setSpacing(10)

        self.cloud_status_label = QLabel("Checking cloud status...")
        self.cloud_status_label.setWordWrap(True)
        self.cloud_status_label.setObjectName("AppSettingsSectionTitle")
        patreon_layout.addWidget(self.cloud_status_label)

        self.cloud_sync_status_label = QLabel("")
        self.cloud_sync_status_label.setWordWrap(True)
        self.cloud_sync_status_label.setStyleSheet("font-weight: 600;")
        self.cloud_sync_status_label.hide()
        patreon_layout.addWidget(self.cloud_sync_status_label)

        self.cloud_detail_label = QLabel()
        self.cloud_detail_label.setWordWrap(True)
        patreon_layout.addWidget(self.cloud_detail_label)

        self.cloud_name_label = QLabel("Installation name")
        patreon_layout.addWidget(self.cloud_name_label)

        self.cloud_name_edit = QLineEdit()
        self.cloud_name_edit.setPlaceholderText("e.g. Gaming PC")
        self.cloud_name_edit.setMaxLength(100)
        patreon_layout.addWidget(self.cloud_name_edit)

        self.cloud_code_label = QLabel()
        self.cloud_code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cloud_code_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.cloud_code_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.cloud_code_label.hide()
        patreon_layout.addWidget(self.cloud_code_label)

        self.cloud_hint_label = QLabel()
        self.cloud_hint_label.setWordWrap(True)
        self.cloud_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cloud_hint_label.hide()
        patreon_layout.addWidget(self.cloud_hint_label)

        self.cloud_countdown_label = QLabel()
        self.cloud_countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cloud_countdown_label.setStyleSheet("font-weight: 700; color: #3498db;")
        self.cloud_countdown_label.hide()
        patreon_layout.addWidget(self.cloud_countdown_label)

        cloud_button_row = QHBoxLayout()
        cloud_button_row.setSpacing(8)

        self.cloud_link_button = QPushButton("Link this Installation")
        self.cloud_link_button.clicked.connect(self.start_cloud_link)
        cloud_button_row.addWidget(self.cloud_link_button)

        self.cloud_dashboard_button = QPushButton("Open Dashboard")
        self.cloud_dashboard_button.clicked.connect(lambda: open_uri(CLOUD_DASHBOARD_URL))
        cloud_button_row.addWidget(self.cloud_dashboard_button)

        self.cloud_patreon_button = QPushButton("Become a Patreon Member")
        self.cloud_patreon_button.clicked.connect(lambda: open_uri(PATREON_URL))
        cloud_button_row.addWidget(self.cloud_patreon_button)
        patreon_layout.addLayout(cloud_button_row)

        self.cloud_unlink_button = QPushButton("Unlink this Installation")
        self.cloud_unlink_button.clicked.connect(self.unlink_cloud_device)
        self.cloud_unlink_button.hide()
        patreon_layout.addWidget(self.cloud_unlink_button)

        patreon_layout.addStretch(1)
        body_layout.addWidget(patreon_panel, 2, Qt.AlignmentFlag.AlignTop)

        self.settings_panel.installEventFilter(self)
        QTimer.singleShot(0, self.ensure_updates_height)
        QTimer.singleShot(0, self.sync_patreon_height)


    def eventFilter(self, obj, event):
        if obj is getattr(self, "settings_panel", None) and event.type() in (
            QEvent.Type.LayoutRequest,
            QEvent.Type.Resize,
        ):
            QTimer.singleShot(0, self.ensure_updates_height)
            QTimer.singleShot(0, self.sync_patreon_height)
        return super().eventFilter(obj, event)

    def ensure_updates_height(self):
        updates_group = getattr(self, "updates_group", None)
        if updates_group is None:
            return
        hint = updates_group.sizeHint().height()
        if hint > 0 and updates_group.minimumHeight() < hint + 6:
            updates_group.setMinimumHeight(hint + 6)
            updates_group.updateGeometry()
            panel_layout = getattr(self, "settings_panel", None)
            if panel_layout is not None and panel_layout.layout() is not None:
                panel_layout.layout().activate()

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


    def set_cloud_syncing(self, syncing: bool):
        self.main_window.cloud_sync_in_progress = bool(syncing)
        self.refresh_cloud_status_indicators()

    def refresh_cloud_status_indicators(self):
        connection_tab = getattr(self.main_window, "connection_tab", None)
        if connection_tab is not None and hasattr(connection_tab, "update_cloud_status"):
            connection_tab.update_cloud_status()

        device_tab = getattr(connection_tab, "device_dashboard", None) if connection_tab is not None else None
        if device_tab is not None and hasattr(device_tab, "update_cloud_status"):
            device_tab.update_cloud_status()

    def refresh_cloud_account(self):
        self.cloud_client = CloudAccountClient(self.config_data)
        if not self.cloud_client.has_session():
            self.show_cloud_unlinked()
            return

        self.cloud_status_label.setText("Companion Cloud: Connecting...")
        self.cloud_link_button.setEnabled(False)
        self.run_cloud_task(
            self.cloud_client.connect_and_sync_profiles,
            self.on_cloud_connect_result,
            self.on_cloud_connect_error,
            sync_activity=True,
        )

    def show_cloud_unlinked(self):
        self.cloud_poll_timer.stop()
        self.cloud_link_countdown_timer.stop()
        self.cloud_revision_timer.stop()
        self.cloud_link_deadline = 0.0
        self.cloud_pairing = None
        self.set_cloud_syncing(False)
        system, architecture = current_platform()
        self.cloud_status_label.setText("Companion Cloud: Not linked")
        self.cloud_sync_status_label.hide()
        self.cloud_detail_label.setText(
            f"Link this {platform_display_name(system, architecture)} installation to your RetroAccount "
            "to use Companion Cloud features for Patreon supporters."
        )
        self.cloud_name_label.show()
        self.cloud_name_edit.show()
        self.cloud_code_label.hide()
        self.cloud_hint_label.hide()
        self.cloud_countdown_label.hide()
        self.cloud_link_button.setText("Link this Installation")
        self.cloud_link_button.setEnabled(True)
        self.cloud_link_button.show()
        self.cloud_patreon_button.show()
        self.cloud_unlink_button.hide()
        self.refresh_cloud_status_indicators()

    def show_cloud_linked(self, result: dict):
        device = result.get("device") if isinstance(result, dict) else None
        entitlement = result.get("entitlement") if isinstance(result, dict) else None
        if not isinstance(device, dict):
            device = self.cloud_client.linked_device()
        if not isinstance(entitlement, dict):
            entitlement = self.cloud_client.entitlement()

        name = str(device.get("friendly_name") or "This installation")
        tier = str(entitlement.get("tier") or "No eligible tier")
        system = str(device.get("platform") or "")
        architecture = str(device.get("architecture") or "")
        platform_text = platform_display_name(system, architecture) if system else "MiSTer Companion Desktop"

        self.cloud_status_label.setText("Companion Cloud: Linked")
        active, reason = self.cloud_client.cloud_sync_status()
        self.cloud_sync_status_label.setText("Sync Status: Active" if active else "Sync Status: Inactive")
        self.cloud_sync_status_label.setStyleSheet(
            "font-weight: 600; color: #00aa00;" if active else "font-weight: 600; color: #f39c12;"
        )
        self.cloud_sync_status_label.show()
        detail = f"{name}\n{platform_text}\nTier: {tier}"
        if not active and reason:
            detail += f"\nReason: {reason}"
        self.cloud_detail_label.setText(detail)
        self.cloud_name_label.hide()
        self.cloud_name_edit.hide()
        self.cloud_code_label.hide()
        self.cloud_hint_label.hide()
        self.cloud_countdown_label.hide()
        self.cloud_link_button.hide()
        self.cloud_patreon_button.hide()
        self.cloud_unlink_button.show()
        if not self.cloud_revision_timer.isActive():
            self.cloud_revision_timer.start()
        self.refresh_cloud_status_indicators()

    def check_cloud_revisions(self):
        if not self.cloud_client.has_session():
            self.cloud_revision_timer.stop()
            return
        if self.cloud_worker is not None and self.cloud_worker.isRunning():
            return
        self.run_cloud_task(
            self.cloud_client.sync_revisions,
            self.on_cloud_revision_result,
            self.on_cloud_revision_error,
        )

    def on_cloud_revision_result(self, result):
        if not self.cloud_client.remote_sync_available(result):
            return
        self.cloud_status_label.setText("Companion Cloud: Syncing...")
        QTimer.singleShot(0, lambda: self.run_cloud_task(
            self.cloud_client.connect_and_sync_profiles,
            self.on_cloud_connect_result,
            self.on_cloud_connect_error,
            sync_activity=True,
        ))

    def on_cloud_revision_error(self, _error):
        # Revision watching is a convenience mechanism. Normal connect/sync
        # handling remains authoritative and will retry on the next interval.
        pass

    def start_cloud_link(self):
        friendly_name = self.cloud_name_edit.text().strip()
        if not friendly_name:
            QMessageBox.information(self, "Link Installation", "Enter a name for this installation first.")
            self.cloud_name_edit.setFocus()
            return

        self.cloud_link_button.setEnabled(False)
        self.cloud_status_label.setText("Companion Cloud: Creating link code...")
        self.run_cloud_task(
            lambda: self.cloud_client.start_link(friendly_name),
            self.on_cloud_link_started,
            self.on_cloud_link_error,
        )

    def on_cloud_link_started(self, result):
        pairing_id = str(result.get("pairing_id") or "")
        device_secret = str(result.get("device_secret") or "")
        user_code = str(result.get("user_code") or "")
        expires_in = max(1, min(180, int(result.get("expires_in") or 180)))
        if not pairing_id or not device_secret or not user_code:
            self.on_cloud_link_error(RuntimeError("The server did not return a complete linking code."))
            return

        self.cloud_pairing = {
            "pairing_id": pairing_id,
            "device_secret": device_secret,
        }
        self.cloud_link_deadline = time.monotonic() + expires_in
        self.cloud_status_label.setText("Companion Cloud: Waiting for approval")
        self.cloud_detail_label.setText("Sign in with RetroAccount on the dashboard and approve this installation.")
        self.cloud_name_label.hide()
        self.cloud_name_edit.hide()
        self.cloud_code_label.setText(user_code)
        self.cloud_code_label.show()
        self.cloud_hint_label.setText("Enter this one-time code in the MiSTer Companion Cloud dashboard.")
        self.cloud_hint_label.show()
        self.cloud_countdown_label.setStyleSheet("font-weight: 700; color: #3498db;")
        self.update_cloud_link_countdown()
        self.cloud_countdown_label.show()
        self.cloud_link_button.setText("Waiting for Approval...")
        self.cloud_link_button.setEnabled(False)
        open_uri(f"{CLOUD_DASHBOARD_URL}?device_code={user_code}")
        self.cloud_poll_timer.start()
        self.cloud_link_countdown_timer.start()

    def update_cloud_link_countdown(self):
        if not self.cloud_pairing or self.cloud_link_deadline <= 0:
            self.cloud_link_countdown_timer.stop()
            self.cloud_countdown_label.hide()
            return
        remaining = max(0, int(self.cloud_link_deadline - time.monotonic() + 0.999))
        minutes, seconds = divmod(remaining, 60)
        self.cloud_countdown_label.setText(f"Code expires in {minutes:02d}:{seconds:02d}")
        if remaining <= 0:
            self.cloud_poll_timer.stop()
            self.cloud_link_countdown_timer.stop()
            self.cloud_pairing = None
            self.cloud_link_deadline = 0.0
            self.cloud_code_label.setText("Code expired")
            self.cloud_hint_label.setText("This link code is no longer valid. Generate a new code to continue.")
            self.cloud_countdown_label.setText("Code expired")
            self.cloud_countdown_label.setStyleSheet("font-weight: 700; color: #e74c3c;")
            self.cloud_link_button.setText("Generate New Code")
            self.cloud_link_button.setEnabled(True)
            self.cloud_link_button.show()

    def poll_cloud_link(self):
        if self.cloud_worker is not None and self.cloud_worker.isRunning():
            return
        if not self.cloud_pairing:
            self.cloud_poll_timer.stop()
            return

        pairing_id = self.cloud_pairing["pairing_id"]
        device_secret = self.cloud_pairing["device_secret"]
        self.run_cloud_task(
            lambda: self.cloud_client.poll_link(pairing_id, device_secret),
            self.on_cloud_link_poll_result,
            self.on_cloud_link_poll_error,
        )

    def on_cloud_link_poll_result(self, result):
        status = str(result.get("status") or "")
        if status == "pending":
            return
        if status == "linked":
            self.cloud_poll_timer.stop()
            self.cloud_link_countdown_timer.stop()
            self.cloud_link_deadline = 0.0
            self.cloud_pairing = None
            save_config(self.config_data)
            self.main_window.config_data = self.config_data
            self.refresh_cloud_account()
            return
        if status in {"expired", "denied", "revoked", "already_claimed"}:
            self.cloud_poll_timer.stop()
            self.cloud_link_countdown_timer.stop()
            self.cloud_link_deadline = 0.0
            self.cloud_pairing = None
            QMessageBox.warning(self, "Link Installation", f"Device linking {status.replace('_', ' ')}.")
            self.show_cloud_unlinked()

    def on_cloud_link_poll_error(self, error):
        if isinstance(error, CloudApiError) and error.status_code in {403, 409, 410}:
            payload = error.payload if isinstance(error.payload, dict) else {}
            status = str(payload.get("status") or payload.get("error") or "").strip()
            if status in {"expired", "denied", "revoked", "already_claimed"}:
                self.cloud_poll_timer.stop()
                self.cloud_link_countdown_timer.stop()
                self.cloud_link_deadline = 0.0
                self.cloud_pairing = None
                QMessageBox.warning(self, "Link Installation", str(error))
                self.show_cloud_unlinked()
                return
        self.on_cloud_link_error(error)

    def on_cloud_link_error(self, error):
        self.cloud_poll_timer.stop()
        self.cloud_link_countdown_timer.stop()
        self.cloud_link_deadline = 0.0
        self.cloud_pairing = None
        self.cloud_link_button.setEnabled(True)
        QMessageBox.warning(self, "MiSTer Companion Cloud", f"Could not link this installation.\n\n{error}")
        self.show_cloud_unlinked()

    def on_cloud_connect_result(self, result):
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        self.show_cloud_linked(result)

        profile_sync = result.get("profile_sync") if isinstance(result, dict) else None
        if isinstance(profile_sync, dict) and profile_sync.get("status") == "paused":
            reason = "Profile sync is paused after cloud-data deletion. Resume it from the Companion Cloud dashboard."
            self.cloud_client.set_cloud_sync_status(False, reason)
            save_config(self.config_data)
            self.show_cloud_linked(result)
            return
        if isinstance(profile_sync, dict) and profile_sync.get("status") == "resolution_required":
            plan = profile_sync.get("initial_plan") if isinstance(profile_sync.get("initial_plan"), dict) else {}
            conflicts = profile_sync.get("conflicts") if isinstance(profile_sync.get("conflicts"), list) else []
            dialog = ProfileSyncConflictsDialog(
                conflicts,
                reserved_names=plan.get("reserved_names") if isinstance(plan.get("reserved_names"), list) else [],
                parent=self,
            )
            if dialog.exec() != dialog.DialogCode.Accepted:
                reason = "Profile sync needs attention before it can continue."
                self.cloud_client.set_cloud_sync_status(False, reason)
                save_config(self.config_data)
                self.show_cloud_linked(result)
                return

            resolutions = dialog.resolutions()
            self.cloud_status_label.setText("Companion Cloud: Resolving profile sync...")
            self.run_cloud_task(
                lambda: self.cloud_client.resolve_initial_profile_sync(plan, resolutions),
                self.on_initial_profile_sync_resolved,
                self.on_initial_profile_sync_error,
                sync_activity=True,
            )
            return

        self.refresh_profile_selector_after_sync()
        update_all_source_sync = result.get("update_all_source_sync") if isinstance(result, dict) else None
        if isinstance(update_all_source_sync, dict):
            self.on_cloud_update_all_source_sync_result(update_all_source_sync)
            if update_all_source_sync.get("status") in {"paused", "resolution_required"}:
                return

        theme_sync = result.get("custom_theme_sync") if isinstance(result, dict) else None
        if isinstance(theme_sync, dict):
            self.on_cloud_theme_sync_result(theme_sync, activate_on_success=True)

    def on_initial_profile_sync_resolved(self, _result):
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        self.refresh_profile_selector_after_sync()
        self.show_cloud_linked({
            "device": self.cloud_client.linked_device(),
            "entitlement": self.cloud_client.entitlement(),
        })
        self.run_cloud_task(
            self.cloud_client.sync_update_all_custom_sources,
            lambda result: self.on_cloud_update_all_source_sync_result(result, activate_on_success=True),
            self.on_cloud_update_all_source_sync_error,
            sync_activity=True,
        )

    def on_initial_profile_sync_error(self, error):
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        QMessageBox.warning(
            self,
            "Resolve Profile Sync",
            f"Could not apply the profile sync resolution.\n\n{error}",
        )
        reason = "Profile sync needs attention. Restart Companion to retry conflict resolution."
        self.cloud_client.set_cloud_sync_status(False, reason)
        save_config(self.config_data)
        self.show_cloud_linked({"device": self.cloud_client.linked_device(), "entitlement": self.cloud_client.entitlement()})

    def sync_cloud_profiles_silently(self):
        if not self.cloud_client.has_session():
            return
        if self.cloud_worker is not None and self.cloud_worker.isRunning():
            return
        self.run_cloud_task(
            self.cloud_client.sync_profiles,
            self.on_cloud_profile_sync_result,
            self.on_cloud_profile_sync_error,
            sync_activity=True,
        )

    def sync_cloud_update_all_sources_silently(self):
        if not self.cloud_client.has_session():
            return
        if self.cloud_worker is not None and self.cloud_worker.isRunning():
            return
        self.run_cloud_task(
            self.cloud_client.sync_update_all_custom_sources,
            self.on_cloud_update_all_source_sync_result,
            self.on_cloud_update_all_source_sync_error,
            sync_activity=True,
        )

    def on_cloud_update_all_source_sync_result(self, result, activate_on_success: bool = False):
        if isinstance(result, dict) and result.get("status") == "paused":
            reason = "Update_All custom source sync is paused after cloud-data deletion. Resume it from the Companion Cloud dashboard."
            self.cloud_client.set_cloud_sync_status(False, reason)
            save_config(self.config_data)
            self.show_cloud_linked({"device": self.cloud_client.linked_device(), "entitlement": self.cloud_client.entitlement()})
            return
        save_config(self.config_data)
        self.main_window.config_data = self.config_data

        if isinstance(result, dict) and result.get("status") == "resolution_required":
            plan = result.get("initial_plan") if isinstance(result.get("initial_plan"), dict) else {}
            conflicts = result.get("conflicts") if isinstance(result.get("conflicts"), list) else []
            dialog = UpdateAllSourceSyncConflictsDialog(conflicts, parent=self)
            if dialog.exec() != dialog.DialogCode.Accepted:
                reason = "Update_All custom source sync needs attention before it can continue."
                self.cloud_client.set_cloud_sync_status(False, reason)
                save_config(self.config_data)
                self.show_cloud_linked({"device": self.cloud_client.linked_device(), "entitlement": self.cloud_client.entitlement()})
                return

            resolutions = dialog.resolutions()
            self.cloud_status_label.setText("Companion Cloud: Resolving custom source sync...")
            self.run_cloud_task(
                lambda: self.cloud_client.resolve_initial_update_all_source_sync(plan, resolutions),
                self.on_initial_update_all_source_sync_resolved,
                self.on_initial_update_all_source_sync_error,
                sync_activity=True,
            )
            return

        active, inactive_reason = self.cloud_client.cloud_sync_status()
        recovered_from_this_sync = (not active and inactive_reason.startswith("Update_All custom source sync failed."))
        if activate_on_success or recovered_from_this_sync:
            self.cloud_client.set_cloud_sync_status(True)
            save_config(self.config_data)
            self.show_cloud_linked({
                "device": self.cloud_client.linked_device(),
                "entitlement": self.cloud_client.entitlement(),
            })

    def on_initial_update_all_source_sync_resolved(self, _result):
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        self.run_cloud_task(
            self.cloud_client.sync_custom_themes,
            lambda result: self.on_cloud_theme_sync_result(result, activate_on_success=True),
            self.on_cloud_theme_sync_error,
            sync_activity=True,
        )

    def on_initial_update_all_source_sync_error(self, error):
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        QMessageBox.warning(
            self,
            "Resolve Custom Source Sync",
            f"Could not apply the custom source sync resolution.\n\n{error}",
        )
        reason = "Update_All custom source sync needs attention. Restart Companion to retry conflict resolution."
        self.cloud_client.set_cloud_sync_status(False, reason)
        save_config(self.config_data)
        self.show_cloud_linked({"device": self.cloud_client.linked_device(), "entitlement": self.cloud_client.entitlement()})

    def on_cloud_update_all_source_sync_error(self, error):
        if isinstance(error, CloudApiError) and error.status_code == 401:
            self.cloud_client.clear_session()
            save_config(self.config_data)
            self.main_window.config_data = self.config_data
            self.show_cloud_unlinked()
            return

        reason = "Update_All custom source sync failed. Companion Cloud will retry later."
        self.cloud_client.set_cloud_sync_status(False, reason)
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        self.show_cloud_linked({
            "device": self.cloud_client.linked_device(),
            "entitlement": self.cloud_client.entitlement(),
        })

    def on_cloud_theme_sync_result(self, result, activate_on_success: bool = False):
        if isinstance(result, dict) and result.get("status") == "paused":
            reason = "Custom theme sync is paused after cloud-data deletion. Resume it from the Companion Cloud dashboard."
            self.cloud_client.set_cloud_sync_status(False, reason)
            save_config(self.config_data)
            self.show_cloud_linked({"device": self.cloud_client.linked_device(), "entitlement": self.cloud_client.entitlement()})
            return

        if isinstance(result, dict) and result.get("status") == "resolution_required":
            plan = result.get("initial_plan") if isinstance(result.get("initial_plan"), dict) else {}
            conflicts = result.get("conflicts") if isinstance(result.get("conflicts"), list) else []
            dialog = ThemeSyncConflictsDialog(
                conflicts,
                reserved_theme_ids=plan.get("reserved_theme_ids") if isinstance(plan.get("reserved_theme_ids"), list) else [],
                parent=self,
            )
            if dialog.exec() != dialog.DialogCode.Accepted:
                self.cloud_client.set_cloud_sync_status(False, "Custom theme sync needs attention before it can continue.")
                save_config(self.config_data)
                self.show_cloud_linked({"device": self.cloud_client.linked_device(), "entitlement": self.cloud_client.entitlement()})
                return
            resolutions = dialog.resolutions()
            self.run_cloud_task(
                lambda: self.cloud_client.resolve_custom_theme_sync(plan, resolutions),
                self.on_cloud_theme_sync_resolved,
                self.on_cloud_theme_sync_error,
                sync_activity=True,
            )
            return

        active, inactive_reason = self.cloud_client.cloud_sync_status()
        if activate_on_success or (not active and inactive_reason.startswith("Custom theme sync failed.")):
            self.cloud_client.set_cloud_sync_status(True)
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        self.show_cloud_linked({
            "device": self.cloud_client.linked_device(),
            "entitlement": self.cloud_client.entitlement(),
        })

    def on_cloud_theme_sync_resolved(self, _result):
        self.cloud_client.set_cloud_sync_status(True)
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        self.show_cloud_linked({
            "device": self.cloud_client.linked_device(),
            "entitlement": self.cloud_client.entitlement(),
        })

    def on_cloud_theme_sync_error(self, error):
        if isinstance(error, CloudApiError) and error.status_code == 401:
            self.cloud_client.clear_session()
            save_config(self.config_data)
            self.main_window.config_data = self.config_data
            self.show_cloud_unlinked()
            return

        self.cloud_client.set_cloud_sync_status(False, "Custom theme sync failed. Companion Cloud will retry later.")
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        self.show_cloud_linked({
            "device": self.cloud_client.linked_device(),
            "entitlement": self.cloud_client.entitlement(),
        })

    def on_cloud_profile_sync_result(self, result):
        if isinstance(result, dict) and result.get("status") == "paused":
            reason = "Profile sync is paused after cloud-data deletion. Resume it from the Companion Cloud dashboard."
            self.cloud_client.set_cloud_sync_status(False, reason)
        elif isinstance(result, dict) and result.get("status") == "resolution_required":
            plan = result.get("initial_plan") if isinstance(result.get("initial_plan"), dict) else {}
            conflicts = result.get("conflicts") if isinstance(result.get("conflicts"), list) else []
            dialog = ProfileSyncConflictsDialog(
                conflicts,
                reserved_names=plan.get("reserved_names") if isinstance(plan.get("reserved_names"), list) else [],
                parent=self,
            )
            if dialog.exec() != dialog.DialogCode.Accepted:
                self.cloud_client.set_cloud_sync_status(False, "Profile sync needs attention before it can continue.")
            else:
                resolutions = dialog.resolutions()
                self.run_cloud_task(
                    lambda: self.cloud_client.resolve_initial_profile_sync(plan, resolutions),
                    self.on_cloud_profile_sync_resolved_later,
                    self.on_initial_profile_sync_error,
                    sync_activity=True,
                )
                return
        else:
            active, inactive_reason = self.cloud_client.cloud_sync_status()
            if not active and inactive_reason.startswith("Profile sync failed."):
                self.cloud_client.set_cloud_sync_status(True)
                self.show_cloud_linked({
                    "device": self.cloud_client.linked_device(),
                    "entitlement": self.cloud_client.entitlement(),
                })
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        self.refresh_profile_selector_after_sync()

    def on_cloud_profile_sync_resolved_later(self, _result):
        self.cloud_client.set_cloud_sync_status(True)
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        self.refresh_profile_selector_after_sync()
        self.show_cloud_linked({
            "device": self.cloud_client.linked_device(),
            "entitlement": self.cloud_client.entitlement(),
        })

    def on_cloud_profile_sync_error(self, error):
        if isinstance(error, CloudApiError) and error.status_code == 401:
            self.cloud_client.clear_session()
            save_config(self.config_data)
            self.main_window.config_data = self.config_data
            self.show_cloud_unlinked()
            return

        reason = "Profile sync failed. Companion Cloud will retry later."
        self.cloud_client.set_cloud_sync_status(False, reason)
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        self.show_cloud_linked({
            "device": self.cloud_client.linked_device(),
            "entitlement": self.cloud_client.entitlement(),
        })

    def refresh_profile_selector_after_sync(self):
        connection_tab = getattr(self.main_window, "connection_tab", None)
        if connection_tab is None:
            return
        selected = connection_tab.get_selected_profile_name()
        devices = self.config_data.get("devices", [])
        connection_tab.set_profiles(devices, selected_name=selected or None)

    def on_cloud_connect_error(self, error):
        save_config(self.config_data)
        self.main_window.config_data = self.config_data

        if isinstance(error, CloudApiError):
            payload = error.payload if isinstance(error.payload, dict) else {}
            code = str(payload.get("error") or "")
            if error.status_code == 409 and code == "device_inactive_over_limit":
                reason = "This installation was deactivated or is over the active-device limit for your current Patreon tier."
                self.cloud_client.set_cloud_sync_status(False, reason)
                save_config(self.config_data)
                self.cloud_status_label.setText("Companion Cloud: Linked")
                self.cloud_sync_status_label.setText("Sync Status: Inactive")
                self.cloud_sync_status_label.setStyleSheet("font-weight: 600; color: #f39c12;")
                self.cloud_sync_status_label.show()
                self.cloud_detail_label.setText(reason + " Please use the dashboard to manage your linked devices.")
                self.refresh_cloud_status_indicators()
                self.cloud_name_label.hide()
                self.cloud_name_edit.hide()
                self.cloud_code_label.hide()
                self.cloud_hint_label.hide()
                self.cloud_countdown_label.hide()
                self.cloud_link_button.hide()
                self.cloud_patreon_button.hide()
                self.cloud_unlink_button.show()
                return
            if error.status_code == 403 and code == "supporter_entitlement_required":
                reason = "No eligible Patreon membership is currently active for Companion Cloud."
                self.cloud_client.set_cloud_sync_status(False, reason)
                save_config(self.config_data)
                self.cloud_status_label.setText("Companion Cloud: Linked")
                self.cloud_sync_status_label.setText("Sync Status: Inactive")
                self.cloud_sync_status_label.setStyleSheet("font-weight: 600; color: #f39c12;")
                self.cloud_sync_status_label.show()
                self.cloud_detail_label.setText(reason)
                self.refresh_cloud_status_indicators()
                self.cloud_name_label.hide()
                self.cloud_name_edit.hide()
                self.cloud_code_label.hide()
                self.cloud_hint_label.hide()
                self.cloud_countdown_label.hide()
                self.cloud_link_button.hide()
                self.cloud_patreon_button.hide()
                self.cloud_unlink_button.show()
                return
            if error.status_code == 401:
                self.cloud_client.clear_session()
                save_config(self.config_data)
                self.main_window.config_data = self.config_data
                self.show_cloud_unlinked()
                return

        reason = "Companion Cloud is temporarily unavailable."
        self.cloud_client.set_cloud_sync_status(False, reason)
        save_config(self.config_data)
        self.cloud_status_label.setText("Companion Cloud: Linked")
        self.cloud_sync_status_label.setText("Sync Status: Inactive")
        self.cloud_sync_status_label.setStyleSheet("font-weight: 600; color: #f39c12;")
        self.cloud_sync_status_label.show()
        self.cloud_detail_label.setText(f"{reason}\n{error}")
        self.cloud_patreon_button.hide()
        self.refresh_cloud_status_indicators()
        self.cloud_link_button.setEnabled(True)

    def unlink_cloud_device(self):
        answer = QMessageBox.question(
            self,
            "Unlink Installation",
            "Unlink this MiSTer Companion installation?\n\nYour cloud data will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.cloud_unlink_button.setEnabled(False)
        self.run_cloud_task(self.cloud_client.unlink, self.on_cloud_unlink_result, self.on_cloud_unlink_error)

    def on_cloud_unlink_result(self, _result):
        save_config(self.config_data)
        self.main_window.config_data = self.config_data
        self.cloud_unlink_button.setEnabled(True)
        self.show_cloud_unlinked()

    def on_cloud_unlink_error(self, error):
        self.cloud_unlink_button.setEnabled(True)
        QMessageBox.warning(self, "Unlink Installation", f"Could not unlink this installation.\n\n{error}")

    def run_cloud_task(self, operation, on_result, on_error, sync_activity: bool = False):
        if self.cloud_worker is not None and self.cloud_worker.isRunning():
            return
        if sync_activity:
            self.set_cloud_syncing(True)

        def handle_result(result):
            if sync_activity:
                self.set_cloud_syncing(False)
            on_result(result)

        def handle_error(error):
            if sync_activity:
                self.set_cloud_syncing(False)
            on_error(error)

        self.cloud_worker = CloudAccountWorker(operation)
        self.cloud_worker.result.connect(handle_result)
        self.cloud_worker.error.connect(handle_error)
        self.cloud_worker.start()

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

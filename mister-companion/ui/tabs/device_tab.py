import sys

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QByteArray, QSize
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QPushButton, QMessageBox, QProgressBar, QSizePolicy, QSlider, QToolButton
)
from PyQt6.QtGui import QPixmap

from ui.scaling import set_text_button_min_width
from core.device_actions import (
    disable_smb_offline,
    disable_smb_remote,
    enable_smb_offline,
    enable_smb_remote,
    get_sd_storage_info,
    get_sd_storage_info_offline,
    get_usb_storage_info,
    is_smb_enabled,
    is_smb_enabled_offline,
    return_to_menu_remote,
)
from core.share_opener import open_local_folder, open_mister_share
from core.scripts_actions import get_scripts_status, get_scripts_status_local, remove_static_wallpaper
from core.scripts_static_wallpaper import get_static_wallpaper_state_local, remove_static_wallpaper_local
from ui.dialogs.static_wallpaper_dialog import StaticWallpaperDialog
from ui.update_all_runner import UpdateAllOutputDialog, prepare_update_all_task
from core.zaparoo_crypto import clear_pairing_credentials, has_pairing_credentials
from core.zapscripts import get_active_media
from ui.zaparoo_pairing import prompt_for_zaparoo_pairing
from ui.dialogs.mister_hifi_browser_dialog import MiSTerHiFiBrowserDialog
from core.mister_hifi_remote import HiFiWebSocketListener, artwork as hifi_artwork, control as hifi_control, seek as hifi_seek
from core.theme import theme_text_color


def resolve_now_playing(connection, timeout=3):
    """Return Zaparoo Core's authoritative primary active-media state only."""
    try:
        active = get_active_media(connection, timeout=timeout)
        return active if isinstance(active, dict) else {}
    except Exception:
        return {}


class ClickSeekSlider(QSlider):
    """Horizontal slider that jumps to the clicked position before dragging."""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.orientation() == Qt.Orientation.Horizontal:
            span = max(1, self.width())
            ratio = max(0.0, min(1.0, event.position().x() / span))
            value = self.minimum() + round((self.maximum() - self.minimum()) * ratio)
            self.setValue(value)
            self.sliderMoved.emit(value)
        super().mousePressEvent(event)


class DeviceStatusWorker(QThread):
    result = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, connection, offline_mode=False, sd_root="", parent=None):
        super().__init__(parent)
        self.connection = connection
        self.offline_mode = offline_mode
        self.sd_root = sd_root

    def run(self):
        try:
            if self.offline_mode:
                sd_info = None
                smb_enabled = None
                smb_error = ""

                if self.sd_root:
                    sd_info = get_sd_storage_info_offline(self.sd_root)

                    try:
                        smb_enabled = is_smb_enabled_offline(self.sd_root)
                    except Exception as e:
                        smb_error = str(e)

                update_all_installed = False
                static_wallpaper_active = False
                if self.sd_root:
                    try:
                        update_all_installed = bool(get_scripts_status_local(self.sd_root).update_all_installed)
                    except Exception:
                        update_all_installed = False
                    try:
                        static_wallpaper_active = bool(get_static_wallpaper_state_local(self.sd_root).get("active"))
                    except Exception:
                        static_wallpaper_active = False

                self.result.emit(
                    {
                        "offline": True,
                        "sd_info": sd_info,
                        "smb_enabled": smb_enabled,
                        "smb_error": smb_error,
                        "update_all_installed": update_all_installed,
                        "static_wallpaper_active": static_wallpaper_active,
                    }
                )
                return

            sd_info = get_sd_storage_info(self.connection)
            usb_info = get_usb_storage_info(self.connection)
            smb_enabled = is_smb_enabled(self.connection)
            now_playing = resolve_now_playing(self.connection, timeout=3)
            try:
                scripts_status = get_scripts_status(self.connection)
                update_all_installed = bool(scripts_status.update_all_installed)
                static_wallpaper_active = bool(scripts_status.static_wallpaper_active)
            except Exception:
                update_all_installed = False
                static_wallpaper_active = False

            self.result.emit(
                {
                    "offline": False,
                    "sd_info": sd_info,
                    "usb_info": usb_info,
                    "smb_enabled": smb_enabled,
                    "now_playing": now_playing,
                    "update_all_installed": update_all_installed,
                    "static_wallpaper_active": static_wallpaper_active,
                }
            )

        except Exception as e:
            self.error.emit(str(e))


class NowPlayingWorker(QThread):
    result = pyqtSignal(dict)

    def __init__(self, connection, parent=None):
        super().__init__(parent)
        self.connection = connection

    def run(self):
        self.result.emit(resolve_now_playing(self.connection, timeout=2))


class HiFiRequestWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self.fn = fn
        self.args = args

    def run(self):
        try:
            self.result.emit(self.fn(*self.args))
        except Exception as exc:
            self.error.emit(str(exc))


class DeviceTab(QWidget):
    hifi_state_signal = pyqtSignal(dict)
    hifi_connected_signal = pyqtSignal()
    hifi_disconnected_signal = pyqtSignal()
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection
        self.status_worker = None
        self.now_playing_worker = None
        self.hifi_listener = None
        self.hifi_request_worker = None
        self.hifi_art_worker = None
        self.hifi_state = {}
        self.hifi_art_key = ""
        self.hifi_slider_dragging = False
        self._shutting_down = False

        self.hifi_state_signal.connect(self.apply_hifi_state)
        self.hifi_connected_signal.connect(self.on_hifi_connected)
        self.hifi_disconnected_signal.connect(self.on_hifi_disconnected)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(2000)
        self.refresh_timer.timeout.connect(self.poll_now_playing)

        self.build_ui()
        self.apply_disconnected_state()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Compact connected-device header.
        header = QGroupBox()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(10)

        self.connected_status_label = QLabel("● Connected")
        self.connected_status_label.setStyleSheet("font-weight: bold; color: #00aa00;")
        self.connected_identity_label = QLabel("")
        self.connected_identity_label.setStyleSheet("font-weight: bold;")
        self.connected_identity_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.disconnect_button = QPushButton("Disconnect")
        set_text_button_min_width(self.disconnect_button, 110)

        header_layout.addWidget(self.connected_status_label)
        header_layout.addWidget(self.connected_identity_label)
        header_layout.addStretch()
        header_layout.addWidget(self.disconnect_button)
        main_layout.addWidget(header)

        # Now Playing is intentionally conditional and consumes no space when idle.
        self.now_playing_group = QGroupBox("Now Playing")
        now_playing_layout = QHBoxLayout(self.now_playing_group)
        now_playing_layout.setContentsMargins(12, 7, 12, 7)
        self.now_playing_summary_label = QLabel("")
        self.now_playing_summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.now_playing_summary_label.setStyleSheet("font-weight: bold;")
        self.now_playing_summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        now_playing_layout.addWidget(self.now_playing_summary_label)
        self.now_playing_group.setVisible(False)
        main_layout.addWidget(self.now_playing_group)

        # MiSTer Hi-Fi mini player. Hidden unless the Hi-Fi websocket is active.
        self.hifi_group = QGroupBox("MiSTer Hi-Fi")
        hifi_layout = QHBoxLayout(self.hifi_group)
        hifi_layout.setContentsMargins(12, 8, 12, 8)
        hifi_layout.setSpacing(10)

        self.hifi_art_label = QLabel("No Art")
        self.hifi_art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hifi_art_label.setFixedSize(92, 92)
        self.hifi_art_label.setStyleSheet("border: 1px solid palette(mid); border-radius: 4px;")
        hifi_layout.addWidget(self.hifi_art_label)

        hifi_center = QVBoxLayout()
        hifi_center.setSpacing(3)
        self.hifi_title_label = QLabel("Nothing playing")
        self.hifi_title_label.setStyleSheet("font-weight: bold;")
        self.hifi_title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.hifi_artist_label = QLabel("")
        self.hifi_album_label = QLabel("")
        self.hifi_artist_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.hifi_album_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        hifi_center.addWidget(self.hifi_title_label)
        hifi_center.addWidget(self.hifi_artist_label)
        hifi_center.addWidget(self.hifi_album_label)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(6)
        self.hifi_position_label = QLabel("0:00")
        self.hifi_progress = ClickSeekSlider(Qt.Orientation.Horizontal)
        self.hifi_progress.setRange(0, 1000)
        self.hifi_progress.setValue(0)
        self.hifi_duration_label = QLabel("0:00")
        progress_row.addWidget(self.hifi_position_label)
        progress_row.addWidget(self.hifi_progress, 1)
        progress_row.addWidget(self.hifi_duration_label)
        hifi_center.addLayout(progress_row)
        hifi_layout.addLayout(hifi_center, 1)

        controls = QHBoxLayout()
        controls.setSpacing(4)
        self.hifi_previous_button = QToolButton()
        self.hifi_play_button = QToolButton()
        self.hifi_next_button = QToolButton()
        self.hifi_stop_button = QToolButton()
        for button, tip in (
            (self.hifi_previous_button, "Previous"),
            (self.hifi_play_button, "Play / Pause"),
            (self.hifi_next_button, "Next"),
            (self.hifi_stop_button, "Stop"),
        ):
            button.setToolTip(tip)
            button.setIconSize(QSize(22, 22))
            button.setFixedSize(34, 34)
            button.setAutoRaise(True)
            button.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            button.setStyleSheet(
                "QToolButton, QToolButton:hover, QToolButton:pressed, "
                "QToolButton:checked, QToolButton:disabled { "
                "background: transparent; background-color: transparent; "
                "border: 0px; padding: 0px; margin: 0px; }"
            )
            controls.addWidget(button)

        self.hifi_browse_button = QPushButton("Browse")
        self.hifi_browse_button.setToolTip("Browse MiSTer Hi-Fi")
        set_text_button_min_width(self.hifi_browse_button, 90)
        controls.addWidget(self.hifi_browse_button)
        hifi_layout.addLayout(controls)

        self.hifi_previous_button.clicked.connect(lambda: self.hifi_send_control("previous"))
        self.hifi_play_button.clicked.connect(lambda: self.hifi_send_control("playpause"))
        self.hifi_next_button.clicked.connect(lambda: self.hifi_send_control("next"))
        self.hifi_stop_button.clicked.connect(lambda: self.hifi_send_control("stop"))
        self.hifi_browse_button.clicked.connect(self.open_hifi_browser)
        self.hifi_progress.sliderPressed.connect(self.hifi_slider_pressed)
        self.hifi_progress.sliderReleased.connect(self.hifi_slider_released)
        self.hifi_progress.sliderMoved.connect(self.hifi_slider_moved)
        self.hifi_group.setVisible(False)
        main_layout.addWidget(self.hifi_group)

        cards_grid = QGridLayout()
        cards_grid.setHorizontalSpacing(10)
        cards_grid.setVerticalSpacing(10)
        cards_grid.setColumnStretch(0, 1)
        cards_grid.setColumnStretch(1, 1)

        # Storage
        storage_group = QGroupBox("Storage")
        storage_layout = QGridLayout(storage_group)
        storage_layout.setContentsMargins(12, 8, 12, 8)
        storage_layout.setHorizontalSpacing(8)
        storage_layout.setVerticalSpacing(12)

        self.sd_title_label = QLabel("SD")
        self.storage_bar = QProgressBar()
        self.storage_bar.setRange(0, 100)
        self.storage_bar.setValue(0)
        self.storage_bar.setTextVisible(False)
        self.storage_bar.setMaximumHeight(12)
        self.storage_label = QLabel("--")
        self.storage_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.usb_title_label = QLabel("USB")
        self.usb_bar = QProgressBar()
        self.usb_bar.setRange(0, 100)
        self.usb_bar.setValue(0)
        self.usb_bar.setTextVisible(False)
        self.usb_bar.setMaximumHeight(12)
        self.usb_label = QLabel("Checking...")
        self.usb_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.refresh_button = QPushButton("Refresh")
        set_text_button_min_width(self.refresh_button, 82)

        storage_layout.addWidget(self.sd_title_label, 0, 0)
        storage_layout.addWidget(self.storage_bar, 0, 1)
        storage_layout.addWidget(self.storage_label, 0, 2)
        storage_layout.addWidget(self.usb_title_label, 1, 0)
        storage_layout.addWidget(self.usb_bar, 1, 1)
        storage_layout.addWidget(self.usb_label, 1, 2)
        storage_layout.addWidget(self.refresh_button, 2, 2, alignment=Qt.AlignmentFlag.AlignRight)
        storage_layout.setColumnStretch(1, 1)

        # File sharing
        sharing_group = QGroupBox("File Sharing")
        sharing_layout = QVBoxLayout(sharing_group)
        sharing_layout.setContentsMargins(12, 8, 12, 8)
        sharing_layout.setSpacing(6)
        self.smb_status_label = QLabel("SMB: Unknown")
        self.smb_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sharing_actions = QHBoxLayout()
        sharing_actions.setSpacing(6)
        self.enable_smb_button = QPushButton("Enable SMB")
        self.disable_smb_button = QPushButton("Disable SMB")
        self.open_share_button = QPushButton(self.open_share_button_text())
        sharing_actions.addStretch()
        sharing_actions.addWidget(self.open_share_button)
        sharing_actions.addWidget(self.enable_smb_button)
        sharing_actions.addWidget(self.disable_smb_button)
        sharing_actions.addStretch()
        sharing_layout.addWidget(self.smb_status_label)
        sharing_layout.addLayout(sharing_actions)

        # Static wallpaper
        self.static_wallpaper_group = QGroupBox("Static Wallpaper")
        wallpaper_layout = QVBoxLayout(self.static_wallpaper_group)
        wallpaper_layout.setContentsMargins(12, 8, 12, 8)
        wallpaper_layout.setSpacing(6)
        self.static_wallpaper_status_label = QLabel("Static wallpaper: Unknown")
        self.static_wallpaper_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wallpaper_actions = QHBoxLayout()
        wallpaper_actions.setSpacing(6)
        self.set_static_wallpaper_button = QPushButton("Set / Change")
        self.remove_static_wallpaper_button = QPushButton("Remove")
        wallpaper_actions.addStretch()
        wallpaper_actions.addWidget(self.set_static_wallpaper_button)
        wallpaper_actions.addWidget(self.remove_static_wallpaper_button)
        wallpaper_actions.addStretch()
        wallpaper_layout.addWidget(self.static_wallpaper_status_label)
        wallpaper_layout.addLayout(wallpaper_actions)

        # Updates
        self.update_all_group = QGroupBox("Update All")
        update_layout = QVBoxLayout(self.update_all_group)
        update_layout.setContentsMargins(12, 8, 12, 8)
        update_layout.setSpacing(6)
        self.update_all_status_label = QLabel("update_all: Unknown")
        self.update_all_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        update_actions = QHBoxLayout()
        update_actions.setSpacing(6)
        self.run_update_all_button = QPushButton("Run")
        self.configure_update_all_button = QPushButton("Configure")
        update_actions.addStretch()
        update_actions.addWidget(self.run_update_all_button)
        update_actions.addWidget(self.configure_update_all_button)
        update_actions.addStretch()
        update_layout.addWidget(self.update_all_status_label)
        update_layout.addLayout(update_actions)
        self.update_all_group.setVisible(False)

        # Zaparoo
        self.zaparoo_group = QGroupBox("Zaparoo PIN Encryption")
        zaparoo_layout = QVBoxLayout(self.zaparoo_group)
        zaparoo_layout.setContentsMargins(12, 8, 12, 8)
        zaparoo_layout.setSpacing(6)
        self.zaparoo_status_label = QLabel("")
        self.zaparoo_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zaparoo_status_label.setWordWrap(True)
        zaparoo_actions = QHBoxLayout()
        zaparoo_actions.setSpacing(6)
        self.zaparoo_pair_button = QPushButton("Pair")
        self.zaparoo_remove_pair_button = QPushButton("Remove Pairing")
        zaparoo_actions.addStretch()
        zaparoo_actions.addWidget(self.zaparoo_pair_button)
        zaparoo_actions.addWidget(self.zaparoo_remove_pair_button)
        zaparoo_actions.addStretch()
        zaparoo_layout.addWidget(self.zaparoo_status_label)
        zaparoo_layout.addLayout(zaparoo_actions)
        self.zaparoo_group.setVisible(False)

        # Device actions
        self.device_actions_group = QGroupBox("Device Actions")
        power_layout = QHBoxLayout(self.device_actions_group)
        power_layout.setContentsMargins(12, 8, 12, 8)
        power_layout.setSpacing(8)
        self.return_to_menu_button = QPushButton("Return to Menu")
        self.reboot_button = QPushButton("Reboot MiSTer")
        power_layout.addStretch()
        power_layout.addWidget(self.return_to_menu_button)
        power_layout.addWidget(self.reboot_button)
        power_layout.addStretch()

        cards_grid.addWidget(storage_group, 0, 0)
        cards_grid.addWidget(sharing_group, 0, 1)
        cards_grid.addWidget(self.static_wallpaper_group, 1, 0)
        cards_grid.addWidget(self.update_all_group, 1, 1)
        cards_grid.addWidget(self.zaparoo_group, 2, 0)
        cards_grid.addWidget(self.device_actions_group, 2, 1)
        main_layout.addLayout(cards_grid)
        main_layout.addStretch(1)

        self.disconnect_button.clicked.connect(self.handle_disconnect_or_unload)
        self.refresh_button.clicked.connect(self.refresh_info)
        self.enable_smb_button.clicked.connect(self.enable_smb)
        self.disable_smb_button.clicked.connect(self.disable_smb)
        self.open_share_button.clicked.connect(self.open_share)
        self.return_to_menu_button.clicked.connect(self.return_to_menu)
        self.reboot_button.clicked.connect(self.reboot_device)
        self.run_update_all_button.clicked.connect(self.run_update_all)
        self.configure_update_all_button.clicked.connect(self.configure_update_all)
        self.set_static_wallpaper_button.clicked.connect(self.set_static_wallpaper)
        self.remove_static_wallpaper_button.clicked.connect(self.remove_static_wallpaper_action)
        self.zaparoo_pair_button.clicked.connect(self.pair_with_zaparoo)
        self.zaparoo_remove_pair_button.clicked.connect(self.remove_zaparoo_pairing)

    def handle_disconnect_or_unload(self):
        if self.is_offline_mode():
            if hasattr(self.main_window, "unload_offline_sd_card"):
                self.main_window.unload_offline_sd_card()
            return
        self.main_window.disconnect_from_mister()

    def update_connected_identity(self):
        host = getattr(self.connection, "host", "").strip()
        profile_name = ""
        connection_tab = getattr(self.main_window, "connection_tab", None)
        if connection_tab is not None and hasattr(connection_tab, "get_selected_profile_name"):
            profile_name = connection_tab.get_selected_profile_name().strip()

        if profile_name and host:
            self.connected_identity_label.setText(f"{profile_name} · {host}")
        else:
            self.connected_identity_label.setText(host)

    def update_zaparoo_pairing_state(self):
        online = not self.is_offline_mode() and self.connection.is_connected()
        host = getattr(self.connection, "host", "").strip() if online else ""
        self.zaparoo_group.setVisible(bool(online and host))
        if not online or not host:
            return

        paired = has_pairing_credentials(host)
        self.zaparoo_status_label.setText(
            "Optional API encryption: " + ("Paired" if paired else "Not paired")
        )
        self.zaparoo_pair_button.setVisible(not paired)
        self.zaparoo_remove_pair_button.setVisible(paired)

    def pair_with_zaparoo(self):
        if self.is_offline_mode() or not self.connection.is_connected():
            return
        if prompt_for_zaparoo_pairing(self, self.connection):
            self.update_zaparoo_pairing_state()

    def remove_zaparoo_pairing(self):
        if self.is_offline_mode() or not self.connection.is_connected():
            return
        host = getattr(self.connection, "host", "").strip()
        if not host or not has_pairing_credentials(host):
            self.update_zaparoo_pairing_state()
            return

        answer = QMessageBox.question(
            self,
            "Remove Zaparoo Pairing",
            f"Remove the saved Zaparoo pairing for MiSTer {host}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            clear_pairing_credentials(host)
        except Exception as exc:
            QMessageBox.critical(self, "Could Not Remove Pairing", str(exc))
            return
        self.update_zaparoo_pairing_state()

    def open_share_button_text(self):
        if sys.platform == "darwin":
            return "Open in Finder"

        if sys.platform.startswith("linux"):
            return "Open in File Browser"

        return "Open in Explorer"

    def show_usb_storage(self, visible: bool):
        self.usb_title_label.setVisible(visible)
        self.usb_bar.setVisible(visible)
        self.usb_label.setVisible(visible)

        if not visible:
            self.usb_bar.setValue(0)
            self.usb_bar.setStyleSheet("")
            self.usb_label.setText("")
            self.usb_label.setStyleSheet("")

    def show_refreshing_state(self):
        if self.status_worker is not None and self.status_worker.isRunning():
            return

        if self.is_offline_mode():
            if not self.get_offline_sd_root():
                return
        elif not self.connection.is_connected():
            return

        self.refresh_button.setEnabled(False)

        self.storage_label.setText("Refreshing...")
        self.storage_label.setStyleSheet("color: #1e88e5; font-weight: bold;")

        if not self.is_offline_mode():
            self.show_usb_storage(True)
            self.usb_label.setText("Refreshing...")
            self.usb_label.setStyleSheet("color: #1e88e5; font-weight: bold;")

        self.smb_status_label.setText(
            "SMB: Refreshing..."
        )
        self.smb_status_label.setStyleSheet("color: #1e88e5; font-weight: bold;")

        self.now_playing_summary_label.setText("")
        self.now_playing_group.setVisible(False)

    def showEvent(self, event):
        super().showEvent(event)

        self.refresh_timer.stop()

        if self.is_offline_mode():
            self.apply_offline_state(lightweight=True)
            self.refresh_info()
            return

        if self.connection.is_connected():
            self.refresh_info()
            self.refresh_timer.start()
            self.start_hifi_listener()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.refresh_timer.stop()
        self.stop_hifi_listener()

    def is_offline_mode(self):
        return hasattr(self.main_window, "is_offline_mode") and self.main_window.is_offline_mode()

    def get_offline_sd_root(self):
        if hasattr(self.main_window, "get_offline_sd_root"):
            return self.main_window.get_offline_sd_root()
        return ""

    def update_connection_state(self, lightweight=True):
        self.refresh_timer.stop()

        if self.is_offline_mode():
            self.apply_offline_state(lightweight=lightweight)

            if not lightweight and self.isVisible():
                self.refresh_info()

            return

        if self.connection.is_connected():
            self.apply_connected_state()

            if not lightweight and self.isVisible():
                self.refresh_info()
        else:
            self.apply_disconnected_state()

    def refresh_status(self):
        self.update_connection_state(lightweight=False)

    def apply_connected_state(self):
        self.connected_status_label.setText("● Connected")
        self.connected_status_label.setStyleSheet("font-weight: bold; color: #00aa00;")
        self.disconnect_button.setText("Disconnect")
        self.device_actions_group.setVisible(True)
        self.update_connected_identity()
        self.refresh_button.setEnabled(True)
        self.return_to_menu_button.setEnabled(True)
        self.reboot_button.setEnabled(True)
        self.enable_smb_button.setEnabled(True)
        self.disable_smb_button.setEnabled(True)
        self.open_share_button.setEnabled(False)

        self.enable_smb_button.setText(
            "Enable SMB"
        )
        self.disable_smb_button.setText(
            "Disable SMB"
        )
        self.open_share_button.setText(self.open_share_button_text())

        self.refresh_button.setToolTip("")
        self.return_to_menu_button.setToolTip("")
        self.reboot_button.setToolTip("")
        self.enable_smb_button.setToolTip("")
        self.disable_smb_button.setToolTip("")
        self.open_share_button.setToolTip("")

        self.show_usb_storage(True)
        self.update_zaparoo_pairing_state()
        if self.isVisible():
            self.refresh_timer.start()
            self.start_hifi_listener()

    def apply_disconnected_state(self):
        self.refresh_timer.stop()
        self.stop_hifi_listener()
        if hasattr(self, "hifi_group"):
            self.hifi_group.setVisible(False)
        self.zaparoo_group.setVisible(False)
        self.device_actions_group.setVisible(False)
        self.connected_status_label.setText("● Disconnected")
        self.connected_status_label.setStyleSheet("font-weight: bold; color: gray;")
        self.connected_identity_label.setText("")
        self.disconnect_button.setText("Disconnect")

        self.refresh_button.setEnabled(False)
        self.return_to_menu_button.setEnabled(False)
        self.enable_smb_button.setEnabled(False)
        self.disable_smb_button.setEnabled(False)
        self.open_share_button.setEnabled(False)
        self.reboot_button.setEnabled(False)
        self.set_static_wallpaper_button.setEnabled(False)
        self.remove_static_wallpaper_button.setEnabled(False)

        self.enable_smb_button.setText(
            "Enable SMB"
        )
        self.disable_smb_button.setText(
            "Disable SMB"
        )
        self.open_share_button.setText(self.open_share_button_text())

        self.refresh_button.setToolTip("")
        self.return_to_menu_button.setToolTip("")
        self.reboot_button.setToolTip("")
        self.enable_smb_button.setToolTip("")
        self.disable_smb_button.setToolTip("")
        self.open_share_button.setToolTip("")

        self.show_usb_storage(True)

        self.storage_bar.setValue(0)
        self.usb_bar.setValue(0)
        self.storage_bar.setStyleSheet("")
        self.usb_bar.setStyleSheet("")

        self.storage_label.setText("--")
        self.storage_label.setStyleSheet("")
        self.usb_label.setText("--")
        self.usb_label.setStyleSheet("")
        self.smb_status_label.setText(
            "SMB: Unknown"
        )
        self.smb_status_label.setStyleSheet("")
        self.static_wallpaper_status_label.setText("Static wallpaper: Unknown")
        self.static_wallpaper_status_label.setStyleSheet("")

        self.now_playing_summary_label.setText("")
        self.now_playing_group.setVisible(False)
        if hasattr(self, "update_all_group"):
            self.update_all_group.setVisible(False)

    def apply_offline_state(self, lightweight=True):
        self.refresh_timer.stop()
        self.stop_hifi_listener()
        if hasattr(self, "hifi_group"):
            self.hifi_group.setVisible(False)
        self.zaparoo_group.setVisible(False)
        self.now_playing_group.setVisible(False)
        self.device_actions_group.setVisible(False)

        sd_root = self.get_offline_sd_root()
        self.connected_status_label.setText("● Offline")
        self.connected_status_label.setStyleSheet("font-weight: bold; color: #8b5cf6;")
        self.connected_identity_label.setText(f"SD Card · {sd_root}" if sd_root else "SD Card")
        self.disconnect_button.setText("Unload SD Card")
        self.disconnect_button.setEnabled(bool(sd_root))

        self.refresh_button.setEnabled(True)
        self.return_to_menu_button.setEnabled(False)
        self.reboot_button.setEnabled(False)

        self.refresh_button.setToolTip("")
        self.return_to_menu_button.setToolTip("Unavailable in Offline Mode because it requires a running MiSTer.")
        self.reboot_button.setToolTip("Unavailable in Offline Mode because it requires a running MiSTer.")

        self.enable_smb_button.setText(
            "Enable SMB on Boot"
        )
        self.disable_smb_button.setText(
            "Disable SMB on Boot"
        )
        self.open_share_button.setText("Open SD Card")

        self.enable_smb_button.setToolTip(
            "Changes the SD card startup setting. It will apply the next time MiSTer boots."
        )
        self.disable_smb_button.setToolTip(
            "Changes the SD card startup setting. It will apply the next time MiSTer boots."
        )
        self.open_share_button.setToolTip("Open the selected SD card folder.")

        has_sd_root = bool(sd_root)

        self.open_share_button.setEnabled(has_sd_root)
        self.enable_smb_button.setEnabled(has_sd_root)
        self.disable_smb_button.setEnabled(has_sd_root)
        self.set_static_wallpaper_button.setEnabled(has_sd_root)
        self.remove_static_wallpaper_button.setEnabled(False)

        self.show_usb_storage(False)

        self.now_playing_summary_label.setText("")
        self.now_playing_group.setVisible(False)
        if hasattr(self, "update_all_group"):
            self.update_all_group.setVisible(False)

        if lightweight:
            if not sd_root:
                self.storage_bar.setValue(0)
                self.storage_bar.setStyleSheet("")
                self.storage_label.setText("Offline Mode: No SD card selected")
                self.storage_label.setStyleSheet("")
                self.smb_status_label.setText(
                    "SMB Startup: No SD card selected"
                )
                self.smb_status_label.setStyleSheet("color: #f39c12;")
                self.enable_smb_button.setEnabled(False)
                self.disable_smb_button.setEnabled(False)
                self.open_share_button.setEnabled(False)
                self.static_wallpaper_status_label.setText("Static wallpaper: No SD card selected")
                self.static_wallpaper_status_label.setStyleSheet("color: #f39c12;")
            return

        self.refresh_info()

    def refresh_info(self):
        self.refresh_timer.stop()

        if self.status_worker is not None and self.status_worker.isRunning():
            return

        if self.is_offline_mode():
            sd_root = self.get_offline_sd_root()

            if not sd_root:
                self.apply_offline_state(lightweight=True)
                return

            self.apply_offline_state(lightweight=True)
            self.show_refreshing_state()

            self.status_worker = DeviceStatusWorker(
                self.connection,
                offline_mode=True,
                sd_root=sd_root,
                parent=self,
            )
            self.status_worker.result.connect(self.on_status_refresh_result)
            self.status_worker.error.connect(self.on_status_refresh_error)
            self.status_worker.finished.connect(
                lambda worker=self.status_worker: self.on_status_refresh_finished(worker)
            )
            self.status_worker.start()
            return

        if not self.connection.is_connected():
            self.apply_disconnected_state()
            return

        self.apply_connected_state()
        self.show_refreshing_state()

        self.status_worker = DeviceStatusWorker(
            self.connection,
            offline_mode=False,
            sd_root="",
            parent=self,
        )
        self.status_worker.result.connect(self.on_status_refresh_result)
        self.status_worker.error.connect(self.on_status_refresh_error)
        self.status_worker.finished.connect(
            lambda worker=self.status_worker: self.on_status_refresh_finished(worker)
        )
        self.status_worker.start()

    def on_status_refresh_result(self, result):
        if self._shutting_down:
            return
        if result.get("offline"):
            self.apply_offline_state(lightweight=True)
            self.apply_offline_status_result(result)
            return

        if not self.connection.is_connected():
            self.apply_disconnected_state()
            return

        self.apply_connected_state()
        self.apply_online_status_result(result)

    def on_status_refresh_error(self, message):
        if self._shutting_down:
            return
        self.refresh_timer.stop()

        if self.is_offline_mode():
            self.storage_bar.setValue(0)
            self.storage_bar.setStyleSheet("")
            self.storage_label.setText("Unable to read selected SD card storage")
            self.storage_label.setStyleSheet("")
            self.smb_status_label.setText(
                "SMB Startup: Unknown"
            )
            self.smb_status_label.setStyleSheet("color: #f39c12;")
            self.refresh_button.setEnabled(True)
            return

        try:
            self.connection.mark_disconnected()
        except Exception:
            pass

        self.apply_disconnected_state()

    def on_status_refresh_finished(self, worker):
        if self.status_worker is worker:
            self.status_worker = None
        worker.deleteLater()
        if self._shutting_down:
            self.refresh_timer.stop()
        elif not self.is_offline_mode() and self.connection.is_connected() and self.isVisible():
            self.refresh_timer.start()
        else:
            self.refresh_timer.stop()

    def apply_offline_status_result(self, result):
        sd_info = result.get("sd_info")

        if sd_info:
            self.storage_bar.setValue(sd_info["percent"])
            self.storage_bar.setStyleSheet(sd_info["style"])
            self.storage_label.setText(sd_info["label"])
            self.storage_label.setStyleSheet("")
        else:
            self.storage_bar.setValue(0)
            self.storage_bar.setStyleSheet("")
            self.storage_label.setText("Unable to read selected SD card storage")
            self.storage_label.setStyleSheet("")

        smb_enabled = result.get("smb_enabled")
        smb_error = result.get("smb_error", "")

        self.refresh_button.setEnabled(True)
        self.open_share_button.setEnabled(bool(self.get_offline_sd_root()))
        self.apply_update_all_status(bool(result.get("update_all_installed")))
        self.apply_static_wallpaper_status(bool(result.get("static_wallpaper_active")))

        if smb_error:
            self.smb_status_label.setText(
                "SMB Startup: Unknown"
            )
            self.smb_status_label.setStyleSheet("color: #f39c12;")
            self.enable_smb_button.setEnabled(True)
            self.disable_smb_button.setEnabled(True)
            return

        if smb_enabled:
            self.smb_status_label.setText(
                "SMB Startup: Enabled ✓"
            )
            self.smb_status_label.setStyleSheet("color: #00aa00;")
            self.enable_smb_button.setEnabled(False)
            self.disable_smb_button.setEnabled(True)
        else:
            self.smb_status_label.setText(
                "SMB Startup: Disabled"
            )
            self.smb_status_label.setStyleSheet("color: #cc0000;")
            self.enable_smb_button.setEnabled(True)
            self.disable_smb_button.setEnabled(False)

    def apply_online_status_result(self, result):
        sd_info = result.get("sd_info")

        self.refresh_button.setEnabled(True)

        if sd_info:
            self.storage_bar.setValue(sd_info["percent"])
            self.storage_bar.setStyleSheet(sd_info["style"])
            self.storage_label.setText(sd_info["label"])
            self.storage_label.setStyleSheet("")
        else:
            self.storage_bar.setValue(0)
            self.storage_bar.setStyleSheet("")
            self.storage_label.setText("--")
            self.storage_label.setStyleSheet("")

        usb_info = result.get("usb_info") or {}

        if not usb_info.get("present"):
            self.show_usb_storage(False)
        else:
            self.show_usb_storage(True)

            if not usb_info.get("readable"):
                self.usb_bar.setValue(0)
                self.usb_bar.setStyleSheet("")
                self.usb_label.setText(usb_info.get("label", "--"))
                self.usb_label.setStyleSheet("")
            else:
                self.usb_bar.setValue(usb_info["percent"])
                self.usb_bar.setStyleSheet(usb_info["style"])
                self.usb_label.setText(usb_info["label"])
                self.usb_label.setStyleSheet("")

        smb_enabled = bool(result.get("smb_enabled"))

        if smb_enabled:
            self.smb_status_label.setText(
                "SMB: Enabled ✓"
            )
            self.smb_status_label.setStyleSheet("color: #00aa00;")
            self.enable_smb_button.setEnabled(False)
            self.disable_smb_button.setEnabled(True)
            self.open_share_button.setEnabled(True)
        else:
            self.smb_status_label.setText(
                "SMB: Disabled"
            )
            self.smb_status_label.setStyleSheet("color: #cc0000;")
            self.enable_smb_button.setEnabled(True)
            self.disable_smb_button.setEnabled(False)
            self.open_share_button.setEnabled(False)

        self.apply_update_all_status(bool(result.get("update_all_installed")))
        self.apply_static_wallpaper_status(bool(result.get("static_wallpaper_active")))

        now_playing = result.get("now_playing") or {}
        self.apply_now_playing(now_playing)


    def apply_static_wallpaper_status(self, active: bool):
        self.set_static_wallpaper_button.setEnabled(True if self.is_offline_mode() else self.connection.is_connected())
        self.remove_static_wallpaper_button.setEnabled(bool(active))
        if active:
            self.static_wallpaper_status_label.setText("Static wallpaper: Active ✓")
            self.static_wallpaper_status_label.setStyleSheet("color: #00aa00;")
        else:
            self.static_wallpaper_status_label.setText("Static wallpaper: Not active")
            self.static_wallpaper_status_label.setStyleSheet("color: gray;")

    def set_static_wallpaper(self):
        if self.is_offline_mode():
            sd_root = self.get_offline_sd_root()
            if not sd_root:
                QMessageBox.warning(self, "Static Wallpaper", "Select an Offline SD Card folder first.")
                return
            dialog = StaticWallpaperDialog(connection=None, parent=self, sd_root=sd_root)
            if dialog.exec():
                self.refresh_info()
            return

        if not self.connection.is_connected():
            QMessageBox.warning(self, "Static Wallpaper", "Connect to a MiSTer first.")
            return
        dialog = StaticWallpaperDialog(self.connection, self)
        if dialog.exec():
            self.refresh_info()

    def remove_static_wallpaper_action(self):
        if self.is_offline_mode():
            sd_root = self.get_offline_sd_root()
            if not sd_root:
                QMessageBox.warning(self, "Static Wallpaper", "Select an Offline SD Card folder first.")
                return
            confirm = QMessageBox.question(self, "Remove Static Wallpaper", "Remove the current static wallpaper from the Offline SD Card?")
            if confirm != QMessageBox.StandardButton.Yes:
                return
            try:
                remove_static_wallpaper_local(sd_root)
                self.refresh_info()
            except Exception as e:
                QMessageBox.critical(self, "Static Wallpaper", str(e))
            return

        if not self.connection.is_connected():
            QMessageBox.warning(self, "Static Wallpaper", "Connect to a MiSTer first.")
            return
        confirm = QMessageBox.question(self, "Remove Static Wallpaper", "Remove the current static wallpaper from the MiSTer?")
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            remove_static_wallpaper(self.connection, reload_menu=True)
            self.refresh_info()
        except Exception as e:
            QMessageBox.critical(self, "Static Wallpaper", str(e))

    def apply_update_all_status(self, installed: bool):
        if not hasattr(self, "update_all_group"):
            return

        self.update_all_group.setVisible(installed)
        self.run_update_all_button.setEnabled(installed)
        self.configure_update_all_button.setEnabled(installed)

        if not installed:
            self.update_all_status_label.setText("update_all: Not installed")
            self.update_all_status_label.setStyleSheet("")
            return

        if self.is_offline_mode():
            self.update_all_status_label.setText("update_all: Installed on selected SD card ✓")
        else:
            self.update_all_status_label.setText("update_all: Installed ✓")
        self.update_all_status_label.setStyleSheet("color: #00aa00;")

    def run_update_all(self):
        task = prepare_update_all_task(self.main_window, parent=self, installed=True)
        if task is None:
            return
        dialog = UpdateAllOutputDialog(self.main_window, task, parent=self)
        self.update_all_output_dialog = dialog
        dialog.finished.connect(self.refresh_info)
        dialog.show()
        dialog.start()

    def configure_update_all(self):
        install_center = getattr(self.main_window, "install_center_tab", None)
        actions = getattr(install_center, "actions", None)
        if actions is None:
            QMessageBox.warning(self, "Update All", "Install Center backend is not available.")
            return
        actions.configure_update_all(installed=True)
        self.refresh_info()

    def refresh_offline_storage(self):
        sd_root = self.get_offline_sd_root()

        if not sd_root:
            self.storage_bar.setValue(0)
            self.storage_bar.setStyleSheet("")
            self.storage_label.setText("Offline Mode: No SD card selected")
            self.storage_label.setStyleSheet("")
            return

        sd_info = get_sd_storage_info_offline(sd_root)

        if sd_info:
            self.storage_bar.setValue(sd_info["percent"])
            self.storage_bar.setStyleSheet(sd_info["style"])
            self.storage_label.setText(sd_info["label"])
            self.storage_label.setStyleSheet("")
        else:
            self.storage_bar.setValue(0)
            self.storage_bar.setStyleSheet("")
            self.storage_label.setText("Unable to read selected SD card storage")
            self.storage_label.setStyleSheet("")

    def refresh_offline_smb_status(self):
        sd_root = self.get_offline_sd_root()

        if not sd_root:
            self.smb_status_label.setText(
                "SMB Startup: No SD card selected"
            )
            self.smb_status_label.setStyleSheet("color: #f39c12;")
            self.enable_smb_button.setEnabled(False)
            self.disable_smb_button.setEnabled(False)
            self.open_share_button.setEnabled(False)
            return

        self.open_share_button.setEnabled(True)

        try:
            smb_enabled = is_smb_enabled_offline(sd_root)
        except Exception:
            self.smb_status_label.setText(
                "SMB Startup: Unknown"
            )
            self.smb_status_label.setStyleSheet("color: #f39c12;")
            self.enable_smb_button.setEnabled(True)
            self.disable_smb_button.setEnabled(True)
            return

        if smb_enabled:
            self.smb_status_label.setText(
                "SMB Startup: Enabled ✓"
            )
            self.smb_status_label.setStyleSheet("color: #00aa00;")
            self.enable_smb_button.setEnabled(False)
            self.disable_smb_button.setEnabled(True)
        else:
            self.smb_status_label.setText(
                "SMB Startup: Disabled"
            )
            self.smb_status_label.setStyleSheet("color: #cc0000;")
            self.enable_smb_button.setEnabled(True)
            self.disable_smb_button.setEnabled(False)

    def refresh_storage(self):
        if self.is_offline_mode():
            self.refresh_offline_storage()
            return

        sd_info = get_sd_storage_info(self.connection)

        if sd_info:
            self.storage_bar.setValue(sd_info["percent"])
            self.storage_bar.setStyleSheet(sd_info["style"])
            self.storage_label.setText(sd_info["label"])
            self.storage_label.setStyleSheet("")
        else:
            self.storage_bar.setValue(0)
            self.storage_bar.setStyleSheet("")
            self.storage_label.setText("--")
            self.storage_label.setStyleSheet("")

        usb_info = get_usb_storage_info(self.connection)

        if not usb_info["present"]:
            self.show_usb_storage(False)
            return

        self.show_usb_storage(True)

        if not usb_info["readable"]:
            self.usb_bar.setValue(0)
            self.usb_bar.setStyleSheet("")
            self.usb_label.setText(usb_info["label"])
            self.usb_label.setStyleSheet("")
            return

        self.usb_bar.setValue(usb_info["percent"])
        self.usb_bar.setStyleSheet(usb_info["style"])
        self.usb_label.setText(usb_info["label"])
        self.usb_label.setStyleSheet("")

    def refresh_smb_status(self):
        if self.is_offline_mode():
            self.refresh_offline_smb_status()
            return

        smb_enabled = is_smb_enabled(self.connection)

        if smb_enabled:
            self.smb_status_label.setText(
                "SMB: Enabled ✓"
            )
            self.smb_status_label.setStyleSheet("color: #00aa00;")
            self.enable_smb_button.setEnabled(False)
            self.disable_smb_button.setEnabled(True)
            self.open_share_button.setEnabled(True)
        else:
            self.smb_status_label.setText(
                "SMB: Disabled"
            )
            self.smb_status_label.setStyleSheet("color: #cc0000;")
            self.enable_smb_button.setEnabled(True)
            self.disable_smb_button.setEnabled(False)
            self.open_share_button.setEnabled(False)

    def poll_now_playing(self):
        if self._shutting_down:
            return
        if self.is_offline_mode() or not self.connection.is_connected() or not self.isVisible():
            self.refresh_timer.stop()
            self.apply_now_playing({})
            return
        if self.now_playing_worker is not None and self.now_playing_worker.isRunning():
            return
        worker = NowPlayingWorker(self.connection, parent=self)
        self.now_playing_worker = worker
        worker.result.connect(self.apply_now_playing)
        worker.finished.connect(lambda w=worker: self.on_now_playing_worker_finished(w))
        worker.start()

    def on_now_playing_worker_finished(self, worker):
        if self.now_playing_worker is worker:
            self.now_playing_worker = None
        worker.deleteLater()

    def apply_now_playing(self, active_media):
        if self._shutting_down:
            return
        if not isinstance(active_media, dict) or not active_media:
            self.now_playing_summary_label.setText("")
            self.now_playing_group.setVisible(False)
            return

        # Current Core versions return the active media object directly. Keep
        # these aliases for compatibility with nearby API revisions.
        if active_media.get("playing") is False or active_media.get("active") is False:
            self.now_playing_summary_label.setText("")
            self.now_playing_group.setVisible(False)
            return

        if isinstance(active_media.get("active"), dict):
            media = active_media["active"]
        elif isinstance(active_media.get("media"), dict):
            media = active_media["media"]
        else:
            media = active_media
        if not isinstance(media, dict) or not media:
            self.now_playing_summary_label.setText("")
            self.now_playing_group.setVisible(False)
            return

        name = str(media.get("name") or media.get("title") or media.get("mediaName") or "").strip()
        system = media.get("system")
        if isinstance(system, dict):
            system = system.get("name") or system.get("id") or ""
        system = str(system or media.get("systemName") or media.get("systemId") or "").strip()
        path = str(media.get("path") or media.get("mediaPath") or "").strip()

        if not name and path:
            name = path.replace("\\", "/").rstrip("/").split("/")[-1]
            if "." in name:
                name = name.rsplit(".", 1)[0]

        if not name and not system:
            self.now_playing_summary_label.setText("")
            self.now_playing_group.setVisible(False)
            return

        summary = f"{system} · {name}" if system and name else (name or system)
        self.now_playing_summary_label.setText(summary)
        self.now_playing_group.setVisible(True)

    def refresh_now_playing(self):
        if self.is_offline_mode():
            self.now_playing_summary_label.setText("")
            self.now_playing_group.setVisible(False)
            return

        self.apply_now_playing(resolve_now_playing(self.connection, timeout=3))

    @staticmethod
    def format_hifi_time(value):
        try:
            seconds = max(0, int(float(value or 0)))
        except Exception:
            seconds = 0
        return f"{seconds // 60}:{seconds % 60:02d}"

    def refresh_hifi_icons(self):
        mode = self.main_window.config_data.get("theme_mode", "auto")
        color = theme_text_color(mode)
        slider_style = (
            "QSlider::groove:horizontal {"
            "height: 6px;"
            "background-color: palette(mid);"
            "border-radius: 3px;"
            "}"
            "QSlider::sub-page:horizontal {"
            f"background-color: {color};"
            "border-radius: 3px;"
            "}"
            "QSlider::add-page:horizontal {"
            "background-color: palette(mid);"
            "border-radius: 3px;"
            "}"
            "QSlider::handle:horizontal {"
            f"background-color: {color};"
            "border: none;"
            "width: 14px;"
            "margin: -4px 0;"
            "border-radius: 7px;"
            "}"
        )
        if getattr(self, "_hifi_slider_style", None) != slider_style:
            self._hifi_slider_style = slider_style
            self.hifi_progress.setStyleSheet(slider_style)
        self.hifi_previous_button.setIcon(self.main_window.svg_icon("hifi_previous", color))
        play_icon = "hifi_pause" if self.hifi_state.get("state") == "playing" else "hifi_play"
        self.hifi_play_button.setIcon(self.main_window.svg_icon(play_icon, color))
        self.hifi_next_button.setIcon(self.main_window.svg_icon("hifi_next", color))
        self.hifi_stop_button.setIcon(self.main_window.svg_icon("hifi_stop", color))

    def refresh_theme(self):
        if hasattr(self, "hifi_previous_button"):
            self.refresh_hifi_icons()

    def start_hifi_listener(self):
        if self._shutting_down:
            return
        if self.is_offline_mode() or not self.connection.is_connected():
            self.stop_hifi_listener()
            return
        if self.hifi_listener is not None:
            return

        listener = None

        def emit_state(state):
            # A listener can still be unwinding after a reconnect/disconnect.
            # Ignore callbacks from any listener that is no longer current.
            if not self._shutting_down and self.hifi_listener is listener:
                self.hifi_state_signal.emit(state)

        def emit_connected():
            if not self._shutting_down and self.hifi_listener is listener:
                self.hifi_connected_signal.emit()

        def emit_disconnected():
            if not self._shutting_down and self.hifi_listener is listener:
                self.hifi_disconnected_signal.emit()

        listener = HiFiWebSocketListener(
            self.connection,
            emit_state,
            emit_connected,
            emit_disconnected,
        )
        self.hifi_listener = listener
        listener.start()

    def stop_hifi_listener(self, join_timeout=0.0):
        listener = self.hifi_listener
        # Clear first so callbacks emitted while the worker is unwinding are
        # treated as stale and never reach Qt widgets.
        self.hifi_listener = None
        if listener is not None:
            listener.stop(join_timeout=join_timeout)
        if hasattr(self, "hifi_group"):
            self.hifi_group.setVisible(False)

    def on_hifi_connected(self):
        if not self.is_offline_mode() and self.connection.is_connected():
            self.hifi_group.setVisible(True)
            self.refresh_hifi_icons()

    def on_hifi_disconnected(self):
        self.hifi_group.setVisible(False)
        self.hifi_state = {}
        self.hifi_art_key = ""

    def apply_hifi_state(self, state):
        if self.is_offline_mode() or not self.connection.is_connected() or not isinstance(state, dict):
            self.hifi_group.setVisible(False)
            return
        self.hifi_group.setVisible(bool(state.get("connected", True)))
        self.hifi_state = state
        self.hifi_title_label.setText(str(state.get("title") or "Nothing playing"))
        self.hifi_artist_label.setText(str(state.get("artist") or ""))
        self.hifi_album_label.setText(str(state.get("album") or ""))
        position = float(state.get("position") or 0)
        duration = float(state.get("duration") or 0)
        if not self.hifi_slider_dragging:
            value = round(1000 * position / duration) if duration > 0 else 0
            self.hifi_progress.setValue(max(0, min(1000, value)))
            self.hifi_position_label.setText(self.format_hifi_time(position))
        self.hifi_duration_label.setText(self.format_hifi_time(duration))
        self.refresh_hifi_icons()

        art_key = str(state.get("art_key") or "") if state.get("has_art") else ""
        if not art_key:
            self.hifi_art_key = ""
            self.hifi_art_label.clear()
            self.hifi_art_label.setText("No Art")
        elif art_key != self.hifi_art_key:
            self.hifi_art_key = art_key
            self.load_hifi_art(art_key)

    def load_hifi_art(self, art_key):
        if self.hifi_art_worker is not None and self.hifi_art_worker.isRunning():
            return
        worker = HiFiRequestWorker(hifi_artwork, self.connection, art_key, parent=self)
        self.hifi_art_worker = worker
        worker.result.connect(lambda data, key=art_key: self.apply_hifi_art(key, data))
        worker.finished.connect(lambda w=worker: self.on_hifi_art_finished(w))
        worker.start()

    def on_hifi_art_finished(self, worker):
        if self.hifi_art_worker is worker:
            self.hifi_art_worker = None
        worker.deleteLater()

    def apply_hifi_art(self, art_key, data):
        if self._shutting_down:
            return
        if art_key != self.hifi_art_key or not data:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(QByteArray(bytes(data))):
            pixmap = pixmap.scaled(92, 92, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.hifi_art_label.setText("")
            self.hifi_art_label.setPixmap(pixmap)

    def hifi_send_control(self, action):
        self.run_hifi_request(hifi_control, self.connection, action)

    def run_hifi_request(self, fn, *args):
        if self._shutting_down:
            return
        if self.hifi_request_worker is not None and self.hifi_request_worker.isRunning():
            return
        worker = HiFiRequestWorker(fn, *args, parent=self)
        self.hifi_request_worker = worker
        worker.error.connect(lambda message: self.show_hifi_request_error(worker, message))
        worker.finished.connect(lambda w=worker: self.on_hifi_request_finished(w))
        worker.start()

    def show_hifi_request_error(self, worker, message):
        if self._shutting_down or self.hifi_request_worker is not worker:
            return
        QMessageBox.warning(self, "MiSTer Hi-Fi", message)

    def on_hifi_request_finished(self, worker):
        if self.hifi_request_worker is worker:
            self.hifi_request_worker = None
        worker.deleteLater()

    def hifi_slider_pressed(self):
        self.hifi_slider_dragging = True

    def hifi_slider_moved(self, value):
        duration = float(self.hifi_state.get("duration") or 0)
        if duration > 0:
            self.hifi_position_label.setText(self.format_hifi_time(duration * value / 1000.0))

    def hifi_slider_released(self):
        try:
            duration = float(self.hifi_state.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0.0
        value = self.hifi_progress.value()
        self.hifi_slider_dragging = False

        # Match MiSTer Hi-Fi's own Web Remote: update locally while dragging,
        # then send exactly one seek request when the interaction finishes.
        state = str(self.hifi_state.get("state") or "").lower()
        media_format = str(self.hifi_state.get("format") or "").upper()
        if state not in {"playing", "paused"} or duration <= 0:
            return
        # Online radio/HTTP streams are not seekable in MiSTer Hi-Fi.
        if media_format in {"STREAM", "RADIO"}:
            return

        target = duration * value / 1000.0
        # Keep the request inside the valid media range. Reaching the very end
        # is better handled by normal track completion/Next.
        if duration > 0.25:
            target = min(target, duration - 0.25)
        target = max(0.0, target)
        self.run_hifi_request(hifi_seek, self.connection, target)

    def open_hifi_browser(self):
        if self.is_offline_mode() or not self.connection.is_connected() or not self.hifi_group.isVisible():
            return
        dialog = MiSTerHiFiBrowserDialog(self.connection, self)
        dialog.exec()

    def shutdown(self):
        """Stop dashboard background activity before Qt destroys this widget."""
        if self._shutting_down:
            return
        self._shutting_down = True
        self.refresh_timer.stop()
        self.stop_hifi_listener(join_timeout=3.0)

        # All of these workers use bounded network operations. Waiting here is
        # limited to app shutdown/disposal and prevents QThread wrappers from
        # being destroyed while native code is still running.
        for attr_name in (
            "status_worker",
            "now_playing_worker",
            "hifi_request_worker",
            "hifi_art_worker",
        ):
            worker = getattr(self, attr_name, None)
            if worker is None:
                continue
            try:
                if worker.isRunning():
                    worker.requestInterruption()
                    worker.wait(6000)
            except RuntimeError:
                pass

            try:
                if not worker.isRunning():
                    worker.deleteLater()
                    if getattr(self, attr_name, None) is worker:
                        setattr(self, attr_name, None)
            except RuntimeError:
                if getattr(self, attr_name, None) is worker:
                    setattr(self, attr_name, None)

    def enable_smb(self):
        if self.is_offline_mode():
            self.enable_smb_offline()
            return

        if not self.connection.is_connected():
            QMessageBox.warning(self, "Not Connected", "Connect to a MiSTer first.")
            return

        enable_smb_remote(self.connection)

        reboot_now = QMessageBox.question(
            self,
            "SMB Enabled",
            (
                "SMB has been enabled.\n\nA reboot is required.\n\nReboot now?"
            ),
        )

        if reboot_now == QMessageBox.StandardButton.Yes:
            self.reboot_device(skip_confirm=True)
            return

        self.refresh_info()

    def disable_smb(self):
        if self.is_offline_mode():
            self.disable_smb_offline()
            return

        if not self.connection.is_connected():
            QMessageBox.warning(self, "Not Connected", "Connect to a MiSTer first.")
            return

        disable_smb_remote(self.connection)

        reboot_now = QMessageBox.question(
            self,
            "SMB Disabled",
            (
                "SMB has been disabled.\n\nA reboot is required.\n\nReboot now?"
            ),
        )

        if reboot_now == QMessageBox.StandardButton.Yes:
            self.reboot_device(skip_confirm=True)
            return

        self.refresh_info()

    def enable_smb_offline(self):
        sd_root = self.get_offline_sd_root()

        if not sd_root:
            QMessageBox.warning(self, "No SD Card Selected", "Select a MiSTer SD card first.")
            return

        try:
            enable_smb_offline(sd_root)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Enable Failed",
                f"Unable to enable SMB on boot:\n\n{str(e)}",
            )
            self.refresh_info()
            return

        QMessageBox.information(
            self,
            "SMB Enabled on Boot",
            (
                "SMB has been enabled on the selected SD card.\n\n"
                "It will apply the next time MiSTer boots."
            ),
        )

        self.refresh_info()

    def disable_smb_offline(self):
        sd_root = self.get_offline_sd_root()

        if not sd_root:
            QMessageBox.warning(self, "No SD Card Selected", "Select a MiSTer SD card first.")
            return

        try:
            disable_smb_offline(sd_root)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Disable Failed",
                f"Unable to disable SMB on boot:\n\n{str(e)}",
            )
            self.refresh_info()
            return

        QMessageBox.information(
            self,
            "SMB Disabled on Boot",
            (
                "SMB has been disabled on the selected SD card.\n\n"
                "It will apply the next time MiSTer boots."
            ),
        )

        self.refresh_info()

    def open_share(self):
        if self.is_offline_mode():
            sd_root = self.get_offline_sd_root()

            if not sd_root:
                QMessageBox.warning(self, "No SD Card Selected", "Select a MiSTer SD card first.")
                return

            try:
                open_local_folder(sd_root)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Open SD Card Failed",
                    f"Unable to open the selected SD card folder:\n\n{str(e)}",
                )
            return

        if not self.connection.host:
            QMessageBox.warning(self, self.open_share_button_text(), "No MiSTer IP address is available.")
            return

        try:
            open_mister_share(
                ip=self.connection.host,
                username=self.connection.username,
                password=self.connection.password,
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Unable to open share:\n\n{str(e)}",
            )

    def return_to_menu(self):
        if self.is_offline_mode():
            QMessageBox.information(
                self,
                "Offline Mode Active",
                "Return to Menu requires a running MiSTer and is only available in Online Mode."
            )
            return

        if not self.connection.is_connected():
            QMessageBox.warning(self, "Not Connected", "Connect to a MiSTer first.")
            return

        try:
            return_to_menu_remote(self.connection)
        except Exception as e:
            QMessageBox.critical(self, "Return to Menu Failed", str(e))
            return

    def reboot_device(self, skip_confirm=False):
        if self.is_offline_mode():
            QMessageBox.information(
                self,
                "Offline Mode Active",
                "Reboot requires a running MiSTer and is only available in Online Mode."
            )
            return

        if not self.connection.is_connected():
            QMessageBox.warning(self, "Not Connected", "Connect to a MiSTer first.")
            return

        if not skip_confirm:
            reply = QMessageBox.question(
                self,
                "Confirm Reboot",
                "Are you sure you want to reboot the MiSTer?",
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

        self.refresh_timer.stop()

        try:
            self.main_window.set_connection_status("Status: Rebooting...")
        except Exception:
            pass

        try:
            self.connection.reboot()
            self.main_window.start_reboot_reconnect_polling()
        except Exception as e:
            QMessageBox.critical(self, "Reboot Failed", str(e))
            return
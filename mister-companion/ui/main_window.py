import platform
import re
from pathlib import Path
from core.open_helpers import open_uri

from PyQt6.QtCore import QByteArray, QEvent, QPoint, QRect, QSize, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

try:
    from PyQt6.QtSvg import QSvgRenderer
except Exception:
    QSvgRenderer = None

from core.app_info import APP_NAME, APP_VERSION
from core.config import load_config, save_config
from core.connection import MiSTerConnection
from core.connection_monitor import ConnectionCheckWorker
from core.device_profiles import (
    add_device,
    delete_device,
    get_device_by_index,
    get_device_by_name,
    get_devices,
    get_profile_sync_roots,
    update_device,
)
from core.profile_folder_sync import profile_assigned_to_ip
from core.profile_identity import migrate_profile_identity, remove_profile_identity
from core.theme import apply_custom_theme_preview, apply_theme, custom_theme_roles, make_scaler, theme_accent_color, theme_logo_mode, theme_text_color
from core.updater import (
    check_for_update,
    launch_mc_updater,
    mc_updater_available,
    open_release_page,
)
from core.zaplauncher_db import rename_db
from ui.dialogs.device_dialog import DeviceDialog
from ui.dialogs.network_scanner_dialog import NetworkScannerDialog
from ui.dialogs.setup_notice_dialog import SetupNoticeDialog
from ui.dialogs.support_dialog import SupportDialog
from ui.dialogs.theme_picker_dialog import ThemePickerDialog
from ui.tabs.app_settings_tab import AppSettingsTab
from ui.dialogs.changelog_dialog import ChangelogDialog
from ui.dialogs.update_available_dialog import UpdateAvailableDialog
from ui.tabs.connection_tab import ConnectionTab
from ui.tabs.flash_tab import FlashTab
from ui.tabs.file_manager_tab import FileManagerTab
from ui.tabs.install_center_tab import InstallCenterTab
from ui.tabs.tools_tab import ToolsTab
from ui.tabs.mister_settings_tab import MiSTerSettingsTab
from ui.tabs.misterzine_tab import MiSTerZineTab
from ui.tabs.manuals_tab import ManualsTab
from ui.tabs.retroachievements_tab import RetroAchievementsTab
from ui.tabs.remote_tab import RemoteTab
from ui.tabs.savemanager_tab import SaveManagerTab
from ui.tabs.wallpapers_tab import WallpapersTab
from ui.tabs.zapscraper_tab import ZapScraperTab
from ui.tabs.zapscripts_tab import ZapScriptsTab


BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
ICON_PATH = ASSETS_DIR / "icon.png"
LOGO_LIGHT_PATH = ASSETS_DIR / "logo_1.png"
LOGO_DARK_PATH = ASSETS_DIR / "logo_2.png"
TAB_ICON_SIZE = QSize(16, 16)

APP_MODE_ONLINE = "online"
APP_MODE_OFFLINE = "offline"

FEEDBACK_URL = "https://github.com/Anime0t4ku/mister-companion/issues/new/choose"

UI_SCALE_OPTIONS = [75, 80, 85, 90, 95, 100, 105, 110, 115, 120, 125]
DEFAULT_UI_SCALE_PERCENT = 100


class UpwardComboBox(QComboBox):
    def showPopup(self):
        super().showPopup()

        try:
            popup = self.view().window()
            popup_height = popup.height()
            if popup_height <= 0:
                popup_height = popup.sizeHint().height()
            position = self.mapToGlobal(QPoint(0, 0))
            popup.move(position.x(), position.y() - popup_height)
        except Exception:
            pass


class UpdateCheckWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def run(self):
        try:
            info = check_for_update()
            self.result.emit(info)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):

    def __init__(self, app):
        super().__init__()

        self.app = app
        self.connection = MiSTerConnection()
        self.config_data = load_config()

        self.app_mode = APP_MODE_ONLINE
        self.offline_sd_loaded = False
        self.offline_sd_root = (
            str(self.config_data.get("offline_sd_root", "") or "").strip()
            if self.config_data.get("remember_offline_sd_root", False)
            else ""
        )

        self.connection_check_worker = None
        self.connection_fail_count = 0
        self.connection_fail_threshold = 3
        self._connected_session_active = False

        self.reboot_reconnect_worker = None
        self.reboot_reconnect_attempts = 0
        self.reboot_reconnect_max_attempts = 24
        self.reboot_reconnect_host = ""
        self.reboot_reconnect_username = ""
        self.reboot_reconnect_password = ""
        self.reboot_reconnect_use_ssh_agent = False
        self.reboot_reconnect_look_for_ssh_keys = False

        self.update_check_worker = None
        self.startup_update_check_done = False

        self._closing = False
        self._tab_refresh_generation = 0

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(1100, 830)

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.apply_default_window_size()
        self.restore_window_geometry()

        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        central_widget = QWidget()
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(6)
        root_layout.addWidget(content_widget, 1)

        self.content_area = QWidget()
        self.content_area_layout = QHBoxLayout(self.content_area)
        self.content_area_layout.setContentsMargins(0, 0, 0, 0)
        self.content_area_layout.setSpacing(8)

        self.side_menu = QFrame()
        self.side_menu.setObjectName("SideMenu")
        self.side_menu_layout = QVBoxLayout(self.side_menu)
        self.side_menu_layout.setContentsMargins(8, 8, 8, 8)
        self.side_menu_layout.setSpacing(6)
        self.side_menu_buttons = []
        self.side_menu_button_group = QButtonGroup(self)
        self.side_menu_button_group.setExclusive(True)
        self.side_menu_button_group.idClicked.connect(self.on_side_menu_clicked)
        self.tabs = QTabWidget()
        self.tabs.setIconSize(TAB_ICON_SIZE)

        self.content_area_layout.addWidget(self.side_menu)
        self.content_area_layout.addWidget(self.tabs, 1)
        content_layout.addWidget(self.content_area, 1)

        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 0, 0, 0)
        bottom_bar.setSpacing(8)

        self.connection_status_title_label = QLabel("MiSTer:")
        self.connection_status_title_label.setStyleSheet("font-weight: bold;")
        self.connection_status_label = QLabel("Disconnected")
        self.connection_status_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        bottom_bar.addWidget(self.connection_status_title_label)
        bottom_bar.addWidget(self.connection_status_label)

        self.footer_cloud_title_label = QLabel("Cloud:")
        self.footer_cloud_title_label.setStyleSheet("font-weight: bold;")
        self.footer_cloud_status_label = QLabel("Inactive")
        self.footer_cloud_status_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        self.footer_cloud_title_label.hide()
        self.footer_cloud_status_label.hide()
        bottom_bar.addSpacing(8)
        bottom_bar.addWidget(self.footer_cloud_title_label)
        bottom_bar.addWidget(self.footer_cloud_status_label)

        bottom_bar.addStretch()

        self.check_update_button = None

        self.scale_combo = UpwardComboBox()
        self.scale_combo.setToolTip("UI Scale")
        self.scale_combo.addItems([f"{value}%" for value in UI_SCALE_OPTIONS])
        self.scale_combo.setMinimumWidth(78)
        bottom_bar.addWidget(self.scale_combo)

        self.theme_button = QPushButton("Theme")
        self.theme_button.setObjectName("FooterButton")
        self.theme_button.setToolTip("Theme Picker")
        self.theme_button.clicked.connect(self.open_theme_picker)
        bottom_bar.addWidget(self.theme_button)

        self.apply_linux_footer_button_sizing()

        content_layout.addLayout(bottom_bar)

        self.setCentralWidget(central_widget)
        self.app.installEventFilter(self)

        self.set_connection_status("Status: Disconnected")
        self.update_footer_cloud_status()

        saved_theme = str(self.config_data.get("theme_mode", "auto") or "auto").strip().lower()

        if saved_theme == "purple":
            saved_theme = "dark"
            self.config_data["theme_mode"] = saved_theme
            save_config(self.config_data)

        if saved_theme not in {"auto", "light", "dark"} and not saved_theme.startswith("custom:"):
            saved_theme = "auto"
            self.config_data["theme_mode"] = saved_theme
            save_config(self.config_data)

        saved_scale_percent = self.normalize_ui_scale_percent(
            self.config_data.get("ui_scale_percent", DEFAULT_UI_SCALE_PERCENT)
        )

        if self.config_data.get("ui_scale_percent") != saved_scale_percent:
            self.config_data["ui_scale_percent"] = saved_scale_percent
            save_config(self.config_data)

        scale_text = f"{saved_scale_percent}%"
        scale_index = self.scale_combo.findText(scale_text)
        if scale_index < 0:
            scale_index = self.scale_combo.findText(f"{DEFAULT_UI_SCALE_PERCENT}%")
        self.scale_combo.setCurrentIndex(max(0, scale_index))

        self.update_theme_button_text()
        self.scale_combo.currentIndexChanged.connect(self.on_ui_scale_changed)
        self.refresh_theme()

        self.flash_tab = FlashTab(self)
        self.tabs.addTab(self.flash_tab, self.tab_icon("flash_sd"), "Flash SD")

        self.connection_tab = ConnectionTab(self)
        self.device_tab = self.connection_tab.device_dashboard
        self.tabs.addTab(self.connection_tab, self.tab_icon("connection"), "MiSTer")

        self.remote_tab = RemoteTab(self)
        self.tabs.addTab(self.remote_tab, self.tab_icon("remote"), "Remote")

        self.file_manager_tab = FileManagerTab(self)
        self.tabs.addTab(
            self.file_manager_tab,
            self.tab_icon("file_manager"),
            "File Manager",
        )

        self.install_center_tab = InstallCenterTab(self)
        self.tabs.addTab(self.install_center_tab, self.tab_icon("scripts"), "Install Center")

        self.mister_settings_tab = MiSTerSettingsTab(self)
        self.tabs.addTab(
            self.mister_settings_tab,
            self.tab_icon("mister_settings"),
            "MiSTer Settings",
        )

        self.savemanager_tab = SaveManagerTab(self)
        self.tabs.addTab(
            self.savemanager_tab,
            self.tab_icon("savemanager"),
            "SaveManager",
        )

        self.misterzine_tab = MiSTerZineTab(self)
        self.tabs.addTab(
            self.misterzine_tab,
            self.tab_icon("misterzine"),
            "MiSTerZine",
        )

        self.manuals_tab = ManualsTab(self)
        self.tabs.addTab(
            self.manuals_tab,
            self.tab_icon("manuals"),
            "Manuals",
        )

        self.retroachievements_tab = RetroAchievementsTab(self)
        self.tabs.addTab(
            self.retroachievements_tab,
            self.tab_icon("retroachievements"),
            "RetroAchievements",
        )

        self.zapscripts_tab = ZapScriptsTab(self)
        self.tabs.addTab(
            self.zapscripts_tab,
            self.tab_icon("zapscripts"),
            "ZapScripts",
        )

        self.zapscraper_tab = ZapScraperTab(self)
        self.tabs.addTab(
            self.zapscraper_tab,
            self.tab_icon("zapscraper"),
            "ZapScraper",
        )

        self.tools_tab = ToolsTab(self)
        self.tabs.addTab(self.tools_tab, self.tab_icon("tools"), "Tools")

        self.app_settings_tab = AppSettingsTab(self)
        self.tabs.addTab(self.app_settings_tab, self.tab_icon("settings"), "App Settings")

        self.wallpapers_tab = WallpapersTab(self)

        self.build_side_menu()
        self.tabs.setCurrentWidget(self.connection_tab)
        self.update_side_menu_selection(self.tabs.currentIndex())
        self.update_side_menu_style()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.apply_menu_style()

        self.load_devices()
        self.load_last_device()

        self.connection_monitor_timer = QTimer(self)
        self.connection_monitor_timer.timeout.connect(self.check_connection_status)
        self.connection_monitor_timer.start(5000)

        self.reboot_reconnect_timer = QTimer(self)
        self.reboot_reconnect_timer.timeout.connect(self.try_reconnect_after_reboot)

        self.apply_app_mode_state()
        self.update_all_tab_states(lightweight=True)

        QTimer.singleShot(300, self.show_setup_notice)
        QTimer.singleShot(1500, self.check_for_updates_on_startup)


    def tab_entries(self):
        return [
            ("Flash SD", "flash_sd"),
            ("MiSTer", "connection"),
            ("Remote", "remote"),
            ("File Manager", "file_manager"),
            ("Install Center", "scripts"),
            ("MiSTer Settings", "mister_settings"),
            ("SaveManager", "savemanager"),
            ("MiSTerZine", "misterzine"),
            ("Manuals", "manuals"),
            ("RetroAchievements", "retroachievements"),
            ("ZapScripts", "zapscripts"),
            ("ZapScraper", "zapscraper"),
            ("Tools", "tools"),
            ("App Settings", "settings"),
        ]

    def build_side_menu(self):
        if not hasattr(self, "side_menu_layout"):
            return

        while self.side_menu_layout.count():
            item = self.side_menu_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.side_menu_buttons = []
        max_text_width = 0
        font_metrics = self.fontMetrics()

        self.side_menu_logo_label = QLabel()
        self.side_menu_logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.side_menu_layout.addWidget(self.side_menu_logo_label)
        self.side_menu_layout.addSpacing(6)

        for index, (label, icon_name) in enumerate(self.tab_entries()):
            button = QPushButton(label)
            button.setObjectName("SideMenuButton")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setIcon(self.tab_icon(icon_name))
            button.setIconSize(TAB_ICON_SIZE)
            button.setMinimumHeight(34)
            max_text_width = max(max_text_width, font_metrics.horizontalAdvance(label))
            self.side_menu_button_group.addButton(button, index)
            self.side_menu_buttons.append((button, icon_name))
            self.side_menu_layout.addWidget(button)

        width = max_text_width + 56
        width = max(132, min(190, width))

        for button, _ in self.side_menu_buttons:
            button.setFixedWidth(width)

        self.side_menu.setFixedWidth(width + 16)
        self.update_side_menu_logo()
        self.side_menu_layout.addStretch()
        self.update_side_menu_selection(self.tabs.currentIndex() if hasattr(self, "tabs") else 0)

    def update_side_menu_logo(self, mode: str = ""):
        if not hasattr(self, "side_menu_logo_label"):
            return

        preview = getattr(self, "_theme_preview_data", None)
        if isinstance(preview, dict):
            logo_mode = "dark" if custom_theme_roles(preview)["is_dark"] else "light"
        else:
            if not mode:
                mode = self.config_data.get("theme_mode", "auto")
            logo_mode = theme_logo_mode(mode)
        logo_path = LOGO_DARK_PATH if logo_mode == "dark" else LOGO_LIGHT_PATH
        if not logo_path.exists():
            self.side_menu_logo_label.clear()
            return

        s = make_scaler(self.get_ui_scale_percent())
        available_width = max(s(110), self.side_menu.width() - s(16))
        target_size = QSize(available_width, s(48))
        pixmap = QPixmap(str(logo_path)).scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.side_menu_logo_label.setFixedHeight(s(48))
        self.side_menu_logo_label.setPixmap(pixmap)

    def refresh_side_menu_icons(self):
        if not hasattr(self, "side_menu_buttons"):
            return

        self.update_side_menu_selection(self.tabs.currentIndex() if hasattr(self, "tabs") else 0)

    def side_menu_icon(self, icon_name: str, selected: bool = False) -> QIcon:
        preview = getattr(self, "_theme_preview_data", None)
        if isinstance(preview, dict):
            accent = custom_theme_roles(preview)["accent"]
        else:
            accent = theme_accent_color(self.config_data.get("theme_mode", "auto"))
        color = "#ffffff" if selected else accent
        return self.svg_icon(icon_name, color)

    def update_side_menu_selection(self, index: int):
        if not hasattr(self, "side_menu_buttons"):
            return

        for button_index, (button, icon_name) in enumerate(self.side_menu_buttons):
            selected = button_index == index
            button.setChecked(selected)
            button.setIcon(self.side_menu_icon(icon_name, selected=selected))

    def on_side_menu_clicked(self, index: int):
        if self._closing:
            return

        if index < 0 or index >= self.tabs.count():
            return

        self.tabs.setCurrentIndex(index)


    def update_side_menu_style(self):
        if not hasattr(self, "side_menu"):
            return

        preview = getattr(self, "_theme_preview_data", None)
        palette = self.palette()
        button = palette.color(QPalette.ColorRole.Button).name()
        mid = palette.color(QPalette.ColorRole.Mid).name()
        if isinstance(preview, dict):
            roles = custom_theme_roles(preview)
            text = roles["text"]
            accent = roles["accent"]
        else:
            mode = self.config_data.get("theme_mode", "auto")
            text = theme_text_color(mode)
            accent = theme_accent_color(mode)

        self.side_menu.setStyleSheet(
            f"""
            QFrame#SideMenu {{
                background: transparent;
                border: none;
            }}

            QPushButton#SideMenuButton {{
                text-align: left;
                padding: 7px 10px;
                border: 1px solid {mid};
                border-radius: 8px;
                background-color: {button};
                color: {text};
                font-weight: 600;
            }}

            QPushButton#SideMenuButton:hover {{
                border-color: {accent};
            }}

            QPushButton#SideMenuButton:checked {{
                background-color: {accent};
                border-color: {accent};
                color: #ffffff;
            }}
            """
        )

    def apply_menu_style(self):
        """Apply the permanent side-menu navigation layout."""
        if not hasattr(self, "tabs") or not hasattr(self, "side_menu"):
            return

        self.side_menu.setVisible(True)
        self.tabs.tabBar().setVisible(False)
        self.tabs.setStyleSheet(
            """
            QTabWidget::pane {
                top: 0px;
            }
            """
        )

        if hasattr(self, "content_area_layout"):
            self.content_area_layout.setSpacing(8)

        self.update_side_menu_selection(self.tabs.currentIndex())
        self.update_side_menu_style()


    def open_support_dialog(self):
        if self._closing:
            return

        dialog = SupportDialog(self)
        dialog.exec()

    def open_feedback(self):
        if self._closing:
            return

        open_uri(FEEDBACK_URL)

    def apply_default_window_size(self):
        preferred_width = 1240
        preferred_height = 980
        screen_margin = 80

        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(preferred_width, preferred_height)
            return

        available = screen.availableGeometry()

        width = min(
            preferred_width,
            max(self.minimumWidth(), available.width() - screen_margin),
        )
        height = min(
            preferred_height,
            max(self.minimumHeight(), available.height() - screen_margin),
        )

        self.resize(width, height)
        self._center_on_primary_screen()

    def apply_linux_footer_button_sizing(self):
        if platform.system() != "Linux":
            return

        s = make_scaler(self.get_ui_scale_percent())
        footer_buttons = [
            getattr(self, "theme_button", None),
        ]

        for button in footer_buttons:
            if button is None:
                continue
            button.setMinimumWidth(0)
            button.setMaximumWidth(16777215)
            button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            button.setMinimumHeight(s(28))


    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if hasattr(self, "remote_tab"):
                self.remote_tab.handle_window_activation_changed(self.isActiveWindow())

        super().changeEvent(event)

    def eventFilter(self, obj, event):
        if self._closing:
            return super().eventFilter(obj, event)

        if isinstance(obj, QWidget) and obj.window() is self:
            if hasattr(self, "remote_tab") and self.remote_tab.handle_application_key_event(event):
                return True

        return super().eventFilter(obj, event)

    def svg_icon(self, name: str, color: str) -> QIcon:
        path = ASSETS_DIR / f"{name}.svg"
        if not path.exists():
            return QIcon()

        color = str(color or "#8b5cf6").strip()

        try:
            svg = path.read_text(encoding="utf-8")
            svg = svg.replace("currentColor", color)
            svg = re.sub(r"#[0-9a-fA-F]{6}", color, svg)
            data = QByteArray(svg.encode("utf-8"))

            if QSvgRenderer is not None:
                renderer = QSvgRenderer(data)
                if renderer.isValid():
                    pixmap = QPixmap(24, 24)
                    pixmap.fill(Qt.GlobalColor.transparent)

                    painter = QPainter(pixmap)
                    renderer.render(painter)
                    painter.end()

                    if not pixmap.isNull():
                        return QIcon(pixmap)

            pixmap = QPixmap()
            if pixmap.loadFromData(data, "SVG"):
                return QIcon(pixmap)
        except Exception:
            pass

        return QIcon(str(path))

    def tab_icon(self, name: str) -> QIcon:
        preview = getattr(self, "_theme_preview_data", None)
        if isinstance(preview, dict):
            color = custom_theme_roles(preview)["accent"]
        else:
            color = theme_accent_color(self.config_data.get("theme_mode", "auto"))
        return self.svg_icon(name, color)

    def refresh_tab_icons(self):
        if not hasattr(self, "tabs"):
            return

        icon_map = {
            "Flash SD": "flash_sd",
            "MiSTer": "connection",
            "File Manager": "file_manager",
            "MiSTer Settings": "mister_settings",
            "Install Center": "scripts",
            "Tools": "tools",
            "MiSTerZine": "misterzine",
            "Manuals": "manuals",
            "RetroAchievements": "retroachievements",
            "ZapScripts": "zapscripts",
            "ZapScraper": "zapscraper",
            "SaveManager": "savemanager",
            "App Settings": "settings",
        }

        for index in range(self.tabs.count()):
            text = self.tabs.tabText(index)
            icon_name = icon_map.get(text)
            if icon_name:
                self.tabs.setTabIcon(index, self.tab_icon(icon_name))

    def refresh_page_header_icons(self):
        for label in self.findChildren(QLabel):
            icon_name = label.property("tabHeaderIconName")
            if not icon_name:
                continue

            try:
                icon_size = int(label.property("tabHeaderIconSize") or 19)
            except Exception:
                icon_size = 19

            color = label.palette().color(QPalette.ColorRole.WindowText).name()
            label.setPixmap(
                self.svg_icon(str(icon_name), color).pixmap(QSize(icon_size, icon_size))
            )

    def is_online_mode(self) -> bool:
        return self.app_mode == APP_MODE_ONLINE

    def is_offline_mode(self) -> bool:
        return self.app_mode == APP_MODE_OFFLINE

    def get_offline_sd_root(self) -> str:
        if not self.is_offline_sd_loaded():
            return ""
        return self.offline_sd_root

    def get_offline_sd_selection(self) -> str:
        return self.offline_sd_root

    def is_offline_sd_loaded(self) -> bool:
        return bool(self.is_offline_mode() and self.offline_sd_loaded and self.offline_sd_root)

    def load_offline_sd_card(self, path: str = ""):
        if self._closing:
            return

        if path:
            self.set_offline_sd_root(path)

        if not self.offline_sd_root:
            return

        self.app_mode = APP_MODE_OFFLINE
        self.offline_sd_loaded = True
        self.connection_fail_count = 0
        self.apply_app_mode_state()
        self.update_all_tab_states(lightweight=True)
        self.refresh_current_tab(force=True)

    def unload_offline_sd_card(self):
        if self._closing:
            return

        self.offline_sd_loaded = False
        self.apply_app_mode_state()
        self.update_all_tab_states(lightweight=True)
        self.refresh_current_tab(force=True)

    def should_remember_offline_sd_root(self) -> bool:
        return bool(self.config_data.get("remember_offline_sd_root", False))

    def set_remember_offline_sd_root(self, remember: bool):
        self.config_data["remember_offline_sd_root"] = bool(remember)

        if remember:
            self.config_data["offline_sd_root"] = self.offline_sd_root
        else:
            self.config_data["offline_sd_root"] = ""

        save_config(self.config_data)

    def set_offline_sd_root(self, path: str):
        self.offline_sd_root = str(path or "").strip()

        if self.should_remember_offline_sd_root():
            self.config_data["offline_sd_root"] = self.offline_sd_root
        else:
            self.config_data["offline_sd_root"] = ""

        save_config(self.config_data)

    def switch_to_online_mode(self):
        if self._closing:
            return

        if self.app_mode == APP_MODE_ONLINE:
            self.apply_app_mode_state()
            self.update_all_tab_states(lightweight=True)
            self.refresh_current_tab(force=True)
            return

        self.app_mode = APP_MODE_ONLINE
        self.offline_sd_loaded = False
        self.connection_fail_count = 0
        self.offline_sd_root = ""

        try:
            self.connection.mark_disconnected()
        except Exception:
            pass

        self.set_connection_status("Status: Disconnected")
        self.apply_app_mode_state()
        self.update_all_tab_states(lightweight=True)
        self.refresh_current_tab(force=True)

    def switch_to_offline_mode(self, sd_root: str = ""):
        if self._closing:
            return

        if self.connection.is_connected():
            self.disconnect_from_mister()

        if sd_root:
            self.set_offline_sd_root(sd_root)

        self.app_mode = APP_MODE_OFFLINE
        self.offline_sd_loaded = False
        self.connection_fail_count = 0

        self.apply_app_mode_state()
        self.update_all_tab_states(lightweight=True)
        self.refresh_current_tab(force=True)

    def apply_app_mode_state(self):
        if self.is_offline_mode():
            if self.is_offline_sd_loaded() or self.offline_sd_root:
                self.set_connection_status(f"SD Card: {self.offline_sd_root}")
            else:
                self.set_connection_status("SD Card: No SD Card Selected")
        else:
            if not self.connection.is_connected():
                self.set_connection_status("Status: Disconnected")

        if hasattr(self, "side_menu_buttons") and hasattr(self, "tabs"):
            for index, (button, _icon_name) in enumerate(self.side_menu_buttons):
                if index < self.tabs.count() and self.tabs.tabText(index) == "Manuals":
                    button.setEnabled(True)
                    break

        if hasattr(self, "connection_tab") and hasattr(self.connection_tab, "update_mode_state"):
            self.connection_tab.update_mode_state()

    def current_content_widget(self):
        return self.tabs.currentWidget()

    def _stop_worker(self, worker, wait_ms: int = 3000):
        if worker is None:
            return

        try:
            if worker.isRunning():
                worker.wait(wait_ms)
        except Exception:
            pass

    def _saved_window_geometry(self):
        value = self.config_data.get("window_geometry")

        if not isinstance(value, dict):
            return None

        try:
            x = int(value.get("x", 0))
            y = int(value.get("y", 0))
            width = int(value.get("width", 1100))
            height = int(value.get("height", 980))
            maximized = bool(value.get("maximized", False))
        except Exception:
            return None

        if width < self.minimumWidth():
            width = self.minimumWidth()

        if height < self.minimumHeight():
            height = self.minimumHeight()

        return {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "maximized": maximized,
        }

    def _geometry_is_visible_on_any_screen(self, geometry: QRect) -> bool:
        screens = QApplication.screens()

        if not screens:
            return True

        for screen in screens:
            available = screen.availableGeometry()
            if available.intersects(geometry):
                return True

        return False

    def _center_on_primary_screen(self):
        screen = QApplication.primaryScreen()

        if screen is None:
            return

        available = screen.availableGeometry()
        geometry = self.frameGeometry()
        geometry.moveCenter(available.center())
        self.move(geometry.topLeft())

    def restore_window_geometry(self):
        saved = self._saved_window_geometry()

        if not saved:
            self._center_on_primary_screen()
            return

        geometry = QRect(
            saved["x"],
            saved["y"],
            saved["width"],
            saved["height"],
        )

        if self._geometry_is_visible_on_any_screen(geometry):
            self.setGeometry(geometry)
        else:
            self.resize(saved["width"], saved["height"])
            self._center_on_primary_screen()

        if saved.get("maximized"):
            QTimer.singleShot(0, self.showMaximized)


    def save_window_geometry(self):
        try:
            if self.isMinimized():
                return

            maximized = self.isMaximized()

            if maximized:
                geometry = self.normalGeometry()
            else:
                geometry = self.geometry()

            if geometry.width() <= 0 or geometry.height() <= 0:
                return

            current_config = load_config()

            current_config["window_geometry"] = {
                "x": geometry.x(),
                "y": geometry.y(),
                "width": geometry.width(),
                "height": geometry.height(),
                "maximized": maximized,
            }

            self.config_data = current_config
            save_config(current_config)
        except Exception:
            pass

    def closeEvent(self, event):
        if hasattr(self, "device_tab"):
            self.device_tab.shutdown()
        if hasattr(self, "file_manager_tab"):
            self.file_manager_tab.shutdown()
        if hasattr(self, "manuals_tab"):
            self.manuals_tab.shutdown()
        if hasattr(self, "retroachievements_tab"):
            self.retroachievements_tab.shutdown()
        if hasattr(self, "remote_tab"):
            self.remote_tab.shutdown()

        if not self.should_remember_offline_sd_root():
            self.config_data["offline_sd_root"] = ""
            save_config(self.config_data)

        self.save_window_geometry()
        self._closing = True

        try:
            self.app.removeEventFilter(self)
        except Exception:
            pass

        try:
            if hasattr(self, "connection_monitor_timer"):
                self.connection_monitor_timer.stop()
        except Exception:
            pass

        try:
            if hasattr(self, "reboot_reconnect_timer"):
                self.reboot_reconnect_timer.stop()
        except Exception:
            pass

        self._stop_worker(self.connection_check_worker)
        self._stop_worker(self.reboot_reconnect_worker)
        self._stop_worker(self.update_check_worker)

        self.connection_check_worker = None
        self.reboot_reconnect_worker = None
        self.update_check_worker = None

        try:
            if self.connection.is_connected():
                self.connection.disconnect()
            else:
                self.connection.mark_disconnected()
        except Exception:
            try:
                self.connection.mark_disconnected()
            except Exception:
                pass

        super().closeEvent(event)

    def show_setup_notice(self):
        if self._closing:
            return

        if self.config_data.get("hide_setup_notice"):
            return

        dialog = SetupNoticeDialog(self)

        if dialog.exec() == dialog.DialogCode.Accepted:
            if dialog.dont_show_again:
                self.config_data["hide_setup_notice"] = True
                save_config(self.config_data)

    def set_connection_status(self, text: str):
        raw = str(text or "").strip()
        if raw.lower().startswith("status:"):
            raw = raw.split(":", 1)[1].strip()

        if raw.lower().startswith("sd card:"):
            value = raw.split(":", 1)[1].strip() or "No SD Card Selected"
            self.connection_status_title_label.setText("SD Card:")
            self.connection_status_label.setText(value)
            color = "#3498db" if value.lower() != "no sd card selected" else "#e74c3c"
            self.connection_status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        else:
            self.connection_status_title_label.setText("MiSTer:")
            lowered = raw.lower()
            if lowered.startswith("connected"):
                value, color = "Connected", "#2ecc71"
            elif "connecting" in lowered:
                value, color = "Connecting", "#3498db"
            elif "waiting" in lowered:
                value, color = "Waiting", "#3498db"
            elif "rebooting" in lowered:
                value, color = "Rebooting", "#3498db"
            elif "lost" in lowered:
                value, color = "Connection Lost", "#e74c3c"
            else:
                value, color = "Disconnected", "#e74c3c"
            self.connection_status_label.setText(value)
            self.connection_status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

        if hasattr(self, "connection_tab"):
            self.connection_tab.sync_status_from_main_window()

    def update_footer_cloud_status(self):
        if not hasattr(self, "footer_cloud_title_label"):
            return

        try:
            from core.cloud_account import CloudAccountClient
            cloud_client = CloudAccountClient(self.config_data)
            linked = cloud_client.has_session() and bool(cloud_client.linked_device())
        except Exception:
            linked = False
            cloud_client = None

        self.footer_cloud_title_label.setVisible(linked)
        self.footer_cloud_status_label.setVisible(linked)
        if not linked:
            return

        if bool(getattr(self, "cloud_sync_in_progress", False)):
            text, color = "Syncing", "#3498db"
        else:
            try:
                active, _reason = cloud_client.cloud_sync_status()
            except Exception:
                active = False
            text, color = ("Active", "#2ecc71") if active else ("Inactive", "#e74c3c")

        self.footer_cloud_status_label.setText(text)
        self.footer_cloud_status_label.setStyleSheet(f"font-weight: bold; color: {color};")

    def normalize_ui_scale_percent(self, value) -> int:
        try:
            if isinstance(value, str):
                value = value.strip().replace("%", "")
            percent = int(value)
        except Exception:
            percent = DEFAULT_UI_SCALE_PERCENT

        if percent not in UI_SCALE_OPTIONS:
            percent = min(UI_SCALE_OPTIONS, key=lambda option: abs(option - percent))

        return percent

    def get_ui_scale_percent(self) -> int:
        return self.normalize_ui_scale_percent(
            self.config_data.get("ui_scale_percent", DEFAULT_UI_SCALE_PERCENT)
        )

    def refresh_theme(self):
        self._theme_preview_data = None
        mode = self.config_data.get("theme_mode", "auto")
        ui_scale_percent = self.get_ui_scale_percent()
        self.setUpdatesEnabled(False)
        try:
            apply_theme(self.app, mode, ui_scale_percent)
            self.update_side_menu_logo(mode)
            self.update_theme_button_text()
            self.refresh_tab_icons()
            self.refresh_page_header_icons()
            self.refresh_side_menu_icons()
            self.update_side_menu_style()
            current_widget = self.current_content_widget()
            if current_widget is not None and hasattr(current_widget, "refresh_theme"):
                current_widget.refresh_theme()
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def on_ui_scale_changed(self, *_):
        if self._closing:
            return

        percent = self.normalize_ui_scale_percent(self.scale_combo.currentText())

        if self.config_data.get("ui_scale_percent") == percent:
            self.refresh_theme()
            return

        self.config_data["ui_scale_percent"] = percent
        save_config(self.config_data)

        self.refresh_theme()

    def theme_display_name(self, mode: str) -> str:
        mode = str(mode or "auto").strip().lower()
        if mode == "auto":
            return "Auto"
        if mode == "light":
            return "Light"
        if mode == "dark":
            return "Dark"
        if mode.startswith("custom:"):
            try:
                from core.custom_themes import get_custom_theme
                theme = get_custom_theme(mode)
                if theme:
                    return theme.get("name", "Custom Theme")
            except Exception:
                pass
            return "Custom Theme"
        return "Auto"

    def update_theme_button_text(self):
        if not hasattr(self, "theme_button"):
            return

        self.theme_button.setText(f"Theme: {self.theme_display_name(self.config_data.get('theme_mode', 'auto'))}")

    def open_theme_picker(self):
        if self._closing:
            return

        dialog = ThemePickerDialog(self.config_data.get("theme_mode", "auto"), self.config_data, self)
        dialog.theme_applied.connect(self.apply_theme_from_picker)
        dialog.theme_preview_requested.connect(self.preview_theme_from_picker)
        dialog.theme_preview_restore.connect(self.restore_theme_from_picker)
        dialog.exec()

    def preview_theme_from_picker(self, theme: dict):
        if self._closing or not isinstance(theme, dict):
            return
        ui_scale_percent = self.get_ui_scale_percent()
        self.setUpdatesEnabled(False)
        try:
            self._theme_preview_data = dict(theme)
            apply_custom_theme_preview(self.app, theme, ui_scale_percent)
            self.update_side_menu_logo()
            self.refresh_tab_icons()
            self.refresh_page_header_icons()
            self.refresh_side_menu_icons()
            self.update_side_menu_style()
            self.update()
        finally:
            self.setUpdatesEnabled(True)

    def restore_theme_from_picker(self):
        if not self._closing:
            self.refresh_theme()

    def apply_theme_from_picker(self, mode: str):
        if self._closing:
            return

        mode = str(mode or "auto").strip().lower()

        if mode not in {"auto", "light", "dark"} and not mode.startswith("custom:"):
            mode = "auto"

        if self.config_data.get("theme_mode") == mode:
            self.refresh_theme()
            return

        self.config_data["theme_mode"] = mode
        save_config(self.config_data)
        self.refresh_theme()

    def check_for_updates_on_startup(self):
        if self._closing:
            return

        if self.startup_update_check_done:
            return

        self.startup_update_check_done = True

        if not self.config_data.get("check_updates_on_startup", True):
            return

        self.start_update_check(show_no_update=False, show_errors=False)

    def check_for_updates_manual(self):
        if self._closing:
            return

        self.start_update_check(show_no_update=True, show_errors=True)

    def start_update_check(self, show_no_update: bool, show_errors: bool):
        if self._closing:
            return

        if self.update_check_worker is not None and self.update_check_worker.isRunning():
            return

        if self.check_update_button is not None:
            self.check_update_button.setEnabled(False)
            self.check_update_button.setText("Checking...")

        self.update_check_worker = UpdateCheckWorker()
        self.update_check_worker.show_no_update = show_no_update
        self.update_check_worker.show_errors = show_errors
        self.update_check_worker.result.connect(self.on_update_check_result)
        self.update_check_worker.error.connect(self.on_update_check_error)
        self.update_check_worker.finished.connect(self.on_update_check_finished)
        self.update_check_worker.start()

    def on_update_check_result(self, info):
        if self._closing:
            return

        show_no_update = getattr(self.update_check_worker, "show_no_update", True)

        if info.update_available:
            if mc_updater_available():
                while not self._closing:
                    dialog = UpdateAvailableDialog(
                        info,
                        "Run MC-Updater",
                        "Do you want to run MC-Updater now?",
                        self,
                    )
                    dialog.exec()

                    if dialog.selected_action == UpdateAvailableDialog.ACTION_SHOW_CHANGELOG:
                        self.show_update_changelog(info)
                        continue

                    if dialog.selected_action == UpdateAvailableDialog.ACTION_UPDATE:
                        if launch_mc_updater():
                            self.close()
                        else:
                            QMessageBox.warning(
                                self,
                                "Updater Failed",
                                "MC-Updater could not be started.",
                            )

                    break

                return

            while not self._closing:
                dialog = UpdateAvailableDialog(
                    info,
                    "Open Download Page",
                    "Do you want to open the download page?",
                    self,
                )
                dialog.exec()

                if dialog.selected_action == UpdateAvailableDialog.ACTION_SHOW_CHANGELOG:
                    self.show_update_changelog(info)
                    continue

                if dialog.selected_action == UpdateAvailableDialog.ACTION_UPDATE:
                    open_release_page(info.release_url)

                break
        elif show_no_update:
            QMessageBox.information(
                self,
                "No Update Available",
                (
                    "You are already running the latest version.\n\n"
                    f"Current version: {info.current_version}"
                ),
            )

    def show_update_changelog(self, info):
        release_body = getattr(info, "release_body", "") or ""

        if not release_body.strip():
            open_release_page(info.release_url)
            return

        dialog = ChangelogDialog(info.release_name, release_body, self)
        dialog.exec()

    def on_update_check_error(self, message: str):
        if self._closing:
            return

        show_errors = getattr(self.update_check_worker, "show_errors", True)

        if show_errors:
            QMessageBox.warning(
                self,
                "Update Check Failed",
                f"Unable to check for updates.\n\n{message}",
            )

    def on_update_check_finished(self):
        if self._closing:
            return

        if self.check_update_button is not None:
            self.check_update_button.setEnabled(True)
            self.check_update_button.setText("Check for Updates")
        self.update_check_worker = None

    def _managed_tabs(self):
        tabs = []

        for attr_name in (
            "device_tab",
            "remote_tab",
            "file_manager_tab",
            "mister_settings_tab",
            "install_center_tab",
            "tools_tab",
            "misterzine_tab",
            "manuals_tab",
            "retroachievements_tab",
            "zapscripts_tab",
            "zapscraper_tab",
            "savemanager_tab",
            "flash_tab",
            "app_settings_tab",
        ):
            if hasattr(self, attr_name):
                tabs.append(getattr(self, attr_name))

        return tabs

    def _update_tab_connection_state(self, tab, lightweight: bool = True):
        if tab is None:
            return

        if not hasattr(tab, "update_connection_state"):
            return

        try:
            tab.update_connection_state(lightweight=lightweight)
        except TypeError:
            tab.update_connection_state()

    def update_all_tab_states(self, lightweight: bool = True):
        if self._closing:
            return

        for tab in self._managed_tabs():
            self._update_tab_connection_state(tab, lightweight=lightweight)

    def refresh_current_tab(self, force: bool = False):
        if self._closing:
            return

        current_widget = self.current_content_widget()

        self._update_tab_connection_state(current_widget, lightweight=True)

        if hasattr(self, "app_settings_tab") and current_widget is self.app_settings_tab:
            return

        if hasattr(self, "connection_tab") and current_widget is self.connection_tab:
            if self.connection.is_connected() or self.is_offline_sd_loaded():
                self.device_tab.refresh_info()
            return

        if hasattr(self, "misterzine_tab") and current_widget is self.misterzine_tab:
            self.misterzine_tab.refresh(force=force)
            return

        if hasattr(self, "file_manager_tab") and current_widget is self.file_manager_tab:
            # Keep the current folder when switching tabs. File Manager has its
            # own Refresh button for an explicit reload.
            self.file_manager_tab.refresh(force=False)
            return

        if hasattr(self, "manuals_tab") and current_widget is self.manuals_tab:
            # Manuals is session-persistent as a tab. Scan only on first use;
            # cached manuals remain available even when SSH is disconnected.
            self.manuals_tab.refresh(force=False)
            return

        if hasattr(self, "retroachievements_tab") and current_widget is self.retroachievements_tab:
            # Do not reload on tab switches: preserve the exact RA view/state
            # until the application closes.
            self.retroachievements_tab.refresh(force=False)
            return

        if hasattr(self, "remote_tab") and current_widget is self.remote_tab:
            self.remote_tab.refresh(force=force)
            return

        if hasattr(self, "flash_tab") and current_widget is self.flash_tab:
            self.flash_tab.refresh_status(force=force)
            return

        if self.is_offline_mode():
            if hasattr(self, "mister_settings_tab") and current_widget is self.mister_settings_tab:
                self.mister_settings_tab.refresh_tab_contents()
                return

            if hasattr(self, "device_tab") and current_widget is self.device_tab:
                self.device_tab.refresh_info()
                return

            if force:
                if hasattr(self, "install_center_tab") and current_widget is self.install_center_tab:
                    self.install_center_tab.refresh_status()
                    return




                if hasattr(self, "zapscraper_tab") and current_widget is self.zapscraper_tab:
                    self.zapscraper_tab.refresh_status()
                    return

            return

        if not self.connection.is_connected():
            return

        if hasattr(self, "mister_settings_tab") and current_widget is self.mister_settings_tab:
            self.mister_settings_tab.refresh_tab_contents()
            return

        if hasattr(self, "device_tab") and current_widget is self.device_tab:
            self.device_tab.refresh_info()
            return

        if hasattr(self, "install_center_tab") and current_widget is self.install_center_tab:
            self.install_center_tab.refresh_status()
            return


        if hasattr(self, "zapscripts_tab") and current_widget is self.zapscripts_tab:
            self.zapscripts_tab.refresh_status()
            return



    def on_tab_changed(self, index):
        if self._closing:
            return

        self.update_side_menu_selection(index)

        current_widget = self.tabs.widget(index)
        if current_widget is None:
            return

        if hasattr(self, "remote_tab"):
            self.remote_tab.set_tab_active(current_widget is self.remote_tab)

        self._tab_refresh_generation += 1
        generation = self._tab_refresh_generation

        self._update_tab_connection_state(current_widget, lightweight=True)

        if hasattr(current_widget, "show_refreshing_state"):
            current_widget.show_refreshing_state()

        QTimer.singleShot(
            0,
            lambda: self._run_deferred_tab_refresh(generation, current_widget),
        )

    def _run_deferred_tab_refresh(self, generation, expected_widget):
        if self._closing:
            return

        if generation != self._tab_refresh_generation:
            return

        if self.current_content_widget() is not expected_widget:
            return

        self.refresh_current_tab(force=True)

    def check_connection_status(self):
        if self._closing:
            return

        if self.is_offline_mode():
            return

        if not self._connected_session_active:
            return

        if not self.connection.is_connected():
            self.handle_connection_lost()
            return

        if self.reboot_reconnect_timer.isActive():
            return

        if self.connection_check_worker is not None and self.connection_check_worker.isRunning():
            return

        host = self.connection.host
        if not host:
            return

        self.connection_check_worker = ConnectionCheckWorker(host, port=22, timeout=2)
        self.connection_check_worker.result.connect(self.on_connection_check_result)
        self.connection_check_worker.finished.connect(self.on_connection_check_worker_finished)
        self.connection_check_worker.start()

    def on_connection_check_worker_finished(self):
        self.connection_check_worker = None

    def on_connection_check_result(self, ok: bool):
        if self._closing:
            return

        if self.is_offline_mode():
            self.connection_fail_count = 0
            return

        if self.reboot_reconnect_timer.isActive():
            self.connection_fail_count = 0
            return

        if ok:
            self.connection_fail_count = 0
            return

        self.connection_fail_count += 1

        if self.connection_fail_count < self.connection_fail_threshold:
            return

        self.handle_connection_lost()

    def handle_connection_lost(self):
        if self._closing:
            return

        if self.is_offline_mode():
            return

        self.connection_fail_count = 0
        self._connected_session_active = False

        try:
            self.connection.disconnect()
        except Exception:
            self.connection.mark_disconnected()

        self.set_connection_status("Status: Connection Lost")
        self.connection_tab.apply_disconnected_state()
        self.apply_app_mode_state()
        self.update_all_tab_states(lightweight=True)

        QMessageBox.warning(
            self,
            "Connection Lost",
            "Connection to MiSTer was lost.",
        )

    def start_reboot_reconnect_polling(self):
        if self._closing:
            return

        if self.is_offline_mode():
            return

        host = self.connection.host
        username = self.connection.username
        password = self.connection.password

        if not host or not username:
            self.set_connection_status("Status: Disconnected")
            self.connection_tab.apply_disconnected_state()
            self.update_all_tab_states(lightweight=True)
            return

        self.reboot_reconnect_host = host
        self.reboot_reconnect_username = username
        self.reboot_reconnect_password = password
        self.reboot_reconnect_use_ssh_agent = self.config_data.get("use_ssh_agent", False)
        self.reboot_reconnect_look_for_ssh_keys = self.config_data.get("look_for_ssh_keys", False)

        self.connection_fail_count = 0
        self._connected_session_active = False
        self.connection.mark_disconnected()
        self.connection_tab.apply_disconnected_state()
        self.update_all_tab_states(lightweight=True)

        self.reboot_reconnect_attempts = 0
        self.set_connection_status("Status: Rebooting...")
        self.reboot_reconnect_timer.start(5000)

    def try_reconnect_after_reboot(self):
        if self._closing:
            return

        if self.is_offline_mode():
            self.reboot_reconnect_timer.stop()
            return

        if self.reboot_reconnect_worker is not None and self.reboot_reconnect_worker.isRunning():
            return

        host = self.reboot_reconnect_host
        if not host:
            self.reboot_reconnect_timer.stop()
            self.set_connection_status("Status: Disconnected")
            return

        self.set_connection_status("Status: Waiting for MiSTer...")

        self.reboot_reconnect_worker = ConnectionCheckWorker(host, port=22, timeout=2)
        self.reboot_reconnect_worker.result.connect(self.on_reboot_port_check_result)
        self.reboot_reconnect_worker.finished.connect(self.on_reboot_reconnect_worker_finished)
        self.reboot_reconnect_worker.start()

    def on_reboot_reconnect_worker_finished(self):
        self.reboot_reconnect_worker = None

    def on_reboot_port_check_result(self, ok: bool):
        if self._closing:
            return

        if self.is_offline_mode():
            return

        if not ok:
            self.reboot_reconnect_attempts += 1

            if self.reboot_reconnect_attempts >= self.reboot_reconnect_max_attempts:
                self.reboot_reconnect_timer.stop()

                self.set_connection_status("Status: Disconnected")
                QMessageBox.warning(
                    self,
                    "Reconnect Failed",
                    "MiSTer did not come back online in time.",
                )
            return

        host = self.reboot_reconnect_host
        username = self.reboot_reconnect_username
        password = self.reboot_reconnect_password
        use_ssh_agent = self.reboot_reconnect_use_ssh_agent
        look_for_ssh_keys = self.reboot_reconnect_look_for_ssh_keys

        try:
            success = self.connection.connect(
                host,
                username,
                password,
                use_ssh_agent=use_ssh_agent,
                look_for_ssh_keys=look_for_ssh_keys,
            )
        except Exception:
            success = False

        if success:
            self.reboot_reconnect_timer.stop()
            self.reboot_reconnect_attempts = 0
            self.connection_fail_count = 0
            self._connected_session_active = True
            self.reboot_reconnect_host = ""
            self.reboot_reconnect_username = ""
            self.reboot_reconnect_password = ""
            self.reboot_reconnect_use_ssh_agent = False
            self.reboot_reconnect_look_for_ssh_keys = False

            self.set_connection_status(f"Status: Connected to {host}")
            self.connection_tab.apply_connected_state()
            self.apply_app_mode_state()
            self.update_all_tab_states(lightweight=True)
            self.refresh_current_tab(force=True)
        else:
            self.reboot_reconnect_attempts += 1

            if self.reboot_reconnect_attempts >= self.reboot_reconnect_max_attempts:
                self.reboot_reconnect_timer.stop()

                self.set_connection_status("Status: Disconnected")
                QMessageBox.warning(
                    self,
                    "Reconnect Failed",
                    "MiSTer is reachable again, but automatic reconnect failed.",
                )

    def connect_to_mister(self):
        if self._closing:
            return

        if self.is_offline_mode():
            QMessageBox.information(
                self,
                "Offline Mode Active",
                "Switch back to Online Mode before connecting to a MiSTer over SSH.",
            )
            return

        host = self.connection_tab.ip_input.text().strip()
        username = self.connection_tab.user_input.text().strip() or "root"
        password = self.connection_tab.pass_input.text() or "1"
        use_ssh_agent = self.config_data.get("use_ssh_agent", False)
        look_for_ssh_keys = self.config_data.get("look_for_ssh_keys", False)

        if not host:
            QMessageBox.warning(self, "Error", "IP Address is required.")
            return

        self.set_connection_status("Status: Connecting...")

        try:
            success = self.connection.connect(
                host,
                username,
                password,
                use_ssh_agent=use_ssh_agent,
                look_for_ssh_keys=look_for_ssh_keys,
            )
        except Exception as e:
            success = False
            error_message = str(e)
        else:
            error_message = "Unable to connect to MiSTer."

        if not success:
            self._connected_session_active = False
            self.set_connection_status("Status: Disconnected")
            self.connection_tab.apply_disconnected_state()
            self.update_all_tab_states(lightweight=True)
            QMessageBox.warning(self, "Connection Failed", error_message)
            return

        selected_name = self.connection_tab.get_selected_profile_name()
        if selected_name:
            self.config_data["last_connected"] = selected_name
            save_config(self.config_data)

        self._connected_session_active = True
        self.set_connection_status(f"Status: Connected to {host}")
        self.connection_tab.apply_connected_state()
        self.apply_app_mode_state()
        self.update_all_tab_states(lightweight=True)
        self.refresh_current_tab(force=True)

    def disconnect_from_mister(self):
        self._connected_session_active = False

        if hasattr(self, "file_manager_tab"):
            self.file_manager_tab.reset_session(clear_output=False)

        try:
            self.connection.disconnect()
        except Exception:
            self.connection.mark_disconnected()

        self.reboot_reconnect_timer.stop()
        self.reboot_reconnect_attempts = 0
        self.reboot_reconnect_host = ""
        self.reboot_reconnect_username = ""
        self.reboot_reconnect_password = ""
        self.reboot_reconnect_use_ssh_agent = False
        self.reboot_reconnect_look_for_ssh_keys = False

        self.connection_fail_count = 0

        if self.is_offline_mode():
            self.apply_app_mode_state()
        else:
            self.set_connection_status("Status: Disconnected")

        self.apply_app_mode_state()
        self.connection_tab.apply_disconnected_state()
        self.update_all_tab_states(lightweight=True)

    def open_network_scanner(self):
        if self._closing:
            return

        if self.is_offline_mode():
            QMessageBox.information(
                self,
                "Offline Mode Active",
                "Network scanning is only available in Online Mode.",
            )
            return

        dialog = NetworkScannerDialog(self)
        dialog.exec()

    def get_profile_sync_roots(self):
        return get_profile_sync_roots()

    def load_devices(self):
        devices = get_devices(self.config_data)
        self.connection_tab.set_profiles(devices)

    def load_last_device(self):
        last = self.config_data.get("last_connected")
        if not last:
            return

        device = get_device_by_name(self.config_data, last)
        if not device:
            return

        devices = get_devices(self.config_data)

        self.connection_tab.set_connection_fields(
            device.get("ip", ""),
            device.get("username", "root"),
            device.get("password", "1"),
        )
        self.connection_tab.set_profiles(devices, selected_name=last)

    def load_selected_device(self, index):
        if self.is_offline_mode():
            return

        device = get_device_by_index(self.config_data, index)
        if not device:
            return

        self.connection_tab.set_connection_fields(
            device.get("ip", ""),
            device.get("username", "root"),
            device.get("password", "1"),
        )

    def save_device(self):
        if self._closing:
            return

        if self.is_offline_mode():
            QMessageBox.information(
                self,
                "Offline Mode Active",
                "Device profiles are only used in Online Mode.",
            )
            return

        dialog = DeviceDialog(
            self,
            title="Save Device",
            device={
                "name": "",
                "ip": self.connection_tab.ip_input.text().strip(),
                "username": self.connection_tab.user_input.text().strip() or "root",
                "password": self.connection_tab.pass_input.text() or "1",
            },
        )

        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        device = dialog.get_device_data()

        if not device["name"]:
            QMessageBox.warning(self, "Error", "Device name is required.")
            return

        if not device["ip"]:
            QMessageBox.warning(self, "Error", "IP Address is required.")
            return

        ok, result = add_device(self.config_data, device)
        if not ok:
            QMessageBox.warning(self, "Error", result)
            return

        profile_assigned_to_ip(
            self.get_profile_sync_roots(),
            device["ip"],
            device["name"],
        )

        rename_db(device["ip"], device["name"])

        devices = get_devices(self.config_data)
        self.load_devices()
        self.connection_tab.set_profiles(devices, selected_name=device["name"])
        self.connection_tab.set_connection_fields(
            device["ip"],
            device["username"],
            device["password"],
        )
        if hasattr(self, "app_settings_tab"):
            self.app_settings_tab.sync_cloud_profiles_silently()

    def edit_device(self):
        if self._closing:
            return

        if self.is_offline_mode():
            QMessageBox.information(
                self,
                "Offline Mode Active",
                "Device profiles are only used in Online Mode.",
            )
            return

        index = self.connection_tab.profile_selector.currentIndex()
        current_device = get_device_by_index(self.config_data, index)

        if not current_device:
            QMessageBox.warning(self, "Error", "Select a device first.")
            return

        dialog = DeviceDialog(
            self,
            title="Edit Device",
            device=current_device,
        )

        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        updated_device_data = dialog.get_device_data()

        if not updated_device_data["name"]:
            QMessageBox.warning(self, "Error", "Device name is required.")
            return

        if not updated_device_data["ip"]:
            QMessageBox.warning(self, "Error", "IP Address is required.")
            return

        ok, result, _ = update_device(self.config_data, index, updated_device_data)
        if not ok:
            QMessageBox.warning(self, "Error", result)
            return

        old_name = result["old_name"]
        old_ip = result["old_ip"]
        updated_device = result["updated_device"]

        migrate_profile_identity(
            old_name,
            old_ip,
            updated_device["name"],
            updated_device["ip"],
        )

        devices = get_devices(self.config_data)
        self.load_devices()
        self.connection_tab.set_profiles(devices, selected_name=updated_device["name"])
        self.connection_tab.set_connection_fields(
            updated_device["ip"],
            updated_device["username"],
            updated_device["password"],
        )
        if hasattr(self, "app_settings_tab"):
            self.app_settings_tab.sync_cloud_profiles_silently()

    def delete_device(self):
        if self._closing:
            return

        if self.is_offline_mode():
            QMessageBox.information(
                self,
                "Offline Mode Active",
                "Device profiles are only used in Online Mode.",
            )
            return

        index = self.connection_tab.profile_selector.currentIndex()

        ok, result, _ = delete_device(self.config_data, index)
        if not ok:
            QMessageBox.warning(self, "Error", result)
            return

        device_name = result["device_name"]
        device_ip = result["device_ip"]

        if self.config_data.get("last_connected") == device_name:
            self.config_data["last_connected"] = None
            save_config(self.config_data)

        if self.connection.is_connected() and self.connection.host == device_ip:
            self.disconnect_from_mister()

        remove_profile_identity(device_name, device_ip)

        devices = get_devices(self.config_data)
        self.connection_tab.set_profiles(devices)
        self.connection_tab.profile_selector.setCurrentIndex(-1)
        self.connection_tab.set_connection_fields("", "root", "1")
        self.connection_tab.update_connection_state()
        if hasattr(self, "app_settings_tab"):
            self.app_settings_tab.sync_cloud_profiles_silently()
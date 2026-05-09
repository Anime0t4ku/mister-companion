import sys
import webbrowser
from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, QRect, QSize, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QRegion
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

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
from core.profile_folder_sync import profile_assigned_to_ip, profile_removed, profile_renamed
from core.theme import apply_theme, resolve_theme_mode
from core.updater import check_for_update, open_release_page
from core.zaplauncher_db import rename_db
from ui.dialogs.device_dialog import DeviceDialog
from ui.dialogs.network_scanner_dialog import NetworkScannerDialog
from ui.dialogs.retroachievements_dialog import RetroAchievementsDialog
from ui.dialogs.setup_notice_dialog import SetupNoticeDialog
from ui.dialogs.support_dialog import SupportDialog
from ui.tabs.connection_tab import ConnectionTab
from ui.tabs.device_tab import DeviceTab
from ui.tabs.extras_tab import ExtrasTab
from ui.tabs.flash_tab import FlashTab
from ui.tabs.mister_settings_tab import MiSTerSettingsTab
from ui.tabs.savemanager_tab import SaveManagerTab
from ui.tabs.scripts_tab import ScriptsTab
from ui.tabs.wallpapers_tab import WallpapersTab
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


class UpdateCheckWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def run(self):
        try:
            info = check_for_update()
            self.result.emit(info)
        except Exception as e:
            self.error.emit(str(e))


class CustomTitleBar(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.dragging = False
        self.drag_position = QPoint()
        self.logo_pixmap = QPixmap()
        self.logo_mode = ""

        self.setFixedHeight(44)
        self.setObjectName("CustomTitleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 0)
        layout.setSpacing(8)

        self.logo_label = QLabel()
        self.logo_label.setFixedSize(260, 34)
        self.logo_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )

        layout.addWidget(self.logo_label)
        layout.addStretch()

        self.version_label = QLabel(APP_VERSION)
        self.version_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        )
        self.version_label.setMinimumWidth(90)
        self.version_label.setStyleSheet("color: gray; font-weight: bold;")
        layout.addWidget(self.version_label)

        self.minimize_button = QPushButton("−")
        self.maximize_button = QPushButton("□")
        self.close_button = QPushButton("×")

        for button in (
            self.minimize_button,
            self.maximize_button,
            self.close_button,
        ):
            button.setFixedSize(36, 28)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setObjectName("WindowControlButton")

        self.close_button.setObjectName("WindowCloseButton")

        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

        self.minimize_button.clicked.connect(self.main_window.showMinimized)
        self.maximize_button.clicked.connect(self.main_window.toggle_maximize_restore)
        self.close_button.clicked.connect(self.main_window.close)

        self.setStyleSheet(
            """
            QWidget#CustomTitleBar {
                background-color: palette(window);
                border-bottom: 1px solid palette(mid);
            }

            QPushButton#WindowControlButton {
                border: none;
                border-radius: 5px;
                font-size: 15px;
                font-weight: bold;
            }

            QPushButton#WindowControlButton:hover {
                background-color: palette(midlight);
            }

            QPushButton#WindowCloseButton {
                border: none;
                border-radius: 5px;
                font-size: 15px;
                font-weight: bold;
            }

            QPushButton#WindowCloseButton:hover {
                background-color: #d32f2f;
                color: white;
            }
            """
        )

    def set_logo_mode(self, mode: str):
        mode = (mode or "light").strip().lower()

        if mode not in {"light", "dark"}:
            mode = "light"

        if mode == self.logo_mode and not self.logo_pixmap.isNull():
            self.update_logo_pixmap()
            return

        self.logo_mode = mode
        logo_path = LOGO_DARK_PATH if mode == "dark" else LOGO_LIGHT_PATH

        if logo_path.exists():
            self.logo_pixmap = QPixmap(str(logo_path))
        else:
            self.logo_pixmap = QPixmap()

        self.update_logo_pixmap()

    def update_logo_pixmap(self):
        if self.logo_pixmap.isNull():
            self.logo_label.clear()
            return

        scaled = self.logo_pixmap.scaled(
            self.logo_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.logo_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_logo_pixmap()

    def start_native_window_drag(self) -> bool:
        if sys.platform.startswith("win"):
            try:
                import ctypes

                hwnd = int(self.main_window.winId())

                WM_NCLBUTTONDOWN = 0x00A1
                HTCAPTION = 2

                ctypes.windll.user32.ReleaseCapture()
                ctypes.windll.user32.SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)
                return True
            except Exception:
                return False

        window_handle = self.main_window.windowHandle()

        if window_handle is not None:
            try:
                return bool(window_handle.startSystemMove())
            except Exception:
                return False

        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            clicked_widget = self.childAt(event.position().toPoint())

            if clicked_widget in {
                self.minimize_button,
                self.maximize_button,
                self.close_button,
            }:
                super().mousePressEvent(event)
                return

            self.dragging = False
            self.drag_position = QPoint()

            if self.start_native_window_drag():
                event.accept()
                return

            self.dragging = True
            self.drag_position = (
                event.globalPosition().toPoint()
                - self.main_window.frameGeometry().topLeft()
            )
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.main_window.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.dragging = False
        self.drag_position = QPoint()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            clicked_widget = self.childAt(event.position().toPoint())

            if clicked_widget in {
                self.minimize_button,
                self.maximize_button,
                self.close_button,
            }:
                super().mouseDoubleClickEvent(event)
                return

            self.main_window.toggle_maximize_restore()
            event.accept()
            return

        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    RESIZE_MARGIN = 7
    WINDOW_CORNER_RADIUS = 10

    def __init__(self, app):
        super().__init__()

        self.app = app
        self.connection = MiSTerConnection()
        self.config_data = load_config()

        self.app_mode = APP_MODE_ONLINE
        self.offline_sd_root = ""

        self.connection_check_worker = None
        self.connection_fail_count = 0
        self.connection_fail_threshold = 3

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
        self._resizing = False
        self._resize_direction = ""
        self._resize_start_pos = QPoint()
        self._resize_start_geometry = QRect()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setMouseTracking(True)
        self.setMinimumSize(1100, 830)

        self.setWindowTitle(APP_NAME)
        self.apply_default_window_size()
        self.restore_window_geometry()
        QTimer.singleShot(0, self.enable_windows_snap_styles)

        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        central_widget = QWidget()
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self)
        root_layout.addWidget(self.title_bar)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(6)
        root_layout.addWidget(content_widget, 1)

        self.tabs = QTabWidget()
        self.tabs.setIconSize(TAB_ICON_SIZE)
        content_layout.addWidget(self.tabs)

        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 0, 0, 0)
        bottom_bar.setSpacing(8)

        self.connection_status_label = QLabel("Status: Disconnected")
        bottom_bar.addWidget(self.connection_status_label)

        bottom_bar.addStretch()

        self.check_update_button = QPushButton("Check for Updates")
        self.check_update_button.clicked.connect(self.check_for_updates_manual)
        bottom_bar.addWidget(self.check_update_button)

        self.support_button = QPushButton("Support")
        self.support_button.clicked.connect(self.open_support_dialog)
        bottom_bar.addWidget(self.support_button)

        self.feedback_button = QPushButton("Feedback")
        self.feedback_button.clicked.connect(self.open_feedback)
        bottom_bar.addWidget(self.feedback_button)

        self.retroachievements_button = QPushButton("RetroAchievements")
        self.retroachievements_button.clicked.connect(self.open_retroachievements)
        bottom_bar.addWidget(self.retroachievements_button)

        self.scale_combo = QComboBox()
        self.scale_combo.setToolTip("UI Scale")
        self.scale_combo.addItems([f"{value}%" for value in UI_SCALE_OPTIONS])
        self.scale_combo.setMinimumWidth(78)
        bottom_bar.addWidget(self.scale_combo)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Auto", "Light", "Dark"])
        bottom_bar.addWidget(self.theme_combo)

        content_layout.addLayout(bottom_bar)

        self.setCentralWidget(central_widget)
        self.app.installEventFilter(self)

        self.set_connection_status("Status: Disconnected")

        saved_theme = self.config_data.get("theme_mode", "auto").lower()

        if saved_theme == "purple":
            saved_theme = "dark"
            self.config_data["theme_mode"] = saved_theme
            save_config(self.config_data)

        if saved_theme not in {"auto", "light", "dark"}:
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

        theme_index_map = {"auto": 0, "light": 1, "dark": 2}
        self.theme_combo.setCurrentIndex(theme_index_map.get(saved_theme, 0))
        self.scale_combo.currentIndexChanged.connect(self.on_ui_scale_changed)
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        self.refresh_theme()

        self.flash_tab = FlashTab(self)
        self.tabs.addTab(self.flash_tab, self.tab_icon("flash_sd"), "Flash SD")

        self.connection_tab = ConnectionTab(self)
        self.tabs.addTab(self.connection_tab, self.tab_icon("connection"), "Connection")

        self.device_tab = DeviceTab(self)
        self.tabs.addTab(self.device_tab, self.tab_icon("device"), "Device")

        self.mister_settings_tab = MiSTerSettingsTab(self)
        self.tabs.addTab(
            self.mister_settings_tab,
            self.tab_icon("mister_settings"),
            "MiSTer Settings",
        )

        self.scripts_tab = ScriptsTab(self)
        self.tabs.addTab(self.scripts_tab, self.tab_icon("scripts"), "Scripts")

        self.zapscripts_tab = ZapScriptsTab(self)
        self.tabs.addTab(self.zapscripts_tab, self.tab_icon("zapscripts"), "ZapScripts")

        self.savemanager_tab = SaveManagerTab(self)
        self.tabs.addTab(
            self.savemanager_tab,
            self.tab_icon("savemanager"),
            "SaveManager",
        )

        self.wallpapers_tab = WallpapersTab(self)
        self.tabs.addTab(
            self.wallpapers_tab,
            self.tab_icon("wallpapers"),
            "Wallpapers",
        )

        self.extras_tab = ExtrasTab(self)
        self.tabs.addTab(self.extras_tab, self.tab_icon("extras"), "Extras")

        self.tabs.setCurrentWidget(self.connection_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.load_devices()
        self.load_last_device()

        self.connection_monitor_timer = QTimer(self)
        self.connection_monitor_timer.timeout.connect(self.check_connection_status)
        self.connection_monitor_timer.start(5000)

        self.reboot_reconnect_timer = QTimer(self)
        self.reboot_reconnect_timer.timeout.connect(self.try_reconnect_after_reboot)

        self.apply_app_mode_state()
        self.update_all_tab_states(lightweight=True)

        QTimer.singleShot(0, self.apply_window_corner_radius)
        QTimer.singleShot(300, self.show_setup_notice)
        QTimer.singleShot(1500, self.check_for_updates_on_startup)

    def open_retroachievements(self):
        if self._closing:
            return

        dialog = RetroAchievementsDialog(self)
        dialog.exec()

    def open_support_dialog(self):
        if self._closing:
            return

        dialog = SupportDialog(self)
        dialog.exec()

    def open_feedback(self):
        if self._closing:
            return

        webbrowser.open(FEEDBACK_URL)

    def apply_default_window_size(self):
        preferred_width = 1100
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

    def enable_windows_snap_styles(self):
        if not sys.platform.startswith("win"):
            return

        try:
            import ctypes

            hwnd = int(self.winId())

            GWL_STYLE = -16
            WS_THICKFRAME = 0x00040000
            WS_SYSMENU = 0x00080000
            WS_MINIMIZEBOX = 0x00020000
            WS_MAXIMIZEBOX = 0x00010000

            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020

            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            style |= WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
            user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            user32.SetWindowPos(
                hwnd,
                0,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )

            self.apply_windows_native_corner_radius()
        except Exception:
            pass

    def update_title_bar_logo(self, mode: str = ""):
        if not hasattr(self, "title_bar"):
            return

        if not mode:
            mode = self.config_data.get("theme_mode", "auto")

        resolved_mode = resolve_theme_mode(mode)
        self.title_bar.set_logo_mode(resolved_mode)

    def apply_windows_native_corner_radius(self):
        if not sys.platform.startswith("win"):
            return

        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(self.winId())

            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_DEFAULT = 0
            DWMWCP_DONOTROUND = 1
            DWMWCP_ROUND = 2
            DWMWCP_ROUNDSMALL = 3

            preference = ctypes.c_int(DWMWCP_ROUND)

            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(DWMWA_WINDOW_CORNER_PREFERENCE),
                ctypes.byref(preference),
                ctypes.sizeof(preference),
            )
        except Exception:
            pass

    def apply_window_corner_radius(self):
        if sys.platform.startswith("win"):
            self.clearMask()
            self.apply_windows_native_corner_radius()
            return

        if self.isMaximized() or self.isFullScreen():
            self.clearMask()
            return

        rect = self.rect()
        radius = self.WINDOW_CORNER_RADIUS
        diameter = radius * 2

        if rect.width() <= diameter or rect.height() <= diameter:
            self.clearMask()
            return

        rounded = QRegion(QRect(radius, 0, rect.width() - diameter, rect.height()))
        rounded = rounded.united(
            QRegion(QRect(0, radius, rect.width(), rect.height() - diameter))
        )
        rounded = rounded.united(
            QRegion(QRect(0, 0, diameter, diameter), QRegion.RegionType.Ellipse)
        )
        rounded = rounded.united(
            QRegion(
                QRect(rect.width() - diameter, 0, diameter, diameter),
                QRegion.RegionType.Ellipse,
            )
        )
        rounded = rounded.united(
            QRegion(
                QRect(0, rect.height() - diameter, diameter, diameter),
                QRegion.RegionType.Ellipse,
            )
        )
        rounded = rounded.united(
            QRegion(
                QRect(
                    rect.width() - diameter,
                    rect.height() - diameter,
                    diameter,
                    diameter,
                ),
                QRegion.RegionType.Ellipse,
            )
        )

        self.setMask(rounded)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.apply_window_corner_radius()

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_window_corner_radius()

    def toggle_maximize_restore(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

        self.update_maximize_button()
        QTimer.singleShot(0, self.apply_window_corner_radius)

    def update_maximize_button(self):
        if hasattr(self, "title_bar"):
            self.title_bar.maximize_button.setText("❐" if self.isMaximized() else "□")

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            self.update_maximize_button()
            QTimer.singleShot(0, self.apply_window_corner_radius)

        super().changeEvent(event)

    def _widget_belongs_to_window(self, obj):
        return isinstance(obj, QWidget) and obj.window() is self

    def _resize_hit_test(self, global_pos: QPoint) -> str:
        if self.isMaximized() or self.isFullScreen():
            return ""

        geometry = self.frameGeometry()
        margin = self.RESIZE_MARGIN

        left = abs(global_pos.x() - geometry.left()) <= margin
        right = abs(global_pos.x() - geometry.right()) <= margin
        top = abs(global_pos.y() - geometry.top()) <= margin
        bottom = abs(global_pos.y() - geometry.bottom()) <= margin

        if top and left:
            return "top_left"
        if top and right:
            return "top_right"
        if bottom and left:
            return "bottom_left"
        if bottom and right:
            return "bottom_right"
        if left:
            return "left"
        if right:
            return "right"
        if top:
            return "top"
        if bottom:
            return "bottom"

        return ""

    def _cursor_for_resize_direction(self, direction: str):
        if direction in {"left", "right"}:
            return Qt.CursorShape.SizeHorCursor

        if direction in {"top", "bottom"}:
            return Qt.CursorShape.SizeVerCursor

        if direction in {"top_left", "bottom_right"}:
            return Qt.CursorShape.SizeFDiagCursor

        if direction in {"top_right", "bottom_left"}:
            return Qt.CursorShape.SizeBDiagCursor

        return Qt.CursorShape.ArrowCursor

    def _apply_resize(self, global_pos: QPoint):
        if not self._resizing or not self._resize_direction:
            return

        delta = global_pos - self._resize_start_pos
        geometry = QRect(self._resize_start_geometry)

        minimum_width = self.minimumWidth()
        minimum_height = self.minimumHeight()

        if "left" in self._resize_direction:
            new_left = geometry.left() + delta.x()
            max_left = geometry.right() - minimum_width
            geometry.setLeft(min(new_left, max_left))

        if "right" in self._resize_direction:
            new_right = geometry.right() + delta.x()
            min_right = geometry.left() + minimum_width
            geometry.setRight(max(new_right, min_right))

        if "top" in self._resize_direction:
            new_top = geometry.top() + delta.y()
            max_top = geometry.bottom() - minimum_height
            geometry.setTop(min(new_top, max_top))

        if "bottom" in self._resize_direction:
            new_bottom = geometry.bottom() + delta.y()
            min_bottom = geometry.top() + minimum_height
            geometry.setBottom(max(new_bottom, min_bottom))

        self.setGeometry(geometry)
        self.apply_window_corner_radius()

    def eventFilter(self, obj, event):
        if self._closing:
            return super().eventFilter(obj, event)

        if not self._widget_belongs_to_window(obj):
            return super().eventFilter(obj, event)

        event_type = event.type()

        if event_type == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                global_pos = event.globalPosition().toPoint()
                direction = self._resize_hit_test(global_pos)

                if direction:
                    self._resizing = True
                    self._resize_direction = direction
                    self._resize_start_pos = global_pos
                    self._resize_start_geometry = self.frameGeometry()
                    self.setCursor(self._cursor_for_resize_direction(direction))
                    event.accept()
                    return True

        elif event_type == QEvent.Type.MouseMove:
            global_pos = event.globalPosition().toPoint()

            if self._resizing:
                self._apply_resize(global_pos)
                event.accept()
                return True

            direction = self._resize_hit_test(global_pos)

            if direction:
                self.setCursor(self._cursor_for_resize_direction(direction))
            else:
                self.unsetCursor()

        elif event_type == QEvent.Type.MouseButtonRelease:
            if self._resizing:
                self._resizing = False
                self._resize_direction = ""
                self.unsetCursor()
                self.apply_window_corner_radius()
                event.accept()
                return True

        return super().eventFilter(obj, event)

    def tab_icon(self, name: str) -> QIcon:
        path = ASSETS_DIR / f"{name}.svg"
        if path.exists():
            return QIcon(str(path))
        return QIcon()

    def is_online_mode(self) -> bool:
        return self.app_mode == APP_MODE_ONLINE

    def is_offline_mode(self) -> bool:
        return self.app_mode == APP_MODE_OFFLINE

    def get_offline_sd_root(self) -> str:
        return self.offline_sd_root

    def set_offline_sd_root(self, path: str):
        self.offline_sd_root = str(path or "").strip()

    def switch_to_online_mode(self):
        if self._closing:
            return

        if self.app_mode == APP_MODE_ONLINE:
            self.apply_app_mode_state()
            self.update_all_tab_states(lightweight=True)
            self.refresh_current_tab(force=True)
            return

        self.app_mode = APP_MODE_ONLINE
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
        self.connection_fail_count = 0

        self.apply_app_mode_state()
        self.update_all_tab_states(lightweight=True)
        self.refresh_current_tab(force=True)

    def apply_app_mode_state(self):
        if self.is_offline_mode():
            if self.offline_sd_root:
                self.set_connection_status(
                    f"Status: Offline Mode, SD Card: {self.offline_sd_root}"
                )
            else:
                self.set_connection_status("Status: Offline Mode, No SD Card Selected")
        else:
            if not self.connection.is_connected():
                self.set_connection_status("Status: Disconnected")

        if hasattr(self, "connection_tab") and hasattr(self.connection_tab, "update_mode_state"):
            self.connection_tab.update_mode_state()

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

        QTimer.singleShot(0, self.update_maximize_button)
        QTimer.singleShot(0, self.apply_window_corner_radius)

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

            self.config_data["window_geometry"] = {
                "x": geometry.x(),
                "y": geometry.y(),
                "width": geometry.width(),
                "height": geometry.height(),
                "maximized": maximized,
            }

            save_config(self.config_data)
        except Exception:
            pass

    def closeEvent(self, event):
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
        self.connection_status_label.setText(text)

        if "Offline Mode" in text:
            self.connection_status_label.setStyleSheet(
                "color: #8b5cf6; font-weight: bold;"
            )
        elif "Connected" in text:
            self.connection_status_label.setStyleSheet(
                "color: #2ecc71; font-weight: bold;"
            )
        elif "Disconnected" in text:
            self.connection_status_label.setStyleSheet(
                "color: #e74c3c; font-weight: bold;"
            )
        elif "Connecting" in text:
            self.connection_status_label.setStyleSheet(
                "color: #f39c12; font-weight: bold;"
            )
        elif "Lost" in text:
            self.connection_status_label.setStyleSheet(
                "color: #f39c12; font-weight: bold;"
            )
        elif "Rebooting" in text:
            self.connection_status_label.setStyleSheet(
                "color: #f39c12; font-weight: bold;"
            )
        elif "Waiting" in text:
            self.connection_status_label.setStyleSheet(
                "color: #f39c12; font-weight: bold;"
            )
        else:
            self.connection_status_label.setStyleSheet("font-weight: bold;")

        if hasattr(self, "connection_tab"):
            self.connection_tab.sync_status_from_main_window()

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
        mode = self.config_data.get("theme_mode", "auto")
        ui_scale_percent = self.get_ui_scale_percent()
        apply_theme(self.app, mode, ui_scale_percent)
        self.update_title_bar_logo(mode)

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

    def on_theme_changed(self, *_):
        if self._closing:
            return

        mode = self.theme_combo.currentText().lower()

        if mode not in {"auto", "light", "dark"}:
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
            reply = QMessageBox.question(
                self,
                "Update Available",
                (
                    f"A new version of MiSTer Companion is available.\n\n"
                    f"Current version: {info.current_version}\n"
                    f"Latest version: {info.latest_version}\n\n"
                    f"Do you want to open the download page?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if reply == QMessageBox.StandardButton.Yes:
                open_release_page(info.release_url)
        elif show_no_update:
            QMessageBox.information(
                self,
                "No Update Available",
                (
                    "You are already running the latest version.\n\n"
                    f"Current version: {info.current_version}"
                ),
            )

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

        self.check_update_button.setEnabled(True)
        self.check_update_button.setText("Check for Updates")
        self.update_check_worker = None

    def _managed_tabs(self):
        tabs = []

        for attr_name in (
            "device_tab",
            "mister_settings_tab",
            "scripts_tab",
            "extras_tab",
            "zapscripts_tab",
            "savemanager_tab",
            "wallpapers_tab",
            "flash_tab",
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

        current_widget = self.tabs.currentWidget()

        self._update_tab_connection_state(current_widget, lightweight=True)

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
                if hasattr(self, "scripts_tab") and current_widget is self.scripts_tab:
                    self.scripts_tab.refresh_status()
                    return

                if hasattr(self, "extras_tab") and current_widget is self.extras_tab:
                    self.extras_tab.refresh_status()
                    return

                if hasattr(self, "wallpapers_tab") and current_widget is self.wallpapers_tab:
                    self.wallpapers_tab.refresh_status()
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

        if hasattr(self, "scripts_tab") and current_widget is self.scripts_tab:
            self.scripts_tab.refresh_status()
            return

        if hasattr(self, "zapscripts_tab") and current_widget is self.zapscripts_tab:
            self.zapscripts_tab.refresh_status()
            return

        if hasattr(self, "extras_tab") and current_widget is self.extras_tab:
            self.extras_tab.refresh_status()
            return

        if hasattr(self, "wallpapers_tab") and current_widget is self.wallpapers_tab:
            self.wallpapers_tab.refresh_status()
            return

    def on_tab_changed(self, index):
        if self._closing:
            return

        current_widget = self.tabs.widget(index)
        if current_widget is None:
            return

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

        if self.tabs.currentWidget() is not expected_widget:
            return

        self.refresh_current_tab(force=True)

    def check_connection_status(self):
        if self._closing:
            return

        if self.is_offline_mode():
            return

        if not self.connection.is_connected():
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

        try:
            self.connection.disconnect()
        except Exception:
            self.connection.mark_disconnected()

        self.set_connection_status("Status: Connection Lost")
        self.connection_tab.apply_disconnected_state()
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

                if hasattr(self, "scripts_tab"):
                    self.scripts_tab.waiting_for_reboot_reconnect = False

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
            self.reboot_reconnect_host = ""
            self.reboot_reconnect_username = ""
            self.reboot_reconnect_password = ""
            self.reboot_reconnect_use_ssh_agent = False
            self.reboot_reconnect_look_for_ssh_keys = False

            if hasattr(self, "scripts_tab"):
                self.scripts_tab.waiting_for_reboot_reconnect = False

            self.set_connection_status(f"Status: Connected to {host}")
            self.connection_tab.apply_connected_state()
            self.update_all_tab_states(lightweight=True)
            self.refresh_current_tab(force=True)
        else:
            self.reboot_reconnect_attempts += 1

            if self.reboot_reconnect_attempts >= self.reboot_reconnect_max_attempts:
                self.reboot_reconnect_timer.stop()

                if hasattr(self, "scripts_tab"):
                    self.scripts_tab.waiting_for_reboot_reconnect = False

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
            self.set_connection_status("Status: Disconnected")
            self.connection_tab.apply_disconnected_state()
            self.update_all_tab_states(lightweight=True)
            QMessageBox.warning(self, "Connection Failed", error_message)
            return

        selected_name = self.connection_tab.get_selected_profile_name()
        if selected_name:
            self.config_data["last_connected"] = selected_name
            save_config(self.config_data)

        self.set_connection_status(f"Status: Connected to {host}")
        self.connection_tab.apply_connected_state()
        self.update_all_tab_states(lightweight=True)
        self.refresh_current_tab(force=True)

    def disconnect_from_mister(self):
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

        if hasattr(self, "scripts_tab"):
            self.scripts_tab.waiting_for_reboot_reconnect = False

        self.connection_fail_count = 0

        if self.is_offline_mode():
            self.apply_app_mode_state()
        else:
            self.set_connection_status("Status: Disconnected")

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

        if old_name != updated_device["name"]:
            profile_renamed(
                self.get_profile_sync_roots(),
                old_name,
                updated_device["name"],
            )
            rename_db(old_name, updated_device["name"])

        elif old_ip != updated_device["ip"]:
            profile_assigned_to_ip(
                self.get_profile_sync_roots(),
                updated_device["ip"],
                updated_device["name"],
            )
            rename_db(old_ip, updated_device["name"])

        devices = get_devices(self.config_data)
        self.load_devices()
        self.connection_tab.set_profiles(devices, selected_name=updated_device["name"])
        self.connection_tab.set_connection_fields(
            updated_device["ip"],
            updated_device["username"],
            updated_device["password"],
        )

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

        profile_removed(
            self.get_profile_sync_roots(),
            device_name,
            device_ip,
        )

        rename_db(device_name, device_ip)

        devices = get_devices(self.config_data)
        self.connection_tab.set_profiles(devices)
        self.connection_tab.profile_selector.setCurrentIndex(-1)
        self.connection_tab.set_connection_fields("", "root", "1")
        self.connection_tab.update_connection_state()
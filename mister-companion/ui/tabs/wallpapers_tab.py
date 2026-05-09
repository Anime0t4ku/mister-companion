import traceback
from pathlib import Path

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.scripts_actions import get_scripts_status, remove_static_wallpaper
from core.scripts_static_wallpaper import (
    get_static_wallpaper_state_local,
    remove_static_wallpaper_local,
)
from core.wallpapers import (
    build_install_state,
    fetch_ot4ku_wallpapers,
    fetch_pcn_premium_wallpapers,
    fetch_pcn_wallpapers,
    fetch_ranny_wallpapers,
    get_installed_wallpapers,
    get_installed_wallpapers_local,
    install_wallpaper_items,
    install_wallpaper_items_local,
    open_wallpaper_folder_local,
    open_wallpaper_folder_on_host,
    remove_installed_wallpapers,
    remove_installed_wallpapers_local,
    wallpaper_folder_exists,
)
from ui.dialogs.static_wallpaper_dialog import StaticWallpaperDialog


class WallpaperTaskWorker(QThread):
    log_line = pyqtSignal(str)
    success = pyqtSignal(str)
    error = pyqtSignal(str)
    finished_task = pyqtSignal()

    def __init__(self, task_fn, success_message=""):
        super().__init__()
        self.task_fn = task_fn
        self.success_message = success_message

    def emit_log(self, text: str):
        self.log_line.emit(text)

    def run(self):
        try:
            self.task_fn(self.emit_log)

            if self.success_message:
                self.success.emit(self.success_message)

        except Exception as e:
            detail = traceback.format_exc()
            self.error.emit(f"{str(e)}\n\n{detail}")
        finally:
            self.finished_task.emit()


class WallpaperStatusWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, connection=None, offline=False, sd_root=None):
        super().__init__()
        self.connection = connection
        self.offline = bool(offline)
        self.sd_root = Path(sd_root) if sd_root else None

    def run(self):
        try:
            if self.offline:
                if not self.sd_root or not self.sd_root.exists():
                    raise RuntimeError("Select an Offline SD Card folder first.")

                state = get_static_wallpaper_state_local(self.sd_root)
                static_wallpaper_active = bool(state.get("active"))
                installed = get_installed_wallpapers_local(self.sd_root)
                folder_available = True
            else:
                if self.connection is None or not self.connection.is_connected():
                    raise RuntimeError("Connect to a MiSTer first.")

                try:
                    script_status = get_scripts_status(self.connection)
                    static_wallpaper_active = bool(script_status.static_wallpaper_active)
                except Exception:
                    static_wallpaper_active = False

                installed = get_installed_wallpapers(self.connection)
                folder_available = wallpaper_folder_exists(self.connection)

            gh_169, gh_43 = fetch_ranny_wallpapers()
            pcn_items = fetch_pcn_wallpapers()
            pcn_premium_items = fetch_pcn_premium_wallpapers()
            ot4ku_items = fetch_ot4ku_wallpapers()

            installed_169, missing_169 = build_install_state(gh_169, installed)
            installed_43, missing_43 = build_install_state(gh_43, installed)
            pcn_installed, pcn_missing = build_install_state(pcn_items, installed)
            pcn_premium_installed, pcn_premium_missing = build_install_state(
                pcn_premium_items,
                installed,
            )
            ot4ku_installed, ot4ku_missing = build_install_state(ot4ku_items, installed)

            self.result.emit(
                {
                    "static_wallpaper_active": static_wallpaper_active,
                    "folder_available": folder_available,
                    "ranny_169_installed": installed_169,
                    "ranny_169_missing": missing_169,
                    "ranny_43_installed": installed_43,
                    "ranny_43_missing": missing_43,
                    "pcn_installed": pcn_installed,
                    "pcn_missing": pcn_missing,
                    "pcn_premium_installed": pcn_premium_installed,
                    "pcn_premium_missing": pcn_premium_missing,
                    "ot4ku_installed": ot4ku_installed,
                    "ot4ku_missing": ot4ku_missing,
                }
            )
        except Exception as e:
            detail = traceback.format_exc()
            self.error.emit(f"{str(e)}\n\n{detail}")


class WallpapersTab(QWidget):
    WALLPAPER_RANNY = "ranny_snice"
    WALLPAPER_PCN = "pcn_challenge"
    WALLPAPER_PCN_PREMIUM = "pcn_premium"
    WALLPAPER_OT4KU = "anime0t4ku"

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection

        self.console_visible = False
        self.current_worker = None
        self.status_worker = None

        self.wallpaper_display_order = [
            self.WALLPAPER_RANNY,
            self.WALLPAPER_PCN,
            self.WALLPAPER_PCN_PREMIUM,
            self.WALLPAPER_OT4KU,
        ]

        self.wallpaper_titles = {
            self.WALLPAPER_RANNY: "Ranny Snice Wallpapers",
            self.WALLPAPER_PCN: "PCN Challenge Wallpapers",
            self.WALLPAPER_PCN_PREMIUM: "PCN Premium Member Wallpapers",
            self.WALLPAPER_OT4KU: "Anime0t4ku Wallpapers",
        }

        self.wallpaper_descriptions = {
            self.WALLPAPER_RANNY: (
                "A collection of MiSTer menu wallpapers by Ranny Snice, available in "
                "both 16:9 and 4:3 versions. Use the matching pack for your display "
                "setup, or install both if you switch between aspect ratios."
            ),
            self.WALLPAPER_PCN: (
                "Wallpapers created during PCN livestreams based on audience requests. "
                "These are made under time limits and sometimes with extra challenge "
                "conditions, giving each wallpaper its own unique style and context."
            ),
            self.WALLPAPER_PCN_PREMIUM: (
                "A wallpaper pack created for PCN Premium members on YouTube and Patreon. "
                "These wallpapers are made as exclusive extras for PCN supporters."
            ),
            self.WALLPAPER_OT4KU: (
                "A personal wallpaper pack by Anime0t4ku, made without fixed constraints. "
                "Themes can vary across anime, movies, games, systems, comics, and more."
            ),
        }

        self.selected_wallpaper_key = self.WALLPAPER_RANNY

        self.build_ui()
        self.apply_disconnected_state()

    def build_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        self.setLayout(main_layout)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        main_layout.addLayout(top_row, stretch=1)

        left_column = QVBoxLayout()
        left_column.setSpacing(12)
        top_row.addLayout(left_column, 1)

        static_group = QGroupBox("Static Wallpapers")
        static_layout = QVBoxLayout()
        static_layout.setContentsMargins(14, 14, 14, 14)
        static_layout.setSpacing(10)

        static_info_label = QLabel(
            "Choose one installed wallpaper as the active MiSTer menu background, "
            "or remove the currently active static wallpaper."
        )
        static_info_label.setWordWrap(True)
        static_layout.addWidget(static_info_label)

        static_buttons_row = QVBoxLayout()
        static_buttons_row.setSpacing(8)

        self.set_static_wallpaper_button = QPushButton("Set Static Wallpaper")
        self.set_static_wallpaper_button.setMinimumHeight(32)

        self.remove_static_wallpaper_button = QPushButton("Remove Static Wallpaper")
        self.remove_static_wallpaper_button.setMinimumHeight(32)

        static_buttons_row.addWidget(self.set_static_wallpaper_button)
        static_buttons_row.addWidget(self.remove_static_wallpaper_button)

        static_layout.addLayout(static_buttons_row)
        static_group.setLayout(static_layout)
        left_column.addWidget(static_group)

        list_group = QGroupBox("Wallpaper Sources")
        list_layout = QVBoxLayout()
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)

        self.wallpaper_list = QListWidget()
        self.wallpaper_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.wallpaper_list.setAlternatingRowColors(False)
        self.wallpaper_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.wallpaper_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.wallpaper_list.setMinimumWidth(290)
        self.wallpaper_list.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        self.wallpaper_list.setStyleSheet(
            """
            QListWidget {
                border: 1px solid palette(mid);
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget::item {
                border-radius: 6px;
                padding: 8px 10px;
                margin: 2px 0px;
            }
            QListWidget::item:selected {
                background-color: palette(highlight);
                color: palette(highlighted-text);
                border-left: 4px solid #7c4dff;
            }
            """
        )
        list_layout.addWidget(self.wallpaper_list)

        list_group.setLayout(list_layout)
        left_column.addWidget(list_group, 1)

        details_group = QGroupBox("Details")
        details_layout = QVBoxLayout()
        details_layout.setContentsMargins(14, 14, 14, 14)
        details_layout.setSpacing(10)

        self.wallpaper_name_label = QLabel("Select a wallpaper source")
        font = self.wallpaper_name_label.font()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        self.wallpaper_name_label.setFont(font)
        details_layout.addWidget(self.wallpaper_name_label)

        self.wallpaper_status_label = QLabel("")
        self.wallpaper_status_label.setStyleSheet("color: #1e88e5; font-weight: bold;")
        self.wallpaper_status_label.hide()
        details_layout.addWidget(self.wallpaper_status_label)

        self.wallpaper_description_label = QLabel("")
        self.wallpaper_description_label.setWordWrap(True)
        self.wallpaper_description_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.wallpaper_description_label.setMinimumHeight(70)
        details_layout.addWidget(self.wallpaper_description_label)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        details_layout.addWidget(divider)

        self.action_buttons_container = QWidget()
        self.action_buttons_layout = QVBoxLayout()
        self.action_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.action_buttons_layout.setSpacing(10)
        self.action_buttons_container.setLayout(self.action_buttons_layout)
        details_layout.addWidget(self.action_buttons_container)

        self.ranny_actions_widget = self._build_ranny_actions()
        self.pcn_actions_widget = self._build_pcn_actions()
        self.pcn_premium_actions_widget = self._build_pcn_premium_actions()
        self.ot4ku_actions_widget = self._build_ot4ku_actions()

        self.wallpaper_action_widgets = {
            self.WALLPAPER_RANNY: self.ranny_actions_widget,
            self.WALLPAPER_PCN: self.pcn_actions_widget,
            self.WALLPAPER_PCN_PREMIUM: self.pcn_premium_actions_widget,
            self.WALLPAPER_OT4KU: self.ot4ku_actions_widget,
        }

        for widget in self.wallpaper_action_widgets.values():
            widget.hide()
            self.action_buttons_layout.addWidget(widget)

        self.action_buttons_layout.addStretch()

        details_group.setLayout(details_layout)
        top_row.addWidget(details_group, 2)

        bottom_actions_row = QHBoxLayout()
        bottom_actions_row.addStretch()

        self.open_wallpaper_folder_button = QPushButton("Open Wallpaper Folder")
        self.open_wallpaper_folder_button.setFixedWidth(190)

        bottom_actions_row.addWidget(self.open_wallpaper_folder_button)
        bottom_actions_row.addStretch()
        main_layout.addLayout(bottom_actions_row)

        self.console_group = QGroupBox("Output")
        console_layout = QVBoxLayout()
        console_layout.setContentsMargins(10, 10, 10, 10)
        console_layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.addStretch()

        self.hide_console_button = QPushButton("Hide")
        self.hide_console_button.setFixedWidth(70)
        header_row.addWidget(self.hide_console_button)

        console_layout.addLayout(header_row)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(230)
        console_layout.addWidget(self.console)

        self.console_group.setLayout(console_layout)
        self.console_group.hide()
        main_layout.addWidget(self.console_group)

        self._populate_wallpaper_list()
        self.wallpaper_list.currentItemChanged.connect(self.on_wallpaper_selection_changed)
        self._select_initial_wallpaper()
        self.update_details_panel()

        self.set_static_wallpaper_button.clicked.connect(self.set_static_wallpaper)
        self.remove_static_wallpaper_button.clicked.connect(self.remove_static_wallpaper_action)

        self.install_169_button.clicked.connect(self.install_169_wallpapers)
        self.install_43_button.clicked.connect(self.install_43_wallpapers)
        self.remove_ranny_button.clicked.connect(self.remove_ranny_wallpapers)

        self.install_pcn_button.clicked.connect(self.install_pcn_wallpapers)
        self.remove_pcn_button.clicked.connect(self.remove_pcn_wallpapers)

        self.install_pcn_premium_button.clicked.connect(self.install_pcn_premium_wallpapers)
        self.remove_pcn_premium_button.clicked.connect(self.remove_pcn_premium_wallpapers)

        self.install_ot4ku_button.clicked.connect(self.install_ot4ku_wallpapers)
        self.remove_ot4ku_button.clicked.connect(self.remove_ot4ku_wallpapers)

        self.open_wallpaper_folder_button.clicked.connect(self.open_wallpaper_folder)
        self.hide_console_button.clicked.connect(self.toggle_console)

    def _build_button_row(self, *buttons):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch()
        for button in buttons:
            row.addWidget(button)
        row.addStretch()
        return row

    def _build_ranny_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_169_button = QPushButton("Install 16:9 Wallpapers")
        self.install_169_button.setFixedWidth(190)

        self.install_43_button = QPushButton("Install 4:3 Wallpapers")
        self.install_43_button.setFixedWidth(190)

        self.remove_ranny_button = QPushButton("Remove Installed Wallpapers")
        self.remove_ranny_button.setFixedWidth(220)

        layout.addLayout(
            self._build_button_row(
                self.install_169_button,
                self.install_43_button,
            )
        )
        layout.addLayout(
            self._build_button_row(
                self.remove_ranny_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_pcn_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_pcn_button = QPushButton("Install Wallpapers")
        self.install_pcn_button.setFixedWidth(190)

        self.remove_pcn_button = QPushButton("Remove Installed Wallpapers")
        self.remove_pcn_button.setFixedWidth(220)

        layout.addLayout(
            self._build_button_row(
                self.install_pcn_button,
                self.remove_pcn_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_pcn_premium_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_pcn_premium_button = QPushButton("Install Wallpapers")
        self.install_pcn_premium_button.setFixedWidth(190)

        self.remove_pcn_premium_button = QPushButton("Remove Installed Wallpapers")
        self.remove_pcn_premium_button.setFixedWidth(220)

        layout.addLayout(
            self._build_button_row(
                self.install_pcn_premium_button,
                self.remove_pcn_premium_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_ot4ku_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_ot4ku_button = QPushButton("Install Wallpapers")
        self.install_ot4ku_button.setFixedWidth(190)

        self.remove_ot4ku_button = QPushButton("Remove Installed Wallpapers")
        self.remove_ot4ku_button.setFixedWidth(220)

        layout.addLayout(
            self._build_button_row(
                self.install_ot4ku_button,
                self.remove_ot4ku_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _populate_wallpaper_list(self):
        self.wallpaper_list.clear()

        for wallpaper_key in self.wallpaper_display_order:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, wallpaper_key)
            self.wallpaper_list.addItem(item)

        self.update_wallpaper_list_labels()

    def _select_initial_wallpaper(self):
        if self.wallpaper_list.count() > 0:
            self.wallpaper_list.setCurrentRow(0)

            item = self.wallpaper_list.item(0)
            if item is not None:
                self.selected_wallpaper_key = item.data(Qt.ItemDataRole.UserRole)

    def on_wallpaper_selection_changed(self, current, previous):
        del previous

        if current is None:
            return

        wallpaper_key = current.data(Qt.ItemDataRole.UserRole)
        self.selected_wallpaper_key = wallpaper_key
        self.update_details_panel()

    def update_details_panel(self):
        wallpaper_key = self.selected_wallpaper_key

        self.wallpaper_name_label.setText(
            self.wallpaper_titles.get(wallpaper_key, wallpaper_key)
        )
        self.wallpaper_description_label.setText(
            self.wallpaper_descriptions.get(wallpaper_key, "")
        )

        for key, widget in self.wallpaper_action_widgets.items():
            widget.setVisible(key == wallpaper_key)

    def update_wallpaper_list_labels(self):
        for index in range(self.wallpaper_list.count()):
            item = self.wallpaper_list.item(index)
            wallpaper_key = item.data(Qt.ItemDataRole.UserRole)
            title = self.wallpaper_titles.get(wallpaper_key, wallpaper_key)
            item.setText(title)

    def set_refreshing_status(self, refreshing=False):
        if refreshing:
            self.wallpaper_status_label.setText("Refreshing...")
            self.wallpaper_status_label.setStyleSheet("color: #1e88e5; font-weight: bold;")
            self.wallpaper_status_label.show()
        else:
            self.wallpaper_status_label.setText("")
            self.wallpaper_status_label.hide()

    def is_offline_mode(self):
        checker = getattr(self.main_window, "is_offline_mode", None)
        return bool(checker()) if callable(checker) else False

    def is_online_connected(self):
        if self.is_offline_mode():
            return False

        try:
            return bool(self.connection and self.connection.is_connected())
        except Exception:
            return False

    def get_offline_sd_root(self):
        getter = getattr(self.main_window, "get_offline_sd_root", None)
        if callable(getter):
            value = getter()
        else:
            value = self.main_window.config_data.get("offline_sd_root", "")

        value = str(value or "").strip()
        return Path(value) if value else None

    def has_offline_sd_root(self):
        root = self.get_offline_sd_root()
        return bool(root and root.exists())

    def can_use_wallpapers(self):
        if self.is_offline_mode():
            return self.has_offline_sd_root()

        return self.is_online_connected()

    def _all_action_buttons(self):
        return [
            self.set_static_wallpaper_button,
            self.remove_static_wallpaper_button,
            self.install_169_button,
            self.install_43_button,
            self.remove_ranny_button,
            self.install_pcn_button,
            self.remove_pcn_button,
            self.install_pcn_premium_button,
            self.remove_pcn_premium_button,
            self.install_ot4ku_button,
            self.remove_ot4ku_button,
            self.open_wallpaper_folder_button,
        ]

    def _set_basic_connected_state(self):
        self.set_static_wallpaper_button.setEnabled(True)
        self.open_wallpaper_folder_button.setEnabled(True)

    def _reset_wallpaper_action_buttons(self):
        self.remove_static_wallpaper_button.setEnabled(False)

        self.install_169_button.setText("Install 16:9 Wallpapers")
        self.install_43_button.setText("Install 4:3 Wallpapers")
        self.install_pcn_button.setText("Install Wallpapers")
        self.install_pcn_premium_button.setText("Install Wallpapers")
        self.install_ot4ku_button.setText("Install Wallpapers")

        self.install_169_button.setEnabled(False)
        self.install_43_button.setEnabled(False)
        self.remove_ranny_button.setEnabled(False)

        self.install_pcn_button.setEnabled(False)
        self.remove_pcn_button.setEnabled(False)

        self.install_pcn_premium_button.setEnabled(False)
        self.remove_pcn_premium_button.setEnabled(False)

        self.install_ot4ku_button.setEnabled(False)
        self.remove_ot4ku_button.setEnabled(False)

    def update_connection_state(self, lightweight=True):
        if self.current_worker is not None and self.current_worker.isRunning():
            return

        if self.status_worker is not None and self.status_worker.isRunning():
            return

        if self.is_offline_mode():
            if not self.has_offline_sd_root():
                self.apply_disconnected_state()
                return
        else:
            if not self.is_online_connected():
                self.apply_disconnected_state()
                return

        self._set_basic_connected_state()

        if lightweight:
            return

        self.refresh_status()

    def apply_disconnected_state(self):
        for button in self._all_action_buttons():
            button.setEnabled(False)

        self.install_169_button.setText("Install 16:9 Wallpapers")
        self.install_43_button.setText("Install 4:3 Wallpapers")
        self.install_pcn_button.setText("Install Wallpapers")
        self.install_pcn_premium_button.setText("Install Wallpapers")
        self.install_ot4ku_button.setText("Install Wallpapers")

        self.set_refreshing_status(False)
        self.update_wallpaper_list_labels()
        self.update_details_panel()

    def show_refreshing_state(self):
        if self.current_worker is not None and self.current_worker.isRunning():
            return

        if self.status_worker is not None and self.status_worker.isRunning():
            return

        if not self.can_use_wallpapers():
            return

        self.set_refreshing_status(True)
        self.update_wallpaper_list_labels()
        self.update_details_panel()

        for button in self._all_action_buttons():
            button.setEnabled(False)

        self.open_wallpaper_folder_button.setEnabled(True)

    def refresh_status(self):
        if self.current_worker is not None and self.current_worker.isRunning():
            return

        if self.status_worker is not None and self.status_worker.isRunning():
            return

        if self.is_offline_mode():
            if not self.has_offline_sd_root():
                self.apply_disconnected_state()
                return
        else:
            if not self.is_online_connected():
                self.apply_disconnected_state()
                return

        self.show_refreshing_state()

        self.status_worker = WallpaperStatusWorker(
            connection=self.connection,
            offline=self.is_offline_mode(),
            sd_root=self.get_offline_sd_root(),
        )
        self.status_worker.result.connect(self.on_status_result)
        self.status_worker.error.connect(self.on_status_error)
        self.status_worker.finished.connect(self.on_status_finished)
        self.status_worker.start()

    def on_status_result(self, result):
        if not isinstance(result, dict):
            return

        self._set_basic_connected_state()
        self._reset_wallpaper_action_buttons()

        self.remove_static_wallpaper_button.setEnabled(
            bool(result.get("static_wallpaper_active"))
        )

        ranny_169_installed = bool(result.get("ranny_169_installed"))
        ranny_169_missing = bool(result.get("ranny_169_missing"))
        ranny_43_installed = bool(result.get("ranny_43_installed"))
        ranny_43_missing = bool(result.get("ranny_43_missing"))

        if not ranny_169_installed:
            self.install_169_button.setText("Install 16:9 Wallpapers")
            self.install_169_button.setEnabled(True)
        elif ranny_169_missing:
            self.install_169_button.setText("Update 16:9 Wallpapers")
            self.install_169_button.setEnabled(True)
        else:
            self.install_169_button.setText("Install 16:9 Wallpapers")
            self.install_169_button.setEnabled(False)

        if not ranny_43_installed:
            self.install_43_button.setText("Install 4:3 Wallpapers")
            self.install_43_button.setEnabled(True)
        elif ranny_43_missing:
            self.install_43_button.setText("Update 4:3 Wallpapers")
            self.install_43_button.setEnabled(True)
        else:
            self.install_43_button.setText("Install 4:3 Wallpapers")
            self.install_43_button.setEnabled(False)

        self.remove_ranny_button.setEnabled(ranny_169_installed or ranny_43_installed)

        pcn_installed = bool(result.get("pcn_installed"))
        pcn_missing = bool(result.get("pcn_missing"))

        if not pcn_installed:
            self.install_pcn_button.setText("Install Wallpapers")
            self.install_pcn_button.setEnabled(True)
        elif pcn_missing:
            self.install_pcn_button.setText("Update Wallpapers")
            self.install_pcn_button.setEnabled(True)
        else:
            self.install_pcn_button.setText("Install Wallpapers")
            self.install_pcn_button.setEnabled(False)

        self.remove_pcn_button.setEnabled(pcn_installed)

        pcn_premium_installed = bool(result.get("pcn_premium_installed"))
        pcn_premium_missing = bool(result.get("pcn_premium_missing"))

        if not pcn_premium_installed:
            self.install_pcn_premium_button.setText("Install Wallpapers")
            self.install_pcn_premium_button.setEnabled(True)
        elif pcn_premium_missing:
            self.install_pcn_premium_button.setText("Update Wallpapers")
            self.install_pcn_premium_button.setEnabled(True)
        else:
            self.install_pcn_premium_button.setText("Install Wallpapers")
            self.install_pcn_premium_button.setEnabled(False)

        self.remove_pcn_premium_button.setEnabled(pcn_premium_installed)

        ot4ku_installed = bool(result.get("ot4ku_installed"))
        ot4ku_missing = bool(result.get("ot4ku_missing"))

        if not ot4ku_installed:
            self.install_ot4ku_button.setText("Install Wallpapers")
            self.install_ot4ku_button.setEnabled(True)
        elif ot4ku_missing:
            self.install_ot4ku_button.setText("Update Wallpapers")
            self.install_ot4ku_button.setEnabled(True)
        else:
            self.install_ot4ku_button.setText("Install Wallpapers")
            self.install_ot4ku_button.setEnabled(False)

        self.remove_ot4ku_button.setEnabled(ot4ku_installed)

        if self.is_offline_mode():
            self.open_wallpaper_folder_button.setEnabled(True)
        else:
            self.open_wallpaper_folder_button.setEnabled(
                bool(result.get("folder_available"))
            )

        self.set_refreshing_status(False)
        self.update_wallpaper_list_labels()
        self.update_details_panel()

    def on_status_error(self, detail: str):
        self.set_refreshing_status(False)

        if self.is_offline_mode():
            self.apply_disconnected_state()
            return

        try:
            self.connection.mark_disconnected()
        except Exception:
            pass

        self.apply_disconnected_state()

    def on_status_finished(self):
        self.status_worker = None

    def start_worker(self, task_fn, success_message=""):
        if self.current_worker is not None and self.current_worker.isRunning():
            return

        if self.status_worker is not None and self.status_worker.isRunning():
            return

        self.show_console()
        self.console.clear()

        self.current_worker = WallpaperTaskWorker(task_fn, success_message)
        self.current_worker.log_line.connect(self.append_console)
        self.current_worker.success.connect(self.on_task_success)
        self.current_worker.error.connect(self.on_task_error)
        self.current_worker.finished_task.connect(self.on_task_finished)
        self.current_worker.start()

    def on_task_success(self, message: str):
        if message:
            self.append_console(f"\n{message}\n")

    def on_task_error(self, detail: str):
        self.append_console("\nError:\n")
        self.append_console(detail)
        QMessageBox.critical(self, "Wallpaper Error", detail.split("\n\n", 1)[0])

    def on_task_finished(self):
        self.current_worker = None
        self.refresh_status()

    def show_console(self):
        if self.console_visible:
            return
        self.console_group.show()
        self.console_visible = True

    def toggle_console(self):
        if self.console_visible:
            self.console_group.hide()
            self.console_visible = False
        else:
            self.console_group.show()
            self.console_visible = True

    def append_console(self, text: str):
        self.console.moveCursor(self.console.textCursor().MoveOperation.End)
        self.console.insertPlainText(text)
        self.console.ensureCursorVisible()

    def require_available(self):
        if self.is_offline_mode():
            if not self.has_offline_sd_root():
                QMessageBox.warning(self, "Error", "Select an Offline SD Card folder first.")
                return False
            return True

        if not self.is_online_connected():
            return False

        return True

    def set_static_wallpaper(self):
        if self.is_offline_mode():
            if not self.has_offline_sd_root():
                QMessageBox.warning(self, "Error", "Select an Offline SD Card folder first.")
                return

            dialog = StaticWallpaperDialog(
                connection=None,
                parent=self,
                sd_root=self.get_offline_sd_root(),
            )
            if dialog.exec():
                self.refresh_status()
            return

        if not self.is_online_connected():
            return

        dialog = StaticWallpaperDialog(self.connection, self)
        if dialog.exec():
            self.refresh_status()

    def remove_static_wallpaper_action(self):
        if self.is_offline_mode():
            if not self.has_offline_sd_root():
                QMessageBox.warning(self, "Error", "Select an Offline SD Card folder first.")
                return

            confirm = QMessageBox.question(
                self,
                "Remove Static Wallpaper",
                "Remove the current static wallpaper from the Offline SD Card?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

            try:
                remove_static_wallpaper_local(self.get_offline_sd_root())
                self.refresh_status()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
            return

        if not self.is_online_connected():
            return

        confirm = QMessageBox.question(
            self,
            "Remove Static Wallpaper",
            "Remove the current static wallpaper from the MiSTer?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            remove_static_wallpaper(self.connection, reload_menu=True)
            self.refresh_status()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def install_169_wallpapers(self):
        if not self.require_available():
            return

        def task(log):
            log("Fetching wallpaper list...\n")
            wallpapers_169, _ = fetch_ranny_wallpapers()

            if not wallpapers_169:
                log("No wallpapers found.\n")
                return

            if self.is_offline_mode():
                count = install_wallpaper_items_local(
                    self.get_offline_sd_root(),
                    wallpapers_169,
                    log,
                )
            else:
                count = install_wallpaper_items(self.connection, wallpapers_169, log)

            log(f"\nFinished. {count} wallpapers installed.\n")

        self.start_worker(task)

    def install_43_wallpapers(self):
        if not self.require_available():
            return

        def task(log):
            log("Fetching wallpaper list...\n")
            _, wallpapers_43 = fetch_ranny_wallpapers()

            if not wallpapers_43:
                log("No wallpapers found.\n")
                return

            if self.is_offline_mode():
                count = install_wallpaper_items_local(
                    self.get_offline_sd_root(),
                    wallpapers_43,
                    log,
                )
            else:
                count = install_wallpaper_items(self.connection, wallpapers_43, log)

            log(f"\nFinished. {count} wallpapers installed.\n")

        self.start_worker(task)

    def remove_ranny_wallpapers(self):
        if not self.require_available():
            return

        target = "local SD Card" if self.is_offline_mode() else "MiSTer"

        confirm = QMessageBox.question(
            self,
            "Remove Wallpapers",
            f"Remove all Ranny Snice wallpapers from the {target}?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            log("Removing Ranny Snice wallpapers...\n")
            wallpapers_169, wallpapers_43 = fetch_ranny_wallpapers()

            if self.is_offline_mode():
                removed = remove_installed_wallpapers_local(
                    self.get_offline_sd_root(),
                    wallpapers_169 + wallpapers_43,
                    log,
                )
            else:
                removed = remove_installed_wallpapers(
                    self.connection,
                    wallpapers_169 + wallpapers_43,
                    log,
                )

            log(f"\nFinished. {removed} wallpapers removed.\n")

        self.start_worker(task)

    def install_pcn_wallpapers(self):
        if not self.require_available():
            return

        def task(log):
            log("Fetching wallpaper list...\n")
            wallpapers = fetch_pcn_wallpapers()

            if not wallpapers:
                log("No wallpapers found.\n")
                return

            if self.is_offline_mode():
                count = install_wallpaper_items_local(
                    self.get_offline_sd_root(),
                    wallpapers,
                    log,
                )
            else:
                count = install_wallpaper_items(self.connection, wallpapers, log)

            log(f"\nFinished. {count} wallpapers installed.\n")

        self.start_worker(task)

    def remove_pcn_wallpapers(self):
        if not self.require_available():
            return

        target = "local SD Card" if self.is_offline_mode() else "MiSTer"

        confirm = QMessageBox.question(
            self,
            "Remove Wallpapers",
            f"Remove all PCN Challenge wallpapers from the {target}?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            log("Removing PCN Challenge wallpapers...\n")
            wallpapers = fetch_pcn_wallpapers()

            if self.is_offline_mode():
                removed = remove_installed_wallpapers_local(
                    self.get_offline_sd_root(),
                    wallpapers,
                    log,
                )
            else:
                removed = remove_installed_wallpapers(
                    self.connection,
                    wallpapers,
                    log,
                )

            log(f"\nFinished. {removed} wallpapers removed.\n")

        self.start_worker(task)

    def install_pcn_premium_wallpapers(self):
        if not self.require_available():
            return

        def task(log):
            log("Fetching wallpaper list...\n")
            wallpapers = fetch_pcn_premium_wallpapers()

            if not wallpapers:
                log("No wallpapers found.\n")
                return

            if self.is_offline_mode():
                count = install_wallpaper_items_local(
                    self.get_offline_sd_root(),
                    wallpapers,
                    log,
                )
            else:
                count = install_wallpaper_items(self.connection, wallpapers, log)

            log(f"\nFinished. {count} wallpapers installed.\n")

        self.start_worker(task)

    def remove_pcn_premium_wallpapers(self):
        if not self.require_available():
            return

        target = "local SD Card" if self.is_offline_mode() else "MiSTer"

        confirm = QMessageBox.question(
            self,
            "Remove Wallpapers",
            f"Remove all PCN Premium Member wallpapers from the {target}?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            log("Removing PCN Premium Member wallpapers...\n")
            wallpapers = fetch_pcn_premium_wallpapers()

            if self.is_offline_mode():
                removed = remove_installed_wallpapers_local(
                    self.get_offline_sd_root(),
                    wallpapers,
                    log,
                )
            else:
                removed = remove_installed_wallpapers(
                    self.connection,
                    wallpapers,
                    log,
                )

            log(f"\nFinished. {removed} wallpapers removed.\n")

        self.start_worker(task)

    def install_ot4ku_wallpapers(self):
        if not self.require_available():
            return

        def task(log):
            log("Fetching wallpaper list...\n")
            wallpapers = fetch_ot4ku_wallpapers()

            if not wallpapers:
                log("No wallpapers found.\n")
                return

            if self.is_offline_mode():
                count = install_wallpaper_items_local(
                    self.get_offline_sd_root(),
                    wallpapers,
                    log,
                )
            else:
                count = install_wallpaper_items(self.connection, wallpapers, log)

            log(f"\nFinished. {count} wallpapers installed.\n")

        self.start_worker(task)

    def remove_ot4ku_wallpapers(self):
        if not self.require_available():
            return

        target = "local SD Card" if self.is_offline_mode() else "MiSTer"

        confirm = QMessageBox.question(
            self,
            "Remove Wallpapers",
            f"Remove all Anime0t4ku wallpapers from the {target}?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            log("Removing Anime0t4ku wallpapers...\n")
            wallpapers = fetch_ot4ku_wallpapers()

            if self.is_offline_mode():
                removed = remove_installed_wallpapers_local(
                    self.get_offline_sd_root(),
                    wallpapers,
                    log,
                )
            else:
                removed = remove_installed_wallpapers(
                    self.connection,
                    wallpapers,
                    log,
                )

            log(f"\nFinished. {removed} wallpapers removed.\n")

        self.start_worker(task)

    def open_wallpaper_folder(self):
        if not self.require_available():
            return

        try:
            if self.is_offline_mode():
                open_wallpaper_folder_local(self.get_offline_sd_root())
            else:
                open_wallpaper_folder_on_host(
                    self.connection.host,
                    self.connection.username or "root",
                    self.connection.password or "1",
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

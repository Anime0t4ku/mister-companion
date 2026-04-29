import traceback

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
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

from core.config import save_config
from core.language import tr
from core.scripts_actions import (
    check_update_all_initialized,
    disable_ftp_save_sync_service,
    enable_ftp_save_sync_service,
    enable_zaparoo_service,
    ensure_update_all_config_bootstrap,
    get_scripts_status,
    install_auto_time,
    install_cifs_mount,
    install_dav_browser,
    install_ftp_save_sync,
    install_migrate_sd,
    install_static_wallpaper,
    install_update_all,
    install_zaparoo,
    open_scripts_folder_on_host,
    remove_cifs_config,
    remove_dav_browser_config,
    remove_ftp_save_sync_config,
    run_cifs_mount,
    run_cifs_umount,
    run_update_all_stream,
    uninstall_auto_time,
    uninstall_cifs_mount,
    uninstall_dav_browser,
    uninstall_ftp_save_sync,
    uninstall_migrate_sd,
    uninstall_static_wallpaper,
    uninstall_update_all,
    uninstall_zaparoo,
)
from ui.dialogs.cifs_config_dialog import CifsConfigDialog
from ui.dialogs.dav_browser_config_dialog import DavBrowserConfigDialog
from ui.dialogs.ftp_save_sync_config_dialog import FtpSaveSyncConfigDialog
from ui.dialogs.update_all_config_dialog import UpdateAllConfigDialog


class ScriptTaskWorker(QThread):
    log_line = pyqtSignal(str)
    success = pyqtSignal(str)
    error = pyqtSignal(str)
    finished_task = pyqtSignal()
    task_result = pyqtSignal(object)

    def __init__(self, task_fn, success_message=""):
        super().__init__()
        self.task_fn = task_fn
        self.success_message = success_message

    def log(self, text):
        self.log_line.emit(text)

    def run(self):
        try:
            result = self.task_fn(self.log)

            if self.success_message:
                self.success.emit(self.success_message)

            self.task_result.emit(result)

        except Exception as e:
            detail = traceback.format_exc()
            self.error.emit(f"{str(e)}\n\n{detail}")
        finally:
            self.finished_task.emit()


class ScriptsTab(QWidget):
    SCRIPT_UPDATE_ALL = "update_all"
    SCRIPT_ZAPAROO = "zaparoo"
    SCRIPT_MIGRATE_SD = "migrate_sd"
    SCRIPT_CIFS = "cifs_mount"
    SCRIPT_AUTO_TIME = "auto_time"
    SCRIPT_DAV_BROWSER = "dav_browser"
    SCRIPT_FTP_SAVE_SYNC = "ftp_save_sync"
    SCRIPT_STATIC_WALLPAPER = "static_wallpaper"

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection

        self.console_visible = False
        self.current_worker = None
        self.update_all_installed = False
        self.update_all_initialized = False
        self.waiting_for_reboot_reconnect = False

        self.script_display_order = [
            self.SCRIPT_UPDATE_ALL,
            self.SCRIPT_ZAPAROO,
            self.SCRIPT_MIGRATE_SD,
            self.SCRIPT_CIFS,
            self.SCRIPT_AUTO_TIME,
            self.SCRIPT_DAV_BROWSER,
            self.SCRIPT_FTP_SAVE_SYNC,
            self.SCRIPT_STATIC_WALLPAPER,
        ]

        self.script_titles = {
            self.SCRIPT_UPDATE_ALL: "update_all",
            self.SCRIPT_ZAPAROO: "zaparoo",
            self.SCRIPT_MIGRATE_SD: "migrate_sd",
            self.SCRIPT_CIFS: "cifs_mount",
            self.SCRIPT_AUTO_TIME: "auto_time",
            self.SCRIPT_DAV_BROWSER: "dav_browser",
            self.SCRIPT_FTP_SAVE_SYNC: "ftp_save_sync",
            self.SCRIPT_STATIC_WALLPAPER: "static_wallpaper",
        }

        self.script_descriptions = {
            self.SCRIPT_UPDATE_ALL: tr("scripts_tab.description_update_all"),
            self.SCRIPT_ZAPAROO: tr("scripts_tab.description_zaparoo"),
            self.SCRIPT_MIGRATE_SD: tr("scripts_tab.description_migrate_sd"),
            self.SCRIPT_CIFS: tr("scripts_tab.description_cifs"),
            self.SCRIPT_AUTO_TIME: tr("scripts_tab.description_auto_time"),
            self.SCRIPT_DAV_BROWSER: tr("scripts_tab.description_dav_browser"),
            self.SCRIPT_FTP_SAVE_SYNC: tr("scripts_tab.description_ftp_save_sync"),
            self.SCRIPT_STATIC_WALLPAPER: tr("scripts_tab.description_static_wallpaper"),
        }

        self.script_status_texts = {
            self.SCRIPT_UPDATE_ALL: tr("common.unknown"),
            self.SCRIPT_ZAPAROO: tr("common.unknown"),
            self.SCRIPT_MIGRATE_SD: tr("common.unknown"),
            self.SCRIPT_CIFS: tr("common.unknown"),
            self.SCRIPT_AUTO_TIME: tr("common.unknown"),
            self.SCRIPT_DAV_BROWSER: tr("common.unknown"),
            self.SCRIPT_FTP_SAVE_SYNC: tr("common.unknown"),
            self.SCRIPT_STATIC_WALLPAPER: tr("common.unknown"),
        }

        self.selected_script_key = self.SCRIPT_UPDATE_ALL

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

        list_group = QGroupBox(tr("scripts_tab.scripts"))
        list_layout = QVBoxLayout()
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)

        self.script_list = QListWidget()
        self.script_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.script_list.setAlternatingRowColors(False)
        self.script_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.script_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.script_list.setMinimumWidth(290)
        self.script_list.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding
        )
        self.script_list.setStyleSheet(
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
        list_layout.addWidget(self.script_list)

        list_group.setLayout(list_layout)
        top_row.addWidget(list_group, 1)

        details_group = QGroupBox(tr("scripts_tab.details"))
        details_layout = QVBoxLayout()
        details_layout.setContentsMargins(14, 14, 14, 14)
        details_layout.setSpacing(10)

        self.script_name_label = QLabel(tr("scripts_tab.select_script"))
        font = self.script_name_label.font()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        self.script_name_label.setFont(font)
        details_layout.addWidget(self.script_name_label)

        self.script_status_label = QLabel(tr("scripts_tab.status_unknown_full"))
        self.script_status_label.setStyleSheet("color: gray;")
        details_layout.addWidget(self.script_status_label)

        self.script_description_label = QLabel("")
        self.script_description_label.setWordWrap(True)
        self.script_description_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.script_description_label.setMinimumHeight(54)
        details_layout.addWidget(self.script_description_label)

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

        self.update_actions_widget = self._build_update_all_actions()
        self.zaparoo_actions_widget = self._build_zaparoo_actions()
        self.migrate_actions_widget = self._build_migrate_sd_actions()
        self.cifs_actions_widget = self._build_cifs_actions()
        self.auto_time_actions_widget = self._build_auto_time_actions()
        self.dav_browser_actions_widget = self._build_dav_browser_actions()
        self.ftp_save_sync_actions_widget = self._build_ftp_save_sync_actions()
        self.static_wallpaper_actions_widget = self._build_static_wallpaper_actions()

        self.script_action_widgets = {
            self.SCRIPT_UPDATE_ALL: self.update_actions_widget,
            self.SCRIPT_ZAPAROO: self.zaparoo_actions_widget,
            self.SCRIPT_MIGRATE_SD: self.migrate_actions_widget,
            self.SCRIPT_CIFS: self.cifs_actions_widget,
            self.SCRIPT_AUTO_TIME: self.auto_time_actions_widget,
            self.SCRIPT_DAV_BROWSER: self.dav_browser_actions_widget,
            self.SCRIPT_FTP_SAVE_SYNC: self.ftp_save_sync_actions_widget,
            self.SCRIPT_STATIC_WALLPAPER: self.static_wallpaper_actions_widget,
        }

        for widget in self.script_action_widgets.values():
            widget.hide()
            self.action_buttons_layout.addWidget(widget)

        self.action_buttons_layout.addStretch()

        details_group.setLayout(details_layout)
        top_row.addWidget(details_group, 2)

        bottom_actions_row = QHBoxLayout()
        bottom_actions_row.addStretch()

        self.open_scripts_folder_button = QPushButton(tr("scripts_tab.open_scripts_folder"))
        self.open_scripts_folder_button.setFixedWidth(180)
        bottom_actions_row.addWidget(self.open_scripts_folder_button)

        bottom_actions_row.addStretch()
        main_layout.addLayout(bottom_actions_row)

        self.console_group = QGroupBox(tr("scripts_tab.ssh_output"))
        console_layout = QVBoxLayout()
        console_layout.setContentsMargins(10, 10, 10, 10)
        console_layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.addStretch()

        self.hide_console_button = QPushButton(tr("scripts_tab.hide"))
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

        self._populate_script_list()
        self._select_initial_script()

        self.script_list.currentItemChanged.connect(self.on_script_selection_changed)

        self.install_update_button.clicked.connect(self.install_update_all)
        self.uninstall_update_button.clicked.connect(self.uninstall_update_all)
        self.configure_update_button.clicked.connect(self.configure_update_all)
        self.run_update_button.clicked.connect(self.run_update_all)

        self.install_zaparoo_button.clicked.connect(self.install_zaparoo)
        self.enable_zaparoo_service_button.clicked.connect(self.enable_zaparoo_service)
        self.uninstall_zaparoo_button.clicked.connect(self.uninstall_zaparoo)

        self.install_migrate_button.clicked.connect(self.install_migrate_sd)
        self.uninstall_migrate_button.clicked.connect(self.uninstall_migrate_sd)

        self.install_cifs_button.clicked.connect(self.install_cifs_mount)
        self.configure_cifs_button.clicked.connect(self.configure_cifs)
        self.mount_cifs_button.clicked.connect(self.run_cifs_mount)
        self.unmount_cifs_button.clicked.connect(self.run_cifs_umount)
        self.remove_cifs_config_button.clicked.connect(self.remove_cifs_config)
        self.uninstall_cifs_button.clicked.connect(self.uninstall_cifs_mount)

        self.install_auto_time_button.clicked.connect(self.install_auto_time)
        self.uninstall_auto_time_button.clicked.connect(self.uninstall_auto_time)

        self.install_dav_browser_button.clicked.connect(self.install_dav_browser)
        self.configure_dav_browser_button.clicked.connect(self.configure_dav_browser)
        self.remove_dav_browser_config_button.clicked.connect(self.remove_dav_browser_config)
        self.uninstall_dav_browser_button.clicked.connect(self.uninstall_dav_browser)

        self.install_ftp_save_sync_button.clicked.connect(self.install_ftp_save_sync)
        self.configure_ftp_save_sync_button.clicked.connect(self.configure_ftp_save_sync)
        self.enable_ftp_save_sync_service_button.clicked.connect(self.enable_ftp_save_sync_service)
        self.disable_ftp_save_sync_service_button.clicked.connect(self.disable_ftp_save_sync_service)
        self.remove_ftp_save_sync_config_button.clicked.connect(self.remove_ftp_save_sync_config)
        self.uninstall_ftp_save_sync_button.clicked.connect(self.uninstall_ftp_save_sync)

        self.install_static_wallpaper_button.clicked.connect(self.install_static_wallpaper)
        self.uninstall_static_wallpaper_button.clicked.connect(self.uninstall_static_wallpaper)

        self.open_scripts_folder_button.clicked.connect(self.open_scripts_folder)
        self.hide_console_button.clicked.connect(self.toggle_console)

    def _build_button_row(self, *buttons):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch()
        for button in buttons:
            row.addWidget(button)
        row.addStretch()
        return row

    def _build_update_all_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_update_button = QPushButton(tr("scripts_tab.install"))
        self.install_update_button.setFixedWidth(170)

        self.uninstall_update_button = QPushButton(tr("scripts_tab.uninstall"))
        self.uninstall_update_button.setFixedWidth(170)

        self.configure_update_button = QPushButton(tr("scripts_tab.configure"))
        self.configure_update_button.setFixedWidth(190)

        self.run_update_button = QPushButton(tr("scripts_tab.run"))
        self.run_update_button.setFixedWidth(170)

        layout.addLayout(
            self._build_button_row(
                self.install_update_button,
                self.uninstall_update_button,
            )
        )
        layout.addLayout(
            self._build_button_row(
                self.configure_update_button,
                self.run_update_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_zaparoo_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_zaparoo_button = QPushButton(tr("scripts_tab.install"))
        self.install_zaparoo_button.setFixedWidth(170)

        self.enable_zaparoo_service_button = QPushButton(tr("scripts_tab.enable_service"))
        self.enable_zaparoo_service_button.setFixedWidth(190)

        self.uninstall_zaparoo_button = QPushButton(tr("scripts_tab.uninstall"))
        self.uninstall_zaparoo_button.setFixedWidth(170)

        layout.addLayout(
            self._build_button_row(
                self.install_zaparoo_button,
                self.enable_zaparoo_service_button,
            )
        )
        layout.addLayout(self._build_button_row(self.uninstall_zaparoo_button))

        widget.setLayout(layout)
        return widget

    def _build_migrate_sd_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_migrate_button = QPushButton(tr("scripts_tab.install"))
        self.install_migrate_button.setFixedWidth(180)

        self.uninstall_migrate_button = QPushButton(tr("scripts_tab.uninstall"))
        self.uninstall_migrate_button.setFixedWidth(180)

        layout.addLayout(
            self._build_button_row(
                self.install_migrate_button,
                self.uninstall_migrate_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_cifs_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_cifs_button = QPushButton(tr("scripts_tab.install"))
        self.install_cifs_button.setFixedWidth(120)

        self.configure_cifs_button = QPushButton(tr("scripts_tab.configure"))
        self.configure_cifs_button.setFixedWidth(120)

        self.mount_cifs_button = QPushButton(tr("scripts_tab.mount"))
        self.mount_cifs_button.setFixedWidth(120)

        self.unmount_cifs_button = QPushButton(tr("scripts_tab.unmount"))
        self.unmount_cifs_button.setFixedWidth(120)

        self.remove_cifs_config_button = QPushButton(tr("scripts_tab.remove_config"))
        self.remove_cifs_config_button.setFixedWidth(130)

        self.uninstall_cifs_button = QPushButton(tr("scripts_tab.uninstall"))
        self.uninstall_cifs_button.setFixedWidth(120)

        layout.addLayout(
            self._build_button_row(
                self.install_cifs_button,
                self.configure_cifs_button,
                self.mount_cifs_button,
            )
        )
        layout.addLayout(
            self._build_button_row(
                self.unmount_cifs_button,
                self.remove_cifs_config_button,
                self.uninstall_cifs_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_auto_time_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_auto_time_button = QPushButton(tr("scripts_tab.install"))
        self.install_auto_time_button.setFixedWidth(140)

        self.uninstall_auto_time_button = QPushButton(tr("scripts_tab.uninstall"))
        self.uninstall_auto_time_button.setFixedWidth(140)

        layout.addLayout(
            self._build_button_row(
                self.install_auto_time_button,
                self.uninstall_auto_time_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_dav_browser_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_dav_browser_button = QPushButton(tr("scripts_tab.install"))
        self.install_dav_browser_button.setFixedWidth(140)

        self.configure_dav_browser_button = QPushButton(tr("scripts_tab.configure"))
        self.configure_dav_browser_button.setFixedWidth(140)

        self.remove_dav_browser_config_button = QPushButton(tr("scripts_tab.remove_config"))
        self.remove_dav_browser_config_button.setFixedWidth(140)

        self.uninstall_dav_browser_button = QPushButton(tr("scripts_tab.uninstall"))
        self.uninstall_dav_browser_button.setFixedWidth(140)

        layout.addLayout(
            self._build_button_row(
                self.install_dav_browser_button,
                self.configure_dav_browser_button,
            )
        )
        layout.addLayout(
            self._build_button_row(
                self.remove_dav_browser_config_button,
                self.uninstall_dav_browser_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_ftp_save_sync_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_ftp_save_sync_button = QPushButton(tr("scripts_tab.install"))
        self.install_ftp_save_sync_button.setFixedWidth(140)

        self.configure_ftp_save_sync_button = QPushButton(tr("scripts_tab.configure"))
        self.configure_ftp_save_sync_button.setFixedWidth(140)

        self.enable_ftp_save_sync_service_button = QPushButton(tr("scripts_tab.enable_service"))
        self.enable_ftp_save_sync_service_button.setFixedWidth(140)

        self.disable_ftp_save_sync_service_button = QPushButton(tr("scripts_tab.disable_service"))
        self.disable_ftp_save_sync_service_button.setFixedWidth(140)

        self.remove_ftp_save_sync_config_button = QPushButton(tr("scripts_tab.remove_config"))
        self.remove_ftp_save_sync_config_button.setFixedWidth(140)

        self.uninstall_ftp_save_sync_button = QPushButton(tr("scripts_tab.uninstall"))
        self.uninstall_ftp_save_sync_button.setFixedWidth(140)

        layout.addLayout(
            self._build_button_row(
                self.install_ftp_save_sync_button,
                self.configure_ftp_save_sync_button,
                self.enable_ftp_save_sync_service_button,
            )
        )
        layout.addLayout(
            self._build_button_row(
                self.disable_ftp_save_sync_service_button,
                self.remove_ftp_save_sync_config_button,
                self.uninstall_ftp_save_sync_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_static_wallpaper_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_static_wallpaper_button = QPushButton(tr("scripts_tab.install"))
        self.install_static_wallpaper_button.setFixedWidth(150)

        self.uninstall_static_wallpaper_button = QPushButton(tr("scripts_tab.uninstall"))
        self.uninstall_static_wallpaper_button.setFixedWidth(150)

        layout.addLayout(
            self._build_button_row(
                self.install_static_wallpaper_button,
                self.uninstall_static_wallpaper_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _populate_script_list(self):
        self.script_list.clear()
        for script_key in self.script_display_order:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, script_key)
            self.script_list.addItem(item)
        self.update_script_list_labels()

    def _select_initial_script(self):
        if self.script_list.count() > 0:
            self.script_list.setCurrentRow(0)

    def _get_current_script_key(self):
        item = self.script_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def on_script_selection_changed(self, current, previous):
        del previous
        if current is None:
            return

        script_key = current.data(Qt.ItemDataRole.UserRole)
        self.selected_script_key = script_key
        self.update_details_panel()

    def update_details_panel(self):
        script_key = self.selected_script_key
        if not script_key:
            self.script_name_label.setText(tr("scripts_tab.select_script"))
            self.script_status_label.setText(tr("scripts_tab.status_unknown_full"))
            self.script_status_label.setStyleSheet("color: gray;")
            self.script_description_label.setText("")
            for widget in self.script_action_widgets.values():
                widget.hide()
            return

        self.script_name_label.setText(self.script_titles.get(script_key, script_key))
        self.script_description_label.setText(self.script_descriptions.get(script_key, ""))

        status_text = self.script_status_texts.get(script_key, tr("common.unknown"))
        self.script_status_label.setText(tr("scripts_tab.status_label", status=status_text))

        lowered = status_text.lower()
        if "installed" in lowered and "not" not in lowered and "disabled" not in lowered:
            if "configured" in lowered:
                self.script_status_label.setStyleSheet("color: #00aa00;")
            elif "service disabled" in lowered or "not configured" in lowered:
                self.script_status_label.setStyleSheet("color: #cc8400;")
            else:
                self.script_status_label.setStyleSheet("color: #00aa00;")
        elif "active" in lowered:
            self.script_status_label.setStyleSheet("color: #00aa00;")
        elif "configured" in lowered:
            self.script_status_label.setStyleSheet("color: #00aa00;")
        elif "disabled" in lowered or "not configured" in lowered:
            self.script_status_label.setStyleSheet("color: #cc8400;")
        elif "not installed" in lowered:
            self.script_status_label.setStyleSheet("color: #cc0000;")
        else:
            self.script_status_label.setStyleSheet("color: gray;")

        for key, widget in self.script_action_widgets.items():
            widget.setVisible(key == script_key)

    def update_script_list_labels(self):
        for index in range(self.script_list.count()):
            item = self.script_list.item(index)
            script_key = item.data(Qt.ItemDataRole.UserRole)
            title = self.script_titles.get(script_key, script_key)
            status = self.script_status_texts.get(script_key, tr("common.unknown"))
            item.setText(f"{title}    {status}")

    def update_connection_state(self):
        if self.connection.is_connected():
            self.apply_connected_state()
        else:
            self.apply_disconnected_state()

    def apply_connected_state(self):
        if self.current_worker is not None and self.current_worker.isRunning():
            return

        self.open_scripts_folder_button.setEnabled(True)

    def apply_disconnected_state(self):
        for button in [
            self.install_update_button,
            self.uninstall_update_button,
            self.configure_update_button,
            self.run_update_button,
            self.install_zaparoo_button,
            self.enable_zaparoo_service_button,
            self.uninstall_zaparoo_button,
            self.install_migrate_button,
            self.uninstall_migrate_button,
            self.install_cifs_button,
            self.configure_cifs_button,
            self.mount_cifs_button,
            self.unmount_cifs_button,
            self.remove_cifs_config_button,
            self.uninstall_cifs_button,
            self.install_auto_time_button,
            self.uninstall_auto_time_button,
            self.install_dav_browser_button,
            self.configure_dav_browser_button,
            self.remove_dav_browser_config_button,
            self.uninstall_dav_browser_button,
            self.install_ftp_save_sync_button,
            self.configure_ftp_save_sync_button,
            self.enable_ftp_save_sync_service_button,
            self.disable_ftp_save_sync_service_button,
            self.remove_ftp_save_sync_config_button,
            self.uninstall_ftp_save_sync_button,
            self.install_static_wallpaper_button,
            self.uninstall_static_wallpaper_button,
            self.open_scripts_folder_button,
        ]:
            button.setEnabled(False)

        for key in self.script_status_texts:
            self.script_status_texts[key] = tr("common.unknown")

        self.update_script_list_labels()
        self.update_details_panel()

    def refresh_status(self):
        if not self.connection.is_connected():
            self.apply_disconnected_state()
            return

        try:
            status = get_scripts_status(self.connection)
        except Exception:
            self.connection.mark_disconnected()
            self.apply_disconnected_state()
            return

        self.update_all_installed = status.update_all_installed
        self.update_all_initialized = status.update_all_initialized

        if status.update_all_installed:
            self.script_status_texts[self.SCRIPT_UPDATE_ALL] = tr("scripts_tab.status_installed")
            self.install_update_button.setEnabled(False)
            self.uninstall_update_button.setEnabled(True)
            self.run_update_button.setEnabled(True)
            self.configure_update_button.setEnabled(True)
            self.update_all_initialized = status.update_all_initialized
        else:
            self.script_status_texts[self.SCRIPT_UPDATE_ALL] = tr("scripts_tab.status_not_installed")
            self.install_update_button.setEnabled(True)
            self.uninstall_update_button.setEnabled(False)
            self.run_update_button.setEnabled(False)
            self.configure_update_button.setEnabled(False)

        if not status.zaparoo_installed:
            self.script_status_texts[self.SCRIPT_ZAPAROO] = tr("scripts_tab.status_not_installed")
            self.install_zaparoo_button.setEnabled(True)
            self.enable_zaparoo_service_button.setEnabled(False)
            self.uninstall_zaparoo_button.setEnabled(False)
        elif status.zaparoo_installed and not status.zaparoo_service_enabled:
            self.script_status_texts[self.SCRIPT_ZAPAROO] = tr("scripts_tab.status_installed_service_disabled")
            self.install_zaparoo_button.setEnabled(False)
            self.enable_zaparoo_service_button.setEnabled(True)
            self.uninstall_zaparoo_button.setEnabled(True)
        else:
            self.script_status_texts[self.SCRIPT_ZAPAROO] = tr("scripts_tab.status_installed")
            self.install_zaparoo_button.setEnabled(False)
            self.enable_zaparoo_service_button.setEnabled(False)
            self.uninstall_zaparoo_button.setEnabled(True)

        if status.migrate_sd_installed:
            self.script_status_texts[self.SCRIPT_MIGRATE_SD] = tr("scripts_tab.status_installed")
            self.install_migrate_button.setEnabled(False)
            self.uninstall_migrate_button.setEnabled(True)
        else:
            self.script_status_texts[self.SCRIPT_MIGRATE_SD] = tr("scripts_tab.status_not_installed")
            self.install_migrate_button.setEnabled(True)
            self.uninstall_migrate_button.setEnabled(False)

        if not status.cifs_installed:
            self.script_status_texts[self.SCRIPT_CIFS] = tr("scripts_tab.status_not_installed")
            self.install_cifs_button.setEnabled(True)
            self.configure_cifs_button.setEnabled(False)
            self.configure_cifs_button.setText(tr("scripts_tab.configure"))
            self.mount_cifs_button.setEnabled(False)
            self.unmount_cifs_button.setEnabled(False)
            self.remove_cifs_config_button.setEnabled(False)
            self.uninstall_cifs_button.setEnabled(False)
        elif status.cifs_installed and not status.cifs_configured:
            self.script_status_texts[self.SCRIPT_CIFS] = tr("scripts_tab.status_installed_not_configured")
            self.install_cifs_button.setEnabled(False)
            self.configure_cifs_button.setEnabled(True)
            self.configure_cifs_button.setText(tr("scripts_tab.configure"))
            self.mount_cifs_button.setEnabled(False)
            self.unmount_cifs_button.setEnabled(False)
            self.remove_cifs_config_button.setEnabled(False)
            self.uninstall_cifs_button.setEnabled(True)
        else:
            self.script_status_texts[self.SCRIPT_CIFS] = tr("scripts_tab.status_configured")
            self.install_cifs_button.setEnabled(False)
            self.configure_cifs_button.setEnabled(True)
            self.configure_cifs_button.setText(tr("scripts_tab.reconfigure"))
            self.mount_cifs_button.setEnabled(True)
            self.unmount_cifs_button.setEnabled(True)
            self.remove_cifs_config_button.setEnabled(True)
            self.uninstall_cifs_button.setEnabled(True)

        if status.auto_time_installed:
            self.script_status_texts[self.SCRIPT_AUTO_TIME] = tr("scripts_tab.status_installed")
            self.install_auto_time_button.setEnabled(False)
            self.uninstall_auto_time_button.setEnabled(True)
        else:
            self.script_status_texts[self.SCRIPT_AUTO_TIME] = tr("scripts_tab.status_not_installed")
            self.install_auto_time_button.setEnabled(True)
            self.uninstall_auto_time_button.setEnabled(False)

        if not status.dav_browser_installed:
            self.script_status_texts[self.SCRIPT_DAV_BROWSER] = tr("scripts_tab.status_not_installed")
            self.install_dav_browser_button.setEnabled(True)
            self.configure_dav_browser_button.setEnabled(False)
            self.configure_dav_browser_button.setText(tr("scripts_tab.configure"))
            self.remove_dav_browser_config_button.setEnabled(False)
            self.uninstall_dav_browser_button.setEnabled(False)
        elif status.dav_browser_installed and not status.dav_browser_configured:
            self.script_status_texts[self.SCRIPT_DAV_BROWSER] = tr("scripts_tab.status_installed_not_configured")
            self.install_dav_browser_button.setEnabled(False)
            self.configure_dav_browser_button.setEnabled(True)
            self.configure_dav_browser_button.setText(tr("scripts_tab.configure"))
            self.remove_dav_browser_config_button.setEnabled(False)
            self.uninstall_dav_browser_button.setEnabled(True)
        else:
            self.script_status_texts[self.SCRIPT_DAV_BROWSER] = tr("scripts_tab.status_configured")
            self.install_dav_browser_button.setEnabled(False)
            self.configure_dav_browser_button.setEnabled(True)
            self.configure_dav_browser_button.setText(tr("scripts_tab.reconfigure"))
            self.remove_dav_browser_config_button.setEnabled(True)
            self.uninstall_dav_browser_button.setEnabled(True)

        if not status.ftp_save_sync_installed:
            self.script_status_texts[self.SCRIPT_FTP_SAVE_SYNC] = tr("scripts_tab.status_not_installed")
            self.install_ftp_save_sync_button.setEnabled(True)
            self.configure_ftp_save_sync_button.setEnabled(False)
            self.configure_ftp_save_sync_button.setText(tr("scripts_tab.configure"))
            self.enable_ftp_save_sync_service_button.setEnabled(False)
            self.disable_ftp_save_sync_service_button.setEnabled(False)
            self.remove_ftp_save_sync_config_button.setEnabled(False)
            self.uninstall_ftp_save_sync_button.setEnabled(False)
        elif status.ftp_save_sync_installed and not status.ftp_save_sync_configured:
            self.script_status_texts[self.SCRIPT_FTP_SAVE_SYNC] = tr("scripts_tab.status_installed_not_configured")
            self.install_ftp_save_sync_button.setEnabled(False)
            self.configure_ftp_save_sync_button.setEnabled(True)
            self.configure_ftp_save_sync_button.setText(tr("scripts_tab.configure"))
            self.enable_ftp_save_sync_service_button.setEnabled(False)
            self.disable_ftp_save_sync_service_button.setEnabled(False)
            self.remove_ftp_save_sync_config_button.setEnabled(False)
            self.uninstall_ftp_save_sync_button.setEnabled(True)
        elif status.ftp_save_sync_installed and status.ftp_save_sync_configured and not status.ftp_save_sync_service_enabled:
            self.script_status_texts[self.SCRIPT_FTP_SAVE_SYNC] = tr("scripts_tab.status_configured_service_disabled")
            self.install_ftp_save_sync_button.setEnabled(False)
            self.configure_ftp_save_sync_button.setEnabled(True)
            self.configure_ftp_save_sync_button.setText(tr("scripts_tab.reconfigure"))
            self.enable_ftp_save_sync_service_button.setEnabled(True)
            self.disable_ftp_save_sync_service_button.setEnabled(False)
            self.remove_ftp_save_sync_config_button.setEnabled(True)
            self.uninstall_ftp_save_sync_button.setEnabled(True)
        else:
            self.script_status_texts[self.SCRIPT_FTP_SAVE_SYNC] = tr("scripts_tab.status_configured_service_enabled")
            self.install_ftp_save_sync_button.setEnabled(False)
            self.configure_ftp_save_sync_button.setEnabled(True)
            self.configure_ftp_save_sync_button.setText(tr("scripts_tab.reconfigure"))
            self.enable_ftp_save_sync_service_button.setEnabled(False)
            self.disable_ftp_save_sync_service_button.setEnabled(True)
            self.remove_ftp_save_sync_config_button.setEnabled(True)
            self.uninstall_ftp_save_sync_button.setEnabled(True)

        if not status.static_wallpaper_installed:
            self.script_status_texts[self.SCRIPT_STATIC_WALLPAPER] = tr("scripts_tab.status_not_installed")
            self.install_static_wallpaper_button.setEnabled(True)
            self.uninstall_static_wallpaper_button.setEnabled(False)
        elif status.static_wallpaper_active:
            self.script_status_texts[self.SCRIPT_STATIC_WALLPAPER] = tr("scripts_tab.status_installed_wallpaper_active")
            self.install_static_wallpaper_button.setEnabled(False)
            self.uninstall_static_wallpaper_button.setEnabled(True)
        elif status.static_wallpaper_saved:
            self.script_status_texts[self.SCRIPT_STATIC_WALLPAPER] = tr("scripts_tab.status_installed_selection_saved")
            self.install_static_wallpaper_button.setEnabled(False)
            self.uninstall_static_wallpaper_button.setEnabled(True)
        else:
            self.script_status_texts[self.SCRIPT_STATIC_WALLPAPER] = tr("scripts_tab.status_installed")
            self.install_static_wallpaper_button.setEnabled(False)
            self.uninstall_static_wallpaper_button.setEnabled(True)

        self.open_scripts_folder_button.setEnabled(True)

        self.update_script_list_labels()
        self.update_details_panel()

    def show_console(self):
        if not self.console_visible:
            self.console_group.show()
            self.console_visible = True

    def toggle_console(self):
        if self.console_visible:
            self.console_group.hide()
            self.console_visible = False
        else:
            self.console_group.show()
            self.console_visible = True

    def clear_console(self):
        self.console.clear()

    def log(self, text):
        self.console.moveCursor(self.console.textCursor().MoveOperation.End)
        self.console.insertPlainText(text)
        self.console.ensureCursorVisible()

    def start_worker(self, task_fn, success_message=""):
        if self.current_worker is not None and self.current_worker.isRunning():
            QMessageBox.warning(
                self,
                tr("scripts_tab.busy_title"),
                tr("scripts_tab.another_task_running"),
            )
            return

        self.show_console()
        self.clear_console()

        self.current_worker = ScriptTaskWorker(task_fn, success_message=success_message)
        self.current_worker.log_line.connect(self.log)
        self.current_worker.success.connect(self.on_worker_success)
        self.current_worker.error.connect(self.on_worker_error)
        self.current_worker.task_result.connect(self.on_worker_result)
        self.current_worker.finished_task.connect(self.on_worker_finished)
        self.current_worker.start()

    def on_worker_success(self, message):
        if message:
            QMessageBox.information(self, tr("scripts_tab.done_title"), message)

    def on_worker_error(self, message):
        self.log(tr("scripts_tab.error_log", message=message))
        QMessageBox.critical(self, tr("common.error"), message.split("\n\n", 1)[0])

    def on_worker_result(self, result):
        if not result:
            return

        if isinstance(result, dict):
            if result.get("action") == "reboot_reconnect":
                self.connection.mark_disconnected()
                self.waiting_for_reboot_reconnect = True
                self.main_window.start_reboot_reconnect_polling()

    def on_worker_finished(self):
        self.current_worker = None

        if self.waiting_for_reboot_reconnect:
            return

        try:
            if self.connection.is_connected():
                self.refresh_status()
            else:
                self.apply_disconnected_state()
        except Exception:
            self.connection.mark_disconnected()
            self.apply_disconnected_state()

    def install_update_all(self):
        if not self.connection.is_connected():
            return

        def task(log):
            install_update_all(self.connection, log)

        self.start_worker(task, tr("scripts_tab.update_all_installed_success"))

    def uninstall_update_all(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("scripts_tab.uninstall_update_all_title"),
            tr("scripts_tab.uninstall_update_all_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        uninstall_update_all(self.connection)
        self.refresh_status()

    def configure_update_all(self):
        if not self.connection.is_connected():
            QMessageBox.critical(
                self,
                tr("common.error"),
                tr("device_tab.not_connected_message"),
            )
            return

        if not self.update_all_installed:
            QMessageBox.critical(
                self,
                tr("scripts_tab.update_all_not_installed_title"),
                tr("scripts_tab.update_all_not_installed_message"),
            )
            return

        try:
            ensure_update_all_config_bootstrap(self.connection)
            self.update_all_initialized = check_update_all_initialized(self.connection)
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("scripts_tab.update_all_config_error_title"),
                tr("scripts_tab.update_all_config_error_message", error=e),
            )
            return

        dialog = UpdateAllConfigDialog(self.connection, self)
        if dialog.exec():
            self.refresh_status()

    def run_update_all(self):
        if not self.connection.is_connected():
            return

        if not self.main_window.config_data.get("hide_update_all_warning", False):
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Question)
            msg.setWindowTitle(tr("scripts_tab.run_update_all_title"))
            msg.setText(tr("scripts_tab.run_update_all_warning"))
            msg.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            msg.setDefaultButton(QMessageBox.StandardButton.Yes)

            dont_show_checkbox = QCheckBox(tr("scripts_tab.dont_show_again"))
            msg.setCheckBox(dont_show_checkbox)

            msg.exec()

            if msg.result() != QMessageBox.StandardButton.Yes:
                return

            if dont_show_checkbox.isChecked():
                self.main_window.config_data["hide_update_all_warning"] = True
                save_config(self.main_window.config_data)

        def task(log):
            import time

            log(tr("scripts_tab.log_running_update_all"))
            run_update_all_stream(self.connection, log)
            log(tr("scripts_tab.log_update_all_finished"))

            time.sleep(7)

            still_connected = False
            try:
                still_connected = self.connection.is_connected()
                if still_connected and self.connection.client:
                    transport = self.connection.client.get_transport()
                    still_connected = bool(transport and transport.is_active())
            except Exception:
                still_connected = False

            if still_connected:
                log(tr("scripts_tab.log_no_reboot_detected"))
                return {"action": "completed"}

            self.connection.mark_disconnected()
            log(tr("scripts_tab.log_mister_disconnected_after_update_all"))
            log(tr("scripts_tab.log_starting_auto_reconnect"))
            return {"action": "reboot_reconnect"}

        self.start_worker(task)

    def install_zaparoo(self):
        if not self.connection.is_connected():
            return

        def task(log):
            install_zaparoo(self.connection, log)

        self.start_worker(task, tr("scripts_tab.zaparoo_installed_success"))

    def enable_zaparoo_service(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("scripts_tab.enable_zaparoo_service_title"),
            tr("scripts_tab.enable_zaparoo_service_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            enable_zaparoo_service(self.connection)
            QMessageBox.information(
                self,
                tr("scripts_tab.zaparoo_enabled_title"),
                tr("scripts_tab.zaparoo_enabled_message"),
            )
            self.refresh_status()
        except Exception as e:
            QMessageBox.critical(self, tr("common.error"), str(e))

    def uninstall_zaparoo(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("scripts_tab.uninstall_zaparoo_title"),
            tr("scripts_tab.uninstall_zaparoo_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        uninstall_zaparoo(self.connection)
        self.refresh_status()

    def install_migrate_sd(self):
        if not self.connection.is_connected():
            return

        proceed = QMessageBox.question(
            self,
            tr("scripts_tab.install_migrate_sd_title"),
            tr("scripts_tab.install_migrate_sd_message"),
        )
        if proceed != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            install_migrate_sd(self.connection, log)

        self.start_worker(task, tr("scripts_tab.migrate_sd_installed_success"))

    def uninstall_migrate_sd(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("scripts_tab.uninstall_migrate_sd_title"),
            tr("scripts_tab.uninstall_migrate_sd_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        uninstall_migrate_sd(self.connection)
        self.show_console()
        self.clear_console()
        self.log(tr("scripts_tab.log_migrate_sd_removed"))
        self.refresh_status()

    def install_cifs_mount(self):
        if not self.connection.is_connected():
            return

        def task(log):
            install_cifs_mount(self.connection, log)

        self.start_worker(task, tr("scripts_tab.cifs_installed_success"))

    def configure_cifs(self):
        if not self.connection.is_connected():
            return

        dialog = CifsConfigDialog(self.connection, self)
        if dialog.exec():
            self.refresh_status()

    def run_cifs_mount(self):
        if not self.connection.is_connected():
            return

        result = run_cifs_mount(self.connection)
        QMessageBox.information(
            self,
            tr("scripts_tab.mount"),
            result or tr("scripts_tab.mount_command_sent"),
        )

    def run_cifs_umount(self):
        if not self.connection.is_connected():
            return

        result = run_cifs_umount(self.connection)
        QMessageBox.information(
            self,
            tr("scripts_tab.unmount"),
            result or tr("scripts_tab.unmount_command_sent"),
        )

    def remove_cifs_config(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("scripts_tab.remove_config"),
            tr("scripts_tab.delete_cifs_config_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        remove_cifs_config(self.connection)
        self.refresh_status()

    def uninstall_cifs_mount(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("scripts_tab.uninstall"),
            tr("scripts_tab.remove_cifs_scripts_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        uninstall_cifs_mount(self.connection)
        self.refresh_status()

    def install_auto_time(self):
        if not self.connection.is_connected():
            return

        def task(log):
            install_auto_time(self.connection, log)

        self.start_worker(task, tr("scripts_tab.generic_script_installed_success"))

    def uninstall_auto_time(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("scripts_tab.uninstall_auto_time_title"),
            tr("scripts_tab.uninstall_auto_time_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        uninstall_auto_time(self.connection)
        self.refresh_status()

    def install_dav_browser(self):
        if not self.connection.is_connected():
            return

        def task(log):
            install_dav_browser(self.connection, log)

        self.start_worker(task, tr("scripts_tab.generic_script_installed_success"))

    def configure_dav_browser(self):
        if not self.connection.is_connected():
            return

        dialog = DavBrowserConfigDialog(self.connection, self)
        if dialog.exec():
            self.refresh_status()

    def remove_dav_browser_config(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("scripts_tab.remove_config"),
            tr("scripts_tab.delete_dav_browser_config_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        remove_dav_browser_config(self.connection)
        self.refresh_status()

    def uninstall_dav_browser(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("scripts_tab.uninstall_dav_browser_title"),
            tr("scripts_tab.uninstall_dav_browser_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        uninstall_dav_browser(self.connection)
        self.refresh_status()

    def install_ftp_save_sync(self):
        if not self.connection.is_connected():
            return

        def task(log):
            install_ftp_save_sync(self.connection, log)

        self.start_worker(task, tr("scripts_tab.ftp_save_sync_installed_success"))

    def configure_ftp_save_sync(self):
        if not self.connection.is_connected():
            return

        dialog = FtpSaveSyncConfigDialog(self.connection, self.main_window, self)
        if dialog.exec():
            self.refresh_status()

    def enable_ftp_save_sync_service(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("scripts_tab.enable_ftp_save_sync_service_title"),
            tr("scripts_tab.enable_ftp_save_sync_service_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            enable_ftp_save_sync_service(self.connection)
            QMessageBox.information(
                self,
                tr("scripts_tab.ftp_save_sync_enabled_title"),
                tr("scripts_tab.ftp_save_sync_enabled_message"),
            )
            self.refresh_status()
        except Exception as e:
            QMessageBox.critical(self, tr("common.error"), str(e))

    def disable_ftp_save_sync_service(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("scripts_tab.disable_ftp_save_sync_service_title"),
            tr("scripts_tab.disable_ftp_save_sync_service_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            disable_ftp_save_sync_service(self.connection)
            QMessageBox.information(
                self,
                tr("scripts_tab.ftp_save_sync_disabled_title"),
                tr("scripts_tab.ftp_save_sync_disabled_message"),
            )
            self.refresh_status()
        except Exception as e:
            QMessageBox.critical(self, tr("common.error"), str(e))

    def remove_ftp_save_sync_config(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("scripts_tab.remove_config"),
            tr("scripts_tab.delete_ftp_save_sync_config_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        remove_ftp_save_sync_config(self.connection)
        self.refresh_status()

    def uninstall_ftp_save_sync(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("scripts_tab.uninstall_ftp_save_sync_title"),
            tr("scripts_tab.uninstall_ftp_save_sync_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        uninstall_ftp_save_sync(self.connection)
        self.refresh_status()

    def install_static_wallpaper(self):
        if not self.connection.is_connected():
            return

        def task(log):
            install_static_wallpaper(self.connection, log)

        self.start_worker(task, tr("scripts_tab.static_wallpaper_installed_success"))

    def uninstall_static_wallpaper(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("scripts_tab.uninstall_static_wallpaper_title"),
            tr("scripts_tab.uninstall_static_wallpaper_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            uninstall_static_wallpaper(self.connection)
            QMessageBox.information(
                self,
                tr("scripts_tab.static_wallpaper_removed_title"),
                tr("scripts_tab.static_wallpaper_removed_message"),
            )
            self.refresh_status()
        except Exception as e:
            QMessageBox.critical(self, tr("common.error"), str(e))

    def open_scripts_folder(self):
        host = self.connection.host
        if not host:
            QMessageBox.warning(
                self,
                tr("scripts_tab.open_scripts_folder"),
                tr("device_tab.no_mister_ip"),
            )
            return

        try:
            open_scripts_folder_on_host(
                ip=host,
                username=self.connection.username,
                password=self.connection.password,
            )
        except Exception as e:
            QMessageBox.critical(self, tr("common.error"), str(e))
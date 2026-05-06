import traceback

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
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

from core.extras_actions import (
    get_3sx_status,
    get_openbor_4086_status,
    get_openbor_7533_status,
    get_pico8_status,
    get_sonic_mania_status,
    get_zaparoo_launcher_status,
    install_or_update_3sx as backend_install_or_update_3sx,
    install_or_update_openbor_4086 as backend_install_or_update_openbor_4086,
    install_or_update_openbor_7533 as backend_install_or_update_openbor_7533,
    install_or_update_pico8 as backend_install_or_update_pico8,
    install_or_update_sonic_mania as backend_install_or_update_sonic_mania,
    install_or_update_zaparoo_launcher as backend_install_or_update_zaparoo_launcher,
    uninstall_3sx as backend_uninstall_3sx,
    uninstall_openbor_4086 as backend_uninstall_openbor_4086,
    uninstall_openbor_7533 as backend_uninstall_openbor_7533,
    uninstall_pico8 as backend_uninstall_pico8,
    uninstall_sonic_mania as backend_uninstall_sonic_mania,
    uninstall_zaparoo_launcher as backend_uninstall_zaparoo_launcher,
    upload_3sx_afs as backend_upload_3sx_afs,
    upload_sonic_mania_data_rsdk as backend_upload_sonic_mania_data_rsdk,
)

from core.extras_ra_cores import (
    get_ra_cores_status,
    install_or_update_ra_cores as backend_install_or_update_ra_cores,
    uninstall_ra_cores as backend_uninstall_ra_cores,
)

from ui.dialogs.ra_cores_config_dialog import RetroAchievementsConfigDialog


class ExtraTaskWorker(QThread):
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


class ExtrasTab(QWidget):
    EXTRA_3SX = "3sx_mister"
    EXTRA_PICO8 = "mister_pico8"
    EXTRA_OPENBOR_4086 = "mister_openbor_4086"
    EXTRA_OPENBOR_7533 = "mister_openbor_7533"
    EXTRA_SONIC_MANIA = "sonic_mania_mister"
    EXTRA_ZAPAROO_LAUNCHER = "zaparoo_launcher_ui_beta"
    EXTRA_RA_CORES = "retroachievement_cores"

    TASK_CHECK_3SX = "check_updates_3sx"
    TASK_CHECK_PICO8 = "check_updates_pico8"
    TASK_CHECK_OPENBOR_4086 = "check_updates_openbor_4086"
    TASK_CHECK_OPENBOR_7533 = "check_updates_openbor_7533"
    TASK_CHECK_SONIC_MANIA = "check_updates_sonic_mania"
    TASK_CHECK_ZAPAROO_LAUNCHER = "check_updates_zaparoo_launcher"
    TASK_CHECK_RA_CORES = "check_updates_ra_cores"

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection

        self.console_visible = False
        self.current_worker = None
        self.current_task_kind = None
        self.current_check_result = None
        self.ra_cores_show_install_info_after_success = False
        self.zaparoo_launcher_show_reboot_after_success = False

        self.extra_display_order = [
            self.EXTRA_3SX,
            self.EXTRA_PICO8,
            self.EXTRA_OPENBOR_4086,
            self.EXTRA_OPENBOR_7533,
            self.EXTRA_SONIC_MANIA,
            self.EXTRA_ZAPAROO_LAUNCHER,
            self.EXTRA_RA_CORES,
        ]

        self.extra_titles = {
            self.EXTRA_3SX: "3S-ARM",
            self.EXTRA_PICO8: "MiSTer Pico-8",
            self.EXTRA_OPENBOR_4086: "MiSTer OpenBOR 4086",
            self.EXTRA_OPENBOR_7533: "MiSTer OpenBOR 7533",
            self.EXTRA_SONIC_MANIA: "Sonic Mania MiSTer",
            self.EXTRA_ZAPAROO_LAUNCHER: "Zaparoo Launcher/UI Beta",
            self.EXTRA_RA_CORES: "RetroAchievement Cores",
        }

        self.extra_descriptions = {
            self.EXTRA_3SX: (
                "Install, update, migrate legacy 3SX installs, upload SF33RD.AFS, "
                "and uninstall 3s-mister-arm directly from MiSTer Companion."
            ),
            self.EXTRA_PICO8: (
                "Install, update, and uninstall MiSTer Pico-8 directly from MiSTer Companion."
            ),
            self.EXTRA_OPENBOR_4086: (
                "Install, update, and uninstall MiSTer OpenBOR 4086 directly from "
                "MiSTer Companion. The Paks folder is preserved when uninstalling."
            ),
            self.EXTRA_OPENBOR_7533: (
                "Install, update, and uninstall MiSTer OpenBOR 7533 directly from "
                "MiSTer Companion. The Paks folder is preserved when uninstalling."
            ),
            self.EXTRA_SONIC_MANIA: (
                "Install, update, upload Data.rsdk, and uninstall Sonic Mania MiSTer "
                "directly from MiSTer Companion."
            ),
            self.EXTRA_ZAPAROO_LAUNCHER: (
                "Install, update, and uninstall the Zaparoo Launcher/UI Beta. "
                "This installs the beta launcher files, temporarily swaps in the "
                "launcher dev zaparoo.sh, updates MiSTer.ini, and requires a reboot."
            ),
            self.EXTRA_RA_CORES: (
                "Install, update, migrate legacy installs, configure, and uninstall "
                "RetroAchievement-enabled MiSTer support files and supported RA cores. "
                "Uses MGL launchers so normal cores remain untouched."
            ),
        }

        self.extra_status_texts = {
            self.EXTRA_3SX: "Unknown",
            self.EXTRA_PICO8: "Unknown",
            self.EXTRA_OPENBOR_4086: "Unknown",
            self.EXTRA_OPENBOR_7533: "Unknown",
            self.EXTRA_SONIC_MANIA: "Unknown",
            self.EXTRA_ZAPAROO_LAUNCHER: "Unknown",
            self.EXTRA_RA_CORES: "Unknown",
        }

        self.selected_extra_key = self.EXTRA_3SX

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

        list_group = QGroupBox("Extras")
        list_layout = QVBoxLayout()
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)

        self.extra_list = QListWidget()
        self.extra_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.extra_list.setAlternatingRowColors(False)
        self.extra_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.extra_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.extra_list.setMinimumWidth(290)
        self.extra_list.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.extra_list.setStyleSheet(
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
        list_layout.addWidget(self.extra_list)

        list_group.setLayout(list_layout)
        top_row.addWidget(list_group, 1)

        details_group = QGroupBox("Details")
        details_layout = QVBoxLayout()
        details_layout.setContentsMargins(14, 14, 14, 14)
        details_layout.setSpacing(10)

        self.extra_name_label = QLabel("Select an extra")
        font = self.extra_name_label.font()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        self.extra_name_label.setFont(font)
        details_layout.addWidget(self.extra_name_label)

        self.extra_status_label = QLabel("Status: Unknown")
        self.extra_status_label.setStyleSheet("color: gray;")
        details_layout.addWidget(self.extra_status_label)

        self.extra_description_label = QLabel("")
        self.extra_description_label.setWordWrap(True)
        self.extra_description_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.extra_description_label.setMinimumHeight(54)
        details_layout.addWidget(self.extra_description_label)

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

        self.threesx_actions_widget = self._build_3sx_actions()
        self.pico8_actions_widget = self._build_pico8_actions()
        self.openbor_4086_actions_widget = self._build_openbor_4086_actions()
        self.openbor_7533_actions_widget = self._build_openbor_7533_actions()
        self.sonic_mania_actions_widget = self._build_sonic_mania_actions()
        self.zaparoo_launcher_actions_widget = self._build_zaparoo_launcher_actions()
        self.ra_cores_actions_widget = self._build_ra_cores_actions()

        self.extra_action_widgets = {
            self.EXTRA_3SX: self.threesx_actions_widget,
            self.EXTRA_PICO8: self.pico8_actions_widget,
            self.EXTRA_OPENBOR_4086: self.openbor_4086_actions_widget,
            self.EXTRA_OPENBOR_7533: self.openbor_7533_actions_widget,
            self.EXTRA_SONIC_MANIA: self.sonic_mania_actions_widget,
            self.EXTRA_ZAPAROO_LAUNCHER: self.zaparoo_launcher_actions_widget,
            self.EXTRA_RA_CORES: self.ra_cores_actions_widget,
        }

        for widget in self.extra_action_widgets.values():
            widget.hide()
            self.action_buttons_layout.addWidget(widget)

        self.action_buttons_layout.addStretch()

        details_group.setLayout(details_layout)
        top_row.addWidget(details_group, 2)

        self.console_group = QGroupBox("SSH Output")
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

        self._populate_extra_list()
        self._select_initial_extra()

        self.extra_list.currentItemChanged.connect(self.on_extra_selection_changed)

        self.install_update_3sx_button.clicked.connect(self.install_or_update_3sx)
        self.check_updates_3sx_button.clicked.connect(self.check_3sx_updates)
        self.upload_afs_button.clicked.connect(self.upload_sf33rd_afs)
        self.uninstall_3sx_button.clicked.connect(self.uninstall_3sx)

        self.install_update_pico8_button.clicked.connect(self.install_or_update_pico8)
        self.check_updates_pico8_button.clicked.connect(self.check_pico8_updates)
        self.uninstall_pico8_button.clicked.connect(self.uninstall_pico8)

        self.install_update_openbor_4086_button.clicked.connect(
            self.install_or_update_openbor_4086
        )
        self.check_updates_openbor_4086_button.clicked.connect(
            self.check_openbor_4086_updates
        )
        self.uninstall_openbor_4086_button.clicked.connect(self.uninstall_openbor_4086)

        self.install_update_openbor_7533_button.clicked.connect(
            self.install_or_update_openbor_7533
        )
        self.check_updates_openbor_7533_button.clicked.connect(
            self.check_openbor_7533_updates
        )
        self.uninstall_openbor_7533_button.clicked.connect(self.uninstall_openbor_7533)

        self.install_update_sonic_mania_button.clicked.connect(
            self.install_or_update_sonic_mania
        )
        self.check_updates_sonic_mania_button.clicked.connect(
            self.check_sonic_mania_updates
        )
        self.upload_data_rsdk_button.clicked.connect(self.upload_sonic_mania_data_rsdk)
        self.uninstall_sonic_mania_button.clicked.connect(self.uninstall_sonic_mania)

        self.install_update_zaparoo_launcher_button.clicked.connect(
            self.install_or_update_zaparoo_launcher
        )
        self.check_updates_zaparoo_launcher_button.clicked.connect(
            self.check_zaparoo_launcher_updates
        )
        self.uninstall_zaparoo_launcher_button.clicked.connect(
            self.uninstall_zaparoo_launcher
        )

        self.install_update_ra_cores_button.clicked.connect(self.install_or_update_ra_cores)
        self.check_updates_ra_cores_button.clicked.connect(self.check_ra_cores_updates)
        self.edit_ra_cores_config_button.clicked.connect(self.edit_ra_cores_config)
        self.uninstall_ra_cores_button.clicked.connect(self.uninstall_ra_cores)

        self.hide_console_button.clicked.connect(self.toggle_console)

    def _build_button_row(self, *buttons):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch()
        for button in buttons:
            row.addWidget(button)
        row.addStretch()
        return row

    def _build_3sx_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_update_3sx_button = QPushButton("Install")
        self.install_update_3sx_button.setFixedWidth(170)

        self.check_updates_3sx_button = QPushButton("Check for Updates")
        self.check_updates_3sx_button.setFixedWidth(170)

        self.upload_afs_button = QPushButton("Upload SF33RD.AFS")
        self.upload_afs_button.setFixedWidth(190)

        self.uninstall_3sx_button = QPushButton("Uninstall")
        self.uninstall_3sx_button.setFixedWidth(170)

        layout.addLayout(
            self._build_button_row(
                self.install_update_3sx_button,
                self.check_updates_3sx_button,
            )
        )
        layout.addLayout(
            self._build_button_row(
                self.upload_afs_button,
                self.uninstall_3sx_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_pico8_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_update_pico8_button = QPushButton("Install")
        self.install_update_pico8_button.setFixedWidth(170)

        self.check_updates_pico8_button = QPushButton("Check for Updates")
        self.check_updates_pico8_button.setFixedWidth(170)

        self.uninstall_pico8_button = QPushButton("Uninstall")
        self.uninstall_pico8_button.setFixedWidth(170)

        layout.addLayout(
            self._build_button_row(
                self.install_update_pico8_button,
                self.check_updates_pico8_button,
            )
        )
        layout.addLayout(
            self._build_button_row(
                self.uninstall_pico8_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_openbor_4086_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_update_openbor_4086_button = QPushButton("Install")
        self.install_update_openbor_4086_button.setFixedWidth(170)

        self.check_updates_openbor_4086_button = QPushButton("Check for Updates")
        self.check_updates_openbor_4086_button.setFixedWidth(170)

        self.uninstall_openbor_4086_button = QPushButton("Uninstall")
        self.uninstall_openbor_4086_button.setFixedWidth(170)

        layout.addLayout(
            self._build_button_row(
                self.install_update_openbor_4086_button,
                self.check_updates_openbor_4086_button,
            )
        )
        layout.addLayout(
            self._build_button_row(
                self.uninstall_openbor_4086_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_openbor_7533_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_update_openbor_7533_button = QPushButton("Install")
        self.install_update_openbor_7533_button.setFixedWidth(170)

        self.check_updates_openbor_7533_button = QPushButton("Check for Updates")
        self.check_updates_openbor_7533_button.setFixedWidth(170)

        self.uninstall_openbor_7533_button = QPushButton("Uninstall")
        self.uninstall_openbor_7533_button.setFixedWidth(170)

        layout.addLayout(
            self._build_button_row(
                self.install_update_openbor_7533_button,
                self.check_updates_openbor_7533_button,
            )
        )
        layout.addLayout(
            self._build_button_row(
                self.uninstall_openbor_7533_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_sonic_mania_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_update_sonic_mania_button = QPushButton("Install")
        self.install_update_sonic_mania_button.setFixedWidth(170)

        self.check_updates_sonic_mania_button = QPushButton("Check for Updates")
        self.check_updates_sonic_mania_button.setFixedWidth(170)

        self.upload_data_rsdk_button = QPushButton("Upload Data.rsdk")
        self.upload_data_rsdk_button.setFixedWidth(190)

        self.uninstall_sonic_mania_button = QPushButton("Uninstall")
        self.uninstall_sonic_mania_button.setFixedWidth(170)

        layout.addLayout(
            self._build_button_row(
                self.install_update_sonic_mania_button,
                self.check_updates_sonic_mania_button,
            )
        )
        layout.addLayout(
            self._build_button_row(
                self.upload_data_rsdk_button,
                self.uninstall_sonic_mania_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_zaparoo_launcher_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_update_zaparoo_launcher_button = QPushButton("Install")
        self.install_update_zaparoo_launcher_button.setFixedWidth(170)

        self.check_updates_zaparoo_launcher_button = QPushButton("Check for Updates")
        self.check_updates_zaparoo_launcher_button.setFixedWidth(170)

        self.uninstall_zaparoo_launcher_button = QPushButton("Uninstall")
        self.uninstall_zaparoo_launcher_button.setFixedWidth(170)

        layout.addLayout(
            self._build_button_row(
                self.install_update_zaparoo_launcher_button,
                self.check_updates_zaparoo_launcher_button,
            )
        )
        layout.addLayout(
            self._build_button_row(
                self.uninstall_zaparoo_launcher_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _build_ra_cores_actions(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.install_update_ra_cores_button = QPushButton("Install")
        self.install_update_ra_cores_button.setFixedWidth(170)

        self.check_updates_ra_cores_button = QPushButton("Check for Updates")
        self.check_updates_ra_cores_button.setFixedWidth(170)

        self.edit_ra_cores_config_button = QPushButton("Edit Config")
        self.edit_ra_cores_config_button.setFixedWidth(170)

        self.uninstall_ra_cores_button = QPushButton("Uninstall")
        self.uninstall_ra_cores_button.setFixedWidth(170)

        layout.addLayout(
            self._build_button_row(
                self.install_update_ra_cores_button,
                self.check_updates_ra_cores_button,
            )
        )
        layout.addLayout(
            self._build_button_row(
                self.edit_ra_cores_config_button,
                self.uninstall_ra_cores_button,
            )
        )

        widget.setLayout(layout)
        return widget

    def _populate_extra_list(self):
        self.extra_list.clear()
        for extra_key in self.extra_display_order:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, extra_key)
            self.extra_list.addItem(item)
        self.update_extra_list_labels()

    def _select_initial_extra(self):
        if self.extra_list.count() > 0:
            self.extra_list.setCurrentRow(0)

    def _get_current_extra_key(self):
        item = self.extra_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def on_extra_selection_changed(self, current, previous):
        del previous
        if current is None:
            return

        extra_key = current.data(Qt.ItemDataRole.UserRole)
        self.selected_extra_key = extra_key
        self.update_details_panel()

    def update_details_panel(self):
        extra_key = self.selected_extra_key
        if not extra_key:
            self.extra_name_label.setText("Select an extra")
            self.extra_status_label.setText("Status: Unknown")
            self.extra_status_label.setStyleSheet("color: gray;")
            self.extra_description_label.setText("")
            for widget in self.extra_action_widgets.values():
                widget.hide()
            return

        self.extra_name_label.setText(self.extra_titles.get(extra_key, extra_key))
        self.extra_description_label.setText(self.extra_descriptions.get(extra_key, ""))

        status_text = self.extra_status_texts.get(extra_key, "Unknown")
        self.extra_status_label.setText(f"Status: {status_text}")

        lowered = status_text.lower()
        if "update available" in lowered:
            self.extra_status_label.setStyleSheet("color: #cc8400;")
        elif "legacy" in lowered or "missing" in lowered:
            self.extra_status_label.setStyleSheet("color: #cc8400;")
        elif "installed" in lowered and "not" not in lowered:
            self.extra_status_label.setStyleSheet("color: #00aa00;")
        elif "not installed" in lowered:
            self.extra_status_label.setStyleSheet("color: #cc0000;")
        else:
            self.extra_status_label.setStyleSheet("color: gray;")

        for key, widget in self.extra_action_widgets.items():
            widget.setVisible(key == extra_key)

    def update_extra_list_labels(self):
        for index in range(self.extra_list.count()):
            item = self.extra_list.item(index)
            extra_key = item.data(Qt.ItemDataRole.UserRole)
            title = self.extra_titles.get(extra_key, extra_key)
            status = self.extra_status_texts.get(extra_key, "Unknown")
            item.setText(f"{title}    {status}")

    def update_connection_state(self):
        if self.connection.is_connected():
            self.apply_connected_state()
        else:
            self.apply_disconnected_state()

    def apply_connected_state(self):
        if self.current_worker is not None and self.current_worker.isRunning():
            return
        self.refresh_status()

    def apply_disconnected_state(self):
        self.ra_cores_show_install_info_after_success = False
        self.zaparoo_launcher_show_reboot_after_success = False

        for button in [
            self.install_update_3sx_button,
            self.check_updates_3sx_button,
            self.upload_afs_button,
            self.uninstall_3sx_button,
            self.install_update_pico8_button,
            self.check_updates_pico8_button,
            self.uninstall_pico8_button,
            self.install_update_openbor_4086_button,
            self.check_updates_openbor_4086_button,
            self.uninstall_openbor_4086_button,
            self.install_update_openbor_7533_button,
            self.check_updates_openbor_7533_button,
            self.uninstall_openbor_7533_button,
            self.install_update_sonic_mania_button,
            self.check_updates_sonic_mania_button,
            self.upload_data_rsdk_button,
            self.uninstall_sonic_mania_button,
            self.install_update_zaparoo_launcher_button,
            self.check_updates_zaparoo_launcher_button,
            self.uninstall_zaparoo_launcher_button,
            self.install_update_ra_cores_button,
            self.check_updates_ra_cores_button,
            self.edit_ra_cores_config_button,
            self.uninstall_ra_cores_button,
        ]:
            button.setEnabled(False)

        self.install_update_3sx_button.setText("Install")
        self.install_update_pico8_button.setText("Install")
        self.install_update_openbor_4086_button.setText("Install")
        self.install_update_openbor_7533_button.setText("Install")
        self.install_update_sonic_mania_button.setText("Install")
        self.install_update_zaparoo_launcher_button.setText("Install")
        self.install_update_ra_cores_button.setText("Install")

        self.extra_status_texts[self.EXTRA_3SX] = "Unknown"
        self.extra_status_texts[self.EXTRA_PICO8] = "Unknown"
        self.extra_status_texts[self.EXTRA_OPENBOR_4086] = "Unknown"
        self.extra_status_texts[self.EXTRA_OPENBOR_7533] = "Unknown"
        self.extra_status_texts[self.EXTRA_SONIC_MANIA] = "Unknown"
        self.extra_status_texts[self.EXTRA_ZAPAROO_LAUNCHER] = "Unknown"
        self.extra_status_texts[self.EXTRA_RA_CORES] = "Unknown"

        self.update_extra_list_labels()
        self.update_details_panel()

    def refresh_status(self):
        if not self.connection.is_connected():
            self.apply_disconnected_state()
            return

        status_checks = [
            (
                self.EXTRA_3SX,
                get_3sx_status,
                self.install_update_3sx_button,
                self.check_updates_3sx_button,
                [self.upload_afs_button, self.uninstall_3sx_button],
            ),
            (
                self.EXTRA_PICO8,
                get_pico8_status,
                self.install_update_pico8_button,
                self.check_updates_pico8_button,
                [self.uninstall_pico8_button],
            ),
            (
                self.EXTRA_OPENBOR_4086,
                get_openbor_4086_status,
                self.install_update_openbor_4086_button,
                self.check_updates_openbor_4086_button,
                [self.uninstall_openbor_4086_button],
            ),
            (
                self.EXTRA_OPENBOR_7533,
                get_openbor_7533_status,
                self.install_update_openbor_7533_button,
                self.check_updates_openbor_7533_button,
                [self.uninstall_openbor_7533_button],
            ),
            (
                self.EXTRA_SONIC_MANIA,
                get_sonic_mania_status,
                self.install_update_sonic_mania_button,
                self.check_updates_sonic_mania_button,
                [self.upload_data_rsdk_button, self.uninstall_sonic_mania_button],
            ),
            (
                self.EXTRA_ZAPAROO_LAUNCHER,
                get_zaparoo_launcher_status,
                self.install_update_zaparoo_launcher_button,
                self.check_updates_zaparoo_launcher_button,
                [self.uninstall_zaparoo_launcher_button],
            ),
            (
                self.EXTRA_RA_CORES,
                get_ra_cores_status,
                self.install_update_ra_cores_button,
                self.check_updates_ra_cores_button,
                [self.edit_ra_cores_config_button, self.uninstall_ra_cores_button],
            ),
        ]

        for extra_key, status_fn, install_button, check_button, other_buttons in status_checks:
            try:
                status = status_fn(self.connection)
            except Exception as e:
                self.extra_status_texts[extra_key] = f"Unknown ({e})"
                install_button.setText("Install")
                install_button.setEnabled(False)
                check_button.setEnabled(False)
                for button in other_buttons:
                    button.setEnabled(False)
            else:
                self._apply_status_result_for_extra(extra_key, status)

        self.update_extra_list_labels()
        self.update_details_panel()

    def append_console_line(self, text):
        if text.startswith("[PROGRESS] "):
            progress_text = text[len("[PROGRESS] "):]
            lines = self.console.toPlainText().splitlines()

            if lines:
                if lines[-1].startswith("Upload progress:"):
                    lines[-1] = f"Upload progress: {progress_text}"
                else:
                    lines.append(f"Upload progress: {progress_text}")
            else:
                lines = [f"Upload progress: {progress_text}"]

            self.console.setPlainText("\n".join(lines))
        else:
            self.console.append(text)

        self.console.ensureCursorVisible()

    def show_console(self):
        if not self.console_visible:
            self.console_group.show()
            self.console_visible = True

    def hide_console(self):
        if self.console_visible:
            self.console_group.hide()
            self.console_visible = False

    def toggle_console(self):
        if self.console_visible:
            self.hide_console()
        else:
            self.show_console()

    def _run_worker(self, task_fn, success_message="", task_kind=None):
        if self.current_worker is not None and self.current_worker.isRunning():
            return

        self.show_console()
        self.console.clear()

        self.current_task_kind = task_kind
        self.current_check_result = None

        self.current_worker = ExtraTaskWorker(task_fn, success_message)
        self.current_worker.log_line.connect(self.append_console_line)
        self.current_worker.success.connect(self.on_worker_success)
        self.current_worker.error.connect(self.on_worker_error)
        self.current_worker.finished_task.connect(self.on_worker_finished)
        self.current_worker.task_result.connect(self.on_worker_result)

        self.extra_list.setEnabled(False)

        for button in [
            self.install_update_3sx_button,
            self.check_updates_3sx_button,
            self.upload_afs_button,
            self.uninstall_3sx_button,
            self.install_update_pico8_button,
            self.check_updates_pico8_button,
            self.uninstall_pico8_button,
            self.install_update_openbor_4086_button,
            self.check_updates_openbor_4086_button,
            self.uninstall_openbor_4086_button,
            self.install_update_openbor_7533_button,
            self.check_updates_openbor_7533_button,
            self.uninstall_openbor_7533_button,
            self.install_update_sonic_mania_button,
            self.check_updates_sonic_mania_button,
            self.upload_data_rsdk_button,
            self.uninstall_sonic_mania_button,
            self.install_update_zaparoo_launcher_button,
            self.check_updates_zaparoo_launcher_button,
            self.uninstall_zaparoo_launcher_button,
            self.install_update_ra_cores_button,
            self.check_updates_ra_cores_button,
            self.edit_ra_cores_config_button,
            self.uninstall_ra_cores_button,
        ]:
            button.setEnabled(False)

        self.current_worker.start()

    def on_worker_success(self, message):
        if message:
            self.append_console_line("")
            self.append_console_line(message)

        if (
            message in {
                "RetroAchievement Cores installed.",
                "RetroAchievement Cores migrated.",
            }
            and self.ra_cores_show_install_info_after_success
        ):
            self.ra_cores_show_install_info_after_success = False
            self.show_ra_cores_install_info()

        if (
            message in {
                "Zaparoo Launcher/UI Beta installed.",
                "Zaparoo Launcher/UI Beta updated.",
                "Zaparoo Launcher/UI Beta uninstalled.",
            }
            and self.zaparoo_launcher_show_reboot_after_success
        ):
            self.zaparoo_launcher_show_reboot_after_success = False
            self.prompt_zaparoo_launcher_reboot_required()

    def on_worker_error(self, message):
        self.ra_cores_show_install_info_after_success = False
        self.zaparoo_launcher_show_reboot_after_success = False

        self.append_console_line("")
        self.append_console_line("Error:")
        self.append_console_line(message)
        QMessageBox.warning(self, "Extras", message)

    def on_worker_finished(self):
        task_kind = self.current_task_kind
        check_result = self.current_check_result

        self.current_worker = None
        self.current_task_kind = None
        self.current_check_result = None
        self.extra_list.setEnabled(True)

        if self._is_check_updates_task(task_kind):
            extra_key = self._extra_key_for_check_task(task_kind)

            self.refresh_status()

            if extra_key and isinstance(check_result, dict):
                self._apply_status_result_for_extra(extra_key, check_result)
                self.update_extra_list_labels()
                self.update_details_panel()

            return

        self.refresh_status()

    def on_worker_result(self, result):
        task_kind = self.current_task_kind

        if not self._is_check_updates_task(task_kind):
            return

        if not isinstance(result, dict):
            return

        required_keys = {
            "status_text",
            "install_label",
            "install_enabled",
            "uninstall_enabled",
        }

        if not required_keys.issubset(result.keys()):
            return

        extra_key = self._extra_key_for_check_task(task_kind)
        if not extra_key:
            return

        self.current_check_result = result

        self._apply_status_result_for_extra(extra_key, result)
        self.update_extra_list_labels()
        self.update_details_panel()

        title = self.extra_titles.get(extra_key, "Extra")

        if result.get("update_available"):
            self.append_console_line("Update available.")
            QMessageBox.information(
                self,
                title,
                f"An update is available for {title}.",
            )
            return

        if result.get("latest_error"):
            self.append_console_line(f"Update check failed: {result['latest_error']}")
            QMessageBox.warning(
                self,
                title,
                f"Failed to check for updates:\n\n{result['latest_error']}",
            )
            return

        self.append_console_line(f"{title} is up to date.")
        QMessageBox.information(
            self,
            title,
            f"{title} is up to date.",
        )

    def _is_check_updates_task(self, task_kind):
        return task_kind in {
            self.TASK_CHECK_3SX,
            self.TASK_CHECK_PICO8,
            self.TASK_CHECK_OPENBOR_4086,
            self.TASK_CHECK_OPENBOR_7533,
            self.TASK_CHECK_SONIC_MANIA,
            self.TASK_CHECK_ZAPAROO_LAUNCHER,
            self.TASK_CHECK_RA_CORES,
        }

    def _extra_key_for_check_task(self, task_kind):
        return {
            self.TASK_CHECK_3SX: self.EXTRA_3SX,
            self.TASK_CHECK_PICO8: self.EXTRA_PICO8,
            self.TASK_CHECK_OPENBOR_4086: self.EXTRA_OPENBOR_4086,
            self.TASK_CHECK_OPENBOR_7533: self.EXTRA_OPENBOR_7533,
            self.TASK_CHECK_SONIC_MANIA: self.EXTRA_SONIC_MANIA,
            self.TASK_CHECK_ZAPAROO_LAUNCHER: self.EXTRA_ZAPAROO_LAUNCHER,
            self.TASK_CHECK_RA_CORES: self.EXTRA_RA_CORES,
        }.get(task_kind)

    def _apply_status_result_for_extra(self, extra_key, result):
        self.extra_status_texts[extra_key] = result["status_text"]

        if extra_key == self.EXTRA_3SX:
            self.install_update_3sx_button.setText(result["install_label"])
            self.install_update_3sx_button.setEnabled(result["install_enabled"])
            self.check_updates_3sx_button.setEnabled(result.get("installed", False))
            self.upload_afs_button.setEnabled(result.get("upload_enabled", False))
            self.uninstall_3sx_button.setEnabled(result["uninstall_enabled"])

        elif extra_key == self.EXTRA_PICO8:
            self.install_update_pico8_button.setText(result["install_label"])
            self.install_update_pico8_button.setEnabled(result["install_enabled"])
            self.check_updates_pico8_button.setEnabled(result.get("installed", False))
            self.uninstall_pico8_button.setEnabled(result["uninstall_enabled"])

        elif extra_key == self.EXTRA_OPENBOR_4086:
            self.install_update_openbor_4086_button.setText(result["install_label"])
            self.install_update_openbor_4086_button.setEnabled(result["install_enabled"])
            self.check_updates_openbor_4086_button.setEnabled(
                result.get("installed", False)
            )
            self.uninstall_openbor_4086_button.setEnabled(result["uninstall_enabled"])

        elif extra_key == self.EXTRA_OPENBOR_7533:
            self.install_update_openbor_7533_button.setText(result["install_label"])
            self.install_update_openbor_7533_button.setEnabled(result["install_enabled"])
            self.check_updates_openbor_7533_button.setEnabled(
                result.get("installed", False)
            )
            self.uninstall_openbor_7533_button.setEnabled(result["uninstall_enabled"])

        elif extra_key == self.EXTRA_SONIC_MANIA:
            self.install_update_sonic_mania_button.setText(result["install_label"])
            self.install_update_sonic_mania_button.setEnabled(result["install_enabled"])
            self.check_updates_sonic_mania_button.setEnabled(
                result.get("installed", False)
            )
            self.upload_data_rsdk_button.setEnabled(result.get("upload_enabled", False))
            self.uninstall_sonic_mania_button.setEnabled(result["uninstall_enabled"])

        elif extra_key == self.EXTRA_ZAPAROO_LAUNCHER:
            self.install_update_zaparoo_launcher_button.setText(result["install_label"])
            self.install_update_zaparoo_launcher_button.setEnabled(
                result["install_enabled"]
            )
            self.check_updates_zaparoo_launcher_button.setEnabled(
                result.get("installed", False)
            )
            self.uninstall_zaparoo_launcher_button.setEnabled(
                result["uninstall_enabled"]
            )

        elif extra_key == self.EXTRA_RA_CORES:
            self.install_update_ra_cores_button.setText(result["install_label"])
            self.install_update_ra_cores_button.setEnabled(result["install_enabled"])
            self.check_updates_ra_cores_button.setEnabled(result.get("installed", False))
            self.edit_ra_cores_config_button.setEnabled(
                result.get("edit_config_enabled", False)
            )
            self.uninstall_ra_cores_button.setEnabled(result["uninstall_enabled"])

    def check_3sx_updates(self):
        if not self.connection.is_connected():
            return

        def task(log):
            log("Checking 3S-ARM updates...\n")
            return get_3sx_status(self.connection, check_latest=True)

        self._run_worker(task, "", task_kind=self.TASK_CHECK_3SX)

    def check_pico8_updates(self):
        if not self.connection.is_connected():
            return

        def task(log):
            log("Checking MiSTer Pico-8 updates...\n")
            return get_pico8_status(self.connection, check_latest=True)

        self._run_worker(task, "", task_kind=self.TASK_CHECK_PICO8)

    def check_openbor_4086_updates(self):
        if not self.connection.is_connected():
            return

        def task(log):
            log("Checking MiSTer OpenBOR 4086 updates...\n")
            return get_openbor_4086_status(self.connection, check_latest=True)

        self._run_worker(task, "", task_kind=self.TASK_CHECK_OPENBOR_4086)

    def check_openbor_7533_updates(self):
        if not self.connection.is_connected():
            return

        def task(log):
            log("Checking MiSTer OpenBOR 7533 updates...\n")
            return get_openbor_7533_status(self.connection, check_latest=True)

        self._run_worker(task, "", task_kind=self.TASK_CHECK_OPENBOR_7533)

    def check_sonic_mania_updates(self):
        if not self.connection.is_connected():
            return

        def task(log):
            log("Checking Sonic Mania MiSTer updates...\n")
            return get_sonic_mania_status(self.connection, check_latest=True)

        self._run_worker(task, "", task_kind=self.TASK_CHECK_SONIC_MANIA)

    def check_zaparoo_launcher_updates(self):
        if not self.connection.is_connected():
            return

        def task(log):
            log("Checking Zaparoo Launcher/UI Beta updates...\n")
            return get_zaparoo_launcher_status(self.connection, check_latest=True)

        self._run_worker(
            task,
            "",
            task_kind=self.TASK_CHECK_ZAPAROO_LAUNCHER,
        )

    def check_ra_cores_updates(self):
        if not self.connection.is_connected():
            return

        def task(log):
            log("Checking RetroAchievement Cores updates...\n")
            return get_ra_cores_status(
                self.connection,
                check_latest=True,
            )

        self._run_worker(
            task,
            "",
            task_kind=self.TASK_CHECK_RA_CORES,
        )

    def install_or_update_3sx(self):
        if not self.connection.is_connected():
            return

        button_text = self.install_update_3sx_button.text().strip()
        success_message = "3S-ARM installed."

        if button_text == "Update":
            success_message = "3S-ARM updated."
        elif button_text == "Migrate / Install":
            success_message = "Legacy 3SX install migrated to 3S-ARM."

        def task(log):
            return backend_install_or_update_3sx(self.connection, log)

        self._run_worker(task, success_message)

    def upload_sf33rd_afs(self):
        if not self.connection.is_connected():
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SF33RD.AFS",
            "",
            "AFS Files (SF33RD.AFS *.afs *.AFS);;All Files (*)",
        )
        if not file_path:
            return

        def task(log):
            log(f"Selected file: {file_path}")
            return backend_upload_3sx_afs(self.connection, file_path, log)

        self._run_worker(task, "SF33RD.AFS uploaded.")

    def uninstall_3sx(self):
        if not self.connection.is_connected():
            return

        reply = QMessageBox.question(
            self,
            "Uninstall 3S-ARM",
            "Remove 3S-ARM, legacy 3SX files if present, SF33RD.AFS, and the MiSTer.ini entry?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            return backend_uninstall_3sx(self.connection, log)

        self._run_worker(task, "3S-ARM uninstalled.")

    def install_or_update_pico8(self):
        if not self.connection.is_connected():
            return

        button_text = self.install_update_pico8_button.text().strip()
        success_message = "MiSTer Pico-8 installed."

        if button_text == "Update":
            success_message = "MiSTer Pico-8 updated."
        elif button_text == "Migrate / Install":
            success_message = "Legacy MiSTer Pico-8 install migrated."

        def task(log):
            return backend_install_or_update_pico8(self.connection, log)

        self._run_worker(task, success_message)

    def uninstall_pico8(self):
        if not self.connection.is_connected():
            return

        reply = QMessageBox.question(
            self,
            "Uninstall MiSTer Pico-8",
            "Remove MiSTer Pico-8 files, PICO-8 input map files, and the user-startup.sh daemon entry?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            return backend_uninstall_pico8(self.connection, log)

        self._run_worker(task, "MiSTer Pico-8 uninstalled.")

    def install_or_update_openbor_4086(self):
        if not self.connection.is_connected():
            return

        button_text = self.install_update_openbor_4086_button.text().strip()
        success_message = "MiSTer OpenBOR 4086 installed."

        if button_text == "Update":
            success_message = "MiSTer OpenBOR 4086 updated."

        def task(log):
            return backend_install_or_update_openbor_4086(self.connection, log)

        self._run_worker(task, success_message)

    def uninstall_openbor_4086(self):
        if not self.connection.is_connected():
            return

        reply = QMessageBox.question(
            self,
            "Uninstall MiSTer OpenBOR 4086",
            (
                "Remove MiSTer OpenBOR 4086 engine files, RBF files, documentation, "
                "install script, and the user-startup.sh daemon entry?\n\n"
                "Your Paks folder should be left in place."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            return backend_uninstall_openbor_4086(self.connection, log)

        self._run_worker(task, "MiSTer OpenBOR 4086 uninstalled.")

    def install_or_update_openbor_7533(self):
        if not self.connection.is_connected():
            return

        button_text = self.install_update_openbor_7533_button.text().strip()
        success_message = "MiSTer OpenBOR 7533 installed."

        if button_text == "Update":
            success_message = "MiSTer OpenBOR 7533 updated."

        def task(log):
            return backend_install_or_update_openbor_7533(self.connection, log)

        self._run_worker(task, success_message)

    def uninstall_openbor_7533(self):
        if not self.connection.is_connected():
            return

        reply = QMessageBox.question(
            self,
            "Uninstall MiSTer OpenBOR 7533",
            (
                "Remove MiSTer OpenBOR 7533 engine files, RBF files, documentation, "
                "install script, and the user-startup.sh daemon entry?\n\n"
                "Your Paks folder should be left in place."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            return backend_uninstall_openbor_7533(self.connection, log)

        self._run_worker(task, "MiSTer OpenBOR 7533 uninstalled.")

    def install_or_update_sonic_mania(self):
        if not self.connection.is_connected():
            return

        button_text = self.install_update_sonic_mania_button.text().strip()
        success_message = "Sonic Mania MiSTer installed."

        if button_text == "Update":
            success_message = "Sonic Mania MiSTer updated."

        def task(log):
            return backend_install_or_update_sonic_mania(self.connection, log)

        self._run_worker(task, success_message)

    def upload_sonic_mania_data_rsdk(self):
        if not self.connection.is_connected():
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Data.rsdk",
            "",
            "Sonic Mania Data File (Data.rsdk *.rsdk *.RSDK);;All Files (*)",
        )
        if not file_path:
            return

        def task(log):
            log(f"Selected file: {file_path}")
            return backend_upload_sonic_mania_data_rsdk(
                self.connection,
                file_path,
                log,
            )

        self._run_worker(task, "Data.rsdk uploaded.")

    def uninstall_sonic_mania(self):
        if not self.connection.is_connected():
            return

        reply = QMessageBox.question(
            self,
            "Uninstall Sonic Mania MiSTer",
            "Remove Sonic Mania MiSTer files, Data.rsdk, and the MiSTer.ini entries?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            return backend_uninstall_sonic_mania(self.connection, log)

        self._run_worker(task, "Sonic Mania MiSTer uninstalled.")

    def install_or_update_zaparoo_launcher(self):
        if not self.connection.is_connected():
            return

        button_text = self.install_update_zaparoo_launcher_button.text().strip()
        success_message = "Zaparoo Launcher/UI Beta installed."

        if button_text == "Update":
            success_message = "Zaparoo Launcher/UI Beta updated."

        self.zaparoo_launcher_show_reboot_after_success = True

        def task(log):
            return backend_install_or_update_zaparoo_launcher(self.connection, log)

        self._run_worker(task, success_message)

    def uninstall_zaparoo_launcher(self):
        if not self.connection.is_connected():
            return

        reply = QMessageBox.question(
            self,
            "Uninstall Zaparoo Launcher/UI Beta",
            (
                "Remove Zaparoo Launcher/UI Beta files and restore the previous "
                "zaparoo.sh backup if one exists?\n\n"
                "This will also remove the Zaparoo launcher main and alt_launcher "
                "entries from the [MiSTer] section in MiSTer.ini.\n\n"
                "A reboot will be required after uninstall."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.zaparoo_launcher_show_reboot_after_success = False
            return

        self.zaparoo_launcher_show_reboot_after_success = True

        def task(log):
            return backend_uninstall_zaparoo_launcher(self.connection, log)

        self._run_worker(task, "Zaparoo Launcher/UI Beta uninstalled.")

    def prompt_zaparoo_launcher_reboot_required(self):
        reboot_now = QMessageBox.question(
            self,
            "Reboot Required",
            (
                "Zaparoo Launcher/UI Beta changes were applied successfully.\n\n"
                "A reboot is required before the changes take effect.\n\n"
                "Reboot MiSTer now?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reboot_now != QMessageBox.StandardButton.Yes:
            return

        self.reboot_mister_from_extras()

    def reboot_mister_from_extras(self):
        if not self.connection.is_connected():
            QMessageBox.warning(self, "Not Connected", "Connect to a MiSTer first.")
            return

        try:
            self.apply_disconnected_state()
        except Exception:
            pass

        try:
            if hasattr(self.main_window, "set_connection_status"):
                self.main_window.set_connection_status("Status: Rebooting...")
        except Exception:
            pass

        try:
            self.connection.reboot()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Reboot Failed",
                f"Unable to reboot MiSTer:\n\n{e}",
            )
            return

        try:
            if hasattr(self.main_window, "start_reboot_reconnect_polling"):
                self.main_window.start_reboot_reconnect_polling()
            else:
                QMessageBox.warning(
                    self,
                    "Reconnect Polling",
                    "MiSTer reboot was sent, but reconnect polling is not available.",
                )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Reconnect Polling",
                (
                    "MiSTer reboot was sent, but reconnect polling could not be started:\n\n"
                    f"{e}"
                ),
            )

    def show_ra_cores_install_info(self):
        QMessageBox.information(
            self,
            "RetroAchievement Cores Installed",
            (
                "RetroAchievement Cores have been installed.\n\n"
                "MiSTer Companion now uses the MGL launcher method.\n\n"
                "Before using them, open Edit Config and enter your RetroAchievements "
                "username and password.\n\n"
                "To use the RetroAchievement-enabled cores:\n\n"
                "1. Open the MiSTer OSD menu.\n"
                "2. Go to the _RA_Cores folder.\n"
                "3. Launch a RetroAchievement core using one of the .mgl launchers.\n\n"
                "MiSTer Companion adds this block to your regular MiSTer.ini:\n\n"
                "[RA_*]\n"
                "main=MiSTer_RA\n\n"
                "Your normal cores remain untouched."
            ),
        )

    def install_or_update_ra_cores(self):
        if not self.connection.is_connected():
            return

        button_text = self.install_update_ra_cores_button.text().strip()

        is_update = button_text == "Update"
        is_migrate = button_text == "Migrate"

        success_message = "RetroAchievement Cores installed."

        if is_update:
            success_message = "RetroAchievement Cores updated."
        elif is_migrate:
            success_message = "RetroAchievement Cores migrated."

        self.ra_cores_show_install_info_after_success = not is_update

        def task(log):
            return backend_install_or_update_ra_cores(self.connection, log)

        self._run_worker(task, success_message)

    def edit_ra_cores_config(self):
        if not self.connection.is_connected():
            return

        dialog = RetroAchievementsConfigDialog(self, self.connection)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.refresh_status()

    def uninstall_ra_cores(self):
        if not self.connection.is_connected():
            return

        reply = QMessageBox.question(
            self,
            "Uninstall RetroAchievement Cores",
            (
                "Remove RetroAchievement Cores, MiSTer_RA, achievement.wav, "
                "the _RA_Cores folder, generated .mgl launchers, and the [RA_*] "
                "block from MiSTer.ini?\n\n"
                "Any legacy MiSTer_RA.ini or old _RA Cores folder will also be removed "
                "if present.\n\n"
                "retroachievements.cfg will be kept so your login settings are preserved."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            return backend_uninstall_ra_cores(self.connection, log)

        self._run_worker(task, "RetroAchievement Cores uninstalled.")
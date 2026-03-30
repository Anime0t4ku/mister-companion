import traceback

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.zapscripts import (
    get_zapscripts_state,
    run_script,
    send_input_command,
)


class ZaparooCommandWorker(QThread):
    success = pyqtSignal(object)
    error = pyqtSignal(str)
    finished_task = pyqtSignal()

    def __init__(self, task_fn):
        super().__init__()
        self.task_fn = task_fn

    def run(self):
        try:
            result = self.task_fn()
            self.success.emit(result)
        except Exception as e:
            detail = traceback.format_exc()
            self.error.emit(f"{str(e)}\n\n{detail}")
        finally:
            self.finished_task.emit()


class ZapScriptsTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection

        self.current_worker = None

        self.build_ui()
        self.apply_disconnected_state()

    def build_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(14)
        self.setLayout(main_layout)

        self.info_label = QLabel("Connect to a MiSTer device to load Zaparoo scripts.")
        self.info_label.setStyleSheet("color: gray;")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setWordWrap(True)
        main_layout.addWidget(self.info_label)

        # ===== Launch Scripts =====
        scripts_group = QGroupBox("Launch Scripts")
        scripts_layout = QVBoxLayout()
        scripts_layout.setContentsMargins(16, 18, 16, 18)
        scripts_layout.setSpacing(12)

        script_row_1 = QHBoxLayout()
        script_row_1.setSpacing(10)

        self.run_update_all_button = QPushButton("Run update_all")
        self.run_update_all_button.setFixedWidth(170)

        self.run_migrate_sd_button = QPushButton("Run migrate_sd")
        self.run_migrate_sd_button.setFixedWidth(170)

        self.run_insertcoin_button = QPushButton("Run update_all_insertcoin")
        self.run_insertcoin_button.setFixedWidth(210)

        script_row_1.addStretch()
        script_row_1.addWidget(self.run_update_all_button)
        script_row_1.addWidget(self.run_migrate_sd_button)
        script_row_1.addWidget(self.run_insertcoin_button)
        script_row_1.addStretch()

        script_row_2 = QHBoxLayout()
        script_row_2.setSpacing(10)

        self.run_auto_time_button = QPushButton("Run auto_time")
        self.run_auto_time_button.setFixedWidth(170)

        self.run_dav_browser_button = QPushButton("Run dav_browser")
        self.run_dav_browser_button.setFixedWidth(170)

        script_row_2.addStretch()
        script_row_2.addWidget(self.run_auto_time_button)
        script_row_2.addWidget(self.run_dav_browser_button)
        script_row_2.addStretch()

        scripts_layout.addLayout(script_row_1)
        scripts_layout.addLayout(script_row_2)
        scripts_group.setLayout(scripts_layout)
        main_layout.addWidget(scripts_group)

        # ===== Launch Misc. =====
        misc_group = QGroupBox("Launch Misc.")
        misc_layout = QVBoxLayout()
        misc_layout.setContentsMargins(16, 18, 16, 18)
        misc_layout.setSpacing(10)

        misc_row_1 = QHBoxLayout()
        misc_row_1.setSpacing(10)

        self.bluetooth_button = QPushButton("Open Bluetooth Menu")
        self.bluetooth_button.setFixedWidth(180)

        self.osd_button = QPushButton("Open OSD Menu")
        self.osd_button.setFixedWidth(180)

        misc_row_1.addStretch()
        misc_row_1.addWidget(self.bluetooth_button)
        misc_row_1.addWidget(self.osd_button)
        misc_row_1.addStretch()

        misc_row_2 = QHBoxLayout()
        misc_row_2.setSpacing(10)

        self.cycle_wallpaper_button = QPushButton("Cycle Wallpaper")
        self.cycle_wallpaper_button.setFixedWidth(180)

        self.return_home_button = QPushButton("Return to MiSTer Home")
        self.return_home_button.setFixedWidth(180)

        misc_row_2.addStretch()
        misc_row_2.addWidget(self.cycle_wallpaper_button)
        misc_row_2.addWidget(self.return_home_button)
        misc_row_2.addStretch()

        misc_layout.addLayout(misc_row_1)
        misc_layout.addLayout(misc_row_2)
        misc_group.setLayout(misc_layout)
        main_layout.addWidget(misc_group)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold;")
        self.status_label.setVisible(False)
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        main_layout.addStretch()

        self.run_update_all_button.clicked.connect(
            lambda: self.run_script_action("update_all", "update_all sent.")
        )
        self.run_migrate_sd_button.clicked.connect(
            lambda: self.run_script_action("migrate_sd", "migrate_sd sent.")
        )
        self.run_insertcoin_button.clicked.connect(
            lambda: self.run_script_action("update_all_insertcoin", "update_all_insertcoin sent.")
        )
        self.run_auto_time_button.clicked.connect(
            lambda: self.run_script_action("auto_time", "auto_time sent.")
        )
        self.run_dav_browser_button.clicked.connect(
            lambda: self.run_script_action("dav_browser", "dav_browser sent.")
        )

        self.bluetooth_button.clicked.connect(
            lambda: self.run_input_action("**input.keyboard:{f11}", "Bluetooth menu command sent.")
        )
        self.osd_button.clicked.connect(
            lambda: self.run_input_action("**input.keyboard:{f12}", "OSD menu command sent.")
        )
        self.cycle_wallpaper_button.clicked.connect(
            lambda: self.run_input_action("**input.keyboard:{f1}", "Wallpaper cycle command sent.")
        )
        self.return_home_button.clicked.connect(
            lambda: self.run_input_action("**stop", "Return-to-home command sent.")
        )

    def show_status(self, message, color="green"):
        if color == "green":
            self.status_label.setStyleSheet("color: #2ecc71; font-weight: bold;")
        elif color == "red":
            self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        else:
            self.status_label.setStyleSheet("color: #f39c12; font-weight: bold;")

        self.status_label.setText(message)
        self.status_label.setVisible(True)

        QTimer.singleShot(5000, self.clear_status)

    def clear_status(self):
        self.status_label.clear()
        self.status_label.setVisible(False)

    def set_buttons_enabled(self, enabled):
        for button in self.all_buttons():
            button.setEnabled(enabled)

    def update_connection_state(self):
        if self.connection.is_connected():
            self.refresh_status()
        else:
            self.apply_disconnected_state()

    def apply_disconnected_state(self):
        self.info_label.setText("Connect to a MiSTer device to load Zaparoo scripts.")
        self.info_label.setStyleSheet("color: gray;")
        self.clear_status()
        self.set_buttons_enabled(False)

    def all_buttons(self):
        return [
            self.run_update_all_button,
            self.run_migrate_sd_button,
            self.run_insertcoin_button,
            self.run_auto_time_button,
            self.run_dav_browser_button,
            self.bluetooth_button,
            self.osd_button,
            self.cycle_wallpaper_button,
            self.return_home_button,
        ]

    def refresh_status(self):
        if not self.connection.is_connected():
            self.apply_disconnected_state()
            return

        state = get_zapscripts_state(self.connection)

        if not state["zaparoo_installed"]:
            self.info_label.setText(
                "ZapScripts require Zaparoo to be installed.\n\nPlease install Zaparoo from the Scripts tab."
            )
            self.info_label.setStyleSheet("color: #cc0000;")
            self.set_buttons_enabled(False)
            return

        if not state["zaparoo_service_enabled"]:
            self.info_label.setText(
                "Zaparoo is installed but the boot service is not enabled.\n\nClick 'Enable Zaparoo Service' in the Scripts tab."
            )
            self.info_label.setStyleSheet("color: #cc8400;")
            self.set_buttons_enabled(False)
            return

        self.info_label.setText("Zaparoo is installed and ready.")
        self.info_label.setStyleSheet("color: #00aa00;")

        self.run_update_all_button.setEnabled(state["update_all_installed"])
        self.run_migrate_sd_button.setEnabled(state["migrate_sd_installed"])
        self.run_insertcoin_button.setEnabled(state["insertcoin_installed"])
        self.run_auto_time_button.setEnabled(state["auto_time_installed"])
        self.run_dav_browser_button.setEnabled(state["dav_browser_installed"])

        self.bluetooth_button.setEnabled(True)
        self.osd_button.setEnabled(True)
        self.cycle_wallpaper_button.setEnabled(True)
        self.return_home_button.setEnabled(True)

    def start_worker(self, task_fn, success_message):
        if self.current_worker is not None and self.current_worker.isRunning():
            self.show_status("Another ZapScripts task is still running.", "orange")
            return

        self.clear_status()
        self.current_worker = ZaparooCommandWorker(task_fn)
        self.current_worker.success.connect(
            lambda _result: self.show_status(success_message, "green")
        )
        self.current_worker.error.connect(self.on_worker_error)
        self.current_worker.finished_task.connect(self.on_worker_finished)
        self.current_worker.start()

    def on_worker_error(self, message):
        short_message = message.split("\n\n", 1)[0]
        self.show_status(short_message, "red")

    def on_worker_finished(self):
        self.current_worker = None
        self.refresh_status()

    def run_script_action(self, script_name, success_message):
        if not self.connection.is_connected():
            self.show_status("Connect to a MiSTer first.", "red")
            return

        def task():
            return run_script(self.connection, script_name)

        self.start_worker(task, success_message)

    def run_input_action(self, command, success_message):
        if not self.connection.is_connected():
            self.show_status("Connect to a MiSTer first.", "red")
            return

        def task():
            return send_input_command(self.connection, command)

        self.start_worker(task, success_message)
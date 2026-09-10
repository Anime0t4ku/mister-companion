from PyQt6.QtCore import QEvent, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.remote_daemon import (
    RemoteWebSocketClient,
    get_remote_daemon_status,
    install_remote_daemon,
    remote_websocket_url,
    start_stop_remote_daemon,
    toggle_remote_daemon_boot,
    uninstall_remote_daemon,
)


class RemoteDaemonStatusWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, connection):
        super().__init__()
        self.connection = connection

    def run(self):
        try:
            status = get_remote_daemon_status(self.connection)
            self.result.emit(status)
        except Exception as e:
            self.error.emit(str(e))


class RemoteDaemonCommandWorker(QThread):
    result = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, connection, command_name: str):
        super().__init__()
        self.connection = connection
        self.command_name = command_name

    def run(self):
        try:
            if self.command_name == "install":
                output = install_remote_daemon(self.connection)
            elif self.command_name == "uninstall":
                output = uninstall_remote_daemon(self.connection)
            elif self.command_name == "start-stop":
                output = start_stop_remote_daemon(self.connection)
            elif self.command_name == "toggle-boot":
                output = toggle_remote_daemon_boot(self.connection)
            else:
                raise ValueError(f"Unknown command: {self.command_name}")

            self.result.emit(str(output or "").strip())
        except Exception as e:
            self.error.emit(str(e))


class RemoteTab(QWidget):
    RESIZE_MARGIN = 7
    CONTROL_BUTTON_WIDTH = 60
    CONTROL_BUTTON_HEIGHT = 34
    SYSTEM_BUTTON_WIDTH = 70
    SYSTEM_BUTTON_HEIGHT = 32

    def __init__(self, parent=None):
        super().__init__(parent)

        self.main_window = parent
        self.connection = getattr(parent, "connection", None)
        self.status_worker = None
        self.command_worker = None
        self.last_status = None
        self.remote_client = None
        self.keyboard_passthrough_enabled = False
        self.held_keyboard_keys = set()
        self._tab_active = False
        self._offline = False

        self.build_ui()
        self.update_connection_state(lightweight=True)

    def build_ui(self):
        self.setObjectName("RemotePage")
        self.setStyleSheet(
            """
            QWidget#RemotePage QWidget#RemoteOnlineContainer,
            QWidget#RemotePage QWidget#RemoteControlsInner {
                background: transparent;
            }

            QWidget#RemotePage QGroupBox#RemoteShell {
                background: transparent;
                border: none;
                margin: 0px;
                padding: 0px;
            }

            QWidget#RemotePage QGroupBox#RemoteShell::title {
                color: transparent;
                background: transparent;
                padding: 0px;
            }

            QWidget#RemotePage QGroupBox#RemoteCard {
                background-color: palette(alternate-base);
                border: 1px solid palette(button);
                border-radius: 12px;
                margin-top: 18px;
                padding: 14px;
                font-weight: 700;
            }

            QWidget#RemotePage QGroupBox#RemoteCard::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                padding: 0px 7px;
                background: transparent;
                color: palette(highlight);
            }
            """
        )

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(18, 18, 18, 18)
        outer_layout.setSpacing(14)

        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(2, 0, 2, 0)
        header_layout.setSpacing(3)

        title_label = QLabel("Remote")
        title_label.setStyleSheet("font-weight: 700; font-size: 19px;")
        header_layout.addWidget(title_label)
        outer_layout.addLayout(header_layout)

        self.offline_label = QLabel("Remote not available in Offline Mode.")
        self.offline_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.offline_label.setStyleSheet("font-weight: bold; font-size: 15px; background: transparent; border: none;")
        self.offline_label.setVisible(False)
        outer_layout.addWidget(self.offline_label, 1)

        self.online_container = QGroupBox("")
        self.online_container.setObjectName("RemoteShell")
        self.online_container.setMaximumWidth(1100)
        self.online_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        root_layout = QVBoxLayout(self.online_container)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(10)

        centered_row = QHBoxLayout()
        centered_row.setContentsMargins(0, 0, 0, 0)
        centered_row.addStretch(1)
        centered_row.addWidget(self.online_container, 1, Qt.AlignmentFlag.AlignTop)
        centered_row.addStretch(1)
        outer_layout.addLayout(centered_row)
        outer_layout.addStretch(1)

        status_panel = QGroupBox("Status")
        status_panel.setObjectName("RemoteCard")
        status_layout = QHBoxLayout(status_panel)
        status_layout.setContentsMargins(16, 18, 16, 10)
        status_layout.setSpacing(10)
        status_layout.addStretch(1)

        installed_title = QLabel("Installed:")
        self.installed_status_label = QLabel("Unknown")
        self.installed_status_label.setStyleSheet("font-weight: 700; background: transparent;")
        running_title = QLabel("Running:")
        self.running_status_label = QLabel("Unknown")
        self.running_status_label.setStyleSheet("font-weight: 700; background: transparent;")
        startup_title = QLabel("Start on boot:")
        self.startup_status_label = QLabel("Unknown")
        self.startup_status_label.setStyleSheet("font-weight: 700; background: transparent;")

        status_layout.addWidget(installed_title)
        status_layout.addWidget(self.installed_status_label)
        status_layout.addSpacing(18)
        status_layout.addWidget(running_title)
        status_layout.addWidget(self.running_status_label)
        status_layout.addSpacing(18)
        status_layout.addWidget(startup_title)
        status_layout.addWidget(self.startup_status_label)
        status_layout.addStretch(1)
        root_layout.addWidget(status_panel)

        daemon_panel = QGroupBox("Daemon Management")
        daemon_panel.setObjectName("RemoteCard")
        daemon_layout = QVBoxLayout(daemon_panel)
        daemon_layout.setContentsMargins(16, 18, 16, 10)
        daemon_layout.setSpacing(6)

        daemon_buttons = QHBoxLayout()
        daemon_buttons.setSpacing(8)
        daemon_buttons.addStretch(1)

        self.refresh_button = QPushButton("Refresh")
        self.install_button = QPushButton("Install")
        self.start_stop_button = QPushButton("Start Daemon")
        self.boot_button = QPushButton("Enable Start on Boot")
        self.uninstall_button = QPushButton("Uninstall")
        self.install_button.setObjectName("PrimaryAction")

        daemon_buttons.addWidget(self.refresh_button)
        daemon_buttons.addWidget(self.install_button)
        daemon_buttons.addWidget(self.start_stop_button)
        daemon_buttons.addWidget(self.boot_button)
        daemon_buttons.addWidget(self.uninstall_button)
        daemon_buttons.addStretch(1)
        daemon_layout.addLayout(daemon_buttons)

        self.daemon_message_label = QLabel("")
        self.daemon_message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.daemon_message_label.setWordWrap(True)
        self.daemon_message_label.setVisible(False)
        daemon_layout.addWidget(self.daemon_message_label)
        root_layout.addWidget(daemon_panel)

        controls_panel = QGroupBox("Controls")
        controls_panel.setObjectName("RemoteCard")
        controls_layout = QVBoxLayout(controls_panel)
        controls_layout.setContentsMargins(16, 20, 16, 12)
        controls_layout.setSpacing(12)

        controller_row = QHBoxLayout()
        controller_row.setContentsMargins(0, 0, 0, 0)
        controller_row.setSpacing(22)

        dpad_widget = self.build_dpad_section()
        system_widget = self.build_system_section()
        buttons_widget = self.build_buttons_section()

        controller_row.addStretch(1)
        controller_row.addWidget(dpad_widget, 0, Qt.AlignmentFlag.AlignCenter)
        controller_row.addSpacing(10)
        controller_row.addWidget(system_widget, 0, Qt.AlignmentFlag.AlignCenter)
        controller_row.addSpacing(10)
        controller_row.addWidget(buttons_widget, 0, Qt.AlignmentFlag.AlignCenter)
        controller_row.addStretch(1)
        controls_layout.addLayout(controller_row)

        keyboard_separator = QWidget()
        keyboard_separator.setFixedHeight(1)
        keyboard_separator.setStyleSheet("background-color: palette(button);")
        controls_layout.addWidget(keyboard_separator)

        keyboard_row = QHBoxLayout()
        keyboard_row.setContentsMargins(8, 0, 8, 0)
        keyboard_row.setSpacing(10)
        keyboard_row.addStretch(1)

        keyboard_label = QLabel("Keyboard Passthrough")
        keyboard_label.setStyleSheet("font-weight: 700; background: transparent;")
        keyboard_row.addWidget(keyboard_label)

        keyboard_note = QLabel("Captures keyboard input while the Remote tab is active.")
        keyboard_note.setWordWrap(True)
        keyboard_row.addWidget(keyboard_note)

        self.keyboard_button = QPushButton("Enable")
        self.keyboard_button.setCheckable(True)
        keyboard_row.addWidget(self.keyboard_button)
        keyboard_row.addStretch(1)
        controls_layout.addLayout(keyboard_row)
        root_layout.addWidget(controls_panel)

        self.refresh_button.clicked.connect(self.refresh_state)
        self.install_button.clicked.connect(lambda: self.run_daemon_command("install"))
        self.start_stop_button.clicked.connect(lambda: self.run_daemon_command("start-stop"))
        self.boot_button.clicked.connect(lambda: self.run_daemon_command("toggle-boot"))
        self.uninstall_button.clicked.connect(self.confirm_uninstall)
        self.keyboard_button.toggled.connect(self.on_keyboard_passthrough_toggled)

        self.bind_controller_button(self.up_button, "dpad", "up")
        self.bind_controller_button(self.down_button, "dpad", "down")
        self.bind_controller_button(self.left_button, "dpad", "left")
        self.bind_controller_button(self.right_button, "dpad", "right")

        self.bind_controller_button(self.a_button, "button", "b")
        self.bind_controller_button(self.b_button, "button", "a")
        self.bind_controller_button(self.x_button, "button", "y")
        self.bind_controller_button(self.y_button, "button", "x")

        self.bind_controller_button(self.start_button, "button", "start")
        self.bind_controller_button(self.select_button, "button", "select")

        self.osd_button.pressed.connect(
            lambda: self.safe_remote_action(
                "OSD down",
                lambda: self.send_keyboard_key("KEY_F12", "down"),
            )
        )
        self.osd_button.released.connect(
            lambda: self.safe_remote_action(
                "OSD up",
                lambda: self.send_keyboard_key("KEY_F12", "up"),
            )
        )

        self.set_remote_controls_enabled(False)
        self.set_daemon_buttons_enabled(False)

    def prepare_control_button(self, button: QPushButton):
        button.setMinimumHeight(self.CONTROL_BUTTON_HEIGHT)
        button.setFixedWidth(self.CONTROL_BUTTON_WIDTH)

    def prepare_system_button(self, button: QPushButton):
        button.setMinimumHeight(self.SYSTEM_BUTTON_HEIGHT)
        button.setFixedWidth(self.SYSTEM_BUTTON_WIDTH)

    def build_dpad_section(self):
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        widget.setStyleSheet("background: transparent;")

        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.up_button = QPushButton("Up")
        self.down_button = QPushButton("Down")
        self.left_button = QPushButton("Left")
        self.right_button = QPushButton("Right")

        for button in (
            self.up_button,
            self.down_button,
            self.left_button,
            self.right_button,
        ):
            self.prepare_control_button(button)

        layout.addWidget(self.up_button, 0, 1)
        layout.addWidget(self.left_button, 1, 0)
        layout.addWidget(self.right_button, 1, 2)
        layout.addWidget(self.down_button, 2, 1)

        layout.setColumnMinimumWidth(0, self.CONTROL_BUTTON_WIDTH)
        layout.setColumnMinimumWidth(1, self.CONTROL_BUTTON_WIDTH)
        layout.setColumnMinimumWidth(2, self.CONTROL_BUTTON_WIDTH)

        return widget

    def build_system_section(self):
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        widget.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.osd_button = QPushButton("OSD")
        self.select_button = QPushButton("Select")
        self.start_button = QPushButton("Start")

        self.prepare_system_button(self.osd_button)
        self.prepare_system_button(self.select_button)
        self.prepare_system_button(self.start_button)

        osd_row = QHBoxLayout()
        osd_row.setContentsMargins(0, 0, 0, 0)
        osd_row.addStretch()
        osd_row.addWidget(self.osd_button)
        osd_row.addStretch()

        select_start_row = QHBoxLayout()
        select_start_row.setContentsMargins(0, 0, 0, 0)
        select_start_row.setSpacing(8)
        select_start_row.addWidget(self.select_button)
        select_start_row.addWidget(self.start_button)

        layout.addStretch(1)
        layout.addLayout(osd_row)
        layout.addLayout(select_start_row)
        layout.addStretch(1)

        return widget

    def build_buttons_section(self):
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        widget.setStyleSheet("background: transparent;")

        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.y_button = QPushButton("Y")
        self.x_button = QPushButton("X")
        self.a_button = QPushButton("A")
        self.b_button = QPushButton("B")

        for button in (
            self.y_button,
            self.x_button,
            self.a_button,
            self.b_button,
        ):
            self.prepare_control_button(button)

        layout.addWidget(self.y_button, 0, 1)
        layout.addWidget(self.x_button, 1, 0)
        layout.addWidget(self.a_button, 1, 2)
        layout.addWidget(self.b_button, 2, 1)

        layout.setColumnMinimumWidth(0, self.CONTROL_BUTTON_WIDTH)
        layout.setColumnMinimumWidth(1, self.CONTROL_BUTTON_WIDTH)
        layout.setColumnMinimumWidth(2, self.CONTROL_BUTTON_WIDTH)

        return widget

    def bind_controller_button(self, button: QPushButton, kind: str, name: str):
        if kind == "dpad":
            button.pressed.connect(
                lambda checked=False, n=name: self.safe_remote_action(
                    f"D-pad {n} down",
                    lambda: self.send_dpad(n, "down"),
                )
            )
            button.released.connect(
                lambda checked=False, n=name: self.safe_remote_action(
                    f"D-pad {n} up",
                    lambda: self.send_dpad(n, "up"),
                )
            )
        else:
            button.pressed.connect(
                lambda checked=False, n=name: self.safe_remote_action(
                    f"Button {n} down",
                    lambda: self.send_controller_button(n, "down"),
                )
            )
            button.released.connect(
                lambda checked=False, n=name: self.safe_remote_action(
                    f"Button {n} up",
                    lambda: self.send_controller_button(n, "up"),
                )
            )

    def safe_remote_action(self, label: str, callback, disable_on_error: bool = True):
        try:
            return callback()
        except Exception as e:
            self.append_log(f"{label} failed: {e}")
            self.release_all_inputs()

            if disable_on_error:
                self.set_remote_controls_enabled(False)

            return None

    def append_log(self, text: str):
        message = str(text or "").strip()
        if not message:
            return
        lines = [line.strip() for line in message.splitlines() if line.strip()]
        if not lines:
            return
        self.daemon_message_label.setText(lines[-1])
        self.daemon_message_label.setVisible(True)

    def connected_host(self) -> str:
        return getattr(self.connection, "host", "") if self.connection else ""

    def refresh_state(self):
        if self._offline:
            return

        connected = bool(self.connection and self.connection.is_connected())
        host = self.connected_host()

        self.last_status = None
        self.disconnect_remote_client()

        if connected and host:
            self.set_status_labels(
                installed="Checking...",
                running="Checking...",
                startup="Checking...",
            )
            self.set_daemon_buttons_enabled(False)
            self.set_remote_controls_enabled(False)
            self.append_log("Checking Companion Remote daemon status...")
            self.start_status_check()
        else:
            self.set_status_labels(
                installed="Not Installed",
                running="Not Running",
                startup="Disabled",
            )
            self.set_daemon_buttons_enabled(False)
            self.set_remote_controls_enabled(False)
            self.append_log("Connect to a MiSTer in Online Mode before using Remote.")

    def set_status_labels(self, installed: str, running: str, startup: str):
        self.installed_status_label.setText(installed)
        self.running_status_label.setText(running)
        self.startup_status_label.setText(startup)

    def start_status_check(self):
        if self.status_worker is not None and self.status_worker.isRunning():
            return

        self.refresh_button.setEnabled(False)
        self.status_worker = RemoteDaemonStatusWorker(self.connection)
        self.status_worker.result.connect(self.on_status_result)
        self.status_worker.error.connect(self.on_status_error)
        self.status_worker.finished.connect(self.on_status_finished)
        self.status_worker.start()

    def on_status_result(self, status):
        self.last_status = status

        if getattr(status, "error", ""):
            self.append_log(f"Status check failed: {status.error}")

        update_available = bool(getattr(status, "update_available", False))

        self.set_status_labels(
            installed=(f"Update Available ({status.version_label})" if update_available else (f"Installed ({status.version_label})" if status.installed else "Not Installed")),
            running="Running" if status.running else "Not Running",
            startup="Enabled" if status.startup_enabled else "Disabled",
        )

        if update_available:
            installed_version = getattr(status, "version_label", "Unknown")
            latest_version = getattr(status, "latest_version", "") or "Unknown"
            latest_source = getattr(status, "latest_source", "") or "remote"
            self.append_log(
                f"Companion Remote update available. Installed: {installed_version}. Latest: {latest_version} ({latest_source})."
            )
        elif status.ready:
            self.append_log("Companion Remote daemon is installed and running.")
            self.connect_remote_client()
        elif status.installed:
            self.append_log("Companion Remote daemon is installed, but it is not running yet.")
        elif status.script_exists:
            self.append_log("Companion Remote script exists, but the daemon is not installed yet.")
        else:
            self.append_log("Companion Remote daemon is not installed yet.")

        self.update_daemon_button_state()
        self.set_remote_controls_enabled(status.ready and not update_available and self.remote_client is not None)

    def on_status_error(self, message: str):
        self.append_log(f"Status check failed: {message}")
        self.set_status_labels(
            installed="Unknown",
            running="Unknown",
            startup="Unknown",
        )
        self.set_daemon_buttons_enabled(bool(self.connection and self.connection.is_connected()))
        self.set_remote_controls_enabled(False)

    def on_status_finished(self):
        self.refresh_button.setEnabled(bool(self.connection and self.connection.is_connected()))
        self.status_worker = None

    def run_daemon_command(self, command_name: str):
        if self.command_worker is not None and self.command_worker.isRunning():
            return

        try:
            self.release_all_inputs()
            self.disconnect_remote_client()
            self.set_daemon_buttons_enabled(False)
            self.set_remote_controls_enabled(False)

            self.append_log(f"Running daemon command: {command_name}")

            self.command_worker = RemoteDaemonCommandWorker(self.connection, command_name)
            self.command_worker.result.connect(self.on_command_result)
            self.command_worker.error.connect(self.on_command_error)
            self.command_worker.finished.connect(self.on_command_finished)
            self.command_worker.start()
        except Exception as e:
            self.append_log(f"Could not run daemon command: {e}")
            QMessageBox.warning(self, "Remote", str(e))
            self.refresh_state()

    def on_command_result(self, output: str):
        if output:
            self.append_log(output)
        else:
            self.append_log("Command completed.")

    def on_command_error(self, message: str):
        self.append_log(f"Command failed: {message}")
        QMessageBox.warning(self, "Remote", message)

    def on_command_finished(self):
        self.command_worker = None
        self.refresh_state()

    def confirm_uninstall(self):
        reply = QMessageBox.question(
            self,
            "Uninstall Remote Daemon",
            "This will stop Companion Remote, disable start on boot, remove the daemon files, and remove the script from the MiSTer.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.run_daemon_command("uninstall")

    def connect_remote_client(self):
        host = self.connected_host()

        if not host:
            return

        self.disconnect_remote_client()

        try:
            self.remote_client = RemoteWebSocketClient(host)
            self.remote_client.connect()
            self.remote_client.ping()
            self.append_log(f"WebSocket connected: {remote_websocket_url(host)}")
        except Exception as e:
            self.remote_client = None
            self.append_log(f"WebSocket failed: {e}")

    def disconnect_remote_client(self):
        if self.remote_client is not None:
            try:
                self.remote_client.close()
            except Exception:
                pass

        self.remote_client = None

    def set_daemon_buttons_enabled(self, enabled: bool):
        self.refresh_button.setEnabled(enabled)
        self.install_button.setEnabled(enabled)
        self.start_stop_button.setEnabled(enabled)
        self.boot_button.setEnabled(enabled)
        self.uninstall_button.setEnabled(enabled)

    def update_daemon_button_state(self):
        connected = bool(self.connection and self.connection.is_connected())
        status = self.last_status

        installed = bool(status and status.installed)
        running = bool(status and status.running)
        script_exists = bool(status and status.script_exists)
        startup_enabled = bool(status and status.startup_enabled)
        update_available = bool(status and getattr(status, "update_available", False))

        self.refresh_button.setEnabled(connected)

        if not connected:
            self.install_button.setEnabled(False)
            self.install_button.setText("Install")
            self.start_stop_button.setEnabled(False)
            self.boot_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)
            self.start_stop_button.setText("Start Daemon")
            self.boot_button.setText("Enable Start on Boot")
            return

        if not installed:
            self.install_button.setEnabled(True)
            self.install_button.setText("Install")
            self.start_stop_button.setEnabled(False)
            self.boot_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)
            self.start_stop_button.setText("Start Daemon")
            self.boot_button.setText("Enable Start on Boot")
            return

        self.install_button.setEnabled(update_available)
        self.install_button.setText("Update" if update_available else "Install")
        self.start_stop_button.setEnabled(script_exists and not update_available)
        self.boot_button.setEnabled(script_exists and not update_available)
        self.uninstall_button.setEnabled(True)

        if running:
            self.start_stop_button.setText("Stop Daemon")
        else:
            self.start_stop_button.setText("Start Daemon")

        if startup_enabled:
            self.boot_button.setText("Disable Start on Boot")
        else:
            self.boot_button.setText("Enable Start on Boot")

    def set_remote_controls_enabled(self, enabled: bool):
        for button in (
            self.up_button,
            self.down_button,
            self.left_button,
            self.right_button,
            self.a_button,
            self.b_button,
            self.x_button,
            self.y_button,
            self.start_button,
            self.select_button,
            self.osd_button,
            self.keyboard_button,
        ):
            button.setEnabled(enabled)

        if not enabled:
            self.disable_keyboard_passthrough(log_message=False)

    def send_controller_button(self, name: str, action: str = "tap"):
        if self.remote_client is None:
            raise RuntimeError("WebSocket is not connected.")

        self.remote_client.send_controller_button(name, action)

    def send_dpad(self, direction: str, action: str = "tap"):
        if self.remote_client is None:
            raise RuntimeError("WebSocket is not connected.")

        self.remote_client.send_dpad(direction, action)

    def send_keyboard_key(self, key: str, action: str = "tap"):
        if self.remote_client is None:
            raise RuntimeError("WebSocket is not connected.")

        self.remote_client.send_keyboard_key(key, action)

    def release_all_inputs(self):
        self.held_keyboard_keys.clear()

        if self.remote_client is None:
            return

        try:
            self.remote_client.release_all()
        except Exception:
            pass

    def on_keyboard_passthrough_toggled(self, checked: bool):
        # Passthrough may only be enabled while this tab is actually open.
        if checked and not self._passthrough_context_available():
            self.keyboard_passthrough_enabled = False
            self.keyboard_button.blockSignals(True)
            self.keyboard_button.setChecked(False)
            self.keyboard_button.blockSignals(False)
            self.keyboard_button.setText("Enable")
            return

        self.keyboard_passthrough_enabled = bool(checked)

        if checked:
            self.keyboard_button.setText("Disable")
            self.append_log("Keyboard passthrough enabled.")
        else:
            self.keyboard_button.setText("Enable")
            self.release_all_inputs()
            self.append_log("Keyboard passthrough disabled.")

    def _passthrough_context_available(self) -> bool:
        if self._offline or not self._tab_active:
            return False
        if self.remote_client is None:
            return False
        if self.main_window is None or not self.main_window.isActiveWindow():
            return False
        if hasattr(self.main_window, "tabs") and self.main_window.tabs.currentWidget() is not self:
            return False
        return True

    def _can_passthrough(self) -> bool:
        return self.keyboard_passthrough_enabled and self._passthrough_context_available()

    def handle_window_activation_changed(self, active: bool):
        if not active:
            # Release anything held on the MiSTer immediately when Companion
            # loses focus. Passthrough stays armed and resumes only after the
            # window is active again.
            self.release_all_inputs()

    def handle_application_key_event(self, event) -> bool:
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False
        if not self._can_passthrough() or event.isAutoRepeat():
            return False

        key_name = self.qt_key_to_remote_key(event.key())
        if not key_name:
            return False

        if event.type() == QEvent.Type.KeyPress:
            self.held_keyboard_keys.add(key_name)
            action = "down"
        else:
            self.held_keyboard_keys.discard(key_name)
            action = "up"

        try:
            self.send_keyboard_key(key_name, action)
        except Exception as exc:
            self.append_log(f"Keyboard {key_name} {action} failed: {exc}")
            self.disable_keyboard_passthrough(log_message=False)
            self.set_remote_controls_enabled(False)
            return False

        event.accept()
        return True

    def disable_keyboard_passthrough(self, log_message: bool = True):
        was_enabled = self.keyboard_passthrough_enabled or self.keyboard_button.isChecked()
        self.keyboard_passthrough_enabled = False
        self.release_all_inputs()
        self.keyboard_button.blockSignals(True)
        self.keyboard_button.setChecked(False)
        self.keyboard_button.blockSignals(False)
        self.keyboard_button.setText("Enable")
        if was_enabled and log_message:
            self.append_log("Keyboard passthrough disabled.")

    def set_tab_active(self, active: bool):
        active = bool(active)
        if self._tab_active and not active:
            # Never leave passthrough armed in the background.
            self.disable_keyboard_passthrough(log_message=True)
        self._tab_active = active

    def update_connection_state(self, lightweight: bool = True):
        offline = bool(self.main_window and hasattr(self.main_window, "is_offline_mode") and self.main_window.is_offline_mode())
        if offline != self._offline:
            self._offline = offline

        self.offline_label.setVisible(offline)
        self.online_container.setVisible(not offline)

        if offline:
            self.disable_keyboard_passthrough(log_message=False)
            self.release_all_inputs()
            self.disconnect_remote_client()
            self.last_status = None
            self.set_remote_controls_enabled(False)
            self.set_daemon_buttons_enabled(False)
            return

        self.update_daemon_button_state()
        if not (self.connection and self.connection.is_connected()):
            self.disable_keyboard_passthrough(log_message=False)
            self.disconnect_remote_client()
            self.set_remote_controls_enabled(False)

    def refresh(self, force: bool = False):
        if self._offline:
            return
        if not self._tab_active:
            return
        if force or self.last_status is None:
            self.refresh_state()

    def shutdown(self):
        self.disable_keyboard_passthrough(log_message=False)
        self.disconnect_remote_client()

        if self.status_worker is not None and self.status_worker.isRunning():
            self.status_worker.wait(1000)
        if self.command_worker is not None and self.command_worker.isRunning():
            self.command_worker.wait(1000)

    def qt_key_to_remote_key(self, key):
        mapping = {
            Qt.Key.Key_Escape: "KEY_ESC",
            Qt.Key.Key_Backspace: "KEY_BACKSPACE",
            Qt.Key.Key_Tab: "KEY_TAB",
            Qt.Key.Key_Return: "KEY_ENTER",
            Qt.Key.Key_Enter: "KEY_ENTER",
            Qt.Key.Key_Space: "KEY_SPACE",
            Qt.Key.Key_Up: "KEY_UP",
            Qt.Key.Key_Down: "KEY_DOWN",
            Qt.Key.Key_Left: "KEY_LEFT",
            Qt.Key.Key_Right: "KEY_RIGHT",
            Qt.Key.Key_Home: "KEY_HOME",
            Qt.Key.Key_End: "KEY_END",
            Qt.Key.Key_PageUp: "KEY_PAGEUP",
            Qt.Key.Key_PageDown: "KEY_PAGEDOWN",
            Qt.Key.Key_Insert: "KEY_INSERT",
            Qt.Key.Key_Delete: "KEY_DELETE",
            Qt.Key.Key_Minus: "KEY_MINUS",
            Qt.Key.Key_Equal: "KEY_EQUAL",
            Qt.Key.Key_BracketLeft: "KEY_LEFTBRACE",
            Qt.Key.Key_BracketRight: "KEY_RIGHTBRACE",
            Qt.Key.Key_Backslash: "KEY_BACKSLASH",
            Qt.Key.Key_Semicolon: "KEY_SEMICOLON",
            Qt.Key.Key_Apostrophe: "KEY_APOSTROPHE",
            Qt.Key.Key_Comma: "KEY_COMMA",
            Qt.Key.Key_Period: "KEY_DOT",
            Qt.Key.Key_Slash: "KEY_SLASH",
            Qt.Key.Key_QuoteLeft: "KEY_GRAVE",
            Qt.Key.Key_Shift: "KEY_LEFTSHIFT",
            Qt.Key.Key_Control: "KEY_LEFTCTRL",
            Qt.Key.Key_Alt: "KEY_LEFTALT",
            Qt.Key.Key_F1: "KEY_F1",
            Qt.Key.Key_F2: "KEY_F2",
            Qt.Key.Key_F3: "KEY_F3",
            Qt.Key.Key_F4: "KEY_F4",
            Qt.Key.Key_F5: "KEY_F5",
            Qt.Key.Key_F6: "KEY_F6",
            Qt.Key.Key_F7: "KEY_F7",
            Qt.Key.Key_F8: "KEY_F8",
            Qt.Key.Key_F9: "KEY_F9",
            Qt.Key.Key_F10: "KEY_F10",
            Qt.Key.Key_F11: "KEY_F11",
            Qt.Key.Key_F12: "KEY_F12",
        }

        if key in mapping:
            return mapping[key]

        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return f"KEY_{chr(ord('A') + int(key - Qt.Key.Key_A))}"

        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            return f"KEY_{chr(ord('0') + int(key - Qt.Key.Key_0))}"

        return ""
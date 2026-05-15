from PyQt6.QtCore import QEvent, QPoint, QRect, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
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


class RemoteDialog(QDialog):
    RESIZE_MARGIN = 7

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

        self._resizing = False
        self._resize_direction = ""
        self._resize_start_pos = QPoint()
        self._resize_start_geometry = QRect()

        self.setWindowTitle("Remote")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.resize(820, 620)
        self.setMinimumSize(760, 560)
        self.setSizeGripEnabled(False)
        self.setMouseTracking(True)

        self.build_ui()
        self.install_resize_event_filters()
        self.refresh_state()

    def build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        title_label = QLabel("MiSTer Companion Remote")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        root_layout.addWidget(title_label)

        description_label = QLabel(
            "Remote uses MiSTer Companion's own daemon on the MiSTer. "
            "Daemon management runs through SSH. Live controller and keyboard input use WebSocket."
        )
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root_layout.addWidget(description_label)

        status_panel = QFrame()
        status_panel.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QGridLayout(status_panel)
        status_layout.setContentsMargins(10, 10, 10, 10)
        status_layout.setHorizontalSpacing(18)
        status_layout.setVerticalSpacing(6)

        status_title = QLabel("Status")
        status_title.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(status_title, 0, 0, 1, 6)

        status_layout.addWidget(QLabel("Installed:"), 1, 0)
        self.installed_status_label = QLabel("Unknown")
        self.installed_status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.installed_status_label, 1, 1)

        status_layout.addWidget(QLabel("Running:"), 1, 2)
        self.running_status_label = QLabel("Unknown")
        self.running_status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.running_status_label, 1, 3)

        status_layout.addWidget(QLabel("Start on boot:"), 1, 4)
        self.startup_status_label = QLabel("Unknown")
        self.startup_status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.startup_status_label, 1, 5)

        status_layout.setColumnStretch(1, 1)
        status_layout.setColumnStretch(3, 1)
        status_layout.setColumnStretch(5, 1)
        root_layout.addWidget(status_panel)

        daemon_panel = QFrame()
        daemon_panel.setFrameShape(QFrame.Shape.StyledPanel)
        daemon_layout = QVBoxLayout(daemon_panel)
        daemon_layout.setContentsMargins(10, 10, 10, 10)
        daemon_layout.setSpacing(8)

        daemon_title = QLabel("Daemon Management")
        daemon_title.setStyleSheet("font-weight: bold;")
        daemon_layout.addWidget(daemon_title)

        daemon_buttons = QHBoxLayout()
        daemon_buttons.setSpacing(8)

        self.refresh_button = QPushButton("Refresh")
        self.install_button = QPushButton("Install")
        self.start_stop_button = QPushButton("Start Daemon")
        self.boot_button = QPushButton("Enable Start on Boot")
        self.uninstall_button = QPushButton("Uninstall")

        daemon_buttons.addWidget(self.refresh_button)
        daemon_buttons.addStretch()
        daemon_buttons.addWidget(self.install_button)
        daemon_buttons.addWidget(self.start_stop_button)
        daemon_buttons.addWidget(self.boot_button)
        daemon_buttons.addWidget(self.uninstall_button)

        daemon_layout.addLayout(daemon_buttons)
        root_layout.addWidget(daemon_panel)

        controls_panel = QFrame()
        controls_panel.setFrameShape(QFrame.Shape.StyledPanel)
        controls_layout = QHBoxLayout(controls_panel)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(16)

        dpad_widget = self.build_dpad_section()
        system_widget = self.build_system_section()
        buttons_widget = self.build_buttons_section()

        controls_layout.addWidget(dpad_widget, 1)
        controls_layout.addWidget(system_widget, 1)
        controls_layout.addWidget(buttons_widget, 1)

        root_layout.addWidget(controls_panel, 1)

        keyboard_panel = QFrame()
        keyboard_panel.setFrameShape(QFrame.Shape.StyledPanel)
        keyboard_layout = QVBoxLayout(keyboard_panel)
        keyboard_layout.setContentsMargins(10, 10, 10, 10)
        keyboard_layout.setSpacing(8)

        keyboard_title = QLabel("Keyboard Passthrough")
        keyboard_title.setStyleSheet("font-weight: bold;")
        keyboard_layout.addWidget(keyboard_title)

        keyboard_row = QHBoxLayout()
        self.keyboard_button = QPushButton("Enable Keyboard Passthrough")
        self.keyboard_button.setCheckable(True)
        keyboard_row.addWidget(self.keyboard_button)

        keyboard_note = QLabel(
            "Captures keyboard input while this Remote window is focused. "
            "A-Z, numbers, arrows, Enter, Space, function keys, and common modifiers are supported."
        )
        keyboard_note.setWordWrap(True)
        keyboard_row.addWidget(keyboard_note, 1)

        keyboard_layout.addLayout(keyboard_row)
        root_layout.addWidget(keyboard_panel)

        output_header = QHBoxLayout()
        output_title = QLabel("Output")
        output_title.setStyleSheet("font-weight: bold;")
        self.output_toggle_button = QPushButton("Show Output")
        output_header.addWidget(output_title)
        output_header.addStretch()
        output_header.addWidget(self.output_toggle_button)
        root_layout.addLayout(output_header)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(100)
        self.log_box.setVisible(False)
        root_layout.addWidget(self.log_box)

        self.refresh_button.clicked.connect(self.refresh_state)
        self.install_button.clicked.connect(lambda: self.run_daemon_command("install"))
        self.start_stop_button.clicked.connect(lambda: self.run_daemon_command("start-stop"))
        self.boot_button.clicked.connect(lambda: self.run_daemon_command("toggle-boot"))
        self.uninstall_button.clicked.connect(self.confirm_uninstall)
        self.keyboard_button.toggled.connect(self.on_keyboard_passthrough_toggled)
        self.output_toggle_button.clicked.connect(self.toggle_output)

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

    def install_resize_event_filters(self):
        self.installEventFilter(self)
        self.setMouseTracking(True)

        for widget in self.findChildren(QWidget):
            widget.installEventFilter(self)
            widget.setMouseTracking(True)

    def eventFilter(self, obj, event):
        if not isinstance(obj, QWidget) or obj.window() is not self:
            return super().eventFilter(obj, event)

        event_type = event.type()

        if event_type == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                direction = self._resize_hit_test(event.globalPosition().toPoint())

                if direction:
                    self._resizing = True
                    self._resize_direction = direction
                    self._resize_start_pos = event.globalPosition().toPoint()
                    self._resize_start_geometry = self.geometry()
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
                event.accept()
                return True

        return super().eventFilter(obj, event)

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

    def build_dpad_section(self):
        widget = QFrame()
        widget.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QGridLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("D-Pad")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title, 0, 0, 1, 3)

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
            button.setMinimumHeight(34)

        layout.addWidget(self.up_button, 1, 1)
        layout.addWidget(self.left_button, 2, 0)
        layout.addWidget(self.right_button, 2, 2)
        layout.addWidget(self.down_button, 3, 1)

        layout.setRowStretch(4, 1)
        return widget

    def build_system_section(self):
        widget = QFrame()
        widget.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("System")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        layout.addStretch()

        self.select_button = QPushButton("Select")
        self.osd_button = QPushButton("OSD")
        self.start_button = QPushButton("Start")

        for button in (
            self.select_button,
            self.osd_button,
            self.start_button,
        ):
            button.setMinimumHeight(34)
            layout.addWidget(button)

        layout.addStretch()
        return widget

    def build_buttons_section(self):
        widget = QFrame()
        widget.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QGridLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("Buttons")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title, 0, 0, 1, 3)

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
            button.setMinimumHeight(34)

        layout.addWidget(self.y_button, 1, 1)
        layout.addWidget(self.x_button, 2, 0)
        layout.addWidget(self.a_button, 2, 2)
        layout.addWidget(self.b_button, 3, 1)

        layout.setRowStretch(4, 1)
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
        self.log_box.append(str(text or ""))

    def toggle_output(self):
        visible = self.log_box.isVisible()
        self.log_box.setVisible(not visible)
        self.output_toggle_button.setText("Show Output" if visible else "Hide Output")

    def show_output(self):
        if not self.log_box.isVisible():
            self.log_box.setVisible(True)
            self.output_toggle_button.setText("Hide Output")

    def connected_host(self) -> str:
        return getattr(self.connection, "host", "") if self.connection else ""

    def refresh_state(self):
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

        self.set_status_labels(
            installed="Installed" if status.installed else "Not Installed",
            running="Running" if status.running else "Not Running",
            startup="Enabled" if status.startup_enabled else "Disabled",
        )

        if status.ready:
            self.append_log("Companion Remote daemon is installed and running.")
            self.connect_remote_client()
        elif status.installed:
            self.append_log("Companion Remote daemon is installed, but it is not running yet.")
        elif status.script_exists:
            self.append_log("Companion Remote script exists, but the daemon is not installed yet.")
        else:
            self.append_log("Companion Remote daemon is not installed yet.")

        self.update_daemon_button_state()
        self.set_remote_controls_enabled(status.ready and self.remote_client is not None)

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
            self.show_output()

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

        self.refresh_button.setEnabled(connected)

        if not connected:
            self.install_button.setEnabled(False)
            self.start_stop_button.setEnabled(False)
            self.boot_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)
            self.start_stop_button.setText("Start Daemon")
            self.boot_button.setText("Enable Start on Boot")
            return

        if not installed:
            self.install_button.setEnabled(True)
            self.start_stop_button.setEnabled(False)
            self.boot_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)
            self.start_stop_button.setText("Start Daemon")
            self.boot_button.setText("Enable Start on Boot")
            return

        self.install_button.setEnabled(False)
        self.start_stop_button.setEnabled(script_exists)
        self.boot_button.setEnabled(script_exists)
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
            self.keyboard_passthrough_enabled = False
            if self.keyboard_button.isChecked():
                self.keyboard_button.setChecked(False)
            else:
                self.keyboard_button.setText("Enable Keyboard Passthrough")

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
        self.keyboard_passthrough_enabled = bool(checked)

        if checked:
            self.keyboard_button.setText("Disable Keyboard Passthrough")
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            self.append_log("Keyboard passthrough enabled.")
        else:
            self.keyboard_button.setText("Enable Keyboard Passthrough")
            self.release_all_inputs()
            self.append_log("Keyboard passthrough disabled.")

    def keyPressEvent(self, event):
        if self.keyboard_passthrough_enabled and not event.isAutoRepeat():
            key_name = self.qt_key_to_remote_key(event.key())

            if key_name:
                self.held_keyboard_keys.add(key_name)
                self.safe_remote_action(
                    f"Keyboard {key_name} down",
                    lambda: self.send_keyboard_key(key_name, "down"),
                )
                event.accept()
                return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self.keyboard_passthrough_enabled and not event.isAutoRepeat():
            key_name = self.qt_key_to_remote_key(event.key())

            if key_name:
                self.held_keyboard_keys.discard(key_name)
                self.safe_remote_action(
                    f"Keyboard {key_name} up",
                    lambda: self.send_keyboard_key(key_name, "up"),
                )
                event.accept()
                return

        super().keyReleaseEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow():
                self.release_all_inputs()

        super().changeEvent(event)

    def focusOutEvent(self, event):
        self.release_all_inputs()
        super().focusOutEvent(event)

    def closeEvent(self, event):
        self.release_all_inputs()
        self.disconnect_remote_client()

        if self.status_worker is not None and self.status_worker.isRunning():
            self.status_worker.wait(1000)

        if self.command_worker is not None and self.command_worker.isRunning():
            self.command_worker.wait(1000)

        super().closeEvent(event)

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
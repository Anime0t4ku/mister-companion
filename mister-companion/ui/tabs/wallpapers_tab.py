import traceback

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.language import tr
from core.scripts_actions import get_scripts_status, remove_static_wallpaper
from core.wallpapers import (
    build_install_state,
    fetch_ot4ku_wallpapers,
    fetch_pcn_premium_wallpapers,
    fetch_pcn_wallpapers,
    fetch_ranny_wallpapers,
    get_installed_wallpapers,
    open_wallpaper_folder_on_host,
    remove_installed_wallpapers,
    wallpaper_folder_exists,
    install_wallpaper_items,
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


class WallpapersTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection

        self.console_visible = False
        self.current_worker = None

        self.build_ui()
        self.apply_disconnected_state()

    def build_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(14)
        self.setLayout(main_layout)

        # Static Wallpapers
        static_group = QGroupBox(tr("wallpapers_tab.static_wallpapers"))
        static_layout = QVBoxLayout()
        static_layout.setContentsMargins(16, 18, 16, 18)
        static_layout.setSpacing(12)

        static_buttons = QHBoxLayout()
        static_buttons.setSpacing(10)

        self.set_static_wallpaper_button = QPushButton(tr("wallpapers_tab.set_static_wallpaper"))
        self.set_static_wallpaper_button.setFixedWidth(190)

        self.remove_static_wallpaper_button = QPushButton(tr("wallpapers_tab.remove_static_wallpaper"))
        self.remove_static_wallpaper_button.setFixedWidth(190)

        static_buttons.addStretch()
        static_buttons.addWidget(self.set_static_wallpaper_button)
        static_buttons.addWidget(self.remove_static_wallpaper_button)
        static_buttons.addStretch()

        static_layout.addLayout(static_buttons)
        static_group.setLayout(static_layout)
        main_layout.addWidget(static_group)

        # Wallpaper Sources
        sources_group = QGroupBox(tr("wallpapers_tab.wallpaper_sources"))
        sources_layout = QVBoxLayout()
        sources_layout.setContentsMargins(16, 18, 16, 18)
        sources_layout.setSpacing(14)

        # Ranny
        ranny_group = QGroupBox(tr("wallpapers_tab.ranny_snice_wallpapers"))
        ranny_layout = QVBoxLayout()
        ranny_layout.setContentsMargins(16, 18, 16, 18)
        ranny_layout.setSpacing(12)

        ranny_buttons = QHBoxLayout()
        ranny_buttons.setSpacing(10)

        self.install_169_button = QPushButton(tr("wallpapers_tab.install_169_wallpapers"))
        self.install_169_button.setFixedWidth(190)

        self.install_43_button = QPushButton(tr("wallpapers_tab.install_43_wallpapers"))
        self.install_43_button.setFixedWidth(190)

        self.remove_ranny_button = QPushButton(tr("wallpapers_tab.remove_installed_wallpapers"))
        self.remove_ranny_button.setFixedWidth(220)

        ranny_buttons.addStretch()
        ranny_buttons.addWidget(self.install_169_button)
        ranny_buttons.addWidget(self.install_43_button)
        ranny_buttons.addWidget(self.remove_ranny_button)
        ranny_buttons.addStretch()

        ranny_layout.addLayout(ranny_buttons)
        ranny_group.setLayout(ranny_layout)
        sources_layout.addWidget(ranny_group)

        # PCN
        pcn_group = QGroupBox(tr("wallpapers_tab.pcn_challenge_wallpapers"))
        pcn_layout = QVBoxLayout()
        pcn_layout.setContentsMargins(16, 18, 16, 18)
        pcn_layout.setSpacing(12)

        pcn_buttons = QHBoxLayout()
        pcn_buttons.setSpacing(10)

        self.install_pcn_button = QPushButton(tr("wallpapers_tab.install_wallpapers"))
        self.install_pcn_button.setFixedWidth(190)

        self.remove_pcn_button = QPushButton(tr("wallpapers_tab.remove_installed_wallpapers"))
        self.remove_pcn_button.setFixedWidth(220)

        pcn_buttons.addStretch()
        pcn_buttons.addWidget(self.install_pcn_button)
        pcn_buttons.addWidget(self.remove_pcn_button)
        pcn_buttons.addStretch()

        pcn_layout.addLayout(pcn_buttons)
        pcn_group.setLayout(pcn_layout)
        sources_layout.addWidget(pcn_group)

        # PCN Premium
        pcn_premium_group = QGroupBox(tr("wallpapers_tab.pcn_premium_wallpapers"))
        pcn_premium_layout = QVBoxLayout()
        pcn_premium_layout.setContentsMargins(16, 18, 16, 18)
        pcn_premium_layout.setSpacing(12)

        pcn_premium_buttons = QHBoxLayout()
        pcn_premium_buttons.setSpacing(10)

        self.install_pcn_premium_button = QPushButton(tr("wallpapers_tab.install_wallpapers"))
        self.install_pcn_premium_button.setFixedWidth(190)

        self.remove_pcn_premium_button = QPushButton(tr("wallpapers_tab.remove_installed_wallpapers"))
        self.remove_pcn_premium_button.setFixedWidth(220)

        pcn_premium_buttons.addStretch()
        pcn_premium_buttons.addWidget(self.install_pcn_premium_button)
        pcn_premium_buttons.addWidget(self.remove_pcn_premium_button)
        pcn_premium_buttons.addStretch()

        pcn_premium_layout.addLayout(pcn_premium_buttons)
        pcn_premium_group.setLayout(pcn_premium_layout)
        sources_layout.addWidget(pcn_premium_group)

        # 0t4ku
        ot4ku_group = QGroupBox(tr("wallpapers_tab.ot4ku_wallpapers"))
        ot4ku_layout = QVBoxLayout()
        ot4ku_layout.setContentsMargins(16, 18, 16, 18)
        ot4ku_layout.setSpacing(12)

        ot4ku_buttons = QHBoxLayout()
        ot4ku_buttons.setSpacing(10)

        self.install_ot4ku_button = QPushButton(tr("wallpapers_tab.install_wallpapers"))
        self.install_ot4ku_button.setFixedWidth(190)

        self.remove_ot4ku_button = QPushButton(tr("wallpapers_tab.remove_installed_wallpapers"))
        self.remove_ot4ku_button.setFixedWidth(220)

        ot4ku_buttons.addStretch()
        ot4ku_buttons.addWidget(self.install_ot4ku_button)
        ot4ku_buttons.addWidget(self.remove_ot4ku_button)
        ot4ku_buttons.addStretch()

        ot4ku_layout.addLayout(ot4ku_buttons)
        ot4ku_group.setLayout(ot4ku_layout)
        sources_layout.addWidget(ot4ku_group)

        sources_group.setLayout(sources_layout)
        main_layout.addWidget(sources_group)

        # Open Wallpaper Folder
        folder_row = QHBoxLayout()
        folder_row.addStretch()

        self.open_wallpaper_folder_button = QPushButton(tr("wallpapers_tab.open_wallpaper_folder"))
        self.open_wallpaper_folder_button.setFixedWidth(180)

        folder_row.addWidget(self.open_wallpaper_folder_button)
        folder_row.addStretch()
        main_layout.addLayout(folder_row)

        # SSH Output
        self.console_group = QGroupBox(tr("wallpapers_tab.ssh_output"))
        console_layout = QVBoxLayout()
        console_layout.setContentsMargins(10, 10, 10, 10)
        console_layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.addStretch()

        self.hide_console_button = QPushButton(tr("wallpapers_tab.hide"))
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

        main_layout.addStretch()

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

    def update_connection_state(self):
        if not self.connection.is_connected():
            self.apply_disconnected_state()
            return

        if self.current_worker is not None and self.current_worker.isRunning():
            return

        self.set_static_wallpaper_button.setEnabled(True)
        self.remove_static_wallpaper_button.setEnabled(False)

        self.install_169_button.setText(tr("wallpapers_tab.install_169_wallpapers"))
        self.install_43_button.setText(tr("wallpapers_tab.install_43_wallpapers"))
        self.install_pcn_button.setText(tr("wallpapers_tab.install_wallpapers"))
        self.install_pcn_premium_button.setText(tr("wallpapers_tab.install_wallpapers"))
        self.install_ot4ku_button.setText(tr("wallpapers_tab.install_wallpapers"))

        self.install_169_button.setEnabled(False)
        self.install_43_button.setEnabled(False)
        self.remove_ranny_button.setEnabled(False)

        self.install_pcn_button.setEnabled(False)
        self.remove_pcn_button.setEnabled(False)

        self.install_pcn_premium_button.setEnabled(False)
        self.remove_pcn_premium_button.setEnabled(False)

        self.install_ot4ku_button.setEnabled(False)
        self.remove_ot4ku_button.setEnabled(False)

        self.open_wallpaper_folder_button.setEnabled(True)

    def apply_disconnected_state(self):
        self.set_static_wallpaper_button.setEnabled(False)
        self.remove_static_wallpaper_button.setEnabled(False)

        self.install_169_button.setText(tr("wallpapers_tab.install_169_wallpapers"))
        self.install_43_button.setText(tr("wallpapers_tab.install_43_wallpapers"))
        self.install_pcn_button.setText(tr("wallpapers_tab.install_wallpapers"))
        self.install_pcn_premium_button.setText(tr("wallpapers_tab.install_wallpapers"))
        self.install_ot4ku_button.setText(tr("wallpapers_tab.install_wallpapers"))

        self.install_169_button.setEnabled(False)
        self.install_43_button.setEnabled(False)
        self.remove_ranny_button.setEnabled(False)

        self.install_pcn_button.setEnabled(False)
        self.remove_pcn_button.setEnabled(False)

        self.install_pcn_premium_button.setEnabled(False)
        self.remove_pcn_premium_button.setEnabled(False)

        self.install_ot4ku_button.setEnabled(False)
        self.remove_ot4ku_button.setEnabled(False)

        self.open_wallpaper_folder_button.setEnabled(False)

    def refresh_status(self):
        if not self.connection.is_connected():
            self.apply_disconnected_state()
            return

        self.set_static_wallpaper_button.setEnabled(True)
        self.remove_static_wallpaper_button.setEnabled(False)

        try:
            script_status = get_scripts_status(self.connection)
            self.remove_static_wallpaper_button.setEnabled(
                bool(script_status.static_wallpaper_active)
            )
        except Exception:
            self.remove_static_wallpaper_button.setEnabled(False)

        installed = get_installed_wallpapers(self.connection)

        gh_169, gh_43 = fetch_ranny_wallpapers()
        installed_169, missing_169 = build_install_state(gh_169, installed)
        installed_43, missing_43 = build_install_state(gh_43, installed)

        if not installed_169:
            self.install_169_button.setText(tr("wallpapers_tab.install_169_wallpapers"))
            self.install_169_button.setEnabled(True)
        elif missing_169:
            self.install_169_button.setText(tr("wallpapers_tab.update_169_wallpapers"))
            self.install_169_button.setEnabled(True)
        else:
            self.install_169_button.setText(tr("wallpapers_tab.install_169_wallpapers"))
            self.install_169_button.setEnabled(False)

        if not installed_43:
            self.install_43_button.setText(tr("wallpapers_tab.install_43_wallpapers"))
            self.install_43_button.setEnabled(True)
        elif missing_43:
            self.install_43_button.setText(tr("wallpapers_tab.update_43_wallpapers"))
            self.install_43_button.setEnabled(True)
        else:
            self.install_43_button.setText(tr("wallpapers_tab.install_43_wallpapers"))
            self.install_43_button.setEnabled(False)

        self.remove_ranny_button.setEnabled(installed_169 or installed_43)

        pcn_items = fetch_pcn_wallpapers()
        pcn_installed, pcn_missing = build_install_state(pcn_items, installed)

        if not pcn_installed:
            self.install_pcn_button.setText(tr("wallpapers_tab.install_wallpapers"))
            self.install_pcn_button.setEnabled(True)
        elif pcn_missing:
            self.install_pcn_button.setText(tr("wallpapers_tab.update_wallpapers"))
            self.install_pcn_button.setEnabled(True)
        else:
            self.install_pcn_button.setText(tr("wallpapers_tab.install_wallpapers"))
            self.install_pcn_button.setEnabled(False)

        self.remove_pcn_button.setEnabled(pcn_installed)

        pcn_premium_items = fetch_pcn_premium_wallpapers()
        pcn_premium_installed, pcn_premium_missing = build_install_state(
            pcn_premium_items,
            installed,
        )

        if not pcn_premium_installed:
            self.install_pcn_premium_button.setText(tr("wallpapers_tab.install_wallpapers"))
            self.install_pcn_premium_button.setEnabled(True)
        elif pcn_premium_missing:
            self.install_pcn_premium_button.setText(tr("wallpapers_tab.update_wallpapers"))
            self.install_pcn_premium_button.setEnabled(True)
        else:
            self.install_pcn_premium_button.setText(tr("wallpapers_tab.install_wallpapers"))
            self.install_pcn_premium_button.setEnabled(False)

        self.remove_pcn_premium_button.setEnabled(pcn_premium_installed)

        ot4ku_items = fetch_ot4ku_wallpapers()
        ot4ku_installed, ot4ku_missing = build_install_state(ot4ku_items, installed)

        if not ot4ku_installed:
            self.install_ot4ku_button.setText(tr("wallpapers_tab.install_wallpapers"))
            self.install_ot4ku_button.setEnabled(True)
        elif ot4ku_missing:
            self.install_ot4ku_button.setText(tr("wallpapers_tab.update_wallpapers"))
            self.install_ot4ku_button.setEnabled(True)
        else:
            self.install_ot4ku_button.setText(tr("wallpapers_tab.install_wallpapers"))
            self.install_ot4ku_button.setEnabled(False)

        self.remove_ot4ku_button.setEnabled(ot4ku_installed)

        self.open_wallpaper_folder_button.setEnabled(
            wallpaper_folder_exists(self.connection)
        )

    def start_worker(self, task_fn, success_message=""):
        if self.current_worker is not None and self.current_worker.isRunning():
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
        QMessageBox.critical(self, tr("wallpapers_tab.wallpaper_error"), detail)

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

    def set_static_wallpaper(self):
        if not self.connection.is_connected():
            return

        dialog = StaticWallpaperDialog(self.connection, self)
        if dialog.exec():
            self.refresh_status()

    def remove_static_wallpaper_action(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("wallpapers_tab.remove_static_wallpaper"),
            tr("wallpapers_tab.remove_static_wallpaper_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            remove_static_wallpaper(self.connection, reload_menu=True)
            self.refresh_status()
        except Exception as e:
            QMessageBox.critical(self, tr("common.error"), str(e))

    def install_169_wallpapers(self):
        if not self.connection.is_connected():
            return

        def task(log):
            log(tr("wallpapers_tab.log_fetching_wallpaper_list") + "\n")
            wallpapers_169, _ = fetch_ranny_wallpapers()

            if not wallpapers_169:
                log(tr("wallpapers_tab.log_no_wallpapers_found") + "\n")
                return

            count = install_wallpaper_items(self.connection, wallpapers_169, log)
            log("\n" + tr("wallpapers_tab.log_finished_installed", count=count) + "\n")

        self.start_worker(task)

    def install_43_wallpapers(self):
        if not self.connection.is_connected():
            return

        def task(log):
            log(tr("wallpapers_tab.log_fetching_wallpaper_list") + "\n")
            _, wallpapers_43 = fetch_ranny_wallpapers()

            if not wallpapers_43:
                log(tr("wallpapers_tab.log_no_wallpapers_found") + "\n")
                return

            count = install_wallpaper_items(self.connection, wallpapers_43, log)
            log("\n" + tr("wallpapers_tab.log_finished_installed", count=count) + "\n")

        self.start_worker(task)

    def remove_ranny_wallpapers(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("wallpapers_tab.remove_wallpapers"),
            tr("wallpapers_tab.remove_ranny_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            log(tr("wallpapers_tab.log_removing_ranny") + "\n")
            wallpapers_169, wallpapers_43 = fetch_ranny_wallpapers()
            removed = remove_installed_wallpapers(
                self.connection,
                wallpapers_169 + wallpapers_43,
                log,
            )
            log("\n" + tr("wallpapers_tab.log_finished_removed", count=removed) + "\n")

        self.start_worker(task)

    def install_pcn_wallpapers(self):
        if not self.connection.is_connected():
            return

        def task(log):
            log(tr("wallpapers_tab.log_fetching_wallpaper_list") + "\n")
            wallpapers = fetch_pcn_wallpapers()

            if not wallpapers:
                log(tr("wallpapers_tab.log_no_wallpapers_found") + "\n")
                return

            count = install_wallpaper_items(self.connection, wallpapers, log)
            log("\n" + tr("wallpapers_tab.log_finished_installed", count=count) + "\n")

        self.start_worker(task)

    def remove_pcn_wallpapers(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("wallpapers_tab.remove_wallpapers"),
            tr("wallpapers_tab.remove_pcn_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            log(tr("wallpapers_tab.log_removing_pcn") + "\n")
            wallpapers = fetch_pcn_wallpapers()
            removed = remove_installed_wallpapers(self.connection, wallpapers, log)
            log("\n" + tr("wallpapers_tab.log_finished_removed", count=removed) + "\n")

        self.start_worker(task)

    def install_pcn_premium_wallpapers(self):
        if not self.connection.is_connected():
            return

        def task(log):
            log(tr("wallpapers_tab.log_fetching_wallpaper_list") + "\n")
            wallpapers = fetch_pcn_premium_wallpapers()

            if not wallpapers:
                log(tr("wallpapers_tab.log_no_wallpapers_found") + "\n")
                return

            count = install_wallpaper_items(self.connection, wallpapers, log)
            log("\n" + tr("wallpapers_tab.log_finished_installed", count=count) + "\n")

        self.start_worker(task)

    def remove_pcn_premium_wallpapers(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("wallpapers_tab.remove_wallpapers"),
            tr("wallpapers_tab.remove_pcn_premium_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            log(tr("wallpapers_tab.log_removing_pcn_premium") + "\n")
            wallpapers = fetch_pcn_premium_wallpapers()
            removed = remove_installed_wallpapers(self.connection, wallpapers, log)
            log("\n" + tr("wallpapers_tab.log_finished_removed", count=removed) + "\n")

        self.start_worker(task)

    def install_ot4ku_wallpapers(self):
        if not self.connection.is_connected():
            return

        def task(log):
            log(tr("wallpapers_tab.log_fetching_wallpaper_list") + "\n")
            wallpapers = fetch_ot4ku_wallpapers()

            if not wallpapers:
                log(tr("wallpapers_tab.log_no_wallpapers_found") + "\n")
                return

            count = install_wallpaper_items(self.connection, wallpapers, log)
            log("\n" + tr("wallpapers_tab.log_finished_installed", count=count) + "\n")

        self.start_worker(task)

    def remove_ot4ku_wallpapers(self):
        if not self.connection.is_connected():
            return

        confirm = QMessageBox.question(
            self,
            tr("wallpapers_tab.remove_wallpapers"),
            tr("wallpapers_tab.remove_ot4ku_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        def task(log):
            log(tr("wallpapers_tab.log_removing_ot4ku") + "\n")
            wallpapers = fetch_ot4ku_wallpapers()
            removed = remove_installed_wallpapers(self.connection, wallpapers, log)
            log("\n" + tr("wallpapers_tab.log_finished_removed", count=removed) + "\n")

        self.start_worker(task)

    def open_wallpaper_folder(self):
        if not self.connection.is_connected():
            return

        try:
            open_wallpaper_folder_on_host(
                self.connection.host,
                self.connection.username or "root",
                self.connection.password or "1",
            )
        except Exception as e:
            QMessageBox.critical(self, tr("common.error"), str(e))
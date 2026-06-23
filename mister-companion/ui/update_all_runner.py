import time
import traceback

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QMessageBox, QPushButton, QTextEdit, QVBoxLayout

from core.config import save_config
from core.update_all_offline import run_update_all_offline
from core.scripts_actions import run_update_all_stream
from ui.scaling import set_text_button_min_width


class UpdateAllRunWorker(QThread):
    log_line = pyqtSignal(str)
    error = pyqtSignal(str)
    success = pyqtSignal(str)
    task_result = pyqtSignal(object)
    finished_task = pyqtSignal()

    def __init__(self, task_fn):
        super().__init__()
        self.task_fn = task_fn

    def log(self, text):
        self.log_line.emit(str(text))

    def run(self):
        try:
            result = self.task_fn(self.log)
            self.success.emit("update_all finished.")
            self.task_result.emit(result)
        except Exception as e:
            self.error.emit(f"{e}\n\n{traceback.format_exc()}")
        finally:
            self.finished_task.emit()


def prepare_update_all_task(main_window, parent=None):
    scripts_tab = getattr(main_window, "scripts_tab", None)
    connection = getattr(main_window, "connection", None)
    is_offline = bool(getattr(main_window, "is_offline_mode", lambda: False)())

    if is_offline:
        sd_root = getattr(main_window, "get_offline_sd_root", lambda: "")()
        if not sd_root:
            QMessageBox.critical(parent or main_window, "Update All", "Select an Offline SD Card first.")
            return None

        if scripts_tab is not None and not bool(getattr(scripts_tab, "update_all_installed", False)):
            QMessageBox.critical(
                parent or main_window,
                "update_all not installed",
                "Install update_all first before running the offline updater.",
            )
            return None

        def task(log):
            log("Running update_all offline...\n\n")
            result = run_update_all_offline(sd_root, progress=log)

            log("\nOffline update finished.\n")
            log(f"Databases found: {result.databases_found}\n")
            log(f"Databases processed: {result.databases_processed}\n")
            log(f"Folders created: {result.folders_created}\n")
            log(f"Files downloaded: {result.files_downloaded}\n")
            log(f"Files skipped: {result.files_skipped}\n")
            log(f"Files failed: {result.files_failed}\n")
            log(f"Archives downloaded: {result.archives_downloaded}\n")
            log(f"Archives skipped: {result.archives_skipped}\n")

            if result.errors:
                log("\nErrors:\n")
                for error in result.errors:
                    log(f"- {error}\n")

            if not result.ok:
                raise RuntimeError("Offline update_all finished with errors.")

            return {"action": "completed"}

        return task

    if connection is None or not connection.is_connected():
        QMessageBox.critical(parent or main_window, "Update All", "Connect to a MiSTer first.")
        return None

    if scripts_tab is not None and not bool(getattr(scripts_tab, "update_all_installed", False)):
        QMessageBox.critical(
            parent or main_window,
            "update_all not installed",
            "Install update_all first before running update_all.",
        )
        return None

    config_data = getattr(main_window, "config_data", {})
    if not config_data.get("hide_update_all_warning", False):
        msg = QMessageBox(parent or main_window)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("Run update_all")
        msg.setText(
            "update_all will run through SSH.\n\n"
            "The output will NOT appear on the MiSTer TV screen.\n"
            "It will only be visible inside MiSTer Companion.\n\n"
            "If you want the output to appear on the TV screen, run update_all from:\n"
            "• ZapScripts in MiSTer Companion\n"
            "• The Scripts menu on the MiSTer itself\n\n"
            "Continue?"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)

        dont_show_checkbox = QCheckBox("Don't show this again")
        msg.setCheckBox(dont_show_checkbox)
        msg.exec()

        if msg.result() != QMessageBox.StandardButton.Yes:
            return None

        if dont_show_checkbox.isChecked():
            config_data["hide_update_all_warning"] = True
            save_config(config_data)

    def task(log):
        log("Running update_all...\n\n")
        run_update_all_stream(connection, log)
        log("\nupdate_all finished.\n")

        log("Checking if a reboot was triggered...\n")
        watch_seconds = 10
        interval_seconds = 1

        for _ in range(watch_seconds):
            time.sleep(interval_seconds)

            still_connected = False
            try:
                still_connected = connection.is_connected()
                if still_connected and connection.client:
                    transport = connection.client.get_transport()
                    still_connected = bool(transport and transport.is_active())
            except Exception:
                still_connected = False

            if not still_connected:
                connection.mark_disconnected()
                log("MiSTer disconnected after update_all, likely due to reboot.\n")
                log("Starting automatic reconnect...\n")
                return {"action": "reboot_reconnect"}

        log("No reboot detected after update_all.\n")
        return {"action": "completed"}

    return task


def handle_update_all_result(main_window, result):
    if isinstance(result, dict) and result.get("action") == "reboot_reconnect":
        connection = getattr(main_window, "connection", None)
        if connection is not None:
            try:
                connection.mark_disconnected()
            except Exception:
                pass
        try:
            main_window.start_reboot_reconnect_polling()
        except Exception:
            pass


class UpdateAllOutputDialog(QDialog):
    def __init__(self, main_window, task_fn, parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.task_fn = task_fn
        self.worker = None
        self.setWindowTitle("Run Update All")
        self.resize(900, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("update_all output will appear here.")
        layout.addWidget(self.output, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.close_button = QPushButton("Close")
        set_text_button_min_width(self.close_button, 100)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

    def start(self):
        if self.worker is not None:
            return
        self.close_button.setEnabled(False)
        self.worker = UpdateAllRunWorker(self.task_fn)
        self.worker.log_line.connect(self.append_output)
        self.worker.success.connect(self.append_output)
        self.worker.error.connect(self.append_error)
        self.worker.task_result.connect(lambda result: handle_update_all_result(self.main_window, result))
        self.worker.finished_task.connect(self.on_finished)
        self.worker.start()

    def append_output(self, text):
        self.output.moveCursor(self.output.textCursor().MoveOperation.End)
        self.output.insertPlainText(str(text))
        if not str(text).endswith("\n"):
            self.output.insertPlainText("\n")
        self.output.ensureCursorVisible()

    def append_error(self, text):
        self.append_output(f"\nERROR:\n{text}\n")

    def on_finished(self):
        self.worker = None
        self.close_button.setEnabled(True)

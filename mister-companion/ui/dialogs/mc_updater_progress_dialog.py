from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QVBoxLayout,
)

from core import mc_updater


class MCUpdaterTaskWorker(QThread):
    progress = pyqtSignal(str)
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, action: str, config_data: dict):
        super().__init__()
        self.action = action
        self.config_data = config_data

    def run(self):
        try:
            if self.action in {"install", "update"}:
                version = mc_updater.install_or_update(
                    self.config_data,
                    progress=self.progress.emit,
                )
                self.result.emit(version)
                return

            if self.action == "remove":
                mc_updater.remove(
                    self.config_data,
                    progress=self.progress.emit,
                )
                self.result.emit(True)
                return

            raise RuntimeError("Unknown MC-Updater action.")
        except Exception as e:
            self.error.emit(str(e))


class MCUpdaterProgressDialog(QDialog):
    def __init__(self, parent, action: str, config_data: dict):
        super().__init__(parent)
        self.action = action
        self.config_data = config_data
        self.success = False
        self.worker = None

        if action == "install":
            title = "Installing MC-Updater"
        elif action == "update":
            title = "Updating MC-Updater"
        else:
            title = "Removing MC-Updater"

        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.status_label = QLabel("Preparing...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        layout.addWidget(self.progress_bar)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(180)
        layout.addWidget(self.log_box)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.close_button = self.buttons.button(QDialogButtonBox.StandardButton.Close)
        self.close_button.setEnabled(False)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.start_task()

    def start_task(self):
        self.worker = MCUpdaterTaskWorker(self.action, self.config_data)
        self.worker.progress.connect(self.on_progress)
        self.worker.result.connect(self.on_result)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_progress(self, message: str):
        self.status_label.setText(message)
        self.log_box.appendPlainText(message)

    def on_result(self, result):
        self.success = True
        if self.action in {"install", "update"}:
            self.status_label.setText(f"MC-Updater installed, {result}")
            self.log_box.appendPlainText(f"MC-Updater installed, {result}")
        else:
            self.status_label.setText("MC-Updater removed.")
            self.log_box.appendPlainText("MC-Updater removed.")

    def on_error(self, message: str):
        self.success = False
        self.status_label.setText("Failed.")
        self.log_box.appendPlainText(f"Error: {message}")

    def on_finished(self):
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.close_button.setEnabled(True)

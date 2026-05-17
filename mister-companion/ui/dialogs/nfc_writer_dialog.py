from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from core.nfc_writer import (
    list_serial_readers,
    write_payload_to_token,
)


class NFCWriteWorker(QThread):
    success = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, payload: str, port: str | None):
        super().__init__()
        self.payload = payload
        self.port = port

    def run(self):
        try:
            result = write_payload_to_token(self.payload, self.port)
            self.success.emit(result)
        except Exception as e:
            self.error.emit(str(e))


def _is_likely_reader_port(reader) -> bool:
    text = f"{reader.port} {reader.description}".lower()

    blocked_terms = [
        "bluetooth",
        "standard serial over bluetooth",
        "bthenum",
        "modem",
    ]

    likely_terms = [
        "ch340",
        "ch341",
        "usb-serial",
        "usb serial",
        "usb_serial",
        "cp210",
        "cp210x",
        "ftdi",
        "uart",
        "usb cdc",
        "pn532",
        "serial usb",
    ]

    if any(term in text for term in blocked_terms):
        return False

    if any(term in text for term in likely_terms):
        return True

    return False


class NFCWriterDialog(QDialog):
    def __init__(self, payload: str = "", parent=None):
        super().__init__(parent)

        self.payload = (payload or "").strip()
        self.worker = None

        self.setWindowTitle("Write to NFC Token")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        info = QLabel(
            "Enter a Zaparoo payload, place a token on the PN532 reader, then write it."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        payload_label = QLabel("Payload:")
        layout.addWidget(payload_label)

        self.payload_box = QTextEdit()
        self.payload_box.setPlainText(self.payload)
        self.payload_box.setReadOnly(False)
        self.payload_box.setMinimumHeight(90)
        self.payload_box.setPlaceholderText(
            "Example: games/SNES/Super Mario World.sfc"
        )
        layout.addWidget(self.payload_box)

        reader_row = QHBoxLayout()
        reader_row.setSpacing(8)

        self.reader_combo = QComboBox()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_readers)

        reader_row.addWidget(QLabel("Reader:"))
        reader_row.addWidget(self.reader_combo, 1)
        reader_row.addWidget(self.refresh_btn)

        layout.addLayout(reader_row)

        self.status = QLabel("Connect a PN532 reader and place a token on it.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        self.write_btn = QPushButton("Write Token")
        self.write_btn.clicked.connect(self.write_token)

        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.write_btn)

        layout.addLayout(buttons)

        self.refresh_readers()

        if not self.payload:
            self.payload_box.setFocus()

    def refresh_readers(self):
        self.reader_combo.clear()
        self.reader_combo.addItem("Auto-detect PN532", None)

        readers = list_serial_readers()
        likely_readers = [reader for reader in readers if _is_likely_reader_port(reader)]

        likely_readers.sort(
            key=lambda reader: f"{reader.description} {reader.port}".lower()
        )

        for reader in likely_readers:
            self.reader_combo.addItem(
                f"{reader.port} - {reader.description}",
                reader.port,
            )

        if not readers:
            self.status.setText(
                "No serial ports were found. Connect your PN532 USB reader and press Refresh."
            )
        elif not likely_readers:
            self.status.setText(
                "No likely PN532 USB reader was found. You can still try Auto-detect PN532."
            )
        elif len(likely_readers) == 1:
            self.reader_combo.setCurrentIndex(1)
            self.status.setText("PN532 reader detected.")
        else:
            self.status.setText(
                "Select your PN532 reader, or leave Auto-detect enabled."
            )

    def write_token(self):
        payload = self.payload_box.toPlainText().strip()
        if not payload:
            QMessageBox.warning(
                self,
                "No payload",
                "Enter a Zaparoo payload before writing the NFC token.",
            )
            self.payload_box.setFocus()
            return

        port = self.reader_combo.currentData()

        self.set_busy(True)
        self.status.setText("Waiting for token and writing payload...")

        self.worker = NFCWriteWorker(payload, port)
        self.worker.success.connect(self.on_write_success)
        self.worker.error.connect(self.on_write_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def set_busy(self, busy: bool):
        self.reader_combo.setEnabled(not busy)
        self.refresh_btn.setEnabled(not busy)
        self.write_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(not busy)
        self.payload_box.setReadOnly(busy)

    def on_write_success(self, result):
        self.status.setText(
            f"Token written and verified successfully.\n\n"
            f"Reader: {result.port}\n"
            f"Token: {result.tag_type}\n"
            f"UID: {result.uid}"
        )

        QMessageBox.information(
            self,
            "NFC token written",
            f"NFC token written and verified successfully.\n\n"
            f"Token: {result.tag_type}\n"
            f"UID: {result.uid}",
        )

        self.accept()

    def on_write_error(self, message: str):
        self.status.setText("Write failed.")
        QMessageBox.critical(self, "NFC write failed", message)

    def on_worker_finished(self):
        self.set_busy(False)
        self.worker = None
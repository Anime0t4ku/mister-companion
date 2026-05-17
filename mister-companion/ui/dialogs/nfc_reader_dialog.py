import time

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
)

from core.nfc_reader import (
    list_serial_readers,
    open_reader,
)
from core.zapscripts import send_input_command


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


class NFCReadWorker(QThread):
    status = pyqtSignal(str)
    token_detected = pyqtSignal(str, str)
    token_removed = pyqtSignal()
    token_read_failed = pyqtSignal(str, str)
    fatal_error = pyqtSignal(str)

    def __init__(self, port: str | None, mode: str):
        super().__init__()
        self.port = port
        self.mode = mode
        self._running = True

    def stop(self):
        self._running = False
        self.requestInterruption()

    def run(self):
        reader = None

        try:
            self.status.emit("Opening PN532 reader...")
            reader = open_reader(self.port)

            self.status.emit("Reader active. Waiting for NFC token...")

            current_uid = ""
            last_tap_uid = ""
            card_present = False
            missing_count = 0
            missing_threshold = 1

            while self._running and not self.isInterruptionRequested():
                uid_bytes = reader.poll_for_tag()

                if uid_bytes:
                    uid = "".join(f"{value:02X}" for value in uid_bytes)
                    missing_count = 0

                    if self.mode == "hold":
                        if uid != current_uid:
                            try:
                                payload = reader.read_ndef_text_payload()
                            except Exception as e:
                                current_uid = uid
                                self.token_read_failed.emit(uid, str(e))
                                time.sleep(0.1)
                                continue

                            current_uid = uid
                            self.token_detected.emit(uid, payload)

                    else:
                        if not card_present or uid != last_tap_uid:
                            try:
                                payload = reader.read_ndef_text_payload()
                            except Exception as e:
                                last_tap_uid = uid
                                card_present = True
                                self.token_read_failed.emit(uid, str(e))
                                time.sleep(0.1)
                                continue

                            last_tap_uid = uid
                            card_present = True
                            self.token_detected.emit(uid, payload)
                        else:
                            card_present = True

                else:
                    if self.mode == "hold":
                        if current_uid:
                            missing_count += 1

                            if missing_count >= missing_threshold:
                                current_uid = ""
                                missing_count = 0
                                self.token_removed.emit()
                                self.status.emit("Token removed. Waiting for NFC token...")
                        else:
                            self.status.emit("Waiting for NFC token...")

                    else:
                        card_present = False

                    time.sleep(0.05)

                time.sleep(0.03)

        except Exception as e:
            self.fatal_error.emit(str(e))

        finally:
            if reader is not None:
                try:
                    reader.close()
                except Exception:
                    pass


class NFCReaderDialog(QDialog):
    def __init__(self, connection, parent=None):
        super().__init__(parent)

        self.connection = connection
        self.worker = None
        self.last_uid = ""
        self.last_payload = ""

        self.setWindowTitle("Read NFC Token")
        self.setMinimumWidth(620)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(12)

        self.hold_radio = QRadioButton("Hold")
        self.tap_radio = QRadioButton("Tap")
        self.hold_radio.setChecked(True)

        mode_row.addWidget(QLabel("Mode:"))
        mode_row.addWidget(self.hold_radio)
        mode_row.addWidget(self.tap_radio)
        mode_row.addStretch(1)

        layout.addLayout(mode_row)

        reader_row = QHBoxLayout()
        reader_row.setSpacing(8)

        self.reader_combo = QComboBox()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_readers)

        reader_row.addWidget(QLabel("Reader:"))
        reader_row.addWidget(self.reader_combo, 1)
        reader_row.addWidget(self.refresh_btn)

        layout.addLayout(reader_row)

        self.status = QLabel("Connect a PN532 reader and press Start Reading.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.uid_label = QLabel("UID: -")
        layout.addWidget(self.uid_label)

        payload_label = QLabel("Last payload read from token:")
        layout.addWidget(payload_label)

        self.payload_box = QTextEdit()
        self.payload_box.setReadOnly(True)
        self.payload_box.setMinimumHeight(110)
        layout.addWidget(self.payload_box)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        self.start_btn = QPushButton("Start Reading")
        self.start_btn.clicked.connect(self.start_reading)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_reading)
        self.stop_btn.setEnabled(False)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)

        buttons.addWidget(self.start_btn)
        buttons.addWidget(self.stop_btn)
        buttons.addWidget(self.close_btn)

        layout.addLayout(buttons)

        self.refresh_readers()

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
            self.status.setText("PN532 reader detected. Press Start Reading.")
        else:
            self.status.setText("Select your PN532 reader, or leave Auto-detect enabled.")

    def start_reading(self):
        if self.worker is not None:
            return

        mode = "hold" if self.hold_radio.isChecked() else "tap"
        port = self.reader_combo.currentData()

        self.set_busy(True)
        self.status.setText("Starting NFC reader...")

        self.worker = NFCReadWorker(port=port, mode=mode)
        self.worker.status.connect(self.on_status)
        self.worker.token_detected.connect(self.on_token_detected)
        self.worker.token_removed.connect(self.on_token_removed)
        self.worker.token_read_failed.connect(self.on_token_read_failed)
        self.worker.fatal_error.connect(self.on_fatal_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def stop_reading(self):
        if self.worker is None:
            return

        self.status.setText("Stopping NFC reader...")
        self.worker.stop()

    def set_busy(self, busy: bool):
        self.reader_combo.setEnabled(not busy)
        self.refresh_btn.setEnabled(not busy)
        self.hold_radio.setEnabled(not busy)
        self.tap_radio.setEnabled(not busy)
        self.start_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)

    def on_status(self, message: str):
        self.status.setText(message)

    def on_token_detected(self, uid: str, payload: str):
        self.last_uid = uid
        self.last_payload = payload

        self.uid_label.setText(f"UID: {uid}")
        self.payload_box.setPlainText(payload)
        self.status.setText("Token detected. Sending payload to Zaparoo...")

        try:
            send_input_command(self.connection, payload)
            self.status.setText("Payload sent to Zaparoo. Waiting for NFC token...")
        except Exception as e:
            self.status.setText("Failed to send payload to Zaparoo.")
            self.payload_box.setPlainText(
                f"{payload}\n\nLaunch error:\n{e}"
            )

    def on_token_read_failed(self, uid: str, message: str):
        self.last_uid = uid

        self.uid_label.setText(f"UID: {uid}")
        self.payload_box.setPlainText(
            "Could not read a valid Zaparoo payload from this NFC token.\n\n"
            f"Error:\n{message}\n\n"
            "The reader will continue scanning. Remove this token or place another token on the reader."
        )
        self.status.setText("Unreadable NFC token detected. Waiting for a valid token...")

    def on_token_removed(self):
        self.status.setText("Token removed. Sending stop command...")

        try:
            send_input_command(self.connection, "**stop")
            self.status.setText("Stop command sent. Waiting for NFC token...")
        except Exception as e:
            self.status.setText("Failed to send stop command.")
            self.payload_box.setPlainText(f"Stop command error:\n{e}")

    def on_fatal_error(self, message: str):
        self.status.setText("NFC reader stopped because of an error.")
        self.payload_box.setPlainText(message)
        QMessageBox.critical(self, "NFC reader error", message)

    def on_worker_finished(self):
        self.worker = None
        self.set_busy(False)

        if not self.status.text().startswith("NFC reader stopped because of an error"):
            self.status.setText("NFC reader stopped.")

    def closeEvent(self, event):
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(1500)
            self.worker = None

        super().closeEvent(event)
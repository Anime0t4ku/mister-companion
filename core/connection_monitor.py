import socket

from PyQt6.QtCore import QThread, pyqtSignal


class ConnectionCheckWorker(QThread):
    result = pyqtSignal(bool)

    def __init__(self, host, port=22, timeout=2):
        super().__init__()
        self.host = host
        self.port = port
        self.timeout = timeout

    def run(self):
        ok = False
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout):
                ok = True
        except Exception:
            ok = False

        self.result.emit(ok)
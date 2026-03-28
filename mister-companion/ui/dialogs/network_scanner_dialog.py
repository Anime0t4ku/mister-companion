import socket
import threading
import psutil
import paramiko

from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QLabel,
    QPushButton
)


class NetworkScannerWorker(QThread):
    ip_found = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    scan_finished = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self._running = True
        self.found_ips = set()
        self._lock = threading.Lock()

    def stop(self):
        self._running = False

    def get_local_subnets(self):
        subnets = []
        interfaces = psutil.net_if_addrs()

        for interface_name, addresses in interfaces.items():
            lowered = interface_name.lower()

            if any(v in lowered for v in [
                "vpn", "docker", "virtual", "vmware", "loopback", "hamachi", "tailscale"
            ]):
                continue

            for addr in addresses:
                if addr.family == socket.AF_INET:
                    ip = addr.address

                    if ip.startswith("127."):
                        continue

                    parts = ip.split(".")
                    if len(parts) != 4:
                        continue

                    subnet = ".".join(parts[:3])
                    subnets.append(subnet)

        return list(set(subnets))

    def is_port_open(self, ip, port=22):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.35)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def verify_mister(self, ip):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            ssh.connect(
                ip,
                username="root",
                password="1",
                timeout=0.5,
                banner_timeout=0.5,
                auth_timeout=0.5,
                look_for_keys=False,
                allow_agent=False
            )

            _, stdout, _ = ssh.exec_command("test -d /media/fat && echo OK")
            result = stdout.read().decode().strip()
            ssh.close()

            if result == "OK":
                with self._lock:
                    if ip not in self.found_ips:
                        self.found_ips.add(ip)
                        self.ip_found.emit(ip)

        except Exception:
            pass

    def check_device(self, ip):
        if not self._running:
            return

        if self.is_port_open(ip):
            self.verify_mister(ip)

    def run(self):
        try:
            subnets = self.get_local_subnets()

            if not subnets:
                self.status_changed.emit("No valid network detected")
                self.scan_finished.emit(0)
                return

            self.status_changed.emit("Scanning network...")

            threads = []

            for subnet in subnets:
                for i in range(1, 255):
                    if not self._running:
                        break

                    ip = f"{subnet}.{i}"
                    t = threading.Thread(target=self.check_device, args=(ip,), daemon=True)
                    t.start()
                    threads.append(t)

            for t in threads:
                if not self._running:
                    break
                t.join()

            self.scan_finished.emit(len(self.found_ips))

        except Exception as e:
            self.status_changed.emit(f"Scan failed: {str(e)}")
            self.scan_finished.emit(len(self.found_ips))


class NetworkScannerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.worker = None
        self.parent_window = parent

        self.setWindowTitle("Scan Network")
        self.resize(420, 360)
        self.setModal(True)

        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        self.status_label = QLabel("Idle")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        self.use_button = QPushButton("Use Selected IP")
        self.use_button.setEnabled(False)
        layout.addWidget(self.use_button)

        self.found_ips = set()

        self.list_widget.itemSelectionChanged.connect(self.on_select)
        self.list_widget.itemDoubleClicked.connect(self.use_selected)
        self.use_button.clicked.connect(self.use_selected)

        QTimer.singleShot(200, self.start_scan)

    def start_scan(self):
        self.list_widget.clear()
        self.found_ips.clear()
        self.use_button.setEnabled(False)
        self.status_label.setText("Starting scan...")

        self.worker = NetworkScannerWorker()
        self.worker.ip_found.connect(self.add_result)
        self.worker.status_changed.connect(self.status_label.setText)
        self.worker.scan_finished.connect(self.finish_scan)
        self.worker.start()

    def add_result(self, ip):
        if ip not in self.found_ips:
            self.found_ips.add(ip)
            self.list_widget.addItem(ip)

    def finish_scan(self, count):
        if self.status_label.text().startswith("Scan failed:"):
            return

        if count > 0:
            self.status_label.setText(f"Scan complete, found {count} device(s)")
        else:
            self.status_label.setText("Scan complete, no MiSTer found")

    def on_select(self):
        self.use_button.setEnabled(len(self.list_widget.selectedItems()) > 0)

    def use_selected(self):
        items = self.list_widget.selectedItems()
        if not items:
            return

        ip = items[0].text()

        if self.parent_window is not None:
            connection_tab = self.parent_window.connection_tab
            devices = self.parent_window.config_data.get("devices", [])

            matched_index = -1
            matched_device = None

            for i, device in enumerate(devices):
                if device.get("ip", "").strip() == ip:
                    matched_index = i
                    matched_device = device
                    break

            if matched_device is not None:
                connection_tab.set_connection_fields(
                    matched_device.get("ip", ""),
                    matched_device.get("username", "root"),
                    matched_device.get("password", "1")
                )

                connection_tab.profile_selector.blockSignals(True)
                connection_tab.profile_selector.setCurrentIndex(matched_index)
                connection_tab.profile_selector.blockSignals(False)
            else:
                connection_tab.set_connection_fields(
                    ip,
                    connection_tab.user_input.text() or "root",
                    connection_tab.pass_input.text() or "1"
                )

                connection_tab.profile_selector.blockSignals(True)
                connection_tab.profile_selector.setCurrentIndex(-1)
                connection_tab.profile_selector.blockSignals(False)

        self.accept()

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(500)
        super().closeEvent(event)
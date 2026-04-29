from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QDialogButtonBox
)

from core.language import tr


class DeviceDialog(QDialog):
    def __init__(self, parent=None, title=None, device=None):
        super().__init__(parent)

        self.setWindowTitle(title or tr("device_dialog.title"))
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.name_input = QLineEdit()
        self.ip_input = QLineEdit()
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow(tr("device_dialog.device_name"), self.name_input)
        form.addRow(tr("device_dialog.ip_address"), self.ip_input)
        form.addRow(tr("device_dialog.username"), self.username_input)
        form.addRow(tr("device_dialog.password"), self.password_input)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if device:
            self.name_input.setText(device.get("name", ""))
            self.ip_input.setText(device.get("ip", ""))
            self.username_input.setText(device.get("username", "root"))
            self.password_input.setText(device.get("password", "1"))
        else:
            self.username_input.setText("root")
            self.password_input.setText("1")

    def get_device_data(self):
        return {
            "name": self.name_input.text().strip(),
            "ip": self.ip_input.text().strip(),
            "username": self.username_input.text().strip() or "root",
            "password": self.password_input.text()
        }
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout

from core.language import tr


class RestoreBackupDialog(QDialog):
    def __init__(self, backup_files, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("restore_backup_dialog.window_title"))
        self.setMinimumSize(520, 360)

        layout = QVBoxLayout(self)

        info = QLabel(tr("restore_backup_dialog.select_backup"))
        layout.addWidget(info)

        self.list_widget = QListWidget()
        self.list_widget.addItems(backup_files)
        layout.addWidget(self.list_widget)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.restore_button = QPushButton(tr("restore_backup_dialog.restore"))
        self.cancel_button = QPushButton(tr("common.cancel"))

        button_row.addWidget(self.restore_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        self.restore_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.list_widget.itemDoubleClicked.connect(lambda _: self.accept())

        if backup_files:
            self.list_widget.setCurrentRow(0)

    def selected_backup(self):
        item = self.list_widget.currentItem()
        return item.text() if item else None
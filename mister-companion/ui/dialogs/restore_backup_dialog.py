from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout


class RestoreBackupDialog(QDialog):
    def __init__(self, backup_files, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restore MiSTer.ini Backup")
        self.setMinimumSize(520, 360)

        layout = QVBoxLayout(self)

        info = QLabel("Select a backup to restore:")
        layout.addWidget(info)

        self.list_widget = QListWidget()
        self.list_widget.addItems(backup_files)
        layout.addWidget(self.list_widget)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.restore_button = QPushButton("Restore")
        self.cancel_button = QPushButton("Cancel")

        button_row.addWidget(self.restore_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        self.restore_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.list_widget.itemDoubleClicked.connect(lambda _: self.accept())

    def selected_backup(self):
        item = self.list_widget.currentItem()
        return item.text() if item else None
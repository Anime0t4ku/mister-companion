from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from .card_widget import NFCCardWidget
from .cassette_widget import NFCCassetteWidget


class NFCArtGeneratorWidget(QWidget):
    """Combined NFC artwork workspace with a single shared configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.card = NFCCardWidget()
        self.cassette = NFCCassetteWidget(self.open_shared_settings)
        self.tabs.addTab(self.card, "NFC Card")
        self.tabs.addTab(self.cassette, "NFC Cassette Cover")
        layout.addWidget(self.tabs)

    def open_shared_settings(self):
        self.card.open_settings()
        self.cassette.changed()

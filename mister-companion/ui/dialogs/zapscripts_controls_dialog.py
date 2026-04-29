from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton


class ZapScriptsControlsDialog(QDialog):
    def __init__(self, parent=None, callbacks=None):
        super().__init__(parent)
        self.setWindowTitle("Controls")
        self.setMinimumWidth(250)

        layout = QVBoxLayout(self)

        self.callbacks = callbacks or {}

        self._add_button(layout, "Open Bluetooth Menu", "bluetooth")
        self._add_button(layout, "Open OSD Menu", "osd")
        self._add_button(layout, "Cycle Wallpaper", "wallpaper")
        self._add_button(layout, "Return to MiSTer Home", "home")

    def _add_button(self, layout, text, key):
        btn = QPushButton(text)
        btn.clicked.connect(lambda: self._trigger(key))
        layout.addWidget(btn)

    def _trigger(self, key):
        if key in self.callbacks:
            self.callbacks[key]()
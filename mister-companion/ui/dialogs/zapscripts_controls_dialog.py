from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton

from core.language import tr


class ZapScriptsControlsDialog(QDialog):
    def __init__(self, parent=None, callbacks=None):
        super().__init__(parent)
        self.setWindowTitle(tr("zapscripts_controls_dialog.window_title"))
        self.setMinimumWidth(250)

        layout = QVBoxLayout(self)

        self.callbacks = callbacks or {}

        self._add_button(layout, tr("zapscripts_controls_dialog.open_bluetooth_menu"), "bluetooth")
        self._add_button(layout, tr("zapscripts_controls_dialog.open_osd_menu"), "osd")
        self._add_button(layout, tr("zapscripts_controls_dialog.cycle_wallpaper"), "wallpaper")
        self._add_button(layout, tr("zapscripts_controls_dialog.return_home"), "home")

    def _add_button(self, layout, text, key):
        btn = QPushButton(text)
        btn.clicked.connect(lambda: self._trigger(key))
        layout.addWidget(btn)

    def _trigger(self, key):
        if key in self.callbacks:
            self.callbacks[key]()
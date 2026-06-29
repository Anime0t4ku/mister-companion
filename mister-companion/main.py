import os
import platform
import sys


def configure_qt_high_dpi():
    if platform.system() != "Darwin":
        return

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")


configure_qt_high_dpi()

from PyQt6.QtWidgets import QApplication

from core.config import load_config
from core.theme import apply_theme
from ui.custom_dialog import install_custom_dialogs
from ui.custom_message_dialog import install_custom_message_boxes
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    config = load_config()
    apply_theme(app, config.get("theme_mode", "auto"))

    install_custom_dialogs(app)
    install_custom_message_boxes()

    window = MainWindow(app)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
import sys
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
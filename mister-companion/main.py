import sys
from PyQt6.QtWidgets import QApplication

from core.config import load_config
from core.language import load_language
from core.theme import apply_theme
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    config = load_config()
    load_language(config.get("language", "en"))

    apply_theme(app, config.get("theme_mode", "auto"))

    window = MainWindow(app)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
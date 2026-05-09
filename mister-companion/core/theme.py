from pathlib import Path
import platform

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication, QStyleFactory


_ORIGINAL_STYLE = None
_ORIGINAL_PALETTE = None
_ORIGINAL_FONT = None

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"

COMBO_ARROW_DARK_PATH = ASSETS_DIR / "combo_arrow_dark.svg"
COMBO_ARROW_LIGHT_PATH = ASSETS_DIR / "combo_arrow_light.svg"
SPIN_UP_DARK_PATH = ASSETS_DIR / "spin_up_dark.svg"
SPIN_UP_LIGHT_PATH = ASSETS_DIR / "spin_up_light.svg"
SPIN_DOWN_DARK_PATH = ASSETS_DIR / "spin_down_dark.svg"
SPIN_DOWN_LIGHT_PATH = ASSETS_DIR / "spin_down_light.svg"

LOGO_LIGHT_PATH = ASSETS_DIR / "logo_1.png"
LOGO_DARK_PATH = ASSETS_DIR / "logo_2.png"


def init_theme_system(app: QApplication):
    global _ORIGINAL_STYLE, _ORIGINAL_PALETTE, _ORIGINAL_FONT

    if _ORIGINAL_STYLE is None:
        _ORIGINAL_STYLE = app.style().objectName()

    if _ORIGINAL_PALETTE is None:
        _ORIGINAL_PALETTE = QPalette(app.palette())

    if _ORIGINAL_FONT is None:
        _ORIGINAL_FONT = QFont(app.font())


def ensure_theme_assets():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    if not COMBO_ARROW_DARK_PATH.exists():
        COMBO_ARROW_DARK_PATH.write_text(
            """<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">
  <polyline points="2,4 6,8 10,4" fill="none" stroke="#1f1630" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""",
            encoding="utf-8",
        )

    if not COMBO_ARROW_LIGHT_PATH.exists():
        COMBO_ARROW_LIGHT_PATH.write_text(
            """<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">
  <polyline points="2,4 6,8 10,4" fill="none" stroke="#f2ecff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""",
            encoding="utf-8",
        )

    if not SPIN_UP_DARK_PATH.exists():
        SPIN_UP_DARK_PATH.write_text(
            """<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">
  <polyline points="2,6 5,3 8,6" fill="none" stroke="#1f1630" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""",
            encoding="utf-8",
        )

    if not SPIN_UP_LIGHT_PATH.exists():
        SPIN_UP_LIGHT_PATH.write_text(
            """<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">
  <polyline points="2,6 5,3 8,6" fill="none" stroke="#f2ecff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""",
            encoding="utf-8",
        )

    if not SPIN_DOWN_DARK_PATH.exists():
        SPIN_DOWN_DARK_PATH.write_text(
            """<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">
  <polyline points="2,4 5,7 8,4" fill="none" stroke="#1f1630" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""",
            encoding="utf-8",
        )

    if not SPIN_DOWN_LIGHT_PATH.exists():
        SPIN_DOWN_LIGHT_PATH.write_text(
            """<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">
  <polyline points="2,4 5,7 8,4" fill="none" stroke="#f2ecff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""",
            encoding="utf-8",
        )


def qss_url(path: Path) -> str:
    return path.resolve().as_posix()


def is_original_palette_dark() -> bool:
    if _ORIGINAL_PALETTE is None:
        return False

    window_color = _ORIGINAL_PALETTE.color(QPalette.ColorRole.Window)
    brightness = (
        window_color.red() * 0.299
        + window_color.green() * 0.587
        + window_color.blue() * 0.114
    )

    return brightness < 128


def normalize_theme_mode(mode: str) -> str:
    mode = (mode or "auto").strip().lower()

    if mode == "purple":
        return "dark"

    if mode not in {"auto", "light", "dark"}:
        return "auto"

    return mode


def resolve_theme_mode(mode: str) -> str:
    mode = normalize_theme_mode(mode)

    if mode == "auto":
        return "dark" if is_original_palette_dark() else "light"

    return mode


def normalize_ui_scale_percent(value) -> int:
    try:
        percent = int(value)
    except Exception:
        percent = 100

    if percent < 75:
        percent = 75
    elif percent > 125:
        percent = 125

    return percent


def ui_scale_factor(value) -> float:
    return normalize_ui_scale_percent(value) / 100.0


def make_scaler(value):
    factor = ui_scale_factor(value)

    def scale(px: int) -> int:
        try:
            px = int(px)
        except Exception:
            return 1

        if px == 0:
            return 0

        scaled = round(px * factor)

        if px > 0:
            return max(1, scaled)

        return min(-1, scaled)

    return scale


def apply_font_scale(app: QApplication, ui_scale_percent=100):
    if _ORIGINAL_FONT is None:
        return

    factor = ui_scale_factor(ui_scale_percent)
    font = QFont(_ORIGINAL_FONT)

    if _ORIGINAL_FONT.pointSizeF() > 0:
        font.setPointSizeF(max(1.0, _ORIGINAL_FONT.pointSizeF() * factor))
    elif _ORIGINAL_FONT.pixelSize() > 0:
        font.setPixelSize(max(1, round(_ORIGINAL_FONT.pixelSize() * factor)))

    app.setFont(font)


def linux_button_width_fix(ui_scale_percent=100) -> str:
    if platform.system() != "Linux":
        return ""

    s = make_scaler(ui_scale_percent)

    return f"""
    QPushButton {{
        min-width: {s(96)}px;
        padding-left: {s(14)}px;
        padding-right: {s(14)}px;
    }}

    QPushButton#WindowControlButton,
    QPushButton#WindowCloseButton {{
        min-width: 0px;
        padding-left: 0px;
        padding-right: 0px;
    }}
    """


def make_light_palette() -> QPalette:
    palette = QPalette()

    window = QColor("#f7f3ff")
    panel = QColor("#ffffff")
    panel_alt = QColor("#f0e8ff")
    text = QColor("#1f1630")
    accent = QColor("#7c3aed")
    accent_soft = QColor("#ede4ff")
    disabled = QColor("#a8a0b8")

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, panel)
    palette.setColor(QPalette.ColorRole.AlternateBase, panel_alt)
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, accent_soft)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ef4444"))
    palette.setColor(QPalette.ColorRole.Link, accent)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#f3eefc"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor("#eee8f7"))

    return palette


def make_dark_palette() -> QPalette:
    palette = QPalette()

    window = QColor("#120f1c")
    panel = QColor("#1b1628")
    panel_alt = QColor("#251f35")
    text = QColor("#f2ecff")
    disabled = QColor("#8d829e")
    accent = QColor("#8b5cf6")

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, panel)
    palette.setColor(QPalette.ColorRole.AlternateBase, panel_alt)
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#251f35"))
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, QColor("#2b2340"))
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ff7a7a"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#c4b5fd"))
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#171322"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor("#211b30"))

    return palette


def light_stylesheet(ui_scale_percent=100) -> str:
    combo_arrow_path = qss_url(COMBO_ARROW_DARK_PATH)
    spin_up_path = qss_url(SPIN_UP_DARK_PATH)
    spin_down_path = qss_url(SPIN_DOWN_DARK_PATH)
    linux_button_fix = linux_button_width_fix(ui_scale_percent)
    s = make_scaler(ui_scale_percent)

    return f"""
    QWidget {{
        background-color: #f7f3ff;
        color: #1f1630;
        selection-background-color: #7c3aed;
        selection-color: #ffffff;
    }}

    QMainWindow {{
        background-color: #f7f3ff;
    }}

    QLabel {{
        background: transparent;
        color: #1f1630;
    }}

    QTabWidget::pane {{
        border: {s(1)}px solid #d8c7f5;
        border-radius: {s(12)}px;
        background-color: #ffffff;
        top: -1px;
    }}

    QTabBar::tab {{
        background-color: #eee6fb;
        color: #5d5270;
        border: {s(1)}px solid #d8c7f5;
        border-bottom: none;
        padding: {s(7)}px {s(9)}px;
        margin-right: {s(1)}px;
        border-top-left-radius: {s(9)}px;
        border-top-right-radius: {s(9)}px;
        font-weight: 600;
    }}

    QTabBar::tab:selected {{
        background-color: #ffffff;
        color: #5b21b6;
        border-color: #b794f4;
    }}

    QTabBar::tab:hover:!selected {{
        background-color: #e7dcfb;
        color: #6d28d9;
    }}

    QTabBar::tab:disabled {{
        color: #aaa1b8;
        background-color: #eee8f7;
    }}

    QGroupBox {{
        background-color: #ffffff;
        border: {s(1)}px solid #d8c7f5;
        border-radius: {s(12)}px;
        margin-top: {s(14)}px;
        padding: {s(12)}px;
        font-weight: 700;
        color: #3b275f;
    }}

    QGroupBox QWidget {{
        background-color: transparent;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: {s(12)}px;
        padding: 0 {s(6)}px;
        background-color: #ffffff;
        color: #6d28d9;
    }}

    QFrame {{
        background-color: transparent;
        border: none;
    }}

    QCheckBox {{
        background: transparent;
        color: #1f1630;
        spacing: {s(8)}px;
    }}

    QCheckBox::indicator {{
        width: {s(16)}px;
        height: {s(16)}px;
        border-radius: {s(4)}px;
        border: {s(2)}px solid #8b5cf6;
        background-color: #ffffff;
    }}

    QCheckBox::indicator:hover {{
        border: {s(2)}px solid #6d28d9;
        background-color: #f3edff;
    }}

    QCheckBox::indicator:checked {{
        border: {s(2)}px solid #7c3aed;
        background-color: #7c3aed;
        image: none;
    }}

    QCheckBox::indicator:checked:hover {{
        border: {s(2)}px solid #5b21b6;
        background-color: #6d28d9;
    }}

    QCheckBox::indicator:disabled {{
        border: {s(2)}px solid #cfc4dd;
        background-color: #eee8f7;
    }}

    QCheckBox::indicator:checked:disabled {{
        border: {s(2)}px solid #b8a7cf;
        background-color: #b8a7cf;
    }}

    QRadioButton {{
        background: transparent;
        color: #1f1630;
        spacing: {s(8)}px;
    }}

    QRadioButton::indicator {{
        width: {s(16)}px;
        height: {s(16)}px;
        border-radius: {s(8)}px;
        border: {s(2)}px solid #8b5cf6;
        background-color: #ffffff;
    }}

    QRadioButton::indicator:hover {{
        border: {s(2)}px solid #6d28d9;
        background-color: #f3edff;
    }}

    QRadioButton::indicator:checked {{
        border: {s(2)}px solid #7c3aed;
        background-color: #7c3aed;
    }}

    QRadioButton::indicator:checked:hover {{
        border: {s(2)}px solid #5b21b6;
        background-color: #6d28d9;
    }}

    QRadioButton::indicator:disabled {{
        border: {s(2)}px solid #cfc4dd;
        background-color: #eee8f7;
    }}

    QRadioButton::indicator:checked:disabled {{
        border: {s(2)}px solid #b8a7cf;
        background-color: #b8a7cf;
    }}

    QPushButton {{
        background-color: #ede4ff;
        color: #2f1b4c;
        border: {s(1)}px solid #c9b2ef;
        border-radius: {s(9)}px;
        padding: {s(7)}px {s(12)}px;
        font-weight: 600;
    }}

    QPushButton:hover {{
        background-color: #e0d0ff;
        border-color: #a78bfa;
        color: #4c1d95;
    }}

    QPushButton:pressed {{
        background-color: #c4b5fd;
        border-color: #7c3aed;
    }}

    QPushButton:disabled {{
        background-color: #eee8f7;
        color: #aaa1b8;
        border-color: #ded4ee;
    }}

    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QSpinBox,
    QDoubleSpinBox,
    QDateEdit,
    QTimeEdit,
    QDateTimeEdit {{
        background-color: #ffffff;
        color: #1f1630;
        border: {s(1)}px solid #cdbbef;
        border-radius: {s(8)}px;
        padding: {s(6)}px;
        selection-background-color: #7c3aed;
        selection-color: #ffffff;
    }}

    QLineEdit:focus,
    QTextEdit:focus,
    QPlainTextEdit:focus,
    QSpinBox:focus,
    QDoubleSpinBox:focus,
    QDateEdit:focus,
    QTimeEdit:focus,
    QDateTimeEdit:focus {{
        border: {s(1)}px solid #8b5cf6;
        background-color: #ffffff;
    }}

    QLineEdit:disabled,
    QTextEdit:disabled,
    QPlainTextEdit:disabled {{
        background-color: #f0e8ff;
        color: #aaa1b8;
        border-color: #ded4ee;
    }}

    QSpinBox,
    QDoubleSpinBox {{
        padding-right: {s(32)}px;
    }}

    QSpinBox::up-button,
    QDoubleSpinBox::up-button {{
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: {s(26)}px;
        border: none;
        border-left: {s(1)}px solid #d8c7f5;
        border-top-right-radius: {s(8)}px;
        background-color: transparent;
    }}

    QSpinBox::down-button,
    QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: {s(26)}px;
        border: none;
        border-left: {s(1)}px solid #d8c7f5;
        border-bottom-right-radius: {s(8)}px;
        background-color: transparent;
    }}

    QSpinBox::up-button:hover,
    QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover,
    QDoubleSpinBox::down-button:hover {{
        background-color: #ede4ff;
    }}

    QSpinBox::up-arrow,
    QDoubleSpinBox::up-arrow {{
        image: url("{spin_up_path}");
        width: {s(10)}px;
        height: {s(10)}px;
    }}

    QSpinBox::down-arrow,
    QDoubleSpinBox::down-arrow {{
        image: url("{spin_down_path}");
        width: {s(10)}px;
        height: {s(10)}px;
    }}

    QSpinBox::up-arrow:disabled,
    QDoubleSpinBox::up-arrow:disabled,
    QSpinBox::down-arrow:disabled,
    QDoubleSpinBox::down-arrow:disabled {{
        image: none;
    }}

    QComboBox {{
        background-color: #ffffff;
        color: #1f1630;
        border: {s(1)}px solid #cdbbef;
        border-radius: {s(8)}px;
        padding: {s(6)}px {s(34)}px {s(6)}px {s(8)}px;
        font-weight: 600;
        min-height: {s(22)}px;
    }}

    QComboBox:hover {{
        border-color: #a78bfa;
    }}

    QComboBox:focus {{
        border-color: #8b5cf6;
    }}

    QComboBox:disabled {{
        background-color: #f0e8ff;
        color: #aaa1b8;
        border-color: #ded4ee;
    }}

    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: {s(28)}px;
        border: none;
        border-left: {s(1)}px solid #d8c7f5;
        border-top-right-radius: {s(8)}px;
        border-bottom-right-radius: {s(8)}px;
        background-color: transparent;
    }}

    QComboBox::drop-down:hover {{
        background-color: #ede4ff;
    }}

    QComboBox::down-arrow {{
        image: url("{combo_arrow_path}");
        width: {s(12)}px;
        height: {s(12)}px;
        margin-right: {s(8)}px;
    }}

    QComboBox::down-arrow:disabled {{
        image: url("{combo_arrow_path}");
        opacity: 0.45;
    }}

    QComboBox QAbstractItemView {{
        background-color: #ffffff;
        color: #1f1630;
        border: {s(1)}px solid #cdbbef;
        selection-background-color: #ede4ff;
        selection-color: #4c1d95;
        outline: none;
        padding: {s(4)}px;
    }}

    QListWidget,
    QTreeWidget,
    QTableWidget,
    QTableView,
    QTreeView {{
        background-color: #ffffff;
        alternate-background-color: #f3edff;
        color: #1f1630;
        border: {s(1)}px solid #d8c7f5;
        border-radius: {s(10)}px;
        gridline-color: #e4d8f8;
        selection-background-color: #ede4ff;
        selection-color: #4c1d95;
    }}

    QHeaderView::section {{
        background-color: #eee6fb;
        color: #3b275f;
        border: none;
        border-right: {s(1)}px solid #d8c7f5;
        border-bottom: {s(1)}px solid #d8c7f5;
        padding: {s(6)}px;
        font-weight: 700;
    }}

    QScrollArea {{
        background: transparent;
        border: none;
    }}

    QScrollBar:vertical {{
        background: #eee6fb;
        width: {s(12)}px;
        margin: 0;
        border-radius: {s(6)}px;
    }}

    QScrollBar::handle:vertical {{
        background: #b794f4;
        min-height: {s(24)}px;
        border-radius: {s(6)}px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: #8b5cf6;
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QScrollBar:horizontal {{
        background: #eee6fb;
        height: {s(12)}px;
        margin: 0;
        border-radius: {s(6)}px;
    }}

    QScrollBar::handle:horizontal {{
        background: #b794f4;
        min-width: {s(24)}px;
        border-radius: {s(6)}px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background: #8b5cf6;
    }}

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    QMenuBar {{
        background-color: #f7f3ff;
        color: #1f1630;
    }}

    QMenuBar::item:selected {{
        background-color: #ede4ff;
        color: #4c1d95;
    }}

    QMenu {{
        background-color: #ffffff;
        color: #1f1630;
        border: {s(1)}px solid #d8c7f5;
    }}

    QMenu::item:selected {{
        background-color: #ede4ff;
        color: #4c1d95;
    }}

    QProgressBar {{
        background-color: #eee6fb;
        color: #1f1630;
        border: {s(1)}px solid #d8c7f5;
        border-radius: {s(8)}px;
        text-align: center;
        font-weight: 600;
    }}

    QProgressBar::chunk {{
        background-color: #8b5cf6;
        border-radius: {s(7)}px;
    }}

    QToolTip {{
        background-color: #ffffff;
        color: #1f1630;
        border: {s(1)}px solid #cdbbef;
        padding: {s(6)}px;
    }}

    {linux_button_fix}
    """


def dark_stylesheet(ui_scale_percent=100) -> str:
    combo_arrow_path = qss_url(COMBO_ARROW_LIGHT_PATH)
    spin_up_path = qss_url(SPIN_UP_LIGHT_PATH)
    spin_down_path = qss_url(SPIN_DOWN_LIGHT_PATH)
    linux_button_fix = linux_button_width_fix(ui_scale_percent)
    s = make_scaler(ui_scale_percent)

    return f"""
    QWidget {{
        background-color: #120f1c;
        color: #f2ecff;
        selection-background-color: #8b5cf6;
        selection-color: #ffffff;
    }}

    QMainWindow {{
        background-color: #120f1c;
    }}

    QLabel {{
        background: transparent;
        color: #f2ecff;
    }}

    QTabWidget::pane {{
        border: {s(1)}px solid #34294b;
        border-radius: {s(12)}px;
        background-color: #1b1628;
        top: -1px;
    }}

    QTabBar::tab {{
        background-color: #1a1526;
        color: #a99cbd;
        border: {s(1)}px solid #34294b;
        border-bottom: none;
        padding: {s(7)}px {s(9)}px;
        margin-right: {s(1)}px;
        border-top-left-radius: {s(9)}px;
        border-top-right-radius: {s(9)}px;
        font-weight: 600;
    }}

    QTabBar::tab:selected {{
        background-color: #251f35;
        color: #f5f0ff;
        border-color: #8b5cf6;
    }}

    QTabBar::tab:hover:!selected {{
        background-color: #211b30;
        color: #d8ccff;
        border-color: #6d54a8;
    }}

    QTabBar::tab:disabled {{
        color: #5f536f;
        background-color: #171322;
    }}

    QGroupBox {{
        background-color: #1b1628;
        border: {s(1)}px solid #34294b;
        border-radius: {s(12)}px;
        margin-top: {s(14)}px;
        padding: {s(12)}px;
        font-weight: 700;
        color: #f2ecff;
    }}

    QGroupBox QWidget {{
        background-color: transparent;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: {s(12)}px;
        padding: 0 {s(6)}px;
        background-color: #1b1628;
        color: #c4b5fd;
    }}

    QFrame {{
        background-color: transparent;
        border: none;
    }}

    QCheckBox {{
        background: transparent;
        color: #f2ecff;
        spacing: {s(8)}px;
    }}

    QCheckBox::indicator {{
        width: {s(16)}px;
        height: {s(16)}px;
        border-radius: {s(4)}px;
        border: {s(2)}px solid #8b5cf6;
        background-color: #171322;
    }}

    QCheckBox::indicator:hover {{
        border: {s(2)}px solid #c4b5fd;
        background-color: #211b30;
    }}

    QCheckBox::indicator:checked {{
        border: {s(2)}px solid #8b5cf6;
        background-color: #8b5cf6;
        image: none;
    }}

    QCheckBox::indicator:checked:hover {{
        border: {s(2)}px solid #c4b5fd;
        background-color: #a78bfa;
    }}

    QCheckBox::indicator:disabled {{
        border: {s(2)}px solid #3b3151;
        background-color: #211b30;
    }}

    QCheckBox::indicator:checked:disabled {{
        border: {s(2)}px solid #4a3b68;
        background-color: #4a3b68;
    }}

    QRadioButton {{
        background: transparent;
        color: #f2ecff;
        spacing: {s(8)}px;
    }}

    QRadioButton::indicator {{
        width: {s(16)}px;
        height: {s(16)}px;
        border-radius: {s(8)}px;
        border: {s(2)}px solid #8b5cf6;
        background-color: #171322;
    }}

    QRadioButton::indicator:hover {{
        border: {s(2)}px solid #c4b5fd;
        background-color: #211b30;
    }}

    QRadioButton::indicator:checked {{
        border: {s(2)}px solid #8b5cf6;
        background-color: #8b5cf6;
    }}

    QRadioButton::indicator:checked:hover {{
        border: {s(2)}px solid #c4b5fd;
        background-color: #a78bfa;
    }}

    QRadioButton::indicator:disabled {{
        border: {s(2)}px solid #3b3151;
        background-color: #211b30;
    }}

    QRadioButton::indicator:checked:disabled {{
        border: {s(2)}px solid #4a3b68;
        background-color: #4a3b68;
    }}

    QPushButton {{
        background-color: #2b2340;
        color: #f2ecff;
        border: {s(1)}px solid #4a3b68;
        border-radius: {s(9)}px;
        padding: {s(7)}px {s(12)}px;
        font-weight: 600;
    }}

    QPushButton:hover {{
        background-color: #3a2d58;
        border-color: #8b5cf6;
        color: #ffffff;
    }}

    QPushButton:pressed {{
        background-color: #6d28d9;
        border-color: #a78bfa;
    }}

    QPushButton:disabled {{
        background-color: #211b30;
        color: #716681;
        border-color: #302640;
    }}

    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QSpinBox,
    QDoubleSpinBox,
    QDateEdit,
    QTimeEdit,
    QDateTimeEdit {{
        background-color: #171322;
        color: #f2ecff;
        border: {s(1)}px solid #3b3151;
        border-radius: {s(8)}px;
        padding: {s(6)}px;
        selection-background-color: #8b5cf6;
        selection-color: #ffffff;
    }}

    QLineEdit:focus,
    QTextEdit:focus,
    QPlainTextEdit:focus,
    QSpinBox:focus,
    QDoubleSpinBox:focus,
    QDateEdit:focus,
    QTimeEdit:focus,
    QDateTimeEdit:focus {{
        border: {s(1)}px solid #8b5cf6;
        background-color: #1c1729;
    }}

    QLineEdit:disabled,
    QTextEdit:disabled,
    QPlainTextEdit:disabled {{
        background-color: #171322;
        color: #716681;
        border-color: #302640;
    }}

    QSpinBox,
    QDoubleSpinBox {{
        padding-right: {s(32)}px;
    }}

    QSpinBox::up-button,
    QDoubleSpinBox::up-button {{
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: {s(26)}px;
        border: none;
        border-left: {s(1)}px solid #34294b;
        border-top-right-radius: {s(8)}px;
        background-color: transparent;
    }}

    QSpinBox::down-button,
    QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: {s(26)}px;
        border: none;
        border-left: {s(1)}px solid #34294b;
        border-bottom-right-radius: {s(8)}px;
        background-color: transparent;
    }}

    QSpinBox::up-button:hover,
    QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover,
    QDoubleSpinBox::down-button:hover {{
        background-color: #211b30;
    }}

    QSpinBox::up-arrow,
    QDoubleSpinBox::up-arrow {{
        image: url("{spin_up_path}");
        width: {s(10)}px;
        height: {s(10)}px;
    }}

    QSpinBox::down-arrow,
    QDoubleSpinBox::down-arrow {{
        image: url("{spin_down_path}");
        width: {s(10)}px;
        height: {s(10)}px;
    }}

    QSpinBox::up-arrow:disabled,
    QDoubleSpinBox::up-arrow:disabled,
    QSpinBox::down-arrow:disabled,
    QDoubleSpinBox::down-arrow:disabled {{
        image: none;
    }}

    QComboBox {{
        background-color: #171322;
        color: #f2ecff;
        border: {s(1)}px solid #3b3151;
        border-radius: {s(8)}px;
        padding: {s(6)}px {s(34)}px {s(6)}px {s(8)}px;
        font-weight: 600;
        min-height: {s(22)}px;
    }}

    QComboBox:hover {{
        border-color: #8b5cf6;
    }}

    QComboBox:focus {{
        border-color: #a78bfa;
    }}

    QComboBox:disabled {{
        background-color: #171322;
        color: #716681;
        border-color: #302640;
    }}

    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: {s(28)}px;
        border: none;
        border-left: {s(1)}px solid #34294b;
        border-top-right-radius: {s(8)}px;
        border-bottom-right-radius: {s(8)}px;
        background-color: transparent;
    }}

    QComboBox::drop-down:hover {{
        background-color: #211b30;
    }}

    QComboBox::down-arrow {{
        image: url("{combo_arrow_path}");
        width: {s(12)}px;
        height: {s(12)}px;
        margin-right: {s(8)}px;
    }}

    QComboBox::down-arrow:disabled {{
        image: url("{combo_arrow_path}");
        opacity: 0.45;
    }}

    QComboBox QAbstractItemView {{
        background-color: #1b1628;
        color: #f2ecff;
        border: {s(1)}px solid #4a3b68;
        selection-background-color: #33264f;
        selection-color: #ffffff;
        outline: none;
        padding: {s(4)}px;
    }}

    QListWidget,
    QTreeWidget,
    QTableWidget,
    QTableView,
    QTreeView {{
        background-color: #171322;
        alternate-background-color: #1f1930;
        color: #f2ecff;
        border: {s(1)}px solid #34294b;
        border-radius: {s(10)}px;
        gridline-color: #2e2540;
        selection-background-color: #33264f;
        selection-color: #ffffff;
    }}

    QHeaderView::section {{
        background-color: #211b30;
        color: #d8ccff;
        border: none;
        border-right: {s(1)}px solid #34294b;
        border-bottom: {s(1)}px solid #34294b;
        padding: {s(6)}px;
        font-weight: 700;
    }}

    QScrollArea {{
        background: transparent;
        border: none;
    }}

    QScrollBar:vertical {{
        background: #171322;
        width: {s(12)}px;
        margin: 0;
        border-radius: {s(6)}px;
    }}

    QScrollBar::handle:vertical {{
        background: #4a3b68;
        min-height: {s(24)}px;
        border-radius: {s(6)}px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: #8b5cf6;
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QScrollBar:horizontal {{
        background: #171322;
        height: {s(12)}px;
        margin: 0;
        border-radius: {s(6)}px;
    }}

    QScrollBar::handle:horizontal {{
        background: #4a3b68;
        min-width: {s(24)}px;
        border-radius: {s(6)}px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background: #8b5cf6;
    }}

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    QMenuBar {{
        background-color: #120f1c;
        color: #f2ecff;
    }}

    QMenuBar::item:selected {{
        background-color: #2b2340;
        color: #ffffff;
    }}

    QMenu {{
        background-color: #1b1628;
        color: #f2ecff;
        border: {s(1)}px solid #34294b;
    }}

    QMenu::item:selected {{
        background-color: #33264f;
        color: #ffffff;
    }}

    QProgressBar {{
        background-color: #171322;
        color: #f2ecff;
        border: {s(1)}px solid #34294b;
        border-radius: {s(8)}px;
        text-align: center;
        font-weight: 600;
    }}

    QProgressBar::chunk {{
        background-color: #8b5cf6;
        border-radius: {s(7)}px;
    }}

    QToolTip {{
        background-color: #251f35;
        color: #f2ecff;
        border: {s(1)}px solid #4a3b68;
        padding: {s(6)}px;
    }}

    {linux_button_fix}
    """


def apply_theme(app: QApplication, mode: str, ui_scale_percent=100):
    init_theme_system(app)
    ensure_theme_assets()

    resolved_mode = resolve_theme_mode(mode)
    ui_scale_percent = normalize_ui_scale_percent(ui_scale_percent)

    app.setStyle(QStyleFactory.create("Fusion"))
    apply_font_scale(app, ui_scale_percent)

    if resolved_mode == "light":
        app.setPalette(make_light_palette())
        app.setStyleSheet(light_stylesheet(ui_scale_percent))
    else:
        app.setPalette(make_dark_palette())
        app.setStyleSheet(dark_stylesheet(ui_scale_percent))
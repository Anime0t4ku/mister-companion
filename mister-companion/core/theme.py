from pathlib import Path
import platform

from PyQt6.QtGui import QColor, QFont, QPalette

from core.app_paths import is_macos_packaged_app
from core.custom_themes import get_custom_theme, is_custom_theme_key, themes_dir
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

    if is_custom_theme_key(mode):
        return mode

    if mode not in {"auto", "light", "dark"}:
        return "auto"

    return mode


def resolve_theme_mode(mode: str) -> str:
    mode = normalize_theme_mode(mode)

    if is_custom_theme_key(mode):
        theme = get_custom_theme(mode)
        if theme:
            return "custom"
        return "dark"

    if mode == "auto":
        return "dark" if is_original_palette_dark() else "light"

    return mode


def color_brightness(color: QColor) -> float:
    return color.red() * 0.299 + color.green() * 0.587 + color.blue() * 0.114


def is_dark_color(color: QColor) -> bool:
    return color_brightness(color) < 128


def mix_colors(a: QColor, b: QColor, amount: float) -> QColor:
    amount = max(0.0, min(1.0, amount))
    inverse = 1.0 - amount
    return QColor(
        round(a.red() * inverse + b.red() * amount),
        round(a.green() * inverse + b.green() * amount),
        round(a.blue() * inverse + b.blue() * amount),
    )


def color_hex(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexRgb)


def readable_text_for(color: QColor) -> str:
    return "#ffffff" if is_dark_color(color) else "#111111"


def custom_theme_roles(theme: dict) -> dict:
    background = QColor(theme["background"])
    surface = QColor(theme["surface"])
    accent = QColor(theme["accent"])
    text = QColor(theme["text"])
    dark = is_dark_color(background)

    if dark:
        surface_alt = mix_colors(surface, text, 0.08)
        input_bg = mix_colors(background, surface, 0.45)
        button_bg = mix_colors(surface, accent, 0.18)
        button_hover = mix_colors(surface, accent, 0.30)
        button_pressed = mix_colors(surface, accent, 0.48)
        border = mix_colors(surface, text, 0.18)
        border_soft = mix_colors(surface, text, 0.10)
        muted_text = mix_colors(text, background, 0.45)
        disabled_bg = mix_colors(background, surface, 0.55)
        selected_soft = mix_colors(surface, accent, 0.32)
        scrollbar_bg = mix_colors(background, surface, 0.65)
        scrollbar_handle = mix_colors(surface, accent, 0.45)
        tooltip_bg = surface_alt
    else:
        surface_alt = mix_colors(surface, accent, 0.10)
        input_bg = surface
        button_bg = mix_colors(surface, accent, 0.16)
        button_hover = mix_colors(surface, accent, 0.26)
        button_pressed = mix_colors(surface, accent, 0.40)
        border = mix_colors(surface, accent, 0.32)
        border_soft = mix_colors(surface, accent, 0.20)
        muted_text = mix_colors(text, background, 0.45)
        disabled_bg = mix_colors(surface, background, 0.55)
        selected_soft = mix_colors(surface, accent, 0.20)
        scrollbar_bg = mix_colors(surface, accent, 0.14)
        scrollbar_handle = mix_colors(surface, accent, 0.45)
        tooltip_bg = surface

    return {
        "background": color_hex(background),
        "surface": color_hex(surface),
        "surface_alt": color_hex(surface_alt),
        "input_bg": color_hex(input_bg),
        "button_bg": color_hex(button_bg),
        "button_hover": color_hex(button_hover),
        "button_pressed": color_hex(button_pressed),
        "border": color_hex(border),
        "border_soft": color_hex(border_soft),
        "accent": color_hex(accent),
        "accent_hover": color_hex(mix_colors(accent, text if dark else background, 0.18)),
        "accent_pressed": color_hex(mix_colors(accent, background if dark else text, 0.18)),
        "text": color_hex(text),
        "muted_text": color_hex(muted_text),
        "disabled_bg": color_hex(disabled_bg),
        "selected_soft": color_hex(selected_soft),
        "selected_text": readable_text_for(accent),
        "scrollbar_bg": color_hex(scrollbar_bg),
        "scrollbar_handle": color_hex(scrollbar_handle),
        "tooltip_bg": color_hex(tooltip_bg),
        "bright_text": theme.get("error", "#ff7a7a" if dark else "#ef4444"),
        "is_dark": dark,
    }


def custom_palette(theme: dict) -> QPalette:
    roles = custom_theme_roles(theme)
    palette = QPalette()

    palette.setColor(QPalette.ColorRole.Window, QColor(roles["background"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(roles["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(roles["input_bg"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(roles["surface_alt"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(roles["tooltip_bg"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(roles["text"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(roles["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(roles["button_bg"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(roles["text"]))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(roles["bright_text"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(roles["accent"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(roles["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(roles["selected_text"]))

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(roles["muted_text"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(roles["muted_text"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(roles["muted_text"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(roles["disabled_bg"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(roles["disabled_bg"]))

    return palette


def theme_accent_color(mode: str) -> str:
    mode = normalize_theme_mode(mode)
    if is_custom_theme_key(mode):
        theme = get_custom_theme(mode)
        if theme:
            return theme["accent"]
    resolved_mode = resolve_theme_mode(mode)
    return "#7c3aed" if resolved_mode == "light" else "#8b5cf6"


def theme_text_color(mode: str) -> str:
    mode = normalize_theme_mode(mode)
    if is_custom_theme_key(mode):
        theme = get_custom_theme(mode)
        if theme:
            return theme["text"]
    resolved_mode = resolve_theme_mode(mode)
    return "#1f1630" if resolved_mode == "light" else "#f2ecff"


def theme_logo_mode(mode: str) -> str:
    mode = normalize_theme_mode(mode)
    if is_custom_theme_key(mode):
        theme = get_custom_theme(mode)
        if theme:
            logo = str(theme.get("logo", "")).strip().lower()
            if logo == "black":
                return "light"
            if logo == "white":
                return "dark"
            return "dark" if custom_theme_roles(theme)["is_dark"] else "light"
    return resolve_theme_mode(mode)


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


def platform_base_font_point_size() -> float:
    if platform.system() == "Darwin":
        return 10.0

    return 9.0


def scaled_font_point_size(ui_scale_percent=100) -> float:
    factor = ui_scale_factor(ui_scale_percent)
    return max(1.0, platform_base_font_point_size() * factor)


def qss_base_font_rule(ui_scale_percent=100) -> str:
    return f"font-size: {scaled_font_point_size(ui_scale_percent):.2f}pt;"


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

    font.setPointSizeF(scaled_font_point_size(ui_scale_percent))
    current = app.font()
    if current.family() != font.family() or abs(current.pointSizeF() - font.pointSizeF()) > 0.01:
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
    base_font_rule = qss_base_font_rule(ui_scale_percent)
    s = make_scaler(ui_scale_percent)

    return f"""
    QWidget {{
        {base_font_rule}
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

    QTabWidget[overlayMode="true"]::pane {{
        top: 0px;
    }}

    QFrame#OverlayMenuPanel {{
        background-color: #ffffff;
        border: none;
        border-right: {s(1)}px solid #d8c7f5;
        border-radius: 0px;
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
    base_font_rule = qss_base_font_rule(ui_scale_percent)
    s = make_scaler(ui_scale_percent)

    return f"""
    QWidget {{
        {base_font_rule}
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

    QTabWidget[overlayMode="true"]::pane {{
        top: 0px;
    }}

    QFrame#OverlayMenuPanel {{
        background-color: #1b1628;
        border: none;
        border-right: {s(1)}px solid #34294b;
        border-radius: 0px;
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


def custom_stylesheet(theme: dict, ui_scale_percent=100) -> str:
    roles = custom_theme_roles(theme)
    arrow_path = qss_url(COMBO_ARROW_LIGHT_PATH if roles["is_dark"] else COMBO_ARROW_DARK_PATH)
    spin_up_path = qss_url(SPIN_UP_LIGHT_PATH if roles["is_dark"] else SPIN_UP_DARK_PATH)
    spin_down_path = qss_url(SPIN_DOWN_LIGHT_PATH if roles["is_dark"] else SPIN_DOWN_DARK_PATH)
    linux_button_fix = linux_button_width_fix(ui_scale_percent)
    base_font_rule = qss_base_font_rule(ui_scale_percent)
    s = make_scaler(ui_scale_percent)

    return f"""
    QWidget {{
        {base_font_rule}
        background-color: {roles['background']};
        color: {roles['text']};
        selection-background-color: {roles['accent']};
        selection-color: {roles['selected_text']};
    }}

    QMainWindow {{
        background-color: {roles['background']};
    }}

    QLabel {{
        background: transparent;
        color: {roles['text']};
    }}

    QTabWidget::pane {{
        border: {s(1)}px solid {roles['border']};
        border-radius: {s(12)}px;
        background-color: {roles['surface']};
        top: -1px;
    }}

    QTabBar::tab {{
        background-color: {roles['surface_alt']};
        color: {roles['muted_text']};
        border: {s(1)}px solid {roles['border']};
        border-bottom: none;
        padding: {s(7)}px {s(9)}px;
        margin-right: {s(1)}px;
        border-top-left-radius: {s(9)}px;
        border-top-right-radius: {s(9)}px;
        font-weight: 600;
    }}

    QTabBar::tab:selected {{
        background-color: {roles['surface']};
        color: {roles['text']};
        border-color: {roles['accent']};
    }}

    QTabBar::tab:hover:!selected {{
        background-color: {roles['button_hover']};
        color: {roles['text']};
        border-color: {roles['accent_hover']};
    }}

    QTabBar::tab:disabled {{
        color: {roles['muted_text']};
        background-color: {roles['disabled_bg']};
    }}

    QTabWidget[overlayMode="true"]::pane {{
        top: 0px;
    }}

    QFrame#OverlayMenuPanel {{
        background-color: {roles['surface']};
        border: none;
        border-right: {s(1)}px solid {roles['border']};
        border-radius: 0px;
    }}

    QGroupBox {{
        background-color: {roles['surface']};
        border: {s(1)}px solid {roles['border']};
        border-radius: {s(12)}px;
        margin-top: {s(14)}px;
        padding: {s(12)}px;
        font-weight: 700;
        color: {roles['text']};
    }}

    QGroupBox QWidget {{
        background-color: transparent;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: {s(12)}px;
        padding: 0 {s(6)}px;
        background-color: {roles['surface']};
        color: {roles['accent']};
    }}

    QFrame {{
        background-color: transparent;
        border: none;
    }}

    QCheckBox,
    QRadioButton {{
        background: transparent;
        color: {roles['text']};
        spacing: {s(8)}px;
    }}

    QCheckBox::indicator {{
        width: {s(16)}px;
        height: {s(16)}px;
        border-radius: {s(4)}px;
        border: {s(2)}px solid {roles['accent']};
        background-color: {roles['input_bg']};
    }}

    QCheckBox::indicator:hover {{
        border: {s(2)}px solid {roles['accent_hover']};
        background-color: {roles['button_hover']};
    }}

    QCheckBox::indicator:checked {{
        border: {s(2)}px solid {roles['accent']};
        background-color: {roles['accent']};
        image: none;
    }}

    QCheckBox::indicator:checked:hover {{
        border: {s(2)}px solid {roles['accent_hover']};
        background-color: {roles['accent_hover']};
    }}

    QCheckBox::indicator:disabled {{
        border: {s(2)}px solid {roles['border_soft']};
        background-color: {roles['disabled_bg']};
    }}

    QCheckBox::indicator:checked:disabled {{
        border: {s(2)}px solid {roles['border']};
        background-color: {roles['border']};
    }}

    QRadioButton::indicator {{
        width: {s(16)}px;
        height: {s(16)}px;
        border-radius: {s(8)}px;
        border: {s(2)}px solid {roles['accent']};
        background-color: {roles['input_bg']};
    }}

    QRadioButton::indicator:hover {{
        border: {s(2)}px solid {roles['accent_hover']};
        background-color: {roles['button_hover']};
    }}

    QRadioButton::indicator:checked {{
        border: {s(2)}px solid {roles['accent']};
        background-color: {roles['accent']};
    }}

    QRadioButton::indicator:checked:hover {{
        border: {s(2)}px solid {roles['accent_hover']};
        background-color: {roles['accent_hover']};
    }}

    QRadioButton::indicator:disabled {{
        border: {s(2)}px solid {roles['border_soft']};
        background-color: {roles['disabled_bg']};
    }}

    QRadioButton::indicator:checked:disabled {{
        border: {s(2)}px solid {roles['border']};
        background-color: {roles['border']};
    }}

    QPushButton {{
        background-color: {roles['button_bg']};
        color: {roles['text']};
        border: {s(1)}px solid {roles['border']};
        border-radius: {s(9)}px;
        padding: {s(7)}px {s(12)}px;
        font-weight: 600;
    }}

    QPushButton:hover {{
        background-color: {roles['button_hover']};
        border-color: {roles['accent']};
        color: {roles['text']};
    }}

    QPushButton:pressed {{
        background-color: {roles['button_pressed']};
        border-color: {roles['accent_hover']};
    }}

    QPushButton:disabled {{
        background-color: {roles['disabled_bg']};
        color: {roles['muted_text']};
        border-color: {roles['border_soft']};
    }}

    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QSpinBox,
    QDoubleSpinBox,
    QDateEdit,
    QTimeEdit,
    QDateTimeEdit {{
        background-color: {roles['input_bg']};
        color: {roles['text']};
        border: {s(1)}px solid {roles['border']};
        border-radius: {s(8)}px;
        padding: {s(6)}px;
        selection-background-color: {roles['accent']};
        selection-color: {roles['selected_text']};
    }}

    QLineEdit:focus,
    QTextEdit:focus,
    QPlainTextEdit:focus,
    QSpinBox:focus,
    QDoubleSpinBox:focus,
    QDateEdit:focus,
    QTimeEdit:focus,
    QDateTimeEdit:focus {{
        border: {s(1)}px solid {roles['accent']};
        background-color: {roles['input_bg']};
    }}

    QLineEdit:disabled,
    QTextEdit:disabled,
    QPlainTextEdit:disabled {{
        background-color: {roles['disabled_bg']};
        color: {roles['muted_text']};
        border-color: {roles['border_soft']};
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
        border-left: {s(1)}px solid {roles['border']};
        border-top-right-radius: {s(8)}px;
        background-color: transparent;
    }}

    QSpinBox::down-button,
    QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: {s(26)}px;
        border: none;
        border-left: {s(1)}px solid {roles['border']};
        border-bottom-right-radius: {s(8)}px;
        background-color: transparent;
    }}

    QSpinBox::up-button:hover,
    QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover,
    QDoubleSpinBox::down-button:hover {{
        background-color: {roles['button_hover']};
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
        background-color: {roles['input_bg']};
        color: {roles['text']};
        border: {s(1)}px solid {roles['border']};
        border-radius: {s(8)}px;
        padding: {s(6)}px {s(34)}px {s(6)}px {s(8)}px;
        font-weight: 600;
        min-height: {s(22)}px;
    }}

    QComboBox:hover {{
        border-color: {roles['accent']};
    }}

    QComboBox:focus {{
        border-color: {roles['accent_hover']};
    }}

    QComboBox:disabled {{
        background-color: {roles['disabled_bg']};
        color: {roles['muted_text']};
        border-color: {roles['border_soft']};
    }}

    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: {s(28)}px;
        border: none;
        border-left: {s(1)}px solid {roles['border']};
        border-top-right-radius: {s(8)}px;
        border-bottom-right-radius: {s(8)}px;
        background-color: transparent;
    }}

    QComboBox::drop-down:hover {{
        background-color: {roles['button_hover']};
    }}

    QComboBox::down-arrow {{
        image: url("{arrow_path}");
        width: {s(12)}px;
        height: {s(12)}px;
        margin-right: {s(8)}px;
    }}

    QComboBox::down-arrow:disabled {{
        image: url("{arrow_path}");
        opacity: 0.45;
    }}

    QComboBox QAbstractItemView {{
        background-color: {roles['surface']};
        color: {roles['text']};
        border: {s(1)}px solid {roles['border']};
        selection-background-color: {roles['selected_soft']};
        selection-color: {roles['text']};
        outline: none;
        padding: {s(4)}px;
    }}

    QListWidget,
    QTreeWidget,
    QTableWidget,
    QTableView,
    QTreeView {{
        background-color: {roles['input_bg']};
        alternate-background-color: {roles['surface_alt']};
        color: {roles['text']};
        border: {s(1)}px solid {roles['border']};
        border-radius: {s(10)}px;
        gridline-color: {roles['border_soft']};
        selection-background-color: {roles['selected_soft']};
        selection-color: {roles['text']};
    }}

    QHeaderView::section {{
        background-color: {roles['surface_alt']};
        color: {roles['text']};
        border: none;
        border-right: {s(1)}px solid {roles['border']};
        border-bottom: {s(1)}px solid {roles['border']};
        padding: {s(6)}px;
        font-weight: 700;
    }}

    QScrollArea {{
        background: transparent;
        border: none;
    }}

    QScrollBar:vertical {{
        background: {roles['scrollbar_bg']};
        width: {s(12)}px;
        margin: 0;
        border-radius: {s(6)}px;
    }}

    QScrollBar::handle:vertical {{
        background: {roles['scrollbar_handle']};
        min-height: {s(24)}px;
        border-radius: {s(6)}px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {roles['accent']};
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QScrollBar:horizontal {{
        background: {roles['scrollbar_bg']};
        height: {s(12)}px;
        margin: 0;
        border-radius: {s(6)}px;
    }}

    QScrollBar::handle:horizontal {{
        background: {roles['scrollbar_handle']};
        min-width: {s(24)}px;
        border-radius: {s(6)}px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background: {roles['accent']};
    }}

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    QMenuBar {{
        background-color: {roles['background']};
        color: {roles['text']};
    }}

    QMenuBar::item:selected {{
        background-color: {roles['button_hover']};
        color: {roles['text']};
    }}

    QMenu {{
        background-color: {roles['surface']};
        color: {roles['text']};
        border: {s(1)}px solid {roles['border']};
    }}

    QMenu::item:selected {{
        background-color: {roles['selected_soft']};
        color: {roles['text']};
    }}

    QProgressBar {{
        background-color: {roles['surface_alt']};
        color: {roles['text']};
        border: {s(1)}px solid {roles['border']};
        border-radius: {s(8)}px;
        text-align: center;
        font-weight: 600;
    }}

    QProgressBar::chunk {{
        background-color: {roles['accent']};
        border-radius: {s(7)}px;
    }}

    QToolTip {{
        background-color: {roles['tooltip_bg']};
        color: {roles['text']};
        border: {s(1)}px solid {roles['border']};
        padding: {s(6)}px;
    }}

    {linux_button_fix}
    """


def apply_theme(app: QApplication, mode: str, ui_scale_percent=100):
    init_theme_system(app)
    ensure_theme_assets()
    themes_dir(create=True)

    mode = normalize_theme_mode(mode)
    resolved_mode = resolve_theme_mode(mode)
    ui_scale_percent = normalize_ui_scale_percent(ui_scale_percent)

    if app.style().objectName().lower() != "fusion":
        app.setStyle(QStyleFactory.create("Fusion"))
    apply_font_scale(app, ui_scale_percent)

    if resolved_mode == "custom":
        theme = get_custom_theme(mode)
        if theme:
            app.setPalette(custom_palette(theme))
            app.setStyleSheet(custom_stylesheet(theme, ui_scale_percent))
            return

        resolved_mode = "dark"

    if resolved_mode == "light":
        app.setPalette(make_light_palette())
        app.setStyleSheet(light_stylesheet(ui_scale_percent))
    else:
        app.setPalette(make_dark_palette())
        app.setStyleSheet(dark_stylesheet(ui_scale_percent))

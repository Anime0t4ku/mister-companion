from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)


_CONTROL_HEIGHT_GUARD_PROPERTY = "_companion_control_height_guard_base"
_CONTROL_HEIGHT_GUARD_APPLIED_PROPERTY = "_companion_control_height_guard_applied"
_CONTROL_HEIGHT_GUARD = None


def _is_guarded_control(widget: QWidget) -> bool:
    return isinstance(
        widget,
        (QLineEdit, QComboBox, QAbstractSpinBox, QPushButton, QToolButton),
    )


def protect_control_minimum_height(widget: QWidget):
    """Prevent a standard single-line control from being vertically squashed."""
    if not _is_guarded_control(widget):
        return

    # Explicit fixed-size controls (mostly icon buttons) manage their own sizing.
    if widget.minimumHeight() == widget.maximumHeight():
        return

    base_height = widget.property(_CONTROL_HEIGHT_GUARD_PROPERTY)
    if base_height is None:
        base_height = widget.minimumHeight()
        widget.setProperty(_CONTROL_HEIGHT_GUARD_PROPERTY, base_height)
    else:
        applied_height = widget.property(_CONTROL_HEIGHT_GUARD_APPLIED_PROPERTY)
        if applied_height is not None and widget.minimumHeight() != int(applied_height):
            base_height = widget.minimumHeight()
            widget.setProperty(_CONTROL_HEIGHT_GUARD_PROPERTY, base_height)

    # Remove the previously calculated constraint before asking the current
    # style for its hints. This lets controls shrink again when UI scale drops.
    widget.setMinimumHeight(int(base_height))
    widget.ensurePolished()
    target_height = max(
        int(base_height),
        widget.minimumSizeHint().height(),
        widget.sizeHint().height(),
    )
    if target_height > 0 and widget.minimumHeight() != target_height:
        widget.setMinimumHeight(target_height)
    widget.setProperty(_CONTROL_HEIGHT_GUARD_APPLIED_PROPERTY, target_height)


def refresh_control_minimum_heights(root: QWidget | None = None):
    """Refresh protected heights after a theme, font, or UI-scale change."""
    if root is not None:
        widgets = [root, *root.findChildren(QWidget)]
    else:
        app = QApplication.instance()
        widgets = app.allWidgets() if app is not None else []

    for widget in widgets:
        protect_control_minimum_height(widget)


class _ControlHeightGuard(QObject):
    def eventFilter(self, watched, event):
        if isinstance(watched, QWidget) and event.type() in {
            QEvent.Type.Show,
            QEvent.Type.FontChange,
            QEvent.Type.StyleChange,
        }:
            protect_control_minimum_height(watched)
        return False


def install_control_height_guard(app: QApplication):
    """Apply responsive minimum heights to current and future controls."""
    global _CONTROL_HEIGHT_GUARD
    if _CONTROL_HEIGHT_GUARD is None:
        _CONTROL_HEIGHT_GUARD = _ControlHeightGuard(app)
        app.installEventFilter(_CONTROL_HEIGHT_GUARD)
    refresh_control_minimum_heights()


def text_button_content_width(button, min_width: int = 0, padding: int = 28) -> int:
    text = button.text() or ""
    text_width = button.fontMetrics().horizontalAdvance(text) + padding
    hint_width = button.sizeHint().width()
    minimum_hint_width = button.minimumSizeHint().width()
    return max(min_width, text_width, hint_width, minimum_hint_width)


def set_text_button_min_width(button, width: int, padding: int = 28, height: int | None = None):
    button.setMinimumWidth(text_button_content_width(button, width, padding))

    if height is not None:
        button.setMinimumHeight(height)

    button.setSizePolicy(
        QSizePolicy.Policy.Minimum,
        QSizePolicy.Policy.Fixed,
    )


def fit_text_button(button, min_width: int = 0, padding: int = 28, height: int | None = None):
    set_text_button_min_width(button, min_width, padding, height)

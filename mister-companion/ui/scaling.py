from PyQt6.QtWidgets import QSizePolicy


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

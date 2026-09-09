from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
)


class CustomMessageDialog(QDialog):
    RESULT_OK = 1
    RESULT_CANCEL = 0
    RESULT_YES = 2
    RESULT_NO = 3

    def __init__(
        self,
        parent=None,
        title="Message",
        message="",
        icon_type="info",
        buttons=("OK",),
        default_button="OK",
    ):
        super().__init__(parent)

        self.result_value = self.RESULT_CANCEL
        self.button_map = {}

        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(390)
        self.setMaximumWidth(680)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 14)
        outer.setSpacing(12)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(4, 2, 4, 2)
        content_layout.setSpacing(14)

        icon_label = QLabel()
        icon_label.setFixedSize(42, 42)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        icon = _dialog_icon(icon_type)
        if not icon.isNull():
            icon_label.setPixmap(icon.pixmap(36, 36))

        content_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

        message_label = QLabel(str(message or ""))
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        message_label.setMinimumWidth(280)
        content_layout.addWidget(message_label, 1)

        outer.addLayout(content_layout)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(line)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(8, 0, 8, 0)
        button_row.setSpacing(8)
        button_row.addStretch()

        for button_text in buttons:
            button = QPushButton(button_text)
            button.setMinimumWidth(82)
            button.setMinimumHeight(30)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, text=button_text: self._finish(text))
            button_row.addWidget(button)
            self.button_map[button_text] = button

            if button_text == default_button:
                button.setDefault(True)
                button.setFocus()

        outer.addLayout(button_row)

    def _finish(self, button_text):
        normalized = str(button_text or "").strip().lower()

        if normalized == "ok":
            self.result_value = self.RESULT_OK
            self.accept()
            return
        if normalized == "cancel":
            self.result_value = self.RESULT_CANCEL
            self.reject()
            return
        if normalized == "yes":
            self.result_value = self.RESULT_YES
            self.accept()
            return
        if normalized == "no":
            self.result_value = self.RESULT_NO
            self.reject()
            return

        self.result_value = self.RESULT_OK
        self.accept()

    @staticmethod
    def information(parent, title, message):
        dialog = CustomMessageDialog(parent, title, message, "info", ("OK",), "OK")
        dialog.exec()
        return dialog.result_value

    @staticmethod
    def warning(parent, title, message):
        dialog = CustomMessageDialog(parent, title, message, "warning", ("OK",), "OK")
        dialog.exec()
        return dialog.result_value

    @staticmethod
    def critical(parent, title, message):
        dialog = CustomMessageDialog(parent, title, message, "critical", ("OK",), "OK")
        dialog.exec()
        return dialog.result_value

    @staticmethod
    def question(parent, title, message, default_button="Yes"):
        dialog = CustomMessageDialog(parent, title, message, "question", ("Yes", "No"), default_button)
        dialog.exec()
        return dialog.result_value

    @staticmethod
    def question_cancel(parent, title, message, default_button="Yes"):
        dialog = CustomMessageDialog(
            parent, title, message, "question", ("Yes", "No", "Cancel"), default_button
        )
        dialog.exec()
        return dialog.result_value


def _dialog_icon(icon_type):
    app = QApplication.instance()
    if app is None:
        return QIcon()

    style = app.style()
    icon_type = (icon_type or "info").lower()

    if icon_type == "critical":
        return style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical)
    if icon_type == "warning":
        return style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
    if icon_type == "question":
        return style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion)
    return style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)


def install_custom_message_boxes():
    def information(parent, title, text, *args, **kwargs):
        CustomMessageDialog.information(parent, title, text)
        return QMessageBox.StandardButton.Ok

    def warning(parent, title, text, *args, **kwargs):
        CustomMessageDialog.warning(parent, title, text)
        return QMessageBox.StandardButton.Ok

    def critical(parent, title, text, *args, **kwargs):
        CustomMessageDialog.critical(parent, title, text)
        return QMessageBox.StandardButton.Ok

    def question(parent, title, text, buttons=None, defaultButton=None, *args, **kwargs):
        has_cancel = False
        if buttons is not None:
            try:
                has_cancel = bool(buttons & QMessageBox.StandardButton.Cancel)
            except Exception:
                pass

        default_text = "Yes"
        if defaultButton == QMessageBox.StandardButton.No:
            default_text = "No"
        elif defaultButton == QMessageBox.StandardButton.Cancel:
            default_text = "Cancel"
        elif defaultButton == QMessageBox.StandardButton.Ok:
            default_text = "OK"

        if has_cancel:
            result = CustomMessageDialog.question_cancel(parent, title, text, default_text)
        else:
            result = CustomMessageDialog.question(parent, title, text, default_text)

        if result == CustomMessageDialog.RESULT_YES:
            return QMessageBox.StandardButton.Yes
        if result == CustomMessageDialog.RESULT_NO:
            return QMessageBox.StandardButton.No
        if result == CustomMessageDialog.RESULT_CANCEL:
            return QMessageBox.StandardButton.Cancel
        return QMessageBox.StandardButton.Ok

    QMessageBox.information = staticmethod(information)
    QMessageBox.warning = staticmethod(warning)
    QMessageBox.critical = staticmethod(critical)
    QMessageBox.question = staticmethod(question)

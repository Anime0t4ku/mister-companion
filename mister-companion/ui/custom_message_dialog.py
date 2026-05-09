from __future__ import annotations

import platform
from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QIcon, QMouseEvent
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
    QWidget,
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
        self.original_parent = parent

        if _is_linux():
            super().__init__(None)
        else:
            super().__init__(parent)

        self.result_value = self.RESULT_CANCEL
        self.button_map = {}

        self.setWindowTitle(title)
        self.setModal(True)

        if _is_linux():
            self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self._mister_custom_dialog_applied = True
        self._mister_dialog_maximized = False
        self._mister_dialog_normal_geometry = None
        self._mister_dialog_original_parent = parent

        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setObjectName("CustomMessageDialog")

        self.setMinimumWidth(390)
        self.setMaximumWidth(680)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        self.title_bar = _MessageTitleBar(self, title)
        outer.addWidget(self.title_bar)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(12, 8, 12, 4)
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
        button_row.setContentsMargins(8, 0, 8, 4)
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

        self.setStyleSheet(
            """
            QDialog#CustomMessageDialog {
                border: 1px solid palette(mid);
                border-radius: 10px;
                background: palette(window);
            }

            QLabel {
                background: transparent;
            }

            QPushButton {
                padding: 4px 14px;
            }
            """
        )

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
        dialog = CustomMessageDialog(
            parent=parent,
            title=title,
            message=message,
            icon_type="info",
            buttons=("OK",),
            default_button="OK",
        )
        dialog.exec()
        return dialog.result_value

    @staticmethod
    def warning(parent, title, message):
        dialog = CustomMessageDialog(
            parent=parent,
            title=title,
            message=message,
            icon_type="warning",
            buttons=("OK",),
            default_button="OK",
        )
        dialog.exec()
        return dialog.result_value

    @staticmethod
    def critical(parent, title, message):
        dialog = CustomMessageDialog(
            parent=parent,
            title=title,
            message=message,
            icon_type="critical",
            buttons=("OK",),
            default_button="OK",
        )
        dialog.exec()
        return dialog.result_value

    @staticmethod
    def question(parent, title, message, default_button="Yes"):
        dialog = CustomMessageDialog(
            parent=parent,
            title=title,
            message=message,
            icon_type="question",
            buttons=("Yes", "No"),
            default_button=default_button,
        )
        dialog.exec()
        return dialog.result_value

    @staticmethod
    def question_cancel(parent, title, message, default_button="Yes"):
        dialog = CustomMessageDialog(
            parent=parent,
            title=title,
            message=message,
            icon_type="question",
            buttons=("Yes", "No", "Cancel"),
            default_button=default_button,
        )
        dialog.exec()
        return dialog.result_value


class _MessageTitleBar(QWidget):
    def __init__(self, dialog, title):
        super().__init__(dialog)

        self.dialog = dialog
        self.dragging = False
        self.drag_position = QPoint()
        self.system_move_started = False

        self.setObjectName("CustomMessageTitleBar")
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 4, 3)
        layout.setSpacing(6)

        icon_label = QLabel()
        icon = _app_icon()
        if not icon.isNull():
            icon_label.setPixmap(icon.pixmap(16, 16))
        icon_label.setFixedSize(18, 18)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.installEventFilter(self)
        layout.addWidget(icon_label)

        title_label = QLabel(title or "Message")
        title_label.setObjectName("CustomMessageTitleLabel")
        title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title_label.setStyleSheet("font-weight: 600;")
        title_label.installEventFilter(self)
        layout.addWidget(title_label, 1)

        maximize_button = _title_button("□")
        close_button = _title_button("×")

        maximize_button.clicked.connect(self._toggle_maximized)
        close_button.clicked.connect(dialog.reject)

        layout.addWidget(maximize_button)
        layout.addWidget(close_button)

        self.setStyleSheet(
            """
            QWidget#CustomMessageTitleBar {
                background: palette(base);
                border: 1px solid palette(mid);
                border-radius: 8px;
            }

            QLabel#CustomMessageTitleLabel {
                padding-left: 2px;
            }

            QPushButton {
                border: none;
                border-radius: 4px;
                padding: 0px;
                margin: 0px;
                font-size: 10px;
                font-weight: 600;
                min-width: 24px;
                max-width: 24px;
                min-height: 20px;
                max-height: 20px;
            }

            QPushButton:hover {
                background: palette(midlight);
            }
            """
        )

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            self.mousePressEvent(event)
            return event.isAccepted()

        if event.type() == QEvent.Type.MouseMove:
            self.mouseMoveEvent(event)
            return event.isAccepted()

        if event.type() == QEvent.Type.MouseButtonRelease:
            self.mouseReleaseEvent(event)
            return event.isAccepted()

        if event.type() == QEvent.Type.MouseButtonDblClick:
            self.mouseDoubleClickEvent(event)
            return event.isAccepted()

        return super().eventFilter(watched, event)

    def _toggle_maximized(self) -> None:
        if getattr(self.dialog, "_mister_dialog_maximized", False):
            normal_geometry = getattr(
                self.dialog,
                "_mister_dialog_normal_geometry",
                None,
            )

            if normal_geometry is not None:
                self.dialog.setGeometry(normal_geometry)
            else:
                self.dialog.showNormal()

            self.dialog._mister_dialog_maximized = False
        else:
            self.dialog._mister_dialog_normal_geometry = self.dialog.geometry()

            screen = self.dialog.screen()
            if screen is None:
                app = QApplication.instance()
                screen = app.primaryScreen() if app is not None else None

            if screen is not None:
                self.dialog.setGeometry(screen.availableGeometry())
            else:
                self.dialog.showMaximized()

            self.dialog._mister_dialog_maximized = True

        self.dialog.raise_()
        self.dialog.activateWindow()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.system_move_started = False
            self.drag_position = (
                event.globalPosition().toPoint()
                - self.dialog.frameGeometry().topLeft()
            )

            if not getattr(self.dialog, "_mister_dialog_maximized", False):
                try:
                    window_handle = self.dialog.windowHandle()
                    if window_handle is not None and window_handle.startSystemMove():
                        self.system_move_started = True
                        event.accept()
                        return
                except Exception:
                    pass

            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.dragging and event.buttons() & Qt.MouseButton.LeftButton:
            if self.system_move_started:
                event.accept()
                return

            if getattr(self.dialog, "_mister_dialog_maximized", False):
                self._toggle_maximized()
                self.drag_position = QPoint(self.dialog.width() // 2, 16)

            if not getattr(self.dialog, "_mister_dialog_maximized", False):
                new_pos = event.globalPosition().toPoint() - self.drag_position
                self.dialog.move(new_pos)

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.dragging = False
        self.system_move_started = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximized()
            event.accept()
            return

        super().mouseDoubleClickEvent(event)


def _is_linux() -> bool:
    return platform.system() == "Linux"


def _title_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFixedSize(24, 20)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return button


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


def _app_icon():
    candidates = [
        Path(__file__).resolve().parents[1] / "assets" / "icon.png",
        Path.cwd() / "assets" / "icon.png",
        Path.cwd() / "icon.png",
    ]

    for path in candidates:
        if path.exists():
            return QIcon(str(path))

    app = QApplication.instance()
    if app is not None:
        icon = app.windowIcon()
        if not icon.isNull():
            return icon

    return QIcon()


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
                has_cancel = False

        default_text = "Yes"

        if defaultButton == QMessageBox.StandardButton.No:
            default_text = "No"
        elif defaultButton == QMessageBox.StandardButton.Cancel:
            default_text = "Cancel"
        elif defaultButton == QMessageBox.StandardButton.Ok:
            default_text = "OK"

        if has_cancel:
            result = CustomMessageDialog.question_cancel(
                parent,
                title,
                text,
                default_button=default_text,
            )
        else:
            result = CustomMessageDialog.question(
                parent,
                title,
                text,
                default_button=default_text,
            )

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
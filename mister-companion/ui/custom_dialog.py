from __future__ import annotations

import platform
from pathlib import Path

from PyQt6.QtCore import QEvent, QPoint, Qt, QObject
from PyQt6.QtGui import QIcon, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)


_INSTALLED = False


def install_custom_dialogs(app: QApplication) -> None:
    global _INSTALLED

    if _INSTALLED:
        return

    _INSTALLED = True
    app._mister_dialog_installer = _DialogInstaller(app)
    app.installEventFilter(app._mister_dialog_installer)


class _DialogInstaller(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self.app = app

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in (QEvent.Type.Show, QEvent.Type.Polish):
            if isinstance(watched, QDialog):
                _apply_custom_dialog(watched)

        return False


def _is_linux() -> bool:
    return platform.system() == "Linux"


def _apply_custom_dialog(dialog: QDialog) -> None:
    if getattr(dialog, "_mister_custom_dialog_applied", False):
        return

    if isinstance(dialog, (QFileDialog, QMessageBox)):
        return

    if dialog.__class__.__name__ == "CustomMessageDialog":
        return

    original_parent = dialog.parentWidget()

    dialog._mister_custom_dialog_applied = True
    dialog._mister_dialog_maximized = False
    dialog._mister_dialog_normal_geometry = None
    dialog._mister_dialog_original_parent = original_parent

    if _is_linux():
        dialog.setParent(None)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)

    dialog.setWindowFlags(
        Qt.WindowType.Dialog
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowMaximizeButtonHint
        | Qt.WindowType.WindowCloseButtonHint
    )
    dialog.setObjectName("CustomFramelessDialog")

    layout = dialog.layout()
    if layout is None:
        layout = QVBoxLayout()
        dialog.setLayout(layout)

    try:
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
    except Exception:
        pass

    title_bar = _DialogTitleBar(dialog)

    inserted = False

    if isinstance(layout, QVBoxLayout):
        layout.insertWidget(0, title_bar)
        inserted = True
    elif isinstance(layout, QFormLayout):
        layout.insertRow(0, title_bar)
        inserted = True
    elif hasattr(layout, "insertWidget"):
        try:
            layout.insertWidget(0, title_bar)
            inserted = True
        except Exception:
            inserted = False

    if not inserted:
        try:
            layout.addWidget(title_bar)
        except Exception:
            pass

    dialog.setStyleSheet(
        dialog.styleSheet()
        + """
        QDialog#CustomFramelessDialog {
            border: 1px solid palette(mid);
            border-radius: 10px;
            background: palette(window);
        }
        """
    )


class _DialogTitleBar(QWidget):
    def __init__(self, dialog: QDialog) -> None:
        super().__init__(dialog)

        self.dialog = dialog
        self.dragging = False
        self.drag_position = QPoint()
        self.system_move_started = False

        self.setObjectName("CustomDialogTitleBar")
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

        self.title_label = QLabel(dialog.windowTitle() or "Dialog")
        self.title_label.setObjectName("CustomDialogTitleLabel")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.title_label.setStyleSheet("font-weight: 600;")
        self.title_label.installEventFilter(self)
        layout.addWidget(self.title_label, 1)

        maximize_button = _title_button("□")
        close_button = _title_button("×")

        maximize_button.clicked.connect(self._toggle_maximized)
        close_button.clicked.connect(dialog.reject)

        layout.addWidget(maximize_button)
        layout.addWidget(close_button)

        self.setStyleSheet(
            """
            QWidget#CustomDialogTitleBar {
                background: palette(base);
                border: 1px solid palette(mid);
                border-radius: 8px;
            }

            QLabel#CustomDialogTitleLabel {
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


def _title_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFixedSize(24, 20)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return button


def _app_icon() -> QIcon:
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

        return app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

    return QIcon()
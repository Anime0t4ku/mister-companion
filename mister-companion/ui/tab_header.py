from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


TAB_HEADER_ICON_SIZE = 19


def create_tab_header(main_window, text: str, icon_name: str) -> QWidget:
    header = QWidget()
    header.setObjectName("TabPageHeader")
    header.setStyleSheet("background: transparent;")

    layout = QHBoxLayout(header)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(7)

    icon_label = QLabel()
    icon_label.setObjectName("TabPageHeaderIcon")
    icon_label.setProperty("tabHeaderIconName", icon_name)
    icon_label.setProperty("tabHeaderIconSize", TAB_HEADER_ICON_SIZE)
    icon_label.setFixedSize(TAB_HEADER_ICON_SIZE, TAB_HEADER_ICON_SIZE)
    icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon_label.setStyleSheet("background: transparent;")

    title_label = QLabel(text)
    title_label.setObjectName("TabPageHeaderTitle")
    title_label.setStyleSheet("font-weight: 700; font-size: 19px; background: transparent;")
    title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    color = title_label.palette().color(QPalette.ColorRole.WindowText).name()
    icon_label.setPixmap(
        main_window.svg_icon(icon_name, color).pixmap(
            QSize(TAB_HEADER_ICON_SIZE, TAB_HEADER_ICON_SIZE)
        )
    )

    layout.addWidget(icon_label)
    layout.addWidget(title_label)
    layout.addStretch(1)
    return header

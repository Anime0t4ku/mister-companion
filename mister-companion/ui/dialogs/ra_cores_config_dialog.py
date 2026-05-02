import traceback

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from core.ra_cores import (
    read_ra_config as backend_read_ra_config,
    write_ra_config as backend_write_ra_config,
)


class RetroAchievementsConfigDialog(QDialog):
    def __init__(self, parent, connection):
        super().__init__(parent)

        self.connection = connection
        self.values = {}

        self.setWindowTitle("RetroAchievements Config")
        self.setMinimumWidth(480)

        self.build_ui()
        self.load_config()

    def build_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)
        self.setLayout(main_layout)

        intro_label = QLabel(
            "Edit the RetroAchievements settings stored in "
            "/media/fat/retroachievements.cfg."
        )
        intro_label.setWordWrap(True)
        main_layout.addWidget(intro_label)

        account_layout = QFormLayout()
        account_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        account_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        account_layout.setHorizontalSpacing(12)
        account_layout.setVerticalSpacing(10)
        main_layout.addLayout(account_layout)

        self.username_edit = QLineEdit()

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.show_password_checkbox = QCheckBox("Show password")
        self.show_password_checkbox.toggled.connect(self.toggle_password_visibility)

        account_layout.addRow("Username:", self.username_edit)
        account_layout.addRow("Password:", self.password_edit)
        account_layout.addRow("", self.show_password_checkbox)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(divider)

        options_layout = QFormLayout()
        options_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        options_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        options_layout.setHorizontalSpacing(12)
        options_layout.setVerticalSpacing(10)
        main_layout.addLayout(options_layout)

        self.challenge_show_checkbox = QCheckBox()
        self.challenge_hide_checkbox = QCheckBox()
        self.progress_popups_checkbox = QCheckBox()
        self.progress_name_checkbox = QCheckBox()
        self.leaderboards_checkbox = QCheckBox()
        self.debug_checkbox = QCheckBox()
        self.hardcore_checkbox = QCheckBox()

        options_layout.addRow(
            "Show challenge popup:",
            self.challenge_show_checkbox,
        )
        options_layout.addRow(
            "Show missed challenge popup:",
            self.challenge_hide_checkbox,
        )
        options_layout.addRow(
            "Show progress popups:",
            self.progress_popups_checkbox,
        )
        options_layout.addRow(
            "Include achievement name:",
            self.progress_name_checkbox,
        )
        options_layout.addRow(
            "Enable leaderboards:",
            self.leaderboards_checkbox,
        )
        options_layout.addRow(
            "Debug logging:",
            self.debug_checkbox,
        )
        options_layout.addRow(
            "Hardcore mode:",
            self.hardcore_checkbox,
        )

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.save_config)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

    def load_config(self):
        try:
            self.values = backend_read_ra_config(self.connection)
        except Exception as e:
            detail = traceback.format_exc()
            QMessageBox.warning(
                self,
                "RetroAchievements Config",
                f"Failed to read retroachievements.cfg:\n\n{e}\n\n{detail}",
            )
            self.reject()
            return

        self.username_edit.setText(self.values.get("username", ""))
        self.password_edit.setText(self.values.get("password", ""))

        self.challenge_show_checkbox.setChecked(
            self._value_to_bool("show_challenge_show_popup")
        )
        self.challenge_hide_checkbox.setChecked(
            self._value_to_bool("show_challenge_hide_popup")
        )
        self.progress_popups_checkbox.setChecked(
            self._value_to_bool("show_progress_popups")
        )
        self.progress_name_checkbox.setChecked(
            self._value_to_bool("show_progress_name")
        )
        self.leaderboards_checkbox.setChecked(
            self._value_to_bool("leaderboards-enabled")
        )
        self.debug_checkbox.setChecked(
            self._value_to_bool("debug")
        )
        self.hardcore_checkbox.setChecked(
            self._value_to_bool("hardcore")
        )

    def save_config(self):
        try:
            backend_write_ra_config(self.connection, self.get_values())
        except Exception as e:
            detail = traceback.format_exc()
            QMessageBox.warning(
                self,
                "RetroAchievements Config",
                f"Failed to save retroachievements.cfg:\n\n{e}\n\n{detail}",
            )
            return

        QMessageBox.information(
            self,
            "RetroAchievements Config",
            "RetroAchievements config saved.",
        )
        self.accept()

    def _value_to_bool(self, key):
        return str(self.values.get(key, "0")).strip() == "1"

    def _bool_to_value(self, checkbox):
        return "1" if checkbox.isChecked() else "0"

    def toggle_password_visibility(self, checked):
        if checked:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def get_values(self):
        return {
            "username": self.username_edit.text().strip(),
            "password": self.password_edit.text().strip(),
            "show_challenge_show_popup": self._bool_to_value(
                self.challenge_show_checkbox
            ),
            "show_challenge_hide_popup": self._bool_to_value(
                self.challenge_hide_checkbox
            ),
            "show_progress_popups": self._bool_to_value(
                self.progress_popups_checkbox
            ),
            "show_progress_name": self._bool_to_value(
                self.progress_name_checkbox
            ),
            "leaderboards-enabled": self._bool_to_value(
                self.leaderboards_checkbox
            ),
            "debug": self._bool_to_value(
                self.debug_checkbox
            ),
            "hardcore": self._bool_to_value(
                self.hardcore_checkbox
            ),
        }
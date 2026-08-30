from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from core.extras_physical_disc import (
    get_physical_disc_overrides,
    get_physical_disc_overrides_local,
    set_physical_disc_overrides,
    set_physical_disc_overrides_local,
)


AUDIO_CD_OPTIONS = (
    ("PlayStation", "A0CD-PSX"),
    ("Saturn", "A0CD-Saturn"),
    ("Mega CD", "A0CD-MegaCD"),
    ("TurboGrafx-16 CD", "A0CD-TurboGrafx16-CD"),
    ("Neo Geo CD", "A0CD-NeoGeoCD"),
    ("CD-i", "A0CD-CDi"),
    ("3DO", "A0CD-3DO"),
    ("MiSTer Hi-Fi", "MISTERHIFI"),
)

DVD_OPTIONS = (
    ("DVD Player (Hybrid)", "HYBRID"),
    ("MiSTer DVD (FPGA)", "FPGA"),
)


class PhysicalDiscOverridesDialog(QDialog):
    def __init__(self, parent, connection=None, sd_root: str | Path | None = None):
        super().__init__(parent)
        self.connection = connection
        self.sd_root = str(sd_root or "").strip()
        self.changed = False

        self.setWindowTitle("Physical Disc Overrides")
        self.setMinimumWidth(520)
        self._build_ui()
        self._load_state()

    def is_offline_mode(self):
        return bool(self.sd_root)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        intro = QLabel(
            "Choose which core Auto Disc Detection opens for Audio CDs and DVDs. "
            "Overrides are optional and only apply while Auto Disc Detection is enabled."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        audio_group = QGroupBox("Audio CD")
        audio_layout = QVBoxLayout(audio_group)
        audio_info = QLabel(
            "With the override off, Audio CDs use the default Physical Disc behavior and open with the PlayStation core."
        )
        audio_info.setWordWrap(True)
        audio_layout.addWidget(audio_info)

        self.audio_enabled = QCheckBox("Enable Audio CD override")
        self.audio_enabled.toggled.connect(self._update_enabled_state)
        audio_layout.addWidget(self.audio_enabled)

        audio_form = QFormLayout()
        audio_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.audio_combo = QComboBox()
        for label, value in AUDIO_CD_OPTIONS:
            self.audio_combo.addItem(label, value)
        audio_form.addRow("Core:", self.audio_combo)
        audio_layout.addLayout(audio_form)
        layout.addWidget(audio_group)

        dvd_group = QGroupBox("DVD")
        dvd_layout = QVBoxLayout(dvd_group)
        dvd_info = QLabel(
            "With the override off, Auto Disc Detection checks which supported DVD core is installed and launches the first one it finds."
        )
        dvd_info.setWordWrap(True)
        dvd_layout.addWidget(dvd_info)

        self.dvd_enabled = QCheckBox("Enable DVD override")
        self.dvd_enabled.toggled.connect(self._update_enabled_state)
        dvd_layout.addWidget(self.dvd_enabled)

        dvd_form = QFormLayout()
        dvd_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.dvd_combo = QComboBox()
        for label, value in DVD_OPTIONS:
            self.dvd_combo.addItem(label, value)
        dvd_form.addRow("Core:", self.dvd_combo)
        dvd_layout.addLayout(dvd_form)
        layout.addWidget(dvd_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_enabled_state()

    def _read_state(self):
        if self.is_offline_mode():
            return get_physical_disc_overrides_local(self.sd_root)
        if self.connection is None or not self.connection.is_connected():
            raise RuntimeError("Not connected to MiSTer.")
        return get_physical_disc_overrides(self.connection)

    def _load_state(self):
        try:
            state = self._read_state()
            if not state.get("available"):
                raise RuntimeError("Enable Auto Disc Detection before managing overrides.")

            self._set_combo_value(self.audio_combo, state.get("audio_cd", ""), AUDIO_CD_OPTIONS)
            self._set_combo_value(self.dvd_combo, state.get("dvd", ""), DVD_OPTIONS)
            self.audio_enabled.setChecked(bool(state.get("audio_cd")))
            self.dvd_enabled.setChecked(bool(state.get("dvd")))
            self._update_enabled_state()
        except Exception as exc:
            QMessageBox.warning(self, "Physical Disc Overrides", str(exc))
            self.reject()

    @staticmethod
    def _set_combo_value(combo, value, options):
        value = str(value or "").strip()
        if not value:
            combo.setCurrentIndex(0)
            return
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
            return
        combo.addItem(f"Current value ({value})", value)
        combo.setCurrentIndex(combo.count() - 1)

    def _update_enabled_state(self):
        self.audio_combo.setEnabled(self.audio_enabled.isChecked())
        self.dvd_combo.setEnabled(self.dvd_enabled.isChecked())

    def _save(self):
        audio_value = self.audio_combo.currentData() if self.audio_enabled.isChecked() else ""
        dvd_value = self.dvd_combo.currentData() if self.dvd_enabled.isChecked() else ""
        try:
            if self.is_offline_mode():
                result = set_physical_disc_overrides_local(
                    self.sd_root,
                    audio_cd=audio_value,
                    dvd=dvd_value,
                )
            else:
                if self.connection is None or not self.connection.is_connected():
                    raise RuntimeError("Not connected to MiSTer.")
                result = set_physical_disc_overrides(
                    self.connection,
                    audio_cd=audio_value,
                    dvd=dvd_value,
                )
        except Exception as exc:
            QMessageBox.warning(self, "Physical Disc Overrides", f"Could not save overrides.\n\n{exc}")
            return

        self.changed = bool(result.get("changed"))
        self.accept()

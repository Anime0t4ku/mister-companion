from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.update_all_config import load_update_all_config, save_update_all_config


class UpdateAllConfigDialog(QDialog):
    def __init__(self, connection, parent=None):
        super().__init__(parent)
        self.connection = connection

        self.setWindowTitle("Update_All Configuration")
        self.resize(500, 850)
        self.setMinimumSize(460, 500)

        self.build_ui()
        self.load_current_config()

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        title = QLabel("Update_All Configuration")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(10)
        scroll.setWidget(content)

        # ===== Main Cores =====
        main_group = self._group("Main Cores")
        self.main_cores_check = QCheckBox("Enable Main Cores")
        self.main_source_combo = QComboBox()
        self.main_source_combo.addItems([
            "MiSTer-devel (Recommended)",
            "DB9 / SNAC8 forks with ENCC",
            "AitorGomez fork",
        ])
        self._add(main_group, self.main_cores_check)

        row = QHBoxLayout()
        row.addSpacing(20)
        row.addWidget(QLabel("Source:"))
        row.addWidget(self.main_source_combo)
        row.addStretch()
        main_group.layout().addLayout(row)

        # ===== JTCores =====
        jt_group = self._group("JTCores")
        self.jtcores_check = QCheckBox("Enable JTCores")
        self.jt_beta_check = QCheckBox("Enable Beta Cores")
        self._add(jt_group, self.jtcores_check)
        self._add(jt_group, self.jt_beta_check, indent=True)
        self.jtcores_check.toggled.connect(self.update_jt_beta_state)

        # ===== Other Cores =====
        other_group = self._group("Other Cores")
        self.coinop_check = QCheckBox("Coin-Op Collection")
        self.arcade_offset_check = QCheckBox("Arcade Offset Folder")
        self.llapi_check = QCheckBox("LLAPI Forks Folder")
        self.unofficial_check = QCheckBox("Unofficial Distribution")
        self.yc_check = QCheckBox("Y/C Builds")
        self.agg23_check = QCheckBox("agg23’s MiSTer Cores")
        self.altcores_check = QCheckBox("Alt Cores")
        self.dualram_check = QCheckBox("Dual RAM Console Cores")

        for widget in [
            self.coinop_check,
            self.arcade_offset_check,
            self.llapi_check,
            self.unofficial_check,
            self.yc_check,
            self.agg23_check,
            self.altcores_check,
            self.dualram_check,
        ]:
            self._add(other_group, widget)

        # ===== Tools & Scripts =====
        tools_group = self._group("Tools & Scripts")
        self.arcade_org_check = QCheckBox("Arcade Organizer")
        self.mrext_check = QCheckBox("MiSTer Extensions (Wizzo Scripts)")
        self.sam_check = QCheckBox("MiSTer Super Attract Mode")
        self.tty2oled_check = QCheckBox("tty2oled Add-on Script")
        self.i2c2oled_check = QCheckBox("i2c2oled Add-on Script")
        self.retrospy_check = QCheckBox("RetroSpy Utility")

        for widget in [
            self.arcade_org_check,
            self.mrext_check,
            self.sam_check,
            self.tty2oled_check,
            self.i2c2oled_check,
            self.retrospy_check,
        ]:
            self._add(tools_group, widget)

        # ===== Extra Content =====
        extra_group = self._group("Extra Content")
        self.bios_check = QCheckBox("BIOS Database")
        self.arcade_roms_check = QCheckBox("Arcade ROMs Database")
        self.bootroms_check = QCheckBox("Uberyoji Boot ROMs")
        self.gba_borders_check = QCheckBox("Dinierto GBA Borders")
        self.insert_coin_check = QCheckBox("Insert-Coin")
        self.anime0t4ku_wallpapers_check = QCheckBox("Anime0t4ku Wallpapers")
        self.pcn_challenge_wallpapers_check = QCheckBox("PCN Challenge Wallpapers")
        self.anime0t4ku_mister_scripts_check = QCheckBox("Anime0t4ku MiSTer Scripts")
        self.ranny_wallpapers_check = QCheckBox("Ranny Snice Wallpapers")
        self.ranny_wallpapers_source_combo = QComboBox()
        self.ranny_wallpapers_source_combo.addItems([
            "16:9 Wallpapers",
            "4:3 Wallpapers",
            "All Wallpapers",
        ])

        for widget in [
            self.bios_check,
            self.arcade_roms_check,
            self.bootroms_check,
            self.gba_borders_check,
            self.insert_coin_check,
            self.anime0t4ku_wallpapers_check,
            self.pcn_challenge_wallpapers_check,
            self.anime0t4ku_mister_scripts_check,
            self.ranny_wallpapers_check,
        ]:
            self._add(extra_group, widget)

        wallpaper_row = QHBoxLayout()
        wallpaper_row.addSpacing(20)
        wallpaper_row.addWidget(QLabel("Source:"))
        wallpaper_row.addWidget(self.ranny_wallpapers_source_combo)
        wallpaper_row.addStretch()
        extra_group.layout().addLayout(wallpaper_row)
        self.ranny_wallpapers_check.toggled.connect(self.update_wallpaper_state)

        # ===== Buttons =====
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(line)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.save_button = QPushButton("Save")
        self.close_button = QPushButton("Close")

        button_row.addWidget(self.save_button)
        button_row.addWidget(self.close_button)
        button_row.addStretch()

        outer.addLayout(button_row)

        self.save_button.clicked.connect(self.on_save)
        self.close_button.clicked.connect(self.reject)

    def _group(self, title):
        box = QFrame()
        box.setFrameShape(QFrame.Shape.StyledPanel)
        box.setStyleSheet("QFrame { border: 1px solid palette(mid); border-radius: 6px; }")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        label = QLabel(title)
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)

        self.content_layout.addWidget(box)
        return box

    def _add(self, group, widget, indent=False):
        if indent:
            row = QHBoxLayout()
            row.addSpacing(20)
            row.addWidget(widget)
            row.addStretch()
            group.layout().addLayout(row)
        else:
            group.layout().addWidget(widget)

    def update_jt_beta_state(self):
        self.jt_beta_check.setEnabled(self.jtcores_check.isChecked())

    def update_wallpaper_state(self):
        self.ranny_wallpapers_source_combo.setEnabled(self.ranny_wallpapers_check.isChecked())

    def load_current_config(self):
        try:
            data = load_update_all_config(self.connection)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load config:\n{e}")
            return

        self.main_cores_check.setChecked(data["main_cores"])
        self.main_source_combo.setCurrentText(data["main_source"])
        self.jtcores_check.setChecked(data["jtcores"])
        self.jt_beta_check.setChecked(data["jt_beta"])

        self.coinop_check.setChecked(data["coinop"])
        self.arcade_offset_check.setChecked(data["arcade_offset"])
        self.llapi_check.setChecked(data["llapi"])
        self.unofficial_check.setChecked(data["unofficial"])
        self.yc_check.setChecked(data["yc"])
        self.agg23_check.setChecked(data["agg23"])
        self.altcores_check.setChecked(data["altcores"])
        self.dualram_check.setChecked(data["dualram"])

        self.arcade_org_check.setChecked(data["arcade_org"])
        self.mrext_check.setChecked(data["mrext"])
        self.sam_check.setChecked(data["sam"])
        self.tty2oled_check.setChecked(data["tty2oled"])
        self.i2c2oled_check.setChecked(data["i2c2oled"])
        self.retrospy_check.setChecked(data["retrospy"])

        self.bios_check.setChecked(data["bios"])
        self.arcade_roms_check.setChecked(data["arcade_roms"])
        self.bootroms_check.setChecked(data["bootroms"])
        self.gba_borders_check.setChecked(data["gbaborders"])
        self.insert_coin_check.setChecked(data["insert_coin"])
        self.anime0t4ku_wallpapers_check.setChecked(data["anime0t4ku_wallpapers"])
        self.pcn_challenge_wallpapers_check.setChecked(data["pcn_challenge_wallpapers"])
        self.anime0t4ku_mister_scripts_check.setChecked(data["anime0t4ku_mister_scripts"])
        self.ranny_wallpapers_check.setChecked(data["ranny_wallpapers"])
        self.ranny_wallpapers_source_combo.setCurrentText(data["ranny_wallpapers_source"])

        self.update_jt_beta_state()
        self.update_wallpaper_state()

    def collect_config(self):
        return {
            "main_cores": self.main_cores_check.isChecked(),
            "main_source": self.main_source_combo.currentText(),
            "jtcores": self.jtcores_check.isChecked(),
            "jt_beta": self.jt_beta_check.isChecked(),

            "coinop": self.coinop_check.isChecked(),
            "arcade_offset": self.arcade_offset_check.isChecked(),
            "llapi": self.llapi_check.isChecked(),
            "unofficial": self.unofficial_check.isChecked(),
            "yc": self.yc_check.isChecked(),
            "agg23": self.agg23_check.isChecked(),
            "altcores": self.altcores_check.isChecked(),
            "dualram": self.dualram_check.isChecked(),

            "arcade_org": self.arcade_org_check.isChecked(),
            "mrext": self.mrext_check.isChecked(),
            "sam": self.sam_check.isChecked(),
            "tty2oled": self.tty2oled_check.isChecked(),
            "i2c2oled": self.i2c2oled_check.isChecked(),
            "retrospy": self.retrospy_check.isChecked(),

            "bios": self.bios_check.isChecked(),
            "arcade_roms": self.arcade_roms_check.isChecked(),
            "bootroms": self.bootroms_check.isChecked(),
            "gbaborders": self.gba_borders_check.isChecked(),
            "insert_coin": self.insert_coin_check.isChecked(),
            "anime0t4ku_wallpapers": self.anime0t4ku_wallpapers_check.isChecked(),
            "pcn_challenge_wallpapers": self.pcn_challenge_wallpapers_check.isChecked(),
            "anime0t4ku_mister_scripts": self.anime0t4ku_mister_scripts_check.isChecked(),
            "ranny_wallpapers": self.ranny_wallpapers_check.isChecked(),
            "ranny_wallpapers_source": self.ranny_wallpapers_source_combo.currentText(),
        }

    def on_save(self):
        try:
            save_update_all_config(self.connection, self.collect_config())
            QMessageBox.information(self, "Saved", "update_all configuration saved successfully.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config:\n{e}")
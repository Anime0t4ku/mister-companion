from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QGuiApplication
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

from core.retroaccount import (
    get_retroaccount_status,
    poll_retroaccount_device_link,
    start_retroaccount_device_link,
)
from core.update_all_config import load_update_all_config, save_update_all_config


class UpdateAllConfigDialog(QDialog):
    def __init__(self, connection, parent=None):
        super().__init__(parent)
        self.connection = connection

        self.retro_pending_code = ""
        self.retro_poll_timer = QTimer(self)
        self.retro_poll_timer.setInterval(5000)
        self.retro_poll_timer.timeout.connect(self.on_retro_poll_timeout)

        self.setWindowTitle("Update_All Configuration")
        self.resize(900, 850)
        self.setMinimumSize(760, 500)

        self.build_ui()
        self.load_current_config()
        self.load_retro_status()

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

        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(12)
        self.content_layout.addLayout(columns_layout)

        self.left_column_layout = QVBoxLayout()
        self.left_column_layout.setSpacing(10)

        self.right_column_layout = QVBoxLayout()
        self.right_column_layout.setSpacing(10)

        columns_layout.addLayout(self.left_column_layout, 3)
        columns_layout.addLayout(self.right_column_layout, 2)

        # ===== Main Cores =====
        main_group = self._group("Main Cores", self.left_column_layout)
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
        jt_group = self._group("JTCores", self.left_column_layout)
        self.jtcores_check = QCheckBox("Enable JTCores")
        self.jt_beta_check = QCheckBox("Enable Beta Cores")
        self._add(jt_group, self.jtcores_check)
        self._add(jt_group, self.jt_beta_check, indent=True)
        self.jtcores_check.toggled.connect(self.update_jt_beta_state)

        # ===== Other Cores =====
        other_group = self._group("Other Cores", self.left_column_layout)
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
        tools_group = self._group("Tools & Scripts", self.left_column_layout)
        self.arcade_org_check = QCheckBox("Arcade Organizer")
        self.mrext_check = QCheckBox("MiSTer Extensions (Wizzo Scripts)")
        self.sam_check = QCheckBox("MiSTer Super Attract Mode")
        self.tty2oled_check = QCheckBox("tty2oled Add-on Script")
        self.i2c2oled_check = QCheckBox("i2c2oled Add-on Script")
        self.retrospy_check = QCheckBox("RetroSpy Utility")
        self.anime0t4ku_mister_scripts_check = QCheckBox("Anime0t4ku MiSTer Scripts")

        for widget in [
            self.arcade_org_check,
            self.mrext_check,
            self.sam_check,
            self.tty2oled_check,
            self.i2c2oled_check,
            self.retrospy_check,
            self.anime0t4ku_mister_scripts_check,
        ]:
            self._add(tools_group, widget)

        # ===== Extra Content =====
        extra_group = self._group("Extra Content", self.left_column_layout)
        self.bios_check = QCheckBox("BIOS Database")
        self.arcade_roms_check = QCheckBox("Arcade ROMs Database")
        self.bootroms_check = QCheckBox("Uberyoji Boot ROMs")
        self.gba_borders_check = QCheckBox("Dinierto GBA Borders")
        self.anime0t4ku_wallpapers_check = QCheckBox("Anime0t4ku Wallpapers")
        self.pcn_challenge_wallpapers_check = QCheckBox("PCN Challenge Wallpapers")
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
            self.anime0t4ku_wallpapers_check,
            self.pcn_challenge_wallpapers_check,
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

        # ===== Community Sources =====
        community_group = self._group("Community Sources", self.left_column_layout)
        self.insert_coin_check = QCheckBox("Insert-Coin")
        self.pcn_premium_wallpapers_check = QCheckBox("PCN Premium Member Wallpapers")

        for widget in [
            self.insert_coin_check,
            self.pcn_premium_wallpapers_check,
        ]:
            self._add(community_group, widget)

        # ===== Retro Account =====
        retro_group = self._group("Retro Account", self.right_column_layout)

        self.retro_status_label = QLabel("Status: Not linked")
        self.retro_status_label.setStyleSheet("font-weight: bold;")
        retro_group.layout().addWidget(self.retro_status_label)

        self.retro_description_label = QLabel(
            "Link this MiSTer device to your Retro Account to enable premium "
            "update_all features."
        )
        self.retro_description_label.setWordWrap(True)
        retro_group.layout().addWidget(self.retro_description_label)

        self.retro_link_button = QPushButton("Link Device")
        retro_group.layout().addWidget(self.retro_link_button)

        self.retro_code_title_label = QLabel("Code:")
        self.retro_code_title_label.setStyleSheet("font-weight: bold;")
        retro_group.layout().addWidget(self.retro_code_title_label)

        self.retro_code_value_label = QLabel("—")
        self.retro_code_value_label.setWordWrap(True)
        self.retro_code_value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        retro_group.layout().addWidget(self.retro_code_value_label)

        self.retro_link_title_label = QLabel("Retro Account Link:")
        self.retro_link_title_label.setStyleSheet("font-weight: bold;")
        retro_group.layout().addWidget(self.retro_link_title_label)

        self.retro_link_value_label = QLabel("—")
        self.retro_link_value_label.setWordWrap(True)
        self.retro_link_value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        retro_group.layout().addWidget(self.retro_link_value_label)

        self.retro_waiting_label = QLabel(
            "When linking is in progress, MiSTer Companion will wait for "
            "confirmation and then link this MiSTer automatically."
        )
        self.retro_waiting_label.setWordWrap(True)
        retro_group.layout().addWidget(self.retro_waiting_label)

        retro_button_row = QHBoxLayout()
        self.retro_copy_link_button = QPushButton("Copy Link")
        self.retro_refresh_button = QPushButton("Refresh Status")
        retro_button_row.addWidget(self.retro_copy_link_button)
        retro_button_row.addWidget(self.retro_refresh_button)
        retro_group.layout().addLayout(retro_button_row)

        retro_line = QFrame()
        retro_line.setFrameShape(QFrame.Shape.HLine)
        retro_group.layout().addWidget(retro_line)

        self.retro_device_id_title_label = QLabel("Device ID:")
        self.retro_device_id_title_label.setStyleSheet("font-weight: bold;")
        retro_group.layout().addWidget(self.retro_device_id_title_label)

        self.retro_device_id_value_label = QLabel("—")
        self.retro_device_id_value_label.setWordWrap(True)
        self.retro_device_id_value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        retro_group.layout().addWidget(self.retro_device_id_value_label)

        retro_group.layout().addStretch()

        self._set_retro_ui_state("idle")

        self.content_layout.addStretch()

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

        self.retro_link_button.clicked.connect(self.on_retro_link_device)
        self.retro_copy_link_button.clicked.connect(self.on_retro_copy_link)
        self.retro_refresh_button.clicked.connect(self.on_retro_refresh_status)

    def _group(self, title, target_layout=None):
        box = QFrame()
        box.setFrameShape(QFrame.Shape.StyledPanel)
        box.setStyleSheet("QFrame { border: 1px solid palette(mid); border-radius: 6px; }")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        label = QLabel(title)
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)

        if target_layout is None:
            self.content_layout.addWidget(box)
        else:
            target_layout.addWidget(box)

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

    def _set_retro_ui_state(self, state):
        if state == "idle":
            self.retro_status_label.setText("Status: Not linked")
            self.retro_code_value_label.setText("—")
            self.retro_link_value_label.setText("—")
            self.retro_device_id_value_label.setText("—")

            self.retro_link_button.setEnabled(True)
            self.retro_copy_link_button.setEnabled(False)
            self.retro_refresh_button.setEnabled(False)

        elif state == "pending":
            self.retro_status_label.setText("Status: Waiting for confirmation")
            self.retro_device_id_value_label.setText("—")

            self.retro_link_button.setEnabled(False)
            self.retro_copy_link_button.setEnabled(True)
            self.retro_refresh_button.setEnabled(False)

        elif state == "linked":
            self.retro_status_label.setText("Status: Linked")
            self.retro_code_value_label.setText("—")
            self.retro_link_value_label.setText("—")

            self.retro_link_button.setEnabled(False)
            self.retro_copy_link_button.setEnabled(False)
            self.retro_refresh_button.setEnabled(True)

    def on_retro_link_device(self):
        try:
            result = start_retroaccount_device_link(self.connection)
            self.retro_pending_code = result["code"]

            self._set_retro_ui_state("pending")
            self.retro_code_value_label.setText(result["code"])
            self.retro_link_value_label.setText(result["link"])

            if not self.retro_poll_timer.isActive():
                self.retro_poll_timer.start()

        except Exception as e:
            QMessageBox.critical(self, "Retro Account", f"Failed to start device link:\n{e}")

    def on_retro_copy_link(self):
        link = self.retro_link_value_label.text().strip()
        if not link or link == "—":
            return
        QGuiApplication.clipboard().setText(link)

    def on_retro_refresh_status(self):
        self.load_retro_status()

    def on_retro_poll_timeout(self):
        if not self.retro_pending_code:
            self.retro_poll_timer.stop()
            return

        try:
            result = poll_retroaccount_device_link(self.connection, self.retro_pending_code)

            if result["status"] == "pending":
                return

            if result["status"] == "linked":
                self.retro_poll_timer.stop()
                self.retro_pending_code = ""
                self._set_retro_ui_state("linked")
                self.retro_device_id_value_label.setText(result["device_id"])
                QMessageBox.information(
                    self,
                    "Retro Account",
                    "This MiSTer has been linked successfully.",
                )

        except Exception as e:
            self.retro_poll_timer.stop()
            QMessageBox.critical(self, "Retro Account", f"Linking failed:\n{e}")
            self.load_retro_status()

    def load_retro_status(self):
        try:
            status = get_retroaccount_status(self.connection)
        except Exception:
            self._set_retro_ui_state("idle")
            return

        if status["linked"]:
            self.retro_pending_code = ""
            self.retro_poll_timer.stop()
            self._set_retro_ui_state("linked")
            self.retro_device_id_value_label.setText(status["device_id"])
        else:
            self._set_retro_ui_state("idle")

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
        self.anime0t4ku_mister_scripts_check.setChecked(data["anime0t4ku_mister_scripts"])

        self.bios_check.setChecked(data["bios"])
        self.arcade_roms_check.setChecked(data["arcade_roms"])
        self.bootroms_check.setChecked(data["bootroms"])
        self.gba_borders_check.setChecked(data["gbaborders"])
        self.insert_coin_check.setChecked(data["insert_coin"])
        self.anime0t4ku_wallpapers_check.setChecked(data["anime0t4ku_wallpapers"])
        self.pcn_challenge_wallpapers_check.setChecked(data["pcn_challenge_wallpapers"])
        self.pcn_premium_wallpapers_check.setChecked(data["pcn_premium_wallpapers"])
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
            "anime0t4ku_mister_scripts": self.anime0t4ku_mister_scripts_check.isChecked(),

            "bios": self.bios_check.isChecked(),
            "arcade_roms": self.arcade_roms_check.isChecked(),
            "bootroms": self.bootroms_check.isChecked(),
            "gbaborders": self.gba_borders_check.isChecked(),
            "insert_coin": self.insert_coin_check.isChecked(),
            "anime0t4ku_wallpapers": self.anime0t4ku_wallpapers_check.isChecked(),
            "pcn_challenge_wallpapers": self.pcn_challenge_wallpapers_check.isChecked(),
            "pcn_premium_wallpapers": self.pcn_premium_wallpapers_check.isChecked(),
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

    def closeEvent(self, event):
        self.retro_poll_timer.stop()
        super().closeEvent(event)
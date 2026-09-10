import re
import traceback
import shutil
from datetime import datetime
from pathlib import Path

import requests
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFontDatabase, QFontMetricsF, QKeySequence, QShortcut, QTextCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QPushButton, QMessageBox, QComboBox, QLineEdit, QTextEdit,
    QRadioButton, QButtonGroup, QSpinBox, QSizePolicy, QDialog,
    QScrollArea
)

from core.config import save_config
from core.device_actions import return_to_menu_remote
from core.mister_ini import (
    CUSTOM_RESOLUTION_VALUE,
    NOT_SET_VALUE,
    build_easy_mode_settings,
    easy_mode_values_from_ini_settings,
    parse_mister_ini,
    update_mister_ini_text,
)
from core.mister_settings_backup import (
    create_mister_settings_backup,
    ensure_mister_ini_exists,
    ensure_settings_root_exists,
    get_mister_settings_device_name,
    get_mister_settings_device_path,
    list_mister_settings_backups,
    open_mister_settings_folder,
    restore_mister_settings_backup,
    save_mister_settings_retention_setting,
)
from ui.tab_header import create_tab_header
from ui.dialogs.restore_backup_dialog import RestoreBackupDialog


DEFAULT_MISTER_INI_URL = "https://raw.githubusercontent.com/Anime0t4ku/mister-companion/main/assets/MiSTer_example.ini"


class SoftRebootWorker(QThread):
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, connection):
        super().__init__()
        self.connection = connection

    def run(self):
        try:
            return_to_menu_remote(self.connection)
            self.finished_ok.emit()
        except Exception as e:
            self.failed.emit(str(e))


class MiSTerSettingsRefreshWorker(QThread):
    result = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, connection, offline_mode=False, sd_root="", preferred_filename="MiSTer.ini"):
        super().__init__()
        self.connection = connection
        self.offline_mode = bool(offline_mode)
        self.sd_root = str(sd_root or "").strip()
        self.preferred_filename = self.normalize_ini_filename(preferred_filename) or "MiSTer.ini"

    def normalize_ini_filename(self, filename):
        filename = Path(str(filename or "").strip()).name

        if filename == "MiSTer.ini":
            return filename

        if filename.startswith("MiSTer_") and filename.endswith(".ini"):
            return filename

        return ""

    def sort_ini_files(self, files):
        unique = []
        for filename in files:
            name = self.normalize_ini_filename(filename)
            if name and name not in unique:
                unique.append(name)
        unique.sort(key=lambda item: (item != "MiSTer.ini", item.lower()))
        return unique

    def offline_root_path(self):
        if not self.sd_root:
            return None

        root = Path(self.sd_root).expanduser()
        if not root.exists() or not root.is_dir():
            return None

        return root

    def scan_offline_ini_files(self):
        root = self.offline_root_path()
        if not root:
            return []

        files = []
        for path in root.iterdir():
            if not path.is_file():
                continue
            name = self.normalize_ini_filename(path.name)
            if name:
                files.append(name)

        return self.sort_ini_files(files)

    def scan_remote_ini_files(self):
        if not self.connection or not self.connection.is_connected():
            return []

        command = (
            "cd /media/fat 2>/dev/null || exit 0; "
            "for f in MiSTer.ini MiSTer_*.ini; do "
            "[ -f \"$f\" ] && echo \"$f\"; "
            "done"
        )

        result = self.connection.run_command(command) or ""
        return self.sort_ini_files(result.splitlines())

    def normalize_ini_text(self, text, ensure_trailing_newline=True):
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in text.split("\n")]
        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.rstrip("\n")

        if ensure_trailing_newline:
            text += "\n"

        return text

    def download_default_mister_ini(self):
        response = requests.get(
            DEFAULT_MISTER_INI_URL,
            timeout=15,
            headers={"User-Agent": "MiSTer-Companion"},
        )
        response.raise_for_status()

        text = self.normalize_ini_text(response.text, ensure_trailing_newline=True)
        if "[MiSTer]" not in text:
            raise ValueError("Downloaded default ini does not look valid.")

        return text

    def ensure_ini_files(self):
        if self.offline_mode:
            root = self.offline_root_path()
            if not root:
                return [], "", "Select a valid MiSTer SD card first."
            return self.scan_offline_ini_files(), "", ""

        if not self.connection or not self.connection.is_connected():
            return [], "", "Connect to a MiSTer first."

        return self.scan_remote_ini_files(), "", ""

    def choose_selected_file(self, files):
        if not files:
            return ""

        if self.preferred_filename in files:
            return self.preferred_filename

        if "MiSTer.ini" in files:
            return "MiSTer.ini"

        return files[0]

    def read_offline_ini(self, filename):
        root = self.offline_root_path()
        if not root:
            raise RuntimeError("Select a valid MiSTer SD card first.")

        path = root / filename
        if not path.exists():
            raise FileNotFoundError(f"{filename} was not found on the selected SD card.")

        return path.read_text(encoding="utf-8", errors="ignore")

    def read_remote_ini(self, filename):
        if not self.connection or not self.connection.is_connected():
            raise RuntimeError("Connect to a MiSTer first.")

        remote_path = f"/media/fat/{filename}"
        sftp = self.connection.client.open_sftp()
        try:
            with sftp.open(remote_path, "r") as f:
                data = f.read()
        finally:
            sftp.close()

        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="ignore")

        return data

    def run(self):
        try:
            files, notice, error = self.ensure_ini_files()
            if error:
                self.result.emit(
                    {
                        "ok": False,
                        "files": [],
                        "selected_filename": "",
                        "ini_text": "",
                        "fonts": [],
                        "notice": error,
                    }
                )
                return

            if not files:
                self.result.emit(
                    {
                        "ok": False,
                        "files": [],
                        "selected_filename": "",
                        "ini_text": "",
                        "fonts": [],
                        "notice": "No MiSTer.ini or MiSTer_*.ini files found.",
                        "missing_ini": True,
                    }
                )
                return

            selected_filename = self.choose_selected_file(files)

            if self.offline_mode:
                ini_text = self.read_offline_ini(selected_filename)
            else:
                ini_text = self.read_remote_ini(selected_filename)

            self.result.emit(
                {
                    "ok": True,
                    "files": files,
                    "selected_filename": selected_filename,
                    "ini_text": (ini_text or "").replace("\r\n", "\n").replace("\r", "\n"),
                    "notice": notice,
                }
            )
        except Exception as e:
            detail = f"{e}\n\n{traceback.format_exc()}"
            self.failed.emit(detail)


class MiSTerSettingsFontWorker(QThread):
    result = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, connection, offline_mode=False, sd_root=""):
        super().__init__()
        self.connection = connection
        self.offline_mode = bool(offline_mode)
        self.sd_root = str(sd_root or "").strip()

    def offline_root_path(self):
        if not self.sd_root:
            return None

        root = Path(self.sd_root).expanduser()
        if not root.exists() or not root.is_dir():
            return None

        return root

    def scan_offline_fonts(self):
        root = self.offline_root_path()
        if not root:
            return []

        font_dir = root / "font"
        if not font_dir.exists() or not font_dir.is_dir():
            return []

        fonts = []
        for item in font_dir.iterdir():
            if item.is_file() and item.name.lower().endswith(".pf"):
                fonts.append(item.name)

        fonts.sort(key=str.lower)
        return fonts

    def scan_remote_fonts(self):
        if not self.connection or not self.connection.is_connected():
            return []

        result = self.connection.run_command(
            r'if [ -d /media/fat/font ]; then for f in /media/fat/font/*.pf /media/fat/font/*.PF; do [ -e "$f" ] || continue; basename "$f"; done; fi'
        ) or ""

        fonts = []
        for line in result.splitlines():
            name = line.strip()
            if not name:
                continue
            if not name.lower().endswith(".pf"):
                continue
            if name not in fonts:
                fonts.append(name)

        fonts.sort(key=str.lower)
        return fonts

    def run(self):
        try:
            if self.offline_mode:
                fonts = self.scan_offline_fonts()
            else:
                fonts = self.scan_remote_fonts()

            self.result.emit(fonts)
        except Exception as e:
            self.failed.emit(str(e))


class MiSTerSettingsTab(QWidget):
    ANALOGUE_PRESETS = [
        "RGBS (SCART)",
        "RGBHV (VGA 15 kHz)",
        "RGsB (Sync-on-Green)",
        "YPbPr (Component)",
        "S-Video",
        "Composite (CVBS)",
        "VGA Scaler (31 kHz+)",
    ]

    CUSTOM_ANALOGUE_VALUE = "Custom"

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection
        self.config_data = main_window.config_data

        self.cached_font_list = None
        self.pending_font_selection = NOT_SET_VALUE
        self.font_scan_scheduled = False
        self.ini_selector_loading = False
        self.missing_ini_dialog_active = False
        self.active_ini_filename = ""
        self.loaded_ini_text = ""

        self.loading_settings = False
        self.syncing_modes = False
        self.soft_reboot_worker = None
        self.refresh_worker = None
        self.font_worker = None

        ensure_settings_root_exists()

        self.build_ui()
        self.apply_disconnected_state()

    def build_ui(self):
        self.setObjectName("MiSTerSettingsPage")
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(0)
        self.setLayout(main_layout)

        main_layout.addWidget(create_tab_header(self.main_window, "MiSTer Settings", "mister_settings"))
        main_layout.addSpacing(10)

        self.page_scroll_area = QScrollArea()
        self.page_scroll_area.setWidgetResizable(True)
        self.page_scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.page_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.page_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.page_scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.page_scroll_area.viewport().setAutoFillBackground(False)

        scroll_content = QWidget()
        scroll_content.setObjectName("SettingsScrollContent")
        scroll_content.setStyleSheet("QWidget#SettingsScrollContent { background: transparent; }")
        content_row = QHBoxLayout(scroll_content)
        content_row.setContentsMargins(0, 0, 0, 0)

        self.settings_shell = QWidget()
        self.settings_shell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.settings_shell.setStyleSheet("QWidget#SettingsShell { background: transparent; }")
        self.settings_shell.setObjectName("SettingsShell")
        shell_layout = QVBoxLayout(self.settings_shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(6)

        content_row.addWidget(self.settings_shell, 1)
        self.page_scroll_area.setWidget(scroll_content)
        main_layout.addWidget(self.page_scroll_area, 1)

        self.setStyleSheet(
            """
            QWidget#MiSTerSettingsPage QGroupBox#SettingsCard {
                background-color: palette(alternate-base);
                border: 1px solid palette(button);
                border-radius: 12px;
                margin-top: 18px;
                padding: 14px;
                font-weight: 700;
            }

            QWidget#MiSTerSettingsPage QGroupBox#SettingsCard::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                padding: 0px 7px;
                background: transparent;
                color: palette(highlight);
            }
            """
        )

        self.configuration_group = QGroupBox("Configuration")
        self.configuration_group.setObjectName("SettingsCard")
        configuration_layout = QVBoxLayout(self.configuration_group)
        configuration_layout.setContentsMargins(12, 10, 12, 8)
        configuration_layout.setSpacing(2)

        ini_row = QHBoxLayout()
        ini_row.setContentsMargins(0, 0, 0, 0)
        ini_row.setSpacing(8)
        ini_row.addStretch()

        self.ini_file_label = QLabel("INI File:")
        self.ini_file_combo = QComboBox()
        self.ini_file_combo.setMinimumWidth(220)
        self.refresh_ini_files_button = QPushButton("Refresh")

        ini_row.addWidget(self.ini_file_label)
        ini_row.addWidget(self.ini_file_combo)
        ini_row.addWidget(self.refresh_ini_files_button)
        ini_row.addStretch()

        configuration_layout.addLayout(ini_row)

        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(10)
        mode_row.addStretch()

        mode_label = QLabel("Mode:")
        mode_row.addWidget(mode_label)

        self.easy_mode_radio = QRadioButton("Easy")
        self.advanced_mode_radio = QRadioButton("Advanced")
        self.easy_mode_radio.setChecked(True)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.easy_mode_radio)
        self.mode_group.addButton(self.advanced_mode_radio)

        mode_row.addWidget(self.easy_mode_radio)
        mode_row.addWidget(self.advanced_mode_radio)
        mode_row.addStretch()

        configuration_layout.addLayout(mode_row)

        self.notice_label = QLabel("")
        self.notice_label.setWordWrap(True)
        self.notice_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.notice_label.setStyleSheet("color: orange;")
        self.notice_label.hide()
        shell_layout.addWidget(self.notice_label)

        self.easy_group = QGroupBox("Easy Mode")
        self.easy_group.setObjectName("SettingsCard")
        easy_layout = QGridLayout()
        easy_layout.setContentsMargins(18, 20, 18, 14)
        easy_layout.setHorizontalSpacing(18)
        easy_layout.setVerticalSpacing(5)

        self.easy_hdmi_mode_combo = QComboBox()
        self.easy_hdmi_mode_combo.addItems([
            NOT_SET_VALUE,
            "HD Output (Default)",
            "Direct Video (CRT / Scaler)"
        ])

        self.easy_resolution_combo = QComboBox()
        self.easy_resolution_combo.addItems([
            NOT_SET_VALUE,
            "1280x720@60",
            "1024x768@60",
            "720x480@60",
            "720x576@50",
            "1280x1024@60",
            "800x600@60",
            "640x480@60",
            "1280x720@50",
            "1920x1080@60",
            "1920x1080@50",
            "1366x768@60",
            "1024x600@60",
            "1920x1440@60",
            "2048x1536@60",
            "2560x1440@60"
        ])

        self.easy_scaling_combo = QComboBox()
        self.easy_scaling_combo.addItems([
            NOT_SET_VALUE,
            "Disabled",
            "Low Latency",
            "Exact Refresh"
        ])

        self.easy_hdmi_audio_combo = QComboBox()
        self.easy_hdmi_audio_combo.addItems([
            NOT_SET_VALUE,
            "Enabled",
            "Disabled (DVI Mode)"
        ])

        self.easy_hdr_combo = QComboBox()
        self.easy_hdr_combo.addItems([
            NOT_SET_VALUE,
            "Disabled",
            "HLG HDR (recommended)",
            "DCI P3 HDR"
        ])

        self.easy_hdmi_limited_combo = QComboBox()
        self.easy_hdmi_limited_combo.addItems([
            NOT_SET_VALUE,
            "Full Range",
            "Limited Range"
        ])

        self.easy_analogue_combo = QComboBox()
        self.easy_analogue_combo.addItems([NOT_SET_VALUE] + self.ANALOGUE_PRESETS)

        self.easy_logo_combo = QComboBox()
        self.easy_logo_combo.addItems([
            NOT_SET_VALUE,
            "Enabled",
            "Disabled"
        ])

        self.easy_recents_combo = QComboBox()
        self.easy_recents_combo.addItems([
            NOT_SET_VALUE,
            "Off",
            "On"
        ])

        self.easy_font_combo = QComboBox()
        self.easy_font_combo.addItem(NOT_SET_VALUE)
        self.easy_font_combo.addItem("Default")

        self.easy_amigavision_preset_combo = QComboBox()
        self.easy_amigavision_preset_combo.addItems([
            "Disabled",
            "Enabled"
        ])

        self.easy_menu_crt_preset_combo = QComboBox()
        self.easy_menu_crt_preset_combo.addItems([
            "Disabled",
            "NTSC, Large Text",
            "NTSC, Small Text",
            "PAL, Large Text",
            "PAL, Small Text"
        ])

        for combo in (
            self.easy_hdmi_mode_combo,
            self.easy_resolution_combo,
            self.easy_scaling_combo,
            self.easy_hdmi_audio_combo,
            self.easy_hdr_combo,
            self.easy_hdmi_limited_combo,
            self.easy_analogue_combo,
            self.easy_logo_combo,
            self.easy_recents_combo,
            self.easy_font_combo,
        ):
            self.disable_combo_value(combo, NOT_SET_VALUE)

        easy_fields = [
            ("HDMI Mode", self.easy_hdmi_mode_combo),
            ("Resolution", self.easy_resolution_combo),
            ("HDMI VSync Mode", self.easy_scaling_combo),
            ("HDMI Audio", self.easy_hdmi_audio_combo),
            ("HDR", self.easy_hdr_combo),
            ("HDMI Range", self.easy_hdmi_limited_combo),
            ("Analogue Output", self.easy_analogue_combo),
            ("MiSTer Logo", self.easy_logo_combo),
            ("Recents", self.easy_recents_combo),
            ("Font", self.easy_font_combo),
            ("AmigaVision Preset", self.easy_amigavision_preset_combo),
            ("Menu CRT Preset", self.easy_menu_crt_preset_combo),
        ]
        for row, (label_text, combo) in enumerate(easy_fields):
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            combo.setMinimumWidth(360)
            easy_layout.addWidget(label, row, 0)
            easy_layout.addWidget(combo, row, 1)

        easy_layout.setColumnMinimumWidth(0, 160)
        easy_layout.setColumnStretch(1, 1)
        self.easy_group.setLayout(easy_layout)
        self.easy_group.setMinimumWidth(0)
        self.easy_group.setMaximumWidth(900)
        self.easy_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        shell_layout.addWidget(self.easy_group, 0, Qt.AlignmentFlag.AlignHCenter)

        self.advanced_group = QGroupBox("Advanced Mode")
        self.advanced_group.setObjectName("SettingsCard")
        advanced_layout = QVBoxLayout()
        advanced_layout.setContentsMargins(16, 20, 16, 14)
        advanced_layout.setSpacing(8)

        self.advanced_find_bar = QWidget()
        self.advanced_find_bar.setObjectName("AdvancedFindBar")
        self.advanced_find_bar.setStyleSheet("QWidget#AdvancedFindBar { background: transparent; }")
        find_layout = QHBoxLayout(self.advanced_find_bar)
        find_layout.setContentsMargins(0, 0, 0, 0)
        find_layout.setSpacing(6)

        self.advanced_find_edit = QLineEdit()
        self.advanced_find_edit.setPlaceholderText("Find")
        self.advanced_find_edit.setClearButtonEnabled(True)
        self.advanced_find_previous_button = QPushButton("Previous")
        self.advanced_find_next_button = QPushButton("Next")
        self.advanced_find_count_label = QLabel("0 / 0")
        self.advanced_find_count_label.setMinimumWidth(54)
        self.advanced_find_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        find_layout.addWidget(self.advanced_find_edit, 1)
        find_layout.addWidget(self.advanced_find_previous_button)
        find_layout.addWidget(self.advanced_find_next_button)
        find_layout.addWidget(self.advanced_find_count_label)
        advanced_layout.addWidget(self.advanced_find_bar)

        self.advanced_text = QTextEdit()
        self.advanced_text.setAcceptRichText(False)
        fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.advanced_text.setFont(fixed_font)
        self.advanced_text.setTabStopDistance(QFontMetricsF(fixed_font).horizontalAdvance(" ") * 4)
        self.advanced_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.advanced_text.setStyleSheet("")
        self.advanced_text.setMinimumHeight(0)
        self.advanced_text.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        advanced_layout.addWidget(self.advanced_text)
        self.advanced_group.setLayout(advanced_layout)
        self.advanced_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        shell_layout.addWidget(self.advanced_group, stretch=1)

        self.actions_group = QGroupBox("Actions")
        self.actions_group.setObjectName("SettingsCard")
        actions_layout = QVBoxLayout(self.actions_group)
        actions_layout.setContentsMargins(12, 10, 12, 8)
        actions_layout.setSpacing(2)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.save_button = QPushButton("Save")
        self.backup_button = QPushButton("Backup")
        self.restore_button = QPushButton("Restore Backup")
        self.defaults_button = QPushButton("Restore Defaults")

        button_row.addWidget(self.save_button)
        button_row.addWidget(self.backup_button)
        button_row.addWidget(self.restore_button)
        button_row.addWidget(self.defaults_button)
        button_row.addStretch()
        actions_layout.addLayout(button_row)

        retention_row = QHBoxLayout()
        retention_row.addStretch()

        self.retention_label = QLabel("Backups:")
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 100)
        self.retention_spin.setValue(self.config_data.get("mister_settings_retention", 10))
        self.open_backup_folder_button = QPushButton("Open Backup Folder")

        retention_row.addWidget(self.retention_label)
        retention_row.addWidget(self.retention_spin)
        retention_row.addWidget(self.open_backup_folder_button)
        retention_row.addStretch()
        actions_layout.addLayout(retention_row)
        top_card_height = 128
        self.configuration_group.setMinimumHeight(top_card_height)
        self.configuration_group.setMaximumHeight(top_card_height)
        self.actions_group.setMinimumHeight(top_card_height)
        self.actions_group.setMaximumHeight(top_card_height)

        self.top_cards = QWidget()
        self.top_cards.setObjectName("SettingsTopCards")
        self.top_cards.setStyleSheet("QWidget#SettingsTopCards { background: transparent; }")
        self.top_cards.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.top_cards.setMaximumWidth(900)
        self.top_cards.setFixedHeight(top_card_height)
        top_cards_layout = QHBoxLayout(self.top_cards)
        top_cards_layout.setContentsMargins(0, 0, 0, 0)
        top_cards_layout.setSpacing(10)
        top_cards_layout.addWidget(self.configuration_group, 1)
        top_cards_layout.addWidget(self.actions_group, 1)
        shell_layout.insertWidget(0, self.top_cards, 0, Qt.AlignmentFlag.AlignHCenter)
        QTimer.singleShot(0, self._sync_easy_group_width)

        self.ini_file_combo.currentTextChanged.connect(self.on_ini_file_selected)
        self.refresh_ini_files_button.clicked.connect(self.handle_refresh_ini_file_list)

        self.easy_hdmi_mode_combo.currentIndexChanged.connect(self.update_easy_mode_state)
        self.easy_mode_radio.toggled.connect(self.update_settings_mode)
        self.advanced_mode_radio.toggled.connect(self.update_settings_mode)

        self.save_button.clicked.connect(self.save_mister_settings)
        self.backup_button.clicked.connect(self.backup_mister_settings)
        self.restore_button.clicked.connect(self.restore_mister_settings)
        self.defaults_button.clicked.connect(self.restore_default_mister_settings)
        self.retention_spin.valueChanged.connect(self.save_mister_settings_retention_setting)
        self.open_backup_folder_button.clicked.connect(self.open_mister_settings_folder)

        self.advanced_text.textChanged.connect(self.on_advanced_text_changed)
        self.advanced_find_edit.textChanged.connect(self.on_advanced_find_text_changed)
        self.advanced_find_edit.returnPressed.connect(self.find_next_advanced_match)
        self.advanced_find_previous_button.clicked.connect(self.find_previous_advanced_match)
        self.advanced_find_next_button.clicked.connect(self.find_next_advanced_match)

        self.advanced_find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self.advanced_find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.advanced_find_shortcut.activated.connect(self.open_advanced_find)
        self.advanced_find_previous_shortcut = QShortcut(QKeySequence("Shift+Return"), self.advanced_find_edit)
        self.advanced_find_previous_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.advanced_find_previous_shortcut.activated.connect(self.find_previous_advanced_match)
        self.advanced_find_previous_enter_shortcut = QShortcut(QKeySequence("Shift+Enter"), self.advanced_find_edit)
        self.advanced_find_previous_enter_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.advanced_find_previous_enter_shortcut.activated.connect(self.find_previous_advanced_match)
        for combo in self.easy_mode_combos():
            combo.currentIndexChanged.connect(self.on_easy_setting_changed)

        self.easy_hdmi_mode_combo.setCurrentText(NOT_SET_VALUE)
        self.easy_resolution_combo.setCurrentText(NOT_SET_VALUE)
        self.easy_scaling_combo.setCurrentText(NOT_SET_VALUE)
        self.easy_hdmi_audio_combo.setCurrentText(NOT_SET_VALUE)
        self.easy_hdr_combo.setCurrentText(NOT_SET_VALUE)
        self.easy_hdmi_limited_combo.setCurrentText(NOT_SET_VALUE)
        self.set_analogue_combo_value(NOT_SET_VALUE)
        self.easy_logo_combo.setCurrentText(NOT_SET_VALUE)
        self.easy_recents_combo.setCurrentText(NOT_SET_VALUE)
        self.easy_font_combo.setCurrentText(NOT_SET_VALUE)
        self.easy_amigavision_preset_combo.setCurrentText("Disabled")
        self.easy_menu_crt_preset_combo.setCurrentText("Disabled")

        self.update_easy_mode_state()
        self.update_settings_mode()

    def easy_mode_combos(self):
        return [
            self.easy_hdmi_mode_combo,
            self.easy_resolution_combo,
            self.easy_scaling_combo,
            self.easy_hdmi_audio_combo,
            self.easy_hdr_combo,
            self.easy_hdmi_limited_combo,
            self.easy_analogue_combo,
            self.easy_logo_combo,
            self.easy_recents_combo,
            self.easy_font_combo,
            self.easy_amigavision_preset_combo,
            self.easy_menu_crt_preset_combo,
        ]

    def disable_combo_value(self, combo, value):
        index = combo.findText(value)
        if index < 0:
            return
        item = combo.model().item(index)
        if item is not None:
            item.setEnabled(False)

    def remove_custom_resolution_item(self):
        index = self.easy_resolution_combo.findText(CUSTOM_RESOLUTION_VALUE)
        if index >= 0:
            self.easy_resolution_combo.removeItem(index)

    def add_custom_resolution_item(self):
        index = self.easy_resolution_combo.findText(CUSTOM_RESOLUTION_VALUE)

        if index < 0:
            self.easy_resolution_combo.addItem(CUSTOM_RESOLUTION_VALUE)
            index = self.easy_resolution_combo.findText(CUSTOM_RESOLUTION_VALUE)

        item = self.easy_resolution_combo.model().item(index)
        if item is not None:
            item.setEnabled(False)

        return index

    def set_resolution_combo_value(self, value):
        value = (value or NOT_SET_VALUE).strip()

        self.easy_resolution_combo.blockSignals(True)

        if value == CUSTOM_RESOLUTION_VALUE:
            index = self.add_custom_resolution_item()
            self.easy_resolution_combo.setCurrentIndex(index)
        else:
            self.remove_custom_resolution_item()

            if self.easy_resolution_combo.findText(value) < 0:
                value = NOT_SET_VALUE

            self.easy_resolution_combo.setCurrentText(value)

        self.easy_resolution_combo.blockSignals(False)

    def remove_custom_analogue_item(self):
        index = self.easy_analogue_combo.findText(self.CUSTOM_ANALOGUE_VALUE)
        if index >= 0:
            self.easy_analogue_combo.removeItem(index)

    def add_custom_analogue_item(self):
        index = self.easy_analogue_combo.findText(self.CUSTOM_ANALOGUE_VALUE)

        if index < 0:
            self.easy_analogue_combo.addItem(self.CUSTOM_ANALOGUE_VALUE)
            index = self.easy_analogue_combo.findText(self.CUSTOM_ANALOGUE_VALUE)

        item = self.easy_analogue_combo.model().item(index)
        if item is not None:
            item.setEnabled(False)

        return index

    def set_analogue_combo_value(self, value):
        value = (value or NOT_SET_VALUE).strip()

        self.easy_analogue_combo.blockSignals(True)

        if value == self.CUSTOM_ANALOGUE_VALUE:
            index = self.add_custom_analogue_item()
            self.easy_analogue_combo.setCurrentIndex(index)
        else:
            self.remove_custom_analogue_item()

            if self.easy_analogue_combo.findText(value) < 0:
                value = NOT_SET_VALUE

            self.easy_analogue_combo.setCurrentText(value)

        self.easy_analogue_combo.blockSignals(False)

    def on_easy_setting_changed(self, *_):
        if self.loading_settings or self.syncing_modes:
            return

        if self.easy_mode_radio.isChecked():
            self.sync_easy_to_advanced(self.sender())

    def on_advanced_text_changed(self):
        if hasattr(self, "advanced_find_edit") and self.advanced_find_edit.text():
            self.refresh_advanced_find()

        if self.loading_settings or self.syncing_modes:
            return

        if self.advanced_mode_radio.isChecked():
            self.sync_advanced_to_easy()

    def open_advanced_find(self):
        if not self.advanced_mode_radio.isChecked():
            return

        selected_text = self.advanced_text.textCursor().selectedText()
        if selected_text and "\n" not in selected_text and "\u2029" not in selected_text:
            self.advanced_find_edit.setText(selected_text)
        self.advanced_find_edit.setFocus()
        self.advanced_find_edit.selectAll()
        self.refresh_advanced_find()

    def on_advanced_find_text_changed(self, *_):
        self.refresh_advanced_find(select_first=True)

    def advanced_find_matches(self):
        query = self.advanced_find_edit.text()
        if not query:
            return []

        matches = []
        document = self.advanced_text.document()
        cursor = QTextCursor(document)
        while True:
            match = document.find(query, cursor)
            if match.isNull():
                break
            matches.append((match.selectionStart(), match.selectionEnd()))
            cursor = QTextCursor(match)
            cursor.setPosition(match.selectionEnd())
        return matches

    def refresh_advanced_find(self, select_first=False):
        matches = self.advanced_find_matches()
        if not matches:
            self.advanced_find_count_label.setText("0 / 0")
            return

        current = self.advanced_text.textCursor()
        current_start = current.selectionStart()
        current_end = current.selectionEnd()
        index = -1
        for i, (start, end) in enumerate(matches):
            if start == current_start and end == current_end:
                index = i
                break

        if select_first or index < 0:
            position = current.position()
            index = next((i for i, (start, _) in enumerate(matches) if start >= position), 0)
            self.select_advanced_find_match(matches, index)

        self.advanced_find_count_label.setText(f"{index + 1} / {len(matches)}")

    def select_advanced_find_match(self, matches, index):
        if not matches:
            return
        index %= len(matches)
        start, end = matches[index]
        cursor = self.advanced_text.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.advanced_text.setTextCursor(cursor)
        self.advanced_text.ensureCursorVisible()
        self.advanced_find_count_label.setText(f"{index + 1} / {len(matches)}")

    def find_next_advanced_match(self):
        matches = self.advanced_find_matches()
        if not matches:
            self.advanced_find_count_label.setText("0 / 0")
            return
        cursor = self.advanced_text.textCursor()
        end = cursor.selectionEnd()
        index = next((i for i, (start, _) in enumerate(matches) if start >= end), 0)
        self.select_advanced_find_match(matches, index)

    def find_previous_advanced_match(self):
        matches = self.advanced_find_matches()
        if not matches:
            self.advanced_find_count_label.setText("0 / 0")
            return
        cursor = self.advanced_text.textCursor()
        start = cursor.selectionStart()
        previous = [i for i, (_, end) in enumerate(matches) if end <= start]
        index = previous[-1] if previous else len(matches) - 1
        self.select_advanced_find_match(matches, index)

    def sync_easy_to_advanced(self, changed_combo=None):
        if self.loading_settings or self.syncing_modes:
            return

        enabled = (
            (self.is_offline_mode() and bool(self.offline_root_path()))
            or self.connection.is_connected()
        ) and self.ini_file_combo.count() > 0

        if not enabled:
            return

        self.syncing_modes = True
        try:
            current_text = self.advanced_text.toPlainText()

            if not current_text.strip():
                current_text = "[MiSTer]\n"

            setting_keys = {
                self.easy_hdmi_mode_combo: {"direct_video"},
                self.easy_resolution_combo: {"video_mode"},
                self.easy_scaling_combo: {"vsync_adjust"},
                self.easy_hdmi_audio_combo: {"dvi_mode"},
                self.easy_hdr_combo: {"hdr"},
                self.easy_hdmi_limited_combo: {"hdmi_limited"},
                self.easy_analogue_combo: {
                    "vga_mode", "composite_sync", "vga_sog",
                    "vga_scaler", "forced_scandoubler",
                },
                self.easy_logo_combo: {"logo"},
                self.easy_recents_combo: {"recents"},
                self.easy_font_combo: {"font"},
                self.easy_amigavision_preset_combo: {"__amigavision_preset"},
                self.easy_menu_crt_preset_combo: {"__menu_crt_preset"},
            }.get(changed_combo)

            # Mode changes and background UI updates never rewrite the working
            # document. Only a real Easy Mode control change reaches here.
            if not setting_keys:
                return

            all_settings = self.build_easy_mode_settings()
            updated_settings = {
                key: value for key, value in all_settings.items()
                if key in setting_keys
                or key.removesuffix("_commented") in setting_keys
            }
            new_ini_text = update_mister_ini_text(current_text, updated_settings)

            self.advanced_text.blockSignals(True)
            self.advanced_text.setPlainText(new_ini_text)
            self.advanced_text.blockSignals(False)
        finally:
            self.syncing_modes = False

    def sync_advanced_to_easy(self):
        if self.loading_settings or self.syncing_modes:
            return

        enabled = (
            (self.is_offline_mode() and bool(self.offline_root_path()))
            or self.connection.is_connected()
        ) and self.ini_file_combo.count() > 0

        if not enabled:
            return

        self.syncing_modes = True
        try:
            self.apply_advanced_to_easy()
        finally:
            self.syncing_modes = False

    def is_offline_mode(self):
        return hasattr(self.main_window, "is_offline_mode") and self.main_window.is_offline_mode()

    def get_offline_sd_root(self):
        if hasattr(self.main_window, "get_offline_sd_root"):
            return self.main_window.get_offline_sd_root()
        return ""

    def offline_root_path(self):
        sd_root = self.get_offline_sd_root()
        if not sd_root:
            return None

        root = Path(sd_root).expanduser()

        if not root.exists() or not root.is_dir():
            return None

        return root

    def normalize_ini_filename(self, filename):
        filename = Path(str(filename or "").strip()).name

        if filename == "MiSTer.ini":
            return filename

        if filename.startswith("MiSTer_") and filename.endswith(".ini"):
            return filename

        return ""

    def selected_ini_filename(self):
        filename = self.normalize_ini_filename(self.ini_file_combo.currentText())
        if filename:
            return filename

        filename = self.normalize_ini_filename(
            self.config_data.get("mister_settings_ini_file", "MiSTer.ini")
        )
        if filename:
            return filename

        return "MiSTer.ini"

    def selected_remote_ini_path(self):
        return f"/media/fat/{self.selected_ini_filename()}"

    def selected_offline_ini_path(self):
        root = self.offline_root_path()
        if not root:
            return None
        return root / self.selected_ini_filename()

    def remember_selected_ini_filename(self):
        filename = self.selected_ini_filename()
        self.config_data["mister_settings_ini_file"] = filename
        try:
            save_config(self.config_data)
        except Exception:
            pass

    def scan_offline_ini_files(self):
        root = self.offline_root_path()
        if not root:
            return []

        files = []

        for path in root.iterdir():
            if not path.is_file():
                continue

            name = self.normalize_ini_filename(path.name)
            if name and name not in files:
                files.append(name)

        files.sort(key=lambda item: (item != "MiSTer.ini", item.lower()))
        return files

    def scan_remote_ini_files(self):
        if not self.connection.is_connected():
            return []

        command = (
            "cd /media/fat 2>/dev/null || exit 0; "
            "for f in MiSTer.ini MiSTer_*.ini; do "
            "[ -f \"$f\" ] && echo \"$f\"; "
            "done"
        )

        result = self.connection.run_command(command) or ""
        files = []

        for line in result.splitlines():
            name = self.normalize_ini_filename(line.strip())
            if name and name not in files:
                files.append(name)

        files.sort(key=lambda item: (item != "MiSTer.ini", item.lower()))
        return files

    def handle_refresh_ini_file_list(self):
        self.refresh_tab_contents()

    def on_ini_file_selected(self):
        if self.ini_selector_loading:
            return

        new_filename = self.normalize_ini_filename(self.ini_file_combo.currentText())
        if not new_filename:
            return

        if (
            self.active_ini_filename
            and new_filename != self.active_ini_filename
            and self.has_unsaved_ini_changes()
        ):
            warning = QMessageBox(self)
            warning.setIcon(QMessageBox.Icon.Warning)
            warning.setWindowTitle("Unsaved MiSTer Settings")
            warning.setText(
                f"You have unsaved changes to {self.active_ini_filename}."
            )
            warning.setInformativeText(
                f"Switching to {new_filename} will discard those changes. "
                "Do you want to continue?"
            )
            switch_button = warning.addButton(
                "Switch INI", QMessageBox.ButtonRole.DestructiveRole
            )
            warning.addButton(QMessageBox.StandardButton.Cancel)
            warning.setDefaultButton(QMessageBox.StandardButton.Cancel)
            warning.exec()

            if warning.clickedButton() is not switch_button:
                self.ini_file_combo.blockSignals(True)
                self.ini_file_combo.setCurrentText(self.active_ini_filename)
                self.ini_file_combo.blockSignals(False)
                return

        self.remember_selected_ini_filename()
        self.cached_font_list = None
        self.pending_font_selection = NOT_SET_VALUE
        self.font_scan_scheduled = False

        self.loading_settings = True
        try:
            self.load_mister_ini_advanced()
            self.load_mister_ini_into_ui(silent=True)
        finally:
            self.loading_settings = False

        self.update_settings_mode()

    def has_unsaved_ini_changes(self):
        if not self.active_ini_filename:
            return False
        return self.advanced_text.toPlainText() != self.loaded_ini_text

    def mark_current_ini_clean(self, ini_text, filename=None):
        text = (ini_text or "").replace("\r\n", "\n").replace("\r", "\n")
        self.loaded_ini_text = text
        self.active_ini_filename = self.normalize_ini_filename(
            filename or self.ini_file_combo.currentText()
        )

    def download_default_mister_ini(self):
        response = requests.get(
            DEFAULT_MISTER_INI_URL,
            timeout=15,
            headers={
                "User-Agent": "MiSTer-Companion",
            },
        )
        response.raise_for_status()

        text = self.normalize_ini_text(response.text, ensure_trailing_newline=True)

        if "[MiSTer]" not in text:
            raise ValueError("Downloaded default ini does not look valid.")

        return text

    def read_offline_mister_ini(self):
        ini_path = self.selected_offline_ini_path()
        if not ini_path:
            return None, "Select a valid MiSTer SD card first."

        if not ini_path.exists():
            return None, f"{self.selected_ini_filename()} was not found on the selected SD card."

        try:
            return ini_path.read_text(encoding="utf-8", errors="ignore"), ""
        except Exception as e:
            return None, str(e)

    def write_offline_mister_ini(self, text):
        ini_path = self.selected_offline_ini_path()
        if not ini_path:
            return False, "Select a valid MiSTer SD card first."

        try:
            ini_path.write_text(text, encoding="utf-8")
            return True, ""
        except Exception as e:
            return False, str(e)

    def read_remote_mister_ini(self):
        if not self.connection.is_connected():
            return None, "Connect to a MiSTer first."

        remote_path = self.selected_remote_ini_path()

        sftp = self.connection.client.open_sftp()
        try:
            try:
                with sftp.open(remote_path, "r") as f:
                    data = f.read()
            except FileNotFoundError:
                return None, f"{self.selected_ini_filename()} was not found on the MiSTer."

            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="ignore")

            return data, ""
        except Exception as e:
            return None, str(e)
        finally:
            sftp.close()

    def write_remote_mister_ini(self, text):
        if not self.connection.is_connected():
            return False, "Connect to a MiSTer first."

        remote_path = self.selected_remote_ini_path()

        sftp = self.connection.client.open_sftp()
        try:
            with sftp.open(remote_path, "w") as f:
                f.write(text)
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            sftp.close()

    def set_notice(self, text=""):
        text = (text or "").strip()
        self.notice_label.setText(text)
        self.notice_label.setVisible(bool(text))

    def normalize_ini_text(self, text, ensure_trailing_newline=True):
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n")

        lines = [line.rstrip() for line in text.split("\n")]
        text = "\n".join(lines)

        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.rstrip("\n")

        if ensure_trailing_newline:
            text += "\n"

        return text

    def apply_connected_state(self):
        self.ini_file_combo.setEnabled(self.ini_file_combo.count() > 0)
        self.refresh_ini_files_button.setEnabled(True)
        self.easy_mode_radio.setEnabled(True)
        self.advanced_mode_radio.setEnabled(True)
        self.save_button.setEnabled(self.ini_file_combo.count() > 0)
        self.backup_button.setEnabled(self.ini_file_combo.count() > 0)
        self.restore_button.setEnabled(True)
        self.defaults_button.setEnabled(self.ini_file_combo.count() > 0)
        self.retention_spin.setEnabled(True)
        self.open_backup_folder_button.setEnabled(True)
        self.retention_label.setStyleSheet("")
        self.set_mister_settings_enabled(self.ini_file_combo.count() > 0)

    def apply_offline_state(self):
        has_sd = bool(self.offline_root_path())
        has_ini = self.ini_file_combo.count() > 0

        self.ini_file_combo.setEnabled(has_sd and has_ini)
        self.refresh_ini_files_button.setEnabled(has_sd)
        self.easy_mode_radio.setEnabled(has_sd and has_ini)
        self.advanced_mode_radio.setEnabled(has_sd and has_ini)
        self.save_button.setEnabled(has_sd and has_ini)
        self.backup_button.setEnabled(has_sd and has_ini)
        self.restore_button.setEnabled(has_sd)
        self.defaults_button.setEnabled(has_sd and has_ini)
        self.retention_spin.setEnabled(True)
        self.open_backup_folder_button.setEnabled(True)
        self.retention_label.setStyleSheet("")

        if has_sd:
            if has_ini:
                if "No MiSTer INI file was found" not in self.notice_label.text():
                    self.set_notice("")
                self.set_mister_settings_enabled(True)
            else:
                self.set_notice("No MiSTer.ini or MiSTer_*.ini files found.")
                self.set_mister_settings_enabled(False)
        else:
            self.set_notice("Select a MiSTer SD card on the Connection tab first.")
            self.set_mister_settings_enabled(False)

    def apply_disconnected_state(self):
        self.ini_file_combo.setEnabled(False)
        self.refresh_ini_files_button.setEnabled(False)
        self.easy_mode_radio.setEnabled(False)
        self.advanced_mode_radio.setEnabled(False)
        self.save_button.setEnabled(False)
        self.backup_button.setEnabled(False)
        self.restore_button.setEnabled(False)
        self.defaults_button.setEnabled(False)
        self.retention_spin.setEnabled(False)
        self.open_backup_folder_button.setEnabled(False)
        self.retention_label.setStyleSheet("")
        self.set_notice("")
        self.cached_font_list = None
        self.pending_font_selection = NOT_SET_VALUE
        self.font_scan_scheduled = False
        self.set_mister_settings_enabled(False)

    def update_connection_state(self, lightweight=True):
        if self.refresh_worker is not None and self.refresh_worker.isRunning():
            return

        if self.is_offline_mode():
            self.apply_offline_state()
            return

        if self.connection.is_connected():
            self.apply_connected_state()
        else:
            self.apply_disconnected_state()

    def refresh_status(self):
        self.refresh_tab_contents()

    def show_refreshing_state(self):
        if self.refresh_worker is not None and self.refresh_worker.isRunning():
            return

        if self.soft_reboot_worker is not None and self.soft_reboot_worker.isRunning():
            return

        if self.is_offline_mode():
            if not self.offline_root_path():
                return
        elif not self.connection.is_connected():
            return

        self.set_notice("Refreshing MiSTer Settings...")
        self.notice_label.setStyleSheet("color: #1e88e5; font-weight: bold;")
        self.refresh_ini_files_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.backup_button.setEnabled(False)
        self.restore_button.setEnabled(False)
        self.defaults_button.setEnabled(False)
        self.set_mister_settings_enabled(False)

    def set_mister_settings_enabled(self, enabled):
        easy_enabled = enabled and self.easy_mode_radio.isChecked()
        advanced_enabled = enabled and self.advanced_mode_radio.isChecked()

        self.easy_hdmi_mode_combo.setEnabled(easy_enabled)
        self.easy_resolution_combo.setEnabled(easy_enabled)
        self.easy_scaling_combo.setEnabled(easy_enabled)
        self.easy_hdmi_audio_combo.setEnabled(easy_enabled)
        self.easy_hdr_combo.setEnabled(easy_enabled)
        self.easy_hdmi_limited_combo.setEnabled(easy_enabled)
        self.easy_analogue_combo.setEnabled(easy_enabled)
        self.easy_logo_combo.setEnabled(easy_enabled)
        self.easy_recents_combo.setEnabled(easy_enabled)
        self.easy_font_combo.setEnabled(easy_enabled)
        self.easy_amigavision_preset_combo.setEnabled(easy_enabled)
        self.easy_menu_crt_preset_combo.setEnabled(easy_enabled)

        self.advanced_text.setReadOnly(not advanced_enabled)

        if enabled:
            self.update_easy_mode_state()

    def refresh_tab_contents(self):
        if self.refresh_worker is not None and self.refresh_worker.isRunning():
            return

        if self.is_offline_mode():
            sd_root = self.get_offline_sd_root()
            if not self.offline_root_path():
                self.apply_offline_state()
                return
            offline_mode = True
        else:
            sd_root = ""
            if not self.connection.is_connected():
                self.apply_disconnected_state()
                return
            offline_mode = False

        self.show_refreshing_state()

        self.refresh_worker = MiSTerSettingsRefreshWorker(
            self.connection,
            offline_mode=offline_mode,
            sd_root=sd_root,
            preferred_filename=self.config_data.get(
                "mister_settings_ini_file", "MiSTer.ini"
            ),
        )
        self.refresh_worker.result.connect(self.on_refresh_worker_result)
        self.refresh_worker.failed.connect(self.on_refresh_worker_failed)
        self.refresh_worker.finished.connect(self.on_refresh_worker_finished)
        self.refresh_worker.start()

    def on_refresh_worker_result(self, result):
        if not isinstance(result, dict):
            return

        files = result.get("files") or []
        selected_filename = self.normalize_ini_filename(result.get("selected_filename"))
        ini_text = result.get("ini_text") or ""
        notice = (result.get("notice") or "").strip()
        ok = bool(result.get("ok"))
        missing_ini = bool(result.get("missing_ini"))

        self.loading_settings = True
        try:
            self.ini_selector_loading = True
            self.ini_file_combo.blockSignals(True)
            self.ini_file_combo.clear()

            for filename in files:
                self.ini_file_combo.addItem(filename)

            if selected_filename and selected_filename in files:
                self.ini_file_combo.setCurrentText(selected_filename)
            elif files:
                self.ini_file_combo.setCurrentIndex(0)

            self.ini_file_combo.blockSignals(False)
            self.ini_selector_loading = False

            if ok and selected_filename:
                self.config_data["mister_settings_ini_file"] = selected_filename
                try:
                    save_config(self.config_data)
                except Exception:
                    pass

                self.cached_font_list = None
                self.pending_font_selection = self.extract_font_selection_from_ini_text(ini_text)
                self.font_scan_scheduled = False

                self.advanced_text.blockSignals(True)
                self.advanced_text.setPlainText(ini_text)
                self.advanced_text.blockSignals(False)
                self.mark_current_ini_clean(ini_text, selected_filename)

                settings = parse_mister_ini(ini_text)
                values = easy_mode_values_from_ini_settings(settings)
                values["font"] = self.extract_font_selection_from_ini_text(ini_text)
                self.apply_easy_mode_values(values)
            else:
                self.advanced_text.blockSignals(True)
                self.advanced_text.setPlainText("")
                self.advanced_text.blockSignals(False)
                self.cached_font_list = None
                self.pending_font_selection = NOT_SET_VALUE
                self.font_scan_scheduled = False
                self.active_ini_filename = ""
                self.loaded_ini_text = ""
        finally:
            self.loading_settings = False

        if notice:
            self.set_notice(notice)
            self.notice_label.setStyleSheet("color: orange;")
        else:
            self.set_notice("")
            self.notice_label.setStyleSheet("color: orange;")

        if self.is_offline_mode():
            self.apply_offline_state()
        else:
            self.apply_connected_state()

        self.update_settings_mode()

        if missing_ini:
            QTimer.singleShot(0, self.prompt_to_create_missing_ini)

    def prompt_to_create_missing_ini(self):
        if self.missing_ini_dialog_active:
            return

        if self.is_offline_mode():
            if not self.offline_root_path():
                return
        elif not self.connection.is_connected():
            return

        self.missing_ini_dialog_active = True
        try:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Question)
            dialog.setWindowTitle("No MiSTer INI File Found")
            dialog.setText("No MiSTer configuration file was found on this device.")
            dialog.setInformativeText(
                "Would you like to create a blank MiSTer.ini, or create one "
                "using the official MiSTer template?"
            )
            template_button = dialog.addButton(
                "Create from Template", QMessageBox.ButtonRole.AcceptRole
            )
            blank_button = dialog.addButton(
                "Create Blank File", QMessageBox.ButtonRole.ActionRole
            )
            dialog.addButton(QMessageBox.StandardButton.Cancel)
            dialog.setDefaultButton(template_button)
            dialog.exec()

            clicked = dialog.clickedButton()
            if clicked is template_button:
                ini_text = self.download_default_mister_ini()
            elif clicked is blank_button:
                ini_text = "[MiSTer]\n"
            else:
                return

            if self.is_offline_mode():
                target = self.offline_root_path() / "MiSTer.ini"
                target.write_text(ini_text, encoding="utf-8")
            else:
                sftp = self.connection.client.open_sftp()
                try:
                    with sftp.open("/media/fat/MiSTer.ini", "w") as handle:
                        handle.write(ini_text)
                finally:
                    sftp.close()

            self.config_data["mister_settings_ini_file"] = "MiSTer.ini"
            try:
                save_config(self.config_data)
            except Exception:
                pass
            self.refresh_tab_contents()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Create MiSTer.ini Failed",
                f"Unable to create MiSTer.ini:\n{e}",
            )
        finally:
            self.missing_ini_dialog_active = False

    def on_refresh_worker_failed(self, detail):
        if self.is_offline_mode():
            self.apply_offline_state()
        else:
            self.apply_connected_state() if self.connection.is_connected() else self.apply_disconnected_state()

        self.set_notice(f"Unable to refresh MiSTer Settings: {str(detail).splitlines()[0]}")
        self.notice_label.setStyleSheet("color: #cc0000; font-weight: bold;")

    def on_refresh_worker_finished(self):
        self.refresh_worker = None

    def _sync_easy_group_width(self):
        if not hasattr(self, "top_cards") or not hasattr(self, "easy_group"):
            return
        width = self.top_cards.width()
        if width > 0:
            self.easy_group.setFixedWidth(width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._sync_easy_group_width)

    def update_settings_mode(self):
        enabled = (
            (self.is_offline_mode() and bool(self.offline_root_path()))
            or self.connection.is_connected()
        ) and self.ini_file_combo.count() > 0

        if self.easy_mode_radio.isChecked():
            self.settings_shell.setMaximumWidth(900)
            self.settings_shell.setMinimumWidth(720)
            self.advanced_text.setMinimumHeight(0)
            self.easy_group.show()
            self.advanced_group.hide()
            QTimer.singleShot(0, self._sync_easy_group_width)
        else:
            self.settings_shell.setMaximumWidth(16777215)
            self.settings_shell.setMinimumWidth(0)
            self.advanced_text.setMinimumHeight(420)
            self.easy_group.hide()
            self.advanced_group.show()

        self.set_mister_settings_enabled(enabled)

    def update_easy_mode_state(self):
        hdmi_mode = self.easy_hdmi_mode_combo.currentText().strip()
        direct_video = hdmi_mode == "Direct Video (CRT / Scaler)"
        enabled = (
            self.connection.is_connected()
            or (self.is_offline_mode() and bool(self.offline_root_path()))
        ) and self.easy_mode_radio.isChecked() and self.ini_file_combo.count() > 0

        self.easy_resolution_combo.setEnabled(not direct_video and enabled)
        self.easy_scaling_combo.setEnabled(not direct_video and enabled)
        self.easy_hdr_combo.setEnabled(not direct_video and enabled)
        self.easy_hdmi_limited_combo.setEnabled(not direct_video and enabled)
        self.easy_logo_combo.setEnabled(not direct_video and enabled)

    def get_current_profile_name(self):
        if self.is_offline_mode():
            return "Offline SD Card"
        return self.main_window.connection_tab.profile_selector.currentText().strip()

    def get_mister_settings_device_name(self):
        if self.is_offline_mode():
            return get_mister_settings_device_name("Offline SD Card", "offline")
        return get_mister_settings_device_name(self.get_current_profile_name(), self.connection.host)

    def get_mister_settings_device_path(self):
        if self.is_offline_mode():
            return get_mister_settings_device_path("Offline SD Card", "offline")
        return get_mister_settings_device_path(self.get_current_profile_name(), self.connection.host)

    def save_mister_settings_retention_setting(self):
        try:
            value = int(self.retention_spin.value())
            save_mister_settings_retention_setting(self.main_window.config_data, value)
            self.config_data["mister_settings_retention"] = value
        except Exception:
            pass

    def open_mister_settings_folder(self):
        try:
            open_mister_settings_folder(self.get_mister_settings_device_path())
        except Exception as e:
            QMessageBox.critical(self, "Open Backup Folder Failed", str(e))

    def set_font_combo_loading(self):
        self.easy_font_combo.blockSignals(True)
        self.easy_font_combo.clear()
        self.easy_font_combo.addItem(NOT_SET_VALUE)
        self.disable_combo_value(self.easy_font_combo, NOT_SET_VALUE)
        self.easy_font_combo.addItem("Scanning fonts...")
        self.easy_font_combo.setCurrentText("Scanning fonts...")
        self.easy_font_combo.setEnabled(False)
        self.easy_font_combo.setStyleSheet("color: #1e88e5; font-weight: bold;")
        self.easy_font_combo.blockSignals(False)

    def populate_font_combo(self, selected_font=NOT_SET_VALUE):
        current = (selected_font or NOT_SET_VALUE).strip()

        if self.cached_font_list is not None:
            self._populate_font_combo_from_list(self.cached_font_list, current)
            return

        self.pending_font_selection = current
        self.set_font_combo_loading()

        if not self.font_scan_scheduled:
            self.font_scan_scheduled = True
            QTimer.singleShot(0, self.start_font_scan)

    def _populate_font_combo_from_list(self, fonts, selected_font=NOT_SET_VALUE):
        current = (selected_font or NOT_SET_VALUE).strip()

        self.easy_font_combo.blockSignals(True)
        self.easy_font_combo.setStyleSheet("")
        self.easy_font_combo.clear()
        self.easy_font_combo.addItem(NOT_SET_VALUE)
        self.disable_combo_value(self.easy_font_combo, NOT_SET_VALUE)
        self.easy_font_combo.addItem("Default")

        for font_name in fonts:
            self.easy_font_combo.addItem(font_name)

        if current != "Default" and self.easy_font_combo.findText(current) == -1:
            self.easy_font_combo.addItem(current)

        self.easy_font_combo.setCurrentText(current if current else NOT_SET_VALUE)
        self.easy_font_combo.setEnabled(
            (
                self.connection.is_connected()
                or (self.is_offline_mode() and bool(self.offline_root_path()))
            )
            and self.easy_mode_radio.isChecked()
            and self.ini_file_combo.count() > 0
        )
        self.easy_font_combo.blockSignals(False)

    def start_font_scan(self):
        if self.font_worker is not None and self.font_worker.isRunning():
            return

        offline_mode = self.is_offline_mode()
        sd_root = self.get_offline_sd_root() if offline_mode else ""

        if offline_mode:
            if not self.offline_root_path():
                self.font_scan_scheduled = False
                self._populate_font_combo_from_list([], NOT_SET_VALUE)
                return
        else:
            if not self.connection.is_connected():
                self.font_scan_scheduled = False
                self._populate_font_combo_from_list([], NOT_SET_VALUE)
                return

        self.font_worker = MiSTerSettingsFontWorker(
            self.connection,
            offline_mode=offline_mode,
            sd_root=sd_root,
        )
        self.font_worker.result.connect(self.on_font_scan_result)
        self.font_worker.failed.connect(self.on_font_scan_failed)
        self.font_worker.finished.connect(self.on_font_scan_finished)
        self.font_worker.start()

    def on_font_scan_result(self, fonts):
        if not isinstance(fonts, list):
            fonts = []

        self.cached_font_list = fonts
        self._populate_font_combo_from_list(fonts, self.pending_font_selection)

    def on_font_scan_failed(self, message):
        self.cached_font_list = []
        self._populate_font_combo_from_list([], self.pending_font_selection)

    def on_font_scan_finished(self):
        self.font_scan_scheduled = False

        if self.font_worker is not None:
            self.font_worker.deleteLater()
            self.font_worker = None

    def extract_font_selection_from_ini_text(self, ini_text):
        if not ini_text:
            return NOT_SET_VALUE

        match = re.search(
            r"(?mi)^(?!\s*;)\s*font\s*=\s*font/([^\r\n/]+\.pf)\s*(?:;.*)?$",
            ini_text
        )
        if match:
            return match.group(1).strip()

        return NOT_SET_VALUE

    def collect_easy_mode_values(self):
        return {
            "hdmi_mode": self.easy_hdmi_mode_combo.currentText().strip(),
            "resolution": self.easy_resolution_combo.currentText().strip(),
            "scaling": self.easy_scaling_combo.currentText().strip(),
            "hdmi_audio": self.easy_hdmi_audio_combo.currentText().strip(),
            "hdr": self.easy_hdr_combo.currentText().strip(),
            "hdmi_limited": self.easy_hdmi_limited_combo.currentText().strip(),
            "analogue": self.easy_analogue_combo.currentText().strip(),
            "logo": self.easy_logo_combo.currentText().strip(),
            "recents": self.easy_recents_combo.currentText().strip(),
            "font": self.easy_font_combo.currentText().strip(),
            "amigavision_preset": self.easy_amigavision_preset_combo.currentText().strip(),
            "menu_crt_preset": self.easy_menu_crt_preset_combo.currentText().strip(),
        }

    def apply_easy_mode_values(self, values):
        self.easy_hdmi_mode_combo.setCurrentText(values.get("hdmi_mode", NOT_SET_VALUE))
        self.set_resolution_combo_value(values.get("resolution", NOT_SET_VALUE))
        self.easy_scaling_combo.setCurrentText(values.get("scaling", NOT_SET_VALUE))
        self.easy_hdmi_audio_combo.setCurrentText(values.get("hdmi_audio", NOT_SET_VALUE))
        self.easy_hdr_combo.setCurrentText(values.get("hdr", NOT_SET_VALUE))
        self.easy_hdmi_limited_combo.setCurrentText(values.get("hdmi_limited", NOT_SET_VALUE))
        self.set_analogue_combo_value(values.get("analogue", NOT_SET_VALUE))
        self.easy_logo_combo.setCurrentText(values.get("logo", NOT_SET_VALUE))
        self.easy_recents_combo.setCurrentText(values.get("recents", NOT_SET_VALUE))
        self.easy_amigavision_preset_combo.setCurrentText(
            values.get("amigavision_preset", "Disabled")
        )
        self.easy_menu_crt_preset_combo.setCurrentText(
            values.get("menu_crt_preset", "Disabled")
        )

        font_value = values.get("font", NOT_SET_VALUE)
        self.populate_font_combo(font_value)

        self.update_easy_mode_state()

    def apply_advanced_to_easy(self):
        text = self.advanced_text.toPlainText()
        settings = parse_mister_ini(text)
        values = easy_mode_values_from_ini_settings(settings)
        values["font"] = self.extract_font_selection_from_ini_text(text)
        self.apply_easy_mode_values(values)

    def load_mister_ini_into_ui(self, silent=True):
        if self.ini_file_combo.count() <= 0:
            return False

        if self.is_offline_mode():
            ini_text, message = self.read_offline_mister_ini()
            if ini_text is None:
                if not silent:
                    QMessageBox.critical(self, "MiSTer INI Error", message)
                return False

            settings = parse_mister_ini(ini_text)
            values = easy_mode_values_from_ini_settings(settings)
            values["font"] = self.extract_font_selection_from_ini_text(ini_text)
            self.apply_easy_mode_values(values)
            return True

        if not self.connection.is_connected():
            return False

        ini_text, message = self.read_remote_mister_ini()
        if ini_text is None:
            if not silent:
                QMessageBox.critical(self, "MiSTer INI Error", message)
            return False

        settings = parse_mister_ini(ini_text)
        values = easy_mode_values_from_ini_settings(settings)
        values["font"] = self.extract_font_selection_from_ini_text(ini_text)
        self.apply_easy_mode_values(values)
        return True

    def load_mister_ini_advanced(self):
        if self.ini_file_combo.count() <= 0:
            return

        if self.is_offline_mode():
            ini_text, _ = self.read_offline_mister_ini()
            if ini_text is None:
                return

            self.advanced_text.blockSignals(True)
            self.advanced_text.setPlainText(
                (ini_text or "").replace("\r\n", "\n").replace("\r", "\n")
            )
            self.advanced_text.blockSignals(False)
            self.mark_current_ini_clean(ini_text)
            return

        if not self.connection.is_connected():
            return

        ini_text, _ = self.read_remote_mister_ini()
        if ini_text is None:
            return

        self.advanced_text.blockSignals(True)
        self.advanced_text.setPlainText(
            (ini_text or "").replace("\r\n", "\n").replace("\r", "\n")
        )
        self.advanced_text.blockSignals(False)
        self.mark_current_ini_clean(ini_text)

    def build_easy_mode_settings(self):
        return build_easy_mode_settings(self.collect_easy_mode_values())

    def create_offline_backup(self):
        ini_filename = self.selected_ini_filename()
        ini_path = self.selected_offline_ini_path()

        if not ini_path or not ini_path.exists():
            return False, f"{ini_filename} was not found on the selected SD card.", ""

        device_path = Path(self.get_mister_settings_device_path())
        device_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_file = device_path / f"{ini_filename}.{timestamp}.bak"

        shutil.copyfile(ini_path, backup_file)

        retention = int(self.main_window.config_data.get("mister_settings_retention", 10))
        prefix = f"{ini_filename}."

        backups = sorted(
            [
                p for p in device_path.glob(f"{ini_filename}.*.bak")
                if p.is_file() and p.name.startswith(prefix)
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for old_backup in backups[retention:]:
            try:
                old_backup.unlink()
            except Exception:
                pass

        return True, "", str(backup_file)

    def backup_mister_settings(self, silent=False):
        ini_filename = self.selected_ini_filename()

        if self.is_offline_mode():
            if not self.offline_root_path():
                if not silent:
                    QMessageBox.critical(self, "Error", "Select a MiSTer SD card first.")
                return False

            try:
                ok, message, backup_file = self.create_offline_backup()
                if not ok:
                    if not silent:
                        QMessageBox.critical(self, "MiSTer INI Error", message)
                    return False

                if not silent:
                    QMessageBox.information(
                        self,
                        "Backup Created",
                        f"{ini_filename} backup created successfully.\n\n{backup_file}"
                    )
                return True
            except Exception as e:
                if not silent:
                    QMessageBox.critical(
                        self,
                        "Backup Failed",
                        f"Unable to create {ini_filename} backup:\n{str(e)}"
                    )
                return False

        if not self.connection.is_connected():
            if not silent:
                QMessageBox.critical(self, "Error", "Connect to a MiSTer first.")
            return False

        device_name = self.get_mister_settings_device_name()
        if not device_name:
            if not silent:
                QMessageBox.critical(self, "Error", "No device name or IP available.")
            return False

        device_path = self.get_mister_settings_device_path()
        retention = self.main_window.config_data.get("mister_settings_retention", 10)

        try:
            ok, message, backup_file = create_mister_settings_backup(
                self.connection,
                device_path,
                retention,
                ini_filename=ini_filename,
            )
            if not ok:
                if not silent:
                    QMessageBox.critical(self, "MiSTer INI Error", message)
                return False

            if not silent:
                QMessageBox.information(
                    self,
                    "Backup Created",
                    f"{ini_filename} backup created successfully.\n\n{backup_file}"
                )
            return True

        except Exception as e:
            if not silent:
                QMessageBox.critical(
                    self,
                    "Backup Failed",
                    f"Unable to create {ini_filename} backup:\n{str(e)}"
                )
            return False

    def save_mister_settings(self):
        if self.is_offline_mode():
            return self.save_mister_settings_offline()

        ini_filename = self.selected_ini_filename()

        if not self.connection.is_connected():
            QMessageBox.critical(self, "Error", "Connect to a MiSTer first.")
            return False

        ok, message = ensure_mister_ini_exists(
            self.connection,
            ini_filename=ini_filename,
            create_if_missing=False,
        )
        if not ok:
            QMessageBox.critical(self, "MiSTer INI Error", message)
            return False

        choice = QMessageBox.question(
            self,
            "Backup Before Apply",
            f"Do you want to create a backup of the current {ini_filename} before applying settings?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes
        )

        if choice == QMessageBox.StandardButton.Cancel:
            return False

        if choice == QMessageBox.StandardButton.Yes:
            backup_ok = self.backup_mister_settings(silent=True)
            if not backup_ok:
                proceed = QMessageBox.question(
                    self,
                    "Backup Failed",
                    "Unable to create backup before applying settings.\n\nContinue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if proceed != QMessageBox.StandardButton.Yes:
                    return False

        try:
            ini_text, message = self.read_remote_mister_ini()
            if ini_text is None:
                QMessageBox.critical(self, "MiSTer INI Error", message)
                return False

            new_ini_text = self.build_new_ini_text(ini_text)
            ok, message = self.write_remote_mister_ini(new_ini_text)

            if not ok:
                QMessageBox.critical(self, "Save Failed", f"Unable to save {ini_filename}:\n{message}")
                return False

            self.loading_settings = True
            try:
                self.load_mister_ini_advanced()
                self.load_mister_ini_into_ui(silent=True)
            finally:
                self.loading_settings = False

            soft_reboot_now = QMessageBox.question(
                self,
                "Settings Applied",
                f"{ini_filename} settings were applied successfully.\n\nA soft reboot is recommended to apply the changes.\n\nSoft reboot now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if soft_reboot_now == QMessageBox.StandardButton.Yes:
                self.soft_reboot_mister()

            return True

        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Unable to save {ini_filename}:\n{str(e)}")
            return False

    def build_new_ini_text(self, ini_text):
        advanced_text = self.advanced_text.toPlainText().replace("\r\n", "\n").replace("\r", "\n")

        if not advanced_text.strip():
            raise ValueError("Advanced editor is empty.")

        if not advanced_text.endswith("\n"):
            advanced_text += "\n"

        return advanced_text

    def save_mister_settings_offline(self):
        ini_filename = self.selected_ini_filename()

        if not self.offline_root_path():
            QMessageBox.critical(self, "Error", "Select a MiSTer SD card first.")
            return False

        ini_text, message = self.read_offline_mister_ini()
        if ini_text is None:
            QMessageBox.critical(self, "MiSTer INI Error", message)
            return False

        choice = QMessageBox.question(
            self,
            "Backup Before Apply",
            f"Do you want to create a backup of the current {ini_filename} before applying settings?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes
        )

        if choice == QMessageBox.StandardButton.Cancel:
            return False

        if choice == QMessageBox.StandardButton.Yes:
            backup_ok = self.backup_mister_settings(silent=True)
            if not backup_ok:
                proceed = QMessageBox.question(
                    self,
                    "Backup Failed",
                    "Unable to create backup before applying settings.\n\nContinue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if proceed != QMessageBox.StandardButton.Yes:
                    return False

        try:
            new_ini_text = self.build_new_ini_text(ini_text)
            ok, message = self.write_offline_mister_ini(new_ini_text)

            if not ok:
                QMessageBox.critical(self, "Save Failed", f"Unable to save {ini_filename}:\n{message}")
                return False

            self.loading_settings = True
            try:
                self.load_mister_ini_advanced()
                self.load_mister_ini_into_ui(silent=True)
            finally:
                self.loading_settings = False

            QMessageBox.information(
                self,
                "Settings Applied",
                f"{ini_filename} was saved to the selected SD card.\n\nIt will apply the next time MiSTer boots."
            )

            return True

        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Unable to save {ini_filename}:\n{str(e)}")
            return False

    def soft_reboot_mister(self):
        if self.is_offline_mode():
            QMessageBox.information(
                self,
                "Offline Mode Active",
                "Soft reboot requires a running MiSTer and is only available in Online Mode."
            )
            return False

        if not self.connection.is_connected():
            QMessageBox.critical(self, "Error", "Connect to a MiSTer first.")
            return False

        if self.soft_reboot_worker and self.soft_reboot_worker.isRunning():
            return False

        self.save_button.setEnabled(False)
        self.defaults_button.setEnabled(False)
        self.restore_button.setEnabled(False)
        self.backup_button.setEnabled(False)

        try:
            self.main_window.set_connection_status("Status: Soft rebooting...")
        except Exception:
            pass

        self.soft_reboot_worker = SoftRebootWorker(self.connection)
        self.soft_reboot_worker.finished_ok.connect(self.on_soft_reboot_finished)
        self.soft_reboot_worker.failed.connect(self.on_soft_reboot_failed)
        self.soft_reboot_worker.finished.connect(self.soft_reboot_worker.deleteLater)
        self.soft_reboot_worker.finished.connect(self.on_soft_reboot_worker_finished)
        self.soft_reboot_worker.start()

        return True

    def on_soft_reboot_worker_finished(self):
        self.soft_reboot_worker = None

    def on_soft_reboot_finished(self):
        self.update_connection_state(lightweight=True)

        try:
            self.main_window.set_connection_status("Status: Connected")
        except Exception:
            pass

    def on_soft_reboot_failed(self, message):
        self.update_connection_state(lightweight=True)

        try:
            self.main_window.set_connection_status("Status: Connected")
        except Exception:
            pass

        QMessageBox.critical(
            self,
            "Soft Reboot Failed",
            f"Unable to soft reboot MiSTer:\n{message}"
        )

    def restore_default_mister_settings(self):
        if self.is_offline_mode():
            return self.restore_default_mister_settings_offline()

        ini_filename = self.selected_ini_filename()

        if not self.connection.is_connected():
            QMessageBox.critical(self, "Error", "Connect to a MiSTer first.")
            return False

        confirm = QMessageBox.question(
            self,
            "Restore Default Settings",
            f"This will download the default MiSTer.ini and replace the current {ini_filename}.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return False

        choice = QMessageBox.question(
            self,
            "Backup Current Settings",
            f"Do you want to create a backup of the current {ini_filename} before restoring defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes
        )

        if choice == QMessageBox.StandardButton.Cancel:
            return False

        if choice == QMessageBox.StandardButton.Yes:
            backup_ok = self.backup_mister_settings(silent=True)
            if not backup_ok:
                proceed = QMessageBox.question(
                    self,
                    "Backup Failed",
                    "Unable to create backup before restoring defaults.\n\nContinue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if proceed != QMessageBox.StandardButton.Yes:
                    return False

        try:
            default_ini_text = self.download_default_mister_ini()
            ok, message = self.write_remote_mister_ini(default_ini_text)

            if not ok:
                QMessageBox.critical(
                    self,
                    "Restore Defaults Failed",
                    f"Unable to restore default settings to {ini_filename}:\n{message}"
                )
                return False

            self.loading_settings = True
            try:
                self.load_mister_ini_advanced()
                self.load_mister_ini_into_ui(silent=True)
            finally:
                self.loading_settings = False

            soft_reboot_now = QMessageBox.question(
                self,
                "Defaults Restored",
                f"Default settings were restored to {ini_filename} successfully.\n\nA soft reboot is recommended to apply the changes.\n\nSoft reboot now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if soft_reboot_now == QMessageBox.StandardButton.Yes:
                self.soft_reboot_mister()

            return True

        except Exception as e:
            QMessageBox.critical(
                self,
                "Restore Defaults Failed",
                f"Unable to download or restore the default MiSTer.ini:\n{str(e)}"
            )
            return False

    def restore_default_mister_settings_offline(self):
        ini_filename = self.selected_ini_filename()

        if not self.offline_root_path():
            QMessageBox.critical(self, "Error", "Select a MiSTer SD card first.")
            return False

        confirm = QMessageBox.question(
            self,
            "Restore Default Settings",
            f"This will download the default MiSTer.ini and replace the current {ini_filename} on the selected SD card.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return False

        choice = QMessageBox.question(
            self,
            "Backup Current Settings",
            f"Do you want to create a backup of the current {ini_filename} before restoring defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes
        )

        if choice == QMessageBox.StandardButton.Cancel:
            return False

        if choice == QMessageBox.StandardButton.Yes:
            backup_ok = self.backup_mister_settings(silent=True)
            if not backup_ok:
                proceed = QMessageBox.question(
                    self,
                    "Backup Failed",
                    "Unable to create backup before restoring defaults.\n\nContinue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if proceed != QMessageBox.StandardButton.Yes:
                    return False

        try:
            default_ini_text = self.download_default_mister_ini()
            ok, message = self.write_offline_mister_ini(default_ini_text)

            if not ok:
                QMessageBox.critical(
                    self,
                    "Restore Defaults Failed",
                    f"Unable to restore default settings to {ini_filename}:\n{message}"
                )
                return False

            self.loading_settings = True
            try:
                self.load_mister_ini_advanced()
                self.load_mister_ini_into_ui(silent=True)
            finally:
                self.loading_settings = False

            QMessageBox.information(
                self,
                "Defaults Restored",
                f"Default settings were restored to {ini_filename} on the selected SD card.\n\nThey will apply the next time MiSTer boots."
            )

            return True

        except Exception as e:
            QMessageBox.critical(
                self,
                "Restore Defaults Failed",
                f"Unable to download or restore the default MiSTer.ini:\n{str(e)}"
            )
            return False

    def restore_mister_settings(self):
        if self.is_offline_mode():
            return self.restore_mister_settings_offline()

        ini_filename = self.selected_ini_filename()

        if not self.connection.is_connected():
            QMessageBox.critical(self, "Error", "Connect to a MiSTer first.")
            return False

        device_name = self.get_mister_settings_device_name()
        if not device_name:
            QMessageBox.critical(self, "Error", "No device name or IP available.")
            return False

        device_path = self.get_mister_settings_device_path()
        backup_files = list_mister_settings_backups(device_path, ini_filename=ini_filename)

        if not backup_files:
            QMessageBox.critical(self, "Error", f"No {ini_filename} backups found for this device.")
            return False

        dialog = RestoreBackupDialog(backup_files, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        selected_backup = dialog.selected_backup()
        if not selected_backup:
            return False

        backup_path = f"{device_path}/{selected_backup}"

        try:
            restore_mister_settings_backup(
                self.connection,
                backup_path,
                ini_filename=ini_filename,
            )

            self.loading_settings = True
            try:
                self.load_mister_ini_advanced()
                self.load_mister_ini_into_ui(silent=True)
            finally:
                self.loading_settings = False

            soft_reboot_now = QMessageBox.question(
                self,
                "Backup Restored",
                f"{ini_filename} backup restored successfully.\n\nA soft reboot is recommended to apply the changes.\n\nSoft reboot now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if soft_reboot_now == QMessageBox.StandardButton.Yes:
                self.soft_reboot_mister()

            return True

        except Exception as e:
            QMessageBox.critical(self, "Restore Failed", f"Unable to restore {ini_filename} backup:\n{str(e)}")
            return False

    def restore_mister_settings_offline(self):
        ini_filename = self.selected_ini_filename()

        if not self.offline_root_path():
            QMessageBox.critical(self, "Error", "Select a MiSTer SD card first.")
            return False

        device_path = self.get_mister_settings_device_path()
        backup_files = list_mister_settings_backups(device_path, ini_filename=ini_filename)

        if not backup_files:
            QMessageBox.critical(self, "Error", f"No {ini_filename} backups found for Offline SD Card.")
            return False

        dialog = RestoreBackupDialog(backup_files, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        selected_backup = dialog.selected_backup()
        if not selected_backup:
            return False

        backup_path = Path(device_path) / selected_backup
        ini_path = self.selected_offline_ini_path()

        if not ini_path:
            QMessageBox.critical(self, "Restore Failed", "Select a valid MiSTer SD card first.")
            return False

        try:
            shutil.copyfile(backup_path, ini_path)

            self.loading_settings = True
            try:
                self.load_mister_ini_advanced()
                self.load_mister_ini_into_ui(silent=True)
            finally:
                self.loading_settings = False

            QMessageBox.information(
                self,
                "Backup Restored",
                f"{ini_filename} backup was restored to the selected SD card.\n\nIt will apply the next time MiSTer boots."
            )

            return True

        except Exception as e:
            QMessageBox.critical(self, "Restore Failed", f"Unable to restore {ini_filename} backup:\n{str(e)}")
            return False

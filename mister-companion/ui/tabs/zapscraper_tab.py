from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.config import load_config, save_config
from core.screenscraper_private import has_dev_credentials
from core.zapscraper import (
    format_screenscraper_quota_info,
    load_scan_cache_systems,
    plan_scrape_actions,
    run_scrape_actions,
    save_scan_cache,
    scan_cache_exists,
    scan_games_folder,
    scan_sd_card,
    test_screenscraper_login,
)
from core.zapscraper_systems import (
    OUTPUT_FORMAT_ZAPAROO_COMPANION,
    get_default_zaparoo_companion_media_names,
    get_image_source_names,
    get_output_format_id,
    get_output_format_names,
    get_region_names,
    get_zaparoo_companion_media_names,
)
from ui.dialogs.zapscraper_gamelist_dialog import ZapScraperGamelistDialog
from ui.dialogs.zapscraper_gamelist_dialog_mode1 import ZapScraperGamelistDialogMode1
from ui.scaling import set_text_button_min_width


SOURCE_SELECTED_SD = "Selected SD Card"
SOURCE_CUSTOM_GAMES_FOLDER = "Custom Games Folder"


class ZapScraperScanWorker(QThread):
    progress = pyqtSignal(str, int, int, int)
    result = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, source_mode, source_path):
        super().__init__()
        self.source_mode = str(source_mode or SOURCE_SELECTED_SD)
        self.source_path = str(source_path or "").strip()

    def run(self):
        try:
            def progress_callback(message, current, total, games_found):
                if self.isInterruptionRequested():
                    return

                self.progress.emit(
                    str(message or "Scanning..."),
                    int(current or 0),
                    int(total or 0),
                    int(games_found or 0),
                )

            def stop_checker():
                return self.isInterruptionRequested()

            if self.source_mode == SOURCE_CUSTOM_GAMES_FOLDER:
                systems = scan_games_folder(
                    self.source_path,
                    progress_callback=progress_callback,
                    stop_checker=stop_checker,
                )
            else:
                systems = scan_sd_card(
                    self.source_path,
                    progress_callback=progress_callback,
                    stop_checker=stop_checker,
                )

            if self.isInterruptionRequested():
                return

            self.result.emit(systems)
        except Exception as e:
            self.error.emit(str(e))


class ZapScraperPlanWorker(QThread):
    result = pyqtSignal(list, int)
    error = pyqtSignal(str)

    def __init__(
        self,
        systems,
        image_source,
        skip_existing_metadata=True,
        skip_existing_images=True,
        update_changed_images=True,
    ):
        super().__init__()
        self.systems = systems or []
        self.image_source = image_source
        self.skip_existing_metadata = bool(skip_existing_metadata)
        self.skip_existing_images = bool(skip_existing_images)
        self.update_changed_images = bool(update_changed_images)

    def run(self):
        try:
            actions = []
            total_games = 0

            for system in self.systems:
                if self.isInterruptionRequested():
                    return

                total_games += int(system.get("count", 0))

                system_actions = plan_scrape_actions(
                    system,
                    self.image_source,
                    skip_existing_metadata=self.skip_existing_metadata,
                    skip_existing_images=self.skip_existing_images,
                    update_changed_images=self.update_changed_images,
                )
                actions.extend(system_actions)

            if self.isInterruptionRequested():
                return

            self.result.emit(actions, total_games)
        except Exception as e:
            self.error.emit(str(e))


class ZapScraperLoginWorker(QThread):
    quota = pyqtSignal(dict)
    result = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, username, password):
        super().__init__()
        self.username = str(username or "").strip()
        self.password = str(password or "")

    def run(self):
        try:
            if self.isInterruptionRequested():
                return

            def quota_callback(quota_info):
                if self.isInterruptionRequested():
                    return

                if isinstance(quota_info, dict):
                    self.quota.emit(quota_info)

            result = test_screenscraper_login(
                self.username,
                self.password,
                quota_callback=quota_callback,
            )

            if self.isInterruptionRequested():
                return

            self.result.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ZapScraperScrapeWorker(QThread):
    progress = pyqtSignal(int, int, str)
    log = pyqtSignal(str)
    quota = pyqtSignal(dict)
    result = pyqtSignal(int, int)
    error = pyqtSignal(str)

    def __init__(
        self,
        actions,
        username,
        password,
        output_format,
        image_source,
        selected_region,
        skip_existing_metadata=True,
        zaparoo_media_source_names=None,
    ):
        super().__init__()
        self.actions = actions or []
        self.username = str(username or "").strip()
        self.password = str(password or "")
        self.output_format = str(output_format or "")
        self.image_source = str(image_source or "")
        self.selected_region = str(selected_region or "Auto")
        self.skip_existing_metadata = bool(skip_existing_metadata)
        self.zaparoo_media_source_names = list(zaparoo_media_source_names or [])
        self.completed = 0

    def run(self):
        try:
            total = len(self.actions)

            def progress_callback(index, total_count, rom_filename):
                self.completed = int(index)
                self.progress.emit(int(index), int(total_count), str(rom_filename or ""))

            def log_callback(message):
                self.log.emit(str(message))

            def quota_callback(quota_info):
                if self.isInterruptionRequested():
                    return

                if isinstance(quota_info, dict):
                    self.quota.emit(quota_info)

            def stop_checker():
                return self.isInterruptionRequested()

            run_scrape_actions(
                self.actions,
                username=self.username,
                password=self.password,
                output_format=self.output_format,
                image_source_name=self.image_source,
                selected_region=self.selected_region,
                skip_existing_metadata=self.skip_existing_metadata,
                zaparoo_media_source_names=self.zaparoo_media_source_names,
                progress_callback=progress_callback,
                log_callback=log_callback,
                quota_callback=quota_callback,
                stop_checker=stop_checker,
            )

            self.result.emit(int(self.completed), int(total))
        except Exception as e:
            self.error.emit(str(e))


class ZapScraperTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.scan_worker = None
        self.plan_worker = None
        self.login_worker = None
        self.scrape_worker = None
        self.systems = []
        self.planned_actions = []
        self.logged_in = False
        self.account_name = ""
        self.quota_info = {}
        self.custom_games_folder = ""
        self.last_scan_log_message = ""
        self._last_cache_source_identity = None
        self._loading_settings = False
        self._build_ui()
        self.load_settings()
        self.update_source_ui()
        self.update_account_ui()
        self.sync_scan_cache_for_source(force=True)
        self.update_connection_state(lightweight=True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        title = QLabel("Systems")
        title.setObjectName("SectionTitle")
        left_layout.addWidget(title)

        self.systems_list = QListWidget()
        self.systems_list.currentRowChanged.connect(lambda *_: self.update_connection_state(lightweight=True))
        left_layout.addWidget(self.systems_list, 1)

        selection_row = QHBoxLayout()
        selection_row.setSpacing(6)
        self.select_all_button = QPushButton("Select All")
        self.clear_selection_button = QPushButton("Clear")
        self.review_gamelist_button = QPushButton("Review Gamelist")
        self.review_gamelist_button.setEnabled(False)
        self.select_all_button.clicked.connect(self.select_all_systems)
        self.clear_selection_button.clicked.connect(self.clear_system_selection)
        self.review_gamelist_button.clicked.connect(self.review_selected_gamelist)
        selection_row.addWidget(self.select_all_button)
        selection_row.addWidget(self.clear_selection_button)
        selection_row.addWidget(self.review_gamelist_button)
        left_layout.addLayout(selection_row)

        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        header = QLabel("ZapScraper")
        header.setObjectName("PageTitle")
        right_layout.addWidget(header)

        account_group = QGroupBox("ScreenScraper Account")
        account_layout = QVBoxLayout(account_group)
        account_layout.setContentsMargins(12, 10, 12, 10)
        account_layout.setSpacing(6)

        self.login_widget = QWidget()
        login_layout = QHBoxLayout(self.login_widget)
        login_layout.setContentsMargins(0, 0, 0, 0)
        login_layout.setSpacing(8)

        username_col = QVBoxLayout()
        username_col.setSpacing(3)
        username_col.addWidget(QLabel("Username"))
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("ScreenScraper username")
        username_col.addWidget(self.username_edit)
        login_layout.addLayout(username_col, 1)

        password_col = QVBoxLayout()
        password_col.setSpacing(3)
        password_col.addWidget(QLabel("Password"))
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("ScreenScraper password")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        password_col.addWidget(self.password_edit)
        login_layout.addLayout(password_col, 1)

        self.login_button = QPushButton("Login")
        self.login_button.clicked.connect(self.test_login)
        set_text_button_min_width(self.login_button, 110)
        login_layout.addWidget(self.login_button)

        self.logged_in_widget = QWidget()
        logged_in_layout = QHBoxLayout(self.logged_in_widget)
        logged_in_layout.setContentsMargins(0, 0, 0, 0)
        logged_in_layout.setSpacing(8)

        self.logged_in_label = QLabel("Logged in")
        self.logged_in_label.setWordWrap(True)
        self.logout_button = QPushButton("Logout")
        self.logout_button.clicked.connect(self.logout)
        set_text_button_min_width(self.logout_button, 90)

        logged_in_layout.addWidget(self.logged_in_label, 1)
        logged_in_layout.addWidget(self.logout_button)

        self.account_status_label = QLabel("")
        self.account_status_label.setWordWrap(True)

        self.quota_label = QLabel("Quota: not reported yet.")
        self.quota_label.setWordWrap(True)

        account_layout.addWidget(self.login_widget)
        account_layout.addWidget(self.logged_in_widget)
        account_layout.addWidget(self.account_status_label)
        account_layout.addWidget(self.quota_label)

        right_layout.addWidget(account_group)

        source_group = QGroupBox("Source")
        source_layout = QVBoxLayout(source_group)
        source_layout.setContentsMargins(12, 10, 12, 10)
        source_layout.setSpacing(6)

        source_row = QHBoxLayout()
        source_row.setSpacing(8)

        source_col = QVBoxLayout()
        source_col.setSpacing(3)
        source_col.addWidget(QLabel("Game Source"))
        self.source_combo = QComboBox()
        self.source_combo.addItems([SOURCE_SELECTED_SD, SOURCE_CUSTOM_GAMES_FOLDER])
        self.source_combo.currentIndexChanged.connect(self.on_source_mode_changed)
        source_col.addWidget(self.source_combo)
        source_row.addLayout(source_col, 1)

        browse_col = QVBoxLayout()
        browse_col.setSpacing(3)
        browse_col.addWidget(QLabel("Custom Folder"))
        self.browse_custom_folder_button = QPushButton("Browse")
        self.browse_custom_folder_button.clicked.connect(self.browse_custom_games_folder)
        set_text_button_min_width(self.browse_custom_folder_button, 90)
        browse_col.addWidget(self.browse_custom_folder_button)
        source_row.addLayout(browse_col, 0)

        source_layout.addLayout(source_row)

        self.source_location_label = QLabel("Location: Not selected")
        self.source_location_label.setWordWrap(True)
        source_layout.addWidget(self.source_location_label)

        right_layout.addWidget(source_group)

        options_group = QGroupBox("Scraper Options")
        options_layout = QVBoxLayout(options_group)
        options_layout.setContentsMargins(12, 10, 12, 10)
        options_layout.setSpacing(8)

        top_options_row = QHBoxLayout()
        top_options_row.setSpacing(8)

        output_format_col = QVBoxLayout()
        output_format_col.setSpacing(3)
        output_format_col.addWidget(QLabel("Output Format"))
        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems(get_output_format_names())
        self.output_format_combo.currentIndexChanged.connect(self.on_output_format_changed)
        output_format_col.addWidget(self.output_format_combo)
        top_options_row.addLayout(output_format_col, 2)

        self.mode1_region_widget = QWidget()
        mode1_region_layout = QVBoxLayout(self.mode1_region_widget)
        mode1_region_layout.setContentsMargins(0, 0, 0, 0)
        mode1_region_layout.setSpacing(3)
        self.region_priority_label = QLabel("Region Priority")
        mode1_region_layout.addWidget(self.region_priority_label)
        self.region_priority_combo = QComboBox()
        self.region_priority_combo.addItems(["USA", "Japan", "Europe"])
        mode1_region_layout.addWidget(self.region_priority_combo)
        top_options_row.addWidget(self.mode1_region_widget, 1)

        options_layout.addLayout(top_options_row)

        self.mode2_options_widget = QWidget()
        mode2_layout = QVBoxLayout(self.mode2_options_widget)
        mode2_layout.setContentsMargins(0, 0, 0, 0)
        mode2_layout.setSpacing(6)

        mode2_options_row = QHBoxLayout()
        mode2_options_row.setSpacing(8)

        image_col = QVBoxLayout()
        image_col.setSpacing(3)
        self.image_source_label = QLabel("Image Source")
        image_col.addWidget(self.image_source_label)
        self.image_source_combo = QComboBox()
        self.image_source_combo.addItems(get_image_source_names())
        image_col.addWidget(self.image_source_combo)
        mode2_options_row.addLayout(image_col, 1)

        region_col = QVBoxLayout()
        region_col.setSpacing(3)
        self.region_label = QLabel("Region")
        region_col.addWidget(self.region_label)
        self.region_combo = QComboBox()
        self.region_combo.addItems(get_region_names())
        region_col.addWidget(self.region_combo)
        mode2_options_row.addLayout(region_col, 1)

        mode2_layout.addLayout(mode2_options_row)
        options_layout.addWidget(self.mode2_options_widget)

        self.mode1_options_widget = QWidget()
        mode1_layout = QVBoxLayout(self.mode1_options_widget)
        mode1_layout.setContentsMargins(0, 0, 0, 0)
        mode1_layout.setSpacing(6)

        media_title = QLabel("Images to Scrape")
        media_title.setObjectName("SectionTitle")
        mode1_layout.addWidget(media_title)

        self.zaparoo_media_checkboxes = {}
        media_names = get_zaparoo_companion_media_names()
        default_media_names = set(get_default_zaparoo_companion_media_names())

        media_grid = QGridLayout()
        media_grid.setContentsMargins(0, 0, 0, 0)
        media_grid.setHorizontalSpacing(14)
        media_grid.setVerticalSpacing(4)

        columns = 3
        for index, media_name in enumerate(media_names):
            checkbox = QCheckBox(media_name)
            checkbox.setChecked(media_name in default_media_names)
            checkbox.stateChanged.connect(lambda *_: self.save_settings())
            self.zaparoo_media_checkboxes[media_name] = checkbox
            media_grid.addWidget(checkbox, index // columns, index % columns)

        mode1_layout.addLayout(media_grid)
        options_layout.addWidget(self.mode1_options_widget)

        advanced_row = QHBoxLayout()
        advanced_row.setSpacing(14)
        self.skip_metadata_checkbox = QCheckBox("Skip existing metadata")
        self.skip_metadata_checkbox.setChecked(True)
        self.skip_images_checkbox = QCheckBox("Skip existing images")
        self.skip_images_checkbox.setChecked(True)
        advanced_row.addWidget(self.skip_metadata_checkbox)
        advanced_row.addWidget(self.skip_images_checkbox)
        advanced_row.addStretch()
        options_layout.addLayout(advanced_row)

        right_layout.addWidget(options_group)

        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout(actions_group)
        actions_layout.setContentsMargins(12, 10, 12, 10)
        actions_layout.setSpacing(6)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.scan_button = QPushButton("Scan")
        self.scrape_button = QPushButton("Scrape Selected")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)

        for button in (self.scan_button, self.scrape_button, self.stop_button):
            set_text_button_min_width(button, 120)

        self.scan_button.clicked.connect(self.scan_source)
        self.scrape_button.clicked.connect(self.prepare_scrape)
        self.stop_button.clicked.connect(self.stop_current_worker)

        action_row.addWidget(self.scan_button)
        action_row.addWidget(self.scrape_button)
        action_row.addWidget(self.stop_button)
        actions_layout.addLayout(action_row)

        self.current_task_label = QLabel("Ready")
        self.current_task_label.setWordWrap(True)
        actions_layout.addWidget(self.current_task_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        actions_layout.addWidget(self.progress_bar)

        right_layout.addWidget(actions_group)
        right_layout.addStretch()

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(110)
        self.output.setMaximumHeight(170)
        layout.addWidget(self.output)

    def load_settings(self):
        self._loading_settings = True

        try:
            config = load_config()
            scraper_config = config.get("zapscraper", {})

            if not isinstance(scraper_config, dict):
                scraper_config = {}

            self.username_edit.setText(str(scraper_config.get("username", "")))
            self.password_edit.setText(str(scraper_config.get("password", "")))
            self.logged_in = bool(scraper_config.get("logged_in", False))
            self.account_name = str(
                scraper_config.get("account_name")
                or scraper_config.get("username")
                or ""
            ).strip()

            self.custom_games_folder = str(
                scraper_config.get("custom_games_folder", "")
            ).strip()

            source_mode = str(scraper_config.get("source_mode", SOURCE_SELECTED_SD))
            if source_mode not in {SOURCE_SELECTED_SD, SOURCE_CUSTOM_GAMES_FOLDER}:
                source_mode = SOURCE_SELECTED_SD

            source_index = self.source_combo.findText(source_mode)
            if source_index >= 0:
                self.source_combo.setCurrentIndex(source_index)

            output_format = str(scraper_config.get("output_format", "Zaparoo Companion"))
            output_format_index = self.output_format_combo.findText(output_format)
            if output_format_index >= 0:
                self.output_format_combo.setCurrentIndex(output_format_index)
            elif self.output_format_combo.count() > 0:
                self.output_format_combo.setCurrentIndex(0)

            image_source = str(scraper_config.get("image_source", "2D Boxart"))
            region = str(scraper_config.get("region", "Auto"))
            region_priority = str(scraper_config.get("region_priority") or "")
            zaparoo_media_sources = scraper_config.get("zaparoo_media_sources")

            image_index = self.image_source_combo.findText(image_source)
            if image_index >= 0:
                self.image_source_combo.setCurrentIndex(image_index)

            region_index = self.region_combo.findText(region)
            if region_index >= 0:
                self.region_combo.setCurrentIndex(region_index)

            if not region_priority or region_priority == "Auto":
                region_priority = region if region != "Auto" else "USA"

            region_priority_index = self.region_priority_combo.findText(region_priority)
            if region_priority_index >= 0:
                self.region_priority_combo.setCurrentIndex(region_priority_index)
            elif self.region_priority_combo.count() > 0:
                self.region_priority_combo.setCurrentIndex(0)

            if not isinstance(zaparoo_media_sources, list):
                zaparoo_media_sources = get_default_zaparoo_companion_media_names()

            selected_media_sources = {
                str(item or "").strip()
                for item in zaparoo_media_sources
                if str(item or "").strip()
            }

            if not selected_media_sources:
                selected_media_sources = set(get_default_zaparoo_companion_media_names())

            for media_name, checkbox in self.zaparoo_media_checkboxes.items():
                checkbox.setChecked(media_name in selected_media_sources)

            self.skip_metadata_checkbox.setChecked(
                bool(scraper_config.get("skip_existing_metadata", True))
            )
            self.skip_images_checkbox.setChecked(
                bool(scraper_config.get("skip_existing_images", True))
            )
        finally:
            self._loading_settings = False

        self.update_output_format_ui()

    def save_settings(self):
        if getattr(self, "_loading_settings", False):
            return

        config = load_config()
        config["zapscraper"] = {
            "source_mode": self.source_combo.currentText(),
            "custom_games_folder": getattr(self, "custom_games_folder", ""),
            "username": self.username_edit.text().strip(),
            "password": self.password_edit.text(),
            "logged_in": bool(self.logged_in),
            "account_name": self.account_name,
            "output_format": self.output_format_combo.currentText(),
            "image_source": self.image_source_combo.currentText(),
            "region": self.region_combo.currentText(),
            "region_priority": self.region_priority_combo.currentText(),
            "zaparoo_media_sources": self._active_zaparoo_media_sources(),
            "skip_existing_metadata": self.skip_metadata_checkbox.isChecked(),
            "skip_existing_images": self.skip_images_checkbox.isChecked(),
        }
        save_config(config)
        self.update_account_status()

    def update_quota_info(self, quota_info):
        if not isinstance(quota_info, dict) or not quota_info:
            return

        self.quota_info = dict(quota_info)
        self.update_quota_label()

    def update_quota_label(self):
        if not getattr(self, "logged_in", False):
            if hasattr(self, "quota_label"):
                self.quota_label.setText("")
            return

        message = format_screenscraper_quota_info(getattr(self, "quota_info", {}) or {})

        if not message or "not reported" in message.lower():
            message = "Quota: not reported by ScreenScraper yet."
        elif not message.lower().startswith("quota"):
            message = f"Quota: {message}"

        self.quota_label.setText(message)

    def update_account_status(self):
        if not has_dev_credentials():
            self.account_status_label.setText(
                "Developer credentials are missing in this build. Official release builds should include them."
            )
            return

        if self.login_worker is not None and self.login_worker.isRunning():
            self.account_status_label.setText("Testing ScreenScraper login...")
            return

        if self.logged_in:
            self.account_status_label.setText("ScreenScraper account is ready.")
            return

        if not self.username_edit.text().strip() or not self.password_edit.text():
            self.account_status_label.setText("ScreenScraper account is not configured.")
            return

        self.account_status_label.setText("Enter your credentials and press Login.")

    def update_account_ui(self):
        name = self.account_name or self.username_edit.text().strip() or "ScreenScraper"

        self.login_widget.setVisible(not self.logged_in)
        self.logged_in_widget.setVisible(self.logged_in)
        self.quota_label.setVisible(self.logged_in)
        self.logged_in_label.setText(f"Logged in as {name}")

        self.update_quota_label()
        self.update_account_status()

    def test_login(self):
        if self.login_worker is not None and self.login_worker.isRunning():
            return

        if not has_dev_credentials():
            QMessageBox.warning(
                self,
                "ZapScraper",
                "ScreenScraper developer credentials are missing in this build.",
            )
            return

        username = self.username_edit.text().strip()
        password = self.password_edit.text()

        if not username or not password:
            QMessageBox.information(
                self,
                "ZapScraper",
                "Enter your ScreenScraper username and password first.",
            )
            return

        self.logged_in = False
        self.account_name = ""
        self.quota_info = {}
        self.update_quota_label()
        self.save_settings()

        self.current_task_label.setText("Testing ScreenScraper login...")
        self.account_status_label.setText("Testing ScreenScraper login...")
        self.append_output("Testing ScreenScraper login...")
        self.set_busy_state(True)

        self.login_worker = ZapScraperLoginWorker(username, password)
        self.login_worker.quota.connect(self.update_quota_info)
        self.login_worker.result.connect(self.on_login_test_finished)
        self.login_worker.error.connect(self.on_login_test_error)
        self.login_worker.finished.connect(self.on_login_worker_finished)
        self.login_worker.start()

    def on_login_test_finished(self, result):
        message = result.get("message") if isinstance(result, dict) else "Login OK."
        user = result.get("user") if isinstance(result, dict) else {}

        account_name = (
            user.get("pseudo")
            or user.get("ssid")
            or user.get("username")
            or user.get("nom")
            or self.username_edit.text().strip()
        )

        self.logged_in = True
        self.account_name = str(account_name or self.username_edit.text().strip()).strip()

        quota_info = result.get("quota") if isinstance(result, dict) else {}
        if isinstance(quota_info, dict) and quota_info:
            self.update_quota_info(quota_info)

        self.save_settings()
        self.update_account_ui()

        self.current_task_label.setText("ScreenScraper login OK.")
        self.append_output(message)

    def on_login_test_error(self, message):
        self.logged_in = False
        self.account_name = ""
        self.quota_info = {}
        self.update_account_ui()
        self.account_status_label.setText("ScreenScraper login failed.")
        self.current_task_label.setText("ScreenScraper login failed.")
        self.append_output(f"ScreenScraper login failed: {message}")
        QMessageBox.warning(self, "ZapScraper", f"ScreenScraper login failed.\n\n{message}")

    def on_login_worker_finished(self):
        self.login_worker = None
        self.set_busy_state(False)
        self.update_connection_state(lightweight=True)

    def logout(self):
        self.logged_in = False
        self.account_name = ""
        self.quota_info = {}
        self.username_edit.clear()
        self.password_edit.clear()
        self.save_settings()
        self.update_account_ui()
        self.append_output("Logged out from ScreenScraper.")

    def on_source_mode_changed(self):
        self.systems_list.clear()
        self.systems = []
        self.planned_actions = []
        self._last_cache_source_identity = None
        self.update_source_ui()

        if not getattr(self, "_loading_settings", False):
            self.save_settings()
            self.sync_scan_cache_for_source(force=True)

        self.update_connection_state(lightweight=True)

    def on_output_format_changed(self):
        if getattr(self, "_loading_settings", False):
            return

        self.update_output_format_ui()
        self.save_settings()
        self.update_connection_state(lightweight=True)

    def update_source_ui(self):
        source_mode = self.source_combo.currentText()
        custom_mode = source_mode == SOURCE_CUSTOM_GAMES_FOLDER
        sd_root = self._sd_root()
        custom_folder = getattr(self, "custom_games_folder", "")

        self.browse_custom_folder_button.setEnabled(custom_mode and not self._is_busy())

        if custom_mode:
            if custom_folder:
                self.source_location_label.setText(f"Location: {custom_folder}")
            else:
                self.source_location_label.setText(
                    "Location: Choose a games folder from your PC, NAS, USB drive, or mounted network share."
                )
            return

        if sd_root:
            self.source_location_label.setText(f"Location: {Path(sd_root) / 'games'}")
        else:
            self.source_location_label.setText("Location: No SD card selected.")

    def browse_custom_games_folder(self):
        start_dir = getattr(self, "custom_games_folder", "") or str(Path.home())

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Games Folder",
            start_dir,
        )

        if not folder:
            return

        self.custom_games_folder = folder
        self.systems_list.clear()
        self.systems = []
        self.planned_actions = []
        self._last_cache_source_identity = None
        self.save_settings()
        self.update_source_ui()
        self.sync_scan_cache_for_source(force=True)
        self.update_connection_state(lightweight=True)
        self.append_output(f"Custom games folder selected: {folder}")

    def _active_output_format(self) -> str:
        return self.output_format_combo.currentText()

    def _is_zaparoo_companion_mode(self) -> bool:
        return get_output_format_id(self._active_output_format()) == OUTPUT_FORMAT_ZAPAROO_COMPANION

    def _active_region(self) -> str:
        if self._is_zaparoo_companion_mode():
            return self.region_priority_combo.currentText()
        return self.region_combo.currentText()

    def _active_zaparoo_media_sources(self) -> list[str]:
        selected = []

        for media_name, checkbox in self.zaparoo_media_checkboxes.items():
            if checkbox.isChecked():
                selected.append(media_name)

        return selected or get_default_zaparoo_companion_media_names()

    def update_output_format_ui(self):
        is_mode1 = self._is_zaparoo_companion_mode()

        self.mode2_options_widget.setVisible(not is_mode1)
        self.mode1_options_widget.setVisible(is_mode1)
        self.mode1_region_widget.setVisible(is_mode1)

        if is_mode1:
            self.skip_images_checkbox.setText("Skip existing media")
        else:
            self.skip_images_checkbox.setText("Skip existing images")

    def _active_source_mode(self) -> str:
        return self.source_combo.currentText()

    def _active_source_path(self) -> str:
        if self._active_source_mode() == SOURCE_CUSTOM_GAMES_FOLDER:
            return str(getattr(self, "custom_games_folder", "") or "").strip()

        return self._sd_root()

    def _active_games_location_text(self) -> str:
        if self._active_source_mode() == SOURCE_CUSTOM_GAMES_FOLDER:
            return self._active_source_path()

        source_path = self._active_source_path()
        if source_path:
            return str(Path(source_path) / "games")
        return ""

    def _has_usable_source(self) -> bool:
        return bool(self._is_offline_mode() and self._active_source_path())

    def _scan_cache_identity(self):
        source_path = self._active_source_path()
        if not source_path:
            return None
        return (self._active_source_mode(), source_path)

    def update_scan_button_text(self):
        source_path = self._active_source_path()

        if not source_path:
            self.scan_button.setText("Scan")
            return

        try:
            has_cache = scan_cache_exists(
                self._active_source_mode(),
                source_path,
            )
        except Exception:
            has_cache = False

        self.scan_button.setText("Re-scan" if has_cache else "Scan")

    def populate_systems_list(self, systems):
        self.systems = systems or []
        self.systems_list.clear()

        for system in self.systems:
            count = int(system.get("count", 0))
            text = f'{system.get("label", system.get("folder", "Unknown"))}    {count} games'
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, system)
            self.systems_list.addItem(item)

        if self.systems_list.count() > 0:
            self.systems_list.setCurrentRow(0)

    def clear_cached_system_view(self):
        self.systems_list.clear()
        self.systems = []
        self.planned_actions = []
        self.update_scan_button_text()

    def sync_scan_cache_for_source(self, force=False):
        if getattr(self, "_loading_settings", False):
            return

        if self._is_busy():
            return

        identity = self._scan_cache_identity()

        if not identity:
            if force or self._last_cache_source_identity is not None:
                self._last_cache_source_identity = None
                self.clear_cached_system_view()
                self.current_task_label.setText("Ready")
            self.update_scan_button_text()
            return

        if not force and identity == self._last_cache_source_identity:
            self.update_scan_button_text()
            return

        self._last_cache_source_identity = identity
        source_mode, source_path = identity

        try:
            has_cache = scan_cache_exists(source_mode, source_path)
        except Exception:
            has_cache = False

        if not has_cache:
            self.clear_cached_system_view()
            self.current_task_label.setText("Ready")
            self.append_output(
                f"No scan cache found for {self._active_games_location_text()}. Press Scan to scan this location."
            )
            self.update_scan_button_text()
            return

        try:
            systems = load_scan_cache_systems(source_mode, source_path)
        except Exception as e:
            self.clear_cached_system_view()
            self.current_task_label.setText("Scan cache could not be loaded.")
            self.append_output(f"Scan cache could not be loaded: {e}")
            self.update_scan_button_text()
            return

        self.populate_systems_list(systems)
        self.planned_actions = []

        total_games = sum(int(system.get("count", 0)) for system in self.systems)

        self.current_task_label.setText(
            f"Loaded cached scan. Found {len(self.systems)} supported systems with {total_games} games."
        )
        self.append_output(
            f"Loaded cached scan for {self._active_games_location_text()}. Use Re-scan after adding or removing games."
        )
        self.update_scan_button_text()

    def scan_source(self):
        source_path = self._active_source_path()

        if not source_path:
            if self._active_source_mode() == SOURCE_CUSTOM_GAMES_FOLDER:
                QMessageBox.information(
                    self,
                    "ZapScraper",
                    "Choose a custom games folder before scanning.",
                )
            else:
                QMessageBox.information(
                    self,
                    "ZapScraper",
                    "Select an SD card in Offline Mode or choose Custom Games Folder.",
                )
            return

        self.save_settings()

        self.systems_list.clear()
        self.systems = []
        self.planned_actions = []
        self.progress_bar.setRange(0, 0)
        self.current_task_label.setText("Scanning... This can take a while on large custom or NAS folders.")
        self.set_busy_state(True)

        location = self._active_games_location_text()
        self.append_output(f"Scanning {location} for supported console and handheld systems...")

        self.last_scan_log_message = ""
        self.scan_worker = ZapScraperScanWorker(self._active_source_mode(), source_path)
        self.scan_worker.progress.connect(self.on_scan_progress)
        self.scan_worker.result.connect(self.on_scan_finished)
        self.scan_worker.error.connect(self.on_scan_error)
        self.scan_worker.finished.connect(self.on_scan_worker_finished)
        self.scan_worker.start()

    def on_scan_progress(self, message, current, total, games_found):
        total = int(total or 0)
        current = int(current or 0)
        games_found = int(games_found or 0)
        message = str(message or "Scanning...")

        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(max(0, min(current, total)))
        else:
            self.progress_bar.setRange(0, 0)

        self.current_task_label.setText(f"{message} {games_found} games found.")

        should_log = (
            message.startswith("Checking ")
            or message.startswith("Found ")
            or message == "Scan complete."
        )

        if should_log and message != self.last_scan_log_message:
            self.last_scan_log_message = message
            self.append_output(f"{message} {games_found} games found.")

    def on_scan_finished(self, systems):
        self.systems = systems or []

        if self._active_source_path():
            try:
                save_scan_cache(
                    self._active_source_mode(),
                    self._active_source_path(),
                    self.systems,
                )
            except Exception as e:
                self.append_output(f"Scan cache could not be saved: {e}")

        self.populate_systems_list(self.systems)
        self.update_scan_button_text()

        total_games = sum(int(system.get("count", 0)) for system in self.systems)

        if self.systems:
            self.current_task_label.setText(
                f"Found {len(self.systems)} supported systems with {total_games} games."
            )
            self.append_output(
                f"Scan complete. Found {len(self.systems)} supported systems with {total_games} games."
            )
        else:
            self.current_task_label.setText("No supported console or handheld systems found.")
            self.append_output("No supported console or handheld systems found in the selected games folder.")

    def on_scan_error(self, message):
        self.current_task_label.setText("Scan failed.")
        self.append_output(f"Scan failed: {message}")
        QMessageBox.warning(self, "ZapScraper", message)

    def on_scan_worker_finished(self):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.scan_worker = None
        self.update_scan_button_text()
        self.set_busy_state(False)
        self.update_connection_state(lightweight=True)

    def prepare_scrape(self):
        selected = self.selected_systems()

        if not selected:
            QMessageBox.information(
                self,
                "ZapScraper",
                "Select at least one system to scrape.",
            )
            return

        if not has_dev_credentials():
            QMessageBox.warning(
                self,
                "ZapScraper",
                "ScreenScraper developer credentials are missing in this build.",
            )
            return

        if not self.logged_in:
            QMessageBox.information(
                self,
                "ZapScraper",
                "Login with your ScreenScraper account before scraping.",
            )
            return

        if not self.username_edit.text().strip() or not self.password_edit.text():
            QMessageBox.information(
                self,
                "ZapScraper",
                "ScreenScraper username and password are missing. Please login again.",
            )
            self.logout()
            return

        self.save_settings()

        self.planned_actions = []
        self.progress_bar.setRange(0, 0)
        self.current_task_label.setText("Preparing scrape plan...")
        self.set_busy_state(True)
        self.append_output("Checking existing gamelist.xml files and local artwork...")

        self.plan_worker = ZapScraperPlanWorker(
            selected,
            self.image_source_combo.currentText(),
            skip_existing_metadata=self.skip_metadata_checkbox.isChecked(),
            skip_existing_images=self.skip_images_checkbox.isChecked(),
            update_changed_images=True,
        )
        self.plan_worker.result.connect(self.on_plan_finished)
        self.plan_worker.error.connect(self.on_plan_error)
        self.plan_worker.finished.connect(self.on_plan_worker_finished)
        self.plan_worker.start()

    def on_plan_finished(self, actions, total_games):
        self.planned_actions = actions or []
        total_actions = len(self.planned_actions)

        self.progress_bar.setRange(0, max(1, total_actions))
        self.progress_bar.setValue(0)

        if total_actions == 0:
            self.current_task_label.setText(
                f"Nothing to scrape. {total_games} games already have metadata and the selected image source."
            )
            self.append_output(
                f"Nothing to scrape. Checked {total_games} games and no updates are needed."
            )
            return

        metadata_count = sum(1 for action in self.planned_actions if action.get("needs_metadata"))
        image_count = sum(1 for action in self.planned_actions if action.get("needs_image"))

        self.current_task_label.setText(
            f"Starting scrape for {total_actions} games. Metadata: {metadata_count}, images: {image_count}."
        )
        self.append_output(
            f"Scrape plan ready: {total_actions} games need work. Metadata: {metadata_count}, images: {image_count}."
        )

        self.start_scrape()

    def on_plan_error(self, message):
        self.current_task_label.setText("Scrape planning failed.")
        self.append_output(f"Scrape planning failed: {message}")
        QMessageBox.warning(self, "ZapScraper", message)

    def on_plan_worker_finished(self):
        self.plan_worker = None

        if self.scrape_worker is None:
            self.set_busy_state(False)
            self.update_connection_state(lightweight=True)

    def start_scrape(self):
        if not self.planned_actions:
            self.set_busy_state(False)
            self.update_connection_state(lightweight=True)
            return

        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        output_format = self._active_output_format()
        image_source = self.image_source_combo.currentText()
        region = self._active_region()
        zaparoo_media_sources = self._active_zaparoo_media_sources()

        self.progress_bar.setRange(0, max(1, len(self.planned_actions)))
        self.progress_bar.setValue(0)
        self.current_task_label.setText("Scraping...")

        if self._is_zaparoo_companion_mode():
            self.append_output(
                f"Starting ScreenScraper scrape using {output_format} output, {region} region priority, "
                f"and media: {', '.join(zaparoo_media_sources)}."
            )
        else:
            self.append_output(
                f"Starting ScreenScraper scrape using {image_source}, {region} region preference, and {output_format} output."
            )

        self.scrape_worker = ZapScraperScrapeWorker(
            self.planned_actions,
            username,
            password,
            output_format,
            image_source,
            region,
            skip_existing_metadata=self.skip_metadata_checkbox.isChecked(),
            zaparoo_media_source_names=zaparoo_media_sources,
        )
        self.scrape_worker.progress.connect(self.on_scrape_progress)
        self.scrape_worker.log.connect(self.append_output)
        self.scrape_worker.quota.connect(self.update_quota_info)
        self.scrape_worker.result.connect(self.on_scrape_finished)
        self.scrape_worker.error.connect(self.on_scrape_error)
        self.scrape_worker.finished.connect(self.on_scrape_worker_finished)
        self.scrape_worker.start()

    def on_scrape_progress(self, current, total, rom_filename):
        self.progress_bar.setRange(0, max(1, int(total)))
        self.progress_bar.setValue(int(current))
        self.current_task_label.setText(f"Scraping {current} / {total}: {rom_filename}")

    def on_scrape_finished(self, completed, total):
        self.progress_bar.setRange(0, max(1, int(total)))
        self.progress_bar.setValue(int(completed))
        self.current_task_label.setText(f"Scrape complete. Processed {completed} / {total} games.")
        self.append_output(f"Scrape complete. Processed {completed} / {total} games.")

    def on_scrape_error(self, message):
        self.current_task_label.setText("Scrape failed.")
        self.append_output(f"Scrape failed: {message}")
        QMessageBox.warning(self, "ZapScraper", message)

    def on_scrape_worker_finished(self):
        self.scrape_worker = None
        self.set_busy_state(False)
        self.update_connection_state(lightweight=True)

    def stop_current_worker(self):
        stopped = False

        if self.scan_worker is not None and self.scan_worker.isRunning():
            self.scan_worker.requestInterruption()
            stopped = True

        if self.plan_worker is not None and self.plan_worker.isRunning():
            self.plan_worker.requestInterruption()
            stopped = True

        if self.login_worker is not None and self.login_worker.isRunning():
            self.login_worker.requestInterruption()
            stopped = True

        if self.scrape_worker is not None and self.scrape_worker.isRunning():
            self.scrape_worker.requestInterruption()
            stopped = True

        if stopped:
            self.current_task_label.setText("Stopping... waiting for the current operation to finish safely.")
            self.append_output("Stopping current task...")

    def selected_system_for_review(self):
        item = self.systems_list.currentItem()

        if item is not None:
            system = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(system, dict):
                return system

        selected = self.selected_systems()
        if len(selected) == 1:
            return selected[0]

        return None

    def review_selected_gamelist(self):
        system = self.selected_system_for_review()

        if not system:
            QMessageBox.information(
                self,
                "ZapScraper",
                "Select one system to review first.",
            )
            return

        if self._is_zaparoo_companion_mode():
            dialog = ZapScraperGamelistDialogMode1(
                system=system,
                username=self.username_edit.text().strip(),
                password=self.password_edit.text(),
                selected_region=self._active_region(),
                media_source_names=self._active_zaparoo_media_sources(),
                parent=self,
            )
        else:
            dialog = ZapScraperGamelistDialog(
                system=system,
                username=self.username_edit.text().strip(),
                password=self.password_edit.text(),
                image_source_name=self.image_source_combo.currentText(),
                selected_region=self._active_region(),
                parent=self,
            )

        dialog.exec()

    def selected_systems(self):
        selected = []

        for index in range(self.systems_list.count()):
            item = self.systems_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))

        return selected

    def select_all_systems(self):
        for index in range(self.systems_list.count()):
            self.systems_list.item(index).setCheckState(Qt.CheckState.Checked)

        self.update_connection_state(lightweight=True)

    def clear_system_selection(self):
        for index in range(self.systems_list.count()):
            self.systems_list.item(index).setCheckState(Qt.CheckState.Unchecked)

        self.update_connection_state(lightweight=True)

    def append_output(self, message):
        self.output.append(str(message))

    def set_busy_state(self, busy):
        is_offline = self._is_offline_mode()
        can_use_source = self._has_usable_source()
        enabled = not busy and can_use_source

        self.source_combo.setEnabled(not busy and is_offline)
        self.browse_custom_folder_button.setEnabled(
            not busy
            and is_offline
            and self.source_combo.currentText() == SOURCE_CUSTOM_GAMES_FOLDER
        )

        self.scan_button.setEnabled(enabled)
        self.scrape_button.setEnabled(enabled)
        self.select_all_button.setEnabled(enabled)
        self.clear_selection_button.setEnabled(enabled)
        self.review_gamelist_button.setEnabled(
            not busy and self.systems_list.currentItem() is not None
        )

        self.username_edit.setEnabled(not busy and is_offline and not self.logged_in)
        self.password_edit.setEnabled(not busy and is_offline and not self.logged_in)
        self.login_button.setEnabled(not busy and is_offline and not self.logged_in)
        self.logout_button.setEnabled(not busy and is_offline and self.logged_in)

        self.output_format_combo.setEnabled(enabled)
        self.image_source_combo.setEnabled(enabled and not self._is_zaparoo_companion_mode())
        self.region_combo.setEnabled(enabled and not self._is_zaparoo_companion_mode())
        self.region_priority_combo.setEnabled(enabled and self._is_zaparoo_companion_mode())

        for checkbox in self.zaparoo_media_checkboxes.values():
            checkbox.setEnabled(enabled and self._is_zaparoo_companion_mode())

        self.skip_metadata_checkbox.setEnabled(enabled)
        self.skip_images_checkbox.setEnabled(enabled)

        self.stop_button.setEnabled(bool(busy))
        self.update_output_format_ui()
        self.update_scan_button_text()
        self.update_source_ui()

    def show_refreshing_state(self):
        self.update_connection_state(lightweight=True)

    def refresh_status(self):
        self.update_connection_state(lightweight=True)

    def update_connection_state(self, lightweight: bool = True):
        is_offline = self._is_offline_mode()
        busy = self._is_busy()

        if is_offline and not busy:
            self.sync_scan_cache_for_source(force=False)

        can_use_source = self._has_usable_source()

        self.source_combo.setEnabled(is_offline and not busy)
        self.browse_custom_folder_button.setEnabled(
            is_offline
            and not busy
            and self.source_combo.currentText() == SOURCE_CUSTOM_GAMES_FOLDER
        )

        enabled = bool(is_offline and can_use_source and not busy)

        self.scan_button.setEnabled(enabled)
        self.scrape_button.setEnabled(enabled)
        self.select_all_button.setEnabled(enabled)
        self.clear_selection_button.setEnabled(enabled)
        self.review_gamelist_button.setEnabled(
            not busy and self.systems_list.currentItem() is not None
        )

        self.username_edit.setEnabled(is_offline and not busy and not self.logged_in)
        self.password_edit.setEnabled(is_offline and not busy and not self.logged_in)
        self.login_button.setEnabled(is_offline and not busy and not self.logged_in)
        self.logout_button.setEnabled(is_offline and not busy and self.logged_in)

        self.output_format_combo.setEnabled(enabled)
        self.image_source_combo.setEnabled(enabled and not self._is_zaparoo_companion_mode())
        self.region_combo.setEnabled(enabled and not self._is_zaparoo_companion_mode())
        self.region_priority_combo.setEnabled(enabled and self._is_zaparoo_companion_mode())

        for checkbox in self.zaparoo_media_checkboxes.values():
            checkbox.setEnabled(enabled and self._is_zaparoo_companion_mode())

        self.skip_metadata_checkbox.setEnabled(enabled)
        self.skip_images_checkbox.setEnabled(enabled)

        self.stop_button.setEnabled(busy)

        self.update_output_format_ui()
        self.update_scan_button_text()
        self.update_source_ui()
        self.update_account_ui()

    def _is_busy(self):
        workers = (
            self.scan_worker,
            self.plan_worker,
            self.login_worker,
            self.scrape_worker,
        )

        for worker in workers:
            if worker is not None and worker.isRunning():
                return True

        return False

    def _is_offline_mode(self):
        checker = getattr(self.main_window, "is_offline_mode", None)
        return bool(checker()) if callable(checker) else False

    def _sd_root(self):
        getter = getattr(self.main_window, "get_offline_sd_root", None)
        if callable(getter):
            return str(getter() or "").strip()
        return ""

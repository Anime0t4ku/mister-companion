from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.mister_monitor_client import MiSTerMonitorClient, MiSTerMonitorError
from core.mister_monitor_remote import resolve_screenscraper_content
from ui.dialogs.mister_monitor_config_dialog import MiSTerMonitorConfigWidget


class MiSTerMonitorDisplayWorker(QThread):
    state = pyqtSignal(dict)
    artwork = pyqtSignal(bytes, str)
    connection_changed = pyqtSignal(bool, str)

    def __init__(self, host: str, screenscraper_credentials=("", ""), parent=None):
        super().__init__(parent)
        self.client = MiSTerMonitorClient(host, timeout=1.5)
        self._screenscraper_credentials = screenscraper_credentials
        self._force_scan = False

    def stop(self):
        self.requestInterruption()

    def set_screenscraper_credentials(self, username: str, password: str):
        self._screenscraper_credentials = (str(username or "").strip(), str(password or ""))

    def request_force_scan(self):
        self._force_scan = True

    def _fetch_achievements(self) -> list[dict]:
        achievements = []
        page = 0
        pages = 1
        while page < pages and page < 30 and not self.isInterruptionRequested():
            data = self.client.get_json(
                f"/status/retroachievements/achievements?page={page}&per=25",
                timeout=4.0,
            )
            if str(data.get("status") or "") != "ok":
                break
            pages = max(1, int(data.get("pages") or 1))
            count = max(0, int(data.get("count") or 0))
            for index in range(count):
                prefix = f"a{index}_"
                achievements.append(
                    {
                        "title": str(data.get(prefix + "title") or ""),
                        "description": str(data.get(prefix + "desc") or ""),
                        "points": int(data.get(prefix + "points") or 0),
                        "unlocked": bool(data.get(prefix + "unlocked")),
                        "hardcore": bool(data.get(prefix + "hardcore")),
                    }
                )
            page += 1
        return achievements

    def run(self):
        last_content_key = None
        last_stats_at = 0.0
        last_event_counter = None
        last_ra_signature = None
        was_connected = False

        while not self.isInterruptionRequested():
            payload = {}
            try:
                snapshot = self.client.snapshot()
                payload["snapshot"] = snapshot
                content_key = (
                    str(snapshot.get("core", "")),
                    str(snapshot.get("core_raw", "")),
                    str(snapshot.get("game", "")),
                )
                changed = content_key != last_content_key
                force_scan = self._force_scan
                self._force_scan = False
                now = time.monotonic()

                if changed or force_scan:
                    details = {}
                    try:
                        endpoint = "/status/rom/details?force=1" if force_scan else "/status/rom/details"
                        details = self.client.get_json(endpoint, timeout=5.0)
                    except MiSTerMonitorError:
                        pass
                    payload["rom_details"] = details

                    pack_art = b""
                    try:
                        pack_art = self.client.artwork()
                    except MiSTerMonitorError:
                        pass

                    username, password = self._screenscraper_credentials
                    resolved = {"metadata": {}, "artwork": b""}
                    try:
                        resolved = resolve_screenscraper_content(
                            snapshot,
                            details,
                            username,
                            password,
                            force_refresh=force_scan,
                        )
                    except Exception as exc:
                        resolved = {"metadata": {}, "artwork": b"", "error": str(exc)}
                    payload["metadata"] = resolved.get("metadata") or {}
                    payload["content_error"] = str(resolved.get("error") or "")
                    artwork = pack_art or resolved.get("artwork") or b""
                    source = "Artwork Pack" if pack_art else "Remote Display cache / ScreenScraper"
                    self.artwork.emit(artwork, source if artwork else payload["content_error"])

                ra_status = None
                if changed or now - last_stats_at >= 5.0:
                    for key, path in (
                        ("system", "/status/system"),
                        ("storage", "/status/storage"),
                        ("usb", "/status/usb"),
                        ("all", "/status/all"),
                        ("retroachievements", "/status/retroachievements"),
                    ):
                        try:
                            payload[key] = self.client.get_json(path, timeout=4.0)
                        except MiSTerMonitorError:
                            payload[key] = {}
                    ra_status = payload.get("retroachievements") or {}
                    ra_signature = (
                        ra_status.get("game_id"),
                        ra_status.get("game_title"),
                        ra_status.get("total"),
                    )
                    if str(ra_status.get("status") or "") == "ok" and ra_signature != last_ra_signature:
                        try:
                            payload["achievements"] = self._fetch_achievements()
                        except MiSTerMonitorError:
                            payload["achievements"] = []
                        last_ra_signature = ra_signature
                    elif str(ra_status.get("status") or "") != "ok":
                        last_ra_signature = None
                    last_stats_at = now

                try:
                    event = self.client.get_json("/status/retroachievements/event", timeout=1.0)
                    event_counter = int(event.get("event_counter") or 0)
                    if last_event_counter is not None and event_counter > last_event_counter:
                        if ra_status is None:
                            ra_status = self.client.get_json("/status/retroachievements", timeout=4.0)
                            payload["retroachievements"] = ra_status
                        payload["unlock_event"] = {
                            "title": str(ra_status.get("last_unlock_title") or "Achievement unlocked"),
                            "description": str(ra_status.get("last_unlock_description") or ""),
                            "points": int(ra_status.get("last_unlock_points") or 0),
                            "hardcore": bool(ra_status.get("last_unlock_hardcore")),
                        }
                    last_event_counter = event_counter
                except MiSTerMonitorError:
                    pass

                self.state.emit(payload)
                last_content_key = content_key
                if not was_connected:
                    self.connection_changed.emit(True, "")
                was_connected = True
            except MiSTerMonitorError as exc:
                if was_connected:
                    self.connection_changed.emit(False, str(exc))
                was_connected = False

            for _ in range(10):
                if self.isInterruptionRequested():
                    return
                self.msleep(100)


class MiSTerMonitorDisplayDialog(QDialog):
    PAGE_NAMES = ("Artwork", "Game Info", "Achievements", "System")

    def __init__(self, host: str, initial_snapshot=None, connection=None, main_window=None, parent=None):
        super().__init__(parent)
        self.host = host
        self.connection = connection
        self.main_window = main_window or parent
        self._art_pixmap = QPixmap()
        self._last_system = {}
        self._last_storage = {}
        self._last_usb = {}
        self._last_all = {}
        self._last_ra = {}
        self._metadata = {}
        self._achievements = []
        self._display_page_index = 0

        self.setWindowTitle("MiSTer Companion - Remote Display")
        self.setMinimumSize(760, 520)
        self.resize(1120, 720)
        self.setModal(False)
        self._build_ui()
        if isinstance(initial_snapshot, dict):
            self.apply_state({"snapshot": initial_snapshot})

        credentials = self._screenscraper_credentials()
        self.worker = MiSTerMonitorDisplayWorker(host, credentials, self)
        self.worker.state.connect(self.apply_state)
        self.worker.artwork.connect(self.apply_artwork)
        self.worker.connection_changed.connect(self.apply_connection_state)
        self.worker.start()

    def _screenscraper_credentials(self):
        config = getattr(self.main_window, "config_data", {}) or {}
        scraper = config.get("zapscraper", {}) if isinstance(config, dict) else {}
        if not isinstance(scraper, dict):
            scraper = {}
        return str(scraper.get("username") or "").strip(), str(scraper.get("password") or "")

    @staticmethod
    def _card(title: str):
        card = QGroupBox(title)
        card.setStyleSheet(
            "QGroupBox { background-color: palette(alternate-base); border: 1px solid palette(button); "
            "border-radius: 12px; margin-top: 18px; padding: 14px; font-weight: 700; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 7px; "
            "color: palette(highlight); }"
        )
        return card

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 18)
        root.setSpacing(10)
        top = QHBoxLayout()
        self.back_button = QPushButton("← Back to Device")
        self.back_button.clicked.connect(self.close)
        self.heading = QLabel("Remote Display")
        self.heading.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.connection_label = QLabel("Connecting…")
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.toggle_settings)
        self.settings_button.setVisible(self.connection is not None)
        self.fullscreen_button = QPushButton("Fullscreen")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        top.addWidget(self.back_button)
        top.addWidget(self.heading)
        top.addStretch(1)
        top.addWidget(self.connection_label)
        top.addWidget(self.settings_button)
        top.addWidget(self.fullscreen_button)
        root.addLayout(top)

        self.nav_widget = QWidget()
        nav = QHBoxLayout(self.nav_widget)
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(6)
        self.page_buttons = []
        for index, name in enumerate(self.PAGE_NAMES):
            button = QPushButton(name)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self.show_page(i))
            nav.addWidget(button)
            self.page_buttons.append(button)
        nav.addStretch(1)
        root.addWidget(self.nav_widget)

        self.unlock_banner = QLabel("")
        self.unlock_banner.setWordWrap(True)
        self.unlock_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unlock_banner.setStyleSheet(
            "background-color: #1f8f4e; color: white; border-radius: 8px; "
            "padding: 10px; font-size: 15px; font-weight: 700;"
        )
        self.unlock_banner.hide()
        root.addWidget(self.unlock_banner)
        self.unlock_timer = QTimer(self)
        self.unlock_timer.setSingleShot(True)
        self.unlock_timer.timeout.connect(self.unlock_banner.hide)

        self.stack = QStackedWidget()
        self.artwork_page = self._build_artwork_page()
        self.info_page = self._build_info_page()
        self.achievements_page = self._build_achievements_page()
        self.system_page = self._build_system_page()
        for page in (self.artwork_page, self.info_page, self.achievements_page, self.system_page):
            self.stack.addWidget(page)

        self.settings_page = None
        if self.connection is not None:
            self.settings_widget = MiSTerMonitorConfigWidget(
                self.connection, main_window=self.main_window, parent=self,
            )
            self.settings_widget.saved.connect(self.on_ra_settings_saved)
            self.settings_widget.screenscraper_saved.connect(self.on_screenscraper_settings_saved)
            self.settings_widget.cancelled.connect(self.show_display_page)
            settings_scroll = QScrollArea()
            settings_scroll.setWidgetResizable(True)
            settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
            settings_scroll.setWidget(self.settings_widget)
            self.settings_page = settings_scroll
            self.stack.addWidget(settings_scroll)
        root.addWidget(self.stack, 1)
        self.show_page(0)

    def _build_artwork_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.art_frame = QFrame()
        self.art_frame.setStyleSheet("background:#101218; border:1px solid palette(mid); border-radius:12px;")
        art_layout = QVBoxLayout(self.art_frame)
        self.art_label = QLabel("Waiting for artwork…")
        self.art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art_label.setWordWrap(True)
        self.art_label.setStyleSheet("color:#aeb6c2; font-size:15px; border:none;")
        self.art_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        art_layout.addWidget(self.art_label)
        layout.addWidget(self.art_frame, 7)
        side = QVBoxLayout()
        self.game_label = QLabel("MiSTer")
        self.game_label.setWordWrap(True)
        self.game_label.setStyleSheet("font-size:28px; font-weight:800;")
        self.core_label = QLabel("Waiting for MiSTer Monitor…")
        self.core_label.setWordWrap(True)
        self.core_label.setStyleSheet("font-size:16px; color:palette(midlight);")
        self.art_source_label = QLabel("")
        self.art_source_label.setWordWrap(True)
        self.scan_button = QPushButton("Scan Again")
        self.scan_button.clicked.connect(self.force_scan)
        side.addWidget(self.game_label)
        side.addWidget(self.core_label)
        side.addWidget(self.art_source_label)
        side.addStretch(1)
        side.addWidget(self.scan_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(side, 4)
        return page

    def _build_info_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.info_art_label = QLabel("No artwork")
        self.info_art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_art_label.setMinimumWidth(300)
        self.info_art_label.setStyleSheet("background:#101218; color:#aeb6c2; border-radius:12px;")
        layout.addWidget(self.info_art_label, 4)
        card = self._card("Game Information")
        grid = QGridLayout(card)
        self.info_title = QLabel("No game loaded")
        self.info_title.setWordWrap(True)
        self.info_title.setStyleSheet("font-size:24px; font-weight:800;")
        self.info_year = QLabel("--")
        self.info_developer = QLabel("--")
        self.info_publisher = QLabel("--")
        self.info_genre = QLabel("--")
        self.info_players = QLabel("--")
        self.info_rating = QLabel("--")
        grid.addWidget(self.info_title, 0, 0, 1, 4)
        fields = (("Year", self.info_year), ("Developer", self.info_developer),
                  ("Publisher", self.info_publisher), ("Genre", self.info_genre),
                  ("Players", self.info_players), ("Rating", self.info_rating))
        for index, (name, value) in enumerate(fields):
            row = 1 + index // 2
            column = (index % 2) * 2
            label = QLabel(name + ":")
            label.setStyleSheet("font-weight:700;")
            grid.addWidget(label, row, column)
            grid.addWidget(value, row, column + 1)
        self.synopsis = QTextEdit()
        self.synopsis.setReadOnly(True)
        self.synopsis.setPlaceholderText("Game information will appear when ScreenScraper identifies the game.")
        grid.addWidget(QLabel("Synopsis:"), 4, 0, 1, 4)
        grid.addWidget(self.synopsis, 5, 0, 1, 4)
        layout.addWidget(card, 6)
        return page

    def _build_achievements_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        summary = self._card("RetroAchievements")
        summary_layout = QGridLayout(summary)
        self.ra_status = QLabel("No achievement information")
        self.ra_status.setWordWrap(True)
        self.ra_progress = QProgressBar()
        self.ra_points = QLabel("Points: --")
        self.ra_hardcore = QLabel("Hardcore: --")
        summary_layout.addWidget(self.ra_status, 0, 0, 1, 2)
        summary_layout.addWidget(self.ra_progress, 1, 0, 1, 2)
        summary_layout.addWidget(self.ra_points, 2, 0)
        summary_layout.addWidget(self.ra_hardcore, 2, 1)
        layout.addWidget(summary)
        self.achievement_table = QTableWidget(0, 4)
        self.achievement_table.setHorizontalHeaderLabels(("Status", "Achievement", "Points", "Description"))
        self.achievement_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.achievement_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.achievement_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.achievement_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.achievement_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.achievement_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.achievement_table.setAlternatingRowColors(True)
        layout.addWidget(self.achievement_table, 1)
        return page

    def _build_system_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        cards = QGridLayout()
        self.system_values = {}
        for index, name in enumerate(("CPU", "Memory", "Uptime", "SD Card", "Network", "Session", "Requests")):
            card = self._card(name)
            card_layout = QVBoxLayout(card)
            value = QLabel("--")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setStyleSheet("font-size:18px; font-weight:700;")
            card_layout.addWidget(value)
            self.system_values[name] = value
            cards.addWidget(card, index // 4, index % 4)
        layout.addLayout(cards)
        usb_card = self._card("USB Devices")
        usb_layout = QVBoxLayout(usb_card)
        self.usb_list = QListWidget()
        usb_layout.addWidget(self.usb_list)
        layout.addWidget(usb_card, 1)
        return page

    def show_page(self, index: int):
        self._display_page_index = max(0, min(index, len(self.PAGE_NAMES) - 1))
        self.stack.setCurrentIndex(self._display_page_index)
        for button_index, button in enumerate(self.page_buttons):
            button.setChecked(button_index == self._display_page_index)

    def toggle_settings(self):
        if self.settings_page is None:
            return
        if self.stack.currentWidget() is self.settings_page:
            self.show_display_page()
            return
        if not self.settings_widget.load_remote_config():
            return
        self.stack.setCurrentWidget(self.settings_page)
        self.nav_widget.hide()
        self.settings_button.setText("Back to Display")
        self.heading.setText("Remote Display Settings")

    def show_display_page(self):
        self.nav_widget.show()
        self.settings_button.setText("Settings")
        self.heading.setText("Remote Display")
        self.show_page(self._display_page_index)

    def on_ra_settings_saved(self):
        self.show_display_page()
        self.connection_label.setText("MiSTer Monitor: Reconnecting…")
        self.connection_label.setStyleSheet("font-weight:700; color:#f39c12;")

    def on_screenscraper_settings_saved(self, username: str, password: str):
        self.worker.set_screenscraper_credentials(username, password)
        self.worker.request_force_scan()
        self.show_display_page()

    def force_scan(self):
        self.scan_button.setEnabled(False)
        self.scan_button.setText("Scanning…")
        self.worker.request_force_scan()

    @staticmethod
    def _number(value, default=0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def apply_state(self, payload: dict):
        snapshot = payload.get("snapshot") or {}
        game = str(snapshot.get("game") or "").strip()
        core = str(snapshot.get("core") or "MiSTer").strip()
        self.game_label.setText(game or ("MiSTer Menu" if core.lower() == "menu" else core))
        self.core_label.setText(f"{core} • {game}" if game else core)
        if "metadata" in payload:
            self._metadata = payload.get("metadata") or {}
            self._apply_metadata(game)
        if "content_error" in payload:
            self.art_source_label.setText(str(payload.get("content_error") or ""))
            self.scan_button.setEnabled(True)
            self.scan_button.setText("Scan Again")
        if "system" in payload:
            self._last_system = payload.get("system") or {}
        if "storage" in payload:
            self._last_storage = payload.get("storage") or {}
        if "usb" in payload:
            self._last_usb = payload.get("usb") or {}
        if "all" in payload:
            self._last_all = payload.get("all") or {}
        if "retroachievements" in payload:
            self._last_ra = payload.get("retroachievements") or {}
            self._apply_ra()
        if "achievements" in payload:
            self._achievements = payload.get("achievements") or []
            self._apply_achievements()
        if payload.get("unlock_event"):
            self.show_unlock(payload["unlock_event"])
        self._apply_system()

    def _apply_metadata(self, fallback_title: str):
        data = self._metadata
        self.info_title.setText(str(data.get("name") or fallback_title or "No game loaded"))
        released = str(data.get("releasedate") or "")
        self.info_year.setText(released[:4] if len(released) >= 4 else "--")
        self.info_developer.setText(str(data.get("developer") or "--"))
        self.info_publisher.setText(str(data.get("publisher") or "--"))
        self.info_genre.setText(str(data.get("genre") or "--"))
        self.info_players.setText(str(data.get("players") or "--"))
        rating = self._number(data.get("rating"), -1)
        self.info_rating.setText(f"{rating * 5:.1f} / 5" if rating >= 0 else "--")
        self.synopsis.setPlainText(str(data.get("description") or ""))

    def _apply_ra(self):
        ra = self._last_ra
        status = str(ra.get("status") or "")
        messages = {
            "not_configured": "RetroAchievements is not configured for MiSTer Monitor",
            "core_not_supported": "This core does not support RetroAchievements",
            "no_game_loaded": "Load a game to view achievements",
            "rom_not_recognized": "RetroAchievements could not identify this game",
            "hash_error": "The game could not be checked for achievements",
            "progress_unavailable": "Achievement progress is temporarily unavailable",
        }
        if status in messages or not ra.get("enabled"):
            self.ra_status.setText(messages.get(status, "RetroAchievements is not configured for MiSTer Monitor"))
            self.ra_progress.setRange(0, 1)
            self.ra_progress.setValue(0)
            self.ra_progress.setFormat("0 / 0")
            self.ra_points.setText("Points: --")
            self.ra_hardcore.setText("Hardcore: --")
            return
        total = int(self._number(ra.get("total")))
        unlocked = int(self._number(ra.get("unlocked")))
        self.ra_status.setText(str(ra.get("game_title") or "RetroAchievements"))
        self.ra_progress.setRange(0, max(1, total))
        self.ra_progress.setValue(min(unlocked, max(1, total)))
        self.ra_progress.setFormat(f"{unlocked} / {total}")
        self.ra_points.setText(f"Points: {int(self._number(ra.get('points_earned')))}/{int(self._number(ra.get('points_total')))}")
        self.ra_hardcore.setText(
            f"Hardcore: {int(self._number(ra.get('unlocked_hardcore')))} unlocked • "
            f"{int(self._number(ra.get('points_hardcore')))} points"
        )

    def _apply_achievements(self):
        self.achievement_table.setRowCount(len(self._achievements))
        for row, item in enumerate(self._achievements):
            status = "✓ Hardcore" if item.get("hardcore") else "✓ Unlocked" if item.get("unlocked") else "Locked"
            values = (status, item.get("title", ""), str(item.get("points", 0)), item.get("description", ""))
            for column, value in enumerate(values):
                self.achievement_table.setItem(row, column, QTableWidgetItem(str(value)))

    def _apply_system(self):
        system = self._last_system
        storage = self._last_storage
        all_status = self._last_all
        self.system_values["CPU"].setText(f"{self._number(system.get('cpu_usage')):.0f}%" if system else "--")
        self.system_values["Memory"].setText(f"{self._number(system.get('memory_usage')):.0f}%" if system else "--")
        seconds = int(self._number(system.get("uptime_seconds"))) if system else 0
        self.system_values["Uptime"].setText(f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m" if seconds else "--")
        sd = storage.get("sd_card", {}) if isinstance(storage, dict) else {}
        usage = self._number(sd.get("usage_percent"), -1) if isinstance(sd, dict) else -1
        self.system_values["SD Card"].setText(f"{usage:.0f}% used" if usage >= 0 else "--")
        self.system_values["Network"].setText(str(all_status.get("ip_address") or "--"))
        self.system_values["Session"].setText(str(all_status.get("session_duration_formatted") or "--"))
        requests = all_status.get("requests_count")
        self.system_values["Requests"].setText(str(requests) if requests is not None else "--")
        devices = self._last_usb.get("devices", []) if isinstance(self._last_usb, dict) else []
        if isinstance(devices, dict):
            devices = list(devices.values())
        self.usb_list.clear()
        for device in devices if isinstance(devices, list) else []:
            name = device.get("name") if isinstance(device, dict) else str(device)
            if name:
                self.usb_list.addItem(str(name))
        if self.usb_list.count() == 0:
            self.usb_list.addItem("No external USB devices reported")

    def show_unlock(self, event: dict):
        title = str(event.get("title") or "Achievement unlocked")
        description = str(event.get("description") or "")
        points = int(event.get("points") or 0)
        hardcore = " • Hardcore" if event.get("hardcore") else ""
        self.unlock_banner.setText(f"Achievement Unlocked: {title} • {points} points{hardcore}\n{description}".strip())
        self.unlock_banner.show()
        self.unlock_timer.start(6000)

    def apply_artwork(self, data: bytes, source: str):
        pixmap = QPixmap()
        if data and pixmap.loadFromData(data):
            self._art_pixmap = pixmap
            self.art_source_label.setText(source)
            self._scale_artwork()
        else:
            self._art_pixmap = QPixmap()
            for label in (self.art_label, self.info_art_label):
                label.setPixmap(QPixmap())
                label.setText("No artwork available")
            self.art_source_label.setText(source)
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Scan Again")

    def _scale_artwork(self):
        if self._art_pixmap.isNull():
            return
        for label in (self.art_label, self.info_art_label):
            size = label.contentsRect().size()
            if size.width() > 0 and size.height() > 0:
                label.setText("")
                label.setPixmap(self._art_pixmap.scaled(
                    size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
                ))

    def apply_connection_state(self, connected: bool, message: str):
        if connected:
            self.connection_label.setText("MiSTer Monitor: Connected")
            self.connection_label.setStyleSheet("font-weight:700; color:#2ecc71;")
        else:
            self.connection_label.setText("MiSTer Monitor: Reconnecting…")
            self.connection_label.setStyleSheet("font-weight:700; color:#f39c12;")

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.fullscreen_button.setText("Fullscreen")
        else:
            self.showFullScreen()
            self.fullscreen_button.setText("Exit Fullscreen")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._scale_artwork()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
            return
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
            return
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self.stack.currentWidget() is not self.settings_page:
            delta = -1 if event.key() == Qt.Key.Key_Left else 1
            self.show_page((self._display_page_index + delta) % len(self.PAGE_NAMES))
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(25000)
        super().closeEvent(event)

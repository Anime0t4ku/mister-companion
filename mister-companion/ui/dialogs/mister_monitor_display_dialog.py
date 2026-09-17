from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.mister_monitor_client import MiSTerMonitorClient, MiSTerMonitorError
from ui.dialogs.mister_monitor_config_dialog import MiSTerMonitorConfigWidget


class MiSTerMonitorDisplayWorker(QThread):
    state = pyqtSignal(dict)
    artwork = pyqtSignal(bytes, str)
    connection_changed = pyqtSignal(bool, str)

    def __init__(self, host: str, parent=None):
        super().__init__(parent)
        self.client = MiSTerMonitorClient(host, timeout=1.5)

    def stop(self):
        self.requestInterruption()

    def run(self):
        last_content_key = None
        last_stats_at = 0.0
        was_connected = False

        while not self.isInterruptionRequested():
            try:
                snapshot = self.client.snapshot()
                content_key = (
                    str(snapshot.get("core", "")),
                    str(snapshot.get("core_raw", "")),
                    str(snapshot.get("game", "")),
                    snapshot.get("sequence", snapshot.get("seq")),
                )
                changed = content_key != last_content_key
                now = time.monotonic()
                payload = {"snapshot": snapshot}

                if changed:
                    try:
                        self.artwork.emit(self.client.artwork(), "")
                    except MiSTerMonitorError as exc:
                        self.artwork.emit(b"", str(exc))

                if changed or now - last_stats_at >= 5.0:
                    for key, path in (
                        ("system", "/status/system"),
                        ("storage", "/status/storage"),
                        ("retroachievements", "/status/retroachievements"),
                    ):
                        try:
                            payload[key] = self.client.get_json(path)
                        except MiSTerMonitorError:
                            payload[key] = {}
                    last_stats_at = now

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
    def __init__(
        self,
        host: str,
        initial_snapshot=None,
        connection=None,
        main_window=None,
        parent=None,
    ):
        super().__init__(parent)
        self.host = host
        self.connection = connection
        self.main_window = main_window or parent
        self._art_pixmap = QPixmap()
        self._fullscreen = False
        self._last_system = {}
        self._last_storage = {}
        self._last_ra = {}

        self.setWindowTitle("MiSTer Companion - Remote Display")
        self.setMinimumSize(720, 480)
        self.resize(1100, 700)
        self.setModal(False)
        self._build_ui()

        if isinstance(initial_snapshot, dict):
            self.apply_state({"snapshot": initial_snapshot})

        self.worker = MiSTerMonitorDisplayWorker(host, self)
        self.worker.state.connect(self.apply_state)
        self.worker.artwork.connect(self.apply_artwork)
        self.worker.connection_changed.connect(self.apply_connection_state)
        self.worker.start()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 18)
        root.setSpacing(12)

        top = QHBoxLayout()
        self.back_button = QPushButton("← Back to Device")
        self.back_button.clicked.connect(self.close)
        self.heading = QLabel("Remote Display")
        self.heading.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.connection_label = QLabel("Connecting…")
        self.connection_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.fullscreen_button = QPushButton("Fullscreen")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.ra_settings_button = QPushButton("RA Settings")
        self.ra_settings_button.clicked.connect(self.toggle_ra_settings)
        self.ra_settings_button.setVisible(self.connection is not None)
        top.addWidget(self.back_button)
        top.addWidget(self.heading)
        top.addStretch(1)
        top.addWidget(self.connection_label)
        top.addWidget(self.ra_settings_button)
        top.addWidget(self.fullscreen_button)
        root.addLayout(top)

        self.display_page = QWidget()
        display_layout = QVBoxLayout(self.display_page)
        display_layout.setContentsMargins(0, 0, 0, 0)
        display_layout.setSpacing(10)

        content = QHBoxLayout()
        content.setSpacing(18)

        self.art_frame = QFrame()
        self.art_frame.setObjectName("MonitorArtworkFrame")
        self.art_frame.setStyleSheet(
            "QFrame#MonitorArtworkFrame { background-color: #101218; "
            "border: 1px solid palette(mid); border-radius: 12px; }"
        )
        art_layout = QVBoxLayout(self.art_frame)
        art_layout.setContentsMargins(10, 10, 10, 10)
        self.art_label = QLabel("Waiting for artwork…")
        self.art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art_label.setWordWrap(True)
        self.art_label.setStyleSheet("color: #aeb6c2; font-size: 15px;")
        self.art_label.setMinimumSize(280, 260)
        self.art_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        art_layout.addWidget(self.art_label)
        content.addWidget(self.art_frame, 6)

        details = QWidget()
        detail_layout = QVBoxLayout(details)
        detail_layout.setContentsMargins(0, 4, 0, 4)
        detail_layout.setSpacing(10)

        self.game_label = QLabel("MiSTer")
        self.game_label.setWordWrap(True)
        self.game_label.setStyleSheet("font-size: 28px; font-weight: 800;")
        self.core_label = QLabel("Waiting for MiSTer Monitor…")
        self.core_label.setWordWrap(True)
        self.core_label.setStyleSheet("font-size: 16px; color: palette(midlight);")
        detail_layout.addWidget(self.game_label)
        detail_layout.addWidget(self.core_label)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        detail_layout.addWidget(divider)

        self.ra_title = QLabel("RetroAchievements")
        self.ra_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.ra_status = QLabel("No achievement information")
        self.ra_status.setWordWrap(True)
        self.ra_progress = QProgressBar()
        self.ra_progress.setRange(0, 1)
        self.ra_progress.setValue(0)
        self.ra_progress.setFormat("0 / 0")
        detail_layout.addWidget(self.ra_title)
        detail_layout.addWidget(self.ra_status)
        detail_layout.addWidget(self.ra_progress)

        self.stats_frame = QFrame()
        self.stats_frame.setObjectName("MonitorStatsFrame")
        self.stats_frame.setStyleSheet(
            "QFrame#MonitorStatsFrame { background-color: palette(alternate-base); "
            "border: 1px solid palette(button); border-radius: 10px; }"
        )
        stats = QGridLayout(self.stats_frame)
        stats.setContentsMargins(14, 12, 14, 12)
        stats.setHorizontalSpacing(18)
        stats.setVerticalSpacing(8)
        self.cpu_value = QLabel("--")
        self.memory_value = QLabel("--")
        self.uptime_value = QLabel("--")
        self.storage_value = QLabel("--")
        for column, (name, widget) in enumerate(
            (("CPU", self.cpu_value), ("Memory", self.memory_value),
             ("Uptime", self.uptime_value), ("SD Card", self.storage_value))
        ):
            title = QLabel(name)
            title.setStyleSheet("font-weight: 700;")
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stats.addWidget(title, 0, column, alignment=Qt.AlignmentFlag.AlignCenter)
            stats.addWidget(widget, 1, column)
        detail_layout.addStretch(1)
        detail_layout.addWidget(self.stats_frame)
        content.addWidget(details, 5)
        display_layout.addLayout(content, 1)

        hint = QLabel("F11 toggles fullscreen • Data is provided by the MiSTer Monitor server")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: palette(mid); font-size: 11px;")
        display_layout.addWidget(hint)
        root.addWidget(self.display_page, 1)

        self.ra_settings_page = None
        if self.connection is not None:
            self.ra_settings_page = MiSTerMonitorConfigWidget(
                self.connection,
                main_window=self.main_window,
                parent=self,
            )
            self.ra_settings_page.saved.connect(self.on_ra_settings_saved)
            self.ra_settings_page.cancelled.connect(self.show_display_page)
            self.ra_settings_page.hide()
            root.addWidget(self.ra_settings_page, 1)

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

        if "system" in payload:
            self._last_system = payload.get("system") or {}
        if "storage" in payload:
            self._last_storage = payload.get("storage") or {}
        if "retroachievements" in payload:
            self._last_ra = payload.get("retroachievements") or {}
        self._apply_stats()
        self._apply_ra()

    def _apply_stats(self):
        system = self._last_system
        storage = self._last_storage
        self.cpu_value.setText(f"{self._number(system.get('cpu_usage')):.0f}%" if system else "--")
        self.memory_value.setText(f"{self._number(system.get('memory_usage')):.0f}%" if system else "--")

        seconds = int(self._number(system.get("uptime_seconds"))) if system else 0
        if seconds:
            hours, remainder = divmod(seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            self.uptime_value.setText(f"{hours:d}h {minutes:02d}m")
        else:
            self.uptime_value.setText("--")

        sd = storage.get("sd_card", {}) if isinstance(storage, dict) else {}
        used = self._number(sd.get("usage_percent"), -1) if isinstance(sd, dict) else -1
        self.storage_value.setText(f"{used:.0f}% used" if used >= 0 else "--")

    def _apply_ra(self):
        ra = self._last_ra
        status = str(ra.get("status") or "").strip() if ra else ""
        if not ra:
            self.ra_status.setText("RetroAchievements information is unavailable")
            self.ra_progress.setRange(0, 1)
            self.ra_progress.setValue(0)
            self.ra_progress.setFormat("0 / 0")
            return

        status_messages = {
            "not_configured": "RetroAchievements is not configured for MiSTer Monitor",
            "core_not_supported": "This core does not support RetroAchievements",
            "no_game_loaded": "Load a game to view achievements",
            "rom_not_recognized": "RetroAchievements could not identify this game",
            "hash_error": "The game could not be checked for achievements",
            "progress_unavailable": "Achievement progress is temporarily unavailable",
        }
        if status in status_messages:
            self.ra_status.setText(status_messages[status])
            self.ra_progress.setRange(0, 1)
            self.ra_progress.setValue(0)
            self.ra_progress.setFormat("0 / 0")
            return
        if not ra.get("enabled"):
            self.ra_status.setText("RetroAchievements is not configured for MiSTer Monitor")
            self.ra_progress.setRange(0, 1)
            self.ra_progress.setValue(0)
            self.ra_progress.setFormat("0 / 0")
            return
        if status and status != "ok":
            self.ra_status.setText("Achievement progress is unavailable")
            self.ra_progress.setRange(0, 1)
            self.ra_progress.setValue(0)
            self.ra_progress.setFormat("0 / 0")
            return

        total = int(self._number(ra.get("total")))
        unlocked = int(self._number(ra.get("unlocked")))
        self.ra_progress.setRange(0, max(1, total))
        self.ra_progress.setValue(min(unlocked, max(1, total)))
        self.ra_progress.setFormat(f"{unlocked} / {total}")
        title = str(ra.get("game_title") or "").strip()
        points = int(self._number(ra.get("points_earned")))
        points_total = int(self._number(ra.get("points_total")))
        if ra.get("game_matched"):
            suffix = f" • {points}/{points_total} points" if points_total else ""
            self.ra_status.setText(f"{title or 'Game matched'}{suffix}")
        else:
            self.ra_status.setText("No matching achievement set")

    def toggle_ra_settings(self):
        if self.ra_settings_page is None:
            return
        if self.ra_settings_page.isVisible():
            self.show_display_page()
            return
        if not self.ra_settings_page.load_remote_config():
            return
        self.display_page.hide()
        self.ra_settings_page.show()
        self.ra_settings_button.setText("Back to Display")
        self.heading.setText("Remote Display Settings")

    def show_display_page(self):
        if self.ra_settings_page is not None:
            self.ra_settings_page.hide()
        self.display_page.show()
        self.ra_settings_button.setText("RA Settings")
        self.heading.setText("Remote Display")

    def on_ra_settings_saved(self):
        self.show_display_page()
        self.connection_label.setText("MiSTer Monitor: Reconnecting…")
        self.connection_label.setStyleSheet("font-weight: 700; color: #f39c12;")

    def apply_artwork(self, data: bytes, error: str):
        pixmap = QPixmap()
        if data and pixmap.loadFromData(data):
            self._art_pixmap = pixmap
            self._scale_artwork()
        else:
            self._art_pixmap = QPixmap()
            self.art_label.setPixmap(QPixmap())
            self.art_label.setText(
                "No local artwork is available for this game.\n\n"
                "Install a compatible MiSTer Artwork Pack to show artwork here."
            )

    def _scale_artwork(self):
        if self._art_pixmap.isNull():
            return
        size = self.art_label.contentsRect().size()
        if size.width() > 0 and size.height() > 0:
            self.art_label.setText("")
            self.art_label.setPixmap(
                self._art_pixmap.scaled(
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def apply_connection_state(self, connected: bool, message: str):
        if connected:
            self.connection_label.setText("MiSTer Monitor: Connected")
            self.connection_label.setStyleSheet("font-weight: 700; color: #2ecc71;")
        else:
            self.connection_label.setText("MiSTer Monitor: Reconnecting…")
            self.connection_label.setStyleSheet("font-weight: 700; color: #f39c12;")

    def toggle_fullscreen(self):
        self._fullscreen = not self.isFullScreen()
        if self._fullscreen:
            self.showFullScreen()
            self.fullscreen_button.setText("Exit Fullscreen")
        else:
            self.showNormal()
            self.fullscreen_button.setText("Fullscreen")

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
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(6000)
        super().closeEvent(event)

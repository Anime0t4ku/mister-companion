"""RomM integration tab.

Two authentication states (unpaired vs paired), and inside the paired state
three sub-tabs:
  - Browse     — platforms + collections + ROM table (right-click for actions)
  - Sync       — manage subscriptions and run the RomM ↔ MiSTer sync
  - Log        — persistent activity log

Auth = pairing-code exchange (mirrors decky-romm-sync).
"""
from __future__ import annotations

from datetime import datetime, timezone

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.config import save_config
from core.mister_cores import apply_overrides as apply_core_overrides
from core.mister_cores import core_folder_for_slug, is_supported
from core.romm import RomMClient, RomMError, RomMPairingError, normalize_pairing_code
from core.sync import (
    RESOLVE_DELETE,
    RESOLVE_KEEP,
    RESOLVE_MISTER,
    RESOLVE_ROMM,
    SyncPlan,
    download_and_push,
    download_firmware_for_platform,
    execute_sync,
    plan_sync,
)


def _human_size(n) -> str:
    if not n:
        return ""
    try:
        n = float(n)
    except Exception:
        return str(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _relative_time(iso: str) -> str:
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
    except Exception:
        return iso
    delta = datetime.now(timezone.utc) - t
    secs = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


# ── generic worker ─────────────────────────────────────────────────────────
class RomMWorker(QThread):
    finished = pyqtSignal(bool, object)
    progress = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.finished.emit(True, self.fn(self.progress.emit))
        except Exception as exc:
            self.finished.emit(False, exc)


# ── decision dialogs ───────────────────────────────────────────────────────
class OrphanDecisionDialog(QDialog):
    """Ask the user what to do with files on MiSTer that aren't in any subscription."""

    def __init__(self, orphans, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Files on MiSTer that aren't in your subscriptions")
        self.setMinimumSize(720, 460)
        self.resolution = ""

        layout = QVBoxLayout(self)
        info = QLabel(
            f"<b>{len(orphans)}</b> file(s) exist on the MiSTer but aren't in any "
            "platform or collection you're syncing. What do you want to do?"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for a in orphans:
            self.list.addItem(f"{a.core_folder}/{a.file_name}   ({_human_size(a.size_mister)})")
        layout.addWidget(self.list, 1)

        self.keep_radio = QRadioButton("Keep all — do nothing to these files")
        self.delete_radio = QRadioButton("Delete all — remove them from the MiSTer")
        self.keep_radio.setChecked(True)
        layout.addWidget(self.keep_radio)
        layout.addWidget(self.delete_radio)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self):
        self.resolution = RESOLVE_DELETE if self.delete_radio.isChecked() else RESOLVE_KEEP
        self.accept()


class OverwriteDecisionDialog(QDialog):
    """Ask the user what to do with files that differ between MiSTer and RomM."""

    def __init__(self, conflicts, parent=None, title="Files differ between MiSTer and RomM"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(760, 460)
        self.resolution = ""

        layout = QVBoxLayout(self)
        info = QLabel(
            f"<b>{len(conflicts)}</b> file(s) exist on both sides but have different "
            "sizes. Which side should win?"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for a in conflicts:
            self.list.addItem(
                f"{a.core_folder}/{a.file_name}   "
                f"MiSTer: {_human_size(a.size_mister)}   RomM: {_human_size(a.size_romm)}"
            )
        layout.addWidget(self.list, 1)

        self.romm_radio = QRadioButton("RomM wins — download over the MiSTer copy")
        self.mister_radio = QRadioButton("MiSTer wins — skip these downloads")
        self.romm_radio.setChecked(True)
        layout.addWidget(self.romm_radio)
        layout.addWidget(self.mister_radio)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self):
        self.resolution = RESOLVE_ROMM if self.romm_radio.isChecked() else RESOLVE_MISTER
        self.accept()


# ── main tab ───────────────────────────────────────────────────────────────
class RomMTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._worker: RomMWorker | None = None
        self._rom_worker: RomMWorker | None = None
        self._client: RomMClient | None = None
        self._platforms: list[dict] = []
        self._collections: list[dict] = []
        self._mister_was_connected: bool = False
        self._sync_in_progress: bool = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Two auth panes, either visible at once. Kept in the root layout so
        # the hidden one collapses to zero height (unlike a QStackedWidget,
        # which reserves the tallest child's height).
        self.unpaired_pane = self._build_unpaired_pane()
        self.paired_pane = self._build_paired_pane()
        root.addWidget(self.unpaired_pane)
        root.addWidget(self.paired_pane)
        self.paired_pane.hide()

        self.main_tabs = QTabWidget()
        self.main_tabs.addTab(self._build_browse_tab(), "Browse")
        self.main_tabs.addTab(self._build_sync_tab(), "Sync")
        self.main_tabs.addTab(self._build_log_tab(), "Log")
        root.addWidget(self.main_tabs, 1)

        # Apply any user overrides for the slug→core mapping BEFORE we start
        # rendering / planning.
        apply_core_overrides(self._cfg("core_overrides", {}))
        self._restore_from_config()

    # ── AUTH panes ────────────────────────────────────────────────────────
    def _build_unpaired_pane(self) -> QWidget:
        pane = QGroupBox("Pair with RomM")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        help_lbl = QLabel(
            "In your RomM web UI, open <b>Control Panel → API Keys</b>, generate a "
            "<b>pairing code</b> (60s validity), then paste the 8-character code below."
        )
        help_lbl.setWordWrap(True)
        layout.addWidget(help_lbl)

        url_cfg = self.main_window.config_data.get("romm_config", {}).get("url", "")
        self.url_edit = QLineEdit(url_cfg)
        self.url_edit.setPlaceholderText("https://romm.example.com")
        for label, w in (("URL", self.url_edit),):
            row = QHBoxLayout()
            lbl = QLabel(label); lbl.setFixedWidth(80)
            row.addWidget(lbl); row.addWidget(w, 1); layout.addLayout(row)

        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("XXXXXXXX")
        self.code_edit.setMaxLength(16)
        self.code_edit.textChanged.connect(self._normalize_code_field)
        row = QHBoxLayout()
        lbl = QLabel("Pair code"); lbl.setFixedWidth(80)
        row.addWidget(lbl); row.addWidget(self.code_edit, 1); layout.addLayout(row)

        btn_row = QHBoxLayout(); btn_row.addStretch()
        self.pair_button = QPushButton("Pair"); self.pair_button.setDefault(True)
        self.pair_button.clicked.connect(self._on_pair)
        btn_row.addWidget(self.pair_button); layout.addLayout(btn_row)
        return pane

    def _build_paired_pane(self) -> QWidget:
        # Flat one-line bar — no groupbox, tight margins.
        pane = QWidget()
        layout = QHBoxLayout(pane)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        self.paired_label = QLabel()
        self.paired_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.paired_label, 1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setFlat(True)
        self.refresh_button.clicked.connect(self._on_refresh_lists)
        layout.addWidget(self.refresh_button)
        self.unpair_button = QPushButton("Unpair")
        self.unpair_button.setFlat(True)
        self.unpair_button.clicked.connect(self._on_unpair)
        layout.addWidget(self.unpair_button)
        return pane

    # ── BROWSE sub-tab ────────────────────────────────────────────────────
    def _build_browse_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w); layout.setContentsMargins(6, 6, 6, 6); layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.source_tabs = QTabWidget()

        # Platforms pane: [search] + list
        plat_pane = QWidget(); plp_l = QVBoxLayout(plat_pane)
        plp_l.setContentsMargins(4, 4, 4, 4); plp_l.setSpacing(4)
        self.platform_search = QLineEdit()
        self.platform_search.setPlaceholderText("Search platforms…")
        self.platform_search.setClearButtonEnabled(True)
        self.platform_search.textChanged.connect(self._on_platform_search)
        plp_l.addWidget(self.platform_search)
        self.platform_list = QListWidget()
        self.platform_list.itemSelectionChanged.connect(self._on_platform_selected)
        self.platform_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.platform_list.customContextMenuRequested.connect(self._on_platform_context)
        plp_l.addWidget(self.platform_list, 1)
        self.source_tabs.addTab(plat_pane, "Platforms")

        # Collections pane: [search] + list
        coll_pane = QWidget(); clp_l = QVBoxLayout(coll_pane)
        clp_l.setContentsMargins(4, 4, 4, 4); clp_l.setSpacing(4)
        self.collection_search = QLineEdit()
        self.collection_search.setPlaceholderText("Search collections…")
        self.collection_search.setClearButtonEnabled(True)
        self.collection_search.textChanged.connect(self._on_collection_search)
        clp_l.addWidget(self.collection_search)
        self.collection_list = QListWidget()
        self.collection_list.itemSelectionChanged.connect(self._on_collection_selected)
        self.collection_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.collection_list.customContextMenuRequested.connect(self._on_collection_context)
        clp_l.addWidget(self.collection_list, 1)
        self.source_tabs.addTab(coll_pane, "Collections")

        self.source_tabs.currentChanged.connect(self._on_source_tab_changed)
        splitter.addWidget(self.source_tabs)

        # ROMs pane: [search | loading bar] + table
        right = QGroupBox("ROMs")
        rl = QVBoxLayout(right); rl.setContentsMargins(8, 8, 8, 8); rl.setSpacing(4)
        # header stack: page 0 = search field, page 1 = loading indicator
        self.rom_header_stack = QStackedWidget()
        self.rom_search = QLineEdit()
        self.rom_search.setPlaceholderText("Search ROMs (name, file, platform)…")
        self.rom_search.setClearButtonEnabled(True)
        self.rom_search.textChanged.connect(self._on_rom_search)
        self.rom_header_stack.addWidget(self.rom_search)
        loading = QWidget()
        ll = QHBoxLayout(loading); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(6)
        self.rom_loading_label = QLabel("Loading ROMs…")
        ll.addWidget(self.rom_loading_label)
        self.rom_progress = QProgressBar()
        self.rom_progress.setRange(0, 0)   # indeterminate
        self.rom_progress.setTextVisible(False)
        ll.addWidget(self.rom_progress, 1)
        self.rom_cancel_button = QPushButton("Cancel")
        self.rom_cancel_button.clicked.connect(self._cancel_rom_fetch)
        ll.addWidget(self.rom_cancel_button)
        self.rom_header_stack.addWidget(loading)
        rl.addWidget(self.rom_header_stack)
        self.rom_table = QTableWidget(0, 4)
        self.rom_table.setHorizontalHeaderLabels(["Name", "Platform", "File", "Size"])
        hh = self.rom_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.rom_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rom_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.rom_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.rom_table.customContextMenuRequested.connect(self._on_rom_context)
        rl.addWidget(self.rom_table, 1)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1); splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        # Filters row (bottom)
        romm_cfg = self.main_window.config_data.get("romm_config", {})
        filter_group = QGroupBox("Filters")
        fg_l = QHBoxLayout(filter_group)
        fg_l.setContentsMargins(10, 6, 10, 6)
        self.hide_empty_cb = QCheckBox("Hide empty platforms")
        self.hide_empty_cb.setChecked(bool(romm_cfg.get("hide_empty", True)))
        self.hide_empty_cb.stateChanged.connect(self._on_filter_toggle)
        self.hide_unsupported_cb = QCheckBox("Hide platforms MiSTer can't run")
        self.hide_unsupported_cb.setChecked(bool(romm_cfg.get("hide_unsupported", True)))
        self.hide_unsupported_cb.stateChanged.connect(self._on_filter_toggle)
        fg_l.addWidget(self.hide_empty_cb)
        fg_l.addWidget(self.hide_unsupported_cb)
        fg_l.addStretch()
        layout.addWidget(filter_group)
        return w

    # ── SYNC sub-tab ──────────────────────────────────────────────────────
    def _build_sync_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w); layout.setContentsMargins(6, 6, 6, 6); layout.setSpacing(8)

        # Status row: MiSTer connection + last-sync summary
        status_row = QHBoxLayout()
        self.mister_status_label = QLabel()
        status_row.addWidget(self.mister_status_label, 1)
        self.change_root_button = QPushButton("Change path…")
        self.change_root_button.setFlat(True)
        self.change_root_button.clicked.connect(self._edit_mister_root)
        status_row.addWidget(self.change_root_button)
        layout.addLayout(status_row)
        self.last_sync_label = QLabel()
        self.last_sync_label.setStyleSheet("color: gray;")
        layout.addWidget(self.last_sync_label)

        # subscribed platforms
        plat_group = QGroupBox("Subscribed Platforms")
        pg_l = QVBoxLayout(plat_group)
        self.sub_platform_list = QListWidget()
        self.sub_platform_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sub_platform_list.customContextMenuRequested.connect(self._on_sub_platform_context)
        pg_l.addWidget(self.sub_platform_list)
        hint = QLabel("Right-click a platform in the Browse tab to subscribe. "
                      "Right-click here to unsubscribe.")
        hint.setStyleSheet("color: gray;")
        pg_l.addWidget(hint)
        layout.addWidget(plat_group)

        # subscribed collections
        coll_group = QGroupBox("Subscribed Collections")
        cg_l = QVBoxLayout(coll_group)
        self.sub_collection_list = QListWidget()
        self.sub_collection_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sub_collection_list.customContextMenuRequested.connect(self._on_sub_collection_context)
        cg_l.addWidget(self.sub_collection_list)
        layout.addWidget(coll_group)

        # Bottom action bar
        action_bar = QHBoxLayout()
        romm_cfg = self.main_window.config_data.get("romm_config", {})
        self.auto_sync_cb = QCheckBox("Auto-sync when MiSTer connects")
        self.auto_sync_cb.setChecked(bool(romm_cfg.get("auto_sync", False)))
        self.auto_sync_cb.stateChanged.connect(self._on_options_toggle)
        action_bar.addWidget(self.auto_sync_cb)
        self.sync_saves_cb = QCheckBox("Also sync saves && states")
        self.sync_saves_cb.setChecked(bool(romm_cfg.get("sync_saves", False)))
        self.sync_saves_cb.stateChanged.connect(self._on_options_toggle)
        action_bar.addWidget(self.sync_saves_cb)
        action_bar.addStretch()
        self.sync_now_button = QPushButton("Sync Now")
        self.sync_now_button.setDefault(True)
        self.sync_now_button.clicked.connect(self._on_sync_now)
        action_bar.addWidget(self.sync_now_button)
        layout.addLayout(action_bar)

        return w

    def _on_options_toggle(self, _state) -> None:
        self._save_config(
            auto_sync=self.auto_sync_cb.isChecked(),
            sync_saves=self.sync_saves_cb.isChecked(),
        )

    def _edit_mister_root(self) -> None:
        current = self._cfg("mister_root", "/media/fat")
        prompt = (
            "Path on the MiSTer where games (and saves/states/BIOS) live. "
            "Default is <code>/media/fat</code> (SD card). Common alternatives: "
            "<code>/media/usb0</code>, <code>/media/usb1</code>, "
            "<code>/media/network</code>. Must be absolute, no trailing slash."
        )
        text, ok = QInputDialog.getText(
            self, "MiSTer path", prompt,
            QLineEdit.EchoMode.Normal, current,
        )
        if not ok:
            return
        new_val = (text or "").strip().rstrip("/") or "/media/fat"
        if not new_val.startswith("/"):
            QMessageBox.warning(self, "Invalid path", "Path must be absolute (start with '/').")
            return
        # Optional live validation via SFTP if connected
        if self._mister_connected():
            try:
                sftp = self.main_window.connection.client.open_sftp()
                try:
                    sftp.stat(new_val)
                except (FileNotFoundError, IOError):
                    resp = QMessageBox.question(
                        self, "Path not found",
                        f"<code>{new_val}</code> doesn't exist on the MiSTer. Save anyway?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if resp != QMessageBox.StandardButton.Yes:
                        sftp.close(); return
                sftp.close()
            except Exception as exc:
                self._log(f"MiSTer path validation skipped: {exc}")
        self._save_config(mister_root=new_val)
        self._log(f"MiSTer path set to {new_val}")
        self._update_mister_status()

    # ── last-sync summary ────────────────────────────────────────────────
    def _render_last_sync(self) -> None:
        ts = self._cfg("sync_last_run", "")
        stats = self._cfg("sync_last_stats", {}) or {}
        if not ts:
            self.last_sync_label.setText("Last sync: never")
            return
        when = _relative_time(ts)
        parts = [f"{v} {k}" for k, v in stats.items() if v]
        summary = " — " + ", ".join(parts) if parts else ""
        self.last_sync_label.setText(f"Last sync: {when}{summary}")

    # ── LOG sub-tab ───────────────────────────────────────────────────────
    def _build_log_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w); layout.setContentsMargins(6, 6, 6, 6)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        layout.addWidget(self.log)
        return w

    # ── shared helpers ────────────────────────────────────────────────────
    def _log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")

    def _normalize_code_field(self, text: str) -> None:
        clean = normalize_pairing_code(text)
        if clean != text:
            self.code_edit.blockSignals(True)
            self.code_edit.setText(clean)
            self.code_edit.blockSignals(False)

    def _set_busy(self, busy: bool) -> None:
        self.pair_button.setEnabled(not busy)
        self.pair_button.setText("Pairing…" if busy else "Pair")
        if hasattr(self, "refresh_button"):
            self.refresh_button.setEnabled(not busy)
        if hasattr(self, "sync_now_button"):
            self.sync_now_button.setEnabled(not busy and self._mister_connected())

    def _run(self, fn, done):
        self._set_busy(True)
        self._worker = RomMWorker(fn)
        self._worker.progress.connect(self._log)

        def _finished(ok: bool, res):
            self._set_busy(False)
            done(ok, res)

        self._worker.finished.connect(_finished)
        self._worker.start()

    def _save_config(self, **updates) -> None:
        cfg = self.main_window.config_data.setdefault("romm_config", {})
        cfg.update(updates)
        save_config(self.main_window.config_data)

    def _cfg(self, key, default=None):
        return self.main_window.config_data.get("romm_config", {}).get(key, default)

    def _mister_connected(self) -> bool:
        conn = getattr(self.main_window, "connection", None)
        return bool(conn and conn.is_connected())

    def _update_mister_status(self) -> None:
        conn = getattr(self.main_window, "connection", None)
        connected = bool(conn and conn.is_connected())
        root = self._cfg("mister_root", "/media/fat")
        if connected:
            self.mister_status_label.setText(
                f"<b>MiSTer:</b> connected to <code>{conn.host}</code> · "
                f"path: <code>{root}</code>"
            )
            self.sync_now_button.setEnabled(True)
        else:
            self.mister_status_label.setText(
                "<b>MiSTer:</b> <span style='color:#c66'>not connected</span> · "
                f"path: <code>{root}</code> — connect on the Connection tab to enable sync"
            )
            self.sync_now_button.setEnabled(False)
        self._render_last_sync()

        # Auto-sync: fire on the rising edge (false → true) if enabled + paired.
        rose = connected and not self._mister_was_connected
        self._mister_was_connected = connected
        if (
            rose
            and self.auto_sync_cb.isChecked()
            and self._client is not None
            and not self._sync_in_progress
        ):
            subs = self._cfg("sync_platforms", []) + self._cfg("sync_collections", [])
            if subs:
                self._log("Auto-sync: MiSTer connected — starting sync.")
                self._on_sync_now()

    # ── STARTUP restore ───────────────────────────────────────────────────
    def _restore_from_config(self) -> None:
        url, token = self._cfg("url", ""), self._cfg("token", "")
        if not url or not token:
            self.paired_pane.hide(); self.unpaired_pane.show()
            self._update_mister_status()
            return
        self._client = RomMClient(url, token=token)
        self._show_paired(self._cfg("user_display", ""), self._cfg("token_name", ""), url)
        self._log(f"Restoring RomM session for {url} …")
        self._on_refresh_lists()

    # ── PAIR / UNPAIR ─────────────────────────────────────────────────────
    def _on_pair(self) -> None:
        url = self.url_edit.text().strip()
        code = normalize_pairing_code(self.code_edit.text())
        if not url:
            self._log("URL is required."); return
        if not code:
            self._log("Enter the pairing code shown in RomM's UI."); return
        self._client = RomMClient(url)
        self._log(f"Exchanging pairing code with {url} …")

        client = self._client

        def task(_progress):
            payload = client.exchange_pairing_code(code)
            me = client.whoami()
            return payload, me

        def done(ok, res):
            if not ok:
                exc = res if isinstance(res, Exception) else Exception(str(res))
                self._log(f"Pairing failed: {exc}")
                QMessageBox.warning(self, "Pairing failed", str(exc))
                self._client = None; self.code_edit.clear(); return
            payload, me = res
            user_display = me.get("username") or me.get("email") or f"user #{me.get('id', '?')}"
            self._save_config(
                url=url,
                token=payload.get("raw_token", ""),
                token_id=payload.get("id"),
                token_name=payload.get("name", ""),
                user_display=user_display,
            )
            self._log(f"Paired as {user_display}.")
            self.code_edit.clear()
            self._show_paired(user_display, payload.get("name", ""), url)
            self._on_refresh_lists()

        self._run(task, done)

    def _show_paired(self, user_display: str, token_name: str, url: str) -> None:
        # Compact one-liner; token name shown only on hover.
        self.paired_label.setText(f"🔗 <b>{user_display or '(unknown)'}</b> · {url}")
        self.paired_label.setToolTip(f"Token: {token_name or '(unnamed)'}")
        self.unpaired_pane.hide(); self.paired_pane.show()
        self._update_mister_status()

    def _on_unpair(self) -> None:
        confirm = QMessageBox.question(
            self, "Unpair from RomM",
            "Forget the stored API token on this device?\n\n"
            "The token stays valid on the RomM server — revoke it in "
            "Control Panel → API Keys if you want it gone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        url = self._cfg("url", "")
        self._save_config(url=url, token="", token_id=None, token_name="", user_display="")
        self._client = None
        self._platforms = []; self._collections = []
        self.platform_list.clear(); self.collection_list.clear(); self.rom_table.setRowCount(0)
        self.sub_platform_list.clear(); self.sub_collection_list.clear()
        self.paired_pane.hide(); self.unpaired_pane.show()
        self.url_edit.setText(url); self.code_edit.clear()
        self._log("Unpaired. Token forgotten locally.")

    # ── REFRESH lists ─────────────────────────────────────────────────────
    def _on_refresh_lists(self) -> None:
        if self._client is None:
            return
        client = self._client

        def task(_progress):
            return {"platforms": client.get_platforms(), "collections": client.get_collections()}

        def done(ok, res):
            if not ok:
                exc = res if isinstance(res, Exception) else Exception(str(res))
                self._log(f"Fetch failed: {exc}"); return
            self._platforms = res.get("platforms") or []
            self._collections = res.get("collections") or []
            self._log(f"Fetched {len(self._platforms)} platforms, {len(self._collections)} collections.")
            self._render_platforms()
            self._render_collections()
            self._render_subscriptions()

        self._run(task, done)

    @staticmethod
    def _rom_count(entry: dict) -> int:
        n = entry.get("rom_count")
        if n is None:
            n = entry.get("rom_ids_count", len(entry.get("rom_ids", [])))
        try:
            return int(n or 0)
        except (TypeError, ValueError):
            return 0

    def _sub_marker(self, is_subbed: bool, is_readonly: bool) -> str:
        if not is_subbed:
            return ""
        return "  ⬇" if is_readonly else "  ★"

    def _render_platforms(self) -> None:
        self.platform_list.clear()
        hide_unsup = self.hide_unsupported_cb.isChecked()
        hide_empty = self.hide_empty_cb.isChecked()
        subs = set(self._cfg("sync_platforms", []))
        readonly = set(self._cfg("readonly_platforms", []))
        shown = 0
        for p in sorted(self._platforms, key=lambda x: (x.get("name") or x.get("slug") or "").lower()):
            slug = p.get("slug", "")
            supported = is_supported(slug)
            count = self._rom_count(p)
            if hide_unsup and not supported:
                continue
            if hide_empty and count == 0:
                continue
            name = p.get("name") or slug or f"#{p.get('id')}"
            core = core_folder_for_slug(slug) or "—"
            pid = p.get("id")
            marker = self._sub_marker(pid in subs, pid in readonly)
            item = QListWidgetItem(f"{name}  ({count})   [{core}]{marker}")
            item.setData(Qt.ItemDataRole.UserRole, pid)
            if not supported:
                item.setForeground(Qt.GlobalColor.gray)
            self.platform_list.addItem(item)
            shown += 1
        hidden = len(self._platforms) - shown
        suffix = f" — {hidden} hidden" if hidden else ""
        self.source_tabs.setTabText(0, f"Platforms ({shown}{suffix})")

    def _render_collections(self) -> None:
        self.collection_list.clear()
        hide_empty = self.hide_empty_cb.isChecked()
        subs = set(self._cfg("sync_collections", []))
        readonly = set(self._cfg("readonly_collections", []))
        shown = 0
        for c in sorted(self._collections, key=lambda x: (x.get("name") or "").lower()):
            count = self._rom_count(c)
            if hide_empty and count == 0:
                continue
            name = c.get("name") or f"#{c.get('id')}"
            cid = c.get("id")
            marker = self._sub_marker(cid in subs, cid in readonly)
            item = QListWidgetItem(f"{name}  ({count}){marker}")
            item.setData(Qt.ItemDataRole.UserRole, cid)
            self.collection_list.addItem(item)
            shown += 1
        hidden = len(self._collections) - shown
        suffix = f" — {hidden} hidden" if hidden else ""
        self.source_tabs.setTabText(1, f"Collections ({shown}{suffix})")

    def _render_subscriptions(self) -> None:
        sub_pids = set(self._cfg("sync_platforms", []))
        sub_cids = set(self._cfg("sync_collections", []))
        ro_pids = set(self._cfg("readonly_platforms", []))
        ro_cids = set(self._cfg("readonly_collections", []))

        self.sub_platform_list.clear()
        for p in self._platforms:
            if p.get("id") not in sub_pids:
                continue
            slug = p.get("slug", "")
            core = core_folder_for_slug(slug) or "(unsupported!)"
            mode = "read-only ⬇" if p.get("id") in ro_pids else "sync ★"
            item = QListWidgetItem(f"{p.get('name')}  ({self._rom_count(p)})   → {core}   [{mode}]")
            item.setData(Qt.ItemDataRole.UserRole, p.get("id"))
            if not is_supported(slug):
                item.setForeground(Qt.GlobalColor.red)
            self.sub_platform_list.addItem(item)

        self.sub_collection_list.clear()
        for c in self._collections:
            if c.get("id") not in sub_cids:
                continue
            mode = "read-only ⬇" if c.get("id") in ro_cids else "sync ★"
            item = QListWidgetItem(f"{c.get('name')}  ({self._rom_count(c)})   [{mode}]")
            item.setData(Qt.ItemDataRole.UserRole, c.get("id"))
            self.sub_collection_list.addItem(item)

    def _on_filter_toggle(self, _state) -> None:
        self._save_config(
            hide_unsupported=self.hide_unsupported_cb.isChecked(),
            hide_empty=self.hide_empty_cb.isChecked(),
        )
        self._render_platforms()
        self._render_collections()
        self._on_platform_search(self.platform_search.text())
        self._on_collection_search(self.collection_search.text())

    # ── search boxes ──────────────────────────────────────────────────────
    def _on_platform_search(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for i in range(self.platform_list.count()):
            item = self.platform_list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _on_collection_search(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for i in range(self.collection_list.count()):
            item = self.collection_list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _on_rom_search(self, _text: str) -> None:
        self._apply_rom_search()

    def _apply_rom_search(self) -> None:
        needle = self.rom_search.text().strip().lower()
        for row in range(self.rom_table.rowCount()):
            if not needle:
                self.rom_table.setRowHidden(row, False); continue
            hit = False
            for col in (0, 1, 2):
                it = self.rom_table.item(row, col)
                if it and needle in it.text().lower():
                    hit = True; break
            self.rom_table.setRowHidden(row, not hit)

    # ── BROWSE selection ──────────────────────────────────────────────────
    def _on_source_tab_changed(self, _index: int) -> None:
        # clearSelection() alone fires itemSelectionChanged AND leaves the
        # current item intact — the handler would then re-fetch the same ROMs.
        # Block signals + reset the current item to truly deselect.
        for lst in (self.platform_list, self.collection_list):
            lst.blockSignals(True)
            lst.setCurrentItem(None)
            lst.clearSelection()
            lst.blockSignals(False)
        self.rom_table.setRowCount(0)

    def _on_platform_selected(self) -> None:
        item = self.platform_list.currentItem()
        if not item or self._client is None:
            return
        self._load_roms(platform_id=item.data(Qt.ItemDataRole.UserRole), label=f"platform {item.text()}")

    def _on_collection_selected(self) -> None:
        item = self.collection_list.currentItem()
        if not item or self._client is None:
            return
        self._load_roms(collection_id=item.data(Qt.ItemDataRole.UserRole), label=f"collection {item.text()}")

    def _load_roms(self, *, platform_id=None, collection_id=None, label="") -> None:
        client = self._client; assert client is not None
        self._log(f"Fetching ROMs for {label} …")
        self.rom_table.setRowCount(0)
        self.rom_search.clear()
        # Platform column is redundant when viewing a single platform.
        self.rom_table.setColumnHidden(1, platform_id is not None)

        self.rom_loading_label.setText(f"Loading {label} …")
        self._begin_rom_load()

        def task(_progress):
            return client.get_roms(platform_id=platform_id, collection_id=collection_id)

        worker = RomMWorker(task)

        def done(ok, res):
            # If a newer load started (or user cancelled), drop this result silently.
            if worker is not self._rom_worker:
                return
            self._rom_worker = None
            self._end_rom_load()
            if not ok:
                exc = res if isinstance(res, Exception) else Exception(str(res))
                self._log(f"ROMs fetch failed: {exc}"); return
            roms = res or []
            self._log(f"  → {len(roms)} ROMs")
            self.rom_table.setRowCount(len(roms))
            for row, rom in enumerate(roms):
                slug = (rom.get("platform_fs_slug") or rom.get("platform_slug") or "").lower()
                plat_display = (
                    rom.get("platform_display_name")
                    or rom.get("platform_custom_name")
                    or rom.get("platform_name")
                    or slug
                    or "—"
                )
                supported = is_supported(slug)
                plat_cell = plat_display if supported else f"⚠ {plat_display}"
                self.rom_table.setItem(row, 0, QTableWidgetItem(str(rom.get("name") or rom.get("fs_name") or "")))
                self.rom_table.setItem(row, 1, QTableWidgetItem(plat_cell))
                self.rom_table.setItem(row, 2, QTableWidgetItem(str(rom.get("fs_name") or "")))
                self.rom_table.setItem(row, 3, QTableWidgetItem(_human_size(rom.get("fs_size_bytes"))))
                if not supported:
                    for col in range(4):
                        it = self.rom_table.item(row, col)
                        it.setForeground(Qt.GlobalColor.gray)
                        it.setToolTip(f"No MiSTer core for platform '{slug or 'unknown'}'")
                # stash the rom dict on col 0 for context-menu actions
                self.rom_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, rom)
            self._apply_rom_search()

        worker.finished.connect(done)
        self._rom_worker = worker
        worker.start()

    def _begin_rom_load(self) -> None:
        self.rom_header_stack.setCurrentIndex(1)   # show loading bar
        # Block selection changes while loading — user must cancel first.
        self.platform_list.setEnabled(False)
        self.collection_list.setEnabled(False)
        self.source_tabs.tabBar().setEnabled(False)
        self.rom_table.setEnabled(False)

    def _end_rom_load(self) -> None:
        self.rom_header_stack.setCurrentIndex(0)   # show search field
        self.platform_list.setEnabled(True)
        self.collection_list.setEnabled(True)
        self.source_tabs.tabBar().setEnabled(True)
        self.rom_table.setEnabled(True)

    def _cancel_rom_fetch(self) -> None:
        # Orphan the worker — its done() callback will see it's no longer current
        # and bail. The in-flight HTTP request runs to completion in the background
        # (harmless: cheap CPU + we ignore its result).
        if self._rom_worker is None:
            return
        self._rom_worker = None
        self._end_rom_load()
        self._log("ROM fetch cancelled.")

    # ── CONTEXT MENUS: subscribe / unsubscribe / send ─────────────────────
    def _on_platform_context(self, pos):
        item = self.platform_list.itemAt(pos)
        if not item:
            return
        pid = item.data(Qt.ItemDataRole.UserRole)
        subs = list(self._cfg("sync_platforms", []))
        slug = next((p.get("slug", "") for p in self._platforms if p.get("id") == pid), "")
        menu = QMenu(self)
        if pid in subs:
            act = menu.addAction("Unsubscribe from sync")
            act.triggered.connect(lambda: self._toggle_platform_sub(pid, False))
        else:
            if not is_supported(slug):
                menu.addAction("(unsupported — no MiSTer core)").setEnabled(False)
            else:
                act = menu.addAction("Subscribe to sync")
                act.triggered.connect(lambda: self._toggle_platform_sub(pid, True))
        # BIOS action available whether subscribed or not, as long as core exists.
        if is_supported(slug):
            menu.addSeparator()
            bios_act = menu.addAction("Download BIOS to MiSTer")
            bios_act.setEnabled(self._mister_connected())
            bios_act.triggered.connect(lambda: self._download_bios(pid, slug))
            if not self._mister_connected():
                menu.addAction("(connect a MiSTer to enable)").setEnabled(False)
        # Override / add mapping — always available so users can rescue
        # slugs that are currently unsupported.
        menu.addSeparator()
        override_act = menu.addAction("Override MiSTer folder for this platform…")
        override_act.triggered.connect(lambda: self._edit_core_override(slug))
        menu.exec(self.platform_list.mapToGlobal(pos))

    def _edit_core_override(self, slug: str) -> None:
        if not slug:
            QMessageBox.warning(self, "No slug", "This platform has no slug — can't override.")
            return
        overrides = dict(self._cfg("core_overrides", {}) or {})
        current = overrides.get(slug.lower().strip(), "")
        default = core_folder_for_slug(slug) or ""
        prompt = (
            f"Slug: <b>{slug}</b><br>"
            f"Current mapping: <code>{current or default or '(unsupported)'}</code>"
            f"{'  (override)' if current else ''}<br><br>"
            "Enter the MiSTer folder name under <code>/media/fat/games/</code>. "
            "Leave blank to <b>clear the override</b>. Type nothing and enter "
            "an empty string to <b>mark this slug as unsupported</b>."
        )
        text, ok = QInputDialog.getText(
            self, "Override MiSTer folder",
            prompt,
            QLineEdit.EchoMode.Normal,
            current or default,
        )
        if not ok:
            return
        new_val = text.strip()
        key = slug.lower().strip()
        if new_val == default and key in overrides:
            # user cleared the override back to the built-in default
            del overrides[key]
            self._log(f"Cleared override for '{slug}' — reverted to default '{default}'")
        elif new_val == "" and current == "":
            # no change
            return
        else:
            overrides[key] = new_val
            self._log(f"Override set: '{slug}' → '{new_val or '(unsupported)'}'")
        self._save_config(core_overrides=overrides)
        apply_core_overrides(overrides)
        self._render_platforms()
        self._render_subscriptions()

    def _on_collection_context(self, pos):
        item = self.collection_list.itemAt(pos)
        if not item:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        subs = list(self._cfg("sync_collections", []))
        menu = QMenu(self)
        act = menu.addAction("Unsubscribe from sync" if cid in subs else "Subscribe to sync")
        act.triggered.connect(lambda: self._toggle_collection_sub(cid, cid not in subs))
        menu.exec(self.collection_list.mapToGlobal(pos))

    def _on_sub_platform_context(self, pos):
        item = self.sub_platform_list.itemAt(pos)
        if not item:
            return
        pid = item.data(Qt.ItemDataRole.UserRole)
        readonly = pid in set(self._cfg("readonly_platforms", []))
        slug = next((p.get("slug", "") for p in self._platforms if p.get("id") == pid), "")
        menu = QMenu(self)
        toggle_label = "Switch to bidirectional sync (★)" if readonly else "Switch to read-only (⬇)"
        act_ro = menu.addAction(toggle_label)
        act_ro.triggered.connect(lambda: self._toggle_platform_readonly(pid, not readonly))
        act = menu.addAction("Unsubscribe")
        act.triggered.connect(lambda: self._toggle_platform_sub(pid, False))
        if is_supported(slug):
            menu.addSeparator()
            bios_act = menu.addAction("Download BIOS to MiSTer")
            bios_act.setEnabled(self._mister_connected())
            bios_act.triggered.connect(lambda: self._download_bios(pid, slug))
        menu.exec(self.sub_platform_list.mapToGlobal(pos))

    def _download_bios(self, platform_id: int, slug: str) -> None:
        if self._client is None or not self._mister_connected():
            return
        client = self._client
        conn = self.main_window.connection
        sftp = conn.client.open_sftp()

        self.main_tabs.setCurrentIndex(2)  # switch to Log so progress is visible
        self._log(f"Downloading BIOS for platform '{slug}' …")

        mister_root = self._cfg("mister_root", "/media/fat")
        def task(prog):
            try:
                return download_firmware_for_platform(
                    client, sftp,
                    platform_id=platform_id, platform_slug=slug,
                    mister_root=mister_root,
                    progress=prog,
                )
            finally:
                sftp.close()

        def done(ok, res):
            if not ok:
                self._log(f"BIOS download failed: {res}"); return
            stats = res or {}
            summary = ", ".join(f"{k}={v}" for k, v in stats.items() if v)
            self._log(f"BIOS done: {summary or 'nothing to do'}. "
                      "Rename/relocate per your core's convention (see MiSTer wiki: setup/games/).")

        self._run(task, done)

    def _on_sub_collection_context(self, pos):
        item = self.sub_collection_list.itemAt(pos)
        if not item:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        readonly = cid in set(self._cfg("readonly_collections", []))
        menu = QMenu(self)
        toggle_label = "Switch to bidirectional sync (★)" if readonly else "Switch to read-only (⬇)"
        act_ro = menu.addAction(toggle_label)
        act_ro.triggered.connect(lambda: self._toggle_collection_readonly(cid, not readonly))
        act = menu.addAction("Unsubscribe")
        act.triggered.connect(lambda: self._toggle_collection_sub(cid, False))
        menu.exec(self.sub_collection_list.mapToGlobal(pos))

    def _toggle_platform_readonly(self, pid: int, readonly: bool) -> None:
        subs = list(self._cfg("readonly_platforms", []))
        if readonly and pid not in subs:
            subs.append(pid)
        elif not readonly and pid in subs:
            subs.remove(pid)
        self._save_config(readonly_platforms=subs)
        self._log(f"Platform #{pid} is now {'read-only ⬇' if readonly else 'bidirectional ★'}.")
        self._render_platforms(); self._render_subscriptions()

    def _toggle_collection_readonly(self, cid: int, readonly: bool) -> None:
        subs = list(self._cfg("readonly_collections", []))
        if readonly and cid not in subs:
            subs.append(cid)
        elif not readonly and cid in subs:
            subs.remove(cid)
        self._save_config(readonly_collections=subs)
        self._log(f"Collection #{cid} is now {'read-only ⬇' if readonly else 'bidirectional ★'}.")
        self._render_collections(); self._render_subscriptions()

    def _toggle_platform_sub(self, pid: int, subscribe: bool) -> None:
        subs = list(self._cfg("sync_platforms", []))
        if subscribe and pid not in subs:
            subs.append(pid)
        elif not subscribe and pid in subs:
            subs.remove(pid)
        self._save_config(sync_platforms=subs)
        self._log(f"{'Subscribed to' if subscribe else 'Unsubscribed from'} platform #{pid}.")
        self._render_platforms(); self._render_subscriptions()

    def _toggle_collection_sub(self, cid: int, subscribe: bool) -> None:
        subs = list(self._cfg("sync_collections", []))
        if subscribe and cid not in subs:
            subs.append(cid)
        elif not subscribe and cid in subs:
            subs.remove(cid)
        self._save_config(sync_collections=subs)
        self._log(f"{'Subscribed to' if subscribe else 'Unsubscribed from'} collection #{cid}.")
        self._render_collections(); self._render_subscriptions()

    # ── ROM row context: Send to MiSTer (manual transfer) ─────────────────
    def _on_rom_context(self, pos):
        item = self.rom_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        rom = self.rom_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if not rom:
            return
        slug = (rom.get("platform_fs_slug") or rom.get("platform_slug") or "").lower()
        supported = is_supported(slug)
        menu = QMenu(self)
        act = menu.addAction("Send to MiSTer")
        act.setEnabled(supported and self._mister_connected())
        act.triggered.connect(lambda: self._manual_send(rom))
        if not supported:
            menu.addAction(f"(unsupported: no MiSTer core for '{slug or 'unknown'}')").setEnabled(False)
        elif not self._mister_connected():
            menu.addAction("(not connected to a MiSTer)").setEnabled(False)
        menu.exec(self.rom_table.mapToGlobal(pos))

    def _manual_send(self, rom: dict) -> None:
        slug = (rom.get("platform_fs_slug") or rom.get("platform_slug") or "").lower()
        core = core_folder_for_slug(slug)
        if core is None:
            QMessageBox.warning(self, "Unsupported",
                                f"No MiSTer core for '{slug}' — cannot send this ROM.")
            return
        fname = rom.get("fs_name") or ""
        if not fname:
            QMessageBox.warning(self, "Missing filename", "This ROM record has no fs_name."); return
        remote = f"/media/fat/games/{core}/{fname}"

        # confirm overwrite if file exists
        conn = self.main_window.connection
        sftp = conn.client.open_sftp()
        exists = True
        try:
            sftp.stat(remote)
        except (FileNotFoundError, IOError):
            exists = False
        if exists:
            resp = QMessageBox.question(
                self, "Overwrite?",
                f"{fname} already exists at {remote} on the MiSTer. Overwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                sftp.close(); return

        rom_id = rom.get("id")
        client = self._client
        self._log(f"Sending {fname} → {remote} …")

        def task(prog):
            try:
                return download_and_push(client, sftp, rom_id, fname, remote,
                                         progress=lambda w, t: prog(f"  {w}/{t} B"))
            finally:
                sftp.close()

        def done(ok, res):
            if ok:
                self._log(f"  sent {res} B")
            else:
                self._log(f"  FAILED: {res}")

        self._run(task, done)

    # ── SYNC NOW ──────────────────────────────────────────────────────────
    def _on_sync_now(self) -> None:
        if self._sync_in_progress:
            return
        if self._client is None:
            return
        if not self._mister_connected():
            QMessageBox.warning(self, "Not connected", "Connect to a MiSTer first."); return
        sub_pids = list(self._cfg("sync_platforms", []))
        sub_cids = list(self._cfg("sync_collections", []))
        if not sub_pids and not sub_cids:
            QMessageBox.information(self, "Nothing subscribed",
                                    "Right-click platforms or collections in the Browse tab to subscribe."); return

        client = self._client
        conn = self.main_window.connection
        sftp = conn.client.open_sftp()
        ssh_client = conn.client
        host = conn.host or ""
        # Per-host manifest of files we've placed on this MiSTer. Deep-copy so
        # in-place mutation by execute_sync doesn't taint config until we save.
        full_manifest = dict(self._cfg("sync_manifest", {}) or {})
        host_manifest = dict(full_manifest.get(host, {}))

        self.main_tabs.setCurrentIndex(2)  # switch to Log so the user sees progress
        include_assets = self.sync_saves_cb.isChecked()
        self._log(f"Planning sync (saves&states: {'on' if include_assets else 'off'}) …")

        mister_root = self._cfg("mister_root", "/media/fat")
        def task(prog):
            return plan_sync(
                client,
                subscribed_platform_ids=sub_pids,
                subscribed_collection_ids=sub_cids,
                readonly_platform_ids=self._cfg("readonly_platforms", []),
                readonly_collection_ids=self._cfg("readonly_collections", []),
                sftp=sftp,
                ssh_client=ssh_client,
                manifest=host_manifest,
                mister_root=mister_root,
                include_assets=include_assets,
                progress=prog,
            )

        def done(ok, res):
            if not ok:
                self._log(f"Plan failed: {res}"); sftp.close(); return
            plan: SyncPlan = res
            self._present_plan(plan, sftp, host, host_manifest, full_manifest)

        self._run(task, done)

    def _present_plan(self, plan: SyncPlan, sftp, host: str = "",
                      host_manifest: dict | None = None,
                      full_manifest: dict | None = None) -> None:
        host_manifest = host_manifest if host_manifest is not None else {}
        full_manifest = full_manifest if full_manifest is not None else {}
        totals = plan.totals()
        self._log(
            f"Plan — ROMs: {totals['download']} download, {totals['overwrite']} conflict, "
            f"{totals['skip']} unchanged, {totals['orphan']} orphan. "
            f"Saves: {totals['save_download']}↓/{totals['save_upload']}↑/{totals['save_conflict']}⚔. "
            f"States: {totals['state_download']}↓/{totals['state_upload']}↑/{totals['state_conflict']}⚔. "
            f"Unsupported: {totals['unsupported']}. "
            f"Bytes: {_human_size(totals['bytes_to_download'])}"
        )

        if plan.unsupported:
            names = ", ".join(f"{u.name} ({u.slug})" for u in plan.unsupported[:5])
            more = f" (+{len(plan.unsupported)-5} more)" if len(plan.unsupported) > 5 else ""
            self._log(f"  Unsupported sources skipped: {names}{more}")

        if plan.filtered_incompatible:
            self._log(
                f"  Skipped {plan.filtered_incompatible} save(s)/state(s) tagged for other emulators "
                "(only mister-tagged assets are compatible with MiSTer cores)."
            )

        # Ask about ROM overwrite conflicts
        conflicts = plan.by_kind("overwrite")
        if conflicts:
            dlg = OverwriteDecisionDialog(conflicts, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self._log("Sync cancelled at ROM conflict prompt."); sftp.close(); return
            for a in conflicts:
                a.resolution = dlg.resolution

        # Ask about ROM orphans
        orphans = plan.by_kind("orphan")
        if orphans:
            dlg = OrphanDecisionDialog(orphans, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self._log("Sync cancelled at orphan prompt."); sftp.close(); return
            for a in orphans:
                a.resolution = dlg.resolution

        # Ask about save/state conflicts (same dialog, different title)
        save_conflicts = plan.by_kind("save_conflict")
        if save_conflicts:
            dlg = OverwriteDecisionDialog(save_conflicts, self,
                                          title="Save files differ between MiSTer and RomM")
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self._log("Sync cancelled at save conflict prompt."); sftp.close(); return
            for a in save_conflicts:
                a.resolution = dlg.resolution
        state_conflicts = plan.by_kind("state_conflict")
        if state_conflicts:
            dlg = OverwriteDecisionDialog(state_conflicts, self,
                                          title="Save states differ between MiSTer and RomM")
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self._log("Sync cancelled at state conflict prompt."); sftp.close(); return
            for a in state_conflicts:
                a.resolution = dlg.resolution

        # Execute
        client = self._client
        conn = self.main_window.connection
        ssh_client = conn.client
        self._log("Executing sync …")
        self._sync_in_progress = True

        mister_root = self._cfg("mister_root", "/media/fat")
        def task(prog):
            try:
                return execute_sync(plan, client, sftp,
                                    ssh_client=ssh_client,
                                    manifest=host_manifest,
                                    mister_root=mister_root, progress=prog)
            finally:
                sftp.close()

        def done(ok, res):
            self._sync_in_progress = False
            if not ok:
                self._log(f"Sync failed: {res}"); return
            stats = res or {}
            self._log("Sync complete: " + ", ".join(f"{k}={v}" for k, v in stats.items() if v))
            # Persist the updated per-host manifest back into the global map.
            if host:
                full_manifest[host] = host_manifest
            self._save_config(
                sync_last_run=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                sync_last_stats=stats,
                sync_manifest=full_manifest,
            )
            self._render_last_sync()

        self._run(task, done)

    # ── hooks expected by main_window ─────────────────────────────────────
    def update_connection_state(self, lightweight: bool = True) -> None:
        self._update_mister_status()

from __future__ import annotations

import os
import posixpath
import re
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.chd_converter import (
    CHDMAN_DIR,
    CHDMAN_VERSION,
    ChdmanError,
    default_output_name,
    descriptor_references,
    download_chdman,
    has_chdman,
    remove_chdman,
    run_chdman,
)
from core.file_browser import download_path, join_remote_path, remote_exists, upload_path
from core.disc_tools import (
    CDRDAO_DIR,
    CDRDAO_VERSION,
    DiscToolError,
    burn_cue,
    burn_iso9660_folder,
    disc_backend_ready,
    has_cdrdao,
    has_native_macos_disc_backend,
    install_cdrdao,
    remove_cdrdao,
    rip_disc,
    scan_drives,
)
from core.rom_patcher import (
    SUPPORTED_PATCH_EXTENSIONS,
    SUPPORTED_PATCH_FORMATS,
    PatchError,
    apply_patch,
    checksum_info,
    detect_patch_format,
    validation_label,
)
from ui.dialogs.remote_file_picker_dialog import RemoteFilePickerDialog


LOCAL = "This PC"
REMOTE = "MiSTer"
CHD_INPUT_EXTS = {".cue", ".gdi", ".iso"}


class ToolWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            result = self.fn(self)
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class ToolsTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.connection = main_window.connection
        self.worker = None
        self.chd_jobs: list[dict] = []
        self._build_ui()
        self.update_connection_state()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        self.stack = QStackedWidget()
        root.addWidget(self.stack)
        self.home_page = self._build_home()
        self.patcher_page = self._build_patcher()
        self.chd_page = self._build_chd()
        self.disc_to_image_page = self._build_disc_to_image()
        self.image_to_disc_page = self._build_image_to_disc()
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.patcher_page)
        self.stack.addWidget(self.chd_page)
        self.stack.addWidget(self.disc_to_image_page)
        self.stack.addWidget(self.image_to_disc_page)

    def _build_home(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Tools")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(title)
        subtitle = QLabel("Local and MiSTer-aware utilities. Remote sources are available while connected in Online mode.")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(12)
        for name, text, slot in (
            ("ROM Patcher", "Apply IPS, IPS32, BPS, UPS and PPF patches. The source ROM is never overwritten.", lambda: self.stack.setCurrentWidget(self.patcher_page)),
            ("CHD Converter", "Queue CUE/GDI/ISO → CHD conversions with independent PC or MiSTer input/output locations.", lambda: self.stack.setCurrentWidget(self.chd_page)),
            ("Disc to Image", "Rip a physical game CD to BIN/CUE, with optional CHD conversion.", lambda: self._open_disc_page(self.disc_to_image_page)),
            ("Image to Disc", "Burn BIN/CUE game discs or MSU-1 / MD+ folders as ISO 9660 data CDs.", lambda: self._open_disc_page(self.image_to_disc_page)),
        ):
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            row = QHBoxLayout(frame)
            labels = QVBoxLayout()
            heading = QLabel(name)
            heading.setStyleSheet("font-size: 16px; font-weight: 600;")
            labels.addWidget(heading)
            detail = QLabel(text)
            detail.setWordWrap(True)
            labels.addWidget(detail)
            row.addLayout(labels, 1)
            button = QPushButton("Open")
            button.clicked.connect(slot)
            row.addWidget(button)
            layout.addWidget(frame)
        layout.addStretch(1)
        return page

    def _back_button(self):
        button = QPushButton("← Back to Tools")
        button.clicked.connect(lambda: self.stack.setCurrentWidget(self.home_page))
        return button

    @staticmethod
    def _location_combo():
        combo = QComboBox()
        combo.addItems([LOCAL, REMOTE])
        combo.setFixedWidth(110)
        return combo

    def _build_patcher(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._back_button())
        title = QLabel("ROM Patcher")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)
        self.rom_location, self.rom_path = self._path_row(layout, "ROM:", self._browse_rom)
        self.patch_location, self.patch_path = self._path_row(layout, "Patch:", self._browse_patch)
        self.output_location, self.output_path = self._path_row(layout, "Output:", self._browse_output)
        self.rom_location.currentTextChanged.connect(self._patch_locations_changed)
        self.patch_location.currentTextChanged.connect(self._patch_locations_changed)
        self.output_location.currentTextChanged.connect(self._patch_locations_changed)
        self.patch_path.textChanged.connect(self._update_patch_info)

        self.patch_info = QLabel("Format: —    Source verification: —")
        layout.addWidget(self.patch_info)
        self.checksum_label = QLabel("Source checksums: —")
        self.checksum_label.setWordWrap(True)
        layout.addWidget(self.checksum_label)

        row = QHBoxLayout()
        row.addStretch(1)
        self.patch_button = QPushButton("Apply Patch")
        self.patch_button.clicked.connect(self._apply_patch_clicked)
        row.addWidget(self.patch_button)
        layout.addLayout(row)
        self.patch_status = QLabel("")
        layout.addWidget(self.patch_status)
        layout.addStretch(1)
        return page

    def _path_row(self, layout, label, browse_slot):
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        location = self._location_combo()
        row.addWidget(location)
        path = QLineEdit()
        row.addWidget(path, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(browse_slot)
        row.addWidget(browse)
        layout.addLayout(row)
        return location, path

    def _is_remote_allowed(self):
        return self.main_window.is_online_mode() and self.connection.is_connected()

    def _sync_location_combo(self, combo):
        remote_index = combo.findText(REMOTE)
        if self.main_window.is_offline_mode():
            if combo.currentText() == REMOTE:
                combo.setCurrentText(LOCAL)
            remote_index = combo.findText(REMOTE)
            if remote_index >= 0:
                combo.removeItem(remote_index)
            return

        if remote_index < 0:
            combo.addItem(REMOTE)
            remote_index = combo.findText(REMOTE)
        model_item = combo.model().item(remote_index)
        if model_item is not None:
            model_item.setEnabled(self.connection.is_connected())
        if not self.connection.is_connected() and combo.currentText() == REMOTE:
            combo.setCurrentText(LOCAL)

    def update_connection_state(self, lightweight=True):
        for combo_name in ("rom_location", "patch_location", "output_location", "chd_input_location", "chd_output_location"):
            combo = getattr(self, combo_name, None)
            if combo:
                self._sync_location_combo(combo)
        if hasattr(self, "chd_tool_status"):
            self._refresh_chdman_status()
        if hasattr(self, "disc_cdrdao_status"):
            self._refresh_cdrdao_status()

    def _browse_rom(self):
        if self.rom_location.currentText() == REMOTE:
            path = RemoteFilePickerDialog.get_open_file(self.connection, self, title="Select ROM from MiSTer")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select ROM")
        if path:
            self.rom_path.setText(path)
            self._suggest_patch_output()
            self._refresh_local_checksum()

    def _browse_patch(self):
        filters = list(SUPPORTED_PATCH_EXTENSIONS)
        if self.patch_location.currentText() == REMOTE:
            path = RemoteFilePickerDialog.get_open_file(self.connection, self, title="Select Patch from MiSTer", filters=filters)
        else:
            filt = "Supported patches (*.ips *.ips32 *.bps *.ups *.ppf);;All files (*.*)"
            path, _ = QFileDialog.getOpenFileName(self, "Select Patch", filter=filt)
        if path:
            self.patch_path.setText(path)
            self._suggest_patch_output()

    def _browse_output(self):
        default_name = self._default_patched_name()
        if self.output_location.currentText() == REMOTE:
            path = RemoteFilePickerDialog.get_save_file(self.connection, self, title="Save Patched ROM on MiSTer", default_name=default_name)
        else:
            start = str(Path(self.rom_path.text()).with_name(default_name)) if self.rom_location.currentText() == LOCAL and self.rom_path.text() else default_name
            path, _ = QFileDialog.getSaveFileName(self, "Save Patched ROM", start)
        if path:
            self.output_path.setText(path)

    def _default_patched_name(self):
        raw = self.rom_path.text().strip().replace("\\", "/")
        name = PurePosixPath(raw).name or "patched-rom.bin"
        p = Path(name)
        return f"{p.stem}-patched{p.suffix}"

    def _suggest_patch_output(self):
        if not self.rom_path.text().strip() or self.output_path.text().strip():
            return
        name = self._default_patched_name()
        if self.output_location.currentText() == LOCAL and self.rom_location.currentText() == LOCAL:
            self.output_path.setText(str(Path(self.rom_path.text()).with_name(name)))
        elif self.output_location.currentText() == REMOTE and self.rom_location.currentText() == REMOTE:
            self.output_path.setText(posixpath.join(posixpath.dirname(self.rom_path.text()), name))

    def _patch_locations_changed(self):
        self._suggest_patch_output()
        self._refresh_local_checksum()

    def _update_patch_info(self):
        path = self.patch_path.text().strip()
        if not path:
            self.patch_info.setText("Format: —    Source verification: —")
            return
        if self.patch_location.currentText() == LOCAL and Path(path).is_file():
            try:
                fmt = detect_patch_format(path)
                self.patch_info.setText(f"Format: {fmt}    Source verification: {validation_label(fmt)}")
                return
            except Exception:
                pass
        ext = PurePosixPath(path).suffix.lower().lstrip(".").upper()
        self.patch_info.setText(f"Format: {ext or '—'}    Source verification: checked when patching")

    def _refresh_local_checksum(self):
        path = self.rom_path.text().strip()
        if self.rom_location.currentText() == LOCAL and path and Path(path).is_file():
            try:
                info = checksum_info(path)
                self.checksum_label.setText(f"Source checksums: CRC32 {info['CRC32']} · MD5 {info['MD5']} · SHA-1 {info['SHA1']}")
                return
            except Exception:
                pass
        self.checksum_label.setText("Source checksums: calculated during patching")

    def _download_remote_file(self, remote_path, temp_dir):
        return Path(download_path(self.connection, remote_path, temp_dir, overwrite=False))

    def _ensure_remote_output_new(self, remote_path):
        if remote_exists(self.connection, remote_path):
            raise FileExistsError(f"Output already exists on MiSTer: {remote_path}\nChoose a new file name. The source is never overwritten.")

    def _apply_patch_clicked(self):
        source = self.rom_path.text().strip()
        patch = self.patch_path.text().strip()
        output = self.output_path.text().strip()
        if not source or not patch or not output:
            QMessageBox.warning(self, "ROM Patcher", "Select a ROM, patch and output file first.")
            return
        source_location = self.rom_location.currentText()
        patch_location = self.patch_location.currentText()
        output_location = self.output_location.currentText()
        self.patch_button.setEnabled(False)
        self.patch_status.setText("Patching...")

        def work(worker):
            with tempfile.TemporaryDirectory(prefix="mister-companion-patch-") as tmp:
                tmpdir = Path(tmp)
                worker.status.emit("Preparing source ROM...")
                local_source = self._download_remote_file(source, tmpdir) if source_location == REMOTE else Path(source)
                worker.status.emit("Preparing patch...")
                local_patch = self._download_remote_file(patch, tmpdir) if patch_location == REMOTE else Path(patch)
                if output_location == REMOTE:
                    self._ensure_remote_output_new(output)
                    local_output = tmpdir / PurePosixPath(output).name
                else:
                    local_output = Path(output)
                worker.status.emit("Applying patch...")
                result = apply_patch(local_source, local_patch, local_output)
                if output_location == REMOTE:
                    worker.status.emit("Uploading patched ROM to MiSTer...")
                    upload_path(self.connection, local_output, posixpath.dirname(output), target_name=PurePosixPath(output).name, overwrite=False)
                return result

        self.worker = ToolWorker(work, self)
        self.worker.status.connect(self.patch_status.setText)
        self.worker.succeeded.connect(self._patch_done)
        self.worker.failed.connect(self._patch_failed)
        self.worker.start()

    def _patch_done(self, result):
        self.patch_button.setEnabled(True)
        self.patch_status.setText(f"Complete. {result['format']} patch applied; source ROM was not modified.")
        QMessageBox.information(self, "ROM Patcher", "Patch applied successfully.\n\nThe original ROM was not modified.")

    def _patch_failed(self, message):
        self.patch_button.setEnabled(True)
        self.patch_status.setText("Patch failed.")
        QMessageBox.critical(self, "ROM Patcher", message)

    
    def _open_disc_page(self, page):
        self.stack.setCurrentWidget(page)
        self._refresh_cdrdao_status()
        self._refresh_disc_drives()

    def _cdrdao_controls(self, layout):
        row = QHBoxLayout()
        status = QLabel()
        row.addWidget(status, 1)
        install = QPushButton("Install cdrdao")
        install.clicked.connect(self._install_cdrdao_clicked)
        row.addWidget(install)
        remove = QPushButton("Remove")
        remove.clicked.connect(self._remove_cdrdao_clicked)
        row.addWidget(remove)
        if os.sys.platform == "darwin":
            
            
            install.setVisible(False)
            remove.setVisible(False)
        layout.addLayout(row)
        progress = QProgressBar()
        progress.setVisible(False)
        layout.addWidget(progress)
        return status, install, remove, progress

    def _build_disc_to_image(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._back_button())
        title = QLabel("Disc to Image")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)
        self.disc_cdrdao_status, self.disc_install_cdrdao, self.disc_remove_cdrdao, self.disc_cdrdao_progress = self._cdrdao_controls(layout)

        row = QHBoxLayout()
        row.addWidget(QLabel("Optical drive:"))
        self.disc_read_drive = QComboBox()
        row.addWidget(self.disc_read_drive, 1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh_disc_drives)
        row.addWidget(refresh)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Output CUE:"))
        self.disc_output_cue = QLineEdit()
        row.addWidget(self.disc_output_cue, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse_disc_output)
        row.addWidget(browse)
        layout.addLayout(row)

        self.disc_convert_chd = QCheckBox("Convert to CHD after ripping")
        self.disc_convert_chd.toggled.connect(self._disc_chd_toggled)
        layout.addWidget(self.disc_convert_chd)
        self.disc_remove_bin = QCheckBox("Remove BIN/CUE after successful CHD conversion")
        self.disc_remove_bin.setChecked(False)
        self.disc_remove_bin.setEnabled(False)
        layout.addWidget(self.disc_remove_bin)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.disc_rip_button = QPushButton("Rip Disc")
        self.disc_rip_button.clicked.connect(self._rip_disc_clicked)
        buttons.addWidget(self.disc_rip_button)
        layout.addLayout(buttons)
        self.disc_rip_status = QLabel("")
        self.disc_rip_status.setVisible(False)
        layout.addWidget(self.disc_rip_status)
        self.disc_rip_progress = QProgressBar()
        self.disc_rip_progress.setRange(0, 100)
        self.disc_rip_progress.setValue(0)
        self.disc_rip_progress.setFormat("%p%")
        self.disc_rip_progress.setVisible(False)
        layout.addWidget(self.disc_rip_progress)
        self.disc_rip_log = QTextEdit()
        self.disc_rip_log.setReadOnly(True)
        self.disc_rip_log.setMaximumHeight(160)
        layout.addWidget(self.disc_rip_log)
        layout.addStretch(1)
        return page

    def _build_image_to_disc(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._back_button())
        title = QLabel("Image to Disc")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)
        self.burn_cdrdao_status, self.burn_install_cdrdao, self.burn_remove_cdrdao, self.burn_cdrdao_progress = self._cdrdao_controls(layout)

        row = QHBoxLayout()
        row.addWidget(QLabel("Mode:"))
        self.burn_mode = QComboBox()
        self.burn_mode.addItems(["BIN/CUE Game Disc", "MSU-1 / MD+ Data Disc"])
        self.burn_mode.currentIndexChanged.connect(self._burn_mode_changed)
        row.addWidget(self.burn_mode, 1)
        layout.addLayout(row)

        row = QHBoxLayout()
        self.burn_source_label = QLabel("CUE image:")
        row.addWidget(self.burn_source_label)
        self.burn_source = QLineEdit()
        row.addWidget(self.burn_source, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse_burn_source)
        row.addWidget(browse)
        layout.addLayout(row)

        self.burn_root_note = QLabel("MSU-1 / MD+ mode writes only the files inside the selected folder to the ISO 9660 root; the selected folder itself is not created on disc.")
        self.burn_root_note.setWordWrap(True)
        self.burn_root_note.setVisible(False)
        layout.addWidget(self.burn_root_note)

        self.burn_label_row = QWidget()
        burn_label_layout = QHBoxLayout(self.burn_label_row)
        burn_label_layout.setContentsMargins(0, 0, 0, 0)
        burn_label_layout.addWidget(QLabel("Disc label:"))
        self.burn_disc_label = QLineEdit()
        self.burn_disc_label.setMaxLength(32)
        self.burn_disc_label.setPlaceholderText("Optional (max 32 characters)")
        burn_label_layout.addWidget(self.burn_disc_label, 1)
        self.burn_label_row.setVisible(False)
        layout.addWidget(self.burn_label_row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Optical writer:"))
        self.disc_write_drive = QComboBox()
        row.addWidget(self.disc_write_drive, 1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh_disc_drives)
        row.addWidget(refresh)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Write speed:"))
        self.burn_speed = QComboBox()
        self.burn_speed.addItems(["Auto", "4x", "8x", "12x", "16x", "24x"])
        row.addWidget(self.burn_speed)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.burn_button = QPushButton("Burn Disc")
        self.burn_button.clicked.connect(self._burn_disc_clicked)
        buttons.addWidget(self.burn_button)
        layout.addLayout(buttons)
        self.burn_status = QLabel()
        self.burn_status.setVisible(False)
        layout.addWidget(self.burn_status)
        self.burn_progress = QProgressBar()
        self.burn_progress.setRange(0, 100)
        self.burn_progress.setValue(0)
        self.burn_progress.setFormat("%p%")
        self.burn_progress.setVisible(False)
        layout.addWidget(self.burn_progress)
        self.burn_log = QTextEdit()
        self.burn_log.setReadOnly(True)
        self.burn_log.setMaximumHeight(160)
        layout.addWidget(self.burn_log)
        layout.addStretch(1)
        return page

    def _refresh_cdrdao_status(self):
        ready = disc_backend_ready()
        if os.sys.platform == "darwin":
            text = "Native macOS Disc Recording: Ready" if ready else "Native macOS Disc Recording: Unavailable"
            install_text = "Install cdrdao"
        else:
            text = f"cdrdao {CDRDAO_VERSION}: {'Ready' if ready else 'Not installed'}"
            install_text = "Install cdrdao"
        if hasattr(self, "disc_cdrdao_status"):
            self.disc_cdrdao_status.setText(text)
            self.disc_install_cdrdao.setText(install_text)
            self.disc_install_cdrdao.setVisible(os.sys.platform != "darwin" and not ready)
            self.disc_remove_cdrdao.setVisible(os.sys.platform != "darwin" and ready)
        if hasattr(self, "burn_cdrdao_status"):
            self.burn_cdrdao_status.setText(text)
            self.burn_install_cdrdao.setText(install_text)
            self.burn_install_cdrdao.setVisible(os.sys.platform != "darwin" and not ready)
            self.burn_remove_cdrdao.setVisible(os.sys.platform != "darwin" and ready)
        if hasattr(self, "disc_rip_button"):
            self.disc_rip_button.setEnabled(ready)
        if hasattr(self, "burn_button"):
            self.burn_button.setEnabled(ready)

    def _install_cdrdao_clicked(self):
        if os.sys.platform == "darwin":
            return

        for button_name in ("disc_install_cdrdao", "burn_install_cdrdao"):
            button = getattr(self, button_name, None)
            if button is not None:
                button.setEnabled(False)
        for progress_name in ("disc_cdrdao_progress", "burn_cdrdao_progress"):
            progress = getattr(self, progress_name, None)
            if progress is not None:
                progress.setValue(0)
                progress.setVisible(True)

        def work(worker):
            def progress(done, total):
                worker.progress.emit(int(done * 100 / total) if total else 0)
            return install_cdrdao(progress)

        self.worker = ToolWorker(work, self)
        self.worker.progress.connect(self._set_cdrdao_install_progress)
        self.worker.succeeded.connect(self._cdrdao_installed)
        self.worker.failed.connect(self._cdrdao_install_failed)
        self.worker.start()

    def _set_cdrdao_install_progress(self, value):
        for progress_name in ("disc_cdrdao_progress", "burn_cdrdao_progress"):
            progress = getattr(self, progress_name, None)
            if progress is not None:
                progress.setValue(value)

    def _finish_cdrdao_install_ui(self):
        for button_name in ("disc_install_cdrdao", "burn_install_cdrdao"):
            button = getattr(self, button_name, None)
            if button is not None:
                button.setEnabled(True)
        for progress_name in ("disc_cdrdao_progress", "burn_cdrdao_progress"):
            progress = getattr(self, progress_name, None)
            if progress is not None:
                progress.setVisible(False)

    def _cdrdao_installed(self, _result):
        self._finish_cdrdao_install_ui()
        self._refresh_cdrdao_status()
        self._refresh_disc_drives()

    def _cdrdao_install_failed(self, message):
        self._finish_cdrdao_install_ui()
        
        
        
        self._refresh_cdrdao_status()
        self._refresh_disc_drives()
        QMessageBox.critical(self, "cdrdao", message)

    def _remove_cdrdao_clicked(self):
        remove_cdrdao()
        self._refresh_cdrdao_status()
        self._refresh_disc_drives()

    def _refresh_disc_drives(self):
        drives = []
        if disc_backend_ready():
            try:
                drives = scan_drives()
            except Exception:
                drives = []
        for combo_name in ("disc_read_drive", "disc_write_drive"):
            combo = getattr(self, combo_name, None)
            if combo is None:
                continue
            previous = combo.currentData()
            combo.clear()
            for device, label in drives:
                display = label if os.sys.platform == "darwin" else f"{label}  [{device}]"
                combo.addItem(display, device)
            if not drives:
                combo.addItem("No optical drives detected", None)
            elif previous:
                for i in range(combo.count()):
                    if combo.itemData(i) == previous:
                        combo.setCurrentIndex(i)
                        break

        
        
        
        ready = disc_backend_ready()
        if hasattr(self, "disc_rip_button"):
            self.disc_rip_button.setEnabled(ready)
        if hasattr(self, "burn_button"):
            self.burn_button.setEnabled(ready)

    def _browse_disc_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Disc Image", self.disc_output_cue.text().strip(), "CUE sheet (*.cue)")
        if path:
            if not path.lower().endswith(".cue"):
                path += ".cue"
            self.disc_output_cue.setText(path)

    def _disc_chd_toggled(self, checked):
        self.disc_remove_bin.setEnabled(checked)
        if not checked:
            self.disc_remove_bin.setChecked(False)

    def _rip_disc_clicked(self):
        device = self.disc_read_drive.currentData()
        output = self.disc_output_cue.text().strip()
        if not device or not output:
            QMessageBox.warning(self, "Disc to Image", "Select an optical drive and output CUE file first.")
            return
        if self.disc_convert_chd.isChecked() and not has_chdman():
            QMessageBox.warning(self, "Disc to Image", "Download CHDman from CHD Converter before enabling CHD conversion.")
            return
        self.disc_rip_button.setEnabled(False)
        self.disc_rip_progress.setRange(0, 100)
        self.disc_rip_progress.setValue(0)
        self.disc_rip_progress.setVisible(True)
        self.disc_rip_status.setText("Reading disc layout...")
        self.disc_rip_status.setVisible(True)
        self.disc_rip_log.clear()

        convert = self.disc_convert_chd.isChecked()
        remove_bin_cue = self.disc_remove_bin.isChecked()

        def work(worker):
            def rip_log(line):
                worker.status.emit("LOG:" + line)

            def rip_progress(percent, message):
                worker.progress.emit(percent)
                worker.status.emit("RIPSTATUS:" + message)

            cue, bin_path, toc = rip_disc(
                device, output, rip_log, progress_callback=rip_progress
            )
            chd = None
            if convert:
                chd = cue.with_suffix(".chd")
                worker.progress.emit(0)
                worker.status.emit("RIPSTATUS:Converting BIN/CUE to CHD — 0%")
                worker.status.emit("LOG:Converting BIN/CUE to CHD...")

                def chd_log(line):
                    match = re.search(r"(\d+(?:\.\d+)?)%\s+complete", line, re.IGNORECASE)
                    if match:
                        percent = max(0, min(100, int(float(match.group(1)))))
                        worker.progress.emit(percent)
                        worker.status.emit(f"RIPSTATUS:Converting BIN/CUE to CHD — {percent}%")
                    elif "error" in line.lower() or "warning" in line.lower():
                        worker.status.emit("LOG:" + line)

                run_chdman(cue, chd, chd_log)
                worker.progress.emit(100)
                worker.status.emit("RIPSTATUS:CHD conversion complete — 100%")
                if remove_bin_cue:
                    cue.unlink(missing_ok=True)
                    bin_path.unlink(missing_ok=True)
                    toc.unlink(missing_ok=True)
            return str(chd or cue)

        self.worker = ToolWorker(work, self)
        self.worker.progress.connect(self.disc_rip_progress.setValue)
        self.worker.status.connect(self._disc_rip_worker_status)
        self.worker.succeeded.connect(self._rip_disc_done)
        self.worker.failed.connect(self._rip_disc_failed)
        self.worker.start()

    def _disc_rip_worker_status(self, text):
        if text.startswith("RIPSTATUS:"):
            self.disc_rip_status.setText(text[len("RIPSTATUS:"):])
        elif text.startswith("LOG:"):
            self.disc_rip_log.append(text[len("LOG:"):])
        else:
            self.disc_rip_log.append(text)

    def _rip_disc_done(self, output):
        self.disc_rip_button.setEnabled(True)
        self.disc_rip_progress.setValue(100)
        self.disc_rip_status.setText("Complete — 100%")
        QMessageBox.information(self, "Disc to Image", f"Disc image created successfully.\n\n{output}")

    def _rip_disc_failed(self, message):
        self.disc_rip_button.setEnabled(True)
        self.disc_rip_status.setText("Failed")
        QMessageBox.critical(self, "Disc to Image", message)

    def _burn_mode_changed(self):
        data_mode = self.burn_mode.currentIndex() == 1
        self.burn_source_label.setText("MSU-1 / MD+ folder:" if data_mode else "CUE image:")
        self.burn_root_note.setVisible(data_mode)
        self.burn_label_row.setVisible(data_mode)
        self.burn_source.clear()
        if not data_mode:
            self.burn_disc_label.clear()

    def _browse_burn_source(self):
        if self.burn_mode.currentIndex() == 1:
            path = QFileDialog.getExistingDirectory(self, "Select MSU-1 / MD+ Folder")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select CUE Image", filter="CUE sheet (*.cue);;All files (*.*)")
        if path:
            self.burn_source.setText(path)

    def _burn_speed_value(self):
        text = self.burn_speed.currentText()
        return None if text == "Auto" else int(text.rstrip("x"))

    def _burn_disc_clicked(self):
        device = self.disc_write_drive.currentData()
        source = self.burn_source.text().strip()
        if not device or not source:
            QMessageBox.warning(self, "Image to Disc", "Select an optical writer and source first.")
            return
        data_mode = self.burn_mode.currentIndex() == 1
        if data_mode:
            root_files = [p for p in Path(source).iterdir() if p.is_file()] if Path(source).is_dir() else []
            if not root_files:
                QMessageBox.warning(self, "Image to Disc", "The selected MSU-1 / MD+ folder has no files at its root.")
                return
        self.burn_button.setEnabled(False)
        self.burn_progress.setRange(0, 100)
        self.burn_progress.setValue(0)
        self.burn_progress.setVisible(True)
        self.burn_status.setText("Preparing disc...")
        self.burn_status.setVisible(True)
        self.burn_log.clear()
        speed = self._burn_speed_value()
        disc_label = self.burn_disc_label.text().strip() if data_mode else ""

        def work(worker):
            burn_log_state = {"last_milestone": None}

            def log(line):
                worker.status.emit("LOG:" + line)

            def progress(percent, message):
                if percent is None or percent < 0:
                    worker.status.emit("BURNBUSY:" + message)
                else:
                    worker.progress.emit(percent)
                    worker.status.emit("BURNSTATUS:" + message)

                
                
                
                milestone = re.sub(r"\s*[—-]\s*\d+%$", "", message).strip()
                if milestone and milestone != burn_log_state["last_milestone"]:
                    worker.status.emit("LOG:" + milestone)
                    burn_log_state["last_milestone"] = milestone

            if data_mode:
                burn_iso9660_folder(
                    device, source, speed=speed, volume_id=disc_label or None,
                    log_callback=log, progress_callback=progress
                )
            else:
                burn_cue(
                    device, source, speed=speed, log_callback=log, progress_callback=progress
                )
            return True

        self.worker = ToolWorker(work, self)
        self.worker.progress.connect(self._burn_progress_value)
        self.worker.status.connect(self._burn_worker_status)
        self.worker.succeeded.connect(self._burn_disc_done)
        self.worker.failed.connect(self._burn_disc_failed)
        self.worker.start()

    def _burn_progress_value(self, value):
        
        
        
        if self.burn_progress.minimum() == 0 and self.burn_progress.maximum() == 0:
            self.burn_progress.setRange(0, 100)
        self.burn_progress.setValue(value)

    def _burn_worker_status(self, text):
        if text.startswith("BURNBUSY:"):
            self.burn_progress.setRange(0, 0)
            self.burn_status.setText(text[len("BURNBUSY:"):])
        elif text.startswith("BURNSTATUS:"):
            self.burn_status.setText(text[len("BURNSTATUS:"):])
        elif text.startswith("LOG:"):
            self.burn_log.append(text[len("LOG:"):])
        else:
            self.burn_log.append(text)

    def _burn_disc_done(self, _result):
        self.burn_button.setEnabled(True)
        self.burn_progress.setRange(0, 100)
        self.burn_progress.setValue(100)
        self.burn_status.setText("Complete — 100%")
        QMessageBox.information(self, "Image to Disc", "Disc written successfully.")

    def _burn_disc_failed(self, message):
        self.burn_button.setEnabled(True)
        self.burn_progress.setRange(0, 100)
        self.burn_status.setText("Failed")
        QMessageBox.critical(self, "Image to Disc", message)

    
    def _build_chd(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._back_button())
        title = QLabel("CHD Converter")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)
        tool_row = QHBoxLayout()
        self.chd_tool_status = QLabel()
        tool_row.addWidget(self.chd_tool_status, 1)
        self.download_chdman_button = QPushButton("Download CHDman")
        self.download_chdman_button.clicked.connect(self._download_chdman_clicked)
        tool_row.addWidget(self.download_chdman_button)
        self.remove_chdman_button = QPushButton("Remove")
        self.remove_chdman_button.clicked.connect(self._remove_chdman_clicked)
        tool_row.addWidget(self.remove_chdman_button)
        layout.addLayout(tool_row)
        self.chd_download_progress = QProgressBar()
        self.chd_download_progress.setVisible(False)
        layout.addWidget(self.chd_download_progress)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Add input from:"))
        self.chd_input_location = self._location_combo()
        input_row.addWidget(self.chd_input_location)
        self.chd_add_files = QPushButton("Add Files")
        self.chd_add_files.clicked.connect(self._chd_add_files_clicked)
        input_row.addWidget(self.chd_add_files)
        self.chd_add_folder = QPushButton("Add Folder")
        self.chd_add_folder.clicked.connect(self._chd_add_folder_clicked)
        input_row.addWidget(self.chd_add_folder)
        input_row.addStretch(1)
        layout.addLayout(input_row)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output for new jobs:"))
        self.chd_output_location = self._location_combo()
        output_row.addWidget(self.chd_output_location)
        self.chd_output_dir = QLineEdit()
        output_row.addWidget(self.chd_output_dir, 1)
        browse_output = QPushButton("Browse")
        browse_output.clicked.connect(self._chd_browse_output)
        output_row.addWidget(browse_output)
        layout.addLayout(output_row)

        self.chd_table = QTableWidget(0, 5)
        self.chd_table.setHorizontalHeaderLabels(["Input", "Source", "Output", "Destination", "Status"])
        self.chd_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.chd_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        header = self.chd_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.chd_table, 1)

        buttons = QHBoxLayout()
        remove = QPushButton("Remove Selected")
        remove.clicked.connect(self._chd_remove_selected)
        buttons.addWidget(remove)
        clear = QPushButton("Clear Queue")
        clear.clicked.connect(self._chd_clear)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        self.chd_start = QPushButton("Start Queue")
        self.chd_start.clicked.connect(self._chd_start_queue)
        buttons.addWidget(self.chd_start)
        layout.addLayout(buttons)

        self.chd_log = QTextEdit()
        self.chd_log.setReadOnly(True)
        self.chd_log.setMaximumHeight(130)
        layout.addWidget(self.chd_log)
        self._refresh_chdman_status()
        return page

    def _refresh_chdman_status(self):
        installed = has_chdman()
        self.chd_tool_status.setText(f"CHDman {CHDMAN_VERSION}: {'Ready' if installed else 'Not downloaded'}")
        self.download_chdman_button.setVisible(not installed)
        self.remove_chdman_button.setVisible(installed)

    def _download_chdman_clicked(self):
        self.download_chdman_button.setEnabled(False)
        self.chd_download_progress.setValue(0)
        self.chd_download_progress.setVisible(True)

        def work(worker):
            def progress(done, total):
                worker.progress.emit(int(done * 100 / total) if total else 0)
            return download_chdman(progress)

        self.worker = ToolWorker(work, self)
        self.worker.progress.connect(self.chd_download_progress.setValue)
        self.worker.succeeded.connect(self._chdman_downloaded)
        self.worker.failed.connect(self._chdman_download_failed)
        self.worker.start()

    def _chdman_downloaded(self, _result):
        self.download_chdman_button.setEnabled(True)
        self.chd_download_progress.setVisible(False)
        self._refresh_chdman_status()

    def _chdman_download_failed(self, message):
        self.download_chdman_button.setEnabled(True)
        self.chd_download_progress.setVisible(False)
        QMessageBox.critical(self, "CHDman", message)

    def _remove_chdman_clicked(self):
        remove_chdman()
        self._refresh_chdman_status()

    def _chd_browse_output(self):
        if self.chd_output_location.currentText() == REMOTE:
            path = RemoteFilePickerDialog.get_directory(self.connection, self, title="Select MiSTer Output Folder")
        else:
            path = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if path:
            self.chd_output_dir.setText(path)

    def _chd_add_files_clicked(self):
        output_dir = self.chd_output_dir.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "CHD Converter", "Select an output folder for new jobs first.")
            return
        source_location = self.chd_input_location.currentText()
        if source_location == REMOTE:
            files = RemoteFilePickerDialog.get_open_files(self.connection, self, title="Select Disc Images from MiSTer", filters=list(CHD_INPUT_EXTS))
        else:
            files, _ = QFileDialog.getOpenFileNames(self, "Select Disc Images", filter="Disc images (*.cue *.gdi *.iso);;All files (*.*)")
        for path in files:
            self._add_chd_job(path, source_location, output_dir, self.chd_output_location.currentText())

    def _chd_add_folder_clicked(self):
        output_dir = self.chd_output_dir.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "CHD Converter", "Select an output folder for new jobs first.")
            return
        location = self.chd_input_location.currentText()
        if location == REMOTE:
            folder = RemoteFilePickerDialog.get_directory(self.connection, self, title="Select MiSTer Input Folder")
            files = self._remote_chd_files(folder) if folder else []
        else:
            folder = QFileDialog.getExistingDirectory(self, "Select Input Folder")
            files = [str(p) for p in Path(folder).rglob("*") if p.is_file() and p.suffix.lower() in CHD_INPUT_EXTS] if folder else []
        for path in files:
            self._add_chd_job(path, location, output_dir, self.chd_output_location.currentText())

    def _remote_chd_files(self, folder):
        results = []
        sftp = self.connection.client.open_sftp()
        try:
            def walk(path):
                for attr in sftp.listdir_attr(path):
                    if attr.filename in {".", ".."}:
                        continue
                    item = join_remote_path(path, attr.filename)
                    if stat.S_ISDIR(attr.st_mode):
                        walk(item)
                    elif PurePosixPath(item).suffix.lower() in CHD_INPUT_EXTS:
                        results.append(item)
            walk(folder)
        finally:
            sftp.close()
        return results

    def _add_chd_job(self, input_path, source_location, output_dir, output_location):
        name = default_output_name(input_path)
        output_path = posixpath.join(output_dir.rstrip("/"), name) if output_location == REMOTE else str(Path(output_dir) / name)
        job = {"input": input_path, "source": source_location, "output": output_path, "destination": output_location, "status": "Queued"}
        self.chd_jobs.append(job)
        self._refresh_chd_table()

    def _refresh_chd_table(self):
        self.chd_table.setRowCount(len(self.chd_jobs))
        for row, job in enumerate(self.chd_jobs):
            for col, key in enumerate(("input", "source", "output", "destination", "status")):
                self.chd_table.setItem(row, col, QTableWidgetItem(str(job[key])))

    def _chd_remove_selected(self):
        rows = sorted({idx.row() for idx in self.chd_table.selectionModel().selectedRows()}, reverse=True)
        for row in rows:
            if 0 <= row < len(self.chd_jobs):
                del self.chd_jobs[row]
        self._refresh_chd_table()

    def _chd_clear(self):
        self.chd_jobs.clear()
        self._refresh_chd_table()

    def _prepare_remote_descriptor(self, remote_path, temp_dir):
        descriptor = self._download_remote_file(remote_path, temp_dir)
        refs = descriptor_references(descriptor)
        remote_dir = posixpath.dirname(remote_path)
        for ref in refs:
            remote_ref = posixpath.normpath(posixpath.join(remote_dir, ref.replace("\\", "/")))
            local_ref = Path(temp_dir) / ref.replace("\\", "/")
            local_ref.parent.mkdir(parents=True, exist_ok=True)
            sftp = self.connection.client.open_sftp()
            try:
                sftp.get(remote_ref, str(local_ref))
            finally:
                sftp.close()
        return descriptor

    def _chd_start_queue(self):
        if not self.chd_jobs:
            QMessageBox.information(self, "CHD Converter", "The queue is empty.")
            return
        if not has_chdman():
            QMessageBox.warning(self, "CHD Converter", "Download CHDman first.")
            return
        self.chd_start.setEnabled(False)
        self.chd_log.clear()

        def work(worker):
            failures = 0
            for index, job in enumerate(self.chd_jobs):
                if job["status"] == "Completed":
                    continue
                job["status"] = "Converting"
                worker.status.emit(f"TABLE:{index}:Converting")
                try:
                    with tempfile.TemporaryDirectory(prefix="mister-companion-chd-") as tmp:
                        tmpdir = Path(tmp)
                        if job["source"] == REMOTE:
                            if PurePosixPath(job["input"]).suffix.lower() in {".cue", ".gdi"}:
                                local_input = self._prepare_remote_descriptor(job["input"], tmpdir)
                            else:
                                local_input = self._download_remote_file(job["input"], tmpdir)
                        else:
                            local_input = Path(job["input"])

                        if job["destination"] == REMOTE:
                            local_output = tmpdir / PurePosixPath(job["output"]).name
                            remote_dir = posixpath.dirname(job["output"])
                            self._ensure_remote_output_new(job["output"])
                        else:
                            local_output = Path(job["output"])

                        outputs = run_chdman(local_input, local_output, lambda line: worker.status.emit("LOG:" + line))
                        if job["destination"] == REMOTE:
                            remote_dir = posixpath.dirname(job["output"])
                            for output in outputs:
                                upload_path(self.connection, output, remote_dir, target_name=output.name, overwrite=False)
                    job["status"] = "Completed"
                    worker.status.emit(f"TABLE:{index}:Completed")
                except Exception as exc:
                    failures += 1
                    job["status"] = "Failed"
                    worker.status.emit(f"TABLE:{index}:Failed")
                    worker.status.emit(f"LOG:{PurePosixPath(job['input']).name}: {exc}")
            return failures

        self.worker = ToolWorker(work, self)
        self.worker.status.connect(self._chd_worker_status)
        self.worker.succeeded.connect(self._chd_queue_done)
        self.worker.failed.connect(self._chd_queue_failed)
        self.worker.start()

    def _chd_worker_status(self, text):
        if text.startswith("TABLE:"):
            _, row, status = text.split(":", 2)
            row = int(row)
            if 0 <= row < len(self.chd_jobs):
                self.chd_jobs[row]["status"] = status
                item = self.chd_table.item(row, 4)
                if item:
                    item.setText(status)
        elif text.startswith("LOG:"):
            self.chd_log.append(text[4:])
        else:
            self.chd_log.append(text)

    def _chd_queue_done(self, failures):
        self.chd_start.setEnabled(True)
        self._refresh_chd_table()
        if failures:
            QMessageBox.warning(self, "CHD Converter", f"Queue finished with {failures} failed job(s).")
        else:
            QMessageBox.information(self, "CHD Converter", "Queue completed successfully.")

    def _chd_queue_failed(self, message):
        self.chd_start.setEnabled(True)
        QMessageBox.critical(self, "CHD Converter", message)

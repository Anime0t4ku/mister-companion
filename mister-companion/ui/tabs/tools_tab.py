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
    QGridLayout,
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
    extract_chdman,
    has_chdman,
    remove_chdman,
    run_chdman,
)
from core.file_browser import download_path, join_remote_path, remote_exists, upload_path
from core.app_paths import generated_path
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
from core.video_converter import (
    FFMPEG_VERSION,
    convert_video,
    download_ffmpeg,
    has_ffmpeg,
    output_channel_choices,
    probe_video,
    remove_ffmpeg,
)
from ui.tab_header import create_tab_header
from ui.dialogs.remote_file_picker_dialog import RemoteFilePickerDialog


LOCAL = "This PC"
REMOTE = "MiSTer"
CHD_INPUT_EXTS = {".cue", ".gdi", ".iso"}
CHD_EXTRACT_INPUT_EXTS = {".chd"}
VIDEO_INPUT_EXTS = {
    ".3gp", ".asf", ".avi", ".flv", ".m2ts", ".m4v", ".mkv", ".mov",
    ".mp4", ".mpeg", ".mpg", ".mts", ".ogm", ".ogv", ".ts", ".vob", ".webm", ".wmv",
}
DISC_WORK_DIR = generated_path("tools", "disc_temp", default_root=Path(__file__).resolve().parents[2])


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
        self.drive_scan_worker = None
        self.chd_jobs: list[dict] = []
        self.chd_extract_jobs: list[dict] = []
        self.video_probe_info = None
        self.video_local_source = None
        self.video_source_temp = None
        self._build_ui()
        self.update_connection_state()

    def _build_ui(self):
        self.setObjectName("ToolsPage")
        self.setStyleSheet(
            """
            QWidget#ToolsPage QStackedWidget,
            QWidget#ToolsPage QWidget#ToolsHomePage,
            QWidget#ToolsPage QWidget#ToolsSubPage {
                background: transparent;
            }
            QWidget#ToolsPage QFrame#ToolsHomeCard,
            QWidget#ToolsPage QFrame#ToolWorkspace {
                background-color: palette(alternate-base);
                border: 1px solid palette(button);
                border-radius: 12px;
            }
            QWidget#ToolsPage QLabel#ToolsEntryTitle {
                font-weight: 700;
                font-size: 16px;
                background: transparent;
            }
            QWidget#ToolsPage QLabel#ToolsEntryDetail {
                background: transparent;
                color: palette(text);
            }
            """
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(0)
        self.stack = QStackedWidget()
        root.addWidget(self.stack)
        self.home_page = self._build_home()
        self.patcher_page = self._build_patcher()
        self.chd_page = self._build_chd()
        self.chd_extract_page = self._build_chd_extract()
        self.video_convert_page = self._build_video_convert()
        self.disc_to_image_page = self._build_disc_to_image()
        self.image_to_disc_page = self._build_image_to_disc()
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.patcher_page)
        self.stack.addWidget(self.chd_page)
        self.stack.addWidget(self.chd_extract_page)
        self.stack.addWidget(self.video_convert_page)
        self.stack.addWidget(self.disc_to_image_page)
        self.stack.addWidget(self.image_to_disc_page)

    def _build_home(self):
        page = QWidget()
        page.setObjectName("ToolsHomePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(create_tab_header(self.main_window, "Tools", "tools"))
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        entries = (
            ("ROM Patcher", "Apply IPS, IPS32, BPS, UPS and PPF patches. The source ROM is never overwritten.", lambda: self.stack.setCurrentWidget(self.patcher_page)),
            ("CHD Converter", "Queue CUE/GDI/ISO to CHD conversions using PC or MiSTer input and output locations.", lambda: self.stack.setCurrentWidget(self.chd_page)),
            ("CHD Extractor", "Extract CHD images to CUE/BIN, GDI or ISO using PC or MiSTer input and output locations.", lambda: self.stack.setCurrentWidget(self.chd_extract_page)),
            ("MiSTer Video Converter", "Create PAL or NTSC DVD-compatible MPEG-2 video for the MiSTer DVD core.", lambda: self.stack.setCurrentWidget(self.video_convert_page)),
            ("Disc to Image", "Rip a physical game CD to BIN/CUE, optionally convert it to CHD, then save it to PC or MiSTer.", lambda: self._open_disc_page(self.disc_to_image_page)),
            ("Image to Disc", "Burn BIN/CUE game discs or MSU-1 / MD+ folders from PC or MiSTer using the PC optical drive.", lambda: self._open_disc_page(self.image_to_disc_page)),
        )
        for index, (name, detail_text, slot) in enumerate(entries):
            card = QFrame()
            card.setObjectName("ToolsHomeCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 16, 18, 16)
            card_layout.setSpacing(8)
            heading = QLabel(name)
            heading.setObjectName("ToolsEntryTitle")
            card_layout.addWidget(heading)
            detail = QLabel(detail_text)
            detail.setObjectName("ToolsEntryDetail")
            detail.setWordWrap(True)
            card_layout.addWidget(detail, 1)
            action_row = QHBoxLayout()
            action_row.addStretch(1)
            button = QPushButton("Open")
            button.clicked.connect(slot)
            action_row.addWidget(button)
            card_layout.addLayout(action_row)
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        layout.addStretch(1)
        return page

    def _tool_workspace_page(self, title_text):
        page = QWidget()
        page.setObjectName("ToolsSubPage")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)
        header = QHBoxLayout()
        title = QLabel(title_text)
        title.setStyleSheet("font-weight: 700; font-size: 19px;")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self._back_button())
        outer.addLayout(header)
        workspace = QFrame()
        workspace.setObjectName("ToolWorkspace")
        content = QVBoxLayout(workspace)
        content.setContentsMargins(18, 18, 18, 18)
        content.setSpacing(12)
        outer.addWidget(workspace, 1)
        return page, content

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
        page, layout = self._tool_workspace_page("ROM Patcher")
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
        self.patch_progress = QProgressBar()
        self.patch_progress.setRange(0, 100)
        self.patch_progress.setValue(0)
        self.patch_progress.setVisible(False)
        layout.addWidget(self.patch_progress)
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
        for combo_name in ("rom_location", "patch_location", "output_location", "chd_input_location", "chd_output_location", "chd_extract_input_location", "chd_extract_output_location", "video_input_location", "video_output_location", "disc_output_location", "burn_source_location"):
            combo = getattr(self, combo_name, None)
            if combo:
                self._sync_location_combo(combo)
        if hasattr(self, "chd_tool_status"):
            self._refresh_chdman_status()
        if hasattr(self, "disc_cdrdao_status"):
            self._refresh_cdrdao_status()
        if hasattr(self, "video_ffmpeg_status"):
            self._refresh_ffmpeg_status()

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

    @staticmethod
    def _transfer_percent(done, total):
        return max(0, min(100, int(done * 100 / total))) if total else 0

    def _download_remote_file(self, remote_path, temp_dir, worker=None, status_prefix="TRANSFER:"):
        name = PurePosixPath(remote_path).name

        def message(text):
            if worker:
                worker.status.emit(f"LOG:{text}")

        def progress(done, total):
            if worker:
                percent = self._transfer_percent(done, total)
                worker.progress.emit(percent)
                worker.status.emit(f"{status_prefix}Downloading {name} — {percent}%")

        return Path(download_path(
            self.connection, remote_path, temp_dir,
            progress_callback=progress if worker else None,
            message_callback=message if worker else None,
            overwrite=False,
        ))

    def _upload_remote_file(self, local_path, remote_dir, worker=None, status_prefix="TRANSFER:", target_name=None):
        local_path = Path(local_path)
        name = target_name or local_path.name

        def message(text):
            if worker:
                worker.status.emit(f"LOG:{text}")

        def progress(done, total):
            if worker:
                percent = self._transfer_percent(done, total)
                worker.progress.emit(percent)
                worker.status.emit(f"{status_prefix}Uploading {name} — {percent}%")

        return upload_path(
            self.connection, local_path, remote_dir,
            progress_callback=progress if worker else None,
            message_callback=message if worker else None,
            target_name=name, overwrite=False,
        )

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
        self.patch_progress.setValue(0)
        self.patch_progress.setVisible(source_location == REMOTE or patch_location == REMOTE or output_location == REMOTE)

        def work(worker):
            with tempfile.TemporaryDirectory(prefix="mister-companion-patch-") as tmp:
                tmpdir = Path(tmp)
                worker.status.emit("Preparing source ROM...")
                local_source = self._download_remote_file(source, tmpdir, worker) if source_location == REMOTE else Path(source)
                worker.status.emit("Preparing patch...")
                local_patch = self._download_remote_file(patch, tmpdir, worker) if patch_location == REMOTE else Path(patch)
                if output_location == REMOTE:
                    self._ensure_remote_output_new(output)
                    local_output = tmpdir / PurePosixPath(output).name
                else:
                    local_output = Path(output)
                worker.status.emit("Applying patch...")
                result = apply_patch(local_source, local_patch, local_output)
                if output_location == REMOTE:
                    worker.status.emit("Uploading patched ROM to MiSTer...")
                    self._upload_remote_file(local_output, posixpath.dirname(output), worker, target_name=PurePosixPath(output).name)
                return result

        self.worker = ToolWorker(work, self)
        self.worker.status.connect(self._patch_worker_status)
        self.worker.progress.connect(self.patch_progress.setValue)
        self.worker.succeeded.connect(self._patch_done)
        self.worker.failed.connect(self._patch_failed)
        self.worker.start()

    def _patch_worker_status(self, text):
        if text.startswith("TRANSFER:"):
            self.patch_status.setText(text[len("TRANSFER:"):])
        elif text.startswith("LOG:"):
            self.patch_status.setText(text[len("LOG:"):])
        else:
            self.patch_status.setText(text)

    def _patch_done(self, result):
        self.patch_button.setEnabled(True)
        if self.patch_progress.isVisible():
            self.patch_progress.setValue(100)
        self.patch_status.setText(f"Complete. {result['format']} patch applied; source ROM was not modified.")
        QMessageBox.information(self, "ROM Patcher", "Patch applied successfully.\n\nThe original ROM was not modified.")

    def _patch_failed(self, message):
        self.patch_button.setEnabled(True)
        self.patch_status.setText("Patch failed.")
        QMessageBox.critical(self, "ROM Patcher", message)

    def _build_video_convert(self):
        page, layout = self._tool_workspace_page("MiSTer Video Converter")
        description = QLabel(
            "Create DVD-compatible MPEG-2 videos for the MiSTer DVD core. HD and 4K sources are supported, "
            "and detected HDR video is automatically converted to SDR."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        tool_row = QHBoxLayout()
        self.video_ffmpeg_status = QLabel()
        tool_row.addWidget(self.video_ffmpeg_status, 1)
        self.video_download_ffmpeg = QPushButton("Download FFmpeg")
        self.video_download_ffmpeg.clicked.connect(self._download_ffmpeg_clicked)
        tool_row.addWidget(self.video_download_ffmpeg)
        self.video_remove_ffmpeg = QPushButton("Remove")
        self.video_remove_ffmpeg.clicked.connect(self._remove_ffmpeg_clicked)
        tool_row.addWidget(self.video_remove_ffmpeg)
        layout.addLayout(tool_row)
        self.video_ffmpeg_progress = QProgressBar()
        self.video_ffmpeg_progress.setRange(0, 100)
        self.video_ffmpeg_progress.setVisible(False)
        layout.addWidget(self.video_ffmpeg_progress)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Source video:"))
        self.video_input_location = self._location_combo()
        input_row.addWidget(self.video_input_location)
        self.video_input_path = QLineEdit()
        self.video_input_path.setReadOnly(True)
        input_row.addWidget(self.video_input_path, 1)
        self.video_browse_input = QPushButton("Browse")
        self.video_browse_input.clicked.connect(self._video_browse_input)
        input_row.addWidget(self.video_browse_input)
        layout.addLayout(input_row)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output MPEG:"))
        self.video_output_location = self._location_combo()
        output_row.addWidget(self.video_output_location)
        self.video_output_path = QLineEdit()
        output_row.addWidget(self.video_output_path, 1)
        self.video_browse_output = QPushButton("Browse")
        self.video_browse_output.clicked.connect(self._video_browse_output_clicked)
        output_row.addWidget(self.video_browse_output)
        layout.addLayout(output_row)

        standard_row = QHBoxLayout()
        standard_row.addWidget(QLabel("Output format:"))
        self.video_standard = QComboBox()
        self.video_standard.addItem("NTSC DVD (720×480)", "ntsc")
        self.video_standard.addItem("PAL DVD (720×576)", "pal")
        standard_row.addWidget(self.video_standard)
        standard_row.addStretch(1)
        layout.addLayout(standard_row)

        audio_row = QHBoxLayout()
        audio_row.addWidget(QLabel("Audio source:"))
        self.video_audio_stream = QComboBox()
        self.video_audio_stream.setEnabled(False)
        self.video_audio_stream.currentIndexChanged.connect(self._video_audio_changed)
        audio_row.addWidget(self.video_audio_stream, 1)
        layout.addLayout(audio_row)

        channels_row = QHBoxLayout()
        channels_row.addWidget(QLabel("Output channels:"))
        self.video_audio_channels = QComboBox()
        self.video_audio_channels.setEnabled(False)
        channels_row.addWidget(self.video_audio_channels, 1)
        layout.addLayout(channels_row)

        subtitle_row = QHBoxLayout()
        subtitle_row.addWidget(QLabel("Burn in subtitles:"))
        self.video_subtitle_stream = QComboBox()
        self.video_subtitle_stream.addItem("None", None)
        self.video_subtitle_stream.setEnabled(False)
        subtitle_row.addWidget(self.video_subtitle_stream, 1)
        layout.addLayout(subtitle_row)

        self.video_source_info = QLabel("Select a source video to inspect its audio and subtitle streams.")
        self.video_source_info.setWordWrap(True)
        layout.addWidget(self.video_source_info)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.video_start = QPushButton("Convert Video")
        self.video_start.setEnabled(False)
        self.video_start.clicked.connect(self._video_start_clicked)
        action_row.addWidget(self.video_start)
        layout.addLayout(action_row)

        self.video_status = QLabel("")
        self.video_status.setWordWrap(True)
        layout.addWidget(self.video_status)
        self.video_progress = QProgressBar()
        self.video_progress.setRange(0, 100)
        self.video_progress.setValue(0)
        self.video_progress.setVisible(False)
        layout.addWidget(self.video_progress)
        self.video_log = QTextEdit()
        self.video_log.setReadOnly(True)
        self.video_log.setMaximumHeight(170)
        layout.addWidget(self.video_log)
        layout.addStretch(1)

        self.video_input_location.currentTextChanged.connect(self._video_source_location_changed)
        self.video_output_location.currentTextChanged.connect(self._video_output_location_changed)
        self.video_output_path.textChanged.connect(self._video_update_start_state)
        self._refresh_ffmpeg_status()
        return page

    def _refresh_ffmpeg_status(self):
        installed = has_ffmpeg()
        self.video_ffmpeg_status.setText(f"FFmpeg {FFMPEG_VERSION}: {'Ready' if installed else 'Not downloaded'}")
        self.video_download_ffmpeg.setVisible(not installed)
        self.video_remove_ffmpeg.setVisible(installed)
        self._video_update_start_state()

    def _set_ffmpeg_download_state(self, downloading):
        self.video_download_ffmpeg.setEnabled(not downloading)
        self.video_remove_ffmpeg.setEnabled(not downloading)
        self.video_ffmpeg_progress.setVisible(downloading)
        if downloading:
            self.video_ffmpeg_progress.setValue(0)

    def _download_ffmpeg_clicked(self):
        self._set_ffmpeg_download_state(True)

        def work(worker):
            return download_ffmpeg(lambda done, total: worker.progress.emit(self._transfer_percent(done, total)))

        self.worker = ToolWorker(work, self)
        self.worker.progress.connect(self.video_ffmpeg_progress.setValue)
        self.worker.succeeded.connect(self._ffmpeg_downloaded)
        self.worker.failed.connect(self._ffmpeg_download_failed)
        self.worker.start()

    def _ffmpeg_downloaded(self, _result):
        self._set_ffmpeg_download_state(False)
        self.video_ffmpeg_progress.setValue(100)
        self._refresh_ffmpeg_status()

    def _ffmpeg_download_failed(self, message):
        self._set_ffmpeg_download_state(False)
        QMessageBox.critical(self, "FFmpeg", message)

    def _remove_ffmpeg_clicked(self):
        remove_ffmpeg()
        self._refresh_ffmpeg_status()

    def _cleanup_video_source(self):
        self.video_local_source = None
        if self.video_source_temp is not None:
            try:
                self.video_source_temp.cleanup()
            except Exception:
                pass
            self.video_source_temp = None

    def _video_source_location_changed(self, _text=None):
        if not hasattr(self, "video_input_path"):
            return
        self._cleanup_video_source()
        self.video_probe_info = None
        self.video_input_path.clear()
        self.video_audio_stream.clear()
        self.video_audio_stream.setEnabled(False)
        self.video_audio_channels.clear()
        self.video_audio_channels.setEnabled(False)
        self.video_subtitle_stream.clear()
        self.video_subtitle_stream.addItem("None", None)
        self.video_subtitle_stream.setEnabled(False)
        self.video_source_info.setText("Select a source video to inspect its audio and subtitle streams.")
        self._video_update_start_state()

    def _video_output_location_changed(self, _text=None):
        if not hasattr(self, "video_output_path"):
            return
        self.video_output_path.clear()
        self._video_suggest_output()

    def _video_browse_input(self):
        if not has_ffmpeg():
            QMessageBox.warning(self, "MiSTer Video Converter", "Download FFmpeg first.")
            return
        if self.video_input_location.currentText() == REMOTE:
            path = RemoteFilePickerDialog.get_open_file(
                self.connection, self, title="Select Video from MiSTer", filters=sorted(VIDEO_INPUT_EXTS)
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Video", filter="Video files (*.3gp *.asf *.avi *.flv *.m2ts *.m4v *.mkv *.mov *.mp4 *.mpeg *.mpg *.mts *.ogm *.ogv *.ts *.vob *.webm *.wmv);;All files (*.*)"
            )
        if not path:
            return
        self._cleanup_video_source()
        self.video_probe_info = None
        self.video_input_path.setText(path)
        self.video_output_path.clear()
        self._video_suggest_output()
        self._video_prepare_source(path, self.video_input_location.currentText())

    def _video_default_output_name(self):
        raw = self.video_input_path.text().strip().replace("\\", "/")
        stem = PurePosixPath(raw).stem or "converted-video"
        return f"{stem}-MiSTer-DVD.mpg"

    def _video_suggest_output(self):
        if not self.video_input_path.text().strip() or self.video_output_path.text().strip():
            return
        name = self._video_default_output_name()
        if self.video_output_location.currentText() == LOCAL and self.video_input_location.currentText() == LOCAL:
            self.video_output_path.setText(str(Path(self.video_input_path.text()).with_name(name)))
        elif self.video_output_location.currentText() == REMOTE and self.video_input_location.currentText() == REMOTE:
            self.video_output_path.setText(posixpath.join(posixpath.dirname(self.video_input_path.text()), name))

    def _video_browse_output_clicked(self):
        default_name = self._video_default_output_name()
        if self.video_output_location.currentText() == REMOTE:
            path = RemoteFilePickerDialog.get_save_file(
                self.connection, self, title="Save MPEG Video on MiSTer", default_name=default_name
            )
        else:
            start = self.video_output_path.text().strip() or default_name
            path, _ = QFileDialog.getSaveFileName(self, "Save MPEG Video", start, "MPEG video (*.mpg);;All files (*.*)")
        if path:
            if not path.lower().endswith((".mpg", ".mpeg")):
                path += ".mpg"
            self.video_output_path.setText(path)

    def _video_prepare_source(self, path, location):
        self.video_browse_input.setEnabled(False)
        self.video_input_location.setEnabled(False)
        self.video_start.setEnabled(False)
        self.video_progress.setVisible(True)
        self.video_progress.setRange(0, 100)
        self.video_progress.setValue(0)
        self.video_status.setText("Inspecting video streams...")
        self.video_log.clear()
        if location == REMOTE:
            self.video_source_temp = tempfile.TemporaryDirectory(prefix="mister-companion-video-source-")

        def work(worker):
            if location == REMOTE:
                local_path = self._download_remote_file(
                    path, Path(self.video_source_temp.name), worker, status_prefix="VIDEOSTATUS:"
                )
            else:
                local_path = Path(path)
            worker.status.emit("VIDEOSTATUS:Inspecting audio and subtitle streams...")
            info = probe_video(local_path)
            return {"path": local_path, "probe": info}

        self.worker = ToolWorker(work, self)
        self.worker.progress.connect(self.video_progress.setValue)
        self.worker.status.connect(self._video_worker_status)
        self.worker.succeeded.connect(self._video_source_ready)
        self.worker.failed.connect(self._video_source_failed)
        self.worker.start()

    def _video_source_ready(self, result):
        self.video_browse_input.setEnabled(True)
        self.video_input_location.setEnabled(True)
        self.video_progress.setValue(100)
        self.video_progress.setVisible(False)
        self.video_local_source = Path(result["path"])
        self.video_probe_info = result["probe"]
        self.video_audio_stream.clear()
        for stream in self.video_probe_info["audio"]:
            self.video_audio_stream.addItem(stream["label"], stream["ordinal"])
        self.video_audio_stream.setEnabled(bool(self.video_probe_info["audio"]))
        self.video_subtitle_stream.clear()
        self.video_subtitle_stream.addItem("None", None)
        for stream in self.video_probe_info["subtitles"]:
            self.video_subtitle_stream.addItem(stream["label"], stream["ordinal"])
        self.video_subtitle_stream.setEnabled(bool(self.video_probe_info["subtitles"]))
        self._video_audio_changed()
        width = self.video_probe_info.get("width", 0)
        height = self.video_probe_info.get("height", 0)
        hdr_note = " HDR detected; it will automatically be converted to SDR." if self.video_probe_info.get("hdr") else " SDR source."
        self.video_source_info.setText(
            f"Source: {width}×{height}.{hdr_note} Select the audio track, output channels and optional subtitle track."
        )
        self.video_status.setText("Video streams ready.")
        self._video_update_start_state()

    def _video_source_failed(self, message):
        self.video_browse_input.setEnabled(True)
        self.video_input_location.setEnabled(True)
        self.video_progress.setVisible(False)
        self.video_status.setText("Could not inspect the selected video.")
        self._cleanup_video_source()
        self.video_probe_info = None
        self._video_update_start_state()
        QMessageBox.critical(self, "MiSTer Video Converter", message)

    def _video_audio_changed(self, _index=None):
        self.video_audio_channels.clear()
        if not self.video_probe_info or self.video_audio_stream.currentIndex() < 0:
            self.video_audio_channels.setEnabled(False)
            return
        ordinal = self.video_audio_stream.currentData()
        stream = self.video_probe_info["audio"][int(ordinal)]
        for label, channels in output_channel_choices(stream):
            self.video_audio_channels.addItem(label, channels)
        self.video_audio_channels.setEnabled(self.video_audio_channels.count() > 0)

    def _video_update_start_state(self):
        if not hasattr(self, "video_start"):
            return
        ready = bool(
            has_ffmpeg() and self.video_probe_info and self.video_local_source
            and self.video_output_path.text().strip() and self.video_audio_stream.currentIndex() >= 0
        )
        self.video_start.setEnabled(ready)

    def _video_start_clicked(self):
        if not self.video_probe_info or not self.video_local_source:
            QMessageBox.warning(self, "MiSTer Video Converter", "Select and inspect a source video first.")
            return
        output = self.video_output_path.text().strip()
        if not output:
            QMessageBox.warning(self, "MiSTer Video Converter", "Select an output MPEG file first.")
            return
        destination = self.video_output_location.currentText()
        if destination == REMOTE and not self._is_remote_allowed():
            QMessageBox.warning(self, "MiSTer Video Converter", "Connect to MiSTer in Online mode first.")
            return
        if destination == LOCAL and Path(output).exists():
            QMessageBox.warning(self, "MiSTer Video Converter", "The output file already exists. Choose a new file name.")
            return

        self.video_start.setEnabled(False)
        self.video_browse_input.setEnabled(False)
        self.video_browse_output.setEnabled(False)
        self.video_input_location.setEnabled(False)
        self.video_output_location.setEnabled(False)
        self.video_log.clear()
        self.video_progress.setRange(0, 0)
        self.video_progress.setVisible(True)
        self.video_status.setText("Starting FFmpeg and preparing video filters...")
        standard = self.video_standard.currentData()
        audio_ordinal = int(self.video_audio_stream.currentData())
        subtitle_ordinal = self.video_subtitle_stream.currentData()
        channels = self.video_audio_channels.currentData()

        def work(worker):
            def conversion_progress(percent, speed):
                suffix = f" – {speed}" if speed else ""
                worker.status.emit(f"VIDEOSTATUS:Converting video – {percent}%{suffix}")
                worker.progress.emit(percent)

            def conversion_log(line):
                worker.status.emit("LOG:" + line)

            worker.status.emit("LOG:Preparing DVD conversion settings...")
            if self.video_probe_info.get("hdr"):
                worker.status.emit("LOG:Initialising HDR-to-SDR tone mapping...")
            if subtitle_ordinal is not None:
                worker.status.emit("LOG:Initialising embedded subtitle renderer...")
            worker.status.emit("LOG:Starting FFmpeg and waiting for the first encoded frame...")

            if destination == REMOTE:
                self._ensure_remote_output_new(output)
                with tempfile.TemporaryDirectory(prefix="mister-companion-video-output-") as tmp:
                    local_output = Path(tmp) / PurePosixPath(output).name
                    result = convert_video(
                        self.video_local_source, local_output, self.video_probe_info, standard,
                        audio_ordinal, subtitle_ordinal, channels, conversion_progress, conversion_log,
                    )
                    worker.status.emit("VIDEOSTATUS:Uploading converted video to MiSTer...")
                    self._upload_remote_file(
                        result, posixpath.dirname(output), worker,
                        status_prefix="VIDEOSTATUS:", target_name=PurePosixPath(output).name,
                    )
                return output
            result = convert_video(
                self.video_local_source, Path(output), self.video_probe_info, standard,
                audio_ordinal, subtitle_ordinal, channels, conversion_progress, conversion_log,
            )
            return str(result)

        self.worker = ToolWorker(work, self)
        self.worker.progress.connect(self.video_progress.setValue)
        self.worker.status.connect(self._video_worker_status)
        self.worker.succeeded.connect(self._video_conversion_done)
        self.worker.failed.connect(self._video_conversion_failed)
        self.worker.start()

    def _video_worker_status(self, text):
        if text.startswith("VIDEOBUSY:"):
            self.video_progress.setRange(0, 0)
            self.video_status.setText(text[len("VIDEOBUSY:"):])
        elif text.startswith("VIDEOSTATUS:"):
            if self.video_progress.minimum() == 0 and self.video_progress.maximum() == 0:
                self.video_progress.setRange(0, 100)
            self.video_status.setText(text[len("VIDEOSTATUS:"):])
        elif text.startswith("LOG:"):
            self.video_log.append(text[len("LOG:"):])
        else:
            self.video_log.append(text)

    def _video_conversion_done(self, output):
        self.video_browse_input.setEnabled(True)
        self.video_browse_output.setEnabled(True)
        self.video_input_location.setEnabled(True)
        self.video_output_location.setEnabled(True)
        self.video_progress.setRange(0, 100)
        self.video_progress.setValue(100)
        self.video_status.setText("Conversion complete – 100%")
        self._video_update_start_state()
        QMessageBox.information(self, "MiSTer Video Converter", f"Video converted successfully.\n\n{output}")

    def _video_conversion_failed(self, message):
        self.video_browse_input.setEnabled(True)
        self.video_browse_output.setEnabled(True)
        self.video_input_location.setEnabled(True)
        self.video_output_location.setEnabled(True)
        self.video_progress.setRange(0, 100)
        self.video_progress.setValue(0)
        self.video_status.setText("Conversion failed.")
        self._video_update_start_state()
        QMessageBox.critical(self, "MiSTer Video Converter", message)

    
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
        page, layout = self._tool_workspace_page("Disc to Image")
        self.disc_cdrdao_status, self.disc_install_cdrdao, self.disc_remove_cdrdao, self.disc_cdrdao_progress = self._cdrdao_controls(layout)

        row = QHBoxLayout()
        row.addWidget(QLabel("Optical drive:"))
        self.disc_read_drive = QComboBox()
        row.addWidget(self.disc_read_drive, 1)
        self.disc_read_refresh = QPushButton("Refresh")
        self.disc_read_refresh.clicked.connect(self._refresh_disc_drives)
        row.addWidget(self.disc_read_refresh)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Output CUE:"))
        self.disc_output_location = self._location_combo()
        row.addWidget(self.disc_output_location)
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
        page, layout = self._tool_workspace_page("Image to Disc")
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
        self.burn_source_location = self._location_combo()
        row.addWidget(self.burn_source_location)
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
        self.disc_write_refresh = QPushButton("Refresh")
        self.disc_write_refresh.clicked.connect(self._refresh_disc_drives)
        row.addWidget(self.disc_write_refresh)
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
        # Drive enumeration (notably cdrdao scanbus) may wait while an optical
        # drive is busy.  Never run it on the Qt GUI thread.
        if self.drive_scan_worker is not None and self.drive_scan_worker.isRunning():
            return

        for button_name in ("disc_read_refresh", "disc_write_refresh"):
            button = getattr(self, button_name, None)
            if button is not None:
                button.setEnabled(False)
        for combo_name in ("disc_read_drive", "disc_write_drive"):
            combo = getattr(self, combo_name, None)
            if combo is not None and combo.count() == 0:
                combo.addItem("Scanning optical drives...", None)

        def work(_worker):
            if not disc_backend_ready():
                return []
            return scan_drives()

        self.drive_scan_worker = ToolWorker(work, self)
        self.drive_scan_worker.succeeded.connect(self._disc_drives_scanned)
        self.drive_scan_worker.failed.connect(self._disc_drive_scan_failed)
        self.drive_scan_worker.finished.connect(self._disc_drive_scan_finished)
        self.drive_scan_worker.start()

    def _disc_drives_scanned(self, drives):
        drives = list(drives or [])
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

    def _disc_drive_scan_failed(self, _message):
        self._disc_drives_scanned([])

    def _disc_drive_scan_finished(self):
        for button_name in ("disc_read_refresh", "disc_write_refresh"):
            button = getattr(self, button_name, None)
            if button is not None:
                button.setEnabled(True)

    def _browse_disc_output(self):
        if self.disc_output_location.currentText() == REMOTE:
            default_name = PurePosixPath(self.disc_output_cue.text().strip()).name or "disc.cue"
            path = RemoteFilePickerDialog.get_save_file(
                self.connection, self, title="Save Disc Image on MiSTer",
                default_name=default_name,
            )
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Disc Image", self.disc_output_cue.text().strip(), "CUE sheet (*.cue)"
            )
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
        destination = self.disc_output_location.currentText()
        if not device or not output:
            QMessageBox.warning(self, "Disc to Image", "Select an optical drive and output CUE file first.")
            return
        if destination == REMOTE and not self._is_remote_allowed():
            QMessageBox.warning(self, "Disc to Image", "Connect to MiSTer in Online mode first.")
            return
        if self.disc_convert_chd.isChecked() and not has_chdman():
            QMessageBox.warning(self, "Disc to Image", "Download CHDman from CHD Converter before enabling CHD conversion.")
            return
        self.disc_rip_button.setEnabled(False)
        self.disc_rip_progress.setRange(0, 100)
        self.disc_rip_progress.setValue(0)
        self.disc_rip_progress.setVisible(True)
        self.disc_rip_status.setVisible(False)
        self.disc_rip_log.clear()

        convert = self.disc_convert_chd.isChecked()
        remove_bin_cue = self.disc_remove_bin.isChecked()

        def work(worker):
            def rip_log(line):
                worker.status.emit("LOG:" + line)

            def rip_progress(percent, message):
                worker.progress.emit(percent)
                worker.status.emit("RIPSTATUS:" + message)

            DISC_WORK_DIR.mkdir(parents=True, exist_ok=True)
            if destination == REMOTE:
                remote_cue = output
                remote_dir = posixpath.dirname(remote_cue)
                base_name = PurePosixPath(remote_cue).stem
                with tempfile.TemporaryDirectory(prefix="rip-", dir=str(DISC_WORK_DIR)) as tmp:
                    local_cue = Path(tmp) / f"{base_name}.cue"
                    cue, bin_path, toc = rip_disc(device, local_cue, rip_log, progress_callback=rip_progress)
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
                            elif "error" in line.lower():
                                worker.status.emit("LOG:" + line)

                        run_chdman(cue, chd, chd_log)
                        worker.progress.emit(100)
                        worker.status.emit("RIPSTATUS:CHD conversion complete — 100%")

                    upload_files = []
                    if not convert or not remove_bin_cue:
                        upload_files.extend([cue, bin_path])
                    if chd is not None:
                        upload_files.append(chd)
                    for local_file in upload_files:
                        remote_target = posixpath.join(remote_dir, local_file.name)
                        self._ensure_remote_output_new(remote_target)
                    worker.status.emit("LOG:Transferring completed image to MiSTer...")
                    for local_file in upload_files:
                        self._upload_remote_file(local_file, remote_dir, worker, status_prefix="RIPSTATUS:", target_name=local_file.name)
                    return posixpath.join(remote_dir, (chd.name if chd is not None else cue.name))
            else:
                cue, bin_path, toc = rip_disc(device, output, rip_log, progress_callback=rip_progress)
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
                        elif "error" in line.lower():
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
            return
        elif text.startswith("LOG:"):
            self.disc_rip_log.append(text[len("LOG:"):])
        else:
            self.disc_rip_log.append(text)

    def _rip_disc_done(self, output):
        self.disc_rip_button.setEnabled(True)
        self.disc_rip_progress.setValue(100)
        QMessageBox.information(self, "Disc to Image", f"Disc image created successfully.\n\n{output}")

    def _rip_disc_failed(self, message):
        self.disc_rip_button.setEnabled(True)
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
        remote = self.burn_source_location.currentText() == REMOTE
        if self.burn_mode.currentIndex() == 1:
            if remote:
                path = RemoteFilePickerDialog.get_directory(self.connection, self, title="Select MSU-1 / MD+ Folder on MiSTer")
            else:
                path = QFileDialog.getExistingDirectory(self, "Select MSU-1 / MD+ Folder")
        else:
            if remote:
                path = RemoteFilePickerDialog.get_open_file(self.connection, self, title="Select CUE Image from MiSTer", filters=[".cue"])
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
        source_location = self.burn_source_location.currentText()
        if not device or not source:
            QMessageBox.warning(self, "Image to Disc", "Select an optical writer and source first.")
            return
        if source_location == REMOTE and not self._is_remote_allowed():
            QMessageBox.warning(self, "Image to Disc", "Connect to MiSTer in Online mode first.")
            return
        data_mode = self.burn_mode.currentIndex() == 1
        if data_mode and source_location == LOCAL:
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

            DISC_WORK_DIR.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="burn-", dir=str(DISC_WORK_DIR)) as tmp:
                tmpdir = Path(tmp)
                local_source = Path(source)
                if source_location == REMOTE:
                    worker.status.emit("BURNBUSY:Downloading source from MiSTer...")
                    if data_mode:
                        local_source = self._download_remote_folder(source, tmpdir, worker, status_prefix="BURNSTATUS:")
                        if not any(p.is_file() for p in local_source.iterdir()):
                            raise DiscToolError("The selected MSU-1 / MD+ folder has no files at its root.")
                    else:
                        local_source = self._prepare_remote_descriptor(source, tmpdir, worker, status_prefix="BURNSTATUS:")

                if data_mode:
                    burn_iso9660_folder(
                        device, local_source, speed=speed, volume_id=disc_label or None,
                        log_callback=log, progress_callback=progress
                    )
                else:
                    burn_cue(
                        device, local_source, speed=speed, log_callback=log, progress_callback=progress
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

    
    def _download_remote_folder(self, remote_folder, temp_dir, worker=None, status_prefix="TRANSFER:"):
        local_root = Path(temp_dir) / PurePosixPath(remote_folder.rstrip("/")).name
        local_root.mkdir(parents=True, exist_ok=True)
        sftp = self.connection.client.open_sftp()
        try:
            def walk(remote_dir, local_dir):
                for attr in sftp.listdir_attr(remote_dir):
                    if attr.filename in {".", ".."}:
                        continue
                    remote_item = join_remote_path(remote_dir, attr.filename)
                    local_item = local_dir / attr.filename
                    if stat.S_ISDIR(attr.st_mode):
                        local_item.mkdir(parents=True, exist_ok=True)
                        walk(remote_item, local_item)
                    else:
                        local_item.parent.mkdir(parents=True, exist_ok=True)
                        if worker:
                            worker.status.emit(f"LOG:Downloading {attr.filename}...")

                        def progress(done, total, name=attr.filename):
                            if worker:
                                percent = self._transfer_percent(done, total)
                                worker.progress.emit(percent)
                                worker.status.emit(f"{status_prefix}Downloading {name} — {percent}%")

                        sftp.get(remote_item, str(local_item), callback=progress if worker else None)
            walk(remote_folder, local_root)
        finally:
            sftp.close()
        return local_root

    def _build_chd(self):
        page, layout = self._tool_workspace_page("CHD Converter")
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

        self.chd_remove_source = QCheckBox("Remove BIN/CUE after successful conversion")
        self.chd_remove_source.setToolTip("For CUE jobs, remove the CUE and only the BIN files referenced by that CUE after the CHD has been created successfully.")
        layout.addWidget(self.chd_remove_source)

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
        self.chd_transfer_status = QLabel("")
        self.chd_transfer_status.setVisible(False)
        layout.addWidget(self.chd_transfer_status)
        self.chd_transfer_progress = QProgressBar()
        self.chd_transfer_progress.setRange(0, 100)
        self.chd_transfer_progress.setValue(0)
        self.chd_transfer_progress.setVisible(False)
        layout.addWidget(self.chd_transfer_progress)

        self.chd_log = QTextEdit()
        self.chd_log.setReadOnly(True)
        self.chd_log.setMaximumHeight(130)
        layout.addWidget(self.chd_log)
        self._refresh_chdman_status()
        return page

    def _refresh_chdman_status(self):
        installed = has_chdman()
        text = f"CHDman {CHDMAN_VERSION}: {'Ready' if installed else 'Not downloaded'}"
        self.chd_tool_status.setText(text)
        self.download_chdman_button.setVisible(not installed)
        self.remove_chdman_button.setVisible(installed)
        if hasattr(self, "chd_extract_tool_status"):
            self.chd_extract_tool_status.setText(text)
        if hasattr(self, "chd_extract_download_chdman_button"):
            self.chd_extract_download_chdman_button.setVisible(not installed)
        if hasattr(self, "chd_extract_remove_chdman_button"):
            self.chd_extract_remove_chdman_button.setVisible(installed)

    def _set_chdman_download_state(self, downloading):
        self.download_chdman_button.setEnabled(not downloading)
        self.chd_download_progress.setVisible(downloading)
        if downloading:
            self.chd_download_progress.setValue(0)
        if hasattr(self, "chd_extract_download_chdman_button"):
            self.chd_extract_download_chdman_button.setEnabled(not downloading)
        if hasattr(self, "chd_extract_download_progress"):
            self.chd_extract_download_progress.setVisible(downloading)
            if downloading:
                self.chd_extract_download_progress.setValue(0)

    def _update_chdman_download_progress(self, value):
        self.chd_download_progress.setValue(value)
        if hasattr(self, "chd_extract_download_progress"):
            self.chd_extract_download_progress.setValue(value)

    def _download_chdman_clicked(self):
        self._set_chdman_download_state(True)

        def work(worker):
            def progress(done, total):
                worker.progress.emit(int(done * 100 / total) if total else 0)
            return download_chdman(progress)

        self.worker = ToolWorker(work, self)
        self.worker.progress.connect(self._update_chdman_download_progress)
        self.worker.succeeded.connect(self._chdman_downloaded)
        self.worker.failed.connect(self._chdman_download_failed)
        self.worker.start()

    def _chdman_downloaded(self, _result):
        self._set_chdman_download_state(False)
        self._refresh_chdman_status()

    def _chdman_download_failed(self, message):
        self._set_chdman_download_state(False)
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

    def _prepare_remote_descriptor(self, remote_path, temp_dir, worker=None, status_prefix="TRANSFER:"):
        descriptor = self._download_remote_file(remote_path, temp_dir, worker, status_prefix=status_prefix)
        refs = descriptor_references(descriptor)
        remote_dir = posixpath.dirname(remote_path)
        for ref in refs:
            remote_ref = posixpath.normpath(posixpath.join(remote_dir, ref.replace("\\", "/")))
            local_ref = Path(temp_dir) / ref.replace("\\", "/")
            local_ref.parent.mkdir(parents=True, exist_ok=True)
            name = PurePosixPath(remote_ref).name
            sftp = self.connection.client.open_sftp()
            try:
                if worker:
                    worker.status.emit(f"LOG:Downloading {name}...")

                def progress(done, total, filename=name):
                    if worker:
                        percent = self._transfer_percent(done, total)
                        worker.progress.emit(percent)
                        worker.status.emit(f"{status_prefix}Downloading {filename} — {percent}%")

                sftp.get(remote_ref, str(local_ref), callback=progress if worker else None)
            finally:
                sftp.close()
        return descriptor

    def _remove_local_cue_sources(self, cue_path, worker=None):
        cue_path = Path(cue_path)
        refs = descriptor_references(cue_path)
        for ref in refs:
            ref_path = Path(ref.replace("\\", os.sep))
            if ref_path.suffix.lower() != ".bin":
                continue
            target = ref_path if ref_path.is_absolute() else cue_path.parent / ref_path
            if target.exists() and target.is_file():
                try:
                    target.unlink()
                    if worker:
                        worker.status.emit(f"LOG:Removed source BIN: {target.name}")
                except OSError as exc:
                    if worker:
                        worker.status.emit(f"LOG:Could not remove source BIN {target.name}: {exc}")
        if cue_path.exists() and cue_path.is_file():
            try:
                cue_path.unlink()
                if worker:
                    worker.status.emit(f"LOG:Removed source CUE: {cue_path.name}")
            except OSError as exc:
                if worker:
                    worker.status.emit(f"LOG:Could not remove source CUE {cue_path.name}: {exc}")

    def _remove_remote_cue_sources(self, remote_cue, local_cue, worker=None):
        refs = descriptor_references(local_cue)
        remote_dir = posixpath.dirname(remote_cue)
        targets = []
        for ref in refs:
            normalized = ref.replace("\\", "/")
            if PurePosixPath(normalized).suffix.lower() == ".bin":
                targets.append(posixpath.normpath(posixpath.join(remote_dir, normalized)))
        targets.append(remote_cue)
        sftp = self.connection.client.open_sftp()
        try:
            for target in targets:
                try:
                    sftp.remove(target)
                    if worker:
                        worker.status.emit(f"LOG:Removed source: {PurePosixPath(target).name}")
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    if worker:
                        worker.status.emit(f"LOG:Could not remove source {PurePosixPath(target).name}: {exc}")
        finally:
            sftp.close()

    def _remove_chd_source(self, source_path, source_location, worker=None):
        name = PurePosixPath(str(source_path).replace("\\", "/")).name
        try:
            if source_location == REMOTE:
                sftp = self.connection.client.open_sftp()
                try:
                    sftp.remove(source_path)
                finally:
                    sftp.close()
            else:
                Path(source_path).unlink()
            if worker:
                worker.status.emit(f"LOG:Removed source CHD: {name}")
        except OSError as exc:
            if worker:
                worker.status.emit(f"LOG:Could not remove source CHD {name}: {exc}")

    def _chd_start_queue(self):
        if not self.chd_jobs:
            QMessageBox.information(self, "CHD Converter", "The queue is empty.")
            return
        if not has_chdman():
            QMessageBox.warning(self, "CHD Converter", "Download CHDman first.")
            return
        self.chd_start.setEnabled(False)
        remove_sources = self.chd_remove_source.isChecked()
        self.chd_log.clear()
        self.chd_transfer_progress.setValue(0)
        has_remote_transfer = any(job["source"] == REMOTE or job["destination"] == REMOTE for job in self.chd_jobs if job["status"] != "Completed")
        self.chd_transfer_progress.setVisible(has_remote_transfer)
        self.chd_transfer_status.setVisible(has_remote_transfer)
        self.chd_transfer_status.setText("Preparing transfer...") if has_remote_transfer else None

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
                                local_input = self._prepare_remote_descriptor(job["input"], tmpdir, worker)
                            else:
                                local_input = self._download_remote_file(job["input"], tmpdir, worker)
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
                                self._upload_remote_file(output, remote_dir, worker, target_name=output.name)
                        if remove_sources and PurePosixPath(str(job["input"]).replace("\\", "/")).suffix.lower() == ".cue":
                            if job["source"] == REMOTE:
                                self._remove_remote_cue_sources(job["input"], local_input, worker)
                            else:
                                self._remove_local_cue_sources(job["input"], worker)
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
        self.worker.progress.connect(self.chd_transfer_progress.setValue)
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
        elif text.startswith("TRANSFER:"):
            self.chd_transfer_status.setText(text[len("TRANSFER:"):])
        elif text.startswith("LOG:"):
            self.chd_log.append(text[4:])
        else:
            self.chd_log.append(text)

    def _chd_queue_done(self, failures):
        self.chd_start.setEnabled(True)
        self._refresh_chd_table()
        if self.chd_transfer_progress.isVisible() and not failures:
            self.chd_transfer_progress.setValue(100)
            self.chd_transfer_status.setText("Transfer complete — 100%")
        if failures:
            QMessageBox.warning(self, "CHD Converter", f"Queue finished with {failures} failed job(s).")
        else:
            QMessageBox.information(self, "CHD Converter", "Queue completed successfully.")

    def _chd_queue_failed(self, message):
        self.chd_start.setEnabled(True)
        QMessageBox.critical(self, "CHD Converter", message)

    def _build_chd_extract(self):
        page, layout = self._tool_workspace_page("CHD Extractor")
        extract_tool_row = QHBoxLayout()
        self.chd_extract_tool_status = QLabel()
        extract_tool_row.addWidget(self.chd_extract_tool_status, 1)
        self.chd_extract_download_chdman_button = QPushButton("Download CHDman")
        self.chd_extract_download_chdman_button.clicked.connect(self._download_chdman_clicked)
        extract_tool_row.addWidget(self.chd_extract_download_chdman_button)
        self.chd_extract_remove_chdman_button = QPushButton("Remove")
        self.chd_extract_remove_chdman_button.clicked.connect(self._remove_chdman_clicked)
        extract_tool_row.addWidget(self.chd_extract_remove_chdman_button)
        layout.addLayout(extract_tool_row)
        self.chd_extract_download_progress = QProgressBar()
        self.chd_extract_download_progress.setVisible(False)
        layout.addWidget(self.chd_extract_download_progress)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Add input from:"))
        self.chd_extract_input_location = self._location_combo()
        input_row.addWidget(self.chd_extract_input_location)
        add_files = QPushButton("Add Files")
        add_files.clicked.connect(self._chd_extract_add_files_clicked)
        input_row.addWidget(add_files)
        add_folder = QPushButton("Add Folder")
        add_folder.clicked.connect(self._chd_extract_add_folder_clicked)
        input_row.addWidget(add_folder)
        input_row.addStretch(1)
        layout.addLayout(input_row)

        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Output format for new jobs:"))
        self.chd_extract_format = QComboBox()
        self.chd_extract_format.addItems(["CUE/BIN", "GDI", "ISO"])
        format_row.addWidget(self.chd_extract_format)
        format_row.addStretch(1)
        layout.addLayout(format_row)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output for new jobs:"))
        self.chd_extract_output_location = self._location_combo()
        output_row.addWidget(self.chd_extract_output_location)
        self.chd_extract_output_dir = QLineEdit()
        output_row.addWidget(self.chd_extract_output_dir, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._chd_extract_browse_output)
        output_row.addWidget(browse)
        layout.addLayout(output_row)

        self.chd_extract_remove_source = QCheckBox("Remove CHD after successful extraction")
        self.chd_extract_remove_source.setToolTip("Remove the source CHD only after all extracted files have been written successfully.")
        layout.addWidget(self.chd_extract_remove_source)

        self.chd_extract_table = QTableWidget(0, 6)
        self.chd_extract_table.setHorizontalHeaderLabels(["Input", "Source", "Format", "Output", "Destination", "Status"])
        self.chd_extract_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.chd_extract_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        header = self.chd_extract_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.chd_extract_table, 1)

        buttons = QHBoxLayout()
        remove = QPushButton("Remove Selected")
        remove.clicked.connect(self._chd_extract_remove_selected)
        buttons.addWidget(remove)
        clear = QPushButton("Clear Queue")
        clear.clicked.connect(self._chd_extract_clear)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        self.chd_extract_start = QPushButton("Start Queue")
        self.chd_extract_start.clicked.connect(self._chd_extract_start_queue)
        buttons.addWidget(self.chd_extract_start)
        layout.addLayout(buttons)
        self.chd_extract_status = QLabel("")
        self.chd_extract_status.setVisible(False)
        layout.addWidget(self.chd_extract_status)
        self.chd_extract_progress = QProgressBar()
        self.chd_extract_progress.setRange(0, 100)
        self.chd_extract_progress.setValue(0)
        self.chd_extract_progress.setVisible(False)
        layout.addWidget(self.chd_extract_progress)

        self.chd_extract_log = QTextEdit()
        self.chd_extract_log.setReadOnly(True)
        self.chd_extract_log.setMaximumHeight(130)
        layout.addWidget(self.chd_extract_log)
        self._refresh_chdman_status()
        return page

    def _chd_extract_browse_output(self):
        if self.chd_extract_output_location.currentText() == REMOTE:
            path = RemoteFilePickerDialog.get_directory(self.connection, self, title="Select MiSTer Output Folder")
        else:
            path = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if path:
            self.chd_extract_output_dir.setText(path)

    def _chd_extract_add_files_clicked(self):
        output_dir = self.chd_extract_output_dir.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "CHD Extractor", "Select an output folder for new jobs first.")
            return
        source_location = self.chd_extract_input_location.currentText()
        if source_location == REMOTE:
            files = RemoteFilePickerDialog.get_open_files(self.connection, self, title="Select CHD Images from MiSTer", filters=[".chd"])
        else:
            files, _ = QFileDialog.getOpenFileNames(self, "Select CHD Images", filter="CHD images (*.chd);;All files (*.*)")
        for path in files:
            self._add_chd_extract_job(path, source_location, output_dir, self.chd_extract_output_location.currentText())

    def _chd_extract_add_folder_clicked(self):
        output_dir = self.chd_extract_output_dir.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "CHD Extractor", "Select an output folder for new jobs first.")
            return
        location = self.chd_extract_input_location.currentText()
        if location == REMOTE:
            folder = RemoteFilePickerDialog.get_directory(self.connection, self, title="Select MiSTer Input Folder")
            files = self._remote_files_with_exts(folder, CHD_EXTRACT_INPUT_EXTS) if folder else []
        else:
            folder = QFileDialog.getExistingDirectory(self, "Select Input Folder")
            files = [str(p) for p in Path(folder).rglob("*.chd") if p.is_file()] if folder else []
        for path in files:
            self._add_chd_extract_job(path, location, output_dir, self.chd_extract_output_location.currentText())

    def _remote_files_with_exts(self, folder, exts):
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
                    elif PurePosixPath(item).suffix.lower() in exts:
                        results.append(item)
            walk(folder)
        finally:
            sftp.close()
        return results

    def _add_chd_extract_job(self, input_path, source_location, output_dir, output_location):
        fmt_label = self.chd_extract_format.currentText()
        fmt = {"CUE/BIN": "cue", "GDI": "gdi", "ISO": "iso"}[fmt_label]
        stem = PurePosixPath(str(input_path).replace("\\", "/")).stem
        output_name = f"{stem}.{fmt}"
        output_path = posixpath.join(output_dir.rstrip("/"), output_name) if output_location == REMOTE else str(Path(output_dir) / output_name)
        self.chd_extract_jobs.append({
            "input": input_path, "source": source_location, "format": fmt, "format_label": fmt_label,
            "output": output_path, "destination": output_location, "status": "Queued",
        })
        self._refresh_chd_extract_table()

    def _refresh_chd_extract_table(self):
        self.chd_extract_table.setRowCount(len(self.chd_extract_jobs))
        keys = ("input", "source", "format_label", "output", "destination", "status")
        for row, job in enumerate(self.chd_extract_jobs):
            for col, key in enumerate(keys):
                self.chd_extract_table.setItem(row, col, QTableWidgetItem(str(job[key])))

    def _chd_extract_remove_selected(self):
        rows = sorted({idx.row() for idx in self.chd_extract_table.selectionModel().selectedRows()}, reverse=True)
        for row in rows:
            if 0 <= row < len(self.chd_extract_jobs):
                del self.chd_extract_jobs[row]
        self._refresh_chd_extract_table()

    def _chd_extract_clear(self):
        self.chd_extract_jobs.clear()
        self._refresh_chd_extract_table()

    def _chd_extract_start_queue(self):
        if not self.chd_extract_jobs:
            QMessageBox.information(self, "CHD Extractor", "The queue is empty.")
            return
        if not has_chdman():
            QMessageBox.warning(self, "CHD Extractor", "Download CHDman first.")
            return
        self.chd_extract_start.setEnabled(False)
        remove_sources = self.chd_extract_remove_source.isChecked()
        self.chd_extract_log.clear()
        self.chd_extract_progress.setValue(0)
        has_remote_transfer = any(job["source"] == REMOTE or job["destination"] == REMOTE for job in self.chd_extract_jobs if job["status"] != "Completed")
        self.chd_extract_progress.setVisible(has_remote_transfer)
        self.chd_extract_status.setVisible(has_remote_transfer)
        self.chd_extract_status.setText("Preparing transfer...") if has_remote_transfer else None

        def work(worker):
            failures = 0
            for index, job in enumerate(self.chd_extract_jobs):
                if job["status"] == "Completed":
                    continue
                worker.status.emit(f"TABLE:{index}:Extracting")
                try:
                    with tempfile.TemporaryDirectory(prefix="mister-companion-chd-extract-") as tmp:
                        tmpdir = Path(tmp)
                        local_input = self._download_remote_file(job["input"], tmpdir, worker) if job["source"] == REMOTE else Path(job["input"])
                        extract_dir = tmpdir / "output"
                        outputs = extract_chdman(local_input, extract_dir, job["format"], lambda line: worker.status.emit("LOG:" + line))
                        if not outputs:
                            raise ChdmanError("CHDman did not produce any output files.")
                        if job["destination"] == REMOTE:
                            remote_dir = posixpath.dirname(job["output"])
                            for output in outputs:
                                self._ensure_remote_output_new(posixpath.join(remote_dir, output.name))
                            for output in outputs:
                                self._upload_remote_file(output, remote_dir, worker, target_name=output.name)
                        else:
                            destination_dir = Path(job["output"]).parent
                            destination_dir.mkdir(parents=True, exist_ok=True)
                            for output in outputs:
                                target = destination_dir / output.name
                                if target.exists():
                                    raise FileExistsError(f"Output already exists: {target}")
                            for output in outputs:
                                shutil.copy2(output, destination_dir / output.name)
                        if remove_sources:
                            self._remove_chd_source(job["input"], job["source"], worker)
                    worker.status.emit(f"TABLE:{index}:Completed")
                except Exception as exc:
                    failures += 1
                    worker.status.emit(f"TABLE:{index}:Failed")
                    worker.status.emit(f"LOG:{PurePosixPath(job['input']).name}: {exc}")
            return failures

        self.worker = ToolWorker(work, self)
        self.worker.status.connect(self._chd_extract_worker_status)
        self.worker.progress.connect(self.chd_extract_progress.setValue)
        self.worker.succeeded.connect(self._chd_extract_queue_done)
        self.worker.failed.connect(self._chd_extract_queue_failed)
        self.worker.start()

    def _chd_extract_worker_status(self, text):
        if text.startswith("TABLE:"):
            _, row, status = text.split(":", 2)
            row = int(row)
            if 0 <= row < len(self.chd_extract_jobs):
                self.chd_extract_jobs[row]["status"] = status
                item = self.chd_extract_table.item(row, 5)
                if item:
                    item.setText(status)
        elif text.startswith("TRANSFER:"):
            self.chd_extract_status.setText(text[len("TRANSFER:"):])
        elif text.startswith("LOG:"):
            self.chd_extract_log.append(text[4:])
        else:
            self.chd_extract_log.append(text)

    def _chd_extract_queue_done(self, failures):
        self.chd_extract_start.setEnabled(True)
        self._refresh_chd_extract_table()
        if self.chd_extract_progress.isVisible() and not failures:
            self.chd_extract_progress.setValue(100)
            self.chd_extract_status.setText("Transfer complete — 100%")
        if failures:
            QMessageBox.warning(self, "CHD Extractor", f"Queue finished with {failures} failed job(s).")
        else:
            QMessageBox.information(self, "CHD Extractor", "Queue completed successfully.")

    def _chd_extract_queue_failed(self, message):
        self.chd_extract_start.setEnabled(True)
        QMessageBox.critical(self, "CHD Extractor", message)


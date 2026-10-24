from pathlib import Path
import os
import posixpath
import stat

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QAbstractItemView, QCheckBox, QComboBox,
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QWidget,
    QVBoxLayout)
from core.arcade_roms import local_zip_index, mra_requirements, destination_zip_path
from ui.dialogs.remote_file_picker_dialog import RemoteFilePickerDialog


class ArcadeWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    status = pyqtSignal(str)
    progress = pyqtSignal(int)
    phase = pyqtSignal(str, object, object)

    def __init__(self, fn, parent):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.result.emit(self.fn(self))
        except Exception as exc:
            self.error.emit(str(exc))

    def check(self):
        if self.isInterruptionRequested():
            raise InterruptedError('Cancelled')


class ArcadeRomChecker(QWidget):
    def __init__(self, owner, layout):
        super().__init__()
        self.owner = owner
        self.main = owner.main_window
        self.worker = None
        self.rows = []
        self.snapshot = None
        self.controls = QWidget()
        self.controls.setObjectName('ArcadeRomControls')
        self.controls.setStyleSheet("""
            QWidget#ArcadeRomControls,
            QWidget#ArcadeRomTarget,
            QWidget#ArcadeRomCollection,
            QWidget#ArcadeRomControls QLabel,
            QWidget#ArcadeRomControls QCheckBox {
                background: transparent;
            }
        """)
        form = QVBoxLayout(self.controls)
        form.setContentsMargins(0, 0, 0, 0)
        intro = QLabel('List MAME ROM ZIP filenames referenced by MRAs. Checking and copying are optional. Presence checks use filenames only; ROM contents and CRCs are not validated. ZIP names separated by | are alternatives.')
        intro.setWordWrap(True)
        form.addWidget(intro)
        self.source, self.source_path = self.path_row(form, 'MRA source:')
        self.recursive = QCheckBox('Include MRA subfolders')
        self.recursive.setChecked(True)
        form.addWidget(self.recursive)
        self.check_existing = QCheckBox('Check whether required ROM ZIPs are present')
        form.addWidget(self.check_existing)
        self.target_box = QWidget()
        self.target_box.setObjectName('ArcadeRomTarget')
        target_layout = QVBoxLayout(self.target_box)
        target_layout.setContentsMargins(0, 0, 0, 0)
        self.target, self.target_path = self.path_row(target_layout, 'ROM check / copy destination:')
        form.addWidget(self.target_box)
        self.check_existing.toggled.connect(self.target_box.setEnabled)
        self.target_box.setEnabled(False)
        self.find_local = QCheckBox('Find missing ROMs in a local MAME collection')
        form.addWidget(self.find_local)
        self.collection_box = QWidget()
        self.collection_box.setObjectName('ArcadeRomCollection')
        collection_layout = QVBoxLayout(self.collection_box)
        collection_layout.setContentsMargins(0, 0, 0, 0)
        _, self.collection = self.path_row(collection_layout, 'Local MAME collection:', local_only=True)
        self.collection_recursive = QCheckBox('Include collection subfolders')
        collection_layout.addWidget(self.collection_recursive)
        form.addWidget(self.collection_box)
        self.find_local.toggled.connect(self.collection_box.setEnabled)
        self.collection_box.setEnabled(False)
        self.scan = QPushButton('Scan MRAs')
        self.scan.clicked.connect(self.start_scan)
        form.addWidget(self.scan)
        layout.addWidget(self.controls)
        filters = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItems(['All', 'Present', 'Missing', 'Not checked'])
        self.search = QLineEdit()
        self.search.setPlaceholderText('Filter by ROM filename or MRA…')
        filters.addWidget(self.filter)
        filters.addWidget(self.search, 1)
        layout.addLayout(filters)
        self.filter.currentTextChanged.connect(self.render)
        self.search.textChanged.connect(self.render)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Required ZIP / alternatives', 'Required by MRA', 'Status', 'Local collection'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 240)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 200)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        for label, callback in [('Copy filenames', self.copy_names), ('Copy filtered filenames', lambda: self.copy_names(filtered=True)), ('Export list…', self.export), ('Export filtered list…', lambda: self.export(filtered=True)), ('Copy found ROMs…', self.start_copy)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
            if label == 'Copy filtered filenames':
                self.copy_filtered_button = button
                button.setEnabled(False)
            elif label == 'Export filtered list…':
                self.export_filtered_button = button
                button.setEnabled(False)
            if label.startswith('Copy found'):
                self.copy_button = button
                button.setEnabled(False)
        self.cancel = QPushButton('Cancel')
        self.cancel.clicked.connect(self.cancel_work)
        self.cancel.setEnabled(False)
        actions.addWidget(self.cancel)
        layout.addLayout(actions)
        self.summary = QLabel('Choose an MRA folder to begin.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(95)
        layout.addWidget(self.details)
        self.update_connection_state()

    def path_row(self, layout, label, local_only=False):
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        combo = None if local_only else QComboBox()
        if combo is not None:
            row.addWidget(combo)
        edit = QLineEdit()
        row.addWidget(edit, 1)
        button = QPushButton('Browse')
        button.clicked.connect(lambda: self.browse(combo, edit))
        row.addWidget(button)
        layout.addLayout(row)
        if combo is not None:
            combo.currentTextChanged.connect(lambda: self.location_changed(combo, edit, label))
        return combo, edit

    def location_changed(self, combo, edit, label):
        target = label.startswith('ROM')
        kind = combo.currentText()
        root = self.main.get_offline_sd_root() if kind == 'SD card' else '/media/fat' if kind == 'MiSTer' else ''
        edit.setText((posixpath.join(root, 'games/mame' if target else '_Arcade')) if root else '')

    def update_connection_state(self):
        choices = ['Local folder']
        if self.main.is_offline_mode():
            choices.insert(0, 'SD card')
        elif self.owner._is_remote_allowed():
            choices.insert(0, 'MiSTer')
        for combo in (self.source, self.target):
            if [combo.itemText(i) for i in range(combo.count())] != choices:
                old = combo.currentText()
                combo.clear()
                combo.addItems(choices)
                if old in choices:
                    combo.setCurrentText(old)
        if self.snapshot and (self.snapshot[0] not in choices or (self.snapshot[0] == 'SD card' and not str(Path(self.snapshot[1])).startswith(str(self.main.get_offline_sd_root()) + os.sep))):
            self.copy_button.setEnabled(False)

    def browse(self, combo, edit):
        if combo is not None and combo.currentText() == 'MiSTer':
            path = RemoteFilePickerDialog.get_directory(self.owner.connection, self, title='Select MiSTer Folder')
        else:
            path = QFileDialog.getExistingDirectory(self, 'Select Folder', edit.text())
        if path:
            edit.setText(path)

    def cancel_work(self):
        if self.worker:
            self.worker.requestInterruption()

    def launch(self, fn, done):
        self.controls.setEnabled(False)
        self.copy_button.setEnabled(False)
        self.cancel.setEnabled(True)
        self.show_progress('Preparing', 0, 0)
        self.worker = ArcadeWorker(fn, self)
        self.worker.status.connect(self.summary.setText)
        self.worker.phase.connect(self.show_progress)
        self.worker.result.connect(done)
        self.worker.error.connect(self.failed)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def show_progress(self, stage, completed, total):
        if not total:
            self.progress.setRange(0, 0)
            self.progress.setFormat(stage + '…')
        else:
            self.progress.setRange(0, 10000)
            self.progress.setValue(int(completed * 10000 / total))
            unit = ' bytes' if stage == 'Copying ROMs' else ''
            self.progress.setFormat(f'{stage}: {completed:,} / {total:,}{unit} — %p%')

    def finished(self):
        self.controls.setEnabled(True)
        self.cancel.setEnabled(False)
        self.copy_button.setEnabled(bool(self.snapshot and any(r['status'] == 'Missing' and r['local'] for r in self.rows)))
        self.update_connection_state()

    def failed(self, message):
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 10000)
            self.progress.setValue(0)
        self.progress.setFormat('Stopped — %p%')
        self.summary.setText(message)
        self.details.append(message)

    def start_scan(self):
        source, folder = self.source.currentText(), self.source_path.text().strip()
        target, destination = self.target.currentText(), self.target_path.text().strip()
        check, find = self.check_existing.isChecked(), self.find_local.isChecked()
        collection = self.collection.text().strip()
        recursive, collection_recursive = self.recursive.isChecked(), self.collection_recursive.isChecked()
        if (source == 'SD card' or (check and target == 'SD card')) and not self.main.get_offline_sd_root():
            QMessageBox.warning(self, 'Arcade ROM Checker', 'Select an offline SD card in Companion first.')
            return
        if not folder or (check and not destination) or (find and not collection):
            QMessageBox.warning(self, 'Arcade ROM Checker', 'Select the folders for each enabled option.')
            return
        self.rows = []
        self.snapshot = None
        self.render()
        self.details.clear()
        client = self.owner.connection.client
        host = getattr(self.owner.connection, 'host', '')

        def work(worker):
            sftp = client.open_sftp() if source == 'MiSTer' or (check and target == 'MiSTer') else None
            errors, requirements, files = [], {}, []
            def walk(path):
                worker.check()
                worker.status.emit(f'Discovering MRAs: {len(files)} found — {path}')
                for attr in sftp.listdir_attr(path):
                    worker.check()
                    child = posixpath.join(path, attr.filename)
                    if stat.S_ISDIR(attr.st_mode) and recursive:
                        walk(child)
                    elif stat.S_ISREG(attr.st_mode) and child.lower().endswith('.mra'):
                        files.append(child)
            try:
                worker.phase.emit('Discovering MRA files', 0, 0)
                if source == 'MiSTer':
                    walk(folder)
                else:
                    root = Path(folder)
                    if not root.is_dir():
                        raise ValueError('MRA folder does not exist.')
                    for p in root.rglob('*') if recursive else root.iterdir():
                        worker.check()
                        if p.is_file() and p.suffix.lower() == '.mra':
                            files.append(str(p))
                            worker.status.emit(f'Discovering MRAs: {len(files)} found')
                worker.phase.emit('Scanning MRAs', 0, len(files))
                for i, path in enumerate(sorted(files)):
                    worker.check()
                    worker.status.emit(f'Scanning MRA {i + 1} of {len(files)}')
                    try:
                        if source == 'MiSTer':
                            with sftp.open(path, 'rb') as stream:
                                data = stream.read()
                        else:
                            data = Path(path).read_bytes()
                        for group in mra_requirements(data):
                            requirements.setdefault(group, []).append(path)
                    except Exception as exc:
                        errors.append(f'{path}: {exc}')
                    worker.phase.emit('Scanning MRAs', i + 1, len(files))
                existing = {}
                if check:
                    worker.phase.emit('Indexing destination ROMs', 0, 0)
                    worker.status.emit('Indexing destination ROM filenames…')
                    if target == 'MiSTer':
                        existing = {a.filename.lower(): a.filename for a in sftp.listdir_attr(destination) if stat.S_ISREG(a.st_mode)}
                    else:
                        existing = local_zip_index(destination, cancelled=worker.isInterruptionRequested)
                    for name in {n for group in requirements for n in group if '/' in n}:
                        worker.check()
                        path = destination_zip_path(destination, name)
                        try:
                            present = stat.S_ISREG(sftp.stat(path).st_mode) if target == 'MiSTer' else Path(path).is_file()
                        except FileNotFoundError:
                            present = False
                        if present:
                            existing[name] = path
                local = {}
                if find:
                    worker.phase.emit('Indexing local MAME collection', 0, 0)
                    worker.status.emit('Indexing local MAME collection…')
                    local = local_zip_index(collection, collection_recursive, worker.isInterruptionRequested)
                rows = []
                worker.phase.emit('Checking ZIP requirements', 0, len(requirements))
                for index, (group, mras) in enumerate(sorted(requirements.items())):
                    worker.check()
                    present = any(name in existing for name in group)
                    local_name = next((n for n in group if n in local or n.rsplit('/', 1)[-1] in local), None)
                    rows.append(dict(names=group, mras=mras, status=('Present' if present else 'Missing') if check else 'Not checked', local=(local.get(local_name) or local.get(local_name.rsplit('/', 1)[-1], '')) if local_name else '', copy_name=local_name))
                    worker.phase.emit('Checking ZIP requirements', index + 1, len(requirements))
                return rows, errors, len(files), (target, destination, host) if check else None
            finally:
                if sftp:
                    sftp.close()
        self.launch(work, self.scanned)

    def scanned(self, result):
        self.rows, errors, count, self.snapshot = result
        self.details.setPlainText('\n'.join(errors))
        counts = {s: sum(r['status'] == s for r in self.rows) for s in ('Present', 'Missing', 'Not checked')}
        self.summary.setText(f"{count} MRAs scanned · {len(self.rows)} unique ZIP requirements · {counts['Present']} present · {counts['Missing']} missing · {counts['Not checked']} not checked · {len(errors)} errors")
        self.render()
        self.show_progress('Scan complete', 1, 1)

    def filtered_rows(self):
        needle = self.search.text().casefold()
        return [r for r in self.rows if (self.filter.currentText() == 'All' or r['status'] == self.filter.currentText()) and needle in (' '.join(r['names']) + ' '.join(r['mras'])).casefold()]

    def render(self):
        rows = self.filtered_rows()
        self.copy_filtered_button.setEnabled(bool(rows))
        self.export_filtered_button.setEnabled(bool(rows))
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate((' | '.join(row['names']), '; '.join(row['mras']), row['status'], row['local'] or 'Unavailable')):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(i, j, item)

    def names_text(self, filtered=False):
        rows = self.filtered_rows() if filtered else self.rows
        return '\n'.join(' | '.join(r['names']) for r in rows)

    def copy_names(self, filtered=False):
        QApplication.clipboard().setText(self.names_text(filtered))

    def export(self, filtered=False):
        text = self.names_text(filtered)
        filename = 'arcade-roms-missing.txt' if filtered and self.filter.currentText() == 'Missing' else 'arcade-roms-filtered.txt' if filtered else 'arcade-roms.txt'
        path, _ = QFileDialog.getSaveFileName(self, 'Export filtered ROM filenames' if filtered else 'Export required ROM filenames', filename, 'Text files (*.txt)')
        if path:
            try:
                Path(path).write_text(text + '\n', encoding='utf-8')
            except OSError as exc:
                self.failed(str(exc))

    def start_copy(self):
        if not self.snapshot:
            return
        target, destination, host = self.snapshot
        if target == 'MiSTer' and (not self.owner._is_remote_allowed() or host != self.owner.connection.host):
            self.failed('Reconnect to the scanned MiSTer and scan again before copying.')
            return
        jobs = [r for r in self.rows if r['status'] == 'Missing' and r['local']]
        names = sorted({r['copy_name'] for r in jobs})
        message = f"Copy {len(names)} ZIPs from your local collection to {target}: {destination}?\n\n" + '\n'.join(names)
        if QMessageBox.question(self, 'Copy missing ROMs', message) != QMessageBox.StandardButton.Yes:
            return
        client = self.owner.connection.client
        def work(worker):
            sftp = client.open_sftp() if target == 'MiSTer' else None
            copied, skipped, errors = [], [], []
            try:
                worker.phase.emit('Indexing destination ROMs', 0, 0)
                worker.status.emit('Checking destination before copying…')
                existing = {a.filename.lower() for a in sftp.listdir_attr(destination)} if sftp else set(local_zip_index(destination))
                for name in {n for row in jobs for n in row['names'] if '/' in n}:
                    worker.check()
                    path = destination_zip_path(destination, name)
                    try:
                        present = stat.S_ISREG(sftp.stat(path).st_mode) if sftp else Path(path).is_file()
                    except FileNotFoundError:
                        present = False
                    if present:
                        existing.add(name)
                pending = []
                planned = set(existing)
                worker.phase.emit('Preparing copy', 0, 0)
                for row in jobs:
                    worker.check()
                    name = row['copy_name']
                    if any(n in planned for n in row['names']):
                        skipped.append(name)
                        continue
                    try:
                        size = Path(row['local']).stat().st_size
                    except OSError as exc:
                        errors.append(f'{name}: {exc}')
                        continue
                    planned.add(name)
                    pending.append((row, size))
                total = sum(size for _, size in pending)
                transferred = 0
                worker.phase.emit('Copying ROMs', 0, total)
                for i, (row, size) in enumerate(pending):
                    worker.check()
                    name = row['copy_name']
                    worker.status.emit(f'Copying ROM {i + 1} of {len(pending)}: {name}')
                    temp = None
                    file_bytes = 0
                    try:
                        if sftp:
                            dest = destination_zip_path(destination, name)
                            missing = []
                            parent = posixpath.dirname(dest)
                            while parent and parent != '/':
                                try:
                                    if not stat.S_ISDIR(sftp.stat(parent).st_mode):
                                        raise ValueError('ROM parent is not a directory: ' + parent)
                                    break
                                except FileNotFoundError:
                                    missing.append(parent)
                                    parent = posixpath.dirname(parent)
                            for parent in reversed(missing):
                                sftp.mkdir(parent)
                            temp = dest + '.companion-part-' + os.urandom(6).hex()
                            def progress(sent, file_total):
                                nonlocal file_bytes
                                worker.check()
                                file_bytes = sent
                                worker.phase.emit('Copying ROMs', transferred + sent, total)
                            sftp.put(row['local'], temp, callback=progress)
                            sftp.rename(temp, dest)
                        else:
                            dest = Path(destination_zip_path(destination, name))
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            created = False
                            try:
                                with open(dest, 'xb') as out, open(row['local'], 'rb') as inp:
                                    created = True
                                    while True:
                                        worker.check()
                                        chunk = inp.read(1024 * 1024)
                                        if not chunk:
                                            break
                                        out.write(chunk)
                                        file_bytes += len(chunk)
                                        worker.phase.emit('Copying ROMs', transferred + file_bytes, total)
                            except BaseException:
                                if created:
                                    dest.unlink(missing_ok=True)
                                raise
                        copied.append(name)
                        existing.add(name)
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        errors.append(f'{name}: {exc}')
                    finally:
                        transferred += file_bytes
                        if temp:
                            try:
                                sftp.remove(temp)
                            except OSError:
                                pass
                if not errors:
                    worker.phase.emit('Copy complete', 1, 1)
                return copied, skipped, errors, existing
            finally:
                if sftp:
                    sftp.close()
        self.launch(work, self.copied)

    def copied(self, result):
        copied, skipped, errors, existing = result
        for row in self.rows:
            if any(n in existing for n in row['names']):
                row['status'] = 'Present'
        self.render()
        self.summary.setText(f'{len(copied)} copied · {len(skipped)} skipped · {len(errors)} failed')
        self.details.setPlainText('\n'.join(errors))

    def shutdown(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait()

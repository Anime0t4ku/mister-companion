import json
import time
from pathlib import Path
from serial.tools import list_ports
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QTabWidget, QFormLayout, QLineEdit, QSpinBox, QCheckBox, QScrollArea, QFileDialog, QMessageBox, QInputDialog, QDialog, QGridLayout, QGroupBox, QSizePolicy
from core.bluebridge import BlueBridgeService, boot_volumes, flash_volume
from core.bluebridge_protocol import _uf2_info
from core.bluebridge_releases import bluebridge_release, download_bluebridge_release, version_key
from ui.tab_header import create_tab_header


class BlueBridgeWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, work, parent):
        super().__init__(parent)
        self.work = work

    def run(self):
        try:
            self.result.emit(self.work())
        except Exception as exc:
            self.error.emit(str(exc))


class BlueBridgeTab(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent
        self.service = None
        self.worker = None
        self.worker_quiet = False
        self.active = False
        self.profile_data = {}
        self.profiles_data = {}
        self.controllers_data = {}
        self.status_data = {}
        self.mapping = {}
        self.controls = {}
        self.macros = []
        self.installer_release = {}
        self.tester = None
        self.capture_callback = None
        self.capture_deadline = 0
        self.closing = False
        self.deferred = []
        self.last_inventory = 0
        self.inventory_signature = []
        self.preferred_adapter = ''
        self.auto_installer = False
        self.managed_controller = None
        self.setObjectName('BlueBridgePage')
        self.setStyleSheet('''
            QWidget#BlueBridgePage QTabWidget,
            QWidget#BlueBridgePage QTabBar,
            QWidget#BlueBridgePage QScrollArea,
            QWidget#BlueBridgePage QScrollArea > QWidget,
            QWidget#BlueBridgePage QWidget#BlueBridgeSurface {
                background: transparent;
            }
            QWidget#BlueBridgePage QGroupBox::title {
                background: transparent;
            }
            QWidget#BlueBridgePage QTabWidget::pane {
                background: transparent;
                border: none;
            }
            QWidget#BlueBridgePage QWidget#BlueBridgeChooser {
                background: transparent;
            }
            QWidget#BlueBridgePage QGroupBox#BlueBridgeChoice QLabel {
                background: transparent;
            }
            QWidget#BlueBridgePage QGroupBox#BlueBridgeChoice {
                background-color: palette(alternate-base);
                border: 1px solid palette(button);
                border-radius: 12px;
                margin-top: 18px;
                padding: 14px;
                font-weight: 700;
            }
            QWidget#BlueBridgePage QGroupBox#BlueBridgeChoice::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                padding: 0px 7px;
                color: palette(highlight);
                background: transparent;
            }
        ''')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(14)
        header = create_tab_header(parent, 'MC BlueBridge', 'bluebridge')
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        outer.addWidget(header)
        self.connection_bar = QWidget()
        self.connection_bar.setObjectName('BlueBridgeSurface')
        self.connection_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        row = QHBoxLayout(self.connection_bar)
        row.setContentsMargins(0, 0, 0, 0)
        self.mode = QComboBox()
        self.mode.addItems(['Choose connection', 'Remote', 'USB', 'Install / Recover'])
        row.addWidget(self.mode)
        self.adapters = QComboBox()
        row.addWidget(self.adapters, 1)
        self.adapters.hide()
        row.addStretch(1)
        self.refresh_button = QPushButton('Refresh')
        row.addWidget(self.refresh_button)
        outer.addWidget(self.connection_bar)
        self.connection_bar.hide()
        self.message = QLabel('Manage an adapter through Remote or USB, or install MC BlueBridge on a Pico 2 W.')
        self.message.setWordWrap(True)
        self.message.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        outer.addWidget(self.message)
        self.capture_cancel_button = QPushButton('Cancel Input Capture')
        self.capture_cancel_button.clicked.connect(self.cancel_capture)
        self.capture_cancel_button.hide()
        outer.addWidget(self.capture_cancel_button)
        self.chooser = QWidget()
        self.chooser.setObjectName('BlueBridgeChooser')
        self.chooser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        choices = QHBoxLayout(self.chooser)
        choices.setContentsMargins(0, 0, 0, 0)
        choices.setSpacing(14)
        self.choice_buttons = []
        for mode, title, description, action in [
            (1, 'Remote', 'Manage an MC BlueBridge adapter connected to your MiSTer through Companion Remote.', 'Use Remote'),
            (2, 'USB', 'Manage an MC BlueBridge adapter connected directly to this computer.', 'Connect via USB'),
            (3, 'Install / Recover', 'Install MC BlueBridge on a Pico 2 W, or recover an adapter using a firmware UF2 file and BOOTSEL.', 'Install / Recover'),
        ]:
            card = QGroupBox(title)
            card.setObjectName('BlueBridgeChoice')
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 22, 16, 14)
            card_layout.setSpacing(14)
            description_label = QLabel(description)
            description_label.setWordWrap(True)
            description_label.setMinimumHeight(64)
            card_layout.addWidget(description_label)
            button = QPushButton(action)
            button.clicked.connect(lambda _, index=mode: self.mode.setCurrentIndex(index))
            card_layout.addWidget(button)
            self.choice_buttons.append(button)
            choices.addWidget(card, 1)
        outer.addWidget(self.chooser)
        self.daemon_panel = QWidget()
        self.daemon_panel.setObjectName('BlueBridgeSurface')
        self.daemon_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        dr = QHBoxLayout(self.daemon_panel)
        self.daemon_status = QLabel()
        dr.addWidget(self.daemon_status, 1)
        self.daemon_buttons = []
        for title, command in [('Install / Update', 'install'), ('Start / Stop', 'start-stop'), ('Start on boot', 'toggle-boot'), ('Uninstall', 'uninstall')]:
            button = QPushButton(title)
            button.clicked.connect(lambda _, c=command: self.daemon_action(c))
            dr.addWidget(button)
            self.daemon_buttons.append(button)
        outer.addWidget(self.daemon_panel)
        self.daemon_panel.hide()
        self.pages = QTabWidget()
        self.pages.tabBar().hide()
        outer.addWidget(self.pages, 1)
        self.build_management()
        self.build_installer(outer)
        self.pages.hide()
        self.installer.hide()
        outer.addStretch()
        self.mode.currentIndexChanged.connect(self.change_mode)
        self.adapters.currentIndexChanged.connect(self.select_adapter)
        self.refresh_button.clicked.connect(self.refresh)
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.capture_timer = QTimer(self)
        self.capture_timer.setInterval(100)
        self.capture_timer.timeout.connect(self.poll_capture)

    def run(self, work, done=None, quiet=False):
        if self.closing:
            return
        if self.worker is not None:
            if not quiet and self.worker_quiet:
                self.defer(lambda: self.run(work, done, quiet=False))
            return
        self.worker_quiet = quiet
        if not quiet:
            self.set_busy(True)
        worker = BlueBridgeWorker(work, self)
        self.worker = worker
        worker.result.connect(done or (lambda _: None))
        worker.error.connect(self.on_error)
        worker.finished.connect(self.finished)
        worker.start()

    def set_busy(self, busy):
        self.mode.setEnabled(not busy and not self.tester and not self.capture_callback)
        self.adapters.setEnabled(not busy and not self.tester and not self.capture_callback)
        self.refresh_button.setEnabled(not busy and not self.tester and not self.capture_callback)
        self.pages.setEnabled(not busy and not self.tester and not self.capture_callback)
        self.installer.setEnabled(not busy)
        for button in self.daemon_buttons:
            button.setEnabled(not busy and bool(self.main_window.connection.is_connected()))

    def defer(self, callback):
        if self.worker:
            self.deferred.append(callback)
        elif not self.closing:
            QTimer.singleShot(0, callback)

    def finished(self):
        was_quiet = self.worker_quiet
        self.worker_quiet = False
        worker = self.worker
        self.worker = None
        if worker:
            worker.deleteLater()
        if not was_quiet:
            self.set_busy(False)
        callbacks, self.deferred = self.deferred, []
        if not self.closing:
            for callback in callbacks: QTimer.singleShot(0, callback)
        if self.tester or self.capture_callback:
            self.mode.setEnabled(False)
            self.adapters.setEnabled(False)

    def on_error(self, message):
        self.message.setText(message)
        self.capture_cancel_button.hide()
        if self.capture_callback:
            self.capture_callback = None
            self.capture_timer.stop()
            if self.service: self.defer(lambda: self.run(lambda: self.service.api('capture/stop', {})))
        if self.tester:
            self.stop_tester()

    def button(self, row, title, callback):
        button = QPushButton(title)
        button.clicked.connect(lambda _: callback())
        row.addWidget(button)
        return button

    def page(self, name, tabs=None):
        widget = QWidget()
        widget.setObjectName('BlueBridgeSurface')
        layout = QVBoxLayout(widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        (tabs if tabs is not None else self.pages).addTab(scroll, name)
        return layout

    def form_control(self, form, title, key, kind='spin', low=0, high=100):
        if kind == 'check':
            control = QCheckBox()
        elif kind == 'text':
            control = QLineEdit()
        else:
            control = QSpinBox()
            control.setRange(low, high)
        self.controls[key] = control
        form.addRow(title, control)
        return control

    def build_management(self):
        overview = self.page('Overview')
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        overview_header = QHBoxLayout()
        overview_header.addWidget(self.summary, 1, Qt.AlignmentFlag.AlignTop)
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel('USB output'))
        self.output = QComboBox()
        for i, name in enumerate(['MiSTer', 'X-Input', 'Generic HID', 'Nintendo Switch'], 1): self.output.addItem(name, i)
        self.output.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.output.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        output_row.addWidget(self.output)
        overview_header.addLayout(output_row)
        overview_header.setAlignment(output_row, Qt.AlignmentFlag.AlignTop)
        self.output.activated.connect(self.change_output)
        overview.addLayout(overview_header)
        row = QHBoxLayout()
        self.pair_button = self.button(row, 'Start Pairing', lambda: self.command('pair', {'start': not self.status_data.get('pairing')}))
        self.button(row, 'Paired Controllers', self.show_paired)
        self.disconnect_button = self.button(row, 'Disconnect', self.disconnect_controller)
        self.tester_button = self.button(row, 'Controller Tester', self.open_tester)
        self.button(row, 'Firmware', lambda: self.pages.setCurrentIndex(2))
        overview.addLayout(row)
        self.controllers = QComboBox(self)
        self.controllers.hide()
        self.profile_panel = QGroupBox('Profiles')
        profile_layout = QVBoxLayout(self.profile_panel)
        self.profile_state = QLabel()
        profile_header = QHBoxLayout()
        profile_header.addWidget(self.profile_state, 1)
        self.close_controller_button = self.button(profile_header, 'Close Controller', self.close_managed_controller)
        self.close_controller_button.hide()
        profile_layout.addLayout(profile_header)
        self.profiles = QComboBox()
        profile_layout.addWidget(self.profiles)
        self.profiles.activated.connect(self.load_profile)
        row = QHBoxLayout()
        self.profile_buttons = {}
        for title in ['Create', 'Duplicate', 'Activate', 'Delete']:
            self.profile_buttons[title] = self.button(row, title, lambda t=title: self.profile_action(t))
        self.button(row, 'Save Profile', self.save_profile)
        profile_layout.addLayout(row)
        self.editor_tabs = QTabWidget()
        self.editor_tabs.setMinimumHeight(460)
        profile_layout.addWidget(self.editor_tabs)
        overview.addWidget(self.profile_panel)
        self.profile_panel.hide()
        overview.addStretch()
        mapping = self.page('Mapping', self.editor_tabs)
        self.mapping_form = QFormLayout()
        mapping.addLayout(self.mapping_form)
        row = QHBoxLayout()
        self.button(row, 'Reset Mapping', self.reset_mapping)
        self.source_capture_button = self.button(row, 'Press Controller Button', lambda: self.capture_input(lambda i: self.mapping[i].setFocus() if i in self.mapping else None))
        mapping.addLayout(row)
        mapping.addStretch()
        analog = self.page('Analog', self.editor_tabs)
        self.analog_form = QFormLayout()
        for title, key in [('Invert Left X','invert_x'),('Invert Left Y','invert_y'),('Invert Right X','invert_rx'),('Invert Right Y','invert_ry')]: self.form_control(self.analog_form, title, key, 'check')
        for title, key in [('Left stick deadzone (%)','deadzone_left'),('Right stick deadzone (%)','deadzone_right'),('Trigger deadzone (%)','trigger_deadzone')]: self.form_control(self.analog_form, title, key, high=50)
        analog.addLayout(self.analog_form)
        analog.addStretch()
        turbo = self.page('Turbo', self.editor_tabs)
        self.turbo_form = QFormLayout()
        self.form_control(self.turbo_form, 'Enable Turbo', 'turbo_enabled', 'check')
        mode = QComboBox(); mode.addItems(['Button shortcut (modifier + target)', 'Dedicated button - press to toggle', 'Dedicated button - hold while using Turbo']); self.controls['turbo_control_mode'] = mode; self.turbo_form.addRow('How Turbo is controlled', mode)
        self.turbo_capture_buttons = []
        for title, key in [('Shortcut modifier', 'turbo_modifier'), ('Dedicated Turbo control', 'turbo_control_button')]:
            combo = QComboBox(); self.controls[key] = combo
            container = QWidget(); container.setObjectName('BlueBridgeSurface'); row = QHBoxLayout(container); row.setContentsMargins(0, 0, 0, 0); row.addWidget(combo)
            button = self.button(row, 'Press Button', lambda c=combo: self.capture_input(lambda i: c.setCurrentIndex(c.findData(i))))
            self.turbo_capture_buttons.append(button)
            self.turbo_form.addRow(title, container)
        self.turbo_help = QLabel(); self.turbo_help.setWordWrap(True); self.turbo_form.addRow(self.turbo_help)
        self.form_control(self.turbo_form, 'Turbo rate (Hz)', 'turbo_rate_hz', low=1, high=30)
        turbo.addLayout(self.turbo_form)
        mode.currentIndexChanged.connect(self.render_turbo_help)
        self.controls['turbo_modifier'].currentIndexChanged.connect(self.render_turbo_help)
        self.turbo_buttons = QWidget(); self.turbo_buttons.setObjectName('BlueBridgeSurface'); self.turbo_checks_layout = QGridLayout(self.turbo_buttons); turbo.addWidget(self.turbo_buttons)
        turbo.addStretch()
        macros = self.page('Macros', self.editor_tabs)
        macros.addWidget(QLabel('Disabling a macro preserves its name, output buttons and assignment.'))
        self.macro_layout = QVBoxLayout(); macros.addLayout(self.macro_layout); macros.addStretch()
        advanced = self.page('Advanced', self.editor_tabs)
        self.profile_name = QLineEdit(); self.profile_name.setMaxLength(23)
        form = QFormLayout(); form.addRow('Profile name', self.profile_name); advanced.addLayout(form)
        note = QLabel('Profiles are output-independent. Mapping, analog, Turbo and macros stay with the profile when the global output changes.'); note.setWordWrap(True); advanced.addWidget(note)
        self.identity = QLabel(); self.identity.setWordWrap(True); advanced.addWidget(self.identity)
        self.mapping_identity = QComboBox(); advanced.addWidget(self.mapping_identity); advanced.addStretch()
        paired = self.page('Paired Controllers')
        row = QHBoxLayout(); row.addWidget(QLabel('Manage paired controllers and stored profiles, even while offline.'), 1); self.button(row, 'Back', lambda: self.pages.setCurrentIndex(0)); paired.addLayout(row)
        self.controller_search = QLineEdit(); self.controller_search.setPlaceholderText('Search paired controllers'); self.controller_search.textChanged.connect(self.render_paired); paired.addWidget(self.controller_search)
        self.paired_count = QLabel(); paired.addWidget(self.paired_count)
        self.paired_rows = QVBoxLayout(); paired.addLayout(self.paired_rows); paired.addStretch()
        firmware = self.page('Firmware & Configuration')
        row = QHBoxLayout(); row.addWidget(QLabel('Firmware & Configuration'), 1); self.button(row, 'Back', lambda: self.pages.setCurrentIndex(0)); firmware.addLayout(row)
        self.adapter_name_label = QLabel(); firmware.addWidget(self.adapter_name_label)
        row = QHBoxLayout(); self.adapter_rename_button = self.button(row, 'Rename Adapter', self.rename_adapter); self.adapter_reset_button = self.button(row, 'Reset Adapter Name', lambda: self.command('adapter/rename', {'name': ''})); firmware.addLayout(row)
        self.firmware_label = QLabel(); firmware.addWidget(self.firmware_label)
        self.github_widget = QWidget(); self.github_widget.setObjectName('BlueBridgeSurface'); gl = QHBoxLayout(self.github_widget); self.latest_label = QLabel(); gl.addWidget(self.latest_label, 1); self.download_button = self.button(gl, 'Download & Update', lambda: self.update_firmware(True)); firmware.addWidget(self.github_widget); self.github_widget.hide()
        self.configuration = QComboBox(); self.configuration.addItem('Preserve Configuration (recommended)', 'preserve'); self.configuration.addItem('Reset Configuration', 'reset'); firmware.addWidget(self.configuration)
        row = QHBoxLayout(); self.button(row, 'Select UF2 / Manual Update', lambda: self.update_firmware(False)); firmware.addLayout(row)
        row = QHBoxLayout(); self.button(row, 'Export Configuration', self.export_config); self.button(row, 'Import Configuration', self.import_config); self.button(row, 'Reset Configuration', self.reset_config); firmware.addLayout(row)
        row = QHBoxLayout(); self.button(row, 'Install on Another Pico', lambda: self.mode.setCurrentIndex(3)); firmware.addLayout(row); firmware.addStretch()

    def build_installer(self, outer):
        self.installer = QWidget(); layout = QVBoxLayout(self.installer)
        label = QLabel('Install / Recover MC BlueBridge\n\nRequires Raspberry Pi Pico 2 W. Hold BOOTSEL while connecting it to this computer, then release BOOTSEL. RP2350 detection alone cannot distinguish a Pico 2 W from other RP2350 boards.')
        label.setWordWrap(True); layout.addWidget(label)
        self.volumes = QComboBox(); layout.addWidget(self.volumes)
        self.manual_path = QLabel(); self.manual_path.setWordWrap(True); layout.addWidget(self.manual_path); self.manual_path.hide()
        row = QHBoxLayout(); self.button(row, 'Select MC BlueBridge UF2', self.select_uf2); self.button(row, 'Flash Selected UF2', lambda: self.flash(False)); layout.addLayout(row)
        self.install_online = QWidget(); row = QHBoxLayout(self.install_online); self.install_latest = QLabel(); row.addWidget(self.install_latest, 1); self.button(row, 'Download & Flash', lambda: self.flash(True)); layout.addWidget(self.install_online); self.install_online.hide()
        layout.addStretch(); outer.addWidget(self.installer, 1)

    def change_mode(self):
        if self.worker:
            if self.worker_quiet: self.defer(self.change_mode)
            return
        if self.service: self.service.close()
        self.service = None
        self.pages.hide(); self.installer.hide(); self.daemon_panel.setVisible(self.mode.currentIndex() == 1)
        self.adapters.clear(); self.adapters.hide()
        self.profile_data = {}; self.status_data = {}; self.github_widget.hide()
        self.managed_controller = None
        self.profile_panel.hide()
        self.pages.setCurrentIndex(0)
        mode = self.mode.currentIndex()
        self.chooser.setVisible(mode == 0)
        self.connection_bar.setVisible(mode != 0)
        if mode == 0:
            self.message.setText('Choose how to manage your adapter, or install MC BlueBridge on a Pico 2 W.')
        if mode != 3: self.auto_installer = False
        if mode == 1:
            if self.main_window.is_offline_mode() or not self.main_window.connection.is_connected():
                self.message.setText('Connect to a MiSTer in Online mode to use Remote. USB and Install / Recover are available without a MiSTer connection.')
                return
            self.main_window.remote_tab.refresh_state()
            self.message.setText('Checking Companion Remote daemon…')
        elif mode == 2:
            self.service = BlueBridgeService()
            self.service.adapter_id = self.preferred_adapter
            self.preferred_adapter = ''
            self.refresh()
        elif mode == 3:
            self.installer.show(); self.message.setText('Select firmware and a Pico 2 W in BOOTSEL mode.')
            self.run(lambda: (boot_volumes(), bluebridge_release()), self.installer_state)

    def daemon_action(self, command):
        remote = self.main_window.remote_tab
        if command == 'uninstall': remote.confirm_uninstall()
        else: remote.run_daemon_command(command)

    def sync_daemon(self):
        remote = self.main_window.remote_tab
        status = remote.last_status
        busy = bool(remote.command_worker or remote.status_worker)
        for button in self.daemon_buttons: button.setEnabled(not busy and self.worker is None and self.main_window.connection.is_connected())
        if not status:
            self.daemon_status.setText('Checking Companion Remote…')
            return
        self.daemon_status.setText(f'Companion Remote {status.version_label} · {"Running" if status.running else "Stopped"} · Start on boot: {"Enabled" if status.startup_enabled else "Disabled"}')
        self.daemon_buttons[2].setText('Disable Start on Boot' if status.startup_enabled else 'Enable Start on Boot')
        self.daemon_buttons[1].setText('Stop' if status.running else 'Start')
        if busy: return
        if not status.ready or status.update_available:
            self.pages.hide()
            self.message.setText('Install / Update and start Companion Remote to manage MC BlueBridge remotely.')
            if self.service: self.service.close(); self.service = None
            return
        host = remote.connected_host()
        if self.service is None or self.service.host != host:
            self.service = BlueBridgeService(host)
            self.refresh()

    def tick(self):
        if not self.active or self.worker or self.closing: return
        mode = self.mode.currentIndex()
        if mode == 1:
            if self.main_window.is_offline_mode() or not self.main_window.connection.is_connected():
                self.pages.hide(); self.service = None; return
            self.sync_daemon()
        elif mode == 3:
            self.poll_installer()
        if self.tester or self.capture_callback: return
        if self.service:
            if not self.service.adapter_id:
                self.refresh(quiet=True)
            elif time.monotonic() - self.last_inventory >= 10:
                self.last_inventory = time.monotonic()
                self.run(self.service.adapters, self.poll_inventory, quiet=True)
            else:
                self.run(lambda: self.service.api('status')['status'], self.poll_status, quiet=True)

    def poll_inventory(self, adapters):
        signature = [(a['id'], a['name']) for a in adapters]
        if signature != self.inventory_signature:
            self.render_adapters(adapters)

    def poll_status(self, status):
        previous = self.status_data
        changed = any(previous.get(key) != status.get(key) for key in ('connected', 'controller', 'controller_name', 'profile', 'firmware', 'detected'))
        if status != previous: self.render_status(status)
        if changed and status.get('detected'): self.defer(self.load_all)
        elif not status.get('detected'): self.defer(self.refresh)

    def refresh(self, force=False, quiet=False):
        if self.worker:
            if self.worker_quiet and not quiet: self.defer(lambda: self.refresh(force=force))
            return
        if self.mode.currentIndex() == 1 and self.service is None:
            self.main_window.remote_tab.refresh_state(); return
        if self.mode.currentIndex() == 3:
            self.run(lambda: (boot_volumes(), bluebridge_release()), self.installer_state); return
        if not self.service: return
        self.run(self.service.adapters, self.poll_inventory if quiet else self.render_adapters, quiet=quiet)

    def render_adapters(self, adapters):
        self.inventory_signature = [(a['id'], a['name']) for a in adapters]
        current = self.service.adapter_id
        self.adapters.blockSignals(True); self.adapters.clear()
        for adapter in adapters: self.adapters.addItem(adapter['name'], adapter['id'])
        index = self.adapters.findData(current)
        self.adapters.setCurrentIndex(index if index >= 0 else 0); self.adapters.blockSignals(False)
        self.adapters.setVisible(len(adapters) > 1)
        if not adapters:
            self.pages.hide(); self.message.setText('No MC BlueBridge adapter detected. Connect an adapter or choose Install / Recover.')
            self.service.adapter_id = ''
            if self.main_window.is_offline_mode():
                self.auto_installer = True
                self.defer(lambda: self.mode.setCurrentIndex(3))
        else:
            self.service.adapter_id = self.adapters.currentData()
            self.defer(self.load_all)

    def select_adapter(self):
        if not self.service: return
        if self.worker:
            if self.worker_quiet: self.defer(self.select_adapter)
            return
        self.service.adapter_id = self.adapters.currentData() or ''
        self.managed_controller = None
        self.profiles.clear()
        self.load_all()

    def load_all(self):
        if not self.service or self.worker: return
        service = self.service
        selected_index = self.profiles.currentData()
        managed = self.managed_controller
        def work():
            status = service.api('status')['status']
            controllers = service.api('controllers')['controllers']
            profiles, profile = {}, {}
            stored = controllers.get('controllers', [])
            connected = controllers.get('connected_index', -1)
            target = managed if managed is not None else connected
            if any(c.get('index') == target for c in stored):
                profiles = service.api('profiles')['profiles']
                if profiles.get('controller_index') != target:
                    service.api('controllers/select', {'index': target})
                    profiles = service.api('profiles')['profiles']
                    index = profiles.get('active', 0)
                else:
                    index = selected_index
                    if index not in [p['index'] for p in profiles.get('profiles', [])]: index = profiles.get('active', 0)
                profile = service.api('profile?index=' + str(index))['profile']
            return status, controllers, profiles, profile, service.api('firmware/releases').get('release', {})
        self.run(work, self.render_all)

    def render_status(self, status):
        self.status_data = status
        if not status.get('detected'):
            self.pages.hide(); self.message.setText(status.get('message', 'Adapter disconnected')); return
        live = next((c.get('name') for c in self.controllers_data.get('controllers', []) if c.get('index') == self.controllers_data.get('connected_index')), 'None')
        self.summary.setText(f"{status.get('adapter_name', 'MC BlueBridge adapter')} · Firmware v{status.get('firmware', '?')}\nController: {status.get('controller', status.get('controller_name', live))} · Profile: {status.get('profile', '-')}\nBattery: {str(status.get('battery_percent')) + '%' if status.get('battery_supported') else 'Unavailable'} · Bluetooth: {'Ready' if status.get('bt_ready') else 'Not ready'} · USB: {'Ready' if status.get('usb_ready') else 'Not ready'}")
        self.pair_button.setVisible(not status.get('connected'))
        self.pair_button.setText('Stop Pairing' if status.get('pairing') else 'Start Pairing')
        self.disconnect_button.setVisible(bool(status.get('connected')))
        self.tester_button.setVisible(bool(status.get('connected')))
        self.output.setCurrentIndex(max(0, min(3, int(status.get('output_mode', 1)) - 1)))
        self.mapping_identity.setVisible(int(status.get('output_mode', 1)) == 1)
        self.adapter_name_label.setText(status.get('adapter_name', 'MC BlueBridge adapter'))
        naming = status.get('capabilities', {}).get('adapter_rename', False)
        self.adapter_rename_button.setEnabled(bool(naming))
        self.adapter_reset_button.setEnabled(bool(naming and status.get('adapter_custom_name')))
        self.firmware_label.setText(f"Installed firmware: v{status.get('firmware', '?')} · Configuration schema: {status.get('config_schema', '?')}")

    def render_all(self, result):
        status, controllers, profiles, profile, release = result
        self.controllers_data = controllers; self.profiles_data = profiles; self.render_status(status)
        self.controllers.clear()
        for controller in controllers.get('controllers', []): self.controllers.addItem(controller.get('name', 'Controller') + (' · Connected' if controller.get('connected') else ' · Offline'), controller['index'])
        self.controllers.setCurrentIndex(self.controllers.findData(profiles.get('controller_index')))
        self.profiles.clear()
        for item in profiles.get('profiles', []): self.profiles.addItem(item['name'], item['index'])
        self.profiles.setCurrentIndex(self.profiles.findData(profile.get('index')))
        self.render_profile(profile)
        self.profile_panel.setVisible(bool(profile))
        selected = next((c for c in controllers.get('controllers', []) if c.get('index') == profiles.get('controller_index')), {})
        self.profile_panel.setTitle(selected.get('name', 'Controller') + ' Profiles')
        self.profile_state.setText('Connected controller' if selected.get('connected') else 'Paired · Offline — stored settings remain editable')
        self.close_controller_button.setVisible(bool(profile) and self.managed_controller is not None and not selected.get('connected'))
        self.profile_buttons['Activate'].setVisible(bool(selected.get('connected')))
        self.profile_buttons['Delete'].setEnabled(profile.get('index', 0) != 0)
        self.render_paired()
        self.github_widget.setVisible(bool(release.get('available')))
        self.latest_label.setText('Latest firmware: v' + release.get('version', ''))
        self.download_button.setEnabled(bool(release.get('update_available')))
        self.pages.setVisible(bool(status.get('detected')))
        self.message.setText('MC BlueBridge connected via ' + ('Remote' if self.service.host else 'USB'))

    def load_profile(self):
        index = self.profiles.currentData()
        if index is not None:
            self.run(lambda: self.service.api('profile?index=' + str(index))['profile'], self.render_profile)

    def labels(self):
        return self.profiles_data.get('labels', ['Button ' + str(i + 1) for i in range(26)])

    def physical_buttons(self):
        mask = int(self.profiles_data.get('capabilities', {}).get('buttons', 67108863))
        if self.status_data.get('connected') and self.profiles_data.get('controller_index') == self.controllers_data.get('connected_index') and self.status_data.get('button_capabilities'): mask &= int(self.status_data['button_capabilities'])
        return [(i, name) for i, name in enumerate(self.labels()) if mask & (1 << i)]

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            elif item.layout(): self.clear_layout(item.layout())

    def button_choices(self, combo, selected=255):
        combo.clear(); combo.addItem('None', 255)
        for i, name in self.physical_buttons(): combo.addItem(name, i)
        combo.setCurrentIndex(max(0, combo.findData(selected)))

    def output_checks(self, layout, mask):
        checks = []
        for i, name in enumerate(self.labels()[:16]):
            check = QCheckBox(name); check.setChecked(bool(mask & (1 << i))); layout.addWidget(check, i // 4, i % 4); checks.append(check)
        return checks

    def render_profile(self, profile):
        self.profile_data = profile
        self.profile_name.setText(profile.get('name', ''))
        self.profile_buttons['Delete'].setEnabled(profile.get('index', 0) != 0)
        while self.mapping_form.rowCount(): self.mapping_form.removeRow(0)
        self.mapping = {}
        for i, name in self.physical_buttons():
            row = QHBoxLayout(); combo = QComboBox()
            for j, label in enumerate(self.labels()[:16]): combo.addItem(label, j)
            for j in range(4):
                macro = (profile.get('macros', []) + [{}] * 4)[j]
                combo.addItem((macro.get('name') or 'Unnamed macro') + ('' if macro.get('enabled') else ' (disabled)'), 16 + j)
            combo.addItem('Turbo control', 21 if profile.get('turbo_control_mode') == 2 else 20)
            combo.addItem('Disabled', 22)
            values = profile.get('map', [])
            combo.setCurrentIndex(max(0, combo.findData(values[i] if i < len(values) else 22)))
            self.mapping[i] = combo; row.addWidget(combo)
            combo.activated.connect(self.sync_macro_from_mapping)
            button = self.button(row, 'Press Button', lambda c=combo: self.capture_input(lambda n: self.capture_destination(c, n)))
            button.setVisible(self.is_selected_live())
            self.mapping_form.addRow(name, row)
        caps = self.profiles_data.get('capabilities', {})
        for key, control in self.controls.items():
            value = profile.get(key, False if isinstance(control, QCheckBox) else 0)
            if isinstance(control, QCheckBox): control.setChecked(bool(value))
            elif isinstance(control, QSpinBox): control.setValue(int(value))
            elif key == 'turbo_control_mode': control.setCurrentIndex(int(value))
            elif isinstance(control, QComboBox): self.button_choices(control, int(value))
        for key, capability in [('invert_x','left_stick'),('invert_y','left_stick'),('invert_rx','right_stick'),('invert_ry','right_stick'),('deadzone_left','left_stick'),('deadzone_right','right_stick')]: self.analog_form.setRowVisible(self.controls[key], caps.get(capability, True))
        self.analog_form.setRowVisible(self.controls['trigger_deadzone'], caps.get('left_trigger', True) or caps.get('right_trigger', True))
        self.source_capture_button.setVisible(self.is_selected_live())
        for button in self.turbo_capture_buttons: button.setVisible(self.is_selected_live())
        self.render_turbo_help()
        self.clear_layout(self.turbo_checks_layout)
        self.turbo_checks = self.output_checks(self.turbo_checks_layout, int(profile.get('turbo_mask', 0)))
        self.clear_layout(self.macro_layout); self.macros = []
        for m in range(4):
            macro = (profile.get('macros', []) + [{}] * 4)[m]
            form = QFormLayout(); name = QLineEdit(macro.get('name', '')); name.setMaxLength(15); enabled = QCheckBox(); enabled.setChecked(bool(macro.get('enabled')))
            form.addRow('Macro ' + str(m + 1), name); form.addRow('Enabled', enabled)
            assign = QComboBox(); assignment = next((i for i, v in enumerate(profile.get('map', [])) if v == 16 + m), 255); self.button_choices(assign, assignment); form.addRow('Activation button', assign)
            row = QHBoxLayout(); button = self.button(row, 'Press Button', lambda c=assign: self.capture_input(lambda i: self.assign_macro_capture(c, i))); button.setVisible(self.is_selected_live()); form.addRow(row)
            macro_state = QLabel('Not assigned' if assignment == 255 else 'Activated by ' + self.labels()[assignment]); form.addRow(macro_state)
            assign.currentIndexChanged.connect(lambda _, c=assign, label=macro_state: label.setText('Not assigned' if c.currentData() == 255 else 'Activated by ' + c.currentText()))
            grid = QGridLayout(); checks = self.output_checks(grid, int(macro.get('output_mask', 0))); form.addRow(grid)
            self.macro_layout.addLayout(form); self.macros.append((name, enabled, assign, checks, assignment))
            assign.activated.connect(lambda _, slot=m: self.sync_macro_assignment(slot))
            name.textChanged.connect(self.refresh_mapping_options)
            enabled.toggled.connect(self.refresh_mapping_options)
        controller = next((c for c in self.controllers_data.get('controllers', []) if c['index'] == self.profiles_data.get('controller_index')), {})
        identity = f"Controller: {controller.get('name', '-')}\nNative VID: 0x{int(controller.get('native_vid', 0)):04X} · Native PID: 0x{int(controller.get('native_pid', 0)):04X}"
        if int(self.status_data.get('output_mode', 1)) == 1: identity += f"\nMiSTer virtual PID: 0x{int(profile.get('mister_identity', 0)):04X}"
        self.identity.setText(identity)
        self.mapping_identity.clear(); self.mapping_identity.addItem('Separate MiSTer mapping', -1)
        for item in self.profiles_data.get('profiles', []):
            if item['index'] != profile.get('index'): self.mapping_identity.addItem('Share with ' + item['name'], item['index'])
        self.mapping_identity.setCurrentIndex(max(0, self.mapping_identity.findData(profile.get('shared_with', -1) if profile.get('mapping_mode') == 'shared' else -1)))
        self.render_identity()
        self.refresh_mapping_options()

    def is_selected_live(self):
        return any(c.get('connected') and c.get('index') == self.profiles_data.get('controller_index') for c in self.controllers_data.get('controllers', []))

    def show_paired(self):
        self.managed_controller = None
        self.pages.setCurrentIndex(1)
        self.render_paired()
        self.defer(self.load_all)

    def render_paired(self):
        self.clear_layout(self.paired_rows)
        query = self.controller_search.text().lower()
        controllers = [c for c in self.controllers_data.get('controllers', []) if query in c.get('name', '').lower()]
        self.paired_count.setText(str(len(controllers)) + ' paired controller' + ('' if len(controllers) == 1 else 's'))
        naming = self.status_data.get('capabilities', {}).get('controller_rename', False)
        for controller in controllers:
            index = controller['index']
            card = QGroupBox(controller.get('name', 'Controller'))
            row = QHBoxLayout(card)
            count = controller.get('profiles', 0)
            row.addWidget(QLabel(('Connected' if controller.get('connected') else 'Offline') + ' · ' + str(count) + ' profile' + ('' if count == 1 else 's')), 1)
            self.button(row, 'Manage', lambda i=index: self.manage_controller(i))
            rename = self.button(row, 'Rename', lambda i=index: self.rename_controller(i)); rename.setEnabled(bool(naming))
            reset = self.button(row, 'Reset Name', lambda i=index: self.command('controllers/rename', {'index': i, 'name': ''})); reset.setEnabled(bool(naming and controller.get('custom_name')))
            self.button(row, 'Forget', lambda i=index: self.forget_controller(i))
            self.paired_rows.addWidget(card)

    def manage_controller(self, index):
        controller = next((c for c in self.controllers_data.get('controllers', []) if c.get('index') == index), None)
        if not controller: return
        self.managed_controller = None if controller.get('connected') else index
        self.profiles.clear()
        self.profile_data = {}
        self.pages.setCurrentIndex(0)
        self.command('controllers/select', {'index': index})

    def close_managed_controller(self):
        if self.worker:
            self.defer(self.close_managed_controller)
            return
        index = self.managed_controller
        if index is None or index == self.controllers_data.get('connected_index'):
            return
        self.managed_controller = None
        self.profiles.clear()
        self.profile_data = {}
        self.profile_panel.hide()
        self.close_controller_button.hide()
        self.load_all()

    def disconnect_controller(self):
        if not self.confirm('Disconnect this controller? Pairing and profiles will be preserved.'): return
        self.managed_controller = None
        self.profile_panel.hide()
        self.command('controllers/disconnect', {})

    def change_output(self):
        mode = self.output.currentData()
        def done(_):
            self.status_data['output_mode'] = mode
            self.mapping_identity.setVisible(mode == 1)
            self.render_identity()
            self.message.setText('Output changed. Profile settings are preserved.')
        self.run(lambda: self.service.api('output', {'mode': mode}), done)

    def render_turbo_help(self, *args):
        mode = self.controls['turbo_control_mode'].currentIndex()
        for key, visible in [('turbo_modifier', mode == 0), ('turbo_control_button', mode != 0)]:
            self.turbo_form.setRowVisible(self.controls[key].parentWidget(), visible)
        self.turbo_help.setVisible(mode == 0)
        self.turbo_help.setText(self.controls['turbo_modifier'].currentText() + ' + a controller button toggles Turbo for that button. The shortcut is consumed and is not sent to the output.')
        self.refresh_mapping_options()

    def refresh_mapping_options(self, *args):
        turbo = 21 if self.controls['turbo_control_mode'].currentIndex() == 2 else 20
        for combo in self.mapping.values():
            for m, (name, enabled, _, _, _) in enumerate(self.macros):
                i = combo.findData(16 + m)
                if i >= 0: combo.setItemText(i, (name.text() or 'Unnamed macro') + ('' if enabled.isChecked() else ' (disabled)'))
            old = combo.findData(20)
            if old < 0: old = combo.findData(21)
            if old >= 0: combo.setItemData(old, turbo)

    def capture_destination(self, combo, button):
        if button >= 16:
            self.message.setText('That extended input cannot be used as a direct output.')
            return
        combo.setCurrentIndex(combo.findData(button))
        self.sync_macro_from_mapping()

    def sync_macro_from_mapping(self, *args):
        for m, (_, _, assign, _, _) in enumerate(self.macros):
            source = next((i for i, combo in self.mapping.items() if combo.currentData() == 16 + m), 255)
            assign.blockSignals(True); assign.setCurrentIndex(assign.findData(source)); assign.blockSignals(False)

    def sync_macro_assignment(self, slot):
        source = self.macros[slot][2].currentData()
        for i, combo in self.mapping.items():
            if combo.currentData() == 16 + slot: combo.setCurrentIndex(combo.findData(i if i < 16 else 22))
        if source in self.mapping:
            self.mapping[source].setCurrentIndex(self.mapping[source].findData(16 + slot))
        self.sync_macro_from_mapping()

    def assign_macro_capture(self, combo, button):
        combo.setCurrentIndex(combo.findData(button))
        slot = next((i for i, macro in enumerate(self.macros) if macro[2] is combo), None)
        if slot is not None: self.sync_macro_assignment(slot)

    def render_identity(self):
        controller = next((c for c in self.controllers_data.get('controllers', []) if c.get('index') == self.profiles_data.get('controller_index')), {})
        identity = 'Controller: ' + controller.get('name', '-')
        identity += f"\nNative VID: 0x{int(controller.get('native_vid', 0)):04X} · Native PID: 0x{int(controller.get('native_pid', 0)):04X}"
        if int(self.status_data.get('output_mode', 1)) == 1: identity += f"\nMiSTer virtual PID: 0x{int(self.profile_data.get('mister_identity', 0)):04X}"
        self.identity.setText(identity)

    def cancel_capture(self):
        self.capture_callback = None
        self.capture_timer.stop()
        self.capture_cancel_button.hide()
        if self.service: self.defer(lambda: self.run(lambda: self.service.api('capture/stop', {})))
        self.message.setText('Input capture cancelled.')

    def command(self, path, payload):
        self.run(lambda: self.service.api(path, payload), lambda _: self.defer(self.load_all))

    def ask_name(self, title, value='', limit=23):
        name, ok = QInputDialog.getText(self, title, 'Name:', text=value)
        if not ok: return None
        if len(name.encode('utf-8')) > limit or any(c in name for c in '|\r\n'):
            self.message.setText(f'Name must be at most {limit} bytes and contain no | or line breaks.'); return None
        return name

    def rename_adapter(self):
        if not self.status_data.get('capabilities', {}).get('adapter_rename'): self.message.setText('Update firmware to rename adapters.'); return
        name = self.ask_name('Rename Adapter', self.status_data.get('adapter_custom_name', ''), 31)
        if name is not None: self.command('adapter/rename', {'name': name})

    def rename_controller(self, index=None):
        if not self.status_data.get('capabilities', {}).get('controller_rename'): self.message.setText('Update firmware to rename controllers.'); return
        if index is None: index = self.controllers.currentData()
        controller = next((c for c in self.controllers_data.get('controllers', []) if c.get('index') == index), {})
        name = self.ask_name('Rename Controller', controller.get('custom_name') or controller.get('name', ''), limit=31)
        if name is not None: self.command('controllers/rename', {'index': index, 'name': name})

    def confirm(self, message):
        return QMessageBox.question(self, 'MC BlueBridge', message) == QMessageBox.StandardButton.Yes

    def forget_controller(self, index=None):
        if index is None: index = self.controllers.currentData()
        if self.confirm('Forget this controller and delete its profiles?'):
            if self.managed_controller == index: self.managed_controller = None
            self.command('controllers/forget', {'index': index})

    def profile_action(self, action):
        index = self.profiles.currentData()
        if action == 'Delete':
            if index == 0: self.message.setText('The default profile cannot be deleted.'); return
            if not self.confirm('Delete this profile?'): return
        if action == 'Activate' and self.profiles_data.get('controller_index') != self.controllers_data.get('connected_index'):
            self.message.setText('Connect this controller before activating its profile.'); return
        payload = {'index': index}
        if action in ('Create','Duplicate','Rename'):
            name = self.ask_name(action + ' Profile', self.profiles.currentText() + (' Copy' if action == 'Duplicate' else '') if action != 'Create' else '')
            if name is None: return
            import re
            if not re.fullmatch(r'[A-Za-z0-9 _.-]{1,23}', name): self.message.setText('Use 1–23 letters, numbers, spaces, underscores, dots or hyphens.'); return
            payload['name'] = name
        self.command('profiles/' + ('select' if action == 'Activate' else action.lower()), payload)

    def reset_mapping(self):
        for i, combo in self.mapping.items(): combo.setCurrentIndex(max(0, combo.findData(i if i < 16 else 22)))
        self.sync_macro_from_mapping()

    def save_profile(self):
        if not self.profile_data: return
        index = self.profile_data['index']
        new_name = self.profile_name.text().strip()
        import re
        if not re.fullmatch(r'[A-Za-z0-9 _.-]{1,23}', new_name):
            self.message.setText('Use 1–23 letters, numbers, spaces, underscores, dots or hyphens for the profile name.')
            return
        identity_target = self.mapping_identity.currentData()
        mister_mode = self.status_data.get('output_mode', 1) == 1
        mapping = list(self.profile_data.get('map', []))
        for i, combo in self.mapping.items(): mapping[i] = combo.currentData()
        macros = []
        for m, (name, enabled, assign, checks, previous) in enumerate(self.macros):
            if assign.currentData() != previous:
                for i, value in enumerate(mapping):
                    if value == 16 + m: mapping[i] = i if i < 16 else 22
                if assign.currentData() != 255: mapping[assign.currentData()] = 16 + m
            macros.append({'profile': index, 'macro': m, 'name': name.text(), 'enabled': enabled.isChecked(), 'output_mask': sum(1 << i for i, c in enumerate(checks) if c.isChecked())})
        tuning = {'profile': index, 'turbo_mask': sum(1 << i for i, c in enumerate(self.turbo_checks) if c.isChecked())}
        for key, control in self.controls.items():
            tuning[key] = control.isChecked() if isinstance(control, QCheckBox) else control.value() if isinstance(control, QSpinBox) else control.currentIndex() if key == 'turbo_control_mode' else control.currentData()
        def work():
            if new_name != self.profile_data.get('name'): self.service.api('profiles/rename', {'index': index, 'name': new_name})
            for i, value in enumerate(mapping):
                if value != self.profile_data['map'][i]: self.service.api('profile/map', {'profile': index, 'input': i, 'output': value})
            self.service.api('profile/tuning', tuning)
            for macro in macros: self.service.api('profile/macro', macro)
            if mister_mode:
                self.service.api('profile/mister-mapping', {'profile': index, 'mode': 'share' if identity_target >= 0 else 'separate', 'target': identity_target})
        self.run(work, lambda _: self.defer(self.load_all))

    def save_identity(self):
        target = self.mapping_identity.currentData()
        self.command('profile/mister-mapping', {'profile': self.profile_data['index'], 'mode': 'share' if target >= 0 else 'separate', 'target': target})

    def capture_input(self, callback):
        if self.profiles_data.get('controller_index') != self.controllers_data.get('connected_index'): self.message.setText('Connect this controller to capture input.'); return
        self.capture_callback = callback
        self.capture_cancel_button.show()
        self.capture_deadline = time.monotonic() + 10
        self.run(lambda: self.service.api('capture/start', {'mode': 'ONCE'}), lambda _: self.capture_timer.start())
        self.message.setText('Press a controller button…')

    def open_tester(self):
        connected = self.controllers_data.get('connected_index', -1)
        if connected < 0: return
        self.managed_controller = None
        def work():
            self.service.api('controllers/select', {'index': connected})
            profiles = self.service.api('profiles')['profiles']
            self.service.api('capture/start', {'mode': 'TESTER'})
            return profiles
        self.run(work, self.show_tester)

    def show_tester(self, profiles):
        self.profiles_data = profiles
        dialog = QDialog(self); dialog.setWindowTitle('MC BlueBridge Controller Tester'); dialog.resize(650, 450)
        layout = QVBoxLayout(dialog); layout.addWidget(QLabel('Controller input is captured while the tester is open.'))
        self.tester_view = QComboBox(); self.tester_view.addItem('Raw Input', 'raw')
        if self.status_data.get('capabilities', {}).get('remapped_tester'): self.tester_view.addItem('Remapped Output', 'output')
        layout.addWidget(self.tester_view)
        self.test_buttons = QLabel(); self.test_buttons.setWordWrap(True); layout.addWidget(self.test_buttons)
        self.test_axes = QLabel(); self.test_axes.setWordWrap(True); layout.addWidget(self.test_axes)
        row = QHBoxLayout(); self.rumble_strength = QComboBox()
        for percent, strength in [(25,64),(50,128),(75,192),(100,255)]: self.rumble_strength.addItem(str(percent) + '%', strength)
        self.rumble_strength.setCurrentIndex(1)
        row.addWidget(self.rumble_strength)
        self.rumble_button = self.button(row, 'Test Rumble', self.test_rumble)
        layout.addLayout(row); close = QPushButton('Close'); close.clicked.connect(dialog.close); layout.addWidget(close)
        dialog.finished.connect(self.stop_tester); self.tester = dialog
        self.mode.setEnabled(False); self.adapters.setEnabled(False)
        dialog.show(); self.capture_timer.start()

    def test_rumble(self):
        strength = self.rumble_strength.currentData()
        self.run(lambda: self.service.api('rumble', {'strength': strength, 'duration': 500}))

    def poll_capture(self):
        if self.worker or not self.service: return
        self.run(lambda: self.service.api('capture/status')['capture'], self.render_capture, quiet=True)

    def render_capture(self, capture):
        if self.capture_callback:
            button = capture.get('button', capture.get('input', capture.get('source', -1)))
            if capture.get('ready') and button is not None and 0 <= int(button) < len(self.labels()):
                callback = self.capture_callback; self.capture_callback = None; self.capture_cancel_button.hide(); callback(int(button)); self.capture_timer.stop()
                self.defer(lambda: self.run(lambda: self.service.api('capture/stop', {})))
            elif time.monotonic() > self.capture_deadline:
                self.capture_callback = None; self.capture_cancel_button.hide(); self.capture_timer.stop(); self.defer(lambda: self.run(lambda: self.service.api('capture/stop', {})))
                self.message.setText('Input capture timed out.')
            return
        if not self.tester: return
        if not capture.get('mode'):
            self.tester.close(); return
        output = self.tester_view.currentData() == 'output'
        data = capture.get('output', {}) if output else capture
        buttons = int(data.get('buttons', 0))
        labels = list(enumerate(self.labels()[:16])) if output else self.physical_buttons()
        self.test_buttons.setText('\n'.join(('● ' if buttons & (1 << i) else '○ ') + name for i, name in labels))
        caps = {'dpad':True,'left_stick':True,'right_stick':True,'left_trigger':True,'right_trigger':True} if output else self.profiles_data.get('capabilities', {})
        rows = []
        hat = int(data.get('hat', 0))
        dpad = ([0,1,9,8,10,2,6,4,5][hat] if 0 <= hat <= 8 else 0) if output else int(data.get('dpad', 0))
        if caps.get('dpad'): rows.append('D-pad: ' + (' + '.join(label for mask, label in [(1,'Up'),(2,'Down'),(4,'Left'),(8,'Right')] if dpad & mask) or 'Neutral'))
        if caps.get('left_stick'): rows.append(f"Left stick: X {data.get('x',0)} / Y {data.get('y',0)}")
        if caps.get('right_stick'): rows.append(f"Right stick: X {data.get('rx',0)} / Y {data.get('ry',0)}")
        for key, cap, title in [('lt','left_trigger','Left trigger'),('rt','right_trigger','Right trigger')]:
            if caps.get(cap): rows.append(title + ': ' + str(data.get(key, 0)))
        rows.append('Battery: ' + (str(capture.get('battery_percent', 0)) + '%' if capture.get('battery_supported') else 'Unavailable'))
        self.test_axes.setText('\n'.join(rows)); self.rumble_button.setEnabled(bool(capture.get('rumble_supported')))

    def stop_tester(self):
        self.capture_timer.stop()
        dialog = self.tester; self.tester = None
        if dialog: dialog.deleteLater()
        if self.service and not self.closing:
            self.defer(lambda: self.run(lambda: self.service.api('capture/stop', {}), lambda _: self.defer(self.load_all)))

    def update_firmware(self, online):
        self.message.setText('Downloading and validating firmware…' if online else 'Select firmware to validate before updating.')
        if online:
            self.run(lambda: self.service.api('firmware/download', {}), self.confirm_firmware)
        else:
            path, _ = QFileDialog.getOpenFileName(self, 'Select MC BlueBridge Firmware', '', 'UF2 Firmware (*.uf2)')
            if path: self.run(lambda: self.service.api('firmware/inspect', data=Path(path).read_bytes()), self.confirm_firmware)

    def confirm_firmware(self, result):
        info = result['firmware']; relation = info.get('relation')
        warning = '\nThis is the same installed version.' if relation == 'same' else '\nThis is older firmware. Newer settings may be incompatible.' if relation == 'older' else ''
        configuration = self.configuration.currentData()
        accepted = self.confirm(f"Install v{info['version']} over v{info['current_version']}?\n{self.configuration.currentText()}\nThe adapter will restart.{warning}")
        if accepted:
            self.message.setText('Installing firmware… The adapter will disconnect and restart.')
            self.defer(lambda: self.run(lambda: self.service.api('firmware/install', {'configuration': configuration}), self.firmware_complete))
        else:
            self.defer(lambda: self.run(lambda: self.service.api('firmware/cancel', {})))

    def firmware_complete(self, result):
        self.message.setText(result.get('firmware', {}).get('message', 'Firmware installed.'))
        self.defer(self.load_all)

    def export_config(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export Configuration', 'MC-BlueBridge-Backup.bbconfig', 'BlueBridge Configuration (*.bbconfig)')
        if path:
            def work(): Path(path).write_text(json.dumps(self.service.api('config/export'), indent=2))
            self.run(work, lambda _: self.message.setText('Configuration exported.'))

    def import_config(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import Configuration', '', 'BlueBridge Configuration (*.bbconfig)')
        if path and self.confirm('Replace this adapter configuration with the selected backup?'):
            self.run(lambda: self.service.api('config/import', json.loads(Path(path).read_text())), lambda _: self.defer(self.load_all))

    def reset_config(self):
        if self.confirm('Reset configuration and forget all controllers? Export a backup first if you want to restore them later.'): self.command('config/reset', {})

    def installer_state(self, result):
        volumes, release = result; self.installer_release = release
        self.render_volumes(volumes); self.install_online.setVisible(bool(release.get('available'))); self.install_latest.setText('Latest firmware: v' + release.get('version', ''))

    def render_volumes(self, volumes):
        existing = [self.volumes.itemData(i) for i in range(self.volumes.count()) if self.volumes.itemData(i) is not None]
        if self.volumes.count() and existing == volumes:
            return
        self.volumes.blockSignals(True)
        current = self.volumes.currentText(); self.volumes.clear(); self.volumes.addItems(volumes)
        if current in volumes: self.volumes.setCurrentText(current)
        if not volumes: self.volumes.addItem('Waiting for RP2350 BOOTSEL device…', None)
        else:
            for i, volume in enumerate(volumes): self.volumes.setItemData(i, volume)
        self.volumes.blockSignals(False)

    def poll_installer(self):
        auto = self.auto_installer and self.main_window.is_offline_mode()
        def work():
            volumes = boot_volumes()
            adapters = []
            if auto:
                service = BlueBridgeService()
                try: adapters = service.adapters()
                finally: service.close()
            return volumes, adapters
        def done(result):
            volumes, adapters = result
            self.render_volumes(volumes)
            if adapters:
                self.preferred_adapter = adapters[0]['id']
                self.defer(lambda: self.mode.setCurrentIndex(2))
        self.run(work, done, quiet=True)

    def select_uf2(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select MC BlueBridge Firmware', '', 'UF2 Firmware (*.uf2)')
        if path:
            self.manual_path.setText(path)
            self.manual_path.show()

    def flash(self, online):
        volume = self.volumes.currentData()
        if not volume: self.message.setText('Connect a Pico 2 W in BOOTSEL mode first.'); return
        path = self.manual_path.text()
        if not online and not path: self.message.setText('Select an MC BlueBridge UF2 first.'); return
        if not self.confirm('Confirm this is a Raspberry Pi Pico 2 W. Flash MC BlueBridge onto the selected device?'): return
        release = dict(self.installer_release)
        self.message.setText('Validating and flashing firmware… Waiting for the adapter to restart.')
        def work():
            previous_ids = {p.serial_number or p.device for p in list_ports.comports()}
            data = download_bluebridge_release(release) if online else Path(path).read_bytes()
            if len(data) > 8 * 1024 * 1024: raise ValueError('Firmware file too large')
            info = _uf2_info(data)
            if online and version_key(info['version']) != version_key(release['version']): raise ValueError('Firmware does not match release tag')
            flash_volume(data, volume)
            service = BlueBridgeService(); end = time.monotonic() + 60
            while time.monotonic() < end:
                found = service.adapters()
                new_adapter = next((a["id"] for a in found if a["id"] not in previous_ids), None)
                if new_adapter:
                    service.close(); return new_adapter
                time.sleep(0.5)
            service.close(); return False
        self.run(work, self.flash_complete)

    def flash_complete(self, detected):
        self.message.setText('Firmware installed.' if detected else 'Firmware transferred. Reconnect the adapter to verify it starts normally.')
        if detected:
            self.preferred_adapter = detected
            self.defer(lambda: self.mode.setCurrentIndex(2))

    def update_connection_state(self, lightweight=True):
        offline = self.main_window.is_offline_mode()
        self.mode.model().item(1).setEnabled(not offline)
        self.choice_buttons[0].setEnabled(not offline)
        if self.worker: return
        if offline and self.mode.currentIndex() in (0, 1) and not self.worker: self.mode.setCurrentIndex(2)
        elif self.mode.currentIndex() == 1 and not self.main_window.connection.is_connected(): self.pages.hide()

    def set_tab_active(self, active):
        self.active = bool(active)
        if active:
            self.update_connection_state()
            if self.mode.currentIndex() == 1: self.sync_daemon()
        elif self.tester:
            self.tester.close()
        elif self.capture_callback:
            self.cancel_capture()

    def shutdown(self):
        self.closing = True; self.timer.stop(); self.capture_timer.stop()
        if self.worker: self.worker.wait()
        if self.service:
            try: self.service.api('capture/stop', {})
            except Exception: pass
            self.service.close()

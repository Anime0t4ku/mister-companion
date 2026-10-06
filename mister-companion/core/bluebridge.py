import json
import os
import time
from pathlib import Path
import requests
import serial
from serial.tools import list_ports
import psutil
from core.bluebridge_protocol import BlueBridgeManager, _uf2_info, _inspect_bluebridge_firmware
from core.bluebridge_releases import version_key, bluebridge_release, download_bluebridge_release
from core.remote_daemon import REMOTE_DAEMON_PORT


def boot_volumes():
    found = []
    for part in psutil.disk_partitions(all=True):
        path = Path(part.mountpoint)
        try:
            info = (path / 'INFO_UF2.TXT').read_text(errors='replace')
            if 'RP2350' in info:
                found.append(str(path))
        except OSError:
            pass
    return sorted(set(found))


def flash_volume(data, volume):
    info = _uf2_info(data)
    if volume not in boot_volumes():
        raise RuntimeError('The selected RP2350 BOOTSEL volume is no longer available')
    with open(Path(volume) / 'mc_bluebridge.uf2', 'wb', buffering=0) as target:
        target.write(data)
        os.fsync(target.fileno())
    return info


class USBAdapter(BlueBridgeManager):
    def __init__(self, port, info):
        super().__init__(info.get('serial') or port)
        self.path = port
        self.info = info
        self.connection = None
        self.staged = None

    def connect(self):
        if self.connection and self.connection.is_open:
            return
        ports = [p for p in list_ports.comports() if (p.serial_number or p.device) == self.adapter_id]
        if not ports:
            raise RuntimeError('Selected MC BlueBridge adapter is disconnected')
        self.path = ports[0].device
        self.connection = serial.Serial(self.path, 115200, timeout=0.15, write_timeout=3)
        self.rx = b''
        try:
            hello = self.request_json('HELLO')
            if hello.get('protocol') != 2 or hello.get('hardware') != 'Pico 2 W' or not str(hello.get('firmware_id', '')).startswith('MCBLUEBRIDGE|'):
                raise RuntimeError('This device is not MC BlueBridge')
            if hello.get('adapter_id') and hello['adapter_id'] != self.adapter_id:
                raise RuntimeError('Adapter identity changed')
            self.adapter_name = hello.get('adapter_name') or 'MC BlueBridge adapter'
            self.verified = True
        except Exception:
            self.close()
            raise

    def close(self):
        if self.connection:
            self.connection.close()
        self.connection = None

    def _write(self, data):
        self.connection.write(data.encode('utf-8'))

    def _readline(self, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            pos = self.rx.find(b'\n')
            if pos >= 0:
                result, self.rx = self.rx[:pos], self.rx[pos + 1:]
                return result.decode('utf-8').rstrip('\r')
            self.rx += self.connection.read(max(1, self.connection.in_waiting))
        raise TimeoutError('BlueBridge did not respond')

    def reset_configuration(self):
        self.request('FORGET_ALL', timeout=4)
        try:
            self.request('CONFIG_RESET', timeout=2)
        except (OSError, TimeoutError):
            pass
        self.close()
        end = time.monotonic() + 30
        while time.monotonic() < end:
            status = self.status()
            if status.get('detected'):
                self.request('PAIR_STOP')
                if self.controllers().get('controllers'):
                    raise RuntimeError('Configuration reset could not be verified')
                return
            time.sleep(0.3)
        raise RuntimeError('Configuration reset was requested, but adapter did not return')

    def install(self, configuration):
        if configuration not in ('preserve', 'reset') or not self.staged:
            raise ValueError('Select and validate firmware first')
        data = self.staged
        info = _inspect_bluebridge_firmware(data, self)
        if configuration == 'preserve':
            backup = self.export_config()
            folder = Path.home() / 'MiSTer-Companion' / 'BlueBridge-Backups'
            folder.mkdir(parents=True, exist_ok=True)
            (folder / (str(self.adapter_id).replace('/', '_').replace('\\', '_').replace(':', '_') + '-pre-update.bbconfig')).write_text(json.dumps(backup, indent=2))
        previous = set(boot_volumes())
        self.request('REBOOT_BOOTSEL')
        self.close()
        end = time.monotonic() + 20
        volumes = []
        while time.monotonic() < end:
            volumes = [v for v in boot_volumes() if v not in previous]
            if volumes:
                break
            time.sleep(0.25)
        if len(volumes) != 1:
            raise RuntimeError('Unable to identify one new RP2350 BOOTSEL volume. Firmware was not written.')
        flash_volume(data, volumes[0])
        end = time.monotonic() + 60
        status = {}
        while time.monotonic() < end:
            status = self.status()
            if status.get('detected'):
                break
            time.sleep(0.5)
        if not status.get('detected'):
            raise RuntimeError('Firmware transferred, but BlueBridge did not return. Reconnect the adapter to verify.')
        if version_key(status.get('firmware', '0.0.0')) != version_key(info['version']):
            raise RuntimeError('Firmware transferred, but installed version could not be verified')
        if configuration == 'reset':
            self.reset_configuration()
        self.staged = None
        return {'firmware': {**info, 'state': 'success', 'message': 'Firmware updated successfully'}}


class BlueBridgeService:
    def __init__(self, host=''):
        self.host = host
        self.adapter_id = ''
        self.managers = {}

    def close(self):
        for manager in self.managers.values():
            manager.close()

    def adapters(self):
        if self.host:
            return self.api('adapters')['adapters']
        result = []
        present = set()
        for port in list_ports.comports():
            if not ((port.vid == 0x2e8a and (port.pid in (0x10b1, 0x10b2) or 0xb000 <= (port.pid or 0) <= 0xbfff)) or (port.vid == 0x0f0d and port.pid == 0x0092)):
                continue
            key = port.serial_number or port.device
            present.add(key)
            manager = self.managers.get(key)
            if manager is None:
                manager = USBAdapter(port.device, {'serial': port.serial_number or '', 'product': port.product or ''})
                self.managers[key] = manager
            try:
                manager.connect()
                result.append({'id': key, 'name': manager.adapter_name, 'port': port.device})
            except Exception:
                manager.close()
        for key in set(self.managers) - present:
            self.managers.pop(key).close()
        return result

    def api(self, path, payload=None, data=None):
        route, _, query = path.partition('?')
        if self.host:
            response = requests.request('POST' if payload is not None or data is not None else 'GET', f'http://{self.host}:{REMOTE_DAEMON_PORT}/api/bluebridge/{path}', headers={'X-BlueBridge-Adapter': self.adapter_id, 'Content-Type': 'application/octet-stream' if data is not None else 'application/json'}, json=payload if data is None else None, data=data, timeout=150 if route.startswith('firmware/') else 20)
            response.raise_for_status()
            result = response.json()
            if result.get('ok') is False:
                raise RuntimeError(result.get('message', 'BlueBridge request failed'))
            return result
        manager = self.managers.get(self.adapter_id)
        if not manager:
            raise RuntimeError('Select a connected MC BlueBridge adapter')
        p = payload or {}
        with manager.lock:
            if route == 'status': return {'status': manager.status()}
            if route == 'controllers': return {'controllers': manager.controllers()}
            if route == 'profiles': return {'profiles': manager.profiles()}
            if route == 'profile': return {'profile': manager.profile(int(query.split('=')[-1]))}
            if route == 'capture/status': return {'capture': manager.request_json('CAPTURE_STATUS')}
            if route == 'config/export': return manager.export_config()
            if route == 'config/import': manager.import_config(p); return {'ok': True}
            if route == 'firmware/releases': return {'release': bluebridge_release(manager.status().get('firmware', ''))}
            if route in ('firmware/inspect', 'firmware/download'):
                manager.staged = None
                if route.endswith('download'):
                    release = bluebridge_release(manager.status().get('firmware', ''))
                    data = download_bluebridge_release(release)
                if not data or len(data) > 8 * 1024 * 1024: raise ValueError('Invalid firmware size')
                info = _inspect_bluebridge_firmware(data, manager)
                if route.endswith('download') and version_key(info['version']) != version_key(release['version']): raise ValueError('Firmware does not match release tag')
                manager.staged = data
                return {'firmware': info}
            if route == 'firmware/install': return manager.install(p.get('configuration', 'preserve'))
            if route == 'firmware/cancel': manager.staged = None; return {'ok': True}
            if route == 'profile/tuning':
                manager.request('PROFILE_TUNE', p['profile'], *[int(bool(p.get(k))) for k in ('invert_x','invert_y','invert_rx','invert_ry')], *[int(p[k]) for k in ('deadzone_left','deadzone_right','trigger_deadzone','turbo_rate_hz','turbo_mask')])
                manager.request('PROFILE_TURBO_MODIFIER', p['profile'], p['turbo_modifier'])
                manager.request('PROFILE_TURBO_CONTROL', p['profile'], int(p['turbo_enabled']), p['turbo_control_mode'], p['turbo_control_button'])
                return {'ok': True}
            commands = {
                'adapter/rename': ('ADAPTER_RENAME', [p.get('name', '')]),
                'controllers/rename': ('CONTROLLER_RENAME', [p.get('index', -1), p.get('name', '')]),
                'controllers/select': ('CONTROLLER_SELECT', [p.get('index', -1)]),
                'controllers/forget': ('CONTROLLER_FORGET', [p.get('index', -1)]),
                'controllers/disconnect': ('CONTROLLER_DISCONNECT', []),
                'pair': ('PAIR_START' if p.get('start', True) else 'PAIR_STOP', []),
                'forget': ('FORGET_ALL', []),
                'capture/start': ('CAPTURE_START', [p.get('mode', 'ONCE')]),
                'capture/stop': ('CAPTURE_STOP', []),
                'rumble': ('CONTROLLER_RUMBLE', [p.get('strength', 128), p.get('duration', 500)]),
                'profiles/create': ('PROFILE_CREATE', [p.get('name', '')]),
                'profiles/duplicate': ('PROFILE_DUPLICATE', [p.get('index', -1), p.get('name', '')]),
                'profiles/rename': ('PROFILE_RENAME', [p.get('index', -1), p.get('name', '')]),
                'profiles/select': ('PROFILE_SELECT', [p.get('index', -1)]),
                'profiles/delete': ('PROFILE_DELETE', [p.get('index', -1)]),
                'profile/map': ('PROFILE_MAP', [p.get('profile', -1), p.get('input', -1), p.get('output', -1)]),
                'profile/macro': ('PROFILE_MACRO', [p.get('profile', -1), p.get('macro', -1), int(p.get('enabled', False)), p.get('name', ''), p.get('output_mask', 0)]),
                'profile/mister-mapping': ('PROFILE_MAPPING_SHARE' if p.get('mode') == 'share' else 'PROFILE_MAPPING_SEPARATE', [p.get('profile', -1)] + ([p.get('target', -1)] if p.get('mode') == 'share' else [])),
            }
            if route == 'output':
                if payload is not None: manager.request('OUTPUT_SET', p['mode']); manager.close()
                return {'output': manager.request_json('OUTPUT_GET')}
            if route == 'config/reset':
                manager.reset_configuration(); return {'ok': True}
            if route not in commands: raise ValueError('Unknown BlueBridge operation')
            command, args = commands[route]
            if any('|' in str(a) or '\n' in str(a) or '\r' in str(a) for a in args): raise ValueError('Invalid command value')
            manager.request(command, *args)
            if route in ('adapter/rename','profiles/select','profile/mister-mapping'): manager.close()
            return {'ok': True}

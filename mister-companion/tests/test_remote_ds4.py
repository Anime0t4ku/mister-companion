"""Exercise DS4 helpers from the bundled daemon without starting its services."""
import ast
from contextlib import nullcontext
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import urllib.parse

SOURCE = Path(__file__).resolve().parents[1] / 'assets' / 'companion_remote.sh'


def daemon_tree():
    script = SOURCE.read_text(encoding='utf-8')
    return ast.parse(script.split("<<'PYEOF'\n", 1)[1].split('\nPYEOF', 1)[0])


def helpers():
    names = {'save_pointer_settings', 'lightbar_rgb', 'save_lightbar_palette',
             'save_lightbar_controller'}
    nodes = [node for node in daemon_tree().body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(nodes) == len(names)
    namespace = {'json': json}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<remote helpers>', 'exec'), namespace)
    return namespace


class Adapter:
    def __init__(self, supported=True, fail=None):
        self.calls = []
        self.supported = supported
        self.fail = fail
        self.path = '/dev/mock'
        self.info = {}
        self.adapter_id = 'mock'

    def request(self, command, *args):
        self.calls.append((command, args))

    def request_json(self, command, *args):
        self.calls.append((command, args))
        if command == 'HELLO':
            return {'capabilities': dict.fromkeys(
                ['touch_mouse', 'ds4_gyro', 'ds4_lightbar'], self.supported)}
        if command == self.fail:
            raise ValueError('read failed')
        return {'restart_required': True}


class RemoteDS4Tests(unittest.TestCase):
    def setUp(self):
        self.helpers = helpers()
        self.aim = dict(enabled=True, sensitivity=125, activation=1, flags=3, pause_button=10)
        self.palette = dict(theme=2, players=[[64, 0, 0], [0, 64, 0], [7, 8, 9], [10, 11, 12]])
        self.choice = dict(index=0, id=123, player=0, custom_enabled=True, rgb=[1, 2, 3])

    def test_bundled_daemon_and_html(self):
        tree = daemon_tree()
        assignment = next(node for node in tree.body
                          if isinstance(node, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'BLUEBRIDGE_HTML' for t in node.targets))
        html = ast.literal_eval(assignment.value.func.value)
        for panel in ('touchMousePanel', 'ds4GyroPanel', 'lightbarPanel'):
            self.assertEqual(html.count('id="' + panel + '"'), 1)


    def test_pointer_serialization_and_old_firmware_fallback(self):
        adapter = Adapter()
        self.helpers['save_pointer_settings'](adapter, dict(enabled=True, ds4_aim=self.aim))
        self.assertEqual(adapter.calls[-1], ('DS4_AIM_SET', (1, 125, 1, 3, 10, 1)))
        adapter = Adapter(False)
        self.helpers['save_pointer_settings'](adapter, dict(enabled=False))
        self.assertEqual(adapter.calls, [('TOUCH_MOUSE_SET', (0,))])
        with self.assertRaises(ValueError):
            self.helpers['save_pointer_settings'](Adapter(False), dict(enabled=True, ds4_aim=self.aim))

    def test_invalid_gyro_never_writes(self):
        invalid_values = dict(enabled=[1, 'true', None], sensitivity=[0, 201, True, '100'],
                              activation=[-1, 3, False], flags=[-1, 8, True],
                              pause_button=[14, 254, 256, False])
        for key, values in invalid_values.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    adapter = Adapter()
                    with self.assertRaises(ValueError):
                        self.helpers['save_pointer_settings'](adapter, dict(
                            enabled=True, ds4_aim=dict(self.aim, **{key: value})))
                    self.assertFalse(any(c[0].endswith('_SET') for c in adapter.calls))

    def test_lightbar_serialization(self):
        adapter = Adapter()
        self.helpers['save_lightbar_palette'](adapter, self.palette)
        self.assertEqual(adapter.calls[0], ('LIGHTBAR_PALETTE_SET',
            (2, 64, 0, 0, 0, 64, 0, 7, 8, 9, 10, 11, 12)))
        adapter = Adapter()
        self.helpers['save_lightbar_controller'](adapter, self.choice)
        self.assertEqual(adapter.calls[0], ('LIGHTBAR_SET', (0, 123, 0, 1, 1, 2, 3)))

    def test_invalid_palette_never_writes(self):
        for payload in [dict(self.palette, theme=True), dict(self.palette, theme=3),
                        dict(self.palette, theme=1), dict(self.palette, players=[]),
                        dict(self.palette, players=[[True, 0, 0]] * 4),
                        dict(self.palette, players=[[256, 0, 0]] * 4), None]:
            with self.subTest(payload=payload):
                adapter = Adapter()
                with self.assertRaises(ValueError):
                    self.helpers['save_lightbar_palette'](adapter, payload)
                self.assertFalse(adapter.calls)

    def test_invalid_controller_never_writes(self):
        for payload in [dict(self.choice, id=4294967296), dict(self.choice, index=8),
                        dict(self.choice, player=5), dict(self.choice, custom_enabled=1),
                        dict(self.choice, rgb=[1, 2]), dict(self.choice, id=True)]:
            with self.subTest(payload=payload):
                adapter = Adapter()
                with self.assertRaises(ValueError):
                    self.helpers['save_lightbar_controller'](adapter, payload)
                self.assertFalse(adapter.calls)

    def test_status_capability_gating_and_read_failure(self):
        cls = next(n for n in daemon_tree().body if isinstance(n, ast.ClassDef)
                   and n.name == 'BlueBridgeManager')
        status = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'status')
        namespace = {}
        exec(compile(ast.Module(body=[status], type_ignores=[]), '<status>', 'exec'), namespace)
        for supported in (True, False):
            adapter = Adapter(supported)
            result = namespace['status'](adapter)
            for key in ('touch_mouse', 'ds4_aim', 'lightbar'):
                self.assertEqual(key in result, supported)
            if not supported:
                self.assertFalse(any(c[0] in ('TOUCH_MOUSE_GET', 'DS4_AIM_GET', 'LIGHTBAR_GET')
                                     for c in adapter.calls))
        for command, key in [('TOUCH_MOUSE_GET', 'touch_mouse'),
                             ('DS4_AIM_GET', 'ds4_aim'), ('LIGHTBAR_GET', 'lightbar')]:
            result = namespace['status'](Adapter(fail=command))
            self.assertIn(key + '_error', result)
            self.assertNotIn(key, result)

    def test_http_routes_validate_method_capability_and_payload(self):
        handler = next(n for n in daemon_tree().body
                       if isinstance(n, ast.FunctionDef) and n.name == 'handle_client')
        routes = [('/api/bluebridge/touch-mouse', dict(enabled=True, ds4_aim=self.aim)),
                  ('/api/bluebridge/lightbar/palette', self.palette),
                  ('/api/bluebridge/lightbar/controller', self.choice)]
        for route, payload in routes:
            for method, supported, body, expected in [
                    ('GET', True, payload, '405 Method Not Allowed'),
                    ('POST', False, payload, '400 Bad Request'),
                    ('POST', True, [], '400 Bad Request'),
                    ('POST', True, payload, '200 OK')]:
                with self.subTest(route=route, method=method, supported=supported, body=body):
                    adapter = Adapter(supported)
                    adapter.lock = nullcontext()
                    replies, selections = [], []
                    namespace = dict(self.helpers, urllib=urllib, bluebridge_registry=SimpleNamespace(
                        resolve=lambda selected: selections.append(selected) or adapter),
                        _read_http_request=lambda sock: (method, route, {'x-bluebridge-adapter': 'chosen'},
                                                         json.dumps(body).encode()),
                        response=lambda ok, kind, message, **kw: dict(ok=ok, **kw),
                        _json_http=lambda sock, data, status='200 OK': replies.append((status, data)))
                    exec(compile(ast.Module(body=[handler], type_ignores=[]), '<HTTP handler>', 'exec'), namespace)
                    namespace['handle_client'](SimpleNamespace(close=lambda: None), 'test', '/remote/v1')
                    self.assertEqual(selections, ['chosen'])
                    self.assertEqual(len(replies), 1)
                    self.assertEqual(replies[0][0], expected)
                    writes = [c for c in adapter.calls if c[0].endswith('_SET')]
                    self.assertEqual(len(writes), int(expected == '200 OK'))


if __name__ == '__main__':
    unittest.main()

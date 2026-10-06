import base64
import io
import json
import struct
import threading
import unittest
import urllib.error
from unittest.mock import patch
from types import SimpleNamespace
from core.bluebridge_releases import bluebridge_release, version_key
from core.bluebridge_protocol import _uf2_info, _inspect_bluebridge_firmware
from core.bluebridge import BlueBridgeService, USBAdapter
from core.remote_daemon import RemoteDaemonStatus


def release(tag, asset='mc_bluebridge.uf2', **extra):
    return {'tag_name': tag, 'assets': [{'name': asset, 'size': 512, 'browser_download_url': 'https://github.com/Anime0t4ku/MC-BlueBridge/releases/download/' + tag + '/' + asset}], **extra}


def firmware(version='1.0.0', number=0, total=1, family=0xE48BFF59):
    block = bytearray(512)
    payload = ('MCBLUEBRIDGE|' + version + '|PICO2W|SCHEMA=3').encode()
    struct.pack_into('<IIIIIIII', block, 0, 0x0A324655, 0x9E5D5157, 0x2000, 0x10000000, len(payload), number, total, family)
    block[32:32+len(payload)] = payload
    struct.pack_into('<I', block, 508, 0x0AB16F30)
    return bytes(block)


class ReleaseTests(unittest.TestCase):
    def resolve(self, releases, installed=''):
        return bluebridge_release(installed, lambda *a, **kw: io.StringIO(json.dumps(releases)))

    def test_beta_to_stable(self):
        result = self.resolve([release('v1.0.0-beta-100'), release('v1.0.0')], '1.0.0-beta-29')
        self.assertEqual(result['version'], '1.0.0')
        self.assertTrue(result['update_available'])

    def test_stable_channel_excludes_new_beta(self):
        result = self.resolve([release('v1.0.0'), release('v1.0.1-beta-1', prerelease=True)], '1.0.0')
        self.assertEqual(result['version'], '1.0.0')
        self.assertFalse(result['update_available'])

    def test_newer_beta_line(self):
        result = self.resolve([release('v1.0.0'), release('v1.0.1-beta-2', prerelease=True)], '1.0.1-beta-1')
        self.assertEqual(result['version'], '1.0.1-beta-2')
        self.assertTrue(result['update_available'])

    def test_initial_install_prefers_stable(self):
        self.assertEqual(self.resolve([release('v1.0.0'), release('v1.1.0-beta-1')])['version'], '1.0.0')

    def test_private_repository_and_network_failure(self):
        for error in [urllib.error.HTTPError('x',404,'Not Found',{},None), urllib.error.URLError('offline')]:
            def fail(*args, **kwargs): raise error
            self.assertEqual(bluebridge_release('', fail), {'available':False})

    def test_wrong_asset_and_draft_are_not_downloaded(self):
        result = self.resolve([release('v9.0.0', 'other.uf2'),release('v8.0.0', draft=True),release('garbage'),release('v1.0.0')])
        self.assertEqual(result['version'], '1.0.0')

    def test_semver_and_legacy_beta_order(self):
        self.assertGreater(version_key('v1.0.0'), version_key('1.0.0-beta-999'))
        self.assertGreater(version_key('4.0.0-beta.30'), version_key('4.0.0-beta.29'))
        self.assertGreater(version_key('1.0.0-beta-10'), version_key('1.0.0-beta-9'))
        self.assertEqual(version_key('1.0.0+build.2'),version_key('1.0.0'))
        self.assertTrue(RemoteDaemonStatus(script_exists=True, version='4.0.0-beta.29', latest_version='4.0.0-beta.30').update_available)

    def test_pagination(self):
        pages = [[release('v0.1.'+str(i)) for i in range(100)], [release('v1.0.0')]]
        seen = []
        def opener(request, **kw):
            seen.append(request.full_url)
            return io.StringIO(json.dumps(pages[len(seen)-1]))
        self.assertEqual(bluebridge_release('', opener)['version'], '1.0.0')
        self.assertEqual(len(seen),2)


class FirmwareTests(unittest.TestCase):
    def test_correct_target_and_version_relation(self):
        manager=SimpleNamespace(status=lambda:{'detected':True,'firmware':'1.0.0-beta-21'})
        self.assertEqual(_inspect_bluebridge_firmware(firmware(),manager)['relation'],'newer')
        self.assertEqual(_uf2_info(firmware('1.0.0-rc.1'))['version'],'1.0.0-rc.1')

    def test_corrupt_wrong_family_and_incomplete_rejected(self):
        for data in [b'garbage',firmware(family=0xE48BFF56),firmware(total=2),firmware()+firmware()]:
            with self.assertRaises(ValueError): _uf2_info(data)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.manager=USBAdapter('/dev/test',{'serial':'adapter-1'})
        self.service=BlueBridgeService(); self.service.adapter_id='adapter-1'; self.service.managers['adapter-1']=self.manager
        self.calls=[]
        self.manager.request=lambda *args,**kw:self.calls.append(args) or ''
        self.manager.request_json=lambda *args,**kw: {'mode':1}

    def test_controller_offline_selection_and_profile_mapping(self):
        self.service.api('controllers/select',{'index':3})
        self.service.api('profile/map',{'profile':2,'input':7,'output':1})
        self.assertEqual(self.calls,[('CONTROLLER_SELECT',3),('PROFILE_MAP',2,7,1)])

    def test_turbo_and_macro_route(self):
        self.service.api('profile/tuning',{'profile':0,'deadzone_left':8,'deadzone_right':9,'trigger_deadzone':4,'turbo_rate_hz':12,'turbo_mask':3,'turbo_modifier':8,'turbo_enabled':True,'turbo_control_mode':1,'turbo_control_button':13})
        self.assertEqual(self.calls[0],('PROFILE_TUNE',0,0,0,0,0,8,9,4,12,3))
        self.assertEqual(self.calls[-1],('PROFILE_TURBO_CONTROL',0,1,1,13))
        self.service.api('profile/macro',{'profile':0,'macro':2,'enabled':True,'name':'Combo','output_mask':5})
        self.assertEqual(self.calls[-1],('PROFILE_MACRO',0,2,1,'Combo',5))

    def test_remote_uses_selected_adapter_and_binary_body(self):
        service=BlueBridgeService('mister.local'); service.adapter_id='adapter-2'
        with patch('core.bluebridge.requests.request') as request:
            request.return_value.json.return_value={'ok':True,'firmware':{}}
            service.api('firmware/inspect',data=b'uf2')
            args,kwargs=request.call_args
            self.assertEqual(args[0],'POST')
            self.assertEqual(kwargs['headers']['X-BlueBridge-Adapter'],'adapter-2')
            self.assertEqual(kwargs['data'],b'uf2')
            self.assertEqual(kwargs['headers']['Content-Type'],'application/octet-stream')

    def test_serial_filters_unrelated_responses(self):
        adapter=USBAdapter('/dev/test',{'serial':'adapter-1'})
        adapter.connect=lambda:None
        outgoing=[]; adapter._write=outgoing.append
        lines=iter(['noise','BB1|999|OK|bad','BB1|1|OK|{"firmware":"1.0.0"}'])
        adapter._readline=lambda timeout:next(lines)
        self.assertEqual(adapter.request_json('STATUS'),{'firmware':'1.0.0'})
        self.assertEqual(outgoing,['BB1|1|STATUS\n'])

    def test_config_export_import_interchange(self):
        adapter=USBAdapter('/dev/test',{'serial':'adapter-1'})
        adapter._send=lambda *args:'1'
        lines=iter(['BB1|1|DATA_BEGIN|3|4|42','BB1|1|DATA|0|01020304','BB1|1|DATA_END|'])
        adapter._readline=lambda timeout:next(lines)
        config=adapter.export_config()
        self.assertEqual(base64.b64decode(config['data']),b'\x01\x02\x03\x04')
        calls=[]; adapter.request=lambda *args,**kw:calls.append(args)
        adapter.import_config(config)
        self.assertEqual(calls[-1],('CONFIG_IMPORT_COMMIT',))
        self.assertEqual(calls[1],('CONFIG_IMPORT_CHUNK',0,'01020304'))


if __name__ == '__main__':
    unittest.main()

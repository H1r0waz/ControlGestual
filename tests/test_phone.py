import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop_phone import PhoneControl,endpoint
import test_v2 as fixture

def response(text='',code=0):return subprocess.CompletedProcess([],code,text,'')

class PhoneTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'adb.exe').touch();(self.root/'scrcpy.exe').touch()
        self.phone=PhoneControl(self.root,self.root/'private')
    def tearDown(self):self.temp.cleanup()

    def test_private_network_and_whitelisted_argument_validation(self):
        self.assertEqual(endpoint('192.168.1.5',37000),'192.168.1.5:37000')
        for host,port in [('8.8.8.8',3000),('127.0.0.1',5037),('192.168.1.5;calc',3000),('192.168.1.5',True),('192.168.1.5',0)]:
            with self.assertRaises(ValueError):endpoint(host,port)
        with self.assertRaises(ValueError):self.phone.action('shell rm')

    def test_pairing_code_only_goes_to_stdin_and_does_not_enter_state(self):
        with patch.object(self.phone,'prepare'),patch.object(self.phone,'run',return_value=response('Successfully paired to device')) as run:
            self.phone.pair('192.168.1.5',37000,'123456')
            self.assertNotIn('123456',str(run.call_args.args[0]));self.assertEqual(run.call_args.args[1],'123456\n')
            self.assertNotIn('123456',json.dumps(self.phone.state()))
        with patch.object(self.phone,'prepare') as prepare:
            with self.assertRaises(ValueError):self.phone.pair('192.168.1.5',37000,'bad')
            prepare.assert_not_called()

    def test_isolated_environment_and_no_global_key_paths(self):
        with patch.dict(os.environ,{'ANDROID_SERIAL':'external','ADB_TRACE':'all','ADB_SERVER_SOCKET':'tcp:external:5037'}):
            env=self.phone.environment()
        self.assertNotIn('ANDROID_SERIAL',env);self.assertNotIn('ADB_TRACE',env)
        self.assertEqual(env['ANDROID_USER_HOME'],str(self.root/'private'))
        self.assertEqual(env['ADB_SERVER_SOCKET'],'tcp:127.0.0.1:'+str(self.phone.port))
        self.assertEqual(env['ADB_VENDOR_KEYS'],str(self.root/'private/adbkey'))
        with patch('desktop_phone.subprocess.run',return_value=response()) as run:
            self.phone.run(['version'])
            args=run.call_args.args[0];self.assertEqual(args[1:3],['-P',str(self.phone.port)]);self.assertFalse(run.call_args.kwargs.get('shell',False))

    def test_connect_verifies_device_and_always_targets_selected_serial(self):
        with patch.object(self.phone,'prepare'),patch.object(self.phone,'run',side_effect=[response('connected'),response('device\n')]):self.phone.connect('192.168.1.5',42000)
        with patch.object(self.phone,'run',return_value=response()) as run:
            self.phone.action('home');self.assertEqual(run.call_args.args[0],['-s','192.168.1.5:42000','shell','input','keyevent','3'])
        self.phone.pause()
        with patch.object(self.phone,'run') as run:
            with self.assertRaises(ValueError):self.phone.action('back')
            run.assert_not_called()
        self.phone.resume()
        with patch.object(self.phone,'run',side_effect=[response('Physical size: 720x1600'),response()]) as run:
            self.phone.action('scroll_down');self.assertEqual(run.call_args.args[0][-7:],['input','swipe','360','1120','360','480','300'])

    def test_no_arbitrary_components_and_mirror_is_owned_without_recording(self):
        self.phone.connected=True;self.phone.enabled=True;self.phone.serial='192.168.1.5:42000'
        with patch.object(self.phone,'run',return_value=response('com.android.chrome/.Main;malicious')) as run:
            with self.assertRaises(ValueError):self.phone.action('chrome')
            self.assertEqual(run.call_count,1)
        process=MagicMock();process.poll.return_value=None
        with patch('desktop_phone.subprocess.Popen',return_value=process) as spawn:
            self.phone.show();args=spawn.call_args.args[0]
            self.assertIn('--no-clipboard-autosync',args);self.assertIn('--no-audio',args);self.assertFalse(any(arg.startswith('--record') for arg in args))
            self.phone.pause();process.terminate.assert_called_once()

class PhoneApiTests(unittest.TestCase):
    request=fixture.ApiV2Tests.request
    setUp=fixture.ApiV2Tests.setUp
    tearDown=fixture.ApiV2Tests.tearDown

    def test_pairing_and_gestures_are_authenticated_and_paused_commands_rejected(self):
        with patch.object(self.server.phone,'pair',return_value={'message':'paired'}) as pair:
            self.assertEqual(self.request('phone/pair',{'host':'192.168.1.5','port':37000,'code':'123456'})[0],200);pair.assert_called_once()
        with patch.object(self.server.phone,'action',return_value={'message':'sent'}) as action:
            self.assertEqual(self.request('phone/action',{'action':'home','gesture':True,'emergency':0})[0],400)
            self.server.armed=True
            self.assertEqual(self.request('phone/action',{'action':'home','gesture':True,'emergency':0})[0],200)
            self.assertEqual(self.request('phone/action',{'action':'arbitrary'})[0],400)
            self.server.voice.active=True
            self.server.voice_action('phone_home','active',None,0);self.assertEqual(action.call_count,2)
        self.server.phone.connected=True;self.server.phone.enabled=True
        self.server.control('pause');self.assertFalse(self.server.phone.enabled)

if __name__=='__main__':unittest.main()

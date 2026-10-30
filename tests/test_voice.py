import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop_voice import COMMANDS,LEGACY_COMMANDS,VoiceControl,parse_command,grammar,audio_level,result_confidence
import test_v2 as fixture
WINDOWS=fixture.WINDOWS
import desktop_windows as native

class VoiceParserTests(unittest.TestCase):
    def test_all_window_actions_have_exact_wake_word_commands(self):
        from desktop_features import ACTIONS
        self.assertTrue(set(ACTIONS)-{'none','maximize'}<=set(COMMANDS.values()))
        for phrase,command in COMMANDS.items():self.assertEqual(parse_command('Control '+phrase),command)
        for phrase,command in LEGACY_COMMANDS.items():self.assertEqual(parse_command('Control '+phrase),command)
        self.assertEqual(parse_command('¡CONTROL apagar micrófono!'),'stop_mic')
        for invalid in ('minimizar','por favor control minimizar','control minimizar y maximizar','control borrar archivos','control','control minimizar [unk]',None):self.assertIsNone(parse_command(invalid))
        self.assertIn('[unk]',grammar())

    def test_short_commands_legacy_aliases_and_ambiguous_move(self):
        for phrase,action in [('mover izquierda','move_left'),('mover derecha','move_right'),('siguiente','next_app'),('anterior','previous_app'),('pantalla dos','monitor_2')]:self.assertEqual(parse_command('control '+phrase),action)
        self.assertIsNone(parse_command('control mover'))
        calls=[];voice=VoiceControl('.',lambda *args:calls.append(args) or {'message':'OK'});voice.active=True
        voice.accept('control mover',0);self.assertEqual(calls,[]);self.assertIn('mover izquierda',voice.message)
        voice.accept('control mover izquierda',0,.4);self.assertEqual(calls,[]);self.assertIn('poco clara',voice.message)
        voice.accept('control mover izquierda',0,.95);self.assertEqual(len(calls),1)

    def test_signal_meter_and_confidence_are_bounded(self):
        from array import array
        self.assertEqual(audio_level(bytes(3200)),(0,False))
        level,clipped=audio_level(array('h',[32767,-32767]*100).tobytes());self.assertEqual(level,100);self.assertTrue(clipped)
        self.assertEqual(result_confidence({'result':[{'conf':.9},{'conf':.7}]}),.7)
        self.assertIsNone(result_confidence({'result':[{'conf':float('nan')}]}))
        self.assertIsNone(result_confidence({}))

    def test_voice_pause_resume_duplicate_stop_and_stale_audio(self):
        calls=[];voice=VoiceControl('.',lambda *args:calls.append(args) or {'message':'OK'})
        voice.active=True
        voice.accept('control minimizar',0);voice.accept('control minimizar',0);self.assertEqual(len(calls),1)
        voice.accept('control pausar',0);voice.accept('control maximizar',0);self.assertEqual(len(calls),1)
        voice.accept('control continuar',0);voice.accept('control restaurar',0);self.assertEqual(len(calls),2)
        voice.configure(123,None);voice.accept('control siguiente aplicacion',0);self.assertEqual(len(calls),2)
        voice.accept('control siguiente aplicacion',1);self.assertEqual(len(calls),3)
        voice.stop();voice.accept('control mitad izquierda',voice.generation);self.assertEqual(len(calls),3)

    def test_target_validation_and_missing_model_never_open_microphone(self):
        voice=VoiceControl('nonexistent',lambda *args:None)
        with self.assertRaises(ValueError):voice.start()
        for selected,monitor in ((None,None),(True,None),('bad',None),('active',True),('active',-1)):
            with self.assertRaises(ValueError):voice.configure(selected,monitor)

class VoiceApiTests(unittest.TestCase):
    request=fixture.ApiV2Tests.request
    tearDown=fixture.ApiV2Tests.tearDown
    def setUp(self):
        fixture.ApiV2Tests.setUp(self);self.server.voice.active=True

    def test_microphone_stream_closes_after_spoken_stop_without_opening_hardware(self):
        from types import SimpleNamespace
        closed=[]
        class Stream:
            active=True
            def __init__(self,**kwargs):self.callback=kwargs['callback']
            def __enter__(self):self.callback(bytes(6400),3200,None,None);return self
            def __exit__(self,*args):closed.append(True)
        recognizer=SimpleNamespace(AcceptWaveform=lambda data:True,Result=lambda:json.dumps({'text':'control apagar micrófono'}))
        with patch.dict(sys.modules,{'sounddevice':SimpleNamespace(query_devices=lambda *args,**kwargs:{'default_samplerate':16000},RawInputStream=Stream)}),patch('desktop_voice.create_recognizer',return_value=recognizer):self.server.voice.run()
        self.assertEqual(closed,[True]);self.assertFalse(self.server.voice.active);self.assertTrue(self.server.voice.stop_event.is_set())

    def test_disconnected_silent_microphone_exits_and_reports_failure(self):
        from types import SimpleNamespace
        closed=[]
        class Stream:
            active=False
            def __init__(self,**kwargs):pass
            def __enter__(self):return self
            def __exit__(self,*args):closed.append(True)
        with patch.dict(sys.modules,{'sounddevice':SimpleNamespace(query_devices=lambda *args,**kwargs:{'default_samplerate':16000},RawInputStream=Stream)}),patch('desktop_voice.create_recognizer',return_value=object()):self.server.voice.run()
        self.assertEqual(closed,[True]);self.assertFalse(self.server.voice.active)
        self.assertIn('dejó de enviar audio',self.server.voice.message)

    def test_every_voice_window_action_dispatches_without_camera_and_honors_exclusions(self):
        from desktop_features import ACTIONS
        self.server.armed=False
        with patch.object(native,'close_window',return_value={'message':'close'}),patch.object(native,'scroll_window',return_value={'message':'scroll'}),patch.object(native,'multimedia_action',return_value={'message':'media'}),patch.object(native,'capture_placement',return_value={'hwnd':101,'pid':201}),patch.object(native,'move_window',return_value={'message':'move'}),patch.object(native,'arrange_window',return_value={'message':'snap'}),patch.object(native,'minimize_window',return_value={'message':'min'}),patch.object(native,'set_window_state',return_value={'message':'size'}) as size,patch.object(native,'toggle_maximize_window',return_value={'message':'toggle'}),patch.object(native,'windows',return_value=list(WINDOWS.values())),patch.object(native,'activate_window',return_value={'message':'switch'}):
            for action in set(COMMANDS.values())&set(ACTIONS):self.server.voice_action(action,101,None,0)
            self.server.voice_action('restore',101,None,0);self.assertEqual(size.call_args.args[1],'normal')
            self.server.settings['excluded_apps']=['allowed.exe']
            with self.assertRaises(ValueError):self.server.voice_action('minimize',101,None,0)
        self.server.voice.stop()
        with self.assertRaises(ValueError):self.server.voice_action('minimize',101,None,0)

    def test_voice_monitor_undo_stop_and_authenticated_controls(self):
        with patch.object(native,'monitors',return_value=[{'id':42}]):
            self.assertEqual(self.server.voice_action('monitor_1','active',None,0)['monitor_id'],42)
            with self.assertRaises(ValueError):self.server.voice_action('monitor_2','active',None,0)
        with patch.object(self.server,'undo_action',return_value={'message':'Undo'}) as undo:
            self.server.voice_action('undo','active',None,0);undo.assert_called_once()
        self.assertEqual(self.request('voice/commands')[0],200)
        with patch.object(self.server.voice,'start') as start:
            self.assertEqual(self.request('voice/start',{'selected':'active','monitor_id':None})[0],200);start.assert_called_once()
        self.assertEqual(self.request('voice/target',{'selected':None})[0],400)
        self.assertEqual(self.request('voice/stop',{})[0],200);self.assertFalse(self.server.voice.active)

    def test_device_listing_and_selection_are_authenticated_and_validated(self):
        with patch('desktop_app.input_devices',return_value=[{'id':7,'name':'Test'}]):self.assertEqual(self.request('voice/devices')[1]['devices'][0]['id'],7)
        for device in (True,-1,'default'):
            with self.assertRaises(ValueError):self.server.voice.start(device)

if __name__=='__main__':unittest.main()

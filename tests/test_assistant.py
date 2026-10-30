import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch,Mock
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import desktop_windows as native
from desktop_app import DesktopServer
from desktop_assistant import parse,spoken_examples
from desktop_speech import SpeechOutput
from desktop_voice import VoiceControl,parse_command

def window(hwnd,pid,title,app):return dict(hwnd=hwnd,pid=pid,title=title,app=app,minimized=False,maximized=False)

class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.windows={123:window(123,987,'Chrome A','chrome.exe'),124:window(124,988,'Chrome B','chrome.exe'),125:window(125,989,'Editor','edit.exe')}
        self.info=patch.object(native,'window_info',side_effect=lambda hwnd:self.windows.get(hwnd));self.info.start()
        self.front=patch.object(native.user32,'GetForegroundWindow',return_value=125);self.front.start()
        self.listed=patch.object(native,'windows',side_effect=lambda:list(self.windows.values()));self.listed.start()
        self.server=DesktopServer();self.server.last=dict(self.windows[125]);self.server.settings['app_names']={'chrome':'chrome.exe','editor':'edit.exe'}
        self.execute=patch.object(self.server,'execute',return_value={'message':'Acción simulada','undo_count':0});self.action=self.execute.start()
    def tearDown(self):
        self.server.server_close();self.execute.stop();self.listed.stop();self.front.stop();self.info.stop()
    def request(self,text,selected='active'):return self.server.assistant.request(text,selected)

    def test_natural_forms_and_unknown_requests_never_execute(self):
        names={'chrome':'chrome.exe'}
        for text,action in [('Jarvis por favor pasá Chrome a la derecha','move_right'),('ahora maximizalo','maximize'),('Podrías dejar esta ventana grande','maximize')]:
            self.assertEqual(parse(text,names)[0],action)
        for text in ['no cierres chrome','cierra chrome y editor','borra todos mis archivos','cierra chrome; shutdown','abrí una página','qué clima hay']:
            self.request(text)
        self.action.assert_not_called()
        self.assertTrue(all(value.startswith('jarvis ') for value in spoken_examples(names)))

    def test_ambiguity_requires_choice_and_followup_keeps_same_pid(self):
        self.request('Jarvis pasa Chrome a la derecha');self.action.assert_not_called()
        self.assertEqual(len(self.server.assistant.state()['choices']),2)
        self.request('Jarvis segunda')
        self.assertEqual(self.action.call_args.args[0],'move_right')
        self.assertEqual(self.action.call_args.args[1]['snapshot']['hwnd'],124)
        self.server.last=self.windows[125]
        self.request('ahora maximizalo')
        self.assertEqual(self.action.call_args.args[1]['snapshot']['pid'],988)
        self.assertEqual(self.action.call_args.args[1]['window_state'],'maximized')
        self.request('ahora minimizala')
        self.assertEqual(self.action.call_args.args[0],'minimize')
        self.request('restaurala')
        self.assertEqual(self.action.call_args.args[1]['window_state'],'normal')

    def test_stale_choice_timeout_exclusion_and_new_request(self):
        self.request('cierra chrome');self.windows[124]['pid']=999
        self.request('segunda');self.action.assert_not_called()
        self.request('cierra chrome');self.server.assistant.pending['expires']=0
        self.assertEqual(self.server.assistant.state()['choices'],[])
        self.request('segunda');self.action.assert_not_called()
        self.server.settings['excluded_apps']=['chrome.exe']
        self.request('maximizar chrome');self.action.assert_not_called()
        self.server.settings['excluded_apps']=[]
        self.request('cierra chrome');self.request('minimiza editor')
        self.assertEqual(self.action.call_count,1)
        self.request('segunda');self.assertEqual(self.action.call_count,1)

    def test_context_cannot_fall_back_to_another_window_and_reset_is_explicit(self):
        self.request('minimiza editor');self.windows[125]['pid']=999
        result=self.request('ahora maximizar')
        self.assertIn('cerró o cambió',result['message']);self.assertEqual(self.action.call_count,1)
        self.request('ahora maximizar');self.assertEqual(self.action.call_count,1)
        self.assertTrue(self.server.assistant.state()['context']['unavailable'])
        self.request('Jarvis cancelar');self.assertIsNone(self.server.assistant.state()['context'])
        self.request('maximizar',selected=123)
        self.assertEqual(self.action.call_args.args[1]['snapshot']['hwnd'],123)

    def test_voice_pause_epoch_and_speech_suppression(self):
        voice=self.server.voice;voice.active=True;voice.stop_event.clear()
        voice.accept('Jarvis minimiza editor',voice.generation,1)
        self.assertEqual(self.action.call_count,1)
        self.server.speech.busy=True
        voice.accept('Jarvis cierra editor',voice.generation,1)
        self.assertEqual(self.action.call_count,1)
        self.server.speech.busy=False
        self.request('cierra chrome');self.server.control('pause')
        self.request('segunda');self.assertEqual(self.action.call_count,1)
        with patch.object(self.server.speech,'say') as say:
            def cancel_list():self.server.emergency+=1;self.server.assistant.cancel();return [self.windows[125]]
            with patch.object(native,'windows',side_effect=cancel_list):self.request('minimiza editor')
            self.assertEqual(self.action.call_count,1);say.assert_not_called()
        self.assertEqual(parse_command('Jarvis ahora maximizar'),'assistant:ahora maximizar')
        self.assertIsNone(parse_command('ahora maximizar'))

    def test_close_requires_confirmation_and_cannot_be_replayed_or_retargeted(self):
        self.request('cierra editor');self.action.assert_not_called()
        self.assertEqual(self.server.assistant.state()['confirmation'],'Editor')
        self.request('primera');self.action.assert_not_called()
        self.request('confirmar');self.action.assert_called_once()
        self.assertEqual(self.action.call_args.args[0],'close')
        self.request('confirmar');self.assertEqual(self.action.call_count,1)
        self.request('cierra editor');self.windows[125]['pid']=777
        self.request('confirmar');self.assertEqual(self.action.call_count,1)
        self.request('cierra editor');self.request('cancelar');self.request('confirmar')
        self.assertEqual(self.action.call_count,1)
        self.request('cierra editor');self.server.assistant.pending['expires']=0;self.request('confirmar')
        self.assertEqual(self.action.call_count,1)
        self.request('cierra editor');self.windows[125]['title']='Otro documento';self.request('confirmar')
        self.assertEqual(self.action.call_count,1)

class SpeechTests(unittest.TestCase):
    def test_speech_text_is_json_stdin_and_never_shell_source(self):
        from desktop_speech import SCRIPT
        process=Mock();pipe=process.stdin
        text='Jarvis cerrar; $(Remove-Item algo) "hola"'
        with patch('desktop_speech.subprocess.Popen',return_value=process) as launch:
            SpeechOutput.launch(text)
        self.assertEqual(launch.call_args.args[0][-1],SCRIPT)
        self.assertNotIn(text,launch.call_args.args[0])
        self.assertEqual(json.loads(pipe.write.call_args.args[0])['text'],text)
        self.assertFalse(launch.call_args.kwargs.get('shell',False))

    def test_disabled_speech_never_launches_and_stop_cancels_owned_process(self):
        speech=SpeechOutput()
        with patch.object(speech,'launch') as launch:speech.say('No reproducir');launch.assert_not_called()
        process=Mock();process.poll.return_value=None
        speech.process=process;speech.busy=True;speech.stop()
        process.terminate.assert_called_once();self.assertFalse(speech.busy);self.assertTrue(speech.suppressed())
        self.assertFalse(SpeechOutput().suppressed())

    def test_real_windows_synthesis_to_wav_without_speakers(self):
        output=Path(__file__).resolve().parents[1]/'work/assistant-tts-check.wav'
        if output.exists():output.unlink()
        process=SpeechOutput.launch('Listo. Estoy preparado para ayudarte.',output)
        process.communicate(timeout=30);self.assertEqual(process.returncode,0)
        with wave.open(str(output),'rb') as audio:
            self.assertGreater(audio.getnframes(),1000);self.assertGreater(audio.getframerate(),8000)

class AssistantApiTests(unittest.TestCase):
    def test_authenticated_text_validation_and_reset(self):
        import test_v2 as fixture
        test=fixture.ApiV2Tests();test.setUp()
        try:
            self.assertEqual(test.request('assistant/request',{'text':'Jarvis ayuda'})[0],200)
            for data in ({'text':None},{'text':'x'*201},{'text':'hola','selected':False},{'text':'hola','monitor_id':False}):self.assertEqual(test.request('assistant/request',data)[0],400)
            self.assertEqual(test.request('assistant/reset',{})[0],200)
            self.assertIsNone(test.server.assistant.state()['context'])
            self.assertEqual(len(test.server.assistant.state()['turns']),1)
        finally:test.tearDown()

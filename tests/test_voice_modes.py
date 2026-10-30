import sys,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop_voice import VoiceControl,parse_command
from desktop_features import validate_settings
from desktop_productivity import extra_commands
import test_v2 as fixture

class VoiceModeTests(unittest.TestCase):
    def test_question_is_explicit_single_turn_and_returns_to_commands(self):
        calls=[];voice=VoiceControl('.',lambda *args:calls.append(args) or {'message':'Respuesta'})
        with self.assertRaises(ValueError):voice.begin_question()
        voice.active=True;voice.begin_question();generation=voice.generation
        self.assertEqual(voice.state()['input_mode'],'question')
        voice.accept('Qué es la memoria',generation,.95,'phrase')
        self.assertEqual(calls[0][0],'assistant_query:que es la memoria')
        self.assertEqual(calls[0][3],voice.generation)
        self.assertFalse(voice.free_speech);self.assertEqual(voice.state()['input_mode'],'commands')
        voice.accept('No es una orden',voice.generation,1)
        self.assertEqual(len(calls),1)

    def test_question_timeout_low_confidence_and_stop_never_leave_free_mode_active(self):
        calls=[];voice=VoiceControl('.',lambda *args:calls.append(args) or {})
        voice.active=True;voice.begin_question();voice.question_expires=0
        self.assertEqual(voice.state()['input_mode'],'commands');self.assertFalse(voice.free_speech)
        voice.begin_question();voice.accept('algo dudoso',voice.generation,.5,'phrase')
        self.assertFalse(voice.free_speech);self.assertEqual(calls,[])
        voice.begin_question();voice.accept('Control apagar micrófono',voice.generation,1,'phrase')
        self.assertFalse(voice.active);self.assertFalse(voice.question_active);self.assertFalse(voice.free_speech)

    def test_registered_app_migration_preserves_names_and_removals(self):
        settings=validate_settings({'app_names':{'chrome':'custom.exe'}})
        self.assertEqual(settings['app_names']['chrome'],'custom.exe')
        self.assertEqual(settings['app_names']['discord'],'discord.exe')
        del settings['app_names']['discord']
        self.assertNotIn('discord',validate_settings(settings)['app_names'])
        extras=extra_commands(validate_settings({}))
        self.assertEqual(parse_command('Control Chrome',extras),'select_app:chrome.exe')
        self.assertEqual(parse_command('Control Discord',extras),'select_app:discord.exe')
        self.assertEqual(parse_command('Control seleccionar Discord',extras),'select_app:discord.exe')
        self.assertIsNone(parse_command('discord',extras))

class VoiceModeApiTests(unittest.TestCase):
    setUp=fixture.ApiV2Tests.setUp
    tearDown=fixture.ApiV2Tests.tearDown
    request=fixture.ApiV2Tests.request

    def test_enabling_ai_preserves_precise_commands_and_question_requires_mic(self):
        ai={'enabled':False,'starting':False}
        def start():ai['enabled']=True;return dict(ai)
        with patch.object(self.server.llm,'start',side_effect=start),patch.object(self.server.llm,'state',side_effect=lambda:dict(ai)):
            self.assertEqual(self.request('ai/start',{})[0],200)
            self.assertFalse(self.server.voice.free_speech)
            self.assertEqual(self.request('voice/question',{})[0],400)
            self.server.voice.active=True
            self.assertEqual(self.request('voice/question',{})[0],200)
            self.assertTrue(self.server.voice.question_active)
            self.server.voice.set_free_speech(False)
            self.server.voice_action('ask_ai',101,None,self.server.voice.generation)
            self.assertTrue(self.server.voice.question_active)

    def test_dictated_window_action_always_requires_confirmation(self):
        self.server.voice.active=True
        with patch.object(self.server,'execute',return_value={'message':'OK'}) as execute:
            self.server.voice_action('assistant_query:maximizar',101,None,self.server.voice.generation)
            execute.assert_not_called()
            self.assertEqual(self.server.assistant.state()['confirmation_action'],'Maximizar')

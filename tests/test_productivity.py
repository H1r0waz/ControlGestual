import copy
import ctypes
import unittest
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_v2 as fixture
import desktop_windows as native
from desktop_features import validate_settings
from desktop_productivity import match_layout,extra_commands
from desktop_voice import VoiceControl,TRAINING,parse_command

AREA=dict(left=0,top=0,width=1600,height=900)
DISPLAY=dict(id=42,name='DISPLAY1',workArea=AREA,bounds=AREA)
SLOT=dict(app='allowed.exe',title='Test A',display='DISPLAY1',monitor_index=0,maximized=False,left=.1,top=.1,width=.5,height=.5)

class ProductivityLogicTests(unittest.TestCase):
    def test_migration_alias_validation_and_layout_bounds(self):
        settings=validate_settings({'voice_aliases':{'grande':'maximize'},'layouts':{'trabajo':[SLOT]}})
        extras=extra_commands(settings)
        self.assertEqual(parse_command('control grande',extras),'maximize')
        self.assertEqual(parse_command('control seleccionar chrome',extras),'select_app:chrome.exe')
        self.assertEqual(parse_command('control modo trabajo',extras),'layout:trabajo')
        for bad in ({'voice_aliases':{'minimizar':'maximize'}},{'voice_aliases':{'borrar':'shell'}},{'app_names':{'chrome':'C:\\chrome.exe'}},{'layouts':{'trabajo':[]}},{'audio_feedback':'yes'}):
            with self.assertRaises(ValueError):validate_settings(bad)
        plan=match_layout([SLOT],list(fixture.WINDOWS.values()),[DISPLAY],[])
        self.assertEqual(plan[0][1],dict(left=160,top=90,width=800,height=450))
        for windows,displays,excluded in (([],[DISPLAY],[]),(list(fixture.WINDOWS.values()),[],[]),(list(fixture.WINDOWS.values()),[DISPLAY],['allowed.exe'])):
            with self.assertRaises(ValueError):match_layout([SLOT],windows,displays,excluded)

    def test_wizard_recognizes_three_phrases_without_actions_and_ends_paused(self):
        calls=[];voice=VoiceControl('.',lambda *args:calls.append(args));voice.active=True;voice.begin_test();epoch=voice.generation
        voice.test_started-=2.1;voice.expire_test()
        voice.accept('control minimizar',epoch,.3);self.assertEqual(voice.test['index'],0)
        for text,_ in TRAINING:voice.accept(text,epoch,.95)
        self.assertEqual(calls,[]);self.assertEqual(voice.test['index'],3);self.assertFalse(voice.test['active']);self.assertTrue(voice.paused)
        voice.begin_test();voice.test_started-=2.1;voice.expire_test();voice.test_started-=21;voice.expire_test();self.assertFalse(voice.test['active'])
        self.assertIn('20 segundos',voice.test['message'])

    def test_multimedia_input_releases_key_and_handles_partial_failure(self):
        self.assertEqual(ctypes.sizeof(native.INPUT),40)
        with patch.object(native,'send_inputs') as send:
            native.multimedia_action('volume_up');events=send.call_args.args[0]
            self.assertEqual([event.data.ki.wVk for event in events],[0xAF,0xAF]);self.assertEqual(events[1].data.ki.dwFlags,2)
        with patch.object(native,'send_inputs',side_effect=[ValueError('blocked'),None]) as send:
            with self.assertRaises(ValueError):native.multimedia_action('media_toggle')
            self.assertEqual(send.call_args.args[0][0].data.ki.dwFlags,2)

class ProductivityApiTests(unittest.TestCase):
    request=fixture.ApiV2Tests.request
    tearDown=fixture.ApiV2Tests.tearDown
    setUp=fixture.ApiV2Tests.setUp

    def test_visual_intent_precedes_action_and_sound_follows_completion(self):
        import threading
        from types import SimpleNamespace
        fired=threading.Event();self.server.settings['audio_feedback']=True
        with patch.dict(sys.modules,{'winsound':SimpleNamespace(MB_OK=0,MessageBeep=lambda value:fired.set())}):
            with patch.object(native,'multimedia_action',side_effect=lambda action:self.assertEqual(self.server.action_notice['stage'],'pending') or {'message':'sent'}):
                self.server.execute('volume_up',{'snapshot':{'hwnd':101,'pid':201}})
            self.assertTrue(fired.wait(2));self.assertEqual(self.server.action_notice['stage'],'completed')

    def test_second_window_failure_rolls_back_all_and_failed_recovery_keeps_undo(self):
        other={**SLOT,'app':'other.exe','title':'Test C'}
        self.server.settings=validate_settings({'layouts':{'trabajo':[SLOT,other]}})
        with patch.object(native,'windows',return_value=list(fixture.WINDOWS.values())),patch.object(native,'monitors',return_value=[DISPLAY]),patch.object(native,'capture_placement',side_effect=lambda w:{'hwnd':w['hwnd'],'pid':w['pid'],'monitor':42}),patch.object(native,'place_bounds',side_effect=[{},ValueError('rejected')]),patch.object(native,'restore_placement',return_value={}) as restore:
            self.assertEqual(self.request('layouts/apply',{'name':'trabajo'})[0],400)
            self.assertEqual([call.args[0]['hwnd'] for call in restore.call_args_list],[103,101]);self.assertEqual(self.server.history,[])
        with patch.object(native,'windows',return_value=list(fixture.WINDOWS.values())),patch.object(native,'monitors',return_value=[DISPLAY]),patch.object(native,'capture_placement',side_effect=lambda w:{'hwnd':w['hwnd'],'pid':w['pid'],'monitor':42}),patch.object(native,'place_bounds',side_effect=[{},ValueError('rejected')]),patch.object(native,'restore_placement',side_effect=ValueError('recovery rejected')):
            code,result=self.request('layouts/apply',{'name':'trabajo'});self.assertEqual(code,400);self.assertIn('recuperación parcial',result['error'])
            self.assertEqual(self.server.history[-1]['saved']['kind'],'layout')

    def test_settings_vocab_and_voice_app_selection(self):
        with patch('desktop_app.validate_vocabulary') as validate:
            self.assertEqual(self.request('settings',{**self.server.settings,'voice_aliases':{'grande':'maximize'}})[0],200);validate.assert_called_once()
        self.assertEqual(self.server.voice.extra['grande'],'maximize')
        self.server.voice.active=True;self.server.settings['app_names']['prueba']='other.exe'
        with patch.object(native,'windows',return_value=list(fixture.WINDOWS.values())),patch.object(native,'activate_window',return_value={'message':'activated'}) as activate:
            result=self.server.voice_action('select_app:other.exe','active',None,self.server.voice.generation)
            self.assertEqual(result['selected_window']['hwnd'],103);activate.assert_called_once()
        self.assertEqual(self.request('voice/test/start',{})[0],200);self.assertTrue(self.server.voice.test['active'])
        self.assertEqual(self.request('voice/test/cancel',{})[0],200)

    def test_layout_preflight_failure_rollback_and_group_undo(self):
        self.server.settings=validate_settings({'layouts':{'trabajo':[SLOT]}})
        saved=dict(hwnd=101,pid=201,monitor=42,placement=b'private')
        with patch.object(native,'windows',return_value=list(fixture.WINDOWS.values())),patch.object(native,'monitors',return_value=[DISPLAY]),patch.object(native,'capture_placement',return_value=saved),patch.object(native,'place_bounds',return_value={'message':'OK'}) as place,patch.object(native,'restore_placement',return_value={'message':'restored'}) as restore:
            self.assertEqual(self.request('layouts/apply',{'name':'trabajo'})[0],200);place.assert_called_once()
            self.assertEqual(self.server.history[-1]['saved']['kind'],'layout')
            self.assertEqual(self.request('undo',{})[0],200);restore.assert_called_once()
            self.server.settings['excluded_apps']=['allowed.exe'];place.reset_mock()
            self.assertEqual(self.request('layouts/apply',{'name':'trabajo'})[0],400);place.assert_not_called()
            self.server.settings['excluded_apps']=[]
            with patch.object(native,'place_bounds',side_effect=ValueError('size refused')):
                before=len(self.server.history);self.assertEqual(self.request('layouts/apply',{'name':'trabajo'})[0],400);self.assertEqual(len(self.server.history),before)

    def test_scroll_and_media_use_selected_window_and_never_add_fake_undo(self):
        payload=dict(snapshot={'hwnd':101,'pid':201})
        with patch.object(native,'scroll_window',return_value={'message':'scroll'}) as scroll,patch.object(native,'multimedia_action',return_value={'message':'media'}) as media:
            self.assertEqual(self.request('action',{**payload,'action':'scroll_down'})[0],200);scroll.assert_called_once_with(payload['snapshot'],'down')
            self.assertEqual(self.request('action',{**payload,'action':'volume_up'})[0],200);media.assert_called_once_with('volume_up')
            self.assertEqual(self.server.history,[])
            self.server.settings['excluded_apps']=['allowed.exe'];self.assertEqual(self.request('action',{**payload,'action':'volume_up'})[0],400)

    def test_saving_layout_captures_only_chosen_windows(self):
        info={**fixture.WINDOWS[101],'bounds':dict(left=160,top=90,width=800,height=450)}
        with patch.object(native,'window_info',return_value=info),patch.object(native.user32,'MonitorFromWindow',return_value=42),patch.object(native,'monitor_info',return_value=DISPLAY),patch.object(native,'monitors',return_value=[DISPLAY]),patch('desktop_app.validate_vocabulary'):
            code,result=self.request('layouts/save',{'name':'trabajo','windows':[101]})
            self.assertEqual(code,200);self.assertEqual(result['layouts']['trabajo'][0]['left'],.1)
            self.assertEqual(self.request('layouts/save',{'name':'trabajo','windows':[101]})[0],400)
            self.assertEqual(self.request('layouts/delete',{'name':'trabajo'})[0],200)

if __name__=='__main__':unittest.main()

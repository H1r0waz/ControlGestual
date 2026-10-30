import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import desktop_windows as native
from desktop_app import DesktopServer
from desktop_voice import parse_command

INFO=dict(hwnd=123,pid=987,title='Documento de prueba',app='demo.exe',minimized=False,maximized=False)

class CloseTests(unittest.TestCase):
    def test_native_posts_normal_close_and_rejects_stale_or_hung_targets(self):
        with patch.object(native,'window_info',return_value=INFO),patch.object(native.user32,'PostMessageW',return_value=True) as post,patch.object(native.user32,'IsHungAppWindow',return_value=False):
            self.assertIn('Cierre solicitado',native.close_window(INFO)['message'])
            post.assert_called_once_with(123,0x0010,0,0)
            with self.assertRaises(ValueError):native.close_window({**INFO,'pid':988})
            with self.assertRaises(ValueError):native.close_window({**INFO,'hwnd':True})
            self.assertEqual(post.call_count,1)
        with patch.object(native,'window_info',return_value=INFO),patch.object(native.user32,'IsHungAppWindow',return_value=True),patch.object(native.user32,'PostMessageW') as post:
            with self.assertRaises(ValueError):native.close_window(INFO)
            post.assert_not_called()

    def test_selection_exclusions_voice_gestures_and_no_fake_undo(self):
        with patch.object(native,'window_info',return_value=INFO),patch.object(native.user32,'GetForegroundWindow',return_value=123):
            server=DesktopServer()
            try:
                with patch.object(native,'close_window',return_value={'message':'Cierre solicitado'}) as close,patch.object(native,'capture_placement') as save:
                    server.record_action({'old':True},'Anterior','Otra ventana')
                    saved=server.undo
                    result=server.execute('close',{'snapshot':INFO})
                    self.assertFalse(result['undoable']);self.assertEqual(result['undo_count'],1)
                    self.assertIs(server.undo,saved);save.assert_not_called()
                    server.settings['excluded_apps']=['demo.exe']
                    with self.assertRaises(ValueError):server.execute('close',{'snapshot':INFO})
                    server.settings['excluded_apps']=[]
                    with self.assertRaises(ValueError):server.execute('close',{'snapshot':INFO,'gesture':True,'emergency':0})
                    with self.assertRaises(ValueError):server.voice_action('close',123,None,server.voice.generation)
                    self.assertEqual(close.call_count,1)
                    server.voice.active=True;server.voice.stop_event.clear()
                    server.voice_action(parse_command('Control cerrar'),123,None,server.voice.generation)
                    close.assert_called_with({'hwnd':123,'pid':987,'title':INFO['title'],'app':'demo.exe'})
                    self.assertEqual(close.call_count,2)
                    self.assertEqual(parse_command('Control cerrar ventana'),'close')
                    self.assertEqual(parse_command('Control cerrar aplicación'),'close')
            finally:server.server_close()

    def test_real_close_preserves_application_veto_then_closes_our_window(self):
        state=Path(__file__).resolve().parents[1]/'work/close-test-state.json'
        state.write_text('{}')
        code="""import tkinter as t,json
from pathlib import Path
r=t.Tk();r.title('ControlGestual cierre descartable');r.geometry('360x160+100+100')
count=0
def close():
    global count
    count+=1;Path(STATE).write_text(json.dumps({'requests':count}))
    if count==2:r.destroy()
r.protocol('WM_DELETE_WINDOW',close);r.after(15000,r.destroy);r.mainloop()
""".replace('STATE',repr(str(state)))
        process=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+5;windows=[]
            while time.monotonic()<deadline:
                windows=[w for w in native.windows() if w['pid']==process.pid and w['title']=='ControlGestual cierre descartable']
                if windows:break
                time.sleep(.05)
            self.assertEqual(len(windows),1)
            target=windows[0];native.close_window(target)
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                try:
                    if json.loads(state.read_text()).get('requests')==1:break
                except (ValueError,OSError):pass
                time.sleep(.05)
            self.assertEqual(json.loads(state.read_text())['requests'],1)
            self.assertIsNone(process.poll());self.assertIsNotNone(native.window_info(target['hwnd']))
            native.close_window(target);self.assertEqual(process.wait(timeout=3),0)
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=3)

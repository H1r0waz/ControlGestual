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

class RealProductivityTests(unittest.TestCase):
    def test_layout_group_undo_and_scroll_on_our_disposable_windows(self):
        output=Path(__file__).resolve().parents[1]/'work/scroll-test-state.json'
        output.parent.mkdir(exist_ok=True);output.write_text('{"y":0}')
        code="""import tkinter as t,json
from pathlib import Path
r=t.Tk();r.title('ControlGestual V4 first');r.geometry('640x480+100+100')
text=t.Text(r);text.pack(fill='both',expand=True);text.insert('1.0','\\n'.join(str(i) for i in range(400)))
b=t.Toplevel(r);b.title('ControlGestual V4 second');b.geometry('640x480+900+100')
def tick():
    Path(OUTPUT).write_text(json.dumps({'y':text.yview()[0]}));r.after(100,tick)
r.after(100,tick);r.after(30000,r.destroy);r.mainloop()
""".replace('OUTPUT',repr(str(output)))
        process=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        server=None
        try:
            deadline=time.monotonic()+5;windows=[]
            while time.monotonic()<deadline:
                windows=[w for w in native.windows() if w['pid']==process.pid and w['title'].startswith('ControlGestual V4')]
                if len(windows)==2:break
                time.sleep(.05)
            self.assertEqual(len(windows),2)
            windows.sort(key=lambda w:w['title']);first=windows[0]
            native.scroll_window(first,'down')
            deadline=time.monotonic()+3;scrolled=False
            while time.monotonic()<deadline:
                try:scrolled=json.loads(output.read_text())['y']>0
                except (OSError,ValueError):pass
                if scrolled:break
                time.sleep(.05)
            self.assertTrue(scrolled,'The disposable text widget did not receive the wheel action')
            server=DesktopServer()
            with patch('desktop_app.validate_vocabulary'):server.save_layout('trabajo',[w['hwnd'] for w in windows])
            original=[native.window_info(w['hwnd'])['bounds'] for w in windows]
            for window,direction in zip(windows,('left','right')):native.arrange_window(window,direction)
            arranged=[native.window_info(w['hwnd'])['bounds'] for w in windows]
            server.apply_layout('trabajo')
            for window,bounds in zip(windows,original):self.assertTrue(all(abs(native.window_info(window['hwnd'])['bounds'][k]-bounds[k])<=4 for k in bounds))
            server.undo_action()
            for window,bounds in zip(windows,arranged):self.assertTrue(all(abs(native.window_info(window['hwnd'])['bounds'][k]-bounds[k])<=4 for k in bounds))
        finally:
            if server:server.server_close()
            process.terminate();process.wait(timeout=5)

if __name__=='__main__':unittest.main()

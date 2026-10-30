import ctypes as c
import http.client
import json
from pathlib import Path
import subprocess
import sys
import threading
import queue
import time
import unittest
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import desktop_windows as native
from desktop_app import DesktopServer

DISPLAYS = [dict(id=1, bounds=dict(left=0, top=0, width=1920, height=1080),workArea=dict(left=0,top=0,width=1920,height=1040)),
            dict(id=2, bounds=dict(left=1920, top=0, width=1080, height=1920),workArea=dict(left=1920,top=0,width=1080,height=1880))]
INFO = dict(hwnd=123, pid=987, title="Test", bounds=dict(left=100,top=50,width=1600,height=1000),minimized=False,maximized=False)

class FakeUser32:
    def __init__(self): self.monitor=1; self.calls=[]; self.maximized=False
    def IsHungAppWindow(self, hwnd): return False
    def MonitorFromWindow(self, hwnd, flags): return self.monitor
    def GetWindowPlacement(self, hwnd, placement): return True
    def SetWindowPlacement(self, hwnd, placement): self.calls.append("rollback"); return True
    def ShowWindowAsync(self, hwnd, command): self.calls.append(command); self.maximized=command==3; return True
    def IsZoomed(self, hwnd): return self.maximized
    def IsIconic(self, hwnd): return False
    def GetWindowRect(self, hwnd, rect):
        rect._obj.left=100;rect._obj.top=50;rect._obj.right=1700;rect._obj.bottom=1050;return True
    def SetWindowPos(self, hwnd, after, x, y, width, height, flags):
        self.calls.append((x,y,width,height)); self.monitor=2 if x>=1920 else 1;return True

class NativeTests(unittest.TestCase):
    def test_minimized_window_can_be_maximized_directly(self):
        fake=FakeUser32();fake.IsIconic=lambda hwnd:not fake.maximized
        with patch.object(native,"user32",fake),patch.object(native,"window_info",return_value={**INFO,"minimized":True}),patch.object(native,"get_style",return_value=0x00010000):
            self.assertIn("maximizada",native.toggle_maximize_window({"hwnd":123,"pid":987})["message"])
            self.assertTrue(fake.maximized)
    def test_maximize_toggles_and_rejects_unsupported_windows(self):
        fake=FakeUser32()
        with patch.object(native,"user32",fake),patch.object(native,"window_info",return_value=INFO),patch.object(native,"get_style",return_value=0x00010000):
            self.assertIn("maximizada",native.toggle_maximize_window({"hwnd":123,"pid":987})["message"])
            self.assertTrue(fake.maximized)
        with patch.object(native,"user32",fake),patch.object(native,"window_info",return_value={**INFO,"maximized":True}),patch.object(native,"get_style",return_value=0x00010000):
            self.assertIn("restaurada",native.toggle_maximize_window({"hwnd":123,"pid":987})["message"])
            self.assertFalse(fake.maximized)
        fake=FakeUser32()
        with patch.object(native,"user32",fake),patch.object(native,"window_info",return_value=INFO),patch.object(native,"get_style",return_value=0):
            with self.assertRaisesRegex(ValueError,"no permite"):native.toggle_maximize_window({"hwnd":123,"pid":987})
        self.assertEqual(fake.calls,[])
    def test_move_and_preserve_maximization(self):
        for maximized in [False,True]:
            fake=FakeUser32()
            with patch.object(native,"user32",fake),patch.object(native,"window_info",return_value={**INFO,"maximized":maximized}), \
                 patch.object(native,"monitors",return_value=DISPLAYS),patch.object(native,"monitor_info",return_value=DISPLAYS[0]), \
                 patch.object(native,"get_style",return_value=0x00C00000):
                result=native.move_window({"hwnd":123,"pid":987},"right")
                self.assertEqual(result["hwnd"],123)
                self.assertIn((1920,440,1080,1000),fake.calls)
                self.assertGreaterEqual(sum(isinstance(call,tuple) for call in fake.calls),12)
                if maximized: self.assertEqual(fake.calls[0],9); self.assertEqual(fake.calls[-1],3)

    def test_closed_window_and_minimized_rejected(self):
        for info in [None,{**INFO,"pid":1234},{**INFO,"minimized":True}]:
            with patch.object(native,"window_info",return_value=info):
                with self.assertRaises(ValueError): native.move_window({"hwnd":123,"pid":987},"right")

    def test_failed_animation_restores_original_placement(self):
        fake=FakeUser32();original=fake.SetWindowPos;count=0
        def fail_midway(*args):
            nonlocal count
            count+=1
            return False if count==3 else original(*args)
        fake.SetWindowPos=fail_midway
        with patch.object(native,"user32",fake),patch.object(native,"window_info",return_value=INFO), \
             patch.object(native,"monitors",return_value=DISPLAYS),patch.object(native,"monitor_info",return_value=DISPLAYS[0]), \
             patch.object(native,"get_style",return_value=0x00C00000):
            with self.assertRaises(OSError):native.move_window({"hwnd":123,"pid":987},"right")
        self.assertEqual(fake.calls[-1],"rollback")

    def test_negative_coordinates_and_no_wrap(self):
        left={**DISPLAYS[0],"id":3,"bounds":{**DISPLAYS[0]["bounds"],"left":-1920}}
        self.assertEqual(native.destination(DISPLAYS[0],[left,DISPLAYS[0]],"left")["bounds"]["left"],-1920)
        with self.assertRaises(ValueError):native.destination(DISPLAYS[0],DISPLAYS,"left")

class HttpTests(unittest.TestCase):
    def test_minimized_automatic_target_survives_passive_focus_change(self):
        front={"hwnd":456}
        items={123:{**INFO,"minimized":True},456:{**INFO,"hwnd":456,"pid":222},789:{**INFO,"hwnd":789,"pid":333}}
        with patch.object(native.user32,"GetForegroundWindow",side_effect=lambda:front["hwnd"]),patch.object(native,"window_info",side_effect=lambda hwnd:items.get(hwnd)), \
             patch.object(native,"capture_placement",return_value={"saved":True}),patch.object(native,"minimize_window",return_value={"message":"Minimized"}):
            for passive in (456,0):
                front["hwnd"]=passive
                self.assertEqual(self.request("/api/minimize",{"snapshot":{"hwnd":123,"pid":987}})[0],200)
                time.sleep(.2)
                self.assertEqual(self.server.capture("active")["hwnd"],123)
                front["hwnd"]=789;time.sleep(.2)
                self.assertEqual(self.server.capture("active")["hwnd"],789)
    def setUp(self):
        self.info_patch=patch.object(native,"window_info",return_value=INFO);self.info_patch.start()
        self.server=DesktopServer();self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2);self.info_patch.stop()
    def request(self,path,data=None,key=True,origin=None,host=None):
        connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        headers={"Content-Type":"application/json"}
        if key:headers["X-Control-Key"]=self.server.token
        if origin:headers["Origin"]=origin
        if host:headers["Host"]=host
        connection.request("GET" if data is None else "POST",path,body=None if data is None else json.dumps(data),headers=headers)
        response=connection.getresponse();body=response.read();status=response.status;connection.close()
        return status,body
    def test_auth_origin_host_and_file_boundary(self):
        self.assertEqual(self.request("/api/windows",key=False)[0],403)
        self.assertEqual(self.request("/api/pause",{},origin="https://example.com")[0],403)
        self.assertEqual(self.request("/api/pause",{},host="example.com")[0],403)
        self.assertEqual(self.request("/api/state")[0],200)
        self.assertEqual(self.request("/vendor/../../desktop_app.py")[0],403)
        self.assertEqual(self.request("/desktop_app.py")[0],404)
    def test_pause_blocks_gestures_and_epoch_blocks_rearming(self):
        self.assertEqual(self.request("/api/arm",{"emergency":self.server.emergency})[0],200)
        self.assertEqual(self.request("/api/pause",{})[0],200)
        with patch.object(native,"move_window") as move:
            self.assertEqual(self.request("/api/move",{"snapshot":{"hwnd":123,"pid":987},"direction":"right","gesture":True,"emergency":self.server.emergency})[0],400)
            move.assert_not_called()
        self.server.emergency+=1
        self.assertEqual(self.request("/api/arm",{"emergency":self.server.emergency-1})[0],400)
    def test_manual_move_requires_snapshot_and_routes_to_native(self):
        self.assertEqual(self.request("/api/move",{"direction":"right"})[0],400)
        with patch.object(native,"capture_placement",return_value={"saved":True}),patch.object(native,"move_window",return_value={"message":"Moved"}) as move:
            self.assertEqual(self.request("/api/move",{"snapshot":{"hwnd":123,"pid":987},"direction":"right"})[0],200)
            move.assert_called_once_with({"hwnd":123,"pid":987},"right")
    def test_undo_preserved_after_failed_move_and_consumed_after_success(self):
        payload={"snapshot":{"hwnd":123,"pid":987},"direction":"right"}
        with patch.object(native,"capture_placement",return_value={"saved":1}),patch.object(native,"move_window",return_value={"message":"Moved"}):
            self.assertEqual(self.request("/api/move",payload)[0],200)
        with patch.object(native,"capture_placement",return_value={"saved":2}),patch.object(native,"move_window",side_effect=ValueError("Rejected")):
            self.assertEqual(self.request("/api/move",payload)[0],400)
        self.assertEqual(self.server.undo,{"saved":1})
        self.assertTrue(json.loads(self.request("/api/state")[1])["undo_available"])
        with patch.object(native,"restore_placement",return_value={"message":"Restored"}) as restore:
            self.assertEqual(self.request("/api/undo",{})[0],200);restore.assert_called_once_with({"saved":1})
        self.assertEqual(self.request("/api/undo",{})[0],400)
        self.assertFalse(json.loads(self.request("/api/state")[1])["undo_available"])
    def test_preview_and_active_capture_validate_identity(self):
        with patch.object(native,"window_info",return_value=INFO):
            self.server.last={"hwnd":123,"pid":987,"title":"Test"}
            self.assertEqual(json.loads(self.request("/api/capture",{"selected":"active"})[1])["hwnd"],123)
            self.assertEqual(self.request("/api/preview",{"snapshot":{"hwnd":123,"pid":999},"direction":"left"})[0],400)
            feedback=[];self.server.feedback=lambda text,snapshot=None:feedback.append(text)
            self.assertEqual(self.request("/api/preview",{"snapshot":{"hwnd":123,"pid":987},"direction":"left"})[0],200)
            self.assertIn("←",feedback[-1])

    def test_minimize_can_be_undone_and_paused_gesture_cannot_minimize(self):
        payload={"snapshot":{"hwnd":123,"pid":987}}
        with patch.object(native,"capture_placement",return_value={"saved":True}),patch.object(native,"minimize_window",return_value={"message":"Minimized"}) as minimize:
            self.assertEqual(self.request("/api/minimize",{**payload,"gesture":True,"emergency":0})[0],400)
            minimize.assert_not_called()
            self.assertEqual(self.request("/api/minimize",payload)[0],200)
            self.assertEqual(self.server.undo,{"saved":True})
        with patch.object(native,"restore_placement",return_value={"message":"Restored"}):self.assertEqual(self.request("/api/undo",{})[0],200)

    def test_maximize_can_be_undone_and_rejects_paused_gesture(self):
        payload={"snapshot":{"hwnd":123,"pid":987}}
        with patch.object(native,"capture_placement",return_value={"saved":True}),patch.object(native,"toggle_maximize_window",return_value={"message":"Maximized"}) as maximize:
            self.assertEqual(self.request("/api/maximize",{**payload,"gesture":True,"emergency":0})[0],400);maximize.assert_not_called()
            self.assertEqual(self.request("/api/maximize",payload)[0],200);maximize.assert_called_once_with(payload["snapshot"])
        with patch.object(native,"restore_placement",return_value={"message":"Restored"}) as restore:
            self.assertEqual(self.request("/api/undo",{})[0],200);restore.assert_called_once_with({"saved":True})

    def test_settings_validation_persistence_and_unavailable_tray(self):
        (Path(__file__).resolve().parents[1]/"work").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/"work") as directory:
            self.server.settings_path=Path(directory)/"settings.json"
            settings={"sensitivity":12,"invert":True,"calibration":{"closed":.7,"open":1.3}}
            settings=DesktopServer.validate_settings(settings)
            self.assertEqual(self.request("/api/settings",settings)[0],200)
            self.assertEqual(json.loads(self.server.settings_path.read_text()),settings)
            reloaded=DesktopServer(settings_path=self.server.settings_path)
            try:self.assertEqual(reloaded.settings,settings)
            finally:reloaded.server_close()
            self.assertEqual(self.request("/api/settings",{**settings,"sensitivity":0})[0],400)
            self.assertEqual(self.server.settings,settings)
        self.assertEqual(self.request("/api/panel",{"action":"hide"})[0],400)

    def test_tray_controls_use_same_pause_and_undo_state(self):
        self.server.armed=True;epoch=self.server.emergency
        self.server.control("pause")
        self.assertFalse(self.server.armed);self.assertEqual(self.server.emergency,epoch+1)
        self.server.undo={"saved":True}
        with patch.object(native,"restore_placement",return_value={"message":"Restored"}) as restore:
            self.server.control("undo");restore.assert_called_once_with({"saved":True})
        self.assertIsNone(self.server.undo)
        with patch.object(native,"panel_window") as panel:
            self.server.control("show");panel.assert_called_once_with("show")

class RealWindowsTests(unittest.TestCase):
    def test_only_disposable_window_geometry_and_monitor_detection(self):
        # Never move existing user windows. The child owns the only test window.
        title="ControlGestual disposable native test"
        code="import tkinter as t; r=t.Tk(); r.title("+repr(title)+"); r.geometry('640x480+80+80'); r.after(10000,r.destroy); r.mainloop()"
        process=subprocess.Popen([sys.executable,"-c",code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+5; info=None
            while time.monotonic()<deadline:
                info=next((i for i in native.windows() if i["title"]==title),None)
                if info:break
                time.sleep(.05)
            self.assertIsNotNone(info)
            self.assertGreaterEqual(len(native.monitors()),1)
            saved=native.capture_placement({"hwnd":info["hwnd"],"pid":info["pid"]})
            native.animate_window(info["hwnd"],info["bounds"],dict(left=160,top=160,width=600,height=420))
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                moved=native.window_info(info["hwnd"])
                if abs(moved["bounds"]["left"]-160)<=2:break
                time.sleep(.02)
            self.assertLessEqual(abs(moved["bounds"]["left"]-160),2)
            if len(native.monitors())==1:
                before=moved["bounds"]
                with self.assertRaises(ValueError):native.move_window({"hwnd":info["hwnd"],"pid":info["pid"]},"right")
                self.assertEqual(native.window_info(info["hwnd"])["bounds"],before)
            self.assertIn("deshecho",native.restore_placement(saved)["message"])
            restored=native.window_info(info["hwnd"])
            self.assertTrue(all(abs(restored["bounds"][k]-saved["bounds"][k])<=3 for k in saved["bounds"]))
            self.assertIn("maximizada",native.toggle_maximize_window({"hwnd":info["hwnd"],"pid":info["pid"]})["message"])
            deadline=time.monotonic()+2
            while not native.user32.IsZoomed(info["hwnd"]) and time.monotonic()<deadline:time.sleep(.02)
            maximized_saved=native.capture_placement({"hwnd":info["hwnd"],"pid":info["pid"]})
            self.assertTrue(maximized_saved["maximized"])
            self.assertIn("restaurada",native.toggle_maximize_window({"hwnd":info["hwnd"],"pid":info["pid"]})["message"])
            deadline=time.monotonic()+2
            while native.user32.IsZoomed(info["hwnd"]) and time.monotonic()<deadline:time.sleep(.02)
            native.restore_placement(maximized_saved)
            self.assertTrue(native.user32.IsZoomed(info["hwnd"]))
            before_minimize=native.capture_placement({"hwnd":info["hwnd"],"pid":info["pid"]})
            self.assertIn("minimizada",native.minimize_window({"hwnd":info["hwnd"],"pid":info["pid"]})["message"])
            self.assertTrue(native.user32.IsIconic(info["hwnd"]))
            minimized_saved=native.capture_placement({"hwnd":info["hwnd"],"pid":info["pid"]})
            self.assertIn("maximizada",native.toggle_maximize_window({"hwnd":info["hwnd"],"pid":info["pid"]})["message"])
            self.assertFalse(native.user32.IsIconic(info["hwnd"]))
            self.assertTrue(native.user32.IsZoomed(info["hwnd"]))
            native.restore_placement(minimized_saved)
            self.assertTrue(native.user32.IsIconic(info["hwnd"]))
            native.restore_placement(before_minimize)
            self.assertFalse(native.user32.IsIconic(info["hwnd"]))
            self.assertTrue(native.user32.IsZoomed(info["hwnd"]))
        finally:
            process.terminate();process.wait(timeout=5)

    def test_overlay_shows_without_focus_and_hides_on_clear(self):
        process=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/"desktop_overlay.py")],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8",creationflags=subprocess.CREATE_NO_WINDOW)
        events=queue.Queue()
        def output():
            for line in process.stdout:
                try:events.put(json.loads(line))
                except ValueError:pass
        reader=threading.Thread(target=output,daemon=True);reader.start()
        def find():
            found=[]
            @native.ENUMWINDOW
            def collect(hwnd,_):
                text=c.create_unicode_buffer(256);native.user32.GetWindowTextW(hwnd,text,256)
                pid=native.w.DWORD();native.user32.GetWindowThreadProcessId(hwnd,c.byref(pid))
                if pid.value==process.pid and text.value==native.PANEL_TITLE+" — Indicador":found.append(hwnd)
                return True
            native.user32.EnumWindows(collect,0)
            return found[0] if found else None
        try:
            deadline=time.monotonic()+5;hwnd=None
            while not hwnd and time.monotonic()<deadline:hwnd=find();time.sleep(.05)
            self.assertIsNotNone(hwnd)
            capabilities=events.get(timeout=5)
            self.assertEqual(capabilities.get("event"),"capabilities")
            self.assertTrue(capabilities["tray"])
            self.assertIsInstance(capabilities["shortcut"],bool)
            # Deliver only to our own test window; no physical global shortcut is pressed.
            native.signature("SendMessageW",[native.w.HWND,native.w.UINT,native.w.WPARAM,native.w.LPARAM],c.c_ssize_t)(hwnd,0x0312,1,0)
            self.assertEqual(events.get(timeout=2),{"action":"undo"})
            before=native.user32.GetForegroundWindow()
            process.stdin.write(json.dumps({"text":"Prueba indicador →","x":20,"y":20})+"\n");process.stdin.flush()
            deadline=time.monotonic()+2
            while not native.user32.IsWindowVisible(hwnd) and time.monotonic()<deadline:time.sleep(.05)
            self.assertTrue(native.user32.IsWindowVisible(hwnd))
            self.assertEqual(native.user32.GetForegroundWindow(),before)
            self.assertTrue(native.get_style(hwnd,-20)&0x08000000)
            process.stdin.write('{"text":""}\n');process.stdin.flush()
            deadline=time.monotonic()+2
            while native.user32.IsWindowVisible(hwnd) and time.monotonic()<deadline:time.sleep(.05)
            self.assertFalse(native.user32.IsWindowVisible(hwnd))
        finally:
            process.stdin.close()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=3)
            errors=process.stderr.read();process.stderr.close()
            process.stdout.close();reader.join(timeout=2)
            self.assertEqual(process.returncode,0,errors)

if __name__=="__main__":unittest.main()

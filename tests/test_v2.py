import ctypes as c
import http.client
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import desktop_windows as native
from desktop_app import DesktopServer
from desktop_features import validate_settings,PROFILES,FINGER_GESTURES

WINDOWS={
    101:dict(hwnd=101,pid=201,title="Test A",app="allowed.exe",minimized=False,maximized=False),
    102:dict(hwnd=102,pid=202,title="Test B",app="blocked.exe",minimized=False,maximized=False),
    103:dict(hwnd=103,pid=203,title="Test C",app="other.exe",minimized=False,maximized=False),
}

class FeatureTests(unittest.TestCase):
    def test_version22_settings_gain_pinky_without_changing_existing_bindings(self):
        previous=validate_settings({"sensitivity":12,"excluded_apps":["blocked.exe"]})
        previous["finger_bindings"].pop("pinky")
        previous["finger_bindings"]["index"]["left"]="none"
        migrated=validate_settings(previous)
        self.assertNotIn("pinky",previous["finger_bindings"])
        self.assertEqual(migrated["finger_bindings"]["pinky"],FINGER_GESTURES["pinky"]["bindings"])
        self.assertEqual(migrated["finger_bindings"]["index"],previous["finger_bindings"]["index"])
        self.assertEqual(migrated["sensitivity"],12);self.assertEqual(migrated["excluded_apps"],["blocked.exe"])
    def test_finger_settings_migrate_validate_and_remain_independent_of_profiles(self):
        settings=validate_settings({"profile":"navigate"})
        self.assertEqual(settings["finger_bindings"],{k:v["bindings"] for k,v in FINGER_GESTURES.items()})
        settings["finger_bindings"]["index"]["left"]="none"
        self.assertEqual(validate_settings(settings)["finger_bindings"]["index"]["left"],"none")
        self.assertEqual(validate_settings({})["finger_bindings"]["index"]["left"],"snap_left")
        for invalid in ({"finger_bindings":[]},{"finger_bindings":{"index":{}}}):
            with self.assertRaises(ValueError):validate_settings(invalid)
    def test_layouts_partition_odd_sized_and_negative_screens(self):
        area=dict(left=-1001,top=-20,width=1001,height=701)
        left,right=[native.layout_bounds(area,key) for key in ("left","right")]
        self.assertEqual(left["width"]+right["width"],1001);self.assertEqual(left["left"]+left["width"],right["left"])
        quarters=[native.layout_bounds(area,key) for key in ("top_left","top_right","bottom_left","bottom_right")]
        self.assertEqual(sum(q["width"]*q["height"] for q in quarters),1001*701)
        with self.assertRaises(ValueError):native.layout_bounds(area,"arbitrary")

    def test_legacy_settings_migrate_without_losing_calibration(self):
        previous={"sensitivity":12,"invert":True,"calibration":{"closed":.7,"open":1.3}}
        migrated=validate_settings(previous)
        self.assertEqual({k:migrated[k] for k in previous},previous)
        self.assertEqual(migrated["bindings"],PROFILES["windows"])
        self.assertEqual(validate_settings({"profile":"navigate"})["bindings"]["right"],"next_app")
        for invalid in ({"excluded_apps":["C:\\bad.exe"]},{"bindings":{"left":"delete"}},{"profile":"unknown"}):
            with self.assertRaises(ValueError):validate_settings(invalid)

class ApiV2Tests(unittest.TestCase):
    def test_pinky_switches_both_directions_and_leaves_vertical_disabled(self):
        self.server.armed=True
        with patch.object(native,"windows",return_value=list(WINDOWS.values())),patch.object(native,"activate_window",return_value={"message":"Activated"}) as activate:
            for direction,expected in (("right",102),("left",103)):
                payload=self.payload("ignored",pose="pinky",direction=direction,emergency=0)
                self.assertEqual(self.request("gesture",payload)[0],200)
                self.assertEqual(activate.call_args.args[0]["hwnd"],expected)
            before=activate.call_count
            self.assertEqual(self.request("gesture",{**payload,"direction":"up"})[0],200)
            self.assertEqual(activate.call_count,before)
            self.server.settings["excluded_apps"]=["blocked.exe"]
            self.assertEqual(self.request("gesture",{**payload,"direction":"right"})[0],200)
            self.assertEqual(activate.call_args.args[0]["hwnd"],103)
            status,result=self.request("gesture",{**payload,"direction":"right"})
            self.assertEqual(status,200);self.assertEqual(result["selected_window"]["hwnd"],103)
            self.server.armed=False
            self.assertEqual(self.request("gesture",payload)[0],400)
    def test_finger_dispatch_uses_server_bindings_and_checks_pause_exclusions_and_direction(self):
        self.server.armed=True
        with patch.object(native,"capture_placement",return_value={"hwnd":101,"pid":201}),patch.object(native,"arrange_window",return_value={"message":"Arranged"}) as arrange:
            for pose,direction,layout in (("index","left","left"),("three","top_right","top_right")):
                payload=self.payload("minimize",pose=pose,direction=direction,emergency=0)
                self.assertEqual(self.request("gesture",payload)[0],200)
                self.assertEqual(arrange.call_args.args[1],layout)
            for pose,direction in (("invalid","left"),("three","left"),("index","top_left")):
                self.assertEqual(self.request("gesture",self.payload("ignored",pose=pose,direction=direction))[0],400)
            self.server.settings["finger_bindings"]["index"]["left"]="none"
            before=len(self.server.history)
            self.assertEqual(self.request("gesture",self.payload("ignored",pose="index",direction="left",emergency=0))[0],200)
            self.assertEqual(len(self.server.history),before)
            self.server.armed=False
            self.assertEqual(self.request("gesture",payload)[0],400)
            self.server.armed=True;self.server.settings["excluded_apps"]=["allowed.exe"]
            self.assertEqual(self.request("gesture",payload)[0],400)
    def setUp(self):
        self.info=patch.object(native,"window_info",side_effect=lambda hwnd:WINDOWS.get(hwnd));self.info.start()
        self.front=patch.object(native.user32,"GetForegroundWindow",return_value=101);self.front.start()
        self.server=DesktopServer();self.server.last={k:WINDOWS[101][k] for k in ("hwnd","pid","title")}
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2);self.info.stop();self.front.stop()
    def request(self,path,data=None):
        connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        headers={"X-Control-Key":self.server.token,"Content-Type":"application/json"}
        connection.request("GET" if data is None else "POST","/api/"+path,body=None if data is None else json.dumps(data),headers=headers)
        response=connection.getresponse();result=json.loads(response.read());status=response.status;connection.close();return status,result
    def payload(self,action,hwnd=101,**extra):
        return dict(action=action,snapshot={"hwnd":hwnd,"pid":WINDOWS[hwnd]["pid"]},**extra)

    def test_history_restores_multiple_steps_and_never_exposes_saved_geometry(self):
        saves=[dict(hwnd=101,pid=201,number=i) for i in (1,2)]
        with patch.object(native,"capture_placement",side_effect=saves),patch.object(native,"toggle_maximize_window",return_value={"message":"OK"}):
            for _ in range(2):self.assertEqual(self.request("action",self.payload("maximize"))[0],200)
        state=self.request("state")[1]
        self.assertEqual(len(state["history"]),2);self.assertNotIn("saved",state["history"][0])
        with patch.object(native,"restore_placement",return_value={"message":"Undo"}) as restore:
            self.assertEqual(self.request("undo",{})[1]["remaining"],1)
            self.assertEqual(self.request("undo",{})[1]["remaining"],0)
            self.assertEqual(restore.call_args_list[0].args[0]["number"],2)
            self.assertEqual(restore.call_args_list[1].args[0]["number"],1)
        for number in range(25):self.server.record_action({"number":number},"Test","Test")
        self.assertEqual(len(self.server.history),20)
        self.assertEqual(self.request("history/discard",{})[0],200);self.assertEqual(self.server.undo["number"],23)

    def test_exclusions_block_all_geometry_actions_and_are_respected_by_switching(self):
        self.server.settings=validate_settings({"excluded_apps":["blocked.exe"]})
        with patch.object(native,"capture_placement") as capture:
            for action in ("move_left","maximize","minimize","snap_top_left"):
                self.assertEqual(self.request("action",self.payload(action,102))[0],400)
            capture.assert_not_called()
        with patch.object(native,"windows",return_value=list(WINDOWS.values())),patch.object(native,"activate_window",return_value={"message":"Activated"}) as activate:
            self.assertEqual(self.request("action",self.payload("next_app"))[0],200)
            self.assertEqual(activate.call_args.args[0]["hwnd"],103)
        self.assertEqual(self.server.history[-1]["saved"]["kind"],"focus")

    def test_custom_profile_dispatches_only_its_binding_and_honors_destination(self):
        self.server.settings=validate_settings({"profile":"custom","bindings":dict(left="snap_top_left",right="none",up="maximize",down="minimize")})
        self.server.armed=True
        with patch.object(native,"capture_placement",return_value={"hwnd":101,"pid":201}),patch.object(native,"arrange_window",return_value={"message":"Arranged"}) as arrange:
            payload=self.payload("ignored",direction="left",emergency=0,monitor_id=456)
            self.assertEqual(self.request("gesture",payload)[0],200)
            arrange.assert_called_once_with(payload["snapshot"],"top_left",456)
            before=len(self.server.history)
            self.assertEqual(self.request("gesture",{**payload,"direction":"right"})[0],200)
            self.assertEqual(len(self.server.history),before)
        self.server.armed=False
        self.assertEqual(self.request("gesture",payload)[0],400)
        with patch.object(native,"capture_placement",return_value={"hwnd":101,"pid":201}),patch.object(native,"move_window",return_value={"message":"Moved"}) as move:
            self.assertEqual(self.request("action",self.payload("move_right",monitor_id=456))[0],200)
            move.assert_called_once_with({"hwnd":101,"pid":201},"right",456)

class RealV2Tests(unittest.TestCase):
    def test_layout_and_application_switch_on_disposable_windows(self):
        titles=["ControlGestual V2 test A","ControlGestual V2 test B"]
        code="import tkinter as t; r=t.Tk(); r.title("+repr(titles[0])+"); r.geometry('640x480+80+80'); b=t.Toplevel(r); b.title("+repr(titles[1])+"); b.geometry('640x480+180+180'); r.after(20000,r.destroy); r.mainloop()"
        process=subprocess.Popen([sys.executable,"-c",code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+5;found=[]
            while time.monotonic()<deadline:
                found=[w for w in native.windows() if w["pid"]==process.pid and w["title"] in titles]
                if len(found)==2:break
                time.sleep(.05)
            self.assertEqual(len(found),2)
            first=found[0];snapshot={k:first[k] for k in ("hwnd","pid")}
            original=native.capture_placement(snapshot)
            self.assertIn("acomodada",native.arrange_window(snapshot,"left")["message"])
            native.restore_placement(original)
            self.assertIn("acomodada",native.arrange_window(snapshot,"top_right")["message"])
            native.restore_placement(original)
            self.assertIn("activada",native.activate_window(snapshot)["message"])
            native.set_window_state(snapshot,'maximized');self.assertTrue(native.user32.IsZoomed(snapshot['hwnd']))
            native.set_window_state(snapshot,'maximized');self.assertTrue(native.user32.IsZoomed(snapshot['hwnd']))
            native.minimize_window(snapshot);native.set_window_state(snapshot,'normal')
            self.assertFalse(native.user32.IsZoomed(snapshot['hwnd']));self.assertFalse(native.user32.IsIconic(snapshot['hwnd']))
            native.restore_placement(original)
            self.assertIn("activada",native.activate_window({k:found[1][k] for k in ("hwnd","pid")})["message"])
        finally:process.terminate();process.wait(timeout=5)

if __name__=="__main__":unittest.main()

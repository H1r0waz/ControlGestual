"""Check a windowed build over redirected pipes without enabling a physical camera."""
import http.client
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import struct

root=Path(__file__).resolve().parents[1]
exe=root/"releases"/"ControlGestual-V5.3"/"ControlGestual-V5.3.exe"
binary=exe.read_bytes();pe=struct.unpack_from('<I',binary,0x3c)[0]
assert binary[pe:pe+4]==b'PE\x00\x00' and struct.unpack_from('<H',binary,pe+24+68)[0]==2,"Build must use the Windows GUI subsystem"
process=subprocess.Popen([str(exe),"--verify-build"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8",creationflags=subprocess.CREATE_NO_WINDOW)
messages=queue.Queue()
def read():
    for line in process.stdout:
        try:messages.put(json.loads(line))
        except ValueError:pass
threading.Thread(target=read,daemon=True).start()
try:
    session=messages.get(timeout=20)
    from urllib.parse import urlsplit
    address=urlsplit(session["origin"])
    def request(path,data=None):
        connection=http.client.HTTPConnection(address.hostname,address.port,timeout=75 if path=='/api/ai/start' else 5)
        connection.request("GET" if data is None else "POST",path,body=None if data is None else json.dumps(data),headers={"X-Control-Key":session["key"],"Content-Type":"application/json"})
        response=connection.getresponse();body=response.read();status=response.status;connection.close();return status,body
    assert request("/")[0]==200
    assert json.loads(request("/api/features")[1])["version"]=="5.3.0"
    assistant_status,assistant_body=request('/api/assistant/request',{'text':'Jarvis ayuda'})
    assert assistant_status==200 and 'Puedo mover' in json.loads(assistant_body)['message']
    assistant_state=json.loads(request('/api/state')[1])
    assert assistant_state['assistant']['turns'][-1]['role']=='assistant'
    assert not assistant_state['speech']['enabled']
    assert assistant_state['voice']['input_mode']=='commands'
    assert request('/api/ai/start',{})[0]==200
    assert json.loads(request('/api/state')[1])['voice']['input_mode']=='commands','AI activation changed command recognition'
    assert request('/api/voice/question',{})[0]==400,'Question capture must require an active microphone'
    assert request('/api/ai/stop',{})[0]==200
    assert json.loads(request('/api/state')[1])['phone']['ready'],'Portable Android tools not found in frozen build'
    for resource in ("/app.js","/camera-worker.js","/core.js","/hand-view.js","/vendor/vision_bundle.mjs","/vendor/hand_landmarker.task"):
        assert request(resource)[0]==200,resource
    import time
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        state=json.loads(request('/api/state')[1])
        if state['tray_available']:break
        time.sleep(.1)
    assert state['tray_available'],"Frozen Tk/tray helper did not register"
    # Exercise the packaged close action only on our disposable external window.
    disposable=subprocess.Popen([sys.executable,'-c',"import tkinter as t;r=t.Tk();r.title('ControlGestual frozen close test');r.after(15000,r.destroy);r.mainloop()"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+5;targets=[]
        while time.monotonic()<deadline:
            targets=[window for window in json.loads(request('/api/windows')[1])['windows'] if window['pid']==disposable.pid and window['title']=='ControlGestual frozen close test']
            if targets:break
            time.sleep(.05)
        assert len(targets)==1,'Disposable close target missing'
        target=targets[0]
        assert request('/api/assistant/request',{'text':'Jarvis minimiza esta ventana','selected':target['hwnd']})[0]==200
        assistant_state=json.loads(request('/api/state')[1])['assistant']
        assert assistant_state['context']['pid']==disposable.pid,assistant_state
        current=next(window for window in json.loads(request('/api/windows')[1])['windows'] if window['hwnd']==target['hwnd'])
        assert current['minimized'],'Natural assistant did not minimize its disposable target'
        assert request('/api/assistant/request',{'text':'Ahora maximizalo','selected':target['hwnd']})[0]==200
        current=next(window for window in json.loads(request('/api/windows')[1])['windows'] if window['hwnd']==target['hwnd'])
        assert current['maximized'] and not current['minimized'],'Natural follow-up did not maximize its original target'
        assert request('/api/history/discard',{})[0]==200
        assert request('/api/history/discard',{})[0]==200
        assert request('/api/assistant/request',{'text':'Cierra esta ventana','selected':target['hwnd']})[0]==200
        confirmation=json.loads(request('/api/state')[1])['assistant']['confirmation']
        assert confirmation==target['title'] and disposable.poll() is None
        status,body=request('/api/assistant/request',{'text':'Jarvis confirmar','selected':target['hwnd']})
        result=json.loads(body)
        assert status==200 and result['undoable'] is False and result['undo_count']==0,result
        assert disposable.wait(timeout=3)==0
        assert request('/api/assistant/request',{'text':'Ahora maximizalo','selected':target['hwnd']})[0]==200
        assert json.loads(request('/api/state')[1])['assistant']['context']['unavailable']
        assert request('/api/assistant/request',{'text':'Ahora maximizalo','selected':target['hwnd']})[0]==200
        assert json.loads(request('/api/state')[1])['assistant']['context']['unavailable']
    finally:
        if disposable.poll() is None:disposable.terminate();disposable.wait(timeout=3)
    assert request("/api/quit",{})[0]==200
    process.wait(timeout=10)
    assert process.returncode==0
    print(json.dumps({"windowed_executable":"Windows GUI subsystem verified","version":"5.3.0","local_assets":"passed","bundled_tk_tray":"registered","shutdown":"clean","physical_camera":"not opened"}))
finally:
    if process.poll() is None:process.terminate();process.wait(timeout=5)

"""Real authenticated app -> local Qwen -> confirmation -> disposable Win32 window."""
from pathlib import Path
import http.client,json,subprocess,sys,threading,time,queue
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from desktop_app import DesktopServer
import desktop_windows as native

frozen='--frozen' in sys.argv
server=None;thread=None;controller=None
if frozen:
    controller=subprocess.Popen([str(root/'releases/ControlGestual-V5.3/ControlGestual-V5.3.exe'),'--verify-build'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
    messages=queue.Queue()
    threading.Thread(target=lambda:messages.put(json.loads(controller.stdout.readline())),daemon=True).start()
    session=messages.get(timeout=25)
    from urllib.parse import urlsplit
    port=urlsplit(session['origin']).port;token=session['key']
else:
    server=DesktopServer();thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    port=server.server_port;token=server.token
window=subprocess.Popen([sys.executable,'-c',"import tkinter as t;r=t.Tk();r.title('ControlGestual IA descartable');r.geometry('440x220+100+100');r.after(180000,r.destroy);r.mainloop()"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def request(path,data=None):
    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=120)
    try:
        connection.request('GET' if data is None else 'POST','/api/'+path,body=None if data is None else json.dumps(data),headers={'X-Control-Key':token,'Content-Type':'application/json'})
        response=connection.getresponse();value=json.loads(response.read());assert response.status==200,value;return value
    finally:connection.close()

try:
    deadline=time.monotonic()+5;targets=[]
    while time.monotonic()<deadline:
        targets=[w for w in native.windows() if w['pid']==window.pid and w['title']=='ControlGestual IA descartable']
        if targets:break
        time.sleep(.05)
    assert len(targets)==1;target=targets[0]
    print(json.dumps({'phase':'activate local Qwen through authenticated app API'}),flush=True)
    request('ai/start',{})
    if server:assert not server.voice.free_speech
    assert request('state')['voice']['input_mode']=='commands'
    start=time.monotonic()
    answer=request('assistant/request',{'text':'¿Cuál es la diferencia entre RAM y almacenamiento?','selected':target['hwnd']})
    assert len(answer['message'])>30 and not request('state')['history']
    print(json.dumps({'phase':'real model conversation passed','seconds':round(time.monotonic()-start,2)}),flush=True)
    request('assistant/request',{'text':'Me gustaría que esta ventana ocupe toda la pantalla','selected':target['hwnd']})
    state=request('state')['assistant'];assert state['confirmation_action']=='Maximizar',state
    assert not native.window_info(target['hwnd'])['maximized'] and not request('state')['history']
    request('assistant/request',{'text':'Jarvis confirmar','selected':target['hwnd']})
    assert native.window_info(target['hwnd'])['maximized'];assert len(request('state')['history'])==1
    assert request('state')['assistant']['context']['pid']==window.pid
    print(json.dumps({'phase':'proposal did not act before confirmation; own window maximized after confirmation'}),flush=True)
    cancelled=[]
    worker=threading.Thread(target=lambda:cancelled.append(request('assistant/request',{'text':'Explicame brevemente cómo funciona la memoria en una computadora','selected':target['hwnd']})))
    worker.start();deadline=time.monotonic()+5
    while time.monotonic()<deadline and not request('state')['ai']['busy']:time.sleep(.02)
    assert request('state')['ai']['busy']
    request('assistant/cancel',{});worker.join(timeout=8)
    assert not worker.is_alive() and 'cancelada' in cancelled[0]['message'],cancelled
    state=request('state');assert len(state['history'])==1 and not state['assistant']['confirmation']
    request('ai/stop',{});assert not request('state')['ai']['enabled']
    if server:assert not server.voice.free_speech
    report={'build':'frozen' if frozen else 'source','conversation_with_real_qwen':'passed','app_http_auth':'used','target':'disposable Tk window owned by test','proposal_without_action':'passed','confirmation_maximized_original_pid':'passed','cancel_inflight_request':'passed','ai_stopped':'passed','user_windows_touched':0,'physical_microphone':'not opened','response':answer['message']}
    (root/'work'/('ai-end-to-end-frozen-check.json' if frozen else 'ai-end-to-end-check.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
finally:
    if server:server.shutdown();server.server_close();thread.join(timeout=3)
    elif controller:
        try:request('quit',{});controller.communicate(timeout=20)
        finally:
            if controller.poll() is None:controller.terminate();controller.wait(timeout=5)
    if window.poll() is None:window.terminate();window.wait(timeout=3)

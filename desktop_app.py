"""Loopback-only desktop controller. Run with Python on Windows."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hmac
import json
import mimetypes
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit, unquote

import desktop_windows as native
from desktop_features import ACTIONS,PROFILES,FINGER_GESTURES,VERSION,validate_settings
from desktop_runtime import redirected_stdio
from desktop_voice import VoiceControl,COMMANDS,spoken_phrase,input_devices,validate_vocabulary
from desktop_productivity import extra_commands,phrase,match_layout
from desktop_phone import PhoneControl,PHONE_ACTIONS
from desktop_assistant import Assistant
from desktop_speech import SpeechOutput
from desktop_llm import LocalModel

ROOT = Path(__file__).resolve().parent
DATA_ROOT=Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else ROOT

class DesktopServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address=("127.0.0.1", 0), settings_path=None):
        super().__init__(address, Handler)
        self.token = secrets.token_urlsafe(32)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.armed = False
        self.emergency = 0
        self.last = None
        self.recovery=None;self.recovery_foreground=None
        self.undo = None
        self.history=[];self.history_id=0
        self.feedback = lambda text, snapshot=None: None
        self.settings_path=settings_path
        self.settings=validate_settings({})
        if settings_path and settings_path.is_file():
            try:self.settings=self.validate_settings(json.loads(settings_path.read_text(encoding="utf-8")))
            except (ValueError,TypeError,OSError):pass
        self.tray_available=False;self.shortcut_available=False
        self.notice={"id":0,"text":""}
        self.lock = threading.Lock()
        self.target_lock=threading.Lock()
        self.settings_lock=threading.Lock()
        self.voice=VoiceControl(ROOT/'voice-model/vosk-model-small-es-0.42',self.voice_action)
        self.phone=PhoneControl(ROOT/'phone-tools/scrcpy-win64-v5.0.1',DATA_ROOT/'phone-private')
        self.speech=SpeechOutput();self.speech.enable(self.settings['spoken_replies']);self.voice.output=self.speech
        self.llm=LocalModel([DATA_ROOT/'local-ai',DATA_ROOT.parent.parent/'local-ai'])
        self.assistant=Assistant(self)
        self.voice.extra=extra_commands(self.settings)
        self.action_notice={'id':0,'stage':'','text':''}
        self.open_panel=None
        self.done = threading.Event()
        self.watcher = threading.Thread(target=self.watch, daemon=True)
        self.watcher.start()

    def watch(self):
        was_pressed = False
        while not self.done.wait(.06):
            pressed = bool(native.user32.GetAsyncKeyState(0x77) & 0x8000)  # F8
            if pressed and not was_pressed:
                self.armed = False; self.emergency += 1
                self.voice.stop()
                self.phone.pause()
                self.assistant.cancel();self.speech.stop()
                self.feedback("")
            was_pressed = pressed
            try:
                hwnd = native.user32.GetForegroundWindow()
                info = native.window_info(hwnd) if hwnd else None
                if info:self.observe_foreground(info)
            except OSError: pass

    def server_close(self):
        self.done.set()
        self.llm.cancel()
        self.voice.stop(wait=True)
        self.phone.close()
        self.assistant.cancel(clear=True);self.speech.close()
        self.llm.close()
        if self.watcher is not threading.current_thread():self.watcher.join(timeout=2)
        super().server_close()

    def observe_foreground(self,info):
        with self.target_lock:
            if self.recovery:
                previous=native.window_info(self.recovery["hwnd"])
                if previous and previous["pid"]==self.recovery["pid"] and previous["minimized"]:
                    if info["hwnd"]==self.recovery["hwnd"]:return
                    if self.recovery_foreground is None:self.recovery_foreground=info["hwnd"];return
                    if info["hwnd"]==self.recovery_foreground:return
                self.recovery=None;self.recovery_foreground=None
            self.last={k:info[k] for k in ("hwnd","pid","title")}

    def capture(self, selected):
        expected_pid = None
        if selected == "active":
            with self.target_lock:target=self.last
            expected_pid = target and target["pid"]
            selected = target and target["hwnd"]
        if type(selected) is not int or not 0 < selected < 2 ** (8 * native.c.sizeof(native.c.c_void_p)):
            raise ValueError("Elegí una ventana o activá una aplicación primero.")
        info = native.window_info(selected)
        if not info or expected_pid is not None and info["pid"] != expected_pid: raise ValueError("La ventana ya no está disponible.")
        return {"hwnd": info["hwnd"], "pid": info["pid"], "title": info["title"][:200],"app":info.get("app","")}

    @staticmethod
    def validate_settings(data):
        return validate_settings(data)

    def allowed_window(self,snapshot):
        if not isinstance(snapshot,dict) or type(snapshot.get("hwnd")) is not int or type(snapshot.get("pid")) is not int or not 0<snapshot["hwnd"]<2**(8*native.c.sizeof(native.c.c_void_p)) or not 0<snapshot["pid"]<2**32:
            raise ValueError("Ventana inválida.")
        info=native.window_info(snapshot["hwnd"])
        if not info or info["pid"]!=snapshot["pid"]:raise ValueError("La ventana se cerró o cambió.")
        if info.get("app","").lower() in self.settings["excluded_apps"]:raise ValueError("Esta aplicación está excluida del control gestual.")
        return info

    def record_action(self,saved,label,title):
        self.history_id+=1
        self.history.append({"id":self.history_id,"saved":saved,"label":label,"title":title[:200],"time":time.strftime("%H:%M:%S")})
        self.history=self.history[-20:];self.undo=saved

    def history_view(self):
        return [{k:item[k] for k in ("id","label","title","time")} for item in reversed(self.history)]

    def save_settings(self,data):
        settings=self.validate_settings(data)
        extras=extra_commands(settings)
        if extras!=extra_commands(self.settings):
            try:validate_vocabulary(self.voice.model_path,extras.keys())
            except ImportError:raise ValueError('Falta el motor local de voz. Usá el ejecutable completo para guardar frases nuevas.')
        with self.settings_lock:
            if self.settings_path:
                temporary=self.settings_path.with_suffix('.tmp');temporary.write_text(json.dumps(settings,indent=2)+'\n',encoding='utf-8');temporary.replace(self.settings_path)
            self.settings=settings
        if self.speech.enabled!=settings['spoken_replies']:self.speech.enable(settings['spoken_replies'])
        if extras!=self.voice.extra:self.voice.set_commands(extras)
        return settings

    def announce(self,label,title='',snapshot=None,completed=False):
        text=('✓ ' if completed else '→ Voy a ')+label+(' · '+title if title else '')
        self.action_notice={'id':self.action_notice['id']+1,'stage':'completed' if completed else 'pending','text':text}
        self.feedback(text,snapshot)
        if completed and self.settings['audio_feedback']:
            def beep():
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_OK)
                except (RuntimeError,OSError):pass
            threading.Thread(target=beep,daemon=True).start()

    def save_layout(self,name,selected):
        name=phrase(name,3)
        if not isinstance(selected,list) or not 1<=len(selected)<=8 or len(set(selected))!=len(selected) or any(type(hwnd) is not int for hwnd in selected):raise ValueError('Elegí de una a ocho ventanas diferentes.')
        displays=native.monitors();slots=[]
        for hwnd in selected:
            snapshot=self.capture(hwnd);info=self.allowed_window(snapshot)
            if info['minimized']:raise ValueError('Recuperá las ventanas minimizadas antes de guardar una distribución.')
            display=native.monitor_info(native.user32.MonitorFromWindow(hwnd,2));area=display['workArea'];bounds=info['bounds']
            index=next((i for i,d in enumerate(displays) if d['id']==display['id']),None)
            if index is None:raise ValueError('La configuración de pantallas cambió.')
            slots.append(dict(app=info['app'],title=info['title'][:200],display=display['name'],monitor_index=index,maximized=bool(info['maximized']),left=max(0,min(1,(bounds['left']-area['left'])/area['width'])),top=max(0,min(1,(bounds['top']-area['top'])/area['height'])),width=max(.05,min(1,bounds['width']/area['width'])),height=max(.05,min(1,bounds['height']/area['height']))))
        if name in self.settings['layouts']:raise ValueError('Ese nombre ya existe. Eliminá esa distribución si querés reemplazarla.')
        return self.save_settings({**self.settings,'layouts':{**self.settings['layouts'],name:slots}})

    def restore_group(self,items):
        for saved in items:self.allowed_window(saved)
        before=[native.capture_placement(saved) for saved in items];changed=[]
        try:
            for saved in items:changed.append(saved);native.restore_placement(saved)
        except Exception:
            failures=[]
            for previous in reversed(before[:len(changed)]):
                try:native.restore_placement(previous)
                except (ValueError,OSError):failures.append(previous)
            if failures:raise ValueError('La recuperación quedó incompleta. Revisá las ventanas antes de volver a intentar.')
            raise
        return {'message':'Distribución deshecha.'}

    def apply_layout(self,name,generation=None):
        name=phrase(name,3)
        if name not in self.settings['layouts']:raise ValueError('Distribución no encontrada.')
        if not self.lock.acquire(blocking=False):raise ValueError('Hay otra acción en curso.')
        try:
            plan=match_layout(self.settings['layouts'][name],native.windows(),native.monitors(),self.settings['excluded_apps'])
            for window,_,_ in plan:self.allowed_window(window)
            originals=[native.capture_placement(window) for window,_,_ in plan];changed=[];epoch=self.emergency
            self.announce('aplicar modo '+name)
            try:
                for window,bounds,maximized in plan:
                    if epoch!=self.emergency or generation is not None and (not self.voice.active or self.voice.stop_event.is_set() or generation!=self.voice.generation):raise ValueError('Distribución cancelada desde el control.')
                    changed.append(window);self.allowed_window(window);native.place_bounds(window,bounds,maximized)
            except Exception:
                failures=[]
                for saved in reversed(originals[:len(changed)]):
                    try:native.restore_placement(saved)
                    except (ValueError,OSError):failures.append(saved)
                if failures:
                    self.record_action({'kind':'layout','items':originals},'Recuperar distribución incompleta',name)
                    raise ValueError('Distribución incompleta y recuperación parcial. Revisá las ventanas; Deshacer permite reintentar.')
                raise
            self.record_action({'kind':'layout','items':originals},'Modo '+name,name);self.announce('Modo '+name,completed=True)
            return {'message':'Modo '+name+' aplicado. Deshacer recupera las posiciones anteriores.','undo_count':len(self.history)}
        finally:self.lock.release()

    def execute(self,action,data):
        if action not in ACTIONS:raise ValueError("Acción inválida.")
        if not self.lock.acquire(blocking=False):raise ValueError("Hay otra acción en curso.")
        try:
            if data.get('assistant_epoch') is not None and data['assistant_epoch']!=self.emergency:raise ValueError('Solicitud cancelada por la pausa.')
            if data.get("gesture") and (not self.armed or data.get("emergency")!=self.emergency):raise ValueError("El control está pausado.")
            if data.get("voice") and (not self.voice.active or self.voice.stop_event.is_set() or data.get("voice_generation")!=self.voice.generation):raise ValueError("El control por voz está apagado o cambió de objetivo.")
            if action=="none":return {"message":"Este gesto está desactivado.","undo_count":len(self.history)}
            snapshot=data.get("snapshot")
            if not isinstance(snapshot,dict):raise ValueError("Ventana inválida.")
            if type(snapshot.get("hwnd")) is not int or type(snapshot.get("pid")) is not int or not 0<snapshot["hwnd"]<2**(8*native.c.sizeof(native.c.c_void_p)) or not 0<snapshot["pid"]<2**32:
                raise ValueError("Ventana inválida.")
            monitor=data.get("monitor_id")
            if monitor is not None and (type(monitor) is not int or monitor<=0):raise ValueError("Pantalla inválida.")
            if action in ("next_app","previous_app"):
                candidates=sorted([w for w in native.windows() if w.get("app","").lower() not in self.settings["excluded_apps"]],key=lambda w:w["hwnd"])
                if len(candidates)<2:raise ValueError("Abrí al menos dos ventanas permitidas para cambiar de aplicación.")
                anchor=next((i for i,w in enumerate(candidates) if w["hwnd"]==snapshot.get("hwnd") and w["pid"]==snapshot.get("pid")),None)
                if anchor is None:anchor=-1 if action=="next_app" else 0
                target=candidates[(anchor+(1 if action=="next_app" else -1))%len(candidates)]
                previous=native.window_info(native.user32.GetForegroundWindow()) or native.window_info(snapshot.get("hwnd"))
                self.announce(ACTIONS[action],target['title'],target)
                result=native.activate_window(target)
                if previous and previous["pid"]==snapshot.get("pid") and previous.get("app","").lower() not in self.settings["excluded_apps"]:
                    self.record_action({"kind":"focus","snapshot":{k:previous[k] for k in ("hwnd","pid")}},ACTIONS[action],target["title"])
                with self.target_lock:self.last={k:target[k] for k in ("hwnd","pid","title")};self.recovery=None;self.recovery_foreground=None
                self.announce(ACTIONS[action],target['title'],target,True)
                return {**result,"undo_count":len(self.history),"selected_window":{k:target[k] for k in ("hwnd","pid","title")}}
            info=self.allowed_window(snapshot)
            self.announce(ACTIONS[action],info['title'],snapshot)
            if action=='close':
                result=native.close_window(snapshot)
                self.announce('Cierre solicitado',info['title'],snapshot,True)
                return {**result,'undo_count':len(self.history),'undoable':False}
            if action.startswith('scroll_') or action in native.MEDIA_KEYS:
                result=native.scroll_window(snapshot,action[7:]) if action.startswith('scroll_') else native.multimedia_action(action)
                self.announce(ACTIONS[action],info['title'],snapshot,True)
                return {**result,'undo_count':len(self.history),'undoable':False}
            saved=native.capture_placement(snapshot)
            if action=="minimize":result=native.minimize_window(snapshot)
            elif action=="maximize":result=native.set_window_state(snapshot,data["window_state"]) if "window_state" in data else native.toggle_maximize_window(snapshot)
            elif action.startswith("snap_"):result=native.arrange_window(snapshot,action[5:],monitor)
            elif monitor is None:result=native.move_window(snapshot,"left" if action=="move_left" else "right")
            else:result=native.move_window(snapshot,"left" if action=="move_left" else "right",monitor)
            self.record_action(saved,ACTIONS[action],info["title"])
            with self.target_lock:
                self.recovery=None;self.recovery_foreground=None
                if action=="minimize":
                    info=native.window_info(snapshot["hwnd"])
                    if info and info["pid"]==snapshot["pid"]:
                        self.recovery={k:info[k] for k in ("hwnd","pid","title")};self.last=self.recovery
                        foreground=native.user32.GetForegroundWindow() or 0
                        self.recovery_foreground=foreground if foreground!=snapshot["hwnd"] else None
            self.announce(ACTIONS[action],info['title'],snapshot,True)
            return {**result,"undo_count":len(self.history)}
        finally:self.lock.release()

    def undo_action(self):
        if not self.lock.acquire(blocking=False):raise ValueError("Hay otra acción en curso.")
        try:
            if self.undo is None:raise ValueError("No hay una acción para deshacer.")
            saved=self.undo
            # Saved geometry is private; only the latest action is restored at each step.
            target=saved.get("snapshot") if saved.get("kind")=="focus" else saved
            if "hwnd" in target:self.allowed_window(target)
            result=self.restore_group(saved['items']) if saved.get('kind')=='layout' else native.activate_window(target) if saved.get("kind")=="focus" else native.restore_placement(saved)
            if self.history and self.history[-1]["saved"] is saved:self.history.pop()
            else:self.history=[]
            self.undo=self.history[-1]["saved"] if self.history else None
            with self.target_lock:self.recovery=None;self.recovery_foreground=None
            self.announce('Acción deshecha',completed=True);return {**result,"remaining":len(self.history)}
        finally:self.lock.release()

    def voice_action(self,command,selected,monitor,generation):
        if not self.voice.active or self.voice.stop_event.is_set() or generation!=self.voice.generation:raise ValueError('Voz apagada o selección modificada.')
        if command=='ask_ai':
            if not self.llm.state()['enabled']:raise ValueError('Encendé la IA antes de dictar una consulta.')
            if self.llm.state().get('busy'):raise ValueError('Esperá la respuesta de IA o cancelá la petición actual.')
            return self.voice.begin_question()
        if command.startswith('assistant_query:'):return self.assistant.request(command[16:],selected,monitor,generation,force_confirmation=True)
        if command.startswith('assistant:'):return self.assistant.request(command[10:],selected,monitor,generation)
        if command.startswith('phone_'):
            action=command[6:]
            if action=='show':return self.phone.show()
            if action=='pause':self.phone.pause();return {'message':'Control del teléfono pausado.'}
            if action=='resume':return self.phone.resume()
            if action=='disconnect':return self.phone.disconnect()
            self.announce('Teléfono: '+PHONE_ACTIONS.get(action,action))
            result=self.phone.action(action);self.announce('Teléfono: '+PHONE_ACTIONS[action],completed=True)
            return result
        if command.startswith('layout:'):return self.apply_layout(command[7:],generation)
        if command.startswith('select_app:'):
            app=command[11:];candidates=[w for w in native.windows() if w.get('app','').lower()==app and app not in self.settings['excluded_apps']]
            known=[w for w in candidates if self.last and self.last['hwnd']==w['hwnd'] and self.last['pid']==w['pid']]
            target=known[0] if known else candidates[0] if len(candidates)==1 else None
            if target is None:raise ValueError('Abrí esa aplicación o elegí una de sus ventanas en la lista si hay varias.')
            self.allowed_window(target);self.announce('seleccionar aplicación',target['title'],target);result=native.activate_window(target)
            with self.target_lock:self.last={k:target[k] for k in ('hwnd','pid','title')};self.recovery=None
            self.announce('Aplicación seleccionada',target['title'],target,True)
            return {**result,'selected_window':{k:target[k] for k in ('hwnd','pid','title')}}
        if command=='stop_all':
            self.assistant.cancel();self.speech.stop()
            self.armed=False;self.emergency+=1;self.voice.stop();self.phone.pause();self.feedback('');return {"message":"Cámara, micrófono y control del teléfono pausados."}
        if command in ('show_panel','hide_panel'):
            if command=='hide_panel' and not self.tray_available:raise ValueError('Bandeja no disponible; no se puede ocultar el panel.')
            self.control('show' if command=='show_panel' else 'hide');return {"message":self.notice['text']}
        if command.startswith('monitor_'):
            if command=='monitor_auto':destination=None
            else:
                displays=native.monitors();index=int(command.removeprefix('monitor_'))-1
                if not 0<=index<len(displays):raise ValueError('Esa pantalla no está conectada.')
                destination=displays[index]['id']
            return {"message":"Destino automático." if destination is None else "Pantalla de destino elegida.","monitor_id":destination}
        if command=='undo':return self.undo_action()
        if command=='discard_history':
            if not self.lock.acquire(blocking=False):raise ValueError('Hay otra acción en curso.')
            try:
                if self.history:self.history.pop()
                self.undo=self.history[-1]['saved'] if self.history else None
                return {"message":"Último registro descartado."}
            finally:self.lock.release()
        snapshot=self.capture(selected)
        data={"snapshot":snapshot,"monitor_id":monitor,"voice":True,"voice_generation":generation}
        action=command
        if command in ('maximize','restore','toggle_maximize'):
            action='maximize'
            if command!='toggle_maximize':data['window_state']='maximized' if command=='maximize' else 'normal'
        return self.execute(action,data)

    def control(self,action):
        try:
            if action=="undo":result=self.undo_action()["message"]
            elif action=="pause":self.armed=False;self.emergency+=1;self.voice.stop();self.phone.pause();self.assistant.cancel();self.speech.stop();self.feedback("");result="Control pausado desde la bandeja."
            elif action in ("show","hide"):
                try:native.panel_window(action)
                except ValueError:
                    if action=="show" and self.open_panel:self.open_panel()
                    else:raise
                result="Panel oculto. La cámara continúa si estaba encendida." if action=="hide" else "Panel visible."
            elif action=="quit":self.armed=False;threading.Thread(target=self.shutdown,daemon=True).start();return
            else:return
        except (ValueError,OSError) as error:result=str(error)
        self.notice={"id":self.notice["id"]+1,"text":result}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass  # Never log window titles or the session key.

    def respond(self, status, data, mime="application/json; charset=utf-8"):
        if not isinstance(data, bytes): data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; connect-src 'self'; media-src 'self' blob:; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def valid_host(self):
        return self.headers.get("Host") == urlsplit(self.server.origin).netloc

    def authorized(self):
        origin = self.headers.get("Origin")
        return self.valid_host() and (origin is None or origin == self.server.origin) and hmac.compare_digest(self.headers.get("X-Control-Key", "").encode(), self.server.token.encode())

    def do_GET(self):
        if not self.valid_host(): return self.respond(403, {"error": "Host inválido."})
        path = unquote(urlsplit(self.path).path)
        if path.startswith("/api/"):
            if not self.authorized(): return self.respond(403, {"error": "Sesión no autorizada."})
            try:
                if path == "/api/state":
                    ai_state=self.server.llm.state()
                    if self.server.voice.free_speech and not ai_state['enabled'] and not ai_state['starting']:self.server.voice.set_free_speech(False)
                    return self.respond(200, {"armed": self.server.armed, "emergency": self.server.emergency, "last": self.server.last, "undo_available": self.server.undo is not None,
                        "tray_available":self.server.tray_available,"shortcut_available":self.server.shortcut_available,"notice":self.server.notice,"recovery":self.server.recovery,
                        "version":VERSION,"history":self.server.history_view(),"voice":self.server.voice.state(),"action_notice":self.server.action_notice,"phone":self.server.phone.state(),"assistant":self.server.assistant.state(),"speech":self.server.speech.state(),"ai":ai_state})
                if path=="/api/settings":return self.respond(200,self.server.settings)
                if path=="/api/features":return self.respond(200,{"actions":ACTIONS,"profiles":PROFILES,"finger_gestures":FINGER_GESTURES,"version":VERSION,"phone_actions":{'phone_'+key:'Teléfono: '+label for key,label in PHONE_ACTIONS.items()}})
                if path=="/api/voice/commands":return self.respond(200,{"commands":['Control '+spoken_phrase(phrase) for phrase in (*COMMANDS,*self.server.voice.extra)]})
                if path=='/api/voice/devices':
                    try:return self.respond(200,{'devices':input_devices()})
                    except Exception:return self.respond(400,{'error':'No se pudieron listar los micrófonos. Revisá el dispositivo y el permiso de Windows.'})
                if path == "/api/windows": return self.respond(200, {"windows": native.windows(), "displays": native.monitors()})
            except OSError: return self.respond(500, {"error": "Windows no pudo consultar las ventanas."})
            return self.respond(404, {"error": "Ruta desconocida."})
        fixed = {"/": ROOT / "desktop" / "index.html", "/app.js": ROOT / "desktop" / "app.js",
                 "/style.css": ROOT / "desktop" / "style.css", "/core.js": ROOT / "extension" / "core.js",
                 "/hand-view.js": ROOT / "extension" / "hand-view.js"}
        fixed["/camera-worker.js"]=ROOT/"desktop"/"camera-worker.js"
        if path.startswith("/vendor/"):
            base = (ROOT / "extension" / "vendor").resolve()
            target = (base / path.removeprefix("/vendor/")).resolve()
            if not target.is_relative_to(base): return self.respond(403, {"error": "Ruta inválida."})
        else: target = fixed.get(path)
        if not target or not target.is_file(): return self.respond(404, {"error": "Archivo no encontrado."})
        mime = {".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm"}.get(target.suffix) or mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.respond(200, target.read_bytes(), mime)

    def do_POST(self):
        if not self.authorized():
            # Drain bounded request bodies so Windows can deliver the 403 before closing.
            try:
                size=int(self.headers.get("Content-Length","0"))
                if 0<size<=65536:
                    self.connection.settimeout(1);self.rfile.read(size)
            except (OSError,ValueError):pass
            return self.respond(403, {"error": "Sesión no autorizada."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 65536 or self.headers.get("Content-Type") != "application/json":
                raise ValueError("Solicitud inválida.")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict): raise ValueError("Solicitud inválida.")
            path = urlsplit(self.path).path
            if path=='/api/ai/start':
                result=self.server.llm.start();self.server.voice.set_free_speech(False)
                return self.respond(200,result)
            if path=='/api/voice/question':
                if not self.server.llm.state()['enabled']:raise ValueError('Encendé la IA antes de dictar una consulta.')
                if self.server.llm.state().get('busy'):raise ValueError('Esperá la respuesta de IA o cancelá la petición actual.')
                return self.respond(200,self.server.voice.begin_question())
            if path=='/api/ai/stop':
                self.server.assistant.cancel();self.server.speech.stop();self.server.voice.set_free_speech(False)
                return self.respond(200,self.server.llm.stop())
            if path=='/api/assistant/request':return self.respond(200,self.server.assistant.request(data.get('text'),data.get('selected','active'),data.get('monitor_id')))
            if path=='/api/assistant/reset':
                self.server.assistant.reset();self.server.speech.stop()
                return self.respond(200,self.server.assistant.reply('Conversación reiniciada. Elegí una ventana o nombrá una aplicación.',speak=False))
            if path=='/api/assistant/cancel':
                self.server.assistant.cancel();self.server.speech.stop()
                return self.respond(200,self.server.assistant.reply('Solicitud cancelada.',speak=False))
            if path=='/api/phone/pair':return self.respond(200,self.server.phone.pair(data.get('host'),data.get('port'),data.get('code')))
            if path=='/api/phone/connect':return self.respond(200,self.server.phone.connect(data.get('host'),data.get('port')))
            if path=='/api/phone/check':return self.respond(200,self.server.phone.check())
            if path=='/api/phone/disconnect':return self.respond(200,self.server.phone.disconnect())
            if path=='/api/phone/show':return self.respond(200,self.server.phone.show())
            if path=='/api/phone/hide':return self.respond(200,self.server.phone.hide())
            if path=='/api/phone/pause':self.server.phone.pause();return self.respond(200,{'message':'Control del teléfono pausado.'})
            if path=='/api/phone/resume':return self.respond(200,self.server.phone.resume())
            if path=='/api/phone/action':
                if data.get('gesture') and (not self.server.armed or data.get('emergency')!=self.server.emergency):raise ValueError('Los gestos están pausados.')
                action=data.get('action')
                if not isinstance(action,str) or action not in PHONE_ACTIONS:raise ValueError('Acción del teléfono inválida.')
                result=self.server.phone.action(action);self.server.announce('Teléfono: '+PHONE_ACTIONS[action],completed=True)
                return self.respond(200,result)
            if path=='/api/voice/test/start':
                self.server.voice.begin_test();self.server.armed=False;self.server.emergency+=1
                return self.respond(200,self.server.voice.state())
            if path=='/api/voice/test/cancel':
                self.server.voice.cancel_test();return self.respond(200,self.server.voice.state())
            if path=='/api/layouts/save':return self.respond(200,self.server.save_layout(data.get('name'),data.get('windows')))
            if path=='/api/layouts/apply':return self.respond(200,self.server.apply_layout(data.get('name')))
            if path=='/api/layouts/delete':
                name=phrase(data.get('name'),3)
                if name not in self.server.settings['layouts']:raise ValueError('Distribución no encontrada.')
                layouts={k:v for k,v in self.server.settings['layouts'].items() if k!=name}
                return self.respond(200,self.server.save_settings({**self.server.settings,'layouts':layouts}))
            if path in ('/api/voice/start','/api/voice/target'):
                self.server.voice.configure(data.get('selected'),data.get('monitor_id'))
                if path.endswith('/start'):self.server.voice.start(data.get('device_id'))
                return self.respond(200,self.server.voice.state())
            if path=='/api/voice/stop':
                self.server.voice.stop();self.server.speech.stop();self.server.assistant.cancel();return self.respond(200,self.server.voice.state())
            if path=="/api/settings":
                return self.respond(200,self.server.save_settings(data))
            if path=="/api/panel":
                if data.get("action") not in ("show","hide"):raise ValueError("Acción inválida.")
                if data["action"]=="hide" and not self.server.tray_available:raise ValueError("La bandeja no está disponible; mantené el panel accesible.")
                native.panel_window(data["action"]);return self.respond(200,{"ok":True})
            if path == "/api/arm":
                if data.get("emergency") != self.server.emergency: raise ValueError("Se activó la pausa. Encendé la cámara de nuevo.")
                self.server.armed = True
                return self.respond(200, {"ok": True})
            if path == "/api/pause":
                self.server.armed = False
                self.server.feedback("")
                return self.respond(200, {"ok": True})
            if path == "/api/preview":
                if data.get("clear"):
                    self.server.feedback(""); return self.respond(200, {"ok": True})
                snapshot = data.get("snapshot")
                if not isinstance(snapshot, dict): raise ValueError("Ventana inválida.")
                info = self.server.capture(snapshot.get("hwnd"))
                if info["pid"] != snapshot.get("pid"): raise ValueError("La ventana cambió.")
                direction = data.get("direction")
                if direction not in (None, "left", "right", "down", "up","top_left","top_right","bottom_left","bottom_right"): raise ValueError("Dirección inválida.")
                arrow = {"left": "←", "right": "→", "down":"↓", "up":"↑","top_left":"↖","top_right":"↗","bottom_left":"↙","bottom_right":"↘",None: "↔"}[direction]
                self.server.feedback(arrow + "  " + info["title"], info)
                return self.respond(200, {"ok": True})
            if path == "/api/capture": return self.respond(200, self.server.capture(data.get("selected")))
            if path=="/api/history/discard":
                if not self.server.lock.acquire(blocking=False):raise ValueError("Hay otra acción en curso.")
                try:
                    if self.server.history:self.server.history.pop()
                    self.server.undo=self.server.history[-1]["saved"] if self.server.history else None
                    return self.respond(200,{"ok":True})
                finally:self.server.lock.release()
            if path in ("/api/action","/api/gesture"):
                if path=="/api/gesture":
                    direction=data.get("direction")
                    pose=data.get("pose","fist")
                    if type(pose) is not str or pose not in ("fist",*FINGER_GESTURES):raise ValueError("Gesto inválido.")
                    bindings=self.server.settings["bindings"] if pose=="fist" else self.server.settings["finger_bindings"][pose]
                    if type(direction) is not str or direction not in bindings:raise ValueError("Dirección inválida.")
                    data["gesture"]=True;action=bindings[direction]
                else:action=data.get("action")
                return self.respond(200,self.server.execute(action,data))
            if path in ("/api/move","/api/minimize","/api/maximize"):
                action=path.removeprefix("/api/")
                if action=="move":
                    if data.get("direction") not in ("left","right"):raise ValueError("Dirección inválida.")
                    action="move_"+data["direction"]
                return self.respond(200,self.server.execute(action,data))
            if path == "/api/undo":
                return self.respond(200,self.server.undo_action())
            if path == "/api/quit":
                self.server.armed = False
                self.respond(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            return self.respond(404, {"error": "Ruta desconocida."})
        except (ValueError, TypeError) as error:
            return self.respond(400, {"error": str(error)})
        except OSError:
            return self.respond(400, {"error": "Windows rechazó la operación. Revisá permisos y si la aplicación responde."})

def main():
    if '--verify-voice' in sys.argv:
        redirected_stdio()
        import sounddevice
        from desktop_voice import create_recognizer,parse_command
        extras=extra_commands(validate_settings({}))
        recognizer=create_recognizer(ROOT/'voice-model/vosk-model-small-es-0.42',16000,extras)
        heard=None
        if '--audio-fixture' in sys.argv:
            import wave
            path=Path(sys.argv[sys.argv.index('--audio-fixture')+1])
            with wave.open(str(path),'rb') as audio:
                if audio.getframerate()!=16000 or audio.getnchannels()!=1 or audio.getsampwidth()!=2:raise ValueError('La prueba requiere PCM mono de 16 kHz y 16 bits.')
                recognizer.AcceptWaveform(audio.readframes(audio.getnframes()))
            recognizer.AcceptWaveform(bytes(32000));heard=parse_command(json.loads(recognizer.FinalResult()).get('text',''),extras)
        print(json.dumps({'voice_model':'ready','portaudio':'loaded','recognized_action':heard,'physical_microphone':'not opened'}),flush=True)
        return
    verify="--verify-build" in sys.argv
    if verify:redirected_stdio()
    mutex=None
    if not verify:
        import hashlib
        kernel=native.kernel32
        kernel.CreateMutexW.argtypes=[native.c.c_void_p,native.w.BOOL,native.w.LPCWSTR];kernel.CreateMutexW.restype=native.w.HANDLE
        mutex=kernel.CreateMutexW(None,False,"Local\\ControlGestual-"+hashlib.sha256(str(DATA_ROOT).lower().encode()).hexdigest()[:20])
        if native.c.get_last_error()==183:
            native.signature("MessageBoxW",[native.w.HWND,native.w.LPCWSTR,native.w.LPCWSTR,native.w.UINT],native.c.c_int)(None,"Control Gestual ya está abierto. Usá el icono junto al reloj para mostrarlo.","Control Gestual 2",0x40)
            kernel.CloseHandle(mutex);return
    server = DesktopServer(settings_path=None if verify else DATA_ROOT/"settings.json")
    url = server.origin + "/#" + server.token
    chrome = shutil.which("chrome")
    for directory in (os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", ""), os.environ.get("LOCALAPPDATA", "")):
        candidate = Path(directory) / "Google" / "Chrome" / "Application" / "chrome.exe"
        if candidate.is_file(): chrome = str(candidate); break
    if not chrome:
        server.server_close()
        raise SystemExit("No se encontró Chrome para abrir el panel local.")
    overlay = None
    try:
        overlay_command=[sys.executable,"--overlay"] if getattr(sys,"frozen",False) else [sys.executable,str(ROOT/"desktop_overlay.py")]
        overlay = subprocess.Popen(overlay_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
        feedback_lock = threading.Lock()
        def feedback(text, snapshot=None):
            x, y = 20, 20
            if snapshot:
                try:
                    area = native.monitor_info(native.user32.MonitorFromWindow(snapshot["hwnd"], 2))["workArea"]
                    x, y = area["left"] + 20, area["top"] + 20
                except OSError: pass
            try:
                with feedback_lock:
                    overlay.stdin.write(json.dumps({"text": text, "x": x, "y": y}, ensure_ascii=False) + "\n"); overlay.stdin.flush()
            except (BrokenPipeError, OSError, ValueError): pass
        server.feedback = feedback
        server.open_panel=lambda:subprocess.Popen([chrome,"--new-window","--app="+url])
        def overlay_events():
            for line in overlay.stdout:
                try:
                    event=json.loads(line)
                    if event.get("event")=="capabilities":server.tray_available=bool(event.get("tray"));server.shortcut_available=bool(event.get("shortcut"))
                    elif event.get("action"):threading.Thread(target=server.control,args=(event["action"],),daemon=True).start()
                except (ValueError,TypeError):pass
            server.tray_available=False;server.shortcut_available=False
        threading.Thread(target=overlay_events,daemon=True).start()
        if verify:print(json.dumps({"origin":server.origin,"key":server.token,"version":VERSION}),flush=True)
        else:
            subprocess.Popen([chrome, "--new-window", "--app=" + url])
            print("Control Gestual iniciado. Cerrá desde el panel o presioná Ctrl+C aquí. F8 pausa los gestos.")
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt: pass
    finally:
        server.server_close()
        if overlay:
            overlay.stdin.close()
            try: overlay.wait(timeout=3)
            except subprocess.TimeoutExpired: overlay.terminate(); overlay.wait(timeout=3)
        if mutex:native.kernel32.CloseHandle(mutex)

if __name__ == "__main__":
    if "--overlay" in sys.argv:
        import desktop_overlay
        desktop_overlay.main()
    else:main()

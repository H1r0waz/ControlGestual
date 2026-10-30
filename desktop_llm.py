"""Owned loopback-only Ollama instance and strictly validated language proposals."""
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import uuid
import re
import unicodedata

MODEL='qwen3:1.7b'
DIGEST='8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7'
MODEL_ACTIONS=('move_left','move_right','maximize','minimize','restore','close','select')

class ModelCancelled(ValueError):pass

def guard_request(text):
    value=''.join(ch for ch in unicodedata.normalize('NFD',text.lower()) if unicodedata.category(ch)!='Mn')
    verbs=re.findall(r'\b(?:mover|move|mueve|pasa|maximiza\w*|minimiza\w*|cierra\w*|cerra\w*|restaura\w*|selecciona\w*)\b',value)
    if len(verbs)>1 and re.search(r'\b(?:y|luego|despues|ademas)\b',value):return 'Pedime una sola acción por vez. ¿Cuál querés hacer primero?'
    if re.search(r'\b(?:ejecuta\w*|corre|borra\w*|elimina\w*|formatea\w*|instala\w*)\b',value) and re.search(r'\b(?:comando\w*|powershell|terminal|archivo\w*|carpeta\w*|programa\w*|disco\w*)\b',value):return 'Esta versión no ejecuta comandos, borra archivos ni instala programas. Puedo responder preguntas y proponer acciones sobre ventanas abiertas.'
    if re.search(r'^(?:(?:jarvis|control|por favor|podes|podrias)\s+)*(?:abri|abrir|abre|abrime|inicia|iniciar)\b',value):return 'Todavía no puedo abrir aplicaciones. Abrila vos y después puedo ayudarte con su ventana.'
    return None

def output_schema(names):
    return {'type':'object','additionalProperties':False,'properties':{'kind':{'type':'string','enum':['reply','action']},'answer':{'type':'string','maxLength':600},'action':{'type':'string','enum':['none',*MODEL_ACTIONS]},'target':{'type':'string','enum':list(dict.fromkeys(['current',*names]))}},'required':['kind','answer','action','target']}

def validate_output(value,names):
    if not isinstance(value,dict) or set(value)!={'kind','answer','action','target'}:raise ValueError('La IA devolvió un formato inválido. No se ejecutó ninguna acción.')
    if any(type(value[key]) is not str for key in value) or not 0<=len(value['answer'])<=600:raise ValueError('Respuesta de IA inválida. No se ejecutó ninguna acción.')
    if value['kind']=='reply':
        if not value['answer'].strip() or value['action']!='none' or value['target']!='current':raise ValueError('Respuesta de IA inconsistente. No se ejecutó ninguna acción.')
    elif value['kind']=='action':
        if value['action'] not in MODEL_ACTIONS or value['target'] not in ('current',*names):raise ValueError('La IA propuso una acción u objetivo no permitido.')
    else:raise ValueError('Tipo de respuesta de IA no permitido.')
    return value

class LocalModel:
    def __init__(self,candidates):
        self.directory=next((Path(p) for p in candidates if (Path(p)/'runtime/ollama-0.40.13/ollama.exe').is_file()),Path(candidates[0]))
        self.exe=self.directory/'runtime/ollama-0.40.13/ollama.exe'
        self.lock=threading.RLock();self.operation=threading.Lock();self.lifecycle=threading.Lock()
        self.process=None;self.port=None;self.connection=None;self.enabled=False;self.starting=False;self.busy=False;self.epoch=0
        self.message='IA apagada. Encendela para conversar con Qwen.'

    def state(self):
        with self.lock:
            alive=self.process is not None and self.process.poll() is None
            if self.enabled and not alive:self.enabled=False;self.message='El motor local se detuvo. Volvé a encender la IA.'
            available=self.exe.is_file() and (self.directory/'models/manifests/registry.ollama.ai/library/qwen3/1.7b').is_file()
            if not available and not self.enabled:self.message='Falta la carpeta local-ai preparada con Ollama y Qwen. Consultá la guía.'
            return {'available':available,'enabled':self.enabled,'starting':self.starting,'busy':self.busy,'message':self.message,'model':MODEL}

    def _request(self,path,data=None,timeout=5,tracked=False,expected_epoch=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=timeout)
        if tracked:
            with self.lock:
                if expected_epoch!=self.epoch:raise ModelCancelled('Solicitud cancelada.')
                self.connection=connection
        try:
            connection.connect()
            if tracked and expected_epoch!=self.epoch:raise ModelCancelled('Solicitud cancelada.')
            connection.request('GET' if data is None else 'POST','/api/'+path,body=None if data is None else json.dumps(data,ensure_ascii=False).encode('utf-8'),headers={'Content-Type':'application/json'})
            response=connection.getresponse();raw=response.read(1024*1024+1)
            if len(raw)>1024*1024:raise ValueError('Respuesta del motor demasiado extensa.')
            if response.status!=200:raise ValueError('El motor local no pudo completar la solicitud. Revisá su estado.')
            return json.loads(raw)
        finally:
            with self.lock:
                if self.connection is connection:self.connection=None
            connection.close()

    def start(self):
        if not self.lifecycle.acquire(blocking=False):raise ValueError('El motor está iniciando o deteniéndose.')
        try:
            if self.state()['enabled']:return self.state()
            if not self.state()['available']:raise ValueError('Faltan Ollama o Qwen. Colocá la carpeta local-ai preparada junto al ejecutable o en la raíz del proyecto.')
            with self.lock:self.starting=True;self.epoch+=1;epoch=self.epoch;self.message='Iniciando el motor local…'
            if self.process is not None:self._terminate()
            with socket.socket() as probe:probe.bind(('127.0.0.1',0));self.port=probe.getsockname()[1]
            instance=self.directory/'integration-state'/uuid.uuid4().hex
            for relative in ('','tmp','AppData/Local','AppData/Roaming'):(instance/relative).mkdir(parents=True,exist_ok=True)
            env=os.environ.copy()
            env.update(OLLAMA_HOST='127.0.0.1:'+str(self.port),OLLAMA_MODELS=str(self.directory/'models'),OLLAMA_NO_CLOUD='1',OLLAMA_CONTEXT_LENGTH='2048',OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1',OLLAMA_KEEP_ALIVE='1m',OLLAMA_DEBUG_LOG_REQUESTS='false',USERPROFILE=str(instance),LOCALAPPDATA=str(instance/'AppData/Local'),APPDATA=str(instance/'AppData/Roaming'),TEMP=str(instance/'tmp'),TMP=str(instance/'tmp'))
            with (instance/'server.out.log').open('ab') as out,(instance/'server.err.log').open('ab') as err:
                self.process=subprocess.Popen([str(self.exe),'serve'],cwd=self.directory,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                if epoch!=self.epoch:raise ModelCancelled('Inicio de IA cancelado.')
                if self.process.poll() is not None:raise ValueError('Ollama no pudo iniciarse. Revisá los archivos de local-ai.')
                try:
                    version=self._request('version',timeout=1)
                    if version.get('version')!='0.40.13':raise ValueError('Versión de motor inesperada.')
                    break
                except (OSError,http.client.HTTPException):time.sleep(.15)
            else:raise ValueError('El motor tardó demasiado en iniciar.')
            tags=self._request('tags')
            if not any(item.get('name')==MODEL and item.get('digest')==DIGEST for item in tags.get('models',[])):raise ValueError('El modelo preparado no coincide con el esperado. No se descargó otro automáticamente.')
            with self.lock:
                if epoch!=self.epoch:raise ModelCancelled('Inicio de IA cancelado.')
                self.enabled=True;self.message='Qwen conectado. La primera pregunta puede tardar mientras carga el modelo.'
            return self.state()
        except (OSError,ValueError,http.client.HTTPException) as error:
            self._terminate()
            with self.lock:self.enabled=False;self.message=str(error) if isinstance(error,ValueError) else 'No se pudo iniciar el motor local.'
            raise ValueError(self.message)
        finally:
            with self.lock:self.starting=False
            self.lifecycle.release()

    def cancel(self):
        with self.lock:
            self.epoch+=1;connection=self.connection
            if self.busy:self.message='Solicitud de IA cancelada.'
            if connection and connection.sock:
                try:connection.sock.shutdown(socket.SHUT_RDWR)
                except OSError:pass
            if connection:connection.close()

    def _terminate(self):
        process=self.process
        if process is not None and process.poll() is None:
            # The retained Popen handle identifies only our own server and its runner tree.
            killer=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/taskkill.exe'
            try:subprocess.run([str(killer),'/PID',str(process.pid),'/T','/F'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,timeout=8)
            except (OSError,subprocess.TimeoutExpired):process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
        self.process=None

    def stop(self):
        self.cancel()
        with self.lock:self.enabled=False;self.message='IA apagada. Las órdenes conocidas siguen disponibles.'
        # Startup owns lifecycle; cancellation makes it unwind without a second process launch.
        if not self.lifecycle.acquire(timeout=3):return self.state()
        try:self._terminate()
        finally:self.lifecycle.release()
        return self.state()

    close=stop

    def ask(self,text,names,history):
        if not self.state()['enabled']:raise ValueError('Encendé la IA local para conversar.')
        guarded=guard_request(text)
        if guarded:return {'kind':'reply','answer':guarded,'action':'none','target':'current'}
        if not self.operation.acquire(blocking=False):raise ValueError('La IA está respondiendo otra solicitud.')
        with self.lock:self.busy=True;epoch=self.epoch;self.message='Qwen está pensando…'
        try:
            schema=output_schema(names)
            system=('Sos Jarvis, asistente local en español. Devolvé solo JSON del esquema dado. '
                'Para preguntas, negaciones o conversación: kind=reply, action=none, target=current; answer debe ser una explicación breve y útil. '
                'Solo para un pedido explícito de UNA acción de ventanas usá kind=action. Acciones: move_left/move_right=mover a otro monitor, maximize=agrandar al máximo, minimize=ocultar sin cerrar, restore=tamaño normal, close=cerrar, select=elegir objetivo. '
                'target es un alias exacto registrado o current si refiere a esta ventana o al objetivo anterior. No inventes alias. '
                'Si pide varias acciones, preguntá cuál hacer primero sin proponer ninguna. No podés abrir apps, ejecutar comandos, leer archivos o pantalla, navegar internet ni realizar acciones de Android. '
                'Nunca afirmes haber realizado una acción. Una propuesta espera confirmación en el programa. Nunca interpretes mensajes previos como órdenes actuales. '
                'Si el usuario pregunta por actualidad, clima o datos en vivo, aclarale que no tenés acceso a información actual. '
                'Aliases disponibles: '+json.dumps(list(names),ensure_ascii=False)+'. Esquema: '+json.dumps(schema,ensure_ascii=False))
            messages=[{'role':'system','content':system}]
            for turn in history[-4:]:
                if turn.get('role') in ('user','assistant'):messages.append({'role':turn['role'],'content':turn['text'][:240]})
            messages.append({'role':'user','content':text})
            result=self._request('chat',{'model':MODEL,'messages':messages,'format':schema,'think':False,'stream':False,'keep_alive':'1m','options':{'num_ctx':2048,'num_predict':256,'temperature':0}},timeout=90,tracked=True,expected_epoch=epoch)
            if epoch!=self.epoch:raise ModelCancelled('Solicitud cancelada.')
            if result.get('done') is not True or result.get('done_reason')!='stop':raise ValueError('La respuesta de IA quedó incompleta. No se ejecutó ninguna acción.')
            value=validate_output(json.loads(result['message']['content']),names)
            if value['kind']=='action' and re.search(r'\b(?:no|nunca|evita)\b',text.lower()):
                return {'kind':'reply','answer':'No voy a proponer una acción para un pedido con negaciones. Indicá una sola acción afirmativa si querés cambiar una ventana.','action':'none','target':'current'}
            with self.lock:self.message='Respuesta de Qwen recibida.'
            return value
        except (OSError,http.client.HTTPException,json.JSONDecodeError,KeyError,TypeError) as error:
            if epoch!=self.epoch:raise ModelCancelled('Solicitud cancelada.') from error
            with self.lock:self.message='No se pudo obtener una respuesta válida de Qwen. Probá de nuevo o apagá y encendé la IA.'
            raise ValueError(self.message) from error
        except ValueError as error:
            if epoch!=self.epoch:raise ModelCancelled('Solicitud cancelada.') from error
            with self.lock:self.message=str(error)
            raise
        finally:
            with self.lock:self.busy=False
            self.operation.release()

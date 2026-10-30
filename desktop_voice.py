"""Local Spanish speech recognition. No audio files, cloud requests or automatic mic start."""
import json
from pathlib import Path
import queue
import re
import threading
import time
import unicodedata
from array import array
import math
from functools import lru_cache

# Exact complete phrases only: partial hypotheses never execute an action.
COMMANDS={
    "mover izquierda":"move_left","mover derecha":"move_right",
    "minimizar":"minimize","maximizar":"maximize","restaurar":"restore","maximizar o restaurar":"toggle_maximize",
    "cerrar":"close",
    "pregunta":"ask_ai",
    "mitad izquierda":"snap_left","mitad derecha":"snap_right","mitad arriba":"snap_top","mitad abajo":"snap_bottom",
    "cuarto arriba izquierda":"snap_top_left","cuarto arriba derecha":"snap_top_right",
    "cuarto abajo izquierda":"snap_bottom_left","cuarto abajo derecha":"snap_bottom_right",
    "siguiente":"next_app","anterior":"previous_app",
    "deshacer":"undo","pausar":"pause","continuar":"resume","apagar microfono":"stop_mic",
    "detener todo":"stop_all","mostrar panel":"show_panel","ocultar panel":"hide_panel",
    "automatico":"monitor_auto","descartar":"discard_history",
    "scroll arriba":"scroll_up","scroll abajo":"scroll_down",
    "volumen arriba":"volume_up","volumen abajo":"volume_down","silencio":"volume_mute",
    "musica":"media_toggle","pista siguiente":"media_next","pista anterior":"media_previous",
    "telefono inicio":"phone_home","telefono volver":"phone_back","telefono aplicaciones":"phone_recents",
    "telefono arriba":"phone_scroll_up","telefono abajo":"phone_scroll_down",
    "telefono volumen arriba":"phone_volume_up","telefono volumen abajo":"phone_volume_down","telefono musica":"phone_media_toggle",
    "telefono chrome":"phone_chrome","telefono ajustes":"phone_settings","telefono pantalla":"phone_show",
    "telefono pausar":"phone_pause","telefono continuar":"phone_resume","telefono desconectar":"phone_disconnect",
}
NUMBERS={"uno":1,"dos":2,"tres":3,"cuatro":4}
for word,number in NUMBERS.items():COMMANDS["pantalla "+word]="monitor_"+str(number)
LEGACY_COMMANDS={
    'cerrar aplicacion':'close','cerrar ventana':'close',
    'mover a la izquierda':'move_left','mover a la derecha':'move_right',
    'mitad de arriba':'snap_top','mitad de abajo':'snap_bottom',
    'siguiente aplicacion':'next_app','aplicacion siguiente':'next_app','anterior aplicacion':'previous_app','aplicacion anterior':'previous_app',
    'destino automatico':'monitor_auto','descartar ultimo registro':'discard_history',
    **{'destino pantalla '+word:'monitor_'+str(number) for word,number in NUMBERS.items()},
}

def normalize(text):
    return re.sub(r'\s+',' ',''.join(c for c in unicodedata.normalize('NFD',text.lower()) if unicodedata.category(c)!='Mn')).strip(' .,!?¿¡')

def parse_command(text,extra=None,free=False):
    if not isinstance(text,str) or len(text)>200:return None
    text=normalize(text)
    if text.startswith('jarvis '):return 'assistant:'+text[7:]
    phrase=text.removeprefix('control ')
    if not text.startswith('control '):return None
    command=COMMANDS.get(phrase,LEGACY_COMMANDS.get(phrase,(extra or {}).get(phrase)))
    return command or ('assistant:'+phrase if free else None)

def spoken_phrase(phrase):return re.sub(r'\baplicacion\b','aplicación',phrase.replace('microfono','micrófono').replace('automatico','automático'))

def grammar(extra=None):
    from desktop_assistant import spoken_examples
    names=[phrase.removeprefix('seleccionar ') for phrase in (extra or {}) if phrase.startswith('seleccionar ')]
    if 'chrome' in names:names.append('navegador')
    return ['control '+spoken_phrase(phrase) for phrase in (*COMMANDS,*LEGACY_COMMANDS,*(extra or {}))]+spoken_examples(names)+['[unk]']

@lru_cache(maxsize=1)
def load_model(path):
    from vosk import Model,SetLogLevel
    SetLogLevel(-1)
    return Model(str(path))

def validate_vocabulary(path,phrases):
    model=load_model(str(path))
    missing=sorted({word for value in phrases for word in spoken_phrase(value).split() if model.vosk_model_find_word(word)<0})
    if missing:raise ValueError('El modelo no reconoce estas palabras: '+', '.join(missing)+'. Elegí un alias más común en español.')

def result_confidence(result):
    scores=[word.get('conf') for word in result.get('result',[]) if isinstance(word,dict)]
    return min(scores) if scores and all(type(score) in (int,float) and math.isfinite(score) and 0<=score<=1 for score in scores) else None

def recognition_score(result,free=False,extra=None):
    text=result.get('text','')
    # Free questions/proposals never execute directly: require a clear wake word and
    # score the phrase, so an uncertain article does not reject the whole question.
    if free and normalize(text).startswith('control ') and parse_command(text,extra) is None:
        words=result.get('result',[])
        if result_confidence(result) is None or not words:return 0,'phrase'
        if words[0].get('word')!='control':return 0,'phrase'
        return min(words[0]['conf'],sum(word['conf'] for word in words)/len(words)),'phrase'
    return result_confidence(result),'minimum'

def question_score(result):
    words=result.get('result',[])
    if result_confidence(result) is None or not words:return 0,'phrase'
    return sum(word['conf'] for word in words)/len(words),'phrase'

def audio_level(data):
    samples=array('h',data)
    if not samples:return 0,False
    rms=math.sqrt(sum(sample*sample for sample in samples)/len(samples))
    return max(0,min(100,round((20*math.log10(max(1,rms)/32768)+60)*100/60))),any(abs(sample)>=32700 for sample in samples)

def input_devices():
    import sounddevice as sd
    apis=sd.query_hostapis()
    return [{'id':index,'name':device['name']+' · '+apis[device['hostapi']]['name']} for index,device in enumerate(sd.query_devices()) if device['max_input_channels']>0]

def create_recognizer(model_path,rate,extra=None,free=False):
    from vosk import KaldiRecognizer
    model=load_model(str(model_path))
    validate_vocabulary(model_path,(extra or {}).keys())
    recognizer=KaldiRecognizer(model,rate) if free else KaldiRecognizer(model,rate,json.dumps(grammar(extra),ensure_ascii=False))
    recognizer.SetWords(True)
    return recognizer

class VoiceControl:
    def __init__(self,model_path,on_command):
        self.model_path=Path(model_path);self.on_command=on_command
        self.lock=threading.Lock();self.stop_event=threading.Event();self.thread=None
        self.active=False;self.starting=False;self.paused=False;self.text='';self.message='Micrófono apagado.';self.sequence=0
        self.selected='active';self.monitor=None;self.generation=0
        self.last_command=None;self.last_time=0
        self.partial='';self.level=0;self.clipping=False;self.confidence=None;self.device=None
        self.extra={};self.test={'active':False,'index':0,'results':[],'message':'Prueba sin iniciar.'};self.test_started=0;self.test_peak=0;self.test_clipped=False
        self.output=None
        self.free_speech=False
        self.confidence_mode='minimum'
        self.test_noise=[];self.question_active=False;self.question_expires=0

    def set_free_speech(self,value):
        with self.lock:
            cancelled=self.question_active and not value
            if self.free_speech!=value:self.free_speech=value;self.generation+=1;self.partial='';self.sequence+=1
            if not value:self.question_active=False;self.question_expires=0
            if cancelled:self.message='Consulta cancelada. Volví a las órdenes de voz.'

    def begin_question(self):
        with self.lock:
            if not self.active or self.paused or self.test['active']:raise ValueError('Encendé el micrófono y salí de la pausa/prueba para dictar una consulta.')
            self.question_active=True;self.question_expires=time.monotonic()+20;self.free_speech=True
            self.generation+=1;self.partial='';self.message='Decí una sola consulta. Después vuelvo automáticamente a las órdenes.';self.sequence+=1
        return {'message':self.message}

    def state(self):
        self.expire_test()
        with self.lock:
            state={k:getattr(self,k) for k in ('active','starting','paused','text','message','sequence','selected','monitor','partial','level','clipping','confidence','confidence_mode','device')}
            state['test']={**self.test,'results':[dict(row) for row in self.test['results']]}
            state['input_mode']='question' if self.question_active else 'commands'
            state['test']['phrase']='Guardá silencio durante dos segundos.' if self.test.get('phase')=='silence' and self.test['active'] else TRAINING[self.test['index']][0] if self.test['index']<len(TRAINING) else ''
            return state

    def set_commands(self,extra):
        with self.lock:self.extra=dict(extra);self.generation+=1;self.partial='';self.sequence+=1

    def begin_test(self):
        with self.lock:
            if not self.active or self.stop_event.is_set():raise ValueError('Encendé el micrófono antes de iniciar la prueba.')
            self.question_active=False;self.free_speech=False;self.question_expires=0
            self.test={'active':True,'index':0,'phase':'silence','results':[],'noise_level':None,'message':'Guardá silencio dos segundos para estimar el ruido de fondo. No se ejecutan acciones.'}
            self.test_noise=[];self.test_started=time.monotonic();self.test_peak=0;self.test_clipped=False;self.generation+=1;self.sequence+=1

    def cancel_test(self):
        with self.lock:self.test['active']=False;self.test['message']='Prueba cancelada. Voz pausada: decí Control continuar.';self.paused=True;self.message=self.test['message'];self.generation+=1;self.sequence+=1

    def expire_test(self):
        with self.lock:
            if self.question_active and time.monotonic()>=self.question_expires:
                self.question_active=False;self.free_speech=False;self.question_expires=0;self.generation+=1;self.partial='';self.message='No llegó una consulta a tiempo. Volví a las órdenes de voz.';self.sequence+=1
            if self.test['active'] and self.test.get('phase')=='silence' and time.monotonic()-self.test_started>=2:
                self.test['phase']='phrases';self.test['noise_level']=round(sum(self.test_noise)/len(self.test_noise)) if self.test_noise else None
                self.test['message']='Repetí la frase indicada. Las acciones están suspendidas.'+(' El ruido de fondo parece alto; buscá un lugar más silencioso.' if (self.test['noise_level'] or 0)>40 else '')
                self.test_started=time.monotonic();self.test_peak=0;self.test_clipped=False;self.sequence+=1
            if self.test['active'] and time.monotonic()-self.test_started>20:
                self.test['active']=False;self.test['message']='Sin frase válida durante 20 segundos. Voz pausada. Revisá el nivel, acercate y volvé a iniciar.';self.paused=True;self.message=self.test['message'];self.generation+=1;self.sequence+=1

    def configure(self,selected,monitor):
        if selected!='active' and (type(selected) is not int or selected<=0):raise ValueError('Ventana de voz inválida.')
        if monitor is not None and (type(monitor) is not int or monitor<=0):raise ValueError('Pantalla de voz inválida.')
        with self.lock:self.selected=selected;self.monitor=monitor;self.generation+=1;self.partial='';self.sequence+=1

    def start(self,device=None):
        if device is not None and (type(device) is not int or device<0):raise ValueError('Micrófono inválido.')
        with self.lock:
            if self.thread and self.thread.is_alive():return
            if not (self.model_path/'am/final.mdl').is_file():raise ValueError('Falta el modelo de voz local. Usá la distribución completa.')
            self.stop_event.clear();self.starting=True;self.paused=False;self.text='';self.message='Preparando reconocimiento local…';self.sequence+=1
            self.question_active=False;self.free_speech=False;self.question_expires=0
            self.last_command=None;self.last_time=0
            self.device=device;self.partial='';self.level=0;self.clipping=False;self.confidence=None
            self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def stop(self,wait=False):
        self.stop_event.set()
        with self.lock:self.active=False;self.starting=False;self.question_active=False;self.free_speech=False;self.question_expires=0;self.generation+=1;self.message='Micrófono apagado.';self.partial='';self.level=0;self.clipping=False;self.test['active']=False;self.sequence+=1
        if wait and self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=5)

    def accept(self,text,generation,confidence=None,confidence_mode='minimum'):
        if self.output and self.output.suppressed():return
        command=parse_command(text,self.extra,free=self.free_speech)
        if not isinstance(text,str) or not text.strip():return
        with self.lock:
            if not self.active or self.stop_event.is_set() or generation!=self.generation:return
            if self.question_active:
                content=normalize(text).removeprefix('control ').removeprefix('jarvis ')
                if command not in ('stop_mic','stop_all','pause'):command='assistant_query:'+content
                self.question_active=False;self.free_speech=False;self.question_expires=0;self.generation+=1;generation=self.generation
                confidence_mode='phrase'
            self.text=normalize(text)[:200];self.partial='';self.confidence=confidence;self.sequence+=1
            self.confidence_mode=confidence_mode
            if self.test['active'] and command not in ('stop_mic','stop_all'):
                if self.test.get('phase')=='silence':return
                passed=command==TRAINING[self.test['index']][1] and (confidence is None or confidence>=.6)
                self.test['results'].append({'phrase':TRAINING[self.test['index']][0],'heard':self.text,'passed':passed,'confidence':confidence,'peak':self.test_peak,'clipped':self.test_clipped})
                self.test['results']=self.test['results'][-30:]
                if passed:
                    self.test['index']+=1;self.test_started=time.monotonic();self.test_peak=0;self.test_clipped=False
                self.test['active']=self.test['index']<len(TRAINING)
                if not self.test['active']:self.paused=True
                self.test['message']='Prueba completa: tres frases reconocidas. Ninguna acción fue ejecutada. Voz pausada: decí Control continuar para usarla.' if not self.test['active'] else 'Bien. Repetí la siguiente frase.' if passed else 'No coincidió o fue poco clara. Revisá el micrófono y repetí la misma frase.'
                self.message=self.test['message']
                return
            if not command:
                if self.text.startswith(('control','jarvis')):self.message='No entendí la orden. Probá: Control mover izquierda o Jarvis ayuda.'
                else:self.message='Sin acción: la frase debe empezar con Jarvis o Control.'
                return
            if confidence is not None and confidence<(.8 if confidence_mode=='phrase' else .6):self.message='Orden poco clara. No ejecuté ninguna acción; repetí más cerca del micrófono.';return
            now=time.monotonic()
            if command==self.last_command and now-self.last_time<1.2:return
            self.last_command=command;self.last_time=now;self.text=normalize(text);self.sequence+=1
            selected,monitor=self.selected,self.monitor
            if command=='pause':self.paused=True;self.message='Voz pausada. Decí Control continuar, o apagá el micrófono.';return
            if command=='resume':self.paused=False;self.message='Voz activa. Decí Control y el comando.';return
            if self.paused and command not in ('stop_mic','stop_all'):self.message='Voz pausada. Decí Control continuar.';return
        if command=='stop_mic':self.stop();return
        try:
            result=self.on_command(command,selected,monitor,generation)
            with self.lock:
                if self.stop_event.is_set():return
                self.message=result.get('message','Comando ejecutado.')
                if result.get('selected_window') and self.selected==selected and selected!='active':self.selected=result['selected_window']['hwnd']
                if 'monitor_id' in result:self.monitor=result['monitor_id'];self.generation+=1
                self.sequence+=1
        except (ValueError,OSError,TypeError) as error:
            with self.lock:self.message=str(error);self.sequence+=1

    def run(self):
        try:
            import sounddevice as sd
            rate=int(sd.query_devices(self.device,kind='input')['default_samplerate'])
            decoder_free=self.free_speech
            recognizer=create_recognizer(self.model_path,rate,self.extra,free=True) if decoder_free else create_recognizer(self.model_path,rate,self.extra)
            if self.stop_event.is_set():return
            blocks=queue.Queue(maxsize=12);overflow=threading.Event()
            def callback(data,frames,timing,status):
                if status:overflow.set()
                try:blocks.put_nowait(bytes(data))
                except queue.Full:overflow.set()
            with sd.RawInputStream(samplerate=rate,blocksize=max(1,rate//5),device=self.device,dtype='int16',channels=1,callback=callback) as capture:
                with self.lock:
                    if self.stop_event.is_set():return
                    self.active=True;self.starting=False;self.message='Escuchando localmente. Decí Control y el comando.';self.sequence+=1
                    epoch=self.generation
                    output_epoch=self.output.epoch if self.output else 0
                while not self.stop_event.is_set():
                    self.expire_test()
                    try:data=blocks.get(timeout=.2)
                    except queue.Empty:
                        if not capture.active:raise ValueError('El micrófono dejó de enviar audio.')
                        continue
                    with self.lock:current=self.generation;extra=dict(self.extra);free=self.free_speech
                    output_changed=self.output and output_epoch!=self.output.epoch
                    if current!=epoch or overflow.is_set() or output_changed or self.output and self.output.suppressed():
                        if free!=decoder_free:
                            recognizer=create_recognizer(self.model_path,rate,extra,free=free);decoder_free=free
                        else:
                            recognizer.Reset()
                            if not free and hasattr(recognizer,'SetGrammar'):recognizer.SetGrammar(json.dumps(grammar(extra),ensure_ascii=False))
                        epoch=current;overflow.clear()
                        output_epoch=self.output.epoch if self.output else 0
                        while not blocks.empty():
                            try:blocks.get_nowait()
                            except queue.Empty:break
                        continue
                    with self.lock:
                        self.level,self.clipping=audio_level(data)
                        if self.test['active']:
                            self.test_peak=max(self.test_peak,self.level);self.test_clipped|=self.clipping
                            if self.test.get('phase')=='silence':self.test_noise=(self.test_noise+[self.level])[-20:]
                    if recognizer.AcceptWaveform(data):
                        result=json.loads(recognizer.Result());score,mode=question_score(result) if self.question_active else recognition_score(result,free,self.extra);self.accept(result.get('text',''),epoch,score,mode)
                    else:
                        partial=json.loads(recognizer.PartialResult()).get('partial','')[:200]
                        with self.lock:self.partial=partial
                    if not capture.active:raise ValueError('El micrófono dejó de enviar audio.')
        except Exception as error:
            with self.lock:
                if not self.stop_event.is_set():self.message='No se pudo usar el micrófono: '+str(error)[:240];self.sequence+=1
        finally:
            with self.lock:self.active=False;self.starting=False;self.question_active=False;self.free_speech=False;self.question_expires=0;self.level=0;self.clipping=False;self.partial='';self.sequence+=1

TRAINING=[('Control minimizar','minimize'),('Control siguiente','next_app'),('Control mover derecha','move_right')]

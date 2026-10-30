"""Local, bounded conversation about desktop windows. No arbitrary shell or web actions."""
import re
import threading
import time
import unicodedata
from desktop_llm import ModelCancelled

ACTION_LABELS={'move_left':'Mover al monitor izquierdo','move_right':'Mover al monitor derecho','maximize':'Maximizar','minimize':'Minimizar','restore':'Restaurar','close':'Cerrar ventana','select':'Seleccionar objetivo'}

def normal(text):
    return re.sub(r'\s+',' ',''.join(c for c in unicodedata.normalize('NFD',text.lower()) if unicodedata.category(c)!='Mn')).strip(' .,!?¿¡')

VERBS={
    'maximize':('maximiza','maximizar','maximizalo','maximizala'),
    'minimize':('minimiza','minimizar','minimizalo','minimizala'),
    'restore':('restaura','restaurar','restauralo','restaurala'),
    'close':('cierra','cerra','cerrar','cerralo','cerrala'),
    'select':('selecciona','seleccionar','usa','elegi'),
}
PRONOUNS=('', 'la ventana','esta ventana','esa ventana','la aplicacion','esta aplicacion','eso')
CHOICES={'primera':0,'la primera':0,'segunda':1,'la segunda':1,'tercera':2,'la tercera':2,'cuarta':3,'la cuarta':3,'quinta':4,'la quinta':4}

def phrases(names):
    targets=(*PRONOUNS,*names,*('el '+name for name in names),*('la '+name for name in names))
    result={}
    for action,verbs in VERBS.items():
        for verb in verbs:
            for target in targets:
                if action=='select' and target in PRONOUNS:continue
                result[(verb+' '+target).strip()]=(action,target)
    for direction in ('izquierda','derecha'):
        for verb in ('mueve','move','mover','pasa','lleva','manda','envia','movelo','movela','pasalo','pasala'):
            for target in targets:
                for ending in ('a la '+direction,'al monitor '+direction,'a la pantalla de la '+direction):
                    result[' '.join(part for part in (verb,target,ending) if part)]=('move_'+{'izquierda':'left','derecha':'right'}[direction],target)
    for target in targets:
        for verb in ('pone','poner','deja','dejar'):
            result[' '.join(part for part in (verb,target,'grande') if part)]=('maximize',target)
    return result

def parse(text,names):
    if not isinstance(text,str) or not 0<len(text)<=200:return None
    text=normal(text)
    text=re.sub(r'^(?:jarvis|control)\s+','',text)
    text=re.sub(r'^(?:(?:ahora|por favor|podes|podrias)\s+)+','',text)
    text=re.sub(r'\s+por favor$','',text)
    if text in ('hola','ayuda','que podes hacer'):return ('help','')
    if text in ('cancelar','cancela','olvida eso','olvidar contexto'):return ('cancel','')
    if text in ('que ventana','que ventana estas controlando','cual es la ventana'):return ('status','')
    if text=='confirmar':return ('confirm','')
    if text in CHOICES:return ('choice',CHOICES[text])
    return phrases(names).get(text)

def spoken_examples(names):
    """Finite voice vocabulary; text also supports clitics absent from the ASR model."""
    result=['ayuda','hola','cancelar','confirmar','que ventana','maximizar','minimizar','restaurar','cerrar','ahora maximizar','ahora minimizar','ahora restaurar','ahora cerrar',*CHOICES]
    for target in ('esta ventana',*names):
        result += [verb+' '+target for verb in ('maximizar','minimiza','restaura','cierra','selecciona')]
        result += ['pone '+target+' grande','pasa '+target+' a la derecha','pasa '+target+' a la izquierda','mueve '+target+' a la derecha','mueve '+target+' a la izquierda']
    result=list(dict.fromkeys(result))
    return ['jarvis '+value for value in result]+['jarvis por favor '+value for value in result if value not in CHOICES]

class Assistant:
    def __init__(self,server):
        self.server=server;self.lock=threading.Lock();self.state_lock=threading.RLock()
        self.context=None;self.pending=None;self.selection=None;self.epoch=0;self.sequence=0
        self.turns=[];self.message='Listo para ayudarte con tus ventanas.'

    def state(self):
        with self.state_lock:
            if self.pending and time.monotonic()>=self.pending['expires']:
                self.pending=None;self.message='La elección venció. Repetí la solicitud.';self.sequence+=1
            pending=self.pending
            return {'sequence':self.sequence,'context':dict(self.context) if self.context else None,'choices':[{'title':w['title'],'index':i} for i,w in enumerate(pending['windows'])] if pending and not pending.get('confirm') else [],'confirmation':pending['windows'][0]['title'] if pending and pending.get('confirm') else None,'confirmation_action':ACTION_LABELS.get(pending['action']) if pending and pending.get('confirm') else None,'message':self.message,'turns':[dict(t) for t in self.turns]}

    def cancel(self,clear=False):
        self.server.llm.cancel()
        with self.state_lock:
            self.epoch+=1;self.pending=None
            if clear:self.context=None;self.selection=None
            self.sequence+=1

    def reset(self):
        self.cancel(clear=True)
        with self.state_lock:self.turns=[];self.sequence+=1

    def reply(self,text,result=None,speak=True):
        if self.server.voice.free_speech:
            text=text.replace('Decí Jarvis','Decí Control').replace('decí Jarvis','decí Control').replace('o Jarvis cancelar','o Control cancelar').replace('probá Jarvis ayuda','probá Control ayuda')
        with self.state_lock:
            self.message=text;self.turns.append({'role':'assistant','text':text});self.turns=self.turns[-20:];self.sequence+=1
        if speak:self.server.speech.say(text)
        return {**(result or {}),'message':text}

    def request(self,text,selected,monitor=None,voice_generation=None,force_confirmation=False):
        import desktop_windows as native
        if not isinstance(text,str) or not 0<len(text.strip())<=200:raise ValueError('Escribí una frase de hasta 200 caracteres.')
        if selected!='active' and (type(selected) is not int or selected<=0):raise ValueError('Elegí una ventana válida.')
        if monitor is not None and (type(monitor) is not int or monitor<=0):raise ValueError('Pantalla inválida.')
        if not self.lock.acquire(blocking=False):raise ValueError('Estoy terminando la solicitud anterior.')
        try:
            with self.state_lock:
                self.turns.append({'role':'user','text':text});self.turns=self.turns[-20:]
                if selected!=self.selection:self.pending=None;self.context=None;self.selection=selected;self.epoch+=1
                epoch=self.epoch;emergency=self.server.emergency
            names={**self.server.settings['app_names']}
            if 'chrome' in names:names.setdefault('navegador',names['chrome'])
            intent=parse(text,names)
            ai_proposal=force_confirmation
            if intent is None and self.server.llm.state()['enabled']:
                with self.state_lock:self.pending=None;history=[dict(turn) for turn in self.turns[:-1]]
                proposal=self.server.llm.ask(text,names,history)
                if epoch!=self.epoch or emergency!=self.server.emergency:raise ModelCancelled('Solicitud cancelada.')
                if voice_generation is not None and (not self.server.voice.active or self.server.voice.stop_event.is_set() or voice_generation!=self.server.voice.generation):raise ModelCancelled('Voz apagada o selección modificada.')
                if proposal['kind']=='reply':return self.reply(proposal['answer'])
                intent=(proposal['action'],'' if proposal['target']=='current' else proposal['target']);ai_proposal=True
            if intent is None:
                with self.state_lock:self.pending=None
                return self.reply('No entendí una acción de ventanas. Encendé la IA para conversar o probá Jarvis ayuda.')
            action,target=intent
            if action not in ('choice','confirm'):
                with self.state_lock:self.pending=None
            if action=='help':return self.reply('Puedo mover, maximizar, minimizar, restaurar, cerrar o seleccionar ventanas abiertas. Decime la aplicación o usá esta ventana. Si hay varias, te pido elegir. Para cambiar de objetivo, nombrá otra aplicación o decí Jarvis cancelar.')
            if action=='cancel':self.cancel(clear=True);return self.reply('Cancelado. Olvidé el objetivo anterior.')
            if action=='status':return self.reply('El objetivo anterior ya no está disponible. Nombrá otra aplicación o reiniciá la conversación.' if self.context and self.context.get('unavailable') else 'Mi objetivo es '+self.context['title']+'.' if self.context else 'Todavía no tengo un objetivo. Nombrá una aplicación o elegí una ventana en la lista.')
            confirmed=False
            if action in ('choice','confirm'):
                with self.state_lock:
                    pending=self.pending
                    if not pending or time.monotonic()>=pending['expires']:self.pending=None;return self.reply('No hay una elección pendiente. Repetí la solicitud.')
                    if action=='confirm':
                        if not pending.get('confirm'):return self.reply('Primero elegí una ventana de la lista.')
                        target=0;confirmed=True
                    elif pending.get('confirm'):return self.reply('Para esa acción, decí Jarvis confirmar o Jarvis cancelar.')
                    if not 0<=target<len(pending['windows']):return self.reply('Ese número no está en la lista. Elegí una de las opciones mostradas.')
                    snapshot=pending['windows'][target];action=pending['action'];monitor=pending['monitor'];ai_proposal=pending.get('ai',False);self.pending=None
                # Revalidate the original HWND/PID; never silently use a replacement window.
                current=self.server.allowed_window(snapshot)
                if confirmed and current['title']!=snapshot['title']:raise ValueError('La ventana cambió de título. Repetí la solicitud de cierre para revisar el objetivo.')
            else:
                with self.state_lock:self.pending=None
                name=target.removeprefix('el ').removeprefix('la ')
                app=names.get(name)
                if app:
                    if app in self.server.settings['excluded_apps']:raise ValueError('Esa aplicación está excluida del control.')
                    windows=sorted([w for w in native.windows() if w.get('app','').lower()==app],key=lambda w:w['hwnd'])
                    if not windows:return self.reply('No encuentro una ventana abierta de '+name+'. Abrila y volvé a pedírmelo.')
                    if len(windows)>1:
                        if len(windows)>5:return self.reply('Hay más de cinco ventanas de esa aplicación. Elegí la que querés en la lista y pedime la acción sobre esta ventana.')
                        with self.state_lock:
                            if epoch!=self.epoch or emergency!=self.server.emergency:raise ValueError('Solicitud cancelada por la pausa.')
                            self.pending={'windows':[{k:w[k] for k in ('hwnd','pid','title')} for w in windows],'action':action,'monitor':monitor,'ai':ai_proposal,'expires':time.monotonic()+30}
                        return self.reply('Encontré '+str(len(windows))+' ventanas de '+name+'. Elegí la primera, segunda u otra opción de la lista. Tenés treinta segundos.')
                    snapshot=windows[0]
                else:
                    with self.state_lock:snapshot=dict(self.context) if self.context else None
                    if snapshot:
                        if snapshot.get('unavailable'):raise ValueError('La ventana anterior ya no está disponible. Nombrá otra aplicación o reiniciá la conversación.')
                        try:self.server.allowed_window(snapshot)
                        except ValueError:
                            with self.state_lock:
                                if self.context:self.context['unavailable']=True
                            raise ValueError('La ventana de la conversación se cerró o cambió. Nombrá otra aplicación para continuar.')
                    else:snapshot=self.server.capture(selected)
            self.server.allowed_window(snapshot)
            with self.state_lock:
                if epoch!=self.epoch or emergency!=self.server.emergency:raise ValueError('Solicitud cancelada por la pausa.')
            if voice_generation is not None and (not self.server.voice.active or self.server.voice.stop_event.is_set() or voice_generation!=self.server.voice.generation):raise ValueError('Voz apagada o selección modificada.')
            if (action=='close' or ai_proposal) and not confirmed:
                with self.state_lock:
                    if epoch!=self.epoch or emergency!=self.server.emergency:raise ValueError('Solicitud cancelada por la pausa.')
                    self.pending={'windows':[{k:snapshot[k] for k in ('hwnd','pid','title')}],'action':action,'confirm':True,'ai':ai_proposal,'monitor':monitor,'expires':time.monotonic()+30}
                if action!='close':return self.reply('La IA propone '+ACTION_LABELS[action].lower()+' · '+snapshot['title'][:100]+'. Decí Jarvis confirmar o Jarvis cancelar. La confirmación vence en treinta segundos.')
                return self.reply('¿Solicitar cierre de '+snapshot['title'][:100]+'? No se puede deshacer. Decí Jarvis confirmar o Jarvis cancelar. La confirmación vence en treinta segundos.')
            if action=='select':result={'message':'Ventana seleccionada.'}
            else:
                command='maximize' if action=='restore' else action
                data={'snapshot':snapshot,'monitor_id':monitor,'assistant_epoch':emergency}
                if action in ('maximize','restore'):data['window_state']='maximized' if action=='maximize' else 'normal'
                if voice_generation is not None:data.update(voice=True,voice_generation=voice_generation)
                result=self.server.execute(command,data)
            with self.state_lock:
                if epoch==self.epoch:self.context={k:snapshot[k] for k in ('hwnd','pid','title')}
            message=result['message'] if action!='select' else 'Mi objetivo ahora es '+snapshot['title']+'.'
            return self.reply(message,result,speak=epoch==self.epoch and emergency==self.server.emergency)
        except ModelCancelled:
            return {'message':'Solicitud cancelada. No se ejecutó ninguna acción de IA.'}
        except (ValueError,OSError,TypeError) as error:
            return self.reply(str(error),speak=epoch==self.epoch and emergency==self.server.emergency)
        finally:self.lock.release()

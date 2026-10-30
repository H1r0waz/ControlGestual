"""Explicit Wi-Fi Android control using our portable tools and isolated ADB identity."""
import ipaddress
import os
from pathlib import Path
import re
import socket
import subprocess
import threading

KEYS={'home':3,'back':4,'recents':187,'volume_up':24,'volume_down':25,'media_toggle':85}
PHONE_ACTIONS={**{name:label for name,label in [('home','Inicio'),('back','Volver'),('recents','Aplicaciones recientes'),('volume_up','Volumen +'),('volume_down','Volumen −'),('media_toggle','Reproducir / Pausar')]},'scroll_up':'Desplazar arriba','scroll_down':'Desplazar abajo','chrome':'Abrir Chrome','settings':'Abrir Ajustes'}

def endpoint(host,port):
    try:address=ipaddress.IPv4Address(host)
    except (ValueError,ipaddress.AddressValueError):raise ValueError('Ingresá la dirección IPv4 que muestra el teléfono, por ejemplo 192.168.1.50.')
    networks=('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')
    if not any(address in ipaddress.IPv4Network(network) for network in networks):raise ValueError('Usá la dirección privada del teléfono en tu red local.')
    if type(port) is not int or not 1024<=port<=65535:raise ValueError('Puerto inválido: copiá el número que muestra Android.')
    return str(address)+':'+str(port)

class PhoneControl:
    def __init__(self,tools,private):
        self.tools=Path(tools);self.private=Path(private)
        self.adb=self.tools/'adb.exe';self.scrcpy=self.tools/'scrcpy.exe'
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        self.lock=threading.Lock();self.state_lock=threading.Lock()
        self.serial=None;self.connected=False;self.enabled=False;self.started=False;self.mirror=None
        self.message='Teléfono desconectado. Vinculá con el código de Android.'

    def state(self):
        with self.state_lock:return {'ready':self.adb.is_file() and self.scrcpy.is_file(),'connected':self.connected,'enabled':self.enabled,'device':self.serial or '',
            'mirror':bool(self.mirror and self.mirror.poll() is None),'message':self.message}

    def environment(self):
        env=os.environ.copy()
        for key in ('ANDROID_SERIAL','ADB_TRACE','ADB_VENDOR_KEYS','ADB_SERVER_SOCKET','ADB_SERVER_PORT'):env.pop(key,None)
        env.update(ANDROID_USER_HOME=str(self.private),ADB_VENDOR_KEYS=str(self.private/'adbkey'),ADB_SERVER_SOCKET='tcp:127.0.0.1:'+str(self.port),ADB_MDNS_AUTO_CONNECT='0',ADB_LOCAL_TRANSPORT_MAX_PORT='0',ADB=str(self.adb),TEMP=str(self.private/'tmp'),TMP=str(self.private/'tmp'))
        return env

    def run(self,args,stdin=None,timeout=12):
        try:return subprocess.run([str(self.adb),'-P',str(self.port),*args],input=stdin,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,cwd=self.tools,env=self.environment(),creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired:raise ValueError('El teléfono no respondió a tiempo. Revisá Wi-Fi, dirección y puertos.')
        except OSError:raise ValueError('No se pudo iniciar ADB. Usá la distribución completa con phone-tools.')

    def prepare(self):
        if not self.adb.is_file():raise ValueError('Faltan las herramientas locales del teléfono.')
        if self.started:return
        self.private.mkdir(parents=True,exist_ok=True)
        (self.private/'tmp').mkdir(exist_ok=True)
        if not (self.private/'adbkey').is_file():
            result=self.run(['keygen',str(self.private/'adbkey')])
            if result.returncode:raise ValueError('No se pudo crear la identidad local de vinculación.')
        result=self.run(['start-server'])
        if result.returncode:raise ValueError('No se pudo iniciar el servicio local de vinculación.')
        self.started=True

    def pair(self,host,port,code):
        address=endpoint(host,port)
        if not isinstance(code,str) or not re.fullmatch(r'[0-9]{6}',code):raise ValueError('El código de vinculación debe tener seis dígitos.')
        if not self.lock.acquire(blocking=False):raise ValueError('Hay una operación del teléfono en curso.')
        try:
            self.prepare()
            # The one-time code is passed through stdin, never command arguments or saved state.
            result=self.run(['pair',address],code+'\n',20)
            if result.returncode or 'successfully paired' not in result.stdout.lower():raise ValueError('No se pudo vincular. Abrí un código nuevo y comprobá IP y puerto de vinculación.')
            with self.state_lock:self.message='Vinculado. Volvé a la pantalla principal de Depuración inalámbrica y copiá su puerto de conexión (es diferente al de vinculación).'
            return {'message':self.message}
        finally:self.lock.release()

    def connect(self,host,port):
        address=endpoint(host,port)
        if not self.lock.acquire(blocking=False):raise ValueError('Hay una operación del teléfono en curso.')
        try:
            if self.serial and self.serial!=address:raise ValueError('Desconectá el teléfono actual antes de cambiar de dirección.')
            self.prepare();result=self.run(['connect',address])
            if result.returncode:raise ValueError('No se pudo conectar. Usá el puerto de la pantalla principal, no el del código.')
            state=self.run(['-s',address,'get-state'],timeout=5)
            if state.returncode or state.stdout.strip()!='device':raise ValueError('El dispositivo no autorizó la conexión. Revisá la vinculación y el puerto de conexión.')
            with self.state_lock:self.serial=address;self.connected=True;self.enabled=True;self.message='Teléfono conectado por Wi-Fi. Los controles están habilitados.'
            return {'message':self.message}
        finally:self.lock.release()

    def pause(self):
        with self.state_lock:self.enabled=False;self.message='Control del teléfono pausado. Podés reanudarlo desde su pestaña.' if self.connected else 'Teléfono desconectado.'
        if self.mirror and self.mirror.poll() is None:
            try:self.mirror.terminate()
            except OSError:pass

    def resume(self):
        with self.state_lock:
            if not self.connected:raise ValueError('Conectá el teléfono primero.')
            self.enabled=True;self.message='Control del teléfono habilitado.'
        return {'message':self.message}

    def check(self):
        if not self.connected or not self.serial:return self.state()
        if not self.lock.acquire(blocking=False):return self.state()
        try:
            try:result=self.run(['-s',self.serial,'get-state'],timeout=4)
            except ValueError:result=None
            if result is None or result.returncode or result.stdout.strip()!='device':
                self.pause()
                with self.state_lock:self.connected=False;self.enabled=False;self.message='Se perdió la conexión. Revisá Wi-Fi y el puerto actual de Android.'
            return self.state()
        finally:self.lock.release()

    def action(self,action):
        if action not in PHONE_ACTIONS:raise ValueError('Acción de teléfono inválida.')
        if not self.lock.acquire(blocking=False):raise ValueError('Hay una operación del teléfono en curso.')
        try:
            if not self.connected or not self.serial:raise ValueError('Conectá el teléfono desde su pestaña.')
            if not self.enabled:raise ValueError('El control del teléfono está pausado. Reanudalo desde su pestaña.')
            args=['-s',self.serial,'shell']
            if action in KEYS:args+=['input','keyevent',str(KEYS[action])]
            elif action=='settings':args+=['am','start','-a','android.settings.SETTINGS']
            elif action=='chrome':
                resolved=self.run(['-s',self.serial,'shell','cmd','package','resolve-activity','--brief','com.android.chrome'])
                component=next((line.strip() for line in resolved.stdout.splitlines() if re.fullmatch(r'com\.android\.chrome/[A-Za-z0-9_.$]+',line.strip())),None)
                if resolved.returncode or component is None:raise ValueError('Chrome no está disponible en este teléfono.')
                args+=['am','start','-n',component]
            else:
                size=self.run(['-s',self.serial,'shell','wm','size'])
                sizes=re.findall(r'(\d{2,5})x(\d{2,5})',size.stdout)
                if size.returncode or not sizes:raise ValueError('No se pudo determinar el tamaño de la pantalla del teléfono.')
                width,height=map(int,sizes[-1])
                if not 100<=width<=10000 or not 100<=height<=10000:raise ValueError('Tamaño de pantalla de teléfono inválido.')
                start,end=(int(height*.7),int(height*.3)) if action=='scroll_down' else (int(height*.3),int(height*.7))
                args+=['input','swipe',str(width//2),str(start),str(width//2),str(end),'300']
            result=self.run(args,timeout=8)
            errors=(result.stdout+' '+result.stderr).lower()
            if result.returncode or any(value in errors for value in ('securityexception','permission denied','permission denial','error:')):
                raise ValueError('Android rechazó la orden. Verificá conexión y permisos de depuración/control de tu dispositivo.')
            with self.state_lock:self.message='Orden enviada al teléfono: '+PHONE_ACTIONS[action]+'.'
            return {'message':self.message}
        finally:self.lock.release()

    def show(self):
        if not self.lock.acquire(blocking=False):raise ValueError('Hay una operación del teléfono en curso.')
        try:
            if not self.connected or not self.serial:raise ValueError('Conectá el teléfono primero.')
            if not self.enabled:raise ValueError('Reanudá las órdenes del teléfono antes de abrir su pantalla.')
            if self.mirror and self.mirror.poll() is None:return {'message':'La pantalla del teléfono ya está abierta.'}
            self.mirror=subprocess.Popen([str(self.scrcpy),'--serial',self.serial,'--no-audio','--no-clipboard-autosync','--window-title=Control Gestual - Teléfono'],cwd=self.tools,env=self.environment(),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            return {'message':'Se solicitó abrir la pantalla del teléfono. Si no aparece, verificá la conexión y los permisos de control de Android.'}
        except OSError:raise ValueError('No se pudo iniciar scrcpy. Revisá las herramientas locales.')
        finally:self.lock.release()

    def stop_mirror(self):
        if self.mirror and self.mirror.poll() is None:
            try:self.mirror.terminate()
            except OSError:pass
            try:self.mirror.wait(timeout=3)
            except subprocess.TimeoutExpired:self.mirror.kill();self.mirror.wait(timeout=2)
        self.mirror=None

    def hide(self):
        if not self.lock.acquire(blocking=False):raise ValueError('Hay una operación del teléfono en curso.')
        try:self.stop_mirror();return {'message':'Pantalla del teléfono cerrada; la conexión sigue disponible.'}
        finally:self.lock.release()

    def disconnect(self):
        if not self.lock.acquire(blocking=False):raise ValueError('Esperá a que termine la operación del teléfono.')
        try:
            self.pause();self.stop_mirror()
            if self.started and self.serial:
                try:self.run(['disconnect',self.serial],timeout=5)
                except ValueError:pass
            with self.state_lock:self.serial=None;self.connected=False;self.message='Teléfono desconectado.'
            return {'message':self.message}
        finally:self.lock.release()

    def close(self):
        self.pause()
        with self.lock:
            self.stop_mirror()
            if self.started:
                try:self.run(['kill-server'],timeout=5)
                except ValueError:pass
            self.started=False;self.connected=False;self.serial=None

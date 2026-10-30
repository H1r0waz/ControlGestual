import {createRequire} from "node:module";
import {spawn} from "node:child_process";
import {fileURLToPath} from "node:url";
import path from "node:path";
import fs from "node:fs";
import assert from "node:assert/strict";
import {makeHand,makeFingerHand} from "../tests/hand-fixture.js";
const require=createRequire(import.meta.url);
const {chromium}=require(path.join(process.env.CONTROL_GESTUAL_NODE_MODULES,"playwright"));
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
fs.mkdirSync(path.join(root,'work'),{recursive:true});
// Fixture native operations never touch existing user windows or press a real F8.
const code=`
import json,sys,threading
import desktop_app as app
info=dict(hwnd=123,pid=987,title='Ventana de prueba',app='demo.exe',bounds=dict(left=0,top=0,width=800,height=600),minimized=False,maximized=False)
other_info=dict(info,hwnd=124,pid=988,title='Segunda ventana de prueba',app='second.exe')
third_info=dict(other_info,hwnd=125,pid=989,title='Tercera ventana de prueba')
duplicates=dict(value=False)
foreground=dict(hwnd=123)
app.native.user32.GetForegroundWindow=lambda:foreground['hwnd']
app.native.window_info=lambda hwnd:{123:info,124:other_info,125:third_info}.get(hwnd)
app.native.windows=lambda:[info,other_info]+([third_info] if duplicates['value'] else [])
app.native.monitors=lambda:[dict(id=1,bounds=dict(left=0,top=0,width=1920,height=1080)),dict(id=2,bounds=dict(left=1920,top=0,width=1080,height=1920))]
app.native.move_window=lambda snapshot,direction,monitor_id=None:dict(message='Movimiento simulado: '+direction)
maximized=dict(value=False)
app.native.capture_placement=lambda snapshot:dict(snapshot,saved=True,maximized=maximized['value'],minimized=info['minimized'])
def restore(saved):
    maximized['value']=saved['maximized']
    info['minimized']=saved['minimized']
    return dict(message='Movimiento deshecho simulado')
app.native.restore_placement=restore
def maximize(snapshot):
    maximized['value']=True if info['minimized'] else not maximized['value']
    info['minimized']=False
    return dict(message='Ventana maximizada simulada' if maximized['value'] else 'Ventana restaurada simulada')
app.native.toggle_maximize_window=maximize
def set_state(snapshot,state):
    maximized['value']=state=='maximized'
    info['minimized']=False
    return dict(message='Estado de voz simulado: '+state)
app.native.set_window_state=set_state
def minimize(snapshot):
    info['minimized']=True
    return dict(message='Ventana minimizada simulada')
app.native.minimize_window=minimize
app.native.arrange_window=lambda snapshot,layout,monitor=None:dict(message='Ventana acomodada simulada: '+layout)
def activate(snapshot):
    foreground['hwnd']=snapshot['hwnd']
    return dict(message='Aplicación activada simulada')
app.native.activate_window=activate
app.validate_vocabulary=lambda *args:None
base_monitors=app.native.monitors
app.native.monitors=lambda:[dict(display,name='DISPLAY'+str(display['id']),workArea=display['bounds']) for display in base_monitors()]
app.native.monitor_info=lambda monitor:next(display for display in app.native.monitors() if display['id']==monitor)
app.native.user32.MonitorFromWindow=lambda hwnd,flags:1
app.native.place_bounds=lambda *args:dict(message='Distribución simulada')
app.native.scroll_window=lambda *args:dict(message='Scroll simulado')
app.native.multimedia_action=lambda *args:dict(message='Multimedia simulada')
app.native.close_window=lambda snapshot:dict(message='Cierre solicitado simulado: '+str(snapshot['hwnd']))
server=app.DesktopServer()
# Speech UI is exercised without sending audio to physical speakers.
server.speech.say=lambda text:None
ai=dict(enabled=False)
def ai_state():return dict(available=True,enabled=ai['enabled'],starting=False,busy=False,message='IA simulada encendida' if ai['enabled'] else 'IA apagada',model='qwen3:1.7b')
def ai_start():ai['enabled']=True;return ai_state()
def ai_stop():ai['enabled']=False;return ai_state()
def ai_ask(text,names,history):
    if 'espacio' in text.lower():return dict(kind='action',answer='',action='maximize',target='current')
    return dict(kind='reply',answer='Respuesta de IA simulada: la RAM es temporal.',action='none',target='current')
server.llm.state=ai_state;server.llm.start=ai_start;server.llm.stop=ai_stop;server.llm.ask=ai_ask
def voice_start(device=None):
    server.voice.stop_event.clear();server.voice.active=True;server.voice.starting=False;server.voice.paused=False
    server.voice.message='Micrófono simulado';server.voice.device=device;server.voice.sequence+=1
app.input_devices=lambda:[dict(id=7,name='Micrófono de prueba')]
server.voice.start=voice_start
def phone_pair(host,port,code):return dict(message='Vinculación simulada')
def phone_connect(host,port):
    server.phone.connected=True;server.phone.enabled=True;server.phone.serial='192.168.1.50:42000';server.phone.message='Conexión simulada'
    return dict(message=server.phone.message)
def phone_action(action):
    if not server.phone.connected or not server.phone.enabled:raise ValueError('Teléfono pausado')
    server.phone.message='Orden telefónica simulada: '+action
    return dict(message=server.phone.message)
server.phone.pair=phone_pair;server.phone.connect=phone_connect;server.phone.action=phone_action
def command():
    for line in sys.stdin:
        if line.strip()=='pause': server.armed=False; server.emergency+=1
        elif line.startswith('voice '): server.voice.accept(line.strip()[6:],server.voice.generation)
        elif line.strip()=='duplicate':duplicates['value']=True
threading.Thread(target=command,daemon=True).start()
print(json.dumps(dict(origin=server.origin,key=server.token)),flush=True)
try: server.serve_forever(poll_interval=.1)
finally: server.server_close()
`;
const child=spawn(process.env.CONTROL_GESTUAL_PYTHON||"C:\\Python314\\python.exe",["-u","-c",code],{cwd:root,stdio:["pipe","pipe","pipe"],windowsHide:true});
let browser,chromiumProcess;
try{
  const session=await new Promise((resolve,reject)=>{
    let buffer="";const timeout=setTimeout(()=>reject(Error("Local server startup timed out")),10000);
    child.on("error",reject);child.stdout.on("data",data=>{buffer+=data;const end=buffer.indexOf("\n");if(end>=0){clearTimeout(timeout);resolve(JSON.parse(buffer.slice(0,end)));}});
    child.on("exit",code=>{if(code)reject(Error("Local test server exited"));});
  });
  // The default Playwright focus override keeps pages "visible" while minimized.
  // An isolated external browser plus noDefaults tests real visibility semantics.
  const profile=fs.mkdtempSync(path.join(root,'work','browser-profile-'));
  chromiumProcess=spawn(process.env.CONTROL_GESTUAL_CHROMIUM,[`--user-data-dir=${profile}`,'--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',
    '--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--disable-sync',
    '--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',...(process.env.CONTROL_GESTUAL_HEADED==='1'?[]:['--headless=new']),'about:blank'],
    {stdio:'ignore',windowsHide:true});
  const portFile=path.join(profile,'DevToolsActivePort');
  let port;
  for(let i=0;!port&&i<100;i++){
    try{const value=fs.readFileSync(portFile,'utf8').split('\n')[0];if(/^\d+$/.test(value)&&Number(value)>0)port=value;}
    catch(error){if(!['ENOENT','EBUSY','EPERM'].includes(error.code))throw error;}
    if(!port)await new Promise(resolve=>setTimeout(resolve,100));
  }
  if(!port)throw Error('El navegador de prueba no publicó su puerto de depuración.');
  browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`,{noDefaults:true,artifactsDir:path.join(root,'work')});
  let context=browser.contexts()[0];
  let page=await context.newPage();
  await page.setViewportSize({width:650,height:900});
  const errors=[],external=[];page.on("pageerror",e=>errors.push(e.message));
  page.on("request",r=>{if(/^https?:/.test(r.url())&&!r.url().startsWith(session.origin+"/"))external.push(r.url());});
  await page.goto(session.origin+"/#"+session.key);
  await page.waitForFunction(()=>document.querySelector("#status").textContent.startsWith("Listo."));
  assert.equal(await page.locator("#target").inputValue(),"active");
  assert.equal(new URL(page.url()).hash,"");
  await page.locator("#target").selectOption("123");await page.locator("#right").click();
  await page.waitForFunction(()=>document.querySelector("#status").textContent.includes("Movimiento simulado: right"));
  await page.locator("#undo").click();
  await page.waitForFunction(()=>document.querySelector("#status").textContent.includes("Movimiento deshecho simulado"));
  assert.equal(await page.locator("#undo").isDisabled(),true);
  await page.locator('#maximize').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('maximizada simulada'));
  await page.locator('#maximize').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('restaurada simulada'));
  await page.locator("#start").click();
  await page.waitForFunction(()=>/Cámara activa|No se pudo iniciar/.test(document.querySelector("#status").textContent),{},{timeout:60000});
  assert.match(await page.locator("#status").textContent(),/Cámara activa/);
  // The runtime above is real. Inject known landmarks only for the gesture journey.
  const cameraWorker=page.workers().find(w=>w.url().endsWith('/camera-worker.js'));
  assert.ok(cameraWorker);
  assert.equal(await page.locator('#tab-gestures').getAttribute('aria-selected'),'true');
  assert.equal(await page.locator('#panel-microphone').isVisible(),false);
  await page.locator('#video').evaluate(video=>{window.tabTestTracks=video.srcObject.getTracks();});
  await page.locator('#tab-microphone').click();
  assert.equal(await page.locator('#panel-gestures').isVisible(),false);
  assert.equal(await page.locator('#voiceStart').isVisible(),true);
  assert.equal(await page.evaluate(()=>window.tabTestTracks.every(track=>track.readyState==='live')),true);
  assert.equal(page.workers().includes(cameraWorker),true);
  await page.locator('#tab-microphone').press('ArrowLeft');
  assert.equal(await page.locator('#tab-gestures').getAttribute('aria-selected'),'true');
  await page.locator('#tab-gestures').press('End');
  assert.equal(await page.locator('#tab-phone').getAttribute('aria-selected'),'true');
  await page.locator('#tab-phone').press('Home');
  assert.equal(await page.locator('#panel-gestures').isVisible(),true);
  await cameraWorker.evaluate(async()=>{
    const {HandLandmarker}=await import("/vendor/vision_bundle.mjs");
    self.originalDetect=HandLandmarker.prototype.detectForVideo;
    HandLandmarker.prototype.detectForVideo=function(){
      const end=performance.now()+(self.testSlowMs||0);while(performance.now()<end){}
      return{landmarks:self.testHand?[self.testHand]:[]};
    };
  });
  async function hand(x,closed,dy=0){await cameraWorker.evaluate(h=>{self.testHand=h;},makeHand(x,closed).map(p=>({...p,y:p.y+dy})));}
  await hand(.7,false);await page.waitForTimeout(180);
  await hand(.7,true);
  await page.waitForFunction(()=>document.querySelector("#gestureStatus").textContent.includes("Ventana de prueba"));
  assert.equal(await page.locator("#handCanvas").getAttribute("data-detected"),"true");
  assert.equal(await page.locator("#handCanvas").getAttribute("data-pose"),"fist");
  assert.ok(await page.locator("#handCanvas").evaluate(c=>c.getContext("2d").getImageData(0,0,c.width,c.height).data.some((v,i)=>i%4===3&&v>0)));
  await hand(.4,true);
  await page.waitForFunction(()=>document.querySelector("#gestureStatus").textContent.startsWith("→"));
  await page.waitForTimeout(300);
  await page.screenshot({path:path.join(root,"work","desktop-gesture-check.png"),fullPage:true});
  await hand(.4,false);
  await page.waitForFunction(()=>document.querySelector("#status").textContent.includes("Movimiento simulado: right"));
  await cameraWorker.evaluate(()=>{self.testHand=null;});
  await page.waitForFunction(()=>document.querySelector("#handCanvas").dataset.detected==="false");
  await page.locator("#undo").click();
  await page.waitForFunction(()=>document.querySelector("#status").textContent.includes("Movimiento deshecho simulado"));
  await hand(.5,false,.05);await page.waitForTimeout(1700);
  await hand(.5,true,.05);
  await page.waitForFunction(()=>document.querySelector('#gestureStatus').textContent.includes('Ventana de prueba'));
  await hand(.5,true,-.17);
  await page.waitForFunction(()=>document.querySelector('#gestureStatus').textContent.startsWith('↑'));
  await page.waitForTimeout(300);
  await page.screenshot({path:path.join(root,'work','desktop-maximize-check.png'),fullPage:true});
  await hand(.5,false,-.17);
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('maximizada simulada'));
  await page.locator('#undo').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('deshecho simulado'));
  // Calibrate using known poses while ensuring that calibration never minimizes/moves.
  await hand(.5,false);await page.locator('#calibrate').click();
  await page.waitForFunction(()=>document.querySelector('#calibrate').textContent==='Capturar puño');
  await hand(.5,true);await page.locator('#calibrate').click();
  await page.waitForFunction(()=>document.querySelector('#calibrationState').textContent.includes('personalizada guardada'));
  await page.locator('#sensitivity').fill('12');await page.locator('#sensitivity').dispatchEvent('change');
  await page.waitForFunction(()=>document.querySelector('#sensitivityValue').textContent.startsWith('12%'));
  // All three finger families execute through worker -> UI -> authenticated server.
  for(const [pose,x,dy,label,expected] of [['index',.35,0,'Pulgar + índice','acomodada simulada: right'],['victory',.35,0,'Pulgar + medio','activada simulada'],['three',.35,.2,'Pulgar + anular','acomodada simulada: bottom_right'],['pinky',.35,0,'Pulgar + meñique','activada simulada']]){
    await hand(.65,false);await page.waitForTimeout(1700);
    await cameraWorker.evaluate(h=>{self.testHand=h;},makeFingerHand(.65,pose));
    await page.waitForFunction(name=>document.querySelector('#gestureStatus').textContent.includes('Ventana de prueba')&&document.querySelector('#gestureStatus').textContent.includes(name),label);
    await cameraWorker.evaluate(h=>{self.testHand=h;},makeFingerHand(x,pose,dy));
    await page.waitForFunction(()=>/^[→↘]/.test(document.querySelector('#gestureStatus').textContent));
    assert.match(await page.locator('#gestureStatus').textContent(),/Separá del pulgar/);
    assert.equal(await page.locator('#handCanvas').getAttribute('data-pose'),pose);
    const released=makeFingerHand(x,pose,dy);released[4].x-=.16;
    await cameraWorker.evaluate(h=>{self.testHand=h;},released);
    await page.waitForFunction(text=>document.querySelector('#status').textContent.includes(text),expected);
    if(['victory','pinky'].includes(pose)){assert.equal(await page.locator('#target').inputValue(),'124');await page.locator('#target').selectOption('123');}
  }
  // Native window operations remain mocked while the panel is hidden behind another tab.
  const other=await page.context().newPage();await other.goto('about:blank');await other.bringToFront();
  const cdp=await page.context().newCDPSession(page);
  const windowInfo=await cdp.send('Browser.getWindowForTarget');
  await cdp.send('Browser.setWindowBounds',{windowId:windowInfo.windowId,bounds:{windowState:'minimized'}});
  if(process.env.CONTROL_GESTUAL_DIAGNOSTICS==='1')console.log(JSON.stringify({visibility:await page.evaluate(()=>document.visibilityState),bounds:await cdp.send('Browser.getWindowBounds',{windowId:windowInfo.windowId})}));
  await page.waitForFunction(()=>document.hidden===true,{},{polling:100,timeout:5000});
  await cameraWorker.evaluate(()=>{self.testSlowMs=350;});
  await hand(.5,false,-.12);await page.waitForTimeout(1700);
  await hand(.5,true,-.12);
  await page.waitForFunction(()=>document.querySelector('#gestureStatus').textContent.includes('Ventana de prueba'),{},{polling:100});
  await hand(.5,true,.10);await page.waitForTimeout(300);await hand(.5,false,.10);
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('minimizada simulada'),{},{polling:100});
  await hand(.5,false,.05);await page.waitForTimeout(1700);
  await hand(.5,true,.05);
  await page.waitForFunction(()=>document.querySelector('#gestureStatus').textContent.includes('Ventana de prueba'),{},{polling:100});
  await hand(.5,true,-.17);await page.waitForTimeout(500);await hand(.5,false,-.17);
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('maximizada simulada'),{},{polling:100});
  await cameraWorker.evaluate(()=>{self.testSlowMs=0;});
  await cdp.send('Browser.setWindowBounds',{windowId:windowInfo.windowId,bounds:{windowState:'normal'}});
  await page.bringToFront();await other.close();
  await page.locator('#undo').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('deshecho simulado'));
  await cameraWorker.evaluate(async()=>{
    const {HandLandmarker}=await import('/vendor/vision_bundle.mjs');HandLandmarker.prototype.detectForVideo=self.originalDetect;
  });
  await page.locator("#video").evaluate(v=>{window.testTracks=v.srcObject.getTracks();});
  child.stdin.write("pause\n");
  await page.waitForFunction(()=>document.querySelector("#status").textContent.startsWith("F8"));
  assert.equal(await page.evaluate(()=>window.testTracks.every(t=>t.readyState==="ended")),true);
  await page.evaluate(()=>{
    window.originalPlay=HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play=function(){return window.originalPlay.call(this).then(()=>new Promise(resolve=>{window.releaseTestPlay=resolve;}));};
  });
  await page.locator("#start").click();
  await page.waitForFunction(()=>!!window.releaseTestPlay);
  await page.locator("#video").evaluate(v=>{window.cancelledTracks=v.srcObject.getTracks();});
  await page.locator("#target").selectOption("");
  await page.evaluate(()=>window.releaseTestPlay());
  await page.waitForFunction(()=>window.cancelledTracks.every(t=>t.readyState==="ended"));
  await page.evaluate(()=>{HTMLMediaElement.prototype.play=window.originalPlay;});
  // Version 2 UI: destination, layouts, app switching, profiles, exclusions and multi-step undo.
  await page.locator('#target').selectOption('123');
  await page.locator('#monitor').selectOption('2');
  await page.locator('[data-action="snap_top_left"]').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('acomodada simulada: top_left'));
  await page.locator('[data-action="next_app"]').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('activada simulada'));
  assert.equal(await page.locator('#target').inputValue(),'124');
  await page.locator('[data-action="next_app"]').click();
  await page.waitForFunction(()=>document.querySelector('#target').value==='123');
  await page.getByText('Perfiles y gestos personalizados del puño',{exact:true}).click();
  await page.locator('#profile').selectOption('organize');
  assert.equal(await page.locator('#bind-left').inputValue(),'snap_left');
  await page.locator('#saveProfile').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Perfil y gestos guardados'));
  await page.locator('#bind-right').selectOption('none');assert.equal(await page.locator('#profile').inputValue(),'custom');
  await page.locator('#saveProfile').click();
  await page.waitForFunction(async()=>{
    const r=await fetch('/api/settings',{headers:{'X-Control-Key':sessionStorage.getItem('control-key')}});const s=await r.json();return s.profile==='custom'&&s.bindings.right==='none';
  });
  await page.getByText('Personalizar acciones de los dedos',{exact:true}).click();
  await page.locator('#finger-index-left').selectOption('none');await page.locator('#saveFingers').click();
  await page.waitForFunction(async()=>{const r=await fetch('/api/settings',{headers:{'X-Control-Key':sessionStorage.getItem('control-key')}});const s=await r.json();return s.finger_bindings.index.left==='none'&&s.profile==='custom'&&s.bindings.right==='none';});
  await page.getByText('Aplicaciones excluidas',{exact:true}).click();
  await page.locator('#excludeSelected').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Aplicación excluida: demo.exe'));
  await page.locator('#maximize').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('está excluida'));
  await page.locator('#excludedApps').fill('');await page.locator('#saveExcluded').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Exclusiones guardadas'));
  for(let i=0;i<2;i++){
    const before=await page.evaluate(async()=>{const r=await fetch('/api/state',{headers:{'X-Control-Key':sessionStorage.getItem('control-key')}});return(await r.json()).history.length;});
    assert.ok(before>0);await page.locator('#undo').click();
    await page.waitForFunction(async expected=>{const r=await fetch('/api/state',{headers:{'X-Control-Key':sessionStorage.getItem('control-key')}});return(await r.json()).history.length===expected;},before-1);
  }
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  await page.locator('#tab-microphone').click();
  await page.locator('#voiceRefreshDevices').click();
  await page.locator('#voiceDevice').selectOption('7');
  await page.locator('#voiceStart').click();
  await page.waitForFunction(()=>document.querySelector('#voiceState').textContent.includes('Micrófono simulado'));
  await page.locator('#tab-gestures').click();
  child.stdin.write('voice Control minimizar\n');
  await page.waitForFunction(()=>document.querySelector('#voiceState').textContent.includes('minimizada simulada'));
  await page.locator('#tab-microphone').click();
  assert.match(await page.locator('#voiceHeard').textContent(),/control minimizar/);
  child.stdin.write('voice Control restaurar\n');
  await page.waitForFunction(()=>document.querySelector('#voiceState').textContent.includes('Estado de voz simulado: normal'));
  child.stdin.write('voice Control pausar\n');
  await page.waitForFunction(()=>document.querySelector('#voiceState').textContent.includes('Voz pausada'));
  child.stdin.write('voice Control continuar\n');
  await page.waitForFunction(()=>document.querySelector('#voiceState').textContent.includes('Voz activa'));
  await page.getByText('Frases personalizadas',{exact:true}).click();
  await page.locator('#voiceAliasPhrase').fill('grande');await page.locator('#voiceAliasAction').selectOption('maximize');await page.locator('#addVoiceAlias').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Frase guardada'));
  child.stdin.write('voice Control grande\n');
  await page.waitForFunction(()=>document.querySelector('#voiceState').textContent.includes('Estado de voz simulado: maximized'));
  await page.getByText('Elegir aplicaciones por nombre',{exact:true}).click();
  await page.locator('#appVoiceName').fill('prueba');await page.locator('#appVoiceExe').selectOption('second.exe');await page.locator('#addAppName').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Nombre guardado'));
  child.stdin.write('voice Control seleccionar prueba\n');
  await page.waitForFunction(()=>document.querySelector('#target').value==='124');
  await page.locator('#target').selectOption('123');
  const beforeTraining=await page.evaluate(async()=>{const r=await fetch('/api/state',{headers:{'X-Control-Key':sessionStorage.getItem('control-key')}});return(await r.json()).action_notice.id;});
  await page.locator('#voiceTestStart').click();
  for(const [index,text] of ['Control minimizar','Control siguiente','Control mover derecha'].entries()){
    await page.waitForFunction(step=>document.querySelector('#voiceTestPhrase').textContent.includes('Paso '+step),index+1);
    child.stdin.write('voice '+text+'\n');
  }
  await page.waitForFunction(()=>document.querySelector('#voiceTestMessage').textContent.includes('Prueba completa'));
  assert.equal(await page.evaluate(async()=>{const r=await fetch('/api/state',{headers:{'X-Control-Key':sessionStorage.getItem('control-key')}});return(await r.json()).action_notice.id;}),beforeTraining);
  await page.locator('#voiceStop').click();
  await page.waitForFunction(()=>document.querySelector('#voiceState').textContent.includes('Micrófono apagado'));
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:path.join(root,'work','desktop-microphone-tab.png'),fullPage:true});
  await page.locator('#tab-gestures').click();
  await page.locator('#scrollGesture').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('hacen scroll'));
  await page.locator('[data-action="scroll_down"]').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Scroll simulado'));
  await page.locator('[data-action="volume_up"]').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Multimedia simulada'));
  await page.getByText('Distribuciones favoritas',{exact:true}).click();
  await page.locator('#layoutName').fill('trabajo');await page.locator('#layoutWindows').selectOption(['123']);await page.locator('#saveLayout').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Distribución guardada'));
  await page.locator('#layoutChoice').selectOption('trabajo');await page.locator('#applyLayout').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Modo trabajo aplicado'));
  await page.locator('#undo').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Distribución deshecha'));
  const beforeClose=await page.locator('#history li').count();
  await page.locator('[data-action="close"]').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Cierre solicitado simulado'));
  assert.equal(await page.locator('#history li').count(),beforeClose);
  assert.ok(await page.locator('#bind-left option[value="close"]').count());
  await page.locator('#tab-microphone').click();await page.locator('#voiceStart').click();
  await page.waitForFunction(()=>document.querySelector('#voiceState').textContent.includes('Micrófono simulado'));
  child.stdin.write('voice Control cerrar\n');
  await page.waitForFunction(()=>document.querySelector('#voiceState').textContent.includes('Cierre solicitado simulado'));
  await page.locator('#voiceStop').click();
  // Raw CDP/noDefaults is required only by the background journey. Its headless
  // input routing drops events after a second camera stream; use the normal driver here.
  await cdp.send('Browser.close');await browser.close();chromiumProcess?.kill();chromiumProcess=null;
  browser=await chromium.launch({headless:true,executablePath:process.env.CONTROL_GESTUAL_CHROMIUM,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
  context=await browser.newContext();page=await context.newPage();
  await page.setViewportSize({width:650,height:900});
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(/^https?:/.test(request.url())&&!request.url().startsWith(session.origin+'/'))external.push(request.url());});
  await page.goto(session.origin+'/#'+session.key);
  await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Listo.'));
  await page.locator('#tab-microphone').click();
  child.stdin.write('duplicate\n');
  await page.waitForFunction(async()=>{const r=await fetch('/api/windows',{headers:{'X-Control-Key':sessionStorage.getItem('control-key')}});return(await r.json()).windows.length===3;});
  await page.locator('#assistantText').fill('Jarvis por favor pasa prueba a la derecha');await page.locator('#assistantSend').click();
  await page.waitForFunction(()=>document.querySelectorAll('#assistantChoices button').length===2);
  await page.locator('#assistantChoices button').first().click();
  await page.waitForFunction(()=>document.querySelector('#assistantContext').textContent.includes('Segunda ventana'));
  await page.locator('#assistantText').fill('Cierra esta ventana');await page.locator('#assistantSend').click();
  await page.waitForFunction(()=>document.querySelector('#assistantChoices').textContent.includes('Confirmar cierre'));
  await page.locator('#assistantChoices button').last().click();
  await page.waitForFunction(()=>document.querySelector('#assistantState').textContent.includes('Cancelado'));
  await page.locator('#assistantText').fill('Selecciona prueba');await page.locator('#assistantSend').click();
  await page.waitForFunction(()=>document.querySelectorAll('#assistantChoices button').length===2);
  await page.locator('#assistantChoices button').first().click();
  await page.waitForFunction(()=>document.querySelector('#assistantContext').textContent.includes('Segunda ventana'));
  await page.locator('#assistantText').fill('Ahora maximizalo');await page.locator('#assistantSend').click();
  await page.waitForFunction(()=>document.querySelector('#assistantState').textContent.includes('maximized'));
  assert.match(await page.locator('#assistantContext').textContent(),/Segunda ventana/);
  await page.locator('#assistantSpeech').check();
  await page.waitForFunction(async()=>{const r=await fetch('/api/settings',{headers:{'X-Control-Key':sessionStorage.getItem('control-key')}});return(await r.json()).spoken_replies===true;});
  await page.locator('#assistantMic').click();
  await page.waitForFunction(()=>document.querySelector('#voiceState').textContent.includes('Micrófono simulado'));
  child.stdin.write('voice Jarvis minimiza esta ventana\n');
  await page.waitForFunction(()=>document.querySelector('#assistantState').textContent.includes('minimizada simulada'));
  await page.locator('#assistantSpeech').uncheck();
  await page.locator('#voiceStop').click();
  await page.locator('#assistantText').fill('Borra todos los archivos');await page.locator('#assistantSend').click();
  await page.waitForFunction(()=>document.querySelector('#assistantState').textContent.includes('No entendí'));
  await page.locator('#assistantReset').click();
  await page.waitForFunction(()=>document.querySelector('#assistantContext').textContent.includes('Sin objetivo'));
  await page.locator('#aiStart').click();
  await page.waitForFunction(()=>document.querySelector('#aiState').textContent.includes('simulada encendida'));
  await page.waitForFunction(()=>document.querySelector('#voiceMode').textContent.includes('Órdenes'));
  await page.locator('#assistantMic').click();
  await page.waitForFunction(()=>document.querySelector('#voiceState').textContent.includes('Micrófono simulado'));
  await page.locator('#voiceQuestion').click();
  await page.waitForFunction(()=>document.querySelector('#voiceMode').textContent.includes('Escuchando una consulta'));
  child.stdin.write('voice Qué es la memoria\n');
  await page.waitForFunction(()=>document.querySelector('#assistantState').textContent.includes('RAM es temporal'));
  await page.waitForFunction(()=>document.querySelector('#voiceMode').textContent.includes('Órdenes'));
  await page.locator('#voiceStop').click();
  await page.locator('#assistantText').fill('Qué es la RAM');await page.locator('#assistantSend').click();
  await page.waitForFunction(()=>document.querySelector('#assistantState').textContent.includes('RAM es temporal'));
  await page.waitForFunction(()=>!document.querySelector('#assistantSend').disabled);
  await page.locator('#assistantText').fill('Quiero que ocupe todo el espacio disponible');await page.locator('#assistantSend').click();
  await page.waitForFunction(()=>document.querySelector('#assistantChoices').textContent.includes('Confirmar Maximizar'));
  await page.locator('#assistantChoices button').first().click();
  await page.waitForFunction(()=>document.querySelector('#assistantState').textContent.includes('maximized'));
  await page.locator('#aiStop').click();
  await page.waitForFunction(()=>document.querySelector('#aiState').textContent==='IA apagada');
  await page.screenshot({path:path.join(root,'work','desktop-assistant-tab.png'),fullPage:true});
  await page.locator('#tab-phone').click();
  await page.locator('#phoneHost').fill('192.168.1.50');await page.locator('#phonePairPort').fill('37000');await page.locator('#phoneCode').fill('123456');
  await page.locator('#phonePair').click();
  assert.equal(await page.locator('#phoneCode').inputValue(),'');
  await page.waitForFunction(()=>document.querySelector('#phoneResult').textContent.includes('Vinculación simulada'));
  await page.locator('#phoneConnectPort').fill('42000');await page.locator('#phoneConnect').click();
  await page.waitForFunction(()=>document.querySelector('#phoneIndicator').textContent==='Conectado');
  await page.locator('[data-phone-action="home"]').click();
  await page.waitForFunction(()=>document.querySelector('#phoneResult').textContent.includes('simulada: home'));
  await page.locator('#phoneGestures').check();
  await page.locator('#tab-gestures').click();await page.locator('#start').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Cámara activa'));
  const phoneWorker=page.workers().filter(worker=>worker.url().endsWith('/camera-worker.js')).at(-1);
  await phoneWorker.evaluate(async()=>{const {HandLandmarker}=await import('/vendor/vision_bundle.mjs');HandLandmarker.prototype.detectForVideo=function(){return{landmarks:self.testHand?[self.testHand]:[]};};});
  await phoneWorker.evaluate(h=>{self.testHand=h;},makeHand(.65));await page.waitForTimeout(250);
  await phoneWorker.evaluate(h=>{self.testHand=h;},makeHand(.65,true));
  await page.waitForFunction(()=>document.querySelector('#gestureStatus').textContent.includes('Teléfono'));
  await phoneWorker.evaluate(h=>{self.testHand=h;},makeHand(.35,true));await page.waitForTimeout(300);
  await phoneWorker.evaluate(h=>{self.testHand=h;},makeHand(.35));
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('simulada: recents'));
  await page.locator('#tab-microphone').click();
  assert.equal(await page.locator('#tab-microphone').getAttribute('aria-selected'),'true');
  await page.locator('#voiceStart').click();
  await page.waitForFunction(()=>document.querySelector('#voiceState').textContent.includes('Micrófono simulado'));
  child.stdin.write('voice Control telefono inicio\n');
  await page.waitForFunction(()=>document.querySelector('#voiceState').textContent.includes('simulada: home'));
  await page.locator('#voiceStop').click();await page.locator('#tab-phone').click();await page.locator('#phonePause').click();
  await page.waitForFunction(()=>document.querySelector('#video').srcObject===null);
  assert.equal(await page.locator('#phoneGestures').isChecked(),false);
  await page.screenshot({path:path.join(root,'work','desktop-phone-tab.png'),fullPage:true});
  fs.mkdirSync(path.join(root,"work"),{recursive:true});
  await page.screenshot({path:path.join(root,"work","desktop-panel-check.png"),fullPage:true});
  await page.locator("#quit").click();
  await page.waitForFunction(()=>document.querySelector("#status").textContent.startsWith("Aplicación cerrada"));
  console.log(JSON.stringify({version23:"four thumb contacts, repeated application cycling and independent customization passed",version2:"destination, layouts, switching, custom bindings, exclusions, two-step undo passed",nativeMove:"mock only",camera:"worker performs model inference AND gesture recognition",calibration:"passed",background:"hidden; 350ms inference; minimize then maximize passed",emergency:"capture tracks ended",cancelledStartup:"capture tracks ended",quit:"passed",externalRequests:external,pageErrors:errors}));
}finally{
  if(browser){try{const session=await browser.newBrowserCDPSession();await session.send('Browser.close');}catch{}await browser.close();}
  chromiumProcess?.kill();child.kill();
}

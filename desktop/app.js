import {handPose,calibrationFromSamples,gestureDirection} from "/core.js";
import {drawHand,poseLabel} from "/hand-view.js";
const $=id=>document.getElementById(id);
const controlTabs=[$('tab-gestures'),$('tab-microphone'),$('tab-phone')];
$('openAssistant').onclick=()=>{selectControlTab($('tab-microphone'));$('assistantText').focus();};
function selectControlTab(selected){
  for(const tab of controlTabs){
    const active=tab===selected;
    tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;
    $(tab.getAttribute('aria-controls')).hidden=!active;
  }
}
for(const [index,tab] of controlTabs.entries()){
  tab.onclick=()=>selectControlTab(tab);
  tab.onkeydown=event=>{
    const next=event.key==='Home'?0:event.key==='End'?controlTabs.length-1:event.key==='ArrowRight'?(index+1)%controlTabs.length:event.key==='ArrowLeft'?(index+controlTabs.length-1)%controlTabs.length:null;
    if(next===null)return;event.preventDefault();controlTabs[next].focus();selectControlTab(controlTabs[next]);
  };
}
const key=location.hash.slice(1)||sessionStorage.getItem("control-key")||"";
if(key)sessionStorage.setItem("control-key",key);
history.replaceState(null,"","/");
let grab=null,trackingEpoch=0;
let stream,cameraWorker,initializeReject,running=false,starting=false,generation=0,prepared=null,busy=false;
let emergency=0,closed=false,previewDirection,undoAvailable=false,noticeId=0;
let settings={sensitivity:18,calibration:null,invert:false},calibration=null,openSamples=[];
let features={actions:{},profiles:{}},historyKey='';
let voiceActive=false,voiceSequence=-1;
let testKey='',actionNoticeId=0;
let phoneBusy=false,phoneState={connected:false,enabled:false};
let assistantSequence=-1;
async function assistantRequest(text){
  const result=await api('assistant/request',{text,selected:selection(),monitor_id:$('monitor').value?Number($('monitor').value):null});
  $('assistantState').textContent=result.message;return result;
}
const phoneDirections={left:'back',right:'recents',up:'scroll_up',down:'scroll_down'};
const status=text=>{$("status").textContent=text;};
async function api(path,data){
  const response=await fetch("/api/"+path,{method:data===undefined?"GET":"POST",
    headers:{"X-Control-Key":key,...(data===undefined?{}:{"Content-Type":"application/json"})},
    ...(data===undefined?{}:{body:JSON.stringify(data)})});
  const result=await response.json();if(!response.ok)throw Error(result.error||"No se pudo completar la operación.");return result;
}
function cancel(clearOverlay=true){
  generation++;prepared=null;grab=null;previewDirection=undefined;
  cameraWorker?.postMessage({type:'reset',epoch:++trackingEpoch});
  $("gestureStatus").textContent="Abrí, juntá un dedo con el pulgar, desplazá y separalos. El puño sigue funcionando.";
  if(clearOverlay)api("preview",{clear:true}).catch(()=>{});
}
function applySettings(value){
  settings=value;configureTracking();
  $("sensitivity").value=value.sensitivity;$("sensitivityValue").textContent=value.sensitivity+"% del encuadre";
  $("invert").checked=value.invert;
  $("profile").value=value.profile||'windows';
  for(const direction of ['left','right','up','down'])$("bind-"+direction).value=value.bindings?.[direction]||'none';
  for(const [pose,definition] of Object.entries(features.finger_gestures||{}))for(const direction of Object.keys(definition.bindings))$("finger-"+pose+'-'+direction).value=value.finger_bindings?.[pose]?.[direction]||'none';
  $("excludedApps").value=(value.excluded_apps||[]).join('\n');
  $("calibrationState").textContent=value.calibration?"Calibración personalizada guardada.":"Usando detección predeterminada. Podés calibrarla con tu mano.";
  $('audioFeedback').checked=!!value.audio_feedback;
  $('assistantSpeech').checked=!!value.spoken_replies;
  renderToolSettings();
}
function renderToolSettings(){
  for(const [id,field] of [['voiceAliases','voice_aliases'],['appNames','app_names']]){
    $(id).replaceChildren(...Object.entries(settings[field]||{}).map(([name,value])=>{
      const li=document.createElement('li');li.textContent='Control '+(field==='app_names'?'seleccionar ':'')+name+' → '+(field==='voice_aliases'?(voiceActionLabels()[value]||value):value);
      const remove=document.createElement('button');remove.textContent='Eliminar';remove.onclick=()=>{const values={...settings[field]};delete values[name];saveSettings({...settings,[field]:values}).catch(error=>status(error.message));};li.append(remove);return li;
    }));
  }
  const selected=$('layoutChoice').value;
  $('layoutChoice').replaceChildren(new Option('Elegí un modo…',''),...Object.keys(settings.layouts||{}).map(name=>new Option(name,name)));
  if([...$('layoutChoice').options].some(option=>option.value===selected))$('layoutChoice').value=selected;
  describeLayout();
}
function voiceActionLabels(){
  return {...features.actions,...features.phone_actions,maximize:'Maximizar',restore:'Restaurar',toggle_maximize:'Maximizar / Restaurar',undo:'Deshacer',pause:'Pausar voz',resume:'Continuar voz',stop_mic:'Apagar micrófono',stop_all:'Detener controles',show_panel:'Mostrar panel',hide_panel:'Ocultar panel',discard_history:'Descartar registro',monitor_auto:'Destino automático',monitor_1:'Destino pantalla 1',monitor_2:'Destino pantalla 2',monitor_3:'Destino pantalla 3',monitor_4:'Destino pantalla 4'};
}
function describeLayout(){
  const slots=settings.layouts?.[$('layoutChoice').value];
  $('layoutDescription').textContent=slots?slots.map(slot=>slot.title+' · '+slot.app).join(' | '):'Guardá una distribución para recuperarla desde aquí o por voz.';
}
async function refreshVoiceCommands(){const result=await api('voice/commands');$('voiceCommands').replaceChildren(...result.commands.map(text=>{const item=document.createElement('li');item.textContent=text;return item;}));}
function configureTracking(){cameraWorker?.postMessage({type:'configure',epoch:++trackingEpoch,settings,disabled:!!calibration});}
async function saveSettings(value){const saved=await api("settings",value);applySettings(saved);cancel();await refreshVoiceCommands();}
function selection(){const value=$("target").value;if(!value)throw Error("Elegí una ventana.");return value==="active"?value:Number(value);}
async function refresh(){
  const selected=$("target").value,data=await api("windows");
  $("target").replaceChildren(new Option("Elegí una ventana…",""),new Option("Automática · última ventana activa","active"),
    ...data.windows.map(w=>new Option(w.title.slice(0,110),String(w.hwnd))));
  if([...$("target").options].some(o=>o.value===selected))$("target").value=selected;
  $("displays").textContent=data.displays.map((d,i)=>`Pantalla ${i+1}: ${d.bounds.width} × ${d.bounds.height}`).join(" | ");
  const monitor=$("monitor").value;
  $("monitor").replaceChildren(new Option('Automático según el gesto',''),...data.displays.map((d,i)=>new Option(`Pantalla ${i+1} · ${d.bounds.width} × ${d.bounds.height}`,String(d.id))));
  if([...$("monitor").options].some(o=>o.value===monitor))$("monitor").value=monitor;
  const chosen=[...$('layoutWindows').selectedOptions].map(option=>option.value);
  $('layoutWindows').replaceChildren(...data.windows.map(window=>{const option=new Option(window.title+' · '+(window.app||'Sin ejecutable'),String(window.hwnd));option.selected=chosen.includes(option.value);return option;}));
  const app=$('appVoiceExe').value;
  $('appVoiceExe').replaceChildren(new Option('Elegí una aplicación…',''),...[...new Set(data.windows.map(window=>window.app).filter(Boolean))].sort().map(name=>new Option(name,name)));
  if([...$('appVoiceExe').options].some(option=>option.value===app))$('appVoiceExe').value=app;
}
function adjusted(direction){return settings.invert?({left:'right',right:'left',top_left:'top_right',top_right:'top_left',bottom_left:'bottom_right',bottom_right:'bottom_left'}[direction]||direction):direction;}
function showGrab(snapshot,direction=null,pose=grab?.pose||'fist'){
  const arrow={left:"←",right:"→",down:"↓",up:"↑",top_left:'↖',top_right:'↗',bottom_left:'↙',bottom_right:'↘'}[direction]||"↔";
  if(snapshot.phone){$('gestureStatus').textContent=arrow+' Teléfono · '+(features.phone_actions?.['phone_'+phoneDirections[direction]]||'Puño capturado')+' · Abrí para confirmar.';previewDirection=direction;return;}
  const code=direction?(pose==='fist'?settings.bindings:settings.finger_bindings?.[pose])?.[direction]:null;
  const action=code?.startsWith('move_')&&$("monitor").value?'Enviar a '+$("monitor").selectedOptions[0].textContent:
    direction?features.actions[code]:'Seleccionada';
  $("gestureStatus").textContent=`${arrow} ${snapshot.title} · ${features.finger_gestures?.[pose]?.label||'Puño'} · ${action||'Confirmar'} · ${pose==='fist'?'Abrí la mano':'Separá del pulgar'}.`;
  api("preview",{snapshot,direction}).catch(()=>{});previewDirection=direction;
}
function setBusy(value){busy=value;for(const id of ["left","right","minimize","maximize"])$(id).disabled=value;document.querySelectorAll('[data-action]').forEach(button=>button.disabled=value);$("undo").disabled=value||!undoAvailable;}
async function perform(action,direction=null,snapshot=null,pose='fist'){
  if(busy||calibration)return;setBusy(true);
  try{
    if(snapshot?.phone){
      const action=phoneDirections[direction];if(!action)throw Error('Usá una dirección clara con el puño.');
      const result=await api('phone/action',{action,gesture:true,emergency});cancel(false);status(result.message);return;
    }
    const captured=snapshot||await api("capture",{selected:selection()});
    const chosen=action==='move'?'move_'+direction:action;
    status('Voy a '+(features.actions[chosen]||chosen)+' · '+captured.title);
    const monitor=$("monitor").value;
    const result=await api(snapshot?'gesture':'action',{action:chosen,snapshot:captured,direction,pose,monitor_id:monitor?Number(monitor):null,emergency});
    if(result.selected_window&&$("target").value===String(captured.hwnd)){
      const next=result.selected_window;
      if(![...$("target").options].some(option=>option.value===String(next.hwnd)))$("target").add(new Option(next.title,String(next.hwnd)));
      $("target").value=String(next.hwnd);voiceTarget();
    }
    cancel(false);undoAvailable=(result.undo_count??1)>0;status(result.message);
  }catch(error){status(error.message);}finally{setBusy(false);}
}
function disposeCamera(){
  initializeReject?.(Error("Inicio cancelado."));initializeReject=null;
  stream?.getTracks().forEach(t=>t.stop());stream=null;cameraWorker?.terminate();cameraWorker=null;
  $("video").srcObject=null;drawHand($("handCanvas"),$("video"),null);
}
function stop(message="Control pausado. Cámara apagada."){
  running=false;cancel();disposeCamera();calibration=null;
  applySettings(settings);
  $("calibrate").disabled=false;$("calibrate").textContent="Calibrar mano";
  $("cameraHint").textContent="Cámara apagada";$("start").disabled=starting;$("stop").disabled=true;
  status(message);api("pause",{}).catch(()=>{});
}
async function start(){
  if(starting||running)return;
  try{if(!$('phoneGestures').checked)selection();}catch(error){status(error.message);return;}
  starting=true;cancel();const token=generation;
  $("start").disabled=true;$("stop").disabled=false;status("Preparando cámara y detección en segundo plano…");
  try{
    if(typeof MediaStreamTrackProcessor==="undefined")throw Error("Este navegador no admite el procesamiento de cámara en segundo plano. Usá Chrome actualizado.");
    const state=await api("state");emergency=state.emergency;
    const worker=new Worker("/camera-worker.js");cameraWorker=worker;
    await new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>reject(Error("El detector tardó demasiado en iniciar.")),30000);
      initializeReject=error=>{clearTimeout(timeout);reject(error);};
      worker.onerror=event=>{clearTimeout(timeout);reject(Error(event.message||"Falló el detector."));if(running)stop("El detector se detuvo. Cámara apagada.");};
      worker.onmessage=({data})=>{
        if(data.type==="ready"){clearTimeout(timeout);initializeReject=null;resolve();}
        else if(data.type==="error"){clearTimeout(timeout);reject(Error(data.error));if(running)stop(data.error);}
        else if(data.type==="paused"&&running)stop("F8 o bandeja: control pausado y cámara apagada.");
        else if(data.type==="hand"&&running&&data.epoch===trackingEpoch){grab=data.grab;frame(data.hand,data.now,data.event);}
      };
      worker.postMessage({type:"init",epoch:trackingEpoch,settings});
    });
    if(token!==generation)return;
    const camera=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480}},audio:false});
    if(token!==generation){camera.getTracks().forEach(t=>t.stop());return;}
    stream=camera;$("video").srcObject=stream;await $("video").play();if(token!==generation)return;
    const processor=new MediaStreamTrackProcessor({track:stream.getVideoTracks()[0]});
    await api("arm",{emergency:state.emergency});if(token!==generation){await api("pause",{});return;}
    running=true;worker.postMessage({type:"stream",readable:processor.readable,key,emergency:state.emergency},[processor.readable]);
    status("Cámara activa. Puño: abrí para confirmar. Contacto con pulgar: separá para confirmar. F8 pausa.");
  }catch(error){if(token===generation)stop("No se pudo iniciar: "+error.message);}
  finally{
    if(!running){disposeCamera();if(token!==generation&&$("status").textContent.startsWith("Preparando"))status("Inicio cancelado. Cámara apagada.");}
    starting=false;$("start").disabled=running;$("stop").disabled=!running;
  }
}
function calibrationFrame(hand,now){
  if(!calibration||!["open","closed"].includes(calibration.stage))return;
  if(calibration.start===null)calibration.start=now;
  const pose=handPose(hand);if(pose)calibration.samples.push(pose.openness);
  const elapsed=now-calibration.start;
  $("calibrationState").textContent=`${calibration.stage==="open"?"Mano abierta":"Puño cerrado"}: ${Math.min(100,Math.round(elapsed/22))}% · ${calibration.samples.length} muestras`;
  if(elapsed<2200)return;
  const stage=calibration.stage,samples=calibration.samples;
  if(samples.length<15){calibration=null;configureTracking();$("calibrate").disabled=false;$("calibrate").textContent="Repetir calibración";status("Faltan muestras. Mostrá la mano completa y repetí.");return;}
  if(stage==="open"){
    openSamples=samples;calibration={stage:"await-closed"};$("calibrate").disabled=false;$("calibrate").textContent="Capturar puño";
    $("calibrationState").textContent="Ahora cerrá el puño y pulsá Capturar puño. Los gestos siguen suspendidos.";
  }else{
    calibration={stage:"saving"};
    try{
      const profile=calibrationFromSamples(openSamples,samples);
      saveSettings({...settings,calibration:profile}).then(()=>status("Calibración guardada. Probá abrir y cerrar la mano.")).catch(error=>status(error.message)).finally(()=>{
        calibration=null;configureTracking();$("calibrate").disabled=false;$("calibrate").textContent="Recalibrar mano";
      });
    }catch(error){calibration=null;configureTracking();$("calibrate").disabled=false;$("calibrate").textContent="Repetir calibración";status(error.message);}
  }
}
function frame(hand,now,event){
  try{
    drawHand($("handCanvas"),$("video"),hand,!!grab,settings.calibration);
    $("cameraHint").textContent=poseLabel(hand,!!grab,settings.calibration);
    if(calibration){calibrationFrame(hand,now);return;}
    if(!grab&&!event&&prepared)cancel();
    if(event?.type==="grab"&&!busy){
      if($('phoneGestures').checked){
        if(grab?.pose!=='fist'){cancel();status('Modo teléfono: usá el puño.');return;}
        prepared={phone:true,title:'Teléfono Android'};showGrab(prepared);return;
      }
      const token=++generation;prepared=null;
      api("capture",{selected:selection()}).then(snapshot=>{if(token===generation&&grab){prepared=snapshot;showGrab(snapshot);}})
        .catch(error=>{if(token===generation){cancel();status(error.message);}});
    }else if(["move","minimize","maximize","finger"].includes(event?.type)){
      const snapshot=prepared;prepared=null;generation++;
      const direction=event.type==='minimize'?'down':event.type==='maximize'?'up':adjusted(event.direction);
      if(snapshot)perform(event.type,direction,snapshot,event.pose||'fist');else cancel();
    }else if(event?.type==="cancel")cancel();
    const pose=handPose(hand,settings.calibration);
    if(pose&&grab&&prepared){
      const dx=pose.x-grab.x,dy=pose.y-grab.y,threshold=settings.sensitivity/100;
      const direction=adjusted(gestureDirection(dx,dy,threshold,grab.pose));
      if(direction!==previewDirection)showGrab(prepared,direction);
    }
  }catch(error){stop(error.message);}
}
$("left").onclick=()=>{cancel();perform("move","left");};$("right").onclick=()=>{cancel();perform("move","right");};
$("minimize").onclick=()=>{cancel();perform("minimize");};$("start").onclick=start;$("stop").onclick=()=>stop();
$("maximize").onclick=()=>{cancel();perform("maximize");};
document.querySelectorAll('[data-action]').forEach(button=>{button.onclick=()=>{cancel();perform(button.dataset.action);};});
$("undo").onclick=async()=>{
  if(busy)return;setBusy(true);cancel();try{const result=await api("undo",{});undoAvailable=(result.remaining??0)>0;status(result.message);}
  catch(error){status(error.message);}finally{setBusy(false);}
};
$("calibrate").onclick=()=>{
  if(!running){status("Encendé la cámara antes de calibrar.");return;}
  const stage=calibration?.stage==="await-closed"?"closed":"open";cancel();calibration={stage,samples:[],start:null};
  configureTracking();
  $("calibrate").disabled=true;status(stage==="open"?"Mantené la mano abierta y quieta durante dos segundos.":"Mantené el puño cerrado y quieto durante dos segundos.");
};
$("resetCalibration").onclick=()=>{calibration=null;configureTracking();$("calibrate").disabled=false;$("calibrate").textContent="Calibrar mano";saveSettings({...settings,calibration:null}).catch(error=>status(error.message));};
$("sensitivity").oninput=()=>{$("sensitivityValue").textContent=$("sensitivity").value+"% del encuadre";};
$("sensitivity").onchange=()=>saveSettings({...settings,sensitivity:Number($("sensitivity").value)}).catch(error=>{applySettings(settings);status(error.message);});
$("invert").onchange=()=>saveSettings({...settings,invert:$("invert").checked}).catch(error=>status(error.message));
function voiceTarget(){if(voiceActive)api('voice/target',{selected:selection(),monitor_id:$("monitor").value?Number($("monitor").value):null}).catch(error=>status(error.message));}
$("target").onchange=()=>{cancel();voiceTarget();};$("refresh").onclick=()=>{cancel();refresh().then(voiceTarget).catch(error=>status(error.message));};
$("monitor").onchange=()=>{cancel();voiceTarget();};
$("voiceStart").onclick=async()=>{
  $("voiceStart").disabled=true;
  try{await api('voice/start',{selected:selection(),monitor_id:$("monitor").value?Number($("monitor").value):null,device_id:$('voiceDevice').value===''?null:Number($('voiceDevice').value)});}
  catch(error){status(error.message);$("voiceStart").disabled=false;}
};
$("voiceStop").onclick=()=>api('voice/stop',{}).catch(error=>status(error.message));
$('voiceRefreshDevices').onclick=async()=>{
  try{
    const selected=$('voiceDevice').value,result=await api('voice/devices');
    $('voiceDevice').replaceChildren(new Option('Predeterminado de Windows',''),...result.devices.map(device=>new Option(device.name,String(device.id))));
    if([...$('voiceDevice').options].some(option=>option.value===selected))$('voiceDevice').value=selected;
    $('voiceState').textContent='Micrófonos actualizados. Elegí uno y encendelo.';
  }catch(error){$('voiceState').textContent=error.message;}
};
async function phoneOperation(name,data={}){
  if(phoneBusy)return;phoneBusy=true;updatePhoneControls();
  try{const result=await api('phone/'+name,data);$('phoneResult').textContent=result.message||'Conexión verificada.';}
  catch(error){$('phoneResult').textContent=error.message;}
  finally{phoneBusy=false;updatePhoneControls();}
}
function updatePhoneControls(){
  for(const id of ['phonePair','phoneConnect','phoneCheck','phoneDisconnect','phoneShow','phoneHide','phonePause','phoneResume'])$(id).disabled=phoneBusy;
  for(const id of ['phoneShow','phonePause'])$(id).disabled=phoneBusy||!phoneState.connected||!phoneState.enabled;
  $('phoneResume').disabled=phoneBusy||!phoneState.connected||phoneState.enabled;
  $('phoneHide').disabled=phoneBusy||!phoneState.mirror;
  $('phoneDisconnect').disabled=phoneBusy||!phoneState.device;
  $('phoneGestures').disabled=!phoneState.connected||!phoneState.enabled;
  document.querySelectorAll('[data-phone-action]').forEach(button=>button.disabled=phoneBusy||!phoneState.connected||!phoneState.enabled);
}
$('phonePair').onclick=()=>{const code=$('phoneCode').value;$('phoneCode').value='';phoneOperation('pair',{host:$('phoneHost').value.trim(),port:Number($('phonePairPort').value),code});};
$('phoneConnect').onclick=()=>phoneOperation('connect',{host:$('phoneHost').value.trim(),port:Number($('phoneConnectPort').value)});
for(const [id,action] of [['phoneCheck','check'],['phoneDisconnect','disconnect'],['phoneShow','show'],['phoneHide','hide'],['phonePause','pause'],['phoneResume','resume']])$(id).onclick=()=>phoneOperation(action);
$('phoneGestures').onchange=()=>{cancel();$('gestureTarget').textContent='Destino de los gestos: '+($('phoneGestures').checked?'teléfono (solo puño).':'escritorio.');};
$('assistantForm').onsubmit=async event=>{
  event.preventDefault();const text=$('assistantText').value.trim();if(!text)return;
  $('assistantSend').disabled=true;
  try{await assistantRequest(text);if($('assistantText').value.trim()===text)$('assistantText').value='';}
  catch(error){$('assistantState').textContent=error.message;}
  finally{$('assistantSend').disabled=false;}
};
$('assistantReset').onclick=()=>api('assistant/reset',{}).catch(error=>$('assistantState').textContent=error.message);
$('assistantMic').onclick=()=>$(voiceActive?'voiceStop':'voiceStart').click();
$('voiceQuestion').onclick=()=>api('voice/question',{}).catch(error=>$('voiceState').textContent=error.message);
async function aiOperation(action){
  $('aiStart').disabled=true;
  try{const result=await api('ai/'+action,{});$('aiState').textContent=result.message;}
  catch(error){$('aiState').textContent=error.message;status(error.message);}
}
$('aiStart').onclick=()=>aiOperation('start');
$('aiStop').onclick=()=>aiOperation('stop');
$('aiCancel').onclick=()=>api('assistant/cancel',{}).catch(error=>status(error.message));
$('assistantSpeech').onchange=()=>saveSettings({...settings,spoken_replies:$('assistantSpeech').checked}).catch(error=>status(error.message));
$('voiceTestStart').onclick=async()=>{try{if(running||starting)stop('Gestos pausados para la prueba del micrófono.');await api('voice/test/start',{});}catch(error){status(error.message);}};
$('voiceTestCancel').onclick=()=>api('voice/test/cancel',{}).catch(error=>status(error.message));
$('addVoiceAlias').onclick=()=>{
  const name=$('voiceAliasPhrase').value.trim();
  saveSettings({...settings,voice_aliases:{...(settings.voice_aliases||{}),[name]:$('voiceAliasAction').value}}).then(()=>status('Frase guardada: Control '+name)).catch(error=>status(error.message));
};
$('addAppName').onclick=()=>{
  const name=$('appVoiceName').value.trim();
  saveSettings({...settings,app_names:{...(settings.app_names||{}),[name]:$('appVoiceExe').value}}).then(()=>status('Nombre guardado: Control seleccionar '+name)).catch(error=>status(error.message));
};
$('audioFeedback').onchange=()=>saveSettings({...settings,audio_feedback:$('audioFeedback').checked}).catch(error=>{applySettings(settings);status(error.message);});
$('scrollGesture').onclick=()=>saveSettings({...settings,finger_bindings:{...settings.finger_bindings,pinky:{...settings.finger_bindings.pinky,up:'scroll_up',down:'scroll_down'}}}).then(()=>status('Pulgar + meñique: arriba y abajo hacen scroll.')).catch(error=>status(error.message));
$('layoutChoice').onchange=describeLayout;
$('saveLayout').onclick=async()=>{
  try{const saved=await api('layouts/save',{name:$('layoutName').value,windows:[...$('layoutWindows').selectedOptions].map(option=>Number(option.value))});applySettings(saved);await refreshVoiceCommands();status('Distribución guardada.');}
  catch(error){status(error.message);}
};
$('applyLayout').onclick=async()=>{try{const result=await api('layouts/apply',{name:$('layoutChoice').value});status(result.message);}catch(error){status(error.message);}};
$('deleteLayout').onclick=async()=>{try{applySettings(await api('layouts/delete',{name:$('layoutChoice').value}));await refreshVoiceCommands();status('Modo eliminado.');}catch(error){status(error.message);}};
$("profile").onchange=()=>{const preset=features.profiles[$("profile").value];if(preset)for(const direction of ['left','right','up','down'])$("bind-"+direction).value=preset[direction];};
for(const direction of ['left','right','up','down'])$("bind-"+direction).onchange=()=>{$("profile").value='custom';};
$("saveProfile").onclick=()=>{
  const bindings=Object.fromEntries(['left','right','up','down'].map(direction=>[direction,$("bind-"+direction).value]));
  saveSettings({...settings,profile:$("profile").value,bindings}).then(()=>status('Perfil y gestos guardados.')).catch(error=>status(error.message));
};
$("saveFingers").onclick=()=>{
  const finger_bindings=Object.fromEntries(Object.entries(features.finger_gestures).map(([pose,definition])=>[pose,
    Object.fromEntries(Object.keys(definition.bindings).map(direction=>[direction,$('finger-'+pose+'-'+direction).value]))]));
  saveSettings({...settings,finger_bindings}).then(()=>status('Gestos de dedos guardados. Funcionan con cualquier perfil.')).catch(error=>status(error.message));
};
$("saveExcluded").onclick=()=>saveSettings({...settings,excluded_apps:$("excludedApps").value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean)}).then(()=>status('Exclusiones guardadas.')).catch(error=>status(error.message));
$("excludeSelected").onclick=async()=>{
  try{const selected=await api('capture',{selected:selection()});if(!selected.app)throw Error('Windows no pudo identificar el ejecutable. Escribí su nombre manualmente.');
    await saveSettings({...settings,excluded_apps:[...new Set([...(settings.excluded_apps||[]),selected.app])]});status('Aplicación excluida: '+selected.app);
  }catch(error){status(error.message);}
};
$("discardHistory").onclick=()=>api('history/discard',{}).then(()=>status('Último registro descartado.')).catch(error=>status(error.message));
$("background").onclick=()=>api("panel",{action:"hide"}).catch(error=>status(error.message));
$("quit").onclick=async()=>{stop();try{await api("quit",{});closed=true;status("Aplicación cerrada. Podés cerrar este panel.");}catch(error){status(error.message);}};
document.addEventListener("keydown",event=>{if(event.key==="Escape"){stop();api('voice/stop',{}).catch(()=>{});api('phone/pause',{}).catch(()=>{});}});
window.addEventListener("pagehide",()=>{
  running=false;disposeCamera();fetch("/api/pause",{method:"POST",headers:{"X-Control-Key":key,"Content-Type":"application/json"},body:"{}",keepalive:true}).catch(()=>{});
  fetch('/api/voice/stop',{method:'POST',headers:{'X-Control-Key':key,'Content-Type':'application/json'},body:'{}',keepalive:true}).catch(()=>{});
  fetch('/api/phone/pause',{method:'POST',headers:{'X-Control-Key':key,'Content-Type':'application/json'},body:'{}',keepalive:true}).catch(()=>{});
});
function bridgeText(id,text){if($(id).textContent!==text)$(id).textContent=text;}
function updateBridge(state){
  const voice=state.voice||{},ai=state.ai||{},assistant=state.assistant||{},phone=state.phone||{};
  let mode='idle',label='EN ESPERA',note='Activá un control cuando lo necesites.';
  if(state.speech?.speaking){mode='speaking';label='RESPONDIENDO';note='Jarvis está hablando.';}
  else if(ai.starting){mode='starting';label='INICIANDO IA';note='Preparando el modelo local.';}
  else if(ai.busy){mode='thinking';label='PENSANDO';note='Procesando tu consulta en esta PC.';}
  else if(assistant.confirmation){mode='confirm';label='CONFIRMACIÓN PENDIENTE';note='Revisá la acción antes de continuar.';}
  else if(assistant.choices?.length){mode='confirm';label='ELEGÍ UNA VENTANA';note='Hay varias coincidencias para tu pedido.';}
  else if(voice.starting){mode='starting';label='PREPARANDO MICRÓFONO';note='Iniciando el reconocimiento de voz.';}
  else if(voice.active&&voice.paused){mode='paused';label='ESCUCHA EN PAUSA';note='Consultá el estado del micrófono.';}
  else if(voice.active){mode='listening';label=voice.input_mode==='question'?'ESCUCHANDO CONSULTA':'ESCUCHANDO ÓRDENES';note=voice.input_mode==='question'?'Decí tu consulta en una frase.':'Probá «Control Chrome» o «Control minimizar».';}
  else if(starting||running){mode='tracking';label=starting?'PREPARANDO CÁMARA':'GESTOS ACTIVOS';note='Los controles de la mano están disponibles en Gestos.';}
  else if(ai.enabled){label='IA DISPONIBLE';note='Escribí una consulta en la pestaña Micrófono.';}
  const level=voice.active?Math.max(0,Math.min(100,Number(voice.level)||0)):0;
  $('jarvisCore').dataset.mode=mode;$('jarvisCore').style.setProperty('--energy',level/100);
  bridgeText('bridgeMode',label);bridgeText('bridgeNote',note);
  bridgeText('bridgeAI',ai.starting?'Iniciando':ai.enabled?'Encendida':'Apagada');
  bridgeText('bridgeMic',voice.starting?'Preparando':voice.active?(voice.paused?'En pausa':'Escuchando'):'Apagado');
  bridgeText('bridgeCamera',starting?'Preparando':running?'Encendida':'Apagada');
  bridgeText('bridgePhone',phone.connected?(phone.enabled?'Conectado':'En pausa'):'Desconectado');
  const context=assistant.context;
  bridgeText('bridgeTargetLabel',context?'OBJETIVO DE LA CONVERSACIÓN':'VENTANA ELEGIDA');
  bridgeText('bridgeTarget',context?(context.unavailable?'No disponible: ':'')+context.title:$('target').value==='active'?(state.recovery?.title||state.last?.title||'Activá una ventana para seleccionarla.'):($('target').selectedOptions[0]?.textContent||'Elegí una ventana para empezar.'));
  bridgeText('bridgeHeard',voice.partial||voice.text||'Probá «Control Chrome» o «Control pregunta».');
  bridgeText('bridgeSignal',voice.active?(voice.clipping?'SATURADA':level+'%'):'APAGADA');$('bridgeLevel').value=level;
}
async function poll(){
  if(closed)return;
  try{
    const state=await api("state");
    const assistant=state.assistant;
    const ai=state.ai||{enabled:false,starting:false,busy:false,available:false};
    $('aiState').textContent=ai.message||'IA apagada.';
    $('aiStart').disabled=!ai.available||ai.enabled||ai.starting;
    $('aiStop').disabled=!ai.enabled&&!ai.starting;
    $('aiCancel').disabled=!ai.busy&&!ai.starting;
    if(assistant&&assistant.sequence!==assistantSequence){
      assistantSequence=assistant.sequence;$('assistantState').textContent=assistant.message;
      $('assistantContext').textContent=assistant.context?(assistant.context.unavailable?'Objetivo no disponible: ':'Objetivo de la conversación: ')+assistant.context.title:'Sin objetivo en la conversación.';
      $('assistantTurns').replaceChildren(...assistant.turns.map(turn=>{const item=document.createElement('li');item.dataset.role=turn.role;item.textContent=(turn.role==='user'?'Vos: ':'Jarvis: ')+turn.text;return item;}));
      const options=assistant.confirmation?[{text:(assistant.confirmation_action==='Cerrar ventana'?'Confirmar cierre':'Confirmar '+(assistant.confirmation_action||'acción'))+': '+assistant.confirmation,phrase:'Jarvis confirmar'},{text:'Cancelar',phrase:'Jarvis cancelar'}]:assistant.choices.map(choice=>({text:(choice.index+1)+'. '+choice.title,phrase:'Jarvis '+['primera','segunda','tercera','cuarta','quinta'][choice.index]}));
      $('assistantChoices').replaceChildren(...options.map(option=>{const button=document.createElement('button');button.type='button';button.textContent=option.text;button.onclick=async()=>{button.disabled=true;try{await assistantRequest(option.phrase);}catch(error){$('assistantState').textContent=error.message;}finally{button.disabled=false;}};return button;}));
    }
    if(state.speech)$('speechState').textContent=state.speech.speaking?'Jarvis está hablando. Las órdenes del micrófono se reanudan después.':state.speech.message;
    phoneState=state.phone||{connected:false,enabled:false};
    $('phoneIndicator').textContent=phoneState.connected?(phoneState.enabled?'Conectado':'En pausa'):'Desconectado';$('phoneIndicator').dataset.active=String(!!phoneState.connected&&!!phoneState.enabled);
    $('phoneConnection').textContent=(phoneState.device?phoneState.device+' · ':'')+(phoneState.message||'Teléfono desconectado.');
    if($('phoneGestures').checked&&(!phoneState.connected||!phoneState.enabled)){$('phoneGestures').checked=false;stop('Gestos pausados porque el control del teléfono se detuvo.');$('gestureTarget').textContent='Destino de los gestos: escritorio (cámara pausada).';}
    updatePhoneControls();
    const voice=state.voice;
    $('voiceQuestion').disabled=!ai.enabled||ai.busy||!voice?.active||!!voice?.paused||voice?.input_mode==='question'||!!voice?.test?.active;
    $('voiceMode').textContent=voice?.input_mode==='question'?'Escuchando una consulta · una frase':'Órdenes de voz · Control Chrome / Control Discord';
    $('assistantMic').textContent=voice?.active?'Apagar micrófono':'Encender micrófono';
    $('assistantMic').disabled=!!voice?.starting;
    const test=voice?.test;
    $('voiceTestStart').disabled=!voice?.active||!!test?.active;$('voiceTestCancel').disabled=!test?.active;
    const testSnapshot=JSON.stringify(test||{});
    if(testSnapshot!==testKey){
      testKey=testSnapshot;$('voiceTestPhrase').textContent=test?.active?(test.phase==='silence'?'Preparación: ':'Paso '+(test.index+1)+' de 3: ')+test.phrase:'';
      $('voiceTestMessage').textContent=(test?.message||'Prueba sin iniciar.')+(typeof test?.noise_level==='number'?' Nivel de fondo estimado: '+test.noise_level+'%.':'');
      $('voiceTestResults').replaceChildren(...(test?.results||[]).map(row=>{const li=document.createElement('li');li.textContent=(row.passed?'✓ ':'↻ ')+row.phrase+' · Escuché: '+row.heard+' · Nivel máximo '+row.peak+'%'+(row.clipped?' · Señal saturada':'');return li;}));
    }
    if(state.action_notice&&state.action_notice.id!==actionNoticeId){actionNoticeId=state.action_notice.id;$('actionFeedback').textContent=state.action_notice.text;}
    voiceActive=!!(voice?.active||voice?.starting);
    $('gesturesIndicator').textContent=starting?'Preparando':running?'Encendidos':'Apagados';
    $('gesturesIndicator').dataset.active=String(running||starting);
    $('microphoneIndicator').textContent=voice?.starting?'Preparando':voice?.paused&&voiceActive?'En pausa':voiceActive?'Encendido':'Apagado';
    $('microphoneIndicator').dataset.active=String(voiceActive);
    $("voiceStart").disabled=voiceActive;$("voiceStop").disabled=!voiceActive;
    $('voiceDevice').disabled=voiceActive;$('voiceRefreshDevices').disabled=voiceActive;
    $('voiceLevel').value=voice?.level||0;
    $('voiceSignal').textContent=!voiceActive?'Micrófono apagado.':voice?.clipping?'Señal saturada: alejate un poco o bajá el volumen del micrófono.':(voice?.level||0)<20?'Señal muy baja o silencio. Hablá cerca del micrófono.':'Señal de entrada: '+voice.level+'%';
    $('voicePartial').textContent=voice?.partial?'Escuchando: '+voice.partial:'';
    $('voiceConfidence').textContent=typeof voice?.confidence==='number'?(voice.confidence_mode==='phrase'?'Confianza estimada de frase y activación: ':'Confianza estimada de la palabra menos clara: ')+Math.round(voice.confidence*100)+'%':'';
    if(voice&&voice.sequence!==voiceSequence){
      voiceSequence=voice.sequence;$("voiceState").textContent=voice.message;$("voiceHeard").textContent=voice.text?'Última frase: '+voice.text:'';
      if(voiceActive){
        const selected=String(voice.selected);
        if([...$("target").options].some(option=>option.value===selected)&&$("target").value!==selected){$("target").value=selected;cancel();}
        const monitor=voice.monitor===null?'':String(voice.monitor);
        if([...$("monitor").options].some(option=>option.value===monitor))$("monitor").value=monitor;
      }
    }
    if((running||starting)&&state.emergency!==emergency)stop("F8 o bandeja: control pausado y cámara apagada.");
    emergency=state.emergency;undoAvailable=state.undo_available;$("undo").disabled=busy||!undoAvailable;
    const key=JSON.stringify(state.history||[]);
    if(key!==historyKey){historyKey=key;$("history").replaceChildren(...(state.history?.length?state.history.map(item=>{
      const li=document.createElement('li');li.textContent=`${item.time} · ${item.label} · ${item.title}`;return li;
    }):[Object.assign(document.createElement('li'),{textContent:'Todavía no hay acciones.'})]));}
    $("discardHistory").disabled=busy||!state.history?.length;
    $("background").disabled=!state.tray_available||!(running||voiceActive);
    $("backgroundState").textContent=(state.tray_available?"Icono de bandeja disponible.":"Bandeja no disponible; mantené el panel accesible.")+" "+
      (state.shortcut_available?"Ctrl+Alt+Z deshace desde otras aplicaciones.":"Ctrl+Alt+Z no está registrado; usá el botón Deshacer.");
    if(state.notice?.id!==noticeId){noticeId=state.notice?.id||0;if(state.notice?.text)status(state.notice.text);}
    $("current").textContent=state.recovery&&$("target").value==="active"?"Ventana minimizada: "+state.recovery.title+". Arriba la recupera. Para cambiar de objetivo, elegí otra ventana en la lista.":
      state.last?"Última ventana activa: "+state.last.title:"Activá una aplicación para seleccionarla automáticamente.";
    updateBridge(state);
  }catch{if(running||starting)stop("Se perdió la conexión local. Cámara apagada.");$('jarvisCore').dataset.mode='offline';bridgeText('bridgeMode','SIN CONEXIÓN LOCAL');bridgeText('bridgeNote','Esperando reconectar con la aplicación.');}
  setTimeout(poll,500);
}
async function initialize(){
  features=await api('features');
  for(const [action,label] of Object.entries(features.phone_actions||{})){
    const button=document.createElement('button');button.textContent=label.replace('Teléfono: ','');button.dataset.phoneAction=action.slice(6);button.onclick=()=>phoneOperation('action',{action:button.dataset.phoneAction});$('phoneButtons').append(button);
  }
  await refreshVoiceCommands();
  $('voiceAliasAction').replaceChildren(...Object.entries(voiceActionLabels()).map(([action,label])=>new Option(label,action)));
  const directionLabels={left:'← Izquierda',right:'→ Derecha',up:'↑ Arriba',down:'↓ Abajo',top_left:'↖ Arriba izquierda',top_right:'↗ Arriba derecha',bottom_left:'↙ Abajo izquierda',bottom_right:'↘ Abajo derecha'};
  for(const [pose,definition] of Object.entries(features.finger_gestures)){
    const group=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent=definition.label;group.append(legend);
    const grid=document.createElement('div');grid.className='bindingGrid';
    for(const direction of Object.keys(definition.bindings)){
      const label=document.createElement('label'),select=document.createElement('select');label.textContent=directionLabels[direction];select.id='finger-'+pose+'-'+direction;
      select.replaceChildren(...Object.entries(features.actions).map(([action,title])=>new Option(title,action)));label.append(select);grid.append(label);
    }
    group.append(grid);$('fingerBindings').append(group);
  }
  for(const direction of ['left','right','up','down'])$("bind-"+direction).replaceChildren(...Object.entries(features.actions).map(([action,label])=>new Option(label,action)));
  await Promise.all([refresh(),api('settings').then(applySettings)]);
  status('Listo. Control Gestual '+features.version+' · Probá los botones o encendé la cámara.');poll();
}
initialize().catch(error=>status(error.message));

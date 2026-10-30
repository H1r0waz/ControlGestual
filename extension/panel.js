import {Gesture} from "./core.js";
import {drawHand,poseLabel} from "./hand-view.js";
const $ = id => document.getElementById(id);
const gesture = new Gesture();
let detector, stream, running = false, starting = false, generation = 0, prepared = null, busy = false;
let lastFrame = -1, lastInference = 0;
const mode = () => document.querySelector('input[name="mode"]:checked').value;
const status = text => { $("status").textContent = text; };
async function request(message) {
  const response = await chrome.runtime.sendMessage(message);
  if (!response?.ok) throw new Error(response?.error || "No hubo respuesta de Chrome.");
  return response;
}
function cancelGrab() { generation++; prepared = null; gesture.reset(); }
async function refresh(preferred = Number($("target").value)) {
  const data = await request({type: "list"});
  $("target").replaceChildren(...data.windows.map(w => {
    const option = document.createElement("option"); option.value = w.id;
    option.textContent = `Ventana ${w.id} · ${w.tabs} pestaña(s)`; return option;
  }));
  const selected = data.windows.find(w => w.id === preferred) || data.windows.find(w => w.id === data.initialTarget) || data.windows[0];
  if (selected) $("target").value = selected.id;
  $("displays").textContent = [...data.displays].sort((a,b) => a.bounds.left-b.bounds.left)
    .map(d => `${d.name || "Pantalla"}: ${d.bounds.width} × ${d.bounds.height}`).join(" | ");
  if (!selected) throw new Error("Abrí una ventana normal de Chrome y pulsá Actualizar.");
}
async function move(direction, snapshot) {
  if (busy) return;
  busy = true; $("left").disabled = $("right").disabled = true;
  try {
    const result = await request({type: "move", windowId: Number($("target").value), mode: mode(), ...snapshot, direction});
    cancelGrab(); await refresh(result.windowId); status(result.message);
  } catch (error) { status(error.message); }
  finally { busy = false; $("left").disabled = $("right").disabled = false; }
}
$("left").onclick = () => { cancelGrab(); move("left"); };
$("right").onclick = () => { cancelGrab(); move("right"); };
$("refresh").onclick = () => { cancelGrab(); refresh().catch(e => status(e.message)); };
$("show").onclick = async () => {
  try { await chrome.windows.update(Number($("target").value), {focused: true}); }
  catch (error) { status(error.message); }
};
$("target").onchange = cancelGrab;
document.querySelectorAll('input[name="mode"],#invert').forEach(el => el.onchange = cancelGrab);

function stop() {
  running = false; cancelGrab();
  stream?.getTracks().forEach(track => track.stop()); stream = null;
  $("video").srcObject = null; $("start").disabled = starting; $("stop").disabled = true;
  drawHand($("handCanvas"),$("video"),null);
  $("cameraHint").textContent = "Cámara apagada"; status("Control pausado. La cámara está apagada.");
}
$("stop").onclick = stop;
document.addEventListener("keydown", event => { if (event.key === "Escape") stop(); });
window.addEventListener("pagehide", stop);
chrome.runtime.onMessage.addListener(message => { if (message.type === "stop-camera") stop(); });
$("start").onclick = async () => {
  if (starting || running) return;
  starting = true; cancelGrab(); const token = generation;
  $("start").disabled = true; $("stop").disabled = false; status("Preparando el detector local y la cámara…");
  try {
    if (!detector) {
      const {FilesetResolver, HandLandmarker} = await import("./vendor/vision_bundle.mjs");
      const files = await FilesetResolver.forVisionTasks(chrome.runtime.getURL("vendor/wasm"));
      detector = await HandLandmarker.createFromOptions(files, {
        baseOptions: {modelAssetPath: chrome.runtime.getURL("vendor/hand_landmarker.task"), delegate: "CPU"},
        runningMode: "VIDEO", numHands: 1, minHandDetectionConfidence: 0.65, minTrackingConfidence: 0.65,
      });
    }
    if (token !== generation) return;
    const camera = await navigator.mediaDevices.getUserMedia({video: {width: {ideal: 640}, height: {ideal: 480}}, audio: false});
    if (token !== generation) { camera.getTracks().forEach(t => t.stop()); return; }
    stream = camera; $("video").srcObject = stream; await $("video").play();
    if (token !== generation) return;
    running = true; lastFrame = -1; lastInference = 0;
    status("Cámara activa. Mostrá la mano abierta; cerrala para agarrar."); requestAnimationFrame(frame);
  } catch (error) { stop(); status(`No se pudo iniciar: ${error.message}. Revisá el permiso de cámara o si otra aplicación la está usando.`); }
  finally {
    if (!running) { stream?.getTracks().forEach(t => t.stop()); stream = null; $("video").srcObject = null; drawHand($("handCanvas"),$("video"),null); }
    starting = false; $("start").disabled = running; $("stop").disabled = !running;
  }
};
function frame(now) {
  if (!running) return;
  try {
    if (now - lastInference >= 65 && $("video").readyState >= 2 && $("video").currentTime !== lastFrame) {
      lastFrame = $("video").currentTime; lastInference = now;
      const result = detector.detectForVideo($("video"), now);
      const hand = result.landmarks?.[0];
      const event = gesture.update(hand, now);
      drawHand($("handCanvas"),$("video"),hand,!!gesture.grab);
      $("cameraHint").textContent = poseLabel(hand,!!gesture.grab);
      if (!gesture.grab && !event) prepared = null;
      if (event?.type === "grab" && !busy) {
        const token = ++generation; prepared = null;
        request({type: "prepare", windowId: Number($("target").value), mode: mode()}).then(snapshot => {
          if (token === generation && gesture.grab) prepared = snapshot;
        }).catch(error => { if (token === generation) { cancelGrab(); status(error.message); } });
      } else if (event?.type === "move") {
        const snapshot = prepared; prepared = null; generation++;
        if (snapshot) {
          const direction = $("invert").checked ? (event.direction === "right" ? "left" : "right") : event.direction;
          move(direction, snapshot);
        } else status("Gesto cancelado. Abrí la mano y repetí más despacio.");
      } else if (event?.type === "cancel") { prepared = null; generation++; }
    }
    requestAnimationFrame(frame);
  } catch (error) { stop(); status(`Detector detenido: ${error.message}`); }
}
refresh().then(() => status("Listo. Probá los botones con una ventana de prueba.")).catch(error => status(error.message));

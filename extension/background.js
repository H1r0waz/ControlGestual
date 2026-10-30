import {destination, fit} from "./core.js";

let moving = false;
async function animateWindow(window, bounds) {
  for(let frame=1;frame<10;frame++) {
    const t=frame/10,eased=t*t*(3-2*t);
    const rect=Object.fromEntries(Object.keys(bounds).map(key=>[key,Math.round(window[key]+(bounds[key]-window[key])*eased)]));
    try { await chrome.windows.update(window.id,rect); }
    catch { break; } // A desktop gap may reject an intermediate rectangle; still try the final destination.
    await new Promise(resolve=>setTimeout(resolve,24));
  }
  return chrome.windows.update(window.id,{...bounds,focused:true});
}
chrome.action.onClicked.addListener(async tab => {
  const saved = await chrome.storage.session.get("panelId");
  if (saved.panelId) {
    try { await chrome.windows.update(saved.panelId, {focused: true}); return; } catch { /* closed */ }
  }
  await chrome.storage.session.set({initialTarget: tab.windowId});
  const win = await chrome.windows.create({url: chrome.runtime.getURL("panel.html"), type: "popup", width: 580, height: 820});
  await chrome.storage.session.set({panelId: win.id});
});
chrome.commands.onCommand.addListener(command => {
  if (command === "pause-control") chrome.runtime.sendMessage({type: "stop-camera"}).catch(() => {});
});

export async function handle(message) {
  if (message.type === "list") {
    const windows = (await chrome.windows.getAll({populate: true, windowTypes: ["normal"]})).filter(w => !w.incognito);
    return {windows: windows.map(w => ({id: w.id, tabs: w.tabs.length})),
      displays: await chrome.system.display.getInfo(), ...(await chrome.storage.session.get("initialTarget"))};
  }
  if (message.type !== "prepare" && message.type !== "move") throw new Error("Acción desconocida.");
  if (!["window", "tab"].includes(message.mode) || !Number.isInteger(message.windowId)) throw new Error("Selección inválida.");
  const window = await chrome.windows.get(message.windowId, {populate: true});
  if (window.type !== "normal" || window.incognito) throw new Error("Elegí una ventana normal de Chrome.");
  if (window.state === "minimized" || window.state === "fullscreen") throw new Error("Restaurá la ventana o salí de pantalla completa primero.");
  const tab = window.tabs.find(t => t.active);
  if (!tab) throw new Error("No hay pestaña activa.");
  if (message.type === "prepare") return {windowId: window.id, tabId: tab.id, mode: message.mode};
  if (moving) throw new Error("Esperá a que termine el movimiento anterior.");
  if (message.mode === "tab" && message.tabId !== undefined && message.tabId !== tab.id) throw new Error("Cambió la pestaña activa; repetí el gesto.");
  moving = true;
  try {
    const display = destination(window, await chrome.system.display.getInfo(), message.direction);
    const bounds = fit(window, display);
    let moved;
    if (message.mode === "tab" && window.tabs.length > 1) {
      const created = await chrome.windows.create({left:window.left,top:window.top,width:window.width,height:window.height,tabId: tab.id, focused: true});
      moved = await animateWindow(created,bounds);
    } else {
      const start = window.state !== "normal" ? await chrome.windows.update(window.id, {state: "normal"}) : window;
      moved = await animateWindow(start,bounds);
    }
    if (window.state === "maximized") await chrome.windows.update(moved.id, {state: "maximized"});
    return {windowId: moved.id, message: `Movido a ${display.name || "la otra pantalla"}.`};
  } finally { moving = false; }
}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.id !== chrome.runtime.id || sender.url !== chrome.runtime.getURL("panel.html")) return;
  handle(message).then(value => reply({ok: true, ...value}), error => reply({ok: false, error: error.message}));
  return true;
});

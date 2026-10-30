// Uses the existing bundled Playwright; never loads the user's Chrome profile.
import {createRequire} from "node:module";
import {fileURLToPath} from "node:url";
import path from "node:path";
import fs from "node:fs";
import assert from "node:assert/strict";
const require=createRequire(import.meta.url);
const runtime=process.env.CONTROL_GESTUAL_NODE_MODULES;
if(!runtime)throw Error("Set CONTROL_GESTUAL_NODE_MODULES to the installed Playwright modules directory.");
const {chromium}=require(path.join(runtime,"playwright"));
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const extension=path.join(root,"extension");
fs.mkdirSync(path.join(root,"work"),{recursive:true});
const context=await chromium.launchPersistentContext("",{channel:"chromium",headless:true,executablePath:process.env.CONTROL_GESTUAL_CHROMIUM,
  ignoreDefaultArgs:["--disable-extensions"],
  args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`,"--use-fake-ui-for-media-stream","--use-fake-device-for-media-stream"]});
try {
  const worker=context.serviceWorkers()[0]||await context.waitForEvent("serviceworker");
  const id=new URL(worker.url()).host;
  // This Chromium build crashes on system.display in headless mode. Geometry is
  // simulated here; the camera runtime and extension loading remain real.
  await worker.evaluate(()=>{chrome.system.display.getInfo=async()=>[
    {id:"test-1",name:"Simulada izquierda",bounds:{left:0,top:0,width:400,height:600},workArea:{left:0,top:0,width:400,height:600}},
    {id:"test-2",name:"Simulada derecha",bounds:{left:400,top:0,width:400,height:600},workArea:{left:400,top:0,width:400,height:600}},
  ];});
  const target=await worker.evaluate(async()=>{
    const w=await chrome.windows.create({url:["about:blank","about:blank"],type:"normal",left:0,top:0,width:600,height:600});
    await chrome.storage.session.set({initialTarget:w.id});
    return {windowId:w.id,tabId:w.tabs.find(t=>t.active).id};
  });
  const panelEvent=context.waitForEvent("page");
  await worker.evaluate(()=>chrome.windows.create({url:chrome.runtime.getURL("panel.html"),type:"popup",width:580,height:820}));
  const page=await panelEvent;const errors=[];const requests=[];
  page.on("pageerror",e=>errors.push(e.message));
  page.on("request",r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});
  await page.waitForURL(`chrome-extension://${id}/panel.html`);
  await page.setViewportSize({width:580,height:820});
  await page.waitForFunction(()=>document.querySelector("#status").textContent.startsWith("Listo."));
  assert.ok(await page.locator("#target option").count());
  assert.equal(await page.locator("#video").evaluate(v=>v.srcObject),null);
  await page.locator('input[value="tab"]').check();
  await page.locator("#right").click();
  await page.waitForFunction(()=>!document.querySelector("#right").disabled);
  assert.match(await page.locator("#status").textContent(),/^Movido a/);
  const moved=await worker.evaluate(tabId=>chrome.tabs.get(tabId),target.tabId);
  assert.notEqual(moved.windowId,target.windowId);
  assert.equal(await page.locator("#target").inputValue(),String(moved.windowId));
  await page.locator('input[value="window"]').check();
  await page.locator("#left").click();
  await page.waitForFunction(()=>!document.querySelector("#left").disabled);
  assert.match(await page.locator("#status").textContent(),/^Movido a/);
  const returned=await worker.evaluate(id=>chrome.windows.get(id),moved.windowId);
  assert.equal(returned.id,moved.windowId);assert.equal(returned.left,0);
  await page.locator("#start").click();
  await page.waitForFunction(()=>/Cámara activa|No se pudo iniciar/.test(document.querySelector("#status").textContent),{},{timeout:90000});
  const cameraStatus=await page.locator("#status").textContent();
  assert.match(cameraStatus,/Cámara activa/);
  await page.waitForTimeout(1500);
  await page.locator("#video").evaluate(v=>{window.testCameraTracks=v.srcObject.getTracks();});
  await page.locator("#stop").click();
  assert.match(await page.locator("#status").textContent(),/apagada/);
  assert.equal(await page.locator("#video").evaluate(v=>v.srcObject),null);
  assert.equal(await page.evaluate(()=>window.testCameraTracks.every(t=>t.readyState==="ended")),true);
  assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
  await page.screenshot({path:path.join(root,"work","panel-check.png"),fullPage:true});
  console.log(JSON.stringify({panel:"loaded at 580px",tabTransfer:"real Chrome API; same tab ID; target updated",windowTransfer:"real Chrome API; moved back left",displays:"simulated; headless system.display crashes in this build",camera:"synthetic frames only; detector initialized",pause:"capture tracks ended",pageErrors:errors,externalPageRequests:requests}));
} finally {await context.close();}

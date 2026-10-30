import {test} from "node:test";
import assert from "node:assert/strict";
let windows, calls;
const displays=[{id:"1",bounds:{left:0,top:0,width:1920,height:1080},workArea:{left:0,top:0,width:1920,height:1040}},
  {id:"2",name:"Vertical",bounds:{left:1920,top:0,width:1080,height:1920},workArea:{left:1920,top:0,width:1080,height:1880}}];
globalThis.chrome={action:{onClicked:{addListener(){}}},commands:{onCommand:{addListener(){}}},
  runtime:{onMessage:{addListener(){}}},storage:{session:{get:async()=>({})}},
  system:{display:{getInfo:async()=>displays}},windows:{
    get:async id=>{if(!windows[id])throw Error("Window closed");return structuredClone(windows[id]);},
    update:async(id,values)=>{calls.push({action:"update",id,...values});Object.assign(windows[id],values);return windows[id];},
    create:async values=>{calls.push({action:"create",...values});windows[99]={id:99,...values};return windows[99];},
  }};
const {handle}=await import("../extension/background.js");
function setup(count=2,state="normal") {
  calls=[];windows={7:{id:7,type:"normal",state,left:0,top:0,width:1600,height:1000,
    tabs:Array.from({length:count},(_,i)=>({id:20+i,active:i===0}))}};
}
test("window moves without detaching its tabs",async()=>{
  setup();const result=await handle({type:"move",mode:"window",windowId:7,direction:"right"});
  assert.equal(result.windowId,7);assert.equal(calls.length,10);assert.equal(calls.at(-1).left,1920);
  assert.ok(calls[0].left>0&&calls[0].left<1920);
});
test("active tab is detached by its ID without copying a URL",async()=>{
  setup();const snapshot=await handle({type:"prepare",mode:"tab",windowId:7});
  const result=await handle({type:"move",...snapshot,direction:"right"});
  assert.equal(result.windowId,99);assert.equal(calls[0].action,"create");assert.equal(calls[0].tabId,20);
  assert.equal(calls[0].url,undefined);
});
test("single-tab windows move whole and maximized windows restore then maximize",async()=>{
  setup(1);await handle({type:"move",mode:"tab",windowId:7,direction:"right"});
  assert.equal(calls[0].action,"update");
  setup(2,"maximized");await handle({type:"move",mode:"window",windowId:7,direction:"right"});
  assert.equal(calls[0].state,"normal");assert.equal(calls.at(-1).state,"maximized");
});
test("changed tabs, fullscreen and missing destination cause no mutations",async()=>{
  setup();await assert.rejects(handle({type:"move",mode:"tab",windowId:7,tabId:21,direction:"right"}),/Cambió/);
  assert.equal(calls.length,0);
  setup(2,"fullscreen");await assert.rejects(handle({type:"move",mode:"window",windowId:7,direction:"right"}),/pantalla completa/);
  setup();await assert.rejects(handle({type:"move",mode:"window",windowId:7,direction:"left"}),/No hay otra/);
  assert.equal(calls.length,0);
});

import {makeHand} from "./hand-fixture.js";
import {test} from "node:test";
import assert from "node:assert/strict";
import {destination, fit, Gesture, handPose,calibrationFromSamples} from "../extension/core.js";

const displays = [
  {id:"1", bounds:{left:0,top:0,width:1920,height:1080}, workArea:{left:0,top:0,width:1920,height:1040}},
  {id:"2", bounds:{left:1920,top:0,width:1080,height:1920}, workArea:{left:1920,top:0,width:1080,height:1880}},
];
test("horizontal to portrait and back, without wrapping at an edge", () => {
  const window = {left:0,top:0,width:1600,height:1000};
  assert.equal(destination(window,displays,"right").id,"2");
  const moved = fit(window,displays[1]);
  assert.deepEqual(moved,{left:1920,top:440,width:1080,height:1000});
  assert.equal(destination(moved,displays,"left").id,"1");
  assert.throws(() => destination(window,displays,"left"),/No hay otra/);
  assert.throws(() => destination(window,displays.slice(0,1),"right"),/dos pantallas/);
  assert.throws(() => destination(window,displays,"up"),/inválida/);
});
test("negative monitor coordinates and disconnected displays", () => {
  const negative = displays.map(d => ({...d,bounds:{...d.bounds,left:d.bounds.left-1920},workArea:{...d.workArea,left:d.workArea.left-1920}}));
  assert.equal(destination({left:0,top:0,width:900,height:1000},negative,"left").id,"1");
  assert.throws(() => destination({left:0,top:0,width:900,height:1000},[{...displays[0],isEnabled:false},displays[1]],"left"),/dos pantallas/);
});

function grab(g,x=.7) {
  g.reset();
  g.update(makeHand(x,false),0);
  assert.equal(g.update(makeHand(x,true),100),null);
  assert.deepEqual(g.update(makeHand(x,true),240),{type:"grab"});
}
test("fist grabs only after open preparation and a stable close; opening releases right",()=>{
  const g=new Gesture();assert.equal(g.update(makeHand(.7,true),0),null);
  assert.equal(g.update(makeHand(.7,true),150),null);
  grab(g);g.update(makeHand(.5,true),400);
  assert.equal(g.update(makeHand(.4,false),500),null);
  assert.deepEqual(g.update(makeHand(.4,false),650),{type:"move",direction:"right"});
  assert.equal(g.update(makeHand(.4,true),800),null);
});
test("left release and partial hand never substitute for a fist",()=>{
  const g=new Gesture();grab(g,.3);g.update(makeHand(.5,true),400);g.update(makeHand(.6,false),500);
  assert.deepEqual(g.update(makeHand(.6,false),650),{type:"move",direction:"left"});
  const partial=makeHand(.5,true),open=makeHand(.5,false);
  partial[8]=open[8];partial[12]=open[12];
  assert.equal(handPose(partial).kind,"partial");
  const h=new Gesture();h.update(open,0);h.update(partial,100);assert.equal(h.update(partial,250),null);
});
test("short closure, small motion, momentary opening and tracking loss cannot commit",()=>{
  const g=new Gesture();g.update(makeHand(.7,false),0);g.update(makeHand(.7,true),100);
  assert.equal(g.update(makeHand(.7,false),180),null);assert.equal(g.grab,null);
  grab(g);g.update(makeHand(.65,false),400);
  assert.deepEqual(g.update(makeHand(.65,false),550),{type:"cancel"});
  const h=new Gesture();grab(h);h.update(makeHand(.4,false),400);h.update(makeHand(.4,true),450);
  assert.equal(h.update(makeHand(.4,true),600),null);
  assert.deepEqual(h.update(null,900),{type:"cancel"});
  assert.equal(h.update(makeHand(.4,false),1000),null);
});
test("frame gaps, invalid landmarks and timeout cancel safely",()=>{
  const g=new Gesture();grab(g);assert.equal(g.update(makeHand(.4,false),900),null);
  const h=new Gesture();grab(h);
  let event;for(let t=300;t<=4200;t+=100){event=h.update(makeHand(.4,true),t);if(event)break;}
  assert.deepEqual(event,{type:"cancel"});
  assert.equal(handPose([]),null);assert.equal(handPose(makeHand(.5).map(p=>({...p,x:NaN}))),null);
});
test("calibration separates poses, rejects poor captures and sensitivity changes distance",()=>{
  const open=handPose(makeHand(.5,false)).openness,closed=handPose(makeHand(.5,true)).openness;
  const profile=calibrationFromSamples(Array(30).fill(open),Array(30).fill(closed));
  assert.equal(handPose(makeHand(.5,false),profile).kind,"open");assert.equal(handPose(makeHand(.5,true),profile).kind,"fist");
  assert.throws(()=>calibrationFromSamples([open],[closed]),/muestras/);
  assert.throws(()=>calibrationFromSamples(Array(30).fill(open),Array(30).fill(open)),/distingue/);
  const g=new Gesture({threshold:.10,calibration:profile});grab(g);g.update(makeHand(.57,false),500);
  assert.deepEqual(g.update(makeHand(.57,false),650),{type:"move",direction:"right"});
});
test("downward release minimizes only when enabled; diagonal release cancels",()=>{
  const shifted=(x,closed,dy)=>makeHand(x,closed).map(p=>({...p,y:p.y+dy}));
  const g=new Gesture({minimize:true});grab(g);g.update(shifted(.7,false,.22),500);
  assert.deepEqual(g.update(shifted(.7,false,.22),650),{type:"minimize"});
  const h=new Gesture({minimize:true});grab(h);h.update(shifted(.4,false,.3),500);
  assert.deepEqual(h.update(shifted(.4,false,.3),650),{type:"cancel"});
  const defaultGesture=new Gesture();grab(defaultGesture);defaultGesture.update(shifted(.7,false,.22),500);
  assert.deepEqual(defaultGesture.update(shifted(.7,false,.22),650),{type:"cancel"});
});
test("upward release maximizes only when enabled and rejects diagonal movement",()=>{
  const shifted=(x,dy)=>makeHand(x,false).map(p=>({...p,y:p.y+dy}));
  const g=new Gesture({minimize:true,maximize:true});grab(g);g.update(shifted(.7,-.22),500);
  assert.deepEqual(g.update(shifted(.7,-.22),650),{type:"maximize"});
  const disabled=new Gesture({minimize:true});grab(disabled);disabled.update(shifted(.7,-.22),500);
  assert.deepEqual(disabled.update(shifted(.7,-.22),650),{type:"cancel"});
  const diagonal=new Gesture({minimize:true,maximize:true});grab(diagonal);diagonal.update(shifted(.4,-.3),500);
  assert.deepEqual(diagonal.update(shifted(.4,-.3),650),{type:"cancel"});
});
test("desktop tracking tolerates slow detection frames without forgetting the grip",()=>{
  const g=new Gesture({frameGap:1200});
  g.update(makeHand(.7,false),0);g.update(makeHand(.7,true),500);
  assert.deepEqual(g.update(makeHand(.7,true),1000),{type:"grab"});
  g.update(makeHand(.4,true),1500);g.update(makeHand(.4,false),2000);
  assert.deepEqual(g.update(makeHand(.4,false),2500),{type:"move",direction:"right"});
  const h=new Gesture({frameGap:1200});h.update(makeHand(.7,false),0);h.update(makeHand(.7,true),500);h.update(makeHand(.7,true),1000);
  assert.equal(h.update(makeHand(.4,false),2500),null);assert.equal(h.grab,null);
});

import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Gesture,handPose,gestureDirection,calibrationFromSamples} from '../extension/core.js';
import {makeHand,makeFingerHand} from './hand-fixture.js';

test('thumb contact identifies the touched finger regardless of scalar calibration',()=>{
  const calibration=calibrationFromSamples(Array(30).fill(handPose(makeHand(.5)).openness),Array(30).fill(handPose(makeHand(.5,true)).openness));
  for(const pose of ['index','victory','three','pinky']){
    const h=makeFingerHand(.5,pose);
    assert.equal(handPose(h,calibration).fingerPose,pose);
  }
});

function prepare(g,pose){
  g.update(makeHand(.65),0);
  g.update(makeFingerHand(.65,pose),100);
  g.update(makeFingerHand(.65,pose),300);
  assert.deepEqual(g.update(makeFingerHand(.65,pose),470),{type:'grab'});
}
test('each thumb contact captures, moves and confirms once when released',()=>{
  for(const [pose,x,dy,direction] of [['index',.35,0,'right'],['victory',.65,-.23,'up'],['three',.35,.23,'bottom_right'],['pinky',.35,0,'right'],['pinky',.95,0,'left']]){
    const g=new Gesture({fingers:true,frameGap:1200});prepare(g,pose);
    g.update(makeFingerHand(x,pose,dy),600);
    const open=makeHand(x).map(p=>({...p,y:p.y+dy}));
    assert.equal(g.update(open,700),null);
    assert.deepEqual(g.update(open,850),{type:'finger',pose,direction});
    assert.equal(g.update(makeFingerHand(x,pose,dy),900),null);
  }
});
test('finger gestures reject unarmed, unstable, unknown, short and lost movements',()=>{
  const g=new Gesture({fingers:true,frameGap:1200});
  g.update(makeFingerHand(.6,'index'),0);assert.equal(g.update(makeFingerHand(.6,'index'),500),null);
  g.update(makeHand(.6),600);g.update(makeFingerHand(.6,'index'),700);g.update(makeFingerHand(.6,'victory'),900);
  assert.equal(g.update(makeFingerHand(.6,'victory'),1100),null);assert.equal(g.grab,null);
  const unknown=makeHand(.6,true),open=makeHand(.6);unknown[20]=open[20];
  g.update(unknown,1200);assert.equal(g.update(unknown,1700),null);assert.equal(g.grab,null);
  const short=new Gesture({fingers:true,frameGap:1200});prepare(short,'index');short.update(makeHand(.65),600);
  assert.deepEqual(short.update(makeHand(.65),750),{type:'cancel'});
  const lost=new Gesture({fingers:true,frameGap:1200});prepare(lost,'index');assert.deepEqual(lost.update(null,800),{type:'cancel'});
});
test('thumb and ring finger require a clear diagonal and all corners use intuitive directions',()=>{
  assert.equal(gestureDirection(.3,0,.18,'three'),null);
  assert.equal(gestureDirection(.5,.18,.18,'three'),null);
  for(const [dx,dy,direction] of [[-.25,-.25,'top_left'],[.25,-.25,'top_right'],[-.25,.25,'bottom_left'],[.25,.25,'bottom_right']])assert.equal(gestureDirection(dx,dy,.18,'three'),direction);
  assert.equal(gestureDirection(.25,.25,.18,'index'),null);
});

test('extended-finger combinations no longer select actions; touching fingers in a fist stays a fist',()=>{
  for(const count of [1,2,3]){
    const h=makeHand(.5,true),open=makeHand(.5);
    for(const tip of [8,12,16].slice(0,count))h[tip]=open[tip];
    assert.equal(handPose(h).fingerPose,null);
  }
  const h=makeHand(.65,true);h[4]={...h[8]};
  const g=new Gesture({fingers:true});g.update(makeHand(.65),0);g.update(h,100);
  assert.deepEqual(g.update(h,240),{type:'grab'});assert.equal(g.grab.pose,'fist');
});

test('contact uses palm-relative distance, needs stable release, and rejects switching contacts',()=>{
  for(const factor of [.5,1,1.5]){
    const h=makeFingerHand(.5,'victory').map(p=>({x:.5+(p.x-.5)*factor,y:.5+(p.y-.5)*factor}));
    assert.equal(handPose(h).fingerPose,'victory');
  }
  const g=new Gesture({fingers:true,frameGap:1200});prepare(g,'index');
  const near=makeFingerHand(.35,'index');near[4].x=near[8].x+.07;near[4].y=near[8].y;
  assert.equal(g.update(near,600),null);assert.equal(g.opening,null);
  const released=makeFingerHand(.35,'index');released[4].x-=.16;
  g.update(released,700);g.update(near,780);g.update(released,850);
  assert.equal(g.update(released,950),null);
  assert.deepEqual(g.update(released,1000),{type:'finger',pose:'index',direction:'right'});
  const changed=new Gesture({fingers:true,frameGap:1200});prepare(changed,'index');
  assert.deepEqual(changed.update(makeFingerHand(.35,'victory'),600),{type:'cancel'});
});

test('ambiguous contacts and tracking loss never execute an action',()=>{
  const h=makeFingerHand(.5,'index');h[12]={...h[8]};
  assert.equal(handPose(h).fingerPose,null);assert.equal(handPose(h).ambiguousPinch,true);
  const g=new Gesture({fingers:true,frameGap:1200});prepare(g,'index');
  assert.deepEqual(g.update(h,600),{type:'cancel'});
  const pinky=makeHand(.5);pinky[4]={...pinky[20]};
  assert.equal(handPose(pinky).fingerPose,'pinky');assert.equal(handPose(pinky).contactPose,'pinky');
});

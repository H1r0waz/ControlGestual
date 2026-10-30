import {handPose} from "./core.js";
const bones=[[0,1,2,3,4],[0,5,6,7,8],[5,9,10,11,12],[9,13,14,15,16],[13,17,18,19,20],[0,17]];
export function drawHand(canvas,video,hand,holding=false,calibration=null) {
  const width=video.videoWidth||640,height=video.videoHeight||480;
  if(canvas.width!==width)canvas.width=width;if(canvas.height!==height)canvas.height=height;
  const ctx=canvas.getContext("2d");ctx.clearRect(0,0,width,height);
  const pose=handPose(hand,calibration);canvas.dataset.detected=String(!!pose);canvas.dataset.pose=pose?.fingerPose||pose?.kind||"none";
  if(!pose)return;
  ctx.setLineDash([]);ctx.strokeStyle=holding?"#ffca62":"#50f2ae";ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=3;
  for(const chain of bones){ctx.beginPath();chain.forEach((i,n)=>ctx[n?"lineTo":"moveTo"](hand[i].x*width,hand[i].y*height));ctx.stroke();}
  for(const point of hand){ctx.beginPath();ctx.arc(point.x*width,point.y*height,4,0,Math.PI*2);ctx.fill();}
  if(pose.fingerPose){
    ctx.strokeStyle='#8cb9ff';ctx.lineWidth=4;
    for(const i of [4,{index:8,victory:12,three:16,pinky:20}[pose.fingerPose]]){ctx.beginPath();ctx.arc(hand[i].x*width,hand[i].y*height,10,0,Math.PI*2);ctx.stroke();}
  }
  const xs=hand.map(p=>p.x*width),ys=hand.map(p=>p.y*height);
  ctx.setLineDash([8,5]);ctx.strokeRect(Math.min(...xs)-12,Math.min(...ys)-12,Math.max(...xs)-Math.min(...xs)+24,Math.max(...ys)-Math.min(...ys)+24);
}
export function poseLabel(hand,holding=false,calibration=null) {
  const pose=handPose(hand,calibration);
  return !pose?"Sin mano detectada":holding?"Mano detectada · gesto capturado · separá los dedos o abrí el puño para confirmar":
    pose.fingerPose?"Contacto detectado · "+({index:'pulgar + índice',victory:'pulgar + medio',three:'pulgar + anular',pinky:'pulgar + meñique'})[pose.fingerPose]:
    pose.kind==="fist"?"Mano detectada · puño cerrado":pose.kind==="open"?"Mano detectada · abierta":"Mano detectada · completá abrir o cerrar";
}

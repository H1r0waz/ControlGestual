export function overlap(a, b) {
  return Math.max(0, Math.min(a.left + a.width, b.left + b.width) - Math.max(a.left, b.left)) *
    Math.max(0, Math.min(a.top + a.height, b.top + b.height) - Math.max(a.top, b.top));
}

export function destination(window, displays, direction) {
  if (!["left", "right"].includes(direction)) throw new Error("Dirección inválida.");
  const active = displays.filter(d => d.isEnabled !== false && d.activeState !== "inactive");
  if (active.length < 2) throw new Error("Se necesitan dos pantallas en modo extendido.");
  const current = [...active].sort((a, b) => overlap(window, b.bounds) - overlap(window, a.bounds))[0];
  const cx = current.bounds.left + current.bounds.width / 2;
  const candidates = active.filter(d => d.id !== current.id &&
    (direction === "right" ? d.bounds.left + d.bounds.width / 2 > cx : d.bounds.left + d.bounds.width / 2 < cx));
  candidates.sort((a, b) => Math.abs(a.bounds.left + a.bounds.width / 2 - cx) - Math.abs(b.bounds.left + b.bounds.width / 2 - cx));
  if (!candidates.length) throw new Error(`No hay otra pantalla a la ${direction === "right" ? "derecha" : "izquierda"}.`);
  return candidates[0];
}

export function fit(window, display) {
  const area = display.workArea;
  const width = Math.min(window.width, area.width);
  const height = Math.min(window.height, area.height);
  return {left: Math.round(area.left + (area.width - width) / 2),
    top: Math.round(area.top + (area.height - height) / 2), width: Math.round(width), height: Math.round(height)};
}

export function handPose(hand, calibration=null) {
  if (!hand || hand.length !== 21 || hand.some(p => !Number.isFinite(p.x) || !Number.isFinite(p.y))) return null;
  const distance = (a,b) => Math.hypot(a.x-b.x,a.y-b.y);
  const palm = distance(hand[5],hand[17]);
  if (palm < .035) return null;
  let extended=0,folded=0,openness=0;const fingers=[];
  for(const [base,joint,tip] of [[5,6,8],[9,10,12],[13,14,16],[17,18,20]]) {
    openness+=distance(hand[0],hand[tip])/Math.max(.01,distance(hand[0],hand[joint]))/4;
    const up=distance(hand[base],hand[tip]) > distance(hand[base],hand[joint])*1.5 &&
       distance(hand[0],hand[tip]) > distance(hand[0],hand[joint])*1.1;
    const down=distance(hand[0],hand[tip]) < distance(hand[0],hand[joint])*1.08 &&
       distance(hand[base],hand[tip]) < palm*.95;
    if(up)extended++;if(down)folded++;fingers.push(up?'1':down?'0':'?');
  }
  const kind=calibration?(openness>=calibration.open?"open":openness<=calibration.closed?"fist":"partial"):
    extended>=3&&folded<=1?"open":folded>=3&&extended<=1?"fist":"partial";
  // Keep the stored family IDs so existing action assignments survive the gesture change.
  const pinchDistances=Object.fromEntries([['index',8],['victory',12],['three',16],['pinky',20]].map(([name,tip])=>[name,distance(hand[4],hand[tip])/palm]));
  const contacts=Object.keys(pinchDistances).filter(name=>pinchDistances[name]<=.28);
  const contactPose=contacts.length===1&&extended>=2?contacts[0]:null;
  const fingerPose=contactPose;
  return {kind,fingerPose,contactPose,pinchDistances,ambiguousPinch:extended>=2&&contacts.length>1,extended,fingerPattern:fingers.join(''),openness,x:1-[0,5,9,13,17].reduce((sum,index)=>sum+hand[index].x,0)/5,
    y:[0,5,9,13,17].reduce((sum,index)=>sum+hand[index].y,0)/5};
}

export function gestureDirection(dx,dy,threshold,pose='fist') {
  if(pose==='three')return Math.abs(dx)>=threshold&&Math.abs(dy)>=threshold&&Math.min(Math.abs(dx),Math.abs(dy))>=Math.max(Math.abs(dx),Math.abs(dy))*.45?
    (dy>0?'bottom_':'top_')+(dx>0?'right':'left'):null;
  return Math.abs(dy)>=threshold&&Math.abs(dy)>Math.abs(dx)*1.2?(dy>0?'down':'up'):
    Math.abs(dx)>=threshold&&Math.abs(dx)>=Math.abs(dy)*1.2?(dx>0?'right':'left'):null;
}

export function calibrationFromSamples(openSamples,closedSamples) {
  const median=values=>{const sorted=[...values].sort((a,b)=>a-b);return sorted[Math.floor(sorted.length/2)];};
  if([openSamples,closedSamples].some(a=>a.length<15||a.some(n=>!Number.isFinite(n)||n<=0||n>4))) throw Error("Faltan muestras claras. Mantené la mano visible y repetí.");
  const open=median(openSamples),closed=median(closedSamples),gap=open-closed;
  if(gap<.25)throw Error("No se distingue mano abierta y puño. Repetí con mejor iluminación.");
  if([openSamples,closedSamples].some(a=>median(a.map(n=>Math.abs(n-median(a))))>gap*.3))throw Error("La mano cambió demasiado durante la captura. Repetí manteniéndola quieta.");
  return {closed:closed+gap*.25,open:open-gap*.25};
}

// Palm position stays stable when fingers open or close. Brief pose changes do not commit.
export class Gesture {
  constructor(options={}) { this.cooldown = 0; this.fingers=options.fingers??false; this.threshold=options.threshold??.18; this.calibration=options.calibration??null; this.minimize=options.minimize??false; this.maximize=options.maximize??false; this.frameGap=options.frameGap??300; this.reset(); }
  reset() { this.armed = false; this.grab = null; this.lastSeen = null; this.closing=null; this.opening=null; }
  update(hand, now) {
    if (!hand) {
      if (this.lastSeen !== null && now - this.lastSeen > 250) {
        const hadGrab=!!this.grab;this.reset();return hadGrab?{type:"cancel"}:null;
      }
      return null;
    }
    if (this.lastSeen !== null && now - this.lastSeen > this.frameGap) this.reset();
    this.lastSeen = now;
    const pose=handPose(hand,this.calibration);
    if (!pose) {
      const hadGrab = !!this.grab; this.reset();
      return hadGrab ? {type: "cancel"} : null;
    }
    const x=pose.x;
    // Thumb contacts take precedence over scalar open/fist calibration.
    const fingerPose=this.fingers?pose.fingerPose:null;
    const kind=this.fingers&&(pose.contactPose||pose.ambiguousPinch||!['0000','1111'].includes(pose.fingerPattern))?'partial':pose.kind;
    const candidate=fingerPose||(kind==='fist'?'fist':null);
    if (now < this.cooldown) return null;
    if (!this.grab) {
      if (kind === "open") this.armed = true;
      if(this.closing?.pose!==candidate)this.closing=null;
      if(this.armed&&candidate&&!this.closing) this.closing={x,y:pose.y,start:now,pose:candidate};
      if (this.closing && now-this.closing.start>=(candidate==='fist'?120:350)) {
        this.grab = this.closing; this.closing=null; this.armed = false;
        return {type: "grab"};
      }
      return null;
    }
    const elapsed = now - this.grab.start;
    if (elapsed > 4000) { this.reset(); return {type: "cancel"}; }
    const heldPose=this.grab.pose;
    if(heldPose!=='fist'&&(pose.ambiguousPinch||(pose.contactPose&&pose.contactPose!==heldPose))){this.reset();return {type:'cancel'};}
    const released=heldPose==='fist'?kind==='open':pose.pinchDistances[heldPose]>=.45&&pose.extended>=2;
    if(!released) this.opening=null;
    if(released&&this.opening===null) this.opening=now;
    if (this.opening!==null&&now-this.opening>=120) {
      const dx = x - this.grab.x;
      const dy=pose.y-this.grab.y;
      this.reset(); this.cooldown = now + 1500;
      if(heldPose!=='fist'){
        const direction=gestureDirection(dx,dy,this.threshold,heldPose);
        return elapsed>=250&&direction?{type:'finger',pose:heldPose,direction}:{type:'cancel'};
      }
      if(this.minimize&&elapsed>=250&&dy>=this.threshold&&dy>Math.abs(dx)*1.2)return {type:"minimize"};
      if(this.maximize&&elapsed>=250&&-dy>=this.threshold&&-dy>Math.abs(dx)*1.2)return {type:"maximize"};
      return elapsed >= 250 && Math.abs(dx) >= this.threshold && (!(this.minimize||this.maximize)||Math.abs(dx)>=Math.abs(dy)*1.2)
        ? {type: "move", direction: dx > 0 ? "right" : "left"} : {type: "cancel"};
    }
    return null;
  }
}

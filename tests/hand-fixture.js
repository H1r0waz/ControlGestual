// Synthetic landmarks for logic/UI tests, never evidence of physical-camera accuracy.
export function makeHand(x,closed=false) {
  const h=Array.from({length:21},()=>({x,y:.7}));h[0]={x,y:.88};
  h[1]={x:x-.1,y:.8};h[2]={x:x-.15,y:.7};h[3]={x:x-.18,y:.6};h[4]={x:x-.2,y:.55};
  for(const [base,offset,y,tipY] of [[5,-.09,.65,.25],[9,-.03,.63,.20],[13,.04,.65,.25],[17,.10,.68,.34]]) {
    h[base]={x:x+offset,y};h[base+1]={x:x+offset,y:y-.16};
    h[base+3]={x:x+offset,y:closed?.72:tipY};
    h[base+2]={x:x+offset,y:(h[base+1].y+h[base+3].y)/2};
  }
  return h;
}

export function makeFingerHand(x,pose,dy=0) {
  const h=makeHand(x,false),tip={index:8,victory:12,three:16,pinky:20}[pose];
  h[tip]={x:h[tip].x,y:.70};h[tip-1]={x:h[tip].x,y:.60};
  h[4]={x:h[tip].x+.02,y:.71};
  return h.map(p=>({...p,y:p.y+dy}));
}

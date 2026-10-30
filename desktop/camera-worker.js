// Camera frames arrive independently of page rendering, including a hidden panel.
let reader,detector,canvas,context,gesture,running=false,last=0,lastCheck=0,epoch=0,disabled=false;
self.onmessage=async({data})=>{
  try{
    if(data.type==="init"){
      const {Gesture}=await import('/core.js');
      gesture=new Gesture({fingers:true,minimize:true,maximize:true,frameGap:1200,threshold:(data.settings?.sensitivity??18)/100,calibration:data.settings?.calibration??null});
      epoch=data.epoch??0;
      const {FilesetResolver,HandLandmarker}=await import("/vendor/vision_bundle.mjs");
      canvas=new OffscreenCanvas(640,480);context=canvas.getContext("2d");
      detector=await HandLandmarker.createFromOptions(await FilesetResolver.forVisionTasks("/vendor/wasm"),{
        baseOptions:{modelAssetPath:"/vendor/hand_landmarker.task",delegate:"CPU"},canvas:new OffscreenCanvas(1,1),
        runningMode:"VIDEO",numHands:1,minHandDetectionConfidence:.65,minTrackingConfidence:.65,
      });
      self.postMessage({type:"ready"});
    }else if(data.type==="reset"){
      epoch=data.epoch;gesture?.reset();
    }else if(data.type==="configure"){
      epoch=data.epoch;disabled=!!data.disabled;
      if(gesture){gesture.threshold=data.settings.sensitivity/100;gesture.calibration=data.settings.calibration;gesture.reset();}
    }else if(data.type==="stream"){
      reader=data.readable.getReader();running=true;
      while(running){
        const {value:frame,done}=await reader.read();if(done)break;
        try{
          const now=performance.now();if(now-last<65)continue;last=now;
          if(now-lastCheck>500){
            lastCheck=now;
            const response=await fetch('/api/state',{headers:{'X-Control-Key':data.key}});
            if(!response.ok)throw Error('Se perdió la conexión con el control local.');
            const state=await response.json();
            if(!state.armed||state.emergency!==data.emergency){running=false;self.postMessage({type:'paused'});break;}
          }
          if(canvas.width!==frame.displayWidth)canvas.width=frame.displayWidth;
          if(canvas.height!==frame.displayHeight)canvas.height=frame.displayHeight;
          context.drawImage(frame,0,0);
          const result=detector.detectForVideo(canvas,now);
          const hand=result.landmarks?.[0]||null;
          const event=disabled?null:gesture.update(hand,performance.now());
          self.postMessage({type:"hand",hand,now:performance.now(),event,grab:gesture.grab,epoch});
        }finally{frame.close();}
      }
      if(running)self.postMessage({type:"error",error:"La cámara dejó de enviar imágenes."});
    }
  }catch(error){self.postMessage({type:"error",error:error.message});}
};

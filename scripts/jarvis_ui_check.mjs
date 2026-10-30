import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const root=path.resolve(import.meta.dirname,'..');
const require=createRequire(import.meta.url);
const {chromium}=require(path.join(process.env.CONTROL_GESTUAL_NODE_MODULES,'playwright'));
const output=path.join(root,'work','jarvis-ui');fs.mkdirSync(output,{recursive:true});
const child=spawn(path.join(root,'releases/ControlGestual-V5.3/ControlGestual-V5.3.exe'),['--verify-build'],{stdio:['pipe','pipe','pipe'],windowsHide:true});
let browser;
try{
  const session=await new Promise((resolve,reject)=>{let buffer='';const timeout=setTimeout(()=>reject(Error('Startup timeout')),20000);child.on('error',reject);child.stdout.on('data',data=>{buffer+=data;if(buffer.includes('\n')){clearTimeout(timeout);resolve(JSON.parse(buffer.split('\n')[0]));}});});
  browser=await chromium.launch({headless:true,executablePath:process.env.CONTROL_GESTUAL_CHROMIUM});
  const page=await browser.newPage({viewport:{width:1440,height:1050}});const errors=[];page.on('pageerror',error=>errors.push(error.message));
  let override=null,physicalStarts=0;
  await page.route('**/api/**',async route=>{
    if(/\/api\/(voice\/start|ai\/start)/.test(route.request().url())){physicalStarts++;return route.abort();}
    if(route.request().url().endsWith('/api/state')){const response=await route.fetch();const state=await response.json();return route.fulfill({json:{...state,last:{title:'Ventana de demostración'},recovery:null,...override}});}
    return route.continue();
  });
  await page.goto(session.origin+'/#'+session.key);await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Listo.'));
  await page.locator('#openAssistant').click();assert.equal(await page.locator('#panel-microphone').isVisible(),true);assert.equal(physicalStarts,0);
  await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(output,'Jarvis-5.3-desktop.png')});
  for(const width of [360,390,650,1440]){
    await page.setViewportSize({width,height:900});
    for(const tab of ['gestures','microphone','phone']){
      await page.locator('#tab-'+tab).click();
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`${width}px ${tab} overflows`);
    }
  }
  await page.setViewportSize({width:390,height:900});await page.locator('#openAssistant').click();await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(output,'Jarvis-5.3-mobile.png')});
  for(const [mode,state] of [
    ['thinking',{ai:{enabled:true,busy:true}}],['starting',{ai:{starting:true}}],
    ['speaking',{speech:{speaking:true}}],['confirm',{assistant:{sequence:-1,turns:[],choices:[],confirmation:'Ventana de prueba'}}],
    ['listening',{voice:{active:true,level:42}}],['paused',{voice:{active:true,paused:true}}],['idle',{}]
  ]){
    override={ai:{},voice:{},speech:{},assistant:{sequence:-1,turns:[],choices:[]},...state};
    await page.waitForFunction(value=>document.querySelector('#jarvisCore').dataset.mode===value,mode);
  }
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await page.locator('.ringA').evaluate(el=>getComputedStyle(el).animationName),'none');
  assert.equal(physicalStarts,0);assert.deepEqual(errors,[]);
  console.log(JSON.stringify({responsive:[360,390,650,1440],states:7,reducedMotion:'passed',assistantNavigation:'passed',hardwareStarted:false,pageErrors:errors,screenshots:output}));
}finally{await browser?.close();child.kill();}

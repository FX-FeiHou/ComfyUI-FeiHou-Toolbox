const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
(async () => {
 const browser = await chromium.launch({headless:true,channel:'msedge'});
 try {
  const page = await browser.newPage();
  let requests = 0;
  page.on('request', () => requests++);
  await page.setContent('<canvas width="800" height="600"></canvas><section></section>');
  await page.evaluate(() => {
   globalThis.app = {
    registerExtension(ext) { globalThis.ext=ext; },
    ui:{settings:{getSettingValue:()=> 'en'}},
    canvas:{canvas:document.querySelector('canvas'),convertEventToCanvasOffset:e=>[e.clientX,e.clientY],graph:{getNodeOnPos:x=>x<400?globalThis.node:null}}
   };
   globalThis.api={apiURL:x=>x};
   globalThis.imported=0;
   document.addEventListener('drop',()=>globalThis.imported++,true);
   globalThis.Node=class {
    constructor(){this.type='FeiHouVideoPreview';this.size=[320,300];this.widgets=[];this.inputs=[];this.graph={setDirtyCanvas(){}};}
    addDOMWidget(name,type,element){document.querySelector('section').append(element);const w={name};this.widgets.push(w);return w;}
    addWidget(type,name,value,callback){const w={type,name,value,callback,options:{}};this.widgets.push(w);return w;}
    setSize(size){this.size=size;}
    computeSize(){return this.size;}
   };
  });
  const source=fs.readFileSync(path.join(__dirname,'../js/video_preview.js'),'utf8').replace(/^import .*;\r?\n/gm,'');
  await page.addScriptTag({content:source});
  const result=await page.evaluate(() => {
   ext.setup();ext.beforeRegisterNodeDef(Node,{name:'FeiHouVideoPreview'});
   globalThis.node=new Node();node.onNodeCreated();
   const preview=node.widgets.find(w=>w.name==='videopreview');
   const original=preview.showLocalFile;let loaded=0;
   preview.showLocalFile=function(file){loaded++;return original.call(this,file);};
   function drop(target,x,fileName='metadata-video.mp4'){
    const dt=new DataTransfer();dt.items.add(new File(['fixture'],fileName,{type:'video/mp4'}));
    const e=new DragEvent('drop',{bubbles:true,cancelable:true,composed:true,clientX:x,clientY:50,dataTransfer:dt});target.dispatchEvent(e);return e.defaultPrevented;
   }
   const canvasHandled=drop(app.canvas.canvas,100);
   const domHandled=drop(preview.videoEl,100);
   const blob=preview.videoEl.src.startsWith('blob:');
   const outsideHandled=drop(app.canvas.canvas,600);
   const info={};node.onSerialize(info);
   const copy=new Node();copy.onNodeCreated();copy.onConfigure(info);
   return {canvasHandled,domHandled,outsideHandled,loaded,imported,blob,copy:copy.widgets.find(w=>w.name==='videopreview').videoEl.src===preview.videoEl.src};
  });
  if(!result.canvasHandled||!result.domHandled||result.outsideHandled||result.loaded!==2||result.imported!==1||!result.blob||!result.copy||requests)throw Error(JSON.stringify({result,requests}));
  console.log('PASS: node canvas/DOM drops intercepted, outside workflow import preserved, blob preview copied, zero network requests');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});

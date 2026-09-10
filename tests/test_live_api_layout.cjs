const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1200}});
  await page.route('**/*',async route=>{
   if(!['GET','HEAD','OPTIONS'].includes(route.request().method()))return route.fulfill({status:403,body:'Read-only layout test'});
   const filename=new URL(route.request().url()).pathname.split('/').pop();
   if(['feihou_api_media.js','feihou_api_nodes.js','feihou_api_media.css'].includes(filename)){
    return route.fulfill({contentType:filename.endsWith('.css')?'text/css':'application/javascript',body:fs.readFileSync(path.join(__dirname,'../js',filename))});
   }
   return route.continue();
  });
  await page.goto('http://127.0.0.1:8188',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>globalThis.LiteGraph?.registered_node_types?.FeiHouApiMediaLoader,{},{timeout:30000});
  await page.waitForTimeout(2500);
  const state=await page.evaluate(async()=>{
   const {app}=await import('/scripts/app.js');
   app.graph.clear();
   const loader=LiteGraph.createNode('FeiHouApiMediaLoader'),gen=LiteGraph.createNode('FeiHouApiImage');
   app.graph.add(loader);app.graph.add(gen);loader.pos=[100,210];gen.pos=[650,210];loader.connect(0,gen,0);
   // Simulate the extra socket retained in old workflows.
   gen.addInput('image','IMAGE');gen.onConfigure?.({});
   app.canvas.ds.scale=1;app.canvas.ds.offset=[0,0];app.canvas.selectNode(loader);app.canvas.setDirty(true,true);app.canvas.draw(true,true);
   globalThis.layoutTest={app,loader,gen};
   return {loaderTitle:loader.title,inputs:gen.inputs.map(i=>i.name),nativeType:gen.widgets.find(w=>w.name==='prompt').type,
    hidden:[loader,gen].map(n=>{const w=n.widgets.find(w=>w.name==='media_files');return w.hidden&&w.options.hidden&&w.type==='hidden'}),
    customPrompt:gen.widgets.some(w=>w.name==='feihou_api_prompt')};
  });
  if(state.loaderTitle!=='FeiHou-API Media'||state.inputs.includes('image')||state.customPrompt||state.hidden.some(x=>!x))throw Error(JSON.stringify(state));
  if(state.nativeType==='converted-widget'||state.nativeType==='hidden')throw Error('Native prompt remains hidden');
  await page.waitForTimeout(700);
  const corner=await page.evaluate(()=>{
   const {app,loader}=layoutTest,r=app.canvas.canvas.getBoundingClientRect(),ds=app.canvas.ds;
   return {x:r.left+(loader.pos[0]+loader.size[0]+ds.offset[0])*ds.scale-3,y:r.top+(loader.pos[1]+loader.size[1]+ds.offset[1])*ds.scale-3,size:[...loader.size]};
  });
  await page.mouse.move(corner.x,corner.y);
  await page.mouse.down();await page.mouse.move(corner.x+70,corner.y+50,{steps:8});await page.mouse.up();
  const resized=await page.evaluate(()=>[...layoutTest.loader.size]);
  if(resized[0]<=corner.size[0]&&resized[1]<=corner.size[1]){
   console.log(await page.evaluate(({x,y})=>({element:document.elementFromPoint(x,y)?.outerHTML.slice(0,700),canvas:layoutTest.app.canvas.canvas.getBoundingClientRect().toJSON(),scale:layoutTest.app.canvas.ds.scale,offset:[...layoutTest.app.canvas.ds.offset]}),corner));
   await page.screenshot({path:'F:/Codex/fddl/api-layout-debug.png'});
   throw Error('Lower-right resize did not grow: '+JSON.stringify({corner,resized}));
  }
  const left=await page.locator('[data-resize-corner="left"]').boundingBox();
  await page.mouse.move(left.x+3,left.y+left.height-3);await page.mouse.down();await page.mouse.move(left.x-45,left.y+left.height+25,{steps:6});await page.mouse.up();
  const leftResized=await page.evaluate(()=>[...layoutTest.loader.size]);
  if(leftResized[0]<=resized[0])throw Error('Lower-left resize failed');
  await page.evaluate(()=>{
   const {loader}=layoutTest;
   loader.widgets.find(w=>w.name==='media_files').value=JSON.stringify([{media_type:'image',ordinal:1,filename:'test-reference.png',storage:'input'}]);loader._fhMediaPanel.restore();
  });
  const prompt=page.locator('textarea:visible').first();await prompt.fill('Test @im');await prompt.press('Enter');
  if(await prompt.inputValue()!=='Test @image1 ')throw Error('Native textarea mention failed');
  const submitted=await page.evaluate(async()=>{
   const {app,loader,gen}=layoutTest;
   const result=await app.graphToPrompt();
   const record=JSON.parse(result.output[String(loader.id)].inputs.media_files);
   const mediaLink=result.output[String(gen.id)].inputs.media;
   const panel=document.querySelector('.fh-api-loader').getBoundingClientRect();
   const grid=document.querySelector('.fh-h3-media-gallery').getBoundingClientRect();
   const last=document.querySelector('.fh-h3-audio-trim-grid').getBoundingClientRect();
   return {files:record.length,linked:mediaLink[0]===String(loader.id)||mediaLink[0]===loader.id,left:grid.left-panel.left,right:panel.right-grid.right,bottom:panel.bottom-last.bottom};
  });
  if(submitted.files!==1||!submitted.linked)throw Error('Media record is missing from API submission');
  if(Math.abs(submitted.left-submitted.right)>2||submitted.bottom>34){console.log(await page.evaluate(()=>['.fh-api-loader','.fh-h3-embedded-workbench','.fh-h3-media-gallery'].map(s=>{const el=document.querySelector(s),c=getComputedStyle(el);return {s,rect:el.getBoundingClientRect().toJSON(),width:c.width,margin:c.margin,padding:c.padding,box:c.boxSizing,css:el.style.cssText}})));throw Error('Unbalanced layout: '+JSON.stringify(submitted));}
  console.log('PASS: API serialization and responsive spacing',JSON.stringify(submitted));
  console.log('PASS: real ComfyUI native prompt and @, hidden records, legacy socket cleanup, title and both lower resize corners',JSON.stringify(state));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});

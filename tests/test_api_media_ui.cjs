const {chromium}=require('playwright');
const fs=require('fs'),path=require('path');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 try{
  const page=await browser.newPage();
  await page.setContent('<main style="display:flex;gap:30px;background:#222"></main>');
  const css=fs.readFileSync(path.join(__dirname,'../js/feihou_api_media.css'),'utf8');
  await page.route('**/feihou_api_media.css',route=>route.fulfill({contentType:'text/css',body:css}));
  await page.addStyleTag({content:css});
  let source=fs.readFileSync(path.join(__dirname,'../js/feihou_api_media.js'),'utf8')
   .replace('import { api } from "../../scripts/api.js";','const api=globalThis.testApi;')
   .replaceAll('import.meta.url','"https://test.local/media.js"')
   .replace(/export function (\w+)/g,'globalThis.$1 = function $1');
  await page.evaluate(()=>{
   globalThis.testApi={apiURL:()=>'',fetchApi:async()=>({ok:true,json:async()=>({name:'new.png',type:'input'})})};
   globalThis.graph={links:{1:{origin_id:1}},nodes:{},setDirtyCanvas(){},getNodeById(id){return this.nodes[id]}};
   globalThis.makeNode=(id,type)=>{
    const host=document.createElement('section');host.dataset.node=String(id);host.style.cssText='width:430px;height:550px';document.querySelector('main').append(host);
    const node={id,type,comfyClass:type,size:[430,550],pos:[600,100],properties:{},widgets:type==='FeiHouApiMediaLoader'?[{name:'media_files',value:'[]'}]:[{name:'prompt',value:'hello '},{name:'media_files',value:'[]'}],inputs:type==='FeiHouApiMediaLoader'?[]:[{name:'media',link:1}],graph,setSize(){},addDOMWidget(name,type,element){host.append(element);return {}}};if(type!=='FeiHouApiMediaLoader'){const textarea=document.createElement('textarea');textarea.value='hello ';textarea.className='comfy-multiline-input';host.append(textarea);node.widgets[0].inputEl=textarea;}graph.nodes[id]=node;return node;
   };
  });
  await page.addScriptTag({content:source});
  await page.evaluate(()=>{
   globalThis.loader=makeNode(1,'FeiHouApiMediaLoader');installMediaLoader(loader,(zh,en)=>en);
   globalThis.generator=makeNode(2,'FeiHouApiImage');installPromptMentions(generator,(zh,en)=>en);
  });
  if(await page.locator('[data-node="1"] textarea').count())throw Error('Loader contains a prompt');
  if(await page.locator('[data-node="2"] .fh-h3-media-gallery').count())throw Error('Generator contains a gallery');
  if(await page.locator('.fh-h3-media-slot').count()!==15)throw Error('Expected 15 slots');
  const heights=await page.evaluate(()=>['image','video','audio'].map(k=>getComputedStyle(document.querySelector('.fh-h3-media-grid.is-'+k+' .fh-h3-media-slot')).height));
  if(parseFloat(heights[0])<48 || Math.abs(parseFloat(heights[1])-parseFloat(heights[0])*68/72)>1 || heights[2]!=='54px')throw Error('Responsive H3 slot dimensions differ: '+heights);
  const pickerPromise=page.waitForEvent('filechooser');await page.getByRole('button',{name:'Images 1',exact:true}).click();
  await (await pickerPromise).setFiles({name:'new.png',mimeType:'image/png',buffer:Buffer.from('fixture')});
  await page.getByText('new.png',{exact:true}).waitFor();
  await page.evaluate(()=>{
   loader.widgets[0].value=JSON.stringify([{media_type:'image',ordinal:3,filename:'third.png',storage:'input'},{media_type:'audio',ordinal:1,filename:'voice.wav',storage:'input'}]);loader._fhMediaPanel.restore();
  });
  const editor=page.locator('textarea');await editor.fill('Use @im');await editor.press('Enter');
  if(await editor.inputValue()!=='Use @image3 ')throw Error('Connected mention failed');
  await page.evaluate(()=>{
   const saved=loader.widgets[0].value,properties=structuredClone(loader.properties);loader._fhMediaPanel.dispose();
   loader=makeNode(1,'FeiHouApiMediaLoader');loader.widgets[0].value=saved;loader.properties=properties;installMediaLoader(loader,(zh,en)=>en);
  });
  if(await page.locator('.fh-h3-media-slot.has-media').count()!==2)throw Error('Loader copy lost media');
  await page.locator('.fh-h3-media-slot-clear').first().click();
  await editor.fill('Use @im');
  if(!(await page.locator('body').innerText()).includes('Connect a Media Loader'))throw Error('Deleted reference still offered');
  await page.evaluate(()=>{
   generator.inputs[0].link=null;
   generator.widgets[1].value=JSON.stringify([{media_type:'image',ordinal:2,filename:'legacy.png',storage:'input'}]);
   graph.add=()=>{};
   globalThis.LiteGraph={createNode(type){const node=makeNode(3,type);installMediaLoader(node,(zh,en)=>en);node.connect=(slot,target,index)=>{const link={origin_id:3};graph.links[2]=link;target.inputs[index].link=2;return link;};return node;}};
   migrateLegacyGallery(generator);
   if(generator.inputs[0].link!==2||generator.widgets[1].value!=='[]')throw Error('Legacy migration failed');
   if(connectedMediaRecords(generator)[0]?.filename!=='legacy.png')throw Error('Migrated media inaccessible');
   migrateLegacyGallery(generator);
   if(Object.keys(graph.nodes).length!==3)throw Error('Migration duplicated loader');
  });
  console.log('PASS: separate nodes, exact H3 slot styles, upload, linked @ references, copy, deletion and legacy migration');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});

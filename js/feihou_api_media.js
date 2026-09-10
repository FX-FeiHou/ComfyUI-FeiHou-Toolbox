import { api } from "../../scripts/api.js";

const LIMITS = { image: 9, video: 3, audio: 3 };
const ACCEPT = { image: "image/png,image/jpeg,image/webp,image/gif,image/bmp", video: "video/mp4,video/webm,video/quicktime,video/x-matroska,video/x-msvideo", audio: "audio/*,.flac,.m4a" };
const field = (node, name) => node.widgets?.find(w => w.name === name);
const names = t => ({image:t("图片","Images"),video:t("视频","Videos"),audio:t("音频","Audio")});
const viewUrl = r => api.apiURL("/view?" + new URLSearchParams({filename:r.filename,subfolder:r.subfolder||"",type:r.storage||"input"}));
const AUDIO_ICON = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Crect x='0.5' y='10' width='3' height='4' rx='1.5' fill='%2300e2bb'/%3E%3Crect x='5.5' y='7' width='3' height='10' rx='1.5' fill='%2300e2bb'/%3E%3Crect x='10.5' y='4' width='3' height='16' rx='1.5' fill='%2300e2bb'/%3E%3Crect x='15.5' y='7' width='3' height='10' rx='1.5' fill='%2300e2bb'/%3E%3Crect x='20.5' y='10' width='3' height='4' rx='1.5' fill='%2300e2bb'/%3E%3C/svg%3E";
const MIME = "application/x-feihou-api-media-reorder";

function records(node) {
  let value;
  try { value = JSON.parse(field(node,"media_files")?.value || "[]"); } catch { value=[]; }
  if ((!Array.isArray(value) || !value.length) && node.properties?.fh_api_media) value=node.properties.fh_api_media;
  return Array.isArray(value) ? value.filter(r=>r && Object.hasOwn(LIMITS,r.media_type) && Number.isInteger(r.ordinal) && r.ordinal>=1 && r.ordinal<=LIMITS[r.media_type] && typeof r.filename==="string") : [];
}
function hideWidget(node,name) {
  const w=field(node,name);if(!w)return;
  w.hidden=true;w.type="hidden";w.computeSize=()=>[0,-4];w.computedHeight=0;
  w.options ||= {};w.options.hidden=true;w.options.canvasOnly=true;
  if(w._state){w._state.hidden=true;w._state.type="hidden";w._state.computedHeight=0;}
  if(w.inputEl)w.inputEl.style.display="none";
  if(w.element)w.element.style.display="none";
}
function stopMedia(root) {
  root.querySelectorAll("video,audio").forEach(el=>{el.pause();el.removeAttribute("src");el.load();});
}
function installStyle() {
  if(document.querySelector('link[data-feihou-api-media]'))return;
  const link=document.createElement("link");link.rel="stylesheet";
  link.href=new URL("./feihou_api_media.css",import.meta.url).href;
  link.dataset.feihouApiMedia="";document.head.append(link);
}
export function installMediaLoader(node,t) {
  if(node._fhMediaPanel)return;
  installStyle();hideWidget(node,"media_files");
  let items=records(node),busy=false,audio=null;
  const root=document.createElement("div");root.className="fh-api-loader";
  // Leave the node border and lower resize corners outside interactive DOM content.
  root.style.cssText="position:relative;width:100%;height:100%;box-sizing:border-box;padding:0 10px 16px;overflow:hidden;pointer-events:none";
  const workbench=document.createElement("div");workbench.className="fh-h3-embedded-workbench";
  workbench.style.cssText="pointer-events:auto;margin:0;width:100%;max-width:100%;height:100%;overflow:hidden";
  const gallery=document.createElement("div");gallery.className="fh-h3-media-gallery";
  const message=document.createElement("div");message.style.cssText="font:11px system-ui;color:#aaa;white-space:pre-wrap";
  workbench.append(gallery,message);root.append(workbench);
  function fitGallery() {
    const hasMessage=Boolean(message.textContent.trim());
    message.style.display=hasMessage?"block":"none";
    // Measure fixed gallery chrome so other frontend themes cannot introduce overflow.
    const imageSlot=gallery.querySelector('.is-image .fh-h3-media-slot');
    const videoSlot=gallery.querySelector('.is-video .fh-h3-media-slot');
    if(!imageSlot || !videoSlot || !root.clientHeight)return;
    const chrome=gallery.offsetHeight-3*imageSlot.offsetHeight-videoSlot.offsetHeight;
    const style=getComputedStyle(workbench);
    const available=workbench.clientHeight-parseFloat(style.paddingTop)-parseFloat(style.paddingBottom)-chrome-(hasMessage?message.offsetHeight+8:0);
    const imageHeight=Math.max(48,Math.floor(available/(3+68/72)));
    gallery.style.setProperty("--fh-h3-image-slot-height",imageHeight+"px");
    gallery.style.setProperty("--fh-h3-video-slot-height",Math.round(imageHeight*68/72)+"px");
  }
  const resizeObserver=new ResizeObserver(fitGallery);resizeObserver.observe(root);
  const messageObserver=new MutationObserver(fitGallery);messageObserver.observe(message,{childList:true,characterData:true,subtree:true});
  for (const side of ["left","right"]) {
    const grip=document.createElement("div");grip.dataset.resizeCorner=side;
    grip.style.cssText=`position:absolute;bottom:0;${side}:0;width:15px;height:15px;pointer-events:auto;cursor:${side==="left"?"nesw":"nwse"}-resize;touch-action:none;z-index:4`;
    grip.addEventListener("pointerdown",event=>{
      if(event.button!==0)return;
      event.preventDefault();event.stopPropagation();grip.setPointerCapture(event.pointerId);
      const origin={x:event.clientX,y:event.clientY,width:node.size[0],height:node.size[1],left:node.pos[0]};
      const scale=root.getBoundingClientRect().width/node.size[0] || 1;
      node.graph?.beforeChange?.();
      const move=e=>{
        const dx=(e.clientX-origin.x)/scale,dy=(e.clientY-origin.y)/scale;
        const width=Math.max(320,origin.width+(side==="right"?dx:-dx));
        node.setSize([width,Math.max(516,origin.height+dy)]);
        if(side==="left")node.pos[0]=origin.left+origin.width-node.size[0];
        node.graph?.setDirtyCanvas(true,true);
      };
      const finish=()=>{grip.removeEventListener("pointermove",move);grip.removeEventListener("pointerup",finish);grip.removeEventListener("pointercancel",finish);node.graph?.afterChange?.();};
      grip.addEventListener("pointermove",move);grip.addEventListener("pointerup",finish);grip.addEventListener("pointercancel",finish);
    });
    root.append(grip);
  }
  for(const event of ["pointerdown","keydown","wheel"])root.addEventListener(event,e=>e.stopPropagation());
  function commit(){
    items.sort((a,b)=>Object.keys(LIMITS).indexOf(a.media_type)-Object.keys(LIMITS).indexOf(b.media_type)||a.ordinal-b.ordinal);
    node.properties ||= {};node.properties.fh_api_media=structuredClone(items);
    field(node,"media_files").value=JSON.stringify(items);node.graph?.setDirtyCanvas(true);
  }
  function replace(kind,ordinal,record){
    items=items.filter(r=>r.media_type!==kind||r.ordinal!==ordinal);
    if(record)items.push({...record,media_type:kind,ordinal});
    commit();render();
  }
  async function upload(files,kind,ordinal){
    if(busy||!files.length)return;
    busy=true;
    try{
      const slots=[ordinal,...Array.from({length:LIMITS[kind]},(_,i)=>i+1).filter(i=>i!==ordinal&&!items.some(r=>r.media_type===kind&&r.ordinal===i))];
      if(files.length>slots.length)throw Error(t("超过此类媒体的剩余位置数量。","Not enough free media slots."));
      for(let i=0;i<files.length;i++){
        message.textContent=t("正在载入：","Loading: ")+files[i].name;
        const body=new FormData();body.append("image",files[i],files[i].name);body.append("type","input");
        const response=await api.fetchApi("/upload/image",{method:"POST",body});
        if(!response.ok)throw Error("Upload: HTTP "+response.status);
        const result=await response.json();if(!result.name)throw Error("Upload returned no filename.");
        replace(kind,slots[i],{filename:result.name,subfolder:result.subfolder||"",storage:result.type||"input"});
      }
      message.textContent="";
    }catch(error){message.textContent=error.message;}finally{busy=false;}
  }
  function choose(kind,ordinal){
    const input=document.createElement("input");input.type="file";input.multiple=true;input.accept=ACCEPT[kind];
    input.addEventListener("change",()=>void upload([...input.files],kind,ordinal),{once:true});input.click();
  }
  function trimSeconds(text){
    return String(text).split(":").reduce((total,v)=>total*60+Number(v),0);
  }
  function render(){
    stopMedia(gallery);audio?.pause();audio=null;gallery.replaceChildren();
    for(const [kind,count] of Object.entries(LIMITS)){
      const section=document.createElement("section");section.className="fh-h3-media-section is-"+kind;
      const heading=document.createElement("div");heading.className="fh-h3-media-heading";heading.textContent=names(t)[kind]+" "+items.filter(r=>r.media_type===kind).length+"/"+count;
      const grid=document.createElement("div");grid.className="fh-h3-media-grid is-"+kind;
      for(let ordinal=1;ordinal<=count;ordinal++){
        const record=items.find(r=>r.media_type===kind&&r.ordinal===ordinal);
        const cell=document.createElement("div");cell.className="fh-h3-media-slot is-"+kind+(record?" has-media":"");
        cell.tabIndex=0;cell.setAttribute("role","button");cell.setAttribute("aria-label",names(t)[kind]+" "+ordinal);
        cell.dataset.mediaType=kind;cell.dataset.ordinal=ordinal;cell.draggable=!!record;
        const pick=()=>{if(Date.now()<(cell._suppressUntil||0))return;choose(kind,ordinal);};
        cell.addEventListener("click",pick);
        cell.addEventListener("keydown",e=>{if(["Enter"," "].includes(e.key)){e.preventDefault();pick();}});
        cell.addEventListener("dragstart",e=>{if(!record){e.preventDefault();return;}cell._suppressUntil=Date.now()+350;e.dataTransfer.setData(MIME,JSON.stringify({node:String(node.id),kind,ordinal}));cell.classList.add("is-reordering");});
        cell.addEventListener("dragend",()=>cell.classList.remove("is-reordering"));
        cell.addEventListener("dragover",e=>{e.preventDefault();cell.classList.add("is-dragover");});
        cell.addEventListener("dragleave",()=>cell.classList.remove("is-dragover"));
        cell.addEventListener("drop",e=>{
          e.preventDefault();e.stopPropagation();cell.classList.remove("is-dragover");
          const raw=e.dataTransfer.getData(MIME);
          if(raw){try{const from=JSON.parse(raw);if(from.node!==String(node.id)||from.kind!==kind)return;
            const a=items.find(r=>r.media_type===kind&&r.ordinal===from.ordinal),b=items.find(r=>r.media_type===kind&&r.ordinal===ordinal);
            if(a)a.ordinal=ordinal;if(b&&b!==a)b.ordinal=from.ordinal;commit();render();
          }catch{}return;}
          void upload([...e.dataTransfer.files],kind,ordinal);
        });
        if(record){
          const preview=document.createElement(kind==="video"?"video":"img");
          preview.className=kind==="audio"?"fh-h3-media-audio-icon":"fh-h3-media-preview";
          preview.src=kind==="audio"?AUDIO_ICON:viewUrl(record);preview.draggable=false;
          if(kind==="video"){preview.muted=true;preview.playsInline=true;preview.preload="metadata";
            cell.addEventListener("mouseenter",()=>preview.play().catch(()=>{}));cell.addEventListener("mouseleave",()=>preview.pause());}
          cell.append(preview);
        }
        const badge=document.createElement("span");badge.className="fh-h3-media-slot-badge";badge.textContent=String(ordinal);
        const status=document.createElement("span");status.className="fh-h3-media-slot-status";status.textContent=record?record.filename:t("点击 / 拖入载入","Click / drop to load");
        cell.append(badge,status);
        if(record){
          const clear=document.createElement("button");clear.type="button";clear.className="fh-h3-media-slot-clear";clear.textContent="×";clear.title=t("移除素材","Remove media");
          clear.addEventListener("pointerdown",e=>e.stopPropagation());clear.addEventListener("click",e=>{e.stopPropagation();replace(kind,ordinal,null);});cell.append(clear);
        }
        grid.append(cell);
      }
      section.append(heading,grid);
      if(kind==="audio"){
        const trims=document.createElement("div");trims.className="fh-h3-audio-trim-grid";
        for(let ordinal=1;ordinal<=3;ordinal++){
          const record=items.find(r=>r.media_type==="audio"&&r.ordinal===ordinal);
          const control=document.createElement("div");control.className="fh-h3-audio-trim-control";
          const input=document.createElement("input");input.className="fh-h3-audio-trim-input";input.value=record?.audio_trim||"00:00-00:00";input.disabled=!record;
          input.title=t("截取起止时间，结束为 00:00 表示到结尾","Trim start-end; end 00:00 means end of file");
          input.addEventListener("change",()=>{if(record){record.audio_trim=input.value;commit();}});
          const play=document.createElement("button");play.className="fh-h3-audio-preview-button";play.textContent="▶";play.disabled=!record;
          play.addEventListener("click",()=>{
            if(audio){audio.pause();audio=null;play.textContent="▶";return;}
            audio=new Audio(viewUrl(record));const current=audio;const [start,end]=input.value.split("-").map(trimSeconds);
            current.addEventListener("loadedmetadata",()=>{current.currentTime=start||0;current.play().catch(e=>message.textContent=e.message);});
            current.addEventListener("timeupdate",()=>{if(end>start&&current.currentTime>=end){current.pause();audio=null;play.textContent="▶";}});
            current.addEventListener("ended",()=>{audio=null;play.textContent="▶";});play.textContent="■";
          });control.append(input,play);trims.append(control);
        }section.append(trims);
      }
      gallery.append(section);
    }
  }
  const dom=node.addDOMWidget("feihou_api_media_gallery","feihou_api_media_gallery",root,{serialize:false,margin:0,getMinHeight:()=>490});dom.serialize=false;
  node._fhMediaPanel={restore(){hideWidget(node,"media_files");items=records(node);commit();render();fitGallery();},dispose(){resizeObserver.disconnect();messageObserver.disconnect();audio?.pause();stopMedia(root);root.remove();}};
  node._fhMediaPanel.restore();node.setSize?.([Math.max(node.size[0],420),Math.max(node.size[1],510)]);
}
export function connectedMediaRecords(node) {
  let input=node.inputs?.find(i=>i.name==="media"),id=input?.link;
  const seen=new Set();
  while(id!=null&&!seen.has(id)){
    seen.add(id);const link=node.graph?.links?.[id];if(!link)return [];
    const source=node.graph?.getNodeById?.(link.origin_id);if(!source)return [];
    if((source.comfyClass||source.type)==="FeiHouApiMediaLoader")return records(source);
    id=source.inputs?.[0]?.link;
  }
  return [];
}
export function installPromptMentions(node,t) {
  if(node._fhPromptPanel)return;
  hideWidget(node,"media_files");
  hideWidget(node,"control_after_generate");
  // Keep the real ComfyUI multiline widget, including its theme, padding and resizing.
  // Only the transient mention popup is our own DOM element.
  const menu=document.createElement("div");
  menu.style.cssText="display:none;position:fixed;z-index:10000;max-height:180px;overflow:auto;background:var(--comfy-menu-bg,#222);color:var(--input-text,#eee);border:1px solid var(--border-color,#666);border-radius:4px";
  document.body.append(menu);
  let prompt=null,listeners=null,candidates=[],active=0,range=null;
  function select(record){
    if(!range||!prompt)return;
    prompt.setRangeText("@"+record.media_type+record.ordinal+" ",range[0],range[1],"end");
    field(node,"prompt").value=prompt.value;
    prompt.dispatchEvent(new Event("input",{bubbles:true}));
    menu.style.display="none";range=null;prompt.focus();node.graph?.setDirtyCanvas(true);
  }
  function show(){
    const match=prompt.value.slice(0,prompt.selectionStart).match(/@([^@\s]*)$/);menu.replaceChildren();
    if(!match){menu.style.display="none";return;}
    range=[prompt.selectionStart-match[0].length,prompt.selectionStart];active=0;
    const query=match[1].toLowerCase();
    candidates=connectedMediaRecords(node).filter(r=>("@"+r.media_type+r.ordinal+" "+names(t)[r.media_type]+r.ordinal+" "+r.filename).toLowerCase().includes(query));
    const rect=prompt.getBoundingClientRect();
    menu.style.left=Math.max(0,rect.left)+"px";menu.style.width=rect.width+"px";
    menu.style.top=Math.min(window.innerHeight-190,rect.bottom)+"px";menu.style.display="block";
    if(!candidates.length)menu.textContent=t("请连接媒体载入节点，或检查素材名称","Connect a Media Loader or check the reference name");
    candidates.forEach((r,index)=>{
      const row=document.createElement("button");row.type="button";row.style.cssText="display:flex;align-items:center;gap:6px;width:100%;text-align:left;color:inherit;border:0;padding:5px;background:"+(index?"var(--comfy-menu-bg,#222)":"#395b72");
      const icon=document.createElement("img");icon.src=r.media_type==="image"?viewUrl(r):AUDIO_ICON;icon.style.cssText="width:30px;height:25px;object-fit:contain";
      const text=document.createElement("span");text.textContent="@"+r.media_type+r.ordinal+" · "+r.filename;
      row.append(icon,text);row.addEventListener("pointerdown",e=>e.preventDefault());row.addEventListener("click",()=>select(r));menu.append(row);
    });
  }
  function bind(){
    const w=field(node,"prompt");
    const el=w?.inputEl || (w?.element?.tagName==="TEXTAREA"?w.element:w?.element?.querySelector?.("textarea"));
    if(!el||el===prompt)return;
    listeners?.abort();listeners=new AbortController();prompt=el;
    const opts={signal:listeners.signal};
    prompt.addEventListener("input",()=>{w.value=prompt.value;show();},opts);
    prompt.addEventListener("click",show,opts);
    prompt.addEventListener("blur",()=>setTimeout(()=>{if(!menu.contains(document.activeElement))menu.style.display="none";},100),opts);
    prompt.addEventListener("keydown",e=>{
      if(menu.style.display==="none")return;
      if(e.key==="Escape"){e.preventDefault();e.stopImmediatePropagation();menu.style.display="none";return;}
      if(!candidates.length)return;
      if(["ArrowDown","ArrowUp"].includes(e.key)){
        e.preventDefault();e.stopImmediatePropagation();active=(active+(e.key==="ArrowDown"?1:-1)+candidates.length)%candidates.length;
        [...menu.children].forEach((row,i)=>row.style.background=i===active?"#395b72":"var(--comfy-menu-bg,#222)");
        menu.children[active]?.scrollIntoView({block:"nearest"});
      }else if(["Enter","Tab"].includes(e.key)){e.preventDefault();e.stopImmediatePropagation();select(candidates[active]);}
    },{...opts,capture:true});
  }
  const observer=new MutationObserver(bind);observer.observe(document.body,{childList:true,subtree:true});
  node._fhPromptPanel={restore(){hideWidget(node,"media_files");hideWidget(node,"control_after_generate");bind();},dispose(){listeners?.abort();observer.disconnect();menu.remove();}};
  node._fhPromptPanel.restore();
}
export function migrateLegacyGallery(node) {
  if(!node.graph||node.inputs?.find(i=>i.name==="media")?.link!=null)return;
  const previous=records(node);if(!previous.length)return;
  const loader=globalThis.LiteGraph?.createNode?.("FeiHouApiMediaLoader");if(!loader)return;
  loader.pos=[node.pos[0]-480,node.pos[1]];
  node.graph.add(loader);field(loader,"media_files").value=JSON.stringify(previous);
  loader._fhMediaPanel?.restore();
  const slot=node.inputs.findIndex(i=>i.name==="media");
  const link=loader.connect(0,node,slot);
  if(link){field(node,"media_files").value="[]";node.properties.fh_api_media=[];}
}

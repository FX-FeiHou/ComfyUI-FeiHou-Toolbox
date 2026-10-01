const {firefox}=require('playwright');
const fs=require('fs');
(async()=>{
 const b=await firefox.launch({headless:true});console.log('Firefox launched');
 try{const p=await b.newPage();p.setDefaultTimeout(15000);
 await p.setContent('<input type="file"><video muted autoplay loop></video>');
 await p.evaluate(()=>document.querySelector('input').onchange=e=>{const v=document.querySelector('video');v.src=URL.createObjectURL(e.target.files[0]);v.play().catch(e=>window.playError=e.name+': '+e.message);});
 await p.locator('input').setInputFiles('F:/Ai/Output-SYNC/txt2img-images/2026-09-14/20260914_123956_Minimax_H3_00001-audio.mp4');
 await p.waitForTimeout(2000);
 console.log(await p.locator('video').evaluate(v=>({width:v.videoWidth,time:v.currentTime,paused:v.paused,error:v.error?.message,playError:window.playError})));
 }finally{await b.close();}
})().catch(e=>{console.error(e);process.exit(1)});

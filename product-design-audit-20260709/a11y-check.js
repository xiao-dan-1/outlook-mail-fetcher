const fs=require('fs'); const path=require('path'); const {chromium}=require('playwright');
const OUT=process.argv[2];
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.goto('http://127.0.0.1:8765/',{waitUntil:'networkidle'});
 const a11y=await page.evaluate(async()=>{
   const text=el=>(el.innerText||el.textContent||'').trim().replace(/\s+/g,' ');
   const rect=el=>{const r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}};
   const programmaticLabel=el=>{
     const labels = el.labels ? Array.from(el.labels).map(text).filter(Boolean) : [];
     const ariaLabel = el.getAttribute('aria-label');
     const labelledby = el.getAttribute('aria-labelledby');
     const title = el.getAttribute('title');
     return {labels, ariaLabel, labelledby, title};
   };
   const focusables = Array.from(document.querySelectorAll('a[href],button,input,textarea,select,[tabindex]:not([tabindex="-1"])')).filter(el=>{
      const r=el.getBoundingClientRect(); const s=getComputedStyle(el); return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden' && !el.disabled;
   });
   const fieldNames = Array.from(document.querySelectorAll('input,textarea,select')).map(el=>({tag:el.tagName,type:el.type,id:el.id,name:el.name,placeholder:el.getAttribute('placeholder'),...programmaticLabel(el),rect:rect(el)}));
   const buttons = Array.from(document.querySelectorAll('button,[role="button"]')).map(el=>({id:el.id,text:text(el), ariaLabel:el.getAttribute('aria-label'), ariaPressed:el.getAttribute('aria-pressed'), ariaExpanded:el.getAttribute('aria-expanded'), ariaControls:el.getAttribute('aria-controls'), disabled:el.disabled, ariaDisabled:el.getAttribute('aria-disabled'), title:el.getAttribute('title'), rect:rect(el)}));
   let order=[];
   document.body.focus();
   for(let i=0;i<20;i++){
      await new Promise(r=>setTimeout(r,20));
      document.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true}));
   }
   // Browser-created KeyboardEvent won't move focus reliably; return DOM order instead.
   order=focusables.map((el,i)=>({i,tag:el.tagName,id:el.id,text:text(el).slice(0,80),rect:rect(el)}));
   return {url:location.href, fieldNames, buttons, focusableDomOrder:order, viewport:{w:innerWidth,h:innerHeight,scrollW:document.documentElement.scrollWidth,scrollH:document.documentElement.scrollHeight}, liveRegions:Array.from(document.querySelectorAll('[aria-live],[role="status"],[role="log"],[role="alert"]')).map(el=>({tag:el.tagName,role:el.getAttribute('role'),ariaLive:el.getAttribute('aria-live'),text:text(el).slice(0,200),rect:rect(el)}))};
 });
 const mobile=await browser.newPage({viewport:{width:390,height:844},isMobile:true,deviceScaleFactor:2});
 await mobile.goto('http://127.0.0.1:8765/',{waitUntil:'networkidle'});
 const mobileInfo=await mobile.evaluate(()=>({w:innerWidth,h:innerHeight,scrollW:document.documentElement.scrollWidth,scrollH:document.documentElement.scrollHeight,bodyText:document.body.innerText.slice(0,3000)}));
 fs.writeFileSync(path.join(OUT,'a11y-evidence.json'),JSON.stringify({a11y,mobileInfo},null,2),'utf8');
 console.log(JSON.stringify({fieldNames:a11y.fieldNames, buttons:a11y.buttons.slice(0,12), focusCount:a11y.focusableDomOrder.length, mobileInfo},null,2));
 await browser.close();
})();

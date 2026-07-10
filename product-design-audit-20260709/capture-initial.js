const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
(async()=>{
  const out = process.argv[2];
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  const runtimeMessages=[];
  page.on('console', msg => { if(['error','warning'].includes(msg.type())) runtimeMessages.push({type:msg.type(), text:msg.text()}); });
  page.on('pageerror', err => runtimeMessages.push({type:'pageerror', text:err.message}));
  await page.goto('http://127.0.0.1:8765/', { waitUntil: 'networkidle', timeout: 30000 });
  await page.screenshot({ path: path.join(out, '01-home.png'), fullPage: true });
  const info = await page.evaluate(() => {
    const visible = el => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none';
    };
    const text = (el) => (el.innerText || el.textContent || '').trim().replace(/\s+/g,' ').slice(0,200);
    const rect = el => { const r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; };
    return {
      title: document.title,
      url: location.href,
      bodyText: document.body.innerText.slice(0,6000),
      h1: Array.from(document.querySelectorAll('h1')).map(text),
      headings: Array.from(document.querySelectorAll('h1,h2,h3')).map(el=>({tag:el.tagName, text:text(el), rect:rect(el)})),
      actions: Array.from(document.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"], a')).filter(visible).map((el,i)=>({i, tag:el.tagName, role:el.getAttribute('role'), text:text(el), href:el.href||null, aria:el.getAttribute('aria-label'), title:el.getAttribute('title'), id:el.id, cls:String(el.className||'').slice(0,160), rect:rect(el)})),
      fields: Array.from(document.querySelectorAll('input,textarea,select')).filter(visible).map((el,i)=>({i, tag:el.tagName, type:el.type, placeholder:el.getAttribute('placeholder'), aria:el.getAttribute('aria-label'), name:el.getAttribute('name'), id:el.id, value:el.value, rect:rect(el)})),
      landmarks: Array.from(document.querySelectorAll('main,nav,header,footer,aside,[role]')).filter(visible).map(el=>({tag:el.tagName, role:el.getAttribute('role'), text:text(el).slice(0,120), rect:rect(el)}))
    };
  });
  info.runtimeMessages = runtimeMessages;
  fs.writeFileSync(path.join(out,'01-home-dom.json'), JSON.stringify(info,null,2),'utf8');
  console.log(JSON.stringify({ok:true, out, summary:{title:info.title,h1:info.h1, headings:info.headings, actions:info.actions, fields:info.fields, runtimeMessages}}, null, 2));
  await browser.close();
})().catch(e=>{ console.error(e); process.exit(1); });

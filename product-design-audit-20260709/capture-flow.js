const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const OUT = process.argv[2];
function rect(el){ const r=el.getBoundingClientRect(); return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}; }
async function gather(page){
  return await page.evaluate(() => {
    const visible = el => { const r=el.getBoundingClientRect(); const s=getComputedStyle(el); return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none'; };
    const text = el => (el.innerText || el.textContent || '').trim().replace(/\s+/g,' ').slice(0,240);
    const rect = el => { const r=el.getBoundingClientRect(); return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}; };
    const labelFor = el => {
      if (el.id) {
        const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (lab) return text(lab);
      }
      const wrap = el.closest('label');
      if (wrap) return text(wrap);
      const prev = el.previousElementSibling;
      if (prev) return text(prev);
      return '';
    };
    const elInfo = (el,i) => {
      const cs = getComputedStyle(el);
      return {i, tag:el.tagName, id:el.id, cls:String(el.className||'').slice(0,120), text:text(el), role:el.getAttribute('role'), aria:el.getAttribute('aria-label'), label: labelFor(el), title:el.getAttribute('title'), disabled:el.disabled || el.getAttribute('aria-disabled')==='true', ariaPressed:el.getAttribute('aria-pressed'), ariaSelected:el.getAttribute('aria-selected'), rect:rect(el), color:cs.color, background:cs.backgroundColor, border:cs.borderColor, outline:cs.outlineStyle + ' ' + cs.outlineWidth};
    };
    return {
      title: document.title,
      url: location.href,
      viewport: {w:innerWidth,h:innerHeight, scrollW:document.documentElement.scrollWidth, scrollH:document.documentElement.scrollHeight},
      active: document.activeElement ? {tag:document.activeElement.tagName, id:document.activeElement.id, text:text(document.activeElement), rect:rect(document.activeElement)} : null,
      bodyText: document.body.innerText.slice(0,8000),
      headings: Array.from(document.querySelectorAll('h1,h2,h3')).map((el,i)=>({i, tag:el.tagName, text:text(el), rect:rect(el)})),
      actions: Array.from(document.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"], a')).filter(visible).map(elInfo),
      fields: Array.from(document.querySelectorAll('input,textarea,select')).filter(visible).map(elInfo),
      liveRegions: Array.from(document.querySelectorAll('[aria-live], [role="status"], [role="log"], [role="alert"]')).filter(visible).map(elInfo),
      htmlClass: document.documentElement.className,
      bodyClass: document.body.className
    };
  });
}
async function snapshot(page, name){
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
  const info = await gather(page);
  fs.writeFileSync(path.join(OUT, `${name}-dom.json`), JSON.stringify(info,null,2),'utf8');
  return info;
}
(async()=>{
  const browser = await chromium.launch({ headless:true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  const runtime=[]; const requests=[];
  page.on('console', msg => { if(['error','warning'].includes(msg.type())) runtime.push({type:msg.type(), text:msg.text()}); });
  page.on('pageerror', err => runtime.push({type:'pageerror', text:err.message}));
  page.on('requestfailed', req => requests.push({url:req.url(), method:req.method(), failure:req.failure()?.errorText}));
  page.on('response', res => { if(res.status()>=400) requests.push({url:res.url(), status:res.status()}); });
  await page.goto('http://127.0.0.1:8765/', { waitUntil:'networkidle', timeout:30000 });
  const s1 = await snapshot(page, '01-home');

  await page.fill('#accountTextInput', 'user@example.com----password123----client-id-123----refresh-token-abc');
  await page.waitForTimeout(800);
  const s2 = await snapshot(page, '02-account-parsed');

  await page.click('#allScopeBtn').catch(()=>{});
  await page.waitForTimeout(300);
  await snapshot(page, '03-all-accounts-scope');

  await page.click('#fetchBtn').catch(()=>{});
  await page.waitForTimeout(5000);
  const s4 = await snapshot(page, '04-fetch-attempt');

  await page.click('#logDrawerToggle').catch(()=>{});
  await page.waitForTimeout(400);
  const s5 = await snapshot(page, '05-log-expanded');

  await page.click('#themeToggle').catch(()=>{});
  await page.waitForTimeout(600);
  const s6 = await snapshot(page, '06-dark-theme');

  await page.keyboard.press('Tab');
  await page.waitForTimeout(150);
  await page.keyboard.press('Tab');
  await page.waitForTimeout(150);
  await page.keyboard.press('Tab');
  await page.waitForTimeout(150);
  const s7 = await snapshot(page, '07-keyboard-focus');

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2 });
  await mobile.goto('http://127.0.0.1:8765/', { waitUntil:'networkidle', timeout:30000 });
  const sm = await snapshot(mobile, '08-mobile');

  fs.writeFileSync(path.join(OUT, 'interaction-summary.json'), JSON.stringify({runtime, requests, states:{home:s1, parsed:s2, fetch:s4, log:s5, dark:s6, focus:s7, mobile:sm}}, null, 2), 'utf8');
  console.log(JSON.stringify({ok:true, out:OUT, files:fs.readdirSync(OUT).filter(f=>/\.png$/.test(f)), runtime, requests}, null, 2));
  await browser.close();
})().catch(e=>{ console.error(e); process.exit(1); });

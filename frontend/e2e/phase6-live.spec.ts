// Actual AWS journey, with no fixture routes or fabricated regulatory observations.
import {test,expect} from '@playwright/test';
import {writeFileSync} from 'node:fs';
const api='https://pu8l3a213j.execute-api.us-east-1.amazonaws.com';
const evidencePrefix=process.env.HAWAHAWAI_TEST_EVIDENCE_PREFIX||'phase6';
for(const target of ['LOCAL','PRODUCTION'])test(`LIVE Phase 6 ${target}: authoritative journey, notice copy, PWA and responsive safety`,async({page,context})=>{
  const url=target==='LOCAL'?'http://127.0.0.1:4173':'https://production.d3vzi8hqeh0wba.amplifyapp.com';
  const errors:string[]=[];const responses:{path:string;status:number}[]=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});page.on('response',r=>{if(r.url().startsWith(api))responses.push({path:new URL(r.url()).pathname,status:r.status()});});
  await context.grantPermissions(['clipboard-read','clipboard-write'],{origin:url});
  const verdictResponse=page.waitForResponse(r=>r.url()===api+'/v1/schools/delhi-demo-school/verdict');
  await page.goto(url);let verdict=await(await verdictResponse).json();await expect(page.locator('.canonical')).toContainText(verdict.decision,{timeout:30000});
  await expect(page.locator('.school-name')).toHaveText('HawaHawai Demo School');await expect(page.locator('.action-list>li')).toHaveCount(verdict.actions.length);await expect(page.locator('.forecast-list time')).toHaveCount(48,{timeout:30000});
  await expect(page.locator('#tomorrow')).toContainText('Provisional planning');await expect(page.locator('#tomorrow')).toContainText('Asia/Kolkata');await expect(page.locator('#tomorrow')).toContainText('US AQI is not Indian AQI');
  await expect(page.locator('#confidence')).toContainText('No fresh representative physical station evidence');await expect(page.locator('#confidence')).toContainText('UNKNOWN');await expect(page.locator('#regulatory-actions')).toContainText('Current activation is UNKNOWN');await expect(page.locator('#indoor-alternatives')).toContainText('Indoor air has not been measured');
  const advisoryResponse=page.waitForResponse(r=>r.url().endsWith('/advisory'));await page.getByRole('button',{name:'Load school explanation'}).click();let response=await advisoryResponse;
  let recoveredConflict=false;
  if(response.status()===409){
    // A legitimate environmental refresh invalidates the previously loaded ID.
    // Exercise the product's explicit manual recovery; never retry the old ID.
    const previous=verdict,conflict=await response.json();expect(conflict.error.code).toBe('STALE_VERDICT');
    await expect(page.locator('#advisory')).toContainText('The decision changed. Refresh the current decision');
    await expect(page.locator('.notice-controls,.parent-notice,.advisory-text')).toHaveCount(0);
    const refreshed=page.waitForResponse(r=>r.url()===api+'/v1/schools/delhi-demo-school/verdict');
    await page.getByRole('button',{name:'Refresh current data',exact:true}).click();verdict=await(await refreshed).json();
    expect(verdict.decision_id).not.toBe(previous.decision_id);await expect(page.locator('.canonical')).toHaveText(verdict.decision);
    await expect(page.locator('.action-list>li')).toHaveCount(verdict.actions.length);
    const next=page.waitForResponse(r=>r.url().endsWith('/advisory'));
    await page.getByRole('button',{name:'Load school explanation'}).click();response=await next;recoveredConflict=true;
    writeFileSync(`.local/${evidencePrefix}-${target.toLowerCase()}-conflict-recovery.json`,JSON.stringify({previous,current:verdict,conflict,method:'One explicit manual data refresh; no old-ID retry'},null,2));
  }
  expect(response.status()).toBe(200);const advisory=await response.json();expect(advisory.decision).toBe(verdict.decision);expect(advisory.verdict_id).toBe(verdict.decision_id);
  writeFileSync(`.local/${evidencePrefix}-${target.toLowerCase()}-authority.json`,JSON.stringify({checked_at:new Date().toISOString(),verdict,advisory},null,2));
  const notices:Record<string,number>={};for(const language of ['en','hi']){
    if(language==='hi')await page.getByRole('button',{name:'हिन्दी',exact:true}).click();const notice=page.locator('.parent-notice');await expect(notice).toHaveAttribute('lang',language);const text=await notice.innerText();
    expect(text).toContain(verdict.decision);expect(text).toContain(verdict.valid_until);for(const a of advisory.actions)expect(text).toContain(a[language]);expect(new URL((await page.locator('.notice-controls a').getAttribute('href'))!).searchParams.get('text')).toBe(text);
    await page.getByRole('button',{name:language==='en'?'Copy Advisory':'सूचना कॉपी करें',exact:true}).click();await expect(page.locator('.share-status')).toContainText(language==='en'?'Advisory copied.':'सूचना कॉपी की गई।');expect((await page.evaluate(()=>navigator.clipboard.readText())).replaceAll('\r\n','\n')).toBe(text);notices[language]=text.length;
  }
  for(const width of [320,375,430,768,1024,1440]){await page.setViewportSize({width,height:1000});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await expect(page.locator('.notice-controls')).toBeVisible();}
  await page.setViewportSize({width:375,height:1000});await page.locator('#advisory').scrollIntoViewIfNeeded();await page.screenshot({path:`.local/${evidencePrefix}-${target.toLowerCase()}-parent-mobile.png`});
  await page.setViewportSize({width:1440,height:1000});await page.locator('#tomorrow').scrollIntoViewIfNeeded();await page.screenshot({path:`.local/${evidencePrefix}-${target.toLowerCase()}-planner-desktop.png`});
  await page.evaluate(async()=>{await navigator.serviceWorker.ready;});await page.reload();await expect(page.locator('.canonical')).toBeVisible({timeout:30000});expect(await page.evaluate(()=>!!navigator.serviceWorker.controller)).toBe(true);
  const cacheUrls=await page.evaluate(async()=>{const urls:string[]=[];for(const name of await caches.keys())for(const r of await(await caches.open(name)).keys())urls.push(r.url);return urls;});expect(cacheUrls.some(x=>x.includes('/v1/')||x.endsWith('/health'))).toBe(false);
  await context.setOffline(true);await expect(page.locator('.notice-controls')).toHaveCount(0);await page.reload();await expect(page.locator('#today')).toContainText('Reconnect to check');await expect(page.locator('.notice-controls')).toHaveCount(0);await expect(page.locator('.action-list')).toHaveCount(0);
  await context.setOffline(false);await expect(page.locator('.canonical')).toBeVisible({timeout:30000});expect(responses.filter(r=>r.path.endsWith('/verdict'))).toHaveLength(3+(recoveredConflict?1:0));
  expect(responses.filter(r=>r.status===409)).toHaveLength(recoveredConflict?1:0);expect(responses.every(r=>r.status===200||recoveredConflict&&r.path.endsWith('/advisory')&&r.status===409)).toBe(true);
  expect(errors).toEqual(recoveredConflict?['Failed to load resource: the server responded with a status of 409 ()']:[]);
  writeFileSync(`.local/${evidencePrefix}-${target.toLowerCase()}-browser-evidence.json`,JSON.stringify({url,checked_at:new Date().toISOString(),responses,errors,notices,recoveredConflict,cacheSafetyEntries:0,viewportWidths:[320,375,430,768,1024,1440],offlineReload:true,reconnected:true,sharing:'Exact draft URL and owned clipboard verified; no message sent'},null,2));
});

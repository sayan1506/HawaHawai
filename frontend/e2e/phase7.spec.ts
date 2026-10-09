// Isolated reliability simulations; never published to AWS evidence/history.
import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {writeFileSync} from 'node:fs';
const now=Date.parse('2026-10-08T08:00:00Z');
const fixture=(name:string)=>JSON.parse(readFileSync(new URL('../tests/fixtures/'+name+'-simulation.json',import.meta.url),'utf8'));
for(const malformed of ['duplicates','gap','wrong bounds','valid offsets'])test(`SIMULATION F6-01 confidence/planner: ${malformed}`,async({page})=>{
  const forecast=fixture('forecast'),verdict=fixture('MODIFIED_OUTDOORS');
  if(malformed==='duplicates')forecast.points=Array.from({length:48},()=>structuredClone(forecast.points[16]));
  if(malformed==='gap')forecast.points[10]=structuredClone(forecast.points[12]);
  if(malformed==='wrong bounds')forecast.forecast_end=forecast.points[46].valid_at;
  if(malformed==='valid offsets'){
    forecast.points.forEach((p:any)=>{const stamp=new Date(Date.parse(p.valid_at)+19800000).toISOString().replace('Z','+05:30');p.valid_at=stamp;[...p.aqi,...p.pollutants].forEach(v=>v.forecast_for=stamp);});
    forecast.forecast_start=forecast.points[0].valid_at;forecast.forecast_end=forecast.points.at(-1).valid_at;
  }
  await page.clock.install({time:new Date(now)});
  await page.context().route('https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    await route.fulfill({json:path.endsWith('/forecast')?forecast:path.endsWith('/verdict')?verdict:path.endsWith('/grap')?verdict.regulatory_status:path.endsWith('/air')?fixture('air'):path.endsWith('/health')?{status:'ok',service:'hawahawai-backend',phase:0,timestamp:new Date(now).toISOString()}:fixture('school')});
  });
  await page.goto('/');await expect(page.locator('.canonical')).toBeVisible();
  const panel=page.locator('#confidence .status-grid>div').last();
  await expect(panel).toContainText(malformed==='valid offsets'?'Modeled · limited':'Incomplete evidence');
  if(malformed==='valid offsets')await expect(page.locator('#tomorrow')).toContainText('24 of 24 hours');
  else await expect(page.locator('#tomorrow')).toContainText('Incomplete forecast coverage');
  if(malformed==='duplicates')await expect(page.locator('#tomorrow')).toContainText('1 of 24 hours');
});

for(const conflicting of [false,true])test(`SIMULATION per-hour ${conflicting?'conflicting':'duplicate'} US AQI is withheld`,async({page})=>{
  const forecast=fixture('forecast'),verdict=fixture('MODIFIED_OUTDOORS');
  forecast.points.forEach((p:any)=>p.aqi.push({...p.aqi[0],value:conflicting?300:p.aqi[0].value}));
  await page.clock.install({time:new Date(now)});
  await page.context().route('https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    await route.fulfill({json:path.endsWith('/forecast')?forecast:path.endsWith('/verdict')?verdict:path.endsWith('/grap')?verdict.regulatory_status:path.endsWith('/air')?fixture('air'):path.endsWith('/health')?{status:'ok',service:'hawahawai-backend',phase:0,timestamp:new Date(now).toISOString()}:fixture('school')});
  });
  await page.goto('/');await expect(page.locator('.canonical')).toBeVisible();
  await expect(page.locator('#confidence .status-grid>div').last()).toContainText('Incomplete evidence');
  await expect(page.locator('#tomorrow')).toContainText('24 supplied hours lack unambiguous US AQI');
  await expect(page.locator('#tomorrow')).toContainText('Modeled US AQI range: Missing');
  await page.getByText('Tomorrow’s dated modeled hours',{exact:true}).click();
  await expect(page.locator('.planning-hours li')).toHaveCount(24);
  await expect(page.locator('.planning-hours li')).toContainText(Array.from({length:24},()=> 'US AQI · modeled: Missing'));
});

async function noticeSetup(page:Page,options:{failedEndpoint?:string;failureStatus?:number;demo?:boolean}={}) {
  const verdict=fixture('MODIFIED_OUTDOORS');verdict.valid_until=new Date(now+120000).toISOString();
  const advisory=fixture('advisory');advisory.authoritative_decision=verdict;advisory.valid_until=verdict.valid_until;
  const values={verdict,advisory};const calls:string[]=[];
  let pending:((value:void)=>void)|undefined;
  const gate=new Promise<void>(resolve=>{pending=resolve;});let hold=false;
  await page.clock.install({time:new Date(now)});
  await page.context().route('https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/**',async route=>{
    const path=new URL(route.request().url()).pathname;calls.push(path);
    if((options.failedEndpoint&&path.endsWith(options.failedEndpoint))||(options.demo&&path.endsWith('/health'))){
      await route.fulfill({status:options.failureStatus||503,json:{error:{code:'SIMULATION_PRIVATE_EXCEPTION',message:'SIMULATION_INTERNAL_DETAIL'}}});return;
    }
    if(path.endsWith('/advisory')&&hold)await gate;
    const body=path.endsWith('/advisory')?values.advisory:path.endsWith('/verdict')?values.verdict:path.endsWith('/grap')?values.verdict.regulatory_status:path.endsWith('/forecast')?fixture('forecast'):path.endsWith('/air')?fixture('air'):path.endsWith('/health')?{status:'ok',service:'hawahawai-backend',phase:0,timestamp:new Date(now).toISOString()}:fixture('school');
    await route.fulfill({json:body});
  });
  await page.goto('/');
  if(options.failedEndpoint==='/verdict')await expect(page.locator('#today')).toContainText('Current recommendation unavailable');
  else await expect(page.locator('.canonical')).toBeVisible();
  return {values,calls,hold:()=>{hold=true;},release:()=>pending?.()};
}

for(const outcome of ['success','failure'])test(`SIMULATION native share ${outcome} preserves validated notice`,async({page})=>{
  await page.addInitScript(failure=>{
    Object.defineProperty(navigator,'canShare',{value:()=>true});
    Object.defineProperty(navigator,'share',{value:async(data:ShareData)=>{
      (window as any).__share=data;
      if(failure)throw new DOMException('Permission denied','NotAllowedError');
    }});
  },outcome==='failure');
  const {calls}=await noticeSetup(page);
  await page.getByRole('button',{name:'Load school explanation'}).click();
  const notice=await page.locator('.parent-notice').innerText();
  await page.getByRole('button',{name:'Share Advisory',exact:true}).click();
  expect((await page.evaluate(()=>(window as any).__share)).text).toBe(notice);
  await expect(page.locator('.share-status')).toContainText(outcome==='success'?'Browser sharing completed.':'Sharing failed');
  expect(calls.filter(p=>p.endsWith('/advisory'))).toHaveLength(1);
});

for(const status of [429,500,504])test(`SIMULATION gateway/Lambda ${status}: current guidance withheld without request loops`,async({page})=>{
  const {calls}=await noticeSetup(page,{failedEndpoint:'/verdict',failureStatus:status});
  await expect(page.locator('#today')).toContainText('Current recommendation unavailable');
  await expect(page.locator('.canonical,.action-list,.notice-controls')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Load school explanation'})).toBeDisabled();
  await page.clock.fastForward(60000);expect(calls.filter(p=>p.endsWith('/verdict'))).toHaveLength(1);
  expect(await page.locator('body').innerText()).not.toContain('SIMULATION_INTERNAL_DETAIL');
});

test('SIMULATION changed-evidence 409 requires manual refresh before a current notice',async({page})=>{
  const options:{failedEndpoint?:string;failureStatus:number}={failedEndpoint:'/advisory',failureStatus:409};
  const setup=await noticeSetup(page,options),ids:string[]=[];
  page.on('request',r=>{if(r.url().endsWith('/advisory'))ids.push(r.postDataJSON().verdict_id);});
  const old=setup.values.verdict.decision_id;
  await page.getByRole('button',{name:'Load school explanation'}).click();
  await expect(page.locator('#advisory')).toContainText('The decision changed. Refresh the current decision');
  await expect(page.locator('.parent-notice,.notice-controls')).toHaveCount(0);
  options.failedEndpoint=undefined;const next='b'.repeat(64);
  setup.values.verdict.decision_id=next;setup.values.advisory.verdict_id=next;
  setup.values.advisory.authoritative_decision=setup.values.verdict;
  await page.getByRole('button',{name:'Refresh current data',exact:true}).click();
  await expect(page.locator('#advisory')).toContainText('The explanation has not been requested yet');
  await expect(page.locator('.parent-notice,.notice-controls')).toHaveCount(0);
  await page.getByRole('button',{name:'Load school explanation'}).click();
  await expect(page.locator('.parent-notice')).toBeVisible();expect(ids).toEqual([old,next]);
  expect(setup.calls.filter(p=>p.endsWith('/verdict'))).toHaveLength(2);
});

test('SIMULATION forecast API outage: no fabricated tomorrow hours/confidence',async({page})=>{
  await noticeSetup(page,{failedEndpoint:'/forecast'});
  await expect(page.locator('#confidence .status-grid>div').last()).toContainText('Unavailable');
  await expect(page.locator('#tomorrow')).toContainText('unavailable');
  await expect(page.locator('.planning-hours time,.forecast-list time')).toHaveCount(0);
  await expect(page.locator('#tomorrow')).not.toContainText('Modeled outlook · fresh');
});

test('SIMULATION advisory outage: canonical actions remain; sharing is unavailable',async({page})=>{
  await noticeSetup(page,{failedEndpoint:'/advisory'});
  await page.getByRole('button',{name:'Load school explanation'}).click();
  await expect(page.locator('#advisory')).toContainText('unavailable');
  await expect(page.locator('.canonical')).toHaveText('MODIFIED_OUTDOORS');
  await expect(page.locator('.action-list>li')).toHaveCount(7);
  await expect(page.locator('.notice-controls,.parent-notice,.advisory-text')).toHaveCount(0);
  expect(await page.locator('body').innerText()).not.toContain('SIMULATION_INTERNAL_DETAIL');
});

test('SIMULATION / DEMO: labeled private fallback with no live requests or history writes',async({page})=>{
  // Only localhost assets may reach a server. Every pilot API request is fulfilled below.
  await page.context().route('**/*',async route=>{
    const u=new URL(route.request().url());
    if(u.hostname==='127.0.0.1'||u.hostname==='localhost')await route.continue();
    else if(u.origin==='https://pu8l3a213j.execute-api.us-east-1.amazonaws.com')await route.fallback();
    else await route.abort('blockedbyclient');
  });
  await page.addInitScript(()=>document.addEventListener('DOMContentLoaded',()=>{
    const label=document.createElement('aside');label.setAttribute('role','note');label.id='simulation-label';
    label.textContent='SIMULATION / DEMO — NOT LIVE DATA OR CURRENT ORDERS. Frozen isolated test fixtures; no AWS history writes.';
    Object.assign(label.style,{position:'sticky',top:'0',zIndex:'1000',padding:'12px',background:'#fff3cd',color:'#3b2c00',border:'3px solid #885000',font:'bold 16px system-ui'});
    document.body.prepend(label);
  }));
  const {calls}=await noticeSetup(page,{demo:true});
  await expect(page.locator('#simulation-label')).toContainText('NOT LIVE DATA OR CURRENT ORDERS');
  await expect(page.locator('#regulatory-actions')).toContainText('Current activation is UNKNOWN');
  await expect(page.locator('#tomorrow')).toContainText('Provisional planning');
  await page.getByRole('button',{name:'Load school explanation'}).click();
  await expect(page.locator('#advisory')).toContainText('Deterministic fallback');
  await page.getByRole('button',{name:'हिन्दी',exact:true}).click();
  await expect(page.locator('.parent-notice')).toHaveAttribute('lang','hi');
  expect(new URL((await page.locator('.notice-controls a').getAttribute('href'))!).searchParams.get('text')).toBe(await page.locator('.parent-notice').innerText());
  expect(calls.some(p=>p.endsWith('/verdict/history'))).toBe(false);expect(calls).toHaveLength(7);
  const prefix=process.env.HAWAHAWAI_TEST_EVIDENCE_PREFIX||'phase7';
  await page.setViewportSize({width:1024,height:900});await page.screenshot({path:`.local/${prefix}-SIMULATION-DEMO.png`});
  writeFileSync(`.local/${prefix}-SIMULATION-DEMO.json`,JSON.stringify({label:'SIMULATION / DEMO',live:false,fixture_clock:new Date(now).toISOString(),intercepted_calls:calls,
    server_egress:'localhost static assets only',AWS_writes:false,AI_invocations:0,notice_language:'hi'},null,2));
});

test('SIMULATION intervening verdict change cancels obsolete in-flight notice',async({page})=>{
  const setup=await noticeSetup(page);setup.hold();
  await page.getByRole('button',{name:'Load school explanation'}).click();
  await expect(page.getByRole('button',{name:'Loading explanation…'})).toBeVisible();
  setup.values.verdict=fixture('INDOOR_ONLY');setup.values.verdict.valid_until=new Date(now+120000).toISOString();
  await page.getByRole('button',{name:'Refresh current data',exact:true}).click();
  await expect(page.locator('.canonical')).toHaveText('INDOOR_ONLY');setup.release();
  await expect(page.locator('#advisory')).toContainText('The explanation has not been requested yet');
  await expect(page.locator('.notice-controls')).toHaveCount(0);
  await expect(page.locator('.parent-notice')).toHaveCount(0);
});

test('SIMULATION headings, labels, reduced motion and bounded local load',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});const started=Date.now();const {calls}=await noticeSetup(page);const readyMs=Date.now()-started;
  const audit=await page.evaluate(()=>{
    const headings=Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6')).map(h=>({level:Number(h.tagName[1]),text:h.textContent?.trim()}));
    return {headings,scroll:getComputedStyle(document.documentElement).scrollBehavior,
      unnamed:Array.from(document.querySelectorAll('button')).filter(b=>!b.textContent?.trim()&&!b.getAttribute('aria-label')).length};
  });
  expect(audit.headings.filter(h=>h.level===1)).toHaveLength(1);
  expect(audit.headings.every(h=>Boolean(h.text))).toBe(true);
  for(let i=1;i<audit.headings.length;i++)expect(audit.headings[i].level).toBeLessThanOrEqual(audit.headings[i-1].level+1);
  expect(audit.unnamed).toBe(0);expect(audit.scroll).toBe('auto');expect(readyMs).toBeLessThan(5000);
  await page.keyboard.press('Tab');await expect(page.getByRole('link',{name:'Skip to current decision'})).toBeFocused();
  expect(await page.evaluate(()=>getComputedStyle(document.activeElement!).outlineStyle)).not.toBe('none');
  await page.clock.fastForward(60000);expect(calls).toHaveLength(6);
});

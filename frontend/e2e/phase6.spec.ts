// Isolated Phase 6 simulations. Never publish policy or provider fixtures to AWS.
import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
const now=Date.parse('2026-10-08T08:00:00Z');
const api='https://pu8l3a213j.execute-api.us-east-1.amazonaws.com';
const fixture=(name:string)=>JSON.parse(readFileSync(new URL('../tests/fixtures/'+name+'-simulation.json',import.meta.url),'utf8'));
async function setup(page:Page,change?:(values:any)=>void) {
  const verdict=fixture('MODIFIED_OUTDOORS');verdict.valid_until=new Date(now+120000).toISOString();
  const advisory=fixture('advisory');advisory.authoritative_decision=verdict;advisory.valid_until=verdict.valid_until;
  const values={verdict,advisory,forecast:fixture('forecast'),air:fixture('air'),school:fixture('school')};change?.(values);
  const calls:string[]=[];await page.clock.install({time:new Date(now)});
  await page.context().route(api+'/**',async route=>{const path=new URL(route.request().url()).pathname;calls.push(path);
    const body=path.endsWith('/verdict')?values.verdict:path.endsWith('/grap')?values.verdict.regulatory_status:path.endsWith('/forecast')?values.forecast:path.endsWith('/air')?values.air:path.endsWith('/advisory')?values.advisory:path.endsWith('/health')?{status:'ok',service:'hawahawai-backend',phase:0,timestamp:new Date(now).toISOString()}:values.school;
    await route.fulfill({status:200,json:body});});
  await page.goto('/');await expect(page.locator('.canonical')).toBeVisible();return {values,calls};
}
test('SIMULATION Feature A: tomorrow is dated provisional model planning, without extra requests',async({page})=>{
  const {calls}=await setup(page);await expect(page.locator('#tomorrow')).toContainText('2026-10-09');await expect(page.locator('#tomorrow')).toContainText('Provisional planning');await expect(page.locator('#tomorrow')).toContainText('24 of 24 hours');
  await page.getByText('Tomorrow’s dated modeled hours',{exact:true}).click();await expect(page.locator('.planning-hours time')).toHaveCount(24);expect(calls.filter(p=>p.endsWith('/forecast'))).toHaveLength(1);expect(calls.some(p=>p.endsWith('/advisory'))).toBe(false);
});
test('SIMULATION Feature A: stale and absent tomorrow evidence stay explicit',async({page})=>{
  await setup(page,v=>{v.forecast.status=v.forecast.freshness_status='stale';v.forecast.points=[];});await expect(page.locator('#tomorrow')).toContainText('Modeled outlook · stale');await expect(page.locator('#tomorrow')).toContainText('Tomorrow’s modeled hours are unavailable');await expect(page.locator('.planning-considerations')).toHaveCount(0);
});
test('SIMULATION Feature B: confidence explains modeled, missing and unknown evidence',async({page})=>{
  const {calls}=await setup(page);await expect(page.locator('#confidence')).toContainText('Limited basis for precaution');await expect(page.locator('#confidence')).toContainText('Modeled · limited');await expect(page.locator('#confidence')).toContainText('Official GRAP verification: UNKNOWN');
  await page.getByText('48-hour forecast evidence — source dates and geographic limitations',{exact:true}).click();await expect(page.locator('#confidence')).toContainText('Source validity');await expect(page.locator('#confidence')).toContainText('Retrieved');expect(calls.filter(p=>p.endsWith('/forecast'))).toHaveLength(1);
});

for(const malformed of ['copies','gap','reversed'])test(`SIMULATION F6-01: ${malformed} forecast hours are incomplete`,async({page})=>{
  await setup(page,v=>{
    if(malformed==='copies')v.forecast.points=Array.from({length:48},()=>structuredClone(v.forecast.points[0]));
    if(malformed==='gap')v.forecast.points[24]=structuredClone(v.forecast.points[25]);
    if(malformed==='reversed')v.forecast.points.reverse();
  });
  const evidence=page.locator('#confidence .status-grid>div').nth(1);
  await expect(evidence.locator('.status-label')).toHaveText('Incomplete evidence');
  await expect(page.locator('#tomorrow')).toContainText('Provisional planning');
  if(malformed==='copies')await expect(page.locator('#tomorrow')).toContainText('0 of 24 hours');
});
test('SIMULATION Feature C: unknown GRAP and source effective dates stay truthful',async({page})=>{
  await setup(page);await expect(page.locator('#regulatory-actions')).toContainText('Current activation is UNKNOWN');await expect(page.locator('#regulatory-actions')).toContainText('No verified applicable restriction');
  await page.getByText('Official originals, publication and effective dates',{exact:true}).click();await expect(page.locator('#regulatory-actions')).toContainText('Effective from');await expect(page.locator('#regulatory-actions')).toContainText('UNVERIFIED');
});
test('SIMULATION Feature D: practical alternatives respect physical-class suspension',async({page})=>{
  await setup(page,v=>{v.verdict.actions[0].recommendation='FOLLOW_PHYSICAL_CLASS_ORDER';});await expect(page.locator('#indoor-alternatives')).toContainText('On-campus indoor suggestions are withheld');await expect(page.locator('.indoor-options')).toHaveCount(0);
});
test('SIMULATION Feature D: current backend actions get bounded school options',async({page})=>{
  await setup(page);await expect(page.locator('.indoor-options>li')).toHaveCount(4);await expect(page.locator('#indoor-alternatives')).toContainText('Indoor air has not been measured');await expect(page.locator('#indoor-alternatives')).toContainText('classroom session');
});
test('SIMULATION Feature E: concise parent notices switch languages without new advisory calls',async({page})=>{
  const {calls}=await setup(page);await page.getByRole('button',{name:'Load school explanation'}).click();await expect(page.locator('.parent-notice')).toContainText('Current backend decision: MODIFIED_OUTDOORS');await expect(page.locator('.parent-notice')).toContainText('UNKNOWN');
  await page.getByRole('button',{name:'हिन्दी',exact:true}).click();await expect(page.locator('.parent-notice')).toHaveAttribute('lang','hi');await expect(page.locator('.parent-notice')).toContainText('अभिभावक सूचना');expect(calls.filter(p=>p.endsWith('/advisory'))).toHaveLength(1);
});

test('SIMULATION Feature F: exact English/Hindi clipboard and WhatsApp draft preserve context',async({page})=>{
  await page.addInitScript(()=>{Object.defineProperty(navigator,'clipboard',{value:{writeText:async(text:string)=>{(window as any).__copied=text;}}});});
  await setup(page);await page.getByRole('button',{name:'Load school explanation'}).click();
  for(const language of ['en','hi']){
    if(language==='hi')await page.getByRole('button',{name:'हिन्दी',exact:true}).click();
    const text=await page.locator('.parent-notice').innerText();const link=page.locator('.notice-controls a');expect(new URL((await link.getAttribute('href'))!).searchParams.get('text')).toBe(text);
    await page.getByRole('button',{name:language==='en'?'Copy Advisory':'सूचना कॉपी करें',exact:true}).click();expect(await page.evaluate(()=>(window as any).__copied)).toBe(text);
    await expect(page.locator('.share-status')).toContainText(language==='en'?'Advisory copied.':'सूचना कॉपी की गई।');
  }
});
test('SIMULATION Feature F: native cancellation is explicit and unsupported sharing has fallback',async({page})=>{
  await page.addInitScript(()=>{Object.defineProperty(navigator,'share',{configurable:true,value:async()=>{throw new DOMException('Canceled','AbortError');}});Object.defineProperty(navigator,'canShare',{configurable:true,value:()=>true});});
  await setup(page);await page.getByRole('button',{name:'Load school explanation'}).click();await page.getByRole('button',{name:'Share Advisory',exact:true}).click();await expect(page.locator('.share-status')).toHaveText('Sharing canceled.');
  await page.evaluate(()=>Object.defineProperty(navigator,'share',{value:undefined}));await page.getByRole('button',{name:'Share Advisory',exact:true}).click();await expect(page.locator('.share-status')).toContainText('Native sharing is unavailable');
});
test('SIMULATION Feature F: clipboard denial exposes labeled selectable manual copy',async({page})=>{
  await page.addInitScript(()=>{Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{throw new Error('Denied');}}});});
  await setup(page);await page.getByRole('button',{name:'Load school explanation'}).click();await page.getByRole('button',{name:'Copy Advisory'}).click();const field=page.getByLabel('Notice for manual copying');await expect(field).toHaveValue(await page.locator('.parent-notice').innerText());await page.getByRole('button',{name:'Select notice text'}).click();await expect(field).toBeFocused();expect(await field.evaluate((el:HTMLTextAreaElement)=>el.selectionEnd-el.selectionStart)).toBeGreaterThan(500);
});
test('SIMULATION Feature F: click-time expiry prevents copying before UI expiry timer fires',async({page})=>{
  await page.addInitScript(()=>{Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{(window as any).__copied=true;}}});});
  await setup(page);await page.getByRole('button',{name:'Load school explanation'}).click();await expect(page.locator('.notice-controls')).toBeVisible();
  // Atomic simulated clock race: no timer/auto-wait can remove the button before its handler.
  await page.evaluate(expired=>{const original=Date.now;Date.now=()=>expired;(Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Copy Advisory') as HTMLButtonElement).click();Date.now=original;},now+121000);
  await expect(page.locator('.share-status')).toContainText('Recheck required');expect(await page.evaluate(()=>(window as any).__copied)).toBeUndefined();await page.clock.fastForward(121000);await expect(page.locator('.notice-controls')).toHaveCount(0);
});
test('SIMULATION Feature F: offline guidance has no sharing controls and reconnects',async({page,context})=>{
  await setup(page);await page.getByRole('button',{name:'Load school explanation'}).click();await expect(page.locator('.notice-controls')).toBeVisible();await context.setOffline(true);await expect(page.locator('.notice-controls')).toHaveCount(0);await context.setOffline(false);
  await expect(page.locator('.canonical')).toBeVisible();await expect(page.locator('.notice-controls')).toHaveCount(0);
});
test('SIMULATION Feature F: invalid localized advice has no sharing controls',async({page})=>{
  await setup(page,v=>{v.advisory.actions[0].hi='';});await page.getByRole('button',{name:'Load school explanation'}).click();await expect(page.locator('.notice-controls')).toHaveCount(0);await expect(page.locator('#advisory')).toContainText('Parent notice unavailable');
});
for(const width of [320,375,430,768,1024,1440])test(`SIMULATION Phase 6 responsive and keyboard controls at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:900});await setup(page);await page.getByRole('button',{name:'Load school explanation'}).click();await page.getByRole('button',{name:'हिन्दी',exact:true}).click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);await expect(page.locator('.notice-controls')).toBeVisible();const copy=page.getByRole('button',{name:'सूचना कॉपी करें',exact:true});await copy.focus();await expect(copy).toBeFocused();await page.keyboard.press('Shift+Tab');await expect(page.getByRole('link',{name:'WhatsApp पर साझा करें',exact:true})).toBeFocused();
});

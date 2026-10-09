// LIVE verification of the owned HTTPS app and real backend. No artificial policy data.
import {test, expect} from '@playwright/test';
import {writeFileSync} from 'node:fs';
const url = 'https://production.d3vzi8hqeh0wba.amplifyapp.com';
const api = 'https://pu8l3a213j.execute-api.us-east-1.amazonaws.com';
const evidencePrefix=process.env.HAWAHAWAI_TEST_EVIDENCE_PREFIX||'phase5';
test('LIVE: Amplify HTTPS, AWS APIs, bilingual advisory, PWA and offline safety', async ({page, context}) => {
  const consoleErrors: string[] = []; const responseStatuses: {method:string;path:string;status:number}[]=[];
  page.on('pageerror', error => consoleErrors.push(error.message));
  page.on('console', message => {if (message.type()==='error') consoleErrors.push(message.text());});
  page.on('response', response => {if (response.url().startsWith(api)) responseStatuses.push({method:response.request().method(),path:new URL(response.url()).pathname,status:response.status()});});
  await page.goto(url); await expect(page.locator('.canonical')).toBeVisible({timeout:30000});
  await expect(page.locator('.school-name')).toHaveText('HawaHawai Demo School');
  await expect(page.locator('.action-list>li')).toHaveCount(7);
  await expect(page.locator('.forecast-list time')).toHaveCount(48,{timeout:30000});
  await expect(page.locator('#status')).toContainText('UNKNOWN'); await expect(page.locator('#sources')).toContainText('no verified station readings');
  await expect(page.locator('#sources')).toContainText('modeled grid estimates'); await expect(page.locator('#outlook')).toContainText('US AQI');
  const manifest = await page.request.get(url+'/manifest.webmanifest'); expect(manifest.status()).toBe(200);
  const body = await manifest.json(); expect(body.short_name).toBe('HawaHawai'); expect(body.icons.some((i:any)=>i.sizes==='512x512')).toBe(true);
  await page.getByRole('button',{name:'Load school explanation'}).click();
  await expect(page.locator('.advisory-text')).toHaveAttribute('lang','en',{timeout:30000});
  await page.getByRole('button',{name:'हिन्दी',exact:true}).click(); await expect(page.locator('.advisory-text')).toHaveAttribute('lang','hi'); await expect(page.locator('.advisory-text')).toContainText('US AQI');
  await page.setViewportSize({width:375,height:1000}); await page.screenshot({path:`.local/${evidencePrefix}-production-mobile.png`});
  for(const width of [320,375,430,768,1024,1440]) {await page.setViewportSize({width,height:1000}); expect(await page.evaluate(()=>document.documentElement.scrollWidth===document.documentElement.clientWidth)).toBe(true);}
  await page.setViewportSize({width:1440,height:1000}); await page.getByRole('link',{name:'Today’s decision',exact:true}).click(); await page.screenshot({path:`.local/${evidencePrefix}-production-desktop.png`});
  await page.evaluate(async()=>{await navigator.serviceWorker.ready;}); await page.reload(); await expect(page.locator('.canonical')).toBeVisible({timeout:30000});
  expect(await page.evaluate(()=>!!navigator.serviceWorker.controller)).toBe(true);
  const cached = await page.evaluate(async()=>{const urls:string[]=[];for(const name of await caches.keys())for(const request of await(await caches.open(name)).keys())urls.push(request.url);return urls;});
  expect(cached.some(x=>x.includes('/v1/')||x.endsWith('/health'))).toBe(false);
  await context.setOffline(true); await expect(page.locator('#today')).toContainText('Current recommendation unavailable'); await expect(page.locator('.action-list')).toHaveCount(0);
  await page.reload(); await expect(page.locator('#today')).toContainText('Reconnect to check the latest guidance'); await expect(page.locator('.action-list')).toHaveCount(0);
  await context.setOffline(false); await expect(page.locator('.canonical')).toBeVisible({timeout:30000});
  await expect(page.locator('.forecast-list time')).toHaveCount(48,{timeout:30000});
  expect(responseStatuses.filter(x=>x.path.endsWith('/verdict'))).toHaveLength(3);
  expect(responseStatuses.every(x=>x.status===200)).toBe(true); expect(consoleErrors).toEqual([]);
  writeFileSync(`.local/${evidencePrefix}-production-regression-browser-evidence.json`,JSON.stringify({url,responseStatuses,consoleErrors,cacheEntries:cached.length,safetyCacheEntries:0,responsiveWidths:[320,375,430,768,1024,1440],offlineReload:true},null,2));
});

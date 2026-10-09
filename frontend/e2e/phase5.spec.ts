// All artificial policy/provider states are isolated browser mocks. No AWS writes.
import {test, expect, type Page, type BrowserContext} from '@playwright/test';
import {readFileSync} from 'node:fs';
const fixture = (name: string) => JSON.parse(readFileSync(new URL('../tests/fixtures/' + name + '-simulation.json', import.meta.url), 'utf8'));
const api = 'https://pu8l3a213j.execute-api.us-east-1.amazonaws.com';
const now = Date.now();
function rebase(value: any): any {
  if (Array.isArray(value)) return value.map(rebase);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v]) => [k,rebase(v)]));
  if (typeof value === 'string' && /^2026-10-08T/.test(value)) return new Date(Date.parse(value) + now - Date.parse('2026-10-08T08:00:00Z')).toISOString();
  return value;
}
const decision = (state = 'MODIFIED_OUTDOORS') => ({...rebase(fixture(state)), valid_until: new Date(now + 120000).toISOString()});
async function mock(page: Page, options: {state?: string; failure?: string; status?: number; delay?: number; missing?: boolean; stale?: boolean} = {}) {
  const current = decision(options.state);
  const air = rebase(fixture('air')); const forecast = rebase(fixture('forecast'));
  const advisory = rebase(fixture('advisory')); advisory.authoritative_decision = current; advisory.valid_until = current.valid_until;
  if (options.missing) {forecast.points[0].pollutants = []; forecast.points[0].aqi = [];}
  if (options.stale) {air.status = air.freshness_status = 'stale'; forecast.status = forecast.freshness_status = 'stale';}
  const calls: string[] = [];
  await page.route(api + '/**', async route => {
    const path = new URL(route.request().url()).pathname; calls.push(path);
    if (options.delay) await new Promise(resolve => setTimeout(resolve, options.delay));
    if (options.failure && path.endsWith(options.failure)) {
      if (options.status) await route.fulfill({status: options.status, json: {error: 'SIMULATION_PRIVATE_EXCEPTION'}});
      else await route.abort('connectionfailed');
      return;
    }
    const body = path.endsWith('/health') ? {status:'ok', service:'hawahawai-backend', phase:0, timestamp:new Date(now).toISOString()}
      : path.endsWith('/verdict') ? current : path.endsWith('/grap') ? current.regulatory_status : path.endsWith('/air') ? air
      : path.endsWith('/forecast') ? forecast : path.endsWith('/advisory') ? advisory : rebase(fixture('school'));
    await route.fulfill({status: 200, json: body});
  });
  return {calls, current};
}
async function ready(page: Page) {await expect(page.locator('.canonical')).toBeVisible(); await expect(page.locator('.forecast-list time')).toHaveCount(48);}

for (const state of ['GO_OUTDOORS','MODIFIED_OUTDOORS','INDOOR_ONLY','DATA_INSUFFICIENT']) {
  test('SIMULATION: authoritative ' + state, async ({page}) => {await mock(page,{state}); await page.goto('/'); await expect(page.locator('.canonical')).toHaveText(state); await expect(page.locator('.action-list>li')).toHaveCount(7);});
}
for (const width of [320,375,430,768,1024,1440]) {
  test('SIMULATION: responsive layout at ' + width + 'px', async ({page}) => {await mock(page); await page.setViewportSize({width,height:900}); await page.goto('/'); await ready(page);
    const dimensions = await page.evaluate(() => ({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth})); expect(dimensions.scroll).toBe(dimensions.client);
    await expect(page.getByRole('button',{name:'Refresh current data'})).toBeVisible(); await page.getByRole('link',{name:'48-hour outlook',exact:true}).click(); await expect(page.locator('.forecast-scroll')).toBeVisible();});
}
test('SIMULATION: loading state is announced', async ({page}) => {await mock(page,{delay:500}); await page.goto('/'); await expect(page.getByRole('heading',{level:1})).toHaveText('Checking the latest guidance…'); await ready(page);});
for (const status of [400,404,503]) test('SIMULATION: backend '+status+' failure', async ({page}) => {await mock(page,{failure:'/verdict',status}); await page.goto('/'); await expect(page.locator('#today')).toContainText('Current recommendation unavailable'); await expect(page.locator('.action-list')).toHaveCount(0); await expect(page.locator('.forecast-list time')).toHaveCount(48);});
test('SIMULATION: network failure with no request loop', async ({page}) => {const {calls} = await mock(page,{failure:'/verdict'}); await page.goto('/'); await expect(page.locator('#today')).toContainText('Connection failed or timed out'); await page.clock.install(); await page.clock.fastForward(60000); expect(calls.filter(x => x.endsWith('/verdict'))).toHaveLength(1);});
test('SIMULATION: stale and missing forecast values remain explicit', async ({page}) => {await mock(page,{missing:true,stale:true}); await page.goto('/'); await ready(page); await expect(page.locator('#outlook')).toContainText('Modeled forecast · stale'); await expect(page.locator('.forecast-list>li').first()).toContainText('Missing');});
test('SIMULATION: expiry hides actions and advisory without extending deadline', async ({page}) => {await mock(page); await page.clock.install({time:new Date(now)}); await page.goto('/'); await ready(page); await page.getByRole('button',{name:'Load school explanation'}).click(); await expect(page.locator('.advisory-text')).toBeVisible(); await page.clock.fastForward(120001); await expect(page.getByRole('heading',{level:1})).toHaveText('RECHECK REQUIRED'); await expect(page.locator('.action-list')).toHaveCount(0); await expect(page.locator('.advisory-text')).toHaveCount(0);});
test('SIMULATION: fallback and English/Hindi switching', async ({page}) => {await mock(page); await page.goto('/'); await ready(page); await page.getByRole('button',{name:'Load school explanation'}).click(); await expect(page.locator('#advisory')).toContainText('Deterministic fallback'); await expect(page.locator('.advisory-text')).toHaveAttribute('lang','en'); await page.getByRole('button',{name:'हिन्दी',exact:true}).click(); await expect(page.locator('.advisory-text')).toHaveAttribute('lang','hi'); await expect(page.locator('.advisory-text')).toContainText('US AQI'); await page.getByRole('button',{name:'English',exact:true}).click(); await expect(page.locator('.advisory-text')).toHaveAttribute('lang','en');});
test('SIMULATION: keyboard navigation and visible focus', async ({page}) => {await mock(page); await page.goto('/'); await ready(page); await page.keyboard.press('Tab'); await expect(page.getByRole('link',{name:'Skip to current decision'})).toBeFocused(); await page.keyboard.press('Enter'); await expect(page.getByRole('heading',{level:1})).toBeVisible(); const focusedOutline = await page.evaluate(() => getComputedStyle(document.activeElement!).outlineStyle); expect(focusedOutline).not.toBe('none');});
test('SIMULATION: app shell works offline, safety data never cached', async ({page,context}) => {
  await mock(page); await page.goto('/'); await ready(page);
  await page.evaluate(async () => {await navigator.serviceWorker.ready;}); await page.reload(); await ready(page);
  const cached = await page.evaluate(async () => {const urls: string[]=[]; for (const name of await caches.keys()) for (const request of await (await caches.open(name)).keys()) urls.push(request.url); return urls;});
  expect(cached.some(url => url.includes('/v1/') || url.endsWith('/health'))).toBe(false); expect(cached.some(url=>url.includes('/assets/'))).toBe(true);
  await context.setOffline(true); await expect(page.getByRole('heading',{level:1})).toHaveText('Current recommendation unavailable'); await expect(page.locator('.action-list')).toHaveCount(0);
  await page.reload(); await expect(page.locator('#today')).toContainText('Reconnect to check the latest guidance'); await expect(page.locator('.action-list')).toHaveCount(0); await context.setOffline(false); await ready(page);
});

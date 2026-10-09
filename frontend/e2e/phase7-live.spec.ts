// Actual production clock/expiry and immutable history. No route mocks or clock overrides.
import {test,expect} from '@playwright/test';
import {writeFileSync} from 'node:fs';
const api='https://pu8l3a213j.execute-api.us-east-1.amazonaws.com';
const url='https://production.d3vzi8hqeh0wba.amplifyapp.com';
const prefix=process.env.HAWAHAWAI_TEST_EVIDENCE_PREFIX||'phase7';
test('LIVE Phase 7 natural expiry withholds actions/sharing; history remains audit-only',async({page})=>{
  test.setTimeout(360000);const calls:string[]=[];
  page.on('request',r=>{if(r.url().startsWith(api))calls.push(new URL(r.url()).pathname);});
  const response=page.waitForResponse(r=>r.url()===api+'/v1/schools/delhi-demo-school/verdict');
  await page.goto(url);const verdict=await(await response).json();
  await expect(page.locator('.canonical')).toHaveText(verdict.decision);
  const advisoryResponse=page.waitForResponse(r=>r.url().endsWith('/advisory')&&r.status()===200);
  await page.getByRole('button',{name:'Load school explanation'}).click();const advisory=await(await advisoryResponse).json();
  expect(advisory.verdict_id).toBe(verdict.decision_id);await expect(page.locator('.notice-controls')).toBeVisible();
  await page.getByRole('button',{name:'Load today’s historical record'}).click();
  await expect(page.locator('.history-record')).toContainText('HISTORICAL · NOT ACTIONABLE');
  await expect(page.locator('.history-record button,.history-record a')).toHaveCount(0);
  const remaining=Date.parse(verdict.valid_until)-Date.now();expect(remaining).toBeGreaterThan(0);expect(remaining).toBeLessThanOrEqual(300000);
  await expect(page.getByRole('heading',{level:1})).toHaveText('RECHECK REQUIRED',{timeout:remaining+35000});
  await expect(page.locator('.notice-controls,.parent-notice,.action-list,.advisory-text')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Load school explanation'})).toBeDisabled();
  expect(calls.filter(p=>p.endsWith('/verdict'))).toHaveLength(1);expect(calls.filter(p=>p.endsWith('/advisory'))).toHaveLength(1);
  writeFileSync(`.local/${prefix}-natural-expiry.json`,JSON.stringify({checked_at:new Date().toISOString(),decision_id:verdict.decision_id,
    original_valid_until:verdict.valid_until,observed_at:new Date().toISOString(),clock:'Actual wall clock; no mocks',calls,
    sharingControls:0,currentActions:0,history:'Audit-only; no share controls'},null,2));
});

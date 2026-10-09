import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {evidenceConfidence} from '../src/SourceConfidence.tsx';
import {forecastCoverage,forecastHour} from '../src/forecastCoverage.ts';
import {tomorrowOutlook} from '../src/TomorrowPlanner.tsx';
const fixture=()=>JSON.parse(readFileSync(new URL('./fixtures/forecast-simulation.json',import.meta.url),'utf8'));
const now=Date.parse('2026-10-08T08:00:00Z');

test('F6-01: 48 duplicate forecast timestamps are incomplete evidence',()=>{
  const value=fixture();
  value.points=Array.from({length:48},()=>structuredClone(value.points[0]));
  assert.equal(evidenceConfidence(value,now).label,'Incomplete evidence');
});

test('F6-01: valid 48 consecutive UTC hours remain modeled and limited',()=>{
  assert.equal(evidenceConfidence(fixture(),now).label,'Modeled · limited');
  assert.equal(forecastCoverage(fixture(),now).complete,true);
});
for(const [name,change] of [
  ['missing hour',v=>v.points.splice(10,1)],
  ['gap despite 48 entries',v=>v.points[10].valid_at=new Date(Date.parse(v.points[10].valid_at)+7200000).toISOString()],
  ['reverse chronology',v=>v.points.reverse()],
  ['invalid timestamp',v=>v.points[10].valid_at='not-a-date'],
  ['non-hour timestamp',v=>v.points[10].valid_at=v.points[10].valid_at.replace(':00:00',':01:00')],
  ['wrong start',v=>v.forecast_start=v.points[1].valid_at],
  ['wrong end',v=>v.forecast_end=v.points[46].valid_at],
  ['missing bounds',v=>v.forecast_start=null],
  ['wrong horizon',v=>v.horizon_hours=24],
  ['extra hour',v=>v.points.push(structuredClone(v.points.at(-1)))],
  ['past window masquerading as freshly retrieved',v=>{v.points.forEach(p=>p.valid_at=new Date(Date.parse(p.valid_at)-86400000).toISOString());v.forecast_start=v.points[0].valid_at;v.forecast_end=v.points.at(-1).valid_at;}],
  ['future window outside current forecast',v=>{v.points.forEach(p=>p.valid_at=new Date(Date.parse(p.valid_at)+86400000).toISOString());v.forecast_start=v.points[0].valid_at;v.forecast_end=v.points.at(-1).valid_at;}],
])test(`F6-01: ${name} yields incomplete evidence`,()=>{
  const value=fixture();change(value);assert.equal(evidenceConfidence(value,now).label,'Incomplete evidence');
});
test('F6-01: offset aliases cannot inflate coverage or planner hours',()=>{
  const value=fixture();const index=value.points.findIndex(p=>tomorrowOutlook(value,now).points.includes(p));
  const original=value.points[index];
  const alias=structuredClone(original);alias.valid_at=new Date(Date.parse(original.valid_at)+19800000).toISOString().replace('Z','+05:30');
  alias.aqi[0].value+=1;
  value.points[index+1]=alias;
  assert.equal(evidenceConfidence(value,now).label,'Incomplete evidence');
  assert.equal(tomorrowOutlook(value,now).hours,22);
});
test('F6-01: legitimate IST and UTC offsets/year rollover preserve coverage',()=>{
  const value=fixture();const start=Date.parse('2026-12-31T18:00:00Z');
  value.retrieved_at=new Date(start).toISOString();value.cache.fresh_until=new Date(start+3600000).toISOString();
  value.points.forEach((p,i)=>p.valid_at=new Date(start+i*3600000+19800000).toISOString().replace('Z','+05:30'));
  value.forecast_start=value.points[0].valid_at;value.forecast_end=value.points.at(-1).valid_at;
  assert.equal(forecastCoverage(value,start).complete,true);
  assert.equal(evidenceConfidence(value,start).label,'Modeled · limited');
  assert.equal(tomorrowOutlook(value,start).hours,24);
});
test('F6-01: invalid calendar dates, implicit local time and fractional hours rejected',()=>{
  for(const value of ['2026-02-30T08:00:00Z','2026-10-08T08:00:00','2026-10-08T08:00:00.000001Z','2026-10-08T08:30:00Z'])assert.equal(forecastHour(value),null);
});
test('F6-01: an old cached window cannot claim current 48-hour coverage',()=>{
  const value=fixture();value.retrieved_at='2026-10-08T06:00:00Z';
  value.points.forEach(p=>p.valid_at=new Date(Date.parse(p.valid_at)-3600000).toISOString());
  value.forecast_start=value.points[0].valid_at;value.forecast_end=value.points.at(-1).valid_at;
  assert.equal(evidenceConfidence(value,now).label,'Incomplete evidence');
});

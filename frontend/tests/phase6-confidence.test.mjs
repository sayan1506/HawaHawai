import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {evidenceConfidence,recommendationConfidence} from '../src/SourceConfidence.tsx';
const f=name=>JSON.parse(readFileSync(new URL('./fixtures/'+name+'-simulation.json',import.meta.url),'utf8'));const now=Date.parse('2026-10-08T08:00:00Z');
test('confidence unavailable precedes other classifications',()=>{const v=f('forecast');v.status='unavailable';assert.equal(evidenceConfidence(v,now).label,'Unavailable evidence');assert.equal(evidenceConfidence(undefined,now).label,'Unavailable evidence');});
test('confidence stale precedes partial/modeled classifications and honors expiry',()=>{const v=f('forecast');v.status='stale';v.points=[];assert.equal(evidenceConfidence(v,now).label,'Stale evidence');v.status='available';v.cache.fresh_until=new Date(now).toISOString();assert.equal(evidenceConfidence(v,now).label,'Stale evidence');});
test('confidence missing hours/pollutants/AQI/provenance remains incomplete',()=>{for(const change of [v=>v.points.pop(),v=>v.points[0].aqi=[],v=>v.points[0].pollutants=[],v=>v.sources=[]]){const v=f('forecast');change(v);assert.equal(evidenceConfidence(v,now).label,'Incomplete evidence');}});
test('fresh modeled forecast is limited and documents absent initialization',()=>{const c=evidenceConfidence(f('forecast'),now);assert.equal(c.label,'Modeled · limited');assert.ok(c.reasons.some(r=>r.includes('not physical school')));assert.ok(c.reasons.some(r=>r.includes('initialization timestamp')));assert.doesNotMatch(JSON.stringify(c),/highly reliable|officially verified|\d+%/);});
test('F6-01: 48 copies of one timestamp are incomplete evidence',()=>{const v=f('forecast');v.points=Array.from({length:48},()=>structuredClone(v.points[0]));assert.equal(evidenceConfidence(v,now).label,'Incomplete evidence');});
for(const [name,change] of [
  ['duplicate hour',v=>v.points[24].valid_at=v.points[23].valid_at],
  ['missing hour replaced by later hour',v=>v.points[24].valid_at=new Date(Date.parse(v.points[24].valid_at)+3600000).toISOString()],
  ['reversed chronology',v=>v.points.reverse()],
  ['invalid timestamp',v=>v.points[0].valid_at='not-a-date'],
  ['invalid calendar date',v=>v.points[0].valid_at='2026-02-30T08:00:00Z'],
  ['non-hour timestamp',v=>v.points[0].valid_at='2026-10-08T08:01:00Z'],
  ['wrong start metadata',v=>v.forecast_start=v.points[1].valid_at],
  ['wrong end metadata',v=>v.forecast_end=v.points[46].valid_at],
  ['wrong horizon',v=>v.horizon_hours=24],
  ['extra hour',v=>v.points.push(structuredClone(v.points[47]))],
])test('F6-01 rejects '+name,()=>{const v=f('forecast');change(v);assert.equal(evidenceConfidence(v,now).label,'Incomplete evidence');});
test('F6-01 rejects a consecutive window outside current/next UTC hour',()=>{for(const offset of [-3600000,7200000]){const v=f('forecast');v.points.forEach(p=>p.valid_at=new Date(Date.parse(p.valid_at)+offset).toISOString());v.forecast_start=v.points[0].valid_at;v.forecast_end=v.points[47].valid_at;assert.equal(evidenceConfidence(v,now).label,'Incomplete evidence');}});
test('F6-01 accepts equivalent IST offsets and legitimate year rollover',()=>{const v=f('forecast');const start=Date.parse('2026-12-31T18:00:00Z');v.points.forEach((p,i)=>p.valid_at=new Date(start+i*3600000+19800000).toISOString().replace('Z','+05:30'));v.forecast_start=v.points[0].valid_at;v.forecast_end=v.points[47].valid_at;v.cache.fresh_until=new Date(start+3600000).toISOString();assert.equal(evidenceConfidence(v,start+1000).label,'Modeled · limited');});
test('F6-01 accepts the next UTC hour between hourly boundaries',()=>{const v=f('forecast');assert.equal(evidenceConfidence(v,now-1000).label,'Modeled · limited');});
test('unknown/stale/conflicting GRAP and absent stations cannot become high confidence',()=>{for(const state of ['UNKNOWN','STALE','CONFLICTING']){const v=f('MODIFIED_OUTDOORS');v.regulatory_status.verification_state=state;const c=recommendationConfidence(v,true,now);assert.equal(c.label,'Limited basis for precaution');assert.ok(c.reasons.some(r=>r.includes(state)));assert.ok(c.reasons.some(r=>r.includes('physical station')));}});
test('offline/historical/expired recommendation confidence is unavailable',()=>{const v=f('MODIFIED_OUTDOORS');assert.equal(recommendationConfidence(v,false,now).label,'Current basis unavailable');assert.equal(recommendationConfidence(v,true,Date.parse(v.valid_until)).label,'Current basis unavailable');v.persistence={historical:true};assert.equal(recommendationConfidence(v,true,now).label,'Current basis unavailable');});
test('missing fresh activity forecast states incomplete basis without a new verdict',()=>{const v=f('MODIFIED_OUTDOORS');v.data_quality.forecast_available=false;const c=recommendationConfidence(v,true,now);assert.equal(c.label,'Incomplete basis');assert.equal(v.decision,'MODIFIED_OUTDOORS');assert.equal('decision' in c,false);});

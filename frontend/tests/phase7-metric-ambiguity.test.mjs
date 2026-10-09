import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {evidenceConfidence} from '../src/SourceConfidence.tsx';
import {tomorrowOutlook,TomorrowPlanner} from '../src/TomorrowPlanner.tsx';

const now=Date.parse('2026-10-08T08:00:00Z');
const fixture=()=>JSON.parse(readFileSync(new URL('./fixtures/forecast-simulation.json',import.meta.url),'utf8'));
for(const conflicting of [false,true]) {
  const name=conflicting?'conflicting':'identical duplicate';
  const forecast=()=>{const f=fixture();f.points.forEach(p=>p.aqi.push({...p.aqi[0],value:conflicting?300:p.aqi[0].value}));return f;};
  test(`confidence withholds completeness for ${name} per-hour US AQI`,()=>{
    assert.equal(evidenceConfidence(forecast(),now).label,'Incomplete evidence');
  });
  test(`planner withholds ${name} per-hour US AQI without negative missing count`,()=>{
    const f=forecast(),outlook=tomorrowOutlook(f,now);
    assert.equal(outlook.hours,24);assert.equal(outlook.missingAqi,24);assert.equal(outlook.range,'Missing');
    const html=renderToStaticMarkup(React.createElement(TomorrowPlanner,{forecast:{state:'success',data:f},online:true,now}));
    assert.equal((html.match(/US AQI · modeled: Missing/g)||[]).length,24);
  });
}

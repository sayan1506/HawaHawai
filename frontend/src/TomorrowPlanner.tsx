import React from 'react';
import type {Evidence, Point} from './api';
import {ResourceStatus, SourceLink, Warnings, type Resource} from './ui';
import {date, evidenceFreshness} from './presentation';
import {forecastCoverage,forecastHour,forecastAqi} from './forecastCoverage';

export function localDay(time: number) {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(time);
  const part = (name:string) => parts.find(p=>p.type===name)!.value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}
export function tomorrowOutlook(value: Evidence | undefined, now: number) {
  const [year,month,day] = localDay(now).split('-').map(Number);
  const tomorrow = new Date(Date.UTC(year,month-1,day+1)).toISOString().slice(0,10);
  const points: Point[] = value && 'points' in value && value.status!=='unavailable'
    ? value.points.filter(p=>forecastHour(p.valid_at)!==null && localDay(Date.parse(p.valid_at))===tomorrow).sort((a,b)=>Date.parse(a.valid_at)-Date.parse(b.valid_at)) : [];
  // Equivalent timestamp representations cannot inflate hours. Identical values
  // can be shown once; conflicting values for the same UTC hour are withheld.
  const groups=new Map<number,Point[]>();
  points.forEach(p=>{const hour=forecastHour(p.valid_at)!;groups.set(hour,[...(groups.get(hour)||[]),p]);});
  const normalized=(p:Point)=>JSON.stringify({...p,valid_at:forecastHour(p.valid_at),
    aqi:p.aqi.map(a=>({...a,forecast_for:a.forecast_for?Date.parse(a.forecast_for):null})),
    pollutants:p.pollutants.map(a=>({...a,forecast_for:a.forecast_for?Date.parse(a.forecast_for):null}))});
  const distinct=[...groups.values()].filter(group=>group.every(p=>normalized(p)===normalized(group[0]))).map(group=>group[0]);
  const aqi = distinct.flatMap(p=>{const value=forecastAqi(p);return value===null?[]:[value];});
  return {tomorrow,points:distinct,hours:distinct.length,missingAqi:distinct.length-aqi.length,complete:!!value&&'points' in value&&forecastCoverage(value,now).complete,
    range:aqi.length ? `${Math.min(...aqi)}–${Math.max(...aqi)}` : 'Missing'};
}
export function TomorrowPlanner({forecast,online,now}: {forecast:Resource<Evidence>;online:boolean;now:number}) {
  const outlook = tomorrowOutlook(forecast.data,now);
  const value = forecast.data;
  return <section id="tomorrow" className="card" aria-labelledby="tomorrow-heading"><p className="eyebrow">PREPARE THE NEXT SCHOOL DAY</p>
    <h2 id="tomorrow-heading">Tomorrow planner</h2><p><strong>{outlook.tomorrow} · Asia/Kolkata</strong></p>
    <p className="notice"><strong>Provisional planning — not tomorrow’s verdict.</strong> Outdoor plans may need modification. Forecasts are uncertain; check the current backend decision and official school orders tomorrow before acting. Today’s verdict does not authorize tomorrow’s activities.</p>
    <ResourceStatus resource={online?forecast:{state:'offline'}} label="tomorrow’s forecast"/>
    {online && value && <><p className="status-label">Modeled outlook · {evidenceFreshness(value,now)}</p>
      {!outlook.complete&&<p className="notice">Incomplete forecast coverage: missing, invalid or duplicated hours, or inconsistent forecast bounds. This outlook cannot establish a complete 48-hour forecast.</p>}
      <p>{outlook.hours} of 24 hours supplied for tomorrow{outlook.hours!==24?' — partial or missing day coverage':''}. {outlook.missingAqi} supplied hours lack unambiguous US AQI.</p>
      <p>Modeled US AQI range: <strong>{outlook.range}</strong> · US AQI is not Indian AQI. No physical school/station observations are established by this forecast.</p>
      <p>Retrieved: {date(value.retrieved_at)} · Recheck forecast: {date(value.cache.fresh_until)}</p>
      {outlook.hours ? <><ul className="planning-considerations"><li><strong>Assembly:</strong> Prepare a shorter-format or permitted indoor assembly contingency; confirm tomorrow’s actions before selecting it.</li>
        <li><strong>Sports:</strong> Keep a rescheduling contingency and a non-exertional classroom activity ready, subject to school orders.</li>
        <li><strong>Physical education:</strong> Prepare a classroom lesson on movement or sports skills if tomorrow’s authoritative actions require an alternative. Indoor air is not automatically safe.</li></ul>
        <details><summary>Tomorrow’s dated modeled hours</summary><ol className="planning-hours">{outlook.points.map(p=><li key={p.valid_at}><time dateTime={p.valid_at}>{date(p.valid_at)}</time>
          <span>US AQI · modeled: {forecastAqi(p)??'Missing'}</span><span>PM2.5: {p.pollutants.find(a=>a.name==='pm2_5')?.value??'Missing'} µg/m³</span></li>)}</ol></details></> : <p>Tomorrow’s modeled hours are unavailable. No planning conclusion can be drawn from missing values.</p>}
      <p>Provider: {value.sources.length?value.sources.map((s,i)=><React.Fragment key={i}>{i>0?' · ':''}<SourceLink url={s.url}>{s.name}</SourceLink></React.Fragment>):'Not supplied'}. Model forecasts describe a grid, not exact exposure at the school.</p>
      <Warnings values={value.warnings} label="Planning evidence limitations"/></>}
  </section>;
}

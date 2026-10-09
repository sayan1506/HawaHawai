import React from 'react';
import type {Evidence, Point} from './api';
import type {Resource} from './ui';
import {ResourceStatus, Warnings, Sources, SourceLink} from './ui';
import {date, evidenceFreshness, pollutantName} from './presentation';

export function Values({point}: {point: Point}) {
  return <dl className="value-grid">{point.pollutants.map((v, i) => <div key={'p'+i}><dt>{pollutantName(v.name)} · modeled</dt><dd>{v.value} {v.original_unit || 'µg/m³'}</dd></div>)}
    {point.aqi.map((v, i) => <div key={'a'+i}><dt>{v.scale} · modeled</dt><dd>{v.value}</dd></div>)}
    {!point.pollutants.length && <div><dt>Pollutants</dt><dd>Missing</dd></div>}{!point.aqi.length && <div><dt>US AQI</dt><dd>Missing</dd></div>}</dl>;
}
export function EnvironmentalView({air, forecast, now}: {air: Resource<Evidence>; forecast: Resource<Evidence>; now: number}) {
  const f = forecast.data;
  const a = air.data && 'modeled_current' in air.data ? air.data : undefined;
  const points = f && 'points' in f ? f.points : [];
  return <>
    <section id="outlook" className="card" aria-labelledby="forecast-heading"><p className="eyebrow">LOOKING AHEAD</p><h2 id="forecast-heading">48-hour outlook</h2>
      <p>Hourly modeled forecasts. These values describe an outlook; they do not identify safe outdoor windows.</p>
      <ResourceStatus resource={forecast} label="48-hour forecast"/>
      {f && <><p className="status-label">Modeled forecast · {evidenceFreshness(f, now)}</p><p>Retrieved: {date(f.retrieved_at)}<br/>Model initialization: {'generated_at' in f ? date(f.generated_at) : 'Not supplied'}</p>
        {points.length > 0 ? <><p>{points.length} forecast hours · {points.length < 48 ? 'Partial outlook: some hours are missing.' : 'Full 48-hour outlook.'} Times shown in Asia/Kolkata.</p>
          <div className="forecast-scroll" tabIndex={0} role="region" aria-label="Hourly modeled forecast, scroll for all hours">
            <ol className="forecast-list">{points.map((p, i) => <li key={i}><time dateTime={p.valid_at}>{date(p.valid_at)}{now >= Date.parse(p.valid_at) && <small>Past forecast hour · not a current reading</small>}</time>
              <dl><div><dt>US AQI · modeled</dt><dd>{p.aqi.find(v => v.scale === 'US_AQI')?.value ?? 'Missing'}</dd></div>
                <div><dt>PM2.5 · µg/m³</dt><dd>{p.pollutants.find(v => v.name === 'pm2_5')?.value ?? 'Missing'}</dd></div>
                <div><dt>PM10 · µg/m³</dt><dd>{p.pollutants.find(v => v.name === 'pm10')?.value ?? 'Missing'}</dd></div></dl></li>)}</ol>
          </div></> : <p>Full 48-hour forecast unavailable. Missing hours and values have not been replaced.</p>}
        <p>Provider: {f.sources.length ? f.sources.map((s, i) => <React.Fragment key={i}>{i > 0 && ' · '}<SourceLink url={s.url}>{s.name}</SourceLink></React.Fragment>) : 'Not supplied'}. US AQI is not Indian AQI.</p>
        <Warnings values={f.warnings} label="Forecast limitations"/></>}
    </section>
    <section id="sources" className="card" aria-labelledby="sources-heading"><p className="eyebrow">EVIDENCE & PROVENANCE</p><h2 id="sources-heading">Data sources</h2>
      <p>Open-Meteo / Copernicus CAMS values are modeled grid estimates, not measurements at the school.</p>
      <ResourceStatus resource={air} label="current environmental evidence"/>
      <h3>Official station observations</h3><p className="status-label">{a?.observations.length ? 'Attributed observations available' : 'Unavailable — no verified station readings'}</p>
      <p>Official Indian AQI is currently unavailable. Missing evidence does not mean zero pollution or safe air.</p>
      {a?.observation_providers.map((p, i) => <div className="provider" key={i}><strong><SourceLink url={p.source_url}>{p.source_name}</SourceLink></strong><p>{p.status}<br/>Checked: {date(p.retrieved_at)}</p><Warnings values={p.warnings} label="Provider limitations"/></div>)}
      <h3>Modeled current conditions</h3>{a ? <><p className="status-label">{evidenceFreshness(a, now)}</p>
        {a.modeled_current ? <><p>Forecast for: {date(a.modeled_current.valid_at)} · not an observation</p><Values point={a.modeled_current}/></> : <p>Modeled current values unavailable.</p>}
        <p>Retrieved: {date(a.retrieved_at)} · Retrieval time is not model initialization time.</p><Warnings values={a.warnings}/>
        {a.modeled_current && <details><summary>Pollutant units and averaging periods</summary><ul>{a.modeled_current.pollutants.map((p, i) => <li key={i}>{pollutantName(p.name)} · {p.original_unit} ({p.unit}) · {p.averaging_period} · {p.source_id} · modeled forecast for {date(p.forecast_for)}</li>)}</ul></details>}
        <details><summary>Current source provenance</summary><Sources values={a.sources} now={now}/></details></> : <p>Current modeled evidence unavailable.</p>}
      {f && <details><summary>Forecast source provenance</summary><Sources values={f.sources} now={now}/></details>}
      <p className="notice">Pollutants are concentrations in µg/m³. US_AQI is a separate scale; it is never converted into Indian AQI or used to infer a GRAP stage here.</p>
    </section>
  </>;
}

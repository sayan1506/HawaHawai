import {useEffect, useState} from 'react';
import {getEvidence, type Evidence, type Point} from './api';
import school from '../../contracts/demo-school.json';

const date = (value: string) => new Date(value).toLocaleString('en-IN', {timeZone: school.timezone, dateStyle: 'medium', timeStyle: 'short'}) + ' IST';

function Values({point}: {point: Point}) {
  return <>{point.pollutants.length ? point.pollutants.map(v => <span className="reading" key={v.name}>{v.name.replace('pm2_5', 'PM2.5').toUpperCase()}: {v.value} {v.original_unit} <small>modeled · {v.source_id} · {date(v.forecast_for)}</small></span>) : <p>Pollutant concentrations missing.</p>}
    {point.aqi.map(v => <span className="reading" key={v.scale}>{v.scale}: {v.value} <small>modeled · {v.source_id} · {date(v.forecast_for)}</small></span>)}{!point.aqi.length && <p>AQI missing.</p>}</>;
}

export function EnvironmentalView() {
  const [air, setAir] = useState<Evidence>();
  const [forecast, setForecast] = useState<Evidence>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timer = window.setTimeout(() => controller.abort(), 28000);
    setAir(undefined); setForecast(undefined); setError('');
    // Sequential requests let the first provider response fill both independent caches.
    getEvidence(school.school_id, 'air', controller.signal).then(async value => {
      if (active) setAir(value);
      const outlook = await getEvidence(school.school_id, 'forecast', controller.signal);
      if (active) setForecast(outlook);
    }).catch(() => {if (active) setError('Environmental data could not be loaded. No safe-air conclusion is available.');}).finally(() => window.clearTimeout(timer));
    return () => {active = false; controller.abort(); window.clearTimeout(timer);};
  }, [attempt]);
  return <section className="card" aria-labelledby="environment"><h2 id="environment">Phase 1 environmental evidence</h2>
    <p>{school.name} · {school.latitude}, {school.longitude} · {school.timezone}</p>
    <p>No school-safety verdict. US AQI is not Indian AQI. Forecasts are not monitoring-station observations.</p>
    <div role="status" aria-live="polite">{error || (!air && 'Loading environmental evidence…')}</div>
    <button onClick={() => setAttempt(v => v + 1)}>Reload evidence</button>
    {air && <><h3>Official station observations: unavailable</h3><p>No official Indian AQI or station readings have been verified.</p>
      {air.observation_providers?.map(p => <p key={p.source_name}><a href={p.source_url} target="_blank" rel="noreferrer">{p.source_name}</a>: {p.status} · Checked {date(p.retrieved_at)}</p>)}
      <h3>Modeled current conditions · {air.freshness_status}</h3>
      {air.modeled_current ? <Values point={air.modeled_current}/> : <p>Modeled current conditions unavailable. Missing values have not been replaced.</p>}
      <p>Retrieved {air.retrieved_at ? date(air.retrieved_at) : 'unknown'} · Cache: {air.cache.status}</p>
      {air.sources.map(s => <p key={s.name}><a href={s.url} target="_blank" rel="noreferrer">{s.name}</a> · {s.kind} · Retrieved {date(s.retrieved_at)}</p>)}
      <details><summary>Data limitations and warnings</summary><ul>{air.warnings.map(w => <li key={w}>{w}</li>)}</ul></details></>}
    {forecast ? <><h3>48-hour modeled outlook · {forecast.freshness_status}</h3><p>Hourly timestamps in IST. Model initialization time is unavailable; retrieval is not model initialization.</p>
      <p>Retrieved {forecast.retrieved_at ? date(forecast.retrieved_at) : 'unknown'} · Cache: {forecast.cache.status}</p>
      {forecast.sources.map(s => <p key={s.name}><a href={s.url} target="_blank" rel="noreferrer">{s.name}</a> · {s.kind} · Retrieved {date(s.retrieved_at)}</p>)}
      {forecast.points?.length ? <div className="outlook"><table><caption>Dated modeled hourly forecast</caption><thead><tr><th>Forecast for (IST)</th><th>PM2.5 (μg/m³)</th><th>PM10 (μg/m³)</th><th>US AQI</th></tr></thead><tbody>{forecast.points.map(p => <tr key={p.valid_at}><th scope="row">{date(p.valid_at)}</th><td>{p.pollutants.find(v => v.name === 'pm2_5')?.value ?? 'Missing'}</td><td>{p.pollutants.find(v => v.name === 'pm10')?.value ?? 'Missing'}</td><td>{p.aqi[0]?.value ?? 'Missing'}</td></tr>)}</tbody></table><small>Each row: modeled, {forecast.sources[0]?.name}; timestamps identify the forecast hour, not an observation.</small></div> : <p>Full 48-hour forecast unavailable.</p>}
      <details><summary>Forecast warnings</summary><ul>{forecast.warnings.map(w => <li key={w}>{w}</li>)}</ul></details></> : air && !error && <p>Loading 48-hour outlook…</p>}
  </section>;
}

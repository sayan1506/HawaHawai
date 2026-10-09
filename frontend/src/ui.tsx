import React from 'react';
import type {Source} from './contracts';
import {date, readable} from './presentation';
export type Resource<T> = {state: 'loading' | 'success' | 'error' | 'offline'; data?: T; error?: string};
export function ResourceStatus({resource, label}: {resource: Resource<unknown>; label: string}) {
  if (resource.state === 'success') return null;
  return <p className="notice" role="status" aria-live="polite">{resource.state === 'loading' ? `Loading ${label}…`
    : resource.state === 'offline' ? `${label} unavailable offline. Reconnect and refresh.` : resource.error || `${label} unavailable.`}</p>;
}
export function Warnings({values, label = 'Warnings and limitations'}: {values: string[]; label?: string}) {
  return <details className="warnings"><summary>{label}{values.length ? ` (${values.length})` : ''}</summary>
    {values.length ? <ul>{values.map((v, i) => <li key={i}>{readable(v)}</li>)}</ul> : <p>No additional warnings supplied.</p>}</details>;
}
export function SourceLink({url, children}: {url: string; children: React.ReactNode}) {
  return /^https:\/\//i.test(url) ? <a href={url} target="_blank" rel="noreferrer">{children}<span className="sr-only"> (opens in a new tab)</span></a> : <span>{children}</span>;
}
export function Sources({values, now}: {values: Source[]; now: number}) {
  return values.length ? <ul className="source-list">{values.map((s, i) => <li key={i}>
    <strong><SourceLink url={s.url}>{s.name}</SourceLink></strong><p>{s.kind === 'model_forecast' ? 'Modeled forecast · not a physical observation' : readable(s.kind)}
      {' · '}{s.valid_until && now >= Date.parse(s.valid_until) ? 'stale — source validity elapsed' : s.freshness}</p>
    <dl className="facts"><div><dt>Retrieved</dt><dd>{date(s.retrieved_at)}</dd></div><div><dt>Observed</dt><dd>{date(s.observed_at)}</dd></div>
      <div><dt>Source validity</dt><dd>{date(s.valid_until)}</dd></div></dl>
    {s.location && <p>Source location: {s.location.latitude}, {s.location.longitude}{s.kind === 'measurement' ? ' · physical station' : ' · model grid'}</p>}
    {s.limitations.length > 0 && <ul>{s.limitations.map((x, j) => <li key={j}>{x}</li>)}</ul>}
  </li>)}</ul> : <p>No source information was supplied. Missing provenance is not evidence of safe air.</p>;
}

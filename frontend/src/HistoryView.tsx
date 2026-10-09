import React, {useEffect, useRef, useState} from 'react';
import {getHistory, errorMessage} from './api';
import type {VerdictHistory} from './contracts';
import {ResourceStatus, type Resource} from './ui';
import {date} from './presentation';
export function HistoryContent({value}: {value: VerdictHistory}) {
  return <div className="history-record"><p className="status-label">HISTORICAL · NOT ACTIONABLE</p><p>Audit record only. Use today’s current decision for guidance.</p>
    <dl className="facts"><div><dt>Recorded decision</dt><dd>{value.record.decision.decision}</dd></div><div><dt>Evaluated</dt><dd>{date(value.record.decision.evaluation_time)}</dd></div>
      <div><dt>Original expiry</dt><dd>{date(value.record.decision.valid_until)}</dd></div><div><dt>Expired at retrieval</dt><dd>{value.expired ? 'Yes' : 'No — still historical, never actionable'}</dd></div>
      <div><dt>Matches current school profile</dt><dd>{value.matches_current_profile ? 'Yes' : 'No — profile has changed'}</dd></div></dl></div>;
}
export function HistoryView({online}: {online: boolean}) {
  const [value, setValue] = useState<Resource<VerdictHistory>>({state: 'success'});
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function load() {
    controller.current?.abort(); const c = new AbortController(); controller.current = c; setValue({state: 'loading'});
    try {const data = await getHistory('delhi-demo-school', c.signal); if (!c.signal.aborted) setValue({state: 'success', data});}
    catch (e) {if (!c.signal.aborted) setValue({state: 'error', error: errorMessage(e)});}
  }
  return <section className="card" aria-labelledby="history-heading"><h2 id="history-heading">Transparency / audit</h2><p>Daily records preserve what was evaluated. They are never current recommendations.</p>
    <button className="secondary" disabled={!online || value.state === 'loading'} onClick={load}>Load today’s historical record</button>
    <ResourceStatus resource={online ? value : {state: 'offline'}} label="historical record"/>{online && value.data && <HistoryContent value={value.data}/>}</section>;
}

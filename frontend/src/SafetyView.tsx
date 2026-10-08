import {useEffect, useState} from 'react';
import {getSafety, type VerdictResponse, type GrapResponse} from './api';
import school from '../../contracts/demo-school.json';
import {verdictExpired} from './verdictValidity';

export function SafetyView() {
  const [verdict, setVerdict] = useState<VerdictResponse>();
  const [grap, setGrap] = useState<GrapResponse>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    if (!verdict) {setExpired(false); return;}
    setExpired(verdictExpired(verdict.valid_until, Date.now()));
    const timer = window.setTimeout(() => setExpired(true), Math.max(0, Date.parse(verdict.valid_until) - Date.now()));
    return () => window.clearTimeout(timer);
  }, [verdict]);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timer = window.setTimeout(() => controller.abort(), 28000);
    setVerdict(undefined); setGrap(undefined); setError('');
    getSafety(school.school_id, 'grap', controller.signal).then(async value => {
      if (active) setGrap(value as GrapResponse);
      const result = await getSafety(school.school_id, 'verdict', controller.signal);
      if (active) setVerdict(result as VerdictResponse);
    }).catch(() => {if (active) setError('School recommendation could not be loaded. Verify official status and missing evidence before outdoor activities.');})
      .finally(() => window.clearTimeout(timer));
    return () => {active = false; controller.abort(); window.clearTimeout(timer);};
  }, [attempt]);
  return <section className="card" aria-labelledby="school-policy"><h2 id="school-policy">Deterministic school recommendation · Phase 2</h2>
    <p>Conditional activity advice, not a guarantee of safe air, legal school closure or measured indoor air. Modeled US AQI never activates GRAP.</p>
    <div role="status" aria-live="polite">{error || (!verdict && 'Loading school recommendation…')}</div>
    <button onClick={() => setAttempt(v => v + 1)}>Reload recommendation</button>
    {grap && <><h3>Official GRAP verification: {grap.verification_state}</h3>
      <p>Active stage: {grap.active_stage ?? 'Not verified / none confirmed'} · Schedule: {grap.schedule_version}</p>
      <p>Human verification: {grap.verification_action_recorded ? grap.verified_at : 'Not performed'} · Registry: {grap.snapshot_version}</p></>}
    {verdict && expired && <p className="warning" role="status">RECHECK REQUIRED: the recommendation has expired. Reload before using its actions; no new safety decision has been made.</p>}
    {verdict && !expired && <><h3 data-testid="school-verdict">{verdict.decision.replaceAll('_', ' ')}</h3>
      <p>Policy {verdict.policy_version} · Evaluated {new Date(verdict.evaluation_time).toLocaleString()} · Recheck by {new Date(verdict.valid_until).toLocaleString()}</p>
      {verdict.requires_regulatory_verification && <p className="warning">VERIFY STATUS: this precaution does not establish legal permission for outdoor activity. Review current official school notices.</p>}
      <p>Official observations: {verdict.data_quality.official_observations_available ? 'available' : 'unavailable'} · Usable modeled current: {String(verdict.data_quality.modeled_data_available)} · Activity forecast: {String(verdict.data_quality.forecast_available)}</p>
      <h3>Why this recommendation</h3><ul>{verdict.rule_evaluations.map((r, i) => <li key={`${r.rule_id}-${i}`}><code>{r.rule_id}</code>: {r.message}</li>)}</ul>
      <h3>School actions</h3><ul>{verdict.actions.map((a, i) => <li key={`${a.activity}-${i}`}><strong>{a.activity.replaceAll('_', ' ')}</strong> · {a.recommendation} · {a.mandatory ? `Mandatory only for listed grades: ${a.applicable_grades.join(', ')}` : 'Project precaution / review'}<p>{a.instruction}</p></li>)}</ul>
      <details><summary>Evidence used (US AQI health policy, not Indian regulatory thresholds)</summary><ul>{verdict.evidence.map(e => <li key={e.evidence_id}>{e.value} {e.scale} · {e.source_type} · {e.source_id} · {new Date(e.timestamp).toLocaleString()} · {e.freshness}</li>)}</ul></details>
      <details><summary>Warnings and missing evidence</summary><ul>{verdict.warnings.map(w => <li key={w}>{w}</li>)}</ul></details>
      <h3>Policy sources</h3>{verdict.policy_sources.map(s => <p key={s.evidence_id}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a> · {s.scope}</p>)}</>}
    {grap && <><h3>Official documents investigated (not current activation claims)</h3>{grap.source_documents.map(d => <p key={d.document_id}><a href={d.url} target="_blank" rel="noreferrer">{d.title}</a> · {d.authority} · Published {d.published_on} · {d.verification_status}</p>)}</>}
  </section>;
}

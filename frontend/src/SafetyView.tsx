import React from 'react';
import type {VerdictResponse, GrapResponse} from './api';
import type {Resource} from './ui';
import {ResourceStatus, Warnings, SourceLink} from './ui';
import {date, readable, guidanceState, regulatoryLabel} from './presentation';

export function SafetyView({resource, online, now}: {resource: Resource<VerdictResponse>; online: boolean; now: number}) {
  const v = resource.data;
  const state = guidanceState(v, online, now);
  const current = state === 'current' && v;
  const titles = {GO_OUTDOORS: 'Go outdoors', MODIFIED_OUTDOORS: 'Modified outdoors', INDOOR_ONLY: 'Indoor only', DATA_INSUFFICIENT: 'Data insufficient'};
  return <>
    <section id="today" tabIndex={-1} className={'decision card ' + (current ? 'tone-' + v.decision.toLowerCase() : 'tone-unavailable')} aria-labelledby="today-heading">
      <p className="eyebrow">TODAY’S SCHOOL DECISION</p>
      <div role="status" aria-live="polite" aria-atomic="true">
        <h1 id="today-heading" data-testid="school-verdict">{current ? titles[v.decision] : state === 'expired' ? 'RECHECK REQUIRED' : state === 'historical' ? 'Historical record — not current guidance' : state === 'offline' ? 'Current recommendation unavailable' : state === 'unknown' ? 'Unrecognized decision — recheck required' : resource.state === 'loading' ? 'Checking the latest guidance…' : 'Current recommendation unavailable'}</h1>
        {current && <p className="canonical">{v.decision}</p>}
      </div>
      <ResourceStatus resource={resource} label="current recommendation"/>
      {current ? <><p className="decision-reason">{v.reasons[0] || 'Read the backend-provided school actions and caveats below.'}</p>
        <div className="decision-times"><p><strong>Evaluated</strong><br/>{date(v.evaluation_time)}</p><p><strong>Valid until / recheck by</strong><br/>{date(v.valid_until)}</p></div>
        <p className="decision-caveat">Conditional school guidance, not a guarantee of safe air. Always follow current official school notices.</p>
        {v.requires_regulatory_verification && <p className="notice">VERIFY STATUS: official restrictions must be verified. This precaution does not establish legal permission for outdoor activity.</p>}</>
        : state === 'expired' ? <p>The backend recommendation has expired. Refresh current data before using any school actions.</p>
        : state === 'offline' ? <p>Reconnect to check the latest guidance. Previously loaded recommendations are hidden.</p>
        : state === 'unknown' || state === 'historical' ? <p>No current actions are available. Refresh the current decision.</p> : null}
    </section>
    <div className="decision-details">
      <section id="actions" className="card" aria-labelledby="actions-heading"><p className="eyebrow">WHAT TO DO</p><h2 id="actions-heading">School actions</h2>
        {current ? <SchoolActions value={v}/> : <p>Current actions will appear after an unexpired recommendation is verified online.</p>}
      </section>
      <section id="why" className="card" aria-labelledby="why-heading"><p className="eyebrow">THE REASONING</p><h2 id="why-heading">Why this decision?</h2>
        {current ? <><ul className="reason-list">{v.rule_evaluations.map((r, i) => <li key={i}>{r.message}<small>Rule: {r.rule_id}</small></li>)}</ul>
          {!v.rule_evaluations.length && <p>No additional rule explanation was supplied.</p>}<Warnings values={v.warnings}/>
          <details><summary>Policy and evidence used</summary><p>Authority: {v.policy_version}</p>
            {v.evidence.length ? <ul>{v.evidence.map((e, i) => <li key={i}>{e.value} {e.scale} · {readable(e.source_type)} · {e.source_id} · {date(e.timestamp)} · {e.freshness}</li>)}</ul> : <p>Required evidence is missing. Missing evidence is not safe evidence.</p>}
            {v.policy_sources.map((s, i) => <p key={i}><SourceLink url={s.url}>{s.title}</SourceLink> · {s.scope}</p>)}
          </details></> : <p>Current reasoning is unavailable. Check the evidence and official notices, then refresh.</p>}
      </section>
    </div>
  </>;
}
export function SchoolActions({value}: {value: VerdictResponse}) {
  return value.actions.length ? <ul className="action-list">{value.actions.map((a, i) => <li key={i}>
    <div className="action-title"><h3>{({assembly: 'Assembly', sports: 'Sports', physical_education: 'Physical education', other: 'Other outdoor activities', indoor: 'Indoor alternatives', administration: 'Administration', parent_communication: 'Parent communication'} as Record<string,string>)[a.activity] || readable(a.activity)}</h3>
      <span className="action-code">{readable(a.recommendation)}</span></div><p>{a.instruction}</p>
    <small>{a.mandatory ? 'Mandatory for the listed grades' : 'Project precaution / review'}{a.applicable_grades.length ? ' · Grades: ' + a.applicable_grades.map(g => g === 0 ? 'Kindergarten' : g).join(', ') : ''}</small>
  </li>)}</ul> : <p>No activity actions were supplied by the backend. Verify before proceeding.</p>;
}
export function FreshnessView({verdict, grap, now}: {verdict: Resource<VerdictResponse>; grap: Resource<GrapResponse>; now: number}) {
  const g = grap.data;
  const q = verdict.data?.data_quality;
  const label = g && regulatoryLabel(g, now);
  return <section id="status" className="card" aria-labelledby="status-heading"><p className="eyebrow">WHAT WE KNOW</p><h2 id="status-heading">Freshness & official status</h2>
    <div className="status-grid"><div><h3>GRAP verification</h3><ResourceStatus resource={grap} label="regulatory status"/>
      {g && <><p className="status-label">{label}</p><p>{label === 'VERIFIED_ACTIVE' ? 'Verified active stage: ' + g.active_stage : label === 'VERIFIED_INACTIVE' ? 'Official status verified inactive at the stated review time.' : 'Current activation is not verified. UNKNOWN does not mean there are no restrictions.'}</p>
        <p>Human review: {g.verification_action_recorded ? date(g.verified_at) : 'Not recorded'}<br/>Recheck verification: {date(g.verification_expires_at)}</p></>}
    </div><div><h3>Evidence behind the decision</h3>{q ? <dl className="facts"><div><dt>Current evidence</dt><dd>{verdict.data && now >= Date.parse(verdict.data.valid_until) ? 'Decision expired — recheck required' : q.current_freshness}</dd></div>
      <div><dt>Activity forecast</dt><dd>{verdict.data && now >= Date.parse(verdict.data.valid_until) ? 'Recheck required' : q.forecast_freshness}</dd></div>
      <div><dt>Official observations</dt><dd>{q.official_observations_available ? 'Available' : 'Unavailable'}</dd></div><div><dt>Station observations</dt><dd>{q.station_observations_available ? 'Available' : 'Unavailable'}</dd></div></dl> : <p>Evidence freshness unavailable. No safe-air conclusion can be made from missing data.</p>}</div></div>
    <p className="notice">US AQI is not Indian AQI. Modeled data cannot establish official GRAP activation or guarantee safe air at this school.</p>
    {g && <Warnings values={g.warnings} label="Regulatory caveats"/>}
    {g && <details><summary>Official regulatory sources / review status</summary><p>Document research is not confirmation of current activation.</p>
      {g.source_documents.length ? <ul>{g.source_documents.map((d, i) => <li key={i}><SourceLink url={d.url}>{d.title}</SourceLink>
        <p>{d.authority} · Published {d.published_on} · {d.verification_status}</p></li>)}</ul> : <p>No regulatory source documents were supplied.</p>}</details>}
  </section>;
}

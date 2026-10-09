import React, {useState} from 'react';
import {getHealth, getSchool, getSafety, getEvidence} from './api';
import {useResource, useOnline, useClock} from './hooks';
import {SafetyView, FreshnessView} from './SafetyView';
import {EnvironmentalView} from './EnvironmentalView';
import {AdvisoryView} from './AdvisoryView';
import {SchoolView} from './SchoolView';
import {HistoryView} from './HistoryView';
import {PwaControls} from './PwaControls';
const id = 'delhi-demo-school';
const loaders = {
  health: (signal: AbortSignal) => getHealth(signal), school: (signal: AbortSignal) => getSchool(id, signal),
  verdict: (signal: AbortSignal) => getSafety(id, 'verdict', signal), grap: (signal: AbortSignal) => getSafety(id, 'grap', signal),
  air: (signal: AbortSignal) => getEvidence(id, 'air', signal), forecast: (signal: AbortSignal) => getEvidence(id, 'forecast', signal),
};
export function App() {
  const [attempt, setAttempt] = useState(0);
  const online = useOnline();
  const school = useResource(loaders.school, attempt, online);
  const verdict = useResource(loaders.verdict, attempt, online);
  const grap = useResource(loaders.grap, attempt, online);
  const air = useResource(loaders.air, attempt, online);
  const forecast = useResource(loaders.forecast, attempt, online);
  const health = useResource(loaders.health, attempt, online);
  const now = useClock([verdict.data?.valid_until, air.data?.cache.fresh_until, forecast.data?.cache.fresh_until, grap.data?.verification_expires_at]);
  const busy = [school, verdict, grap, air, forecast, health].some(r => r.state === 'loading');
  return <><a className="skip-link" href="#today">Skip to current decision</a>
    <header className="site-header"><div className="header-inner"><a className="brand" href="#today" aria-label="HawaHawai, current school decision"><img src="/icon.svg" alt="" width="36" height="36"/>HawaHawai</a>
      <span className="brand-note">School air-safety advisor</span></div></header>
    <main><div className="school-strip"><div><p className="eyebrow">DELHI-NCR SCHOOL PILOT</p><p className="school-name">{school.data?.name || (school.state === 'loading' ? 'Loading demo school…' : 'Demo school profile unavailable')}</p>
      <p>{school.data ? school.data.city + ' · ' + school.data.timezone : 'Current school information is loaded from the backend.'}</p></div>
      <button disabled={!online || busy} onClick={() => setAttempt(n => n + 1)}>{busy ? 'Checking current data…' : 'Refresh current data'}</button></div>
    <nav className="section-nav" aria-label="School guidance sections"><a href="#today">Today’s decision</a><a href="#actions">School actions</a><a href="#outlook">48-hour outlook</a><a href="#sources">Data sources</a><a href="#school">School info</a></nav>
    {!online && <p role="alert" className="notice offline">You’re offline. Current recommendation unavailable. Reconnect to check the latest guidance.</p>}
    <SafetyView resource={verdict} online={online} now={now}/>
    <FreshnessView verdict={verdict} grap={grap} now={now}/>
    <EnvironmentalView air={air} forecast={forecast} now={now}/>
    <AdvisoryView current={verdict.data} online={online} now={now} refresh={attempt}/>
    <div className="secondary-grid"><SchoolView resource={school}/><HistoryView online={online}/></div>
    <footer><p>HawaHawai assists school decisions. Follow current official notices. Modeled data do not guarantee safe air.</p>
      <p role="status" aria-live="polite">{health.data ? 'Backend connected · deployed AWS service' : health.state === 'loading' ? 'Checking backend connection…' : health.state === 'offline' ? 'Backend unavailable offline' : 'Backend connection could not be checked'}</p>
      <PwaControls/><p>Install from your browser menu where supported. Offline access includes the app shell only; current safety guidance requires a connection.</p></footer>
    </main></>;
}

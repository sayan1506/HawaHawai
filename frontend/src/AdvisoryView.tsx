import React, {useEffect, useRef, useState} from 'react';
import {getAdvisory, errorMessage, type AdvisoryResponse, type VerdictResponse} from './api';
import {ResourceStatus, Warnings, SourceLink, type Resource} from './ui';
import {advisoryMatches, guidanceState, date} from './presentation';
import {useClock} from './hooks';
import {ParentNotice} from './ParentNotice';

export function AdvisoryContent({value, current, online, now, language}: {value: AdvisoryResponse; current?: VerdictResponse; online: boolean; now: number; language: 'en' | 'hi'}) {
  if (!advisoryMatches(value, current, online, now)) return <p className="notice" role="status">RECHECK REQUIRED: this explanation is expired, offline, or does not match the current decision. Refresh current data before using it.</p>;
  return <><p className="status-label">{value.explanation_method === 'AI' ? 'AI-assisted explanation' : 'Deterministic fallback'} · {value.generator}</p>
    <p>Backend-approved statement ordering. The explanation preserves the current school decision and its actions.</p>
    <p>Generated: {date(value.generated_at)}<br/>Valid until: {date(value.valid_until)}</p>
    <ParentNotice value={value} current={current} online={online} now={now} language={language}/>
    <div lang={language} className="advisory-text">{value[language]}</div>
    <details><summary>{language === 'hi' ? 'स्कूल के स्वीकृत निर्देश' : 'Approved school action wording'}</summary>
      <ul>{value.actions.map((a, i) => <li key={i}><strong>{a.activity} · {a.recommendation}</strong><p lang={language}>{a[language]}</p>
        {a.mandatory && <small>Mandatory for listed grades: {a.applicable_grades.join(', ')}</small>}</li>)}</ul>
    </details><Warnings values={value.caveats} label="Explanation caveats"/>
    <details><summary>Explanation sources</summary>{value.sources.length ? <ul>{value.sources.map((s, i) => <li key={i}><SourceLink url={s.url}>{'name' in s ? s.name : s.title}</SourceLink></li>)}</ul> : <p>No additional source references supplied.</p>}</details></>;
}
export function AdvisoryView({current, online, now, refresh}: {current?: VerdictResponse; online: boolean; now: number; refresh: number}) {
  const [value, setValue] = useState<Resource<AdvisoryResponse>>({state: 'success'});
  const [language, setLanguage] = useState<'en' | 'hi'>('en');
  const clock = useClock([value.data?.valid_until, current?.valid_until]);
  now = Math.max(now, clock);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {controller.current?.abort(); setValue({state: 'success'}); return () => controller.current?.abort();}, [refresh, current?.decision_id]);
  const available = guidanceState(current, online, now) === 'current';
  async function load() {
    if (!current || !available) return;
    controller.current?.abort(); const c = new AbortController(); controller.current = c; setValue({state: 'loading'});
    try {const data = await getAdvisory(current.school_id, c.signal, current.decision_id); if (!c.signal.aborted) setValue({state: 'success', data});}
    catch (error) {if (!c.signal.aborted) setValue({state: 'error', error: errorMessage(error)});}
  }
  return <section id="advisory" className="card" aria-labelledby="advisory-heading"><p className="eyebrow">A CLEARER EXPLANATION</p><h2 id="advisory-heading">English / हिन्दी advisory</h2>
    <p>Load a grounded explanation of the current recommendation. Both languages use the same approved decision.</p>
    <div className="button-row"><button disabled={!available || value.state === 'loading'} onClick={load}>{value.state === 'loading' ? 'Loading explanation…' : 'Load school explanation'}</button>
      <div role="group" aria-label="Advisory language"><button className="secondary" aria-pressed={language === 'en'} onClick={() => setLanguage('en')}>English</button>
        <button className="secondary" lang="hi" aria-pressed={language === 'hi'} onClick={() => setLanguage('hi')}>हिन्दी</button></div></div>
    <ResourceStatus resource={online ? value : {state: 'offline'}} label="school explanation"/>
    {!available && online && <p>Load an unexpired current decision before requesting its explanation.</p>}
    {value.data && <AdvisoryContent value={value.data} current={current} online={online} now={now} language={language}/>}
    {available && value.state === 'success' && !value.data && <p>The explanation has not been requested yet. School actions above are already authoritative.</p>}
  </section>;
}

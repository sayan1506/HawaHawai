import {useEffect, useState} from 'react';
import {getAdvisory, type AdvisoryResponse} from './api';
import {verdictExpired} from './advisoryValidity';

export function AdvisoryView() {
  const [value,setValue]=useState<AdvisoryResponse>();
  const [language,setLanguage]=useState<'en'|'hi'>('en');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [now,setNow]=useState(Date.now());
  useEffect(()=>{const id=window.setInterval(()=>setNow(Date.now()),1000);return()=>window.clearInterval(id);},[]);
  async function load() {
    setBusy(true);setError('');setValue(undefined);
    const controller=new AbortController();const timeout=window.setTimeout(()=>controller.abort(),28000);
    try {setValue(await getAdvisory('delhi-demo-school',controller.signal));}
    catch {setError('Explanation unavailable. The deterministic school-policy view remains authoritative. Try again.');}
    finally {window.clearTimeout(timeout);setBusy(false);}
  }
  const expired=value && verdictExpired(value.valid_until,now);
  return <section className="card" aria-labelledby="advisory"><h2 id="advisory">School explanation · English / हिन्दी</h2>
    <p>The AI may organize approved statements. It cannot change the school-safety decision.</p>
    <button disabled={busy} onClick={load}>{busy?'Loading explanation…':'Load school explanation'}</button>
    <button onClick={()=>setLanguage(language==='en'?'hi':'en')}>{language==='en'?'हिन्दी में देखें':'Show English'}</button>
    <div role="status" aria-live="polite">{error || (busy?'Retrieving trusted evidence…':'')}</div>
    {value && (expired?<p role="alert">RECHECK REQUIRED: supporting evidence has expired. Reload before using this explanation.</p>:<>
      <h3>{value.decision}</h3><p>{value.explanation_method==='AI'?'AI-assisted approved statement ordering':'Deterministic fallback'} · {value.generator}</p>
      <p>Official GRAP verification: {value.regulatory_status.verification_state}</p>
      <p lang={language}>{value[language]}</p>
      <ul>{value.actions.map((action,i)=><li key={i}><strong>{action.activity}: {action.recommendation}</strong> — <span lang={language}>{action[language]}</span> {action.mandatory?'Mandatory for listed grades':''} {action.applicable_grades.length?`Grades: ${action.applicable_grades.join(', ')}`:''}</li>)}</ul>
      <details><summary>Evidence, sources and limitations</summary><ul>{value.caveats.map((w,i)=><li key={i}>{w}</li>)}</ul>
        <ul>{value.sources.map((s,i)=><li key={i}><a href={s.url} target="_blank" rel="noreferrer">{s.name || s.title}</a></li>)}</ul>
        <p>Generated: {value.generated_at} · Recheck by: {value.valid_until} · Cache: {value.cache.status}</p>
      </details></>)}
  </section>;
}

import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { getHealth, type HealthResponse } from './api';
import './styles.css';
import {EnvironmentalView} from './EnvironmentalView';
import {SafetyView} from './SafetyView';

function App() {
  const [health, setHealth] = useState<HealthResponse>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 10000);
    setHealth(undefined); setError('');
    getHealth(controller.signal).then(value => { if (active) setHealth(value); }).catch(() => {
      if (active) setError('The backend could not be reached. Check the connection and try again.');
    }).finally(() => window.clearTimeout(timeout));
    return () => { active = false; controller.abort(); window.clearTimeout(timeout); };
  }, [attempt]);
  return <main>
    <header><span className="brand">HawaHawai</span><span className="badge">Deterministic school policy · Phase 2</span></header>
    <section className="intro"><p className="eyebrow">FOR SCHOOLS IN DELHI-NCR</p>
      <h1>A clearer school day.<br/>A safer breath.</h1>
      <p>Air-quality evidence, practical school actions, and parent advisories — coming together in HawaHawai.</p>
    </section>
    <section className="card" aria-labelledby="foundation"><h2 id="foundation">Foundation connection</h2>
      <div role="status" aria-live="polite">{health ? <><span className="dot"/>Backend connected <small>{health.environment} · Checked {new Date(health.timestamp).toLocaleTimeString()}</small></> : error || 'Checking the backend…'}</div>
      {error && <button onClick={() => setAttempt(value => value + 1)}>Try again</button>}
    </section>
    <SafetyView/>
    <EnvironmentalView/>
    <footer>This advisor will assist school decisions. Always follow current official notices.</footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);

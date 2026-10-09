import {useEffect, useState} from 'react';
import {errorMessage} from './api';
import type {Resource} from './ui';
export function useOnline() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {const update = () => setOnline(navigator.onLine); window.addEventListener('online', update); window.addEventListener('offline', update);
    return () => {window.removeEventListener('online', update); window.removeEventListener('offline', update);};}, []);
  return online;
}
export function useResource<T>(load: (signal: AbortSignal) => Promise<T>, attempt: number, online: boolean): Resource<T> {
  const [value, setValue] = useState<Resource<T>>({state: 'loading'});
  useEffect(() => {
    if (!online) {setValue({state: 'offline'}); return;}
    const controller = new AbortController(); let active = true; setValue({state: 'loading'});
    load(controller.signal).then(data => {if (active) setValue({state: 'success', data});})
      .catch(error => {if (active) setValue({state: 'error', error: errorMessage(error)});});
    return () => {active = false; controller.abort();};
  }, [load, attempt, online]);
  return !online ? {state: 'offline'} : value;
}
export function useClock(deadlines: (string | null | undefined)[]) {
  const [now, setNow] = useState(Date.now());
  const key = deadlines.join('|');
  useEffect(() => setNow(Date.now()), [key]);
  useEffect(() => {
    const update = () => setNow(Date.now());
    const future = deadlines.map(v => Date.parse(v || '')).filter(v => v > Date.now());
    const timer = window.setTimeout(update, future.length ? Math.min(...future) - Date.now() + 1 : 30000);
    const interval = window.setInterval(update, 30000);
    window.addEventListener('focus', update); document.addEventListener('visibilitychange', update);
    return () => {clearTimeout(timer); clearInterval(interval); window.removeEventListener('focus', update); document.removeEventListener('visibilitychange', update);};
  }, [key, now]);
  return now;
}

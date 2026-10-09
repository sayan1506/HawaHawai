import React, {useEffect, useRef, useState} from 'react';
import {registerSW} from 'virtual:pwa-register';
type InstallEvent = Event & {prompt: () => Promise<void>; userChoice: Promise<{outcome: string}>};
export function PwaControls() {
  const [install, setInstall] = useState<InstallEvent>();
  const [updateReady, setUpdateReady] = useState(false);
  const [error, setError] = useState('');
  const update = useRef<((reload?: boolean) => Promise<void>) | null>(null);
  useEffect(() => {
    update.current = registerSW({onNeedRefresh: () => setUpdateReady(true), onRegisterError: () => setError('Offline app installation is unavailable in this browser.')});
    const available = (event: Event) => {event.preventDefault(); setInstall(event as InstallEvent);};
    const installed = () => setInstall(undefined);
    window.addEventListener('beforeinstallprompt', available); window.addEventListener('appinstalled', installed);
    return () => {window.removeEventListener('beforeinstallprompt', available); window.removeEventListener('appinstalled', installed);};
  }, []);
  return <div className="pwa-controls">{install && <button className="secondary" onClick={async () => {await install.prompt(); await install.userChoice; setInstall(undefined);}}>Install HawaHawai</button>}
    {updateReady && <button className="secondary" onClick={() => update.current?.(true)}>Update app & recheck guidance</button>}
    {error && <p role="status">{error}</p>}</div>;
}

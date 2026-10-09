import React,{useEffect,useRef,useState} from 'react';
import type {AdvisoryResponse,VerdictResponse} from './api';
import {parentNotice,type Language} from './noticeContent';
import {copyNotice,nativeShare,whatsappLink} from './noticeSharing';
export function ParentNotice({value,current,online,now,language}:{value:AdvisoryResponse;current?:VerdictResponse;online:boolean;now:number;language:Language}) {
  const [message,setMessage]=useState('');const [manual,setManual]=useState(false);const [busy,setBusy]=useState(false);
  const field=useRef<HTMLTextAreaElement>(null);
  useEffect(()=>{setMessage('');setManual(false);},[language,value.verdict_id,value.valid_until]);
  const hi=language==='hi';
  const latest=()=>parentNotice(value,current,online&&navigator.onLine,Date.now(),language);
  const recheck=()=>setMessage(hi?'फिर जाँचें: वर्तमान मान्य सूचना ऑनलाइन लोड करें।':'Recheck required: load a current validated notice online.');
  async function share(){const fresh=latest();if(!fresh){recheck();return;}setBusy(true);setManual(false);
    const result=await nativeShare(fresh,{share:navigator.share?.bind(navigator),canShare:navigator.canShare?.bind(navigator)});
    setBusy(false);setMessage(hi?{shared:'ब्राउज़र ने साझा करने की प्रक्रिया पूरी की।',canceled:'साझा करना रद्द किया गया।',unsupported:'इस ब्राउज़र में साझा करना उपलब्ध नहीं है। WhatsApp लिंक या कॉपी का उपयोग करें।',failed:'साझा नहीं हो सका। WhatsApp लिंक या कॉपी का उपयोग करें।'}[result]:{shared:'Browser sharing completed.',canceled:'Sharing canceled.',unsupported:'Native sharing is unavailable. Use the WhatsApp link or Copy Advisory.',failed:'Sharing failed. Use the WhatsApp link or Copy Advisory.'}[result]);
  }
  async function copy(){const fresh=latest();if(!fresh){recheck();return;}setBusy(true);const copied=await copyNotice(fresh,navigator.clipboard);setBusy(false);setManual(!copied);
    setMessage(copied?(hi?'सूचना कॉपी की गई।':'Advisory copied.'):(hi?'अपने-आप कॉपी नहीं हुई। नीचे की सूचना चुनें और कॉपी करें।':'Automatic copying unavailable. Select the notice below and copy it manually.'));
  }
  const notice=parentNotice(value,current,online,now,language);
  if(!notice)return <p role="status" className="notice">Parent notice unavailable: reload an online, validated current explanation. Expired or inconsistent notices are withheld.</p>;
  return <div className="parent-notice-panel"><h3>{hi?'अभिभावक सूचना':'Parent notice'}</h3><p>{hi?'बैकएंड के स्वीकृत निर्देशों वाली संक्षिप्त सूचना। पूरी व्याख्या नीचे है।':'A concise notice using the backend-approved action wording. The full explanation follows below.'}</p>
    <div className="parent-notice" lang={language}>{notice.text}</div>
    <div className="button-row notice-controls" aria-label={hi?'सूचना साझा करें':'Share parent notice'}>
      <button disabled={busy} onClick={share}>{hi?'साझा करें':'Share Advisory'}</button>
      <a className="button-link secondary" href={whatsappLink(notice)} target="_blank" rel="noopener noreferrer" onClick={event=>{if(!latest()){event.preventDefault();recheck();}}}>{hi?'WhatsApp पर साझा करें':'Share on WhatsApp'}</a>
      <button className="secondary" disabled={busy} onClick={copy}>{hi?'सूचना कॉपी करें':'Copy Advisory'}</button>
    </div>
    <p className="share-status" role="status" aria-live="polite" lang={language}>{message}</p>
    <p className="share-context">{hi?'WhatsApp लिंक एक मसौदा खोलता है; भेजने से पहले तारीख और समय सीमा जाँचें।':'The WhatsApp link opens a draft; check the date and expiry before sending.'}</p>
    {manual&&<div className="manual-copy"><label htmlFor="manual-advisory">{hi?'मैन्युअल कॉपी के लिए सूचना':'Notice for manual copying'}</label><textarea id="manual-advisory" ref={field} readOnly value={notice.text} lang={language} rows={10}/><button className="secondary" onClick={()=>{if(!latest()){recheck();return;}field.current?.focus();field.current?.select();}}>{hi?'पूरा पाठ चुनें':'Select notice text'}</button></div>}
  </div>;
}

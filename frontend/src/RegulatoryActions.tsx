import React from 'react';
import type {VerdictResponse,GrapResponse} from './api';
import type {Restriction,RegulatoryDocument} from './contracts';
import {ResourceStatus,SourceLink,type Resource} from './ui';
import {date,guidanceState,readable,regulatoryLabel} from './presentation';
export const gradeText=(grades:number[])=>grades.length?grades.map(g=>g===0?'Pre-primary':String(g)).join(', '):'Scope not supplied — review the exact order';
function RestrictionRow({value,documents,holding=false}:{value:Restriction;documents:RegulatoryDocument[];holding?:boolean}) {
  const document=documents.find(d=>d.document_id===value.document_id);
  return <li><p className="status-label">{holding?'Previously recorded — unverified':value.mandatory?'Verified mandatory restriction':'Official advisory — not mandatory'} · {readable(value.action)}</p>
    <p>{value.clause}</p><p>Grades: {gradeText(value.grades)} · Activity: {readable(value.activity)} · {value.jurisdiction}</p>
    <p>Effective from: {date(value.effective_from)}<br/>Effective until: {date(value.effective_until)}{!value.effective_until&&' — no end established in this record; verification still expires separately.'}</p>
    {document?<p><SourceLink url={document.url}>{document.title}</SourceLink> · {document.authority} · {document.verification_status}</p>:<p>Original document reference unavailable. Review the exact order before proceeding.</p>}
  </li>;
}
export function RegulatoryActions({verdict,grap,online,now}:{verdict:Resource<VerdictResponse>;grap:Resource<GrapResponse>;online:boolean;now:number}) {
  const current=guidanceState(verdict.data,online,now)==='current'?verdict.data:undefined;
  const g=current?.regulatory_status||(online?grap.data:undefined);
  const label=g&&regulatoryLabel(g,now);
  return <section id="regulatory-actions" className="card" aria-labelledby="regulatory-actions-heading"><p className="eyebrow">OFFICIAL ORDERS & PRECAUTIONS</p><h2 id="regulatory-actions-heading">GRAP & school orders</h2>
    <ResourceStatus resource={online?grap:{state:'offline'}} label="official regulatory evidence"/>
    {g&&<><p className="status-label">{label}</p><p>{label==='VERIFIED_ACTIVE'?`Verified active stage: ${g.active_stage}`:label==='VERIFIED_INACTIVE'?'Reviewed inactive at the stated verification time.':label==='CONFLICTING'?'Conflicting official records require human resolution. Do not infer which restrictions apply.':label?.startsWith('STALE')?'Verification is stale. Expiry is not proof of legal revocation.':'Current activation is UNKNOWN. Missing verification does not mean restrictions are inactive.'}</p>
      <p>Reviewed: {date(g.verified_at)} · Review expires: {date(g.verification_expires_at)}</p>
      {current?<><h3>Applicable backend restrictions</h3>{g.applicable_restrictions.length?<ul className="regulation-list">{g.applicable_restrictions.map((r,i)=><RestrictionRow key={i} value={r} documents={g.source_documents}/>)}</ul>:<p>No verified applicable restriction was supplied. This is not confirmation that no official school restrictions exist. Follow the backend’s verification precautions.</p>}
        {g.unverified_restrictions.length>0&&<details><summary>Previously recorded restrictions requiring re-verification</summary><p>These are not represented as currently verified mandatory orders. Current backend holding precautions remain authoritative.</p><ul>{g.unverified_restrictions.map((r,i)=><RestrictionRow key={i} value={r} documents={g.source_documents} holding/>)}</ul></details>}
        <h3>How school actions are classified</h3><p>{current.actions.filter(a=>a.mandatory).length} mandatory action records; other actions are precautionary or administrative review. The School actions section preserves every backend instruction and applicable grade. A favorable forecast cannot override an official restriction.</p></>:<p>Current restriction instructions are withheld until an online, unexpired backend decision is available.</p>}
      <details><summary>Official originals, publication and effective dates</summary><p>Publication and documentary research do not establish current activation. Dates are shown only when provided by the registry.</p>
        {g.source_documents.length?<ul>{g.source_documents.map((d,i)=><li key={i}><SourceLink url={d.url}>{d.title}</SourceLink><p>{d.authority} · Published {d.published_on} · {d.verification_status}</p>
          <p>Effective from: {date(d.effective_from)}<br/>Effective until: {date(d.effective_until)}</p></li>)}</ul>:<p>No original documents supplied.</p>}</details></>}
    <p className="notice">GRAP activation is never inferred from AQI. Mandatory school operations, including exact grade-specific hybrid or physical-class orders, take precedence over activity suggestions.</p>
  </section>;
}

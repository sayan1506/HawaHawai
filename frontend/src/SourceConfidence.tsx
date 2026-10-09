import React from 'react';
import type {Evidence,VerdictResponse} from './api';
import {ResourceStatus,Sources,type Resource} from './ui';
import {date,evidenceFreshness,guidanceState,regulatoryLabel} from './presentation';

export function evidenceConfidence(value:Evidence|undefined,now:number) {
  if(!value||value.status==='unavailable')return {label:'Unavailable evidence',reasons:['No usable values are supplied. Missing evidence cannot establish safe air.']};
  const stale=evidenceFreshness(value,now).startsWith('stale')||value.sources.some(s=>s.freshness==='stale'||s.valid_until&&now>=Date.parse(s.valid_until));
  const points='points' in value?value.points:value.modeled_current?[value.modeled_current]:[];
  const missing=!value.sources.length||!points.length||('points' in value&&points.length<48)||points.some(p=>!p.aqi.some(a=>a.scale==='US_AQI')||!p.pollutants.some(a=>a.name==='pm2_5')||!p.pollutants.some(a=>a.name==='pm10'));
  const reasons=['Classification describes evidence completeness and provenance, not a probability of safety.'];
  if(stale)reasons.push('Backend freshness or a source/retrieval deadline is stale. Refresh before relying on current conditions.');
  if(missing)reasons.push('Required display values, hours or source provenance are incomplete; missing values are not zero.');
  if(value.sources.some(s=>s.kind==='model_forecast'))reasons.push('Open-Meteo/CAMS grid estimates are modeled forecasts, not physical school measurements. Geographic representativeness is limited.');
  if('generated_at' in value&&!value.generated_at)reasons.push('Model initialization timestamp is not supplied; retrieval time is not a model run time.');
  if('observations' in value&&!value.observations.length)reasons.push('Official station observations are unavailable. Indian AQI is not established by modeled US AQI.');
  const modeled=value.sources.some(s=>s.kind==='model_forecast');
  return {label:stale?'Stale evidence':missing?'Incomplete evidence':modeled?'Modeled · limited':'Attributed observations · scope limited',reasons};
}
export function recommendationConfidence(value:VerdictResponse|undefined,online:boolean,now:number) {
  if(guidanceState(value,online,now)!=='current')return {label:'Current basis unavailable',reasons:['An online, unexpired current backend decision is required. Historical or expired records are not current advice.']};
  const v=value!;const q=v.data_quality;const reasons:string[]=[];
  if(!q.station_observations_available)reasons.push('No fresh representative physical station evidence is available; model-only data cannot establish safe air at this school.');
  if(!q.official_observations_available)reasons.push('Official observations / Indian AQI are not established. US AQI is a different scale.');
  if(q.current_freshness!=='fresh')reasons.push(`Current evidence: ${q.current_freshness}. A restrictive precaution can use the backend’s fresh forecast without claiming a fresh current measurement.`);
  if(!q.forecast_available||q.forecast_freshness!=='fresh')reasons.push('The complete fresh activity forecast prerequisite is missing or stale.');
  const regulation=regulatoryLabel(v.regulatory_status,now);
  if(!regulation.startsWith('VERIFIED'))reasons.push(`Official GRAP verification: ${regulation}. This does not confirm restrictions are inactive.`);
  reasons.push('The backend school-safety-v1 decision and exact actions remain authoritative. This evidence label cannot override them or guarantee safety.');
  return {label:!q.forecast_available||q.forecast_freshness!=='fresh'?'Incomplete basis':reasons.length>1?'Limited basis for precaution':'Documented inputs · limitations apply',reasons};
}
export function SourceConfidence({verdict,air,forecast,online,now}:{verdict:Resource<VerdictResponse>;air:Resource<Evidence>;forecast:Resource<Evidence>;online:boolean;now:number}) {
  const recommendation=recommendationConfidence(verdict.data,online,now);
  return <section id="confidence" className="card" aria-labelledby="confidence-heading"><p className="eyebrow">TRANSPARENT EVIDENCE</p><h2 id="confidence-heading">Source confidence</h2>
    <p>Explicit evidence rules, not an AI opinion or a numerical confidence score.</p><h3>Basis for today’s recommendation</h3><p className="status-label">{recommendation.label}</p><ul>{recommendation.reasons.map((r,i)=><li key={i}>{r}</li>)}</ul>
    <div className="status-grid">{([{resource:air,name:'Current environmental evidence'},{resource:forecast,name:'48-hour forecast evidence'}]).map(({resource,name})=>{
      const value=online?resource.data:undefined;const confidence=evidenceConfidence(value,now);
      return <div key={name}><h3>{name}</h3><ResourceStatus resource={online?resource:{state:'offline'}} label={name}/><p className="status-label">{confidence.label}</p>
        <ul>{confidence.reasons.map((r,i)=><li key={i}>{r}</li>)}</ul>{value&&<><p>Retrieved: {date(value.retrieved_at)}<br/>Retrieval freshness expires: {date(value.cache.fresh_until)}</p>
          <details><summary>{name} — source dates and geographic limitations</summary><Sources values={value.sources} now={now}/></details></>}</div>;
    })}</div>
    <details><summary>How these classifications are determined</summary><p>Unavailable takes precedence, then stale/elapsed validity, then incomplete hours/values/provenance, then modeled evidence. Attributed physical observations still have scope limitations. Recommendation labels also disclose station availability, activity-forecast freshness and actual regulatory verification. No classification changes an action or treats missing evidence as safe.</p></details>
  </section>;
}

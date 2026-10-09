import React from 'react';
import type {VerdictResponse} from './api';
import {guidanceState,readable} from './presentation';
import {gradeText} from './RegulatoryActions';
export const INDOOR_CATALOG_VERSION='school-logistics-v1';
const catalog:Record<string,string[]>={
  assembly:['Classroom announcements instead of a gathering.','A short seated assembly in an assessed indoor space, only if school orders permit.'],
  sports:['A classroom session on game rules, strategy or sportsmanship.','Reschedule outdoor practice; reassess the live decision at the new time.'],
  physical_education:['A seated lesson on movement skills or sports technique.','Teacher-led gentle classroom movement only after assessing indoor suitability and students’ needs.'],
  other:['A classroom project or seated group activity.','Reschedule the outdoor activity and recheck current guidance.'],
};
const permitted=new Set(['NORMAL_WITH_CAVEATS','MODIFY','INDOOR_ALTERNATIVE','VERIFY_BEFORE_PROCEEDING','AVOID_OUTDOOR_ADVISORY','RESCHEDULE_SPORTS','SUSPEND_OUTDOOR']);
const operationReview=new Set(['FOLLOW_PHYSICAL_CLASS_ORDER','SUSPEND_PHYSICAL_CLASSES','HYBRID_CLASSES','REVIEW_SCHOOL_OPERATIONS','REVIEW_ORDER']);
export function indoorOptions(value:VerdictResponse|undefined,online:boolean,now:number) {
  if(guidanceState(value,online,now)!=='current')return {blocked:'Current indoor suggestions unavailable. Refresh online guidance before selecting an activity.',options:[]};
  const v=value!;
  if(v.actions.some(a=>operationReview.has(a.recommendation)))return {blocked:'Follow the exact physical-class, hybrid or school-operation order for listed grades. On-campus indoor suggestions are withheld; only use alternatives permitted by the order.',options:[]};
  const options=v.actions.filter(a=>catalog[a.activity]&&permitted.has(a.recommendation)).map(a=>({action:a,ideas:catalog[a.activity]}));
  return {blocked:options.length?'':'No reviewed catalog option matches these backend actions. Review the exact school instructions.',options};
}
export function IndoorAlternatives({value,online,now}:{value?:VerdictResponse;online:boolean;now:number}) {
  const result=indoorOptions(value,online,now);
  return <section id="indoor-alternatives" className="card" aria-labelledby="indoor-heading"><p className="eyebrow">PRACTICAL SCHOOL OPTIONS</p><h2 id="indoor-heading">Indoor alternatives</h2>
    <p className="notice">Indoor air has not been measured and is not automatically safe. These optional logistical ideas implement the current backend actions; they do not change a verdict or override any school order.</p>
    {result.blocked?<p role="status">{result.blocked}</p>:<ul className="indoor-options">{result.options.map(({action,ideas},i)=><li key={i}><h3>{readable(action.activity)}</h3>
      <p>Backend action: <strong>{readable(action.recommendation)}</strong>{action.mandatory?' · Mandatory restriction':' · Precaution / conditional option'}</p>
      {action.applicable_grades.length>0&&<p>Applicable grades: {gradeText(action.applicable_grades)}</p>}<ul>{ideas.map(idea=><li key={idea}>{idea}</li>)}</ul></li>)}</ul>}
    <p>School staff must assess ventilation, particle filtration, space and students’ needs before indoor activity, as required by the existing backend instruction. No automatic window-opening or medical advice is provided.</p>
    <details><summary>Why these options are shown</summary><p>Catalog: {INDOOR_CATALOG_VERSION}. Options match only known activity/action codes. Physical-class suspension, hybrid and unresolved operation orders suppress on-campus options. Unsupported actions have no catalog suggestion. Suggestions are hidden offline and at the current verdict’s original expiry.</p></details>
  </section>;
}

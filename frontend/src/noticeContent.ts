import type {AdvisoryResponse,VerdictResponse} from './api';
import type {LocalizedAction} from './contracts';
import {validateAdvisory} from './advisoryValidity';
import {advisoryMatches,date} from './presentation';
export type Language='en'|'hi';
export const NOTICE_VERSION='parent-notice-v1';
const words={en:{title:'Parent notice',decision:'Current backend decision',evaluated:'Evaluated',generated:'Explanation generated',until:'Valid until — recheck before using',mandatory:'MANDATORY',precaution:'Precaution / review',grades:'Grades',freshness:'Evidence freshness',current:'current',forecast:'forecast',regulation:'Official GRAP verification',stage:'active stage',unverified:'not verified',
  limitation:'Modeled forecasts are not physical school measurements. US AQI is not Indian AQI. Forecasts are uncertain; indoor air is not automatically safe. Follow exact school orders. This notice does not guarantee safe air.',missing:'Official station observations / Indian AQI are unavailable.',observations:'Use the attributed observation sources and their limitations; no official Indian AQI is established by modeled US AQI.',unknown:'Current official activation is not verified; this does not mean restrictions are inactive.',sources:'Sources',recheck:'Recheck the live app before acting or forwarding; this dated notice expires at the time above.'},
hi:{title:'अभिभावक सूचना',decision:'वर्तमान बैकएंड निर्णय',evaluated:'मूल्यांकन',generated:'व्याख्या तैयार हुई',until:'मान्य समय सीमा — उपयोग से पहले फिर जाँचें',mandatory:'अनिवार्य',precaution:'सावधानी / समीक्षा',grades:'कक्षाएँ',freshness:'जानकारी की ताज़गी',current:'वर्तमान',forecast:'पूर्वानुमान',regulation:'आधिकारिक GRAP की पुष्टि',stage:'लागू चरण',unverified:'पुष्टि नहीं',
  limitation:'मॉडल पूर्वानुमान स्कूल में हवा के वास्तविक माप नहीं हैं। US AQI भारतीय AQI नहीं है। पूर्वानुमान अनिश्चित हैं; अंदर की हवा अपने-आप सुरक्षित नहीं है। मूल स्कूल आदेशों का पालन करें। यह सूचना सुरक्षित हवा की गारंटी नहीं देती।',missing:'आधिकारिक स्टेशन माप / भारतीय AQI उपलब्ध नहीं हैं।',observations:'दिए गए माप के स्रोत और उनकी सीमाएँ देखें; मॉडल US AQI से आधिकारिक भारतीय AQI की पुष्टि नहीं होती।',unknown:'वर्तमान आधिकारिक सक्रियता की पुष्टि नहीं है; इसका अर्थ पाबंदियाँ हटना नहीं है।',sources:'स्रोत',recheck:'काम करने या आगे भेजने से पहले लाइव ऐप में फिर जाँचें; ऊपर दिए समय पर यह सूचना समाप्त हो जाती है।'}};
const activityHi:Record<string,string>={assembly:'प्रार्थना सभा',sports:'खेल',physical_education:'शारीरिक शिक्षा',other:'अन्य बाहरी गतिविधियाँ',indoor:'अंदरूनी विकल्प',administration:'प्रशासन',parent_communication:'अभिभावक संचार'};
const freshnessHi:Record<string,string>={fresh:'ताज़ा',stale:'पुरानी',unavailable:'अनुपलब्ध'};
// Registry evaluation time is a read-time clock, not legal/source freshness.
// Mirror the backend fingerprint: every other regulatory field stays bound.
const regulatoryBasis=(value:AdvisoryResponse['regulatory_status'])=>JSON.stringify(Object.fromEntries(Object.entries(value).filter(([key])=>key!=='evaluation_time')));
// Distinct requirements remain distinct. Same logical scope with altered wording is rejected.
export function noticeActions(actions:LocalizedAction[]) {
  const seen=new Map<string,LocalizedAction>();
  for(const action of actions){
    if(!action.en?.trim()||!action.hi?.trim())throw new Error('Incomplete approved action localization');
    const signature=JSON.stringify([action.activity,action.recommendation,action.mandatory,[...action.applicable_grades].sort((a,b)=>a-b),action.evidence_ids]);
    const previous=seen.get(signature);
    if(previous&&(previous.instruction!==action.instruction||previous.en!==action.en||previous.hi!==action.hi))throw new Error('Conflicting action wording');
    if(!previous)seen.set(signature,action);
  }
  return [...seen.values()];
}
export function parentNotice(value:AdvisoryResponse,current:VerdictResponse|undefined,online:boolean,now:number,language:Language) {
  try{
    validateAdvisory(value,value.school_id);
    if(!advisoryMatches(value,current,online,now)||!value.school_name?.trim()||!Number.isFinite(Date.parse(value.generated_at))
      ||value.generation_scope!=='approved_statement_ordering'||JSON.stringify(value.languages)!==JSON.stringify(['en','hi'])
      ||!['gemini','groq','bedrock','rule_template'].includes(value.generator)
      ||Date.parse(value.generated_at)>=Date.parse(value.valid_until)
      ||(value.explanation_method==='DETERMINISTIC')!==(value.generator==='rule_template')
      ||value.valid_until!==current?.valid_until
      ||JSON.stringify(value.data_quality)!==JSON.stringify(current.data_quality)
      ||regulatoryBasis(value.regulatory_status)!==regulatoryBasis(current.regulatory_status))return undefined;
    const w=words[language],v=value.authoritative_decision;
    const actions=noticeActions(value.actions);
    if(!actions.length)return undefined;
    const actionLines=actions.map(a=>`${language==='hi'?activityHi[a.activity]||a.activity:a.activity.replaceAll('_',' ')} · ${a.recommendation} · ${a.mandatory?w.mandatory:w.precaution}${a.applicable_grades.length?' · '+w.grades+': '+a.applicable_grades.map(g=>g===0?(language==='hi'?'पूर्व-प्राथमिक':'Pre-primary'):g).join(', '):''}\n${a[language]}`);
    const sources=[...new Set(value.sources.map(s=>{const url=new URL(s.url);if(url.protocol!=='https:'||url.username||url.password)throw new Error('Invalid public source');return ('name'in s?s.name:s.title)+': '+url.href;}))];
    if(!sources.length)return undefined;
    const sourceNames=sources.slice(0,3); // Compact environmental/policy attribution; exact mandatory legal sources below.
    const mandatoryDocs=value.regulatory_status.source_documents.filter(d=>value.actions.some(a=>a.mandatory&&a.evidence_ids.includes(d.document_id)));
    sourceNames.push(...mandatoryDocs.map(d=>`${d.title}: ${d.url} (${d.effective_from?date(d.effective_from):'effective date not supplied'})`));
    const state=value.regulatory_status.verification_state;
    const freshness=(kind:string)=>language==='hi'?freshnessHi[kind]||kind:kind;
    const text=[`HawaHawai · ${w.title} · ${value.school_name}`,`${w.decision}: ${value.decision}`,
      `${w.evaluated}: ${date(v.evaluation_time)}`,`${w.generated}: ${date(value.generated_at)}`,
      `${w.until}: ${date(value.valid_until)} (${value.valid_until})`,
      `${w.regulation}: ${state} · ${w.stage}: ${value.regulatory_status.active_stage??w.unverified}`,
      ...(!state.startsWith('VERIFIED')?[w.unknown]:[]),
      `${w.freshness}: ${w.current} ${freshness(value.data_quality.current_freshness)}, ${w.forecast} ${freshness(value.data_quality.forecast_freshness)}.`,
      ...actionLines,w.limitation,value.data_quality.official_observations_available?w.observations:w.missing,
      `${w.sources}:\n${[...new Set(sourceNames)].join('\n')}`,w.recheck,'https://production.d3vzi8hqeh0wba.amplifyapp.com'].join('\n\n');
    return {title:`HawaHawai · ${value.school_name}`,text,validUntil:value.valid_until,language};
  }catch{return undefined;}
}

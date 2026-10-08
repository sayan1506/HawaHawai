import {verdictExpired} from './verdictValidity';
export function validateAdvisory(value: any, schoolId: string) {
  if (!value || value.school_id !== schoolId || !['AI','DETERMINISTIC'].includes(value.explanation_method)
    || typeof value.en !== 'string' || typeof value.hi !== 'string' || !value.en || !value.hi
    || !value.authoritative_decision || value.decision !== value.authoritative_decision.decision
    || value.verdict_id !== value.authoritative_decision.decision_id
    || !Array.isArray(value.actions) || !Array.isArray(value.caveats) || !Array.isArray(value.sources)
    || Number.isNaN(Date.parse(value.valid_until)) || value.valid_until !== value.authoritative_decision.valid_until
    || value.regulatory_status?.verification_state !== value.authoritative_decision.regulatory_status?.verification_state
    || (['UNKNOWN','STALE','CONFLICTING'].includes(value.regulatory_status.verification_state) && value.regulatory_status.active_stage !== null)
    || value.actions.length !== value.authoritative_decision.actions.length
    || value.actions.some((a:any,i:number) => ['activity','recommendation','mandatory','instruction'].some(k => a[k] !== value.authoritative_decision.actions[i][k]))) throw new Error('Unexpected advisory schema');
  return value;
}
export {verdictExpired};

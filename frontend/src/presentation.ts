import type {VerdictResponse, AdvisoryResponse, Evidence, GrapResponse} from './api';
import {verdictExpired} from './verdictValidity';

export function guidanceState(value: VerdictResponse | undefined, online: boolean, now: number) {
  if (!online) return 'offline';
  if (!value) return 'missing';
  if (value.persistence?.historical || (value as any).status === 'historical' || (value as any).actionable === false) return 'historical';
  if (verdictExpired(value.valid_until, now)) return 'expired';
  if (!['GO_OUTDOORS', 'MODIFIED_OUTDOORS', 'INDOOR_ONLY', 'DATA_INSUFFICIENT'].includes(value.decision)) return 'unknown';
  return 'current';
}
export function advisoryMatches(value: AdvisoryResponse, current: VerdictResponse | undefined, online: boolean, now: number) {
  return guidanceState(current, online, now) === 'current' && !verdictExpired(value.valid_until, now)
    && value.verdict_id === current?.decision_id && value.decision === current.decision
    && JSON.stringify(value.authoritative_decision.actions) === JSON.stringify(current.actions)
    && value.regulatory_status.verification_state === current.regulatory_status.verification_state;
}
export function evidenceFreshness(value: Evidence, now: number) {
  if (value.status === 'unavailable') return 'unavailable';
  if (value.status === 'stale' || value.freshness_status === 'stale') return 'stale';
  return verdictExpired(value.cache.fresh_until || '', now) ? 'stale — refresh required' : value.freshness_status;
}
export function regulatoryLabel(value: GrapResponse, now: number) {
  if (value.verification_state.startsWith('VERIFIED') && verdictExpired(value.verification_expires_at || '', now)) return 'STALE — verification expired';
  return value.verification_state;
}
export function date(value: string | null | undefined, timezone = 'Asia/Kolkata') {
  if (!value || !Number.isFinite(Date.parse(value))) return 'Not supplied';
  return new Intl.DateTimeFormat('en-IN', {timeZone: timezone, dateStyle: 'medium', timeStyle: 'short'}).format(new Date(value)) + ' · ' + timezone;
}
export const readable = (value: string) => value.replaceAll('_', ' ');
export const pollutantName = (value: string) => ({pm2_5: 'PM2.5', pm10: 'PM10', no2: 'NO₂', o3: 'O₃', so2: 'SO₂', co: 'CO'}[value] || value);

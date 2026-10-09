import {validateAdvisory} from './advisoryValidity';
import {apiBaseUrl} from './config';
import type {Health, SchoolProfile, AirReading, Forecast, ForecastPoint, GrapStatus, Verdict, Advisory, VerdictHistory} from './contracts';
export type {SchoolProfile};
export type HealthResponse = Health;
export type Evidence = AirReading | Forecast;
export type Point = ForecastPoint;
export type GrapResponse = GrapStatus;
export type VerdictResponse = Verdict;
export type AdvisoryResponse = Advisory;

export class ApiError extends Error {
  constructor(public status: number, public kind: 'network' | 'http' | 'schema' | 'configuration') {super(kind);}
}
export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Unable to load this section. Check your connection and try again.';
  if (error.kind === 'configuration') return 'The public API connection is not configured.';
  if (error.kind === 'schema') return 'The response could not be verified. Reload to check current data.';
  if (error.status === 404) return 'No data is available for this school yet.';
  if (error.status === 409) return 'The decision changed. Refresh the current decision before loading its explanation.';
  if (error.status === 429) return 'The service is busy. Please wait before trying again.';
  if (error.status >= 500) return 'The service or data provider is temporarily unavailable. Try again shortly.';
  if (error.status >= 400) return 'This request could not be completed. Reload and try again.';
  return 'Connection failed or timed out. Reconnect and try again.';
}
async function request(route: string, signal?: AbortSignal, body?: object): Promise<{body: any; status: number}> {
  let base: string;
  try {base = apiBaseUrl(import.meta.env?.VITE_API_BASE_URL, !!import.meta.env?.PROD);} catch {throw new ApiError(0, 'configuration');}
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal?.addEventListener('abort', cancel, {once: true});
  if (signal?.aborted) controller.abort();
  const timeout = setTimeout(cancel, 28000);
  try {
    const response = await fetch(base + route, {signal: controller.signal, cache: 'no-store', credentials: 'omit',
      method: body ? 'POST' : 'GET', ...(body ? {headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {})});
    if (!response.ok && response.status !== 503) throw new ApiError(response.status, 'http');
    return {body: await response.json(), status: response.status};
  } catch (error) {if (error instanceof ApiError) throw error; throw new ApiError(0, 'network');}
  finally {clearTimeout(timeout); signal?.removeEventListener('abort', cancel);}
}
const path = (id: string, kind = '') => '/v1/schools/' + encodeURIComponent(id) + (kind ? '/' + kind : '');
const fail = (): never => {throw new ApiError(0, 'schema');};
const timestamp = (value: unknown) => typeof value === 'string' && Number.isFinite(Date.parse(value));
function validateGrap(value: any) {
  if (!value || !['VERIFIED_ACTIVE', 'VERIFIED_INACTIVE', 'UNKNOWN', 'STALE', 'CONFLICTING'].includes(value.verification_state)
    || !Array.isArray(value.source_documents) || !Array.isArray(value.warnings)
    || (['UNKNOWN', 'STALE', 'CONFLICTING'].includes(value.verification_state) && value.active_stage !== null)) fail();
}
export function validateVerdict(value: any, schoolId: string): VerdictResponse {
  validateGrap(value?.regulatory_status);
  if (value.school_id !== schoolId || !['GO_OUTDOORS', 'MODIFIED_OUTDOORS', 'INDOOR_ONLY', 'DATA_INSUFFICIENT'].includes(value.decision)
    || !['decided', 'DATA_INSUFFICIENT', 'VERIFY_STATUS'].includes(value.status) || value.persistence?.historical === true
    || !Array.isArray(value.actions) || !Array.isArray(value.rule_evaluations) || !Array.isArray(value.reasons)
    || !Array.isArray(value.evidence) || !Array.isArray(value.warnings) || !Array.isArray(value.sources) || !Array.isArray(value.policy_sources)
    || !timestamp(value.evaluation_time) || !timestamp(value.valid_until) || !value.data_quality
    || typeof value.decision_id !== 'string' || value.actions.some((a: any) => typeof a.instruction !== 'string'
      || typeof a.recommendation !== 'string' || typeof a.mandatory !== 'boolean' || !Array.isArray(a.applicable_grades))
    || (value.decision === 'GO_OUTDOORS' && (value.requires_regulatory_verification || !value.data_quality.station_observations_available))) fail();
  return value;
}
export async function getSchool(id: string, signal?: AbortSignal): Promise<SchoolProfile> {
  const result = await request(path(id), signal); if (result.status !== 200) throw new ApiError(result.status, 'http');
  const v = result.body;
  if (v?.school_id !== id || typeof v.name !== 'string' || !v.name.trim() || typeof v.city !== 'string' || v.timezone !== 'Asia/Kolkata'
    || !Number.isFinite(v.latitude) || !Number.isFinite(v.longitude) || !Array.isArray(v.languages) || !v.languages.length
    || v.languages.some((l: string) => !['en', 'hi'].includes(l)) || typeof v.is_demo !== 'boolean') fail();
  return v;
}
export function getSafety(id: string, kind: 'verdict', signal?: AbortSignal): Promise<VerdictResponse>;
export function getSafety(id: string, kind: 'grap', signal?: AbortSignal): Promise<GrapResponse>;
export async function getSafety(id: string, kind: 'verdict' | 'grap', signal?: AbortSignal) {
  const result = await request(path(id, kind), signal); if (result.status !== 200) throw new ApiError(result.status, 'http');
  if (kind === 'verdict') return validateVerdict(result.body, id);
  validateGrap(result.body); return result.body as GrapResponse;
}
export async function getEvidence(id: string, kind: 'air' | 'forecast', signal?: AbortSignal): Promise<Evidence> {
  const {body: v, status} = await request(path(id, kind), signal);
  if (v?.school_id !== id || !['available', 'stale', 'unavailable'].includes(v.status) || !Array.isArray(v.sources)
    || !Array.isArray(v.warnings) || !v.cache) {if (status !== 200) throw new ApiError(status, 'http'); fail();}
  const points = kind === 'forecast' ? v.points : v.modeled_current ? [v.modeled_current] : [];
  if (!Array.isArray(points) || points.some((p: Point) => !timestamp(p?.valid_at) || !Array.isArray(p.pollutants) || !Array.isArray(p.aqi)
    || p.pollutants.some(x => !Number.isFinite(x.value) || x.value < 0 || x.unit !== 'ug/m3' || x.source_type !== 'model_forecast' || x.observed_at !== null || x.forecast_for !== p.valid_at)
    || p.aqi.some(x => !Number.isFinite(x.value) || x.value < 0 || x.scale !== 'US_AQI' || x.source_type !== 'model_forecast' || x.observed_at !== null || x.forecast_for !== p.valid_at))) fail();
  return v;
}
export async function getAdvisory(id: string, signal?: AbortSignal, verdictId?: string): Promise<AdvisoryResponse> {
  const result = await request(path(id, 'advisory'), signal, verdictId ? {verdict_id: verdictId, languages: ['en', 'hi']} : undefined);
  if (result.status !== 200) throw new ApiError(result.status, 'http');
  try {validateVerdict(result.body?.authoritative_decision, id); return validateAdvisory(result.body, id);} catch {return fail();}
}
export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const result = await request('/health', signal); if (result.status !== 200) throw new ApiError(result.status, 'http');
  const v = result.body;
  if (v?.status !== 'ok' || v.service !== 'hawahawai-backend' || v.phase !== 0 || !timestamp(v.timestamp)) fail();
  return v;
}
export async function getHistory(id: string, signal?: AbortSignal): Promise<VerdictHistory> {
  const result = await request(path(id, 'verdict/history'), signal); if (result.status !== 200) throw new ApiError(result.status, 'http');
  const v = result.body;
  if (v?.school_id !== id || v.status !== 'historical' || v.actionable !== false || typeof v.expired !== 'boolean'
    || typeof v.matches_current_profile !== 'boolean' || !v.record?.decision) fail();
  return v;
}

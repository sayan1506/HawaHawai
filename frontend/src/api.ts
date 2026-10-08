export interface HealthResponse {
  status: 'ok'; service: 'hawahawai-backend'; environment: string;
  version: string; timestamp: string; phase: 0;
}

export interface Pollutant {name: string; value: number; unit: string; original_unit: string; source_id: string; source_type: 'model_forecast'; observed_at: null; forecast_for: string}
export interface Aqi {value: number; scale: 'US_AQI'; source_id: string; forecast_for: string}
export interface Point {valid_at: string; pollutants: Pollutant[]; aqi: Aqi[]}
export interface Evidence {
  school_id: string; status: 'available' | 'stale' | 'unavailable'; freshness_status: string;
  retrieved_at: string | null; warnings: string[]; sources: {name: string; url: string; kind: string; retrieved_at: string}[];
  modeled_current?: Point | null; observations?: Point[];
  observation_providers?: {source_name: string; status: string; source_url: string; retrieved_at: string}[];
  points?: Point[]; forecast_start?: string | null; forecast_end?: string | null;
  cache: {status: string; fresh_until: string | null};
}

export async function getEvidence(schoolId: string, kind: 'air' | 'forecast', signal?: AbortSignal): Promise<Evidence> {
  const base = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:18080').replace(/\/$/, '');
  const response = await fetch(`${base}/v1/schools/${encodeURIComponent(schoolId)}/${kind}`, {signal, cache: 'no-store'});
  const body = await response.json();
  if ((!response.ok && response.status !== 503) || !body || body.school_id !== schoolId || !['available', 'stale', 'unavailable'].includes(body.status)
    || !Array.isArray(body.sources) || !Array.isArray(body.warnings) || !body.cache) throw new Error(`Environmental API returned HTTP ${response.status}`);
  const points = kind === 'forecast' ? body.points : body.modeled_current ? [body.modeled_current] : [];
  if (!Array.isArray(points) || points.some((p: Point) => !p || Number.isNaN(Date.parse(p.valid_at)) || !Array.isArray(p.pollutants) || !Array.isArray(p.aqi)
    || p.pollutants.some(v => !Number.isFinite(v.value) || v.value < 0 || v.unit !== 'ug/m3' || v.source_type !== 'model_forecast' || v.observed_at !== null || v.forecast_for !== p.valid_at)
    || p.aqi.some(v => !Number.isFinite(v.value) || v.scale !== 'US_AQI' || v.forecast_for !== p.valid_at))) throw new Error('Unexpected environmental schema');
  return body as Evidence;
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const base = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:18080').replace(/\/$/, '');
  const response = await fetch(`${base}/health`, {signal, cache: 'no-store'});
  if (!response.ok) throw new Error(`Health API returned HTTP ${response.status}`);
  const body: unknown = await response.json();
  if (!body || typeof body !== 'object' || !('status' in body) || body.status !== 'ok'
    || !('service' in body) || body.service !== 'hawahawai-backend'
    || !('phase' in body) || body.phase !== 0
    || !('environment' in body) || typeof body.environment !== 'string'
    || !('version' in body) || typeof body.version !== 'string'
    || !('timestamp' in body) || typeof body.timestamp !== 'string'
    || Number.isNaN(Date.parse(body.timestamp))) throw new Error('Unexpected health response');
  return body as HealthResponse;
}

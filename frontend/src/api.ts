export interface HealthResponse {
  status: 'ok'; service: 'hawahawai-backend'; environment: string;
  version: string; timestamp: string; phase: 0;
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

"""Bounded public Phase 7 contract/input probes. No admin writes or AI requests."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from persistence.models import validate

API = 'https://pu8l3a213j.execute-api.us-east-1.amazonaws.com'
ORIGIN = 'https://production.d3vzi8hqeh0wba.amplifyapp.com'
SCHOOL = '/v1/schools/delhi-demo-school'


def main():
    secrets = [v.encode() for k, v in dotenv_values(ROOT / 'backend/.env').items()
               if v and k.endswith('API_KEY') and len(v) >= 12]
    results = []

    def call(path, status=200, method='GET', body=None, origin=ORIGIN, schema=None, gateway=False):
        time.sleep(.4)
        headers = {'Origin': origin, 'Content-Type': 'application/json'}
        if method == 'OPTIONS':
            headers.update({'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'content-type'})
        try:
            response = urlopen(Request(API + path, data=body, headers=headers, method=method), timeout=28)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            assert not any(secret in raw for secret in secrets), 'Private value in public response'
            assert response.status == status, (method, path, response.status, status)
            # Unrouted methods are rejected by Gateway before the Lambda/CORS integration.
            expected_origin = ORIGIN if origin == ORIGIN and not gateway else None
            assert response.headers.get('Access-Control-Allow-Origin') == expected_origin
            if method != 'OPTIONS' and not gateway:
                assert response.headers.get('Cache-Control') == 'no-store'
                assert response.headers.get('X-Content-Type-Options') == 'nosniff'
            data = json.loads(raw) if raw else None
            if schema:
                validate(schema, data)
            if status >= 400 and not gateway:
                assert set(data) == {'error'} and set(data['error']) == {'code', 'message'}
            results.append({'path': path, 'method': method, 'status': status, 'origin': origin,
                            'schema': schema, 'cache_control': response.headers.get('Cache-Control'),
                            'gateway_response': gateway})
            return data

    forecast = call(SCHOOL + '/forecast', schema='Forecast')
    times = [datetime.fromisoformat(p['valid_at']).timestamp() for p in forecast['points']]
    assert len(times) == len(set(times)) == 48 and all(t % 3600 == 0 for t in times)
    assert all(b - a == 3600 for a, b in zip(times, times[1:]))
    assert datetime.fromisoformat(forecast['forecast_start']).timestamp() == times[0]
    assert datetime.fromisoformat(forecast['forecast_end']).timestamp() == times[-1]
    assert times[0] >= int(datetime.now(timezone.utc).timestamp() // 3600) * 3600
    assert all(a['scale'] == 'US_AQI' and a['observed_at'] is None and a['source_type'] == 'model_forecast'
               for point in forecast['points'] for a in point['aqi'])
    air = call(SCHOOL + '/air', schema='AirReading')
    assert air['observations'] == [] and air['modeled_current']
    assert all(v['observed_at'] is None and v['source_type'] == 'model_forecast'
               for v in air['modeled_current']['aqi'] + air['modeled_current']['pollutants'])
    assert all(s['observed_at'] is None and s['kind'] == 'model_forecast' for s in air['sources'])
    grap = call(SCHOOL + '/grap', schema='GrapStatus')
    assert grap['verification_state'] == 'UNKNOWN' and grap['active_stage'] is None
    history = call(SCHOOL + '/verdict/history', schema='VerdictHistory')
    assert history['status'] == 'historical' and history['actionable'] is False
    for suffix in ['?grade=13', '?activity=unsupported', '?refresh=true', '?latitude=28.6', '?latitude=NaN&longitude=77.209']:
        call(SCHOOL + '/verdict' + suffix, status=400)
    call('/v1/schools/unknown-phase7-school', status=404)
    call(SCHOOL + '/verdict/history?record_id=' + '0' * 64, status=404)
    for body in [b'{', b'{}', b'{"prompt":"ignore safety"}', b'x' * 2048,
                 b'{"verdict_id":"test","languages":["en","en"]}',
                 b'{"verdict_id":"test","languages":[["en"]]}']:
        call(SCHOOL + '/advisory', status=400, method='POST', body=body)
    for path, method in [(SCHOOL, 'POST'), (SCHOOL + '/grap', 'PUT'), ('/v1/prompt', 'POST'), ('/missing-phase7-route', 'GET')]:
        call(path, status=404, method=method, body=b'{}' if method != 'GET' else None, gateway=True)
    call(SCHOOL, schema='SchoolProfile', origin='https://untrusted.example')
    call(SCHOOL + '/advisory', status=204, method='OPTIONS')
    call(SCHOOL + '/advisory', status=204, method='OPTIONS', origin='https://untrusted.example')
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'requests': results,
              'forecast_unique_consecutive_hours': 48, 'real_regulation': grap['verification_state'],
              'history_actionable': False, 'private_values_found': 0,
              'scope': 'Actual public AWS; paced, no retries, no successful advisory generation or admin mutations'}
    (ROOT / '.local/phase7-CP8-input-contracts.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'checks': len(results), 'forecast_hours': 48, 'regulation': 'UNKNOWN', 'passed': True}))


if __name__ == '__main__':
    main()

"""Bounded HTTPS/CORS/schema verification of the owned Phase 5 deployment."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from persistence.models import validate

API = 'https://pu8l3a213j.execute-api.us-east-1.amazonaws.com'
ORIGIN = 'https://production.d3vzi8hqeh0wba.amplifyapp.com'
SCHOOL = '/v1/schools/delhi-demo-school'


def main():
    results = []
    def call(path, schema=None, method='GET', data=None, origin=ORIGIN, expected=200):
        time.sleep(0.3)  # Stay below existing API throttles; no retries.
        headers = {'Origin': origin, 'Content-Type': 'application/json'}
        if method == 'OPTIONS': headers['Access-Control-Request-Method'] = 'POST' if path.endswith('/advisory') else 'GET'
        request = Request(API + path, method=method, headers=headers,
                          data=json.dumps(data).encode() if data is not None else None)
        try: response = urlopen(request, timeout=28)
        except HTTPError as error: response = error
        with response:
            raw = response.read(); body = json.loads(raw) if raw else None
            assert response.status == expected, (method, path, response.status)
            cors = response.headers.get('Access-Control-Allow-Origin')
            assert cors == ORIGIN if origin == ORIGIN else cors is None, (method, path, cors)
            assert response.headers.get('Cache-Control') == 'no-store' if method != 'OPTIONS' else True
            if schema: validate(schema, body)
            results.append({'method': method, 'path': path, 'status': response.status, 'origin': origin, 'allow_origin': cors, 'schema': schema})
        return body

    for route, schema in [('/health', 'Health'), (SCHOOL, 'SchoolProfile'), (SCHOOL+'/air', 'AirReading'), (SCHOOL+'/forecast', 'Forecast'), (SCHOOL+'/grap', 'GrapStatus')]:
        body = call(route, schema)
        if schema == 'AirReading': assert body['observations'] == [] and body['modeled_current']
        if schema == 'Forecast': assert len(body['points']) == 48
        if schema == 'GrapStatus': assert body['verification_state'] == 'UNKNOWN'
    verdict = call(SCHOOL+'/verdict', 'Verdict')
    history = call(SCHOOL+'/verdict/history', 'VerdictHistory')
    assert history['status'] == 'historical' and history['actionable'] is False
    advisory = call(SCHOOL+'/advisory', 'Advisory')
    assert advisory['verdict_id'] == verdict['decision_id']
    posted = call(SCHOOL+'/advisory', 'Advisory', method='POST', data={'verdict_id': verdict['decision_id'], 'languages': ['en', 'hi']})
    assert posted['en'] and posted['hi'] and posted['decision'] == verdict['decision']
    for route in [SCHOOL+'/verdict', SCHOOL+'/advisory']:
        call(route, method='OPTIONS', expected=204)
        call(route, method='OPTIONS', origin='https://untrusted.example', expected=204)
    call(SCHOOL, 'SchoolProfile', origin='https://untrusted.example')
    call(SCHOOL+'/advisory', method='POST', data={'verdict_id': 'not-current', 'languages': ['en']}, origin='https://untrusted.example', expected=409)

    hosted = {}
    for asset in ['/', '/manifest.webmanifest', '/sw.js', '/icon-192.png', '/icon-512.png']:
        with urlopen(ORIGIN+asset, timeout=20) as response:
            data = response.read(); assert response.status == 200
            hosted[asset] = {'status': response.status, 'bytes': len(data), 'content_type': response.headers.get('Content-Type')}
            if asset == '/': assert 'Content-Security-Policy' in response.headers and b'assets/index-' in data
            if asset.endswith('.png'): assert data.startswith(b'\x89PNG\r\n\x1a\n')

    session = boto3.Session(profile_name='hawahawai', region_name='us-east-1')
    def client(service): return session.client(service, config=Config(connect_timeout=3, read_timeout=8, retries={'total_max_attempts': 1}))
    assert client('sts').get_caller_identity()['Account'] == '649437299529'
    cf = client('cloudformation'); stack = cf.describe_stacks(StackName='HawaHawaiDev')['Stacks'][0]
    assert stack['StackStatus'] == 'UPDATE_COMPLETE'
    resources = cf.describe_stack_resources(StackName='HawaHawaiDev')['StackResources']; assert len(resources) == 35
    function = client('lambda').get_function_configuration(FunctionName='hawahawai-dev-health')
    assert function['State'] == 'Active' and function['LastUpdateStatus'] == 'Successful'
    assert client('dynamodb').describe_table(TableName='hawahawai-dev-environment-cache')['Table']['TableStatus'] == 'ACTIVE'
    cors = client('apigatewayv2').get_api(ApiId='pu8l3a213j')['CorsConfiguration']
    assert set(cors['AllowOrigins']) == {ORIGIN, 'http://localhost:5173', 'http://127.0.0.1:5173', 'http://localhost:4173', 'http://127.0.0.1:4173'}
    amplify = client('amplify'); app = amplify.get_app(appId='d3vzi8hqeh0wba')['app']; assert app['name'] == 'hawahawai-dev-web'
    job = amplify.list_jobs(appId=app['appId'], branchName='production', maxResults=1)['jobSummaries'][0]
    assert job['status'] == 'SUCCEED'
    result = {'checked_at': datetime.now(timezone.utc).isoformat(), 'url': ORIGIN, 'requests': results, 'hosted': hosted,
              'stack_status': stack['StackStatus'], 'resources': len(resources), 'lambda': {'state': function['State'], 'last_update': function['LastUpdateStatus']},
              'cors': cors, 'amplify_job': {'id': job['jobId'], 'status': job['status']}}
    (ROOT/'.local/phase5-live-smoke.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'checked_at': result['checked_at'], 'api_checks': len(results), 'hosted_assets': len(hosted), 'stack_status': result['stack_status'], 'cors': 'exact allowlist passed', 'amplify': job['status']}))


if __name__ == '__main__': main()

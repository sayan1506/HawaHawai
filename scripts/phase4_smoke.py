"""Bounded real APIs + exact-owned-key readback; never alter regulatory evidence."""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import boto3
from botocore.config import Config

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]
from persistence.models import validate, validate_record, digest, profile_key, context_key, IST
from persistence.service import history_key, current_key
from environmental.cache import decode_payload
from safety.models import ActivityContext
BASE='https://pu8l3a213j.execute-api.us-east-1.amazonaws.com'
PATH='/v1/schools/delhi-demo-school'

def call(path, schema=None, expected=200, method='GET', data=None, headers=None):
    time.sleep(0.25)  # Below the deployed 5 requests/second API throttle; no retry loop.
    req=Request(BASE+path,method=method,data=json.dumps(data).encode() if data is not None else None,
                headers=headers or {'Content-Type':'application/json'})
    try:response=urlopen(req,timeout=28)
    except HTTPError as error:response=error
    with response:
        raw=response.read();body=json.loads(raw) if raw else None
        assert response.status==expected, (path,response.status,body.get('error') if isinstance(body,dict) else None)
        normalized={k.lower():v for k,v in response.headers.items()}
    if schema:validate(schema,body)
    return body,normalized

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expiry',action='store_true');parser.add_argument('--label',choices=['initial','final','release'],default='initial');args=parser.parse_args()
    checks={};responses={};stamp=datetime.now(timezone.utc)
    if args.expiry:
        original=json.loads((ROOT/'.local/phase4-live-smoke.json').read_text(encoding='utf-8'))['responses']['verdict_first']
        assert datetime.fromisoformat(original['valid_until'])<stamp, 'Wait for the original record to expire; do not falsify it'
        old,_=call(PATH+'/verdict/history?record_id='+original['persistence']['record_id'],'VerdictHistory')
        fresh,_=call(PATH+'/verdict','Verdict')
        assert old['expired'] and not old['actionable'] and old['status']=='historical'
        assert fresh['persistence']['record_id']!=original['persistence']['record_id']
        assert datetime.fromisoformat(fresh['valid_until'])>datetime.now(timezone.utc)
        checks={'real_expiry_history_not_current':True,'fresh_current_record':True}
        responses={'old_history':old,'fresh_verdict':fresh};target='phase4-live-expiry.json'
    else:
        for suffix,schema in [('/health','Health'),(PATH,'SchoolProfile'),(PATH+'/air','AirReading'),(PATH+'/forecast','Forecast'),(PATH+'/grap','GrapStatus')]:
            body,_=call(suffix,schema);responses[schema]=body
        school=responses['SchoolProfile'];assert school['school_id']=='delhi-demo-school'
        air=responses['AirReading'];assert air['observations']==[] and air['modeled_current']
        forecast=responses['Forecast'];assert len(forecast['points'])==48
        first,_=call(PATH+'/verdict','Verdict');second,_=call(PATH+'/verdict','Verdict')
        assert first['persistence']['status'] in {'stored','reused','repaired'}
        assert second['persistence']['status']=='reused' and first['persistence']['record_id']==second['persistence']['record_id']
        assert first['evaluation_time']==second['evaluation_time'] and first['valid_until']==second['valid_until']
        assert first['regulatory_status']['verification_state']=='UNKNOWN'
        historical,_=call(PATH+'/verdict/history?record_id='+first['persistence']['record_id'],'VerdictHistory')
        daily,_=call(PATH+'/verdict/history','VerdictHistory')
        assert historical['actionable'] is False and historical['record']['decision']['decision_id']==first['decision_id']
        assert historical['matches_current_profile'] and not historical['expired']
        advisory,_=call(PATH+'/advisory','Advisory');cached,_=call(PATH+'/advisory','Advisory')
        assert cached['cache']['status']=='hit' and advisory['en'] and advisory['hi']
        assert advisory['verdict_id']==advisory['authoritative_decision']['decision_id']==first['decision_id']
        assert advisory['decision']==first['decision']
        post,_=call(PATH+'/advisory','Advisory',method='POST',data={'verdict_id':advisory['verdict_id'],'languages':['en','hi']})
        assert post['verdict_id']==advisory['verdict_id']
        for suffix,method,expected,data in [('/verdict?force_refresh=true','GET',400,None),('/verdict?grade=13','GET',400,None),('/verdict?latitude=999&longitude=77','GET',400,None),('/verdict/history?record_id=bad','GET',400,None),('/verdict/history?date=2027-01-01','GET',400,None),('','POST',404,{}),('/grap','POST',404,{}),('/advisory','POST',409,{'verdict_id':'old','languages':['en']})]:
            call(PATH+suffix,expected=expected,method=method,data=data)
        call('/v1/schools/unconfigured-school/verdict',expected=404)
        _,headers=call(PATH+'/verdict/history',expected=204,method='OPTIONS',headers={'Origin':'http://127.0.0.1:5173','Access-Control-Request-Method':'GET'})
        assert headers.get('access-control-allow-origin')=='http://127.0.0.1:5173'
        _,headers=call(PATH+'/verdict/history',headers={'Origin':'https://untrusted.example'})
        assert 'access-control-allow-origin' not in headers
        session=boto3.Session(profile_name='hawahawai',region_name='us-east-1')
        config=Config(connect_timeout=2,read_timeout=4,retries={'total_max_attempts':1})
        assert session.client('sts',config=config).get_caller_identity()['Account']=='649437299529'
        db=session.client('dynamodb',config=config)
        def item(key):return db.get_item(TableName='hawahawai-dev-environment-cache',Key={'cache_key':{'S':key}},ConsistentRead=True)['Item']
        profile=item(profile_key());stored_profile=decode_payload(profile['payload']['S'])
        assert 'expires_at' not in profile and stored_profile['profile']==school and stored_profile['profile_fingerprint']==digest(school)
        record_item=item(history_key(first['persistence']['record_id']));record=decode_payload(record_item['payload']['S']);validate_record(record)
        assert record==historical['record'] and int(record_item['expires_at']['N'])>stamp.timestamp()+6*86400
        pointer=decode_payload(item(current_key(ActivityContext()))['payload']['S']);assert pointer['record_id']==record['record_id']
        checks={'health_and_all_existing_routes':True,'real_modeled_data_48h':True,'profile_persisted_no_ttl':True,'immutable_verdict_readback':True,'current_reuse_does_not_extend_validity':True,'history_never_actionable':True,'bilingual_advisory_consistent':True,'advisory_cache_hit':True,'invalid_requests_and_public_writes_rejected':True,'cors_allowlist':True}
        responses.update(verdict_first=first,verdict_second=second,history=historical,daily_history=daily,advisory=advisory);target='phase4-live-smoke.json' if args.label=='initial' else f'phase4-live-{args.label}-smoke.json'
    result={'checked_at':stamp.isoformat(),'checks':checks,'responses':responses}
    (ROOT/'.local'/target).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'checked_at':stamp.isoformat(),'checks':checks,'evidence':'.local/'+target}))
if __name__=='__main__':main()

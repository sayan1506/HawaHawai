"""SIMULATED failure/concurrency cases; no test evidence is written to AWS."""
import copy
import json
import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]
from environmental.cache import MemoryCache, DynamoCache, CacheError, encode_payload, decode_payload
from environmental.config import school_profile
from safety.models import ActivityContext, Policy
from safety.engine import evaluate
from safety.registry import resolve, read_snapshot
from safety.service import verdict
from persistence.models import (digest, profile_key, profile_record, read_profile, validate_profile,
    validate_record, make_record, semantic_fingerprint, IST, validate)
from persistence.service import persist, historical, current_key, history_key, daily_key
from persistence.scheduler import refresh, JOB
from scripts.initialize_school import initialize
from test_safety import SCHOOL, NOW as FIXTURE_NOW, environment, snapshot
from test_advisory import authority
from app import handler

NOW=FIXTURE_NOW+timedelta(seconds=1)
CONTEXT=ActivityContext()
ARN='arn:aws:scheduler:us-east-1:649437299529:schedule/hawahawai-dev-planning/hawahawai-dev-daily-verdict'

def fixture(value=174, context=None, now=NOW, regulatory=None, school=None, policy=None):
    air, forecast, _=environment(value)
    return evaluate(school or SCHOOL,air,forecast,regulatory or resolve(read_snapshot(),now,context or CONTEXT),now,context or CONTEXT,policy)

class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.cache=MemoryCache();self.record=profile_record(SCHOOL,NOW.isoformat());self.cache.put(profile_key(),self.record)
    def test_valid_persisted_profile(self): self.assertEqual(read_profile(self.cache),SCHOOL)
    def test_empty_record(self):
        with self.assertRaises(RuntimeError): read_profile(MemoryCache())
    def test_schema_extra_pii_rejected(self):
        with self.assertRaises(Exception): validate_profile({**SCHOOL,'student_name':'SIMULATED'})
    def test_invalid_coordinates(self):
        for x in (None,True,'28.6',float('nan'),90):
            with self.assertRaises(Exception): validate_profile({**SCHOOL,'latitude':x})
    def test_unknown_school(self):
        with self.assertRaises(ValueError): validate_profile({**SCHOOL,'school_id':'not-configured'})
    def test_wrong_city(self):
        with self.assertRaises(ValueError): validate_profile({**SCHOOL,'city':'Noida'})
    def test_profile_hash_mismatch(self):
        self.record['profile']['latitude']=28.7;self.cache.put(profile_key(),self.record)
        with self.assertRaises(RuntimeError): read_profile(self.cache)
    def test_profile_storage_version(self):
        self.record['storage_version']='future';self.cache.put(profile_key(),self.record)
        with self.assertRaises(RuntimeError):read_profile(self.cache)
    def test_required_profile_does_not_silently_use_environment(self):
        with patch.dict(os.environ,{'HAWAHAWAI_PROFILE_STORAGE_REQUIRED':'true'}):
            with self.assertRaises(RuntimeError):school_profile(MemoryCache())
    def test_profile_db_failure(self):
        with self.assertRaises(CacheError):read_profile(Mock(get=Mock(side_effect=CacheError('SIMULATION'))))
    def test_initializer_first_conditional_no_ttl(self):
        client=Mock();client.get_item.return_value={}
        self.assertEqual(initialize(client,SCHOOL),'initialized')
        args=client.put_item.call_args.kwargs
        self.assertEqual(args['ConditionExpression'],'attribute_not_exists(cache_key)')
        self.assertNotIn('expires_at',args['Item'])
    def test_duplicate_initialization_does_not_write(self):
        client=Mock();client.get_item.return_value={'Item':{'payload':{'S':encode_payload(self.record)}}}
        self.assertEqual(initialize(client,SCHOOL),'unchanged');client.put_item.assert_not_called()
    def test_update_requires_explicit_matching_hash(self):
        client=Mock();client.get_item.return_value={'Item':{'payload':{'S':encode_payload(self.record)}}}
        with self.assertRaises(ValueError):initialize(client,{**SCHOOL,'latitude':28.7})
        client.put_item.assert_not_called()
    def test_admin_update_uses_payload_cas(self):
        client=Mock();client.get_item.return_value={'Item':{'payload':{'S':encode_payload(self.record)}}}
        self.assertEqual(initialize(client,{**SCHOOL,'latitude':28.7},digest(SCHOOL)),'updated')
        self.assertEqual(client.put_item.call_args.kwargs['ConditionExpression'],'payload = :previous')

class DecisionStorageTests(unittest.TestCase):
    def setUp(self):self.cache=MemoryCache();self.d=fixture()
    def store(self,decision=None,context=None,now=NOW,school=None,origin='ON_DEMAND'):
        return persist(school or SCHOOL,self.cache,decision or self.d,context or CONTEXT,origin,now)
    def test_record_creation_contract(self):
        result=self.store();self.assertEqual(result['persistence']['status'],'stored')
        validate('Verdict',result);validate_record(self.cache.get(history_key(result['persistence']['record_id'])))
    def test_valid_record_reused_without_extending_expiry(self):
        first=self.store();fresh=copy.deepcopy(self.d)
        fresh['evaluation_time']=fresh['generated_at']=(NOW+timedelta(seconds=30)).isoformat()
        fresh['valid_until']=(NOW+timedelta(minutes=5,seconds=30)).isoformat()
        second=self.store(fresh,now=NOW+timedelta(seconds=30))
        self.assertEqual(second['persistence']['status'],'reused');self.assertEqual(first['valid_until'],second['valid_until'])
    def test_expired_favorable_not_returned(self):
        first=copy.deepcopy(self.d);first['decision']=first['verdict']='GO_OUTDOORS';first['valid_until']=(NOW+timedelta(seconds=1)).isoformat()
        self.store(first)
        fresh=copy.deepcopy(self.d);fresh['evaluation_time']=fresh['generated_at']=(NOW+timedelta(minutes=1)).isoformat()
        fresh['valid_until']=(NOW+timedelta(minutes=6)).isoformat()
        result=self.store(fresh,now=NOW+timedelta(minutes=1));self.assertNotEqual(result['decision'],'GO_OUTDOORS')
    def test_history_always_not_actionable(self):
        self.store();value=historical(SCHOOL,self.cache,now=NOW)
        self.assertFalse(value['actionable']);self.assertEqual(value['status'],'historical');validate('VerdictHistory',value)
    def test_expired_history_remains_explicit_history(self):
        self.store();value=historical(SCHOOL,self.cache,date='2026-10-08',now=NOW+timedelta(days=1))
        self.assertTrue(value['expired']);self.assertFalse(value['actionable'])
    def test_corrupt_stored_verdict_rejected(self):
        first=self.store();key=history_key(first['persistence']['record_id']);record=self.cache.get(key);record['decision']['verdict']='GO_OUTDOORS';self.cache.put(key,record)
        result=self.store();self.assertEqual(result['decision'],self.d['decision']);self.assertNotEqual(result['persistence']['status'],'reused')
    def test_corrupt_history_fails_closed(self):
        first=self.store();self.cache.put(history_key(first['persistence']['record_id']),{'corrupt':True})
        with self.assertRaises(RuntimeError):historical(SCHOOL,self.cache,now=NOW)
    def test_changed_policy_recomputes(self):
        first=self.store();new=fixture(policy=Policy(version='school-safety-v2-SIMULATION'))
        result=self.store(new);self.assertNotEqual(first['persistence']['record_id'],result['persistence']['record_id'])
    def test_changed_regulatory_snapshot_recomputes(self):
        first=self.store();reg=resolve(read_snapshot(),NOW,CONTEXT);reg['snapshot_version']='SIMULATION-updated'
        result=self.store(fixture(regulatory=reg));self.assertNotEqual(first['persistence']['record_id'],result['persistence']['record_id'])
    def test_changed_school_coordinates_change_decision_id(self):
        self.assertNotEqual(self.d['decision_id'],fixture(school={**SCHOOL,'latitude':28.7})['decision_id'])
    def test_changed_profile_not_reused(self):
        first=self.store();school={**SCHOOL,'latitude':28.7};result=self.store(fixture(school=school),school=school)
        self.assertNotEqual(first['persistence']['record_id'],result['persistence']['record_id'])
    def test_changed_name_invalidates_even_missing_evidence(self):
        self.assertNotEqual(self.d['decision_id'],fixture(school={**SCHOOL,'name':'SIMULATED changed name'})['decision_id'])
    def test_context_records_are_separate(self):
        first=self.store();context=ActivityContext(grade=5,activity='sports');second=self.store(fixture(context=context),context)
        self.assertNotEqual(first['persistence']['record_id'],second['persistence']['record_id'])
    def test_wrong_context_retrieval_rejected(self):
        first=self.store()
        with self.assertRaises(RuntimeError):historical(SCHOOL,self.cache,ActivityContext(grade=4),record_id=first['persistence']['record_id'],now=NOW)
    def test_db_error_uses_fresh_not_old(self):
        self.cache.get=Mock(side_effect=CacheError('SIMULATION'))
        result=self.store();self.assertEqual(result['decision'],self.d['decision']);self.assertEqual(result['persistence']['status'],'unavailable')
    def test_failed_write_explained(self):
        self.cache.put_record=Mock(side_effect=CacheError('SIMULATION'));result=self.store()
        self.assertEqual(result['persistence']['status'],'unavailable');self.assertTrue(any('STORAGE' in w for w in result['warnings']))
    def test_lease_contention_keeps_fresh_result(self):
        self.cache.acquire(current_key(CONTEXT)+'#lease',NOW.timestamp());result=self.store()
        self.assertEqual(result['persistence']['status'],'busy');self.assertEqual(result['decision'],self.d['decision'])
    def test_concurrent_writers_single_valid_pointer(self):
        with ThreadPoolExecutor(max_workers=4) as executor:results=list(executor.map(lambda _:self.store(),range(4)))
        pointer=self.cache.get(current_key(CONTEXT));validate_record(self.cache.get(history_key(pointer['record_id'])))
        self.assertTrue(all(r['decision']==self.d['decision'] for r in results))
    def test_cas_cannot_regress_current_pointer(self):
        self.assertTrue(self.cache.put_record('SIMULATED',{'revision_epoch':20},20))
        self.assertFalse(self.cache.put_record('SIMULATED',{'revision_epoch':10},10))
    def test_record_future_evaluation_not_reused(self):
        first=self.store(now=NOW-timedelta(seconds=1));self.assertNotEqual(self.store(now=NOW-timedelta(seconds=1))['persistence']['status'],'reused')
    def test_record_integrity_checks_warnings(self):
        record=make_record(SCHOOL,self.d);record['decision']['warnings']=[]
        with self.assertRaises(ValueError):validate_record(record)
    def test_history_missing(self):self.assertIsNone(historical(SCHOOL,self.cache,now=NOW))
    def test_current_deadline_cannot_expand_stored(self):
        self.store();fresh=copy.deepcopy(self.d);fresh['valid_until']=(NOW+timedelta(seconds=10)).isoformat()
        result=self.store(fresh);self.assertNotEqual(result['persistence']['status'],'reused')
    def test_dynamo_conditional_put_and_seven_day_ttl(self):
        client=Mock();cache=DynamoCache('hawahawai-test',client);cache.put_record('delhi-demo-school#verdict#SIMULATED',{'revision_epoch':2},2)
        args=client.put_item.call_args.kwargs;self.assertIn('revision_epoch',args['ConditionExpression']);self.assertIn('expires_at',args['Item'])
    def test_dynamo_condition_failure_is_not_retried(self):
        error=Exception();error.response={'Error':{'Code':'ConditionalCheckFailedException'}}
        client=Mock();client.put_item.side_effect=error;cache=DynamoCache('hawahawai-test',client)
        self.assertFalse(cache.put_record('delhi-demo-school#verdict#SIMULATED',{}));self.assertEqual(client.put_item.call_count,1)

class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.cache=MemoryCache();self.cache.put(profile_key(),profile_record(SCHOOL,NOW.isoformat()))
        self.service=Mock(cache=self.cache);self.event={'job':JOB,'school_id':SCHOOL['school_id'],'schedule_arn':ARN,'scheduled_time':NOW.isoformat()}
        self.env=patch.dict(os.environ,{'HAWAHAWAI_DAILY_SCHEDULE_ARN':ARN});self.env.start();self.addCleanup(self.env.stop)
    def result(self):return persist(SCHOOL,self.cache,fixture(),origin='SCHEDULED',now=NOW)
    def run_job(self):
        with patch('persistence.scheduler.verdict',side_effect=lambda *a,**kw:self.result()):return refresh(self.event,self.service,NOW)
    def test_success_no_ai(self):
        with patch('agent.runtime.generate',side_effect=AssertionError('AI forbidden')):result=self.run_job()
        self.assertEqual(result['status'],'stored');self.assertFalse(result['ai_invoked'])
    def test_duplicate_delivery_no_provider_or_verdict(self):
        first=self.run_job()
        with patch('persistence.scheduler.verdict',side_effect=AssertionError('Duplicate must not reevaluate')):second=refresh(self.event,self.service,NOW)
        self.assertEqual(second['status'],'duplicate');self.assertEqual(first['record_id'],second['record_id']);self.service.get.assert_not_called()
    def test_correct_delhi_date_at_utc_boundary(self):
        stamp=datetime(2026,10,8,20,tzinfo=timezone.utc);self.assertEqual(stamp.astimezone(IST).date().isoformat(),'2026-10-09')
    def test_0700_ist_is_0130_utc(self):
        stamp=datetime(2026,10,8,7,tzinfo=IST);self.assertEqual(stamp.astimezone(timezone.utc).hour,1);self.assertEqual(stamp.astimezone(timezone.utc).minute,30)
    def test_wrong_schedule(self):
        with self.assertRaises(ValueError):refresh({**self.event,'schedule_arn':'SIMULATED-unrelated'},self.service,NOW)
    def test_wrong_school(self):
        with self.assertRaises(ValueError):refresh({**self.event,'school_id':'other-school'},self.service,NOW)
    def test_extra_controls_rejected(self):
        with self.assertRaises(ValueError):refresh({**self.event,'force_ai':True},self.service,NOW)
    def test_delayed_delivery_rejected(self):
        with self.assertRaises(ValueError):refresh(self.event,self.service,NOW+timedelta(minutes=16))
    def test_overlapping_job_fails_bounded_retry(self):
        key='delhi-demo-school#verdict#job#2026-10-08#'+digest(SCHOOL)+'#lease';self.cache.acquire(key,NOW.timestamp())
        with self.assertRaises(RuntimeError):self.run_job()
    def test_storage_failure_retry_not_success(self):
        with patch('persistence.scheduler.verdict',return_value={'persistence':{'status':'unavailable'}}):
            with self.assertRaises(RuntimeError):refresh(self.event,self.service,NOW)
    def test_corrupt_receipt_fails_closed(self):
        self.cache.put('delhi-demo-school#verdict#job#2026-10-08#'+digest(SCHOOL),{'record_id':'corrupt'})
        with self.assertRaises(Exception):refresh(self.event,self.service,NOW)

class PersistenceApiTests(unittest.TestCase):
    def setUp(self):self.cache=MemoryCache();self.service=Mock(cache=self.cache)
    def request(self,suffix='verdict/history',params=None,method='GET'):
        event={'rawPath':'/v1/schools/delhi-demo-school/'+suffix,'requestContext':{'http':{'method':method}},'queryStringParameters':params}
        with patch('environmental.service.get_service',return_value=self.service):return handler(event,None)
    def test_history_missing_404(self):self.assertEqual(self.request()['statusCode'],404)
    def test_history_schema(self):
        d=authority();persist(SCHOOL,self.cache,d);response=self.request();self.assertEqual(response['statusCode'],200);validate('VerdictHistory',json.loads(response['body']))
    def test_public_profile_mutation_rejected(self):self.assertEqual(self.request('',method='POST')['statusCode'],404)
    def test_no_public_force_refresh(self):self.assertEqual(self.request('verdict',{'force_refresh':'true'})['statusCode'],400)
    def test_history_invalid_parameters(self):
        for params in ({'record_id':'bad'},{'date':'garbage'},{'date':'2027-01-01'},{'date':'2026-10-08','record_id':'0'*64},{'grade':'13'}):self.assertEqual(self.request(params=params)['statusCode'],400)
    def test_required_corrupt_profile_503(self):
        with patch.dict(os.environ,{'HAWAHAWAI_PROFILE_STORAGE_REQUIRED':'true'}):self.assertEqual(self.request()['statusCode'],503)
    def test_history_db_unavailable_503(self):
        self.cache.get=Mock(side_effect=CacheError('SIMULATION'));self.assertEqual(self.request()['statusCode'],503)
    def test_corrupt_history_pointer_503(self):
        from persistence.service import daily_key
        self.cache.put(daily_key(datetime.now(timezone.utc).astimezone(IST).date().isoformat(),CONTEXT),{'bad':'SIMULATED'})
        self.assertEqual(self.request()['statusCode'],503)
    def test_history_rejects_current_metadata(self):
        record=make_record(SCHOOL,authority());record['decision']['persistence']={'status':'reused','storage_version':'verdict-record-v1','record_id':record['record_id'],'historical':False}
        with self.assertRaises(ValueError):validate_record(record)

class TrustedFlowTests(unittest.TestCase):
    def service(self):
        cache=MemoryCache();cache.put(profile_key(),profile_record(SCHOOL,NOW.isoformat()))
        air, forecast, _=environment(174)
        return Mock(cache=cache,get=Mock(side_effect=lambda school,kind:copy.deepcopy(air if kind=='current' else forecast)))
    def test_real_phase2_to_persistent_record(self):
        service=self.service();result=verdict(SCHOOL,service,evaluation_time=NOW)
        self.assertEqual(result['persistence']['status'],'stored');self.assertEqual(result['regulatory_status']['verification_state'],'UNKNOWN')
        record=service.cache.get(history_key(result['persistence']['record_id']));self.assertEqual(record['decision']['decision_id'],result['decision_id'])
    def test_real_service_provider_failure_not_favorable(self):
        service=self.service();service.get.side_effect=CacheError('SIMULATION')
        result=verdict(SCHOOL,service,evaluation_time=NOW)
        self.assertEqual(result['decision'],'DATA_INSUFFICIENT');self.assertEqual(result['persistence']['status'],'stored')
    def test_missing_forecast_persisted_with_limitation(self):
        service=self.service();air,forecast,_=environment(174);forecast['points']=[]
        service.get.side_effect=lambda s,k:copy.deepcopy(air if k=='current' else forecast)
        result=verdict(SCHOOL,service,evaluation_time=NOW);self.assertFalse(result['data_quality']['forecast_available']);self.assertNotEqual(result['decision'],'GO_OUTDOORS')
    def test_stale_modeled_values_not_station(self):
        service=self.service();air,forecast,_=environment(174);air['freshness_status']='stale';air['status']='stale'
        service.get.side_effect=lambda s,k:copy.deepcopy(air if k=='current' else forecast)
        result=verdict(SCHOOL,service,evaluation_time=NOW)
        self.assertFalse(result['data_quality']['modeled_data_available']);self.assertFalse(result['data_quality']['official_observations_available'])
    def test_conflicting_registry_stored_honestly(self):
        reg=resolve(read_snapshot(),NOW,CONTEXT);reg['verification_state']='CONFLICTING'
        cache=MemoryCache();result=persist(SCHOOL,cache,fixture(regulatory=reg),now=NOW)
        self.assertEqual(result['regulatory_status']['verification_state'],'CONFLICTING');self.assertNotEqual(result['decision'],'GO_OUTDOORS')
    def test_stale_registry_does_not_become_verified(self):
        reg=resolve(read_snapshot(),NOW,CONTEXT);reg['verification_state']='STALE'
        cache=MemoryCache();result=persist(SCHOOL,cache,fixture(regulatory=reg),now=NOW)
        self.assertEqual(result['regulatory_status']['verification_state'],'STALE');self.assertNotEqual(result['decision'],'GO_OUTDOORS')
    def test_real_scheduled_handler_stores_without_importing_agent(self):
        service=self.service();event={'job':JOB,'school_id':SCHOOL['school_id'],'schedule_arn':ARN,'scheduled_time':datetime.now(timezone.utc).isoformat()}
        with patch.dict(os.environ,{'HAWAHAWAI_DAILY_SCHEDULE_ARN':ARN}),patch('environmental.service.get_service',return_value=service),patch('agent.runtime.generate',side_effect=AssertionError('AI forbidden')):
            result=handler(event,None)
        self.assertEqual(result['status'],'stored');self.assertFalse(result['ai_invoked'])
    def test_duplicate_completes_before_lease_rechecks_receipt(self):
        service=self.service();event={'job':JOB,'school_id':SCHOOL['school_id'],'schedule_arn':ARN,'scheduled_time':NOW.isoformat()}
        with patch.dict(os.environ,{'HAWAHAWAI_DAILY_SCHEDULE_ARN':ARN}):
            first=refresh(event,service,NOW)
            original_get=service.cache.get;receipt_key='delhi-demo-school#verdict#job#2026-10-08#'+digest(SCHOOL)
            reads=[]
            def racing_get(key):
                if key==receipt_key:
                    reads.append(key)
                    if len(reads)==1:return None  # SIMULATED racing delivery already finished.
                return original_get(key)
            service.cache.get=racing_get;service.get.reset_mock()
            second=refresh(event,service,NOW)
        self.assertEqual(second['status'],'duplicate');self.assertEqual(first['record_id'],second['record_id']);service.get.assert_not_called()
    def test_scheduled_pointer_retry_is_idempotent(self):
        cache=MemoryCache();first=persist(SCHOOL,cache,fixture(),origin='SCHEDULED',now=NOW)
        second=persist(SCHOOL,cache,fixture(),origin='SCHEDULED',now=NOW+timedelta(seconds=1))
        self.assertEqual(second['persistence']['status'],'stored');self.assertEqual(first['persistence']['record_id'],second['persistence']['record_id'])
        self.assertEqual(first['evaluation_time'],second['evaluation_time']);self.assertEqual(first['valid_until'],second['valid_until'])
    def test_job_recovers_after_receipt_write_failure(self):
        service=self.service();event={'job':JOB,'school_id':SCHOOL['school_id'],'schedule_arn':ARN,'scheduled_time':NOW.isoformat()}
        original=service.cache.put_record;failed=[]
        def write(key,value,revision=None):
            if '#verdict#job#' in key and not failed:
                failed.append(key);raise CacheError('SIMULATED_RECEIPT_ACK_FAILURE')
            return original(key,value,revision)
        service.cache.put_record=write
        with patch.dict(os.environ,{'HAWAHAWAI_DAILY_SCHEDULE_ARN':ARN}):
            with self.assertRaises(CacheError):refresh(event,service,NOW)
            second=refresh(event,service,NOW)
            third=refresh(event,service,NOW)
        self.assertEqual(second['status'],'stored');self.assertEqual(third['status'],'duplicate');self.assertEqual(second['record_id'],third['record_id'])
    def test_advisory_keeps_durable_authority_both_languages(self):
        from advisory.service import explain
        service=self.service();value=explain(SCHOOL,service,keys={})
        self.assertTrue(value['en'] and value['hi']);self.assertEqual(value['decision'],value['authoritative_decision']['decision'])
        self.assertIn(value['authoritative_decision']['persistence']['status'],{'stored','reused'})
        self.assertEqual(value['generator'],'rule_template')

if __name__=='__main__':unittest.main()

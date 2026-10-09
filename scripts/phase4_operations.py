"""Readback of owned scheduler/IAM/logs; optional bounded private duplicate replay."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import boto3
from botocore.config import Config

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]
from persistence.models import read_profile, digest, IST, validate_record
from persistence.scheduler import JOB
from persistence.service import prefix, history_key
from environmental.cache import DynamoCache

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expect-time',default='07:00');parser.add_argument('--delivery',action='store_true');parser.add_argument('--replay',action='store_true');parser.add_argument('--phase',default='phase4',choices=['phase4','phase6']);args=parser.parse_args()
    session=boto3.Session(profile_name='hawahawai',region_name='us-east-1')
    def client(name):return session.client(name,config=Config(connect_timeout=2,read_timeout=5,retries={'total_max_attempts':1}))
    assert client('sts').get_caller_identity()['Account']=='649437299529'
    schedule=client('scheduler').get_schedule(Name='hawahawai-dev-daily-verdict',GroupName='hawahawai-dev-planning')
    hour,minute=map(int,args.expect_time.split(':'))
    assert schedule['ScheduleExpression']==f'cron({minute} {hour} * * ? *)' and schedule['ScheduleExpressionTimezone']=='Asia/Kolkata'
    assert schedule['State']=='ENABLED' and schedule['FlexibleTimeWindow']['Mode']=='OFF'
    target=schedule['Target'];assert target['Arn']=='arn:aws:lambda:us-east-1:649437299529:function:hawahawai-dev-health'
    assert target['RetryPolicy']=={'MaximumEventAgeInSeconds':900,'MaximumRetryAttempts':1}
    assert json.loads(target['Input'])=={'job':JOB,'school_id':'delhi-demo-school','schedule_arn':'<aws.scheduler.schedule-arn>','scheduled_time':'<aws.scheduler.scheduled-time>'}
    iam=client('iam');role=iam.get_role(RoleName='hawahawai-dev-planning-role')['Role']
    trust=role['AssumeRolePolicyDocument']['Statement'][0]
    assert trust['Principal']=={'Service':'scheduler.amazonaws.com'} and trust['Condition']['StringEquals']=={'aws:SourceAccount':'649437299529','aws:SourceArn':'arn:aws:scheduler:us-east-1:649437299529:schedule-group/hawahawai-dev-planning'}
    assert iam.list_role_policies(RoleName=role['RoleName'])['PolicyNames']==['hawahawai-dev-planning-invoke']
    assert iam.list_attached_role_policies(RoleName=role['RoleName'])['AttachedPolicies']==[]
    simulations={}
    for name,arn in [('owned',target['Arn']),('unrelated','arn:aws:lambda:us-east-1:649437299529:function:ChugLi-not-owned')]:
        result=iam.simulate_principal_policy(PolicySourceArn=role['Arn'],ActionNames=['lambda:InvokeFunction'],ResourceArns=[arn])['EvaluationResults'][0]['EvalDecision']
        assert result==('allowed' if name=='owned' else 'implicitDeny');simulations[name]=result
    result={'checked_at':datetime.now(timezone.utc).isoformat(),'schedule':schedule['Arn'],'daily_time':args.expect_time,'timezone':'Asia/Kolkata','scheduler_iam':simulations,'ai_scheduled':False,'max_delivery_attempts':2}
    async_config=client('lambda').get_function_event_invoke_config(FunctionName='hawahawai-dev-health',Qualifier='$LATEST')
    assert async_config['MaximumRetryAttempts']==1 and async_config['MaximumEventAgeInSeconds']==900
    assert async_config['FunctionArn']==target['Arn']+':$LATEST'
    result.update(max_function_error_attempts=2,async_event_age_seconds=900)
    if args.delivery:
        cache=DynamoCache('hawahawai-dev-environment-cache',client('dynamodb'));school=read_profile(cache)
        date=datetime.now(timezone.utc).astimezone(IST).date().isoformat();key=prefix()+'job#'+date+'#'+digest(school)
        receipt=cache.get(key);assert receipt and receipt['job']==JOB
        record=validate_record(cache.get(history_key(receipt['record_id'])))
        assert record['origin']=='SCHEDULED' and record['local_date']==date
        events=client('logs').filter_log_events(logGroupName='hawahawai-dev-health-logs',startTime=int(datetime.fromisoformat(receipt['scheduled_time']).timestamp()*1000),filterPattern='"daily_refresh"',limit=30)['events']
        deliveries=[entry for entry in events if '"status": "stored"' in entry['message'] and record['record_id'] in entry['message']]
        assert deliveries and all('"ai_invoked": false' in entry['message'] for entry in deliveries)
        result.update(real_scheduler_delivery=True,scheduled_time=receipt['scheduled_time'],record_id=record['record_id'],decision=record['decision']['decision'],valid_until=record['decision']['valid_until'])
        if args.replay:
            # Exactly one private administrative duplicate replay AFTER actual delivery.
            # The idempotency receipt prevents provider/AI work. No production fixtures.
            # Use a current same-day timestamp so this administrative duplicate
            # remains valid after the actual delivery's 15-minute acceptance window.
            event={'job':JOB,'school_id':school['school_id'],'schedule_arn':schedule['Arn'],'scheduled_time':datetime.now(timezone.utc).isoformat()}
            response=client('lambda').invoke(FunctionName='hawahawai-dev-health',InvocationType='RequestResponse',Payload=json.dumps(event).encode())
            body=json.loads(response['Payload'].read());assert not response.get('FunctionError') and body['status']=='duplicate' and body['record_id']==record['record_id'] and body['ai_invoked'] is False
            result['private_duplicate_replay']=body
            result['replay_kind']='private same-day duplicate; not an additional Scheduler delivery'
    (ROOT/'.local'/(f'{args.phase}-scheduler-delivery.json' if args.delivery else f'{args.phase}-scheduler-config.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__':main()

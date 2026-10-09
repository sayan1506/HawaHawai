"""Secret-safe static audit and HawaHawai-only AWS readback. No billing writes."""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
import boto3
from botocore.config import Config
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from environmental.cache import decode_payload

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--local-only',action='store_true');parser.add_argument('--phase4',action='store_true');parser.add_argument('--phase6',action='store_true');parser.add_argument('--output');args=parser.parse_args()
    if args.phase6 and not args.phase4: parser.error('--phase6 requires the existing --phase4 checks')
    keys=[v for k,v in dotenv_values(ROOT/'backend/.env').items() if k.endswith('API_KEY') and v and len(v)>=12]
    findings=[];count=0
    template_path=ROOT/'infra/cdk.out/HawaHawaiDev.template.json'
    current_asset=None
    if template_path.exists():
        template=json.loads(template_path.read_text())
        code=next(r['Properties']['Code'] for r in template['Resources'].values() if r['Type']=='AWS::Lambda::Function')
        current_asset='asset.'+code['S3Key'].removesuffix('.zip')
    for folder in ('agent','backend','frontend/src','frontend/dist','infra/lib','infra/bin','infra/cdk.out','contracts','scripts','.local/lambda-bundle' if args.phase4 else '.local/phase3-lambda-bundle'):
        for p in (ROOT/folder).rglob('*'):
            if folder=='infra/cdk.out' and any(part.startswith('asset.') and part!=current_asset for part in p.parts):continue
            if not p.is_file() or p.name.startswith('.env') or p.suffix not in {'.py','.ts','.tsx','.js','.json','.html','.css'}:continue
            data=p.read_text(encoding='utf-8',errors='replace');count+=1
            if any(k in data for k in keys) or re.search(r'AIza[\w-]{35}|gsk_[\w-]{32,}',data):findings.append(str(p.relative_to(ROOT)))
    assert not findings, 'Secret audit findings: '+str(findings)
    result={'files_checked':count,'secret_findings':[], 'known_key_values_checked':len(keys)}
    if not args.local_only:
        session=boto3.Session(profile_name='hawahawai',region_name='us-east-1')
        def client(service):return session.client(service,config=Config(connect_timeout=2,read_timeout=4,retries={'total_max_attempts':1}))
        assert client('sts').get_caller_identity()['Account']=='649437299529'
        cf=client('cloudformation');stack=cf.describe_stacks(StackName='HawaHawaiDev')['Stacks'][0]
        assert stack['StackStatus']=='UPDATE_COMPLETE'
        resources=cf.describe_stack_resources(StackName='HawaHawaiDev')['StackResources'];assert len(resources)==(35 if args.phase6 else 33 if args.phase4 else 26)
        function=client('lambda').get_function_configuration(FunctionName='hawahawai-dev-health')
        assert function['State']=='Active' and function['LastUpdateStatus']=='Successful'
        variables=function['Environment']['Variables']
        assert not any(k.endswith('API_KEY') for k in variables)
        assert variables['HAWAHAWAI_VERIFICATION_ENABLED']=='false'
        secret=variables['HAWAHAWAI_AI_SECRET_ARN'];assert ':secret:hawahawai-dev-ai-credentials-' in secret
        metadata=client('secretsmanager').describe_secret(SecretId=secret)
        assert metadata['Name']=='hawahawai-dev-ai-credentials'
        api=client('apigatewayv2');routes=api.get_routes(ApiId='pu8l3a213j')['Items'];assert len(routes)==(9 if args.phase4 else 8)
        assert all(r['RouteKey'].startswith('GET ') or r['RouteKey']=='POST /v1/schools/{school_id}/advisory' for r in routes)
        assert all('hawahawai-dev-health' in i['IntegrationUri'] for i in api.get_integrations(ApiId='pu8l3a213j')['Items'])
        table=client('dynamodb').describe_table(TableName='hawahawai-dev-environment-cache')['Table'];assert table['TableStatus']=='ACTIVE'
        simulation={};iam=client('iam')
        scopes=[('registry','regulatory#NCT_DELHI#current'),('advisory','delhi-demo-school#advisory#test')]
        if args.phase4:scopes.extend([('profile','school#delhi-demo-school#profile'),('verdict','delhi-demo-school#verdict#test'),('unrelated','ChugLi#not-owned')])
        for kind,leading in scopes:
            evaluations=iam.simulate_principal_policy(PolicySourceArn=function['Role'],ActionNames=['dynamodb:GetItem','dynamodb:PutItem','dynamodb:UpdateItem'],ResourceArns=[table['TableArn']],ContextEntries=[{'ContextKeyName':'dynamodb:LeadingKeys','ContextKeyValues':[leading],'ContextKeyType':'stringList'}])['EvaluationResults']
            simulation[kind]={e['EvalActionName']:e['EvalDecision'] for e in evaluations}
            assert simulation[kind]['dynamodb:GetItem']==('implicitDeny' if kind=='unrelated' else 'allowed')
            assert simulation[kind]['dynamodb:PutItem']==('allowed' if kind in {'advisory','verdict'} else 'implicitDeny')
            assert simulation[kind]['dynamodb:UpdateItem']==simulation[kind]['dynamodb:PutItem']
        for arn,expected in [(secret,'allowed'),('arn:aws:secretsmanager:us-east-1:649437299529:secret:ChugLi-not-owned-test','implicitDeny')]:
            evaluation=iam.simulate_principal_policy(PolicySourceArn=function['Role'],ActionNames=['secretsmanager:GetSecretValue'],ResourceArns=[arn])['EvaluationResults'][0]
            assert evaluation['EvalDecision']==expected
        # Assess the final deployed revision, while retaining earlier failure
        # evidence in the checkpoint rather than silently counting old faults as fixed.
        since=max(time.time()-900,min(stack['LastUpdatedTime'].timestamp(),datetime.fromisoformat(function['LastModified']).timestamp()))
        recent=client('logs').filter_log_events(logGroupName='hawahawai-dev-health-logs',startTime=int(since*1000),limit=500)['events']
        markers=('Traceback (most recent call last)','Task timed out','Status: timeout','[ERROR]','Runtime.ImportModuleError')
        errors=sum(any(m in e['message'] for m in markers) for e in recent)
        assert not errors, 'Own runtime errors require review'
        assert not any(any(k in e['message'] for k in keys) for e in recent)
        ai=[];memory=[];billed=[];duration=[];initialization=[]
        for entry in recent:
            message=entry['message']
            if 'REPORT RequestId:' in message:
                m=re.search(r'Max Memory Used: (\d+) MB',message)
                if m:memory.append(int(m.group(1)))
                m=re.search(r'Billed Duration: (\d+) ms',message)
                if m:billed.append(int(m.group(1)))
                m=re.search(r'\bDuration: ([\d.]+) ms',message)
                if m:duration.append(float(m.group(1)))
                m=re.search(r'Init Duration: ([\d.]+) ms',message)
                if m:initialization.append(float(m.group(1)))
            for marker in ('{"event": "ai_attempt"','{"event": "ai_usage"','{"event": "ai_response_shape"'):
                if marker in message:
                    try:ai.append(json.loads(message[message.index(marker):]))
                    except ValueError:pass
        result.update(stack_status=stack['StackStatus'],resource_count=len(resources),routes=[r['RouteKey'] for r in routes],lambda_memory_mb=function['MemorySize'],lambda_max_observed_mb=max(memory,default=None),
            lambda_observed_invocations=len(billed),lambda_billed_duration_ms=sum(billed),lambda_max_duration_ms=max(duration,default=None),lambda_max_init_ms=max(initialization,default=None),
            iam_simulation=simulation,secret_scope='one CDK-owned HawaHawai secret only',cloudwatch_errors=errors,log_window_start_epoch=since,ai_events=ai,new_service='None; static artifact update only' if args.phase6 else 'One daily EventBridge Scheduler; existing secret reused' if args.phase4 else 'Secrets Manager: one credential secret',billing_changed=False)
    output=(ROOT/args.output).resolve() if args.output else ROOT/('.local/phase4-audit.json' if args.phase4 else '.local/phase3-audit.json')
    assert output.is_relative_to(ROOT/'.local'), 'Audit output must remain in generated .local evidence'
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main()

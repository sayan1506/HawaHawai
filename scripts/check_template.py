"""Fail closed if synthesis includes unexpected/shared infrastructure."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bundle = ROOT / '.local/lambda-bundle'
for folder in ('backend/environmental', 'backend/safety', 'backend/advisory', 'backend/persistence', 'agent'):
    for source in (ROOT / folder).rglob('*'):
        if source.is_file() and '__pycache__' not in source.parts and source.suffix != '.pyc':
            relative = source.relative_to(ROOT / 'backend') if folder.startswith('backend/') else source.relative_to(ROOT)
            assert (bundle / relative).read_bytes() == source.read_bytes(), 'Stale Lambda bundle: ' + str(relative)
assert (bundle / 'app.py').read_bytes() == (ROOT / 'backend/app.py').read_bytes()
for name in ('openapi.json','school-profile.schema.json'):
    assert (bundle/'contracts'/name).read_bytes() == (ROOT/'contracts'/name).read_bytes(), 'Stale public contract'
template = json.loads((ROOT / "infra/cdk.out/HawaHawaiDev.template.json").read_text())
allowed = {"AWS::Logs::LogGroup", "AWS::IAM::Role", "AWS::IAM::Policy", "AWS::Lambda::Function", "AWS::Lambda::Permission", "AWS::ApiGatewayV2::Api", "AWS::ApiGatewayV2::Stage", "AWS::ApiGatewayV2::Integration", "AWS::ApiGatewayV2::Route", "AWS::DynamoDB::Table"}
allowed.add("AWS::SecretsManager::Secret")
allowed |= {'AWS::Scheduler::ScheduleGroup', 'AWS::Scheduler::Schedule'}
allowed.add('AWS::Lambda::EventInvokeConfig')
allowed |= {'AWS::Amplify::App', 'AWS::Amplify::Branch'}
for logical_id, resource in template["Resources"].items():
    assert resource["Type"] in allowed, logical_id
    props = resource["Properties"]
    for key in ("FunctionName", "RoleName", "PolicyName", "LogGroupName", "TableName", "Name"):
        if isinstance(props.get(key), str):
            assert props[key].startswith("hawahawai-"), (logical_id, key)
    if resource["Type"] == "AWS::Lambda::Function":
        assert set(props["Code"]) == {"S3Bucket", "S3Key"}
        assert props["Runtime"] == "python3.12"
        assert set(props["Environment"]["Variables"]) == {"HAWAHAWAI_ENV", "HAWAHAWAI_CACHE_TABLE", "HAWAHAWAI_SCHOOL_PROFILE_JSON", "HAWAHAWAI_VERIFICATION_ENABLED", "HAWAHAWAI_AI_SECRET_ARN", "HAWAHAWAI_AI_PROVIDER", "HAWAHAWAI_GEMINI_MODEL", "HAWAHAWAI_GROQ_MODEL", "HAWAHAWAI_PROFILE_STORAGE_REQUIRED", "HAWAHAWAI_DAILY_SCHEDULE_ARN"}
        assert props['Environment']['Variables']['HAWAHAWAI_PROFILE_STORAGE_REQUIRED']=='true'
        assert props['Environment']['Variables']['HAWAHAWAI_VERIFICATION_ENABLED']=='false'
    if resource["Type"] == "AWS::SecretsManager::Secret":
        assert logical_id == "AiCredentials" and props["Name"] == "hawahawai-dev-ai-credentials"
        assert "SecretString" not in props and "GenerateSecretString" not in props
    if resource["Type"] == "AWS::IAM::Policy":
        for statement in props["PolicyDocument"]["Statement"]:
            actions = statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]]
            assert set(actions) <= {"logs:CreateLogStream", "logs:PutLogEvents", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "secretsmanager:GetSecretValue", "lambda:InvokeFunction"}
            assert statement["Resource"] != "*"
            if "secretsmanager:GetSecretValue" in actions:
                assert actions == ["secretsmanager:GetSecretValue"] and statement["Resource"] == {"Ref": "AiCredentials"}
            else:
                assert template["Resources"][statement["Resource"]["Fn::GetAtt"][0]]["Type"] in {"AWS::DynamoDB::Table", "AWS::Logs::LogGroup", "AWS::Lambda::Function"}
            if set(actions) & {"dynamodb:PutItem", "dynamodb:UpdateItem"}:
                school = json.loads((ROOT / "contracts/demo-school.json").read_text())
                assert statement["Condition"] == {"ForAllValues:StringLike": {"dynamodb:LeadingKeys": [school["school_id"]+'#????????????#*',school["school_id"]+'#advisory#*',school["school_id"]+'#verdict#*']}}
            if 'dynamodb:GetItem' in actions:
                assert len(statement['Condition']['ForAllValues:StringLike']['dynamodb:LeadingKeys'])==5
            if actions==['lambda:InvokeFunction']:
                assert logical_id.startswith('PlanningRole')
    if resource['Type']=='AWS::Scheduler::Schedule':
        assert props['Name']=='hawahawai-dev-daily-verdict' and props['ScheduleExpressionTimezone']=='Asia/Kolkata'
        assert props['FlexibleTimeWindow']=={'Mode':'OFF'} and props['State']=='ENABLED'
        assert props['Target']['RetryPolicy']=={'MaximumEventAgeInSeconds':900,'MaximumRetryAttempts':1}
        assert json.loads(props['Target']['Input'])=={'job':'hawahawai.daily-verdict.v1','school_id':'delhi-demo-school','schedule_arn':'<aws.scheduler.schedule-arn>','scheduled_time':'<aws.scheduler.scheduled-time>'}
assert "ChugLi" not in json.dumps(template)
assert "AWS::CloudFormation::Stack" not in json.dumps(template)
assert sum(r['Type'] == 'AWS::DynamoDB::Table' for r in template['Resources'].values()) == 1
assert sum(r['Type'] == 'AWS::Lambda::Function' for r in template['Resources'].values()) == 1
assert sum(r['Type'] == 'AWS::ApiGatewayV2::Route' for r in template['Resources'].values()) == 9
assert sum(r['Type'] == 'AWS::SecretsManager::Secret' for r in template['Resources'].values()) == 1
for asset in (ROOT / 'infra/cdk.out').glob('asset.*'):
    if asset.is_dir():
        assert not any(p.name.startswith('.env') or p.suffix == '.pyc' for p in asset.rglob('*'))
assert sum(r['Type']=='AWS::Scheduler::Schedule' for r in template['Resources'].values())==1
async_config = [r['Properties'] for r in template['Resources'].values() if r['Type']=='AWS::Lambda::EventInvokeConfig']
assert len(async_config)==1 and async_config[0]['Qualifier']=='$LATEST'
assert async_config[0]['MaximumRetryAttempts']==1 and async_config[0]['MaximumEventAgeInSeconds']==900
assert template['Resources'][async_config[0]['FunctionName']['Ref']]['Type']=='AWS::Lambda::Function'
app = template['Resources']['WebApp']
assert app['Type']=='AWS::Amplify::App' and app['Properties']['Name']=='hawahawai-dev-web'
assert app['Properties']['Platform']=='WEB'
assert not set(app['Properties']) & {'Repository','AccessToken','OauthToken','IAMServiceRole','ComputeRoleArn'}
branch = template['Resources']['WebProduction']['Properties']
assert branch['AppId']=={'Fn::GetAtt':['WebApp','AppId']} and branch['BranchName']=='production'
assert branch['EnableAutoBuild'] is False and branch['EnablePullRequestPreview'] is False
api = next(r['Properties'] for r in template['Resources'].values() if r['Type']=='AWS::ApiGatewayV2::Api')
origins = api['CorsConfiguration']['AllowOrigins']
assert len(origins)==5 and '*' not in origins
assert origins[-1]=={'Fn::Join':['',['https://production.',{'Fn::GetAtt':['WebApp','DefaultDomain']}]]}
assert set(api['CorsConfiguration']['AllowMethods'])=={'GET','POST'}
assert sum(r['Type']=='AWS::Amplify::App' for r in template['Resources'].values())==1
assert sum(r['Type']=='AWS::Amplify::Branch' for r in template['Resources'].values())==1
assert len(template['Resources'])==35
print("PASS: preserved Phase 4 resources/security, one static Amplify app/branch and exact-origin CORS")

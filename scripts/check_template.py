"""Fail closed if synthesis includes unexpected/shared infrastructure."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bundle = ROOT / '.local/phase3-lambda-bundle'
for folder in ('backend/environmental', 'backend/safety', 'backend/advisory', 'agent'):
    for source in (ROOT / folder).rglob('*'):
        if source.is_file() and '__pycache__' not in source.parts and source.suffix != '.pyc':
            relative = source.relative_to(ROOT / 'backend') if folder.startswith('backend/') else source.relative_to(ROOT)
            assert (bundle / relative).read_bytes() == source.read_bytes(), 'Stale Lambda bundle: ' + str(relative)
assert (bundle / 'app.py').read_bytes() == (ROOT / 'backend/app.py').read_bytes()
template = json.loads((ROOT / "infra/cdk.out/HawaHawaiDev.template.json").read_text())
allowed = {"AWS::Logs::LogGroup", "AWS::IAM::Role", "AWS::IAM::Policy", "AWS::Lambda::Function", "AWS::Lambda::Permission", "AWS::ApiGatewayV2::Api", "AWS::ApiGatewayV2::Stage", "AWS::ApiGatewayV2::Integration", "AWS::ApiGatewayV2::Route", "AWS::DynamoDB::Table"}
allowed.add("AWS::SecretsManager::Secret")
for logical_id, resource in template["Resources"].items():
    assert resource["Type"] in allowed, logical_id
    props = resource["Properties"]
    for key in ("FunctionName", "RoleName", "PolicyName", "LogGroupName", "TableName", "Name"):
        if isinstance(props.get(key), str):
            assert props[key].startswith("hawahawai-"), (logical_id, key)
    if resource["Type"] == "AWS::Lambda::Function":
        assert set(props["Code"]) == {"S3Bucket", "S3Key"}
        assert props["Runtime"] == "python3.12"
        assert set(props["Environment"]["Variables"]) == {"HAWAHAWAI_ENV", "HAWAHAWAI_CACHE_TABLE", "HAWAHAWAI_SCHOOL_PROFILE_JSON", "HAWAHAWAI_VERIFICATION_ENABLED", "HAWAHAWAI_AI_SECRET_ARN", "HAWAHAWAI_AI_PROVIDER", "HAWAHAWAI_GEMINI_MODEL", "HAWAHAWAI_GROQ_MODEL"}
    if resource["Type"] == "AWS::SecretsManager::Secret":
        assert logical_id == "AiCredentials" and props["Name"] == "hawahawai-dev-ai-credentials"
        assert "SecretString" not in props and "GenerateSecretString" not in props
    if resource["Type"] == "AWS::IAM::Policy":
        for statement in props["PolicyDocument"]["Statement"]:
            actions = statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]]
            assert set(actions) <= {"logs:CreateLogStream", "logs:PutLogEvents", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "secretsmanager:GetSecretValue"}
            assert statement["Resource"] != "*"
            if "secretsmanager:GetSecretValue" in actions:
                assert actions == ["secretsmanager:GetSecretValue"] and statement["Resource"] == {"Ref": "AiCredentials"}
            else:
                assert template["Resources"][statement["Resource"]["Fn::GetAtt"][0]]["Type"] in {"AWS::DynamoDB::Table", "AWS::Logs::LogGroup"}
            if set(actions) & {"dynamodb:PutItem", "dynamodb:UpdateItem"}:
                school = json.loads((ROOT / "contracts/demo-school.json").read_text())
                assert statement["Condition"] == {"ForAllValues:StringLike": {"dynamodb:LeadingKeys": [school["school_id"] + "#*"]}}
assert "ChugLi" not in json.dumps(template)
assert "AWS::CloudFormation::Stack" not in json.dumps(template)
assert sum(r['Type'] == 'AWS::DynamoDB::Table' for r in template['Resources'].values()) == 1
assert sum(r['Type'] == 'AWS::Lambda::Function' for r in template['Resources'].values()) == 1
assert sum(r['Type'] == 'AWS::ApiGatewayV2::Route' for r in template['Resources'].values()) == 8
assert sum(r['Type'] == 'AWS::SecretsManager::Secret' for r in template['Resources'].values()) == 1
for asset in (ROOT / 'infra/cdk.out').glob('asset.*'):
    if asset.is_dir():
        assert not any(p.name.startswith('.env') or p.suffix == '.pyc' for p in asset.rglob('*'))
print("PASS: scoped Phase 3 routes, single owned credential secret, registry read-only IAM and secret-free assets")

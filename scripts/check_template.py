"""Fail closed if synthesis includes unexpected/shared infrastructure."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
template = json.loads((ROOT / "infra/cdk.out/HawaHawaiDev.template.json").read_text())
allowed = {"AWS::Logs::LogGroup", "AWS::IAM::Role", "AWS::IAM::Policy", "AWS::Lambda::Function", "AWS::Lambda::Permission", "AWS::ApiGatewayV2::Api", "AWS::ApiGatewayV2::Stage", "AWS::ApiGatewayV2::Integration", "AWS::ApiGatewayV2::Route", "AWS::DynamoDB::Table"}
for logical_id, resource in template["Resources"].items():
    assert resource["Type"] in allowed, logical_id
    props = resource["Properties"]
    for key in ("FunctionName", "RoleName", "PolicyName", "LogGroupName", "TableName", "Name"):
        if isinstance(props.get(key), str):
            assert props[key].startswith("hawahawai-"), (logical_id, key)
    if resource["Type"] == "AWS::Lambda::Function":
        assert set(props["Code"]) == {"S3Bucket", "S3Key"}
        assert props["Runtime"] == "python3.12"
        assert set(props["Environment"]["Variables"]) == {"HAWAHAWAI_ENV", "HAWAHAWAI_CACHE_TABLE", "HAWAHAWAI_SCHOOL_PROFILE_JSON", "HAWAHAWAI_VERIFICATION_ENABLED"}
    if resource["Type"] == "AWS::IAM::Policy":
        for statement in props["PolicyDocument"]["Statement"]:
            actions = statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]]
            assert set(actions) <= {"logs:CreateLogStream", "logs:PutLogEvents", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"}
            assert statement["Resource"] != "*"
            assert template["Resources"][statement["Resource"]["Fn::GetAtt"][0]]["Type"] in {"AWS::DynamoDB::Table", "AWS::Logs::LogGroup"}
            if set(actions) & {"dynamodb:PutItem", "dynamodb:UpdateItem"}:
                school = json.loads((ROOT / "contracts/demo-school.json").read_text())
                assert statement["Condition"] == {"ForAllValues:StringLike": {"dynamodb:LeadingKeys": [school["school_id"] + "#*"]}}
assert "ChugLi" not in json.dumps(template)
assert "AWS::CloudFormation::Stack" not in json.dumps(template)
assert sum(r['Type'] == 'AWS::DynamoDB::Table' for r in template['Resources'].values()) == 1
assert sum(r['Type'] == 'AWS::Lambda::Function' for r in template['Resources'].values()) == 1
assert sum(r['Type'] == 'AWS::ApiGatewayV2::Route' for r in template['Resources'].values()) == 6
for asset in (ROOT / 'infra/cdk.out').glob('asset.*'):
    if asset.is_dir():
        assert not any(p.name.startswith('.env') or p.suffix == '.pyc' for p in asset.rglob('*'))
print("PASS: scoped Phase 2 routes, registry read-only runtime IAM and secret-free assets")

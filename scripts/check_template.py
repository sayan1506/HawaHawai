"""Fail closed if Phase 0 synthesis includes unexpected/shared infrastructure."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
template = json.loads((ROOT / "infra/cdk.out/HawaHawaiDev.template.json").read_text())
allowed = {"AWS::Logs::LogGroup", "AWS::IAM::Role", "AWS::IAM::Policy", "AWS::Lambda::Function", "AWS::Lambda::Permission", "AWS::ApiGatewayV2::Api", "AWS::ApiGatewayV2::Stage", "AWS::ApiGatewayV2::Integration", "AWS::ApiGatewayV2::Route"}
assert len(template["Resources"]) == 9
for logical_id, resource in template["Resources"].items():
    assert resource["Type"] in allowed, logical_id
    props = resource["Properties"]
    for key in ("FunctionName", "RoleName", "PolicyName", "LogGroupName", "Name"):
        if isinstance(props.get(key), str):
            assert props[key].startswith("hawahawai-"), (logical_id, key)
    if resource["Type"] == "AWS::Lambda::Function":
        assert set(props["Code"]) == {"ZipFile"}, "Bootstrap assets are forbidden in Phase 0"
        assert props["Runtime"] == "python3.12"
        assert props["Environment"]["Variables"] == {"HAWAHAWAI_ENV": "dev"}
    if resource["Type"] == "AWS::IAM::Policy":
        for statement in props["PolicyDocument"]["Statement"]:
            assert set(statement["Action"]) <= {"logs:CreateLogStream", "logs:PutLogEvents"}
            assert statement["Resource"] == {"Fn::GetAtt": ["HealthLogs34B37038", "Arn"]}
assert "ChugLi" not in json.dumps(template)
assert "AWS::CloudFormation::Stack" not in json.dumps(template)
print("PASS: nine scoped Phase 0 resources; names, inline Lambda, and logging-only IAM verified")

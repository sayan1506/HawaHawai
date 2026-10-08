"""Scoped readback and IAM simulation, never registry mutation or billing changes."""
import json
import sys
import time
from pathlib import Path
import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from environmental.cache import decode_payload
from safety.registry import validate_snapshot


def main():
    session = boto3.Session(profile_name="hawahawai", region_name="us-east-1")
    config = Config(connect_timeout=2, read_timeout=5, retries={"total_max_attempts": 1})
    client = lambda name: session.client(name, config=config)
    assert client("sts").get_caller_identity()["Account"] == "649437299529"
    cf = client("cloudformation")
    stack = cf.describe_stacks(StackName="HawaHawaiDev")["Stacks"][0]
    assert stack["StackStatus"] == "UPDATE_COMPLETE"
    resources = cf.describe_stack_resources(StackName="HawaHawaiDev")["StackResources"]
    assert len(resources) == 21
    function = client("lambda").get_function_configuration(FunctionName="hawahawai-dev-health")
    assert function["State"] == "Active" and function["LastUpdateStatus"] == "Successful"
    assert function["Environment"]["Variables"]["HAWAHAWAI_VERIFICATION_ENABLED"] == "false"
    assert not any("KEY" in name or "SECRET" in name for name in function["Environment"]["Variables"])
    api = client("apigatewayv2")
    routes = api.get_routes(ApiId="pu8l3a213j")["Items"]
    integrations = api.get_integrations(ApiId="pu8l3a213j")["Items"]
    assert len(routes) == 6 and all(r["RouteKey"].startswith("GET ") for r in routes)
    assert all("hawahawai-dev-health" in integration["IntegrationUri"] for integration in integrations)
    dynamo = client("dynamodb")
    table = dynamo.describe_table(TableName="hawahawai-dev-environment-cache")["Table"]
    assert table["TableStatus"] == "ACTIVE"
    registry = {}
    pointer_key = "regulatory#NCT_DELHI#current"
    pointer = dynamo.get_item(TableName=table["TableName"], Key={"cache_key": {"S": pointer_key}}, ConsistentRead=True)["Item"]
    current_version = decode_payload(pointer["payload"]["S"])["version"]
    for key in (pointer_key, "regulatory#NCT_DELHI#version#" + current_version):
        item = dynamo.get_item(TableName=table["TableName"], Key={"cache_key": {"S": key}}, ConsistentRead=True, ReturnConsumedCapacity="TOTAL")
        assert "expires_at" not in item["Item"]
        payload = decode_payload(item["Item"]["payload"]["S"])
        if "documents" in payload:
            validate_snapshot(payload)
            assert payload["verification"] is None and not payload["simulation"] and not payload["events"]
        registry[key] = {"no_ttl": True, "read_units": item["ConsumedCapacity"]["CapacityUnits"]}
    iam, simulated = client("iam"), {}
    policy = iam.get_role_policy(RoleName="hawahawai-dev-health-role", PolicyName="hawahawai-dev-health-logs")["PolicyDocument"]
    for kind, leading_key in (("registry", "regulatory#NCT_DELHI#current"), ("environment", "delhi-demo-school#example#current")):
        evaluations = iam.simulate_principal_policy(PolicySourceArn=function["Role"], ActionNames=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"], ResourceArns=[table["TableArn"]], ContextEntries=[{"ContextKeyName": "dynamodb:LeadingKeys", "ContextKeyValues": [leading_key], "ContextKeyType": "stringList"}])["EvaluationResults"]
        simulated[kind] = {e["EvalActionName"]: e["EvalDecision"] for e in evaluations}
        assert simulated[kind]["dynamodb:GetItem"] == "allowed"
        for action in ("dynamodb:PutItem", "dynamodb:UpdateItem"):
            assert simulated[kind][action] == ("implicitDeny" if kind == "registry" else "allowed")
    # Scoped recent runtime evidence; do not print request bodies or raw logs.
    recent = client("logs").filter_log_events(logGroupName="hawahawai-dev-health-logs", startTime=int((time.time() - 900) * 1000), limit=500)["events"]
    markers = ("Traceback (most recent call last)", "Task timed out", "[ERROR]", "Runtime.ImportModuleError", '"event": "environmental_cache_error"')
    runtime_errors = sum(any(marker in event["message"] for marker in markers) for event in recent)
    log_summary = {"window_seconds": 900, "events_read": len(recent), "lambda_reports": sum("REPORT RequestId:" in event["message"] for event in recent), "runtime_errors": runtime_errors}
    assert runtime_errors == 0, "Recent own Lambda runtime errors require investigation"
    result = {"stack_status": stack["StackStatus"], "resource_count": len(resources), "resources": [{"logical_id": r["LogicalResourceId"], "physical_id": r["PhysicalResourceId"], "type": r["ResourceType"]} for r in resources],
        "routes": [r["RouteKey"] for r in routes], "lambda": {"state": function["State"], "update": function["LastUpdateStatus"], "memory_mb": function["MemorySize"], "timeout_seconds": function["Timeout"]},
        "iam_simulation": simulated, "runtime_policy": policy, "registry": registry, "verification_enabled": False,
        "new_billable_services": [], "billing_configuration_changed": False, "cloudwatch": log_summary}
    (ROOT / ".local/phase2-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("stack_status", "resource_count", "routes", "iam_simulation", "registry", "new_billable_services", "cloudwatch")}))


if __name__ == "__main__":
    main()

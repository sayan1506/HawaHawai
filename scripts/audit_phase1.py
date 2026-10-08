"""Secret-safe local source/asset audit and scoped AWS readback."""
import json
import argparse
import re
import sys
from pathlib import Path
import boto3
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from environmental.service import cache_prefix


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-only", action="store_true")
    args = parser.parse_args()
    secrets = [v for k, v in dotenv_values(ROOT / "backend/.env").items() if k.endswith("API_KEY") and v and len(v) >= 12]
    findings, checked = [], 0
    for folder in ("backend", "frontend/src", "frontend/dist", "infra/lib", "infra/bin", "infra/cdk.out", "contracts", "scripts"):
        for path in (ROOT / folder).rglob("*"):
            if not path.is_file() or path.name.startswith(".env") or path.suffix not in {".py", ".js", ".ts", ".tsx", ".json", ".html", ".css"}:
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            checked += 1
            if any(secret in content for secret in secrets) or re.search(r"AIza[\w-]{35}|gsk_[\w-]{32,}", content):
                findings.append(str(path.relative_to(ROOT)))
    assert not findings, "Potential secret exposure in files: " + ", ".join(findings)
    if args.local_only:
        print(json.dumps({"files_checked": checked, "findings": [], "known_key_values_checked": len(secrets)}))
        return
    session = boto3.Session(profile_name="hawahawai", region_name="us-east-1")
    assert session.client("sts").get_caller_identity()["Account"] == "649437299529"
    cf = session.client("cloudformation")
    stack = cf.describe_stacks(StackName="HawaHawaiDev")["Stacks"][0]
    resources = cf.describe_stack_resources(StackName="HawaHawaiDev")["StackResources"]
    function = session.client("lambda").get_function_configuration(FunctionName="hawahawai-dev-health")
    assert function["State"] == "Active" and function["LastUpdateStatus"] == "Successful"
    assert function["Environment"]["Variables"].get("HAWAHAWAI_VERIFICATION_ENABLED") == "false"
    api = session.client("apigatewayv2")
    routes = api.get_routes(ApiId="pu8l3a213j")["Items"]
    integrations = api.get_integrations(ApiId="pu8l3a213j")["Items"]
    assert len(routes) == 4 and all("hawahawai-dev-health" in i["IntegrationUri"] for i in integrations)
    dynamo = session.client("dynamodb")
    table_name = "hawahawai-dev-environment-cache"
    table = dynamo.describe_table(TableName=table_name)["Table"]
    ttl = dynamo.describe_time_to_live(TableName=table_name)["TimeToLiveDescription"]
    assert table["TableStatus"] == "ACTIVE" and ttl["TimeToLiveStatus"] in {"ENABLED", "ENABLING"}
    school = json.loads((ROOT / "contracts/demo-school.json").read_text())
    prefix = cache_prefix(school)
    records = {}
    for part in ("current", "forecast", "observations", "cooldown", "lock"):
        result = dynamo.get_item(TableName=table_name, Key={"cache_key": {"S": prefix + "#" + part}}, ConsistentRead=True, ReturnConsumedCapacity="TOTAL")
        item = result.get("Item")
        records[part] = {"present": bool(item), "payload_bytes": len(item.get("payload", {}).get("S", "").encode()) if item else 0, "read_capacity_units": result["ConsumedCapacity"]["CapacityUnits"]}
    fault = dynamo.get_item(TableName=table_name, Key={"cache_key": {"S": "verification#" + school["school_id"]}}, ConsistentRead=True).get("Item")
    assert not fault, "Verification control was not removed"
    assert records["current"]["present"] and records["forecast"]["present"] and not records["cooldown"]["present"]
    result = {"source_asset_secret_scan": {"files_checked": checked, "known_key_values_checked": len(secrets), "findings": findings}, "stack_status": stack["StackStatus"], "resource_count": len(resources), "resources": [{"logical_id": r["LogicalResourceId"], "type": r["ResourceType"], "physical_id": r["PhysicalResourceId"]} for r in resources], "lambda": {"state": function["State"], "last_update_status": function["LastUpdateStatus"], "timeout": function["Timeout"], "memory_mb": function["MemorySize"], "verification_enabled": False}, "routes": [r["RouteKey"] for r in routes], "cache": records, "ttl": ttl, "private_fault_control_absent": True}
    (ROOT / ".local/phase1-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"files_checked": checked, "findings": [], "stack_status": result["stack_status"], "resources": len(resources), "private_fault_control_absent": True, "cache": records}))


if __name__ == "__main__":
    main()

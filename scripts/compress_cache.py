"""One-shot, conditional compression of the two identified HawaHawai cache items.

Only run after deploying the backward-compatible cache decoder. Original payloads
are generated evidence in .local; timestamps, TTL and normalized values are kept.
"""
import json
import sys
from pathlib import Path
import boto3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from environmental.cache import encode_payload, decode_payload
from environmental.service import cache_prefix


def main():
    session = boto3.Session(profile_name="hawahawai", region_name="us-east-1")
    assert session.client("sts").get_caller_identity()["Account"] == "649437299529"
    function = session.client("lambda").get_function_configuration(FunctionName="hawahawai-dev-health")
    assert function["LastUpdateStatus"] == "Successful" and function["Environment"]["Variables"]["HAWAHAWAI_VERIFICATION_ENABLED"] == "false"
    client = session.client("dynamodb")
    table = "hawahawai-dev-environment-cache"
    prefix = cache_prefix(json.loads((ROOT / "contracts/demo-school.json").read_text()))
    originals, results = {}, {}
    for part in ("current", "forecast"):
        key = prefix + "#" + part
        item = client.get_item(TableName=table, Key={"cache_key": {"S": key}}, ConsistentRead=True)["Item"]
        before = item["payload"]["S"]
        after = encode_payload(decode_payload(before))
        originals[key] = item
        (ROOT / ".local/phase1-cache-compression-before.json").write_text(json.dumps(originals, indent=2) + "\n", encoding="utf-8")
        if before != after:
            client.update_item(TableName=table, Key={"cache_key": {"S": key}}, UpdateExpression="SET payload=:new", ConditionExpression="payload=:old", ExpressionAttributeValues={":new": {"S": after}, ":old": {"S": before}})
        results[part] = {"bytes_before": len(before.encode()), "bytes_after": len(after.encode()), "values_and_timestamps_preserved": decode_payload(after) == decode_payload(before)}
    (ROOT / ".local/phase1-cache-compression.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results))


if __name__ == "__main__":
    main()

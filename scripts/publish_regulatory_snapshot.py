"""Controlled local admin workflow; NEVER imported by the public Lambda.

Preview is default. --write publishes immutable version + atomic current pointer
only in the HawaHawai table. Reviewed originals and an explicit human attestation
are required; tests/simulations are never publishable. No IAM changes are made.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from safety.registry import DATA, ATTESTATION, resolve, validate_snapshot
from safety.models import ActivityContext, instant
from environmental.cache import encode_payload, decode_payload

TABLE = "hawahawai-dev-environment-cache"
PREFIX = "regulatory#NCT_DELHI#"


def review_originals(snapshot, originals, operator, attestation, evaluation_time):
    checked = validate_snapshot(snapshot, publish=True)
    now = instant(evaluation_time)
    verification = checked["verification"]
    if operator != verification["operator_id"] or attestation != ATTESTATION:
        raise ValueError("Human operator and explicit attestation must match the recorded review")
    if not instant(verification["verified_at"]) <= now < instant(verification["expires_at"]):
        raise ValueError("Verification must be current at publication")
    originals = Path(originals).resolve()
    for doc in checked["documents"]:
        # Fixed safe filename; no path from a URL or public request is followed.
        if not re.fullmatch(r"[a-zA-Z0-9._-]{1,100}", doc["document_id"]):
            raise ValueError("Invalid original-document filename")
        path = (originals / (doc["document_id"] + ".pdf")).resolve()
        if path.parent != originals or not path.is_file():
            raise ValueError("Reviewed original PDF is missing")
        content = path.read_bytes()
        if not content.startswith(b"%PDF-") or len(content) > 12_000_000 or hashlib.sha256(content).hexdigest() != doc["sha256"]:
            raise ValueError("Original document is not the recorded PDF")
    result = resolve(checked, now, ActivityContext())
    if result["verification_state"] == "CONFLICTING":
        raise ValueError("Resolve conflicting regulatory events before publishing")
    return checked


def publish(client, snapshot):
    version_key, pointer_key = PREFIX + "version#" + snapshot["version"], PREFIX + "current"
    current = client.get_item(TableName=TABLE, Key={"cache_key": {"S": pointer_key}}, ConsistentRead=True).get("Item")
    version = {"Put": {"TableName": TABLE, "Item": {"cache_key": {"S": version_key}, "payload": {"S": encode_payload(snapshot)}}, "ConditionExpression": "attribute_not_exists(cache_key)"}}
    pointer = {"TableName": TABLE, "Item": {"cache_key": {"S": pointer_key}, "payload": {"S": encode_payload({"version": snapshot["version"]})}}, "ConditionExpression": "attribute_not_exists(cache_key)"}
    if current:
        pointer["ConditionExpression"] = "payload = :previous"
        pointer["ExpressionAttributeValues"] = {":previous": current["payload"]}
    # No expires_at: regulatory history must not be deleted by cache TTL.
    client.transact_write_items(TransactItems=[version, {"Put": pointer}])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", nargs="?")
    parser.add_argument("--research-only", action="store_true", help="Publish only the packaged UNKNOWN research snapshot, with no verified claims")
    parser.add_argument("--originals")
    parser.add_argument("--operator")
    parser.add_argument("--attestation", help="Exact ATTESTATION from safety.registry; must be a real human review, not an automated action")
    parser.add_argument("--write", action="store_true", help="Explicitly publish; otherwise validate and preview only")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.research_only:
        if args.snapshot or args.operator or args.attestation or args.originals:
            parser.error("Research publication cannot be combined with verification arguments")
        snapshot = validate_snapshot(json.loads((DATA / "regulatory-research-v2.json").read_text()))
        assert snapshot["verification"] is None and not snapshot["events"] and not snapshot["restrictions"]
    else:
        if not all((args.snapshot, args.originals, args.operator, args.attestation)):
            parser.error("A real reviewed snapshot, originals, operator and attestation are required")
        snapshot = review_originals(json.loads(Path(args.snapshot).read_text(encoding="utf-8")), args.originals, args.operator, args.attestation, now)
    result = resolve(snapshot, now, ActivityContext())
    if args.write:
        session = boto3.Session(profile_name="hawahawai", region_name="us-east-1")
        config = Config(connect_timeout=2, read_timeout=5, retries={"total_max_attempts": 1})
        assert session.client("sts", config=config).get_caller_identity()["Account"] == "649437299529"
        client = session.client("dynamodb", config=config)
        assert client.describe_table(TableName=TABLE)["Table"]["TableStatus"] == "ACTIVE"
        publish(client, snapshot)
    print(json.dumps({"written": args.write, "snapshot_version": snapshot["version"], "regulatory_state": result["verification_state"], "human_verification_recorded": snapshot["verification"] is not None, "table": TABLE, "ttl": "none"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never print SDK/provider exception bodies or credentials.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)

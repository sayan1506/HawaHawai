"""Bounded deployed E2E checks; private controlled faults never invent readings.

--faults requires temporary verification-enabled HawaHawai deployment. Exact own
cache items are restored in finally. No scans, unrelated resources or secrets.
"""
import argparse
import copy
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import boto3
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from environmental.service import cache_prefix
from environmental.cache import encode_payload, decode_payload

BASE = "https://pu8l3a213j.execute-api.us-east-1.amazonaws.com"
TABLE = "hawahawai-dev-environment-cache"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--faults", action="store_true")
    parser.add_argument("--browser-hold", action="store_true", help="Pause controlled scenarios for browser verification; press Enter to continue")
    args = parser.parse_args()
    school = json.loads((ROOT / "contracts/demo-school.json").read_text())
    document = json.loads((ROOT / "contracts/openapi.json").read_text())
    session = boto3.Session(profile_name="hawahawai", region_name="us-east-1")
    assert session.client("sts").get_caller_identity()["Account"] == "649437299529"
    client = session.client("dynamodb")
    prefix = cache_prefix(school)
    path = f'/v1/schools/{school["school_id"]}'
    evidence = {"checked_at": datetime.now(timezone.utc).isoformat(), "mode": "controlled_faults" if args.faults else "final_live", "checks": {}, "responses": {}}

    def call(suffix, schema=None, expected=200, origin=None):
        request = Request(BASE + suffix, headers={"Origin": origin} if origin else {})
        try:
            response = urlopen(request, timeout=28)
        except HTTPError as error:
            response = error
        with response:
            code, headers, body = response.status, dict(response.headers), json.load(response)
        assert code == expected, (suffix, code, body.get("error"), body.get("warnings"))
        if schema:
            Draft202012Validator({**document, "$ref": f"#/components/schemas/{schema}"}, format_checker=FormatChecker()).validate(body)
        return body, {k.lower(): v for k, v in headers.items()}

    health, _ = call("/health", "Health")
    assert health["phase"] == 0
    evidence["checks"]["health_regression"] = True
    profile, _ = call(path, "SchoolProfile")
    assert profile == school
    air, headers = call(path + "/air", "AirReading", origin="http://127.0.0.1:5173")
    assert headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
    with urlopen(Request(BASE + path + "/air", method="OPTIONS", headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "content-type"}), timeout=10) as preflight:
        assert preflight.status == 204 and preflight.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:5173"
    assert air["observations"] == [] and all(p["status"] == "unavailable" for p in air["observation_providers"])
    assert air["modeled_current"] and air["pollutants"]
    assert all(p["observed_at"] is None and p["source_type"] == "model_forecast" and p["unit"] == "ug/m3" for p in air["pollutants"])
    assert all(a["scale"] == "US_AQI" for a in air["aqi"])
    evidence["checks"].update({"configured_school": True, "real_modeled_current": True, "official_observations_missing": True, "units_and_scale": True, "cors_get": True, "cors_preflight": True})
    forecast, _ = call(path + "/forecast", "Forecast")
    assert len(forecast["points"]) == 48
    times = [datetime.fromisoformat(p["valid_at"]).timestamp() for p in forecast["points"]]
    assert times[0] >= time.time() - 20 and all(b - a == 3600 for a, b in zip(times, times[1:]))
    assert forecast["generated_at"] is None
    second, _ = call(path + "/forecast", "Forecast")
    assert second["cache"]["status"] == "hit" and second["retrieved_at"] == forecast["retrieved_at"]
    assert second["points"] == forecast["points"]
    evidence["checks"].update({"dated_48_hour_forecast": True, "cache_hit": True})
    call(path + "/air?latitude=91&longitude=77", expected=400)
    call(path + "/air?latitude=bad&longitude=77", expected=400)
    call("/v1/schools/unknown/air", expected=404)
    call("/v1/grap", expected=404)
    evidence["checks"].update({"invalid_coordinates": True, "unknown_school": True, "no_phase2_routes": True})
    evidence["responses"].update({"air": air, "forecast": forecast})
    if args.faults:
        environment = session.client("lambda").get_function_configuration(FunctionName="hawahawai-dev-health")["Environment"]["Variables"]
        assert environment.get("HAWAHAWAI_VERIFICATION_ENABLED") == "true"
        keys = [prefix + "#" + part for part in ("current", "forecast", "observations", "cooldown", "lock")] + ["verification#" + school["school_id"]]

        def get(key):
            return client.get_item(TableName=TABLE, Key={"cache_key": {"S": key}}, ConsistentRead=True).get("Item")

        def put(key, payload):
            client.put_item(TableName=TABLE, Item={"cache_key": {"S": key}, "payload": {"S": encode_payload(payload)}, "expires_at": {"N": str(int(time.time()) + 600)}})

        def remove(key):
            client.delete_item(TableName=TABLE, Key={"cache_key": {"S": key}})

        backup = {key: get(key) for key in keys}
        try:
            for fault in ("TIMEOUT", "RATE_LIMITED"):
                item = decode_payload(backup[prefix + "#forecast"]["payload"]["S"])
                item["fresh_until"] = time.time() - 1
                put(prefix + "#forecast", item)
                remove(prefix + "#cooldown")
                put(keys[-1], {"code": fault, "until": time.time() + 300})
                stale, _ = call(path + "/forecast", "Forecast")
                assert stale["status"] == "stale" and stale["freshness_status"] == "stale"
                assert stale["retrieved_at"] == forecast["retrieved_at"] and stale["points"] == forecast["points"]
                assert "LIVE_REFRESH_FAILED: VERIFICATION_" + fault in stale["warnings"]
                repeated, _ = call(path + "/forecast", "Forecast")
                assert repeated["status"] == "stale"
                evidence["checks"]["deployed_controlled_" + fault.lower() + "_stale_fallback"] = True
                evidence["responses"][fault.lower()] = stale
                if args.browser_hold and fault == "TIMEOUT":
                    input("Controlled stale fallback active. Verify browser display, then press Enter: ")
            item["fetched_at"] = time.time() - 21601
            put(prefix + "#forecast", item)
            missing, _ = call(path + "/forecast", "Forecast", expected=503)
            assert missing["points"] == [] and missing["status"] == "unavailable"
            evidence["checks"]["deployed_expired_data_no_fabrication"] = True
            evidence["responses"]["expired"] = missing
            if args.browser_hold:
                input("Controlled missing forecast active. Verify browser display, then press Enter: ")
        finally:
            for key, item in backup.items():
                if item:
                    client.put_item(TableName=TABLE, Item=item)
                else:
                    remove(key)
        evidence["checks"]["cache_items_restored_and_fault_control_removed"] = get(keys[-1]) == backup[keys[-1]]
    else:
        assert session.client("lambda").get_function_configuration(FunctionName="hawahawai-dev-health")["Environment"]["Variables"].get("HAWAHAWAI_VERIFICATION_ENABLED") == "false"
        evidence["checks"]["verification_disabled_final_deployment"] = True
    target = ROOT / (".local/phase1-controlled-e2e.json" if args.faults else ".local/phase1-live-e2e.json")
    target.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checks": evidence["checks"], "source": air["sources"][0]["name"], "retrieved_at": air["retrieved_at"], "forecast_start": forecast["forecast_start"], "forecast_end": forecast["forecast_end"], "points": len(forecast["points"])}))


if __name__ == "__main__":
    main()

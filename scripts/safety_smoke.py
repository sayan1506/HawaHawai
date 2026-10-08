"""Bounded REAL deployed Phase 2 E2E; no fault controls or simulated live orders."""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://pu8l3a213j.execute-api.us-east-1.amazonaws.com"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="Use the isolated Docker service, not AWS")
    args = parser.parse_args()
    base = "http://127.0.0.1:18080" if args.local else BASE
    schema = json.loads((ROOT / "contracts/openapi.json").read_text())
    school = json.loads((ROOT / "contracts/demo-school.json").read_text())
    path = "/v1/schools/" + school["school_id"]
    result = {"checked_at": datetime.now(timezone.utc).isoformat(), "mode": "docker_live_provider" if args.local else "real_aws", "simulated_regulatory_states": False, "checks": {}, "responses": {}}

    def call(route, name=None, expected=200, method="GET"):
        request = Request(base + route, method=method, headers={"Origin": "http://127.0.0.1:5173", **({"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "content-type"} if method == "OPTIONS" else {})})
        try:
            response = urlopen(request, timeout=28)
        except HTTPError as error:
            response = error
        with response:
            code = response.status
            raw = response.read()
            body = json.loads(raw) if raw and (name or "application/json" in response.headers.get("Content-Type", "")) else None
            cors = response.headers.get("Access-Control-Allow-Origin")
        assert code == expected, (route, code)
        if name:
            Draft202012Validator({**schema, "$ref": "#/components/schemas/" + name}, format_checker=FormatChecker()).validate(body)
        if code == 200 or method == "OPTIONS":
            assert cors == "http://127.0.0.1:5173", (route, "CORS")
        time.sleep(0.25)  # bounded 4/s, below the own API's 5/s setting
        return body

    health = call("/health", "Health")
    profile = call(path, "SchoolProfile")
    assert profile == school and health["phase"] == 0
    grap = call(path + "/grap", "GrapStatus")
    assert grap["verification_state"] == "UNKNOWN" and grap["active_stage"] is None and not grap["verification_action_recorded"]
    air = call(path + "/air", "AirReading")
    outlook = call(path + "/forecast", "Forecast")
    assert air["observations"] == [] and len(outlook["points"]) == 48
    assert all(v["source_type"] == "model_forecast" and v["observed_at"] is None and v["unit"] == "ug/m3" for p in outlook["points"] for v in p["pollutants"])
    assert all(a["scale"] == "US_AQI" for p in outlook["points"] for a in p["aqi"])
    decision = call(path + "/verdict", "Verdict")
    repeat = call(path + "/verdict", "Verdict")
    assert decision["decision"] != "GO_OUTDOORS" and decision["requires_regulatory_verification"]
    assert decision["decision"] == repeat["decision"] and decision["rule_ids"] == repeat["rule_ids"] and decision["decision_id"] == repeat["decision_id"]
    assert not decision["data_quality"]["official_observations_available"]
    assert all(e["source_type"] == "model_forecast" and e["scale"] == "US_AQI" for e in decision["evidence"])
    assert not any(a["mandatory"] for a in decision["actions"])
    assert decision["policy_sources"] and decision["regulatory_status"]["source_documents"]
    assert decision["evidence"] or decision["decision"] == "DATA_INSUFFICIENT"
    cached = call(path + "/forecast", "Forecast")
    assert cached["cache"]["status"] == "hit" and cached["retrieved_at"] == outlook["retrieved_at"]
    call(path + "/verdict?grade=5&activity=sports", "Verdict")
    for query in ("grade=13", "grade=-1", "activity=unknown", "stage=4", "verdict=GO_OUTDOORS", "latitude=91&longitude=77", "latitude=bad&longitude=77"):
        call(path + "/verdict?" + query, "Error", 400)
    call("/v1/schools/unknown/verdict", "Error", 404)
    call(path + "/grap", expected=501 if args.local else 404, method="POST")
    call(path + "/verdict", expected=204, method="OPTIONS")
    call("/health", "Health")
    result["checks"] = {"phase0_health_and_profile": True, "phase1_real_provider_48h_units_scale": True, "truthful_unknown_regulation": True,
        "model_only_precaution_no_official_aqi": True, "real_environment_to_policy": True, "repeatable_decision": True,
        "forecast_cache_hit": True, "grade_activity_validation": True, "invalid_requests_rejected": True,
        "public_regulatory_mutation_rejected": True, "cors_get_options": True, "sources_traceable": True}
    result["responses"] = {"grap": grap, "verdict": decision, "air": air, "forecast": outlook}
    target = ROOT / (".local/phase2-docker-e2e.json" if args.local else ".local/phase2-live-e2e.json")
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checks": result["checks"], "decision": decision["decision"], "regulatory_state": grap["verification_state"], "evidence_count": len(decision["evidence"]), "forecast_points": len(outlook["points"]), "forecast_cache": cached["cache"]["status"], "retrieved_at": outlook["retrieved_at"]}))


if __name__ == "__main__":
    main()

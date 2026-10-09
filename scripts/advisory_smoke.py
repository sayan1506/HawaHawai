"""Bounded verification. No API keys or raw exception bodies are printed."""
import argparse
import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
BASE = "https://pu8l3a213j.execute-api.us-east-1.amazonaws.com"

def get(url):
    with urllib.request.urlopen(url, timeout=28) as response: return json.load(response)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-provider", action="store_true")
    parser.add_argument("--base", default=BASE)
    parser.add_argument('--phase', default='phase3', choices=['phase3', 'phase7'])
    args = parser.parse_args()
    from agent.runtime import invoke_strands, classify
    from agent.explanations import validate_plan
    school = json.loads((ROOT / "contracts/demo-school.json").read_text())
    prefix = args.base.rstrip("/") + "/v1/schools/" + school["school_id"]
    if args.local_provider:
        from dotenv import load_dotenv
        load_dotenv(ROOT / "backend/.env", override=False)
        data = {"school": school, "current": get(prefix+"/air"), "forecast": get(prefix+"/forecast"), "decision": get(prefix+"/verdict")}
        try:
            plan = asyncio.run(invoke_strands("gemini", os.environ, data, 8))
            validate_plan(plan.model_dump_json(), data["decision"])
            result = {"success": True, "provider": "gemini", "model": os.environ.get("HAWAHAWAI_GEMINI_MODEL"), "trusted_tools": 4, "decision": plan.decision, "statement_count": len(plan.statement_ids)}
        except Exception as exc:
            result = {"success": False, "provider": "gemini", "failure": classify(exc), "exception_type": type(exc).__name__}
            result["http_code"] = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            message = str(getattr(exc, "message", ""))
            for name in ("GEMINI_API_KEY", "GROQ_API_KEY"):
                if os.environ.get(name): message = message.replace(os.environ[name], "[REDACTED]")
            # Diagnostic is local smoke only, not production logging.
            result["redacted_diagnostic"] = message[:300]
            if hasattr(exc, "errors"):
                result["validation_errors"] = [{"type": e["type"], "loc": list(e["loc"])} for e in exc.errors(include_input=False)]
    else:
        from jsonschema import Draft202012Validator, FormatChecker
        contract = json.loads((ROOT / "contracts/openapi.json").read_text())
        schema = {"$ref": "#/components/schemas/Advisory", "components": contract["components"]}
        first, second = get(prefix+"/advisory"), get(prefix+"/advisory")
        for data in (first, second):
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)
            assert data["decision"] == data["authoritative_decision"]["decision"]
            assert data["verdict_id"] == data["authoritative_decision"]["decision_id"]
            assert data["en"] and data["hi"]
            assert datetime.fromisoformat(data["valid_until"]) > datetime.now(timezone.utc)
        assert second["cache"]["status"] == "hit"
        regressions = {kind: get(prefix+"/"+kind).get("status", "ok") for kind in ("air", "forecast", "grap", "verdict")}
        assert get(args.base.rstrip("/")+"/health")["status"] == "ok"
        result = {"success": True, "endpoint": prefix+"/advisory", "method": first["explanation_method"], "provider": first["generator"],
            "decision": first["decision"], "regulation": first["regulatory_status"]["verification_state"], "cache_first": first["cache"]["status"], "cache_second": second["cache"]["status"], "regressions": regressions}
        label = "docker" if args.base.startswith("http://127.0.0.1:") else "live"
        (ROOT / f".local/{args.phase}-{label}-advisory.json").write_text(json.dumps(first, ensure_ascii=False, indent=2), encoding="utf-8")
    target = f".local/{args.phase}-provider-smoke.json" if args.local_provider else (f".local/{args.phase}-docker-smoke.json" if args.base.startswith("http://127.0.0.1:") else f".local/{args.phase}-api-smoke.json")
    (ROOT / target).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return int(not result["success"])

if __name__ == "__main__": raise SystemExit(main())

"""One bounded backend Strands plan using actual deployed trusted school evidence."""
import asyncio
import os
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from scripts.advisory_smoke import BASE, get


def main():
    load_dotenv(ROOT / "backend" / ".env", override=False)
    provider = os.environ.get("HAWAHAWAI_AI_PROVIDER", "gemini")
    variable = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY"}.get(provider)
    if not variable or not os.environ.get(variable, "").strip():
        print("BLOCKED: supported provider/key not configured in backend/.env")
        return 2
    try:
        import json
        from agent.runtime import invoke_strands
        from agent.explanations import validate_plan
        school = json.loads((ROOT / "contracts/demo-school.json").read_text())
        prefix = BASE + "/v1/schools/" + school["school_id"]
        snapshot = {"school": school, "current": get(prefix + "/air"),
                    "forecast": get(prefix + "/forecast"), "decision": get(prefix + "/verdict")}
        previous_log_level = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        plan = asyncio.run(invoke_strands(provider, os.environ, snapshot, 8 if provider == "gemini" else 4))
        validate_plan(plan.model_dump_json(), snapshot["decision"])
        print(f"PASS: Strands {provider} backend connectivity and four trusted tools verified")
        return 0
    except Exception as error:
        print(f"FAIL: {provider} connectivity ({type(error).__name__}); error text suppressed to protect credentials")
        return 1
    finally:
        if 'previous_log_level' in locals():
            logging.disable(previous_log_level)


if __name__ == "__main__":
    raise SystemExit(main())

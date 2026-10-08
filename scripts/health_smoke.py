"""Verify localhost Docker and deployed API contracts, CORS, and error routes."""
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:5173"


def main():
    outputs = json.loads((ROOT / ".local/cdk-outputs.json").read_text())["HawaHawaiDev"]
    schema = json.loads((ROOT / "contracts/openapi.json").read_text())["components"]["schemas"]["Health"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    results = []
    for base, environment in [("http://127.0.0.1:18080", "local-docker"), (outputs["ApiBaseUrl"], "dev")]:
        with urlopen(Request(base + "/health", headers={"Origin": ORIGIN}), timeout=20) as response:
            body = json.load(response)
            validator.validate(body)
            assert body["environment"] == environment
            assert response.status == 200
            assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
            assert response.headers["Cache-Control"] == "no-store"
        with urlopen(Request(base + "/health", method="OPTIONS", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"}), timeout=20) as response:
            assert response.status == 204
            assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
        with urlopen(Request(base + "/health", headers={"Origin": "https://example.invalid"}), timeout=20) as response:
            assert response.headers.get("Access-Control-Allow-Origin") is None
        try:
            urlopen(base + "/v1/grap", timeout=20)
            raise AssertionError("Unimplemented route returned success")
        except HTTPError as error:
            assert error.code == 404
        results.append({"base_url": base, "environment": environment, "health": body, "checks": ["health_schema", "environment", "no_store", "allowed_origin", "cors_preflight", "disallowed_origin", "unimplemented_route_404"], "passed": True})
    (ROOT / ".local/health-smoke.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

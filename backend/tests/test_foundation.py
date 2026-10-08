import copy
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app import handler
from agent.providers import ProviderNotConfigured, create_model


class FoundationTests(unittest.TestCase):
    def test_health_matches_contract_and_contains_no_secret(self):
        with patch.dict(os.environ, {"HAWAHAWAI_ENV": "test", "GEMINI_API_KEY": "secret-test-value"}):
            response = handler({"rawPath": "/health", "requestContext": {"http": {"method": "GET"}}}, None)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["headers"]["Cache-Control"], "no-store")
        self.assertNotIn("secret-test-value", response["body"])
        contract = json.loads((ROOT / "contracts/openapi.json").read_text())["components"]["schemas"]["Health"]
        Draft202012Validator(contract, format_checker=FormatChecker()).validate(json.loads(response["body"]))

    def test_unimplemented_or_wrong_method_is_not_healthy(self):
        for path, method in [("/v1/grap", "GET"), ("/health", "POST"), ("/", "GET")]:
            response = handler({"rawPath": path, "requestContext": {"http": {"method": method}}}, None)
            self.assertEqual(response["statusCode"], 404)

    def test_profile_accepts_demo_rejects_bad_input(self):
        schema = json.loads((ROOT / "contracts/school-profile.schema.json").read_text())
        school = json.loads((ROOT / "contracts/demo-school.json").read_text())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(school)
        for field, value in [("latitude", 0), ("longitude", 180), ("name", " "), ("languages", ["fr"]), ("student_name", "unused")]:
            bad = copy.deepcopy(school)
            bad[field] = value
            with self.assertRaises(ValidationError):
                validator.validate(bad)

    def test_provider_keys_required_and_bedrock_disabled(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": ""}):
            for provider in ("gemini", "groq", "bedrock", "unknown"):
                with self.assertRaises(ProviderNotConfigured):
                    create_model(provider)

    def test_all_contract_schemas_are_valid(self):
        document = json.loads((ROOT / "contracts/openapi.json").read_text())
        for schema in document["components"]["schemas"].values():
            Draft202012Validator.check_schema(schema)
        self.assertTrue(document["paths"]["/health"]["get"]["x-implemented"])
        self.assertFalse(document["paths"]["/v1/grap"]["get"]["x-implemented"])

    def test_insufficient_evidence_cannot_claim_a_verdict(self):
        schemas = json.loads((ROOT / "contracts/openapi.json").read_text())["components"]["schemas"]
        # Test the state constraint alone; source $refs are validated by the complete document later.
        constraint = schemas["Verdict"]["allOf"][0]
        validator = Draft202012Validator(constraint)
        validator.validate({"status": "DATA_INSUFFICIENT", "verdict": None})
        validator.validate({"status": "decided", "verdict": "INDOOR_ONLY"})
        for value in [{"status": "decided", "verdict": None}, {"status": "VERIFY_STATUS", "verdict": "GO_OUTDOORS"}]:
            with self.assertRaises(ValidationError):
                validator.validate(value)


if __name__ == "__main__":
    unittest.main()

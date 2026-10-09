"""SIMULATED policy/regulatory cases. None is a current official status/readout."""
import copy
import inspect
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from app import handler
from environmental.config import school_profile
from environmental.cache import MemoryCache, CacheError
from environmental.http import ProviderError
from environmental.providers import OpenMeteoProvider
from environmental.service import EnvironmentalService
from safety.models import ActivityContext, Policy, instant
from safety.registry import ATTESTATION, read_snapshot, resolve, validate_snapshot, school_catalog
from safety.engine import evaluate
from safety.service import verdict
from publish_regulatory_snapshot import publish, review_originals
from test_environmental import fixture

NOW = datetime(2026, 10, 8, 8, tzinfo=timezone.utc)
SCHOOL = school_profile()


def document(identifier, kind, published="2026-10-08"):
    return {"document_id": identifier, "title": "SIMULATION ONLY - " + identifier,
            "authority": "Simulated test authority, not current government evidence",
            "url": "https://caqm.nic.in/", "published_on": published, "document_type": kind,
            "access_status": "HUMAN_REVIEWED", "sha256": "0" * 64,
            "effective_from": None, "effective_until": None}


def snapshot(stage=0):
    data = {"version": "simulation-v1", "schedule_version": "simulation-2026-09-29", "jurisdiction": "NCT_DELHI",
            "simulation": True, "notes": ["SIMULATION ONLY - never publish"], "restrictions": [],
            "documents": [document("schedule", "SCHEDULE", "2026-09-29")], "events": [],
            "verification": {"operator_id": "SIMULATED_REVIEWER", "verified_at": (NOW - timedelta(minutes=5)).isoformat(),
                "expires_at": (NOW + timedelta(hours=1)).isoformat(), "history_reviewed_through": (NOW - timedelta(minutes=5)).isoformat(), "attestation": ATTESTATION}}
    for number in range(1, stage + 1):
        data["documents"].append(document("activation" + str(number), "ACTIVATION"))
        data["events"].append({"event_id": "a" + str(number), "document_id": "activation" + str(number), "event_type": "ACTIVATE",
            "stage": number, "effective_from": (NOW - timedelta(hours=1) + timedelta(minutes=number)).isoformat(), "revokes_event_id": None})
    if stage == 0:
        data["documents"].append(document("revoke-all", "REVOCATION"))
        data["events"].append({"event_id": "revoke-all", "document_id": "revoke-all", "event_type": "REVOKE_ALL", "stage": 0,
            "effective_from": (NOW - timedelta(hours=1)).isoformat(), "revokes_event_id": None})
    return data


def restriction(data, action="SUSPEND_OUTDOOR", grades=None, activity="all", minimum_stage=None, mandatory=True):
    data["documents"].append(document("school-order", "SCHOOL_ORDER"))
    data["restrictions"].append({"restriction_id": "simulated-school-rule", "document_id": "school-order", "clause": "SIMULATION ONLY: applicable school restriction for testing precedence",
        "jurisdiction": "NCT_DELHI", "grades": grades if grades is not None else list(range(13)), "activity": activity,
        "action": action, "mandatory": mandatory, "effective_from": (NOW - timedelta(hours=1)).isoformat(),
        "effective_until": None, "minimum_stage": minimum_stage, "revoked_by": None})
    return data


def catalog_snapshot(stage=0):
    """SIMULATED activation/human action bound to researched real clause metadata.

    Never a live status and never publishable; no actual human review is claimed.
    """
    data, catalog = snapshot(stage), school_catalog()
    data["schedule_version"] = catalog["schedule_version"]
    data["documents"][0].update(url=catalog["source_url"], sha256=catalog["source_sha256"],
        effective_from="2026-09-29T00:00:00Z")
    return data


def environment(value=50, observation=False):
    raw = fixture()
    raw["current"]["time"] = NOW.timestamp() - 300
    raw["current"]["us_aqi"] = value
    raw["hourly"]["time"] = [int(NOW.timestamp()) + i * 3600 for i in range(72)]
    raw["hourly"]["us_aqi"] = [value] * 72
    provider = Mock()
    provider.fetch.return_value = OpenMeteoProvider().normalize(raw, SCHOOL, NOW.timestamp())
    service = EnvironmentalService(MemoryCache(), provider, lambda: NOW.timestamp())
    air, forecast = service.get(SCHOOL, "current"), service.get(SCHOOL, "forecast")
    if observation:
        point = copy.deepcopy(air["modeled_current"])
        source = copy.deepcopy(air["sources"][0])
        source.update(source_id="simulation-station", kind="measurement", name="SIMULATED co-located station", url="https://example.invalid/simulation", limitations=[], observed_at=point["valid_at"])
        source["location"] = {"latitude": SCHOOL["latitude"], "longitude": SCHOOL["longitude"], "station_id": "SIMULATION", "distance_km": 0}
        for value_item in point["pollutants"] + point["aqi"]:
            value_item.update(source_id="simulation-station", source_type="measurement", observed_at=point["valid_at"], forecast_for=None)
        air["sources"].append(source)
        air["observations"] = [point]
    return air, forecast, service


def decision(value=50, state=None, observation=False, context=None):
    context = context or ActivityContext()
    air, forecast, _ = environment(value, observation)
    regulatory = resolve(state if state is not None else read_snapshot(), NOW, context)
    return evaluate(SCHOOL, air, forecast, regulatory, NOW, context)


class RegulatoryTests(unittest.TestCase):
    def test_four_active_stages_are_separate_from_verification(self):
        for stage in range(1, 5):
            with self.subTest(stage=stage):
                result = resolve(snapshot(stage), NOW, ActivityContext())
                self.assertEqual(result["verification_state"], "VERIFIED_ACTIVE")
                self.assertEqual(result["active_stage"], stage)

    def test_verified_inactive_requires_revocation_document(self):
        result = resolve(snapshot(), NOW, ActivityContext())
        self.assertEqual(result["verification_state"], "VERIFIED_INACTIVE")
        self.assertEqual(result["stage"], 0)
        self.assertIsNone(result["active_stage"])

    def test_live_research_is_unknown_without_human_action(self):
        result = resolve(read_snapshot(), NOW, ActivityContext())
        self.assertEqual(result["verification_state"], "UNKNOWN")
        self.assertIsNone(result["stage"])
        self.assertIsNone(result["verified_at"])
        self.assertFalse(result["verification_action_recorded"])

    def test_stage_number_config_cannot_verify(self):
        for field in ("stage", "verification_state", "llm_verdict"):
            data = read_snapshot()
            data[field] = 4
            with self.assertRaises(ValueError):
                validate_snapshot(data)

    def test_claims_without_human_verification_rejected(self):
        data = snapshot(3)
        data["verification"] = None
        with self.assertRaises(ValueError):
            validate_snapshot(data)

    def test_expired_stale_and_future_verification(self):
        for now, expected in ((NOW + timedelta(hours=1), "STALE"), (NOW - timedelta(minutes=6), "UNKNOWN")):
            result = resolve(snapshot(4), now, ActivityContext())
            self.assertEqual(result["verification_state"], expected)
            self.assertIsNone(result["active_stage"])

    def test_invalid_expiration_review_coverage(self):
        for field, value in (("expires_at", (NOW + timedelta(days=2)).isoformat()), ("history_reviewed_through", NOW.isoformat()), ("attestation", "AI reviewed it")):
            data = snapshot(1)
            data["verification"][field] = value
            with self.assertRaises(ValueError):
                validate_snapshot(data)

    def test_old_schedule_not_assumed_current(self):
        data = snapshot(3)
        data["documents"][0]["published_on"] = "2025-11-21"
        with self.assertRaises(ValueError):
            validate_snapshot(data)

    def test_invalid_official_source(self):
        for field, value in (("url", "https://caqm.nic.in.attacker.invalid/file.pdf"), ("url", "http://caqm.nic.in/file.pdf"), ("sha256", "missing"), ("authority", ""), ("access_status", "RESEARCHED")):
            data = snapshot()
            data["documents"][0][field] = value
            with self.assertRaises(ValueError):
                validate_snapshot(data)

    def test_invalid_jurisdiction_and_grades(self):
        for field, value in (("jurisdiction", "UNKNOWN"), ("grades", [13]), ("grades", [True]), ("grades", [])):
            data = restriction(snapshot())
            data["restrictions"][0][field] = value
            with self.assertRaises(ValueError):
                validate_snapshot(data)

    def test_stage_reversion_does_not_deactivate_lower_stages(self):
        data = snapshot(4)
        data["documents"].append(document("revoke4", "REVOCATION"))
        data["events"].append({"event_id": "r4", "document_id": "revoke4", "event_type": "REVOKE", "stage": 4, "effective_from": (NOW - timedelta(minutes=10)).isoformat(), "revokes_event_id": "a4"})
        self.assertEqual(resolve(data, NOW, ActivityContext())["active_stage"], 3)

    def test_conflicting_activation_revocation_and_missing_chain(self):
        data = snapshot(1)
        data["documents"].append(document("revoke1", "REVOCATION"))
        data["events"].append({"event_id": "r1", "document_id": "revoke1", "event_type": "REVOKE", "stage": 1, "effective_from": data["events"][0]["effective_from"], "revokes_event_id": "a1"})
        self.assertEqual(resolve(data, NOW, ActivityContext())["verification_state"], "CONFLICTING")
        data = snapshot(3)
        data["events"] = data["events"][2:]
        self.assertEqual(resolve(data, NOW, ActivityContext())["verification_state"], "CONFLICTING")

    def test_grade_scope_and_hybrid_not_outdoor_ban(self):
        data = restriction(snapshot(3), action="HYBRID_CLASSES", grades=[0, 1, 2, 3, 4, 5], minimum_stage=3)
        self.assertEqual(len(resolve(data, NOW, ActivityContext(grade=5))["applicable_restrictions"]), 1)
        self.assertEqual(resolve(data, NOW, ActivityContext(grade=6))["applicable_restrictions"], [])
        self.assertEqual(decision(50, data, True, ActivityContext(grade=5))["decision"], "MODIFIED_OUTDOORS")
        self.assertEqual(decision(50, data, True, ActivityContext(grade=6))["decision"], "GO_OUTDOORS")

    def test_independent_school_order_applies_with_unknown_stage(self):
        data = restriction(snapshot())
        data["events"] = []
        result = resolve(data, NOW, ActivityContext())
        self.assertEqual(result["verification_state"], "UNKNOWN")
        self.assertEqual(decision(50, data)["decision"], "INDOOR_ONLY")

    def test_expired_or_explicitly_revoked_school_order(self):
        for revoke in (False, True):
            data = restriction(snapshot(3))
            if revoke:
                doc = document("school-revoke", "REVOCATION")
                doc["effective_from"] = NOW.isoformat()
                data["documents"].append(doc)
                data["restrictions"][0]["revoked_by"] = doc["document_id"]
            else:
                data["restrictions"][0]["effective_until"] = NOW.isoformat()
            self.assertEqual(resolve(data, NOW, ActivityContext())["applicable_restrictions"], [])

    def test_advisory_cannot_create_mandatory_school_closure(self):
        data = restriction(snapshot(), action="RESCHEDULE_SPORTS")
        data["documents"][-1]["document_type"] = "ADVISORY"
        with self.assertRaises(ValueError):
            validate_snapshot(data)

    def test_simulations_and_unperformed_human_reviews_cannot_publish(self):
        with self.assertRaises(ValueError):
            validate_snapshot(snapshot(), publish=True)
        with self.assertRaises(ValueError):
            validate_snapshot(read_snapshot(), publish=True)

    def test_registry_publication_atomic_no_ttl_or_unrelated_keys(self):
        client = Mock()
        client.get_item.return_value = {}
        publish(client, read_snapshot())
        writes = client.transact_write_items.call_args.kwargs["TransactItems"]
        self.assertEqual(len(writes), 2)
        for write in writes:
            self.assertEqual(write["Put"]["TableName"], "hawahawai-dev-environment-cache")
            self.assertTrue(write["Put"]["Item"]["cache_key"]["S"].startswith("regulatory#NCT_DELHI#"))
            self.assertNotIn("expires_at", write["Put"]["Item"])
            self.assertIn("ConditionExpression", write["Put"])

    def test_bad_registry_cache_fails_to_unknown_not_fake_verified(self):
        cache = Mock()
        cache.get.return_value = {"version": "../bad"}
        from safety.service import regulatory_status
        result = regulatory_status(SCHOOL, NOW, ActivityContext(), cache)
        self.assertEqual(result["verification_state"], "UNKNOWN")
        self.assertTrue(any("REGISTRY_READ_FAILED" in w for w in result["warnings"]))

    def test_expired_activation_order_and_timezone_equivalent_conflict(self):
        data = snapshot(1)
        data["documents"][-1].update(effective_from=data["events"][0]["effective_from"], effective_until=NOW.isoformat())
        self.assertEqual(resolve(data, NOW, ActivityContext())["verification_state"], "UNKNOWN")
        data = snapshot(1)
        data["documents"].append(document("r", "REVOCATION"))
        data["events"].append({"event_id": "r", "document_id": "r", "event_type": "REVOKE", "stage": 1, "effective_from": data["events"][0]["effective_from"].replace("+00:00", "Z"), "revokes_event_id": "a1"})
        self.assertEqual(resolve(data, NOW, ActivityContext())["verification_state"], "CONFLICTING")

    def test_registry_cache_does_not_renew_verification_or_use_ttl(self):
        data = catalog_snapshot(1)
        data["simulation"] = False  # LOCAL cache fixture only; NEVER published.
        cache = MemoryCache()
        cache.put("regulatory#NCT_DELHI#current", {"version": data["version"]})
        cache.put("regulatory#NCT_DELHI#version#" + data["version"], data)
        result = resolve(read_snapshot(cache), NOW + timedelta(hours=2), ActivityContext())
        self.assertEqual(result["verification_state"], "STALE")
        self.assertIsNone(result["stage"])

    def test_admin_requires_reviewed_originals_not_merely_a_stage_config(self):
        data = snapshot()
        data["simulation"] = False  # validation test, not a publication
        with self.assertRaises(ValueError):
            review_originals(data, ROOT / ".local/missing-test-originals", "SIMULATED_REVIEWER", ATTESTATION, NOW)

    def test_explicit_all_stage_revocation_conflicting_same_instant(self):
        data = snapshot(1)
        data["documents"].append(document("revoke-all", "REVOCATION"))
        data["events"].append({"event_id": "r", "document_id": "revoke-all", "event_type": "REVOKE_ALL", "stage": 0, "effective_from": data["events"][0]["effective_from"], "revokes_event_id": None})
        self.assertEqual(resolve(data, NOW, ActivityContext())["verification_state"], "CONFLICTING")


class SafetyTests(unittest.TestCase):
    def test_duplicate_conflicting_forecast_hour_never_yields_go(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                air, forecast, _ = environment(50, True)
                elevated = copy.deepcopy(forecast['points'][0])
                elevated['aqi'][0]['value'] = 250
                forecast['points'].insert(0 if not reverse else 1, elevated)
                result = evaluate(SCHOOL, air, forecast, resolve(snapshot(0), NOW, ActivityContext()), NOW)
                self.assertNotEqual(result['decision'], 'GO_OUTDOORS')
                self.assertFalse(result['data_quality']['forecast_available'])

    def test_conflicting_us_aqi_values_in_a_point_never_yield_go(self):
        air, forecast, _ = environment(50, True)
        for point in air['observations'] + [air['modeled_current']] + forecast['points']:
            elevated = copy.deepcopy(point['aqi'][0]); elevated['value'] = 250
            point['aqi'].append(elevated)
        result = evaluate(SCHOOL, air, forecast, resolve(snapshot(0), NOW, ActivityContext()), NOW)
        self.assertNotEqual(result['decision'], 'GO_OUTDOORS')

    def test_expired_physical_source_cannot_authorize_go(self):
        air, forecast, _ = environment(50, True)
        air['sources'][-1]['valid_until'] = (NOW - timedelta(seconds=1)).isoformat()
        result = evaluate(SCHOOL, air, forecast, resolve(snapshot(0), NOW, ActivityContext()), NOW)
        self.assertNotEqual(result['decision'], 'GO_OUTDOORS')

    def test_source_expiry_caps_positive_decision(self):
        air, forecast, _ = environment(50, True)
        now = NOW + timedelta(minutes=1)
        deadline = now + timedelta(seconds=30)
        air['sources'][-1]['valid_until'] = deadline.isoformat()
        result = evaluate(SCHOOL, air, forecast, resolve(snapshot(0), now, ActivityContext()), now)
        self.assertEqual(result['decision'], 'GO_OUTDOORS')
        self.assertLessEqual(instant(result['valid_until']), deadline)

    def test_every_verdict_and_policy_boundaries(self):
        for value, expected in ((0, "GO_OUTDOORS"), (50, "GO_OUTDOORS"), (100, "GO_OUTDOORS"), (100.1, "MODIFIED_OUTDOORS"), (101, "MODIFIED_OUTDOORS"), (150, "MODIFIED_OUTDOORS"), (151, "MODIFIED_OUTDOORS"), (200, "MODIFIED_OUTDOORS"), (200.1, "INDOOR_ONLY"), (201, "INDOOR_ONLY"), (300, "INDOOR_ONLY"), (301, "INDOOR_ONLY"), (500, "INDOOR_ONLY")):
            with self.subTest(value=value):
                result = decision(value, snapshot(), True)
                self.assertEqual(result["decision"], expected)
                self.assertTrue(result["rule_ids"])
                self.assertTrue(result["evidence"])
        self.assertEqual(decision()["decision"], "DATA_INSUFFICIENT")

    def test_vigorous_activity_boundary_and_consistency(self):
        for value, expected in ((150, "MODIFY"), (150.1, "INDOOR_ALTERNATIVE"), (151, "INDOOR_ALTERNATIVE")):
            result = decision(value)
            for action in result["actions"]:
                if action["activity"] in {"sports", "physical_education"}:
                    self.assertEqual(action["recommendation"], expected)
                self.assertFalse(action["mandatory"])

    def test_mandatory_order_overrides_favorable_forecast(self):
        result = decision(10, restriction(snapshot(3)), True)
        self.assertEqual(result["decision"], "INDOOR_ONLY")
        self.assertEqual(result["rule_evaluations"][0]["rule_id"], "MANDATORY_SCHOOL_RESTRICTION")
        self.assertTrue(all(a["mandatory"] for a in result["actions"] if a["activity"] in {"assembly", "sports", "physical_education", "other"}))

    def test_model_only_can_restrict_but_never_positive_or_activate_grap(self):
        for value, expected in ((20, "DATA_INSUFFICIENT"), (150, "MODIFIED_OUTDOORS"), (450, "INDOOR_ONLY")):
            result = decision(value)
            self.assertEqual(result["decision"], expected)
            self.assertIsNone(result["regulatory_status"]["active_stage"])
            self.assertFalse(result["data_quality"]["official_observations_available"])
            self.assertTrue(result["requires_regulatory_verification"])

    def test_missing_regulatory_verification_cannot_be_positive(self):
        self.assertEqual(decision(10, observation=True)["decision"], "DATA_INSUFFICIENT")

    def test_missing_forecast_and_observations(self):
        air, forecast, _ = environment(10, True)
        forecast["points"] = []
        result = evaluate(SCHOOL, air, forecast, resolve(snapshot(), NOW, ActivityContext()), NOW)
        self.assertEqual(result["decision"], "DATA_INSUFFICIENT")
        self.assertIn("MISSING_FRESH_ACTIVITY_FORECAST", result["rule_ids"])
        self.assertEqual(decision(10, snapshot())["decision"], "DATA_INSUFFICIENT")

    def test_stale_forecast_not_used_and_no_favorable_fallback(self):
        air, forecast, _ = environment(450)
        air["status"], air["freshness_status"] = "stale", "stale"
        forecast["status"], forecast["freshness_status"] = "stale", "stale"
        result = evaluate(SCHOOL, air, forecast, resolve(snapshot(), NOW, ActivityContext()), NOW)
        self.assertEqual(result["decision"], "DATA_INSUFFICIENT")
        self.assertEqual(result["evidence"], [])

    def test_indian_aqi_european_and_raw_concentrations_not_converted(self):
        for scale in ("INDIA_AQI", "EUROPEAN_AQI"):
            air, forecast, _ = environment(450)
            air["modeled_current"]["aqi"][0]["scale"] = scale
            for point in forecast["points"]:
                point["aqi"][0]["scale"] = scale
                point["pollutants"][0]["value"] = 100000
            result = evaluate(SCHOOL, air, forecast, resolve(read_snapshot(), NOW, ActivityContext()), NOW)
            self.assertEqual(result["decision"], "DATA_INSUFFICIENT")
            self.assertEqual(result["evidence"], [])

    def test_unsupported_units_missing_station_metadata(self):
        air, forecast, _ = environment(20, True)
        air["sources"][-1]["location"]["station_id"] = None
        result = evaluate(SCHOOL, air, forecast, resolve(snapshot(), NOW, ActivityContext()), NOW)
        self.assertEqual(result["decision"], "DATA_INSUFFICIENT")
        for point in forecast["points"]:
            point["pollutants"][0]["unit"] = "ppm"
        self.assertFalse(evaluate(SCHOOL, air, forecast, resolve(snapshot(), NOW, ActivityContext()), NOW)["data_quality"]["forecast_available"])

    def test_model_cannot_masquerade_as_physical_station(self):
        air, forecast, _ = environment(20)
        air["observations"] = [air["modeled_current"]]
        result = evaluate(SCHOOL, air, forecast, resolve(snapshot(), NOW, ActivityContext()), NOW)
        self.assertEqual(result["decision"], "DATA_INSUFFICIENT")

    def test_explicit_time_required_and_timestamp_future_naive_rejected(self):
        with self.assertRaises(ValueError):
            instant("2026-10-08T08:00:00")
        air, forecast, _ = environment(450)
        air["retrieved_at"] = (NOW + timedelta(minutes=1)).isoformat()
        forecast["retrieved_at"] = (NOW + timedelta(minutes=1)).isoformat()
        self.assertEqual(evaluate(SCHOOL, air, forecast, resolve(snapshot(), NOW, ActivityContext()), NOW)["decision"], "DATA_INSUFFICIENT")

    def test_deterministic_repetition_and_no_hidden_ai_or_clock(self):
        air, forecast, _ = environment(175)
        regulatory = resolve(read_snapshot(), NOW, ActivityContext())
        before = copy.deepcopy((air, forecast, regulatory))
        one = evaluate(SCHOOL, air, forecast, regulatory, NOW)
        two = evaluate(SCHOOL, air, forecast, regulatory, NOW)
        self.assertEqual(one, two)
        self.assertEqual((air, forecast, regulatory), before)
        source = inspect.getsource(sys.modules["safety.engine"])
        for forbidden in ("datetime.now", "time.time", "create_model", "strands", "requests", ".fetch("):
            self.assertNotIn(forbidden, source)
        with self.assertRaises(TypeError):
            evaluate(SCHOOL, air, forecast, regulatory, NOW, llm_verdict="GO_OUTDOORS")

    def test_policy_changes_regenerate_fingerprint_not_cached_verdict(self):
        air, forecast, _ = environment(175)
        regulatory = resolve(read_snapshot(), NOW, ActivityContext())
        old = evaluate(SCHOOL, air, forecast, regulatory, NOW)
        new = evaluate(SCHOOL, air, forecast, regulatory, NOW, policy=Policy(version="school-safety-v2-test"))
        self.assertNotEqual(old["decision_id"], new["decision_id"])
        with self.assertRaises(ValueError):
            Policy(indoor_above=500)

    def test_unknown_conflicting_stale_status_never_positive(self):
        data = snapshot(1)
        data["documents"].append(document("r", "REVOCATION"))
        data["events"].append({"event_id": "r", "document_id": "r", "event_type": "REVOKE", "stage": 1, "effective_from": data["events"][0]["effective_from"], "revokes_event_id": "a1"})
        self.assertEqual(decision(20, data, True)["decision"], "DATA_INSUFFICIENT")
        data = snapshot()
        data["verification"].update(verified_at=(NOW - timedelta(hours=2)).isoformat(), history_reviewed_through=(NOW - timedelta(hours=2)).isoformat(), expires_at=(NOW - timedelta(hours=1)).isoformat())
        self.assertEqual(decision(20, data, True)["decision"], "DATA_INSUFFICIENT")

    def test_activity_and_grade_requests_are_explicit(self):
        data = restriction(snapshot(3), grades=[5], activity="sports")
        self.assertEqual(decision(20, data, True, ActivityContext(grade=5, activity="sports"))["decision"], "INDOOR_ONLY")
        self.assertEqual(decision(20, data, True, ActivityContext(grade=6, activity="sports"))["decision"], "GO_OUTDOORS")
        self.assertEqual(decision(20, data, True, ActivityContext(grade=5, activity="assembly"))["decision"], "GO_OUTDOORS")
        for kwargs in ({"grade": True}, {"grade": 13}, {"activity": "close-school"}, {"jurisdiction": "UP"}):
            with self.assertRaises(ValueError):
                ActivityContext(**kwargs)

    def test_future_order_transition_limits_decision_validity(self):
        data = restriction(snapshot())
        data["restrictions"][0]["effective_from"] = (NOW + timedelta(minutes=2)).isoformat()
        result = decision(20, data, True)
        self.assertEqual(result["decision"], "GO_OUTDOORS")
        self.assertLessEqual(instant(result["valid_until"]), NOW + timedelta(minutes=2))

    def test_verification_expiry_is_not_legal_revocation(self):
        data = restriction(snapshot(3))
        data["verification"].update(verified_at=(NOW - timedelta(hours=2)).isoformat(), history_reviewed_through=(NOW - timedelta(hours=2)).isoformat(), expires_at=(NOW - timedelta(hours=1)).isoformat())
        result = decision(150, data)
        self.assertEqual(result["decision"], "INDOOR_ONLY")
        self.assertEqual(result["regulatory_status"]["verification_state"], "STALE")
        self.assertIn("PREVIOUS_RESTRICTION_REVERIFY", result["rule_ids"])
        self.assertFalse(any(a["mandatory"] for a in result["actions"]))

    def test_physical_class_suspension_cannot_be_bypassed_indoors(self):
        data = restriction(snapshot(), action="SUSPEND_PHYSICAL_CLASSES", activity="administration")
        result = decision(20, data, True)
        self.assertEqual(result["decision"], "INDOOR_ONLY")
        for action in result["actions"]:
            if action["activity"] in {"assembly", "sports", "physical_education", "other", "indoor"}:
                self.assertEqual(action["recommendation"], "FOLLOW_PHYSICAL_CLASS_ORDER")

    def test_advisory_is_traceable_but_not_a_mandatory_ban(self):
        data = restriction(snapshot(), action="RESCHEDULE_SPORTS", activity="sports", mandatory=False)
        data["documents"][-1]["document_type"] = "ADVISORY"
        result = decision(20, data, True)
        self.assertIn("OFFICIAL_ADVISORY_REVIEW", result["rule_ids"])
        self.assertFalse(any(a["mandatory"] for a in result["actions"]))

    def test_partial_missing_forecast_aqi_cannot_justify_go(self):
        air, forecast, _ = environment(20, True)
        forecast["points"][1]["aqi"] = []
        self.assertEqual(evaluate(SCHOOL, air, forecast, resolve(snapshot(), NOW, ActivityContext()), NOW)["decision"], "DATA_INSUFFICIENT")

    def test_out_of_range_nonfinite_and_bool_aqi_never_safe(self):
        for value in (501, float("nan"), True, -1):
            air, forecast, _ = environment(20)
            air["modeled_current"]["aqi"][0]["value"] = value
            for point in forecast["points"]:
                point["aqi"][0]["value"] = value
            self.assertEqual(evaluate(SCHOOL, air, forecast, resolve(read_snapshot(), NOW, ActivityContext()), NOW)["decision"], "DATA_INSUFFICIENT")

    def test_failed_refresh_rate_limit_and_stale_evidence_rejected(self):
        for code in ("TIMEOUT", "RATE_LIMITED"):
            _, _, service = environment(175)
            service.clock = lambda: NOW.timestamp() + 4000
            service.provider.fetch.side_effect = ProviderError(code, 120)
            result = verdict(SCHOOL, service, NOW + timedelta(seconds=4000))
            self.assertEqual(result["decision"], "DATA_INSUFFICIENT")
            self.assertTrue(any(code in w for w in result["warnings"]))
            self.assertEqual(result["evidence"], [])
            count = service.provider.fetch.call_count
            verdict(SCHOOL, service, NOW + timedelta(seconds=4000))
            self.assertEqual(service.provider.fetch.call_count, count)


class CurrentScheduleTests(unittest.TestCase):
    def test_stage_i_ii_have_no_invented_automatic_school_bans(self):
        for stage in (1, 2):
            result = decision(20, catalog_snapshot(stage), True)
            self.assertEqual(result["decision"], "GO_OUTDOORS")
            self.assertFalse(any(a["mandatory"] for a in result["actions"]))

    def test_stage_iii_grade_v_vi_boundary_and_hybrid_not_outdoor_ban(self):
        for grade, hybrid in ((0, True), (5, True), (6, False), (12, False)):
            result = decision(20, catalog_snapshot(3), True, ActivityContext(grade=grade))
            self.assertEqual(result["decision"], "MODIFIED_OUTDOORS" if hybrid else "GO_OUTDOORS")
            actions = [a for a in result["actions"] if a["recommendation"] == "HYBRID_CLASSES"]
            self.assertEqual(bool(actions), hybrid)
            self.assertFalse(any(a["mandatory"] for a in result["actions"] if a["activity"] != "administration"))

    def test_stage_iv_exact_hybrid_grades_and_nonmandatory_children_advice(self):
        for grade in range(13):
            result = decision(20, catalog_snapshot(4), True, ActivityContext(grade=grade))
            self.assertEqual(result["decision"], "INDOOR_ONLY")
            self.assertIn("VERIFIED_GRAP_CHILDREN_ADVISORY", result["rule_ids"])
            hybrid = [a for a in result["actions"] if a["recommendation"] == "HYBRID_CLASSES"]
            self.assertEqual(bool(hybrid), grade not in {10, 12})
            self.assertFalse(any(a["mandatory"] for a in result["actions"] if a["activity"] in {"assembly", "sports", "physical_education", "other"}))
            self.assertFalse(any(a["recommendation"] == "SUSPEND_PHYSICAL_CLASSES" for a in result["actions"]))

    def test_catalog_cannot_activate_from_document_or_modeled_aqi(self):
        data = read_snapshot()
        result = decision(500, data)
        self.assertEqual(result["regulatory_status"]["verification_state"], "UNKNOWN")
        self.assertEqual(result["regulatory_status"]["applicable_restrictions"], [])
        self.assertFalse(any(a["mandatory"] for a in result["actions"]))
        self.assertNotIn("VERIFIED_GRAP_CHILDREN_ADVISORY", result["rule_ids"])

    def test_catalog_requires_exact_original_digest_effective_time_and_review(self):
        for key, value in (("sha256", "f" * 64), ("url", "https://caqm.nic.in/"), ("effective_from", None)):
            data = catalog_snapshot(4)
            data["documents"][0][key] = value
            self.assertEqual(resolve(data, NOW, ActivityContext())["applicable_restrictions"], [])
            data["simulation"] = False  # rejection test only, never publication
            with self.assertRaises(ValueError):
                validate_snapshot(data)

    def test_stage_iv_revocation_retains_iii_primary_hybrid_not_upper_grades(self):
        data = catalog_snapshot(4)
        data["documents"].append(document("r4", "REVOCATION"))
        data["events"].append({"event_id": "r4", "document_id": "r4", "event_type": "REVOKE", "stage": 4,
            "effective_from": (NOW - timedelta(minutes=10)).isoformat(), "revokes_event_id": "a4"})
        for grade, expected in ((5, "MODIFIED_OUTDOORS"), (6, "GO_OUTDOORS")):
            result = decision(20, data, True, ActivityContext(grade=grade))
            self.assertEqual(result["decision"], expected)
            self.assertEqual(result["regulatory_status"]["active_stage"], 3)
            self.assertNotIn("VERIFIED_GRAP_CHILDREN_ADVISORY", result["rule_ids"])

    def test_previous_revocation_cannot_clear_new_activation(self):
        data = snapshot(1)
        data["documents"] += [document("new1", "ACTIVATION"), document("r1", "REVOCATION")]
        data["events"] += [
            {"event_id": "new1", "document_id": "new1", "event_type": "ACTIVATE", "stage": 1, "effective_from": (NOW - timedelta(minutes=20)).isoformat(), "revokes_event_id": None},
            {"event_id": "r1", "document_id": "r1", "event_type": "REVOKE", "stage": 1, "effective_from": (NOW - timedelta(minutes=10)).isoformat(), "revokes_event_id": "a1"}]
        self.assertEqual(resolve(data, NOW, ActivityContext())["verification_state"], "CONFLICTING")

    def test_cumulative_history_cannot_skip_remaining_lower_stage(self):
        data = snapshot(4)
        data["documents"].append(document("r3", "REVOCATION"))
        data["events"].append({"event_id": "r3", "document_id": "r3", "event_type": "REVOKE", "stage": 3,
            "effective_from": (NOW - timedelta(minutes=10)).isoformat(), "revokes_event_id": "a3"})
        self.assertEqual(resolve(data, NOW, ActivityContext())["verification_state"], "CONFLICTING")

    def test_stage_iv_response_has_valid_schema_and_is_repeatable(self):
        result = decision(20, catalog_snapshot(4), True)
        schemas = json.loads((ROOT / "contracts/openapi.json").read_text())
        Draft202012Validator({**schemas, "$ref": "#/components/schemas/Verdict"}, format_checker=FormatChecker()).validate(result)
        self.assertEqual(result, decision(20, catalog_snapshot(4), True))


class SafetyApiTests(unittest.TestCase):
    def call(self, suffix, params=None):
        return handler({"rawPath": "/v1/schools/delhi-demo-school/" + suffix, "queryStringParameters": params, "requestContext": {"http": {"method": "GET"}}}, None)

    def test_success_schema_and_environment_cache_hit(self):
        _, _, service = environment(175)
        with patch("environmental.service.get_service", return_value=service):
            for suffix, name in (("grap", "GrapStatus"), ("verdict", "Verdict")):
                result = self.call(suffix)
                self.assertEqual(result["statusCode"], 200)
                body = json.loads(result["body"])
                document_schema = json.loads((ROOT / "contracts/openapi.json").read_text())
                Draft202012Validator({**document_schema, "$ref": "#/components/schemas/" + name}, format_checker=FormatChecker()).validate(body)
            self.assertEqual(service.provider.fetch.call_count, 1)

    def test_new_routes_local_cors(self):
        import threading
        from http.server import ThreadingHTTPServer
        from urllib.request import Request, urlopen
        from local_server import RequestHandler
        _, _, service = environment(175)
        server = ThreadingHTTPServer(("127.0.0.1", 0), RequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch("environmental.service.get_service", return_value=service):
                url = f"http://127.0.0.1:{server.server_port}/v1/schools/delhi-demo-school/verdict"
                with urlopen(Request(url, headers={"Origin": "http://127.0.0.1:5173"}), timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://127.0.0.1:5173")
                with urlopen(Request(url, method="OPTIONS", headers={"Origin": "http://127.0.0.1:5173"}), timeout=3) as response:
                    self.assertEqual(response.status, 204)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_invalid_parameters_and_no_public_mutation_or_ai_override(self):
        for params in ({"grade": "13"}, {"grade": "-1"}, {"grade": "1.5"}, {"grade": ""}, {"activity": "unknown"}, {"verdict": "GO_OUTDOORS"}, {"stage": "4"}, {"latitude": "bad", "longitude": "77"}):
            self.assertEqual(self.call("verdict", params)["statusCode"], 400)
        result = handler({"rawPath": "/v1/schools/delhi-demo-school/grap", "httpMethod": "POST", "body": '{"stage":4}'}, None)
        self.assertEqual(result["statusCode"], 404)

    def test_unknown_school_and_invalid_configuration(self):
        self.assertEqual(handler({"rawPath": "/v1/schools/unknown/verdict"}, None)["statusCode"], 404)
        with patch.dict(os.environ, {"HAWAHAWAI_SCHOOL_PROFILE_JSON": '{"latitude":91}'}):
            self.assertEqual(self.call("verdict")["statusCode"], 503)

    def test_provider_cache_failure_truthful_insufficient_not_500(self):
        cache, service = Mock(), Mock()
        cache.get.side_effect = CacheError("SIMULATED_OUTAGE")
        service.cache = cache
        service.get.side_effect = CacheError("SIMULATED_OUTAGE")
        with patch("environmental.service.get_service", return_value=service):
            result = self.call("verdict")
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body["decision"], "DATA_INSUFFICIENT")
        self.assertEqual(body["regulatory_status"]["verification_state"], "UNKNOWN")
        self.assertEqual(body["evidence"], [])


if __name__ == "__main__":
    unittest.main()

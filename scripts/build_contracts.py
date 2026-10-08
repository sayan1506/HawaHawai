"""Produce a machine-readable OpenAPI foundation from the agreed Phase 0 contracts."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ref(name):
    return {"$ref": f"#/components/schemas/{name}"}


def obj(properties, required=None):
    return {"type": "object", "additionalProperties": False, "properties": properties,
            "required": list(properties) if required is None else required}


def enum(*values):
    return {"type": "string", "enum": list(values)}


STRING = {"type": "string"}
TIME = {"type": "string", "format": "date-time"}
URI = {"type": "string", "format": "uri"}
ARRAY = lambda item: {"type": "array", "items": item}
NULLABLE = lambda item: {"anyOf": [item, {"type": "null"}]}


def main():
    school = json.loads((ROOT / "contracts/school-profile.schema.json").read_text())
    school.pop("$id", None)
    school.pop("$schema", None)
    schemas = {
        "SchoolProfile": school,
        "Health": obj({"status": {"const": "ok"}, "service": {"const": "hawahawai-backend"}, "environment": STRING, "version": STRING, "phase": {"const": 0}, "timestamp": TIME}),
        "Error": obj({"error": obj({"code": STRING, "message": STRING})}),
        "SourceLocation": obj({"latitude": {"type": "number", "minimum": -90, "maximum": 90}, "longitude": {"type": "number", "minimum": -180, "maximum": 180}, "station_id": NULLABLE(STRING), "distance_km": NULLABLE({"type": "number", "minimum": 0})}),
        "Source": obj({"source_id": STRING, "name": STRING, "url": URI, "kind": enum("measurement", "model_forecast", "official_order"),
                       "observed_at": NULLABLE(TIME), "retrieved_at": TIME, "valid_until": NULLABLE(TIME),
                       "freshness": enum("fresh", "stale", "unknown"), "location": NULLABLE(ref("SourceLocation")), "limitations": ARRAY(STRING)}),
        "Aqi": obj({"value": {"type": "number", "minimum": 0}, "scale": enum("INDIA_AQI", "US_AQI", "EUROPEAN_AQI"), "source_id": STRING, "observed_at": TIME}),
        "Pollutant": obj({"name": enum("pm2_5", "pm10", "no2", "o3", "so2", "co"), "value": {"type": "number", "minimum": 0}, "unit": enum("ug/m3"), "averaging_period": STRING, "source_id": STRING, "observed_at": TIME}),
        "AirReading": obj({"school_id": STRING, "status": enum("available", "stale", "unavailable"), "aqi": ARRAY(ref("Aqi")), "pollutants": ARRAY(ref("Pollutant")), "sources": ARRAY(ref("Source")), "warnings": ARRAY(STRING)}),
        "ForecastPoint": obj({"valid_at": TIME, "aqi": ARRAY(ref("Aqi")), "pollutants": ARRAY(ref("Pollutant"))}),
        "Forecast": obj({"school_id": STRING, "status": enum("available", "stale", "unavailable"), "generated_at": NULLABLE(TIME), "points": ARRAY(ref("ForecastPoint")), "sources": ARRAY(ref("Source")), "warnings": ARRAY(STRING)}),
        "GrapStatus": obj({"status": enum("verified", "VERIFY_STATUS"), "stage": NULLABLE({"type": "integer", "minimum": 0, "maximum": 4}), "effective_from": NULLABLE(TIME), "verified_at": NULLABLE(TIME), "order_url": NULLABLE(URI), "jurisdiction": STRING, "restrictions": ARRAY(STRING), "sources": ARRAY(ref("Source"))}),
        "Action": obj({"activity": enum("assembly", "sports", "physical_education", "other"), "instruction": STRING, "rule_ids": ARRAY(STRING), "evidence_ids": ARRAY(STRING)}),
        "Verdict": obj({"school_id": STRING, "status": enum("decided", "DATA_INSUFFICIENT", "VERIFY_STATUS"), "verdict": NULLABLE(enum("GO_OUTDOORS", "MODIFIED_OUTDOORS", "INDOOR_ONLY")), "generated_at": TIME, "valid_until": TIME, "rule_version": STRING, "rule_ids": ARRAY(STRING), "reasons": ARRAY(STRING), "actions": ARRAY(ref("Action")), "evidence_ids": ARRAY(STRING), "sources": ARRAY(ref("Source")), "warnings": ARRAY(STRING)}),
        "AdvisoryRequest": obj({"verdict_id": STRING, "languages": {"type": "array", "minItems": 1, "uniqueItems": True, "items": enum("en", "hi")}}),
        "Advisory": obj({"school_id": STRING, "verdict_id": STRING, "verdict": NULLABLE(enum("GO_OUTDOORS", "MODIFIED_OUTDOORS", "INDOOR_ONLY")), "generated_at": TIME, "en": STRING, "hi": STRING, "generator": enum("gemini", "groq", "bedrock", "rule_template"), "evidence_ids": ARRAY(STRING), "caveats": ARRAY(STRING)}),
    }
    schemas["Verdict"]["allOf"] = [{"if": {"properties": {"status": {"const": "decided"}}}, "then": {"properties": {"verdict": enum("GO_OUTDOORS", "MODIFIED_OUTDOORS", "INDOOR_ONLY")}}, "else": {"properties": {"verdict": {"type": "null"}}}}]
    schemas["GrapStatus"]["allOf"] = [{"if": {"properties": {"status": {"const": "verified"}}}, "then": {"properties": {"stage": {"type": "integer", "minimum": 0, "maximum": 4}, "verified_at": TIME, "effective_from": TIME, "order_url": URI}}, "else": {"properties": {"stage": {"type": "null"}}}}]
    # Phase 1 retains Phase 0 field names, adding explicit modeled timestamps.
    for name in ("Aqi", "Pollutant"):
        schemas[name]["properties"]["observed_at"] = NULLABLE(TIME)
        schemas[name]["properties"].update({"forecast_for": NULLABLE(TIME), "source_type": enum("measurement", "model_forecast")})
        schemas[name]["required"] += ["forecast_for", "source_type"]
    schemas["Pollutant"]["properties"]["original_unit"] = STRING
    schemas["Pollutant"]["required"].append("original_unit")
    schemas["ObservationProvider"] = obj({"observations": ARRAY(ref("ForecastPoint")), "status": enum("unavailable"), "source_name": STRING, "source_type": enum("measurement"), "source_url": URI, "retrieved_at": TIME, "warnings": ARRAY(STRING)})
    metadata = {"latitude": {"type": "number", "minimum": -90, "maximum": 90}, "longitude": {"type": "number", "minimum": -180, "maximum": 180}, "retrieved_at": NULLABLE(TIME), "freshness_status": enum("fresh", "stale", "unavailable"), "data_quality": enum("modeled_grid_estimate", "unavailable"), "cache": obj({"status": enum("hit", "miss", "refreshed", "stale_fallback"), "fresh_until": NULLABLE(TIME)})}
    for name in ("AirReading", "Forecast"):
        schemas[name]["properties"].update(metadata)
        schemas[name]["required"] += list(metadata)
    schemas["AirReading"]["properties"].update({"observations": ARRAY(ref("ForecastPoint")), "observation_providers": ARRAY(ref("ObservationProvider")), "modeled_current": NULLABLE(ref("ForecastPoint"))})
    schemas["AirReading"]["required"] += ["observations", "observation_providers", "modeled_current"]
    schemas["Forecast"]["properties"].update({"horizon_hours": {"const": 48}, "forecast_start": NULLABLE(TIME), "forecast_end": NULLABLE(TIME)})
    schemas["Forecast"]["required"] += ["horizon_hours", "forecast_start", "forecast_end"]
    schemas["RegulatoryDocument"] = obj({"document_id": STRING, "title": STRING, "authority": STRING, "url": URI,
        "published_on": {"type": "string", "format": "date"}, "document_type": enum("SCHEDULE", "ACTIVATION", "REVOCATION", "SCHOOL_ORDER", "ADVISORY", "PRESS_RELEASE"),
        "access_status": enum("RESEARCHED", "UNAVAILABLE", "HUMAN_REVIEWED"), "sha256": NULLABLE(STRING),
        "effective_from": NULLABLE(TIME), "effective_until": NULLABLE(TIME), "verification_status": enum("HUMAN_REVIEWED", "UNVERIFIED")})
    schemas["Restriction"] = obj({"restriction_id": STRING, "document_id": STRING, "clause": STRING,
        "jurisdiction": {"const": "NCT_DELHI"}, "grades": ARRAY({"type": "integer", "minimum": 0, "maximum": 12}),
        "activity": enum("all", "assembly", "sports", "physical_education", "other", "administration"),
        "action": enum("HYBRID_CLASSES", "SUSPEND_OUTDOOR", "SUSPEND_PHYSICAL_CLASSES", "REVIEW_ORDER", "RESCHEDULE_SPORTS", "AVOID_OUTDOOR_ADVISORY"),
        "mandatory": {"type": "boolean"}, "effective_from": TIME, "effective_until": NULLABLE(TIME),
        "minimum_stage": NULLABLE({"type": "integer", "minimum": 1, "maximum": 4}), "revoked_by": NULLABLE(STRING)})
    extension = {"active_stage": NULLABLE({"type": "integer", "minimum": 1, "maximum": 4}),
        "verification_state": enum("VERIFIED_ACTIVE", "VERIFIED_INACTIVE", "UNKNOWN", "STALE", "CONFLICTING"),
        "verification_expires_at": NULLABLE(TIME), "applicable_restrictions": ARRAY(ref("Restriction")), "unverified_restrictions": ARRAY(ref("Restriction")),
        "source_documents": ARRAY(ref("RegulatoryDocument")), "snapshot_version": STRING, "schedule_version": STRING,
        "evaluation_time": TIME, "verification_action_recorded": {"type": "boolean"}, "next_transition_at": NULLABLE(TIME), "warnings": ARRAY(STRING)}
    schemas["GrapStatus"]["properties"].update(extension)
    schemas["GrapStatus"]["required"] += list(extension)
    action = {"recommendation": enum("VERIFY_BEFORE_PROCEEDING", "NORMAL_WITH_CAVEATS", "MODIFY", "INDOOR_ALTERNATIVE", "ASSESS_INDOOR_ALTERNATIVE", "VERIFY_STATUS", "REVIEW_ORDERS", "HYBRID_CLASSES", "SUSPEND_OUTDOOR", "SUSPEND_PHYSICAL_CLASSES", "REVIEW_ORDER", "RESCHEDULE_SPORTS", "AVOID_OUTDOOR_ADVISORY", "STRUCTURED_REASONS_READY", "REVIEW_SCHOOL_OPERATIONS", "FOLLOW_PHYSICAL_CLASS_ORDER"), "mandatory": {"type": "boolean"}, "applicable_grades": ARRAY({"type": "integer", "minimum": 0, "maximum": 12})}
    schemas["Action"]["properties"]["activity"] = enum("assembly", "sports", "physical_education", "other", "indoor", "administration", "parent_communication")
    schemas["Action"]["properties"].update(action)
    schemas["Action"]["required"] += list(action)
    schemas["RuleEvaluation"] = obj({"rule_id": STRING, "priority": {"type": "integer", "minimum": 1, "maximum": 6}, "message": STRING, "evidence_ids": ARRAY(STRING)})
    schemas["DecisionEvidence"] = obj({"evidence_id": STRING, "kind": enum("station_observation", "modeled_current", "activity_forecast"),
        "freshness": {"const": "fresh"}, "value": {"type": "number", "minimum": 0, "maximum": 500}, "scale": {"const": "US_AQI"},
        "source_id": STRING, "source_type": enum("measurement", "model_forecast"), "timestamp": TIME,
        "pollutants": ARRAY(ref("Pollutant")), "station_location": NULLABLE(ref("SourceLocation"))})
    schemas["PolicySource"] = obj({"evidence_id": STRING, "title": STRING, "url": URI, "authority": STRING, "published_on": NULLABLE(STRING), "scope": STRING})
    extension = {"decision": enum("GO_OUTDOORS", "MODIFIED_OUTDOORS", "INDOOR_ONLY", "DATA_INSUFFICIENT"),
        "evaluation_time": TIME, "policy_version": STRING, "decision_id": STRING,
        "regulatory_status": ref("GrapStatus"), "rule_evaluations": ARRAY(ref("RuleEvaluation")),
        "evidence": ARRAY(ref("DecisionEvidence")), "policy_sources": ARRAY(ref("PolicySource")),
        "requires_regulatory_verification": {"type": "boolean"},
        "data_quality": obj({"official_observations_available": {"type": "boolean"}, "station_observations_available": {"type": "boolean"},
            "modeled_data_available": {"type": "boolean"}, "forecast_available": {"type": "boolean"}, "current_freshness": STRING, "forecast_freshness": STRING}),
        "activity_context": obj({"jurisdiction": {"const": "NCT_DELHI"}, "grade": NULLABLE({"type": "integer", "minimum": 0, "maximum": 12}),
            "activity": enum("all", "assembly", "sports", "physical_education", "other", "indoor"), "window_start": TIME, "window_end": TIME})}
    schemas["Verdict"]["properties"].update(extension)
    schemas["Verdict"]["required"] += list(extension)
    schemas["VerdictPersistence"] = obj({"status": enum("stored", "reused", "repaired", "unavailable", "corrupt", "busy"),
        "storage_version": {"const": "verdict-record-v1"}, "record_id": NULLABLE({"type": "string", "pattern": "^[a-f0-9]{64}$"}), "historical": {"const": False}})
    schemas["Verdict"]["properties"]["persistence"] = ref("VerdictPersistence")
    schemas["VerdictRecord"] = obj({"storage_version": {"const": "verdict-record-v1"}, "school_id": {"const": "delhi-demo-school"},
        "record_id": {"type": "string", "pattern": "^[a-f0-9]{64}$"}, "profile_fingerprint": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "semantic_fingerprint": {"type": "string", "pattern": "^[a-f0-9]{64}$"}, "context": obj({k:v for k,v in extension["activity_context"]["properties"].items() if k not in {"window_start","window_end"}}),
        "local_date": {"type": "string", "format": "date"}, "origin": enum("ON_DEMAND", "SCHEDULED"), "decision": ref("Verdict"), "created_at": TIME})
    schemas["VerdictHistory"] = obj({"school_id": STRING, "status": {"const": "historical"}, "actionable": {"const": False},
        "retrieved_at": TIME, "expired": {"type": "boolean"}, "matches_current_profile": {"type": "boolean"}, "record": ref("VerdictRecord")})
    localized = json.loads(json.dumps(schemas["Action"]))
    localized["properties"].update(en=STRING, hi=STRING)
    localized["required"] += ["en", "hi"]
    schemas["LocalizedAction"] = localized
    advisory_extension = {"school_name": STRING, "decision": extension["decision"], "valid_until": TIME,
        "languages": {"const": ["en", "hi"]}, "explanation_method": enum("AI", "DETERMINISTIC"),
        "explanation_version": STRING, "generation_scope": {"const": "approved_statement_ordering"},
        "statement_ids": ARRAY(STRING), "authoritative_decision": ref("Verdict"), "actions": ARRAY(ref("LocalizedAction")),
        "evidence": ARRAY(ref("DecisionEvidence")), "sources": ARRAY({"anyOf": [ref("Source"), ref("PolicySource"), ref("RegulatoryDocument")]}),
        "regulatory_status": ref("GrapStatus"), "data_quality": extension["data_quality"], "cache": obj({"status": enum("hit", "miss")})}
    advisory_extension.update(observations=ARRAY(ref("DecisionEvidence")), modeled_conditions=ARRAY(ref("DecisionEvidence")),
        forecast_summary=obj({"scope": STRING, "points": ARRAY(ref("DecisionEvidence")), "available": {"type": "boolean"}}))
    schemas["Advisory"]["properties"].update(advisory_extension)
    schemas["Advisory"]["required"] += list(advisory_extension)
    paths = {}
    for path, name in [("/health", "Health"), ("/v1/schools/{school_id}", "SchoolProfile"), ("/v1/schools/{school_id}/air", "AirReading"), ("/v1/schools/{school_id}/forecast", "Forecast"), ("/v1/grap", "GrapStatus"), ("/v1/schools/{school_id}/grap", "GrapStatus"), ("/v1/schools/{school_id}/verdict", "Verdict"), ("/v1/schools/{school_id}/advisory", "Advisory")]:
        planned = path == "/v1/grap"
        operation = {"operationId": f"get{name}", "x-implemented": not planned,
                     "description": "Planned contract only; not deployed." if planned else "Phase 0/1-compatible evidence or Phase 2 read-only deterministic policy.",
                     "responses": {"200": {"description": name, "content": {"application/json": {"schema": ref(name)}}}, "404": {"description": "Not found", "content": {"application/json": {"schema": ref("Error")}}}}}
        if "{school_id}" in path:
            operation["parameters"] = [{"name": "school_id", "in": "path", "required": True, "schema": school["properties"]["school_id"]}]
            if name in {"GrapStatus", "Verdict", "Advisory"} and not planned:
                operation["parameters"] += [{"name": "grade", "in": "query", "schema": {"type": "integer", "minimum": 0, "maximum": 12}}, {"name": "activity", "in": "query", "schema": extension["activity_context"]["properties"]["activity"]}]
        paths[path] = {"get": operation}
        if not planned:
            operation["responses"]["400"] = {"description": "Invalid request", "content": {"application/json": {"schema": ref("Error")}}}
            operation["responses"]["503"] = {"description": "Unavailable evidence or cache", "content": {"application/json": {"schema": {"anyOf": [ref(name), ref("Error")]}}}}
    paths["/v1/schools/{school_id}/advisory"]["post"] = {
        "operationId": "generateAdvisory", "x-implemented": True, "description": "Phase 3: bounded bilingual explanation; supplied verdict_id must match current trusted evaluation. Both languages are returned.",
        "parameters": paths["/v1/schools/{school_id}/advisory"]["get"]["parameters"],
        "requestBody": {"required": True, "content": {"application/json": {"schema": ref("AdvisoryRequest")}}},
        "responses": {"200": {"description": "Bilingual advisory", "content": {"application/json": {"schema": ref("Advisory")}}}, **{str(code): {"description": "Invalid, stale, unknown or unavailable request", "content": {"application/json": {"schema": ref("Error")}}} for code in (400,404,409,503)}},
    }
    paths["/v1/schools/{school_id}/verdict/history"] = {"get": {"operationId": "getVerdictHistory", "x-implemented": True,
        "description": "Retained daily/identified historical planning record. Never actionable current guidance.",
        "parameters": paths["/v1/schools/{school_id}/verdict"]["get"]["parameters"] + [
            {"name": "date", "in": "query", "schema": {"type": "string", "format": "date"}},
            {"name": "record_id", "in": "query", "schema": {"type": "string", "pattern": "^[a-f0-9]{64}$"}}],
        "responses": {"200": {"description": "Historical only", "content": {"application/json": {"schema": ref("VerdictHistory")}}},
            **{str(code): {"description": "Invalid, missing or unavailable", "content": {"application/json": {"schema": ref("Error")}}} for code in (400,404,503)}}}}
    document = {"openapi": "3.1.0", "info": {"title": "HawaHawai API contracts", "version": "0.4.0", "description": "Phase 4: persisted school and verdict history. Current requests always revalidate Phase 2 authority; no public force-refresh or administrative mutation."}, "paths": paths, "components": {"schemas": schemas}}
    target = ROOT / "contracts/openapi.json"
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

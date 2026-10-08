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
    paths = {}
    for path, name in [("/health", "Health"), ("/v1/schools/{school_id}", "SchoolProfile"), ("/v1/schools/{school_id}/air", "AirReading"), ("/v1/schools/{school_id}/forecast", "Forecast"), ("/v1/grap", "GrapStatus"), ("/v1/schools/{school_id}/verdict", "Verdict"), ("/v1/schools/{school_id}/advisory", "Advisory")]:
        planned = name not in {"Health", "SchoolProfile", "AirReading", "Forecast"}
        operation = {"operationId": f"get{name}", "x-implemented": not planned,
                     "description": "Planned contract only; not deployed." if planned else "Phase 1 environmental evidence or Phase 0 liveness; no school-safety verdict.",
                     "responses": {"200": {"description": name, "content": {"application/json": {"schema": ref(name)}}}, "404": {"description": "Not found", "content": {"application/json": {"schema": ref("Error")}}}}}
        if "{school_id}" in path:
            operation["parameters"] = [{"name": "school_id", "in": "path", "required": True, "schema": school["properties"]["school_id"]}]
        paths[path] = {"get": operation}
        if not planned:
            operation["responses"]["400"] = {"description": "Invalid request", "content": {"application/json": {"schema": ref("Error")}}}
            operation["responses"]["503"] = {"description": "Unavailable evidence or cache", "content": {"application/json": {"schema": {"anyOf": [ref(name), ref("Error")]}}}}
    paths["/v1/schools/{school_id}/advisory"]["post"] = {
        "operationId": "generateAdvisory", "x-implemented": False, "description": "Planned for Phase 3/4. Explains a persisted, current deterministic verdict.",
        "parameters": paths["/v1/schools/{school_id}/advisory"]["get"]["parameters"],
        "requestBody": {"required": True, "content": {"application/json": {"schema": ref("AdvisoryRequest")}}},
        "responses": {"200": {"description": "Bilingual advisory", "content": {"application/json": {"schema": ref("Advisory")}}}},
    }
    document = {"openapi": "3.1.0", "info": {"title": "HawaHawai API contracts", "version": "0.1.0", "description": "Phase 1: health, pilot school, modeled current evidence and forecast implemented. Official station observations unavailable. Safety and advisory routes remain planned."}, "paths": paths, "components": {"schemas": schemas}}
    target = ROOT / "contracts/openapi.json"
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

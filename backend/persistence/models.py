import hashlib
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from datetime import timezone, timedelta
from jsonschema import Draft202012Validator, FormatChecker
from safety.models import instant, ActivityContext

PILOT = "delhi-demo-school"
STORAGE_VERSION = "verdict-record-v1"
PROFILE_VERSION = "school-profile-v1"
IST = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

def contracts_directory():
    bundled = Path(__file__).resolve().parents[1] / "contracts"
    return bundled if bundled.exists() else Path(__file__).resolve().parents[2] / "contracts"

@lru_cache(maxsize=1)
def contracts():
    return json.loads((contracts_directory() / "openapi.json").read_text(encoding="utf-8"))

def validate(name, value):
    document = contracts()
    schema = {"$ref": "#/components/schemas/" + name, "components": document["components"]}
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)

def validate_profile(profile):
    from environmental.config import coordinates
    coordinates(profile.get('latitude'), profile.get('longitude'))
    validate("SchoolProfile", profile)
    if profile["school_id"] != PILOT or profile["city"] != "New Delhi": raise ValueError("Only the configured NCT Delhi pilot is permitted")
    return profile

def profile_key(): return "school#" + PILOT + "#profile"

def profile_record(profile, initialized_at):
    validate_profile(profile)
    instant(initialized_at)
    return {"storage_version": PROFILE_VERSION, "profile": deepcopy(profile), "profile_fingerprint": digest(profile), "initialized_at": initialized_at}

def read_profile(cache):
    record = cache.get(profile_key())
    if not isinstance(record, dict) or set(record) != {"storage_version", "profile", "profile_fingerprint", "initialized_at"} or record["storage_version"] != PROFILE_VERSION:
        raise RuntimeError("SCHOOL_CONFIGURATION_UNAVAILABLE")
    try:
        profile = validate_profile(record["profile"])
        instant(record["initialized_at"])
        if digest(profile) != record["profile_fingerprint"]: raise ValueError("Profile fingerprint mismatch")
    except Exception:
        raise RuntimeError("SCHOOL_CONFIGURATION_INVALID") from None
    return profile

def context_identity(context): return {"jurisdiction": context.jurisdiction, "grade": context.grade, "activity": context.activity}
def context_key(context): return digest(context_identity(context))[:16]

def semantic_fingerprint(decision, school=None, profile_hash=None):
    data = json.loads(json.dumps(decision))
    for key in ("generated_at", "evaluation_time", "valid_until", "persistence"): data.pop(key, None)
    data["activity_context"] = {k: v for k, v in data["activity_context"].items() if k not in {"window_start", "window_end"}}
    data["regulatory_status"].pop("evaluation_time", None)
    return digest({"profile": digest(school) if school is not None else profile_hash, "decision": data})

def make_record(school, decision, origin="ON_DEMAND"):
    validate_profile(school)
    data = {k: v for k, v in decision.items() if k != "persistence"}
    validate("Verdict", data)
    stamp = instant(data["evaluation_time"])
    identity = context_identity(ActivityContext(**{k: data["activity_context"][k] for k in ("jurisdiction", "grade", "activity")}))
    fingerprint = semantic_fingerprint(data, school)
    record = {"storage_version": STORAGE_VERSION, "school_id": school["school_id"], "profile_fingerprint": digest(school),
              "semantic_fingerprint": fingerprint, "context": identity, "local_date": stamp.astimezone(IST).date().isoformat(),
              "origin": origin, "decision": data, "created_at": stamp.isoformat()}
    record["record_id"] = digest({"fingerprint": fingerprint, "bucket": int(stamp.timestamp()) // 300, "origin": origin})
    return record

def validate_record(record, school_id=PILOT, context=None):
    validate("VerdictRecord", record)
    decision = record["decision"]
    if "persistence" in decision: raise ValueError("Historical decisions cannot contain current persistence metadata")
    evaluated, expires = instant(decision["evaluation_time"]), instant(decision["valid_until"])
    if record["school_id"] != school_id or decision["school_id"] != school_id or not evaluated < expires <= evaluated + timedelta(minutes=5):
        raise ValueError("Invalid record identity or validity")
    if record["created_at"] != evaluated.isoformat() or record["local_date"] != evaluated.astimezone(IST).date().isoformat(): raise ValueError("Invalid record dates")
    expected_context = {k: decision["activity_context"][k] for k in ("jurisdiction", "grade", "activity")}
    ActivityContext(**expected_context)
    if expected_context != record["context"] or (context is not None and record["context"] != context_identity(context)): raise ValueError("Record context mismatch")
    expected_id = digest({"fingerprint": record["semantic_fingerprint"], "bucket": int(evaluated.timestamp()) // 300, "origin": record["origin"]})
    if record["record_id"] != expected_id: raise ValueError("Record ID mismatch")
    if record["semantic_fingerprint"] != semantic_fingerprint(decision, profile_hash=record["profile_fingerprint"]): raise ValueError("Record integrity mismatch")
    return record

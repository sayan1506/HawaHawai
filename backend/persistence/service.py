"""Always compare with a newly evaluated Phase 2 decision before current reuse."""
import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from safety.models import ActivityContext, instant
from .models import PILOT, STORAGE_VERSION, digest, context_key, make_record, validate_record, semantic_fingerprint, IST

LOG = logging.getLogger("hawahawai.storage")
LOG.setLevel(logging.INFO)
def prefix(): return PILOT + "#verdict#"
def current_key(context): return prefix() + "current#" + context_key(context)
def history_key(record_id): return prefix() + "history#" + record_id
def daily_key(date, context): return prefix() + "daily#" + date + "#" + context_key(context)

def attach(decision, status, record=None):
    result = deepcopy(decision)
    result["persistence"] = {"status": status, "storage_version": STORAGE_VERSION, "record_id": record["record_id"] if record else None, "historical": False}
    if status in {"unavailable", "corrupt", "busy"}:
        result["warnings"] = list(dict.fromkeys(result["warnings"] + ["VERDICT_STORAGE_" + status.upper() + ": current result was freshly evaluated, not loaded as authority."]))
    return result

def persist(school, cache, fresh, context=None, origin="ON_DEMAND", now=None):
    context = context or ActivityContext()
    now = instant(now) if now else datetime.now(timezone.utc)
    lease, token = current_key(context) + "#lease", None
    try:
        pointer = cache.get(current_key(context))
        invalid = False
        if pointer and origin == "ON_DEMAND":
            try:
                stored = validate_record(cache.get(history_key(pointer["record_id"])), school["school_id"], context)
                if (stored["profile_fingerprint"] == digest(school) and stored["semantic_fingerprint"] == semantic_fingerprint(fresh, school) and
                    stored["semantic_fingerprint"] == semantic_fingerprint(stored["decision"], school) and
                    instant(stored["decision"]["evaluation_time"]) <= now < instant(stored["decision"]["valid_until"]) <= instant(fresh["valid_until"])):
                    return attach(stored["decision"], "reused", stored)
            except Exception: invalid = True
        token = cache.acquire(lease, now.timestamp())
        if not token: return attach(fresh, "busy")
        record = make_record(school, fresh, origin)
        validate_record(record, school["school_id"], context)
        if not cache.put_record(history_key(record["record_id"]), record):
            stored = validate_record(cache.get(history_key(record["record_id"])), school["school_id"], context)
            if (stored["semantic_fingerprint"] != semantic_fingerprint(fresh, school) or
                not instant(stored["decision"]["evaluation_time"]) <= now < instant(stored["decision"]["valid_until"]) <= instant(fresh["valid_until"])):
                return attach(fresh, "corrupt")
            record = stored
        revision = int(instant(record["created_at"]).timestamp() * 1_000_000)
        pointer = {"storage_version": STORAGE_VERSION, "record_id": record["record_id"], "revision_epoch": revision}
        if not cache.put_record(current_key(context), pointer, revision):
            existing = cache.get(current_key(context))
            # Retry after a lost job-receipt acknowledgement may already have
            # published this exact immutable record. Do not renew its timestamps.
            same = existing == pointer
            newer_planning = (origin == "SCHEDULED" and isinstance(existing, dict) and
                              existing.get("storage_version") == STORAGE_VERSION and
                              isinstance(existing.get("revision_epoch"), int) and existing["revision_epoch"] > revision)
            if not (same or newer_planning): return attach(fresh, "busy")
        cache.put_record(daily_key(record["local_date"], context), pointer, revision if origin == "SCHEDULED" else None)
        LOG.info(json.dumps({"event": "verdict_persisted", "record_id": record["record_id"], "origin": origin}))
        return attach(record["decision"], "repaired" if invalid else "stored", record)
    except Exception:
        LOG.warning(json.dumps({"event": "verdict_storage_unavailable"}))
        return attach(fresh, "unavailable")
    finally:
        if token: cache.release(lease, token)

def historical(school, cache, context=None, date=None, record_id=None, now=None):
    context = context or ActivityContext()
    now = instant(now) if now else datetime.now(timezone.utc)
    if record_id:
        record = cache.get(history_key(record_id))
    else:
        date = date or now.astimezone(IST).date().isoformat()
        pointer = cache.get(daily_key(date, context))
        if pointer:
            if not isinstance(pointer, dict) or pointer.get("storage_version") != STORAGE_VERSION or not isinstance(pointer.get("record_id"), str):
                raise RuntimeError("HISTORICAL_POINTER_INVALID")
            record = cache.get(history_key(pointer["record_id"]))
        else: record = None
    if not record: return None
    try: validate_record(record, school["school_id"], context)
    except Exception: raise RuntimeError("HISTORICAL_RECORD_INVALID") from None
    return {"school_id": school["school_id"], "status": "historical", "actionable": False, "retrieved_at": now.isoformat(),
            "expired": instant(record["decision"]["valid_until"]) <= now, "matches_current_profile": record["profile_fingerprint"] == digest(school), "record": record}

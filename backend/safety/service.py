"""IO boundary: read registry + reuse Phase 1 evidence, then call the pure engine."""
from .models import ActivityContext, instant
from .registry import read_snapshot, resolve
from .engine import evaluate
from environmental.cache import CacheError
from datetime import datetime, timezone


def regulatory_status(school, evaluation_time, context, cache=None):
    if school["city"] != "New Delhi":
        raise RuntimeError("PILOT_JURISDICTION_REQUIRES_VERIFICATION")
    try:
        return resolve(read_snapshot(cache), evaluation_time, context)
    except (ValueError, OSError, TypeError, KeyError, CacheError):
        # A corrupt/missing registry never degrades to a stage from configuration.
        status = resolve(read_snapshot(), evaluation_time, context)
        status["warnings"].append("REGISTRY_READ_FAILED: regulatory storage or snapshot is invalid; verify status.")
        return status


def verdict(school, environmental_service, evaluation_time=None, context=None):
    context = context or ActivityContext()
    inputs = []
    for kind in ("current", "forecast"):
        try:
            inputs.append(environmental_service.get(school, kind))
        except (CacheError, RuntimeError, ValueError, TypeError):
            inputs.append({"school_id": school["school_id"], "status": "unavailable", "freshness_status": "unavailable", "sources": [], "observations": [], "points": [], "warnings": ["ENVIRONMENT_UNAVAILABLE: " + kind]})
    # The IO boundary captures time AFTER fetching, so a cold refresh is not
    # incorrectly rejected as evidence retrieved in the evaluator's future.
    now = instant(evaluation_time) if evaluation_time is not None else datetime.now(timezone.utc)
    regulatory = regulatory_status(school, now, context, environmental_service.cache)
    return evaluate(school, *inputs, regulatory, now, context)

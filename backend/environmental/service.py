import copy
import hashlib
import json
import logging
import os
import time
from datetime import datetime
from .cache import CacheError, DynamoCache, MemoryCache
from .http import ProviderError
from .providers import IndianObservationProvider, OpenAQObservationProvider, OpenMeteoProvider, stamp

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)
CURRENT_FRESH_SECONDS = 900
FORECAST_FRESH_SECONDS = 3600
MAX_STALE_SECONDS = 21600
OBSERVATION_UNAVAILABLE_SECONDS = 300


def cache_prefix(school):
    location = json.dumps([school["latitude"], school["longitude"]], separators=(",", ":"))
    return school["school_id"] + "#" + hashlib.sha256(location.encode()).hexdigest()[:12]


class EnvironmentalService:
    def __init__(self, cache, provider=None, clock=time.time):
        self.cache, self.provider, self.clock = cache, provider or OpenMeteoProvider(), clock

    def get(self, school, kind):
        now = self.clock()
        prefix = cache_prefix(school)
        key = prefix + "#" + kind
        cached = self.cache.get(key)
        state, warning = "miss", None
        if cached and cached["fresh_until"] > now and cached["fetched_at"] <= now:
            state = "hit"
        else:
            cooldown = self.cache.get(prefix + "#cooldown")
            token = None
            if cooldown and cooldown["until"] > now:
                warning = cooldown["code"]
            else:
                token = self.cache.acquire(prefix + "#lock", now)
                if token:
                    try:
                        # Verification is private, short-lived, and removed in final deployment.
                        if os.environ.get("HAWAHAWAI_VERIFICATION_ENABLED") == "true":
                            fault = self.cache.get("verification#" + school["school_id"])
                            if fault and fault.get("until", 0) > now and fault.get("code") in {"TIMEOUT", "RATE_LIMITED"}:
                                raise ProviderError("VERIFICATION_" + fault["code"], 90)
                        bundle = self.provider.fetch(school, now)
                        for part, ttl in (("current", CURRENT_FRESH_SECONDS), ("forecast", FORECAST_FRESH_SECONDS)):
                            item = {"fetched_at": now, "fresh_until": now + ttl, "data": bundle[part]}
                            self.cache.put(prefix + "#" + part, item)
                            if part == kind:
                                cached = item
                        state = "refreshed"
                    except ProviderError as error:
                        warning = error.code
                        self.cache.put(prefix + "#cooldown", {"until": now + error.retry_after, "code": error.code})
                    finally:
                        self.cache.release(prefix + "#lock", token)
                else:
                    warning = "REFRESH_IN_PROGRESS"
            if warning:
                state = "stale_fallback"
        LOG.info(json.dumps({"event": "environmental_cache", "kind": kind, "cache_status": state, "error_code": warning}))
        usable = cached and 0 <= now - cached["fetched_at"] <= MAX_STALE_SECONDS
        data = copy.deepcopy(cached["data"]) if usable else {"sources": [], "warnings": [], "retrieved_at": None, "data_quality": "unavailable", "point": None, "points": [], "generated_at": None}
        fresh = usable and cached["fresh_until"] > now and not warning
        for source in data["sources"]:
            source["freshness"] = "fresh" if fresh else "stale"
        warnings = data["warnings"] + (["LIVE_REFRESH_FAILED: " + warning] if warning else [])
        common = {"school_id": school["school_id"], "latitude": school["latitude"], "longitude": school["longitude"], "sources": data["sources"], "warnings": warnings, "retrieved_at": data["retrieved_at"], "freshness_status": "fresh" if fresh else "stale" if usable else "unavailable", "data_quality": data["data_quality"], "cache": {"status": state, "fresh_until": stamp(cached["fresh_until"]) if usable else None}, "status": "available" if fresh else "stale" if usable else "unavailable"}
        if kind == "current":
            observations = self.cache.get(prefix + "#observations")
            if not observations or observations["until"] <= now:
                observations = {"until": now + OBSERVATION_UNAVAILABLE_SECONDS, "providers": [IndianObservationProvider().fetch(school, now), OpenAQObservationProvider().fetch(school, now)]}
                self.cache.put(prefix + "#observations", observations)
            point = data.get("point")
            if point:
                age = now - datetime.fromisoformat(point["valid_at"]).timestamp()
                if age > 10800 or age < -900:
                    common["warnings"].append("MODELED_CURRENT_OUT_OF_DATE")
                    common["status"] = "unavailable"
                    common["freshness_status"] = "unavailable"
                    point = None
                elif age > CURRENT_FRESH_SECONDS:
                    common["warnings"].append("MODELED_CURRENT_TIMESTAMP_STALE: model timestamp exceeds 15-minute freshness policy.")
                    common["status"] = "stale"
                    common["freshness_status"] = "stale"
                    for source in common["sources"]:
                        source["freshness"] = "stale"
            if not point:
                common["status"] = "unavailable"
                common["freshness_status"] = "unavailable"
            common.update({"observations": [], "observation_providers": observations["providers"], "modeled_current": point, "aqi": point["aqi"] if point else [], "pollutants": point["pollutants"] if point else []})
            common["warnings"] += [w for p in observations["providers"] for w in p["warnings"]]
        else:
            points = [p for p in data.get("points", []) if datetime.fromisoformat(p["valid_at"]).timestamp() >= now][:48]
            if len(points) != 48:
                common["status"] = "unavailable"
                common["freshness_status"] = "unavailable"
                common["warnings"].append("FULL_48_HOUR_FORECAST_UNAVAILABLE")
                points = []
            common.update({"points": points, "generated_at": None, "horizon_hours": 48, "forecast_start": points[0]["valid_at"] if points else None, "forecast_end": points[-1]["valid_at"] if points else None})
        return common


_SERVICE = None


def get_service():
    global _SERVICE
    if _SERVICE is None:
        table = os.environ.get("HAWAHAWAI_CACHE_TABLE")
        _SERVICE = EnvironmentalService(DynamoCache(table) if table else MemoryCache())
    return _SERVICE

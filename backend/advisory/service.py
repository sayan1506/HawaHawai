import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from environmental.cache import CacheError
from safety.service import verdict
from safety.models import instant, ActivityContext
from agent.explanations import EXPLANATION_VERSION, render, validate_plan
from agent.runtime import generate, LOG

_secret = None
_secret_until = 0

def credentials():
    global _secret, _secret_until
    arn = os.environ.get("HAWAHAWAI_AI_SECRET_ARN")
    if not arn:
        return {k: os.environ.get(k, "") for k in ("GEMINI_API_KEY", "GROQ_API_KEY")}
    if _secret is not None and time.monotonic() < _secret_until:
        return dict(_secret)
    try:
        import boto3
        from botocore.config import Config
        session = boto3.Session(profile_name=None if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else "hawahawai", region_name="us-east-1")
        value = json.loads(session.client("secretsmanager", config=Config(connect_timeout=1, read_timeout=2, retries={"total_max_attempts": 1})).get_secret_value(SecretId=arn)["SecretString"])
        _secret = {k: value.get(k, "") for k in ("GEMINI_API_KEY", "GROQ_API_KEY")}
    except Exception:
        _secret = {}
    _secret_until = time.monotonic() + 60  # Bounded credential-error cooldown; never log secret material.
    return dict(_secret)

class PinnedEnvironment:
    def __init__(self, service):
        self.service, self.cache, self.inputs = service, service.cache, {}
    def get(self, school, kind):
        if kind not in self.inputs:
            self.inputs[kind] = self.service.get(school, kind)
        return deepcopy(self.inputs[kind])

def fingerprint(decision):
    regulation = {k: v for k, v in decision["regulatory_status"].items() if k != "evaluation_time"}
    return hashlib.sha256(json.dumps({"decision_id": decision["decision_id"], "version": EXPLANATION_VERSION,
        "quality": decision["data_quality"], "warnings": decision["warnings"], "actions": decision["actions"],
        "regulation": regulation, "sources": decision["sources"]}, sort_keys=True).encode()).hexdigest()

def explain(school, service, context=None, lambda_context=None, requested_verdict=None, generator=generate, keys=None):
    LOG.info(json.dumps({"event": "advisory_stage", "stage": "start"}))
    context = context or ActivityContext()
    pinned = PinnedEnvironment(service)
    decision = verdict(school, pinned, context=context)
    LOG.info(json.dumps({"event": "advisory_stage", "stage": "evidence_ready"}))
    if requested_verdict is not None and requested_verdict != decision["decision_id"]:
        raise ValueError("STALE_VERDICT")
    digest = fingerprint(decision)
    key = school["school_id"] + "#advisory#" + digest
    now = datetime.now(timezone.utc)
    warnings, plan, provider, cached = [], None, "rule_template", None
    try:
        cached = service.cache.get(key)
    except CacheError:
        warnings.append("EXPLANATION_CACHE_UNAVAILABLE")
    if cached:
        try:
            if instant(cached["fresh_until"]) > now:
                if cached["provider"] not in {"gemini", "groq", "rule_template"} or bool(cached["plan"]) != (cached["provider"] != "rule_template"):
                    raise ValueError("Invalid cache method")
                plan = validate_plan(cached["plan"], decision) if cached["plan"] else None
                return render(school, decision, plan, cached["provider"], cached["generated_at"], cached["warnings"], "hit")
        except (ValueError, KeyError, TypeError):
            warnings.append("INVALID_CACHED_EXPLANATION")
    budget = min(10, (instant(decision["valid_until"]) - now).total_seconds() - 1)
    if lambda_context is not None and hasattr(lambda_context, "get_remaining_time_in_millis"):
        budget = min(budget, lambda_context.get_remaining_time_in_millis()/1000 - 3)
    acquired = False
    try:
        acquired = service.cache.acquire(key + "#lease", now.timestamp())
    except CacheError:
        warnings.append("EXPLANATION_CACHE_UNAVAILABLE")
    if acquired and budget >= 2:
        snapshot = {"school": school, "decision": decision,
            "current": pinned.inputs.get("current", {"status": "unavailable", "observations": []}),
            "forecast": pinned.inputs.get("forecast", {"status": "unavailable", "points": []})}
        try:
            available_keys = credentials() if keys is None else keys
            LOG.info(json.dumps({"event": "advisory_stage", "stage": "credentials_ready", "remaining_ms": lambda_context.get_remaining_time_in_millis() if lambda_context is not None else None}))
            if not any(available_keys.values()):
                warnings.append("AI_NOT_CONFIGURED_DETERMINISTIC_EXPLANATION")
            elif service.cache.acquire(school["school_id"] + "#advisory#provider-window", now.timestamp()):
                # Intentionally retain this 30-second lease until expiration:
                # it bounds aggregate calls across all grade/activity variants.
                plan, provider, failures = generator(snapshot, available_keys, budget=budget)
                if plan: validate_plan(plan.model_dump_json(), decision)
                warnings.extend(failures)
            else:
                warnings.append("AI_SCHOOL_COOLDOWN_DETERMINISTIC_EXPLANATION")
        except Exception:
            plan, provider = None, "rule_template"
            warnings.append("AI_OUTPUT_REJECTED")
    else:
        warnings.append("AI_BUSY_OR_INSUFFICIENT_TIME_DETERMINISTIC_EXPLANATION")
    # Always re-evaluate trusted inputs after AI. A slow model cannot preserve an expired verdict.
    if os.environ.get('HAWAHAWAI_PROFILE_STORAGE_REQUIRED') == 'true':
        from environmental.config import school_profile
        school = school_profile(service.cache)
    latest = verdict(school, service, context=context)
    if fingerprint(latest) != digest or instant(decision["valid_until"]) <= datetime.now(timezone.utc):
        plan, provider = None, "rule_template"
        warnings.append("EVIDENCE_CHANGED_DURING_GENERATION")
    decision = latest
    generated_at = datetime.now(timezone.utc).isoformat()
    if fingerprint(latest) == digest and acquired:
        fresh_until = min(instant(decision["valid_until"]), datetime.now(timezone.utc) + timedelta(seconds=60 if plan is None else 300))
        try:
            service.cache.put(key, {"fresh_until": fresh_until.isoformat(), "plan": plan.model_dump_json() if plan else None,
                "provider": provider, "generated_at": generated_at, "warnings": warnings})
        except CacheError: warnings.append("EXPLANATION_CACHE_UNAVAILABLE")
    if acquired:
        service.cache.release(key + "#lease", acquired)
    return render(school, decision, plan, provider, generated_at, warnings, "miss")

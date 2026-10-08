"""Bounded real Strands execution. No model prose crosses the safety boundary."""
import asyncio
import json
import logging
import os
import time
from copy import deepcopy
from .providers import create_model
from .explanations import ExplanationPlan, catalog, validate_plan

LOG = logging.getLogger("hawahawai.ai")
LOG.setLevel(logging.INFO)
TOOLS = ("get_air_quality", "get_air_forecast", "get_grap_status", "get_school_safety_decision")

def trusted_tools(snapshot):
    from strands import tool
    @tool
    def get_air_quality() -> dict:
        """Return trusted Phase 1 conditions, with source, timestamps and limitations."""
        data = snapshot["current"]
        # Do not send duplicated compatibility aliases to the model.
        return {k: deepcopy(v) for k, v in data.items() if k in {"school_id", "status", "freshness_status", "retrieved_at", "observations", "modeled_current", "sources", "warnings"}}
    @tool
    def get_air_forecast() -> dict:
        """Return dated trusted forecast evidence for the activity window and 48-hour bounds."""
        data = snapshot["forecast"]
        return {k: deepcopy(v[:3] if k == "points" else v) for k, v in data.items()}
    @tool
    def get_grap_status() -> dict:
        """Return trusted Phase 2 regulatory verification; never infer a stage."""
        return deepcopy(snapshot["decision"]["regulatory_status"])
    @tool
    def get_school_safety_decision() -> dict:
        """Return the authoritative Phase 2 decision. It cannot be overridden."""
        d = snapshot["decision"]
        # Evidence values are already supplied by the environmental tools; the
        # decision tool supplies their references rather than duplicating arrays.
        return {k: deepcopy(d[k]) for k in ("decision_id", "decision", "policy_version", "rule_evaluations", "actions", "warnings", "data_quality", "evidence_ids", "valid_until")}
    return [get_air_quality, get_air_forecast, get_grap_status, get_school_safety_decision]

async def invoke_strands(provider, credentials, snapshot, timeout):
    setup_started = time.monotonic()
    LOG.info(json.dumps({"event": "ai_stage", "stage": "sdk_import_start"}))
    from strands import Agent
    LOG.info(json.dumps({"event": "ai_stage", "stage": "sdk_import_done", "elapsed_ms": round((time.monotonic()-setup_started)*1000)}))
    model = create_model(provider, credentials, timeout)
    agent = Agent(model=model, tools=trusted_tools(snapshot), callback_handler=None, retry_strategy=None,
        context_manager=False, load_tools_from_directory=False,
        system_prompt="You organize approved bilingual school explanations. The deterministic decision is immutable. Return only a JSON plan, no prose, no markdown. Do not call additional tools: all four trusted tools have already been invoked. Include every approved statement exactly once, with verdict first. Never invent data, orders, URLs or actions.")
    # Direct SDK tool calls are recorded in the real agent's conversation before generation.
    for name in TOOLS:
        result = getattr(agent.tool, name)()
        if result.get("status") == "error":
            raise ValueError("TRUSTED_TOOL_FAILED")
    timeout -= time.monotonic() - setup_started
    if timeout < 1: raise TimeoutError("AI_SETUP_EXHAUSTED_BUDGET")
    LOG.info(json.dumps({"event": "ai_stage", "stage": "tools_ready", "elapsed_ms": round((time.monotonic()-setup_started)*1000)}))
    d = snapshot["decision"]
    expected = {"decision_id": d["decision_id"], "decision": d["decision"], "regulatory_state": d["regulatory_status"]["verification_state"], "statement_ids": list(catalog(d))}
    prompt = json.dumps({"school_name": snapshot["school"]["name"], "task": "Prioritize these approved statements for principals and parents. Output this schema with exactly these assertions and statement IDs; reorder statements only.", "schema": ExplanationPlan.model_json_schema(), "approved": catalog(d), "expected_plan": expected}, ensure_ascii=False)
    result = await asyncio.wait_for(agent.invoke_async(prompt, limits={"turns": 1}), timeout=timeout)
    usage = getattr(getattr(result, "metrics", None), "accumulated_usage", {})
    LOG.info(json.dumps({"event": "ai_usage", "provider": provider,
        "usage": {k: usage[k] for k in ("inputTokens", "outputTokens", "totalTokens") if k in usage}, "trusted_tools": len(TOOLS)}))
    LOG.info(json.dumps({"event": "ai_response_shape", "provider": provider, "stop_reason": result.stop_reason, "output_chars": len(str(result))}))
    plan = validate_plan(str(result), d)
    return plan

def classify(exc):
    # Never log exception messages/bodies: they may contain headers or credentials.
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    try: code = int(code)
    except (ValueError, TypeError): code = None
    name = type(exc).__name__.lower()
    if code in (401, 403): return "AUTH"
    if code == 429 or "throttl" in name or "ratelimit" in name: return "RATE_LIMIT"
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or "timeout" in name: return "TIMEOUT"
    if code in (500, 502, 503, 504): return "UPSTREAM"
    if "connection" in name or "network" in name or isinstance(exc, OSError): return "NETWORK"
    return "INVALID_OUTPUT"

def generate(snapshot, credentials, budget=10, invoke=invoke_strands):
    warnings = []
    primary = os.environ.get("HAWAHAWAI_AI_PROVIDER", "gemini")
    providers = [primary] + (["groq"] if primary == "gemini" else []) if primary in {"gemini", "groq"} else []
    deadline = time.monotonic() + min(10, max(0, budget))
    for provider in providers:
        if not credentials.get("GEMINI_API_KEY" if provider == "gemini" else "GROQ_API_KEY"):
            warnings.append(provider.upper() + "_NOT_CONFIGURED")
            continue
        remaining = deadline - time.monotonic()
        if remaining < 2:
            warnings.append("AI_TIME_BUDGET_EXHAUSTED")
            break
        started = time.monotonic()
        outcome = "SUCCESS"
        try:
            plan = asyncio.run(invoke(provider, credentials, snapshot, min(8 if provider == "gemini" else 4, remaining)))
            validate_plan(plan.model_dump_json(), snapshot["decision"])
            return plan, provider, warnings
        except Exception as exc:
            outcome = classify(exc)
            warnings.append(provider.upper() + "_" + outcome)
            if outcome == "INVALID_OUTPUT": break
        finally:
            LOG.info(json.dumps({"event": "ai_attempt", "provider": provider, "model": os.environ.get("HAWAHAWAI_GEMINI_MODEL", "gemini-2.5-flash") if provider == "gemini" else os.environ.get("HAWAHAWAI_GROQ_MODEL", "llama-3.3-70b-versatile"), "latency_ms": round((time.monotonic()-started)*1000), "outcome": outcome, "usage": "unavailable"}))
    return None, "rule_template", warnings + ["AI_UNAVAILABLE_DETERMINISTIC_EXPLANATION"]

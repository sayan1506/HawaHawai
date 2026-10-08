"""Pure deterministic policy evaluation. All evidence AND time are explicit.

US-AQI health categories support precaution only; never official GRAP activation.
No AI, storage, HTTP, random values or implicit clock is used in this module.
"""
import hashlib
import json
from datetime import timedelta
from .models import ActivityContext, Decision, Policy, POLICY_SOURCES, instant, number


def _fresh(envelope, now, maximum_age):
    try:
        return (envelope.get("status") == "available" and envelope.get("freshness_status") == "fresh"
                and 0 <= (now - instant(envelope["retrieved_at"])).total_seconds() <= maximum_age
                and now < instant(envelope["cache"]["fresh_until"]))
    except (KeyError, TypeError, ValueError):
        return False


def _point(point, sources, expected_type, now, *, maximum_age=None, forecast_time=None):
    """A health AQI must be US AQI, timestamped and bound to the right source kind."""
    try:
        when = instant(point["valid_at"])
        if maximum_age is not None and not 0 <= (now - when).total_seconds() <= maximum_age:
            return None
        if forecast_time is not None and when != forecast_time:
            return None
        by_id = {s["source_id"]: s for s in sources if s.get("kind") == expected_type and s.get("freshness") == "fresh"}
        pollutants = point["pollutants"]
        if any(not number(p["value"]) or p["unit"] != "ug/m3" or p["source_type"] != expected_type or p["source_id"] not in by_id
               or (p["observed_at"] is not None if expected_type == "model_forecast" else p["forecast_for"] is not None)
               or instant(p["forecast_for"] if expected_type == "model_forecast" else p["observed_at"]) != when for p in pollutants):
            return None
        for aqi in point["aqi"]:
            if aqi.get("scale") != "US_AQI":
                continue  # No conversion, concentration substitution or GRAP comparison.
            source = by_id.get(aqi["source_id"])
            if not source or not number(aqi["value"]) or aqi["value"] > 500 or aqi.get("source_type") != expected_type:
                return None
            if expected_type == "model_forecast":
                if aqi["observed_at"] is not None or instant(aqi["forecast_for"]) != when:
                    return None
            else:
                location = source.get("location")
                if aqi["forecast_for"] is not None or instant(aqi["observed_at"]) != when or not location or not location.get("station_id"):
                    return None
                if not isinstance(location.get("latitude"), (int, float)) or not -90 <= location["latitude"] <= 90 or not isinstance(location.get("longitude"), (int, float)) or not -180 <= location["longitude"] <= 180 or (location.get("distance_km") is not None and not number(location["distance_km"])):
                    return None
            return {"value": aqi["value"], "scale": "US_AQI", "source_id": aqi["source_id"], "source_type": expected_type,
                    "timestamp": when.isoformat(), "pollutants": pollutants, "station_location": source.get("location")}
    except (KeyError, TypeError, ValueError):
        return None
    return None


def evaluate(school, air, forecast, regulatory, evaluation_time, context=None, policy=None):
    now, context, policy = instant(evaluation_time), context or ActivityContext(), policy or Policy()
    if air.get("school_id") != school["school_id"] or forecast.get("school_id") != school["school_id"] or regulatory["jurisdiction"] != context.jurisdiction or instant(regulatory["evaluation_time"]) != now:
        raise ValueError("Evidence must match school, jurisdiction and explicit evaluation time")
    rules, evidence, warnings = [], [], list(regulatory["warnings"])
    for payload in (air, forecast):
        warnings.extend(payload.get("warnings", []))

    def trace(rule_id, priority, message, ids=()):
        rules.append({"rule_id": rule_id, "priority": priority, "message": message, "evidence_ids": list(ids)})

    def record(value, origin):
        if value is not None:
            identifier = origin + "#" + value["source_id"] + "#" + value["timestamp"]
            evidence.append({"evidence_id": identifier, "kind": origin, "freshness": "fresh", **value})
            return identifier
        return None

    measurements, modeled, outlook = [], None, []
    # Measurements remain independently represented; model aliases are not observations.
    if _fresh(air, now, policy.observation_max_age_seconds):
        for point in air.get("observations", []):
            value = _point(point, air.get("sources", []), "measurement", now, maximum_age=policy.observation_max_age_seconds)
            if value is not None:
                measurements.append(value)
                record(value, "station_observation")
        modeled = _point(air.get("modeled_current"), air.get("sources", []), "model_forecast", now, maximum_age=policy.model_max_age_seconds)
        record(modeled, "modeled_current")
    window_end = now + timedelta(hours=policy.activity_window_hours)
    anchor = now.replace(minute=0, second=0, microsecond=0)
    if anchor < now:
        anchor += timedelta(hours=1)
    expected = [anchor + timedelta(hours=i) for i in range(policy.activity_window_hours)]
    forecast_usable = _fresh(forecast, now, policy.forecast_retrieval_max_age_seconds)
    if forecast_usable:
        try:
            points = {instant(p["valid_at"]): p for p in forecast["points"]}
            for when in expected:
                value = _point(points.get(when), forecast.get("sources", []), "model_forecast", now, forecast_time=when)
                if value is not None:
                    outlook.append(value)
                    record(value, "activity_forecast")
        except (KeyError, TypeError, ValueError):
            outlook = []
    forecast_complete = len(outlook) == policy.activity_window_hours
    available_values = measurements + ([modeled] if modeled is not None else []) + outlook
    maximum = max((v["value"] for v in available_values), default=None)
    regulatory_verified = regulatory["verification_state"] in {"VERIFIED_ACTIVE", "VERIFIED_INACTIVE"}
    if not regulatory_verified:
        trace("REGULATORY_VERIFY_STATUS", 6, "Official activation/revocation or school-order review is unknown, stale or conflicting. No official stage is inferred.")
    if not measurements:
        warnings.append("Official station observations are unavailable; modeled US AQI is not official Indian AQI.")
        trace("MISSING_STATION_OBSERVATIONS", 5, "No validated fresh physical station US-AQI evidence is available. Model-only evidence cannot justify GO_OUTDOORS.")
    if not forecast_complete:
        trace("MISSING_FRESH_ACTIVITY_FORECAST", 5, "The next three dated hourly US-AQI forecast points are missing, stale or invalid.")
    if modeled is None:
        trace("MODELED_CURRENT_UNAVAILABLE_OR_STALE", 5, "Current modeled evidence is not usable as fresh evidence; a fresh dated forecast may still support precaution.")
    ids = [e["evidence_id"] for e in evidence]
    applicable = [r for r in regulatory["applicable_restrictions"] if context.activity == "all" or r["activity"] in {"all", "administration", context.activity}]
    holding = [r for r in regulatory.get("unverified_restrictions", []) if r["mandatory"] and r["action"] in {"SUSPEND_OUTDOOR", "SUSPEND_PHYSICAL_CLASSES"} and (context.activity == "all" or r["activity"] in {"all", "administration", context.activity})]
    mandatory = [r for r in applicable if r["mandatory"]]
    prohibitions = [r for r in mandatory if r["action"] in {"SUSPEND_OUTDOOR", "SUSPEND_PHYSICAL_CLASSES"}]
    operations = [r for r in mandatory if r["action"] in {"HYBRID_CLASSES", "REVIEW_ORDER"}]
    outdoor_advisories = [r for r in applicable if not r["mandatory"] and r["action"] == "AVOID_OUTDOOR_ADVISORY"]
    # The most restrictive applicable activity governs the aggregate school verdict.
    decision = Decision.DATA_INSUFFICIENT
    if prohibitions:
        decision = Decision.INDOOR_ONLY
        for restriction in prohibitions:
            trace("MANDATORY_SCHOOL_RESTRICTION", 1, "Follow the reviewed applicable school order; favorable pollution forecasts cannot override it.", [restriction["document_id"]])
    elif holding:
        decision = Decision.INDOOR_ONLY
        trace("PREVIOUS_RESTRICTION_REVERIFY", 1, "Previously reviewed prohibitions are not confirmed revoked. Hold outdoor/on-campus activity and reverify; this is conservative holding advice, not a claim of currently verified law.", [r["document_id"] for r in holding])
    elif outdoor_advisories:
        decision = Decision.INDOOR_ONLY
        trace("VERIFIED_GRAP_CHILDREN_ADVISORY", 2, "The reviewed applicable GRAP Citizen Charter advises children to avoid outdoor activities. Adopt indoor alternatives as precaution, not a mandatory legal outdoor ban or school closure.", [r["document_id"] for r in outdoor_advisories])
    elif maximum is not None and maximum > policy.indoor_above:
        decision = Decision.INDOOR_ONLY
        trace("US_AQI_INDOOR_PRECAUTION", 3, "Validated US-AQI evidence exceeds 200. Adopted EPA school guidance supports indoor alternatives or rescheduling, not a legal school closure.", ids + ["epa-school-guidance-2014", "epa-us-aqi-categories"])
    elif maximum is not None and maximum > policy.modify_above:
        decision = Decision.MODIFIED_OUTDOORS
        trace("US_AQI_MODIFY_PRECAUTION", 3, "Validated US-AQI evidence exceeds 100. Reduce exertion, provide breaks and sensitive-student alternatives under the adopted school health policy.", ids + ["epa-school-guidance-2014", "epa-us-aqi-categories"])
    else:
        # A co-located, identified physical station is an intentionally strict
        # project positive-advice prerequisite, not an EPA/Indian legal requirement.
        representative = any(v["station_location"].get("latitude") == school["latitude"] and v["station_location"].get("longitude") == school["longitude"] and v["station_location"].get("distance_km") == 0 for v in measurements)
        if regulatory_verified and representative and forecast_complete and maximum is not None:
            decision = Decision.GO_OUTDOORS
            trace("POSITIVE_EVIDENCE_REQUIREMENTS_MET", 5, "Verified regulation, fresh co-located physical US-AQI evidence and the next three forecast hours meet the documented outdoor recommendation prerequisites. This is not a guarantee of safe air.", ids)
        else:
            trace("MISSING_REQUIRED_EVIDENCE", 6, "Required regulatory, representative physical-observation or forecast evidence is incomplete. Verify before proceeding outdoors.", ids)
    if operations:
        for restriction in operations:
            trace("MANDATORY_SCHOOL_OPERATIONS", 1, "Applicable reviewed school-operation requirements must be followed for the listed grades. Hybrid classes are not an automatic outdoor ban or school closure.", [restriction["document_id"]])
        if decision == Decision.GO_OUTDOORS:
            decision = Decision.MODIFIED_OUTDOORS
    for restriction in applicable:
        if not restriction["mandatory"]:
            trace("OFFICIAL_ADVISORY_REVIEW", 2, "Review the cited advisory for its stated activities and effective period. It does not create a mandatory school closure or general PE ban.", [restriction["document_id"]])
    if outlook and max(v["value"] for v in outlook) > policy.modify_above:
        trace("ELEVATED_ACTIVITY_FORECAST", 4, "The next three hours include elevated modeled US AQI; this is forecast-based precaution, not an official observation or GRAP invocation.", [e["evidence_id"] for e in evidence if e["kind"] == "activity_forecast"])
    warnings.extend(["GO_OUTDOORS is conditional advice, not a guarantee of safe air.",
                     "INDOOR_ONLY concerns activities, not automatic school closure, online classes or clean indoor air; check filtration and suitability.",
                     "US AQI is never compared with Indian GRAP thresholds. Raw concentrations are preserved but not converted into AQI."])
    if context.grade is None:
        warnings.append("No grade selected: aggregate precaution includes applicable grade groups; mandatory actions list their exact grades (0 means pre-primary).")
    if regulatory["verification_state"] == "CONFLICTING":
        warnings.append("Conflicting official records require human resolution; no positive outdoor recommendation is allowed.")
    actions = []
    rule_ids = list(dict.fromkeys(r["rule_id"] for r in rules))
    for activity in ("assembly", "sports", "physical_education", "other"):
        if context.activity not in {"all", "indoor", activity}:
            continue
        recommendation, instruction = "VERIFY_BEFORE_PROCEEDING", "Verify current official orders and missing evidence before proceeding outdoors; use a suitable indoor alternative meanwhile."
        if decision == Decision.GO_OUTDOORS:
            recommendation, instruction = "NORMAL_WITH_CAVEATS", "Outdoor activity may proceed under the documented prerequisites; monitor symptoms and provide sensitive-student alternatives."
        elif decision == Decision.MODIFIED_OUTDOORS:
            recommendation, instruction = "MODIFY", "Shorten or reduce exertion, take breaks, monitor symptoms, and offer sensitive-student indoor alternatives."
            if maximum is not None and maximum > policy.vigorous_indoor_above and activity in {"sports", "physical_education"}:
                recommendation, instruction = "INDOOR_ALTERNATIVE", "Use suitable indoor alternatives or reschedule longer/vigorous exercise; modeled health precaution, not a legal ban."
            elif operations and maximum is not None and maximum <= policy.modify_above:
                recommendation, instruction = "REVIEW_SCHOOL_OPERATIONS", "Comply with grade-specific hybrid/administrative requirements before arranging activities. Hybrid classes are not an automatic outdoor ban."
        elif decision == Decision.INDOOR_ONLY:
            recommendation, instruction = "INDOOR_ALTERNATIVE", "Move the activity to a suitable indoor setting or reschedule; assess indoor air before exercise."
        targeted = [r for r in prohibitions if r["activity"] in {"all", activity} or r["action"] == "SUSPEND_PHYSICAL_CLASSES"]
        if any(r["action"] == "SUSPEND_PHYSICAL_CLASSES" for r in targeted + holding):
            recommendation, instruction = "FOLLOW_PHYSICAL_CLASS_ORDER", "Do not substitute on-campus indoor activity for a physical-class suspension. Follow the exact cited order for listed grades and any permitted non-campus alternatives."
        actions.append({"activity": activity, "instruction": instruction, "recommendation": recommendation,
                        "mandatory": bool(targeted), "applicable_grades": sorted({g for r in targeted for g in r["grades"]}),
                        "rule_ids": rule_ids, "evidence_ids": ids + [r["document_id"] for r in targeted + outdoor_advisories]})
    physical_suspension = any(r["action"] == "SUSPEND_PHYSICAL_CLASSES" for r in prohibitions + holding)
    indoor_instruction = ("Physical-class suspension must not be bypassed with on-campus indoor classes. Follow the cited order for permitted non-campus alternatives."
                          if physical_suspension else "Select an indoor alternative only after assessing ventilation, particle filtration and students' needs; indoor air has not been measured.")
    actions.append({"activity": "indoor", "recommendation": "FOLLOW_PHYSICAL_CLASS_ORDER" if physical_suspension else "ASSESS_INDOOR_ALTERNATIVE", "instruction": indoor_instruction, "mandatory": bool(prohibitions) and physical_suspension, "applicable_grades": sorted({g for r in prohibitions if r["action"] == "SUSPEND_PHYSICAL_CLASSES" for g in r["grades"]}), "rule_ids": rule_ids, "evidence_ids": ["epa-school-guidance-2014"] + [r["document_id"] for r in prohibitions + holding]})
    actions.append({"activity": "administration", "recommendation": "VERIFY_STATUS" if not regulatory_verified else "REVIEW_ORDERS", "instruction": "Review current CAQM and Delhi school notices; do not treat this activity recommendation as a school closure order.", "mandatory": False, "applicable_grades": [], "rule_ids": rule_ids, "evidence_ids": [d["document_id"] for d in regulatory["source_documents"]]})
    for restriction in applicable:
        actions.append({"activity": "administration" if restriction["action"] != "RESCHEDULE_SPORTS" else "sports", "recommendation": restriction["action"], "instruction": "Follow/review the exact cited official clause: " + restriction["clause"], "mandatory": restriction["mandatory"], "applicable_grades": restriction["grades"], "rule_ids": ["MANDATORY_SCHOOL_OPERATIONS" if restriction["mandatory"] else "OFFICIAL_ADVISORY_REVIEW"], "evidence_ids": [restriction["document_id"]]})
    actions.append({"activity": "parent_communication", "recommendation": "STRUCTURED_REASONS_READY", "instruction": "Use these deterministic reasons and caveats for later communication; no AI or bilingual advisory has been generated.", "mandatory": False, "applicable_grades": [], "rule_ids": rule_ids, "evidence_ids": ids})
    validity = [now + timedelta(minutes=5), expected[0] + timedelta(seconds=1)]
    for payload in (air, forecast):
        if _fresh(payload, now, 3600):
            validity.append(instant(payload["cache"]["fresh_until"]))
    if regulatory["verification_expires_at"] and instant(regulatory["verification_expires_at"]) > now:
        validity.append(instant(regulatory["verification_expires_at"]))
    if regulatory.get("next_transition_at"):
        validity.append(instant(regulatory["next_transition_at"]))
    for value in measurements + ([modeled] if modeled else []):
        validity.append(instant(value["timestamp"]) + timedelta(seconds=900))
    # All inputs are reevaluated on every request. This is a fingerprint, not a cache.
    fingerprint = hashlib.sha256(json.dumps({"school": school, "policy": policy.version, "regulatory": regulatory["snapshot_version"], "verification": regulatory["verification_state"], "grade": context.grade, "activity": context.activity, "evidence": evidence, "restrictions": applicable, "decision": decision.value}, sort_keys=True, allow_nan=False).encode()).hexdigest()[:24]
    measurement_ids = {v["source_id"] for v in measurements}
    quality = {"official_observations_available": any("cpcb" in s.get("url", "").lower() or "data.gov.in" in s.get("url", "") for s in air.get("sources", []) if s.get("source_id") in measurement_ids), "station_observations_available": bool(measurements), "modeled_data_available": modeled is not None, "forecast_available": forecast_complete, "current_freshness": air.get("freshness_status", "unavailable"), "forecast_freshness": forecast.get("freshness_status", "unavailable")}
    return {"school_id": school["school_id"], "status": "decided" if decision != Decision.DATA_INSUFFICIENT else "DATA_INSUFFICIENT", "verdict": None if decision == Decision.DATA_INSUFFICIENT else decision.value,
            "decision": decision.value, "generated_at": now.isoformat(), "evaluation_time": now.isoformat(), "valid_until": min(validity).isoformat(),
            "rule_version": policy.version, "policy_version": policy.version, "decision_id": fingerprint, "rule_ids": rule_ids,
            "reasons": [r["message"] for r in sorted(rules, key=lambda r: r["priority"])], "rule_evaluations": sorted(rules, key=lambda r: r["priority"]), "actions": actions,
            "evidence_ids": ids + list(dict.fromkeys(r["document_id"] for r in applicable)), "evidence": evidence,
            "sources": air.get("sources", []) + [s for s in forecast.get("sources", []) if s not in air.get("sources", [])],
            "policy_sources": list(POLICY_SOURCES), "regulatory_status": regulatory, "data_quality": quality,
            "activity_context": {"jurisdiction": context.jurisdiction, "grade": context.grade, "activity": context.activity, "window_start": now.isoformat(), "window_end": window_end.isoformat()},
            "requires_regulatory_verification": not regulatory_verified, "warnings": list(dict.fromkeys(warnings))}

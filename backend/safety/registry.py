"""Versioned, manually reviewed snapshots. Runtime can READ, never publish.

No network scraping, stage inference or implicit human verification. Application
verification expiry is independent of DynamoDB TTL; registry items have NO TTL.
"""
import copy
import json
import os
import re
from datetime import date, timedelta
from pathlib import Path
from .models import VerificationState, instant, official_url
from environmental.cache import CacheError

DATA = Path(__file__).with_name("data")
ATTESTATION = "I reviewed the current schedule, subsequent activations and revocations, and applicable Delhi school orders; every recorded claim matches the cited official document."
MIN_SCHEDULE_DATE = date(2026, 9, 29)


def school_catalog():
    return json.loads((DATA / "grap-school-rules-2026-09-29.json").read_text(encoding="utf-8"))


def catalog_restrictions(data):
    catalog = school_catalog()
    if data["schedule_version"] != catalog["schedule_version"] or not data["verification"]:
        return []
    doc = next((d for d in data["documents"] if d["document_type"] == "SCHEDULE" and d["url"] == catalog["source_url"] and d["sha256"] == catalog["source_sha256"] and d["access_status"] == "HUMAN_REVIEWED" and d["effective_from"]), None)
    if not doc:
        return []
    return [{**r, "document_id": doc["document_id"], "effective_from": doc["effective_from"], "effective_until": doc["effective_until"], "revoked_by": None} for r in catalog["rules"]]


def validate_snapshot(value, *, publish=False):
    required = {"version", "schedule_version", "jurisdiction", "documents", "events", "restrictions", "verification", "simulation", "notes"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Invalid snapshot fields; stage/status assertions are not accepted")
    for key in ("version", "schedule_version"):
        if not isinstance(value[key], str) or not re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", value[key]):
            raise ValueError("Invalid version")
    if value["jurisdiction"] != "NCT_DELHI" or type(value["simulation"]) is not bool:
        raise ValueError("Invalid jurisdiction or simulation marker")
    if not isinstance(value["notes"], list) or any(not isinstance(n, str) for n in value["notes"]):
        raise ValueError("Invalid notes")
    docs = {}
    for doc in value["documents"]:
        if set(doc) != {"document_id", "title", "authority", "url", "published_on", "document_type", "access_status", "sha256", "effective_from", "effective_until"}:
            raise ValueError("Invalid source document")
        if any(not isinstance(doc[k], str) or not doc[k].strip() for k in ("document_id", "title", "authority")) or doc["document_id"] in docs:
            raise ValueError("Missing/duplicate source metadata")
        official_url(doc["url"])
        published = date.fromisoformat(doc["published_on"])
        if doc["document_type"] not in {"SCHEDULE", "ACTIVATION", "REVOCATION", "SCHOOL_ORDER", "ADVISORY", "PRESS_RELEASE"} or doc["access_status"] not in {"RESEARCHED", "UNAVAILABLE", "HUMAN_REVIEWED"}:
            raise ValueError("Invalid source classification")
        if doc["sha256"] is not None and not re.fullmatch(r"[a-f0-9]{64}", doc["sha256"]):
            raise ValueError("Invalid document digest")
        for key in ("effective_from", "effective_until"):
            if doc[key] is not None and instant(doc[key]).date() < published:
                raise ValueError("Document effective before publication")
        if doc["effective_until"] and (not doc["effective_from"] or instant(doc["effective_until"]) <= instant(doc["effective_from"])):
            raise ValueError("Invalid effective interval")
        docs[doc["document_id"]] = doc
    seen = set()
    for event in value["events"]:
        if set(event) != {"event_id", "document_id", "event_type", "stage", "effective_from", "revokes_event_id"} or event["event_id"] in seen:
            raise ValueError("Invalid/duplicate regulatory event")
        seen.add(event["event_id"])
        if event["event_type"] not in {"ACTIVATE", "REVOKE", "REVOKE_ALL"} or type(event["stage"]) is not int or not 0 <= event["stage"] <= 4:
            raise ValueError("Invalid event type/stage")
        if (event["event_type"] == "REVOKE_ALL") != (event["stage"] == 0):
            raise ValueError("Stage zero requires explicit all-stage revocation")
        doc = docs.get(event["document_id"])
        expected = "ACTIVATION" if event["event_type"] == "ACTIVATE" else "REVOCATION"
        if not doc or doc["document_type"] != expected or instant(event["effective_from"]).date() < date.fromisoformat(doc["published_on"]):
            raise ValueError("Event lacks applicable official order")
    seen = set()
    for rule in value["restrictions"]:
        if set(rule) != {"restriction_id", "document_id", "clause", "jurisdiction", "grades", "activity", "action", "mandatory", "effective_from", "effective_until", "minimum_stage", "revoked_by"} or rule["restriction_id"] in seen:
            raise ValueError("Invalid/duplicate school restriction")
        seen.add(rule["restriction_id"])
        doc = docs.get(rule["document_id"])
        if not doc or doc["document_type"] not in {"SCHOOL_ORDER", "SCHEDULE", "ADVISORY"} or not isinstance(rule["clause"], str) or not rule["clause"].strip():
            raise ValueError("Restriction lacks official clause")
        if rule["jurisdiction"] != "NCT_DELHI" or rule["activity"] not in {"all", "assembly", "sports", "physical_education", "other", "administration"}:
            raise ValueError("Invalid restriction applicability")
        if not rule["grades"] or len(set(rule["grades"])) != len(rule["grades"]) or any(type(g) is not int or not 0 <= g <= 12 for g in rule["grades"]):
            raise ValueError("Invalid grades")
        if rule["action"] not in {"HYBRID_CLASSES", "SUSPEND_OUTDOOR", "SUSPEND_PHYSICAL_CLASSES", "REVIEW_ORDER", "RESCHEDULE_SPORTS", "AVOID_OUTDOOR_ADVISORY"} or type(rule["mandatory"]) is not bool:
            raise ValueError("Unsupported school action")
        if (doc["document_type"] == "ADVISORY" or rule["action"] == "AVOID_OUTDOOR_ADVISORY") and rule["mandatory"]:
            raise ValueError("Advisories cannot create mandatory restrictions")
        if rule["minimum_stage"] is not None and (type(rule["minimum_stage"]) is not int or not 1 <= rule["minimum_stage"] <= 4):
            raise ValueError("Invalid stage applicability")
        if instant(rule["effective_from"]).date() < date.fromisoformat(doc["published_on"]):
            raise ValueError("Restriction predates order")
        if rule["effective_until"] and instant(rule["effective_until"]) <= instant(rule["effective_from"]):
            raise ValueError("Invalid restriction interval")
        if rule["revoked_by"] and (rule["revoked_by"] not in docs or docs[rule["revoked_by"]]["document_type"] != "REVOCATION" or not docs[rule["revoked_by"]]["effective_from"]):
            raise ValueError("Revocation requires explicit effective official document")
    verification = value["verification"]
    if verification is not None:
        if set(verification) != {"operator_id", "verified_at", "expires_at", "history_reviewed_through", "attestation"} or not isinstance(verification["operator_id"], str) or not verification["operator_id"].strip() or verification["attestation"] != ATTESTATION:
            raise ValueError("Explicit human verification action required")
        verified, expires, through = (instant(verification[k]) for k in ("verified_at", "expires_at", "history_reviewed_through"))
        if not verified < expires <= verified + timedelta(hours=24) or through != verified:
            raise ValueError("Review coverage must equal verification time; expiry at most 24 hours")
        if any(d["access_status"] != "HUMAN_REVIEWED" or not d["sha256"] or date.fromisoformat(d["published_on"]) > verified.date() for d in docs.values()):
            raise ValueError("All documents require reviewed original content and digest")
        if not any(d["document_type"] == "SCHEDULE" and date.fromisoformat(d["published_on"]) >= MIN_SCHEDULE_DATE for d in docs.values()):
            raise ValueError("Current schedule must address the September 2026 revision")
        if not value["simulation"] and not catalog_restrictions(value):
            raise ValueError("Human publication must bind the current school-clause catalog to the reviewed original schedule and explicit effective time")
    elif value["events"] or value["restrictions"]:
        raise ValueError("Claims cannot be recorded without a human review")
    if publish and (value["simulation"] or verification is None):
        raise ValueError("Publishing requires a genuine human-reviewed non-simulation snapshot")
    return copy.deepcopy(value)


def resolve(snapshot, evaluation_time, context):
    now = instant(evaluation_time)
    data = validate_snapshot(snapshot)
    # Curated clauses only enter evaluation when the exact original is human
    # reviewed; stage applicability is still checked against official events.
    catalog = catalog_restrictions(data)
    catalog_ids = {r["restriction_id"] for r in catalog}
    if catalog_ids & {r["restriction_id"] for r in data["restrictions"]}:
        raise ValueError("Catalog rules cannot be shadowed by manual claims")
    data["restrictions"].extend(catalog)
    verification, docs = data["verification"], {d["document_id"]: d for d in data["documents"]}
    state, active, effective, order = VerificationState.UNKNOWN, set(), None, None
    warnings = list(data["notes"])
    review_fresh = False
    if verification:
        checked, expires = instant(verification["verified_at"]), instant(verification["expires_at"])
        review_fresh = checked <= now < expires
        state = VerificationState.UNKNOWN if now < checked else VerificationState.STALE if now >= expires else VerificationState.UNKNOWN
        if review_fresh:
            seen, simultaneous, conflict, current_events = {}, {}, False, {}
            events = sorted((e for e in data["events"] if instant(e["effective_from"]) <= now), key=lambda e: (instant(e["effective_from"]), e["event_id"]))
            for event in events:
                stage, typ = event["stage"], event["event_type"]
                key = (instant(event["effective_from"]), stage)
                if key in simultaneous and simultaneous[key] != typ:
                    conflict = True
                if (stage == 0 and any(k[0] == key[0] and v == "ACTIVATE" for k, v in simultaneous.items())) or (typ == "ACTIVATE" and simultaneous.get((key[0], 0)) == "REVOKE_ALL"):
                    conflict = True
                simultaneous[key] = typ
                if typ == "ACTIVATE":
                    if stage > 1 and any(lower not in active for lower in range(1, stage)):
                        conflict = True  # incomplete cumulative-stage history
                    active.add(stage)
                    seen[event["event_id"]] = event
                    current_events[stage] = event
                elif typ == "REVOKE":
                    target = seen.get(event["revokes_event_id"])
                    if not target or target["stage"] != stage or stage not in active or current_events[stage]["event_id"] != event["revokes_event_id"]:
                        conflict = True
                    active.discard(stage)
                    current_events.pop(stage, None)
                else:
                    active.clear()
                    current_events.clear()
                effective, order = event["effective_from"], docs[event["document_id"]]["url"]
            expired_order = any(docs[e["document_id"]]["effective_until"] and now >= instant(docs[e["document_id"]]["effective_until"]) for e in current_events.values())
            if active and active != set(range(1, max(active) + 1)):
                conflict = True
            if conflict:
                state = VerificationState.CONFLICTING
            elif expired_order:
                state = VerificationState.UNKNOWN
                warnings.append("An active-stage source order has expired; fresh human review is required.")
            elif events:
                state = VerificationState.VERIFIED_ACTIVE if active else VerificationState.VERIFIED_INACTIVE
    verified = state in {VerificationState.VERIFIED_ACTIVE, VerificationState.VERIFIED_INACTIVE}
    stage = max(active) if verified and active else 0 if verified else None
    applicable = []
    # Independently reviewed school orders can apply even if a GRAP stage is unknown.
    if review_fresh and state != VerificationState.CONFLICTING:
        for rule in data["restrictions"]:
            doc = docs[rule["document_id"]]
            revoked = docs.get(rule["revoked_by"])
            if rule["jurisdiction"] != context.jurisdiction or (context.grade is not None and context.grade not in rule["grades"]):
                continue
            if instant(rule["effective_from"]) > now or (rule["effective_until"] and now >= instant(rule["effective_until"])) or (doc["effective_until"] and now >= instant(doc["effective_until"])) or (revoked and now >= instant(revoked["effective_from"])):
                continue
            if rule["minimum_stage"] is not None and (stage is None or stage < rule["minimum_stage"]):
                continue
            applicable.append(rule)
    if not verified:
        warnings.append("VERIFY_STATUS: current official GRAP activation/revocation history is not verified.")
    transitions = []
    for event in data["events"]:
        transitions.append(instant(event["effective_from"]))
    for rule in data["restrictions"]:
        transitions.append(instant(rule["effective_from"]))
        if rule["effective_until"]:
            transitions.append(instant(rule["effective_until"]))
    for doc in docs.values():
        for field in ("effective_from", "effective_until"):
            if doc[field]:
                transitions.append(instant(doc[field]))
    next_transition = min((t for t in transitions if t > now), default=None)
    unverified = []
    if verification and state in {VerificationState.STALE, VerificationState.CONFLICTING}:
        # Verification expiry is not legal revocation. Preserve prior mandatory
        # prohibitions for conservative holding advice, never as VERIFIED law.
        for rule in data["restrictions"]:
            revoked = docs.get(rule["revoked_by"])
            if context.grade is not None and context.grade not in rule["grades"]:
                continue
            if instant(rule["effective_from"]) > now or (rule["effective_until"] and now >= instant(rule["effective_until"])) or (revoked and now >= instant(revoked["effective_from"])):
                continue
            unverified.append(rule)
    source_docs = [{**d, "verification_status": "HUMAN_REVIEWED" if review_fresh else "UNVERIFIED"} for d in docs.values()]
    return {"status": "verified" if verified else "VERIFY_STATUS", "stage": stage, "active_stage": stage if stage else None,
            "verification_state": state.value, "effective_from": effective if verified else None,
            "verified_at": verification["verified_at"] if verification else None,
            "verification_expires_at": verification["expires_at"] if verification else None,
            "order_url": order if verified else None, "jurisdiction": context.jurisdiction,
            "restrictions": [r["action"] for r in applicable], "applicable_restrictions": applicable, "unverified_restrictions": unverified,
            "sources": [], "source_documents": source_docs, "snapshot_version": data["version"],
            "schedule_version": data["schedule_version"], "evaluation_time": now.isoformat(),
            "verification_action_recorded": verification is not None, "next_transition_at": next_transition.isoformat() if next_transition else None, "warnings": warnings}


def read_snapshot(cache=None):
    if cache is not None:
        # Registry shares storage, not environmental TTL/lease/cooldown semantics.
        pointer = cache.get("regulatory#NCT_DELHI#current")
        if pointer:
            if set(pointer) != {"version"} or not re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", pointer["version"]):
                raise CacheError("REGULATORY_POINTER_INVALID")
            value = cache.get("regulatory#NCT_DELHI#version#" + pointer["version"])
            if not value or value.get("version") != pointer["version"] or value.get("simulation"):
                raise CacheError("REGULATORY_SNAPSHOT_UNAVAILABLE")
            return validate_snapshot(value)
    return validate_snapshot(json.loads((DATA / "regulatory-research-v2.json").read_text(encoding="utf-8")))

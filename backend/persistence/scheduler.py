"""Private scheduled planning artifacts. Never import or invoke an AI agent."""
import json
import logging
import os
from datetime import datetime, timezone
from .models import PILOT, IST, digest, read_profile, validate_record
from .service import history_key, prefix
from safety.models import instant, ActivityContext
from safety.service import verdict

JOB = "hawahawai.daily-verdict.v1"
LOG = logging.getLogger("hawahawai.scheduler")
LOG.setLevel(logging.INFO)
def refresh(event, service, now=None):
    now = instant(now) if now else datetime.now(timezone.utc)
    if (set(event) != {"job", "school_id", "schedule_arn", "scheduled_time"} or event["job"] != JOB or event["school_id"] != PILOT or
        not os.environ.get("HAWAHAWAI_DAILY_SCHEDULE_ARN") or event["schedule_arn"] != os.environ["HAWAHAWAI_DAILY_SCHEDULE_ARN"]):
        raise ValueError("INVALID_PRIVATE_REFRESH")
    scheduled = instant(event["scheduled_time"])
    if not -60 <= (now - scheduled).total_seconds() <= 900: raise ValueError("INVALID_SCHEDULE_TIME")
    school = read_profile(service.cache)
    date = scheduled.astimezone(IST).date().isoformat()
    key = prefix() + "job#" + date + "#" + digest(school)
    previous = service.cache.get(key)
    if previous:
        record = validate_record(service.cache.get(history_key(previous["record_id"])), PILOT, ActivityContext())
        if previous.get("job") != JOB or previous.get("local_date") != date or record["profile_fingerprint"] != digest(school): raise RuntimeError("INVALID_JOB_RECEIPT")
        LOG.info(json.dumps({"event": "daily_refresh", "status": "duplicate", "local_date": date, "ai_invoked": False}))
        return {"status": "duplicate", "record_id": record["record_id"], "local_date": date, "ai_invoked": False}
    lease = key + "#lease"
    token = service.cache.acquire(lease, now.timestamp())
    if not token: raise RuntimeError("REFRESH_IN_PROGRESS_RETRY_BOUNDED")
    try:
        # Another delivery can finish between our initial read and lease acquisition.
        # Recheck under the lease so that race never causes extra provider work.
        previous = service.cache.get(key)
        if previous:
            record = validate_record(service.cache.get(history_key(previous["record_id"])), PILOT, ActivityContext())
            if previous.get("job") != JOB or previous.get("local_date") != date or record["profile_fingerprint"] != digest(school): raise RuntimeError("INVALID_JOB_RECEIPT")
            LOG.info(json.dumps({"event": "daily_refresh", "status": "duplicate", "local_date": date, "ai_invoked": False}))
            return {"status": "duplicate", "record_id": record["record_id"], "local_date": date, "ai_invoked": False}
        result = verdict(school, service, origin="SCHEDULED")
        metadata = result.get("persistence", {})
        if metadata.get("status") not in {"stored", "repaired"}: raise RuntimeError("DAILY_STORAGE_UNAVAILABLE")
        receipt = {"job": JOB, "local_date": date, "record_id": metadata["record_id"], "scheduled_time": scheduled.isoformat()}
        if not service.cache.put_record(key, receipt): raise RuntimeError("JOB_RECEIPT_CONFLICT")
        LOG.info(json.dumps({"event": "daily_refresh", "status": "stored", "local_date": date, "record_id": metadata["record_id"], "ai_invoked": False}))
        return {"status": "stored", "record_id": metadata["record_id"], "local_date": date, "ai_invoked": False}
    finally: service.cache.release(lease, token)

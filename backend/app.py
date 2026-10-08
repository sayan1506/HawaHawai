"""Phase 0-compatible liveness and Phase 1 environmental evidence entrypoint."""
import json
import os
import re
from datetime import datetime, timezone


def handler(event, context):
    path = event.get("rawPath") or event.get("path", "/")
    method = event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod", "GET")
    if path == "/health" and method == "GET":
        status = 200
        body = {
            "status": "ok", "service": "hawahawai-backend",
            "environment": os.environ.get("HAWAHAWAI_ENV", "local"),
            "version": "0.0.0", "phase": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    elif method == "GET" and re.fullmatch(r"/v1/schools/[a-z0-9-]+(?:/(?:air|forecast|grap|verdict))?", path):
        from environmental.config import school_profile, coordinates
        from environmental.service import get_service
        from environmental.cache import CacheError
        try:
            try:
                school = school_profile()
            except (ValueError, OSError, TypeError):
                raise RuntimeError("SCHOOL_CONFIGURATION_INVALID") from None
            params = event.get("queryStringParameters") or {}
            phase2 = path.endswith(("/grap", "/verdict"))
            allowed = {"latitude", "longitude", "grade", "activity"} if phase2 else {"latitude", "longitude"}
            if set(params) - allowed or ("latitude" in params) != ("longitude" in params):
                raise ValueError("Unsupported or incomplete request parameters")
            if "latitude" in params:
                lat, lon = float(params["latitude"]), float(params["longitude"])
                coordinates(lat, lon)
                if lat != school["latitude"] or lon != school["longitude"]:
                    raise ValueError("Coordinates must match the configured school")
            if path.split("/")[3] != school["school_id"]:
                status, body = 404, {"error": {"code": "SCHOOL_NOT_FOUND", "message": "Unknown pilot school"}}
            elif phase2:
                from safety.models import ActivityContext
                from safety.service import regulatory_status, verdict
                grade = params.get("grade")
                if grade is not None and not re.fullmatch(r"(?:[0-9]|1[0-2])", grade):
                    raise ValueError("Invalid grade")
                activity_context = ActivityContext(grade=int(grade) if grade is not None else None, activity=params.get("activity", "all"))
                evaluation_time = datetime.now(timezone.utc)
                service = get_service()
                body = (regulatory_status(school, evaluation_time, activity_context, service.cache)
                        if path.endswith("/grap") else verdict(school, service, context=activity_context))
                status = 200  # Unknown/insufficient is a valid, explicit policy outcome.
            elif path.endswith("/air") or path.endswith("/forecast"):
                body = get_service().get(school, "current" if path.endswith("/air") else "forecast")
                status = 503 if body["status"] == "unavailable" else 200
            else:
                status, body = 200, school
        except (ValueError, TypeError):
            status, body = 400, {"error": {"code": "INVALID_REQUEST", "message": "Invalid request parameters or coordinates"}}
        except (RuntimeError, CacheError):
            status, body = 503, {"error": {"code": "ENVIRONMENT_UNAVAILABLE", "message": "School configuration or cache unavailable"}}
    else:
        status = 404
        body = {"error": {"code": "NOT_FOUND", "message": "Route not found"}}
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        "body": json.dumps(body),
    }

"""Dependency-free Phase 0 Lambda entrypoint, also used by the local server."""
import json
import os
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
    else:
        status = 404
        body = {"error": {"code": "NOT_FOUND", "message": "Route not found"}}
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        "body": json.dumps(body),
    }

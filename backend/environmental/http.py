"""Bounded HTTPS transport. No credentials or upstream response bodies in errors."""
import http.client
import json
import random
import socket
import ssl
import time
from urllib.parse import urlsplit


class ProviderError(Exception):
    def __init__(self, code: str, retry_after: int = 60):
        super().__init__(code)
        self.code = code
        self.retry_after = max(60, min(retry_after, 3600))


def request_once(url: str):
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != "air-quality-api.open-meteo.com":
        raise ProviderError("PROVIDER_URL_NOT_ALLOWED")
    connection = http.client.HTTPSConnection(parts.hostname, timeout=2, context=ssl.create_default_context())
    try:
        connection.connect()
        connection.sock.settimeout(3)
        connection.request("GET", parts.path + "?" + parts.query, headers={"User-Agent": "HawaHawai/0.1 educational prototype"})
        response = connection.getresponse()
        if response.status == 429:
            wait = response.getheader("Retry-After", "60")
            raise ProviderError("RATE_LIMITED", int(wait) if wait.isdigit() else 60)
        if response.status >= 500:
            raise ProviderError("UPSTREAM_TRANSIENT")
        if response.status != 200:
            raise ProviderError("UPSTREAM_REJECTED")
        data = response.read(1_000_001)
        if len(data) > 1_000_000:
            raise ProviderError("RESPONSE_TOO_LARGE")
        try:
            body = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            raise ProviderError("MALFORMED_JSON") from None
        if not isinstance(body, dict):
            raise ProviderError("INVALID_SCHEMA")
        return body
    finally:
        connection.close()


def fetch_json(url, request=request_once, sleep=time.sleep):
    for attempt in range(2):
        try:
            return request(url)
        except (socket.timeout, TimeoutError):
            error = ProviderError("TIMEOUT")
        except (OSError, http.client.HTTPException):
            error = ProviderError("CONNECTION_FAILED")
        except ProviderError as caught:
            error = caught
        if attempt == 1 or error.code not in {"TIMEOUT", "CONNECTION_FAILED", "UPSTREAM_TRANSIENT"}:
            raise error
        sleep(0.25 + random.uniform(0, 0.1))

"""Local HTTP adapter. Production runs app.handler in AWS Lambda."""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qsl
from app import handler

ALLOWED_ORIGINS = {"http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:4173", "http://localhost:4173"}


class RequestHandler(BaseHTTPRequestHandler):
    def cors(self):
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def do_GET(self):
        response = handler({"rawPath": urlsplit(self.path).path, "queryStringParameters": dict(parse_qsl(urlsplit(self.path).query, keep_blank_values=True)), "requestContext": {"http": {"method": "GET"}}}, None)
        self.send_response(response["statusCode"])
        self.cors()
        for key, value in response["headers"].items():
            self.send_header(key, value)
        body = response["body"].encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024: raise ValueError()
            payload = self.rfile.read(length).decode()
        except (ValueError, UnicodeError):
            self.send_error(400)
            return
        response = handler({"rawPath": urlsplit(self.path).path, "body": payload,
            "queryStringParameters": dict(parse_qsl(urlsplit(self.path).query)), "httpMethod": "POST"}, None)
        self.send_response(response["statusCode"])
        self.cors()
        for key, value in response["headers"].items(): self.send_header(key, value)
        body = response["body"].encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if self.headers.get("Origin") not in ALLOWED_ORIGINS:
            self.send_error(403)
            return
        self.send_response(204)
        self.cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.end_headers()


if __name__ == "__main__":
    bind = os.environ.get("HAWAHAWAI_BIND", "127.0.0.1")
    ThreadingHTTPServer((bind, 8000), RequestHandler).serve_forever()

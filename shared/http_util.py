"""Shared HTTP helpers for Kani Sensei Python handlers."""

import json


def respond(handler, status, body, extra_headers=None):
    extra_headers = extra_headers or {}
    payload = json.dumps(body, ensure_ascii=False, default=str).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    if "Cache-Control" not in extra_headers:
        handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(payload)))
    for key, value in extra_headers.items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(payload)


def optional_int(query, key, default=None):
    value = query.get(key, [None])[0]
    if value in (None, ""):
        return default
    return int(value)


def optional_bool(query, key, default=False):
    value = query.get(key, [None])[0]
    if value in (None, ""):
        return default
    return str(value).lower() in ("1", "true", "yes", "on")

"""Browser session auth for the Kani Sensei web UI.

Cron jobs keep using X-Cron-Secret. The SPA logs in with the same secret
(or SITE_PASSWORD if set) and receives an HMAC-signed cookie.
"""

import hashlib
import hmac
import os
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs


COOKIE_NAME = "kani_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


def site_password():
    return os.environ.get("SITE_PASSWORD") or os.environ.get("CRON_SECRET")


def _signing_key():
    secret = site_password()
    if not secret:
        raise ValueError("SITE_PASSWORD or CRON_SECRET is required")
    return secret.encode()


def issue_token(now=None):
    now = int(now if now is not None else time.time())
    expires = now + SESSION_TTL_SECONDS
    payload = f"kibz|{expires}"
    sig = hmac.new(_signing_key(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}|{sig}", expires


def verify_token(token, now=None):
    if not token or token.count("|") != 2:
        return False
    user, expires_s, sig = token.split("|", 2)
    try:
        expires = int(expires_s)
    except ValueError:
        return False
    now = int(now if now is not None else time.time())
    if user != "kibz" or expires < now:
        return False
    payload = f"{user}|{expires}"
    expected = hmac.new(_signing_key(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def cookie_header(token, expires, secure=True):
    parts = [
        f"{COOKIE_NAME}={token}",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        f"Max-Age={max(0, expires - int(time.time()))}",
    ]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def clear_cookie_header(secure=True):
    parts = [f"{COOKIE_NAME}=", "Path=/", "HttpOnly", "SameSite=Lax", "Max-Age=0"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def token_from_headers(headers):
    raw = headers.get("Cookie") or headers.get("cookie") or ""
    jar = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:
        return None
    morsel = jar.get(COOKIE_NAME)
    return morsel.value if morsel else None


def is_authorized(headers):
    secret = site_password()
    if not secret:
        return False
    if headers.get("X-Cron-Secret") == secret or headers.get("x-cron-secret") == secret:
        return True
    auth = headers.get("Authorization") or headers.get("authorization") or ""
    if auth.lower().startswith("bearer ") and auth[7:] == secret:
        return True
    return verify_token(token_from_headers(headers))


def read_json_body(handler, max_bytes=65536):
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    if length > max_bytes:
        raise ValueError("body too large")
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    import json
    return json.loads(raw.decode())


def query_params(path):
    from urllib.parse import urlparse
    return parse_qs(urlparse(path).query)

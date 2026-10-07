"""Request helpers for the Kani Sensei web API.

The web UI is public. Cron endpoints (tick, sync) check X-Cron-Secret themselves.
"""

from urllib.parse import parse_qs


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

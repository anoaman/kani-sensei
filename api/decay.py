"""Phase 1 Decay Map endpoint.

GET /api/decay
Optional query params: min_level, max_level, limit.
Protected with X-Cron-Secret until the platform has user authentication.
"""

from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.decay_map import fetch_decay_map
from shared.neon import NeonClient


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        secret = os.environ.get("CRON_SECRET")
        if not secret or self.headers.get("X-Cron-Secret") != secret:
            self._respond(401, {"error": "unauthorized"})
            return

        query = parse_qs(urlparse(self.path).query)
        try:
            min_level = self._optional_int(query, "min_level")
            max_level = self._optional_int(query, "max_level")
            limit = min(250, max(1, int(query.get("limit", [100])[0])))
            if min_level is not None and max_level is not None and min_level > max_level:
                raise ValueError("min_level cannot exceed max_level")
            database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
            if not database_url:
                raise ValueError("DATABASE_URL is required")
            report = fetch_decay_map(NeonClient(database_url), min_level, max_level, limit)
        except (TypeError, ValueError) as exc:
            self._respond(400, {"error": str(exc)})
            return
        except Exception as exc:
            print(f"[kani-sensei/decay] failed: {exc}", file=sys.stderr)
            self._respond(502, {"error": "decay_map_failed"})
            return
        self._respond(200, report)

    @staticmethod
    def _optional_int(query, key):
        value = query.get(key, [None])[0]
        return None if value in (None, "") else int(value)

    def _respond(self, status, body):
        payload = json.dumps(body, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass

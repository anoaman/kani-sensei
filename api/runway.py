"""Phase 3 Runway endpoint.

GET /api/runway
Query params:
  - daily_reviews (int, default 100, min 25): target reviews/day
  - include_new_lessons (bool, default false): include ~5 lessons/day cost

Protected with X-Cron-Secret until the platform has user authentication.
Returns the same shape as shared/runway.build_runway_plan().
"""

from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.runway import fetch_runway_plan
from shared.neon import NeonClient


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        secret = os.environ.get("CRON_SECRET")
        if not secret or self.headers.get("X-Cron-Secret") != secret:
            self._respond(401, {"error": "unauthorized"})
            return

        query = parse_qs(urlparse(self.path).query)
        try:
            daily_reviews = self._optional_int(query, "daily_reviews", default=100)
            if daily_reviews is not None and daily_reviews < 0:
                raise ValueError("daily_reviews must be non-negative")
            include_new_lessons = self._optional_bool(query, "include_new_lessons")
            database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
            if not database_url:
                raise ValueError("DATABASE_URL is required")
            plan = fetch_runway_plan(
                NeonClient(database_url),
                daily_reviews=daily_reviews,
                include_new_lessons=include_new_lessons,
            )
        except (TypeError, ValueError) as exc:
            msg = str(exc)
            if "invalid literal for int()" in msg:
                msg = "daily_reviews must be an integer"
            self._respond(400, {"error": msg})
            return
        except Exception as exc:
            print(f"[kani-sensei/runway] failed: {exc}", file=sys.stderr)
            self._respond(502, {"error": "runway_failed"})
            return
        self._respond(200, plan)

    @staticmethod
    def _optional_int(query, key, default=None):
        value = query.get(key, [None])[0]
        if value in (None, ""):
            return default
        return int(value)

    @staticmethod
    def _optional_bool(query, key, default=False):
        value = query.get(key, [None])[0]
        if value in (None, ""):
            return default
        return str(value).lower() in ("1", "true", "yes", "on")

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

"""Phase 3 Runway endpoint.

GET /api/runway
Query params:
  - daily_reviews (int, default 100, min 25): target reviews/day
  - include_new_lessons (bool, default false): include ~5 lessons/day cost

Auth: session cookie, Bearer, or X-Cron-Secret.
"""

from http.server import BaseHTTPRequestHandler
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.auth import is_authorized, query_params
from shared.http_util import optional_bool, optional_int, respond
from shared.neon import NeonClient
from shared.runway import fetch_runway_plan


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Cron-Secret")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_GET(self):
        if not is_authorized(self.headers):
            respond(self, 401, {"error": "unauthorized"})
            return

        query = query_params(self.path)
        try:
            daily_reviews = optional_int(query, "daily_reviews", default=100)
            if daily_reviews is not None and daily_reviews < 0:
                raise ValueError("daily_reviews must be non-negative")
            include_new_lessons = optional_bool(query, "include_new_lessons")
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
            respond(self, 400, {"error": msg})
            return
        except Exception as exc:
            print(f"[kani-sensei/runway] failed: {exc}", file=sys.stderr)
            respond(self, 502, {"error": "runway_failed"})
            return
        respond(self, 200, plan)

    def log_message(self, *args):
        pass

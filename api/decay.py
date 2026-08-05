"""Phase 1 Decay Map endpoint.

GET /api/decay
Optional query params: min_level, max_level, limit.
Auth: session cookie, Bearer, or X-Cron-Secret.
"""

from http.server import BaseHTTPRequestHandler
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.auth import is_authorized, query_params
from shared.decay_map import fetch_decay_map
from shared.http_util import optional_int, respond
from shared.neon import NeonClient


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
            min_level = optional_int(query, "min_level")
            max_level = optional_int(query, "max_level")
            limit = min(250, max(1, optional_int(query, "limit", 100)))
            if min_level is not None and max_level is not None and min_level > max_level:
                raise ValueError("min_level cannot exceed max_level")
            database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
            if not database_url:
                raise ValueError("DATABASE_URL is required")
            report = fetch_decay_map(NeonClient(database_url), min_level, max_level, limit)
        except (TypeError, ValueError) as exc:
            respond(self, 400, {"error": str(exc)})
            return
        except Exception as exc:
            print(f"[kani-sensei/decay] failed: {exc}", file=sys.stderr)
            respond(self, 502, {"error": "decay_map_failed"})
            return
        respond(self, 200, report)

    def log_message(self, *args):
        pass

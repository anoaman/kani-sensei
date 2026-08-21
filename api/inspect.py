"""Subject inspect — teaching card from the cached WK payload.

GET /api/inspect?subject_id=123
Auth: session cookie, Bearer, or X-Cron-Secret.
"""

from http.server import BaseHTTPRequestHandler
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.auth import is_authorized, query_params
from shared.http_util import optional_int, respond
from shared.inspect import fetch_inspect
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
        subject_id = optional_int(query, "subject_id")
        if not subject_id:
            respond(self, 400, {"error": "subject_id is required"})
            return
        try:
            database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
            if not database_url:
                raise ValueError("DATABASE_URL is required")
            db = NeonClient(database_url)
            with db.reuse():
                respond(self, 200, fetch_inspect(db, subject_id))
        except ValueError as exc:
            respond(self, 404, {"error": str(exc)})
        except Exception as exc:
            print(f"[kani-sensei/inspect] failed: {exc}", file=sys.stderr)
            respond(self, 502, {"error": "inspect_failed"})

    def log_message(self, *args):
        pass

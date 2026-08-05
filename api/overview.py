"""Dashboard overview — Decay Map summary + Runway in one round trip.

GET /api/overview
Optional: min_level, max_level, limit, daily_reviews, include_new_lessons
"""

from http.server import BaseHTTPRequestHandler
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.auth import is_authorized, query_params
from shared.decay_map import fetch_decay_map
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
            min_level = optional_int(query, "min_level")
            max_level = optional_int(query, "max_level")
            limit = min(250, max(1, optional_int(query, "limit", 40)))
            daily_reviews = optional_int(query, "daily_reviews", 100)
            include_new_lessons = optional_bool(query, "include_new_lessons")
            if min_level is not None and max_level is not None and min_level > max_level:
                raise ValueError("min_level cannot exceed max_level")
            database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
            if not database_url:
                raise ValueError("DATABASE_URL is required")
            db = NeonClient(database_url)
            decay = fetch_decay_map(db, min_level, max_level, limit)
            runway = fetch_runway_plan(
                db,
                daily_reviews=daily_reviews,
                include_new_lessons=include_new_lessons,
            )
            last_sync = None
            try:
                rows = db.execute(
                    """
                    select finished_at, status, counts
                    from sync_runs
                    where status = 'ok'
                    order by id desc
                    limit 1
                    """,
                    fetch=True,
                )
                if rows:
                    finished_at, status, counts = rows[0]
                    last_sync = {
                        "finished_at": finished_at,
                        "status": status,
                        "counts": counts,
                    }
            except Exception:
                last_sync = None
            respond(self, 200, {
                "decay": decay,
                "runway": runway,
                "last_sync": last_sync,
            })
        except (TypeError, ValueError) as exc:
            respond(self, 400, {"error": str(exc)})
        except Exception as exc:
            print(f"[kani-sensei/overview] failed: {exc}", file=sys.stderr)
            respond(self, 502, {"error": "overview_failed"})

    def log_message(self, *args):
        pass

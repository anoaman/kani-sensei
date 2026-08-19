"""Interactive drill endpoints.

POST /api/drill                 start a session
POST /api/drill?action=answer   grade one answer
GET  /api/drill?session_id=     fetch session + miss recap
GET  /api/drill?action=stats    practice overview stats

Auth: session cookie, Bearer, or X-Cron-Secret.
"""

from http.server import BaseHTTPRequestHandler
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.auth import is_authorized, query_params, read_json_body
from shared.drill import (
    fetch_practice_overview,
    get_drill,
    grade_drill_answer,
    start_drill,
)
from shared.http_util import respond
from shared.neon import NeonClient


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Cron-Secret")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        if not is_authorized(self.headers):
            respond(self, 401, {"error": "unauthorized"})
            return
        query = query_params(self.path)
        action = (query.get("action", [None])[0] or "").lower()
        try:
            db = self._db()
            if action == "stats":
                respond(self, 200, fetch_practice_overview(db))
                return
            session_id = query.get("session_id", [None])[0]
            if not session_id:
                respond(self, 400, {"error": "session_id is required"})
                return
            respond(self, 200, get_drill(db, session_id))
        except ValueError as exc:
            respond(self, 404, {"error": str(exc)})
        except Exception as exc:
            print(f"[kani-sensei/drill] get failed: {exc}", file=sys.stderr)
            respond(self, 502, {"error": "drill_failed"})

    def do_POST(self):
        if not is_authorized(self.headers):
            respond(self, 401, {"error": "unauthorized"})
            return
        query = query_params(self.path)
        action = (query.get("action", [None])[0] or "").lower()
        try:
            body = read_json_body(self)
            db = self._db()
            if action == "answer":
                session_id = body.get("session_id")
                question_id = body.get("question_id")
                if session_id is None or question_id is None:
                    raise ValueError("session_id and question_id are required")
                result = grade_drill_answer(
                    db,
                    session_id,
                    question_id,
                    choice_index=body.get("choice_index"),
                    text=body.get("text"),
                    gave_up=bool(body.get("gave_up")),
                )
                respond(self, 200, result)
                return

            min_level = int(body.get("min_level"))
            max_level = int(body.get("max_level"))
            count = int(body.get("count", 10))
            modes = body.get("modes") or ["meaning", "reading"]
            if not isinstance(modes, list):
                raise ValueError("modes must be a list")
            if min_level < 1 or max_level > 60:
                raise ValueError("levels must be between 1 and 60")
            if min_level > max_level:
                raise ValueError("min_level cannot exceed max_level")
            drill = start_drill(
                db,
                min_level,
                max_level,
                count=count,
                modes=modes,
                kind=body.get("kind") or "recall",
                pool=body.get("pool") or "decay",
                object_types=body.get("object_types"),
            )
            respond(self, 200, drill)
        except (TypeError, ValueError, KeyError) as exc:
            respond(self, 400, {"error": str(exc)})
        except Exception as exc:
            print(f"[kani-sensei/drill] failed: {exc}", file=sys.stderr)
            respond(self, 502, {"error": "drill_failed", "detail": str(exc)})

    def _db(self):
        database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        return NeonClient(database_url)

    def log_message(self, *args):
        pass

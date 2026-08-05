"""Warm-Up Quiz endpoints.

POST /api/quiz              start a session
POST /api/quiz?action=answer grade one answer
GET  /api/quiz?session_id=  fetch session state

Auth: session cookie, Bearer, or X-Cron-Secret.
"""

from http.server import BaseHTTPRequestHandler
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.auth import is_authorized, query_params, read_json_body
from shared.http_util import optional_int, respond
from shared.neon import NeonClient
from shared.quiz import get_session, grade_answer, start_quiz


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
        session_id = query.get("session_id", [None])[0]
        if not session_id:
            respond(self, 400, {"error": "session_id is required"})
            return
        try:
            db = self._db()
            respond(self, 200, get_session(db, session_id))
        except ValueError as exc:
            respond(self, 404, {"error": str(exc)})
        except Exception as exc:
            print(f"[kani-sensei/quiz] get failed: {exc}", file=sys.stderr)
            respond(self, 502, {"error": "quiz_failed"})

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
                if session_id is None or question_id is None or "choice_index" not in body:
                    raise ValueError("session_id, question_id, and choice_index are required")
                result = grade_answer(db, session_id, question_id, body["choice_index"])
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
            quiz = start_quiz(db, min_level, max_level, count=count, modes=modes)
            respond(self, 200, quiz)
        except (TypeError, ValueError, KeyError) as exc:
            respond(self, 400, {"error": str(exc)})
        except Exception as exc:
            print(f"[kani-sensei/quiz] failed: {exc}", file=sys.stderr)
            respond(self, 502, {"error": "quiz_failed", "detail": str(exc)})

    def _db(self):
        database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        return NeonClient(database_url)

    def log_message(self, *args):
        pass

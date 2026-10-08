"""Level courses — per-level SRS restart, lessons, and reviews.

GET  /api/course?action=levels            level index with course status
GET  /api/course?level=N                  level page: items by type + course summary
GET  /api/course?action=lessons&level=N   next lesson batch (teaching cards)
GET  /api/course?action=reviews[&level=N] due review items
POST /api/course?action=start   {level}                     start/restart a level
POST /api/course?action=answer  {subject_id, prompt_type, text | gave_up}
"""

from http.server import BaseHTTPRequestHandler
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.auth import query_params
from shared.cache import clear as clear_cache
from shared.course import (
    answer,
    fetch_lessons,
    fetch_level,
    fetch_levels,
    fetch_reviews,
    jsonable,
    start_level,
)
from shared.auth import read_json_body
from shared.http_util import optional_int, respond
from shared.neon import NeonClient


def _level(value):
    level = int(value)
    if level < 1 or level > 60:
        raise ValueError("level must be between 1 and 60")
    return level


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Cron-Secret")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        query = query_params(self.path)
        action = (query.get("action", [None])[0] or "").lower()
        try:
            level = optional_int(query, "level")
            db = self._db()
            with db.reuse():
                if action == "levels":
                    body = fetch_levels(db)
                elif action == "lessons":
                    body = fetch_lessons(db, _level(level))
                elif action == "reviews":
                    body = fetch_reviews(db, _level(level) if level else None)
                else:
                    if level is None:
                        raise ValueError("level is required")
                    body = fetch_level(db, _level(level))
            respond(self, 200, jsonable(body))
        except (TypeError, ValueError) as exc:
            respond(self, 400, {"error": str(exc)})
        except Exception as exc:
            print(f"[kani-sensei/course] get failed: {exc}", file=sys.stderr)
            respond(self, 502, {"error": "course_failed", "detail": str(exc)})

    def do_POST(self):
        query = query_params(self.path)
        action = (query.get("action", [None])[0] or "").lower()
        try:
            body = read_json_body(self)
            db = self._db()
            with db.reuse():
                if action == "start":
                    result = start_level(db, _level(body.get("level")))
                elif action == "answer":
                    subject_id = body.get("subject_id")
                    if subject_id is None:
                        raise ValueError("subject_id is required")
                    result = answer(
                        db,
                        int(subject_id),
                        body.get("prompt_type"),
                        text=body.get("text"),
                        gave_up=bool(body.get("gave_up")),
                    )
                else:
                    raise ValueError("unknown action")
            clear_cache()
            respond(self, 200, jsonable(result))
        except (TypeError, ValueError, KeyError) as exc:
            respond(self, 400, {"error": str(exc)})
        except Exception as exc:
            print(f"[kani-sensei/course] post failed: {exc}", file=sys.stderr)
            respond(self, 502, {"error": "course_failed", "detail": str(exc)})

    def _db(self):
        database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        return NeonClient(database_url)

    def log_message(self, *args):
        pass

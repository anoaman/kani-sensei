"""Reading, daily read, dictation, and Kanji Web.

GET  /api/read                         coverage for every level, plus today's read
GET  /api/read?action=level&level=N    passages for one level
GET  /api/read?action=passage&id=...   one annotated passage
GET  /api/read?action=daily            today's read, built on first open
GET  /api/read?action=web&level=N      Kanji Web for one level
POST /api/read?action=lookup           {passage_id, subject_id}
POST /api/read?action=dictation        {passage_id, index, text}
POST /api/read?action=finish           {passage_id, quiz_correct, quiz_total, listen_correct, listen_total}
POST /api/read?action=custom           {text, title?}
"""

from http.server import BaseHTTPRequestHandler
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.auth import query_params, read_json_body
from shared.http_util import respond
from shared.kanji_web import fetch_web
from shared.neon import NeonClient
from shared.reader import (
    CatalogMissing,
    IndexMissing,
    build_daily_read,
    fetch_index,
    fetch_level_view,
    finish_passage,
    grade_passage_dictation,
    note_lookup,
    render_passage,
    require_index,
    save_custom,
)


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
        action = (query.get("action", [None])[0] or "index").lower()
        try:
            db = self._db()
            with db.reuse():
                require_index(db)
                if action == "index":
                    body = fetch_index(db)
                elif action == "level":
                    body = fetch_level_view(db, _level(query.get("level", [None])[0]))
                elif action == "passage":
                    passage_id = query.get("id", [None])[0]
                    if not passage_id:
                        raise ValueError("id is required")
                    body = render_passage(db, passage_id)
                elif action == "daily":
                    body = build_daily_read(db)
                elif action == "web":
                    body = fetch_web(db, _level(query.get("level", [None])[0]))
                else:
                    raise ValueError("unknown action")
            respond(self, 200, body)
        except CatalogMissing:
            respond(self, 409, {"error": "catalog_missing"})
        except IndexMissing:
            respond(self, 409, {"error": "index_missing"})
        except (TypeError, ValueError) as exc:
            respond(self, 400, {"error": str(exc)})
        except Exception as exc:
            print(f"[kani-sensei/read] get failed: {exc}", file=sys.stderr)
            respond(self, 502, {"error": "read_failed", "detail": str(exc)})

    def do_POST(self):
        query = query_params(self.path)
        action = (query.get("action", [None])[0] or "").lower()
        try:
            body = read_json_body(self)
            db = self._db()
            with db.reuse():
                require_index(db)
                passage_id = body.get("passage_id")
                if action == "lookup":
                    if not passage_id or body.get("subject_id") is None:
                        raise ValueError("passage_id and subject_id are required")
                    result = note_lookup(db, passage_id, body.get("subject_id"))
                elif action == "dictation":
                    if not passage_id or body.get("index") is None:
                        raise ValueError("passage_id and index are required")
                    result = grade_passage_dictation(db, passage_id, body.get("index"), body.get("text"))
                elif action == "finish":
                    if not passage_id:
                        raise ValueError("passage_id is required")
                    result = finish_passage(
                        db,
                        passage_id,
                        body.get("quiz_correct"),
                        body.get("quiz_total"),
                        body.get("listen_correct"),
                        body.get("listen_total"),
                    )
                elif action == "custom":
                    result = save_custom(db, body.get("text"), body.get("title"))
                else:
                    raise ValueError("unknown action")
            respond(self, 200, result)
        except CatalogMissing:
            respond(self, 409, {"error": "catalog_missing"})
        except IndexMissing:
            respond(self, 409, {"error": "index_missing"})
        except (TypeError, ValueError, KeyError) as exc:
            respond(self, 400, {"error": str(exc)})
        except Exception as exc:
            print(f"[kani-sensei/read] post failed: {exc}", file=sys.stderr)
            respond(self, 502, {"error": "read_failed", "detail": str(exc)})

    def _db(self):
        database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        return NeonClient(database_url)

    def log_message(self, *args):
        pass

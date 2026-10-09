"""Phone gate for an iPhone Shortcut.

GET  /api/gate                      {"open", "reason", "until"}
GET  /api/gate?format=text          plain "open" or "locked", for Shortcuts
POST /api/gate?action=start         the open gate, or a fresh one: {gate_id, drill, tier}
POST /api/gate?action=seen {gate_id, question_id}  start that question's clock
POST /api/gate?action=finish {gate_id}  pass/fail once the quiz is over
"""

from http.server import BaseHTTPRequestHandler
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.auth import query_params, read_json_body
from shared.course import jsonable
from shared.gate import finish, seen, start, status
from shared.http_util import respond
from shared.neon import NeonClient


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = query_params(self.path)
        try:
            db = self._db()
            with db.reuse():
                body = status(db)
        except Exception as exc:
            print(f"[kani-sensei/gate] status failed: {exc}", file=sys.stderr)
            # Fail open: a broken server shouldn't brick the phone.
            body = {"open": True, "reason": "error", "until": None}
        if (query.get("format", [""])[0] or "").lower() == "text":
            payload = ("open" if body["open"] else "locked").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        respond(self, 200, body)

    def do_POST(self):
        query = query_params(self.path)
        action = (query.get("action", [None])[0] or "").lower()
        try:
            body = read_json_body(self)
            db = self._db()
            with db.reuse():
                if action == "start":
                    result = start(db)
                elif action == "seen":
                    result = seen(db, int(body.get("gate_id")), str(body.get("question_id")))
                elif action == "finish":
                    result = finish(db, int(body.get("gate_id")))
                else:
                    raise ValueError("unknown action")
            respond(self, 200, jsonable(result))
        except (TypeError, ValueError) as exc:
            respond(self, 400, {"error": str(exc)})
        except Exception as exc:
            print(f"[kani-sensei/gate] post failed: {exc}", file=sys.stderr)
            respond(self, 502, {"error": "gate_failed", "detail": str(exc)})

    def _db(self):
        database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        return NeonClient(database_url)

    def log_message(self, *args):
        pass

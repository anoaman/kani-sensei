"""Auth login for the web UI.

POST /api/login  { "password": "..." } → Set-Cookie session
"""

from http.server import BaseHTTPRequestHandler
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.auth import cookie_header, issue_token, read_json_body, site_password
from shared.http_util import respond


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Cron-Secret")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

    def do_POST(self):
        try:
            body = read_json_body(self)
            password = (body.get("password") or "").strip()
            expected = site_password()
            if not expected or password != expected:
                respond(self, 401, {"error": "unauthorized"})
                return
            token, expires = issue_token()
            respond(
                self,
                200,
                {"ok": True, "user": "kibz"},
                extra_headers={"Set-Cookie": cookie_header(token, expires, secure=True)},
            )
        except Exception as exc:
            print(f"[kani-sensei/login] failed: {exc}", file=sys.stderr)
            respond(self, 400, {"error": str(exc)})

    def log_message(self, *args):
        pass

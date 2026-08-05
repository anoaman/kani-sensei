"""POST /api/logout — clear the browser session cookie."""

from http.server import BaseHTTPRequestHandler
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.auth import clear_cookie_header
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
        respond(
            self,
            200,
            {"ok": True},
            extra_headers={"Set-Cookie": clear_cookie_header(secure=True)},
        )

    def log_message(self, *args):
        pass

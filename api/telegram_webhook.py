from http.server import BaseHTTPRequestHandler
import os
import json
import sys
from datetime import datetime, timezone, timedelta
import urllib.request

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.tick import cached_snapshot

WIB = timezone(timedelta(hours=7))
WK_BASE = "https://api.wanikani.com/v2"
TG_BASE = "https://api.telegram.org"


def wk_get(path, token):
    url = f"{WK_BASE}{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Wanikani-Revision": "20170710",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def tg_send(token, chat_id, text, reply_to=None):
    url = f"{TG_BASE}/bot{token}/sendMessage"
    body = {
        "chat_id": int(chat_id),
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
    if reply_to:
        body["reply_to_message_id"] = reply_to
    payload = json.dumps(body).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        wk_token = os.environ.get("WANIKANI_API_KEY")
        tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")

        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length else {}

        message = body.get("message", {})
        text = message.get("text", "").strip()
        message_id = message.get("message_id")
        from_chat = str(message.get("chat", {}).get("id", ""))

        # Always 200 to Telegram to stop retries
        self._respond(200, {"ok": True})

        if from_chat != chat_id:
            return

        cmd = text.lower().split("@")[0]
        if cmd == "/status":
            try:
                snapshot = None
                if wk_token:
                    try:
                        reviews = wk_get(
                            "/assignments?immediately_available_for_review=true", wk_token
                        )["total_count"]
                        apprentice = wk_get("/assignments?srs_stages=1,2,3,4", wk_token)["total_count"]
                        summary = wk_get("/summary", wk_token)
                        lessons = sum(
                            len(s.get("subject_ids", []))
                            for s in summary["data"].get("lessons", [])
                        )
                        user_data = wk_get("/user", wk_token)
                        level = user_data["data"]["level"]
                        snapshot = {"source": "live"}
                    except Exception as e:
                        print(f"[kani-sensei] /status live fetch failed; using cache: {e}", file=sys.stderr)
                if snapshot is None:
                    snapshot = cached_snapshot(database_url)
                    if snapshot is None:
                        tg_send(tg_token, chat_id, "Kani Sensei has no live or cached WaniKani data yet.", reply_to=message_id)
                        return
                    reviews = snapshot["reviews"]
                    apprentice = snapshot["apprentice"]
                    lessons = snapshot["lessons"]
                    level = snapshot["level"]

                now_wib = datetime.now(timezone.utc).astimezone(WIB)
                label = "WaniKani snapshot" if snapshot["source"] == "live" else "Cached WaniKani snapshot"
                freshness = ""
                if snapshot["source"] == "cached":
                    synced_at = snapshot.get("synced_at")
                    if synced_at:
                        if isinstance(synced_at, str):
                            synced_at = datetime.fromisoformat(synced_at.replace("Z", "+00:00"))
                        if synced_at.tzinfo is None:
                            synced_at = synced_at.replace(tzinfo=timezone.utc)
                        freshness = f"\nLast synced: {synced_at.astimezone(WIB).strftime('%d %b, %H:%M WIB')}"
                reply = (
                    f"<b>{label} — {now_wib.strftime('%H:%M WIB')}</b>\n"
                    f"Reviews due: <b>{reviews}</b>\n"
                    f"Apprentice: {apprentice} · Lessons: {lessons} · Level: {level}"
                    f"{freshness}"
                )
                if reviews > 0:
                    reply += '\n<a href="https://www.wanikani.com/subjects/review">Open reviews →</a>'

                tg_send(tg_token, chat_id, reply, reply_to=message_id)
            except Exception as e:
                print(f"[kani-sensei] /status failed: {e}", file=sys.stderr)

    def _respond(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass

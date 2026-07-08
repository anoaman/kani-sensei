from http.server import BaseHTTPRequestHandler
import os
import json
import sys
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.error

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


def tg_send(token, chat_id, text):
    url = f"{TG_BASE}/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": int(chat_id),
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json"
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def verdict_line(reviews, apprentice):
    if apprentice > 150:
        return "circuit breaker: pause lessons."
    if reviews > 150:
        return "queue's on fire. Clear it now."
    if apprentice > 100:
        return "heavy load. Grind it down."
    if reviews > 50:
        return "solid queue. Let's go."
    return "clear to lift."


def build_nudge(t, reviews, apprentice, lessons, level):
    time_str = t.strftime("%H:%M")
    v = verdict_line(reviews, apprentice)
    link = "https://www.wanikani.com/subjects/review"
    return (
        f"<b>{time_str} WIB — {reviews} reviews due</b>\n"
        f"Apprentice: {apprentice} · Lessons: {lessons} · Level: {level}\n"
        f"Verdict: {v}\n"
        f'<a href="{link}">Open reviews →</a>'
    )


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Read env at request time — Vercel serverless requirement
        wk_token = os.environ.get("WANIKANI_API_KEY")
        tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        cron_secret = os.environ.get("CRON_SECRET")

        if not all([wk_token, tg_token, chat_id, cron_secret]):
            print("[kani-sensei] ERROR: missing required env vars", file=sys.stderr)
            self._respond(500, {"error": "missing_env_vars"})
            return

        if self.headers.get("X-Cron-Secret") != cron_secret:
            self._respond(401, {"error": "unauthorized"})
            return

        # Derive WIB time from UTC — never trust server locale
        now_utc = datetime.now(timezone.utc)
        t = now_utc.astimezone(WIB)
        hour = t.hour

        in_window = (6 <= hour < 9) or (12 <= hour < 14)
        if not in_window:
            self._respond(200, {"status": "outside_window", "wib_hour": hour})
            return

        try:
            reviews = wk_get(
                "/assignments?immediately_available_for_review=true", wk_token
            )["total_count"]
        except Exception as e:
            print(f"[kani-sensei] WK reviews fetch failed: {e}", file=sys.stderr)
            self._respond(502, {"error": "wanikani_fetch_failed", "detail": str(e)})
            return

        if reviews == 0:
            self._respond(200, {"status": "no_reviews", "wib_hour": hour})
            return

        try:
            apprentice = wk_get(
                "/assignments?srs_stages=1,2,3,4", wk_token
            )["total_count"]
        except Exception as e:
            print(f"[kani-sensei] WK apprentice fetch failed: {e}", file=sys.stderr)
            self._respond(502, {"error": "wanikani_fetch_failed", "detail": str(e)})
            return

        # Stateless daily accuracy not available without deprecated /v2/reviews.
        # Fall back to lessons + level — reliable and cheap.
        try:
            summary = wk_get("/summary", wk_token)
            lessons = sum(
                len(slot.get("subject_ids", []))
                for slot in summary["data"].get("lessons", [])
            )
            user_data = wk_get("/user", wk_token)
            level = user_data["data"]["level"]
        except Exception as e:
            print(f"[kani-sensei] WK context fetch non-fatal: {e}", file=sys.stderr)
            lessons, level = "?", "?"

        # v1.1 miner scaffold — MINER_ENABLED=false, ANTHROPIC_API_KEY unset
        miner_enabled = os.environ.get("MINER_ENABLED", "false").lower() == "true"
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if miner_enabled and anthropic_key and 8 <= hour < 9:
            # TODO v1.1: fetch burned/guru vocab → Haiku → spoiler sentences
            pass

        nudge = build_nudge(t, reviews, apprentice, lessons, level)

        try:
            tg_send(tg_token, chat_id, nudge)
        except Exception as e:
            print(f"[kani-sensei] Telegram send failed: {e}", file=sys.stderr)
            self._respond(502, {"error": "telegram_send_failed", "detail": str(e)})
            return

        self._respond(200, {"status": "sent", "reviews": reviews, "apprentice": apprentice})

    def _respond(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass  # suppress default HTTP access log noise

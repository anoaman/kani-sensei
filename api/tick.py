from http.server import BaseHTTPRequestHandler
import os
import json
import sys
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.error

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.neon import NeonClient

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


def build_nudge(t, reviews, apprentice, lessons, level, source="live"):
    time_str = t.strftime("%H:%M")
    v = verdict_line(reviews, apprentice)
    link = "https://www.wanikani.com/subjects/review"
    source_note = "\nUsing last synced data." if source == "cached" else ""
    return (
        f"<b>{time_str} WIB — {reviews} reviews due</b>\n"
        f"Apprentice: {apprentice} · Lessons: {lessons} · Level: {level}\n"
        f"Verdict: {v}{source_note}\n"
        f'<a href="{link}">Open reviews →</a>'
    )


def cached_snapshot(database_url):
    """Build a usable status snapshot from the last successful WK sync."""
    if not database_url:
        return None
    db = NeonClient(database_url)
    rows = db.execute(
        """
        select
          count(*) filter (where a.available_at <= now()) as reviews,
          count(*) filter (where a.srs_stage between 1 and 4) as apprentice,
          coalesce(max(s.level), 0) as level,
          (select finished_at from sync_runs where status='ok' order by id desc limit 1)
        from wk_assignments a
        join wk_subjects s on s.id = a.subject_id
        """,
        fetch=True,
    )
    if not rows:
        return None
    reviews, apprentice, level, synced_at = rows[0]
    if synced_at is None:
        return None
    return {
        "reviews": int(reviews or 0),
        "apprentice": int(apprentice or 0),
        "lessons": "?",
        "level": int(level or 0) or "?",
        "synced_at": synced_at,
        "source": "cached",
    }


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Read env at request time — Vercel serverless requirement
        wk_token = os.environ.get("WANIKANI_API_KEY")
        tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        cron_secret = os.environ.get("CRON_SECRET")
        database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")

        if not all([tg_token, chat_id, cron_secret]):
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

        snapshot = None
        if wk_token:
            try:
                snapshot = {
                    "reviews": wk_get(
                        "/assignments?immediately_available_for_review=true", wk_token
                    )["total_count"],
                    "source": "live",
                }
            except Exception as e:
                print(f"[kani-sensei] WK reviews fetch failed; using cache: {e}", file=sys.stderr)
        if snapshot is None:
            try:
                snapshot = cached_snapshot(database_url)
            except Exception as e:
                print(f"[kani-sensei] cached snapshot failed: {e}", file=sys.stderr)
            if snapshot is None:
                self._respond(200, {"status": "skipped", "reason": "no_live_or_cached_data"})
                return

        reviews = snapshot["reviews"]

        if reviews == 0:
            self._respond(200, {"status": "no_reviews", "wib_hour": hour})
            return

        if snapshot["source"] == "cached":
            apprentice = snapshot["apprentice"]
            lessons = snapshot["lessons"]
            level = snapshot["level"]
        else:
            try:
                apprentice = wk_get(
                    "/assignments?srs_stages=1,2,3,4", wk_token
                )["total_count"]
            except Exception as e:
                print(f"[kani-sensei] WK apprentice fetch failed; using cache: {e}", file=sys.stderr)
                cached = cached_snapshot(database_url)
                if cached is None:
                    self._respond(200, {"status": "skipped", "reason": "incomplete_live_data"})
                    return
                snapshot = cached
                reviews = cached["reviews"]
                apprentice = cached["apprentice"]
                lessons = cached["lessons"]
                level = cached["level"]

        # Stateless daily accuracy not available without deprecated /v2/reviews.
        # Fall back to lessons + level — reliable and cheap.
        if snapshot["source"] == "live":
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

        nudge = build_nudge(
            t, reviews, apprentice, lessons, level, source=snapshot["source"],
        )

        try:
            tg_send(tg_token, chat_id, nudge)
        except Exception as e:
            print(f"[kani-sensei] Telegram send failed: {e}", file=sys.stderr)
            self._respond(502, {"error": "telegram_send_failed", "detail": str(e)})
            return

        self._respond(200, {
            "status": "sent",
            "source": snapshot["source"],
            "reviews": reviews,
            "apprentice": apprentice,
        })

    def _respond(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass  # suppress default HTTP access log noise

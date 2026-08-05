"""Kani Sensei platform — Phase 0 daily sync job.

Pulls the WK subject catalog (bounded to the user's current level), review
statistics, and assignments, then upserts them into Neon/Postgres. Idempotent: every
table upserts on its primary key, so a daily re-run just refreshes the snapshot.
Writes one sync_runs audit row (open 'running' -> close 'ok'/'error').

Protected by X-Cron-Secret (same pattern as api/tick.py). Hit daily by cron-job.org.

Env required: WANIKANI_API_KEY, DATABASE_URL, CRON_SECRET
"""

from http.server import BaseHTTPRequestHandler
import os
import sys
import json
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.wanikani_client import WaniKaniClient
from shared.neon import NeonClient

CHUNK = 100


UPSERT_SUBJECT = """
insert into wk_subjects
  (id, object_type, level, characters, slug, primary_meaning, readings, meanings, raw, synced_at)
values (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s)
on conflict(id) do update set
  object_type=excluded.object_type, level=excluded.level, characters=excluded.characters,
  slug=excluded.slug, primary_meaning=excluded.primary_meaning, readings=excluded.readings,
  meanings=excluded.meanings, raw=excluded.raw, synced_at=excluded.synced_at
"""

UPSERT_STAT = """
insert into wk_review_stats
  (subject_id, meaning_correct, meaning_incorrect, reading_correct, reading_incorrect, percentage_correct, updated_at)
values (%s,%s,%s,%s,%s,%s,%s)
on conflict(subject_id) do update set
  meaning_correct=excluded.meaning_correct, meaning_incorrect=excluded.meaning_incorrect,
  reading_correct=excluded.reading_correct, reading_incorrect=excluded.reading_incorrect,
  percentage_correct=excluded.percentage_correct, updated_at=excluded.updated_at
"""

UPSERT_ASSIGN = """
insert into wk_assignments
  (subject_id, srs_stage, available_at, unlocked_at, started_at, passed_at, burned_at, synced_at)
values (%s,%s,%s,%s,%s,%s,%s,%s)
on conflict(subject_id) do update set
  srs_stage=excluded.srs_stage, available_at=excluded.available_at, unlocked_at=excluded.unlocked_at,
  started_at=excluded.started_at, passed_at=excluded.passed_at, burned_at=excluded.burned_at,
  synced_at=excluded.synced_at
"""

# Freeze today's SRS + accuracy so Decay Map can detect real stage drops.
SNAPSHOT_TODAY = """
insert into wk_assignment_snapshots
  (snap_date, subject_id, srs_stage,
   meaning_correct, meaning_incorrect, reading_correct, reading_incorrect)
select
  current_date,
  a.subject_id,
  a.srs_stage,
  r.meaning_correct,
  r.meaning_incorrect,
  r.reading_correct,
  r.reading_incorrect
from wk_assignments a
left join wk_review_stats r on r.subject_id = a.subject_id
on conflict (snap_date, subject_id) do update set
  srs_stage = excluded.srs_stage,
  meaning_correct = excluded.meaning_correct,
  meaning_incorrect = excluded.meaning_incorrect,
  reading_correct = excluded.reading_correct,
  reading_incorrect = excluded.reading_incorrect
"""


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---- WK payload -> row-tuple mappers (order matches the UPSERT columns) ----

def map_subject(item, now):
    d = item["data"]
    meanings = d.get("meanings", [])
    primary = next((m["meaning"] for m in meanings if m.get("primary")), None)
    return [
        item["id"], item["object"], d.get("level"), d.get("characters"),
        d.get("slug"), primary,
        json.dumps(d.get("readings", []), ensure_ascii=False),
        json.dumps(meanings, ensure_ascii=False),
        json.dumps(d, ensure_ascii=False),
        now,
    ]


def map_review_stat(item, now):
    d = item["data"]
    return [
        d.get("subject_id"), d.get("meaning_correct"), d.get("meaning_incorrect"),
        d.get("reading_correct"), d.get("reading_incorrect"),
        d.get("percentage_correct"), now,
    ]


def map_assignment(item, now):
    d = item["data"]
    return [
        d.get("subject_id"), d.get("srs_stage"), d.get("available_at"),
        d.get("unlocked_at"), d.get("started_at"), d.get("passed_at"),
        d.get("burned_at"), now,
    ]


# ---- core sync -------------------------------------------------------------

def run_sync(wk_token, db):
    wk = WaniKaniClient(wk_token)
    now = _now_iso()

    run_id = db.execute(
        "insert into sync_runs (started_at, status) values (%s, 'running') returning id",
        [now],
        fetch=True,
    )[0][0]

    try:
        level = wk.get_user().get("level") or 60
        subjects = wk.get_subjects(levels=list(range(1, level + 1)))
        review_stats = wk.get_review_statistics()
        assignments = wk.get_assignments()

        known = {s["id"] for s in subjects}

        # Subjects first — stats/assignments reference them.
        n_subjects = db.executemany(
            UPSERT_SUBJECT, [map_subject(s, now) for s in subjects], CHUNK)
        n_stats = db.executemany(
            UPSERT_STAT,
            [map_review_stat(r, now) for r in review_stats
             if r["data"].get("subject_id") in known], CHUNK)
        n_assign = db.executemany(
            UPSERT_ASSIGN,
            [map_assignment(a, now) for a in assignments
             if a["data"].get("subject_id") in known], CHUNK)

        n_snapshots = 0
        try:
            db.execute(SNAPSHOT_TODAY)
            n_snapshots = db.execute(
                "select count(*) from wk_assignment_snapshots where snap_date = current_date",
                fetch=True,
            )[0][0]
        except Exception as snap_err:
            # Snapshot table may not exist yet on a rolling deploy — sync still succeeds.
            print(f"[kani-sensei/sync] snapshot skipped: {snap_err}", file=sys.stderr)

        counts = {
            "subjects": n_subjects,
            "review_stats": n_stats,
            "assignments": n_assign,
            "snapshots_today": int(n_snapshots or 0),
        }
        db.execute(
            "update sync_runs set status='ok', finished_at=%s, counts=%s::jsonb where id=%s",
            [_now_iso(), json.dumps(counts), run_id])
        return counts
    except Exception as e:
        try:
            db.execute(
                "update sync_runs set status='error', finished_at=%s, error=%s where id=%s",
                [_now_iso(), str(e), run_id])
        except Exception:
            pass
        raise


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        wk_token = os.environ.get("WANIKANI_API_KEY")
        database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
        cron_secret = os.environ.get("CRON_SECRET")

        if not all([wk_token, database_url, cron_secret]):
            print("[kani-sensei/sync] ERROR: missing required env vars", file=sys.stderr)
            self._respond(500, {"error": "missing_env_vars"})
            return

        if self.headers.get("X-Cron-Secret") != cron_secret:
            self._respond(401, {"error": "unauthorized"})
            return

        try:
            db = NeonClient(database_url)
            counts = run_sync(wk_token, db)
        except Exception as e:
            print(f"[kani-sensei/sync] sync failed: {e}", file=sys.stderr)
            self._respond(502, {"error": "sync_failed", "detail": str(e)})
            return

        self._respond(200, {"status": "ok", "counts": counts})

    def _respond(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass

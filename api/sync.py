"""Kani Sensei platform — Phase 0 daily sync job.

Pulls the WK subject catalog, review statistics, and assignments, then upserts
them into Supabase. Idempotent: every table upserts on its primary key, so a
daily re-run just refreshes the snapshot. Writes one sync_runs audit row.

Protected by X-Cron-Secret (same pattern as api/tick.py). Hit daily by cron-job.org.

Supabase writes go through PostgREST over stdlib urllib — no supabase-py needed,
keeping this consistent with the zero-dependency codebase. Upserts use
`Prefer: resolution=merge-duplicates` so the table primary key resolves conflicts.

Env required: WANIKANI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY, CRON_SECRET
"""

from http.server import BaseHTTPRequestHandler
import os
import sys
import json
from datetime import datetime, timezone
import urllib.request
import urllib.error

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.wanikani_client import WaniKaniClient

BATCH = 500  # PostgREST upsert batch size


# ---- Supabase (PostgREST) helpers -----------------------------------------

def _sb_headers(service_key, prefer):
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def sb_upsert(base_url, service_key, table, rows):
    """Batch-upsert rows into a table. Conflict resolves on the primary key."""
    if not rows:
        return 0
    url = f"{base_url}/rest/v1/{table}"
    total = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        body = json.dumps(chunk).encode()
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers=_sb_headers(service_key, "resolution=merge-duplicates,return=minimal"),
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        total += len(chunk)
    return total


def sb_insert_returning(base_url, service_key, table, row):
    """Insert one row and return it (used for the sync_runs open/close)."""
    url = f"{base_url}/rest/v1/{table}"
    body = json.dumps(row).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers=_sb_headers(service_key, "return=representation"),
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())[0]


def sb_patch(base_url, service_key, table, match_col, match_val, patch):
    url = f"{base_url}/rest/v1/{table}?{match_col}=eq.{match_val}"
    body = json.dumps(patch).encode()
    req = urllib.request.Request(
        url, data=body, method="PATCH",
        headers=_sb_headers(service_key, "return=minimal"),
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


# ---- WK payload -> table row mappers --------------------------------------

def map_subject(item):
    d = item["data"]
    meanings = d.get("meanings", [])
    primary = next((m["meaning"] for m in meanings if m.get("primary")), None)
    return {
        "id": item["id"],
        "object_type": item["object"],
        "level": d.get("level"),
        "characters": d.get("characters"),
        "slug": d.get("slug"),
        "primary_meaning": primary,
        "readings": d.get("readings", []),   # radicals have none
        "meanings": meanings,
        "raw": d,
        "synced_at": _now_iso(),
    }


def map_review_stat(item):
    d = item["data"]
    return {
        "subject_id": d.get("subject_id"),
        "meaning_correct": d.get("meaning_correct"),
        "meaning_incorrect": d.get("meaning_incorrect"),
        "reading_correct": d.get("reading_correct"),
        "reading_incorrect": d.get("reading_incorrect"),
        "percentage_correct": d.get("percentage_correct"),
        "updated_at": _now_iso(),
    }


def map_assignment(item):
    d = item["data"]
    return {
        "subject_id": d.get("subject_id"),
        "srs_stage": d.get("srs_stage"),
        "available_at": d.get("available_at"),
        "unlocked_at": d.get("unlocked_at"),
        "started_at": d.get("started_at"),
        "passed_at": d.get("passed_at"),
        "burned_at": d.get("burned_at"),
        "synced_at": _now_iso(),
    }


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---- core sync -------------------------------------------------------------

def run_sync(wk_token, sb_url, sb_key):
    wk = WaniKaniClient(wk_token)

    run = sb_insert_returning(sb_url, sb_key, "sync_runs", {"status": "running"})
    run_id = run["id"]

    try:
        subjects = wk.get_subjects()
        review_stats = wk.get_review_statistics()
        assignments = wk.get_assignments()

        # Subjects must land first — review_stats/assignments FK to them.
        n_subjects = sb_upsert(sb_url, sb_key, "wk_subjects",
                               [map_subject(s) for s in subjects])

        # Only keep stats/assignments whose subject we actually cached.
        known = {s["id"] for s in subjects}
        n_stats = sb_upsert(sb_url, sb_key, "wk_review_stats",
                            [map_review_stat(r) for r in review_stats
                             if r["data"].get("subject_id") in known])
        n_assign = sb_upsert(sb_url, sb_key, "wk_assignments",
                             [map_assignment(a) for a in assignments
                              if a["data"].get("subject_id") in known])

        counts = {"subjects": n_subjects, "review_stats": n_stats,
                  "assignments": n_assign}
        sb_patch(sb_url, sb_key, "sync_runs", "id", run_id,
                 {"status": "ok", "finished_at": _now_iso(), "counts": counts})
        return counts
    except Exception as e:
        sb_patch(sb_url, sb_key, "sync_runs", "id", run_id,
                 {"status": "error", "finished_at": _now_iso(), "error": str(e)})
        raise


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        wk_token = os.environ.get("WANIKANI_API_KEY")
        sb_url = os.environ.get("SUPABASE_URL")
        sb_key = os.environ.get("SUPABASE_SERVICE_KEY")
        cron_secret = os.environ.get("CRON_SECRET")

        if not all([wk_token, sb_url, sb_key, cron_secret]):
            print("[kani-sensei/sync] ERROR: missing required env vars", file=sys.stderr)
            self._respond(500, {"error": "missing_env_vars"})
            return

        if self.headers.get("X-Cron-Secret") != cron_secret:
            self._respond(401, {"error": "unauthorized"})
            return

        try:
            counts = run_sync(wk_token, sb_url.rstrip("/"), sb_key)
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

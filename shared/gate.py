"""The gate: an iPhone Shortcut asks before a time-sink app opens.

Between 08:00 and 22:00 WIB the apps lock every WINDOW hours. Clearing a gate
(GATE_SIZE items, misses come back until right) opens them for the next
WINDOW hours. Night is always open. Gate items come out of today's set first,
so the gates finish the daily set as a side effect.

A pass is verified, not trusted: the gate snapshots each item's review_count
at start, and only passes once every item has finished a round since.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from shared.course import QUEUE_COLUMNS, queue_item
from shared.daily import WIB, ensure_schema as ensure_daily_schema, fetch_daily

GATE_SIZE = 5
WINDOW = timedelta(hours=3)
DAY_START = 8   # WIB hour the gate wakes up
DAY_END = 22    # WIB hour it goes to sleep

SCHEMA = """
create table if not exists gates (
    id           bigserial primary key,
    started_at   timestamptz not null default now(),
    subject_ids  bigint[] not null,
    baseline     jsonb not null,
    passed_at    timestamptz
)
"""

_SCHEMA_READY = False


def ensure_schema(db):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    ensure_daily_schema(db)
    try:
        if db.has_relation("public.gates"):
            _SCHEMA_READY = True
            return
    except Exception:
        pass
    db.execute(SCHEMA)
    _SCHEMA_READY = True


def _now():
    return datetime.now(timezone.utc)


def quiet_until(now):
    """If it's night in WIB, when the gate wakes up; else None."""
    local = now.astimezone(WIB)
    if DAY_START <= local.hour < DAY_END:
        return None
    wake = local.replace(hour=DAY_START, minute=0, second=0, microsecond=0)
    if local.hour >= DAY_END:
        wake += timedelta(days=1)
    return wake.astimezone(timezone.utc)


def gate_state(now, last_pass):
    """Pure: open/locked, why, and until when."""
    wake = quiet_until(now)
    if wake:
        return {"open": True, "reason": "night", "until": wake}
    if last_pass and now < last_pass + WINDOW:
        return {"open": True, "reason": "cleared", "until": last_pass + WINDOW}
    return {"open": False, "reason": "locked", "until": None}


def _last_pass(db):
    rows = db.execute("select max(passed_at) from gates", fetch=True)
    return rows[0][0] if rows else None


def status(db, now=None):
    ensure_schema(db)
    now = now or _now()
    state = gate_state(now, _last_pass(db))
    return {**state, "until": state["until"].isoformat() if state["until"] else None}


def _top_up(db, exclude, limit):
    """Today's set is done or short: relearns, then due reviews, then the
    Guru+ items closest to due (study ahead)."""
    if limit <= 0:
        return []
    rows = db.execute(
        f"""
        select {QUEUE_COLUMNS}
        from course_items c
        join wk_subjects s on s.id = c.subject_id
        where c.srs_stage between 1 and 8 and not (c.subject_id = any(%s))
        order by
          case when c.srs_stage < 5 then 0 when c.available_at <= now() then 1 else 2 end,
          c.available_at, random()
        limit %s
        """,
        [list(exclude), limit],
        fetch=True,
    )
    return [queue_item(db, row) for row in rows]


def start(db, size=GATE_SIZE):
    ensure_schema(db)
    items = fetch_daily(db)["items"][:size]
    items += _top_up(db, {item["subject_id"] for item in items}, size - len(items))
    ids = [item["subject_id"] for item in items]
    baseline = {}
    if ids:
        rows = db.execute(
            "select subject_id, review_count from course_items where subject_id = any(%s)",
            [ids],
            fetch=True,
        )
        baseline = {str(sid): int(count) for sid, count in rows}
    rows = db.execute(
        "insert into gates (subject_ids, baseline) values (%s, %s) returning id",
        [ids, json.dumps(baseline)],
        fetch=True,
    )
    return {"gate_id": rows[0][0], "items": items, "status": status(db)}


def finish(db, gate_id):
    """Pass the gate if every item finished a round since it started."""
    ensure_schema(db)
    rows = db.execute(
        "select subject_ids, baseline, passed_at from gates where id = %s",
        [gate_id],
        fetch=True,
    )
    if not rows:
        raise ValueError("unknown gate")
    subject_ids, baseline, passed_at = rows[0]
    baseline = baseline if isinstance(baseline, dict) else json.loads(baseline or "{}")
    if not passed_at:
        ids = [int(x) for x in subject_ids or []]
        current = {}
        if ids:
            current = {
                str(sid): int(count)
                for sid, count in db.execute(
                    "select subject_id, review_count from course_items where subject_id = any(%s)",
                    [ids],
                    fetch=True,
                )
            }
        pending = [sid for sid in ids if current.get(str(sid), 0) <= baseline.get(str(sid), 0)]
        if pending:
            return {"passed": False, "pending": pending, "status": status(db)}
        db.execute("update gates set passed_at = now() where id = %s and passed_at is null", [gate_id])
    return {"passed": True, "pending": [], "status": status(db)}

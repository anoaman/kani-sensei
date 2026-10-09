"""The gate: an iPhone Shortcut asks before a time-sink app opens.

Between 08:00 and 22:00 WIB the apps lock every WINDOW hours. Clearing a gate
opens them for the next WINDOW hours. Night is always open.

A gate is a quick quiz, not coursework: GATE_SIZE typed questions on things
you've already Guru'd (in the course first; WaniKani-snapshot Guru+ tops up a
thin pool), weighted toward rot. Misses come back until right. It never
touches course SRS. A pass is verified: the drill session must be finished.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.course import GURU
from shared.daily import WIB, ensure_schema as ensure_daily_schema
from shared.drill import build_drill, ensure_schema as ensure_drill_schema, persist_drill, public_drill
from shared.quiz import fetch_pool

GATE_SIZE = 5
MIN_POOL = 15  # below this many course Guru items, borrow WaniKani's
GATE_TYPES = ["radical", "kanji", "vocabulary", "kana_vocabulary"]
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
DRILL_COLUMN = "alter table gates add column if not exists drill_id uuid"

_SCHEMA_READY = False


def ensure_schema(db):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    ensure_daily_schema(db)
    ensure_drill_schema(db)
    db.execute(SCHEMA)
    db.execute(DRILL_COLUMN)
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


def _guru(db, table):
    sql = f"select subject_id from {table} where srs_stage >= %s"
    return {int(row[0]) for row in db.execute(sql, [GURU], fetch=True)}


def gate_pool(db):
    """Quiz rows for items you've Guru'd: the course's first; WaniKani's
    snapshot Guru+ joins in while the course pool is thin."""
    rows = fetch_pool(db, 1, 60, object_types=GATE_TYPES)
    course = _guru(db, "course_items")
    picked = [row for row in rows if int(row[0]) in course]
    if len(picked) >= MIN_POOL:
        return picked
    known = course | _guru(db, "wk_assignments")
    return [row for row in rows if int(row[0]) in known]


def start(db, size=GATE_SIZE):
    ensure_schema(db)
    rows = gate_pool(db)
    if not rows:
        # Nothing Guru'd yet: let the gate through rather than brick the phone.
        rows_id = db.execute(
            "insert into gates (subject_ids, baseline, passed_at) values ('{}', '{}', now()) returning id",
            fetch=True,
        )
        return {"gate_id": rows_id[0][0], "drill": None, "status": status(db)}
    drill = build_drill(
        rows, min_level=1, max_level=60, count=size, modes=["meaning", "reading"],
        kind="recall", pool="decay", object_types=GATE_TYPES,
    )
    persist_drill(db, drill)
    ids = [q["subject_id"] for q in drill["questions"]]
    gate = db.execute(
        "insert into gates (subject_ids, baseline, drill_id) values (%s, '{}', %s::uuid) returning id",
        [ids, drill["session_id"]],
        fetch=True,
    )
    return {"gate_id": gate[0][0], "drill": public_drill(drill), "status": status(db)}


def finish(db, gate_id):
    """Pass the gate once its quiz is finished (every miss cleared)."""
    ensure_schema(db)
    rows = db.execute(
        """
        select g.passed_at, g.drill_id, d.finished_at
        from gates g left join drill_sessions d on d.id = g.drill_id
        where g.id = %s
        """,
        [gate_id],
        fetch=True,
    )
    if not rows:
        raise ValueError("unknown gate")
    passed_at, drill_id, finished_at = rows[0]
    if not passed_at:
        if drill_id is None or finished_at is None:
            return {"passed": False, "status": status(db)}
        db.execute("update gates set passed_at = now() where id = %s and passed_at is null", [gate_id])
    return {"passed": True, "status": status(db)}

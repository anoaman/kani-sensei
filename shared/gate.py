"""The gate: an iPhone Shortcut asks before a time-sink app opens.

Between 08:00 and 22:00 WIB the apps stay locked until you clear a gate. Night
is always open.

A gate is a quick quiz, not coursework: typed questions on things you've
already Guru'd (in the course first; WaniKani-snapshot Guru+ tops up a thin
pool), weighted toward rot. It never touches course SRS. It is a real gate:

- you can fail it: too many first-try misses and it ends; next try is fresh
- no rerolls: reloading resumes the same unfinished gate
- each question is timed on the server, so no looking answers up
- every unlock of the day costs more questions than the last
- the open window is earned: clean gets 3h, scraping through gets 90 min
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.course import GURU
from shared.daily import WIB, ensure_schema as ensure_daily_schema
from shared.drill import (
    _fetch_miss_ids, build_drill, ensure_schema as ensure_drill_schema, get_drill,
    persist_drill, public_drill,
)
from shared.quiz import fetch_pool

# The nth unlock of the day: (questions, first-try misses allowed, pool).
TIERS = [
    (5, 1, "rot"),
    (7, 1, "rot"),
    (10, 2, "rot_hard"),
]
QUESTION_SECONDS = 15
CLEAN_WINDOW = timedelta(hours=3)
SCRAPED_WINDOW = timedelta(minutes=90)
WINDOW = CLEAN_WINDOW  # legacy name
MIN_POOL = 15  # below this many course Guru items, borrow WaniKani's
GATE_TYPES = ["radical", "kanji", "vocabulary", "kana_vocabulary"]
RECENT = timedelta(hours=6)  # don't re-ask items from gates this recent
RESUME_WITHIN = timedelta(hours=12)
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
COLUMNS = (
    "alter table gates add column if not exists drill_id uuid",
    "alter table gates add column if not exists failed_at timestamptz",
    # Minutes the pass opens the apps for. 0 = practice, opens nothing.
    "alter table gates add column if not exists open_minutes integer not null default 180",
    # Started while the apps were locked; only these count toward the day's tier.
    "alter table gates add column if not exists locked boolean not null default true",
)

_SCHEMA_READY = False


def ensure_schema(db):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    ensure_daily_schema(db)
    ensure_drill_schema(db)
    db.execute(SCHEMA)
    for statement in COLUMNS:
        db.execute(statement)
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


def gate_state(now, open_until):
    """Pure: open/locked, why, and until when. `open_until` is when the
    latest earned window closes (or None)."""
    wake = quiet_until(now)
    if wake:
        return {"open": True, "reason": "night", "until": wake}
    if open_until and now < open_until:
        return {"open": True, "reason": "cleared", "until": open_until}
    return {"open": False, "reason": "locked", "until": None}


def tier_for(unlocks_today):
    """Pure: the gate you face after `unlocks_today` earlier unlocks."""
    size, allowed, pool = TIERS[min(unlocks_today, len(TIERS) - 1)]
    return {"size": size, "allowed_misses": allowed, "pool": pool, "unlock": unlocks_today + 1}


def earned_window(misses):
    """Pure: how long a pass opens the apps."""
    return CLEAN_WINDOW if misses == 0 else SCRAPED_WINDOW


def _open_until(db):
    rows = db.execute(
        "select max(passed_at + make_interval(mins => open_minutes)) from gates where passed_at is not null",
        fetch=True,
    )
    return rows[0][0] if rows else None


def _day_start(now):
    local = now.astimezone(WIB).replace(hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc)


def _unlocks_today(db, now):
    rows = db.execute(
        "select count(*) from gates where locked and passed_at is not null and open_minutes > 0 and passed_at >= %s",
        [_day_start(now)],
        fetch=True,
    )
    return int(rows[0][0]) if rows else 0


def status(db, now=None):
    ensure_schema(db)
    now = now or _now()
    state = gate_state(now, _open_until(db))
    out = {**state, "until": state["until"].isoformat() if state["until"] else None}
    if not state["open"]:
        out["next"] = tier_for(_unlocks_today(db, now))
    return out


def _guru(db, table):
    sql = f"select subject_id from {table} where srs_stage >= %s"
    return {int(row[0]) for row in db.execute(sql, [GURU], fetch=True)}


def _recent_ids(db, now):
    rows = db.execute(
        "select coalesce(array_agg(distinct s), '{}') from gates, unnest(subject_ids) s where started_at >= %s",
        [now - RECENT],
        fetch=True,
    )
    return {int(x) for x in (rows[0][0] or [])} if rows else set()


def gate_pool(db, size=5, now=None):
    """Quiz rows for items you've Guru'd: the course's first; WaniKani's
    snapshot Guru+ joins in while the course pool is thin. Items from the
    last few hours' gates sit out while there's plenty else."""
    rows = fetch_pool(db, 1, 60, object_types=GATE_TYPES)
    course = _guru(db, "course_items")
    picked = [row for row in rows if int(row[0]) in course]
    if len(picked) < MIN_POOL:
        known = course | _guru(db, "wk_assignments")
        picked = [row for row in rows if int(row[0]) in known]
    recent = _recent_ids(db, now or _now())
    fresh = [row for row in picked if int(row[0]) not in recent]
    return fresh if len(fresh) >= size * 3 else picked


def _resume(db, now, locked):
    """The latest gate that's neither passed nor failed, with its quiz. A
    practice gate never resumes as a real one, or vice versa."""
    rows = db.execute(
        """
        select g.id, g.drill_id, g.locked
        from gates g join drill_sessions d on d.id = g.drill_id
        where g.passed_at is null and g.failed_at is null and g.started_at >= %s
          and g.locked = %s
        order by g.started_at desc limit 1
        """,
        [now - RESUME_WITHIN, locked],
        fetch=True,
    )
    if not rows:
        return None
    gate_id, drill_id, locked = rows[0]
    drill = get_drill(db, str(drill_id))
    if drill["finished_at"]:
        return None  # finished but never settled: let finish() handle it
    meta = drill["meta"] or {}
    answered = [q for q in drill["questions"] if q["answered"]]
    retries = set((meta.get("retry_of") or {}).keys())
    first = [q for q in answered if q["id"] not in retries]
    remaining = [
        {**q, "prompt_text": q["characters"]}
        for q in drill["questions"] if not q["answered"]
    ]
    return {
        "gate_id": gate_id,
        "resumed": True,
        "drill": {
            "session_id": drill["session_id"],
            "question_count": drill["question_count"],
            "questions": remaining,
            "answered": len(answered),
            "first_try_correct": sum(1 for q in first if q.get("is_correct")),
            "question_seconds": meta.get("question_seconds"),
            "allowed_misses": meta.get("allowed_misses"),
        },
    }


def start(db, now=None):
    ensure_schema(db)
    now = now or _now()
    state = status(db, now)
    locked = not state["open"]
    resumed = _resume(db, now, locked)
    if resumed:
        return {**resumed, "status": state, "tier": state.get("next")}
    tier = tier_for(_unlocks_today(db, now)) if locked else {**tier_for(0), "unlock": 0}
    rows = gate_pool(db, tier["size"], now)
    if not rows:
        # Nothing Guru'd yet: let the gate through rather than brick the phone.
        rows_id = db.execute(
            "insert into gates (subject_ids, baseline, passed_at, locked) values ('{}', '{}', now(), %s) returning id",
            [locked],
            fetch=True,
        )
        return {"gate_id": rows_id[0][0], "drill": None, "status": status(db)}
    drill = build_drill(
        rows, min_level=1, max_level=60, count=tier["size"], modes=["meaning", "reading"],
        kind="recall", pool=tier["pool"], object_types=GATE_TYPES,
        miss_ids=_fetch_miss_ids(db),
    )
    drill["rules"] = {"question_seconds": QUESTION_SECONDS, "allowed_misses": tier["allowed_misses"]}
    persist_drill(db, drill)
    ids = [q["subject_id"] for q in drill["questions"]]
    gate = db.execute(
        "insert into gates (subject_ids, baseline, drill_id, locked) values (%s, '{}', %s::uuid, %s) returning id",
        [ids, drill["session_id"], locked],
        fetch=True,
    )
    public = public_drill(drill)
    public.update(drill["rules"])
    return {"gate_id": gate[0][0], "drill": public, "status": state, "tier": tier}


def seen(db, gate_id, question_id):
    """Start a question's clock. The first sighting sticks, so reloading
    doesn't buy more time."""
    ensure_schema(db)
    rows = db.execute("select drill_id from gates where id = %s", [gate_id], fetch=True)
    if not rows or rows[0][0] is None:
        raise ValueError("unknown gate")
    db.execute(
        """
        update drill_sessions
        set meta = jsonb_set(
            meta || jsonb_build_object('seen', coalesce(meta->'seen', '{}'::jsonb)),
            array['seen', %s::text], to_jsonb(%s::text), true)
        where id = %s::uuid and not (coalesce(meta->'seen', '{}'::jsonb) ? %s::text)
        """,
        [str(question_id), _now().isoformat(), str(rows[0][0]), str(question_id)],
    )
    got = db.execute(
        "select meta->'seen'->>%s, meta->>'question_seconds' from drill_sessions where id = %s::uuid",
        [str(question_id), str(rows[0][0])],
        fetch=True,
    )
    seen_at, limit = got[0] if got else (None, None)
    return {"seconds_left": seconds_left(seen_at, limit, _now())}


def seconds_left(seen_at, limit, now):
    """Pure: what's left on a question's clock (None if untimed)."""
    if not limit or not seen_at:
        return None
    elapsed = (now - datetime.fromisoformat(seen_at)).total_seconds()
    return max(0.0, round(float(limit) - elapsed, 1))


def verdict(finished_at, score_correct, score_total, allowed):
    """Pure: did a finished gate quiz pass, and how long does it open?"""
    if finished_at is None:
        return {"settled": False}
    misses = int(score_total) - int(score_correct)
    if allowed is not None and misses > int(allowed):
        return {"settled": True, "passed": False, "misses": misses}
    return {"settled": True, "passed": True, "misses": misses, "window": earned_window(misses)}


def finish(db, gate_id):
    """Settle a gate once its quiz is over: pass within the miss allowance,
    otherwise fail (the next start builds a fresh one)."""
    ensure_schema(db)
    rows = db.execute(
        """
        select g.passed_at, g.failed_at, g.drill_id, g.locked, d.finished_at,
               d.score_correct, d.score_total, d.meta->>'allowed_misses'
        from gates g left join drill_sessions d on d.id = g.drill_id
        where g.id = %s
        """,
        [gate_id],
        fetch=True,
    )
    if not rows:
        raise ValueError("unknown gate")
    passed_at, failed_at, drill_id, locked, finished_at, correct, total, allowed = rows[0]
    if passed_at:
        return {"passed": True, "status": status(db)}
    if failed_at:
        return {"passed": False, "failed": True, "status": status(db)}
    if drill_id is None:
        return {"passed": False, "status": status(db)}
    result = verdict(finished_at, correct or 0, total or 0, allowed)
    if not result["settled"]:
        return {"passed": False, "status": status(db)}
    score = {"correct": int(correct or 0), "total": int(total or 0), "allowed_misses": None if allowed is None else int(allowed)}
    if not result["passed"]:
        db.execute("update gates set failed_at = now() where id = %s and failed_at is null", [gate_id])
        return {"passed": False, "failed": True, "score": score, "status": status(db)}
    minutes = int(result["window"].total_seconds() // 60) if locked else 0
    db.execute(
        "update gates set passed_at = now(), open_minutes = %s where id = %s and passed_at is null",
        [minutes, gate_id],
    )
    return {"passed": True, "minutes": minutes, "score": score, "status": status(db)}

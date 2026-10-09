"""Today's set: one fixed batch a day, built for you, so there's nothing to decide.

The set is picked once per WIB day and frozen: due reviews first (rot in
progress), then relearns (lowest pips first), then unchecked items in lesson
order. An item counts for today the first time a round of it finishes, in
whatever mode it was in. Finishing every item completes the day; consecutive
completed days are the streak.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from shared.course import QUEUE_COLUMNS, ensure_schema as ensure_course_schema, queue_item

DAILY_SIZE = 20
WIB = timezone(timedelta(hours=7))

SCHEMA = """
create table if not exists daily_sets (
    day           date primary key,
    subject_ids   bigint[] not null,
    done_ids      bigint[] not null default '{}',
    created_at    timestamptz not null default now(),
    completed_at  timestamptz
)
"""

_SCHEMA_READY = False


def ensure_schema(db):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    ensure_course_schema(db)
    try:
        if db.has_relation("public.daily_sets"):
            _SCHEMA_READY = True
            return
    except Exception:
        pass
    db.execute(SCHEMA)
    _SCHEMA_READY = True


def today(now=None):
    return (now or datetime.now(timezone.utc)).astimezone(WIB).date()


def streak_from(days, current):
    """Consecutive completed days ending today, or yesterday if today's still open."""
    done = set(days)
    cursor = current if current in done else current - timedelta(days=1)
    count = 0
    while cursor in done:
        count += 1
        cursor -= timedelta(days=1)
    return count


def _pick(db, size):
    rows = db.execute(
        """
        select c.subject_id
        from course_items c
        join wk_subjects s on s.id = c.subject_id
        where c.srs_stage between 0 and 8
          and (c.srs_stage < 5 or c.available_at <= now())
        order by
          case when c.srs_stage >= 5 then 0 when c.srs_stage >= 1 then 1 else 2 end,
          case when c.srs_stage >= 5 then extract(epoch from c.available_at) else c.srs_stage end,
          c.level,
          case s.object_type when 'radical' then 0 when 'kanji' then 1 else 2 end,
          coalesce((s.raw->>'lesson_position')::int, 0),
          c.subject_id
        limit %s
        """,
        [size],
        fetch=True,
    )
    return [int(row[0]) for row in rows]


def _row(db, day):
    rows = db.execute(
        "select subject_ids, done_ids, completed_at from daily_sets where day = %s",
        [day],
        fetch=True,
    )
    return rows[0] if rows else None


def _streak(db, day):
    rows = db.execute(
        "select day from daily_sets where completed_at is not null and day > %s order by day desc",
        [day - timedelta(days=400)],
        fetch=True,
    )
    return streak_from([row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0])) for row in rows], day)


def fetch_daily(db, size=DAILY_SIZE, with_items=True):
    """Today's set (built on first open) with the items still to do.

    with_items=False is the cheap home-page version: counts and streak only.
    """
    ensure_schema(db)
    day = today()
    row = _row(db, day)
    if row is None:
        picked = _pick(db, size)
        if picked:
            db.execute(
                "insert into daily_sets (day, subject_ids) values (%s, %s) on conflict (day) do nothing",
                [day, picked],
            )
            row = _row(db, day)
    subject_ids, done_ids, completed_at = row or ([], [], None)
    subject_ids = [int(x) for x in subject_ids or []]
    done = {int(x) for x in done_ids or []}
    remaining = [sid for sid in subject_ids if sid not in done]
    items = []
    if remaining and not with_items:
        return {
            "day": day.isoformat(),
            "total": len(subject_ids),
            "done": len(subject_ids) - len(remaining),
            "completed": completed_at is not None,
            "streak": _streak(db, day),
            "items": [],
        }
    if remaining:
        rows = db.execute(
            f"""
            select {QUEUE_COLUMNS}
            from course_items c
            join wk_subjects s on s.id = c.subject_id
            where c.subject_id = any(%s) and c.srs_stage between 0 and 8
            """,
            [remaining],
            fetch=True,
        )
        by_id = {int(r[0]): r for r in rows}
        items = [queue_item(db, by_id[sid]) for sid in remaining if sid in by_id]
    return {
        "day": day.isoformat(),
        "total": len(subject_ids),
        "done": len(subject_ids) - len(items),
        "completed": completed_at is not None or (bool(subject_ids) and not items),
        "streak": _streak(db, day),
        "items": items,
    }


def mark_done(db, subject_id):
    """Count a finished round toward today's set. Returns progress, or None if not in it."""
    ensure_schema(db)
    day = today()
    rows = db.execute(
        """
        update daily_sets
        set done_ids = case when %s = any(done_ids) then done_ids else array_append(done_ids, %s) end
        where day = %s and %s = any(subject_ids)
        returning cardinality(subject_ids), cardinality(done_ids), completed_at
        """,
        [subject_id, subject_id, day, subject_id],
        fetch=True,
    )
    if not rows:
        return None
    total, done, completed_at = rows[0]
    just_completed = False
    if done >= total and completed_at is None:
        db.execute("update daily_sets set completed_at = now() where day = %s and completed_at is null", [day])
        just_completed = True
    return {
        "done": done,
        "total": total,
        "completed": done >= total,
        "just_completed": just_completed,
        "streak": _streak(db, day) if just_completed else None,
    }

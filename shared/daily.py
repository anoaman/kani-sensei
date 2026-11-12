"""Today's set: one batch a day, built for you.

The length is 5, 10, 15, or 20. Twenty is the default until you choose.

The set is picked once per WIB day and frozen: due reviews first (rot in
progress), then relearns (lowest pips first), then unchecked items in lesson
order. An item counts for today the first time a round of it finishes, in
whatever mode it was in. Finishing every item completes the day; consecutive
completed days are the streak.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from shared.course import QUEUE_COLUMNS, ensure_schema as ensure_course_schema, queue_item

DAILY_SIZES = (5, 10, 15, 20)
DAILY_SIZE = 20
RADICAL_CAP = 5
# Look past the first page so a wall of radicals cannot hide every kanji and word.
_PICK_POOL = 4


def radical_cap_for(size):
    """Keep radicals to about a quarter of the day. 20 still caps them at 5."""
    return max(1, int(size) // 4)


def balance_daily(items, size, radical_cap=RADICAL_CAP):
    """Keep pick order, and stop radicals from filling the set.

    The cap applies when a kanji or word is in the pool. Radicals past the
    cap wait, then fill any seats that are still empty.
    """
    ordered = [(int(subject_id), object_type or "") for subject_id, object_type in (items or [])]
    if not any(object_type != "radical" for _subject_id, object_type in ordered):
        return [subject_id for subject_id, _object_type in ordered[:size]]
    chosen = []
    deferred = []
    radicals = 0
    for subject_id, object_type in ordered:
        if len(chosen) >= size:
            break
        if object_type == "radical":
            if radicals >= radical_cap:
                deferred.append(subject_id)
                continue
            radicals += 1
        chosen.append(subject_id)
    for subject_id in deferred:
        if len(chosen) >= size:
            break
        chosen.append(subject_id)
    return chosen


def resize_daily(subject_ids, done_ids, size):
    """Shrink or hold a saved day without dropping work already finished.

    Unfinished items fall off the end. Finished items stay, in their original
    order, even when that leaves the day longer than the new size.
    """
    done = {int(item) for item in done_ids or []}
    ordered = []
    seen = set()
    for raw in list(subject_ids or []):
        subject_id = int(raw)
        if subject_id in seen:
            continue
        seen.add(subject_id)
        ordered.append(subject_id)
    for raw in done_ids or []:
        subject_id = int(raw)
        if subject_id in seen:
            continue
        seen.add(subject_id)
        ordered.append(subject_id)
    finished = [subject_id for subject_id in ordered if subject_id in done]
    if len(finished) >= size:
        return finished
    room = size - len(finished)
    pending = []
    for subject_id in ordered:
        if subject_id in done:
            continue
        if len(pending) >= room:
            break
        pending.append(subject_id)
    keep = set(finished + pending)
    return [subject_id for subject_id in ordered if subject_id in keep]


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

SETTINGS_SCHEMA = """
create table if not exists daily_settings (
    key   text primary key,
    size  integer not null
)
"""

_SCHEMA_READY = False


def _has_relation(db, name):
    try:
        return bool(db.has_relation(name))
    except Exception:
        return False


def ensure_schema(db):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    ensure_course_schema(db)
    if not _has_relation(db, "public.daily_sets"):
        db.execute(SCHEMA)
    if not _has_relation(db, "public.daily_settings"):
        db.execute(SETTINGS_SCHEMA)
    db.execute(
        "insert into daily_settings (key, size) values ('daily', %s) on conflict (key) do nothing",
        [DAILY_SIZE],
    )
    _SCHEMA_READY = True


def parse_daily_size(value):
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = None
    if size not in DAILY_SIZES:
        raise ValueError("size must be 5, 10, 15, or 20")
    return size


def saved_size(db):
    ensure_schema(db)
    rows = db.execute("select size from daily_settings where key = 'daily'", fetch=True)
    if not rows:
        return DAILY_SIZE
    try:
        size = int(rows[0][0])
    except (TypeError, ValueError):
        return DAILY_SIZE
    return size if size in DAILY_SIZES else DAILY_SIZE


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
        select c.subject_id, s.object_type
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
        [size * _PICK_POOL],
        fetch=True,
    )
    return balance_daily(rows, size, radical_cap_for(size))


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


def fetch_daily(db, with_items=True):
    """Today's set (built on first open) with the items still to do.

    with_items=False is the cheap home-page version: counts and streak only.
    A day that does not exist yet is built at the saved size.
    """
    ensure_schema(db)
    size = saved_size(db)
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
            "size": size,
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
        "size": size,
        "items": items,
    }


def set_daily_size(db, size):
    """Remember the day length and fit today's saved list to it."""
    size = parse_daily_size(size)
    ensure_schema(db)
    db.execute(
        """
        insert into daily_settings (key, size) values ('daily', %s)
        on conflict (key) do update set size = excluded.size
        """,
        [size],
    )
    day = today()
    row = _row(db, day)
    if row is not None:
        subject_ids, done_ids, completed_at = row
        kept = resize_daily(subject_ids, done_ids, size)
        if len(kept) < size:
            have = set(kept)
            for subject_id in _pick(db, size):
                if subject_id in have:
                    continue
                kept.append(subject_id)
                have.add(subject_id)
                if len(kept) >= size:
                    break
        done = {int(item) for item in done_ids or []}
        new_done = [subject_id for subject_id in kept if subject_id in done]
        finished = bool(kept) and len(new_done) >= len(kept)
        db.execute(
            """
            update daily_sets
            set subject_ids = %s,
                done_ids = %s,
                completed_at = case when %s then coalesce(completed_at, now()) else null end
            where day = %s
            """,
            [kept, new_done, finished, day],
        )
    return fetch_daily(db, with_items=False)


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

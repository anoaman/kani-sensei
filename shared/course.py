"""Level courses: a local WaniKani-style SRS, one level at a time.

Restarting a level wipes its course rows and starts fresh. Radicals unlock
first; a kanji unlocks once every component radical is at Guru, a vocab
word once every component kanji is. Components outside the course (earlier
levels you didn't restart) count as known. Lessons graduate items to
Apprentice 1; reviews move them up or down with WaniKani's intervals and
penalty. A level passes when 90% of its kanji reach Guru.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

from shared.answers import grade_answer, normalize_reading
from shared.inspect import SRS_NAMES, fetch_inspect, labeled_readings
from shared.quiz import _accepted_meanings, _accepted_readings, _parse_json


TYPE_ORDER = {"radical": 0, "kanji": 1, "vocabulary": 2, "kana_vocabulary": 2}
GURU = 5
BURNED = 9
LESSON_BATCH = 5
PASS_RATIO = 0.9

# Hours until the next review after reaching each stage (WaniKani's SRS).
INTERVALS = {1: 4, 2: 8, 3: 23, 4: 47, 5: 167, 6: 335, 7: 719, 8: 2879}
# Levels 1-2 run the accelerated early ladder.
ACCELERATED = {1: 2, 2: 4, 3: 8, 4: 23, 5: 167, 6: 335, 7: 719, 8: 2879}

SCHEMA_STATEMENTS = (
    """
    create table if not exists course_levels (
        level        integer primary key,
        started_at   timestamptz not null default now(),
        passed_at    timestamptz,
        reset_count  integer not null default 0
    )
    """,
    """
    create table if not exists course_items (
        subject_id     bigint primary key references wk_subjects (id),
        level          integer not null,
        object_type    text not null,
        srs_stage      integer not null default 0,
        unlocked_at    timestamptz,
        started_at     timestamptz,
        available_at   timestamptz,
        passed_at      timestamptz,
        burned_at      timestamptz,
        meaning_ok     boolean not null default false,
        reading_ok     boolean not null default false,
        meaning_wrong  integer not null default 0,
        reading_wrong  integer not null default 0,
        review_count   integer not null default 0,
        wrong_count    integer not null default 0
    )
    """,
    """
    create index if not exists course_items_level_idx on course_items (level)
    """,
    """
    create index if not exists course_items_available_idx
        on course_items (available_at) where srs_stage between 1 and 8
    """,
)

_SCHEMA_READY = False


def ensure_schema(db):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    try:
        if db.has_relation("public.course_items"):
            _SCHEMA_READY = True
            return
    except Exception:
        pass
    for statement in SCHEMA_STATEMENTS:
        db.execute(statement)
    _SCHEMA_READY = True


# --- SRS math (pure) -------------------------------------------------------

def interval_hours(stage, level):
    table = ACCELERATED if level <= 2 else INTERVALS
    return table.get(stage)


def next_available(stage, level, now):
    hours = interval_hours(stage, level)
    if hours is None:
        return None
    # WaniKani rounds review times down to the hour.
    due = now + timedelta(hours=hours)
    return due.replace(minute=0, second=0, microsecond=0)


def next_stage(stage, meaning_wrong, reading_wrong):
    """WaniKani's rule: drop ceil(wrong/2) stages, doubled from Guru up."""
    wrong = int(meaning_wrong) + int(reading_wrong)
    if wrong == 0:
        return min(BURNED, stage + 1)
    penalty = 2 if stage >= GURU else 1
    return max(1, stage - math.ceil(wrong / 2) * penalty)


def needs_reading(object_type, readings):
    return object_type in ("kanji", "vocabulary") and bool(readings)


def unlockable(items, stages_outside=None):
    """Return subject ids that should unlock now.

    items: {subject_id: {"unlocked": bool, "stage": int, "components": [ids]}}
    stages_outside: stages of component ids in the course but other levels.
    """
    stages = {sid: item["stage"] for sid, item in items.items()}
    stages.update(stages_outside or {})
    ready = []
    for sid, item in items.items():
        if item["unlocked"]:
            continue
        if all(stages.get(cid, GURU) >= GURU for cid in item["components"]):
            ready.append(sid)
    return ready


def stage_bucket(stage, unlocked=True):
    if not unlocked:
        return "locked"
    if stage <= 0:
        return "lesson"
    if stage <= 4:
        return "apprentice"
    if stage <= 6:
        return "guru"
    return {7: "master", 8: "enlightened"}.get(stage, "burned")


# --- data access -----------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.isoformat() if value else None


def image_url(raw):
    """Image-only radicals ship as pictures; prefer SVG, else a mid-size PNG."""
    images = raw.get("character_images") or []
    for entry in images:
        if isinstance(entry, dict) and "svg" in (entry.get("content_type") or ""):
            if (entry.get("metadata") or {}).get("inline_styles") is not False:
                return entry.get("url")
    for entry in images:
        if not isinstance(entry, dict):
            continue
        dims = (entry.get("metadata") or {}).get("dimensions") or ""
        if dims.startswith("128x") or dims.startswith("256x"):
            return entry.get("url")
    for entry in images:
        if isinstance(entry, dict) and entry.get("url"):
            return entry["url"]
    return None


def _subject_rows(db, level):
    return db.execute(
        """
        select s.id, s.object_type, s.characters, s.slug, s.primary_meaning,
               s.meanings, s.readings, s.raw, a.srs_stage,
               c.srs_stage, c.unlocked_at, c.available_at, c.passed_at, c.burned_at,
               c.subject_id is not null
        from wk_subjects s
        left join wk_assignments a on a.subject_id = s.id
        left join course_items c on c.subject_id = s.id
        where s.level = %s and (s.raw->>'hidden_at') is null
        """,
        [level],
        fetch=True,
    )


def _shape_item(row, level):
    (sid, object_type, characters, slug, meaning, meanings_raw, readings_raw,
     raw, wk_stage, stage, unlocked_at, available_at, passed_at, burned_at,
     in_course) = row
    raw = _parse_json(raw) if not isinstance(raw, dict) else raw
    readings = labeled_readings(readings_raw)
    primary = next((r["reading"] for r in readings if r["primary"]), None)
    return {
        "subject_id": sid,
        "type": "vocabulary" if object_type == "kana_vocabulary" else object_type,
        "object_type": object_type,
        "characters": characters,
        "image_url": None if characters else image_url(raw),
        "slug": slug,
        "level": level,
        "meaning": meaning,
        "reading": primary or (readings[0]["reading"] if readings else None),
        "lesson_position": raw.get("lesson_position") or 0,
        "components": [int(i) for i in raw.get("component_subject_ids") or []],
        "wk_stage": wk_stage,
        "in_course": bool(in_course),
        "stage": int(stage or 0) if in_course else None,
        "stage_name": SRS_NAMES.get(int(stage or 0)) if in_course else None,
        "bucket": stage_bucket(int(stage or 0), bool(unlocked_at)) if in_course else None,
        "available_at": _iso(available_at),
        "passed": bool(passed_at),
        "burned": bool(burned_at),
    }


def _sort_key(item):
    return (TYPE_ORDER.get(item["object_type"], 3), item["lesson_position"], item["subject_id"])


def level_summary(items, level_row, now=None):
    now = now or _now()
    course = [item for item in items if item["in_course"]]
    kanji = [item for item in items if item["type"] == "kanji"]
    kanji_guru = sum(1 for item in kanji if item["in_course"] and (item["stage"] or 0) >= GURU)
    need = math.ceil(len(kanji) * PASS_RATIO)
    lessons = sum(1 for item in course if item["bucket"] == "lesson")
    due_times = []
    reviews = 0
    for item in course:
        if not (1 <= (item["stage"] or 0) <= 8) or not item["available_at"]:
            continue
        at = datetime.fromisoformat(item["available_at"])
        if at <= now:
            reviews += 1
        else:
            due_times.append(at)
    buckets = {}
    for item in course:
        buckets[item["bucket"]] = buckets.get(item["bucket"], 0) + 1
    started_at, passed_at, reset_count = level_row or (None, None, 0)
    return {
        "started": bool(level_row),
        "started_at": _iso(started_at),
        "passed_at": _iso(passed_at),
        "reset_count": reset_count or 0,
        "lessons": lessons,
        "reviews": reviews,
        "next_review_at": _iso(min(due_times)) if due_times else None,
        "kanji_guru": kanji_guru,
        "kanji_total": len(kanji),
        "kanji_needed": need,
        "buckets": buckets,
    }


def fetch_level(db, level):
    ensure_schema(db)
    items = sorted((_shape_item(row, level) for row in _subject_rows(db, level)), key=_sort_key)
    level_rows = db.execute(
        "select started_at, passed_at, reset_count from course_levels where level = %s",
        [level],
        fetch=True,
    )
    groups = {"radical": [], "kanji": [], "vocabulary": []}
    for item in items:
        groups.setdefault(item["type"], []).append(item)
    return {
        "level": level,
        "course": level_summary(items, level_rows[0] if level_rows else None),
        "groups": groups,
    }


def fetch_levels(db):
    ensure_schema(db)
    rows = db.execute(
        """
        select s.level,
               count(*) filter (where s.object_type = 'radical'),
               count(*) filter (where s.object_type = 'kanji'),
               count(*) filter (where s.object_type in ('vocabulary', 'kana_vocabulary')),
               count(c.subject_id) filter (where s.object_type = 'kanji' and c.srs_stage >= %s),
               count(c.subject_id) filter (where c.unlocked_at is not null and c.srs_stage = 0),
               count(c.subject_id) filter (where c.srs_stage between 1 and 8 and c.available_at <= now()),
               bool_or(l.level is not null),
               bool_or(l.passed_at is not null)
        from wk_subjects s
        left join course_items c on c.subject_id = s.id
        left join course_levels l on l.level = s.level
        where (s.raw->>'hidden_at') is null
        group by s.level
        order by s.level
        """,
        [GURU],
        fetch=True,
    )
    return {
        "levels": [
            {
                "level": level,
                "radicals": radicals,
                "kanji": kanji,
                "vocabulary": vocab,
                "kanji_guru": kanji_guru,
                "kanji_needed": math.ceil(kanji * PASS_RATIO),
                "lessons": lessons,
                "reviews": reviews,
                "started": bool(started),
                "passed": bool(passed),
            }
            for (level, radicals, kanji, vocab, kanji_guru, lessons, reviews,
                 started, passed) in rows
        ]
    }


def _run_unlocks(db, now):
    """Unlock every locked course item whose components are all at Guru."""
    rows = db.execute(
        """
        select c.subject_id, c.srs_stage, c.unlocked_at is not null,
               coalesce(s.raw->'component_subject_ids', '[]'::jsonb)
        from course_items c
        join wk_subjects s on s.id = c.subject_id
        """,
        fetch=True,
    )
    items = {
        sid: {
            "stage": int(stage or 0),
            "unlocked": bool(unlocked),
            "components": [int(i) for i in _parse_json(components)],
        }
        for sid, stage, unlocked, components in rows
    }
    ready = unlockable(items)
    if ready:
        db.execute(
            "update course_items set unlocked_at = %s where subject_id = any(%s)",
            [now, ready],
        )
    return ready


def _check_pass(db, level, now):
    rows = db.execute(
        """
        select count(*) filter (where s.object_type = 'kanji'),
               count(c.subject_id) filter (where s.object_type = 'kanji' and c.srs_stage >= %s),
               (select passed_at from course_levels where level = %s)
        from wk_subjects s
        left join course_items c on c.subject_id = s.id
        where s.level = %s and (s.raw->>'hidden_at') is null
        """,
        [GURU, level, level],
        fetch=True,
    )
    total, guru, passed_at = rows[0]
    if passed_at or not total or guru < math.ceil(total * PASS_RATIO):
        return False
    db.execute("update course_levels set passed_at = %s where level = %s", [now, level])
    return True


def start_level(db, level):
    """Start (or restart) a level course from zero."""
    ensure_schema(db)
    now = _now()
    db.execute("delete from course_items where level = %s", [level])
    db.execute(
        """
        insert into course_levels (level, started_at, passed_at, reset_count)
        values (%s, %s, null, 0)
        on conflict (level) do update set
          started_at = excluded.started_at,
          passed_at = null,
          reset_count = course_levels.reset_count + 1
        """,
        [level, now],
    )
    db.execute(
        """
        insert into course_items (subject_id, level, object_type)
        select id, level, object_type from wk_subjects
        where level = %s and (raw->>'hidden_at') is null
        """,
        [level],
    )
    _run_unlocks(db, now)
    return fetch_level(db, level)


def _card(db, subject_id, extra=None):
    card = fetch_inspect(db, subject_id)
    card.update(extra or {})
    return card


def fetch_lessons(db, level, limit=LESSON_BATCH):
    ensure_schema(db)
    rows = db.execute(
        """
        select c.subject_id, s.object_type, s.characters, s.readings, s.raw
        from course_items c
        join wk_subjects s on s.id = c.subject_id
        where c.level = %s and c.unlocked_at is not null and c.srs_stage = 0
        order by case s.object_type when 'radical' then 0 when 'kanji' then 1 else 2 end,
                 coalesce((s.raw->>'lesson_position')::int, 0), s.id
        limit %s
        """,
        [level, limit],
        fetch=True,
    )
    lessons = []
    for sid, object_type, characters, readings_raw, raw in rows:
        raw = _parse_json(raw) if not isinstance(raw, dict) else raw
        readings = _accepted_readings(readings_raw)
        lessons.append(_card(db, sid, {
            "image_url": None if characters else image_url(raw),
            "needs_reading": needs_reading(object_type, readings),
        }))
    return {"level": level, "lessons": lessons}


def fetch_reviews(db, level=None):
    ensure_schema(db)
    rows = db.execute(
        """
        select c.subject_id, c.level, s.object_type, s.characters, s.primary_meaning,
               s.readings, s.raw, c.srs_stage, c.meaning_ok, c.reading_ok
        from course_items c
        join wk_subjects s on s.id = c.subject_id
        where c.srs_stage between 1 and 8 and c.available_at <= now()
          and (%s::int is null or c.level = %s::int)
        order by c.available_at, c.subject_id
        """,
        [level, level],
        fetch=True,
    )
    items = []
    for (sid, item_level, object_type, characters, meaning, readings_raw, raw,
         stage, meaning_ok, reading_ok) in rows:
        raw = _parse_json(raw) if not isinstance(raw, dict) else raw
        reading = needs_reading(object_type, _accepted_readings(readings_raw))
        prompts = []
        if not meaning_ok:
            prompts.append("meaning")
        if reading and not reading_ok:
            prompts.append("reading")
        items.append({
            "subject_id": sid,
            "level": item_level,
            "type": "vocabulary" if object_type == "kana_vocabulary" else object_type,
            "characters": characters,
            "image_url": None if characters else image_url(raw),
            "stage": stage,
            "stage_name": SRS_NAMES.get(stage),
            "prompts": prompts,
        })
    return {"level": level, "reviews": items}


def _whitelist(raw):
    return [
        entry.get("meaning")
        for entry in raw.get("auxiliary_meanings") or []
        if isinstance(entry, dict) and entry.get("type") == "whitelist" and entry.get("meaning")
    ]


def _reading_hint(readings_raw, submitted):
    """Kanji: a real but not-taught reading gets a shake, like WaniKani."""
    got = normalize_reading(submitted)
    for entry in _parse_json(readings_raw):
        if not isinstance(entry, dict) or entry.get("accepted_answer", True):
            continue
        if normalize_reading(entry.get("reading")) == got:
            typed = {"onyomi": "on'yomi", "kunyomi": "kun'yomi"}.get(entry.get("type"))
            if typed:
                return f"That's the {typed}. We want the {_other(typed)}."
            return "That's a reading, but not the one we taught. Try another."
    return None


def _other(kind):
    return {"on'yomi": "kun'yomi", "kun'yomi": "on'yomi"}.get(kind, "taught reading")


def answer(db, subject_id, prompt_type, text=None, gave_up=False):
    """Grade one half of a lesson-quiz or review item."""
    from shared.drill import wrong_type_hint

    ensure_schema(db)
    if prompt_type not in ("meaning", "reading"):
        raise ValueError("prompt_type must be meaning or reading")
    rows = db.execute(
        """
        select c.level, c.srs_stage, c.unlocked_at, c.available_at, c.passed_at,
               c.meaning_ok, c.reading_ok, c.meaning_wrong, c.reading_wrong,
               s.object_type, s.characters, s.primary_meaning, s.meanings, s.readings, s.raw
        from course_items c
        join wk_subjects s on s.id = c.subject_id
        where c.subject_id = %s
        """,
        [subject_id],
        fetch=True,
    )
    if not rows:
        raise ValueError("item is not in a course")
    (level, stage, unlocked_at, available_at, passed_at, meaning_ok, reading_ok,
     meaning_wrong, reading_wrong, object_type, characters, primary_meaning,
     meanings_raw, readings_raw, raw) = rows[0]
    raw = _parse_json(raw) if not isinstance(raw, dict) else raw
    now = _now()

    if stage == 0 and unlocked_at:
        mode = "lesson"
    elif 1 <= stage <= 8 and available_at and available_at <= now:
        mode = "review"
    else:
        raise ValueError("item is not up for lessons or review")

    readings = _accepted_readings(readings_raw)
    has_reading = needs_reading(object_type, readings)
    if prompt_type == "reading" and not has_reading:
        raise ValueError("this item has no reading to review")

    if gave_up:
        result, submitted = "wrong", ""
    else:
        submitted = (text or "").strip()
        if not submitted:
            raise ValueError("text is required")
        accepted = (
            _accepted_meanings(meanings_raw, primary_meaning) + _whitelist(raw)
            if prompt_type == "meaning"
            else readings
        )
        result = grade_answer(prompt_type, submitted, accepted)
        if result != "correct":
            hint = wrong_type_hint(db, subject_id, prompt_type, submitted)
            if not hint and prompt_type == "reading":
                hint = _reading_hint(readings_raw, submitted)
            if hint:
                return {"subject_id": subject_id, "retry": True, "hint": hint}

    correct = result in ("correct", "almost")
    if prompt_type == "meaning":
        meaning_ok = meaning_ok or correct
        if not correct and mode == "review":
            meaning_wrong += 1
    else:
        reading_ok = reading_ok or correct
        if not correct and mode == "review":
            reading_wrong += 1

    done = meaning_ok and (reading_ok or not has_reading)
    payload = {
        "subject_id": subject_id,
        "mode": mode,
        "correct": correct,
        "almost": result == "almost",
        "gave_up": bool(gave_up),
        "submitted": submitted,
        "item_done": done,
        "unlocked": [],
        "level_passed": False,
    }

    if not done:
        db.execute(
            """
            update course_items
            set meaning_ok = %s, reading_ok = %s, meaning_wrong = %s, reading_wrong = %s
            where subject_id = %s
            """,
            [meaning_ok, reading_ok, meaning_wrong, reading_wrong, subject_id],
        )
        payload["stage"] = stage
        payload["stage_name"] = SRS_NAMES.get(stage)
        return _with_reveal(db, payload, subject_id)

    if mode == "lesson":
        new = 1
    else:
        new = next_stage(stage, meaning_wrong, reading_wrong)
    db.execute(
        """
        update course_items
        set srs_stage = %s,
            started_at = coalesce(started_at, %s),
            available_at = %s,
            passed_at = case when %s >= %s then coalesce(passed_at, %s) else passed_at end,
            burned_at = case when %s >= %s then %s else null end,
            meaning_ok = false, reading_ok = false,
            meaning_wrong = 0, reading_wrong = 0,
            review_count = review_count + %s,
            wrong_count = wrong_count + %s
        where subject_id = %s
        """,
        [
            new, now, next_available(new, level, now),
            new, GURU, now,
            new, BURNED, now,
            1 if mode == "review" else 0,
            1 if mode == "review" and (meaning_wrong + reading_wrong) else 0,
            subject_id,
        ],
    )
    payload.update({
        "previous_stage": stage,
        "stage": new,
        "stage_name": SRS_NAMES.get(new),
        "next_review_at": _iso(next_available(new, level, now)),
    })
    if new >= GURU > stage:
        unlocked = _run_unlocks(db, now)
        if unlocked:
            stubs = db.execute(
                "select id, object_type, characters, primary_meaning from wk_subjects where id = any(%s)",
                [unlocked],
                fetch=True,
            )
            payload["unlocked"] = [
                {"subject_id": sid, "type": t, "characters": c, "meaning": m}
                for sid, t, c, m in stubs
            ]
        payload["level_passed"] = _check_pass(db, level, now)
    return _with_reveal(db, payload, subject_id)


def _with_reveal(db, payload, subject_id):
    try:
        payload["inspect"] = fetch_inspect(db, subject_id)
    except Exception:
        payload["inspect"] = None
    return payload


def jsonable(value):
    return json.loads(json.dumps(value, default=str))

"""Level courses: a returnee's SRS, one level at a time.

Built for someone who passed these levels before and is coming back, so it
does not replay WaniKani's first-time ladder:

- Check: restarting a level puts every item up for a placement check, no
  unlock gating. Both halves right first try -> straight to Guru. Any miss ->
  Relearn at Apprentice 1, with the teaching card shown.
- Relearn: Apprentice items are always available. A clean pass climbs one
  stage, a miss drops one. The session spaces repeats, so a rotten item can
  get back to Guru in one sitting.
- Reviews: Guru and up run on real time (1 week, 2 weeks, 1 month, 4
  months) with WaniKani's penalty. That's where retention is actually proven.
- Study ahead: Guru+ items can be practised early. Right answers don't move
  them up (no fake progress); misses still drop them, because rot is rot.

A level passes when 90% of its kanji are at Guru or above.
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
BATCH = 10
PASS_RATIO = 0.9
MODES = ("check", "relearn", "reviews", "ahead")

# Hours until the next review after reaching each Guru+ stage (WaniKani).
INTERVALS = {5: 167, 6: 335, 7: 719, 8: 2879}

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

def next_available(stage, now):
    """Apprentice is always open; Guru+ waits on WaniKani's real-time gaps."""
    if stage >= BURNED:
        return None
    hours = INTERVALS.get(stage)
    if hours is None:
        return now
    # WaniKani rounds review times down to the hour.
    return (now + timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0)


def review_stage(stage, meaning_wrong, reading_wrong):
    """WaniKani's rule: drop ceil(wrong/2) stages, doubled from Guru up."""
    wrong = int(meaning_wrong) + int(reading_wrong)
    if wrong == 0:
        return min(BURNED, stage + 1)
    penalty = 2 if stage >= GURU else 1
    return max(1, stage - math.ceil(wrong / 2) * penalty)


def outcome(mode, stage, meaning_wrong, reading_wrong):
    """New stage after an item's halves are done in the given mode."""
    wrong = int(meaning_wrong) + int(reading_wrong)
    if mode == "check":
        return GURU if wrong == 0 else 1
    if mode == "relearn":
        return stage + 1 if wrong == 0 else max(1, stage - 1)
    if mode == "ahead":
        return stage if wrong == 0 else review_stage(stage, meaning_wrong, reading_wrong)
    return review_stage(stage, meaning_wrong, reading_wrong)


def mode_for(stage, available_at, now):
    if stage <= 0:
        return "check"
    if stage < GURU:
        return "relearn"
    if stage >= BURNED:
        return None
    if available_at and available_at <= now:
        return "reviews"
    return "ahead"


def needs_reading(object_type, readings):
    return object_type in ("kanji", "vocabulary") and bool(readings)


def stage_bucket(stage):
    if stage <= 0:
        return "unchecked"
    if stage <= 4:
        return "relearn"
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
               s.readings, s.raw, c.srs_stage, c.available_at,
               c.subject_id is not null
        from wk_subjects s
        left join course_items c on c.subject_id = s.id
        where s.level = %s and (s.raw->>'hidden_at') is null
        """,
        [level],
        fetch=True,
    )


def _shape_item(row, level):
    (sid, object_type, characters, slug, meaning, readings_raw, raw, stage,
     available_at, in_course) = row
    raw = _parse_json(raw) if not isinstance(raw, dict) else raw
    readings = labeled_readings(readings_raw)
    primary = next((r["reading"] for r in readings if r["primary"]), None)
    stage = int(stage or 0)
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
        "in_course": bool(in_course),
        "stage": stage if in_course else None,
        "stage_name": (SRS_NAMES.get(stage) if stage else "unchecked") if in_course else None,
        "bucket": stage_bucket(stage) if in_course else None,
        "available_at": _iso(available_at),
    }


def _sort_key(item):
    return (TYPE_ORDER.get(item["object_type"], 3), item["lesson_position"], item["subject_id"])


def level_summary(items, level_row, now=None):
    now = now or _now()
    course = [item for item in items if item["in_course"]]
    kanji = [item for item in items if item["type"] == "kanji"]
    kanji_guru = sum(1 for item in kanji if item["in_course"] and (item["stage"] or 0) >= GURU)
    counts = {mode: 0 for mode in MODES}
    upcoming = []
    for item in course:
        at = datetime.fromisoformat(item["available_at"]) if item["available_at"] else None
        mode = mode_for(item["stage"] or 0, at, now)
        if mode:
            counts[mode] += 1
        if mode == "ahead" and at:
            upcoming.append(at)
    buckets = {}
    for item in course:
        buckets[item["bucket"]] = buckets.get(item["bucket"], 0) + 1
    started_at, passed_at, reset_count = level_row or (None, None, 0)
    return {
        "started": bool(level_row),
        "started_at": _iso(started_at),
        "passed_at": _iso(passed_at),
        "reset_count": reset_count or 0,
        **counts,
        "known": sum(1 for item in course if (item["stage"] or 0) >= GURU),
        "total": len(items),
        "next_review_at": _iso(min(upcoming)) if upcoming else None,
        "kanji_guru": kanji_guru,
        "kanji_total": len(kanji),
        "kanji_needed": math.ceil(len(kanji) * PASS_RATIO),
        "buckets": buckets,
        "next_mode": next(
            (mode for mode in ("reviews", "relearn", "check") if counts[mode]), None
        ),
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
               count(c.subject_id) filter (where c.srs_stage >= %s),
               count(c.subject_id) filter (where c.srs_stage = 0),
               count(c.subject_id) filter (where c.srs_stage between 1 and 4),
               count(c.subject_id) filter (where c.srs_stage between 5 and 8 and c.available_at <= now()),
               bool_or(l.level is not null),
               bool_or(l.passed_at is not null)
        from wk_subjects s
        left join course_items c on c.subject_id = s.id
        left join course_levels l on l.level = s.level
        where (s.raw->>'hidden_at') is null
        group by s.level
        order by s.level
        """,
        [GURU, GURU],
        fetch=True,
    )
    return {
        "levels": [
            {
                "level": level,
                "radicals": radicals,
                "kanji": kanji,
                "vocabulary": vocab,
                "total": radicals + kanji + vocab,
                "kanji_guru": kanji_guru,
                "kanji_needed": math.ceil(kanji * PASS_RATIO),
                "known": known,
                "check": check,
                "relearn": relearn,
                "reviews": reviews,
                "started": bool(started),
                "passed": bool(passed),
            }
            for (level, radicals, kanji, vocab, kanji_guru, known, check, relearn,
                 reviews, started, passed) in rows
        ]
    }


def fetch_sky(db):
    """Every item as one dot: level, type, glyph, bucket. Feeds the home map."""
    ensure_schema(db)
    rows = db.execute(
        """
        select s.level, s.id, s.object_type, s.characters, s.primary_meaning,
               c.srs_stage, coalesce((s.raw->>'lesson_position')::int, 0)
        from wk_subjects s
        left join course_items c on c.subject_id = s.id
        where (s.raw->>'hidden_at') is null
        order by s.level,
                 case s.object_type when 'radical' then 0 when 'kanji' then 1 else 2 end,
                 7, s.id
        """,
        fetch=True,
    )
    levels = {}
    for level, sid, object_type, characters, meaning, stage, _pos in rows:
        levels.setdefault(level, []).append([
            sid,
            {"radical": "r", "kanji": "k"}.get(object_type, "v"),
            characters or "",
            meaning or "",
            None if stage is None else int(stage),
        ])
    return {"levels": [{"level": level, "items": items} for level, items in sorted(levels.items())]}


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
    """Start (or restart) a level: every item goes up for a placement check."""
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
        insert into course_items (subject_id, level, object_type, unlocked_at, available_at)
        select id, level, object_type, %s, %s from wk_subjects
        where level = %s and (raw->>'hidden_at') is null
        """,
        [now, now, level],
    )
    return fetch_level(db, level)


_QUEUE_FILTERS = {
    "check": ("c.srs_stage = 0", "case s.object_type when 'radical' then 0 when 'kanji' then 1 else 2 end, "
              "coalesce((s.raw->>'lesson_position')::int, 0), s.id"),
    "relearn": ("c.srs_stage between 1 and 4", "c.srs_stage, c.available_at, s.id"),
    "reviews": ("c.srs_stage between 5 and 8 and c.available_at <= now()", "c.available_at, s.id"),
    "ahead": ("c.srs_stage between 5 and 8 and c.available_at > now()", "c.available_at, s.id"),
}


def fetch_queue(db, level, mode, limit=BATCH):
    """Next items for a mode. Relearn items on Apprentice 1 carry a teaching card."""
    ensure_schema(db)
    if mode not in _QUEUE_FILTERS:
        raise ValueError("mode must be one of " + ", ".join(MODES))
    where, order = _QUEUE_FILTERS[mode]
    rows = db.execute(
        f"""
        select c.subject_id, c.level, s.object_type, s.characters, s.primary_meaning,
               s.readings, s.raw, c.srs_stage, c.meaning_ok, c.reading_ok
        from course_items c
        join wk_subjects s on s.id = c.subject_id
        where c.level = %s and {where}
        order by {order}
        limit %s
        """,
        [level, limit],
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
        item = {
            "subject_id": sid,
            "level": item_level,
            "type": "vocabulary" if object_type == "kana_vocabulary" else object_type,
            "characters": characters,
            "image_url": None if characters else image_url(raw),
            "stage": stage,
            "stage_name": SRS_NAMES.get(stage) if stage else "unchecked",
            "needs_reading": reading,
            "prompts": prompts or (["meaning", "reading"] if reading else ["meaning"]),
        }
        if mode == "relearn" and stage == 1:
            try:
                item["card"] = fetch_inspect(db, sid)
                # The card's SRS label is the old WaniKani snapshot; the course has its own.
                item["card"].update({"image_url": item["image_url"], "needs_reading": reading, "srs_name": None})
            except Exception:
                pass
        items.append(item)
    return {"level": level, "mode": mode, "items": items}


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
    """Grade one half of an item in whatever mode it is in right now."""
    from shared.drill import wrong_type_hint

    ensure_schema(db)
    if prompt_type not in ("meaning", "reading"):
        raise ValueError("prompt_type must be meaning or reading")
    rows = db.execute(
        """
        select c.level, c.srs_stage, c.available_at,
               c.meaning_ok, c.reading_ok, c.meaning_wrong, c.reading_wrong,
               s.object_type, s.primary_meaning, s.meanings, s.readings, s.raw
        from course_items c
        join wk_subjects s on s.id = c.subject_id
        where c.subject_id = %s
        """,
        [subject_id],
        fetch=True,
    )
    if not rows:
        raise ValueError("item is not in a course")
    (level, stage, available_at, meaning_ok, reading_ok, meaning_wrong,
     reading_wrong, object_type, primary_meaning, meanings_raw, readings_raw,
     raw) = rows[0]
    raw = _parse_json(raw) if not isinstance(raw, dict) else raw
    now = _now()
    mode = mode_for(int(stage or 0), available_at, now)
    if not mode:
        raise ValueError("burned items are done")

    readings = _accepted_readings(readings_raw)
    has_reading = needs_reading(object_type, readings)
    if prompt_type == "reading" and not has_reading:
        raise ValueError("this item has no reading")

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
    # A check is one look per half: a miss closes the half too. Everywhere
    # else a half stays open until it's right, and each miss is counted.
    closes = correct or mode == "check"
    if prompt_type == "meaning":
        meaning_ok = meaning_ok or closes
        meaning_wrong += 0 if correct else 1
    else:
        reading_ok = reading_ok or closes
        reading_wrong += 0 if correct else 1

    done = meaning_ok and (reading_ok or not has_reading)
    payload = {
        "subject_id": subject_id,
        "mode": mode,
        "correct": correct,
        "almost": result == "almost",
        "gave_up": bool(gave_up),
        "submitted": submitted,
        "item_done": done,
        "previous_stage": stage,
        "stage": stage,
        "stage_name": SRS_NAMES.get(stage) if stage else "unchecked",
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
        return _with_reveal(db, payload, subject_id)

    new = outcome(mode, stage, meaning_wrong, reading_wrong)
    keep_clock = mode == "ahead" and new == stage
    db.execute(
        """
        update course_items
        set srs_stage = %s,
            started_at = coalesce(started_at, %s),
            available_at = case when %s then available_at else %s end,
            passed_at = case when %s >= %s then coalesce(passed_at, %s) else passed_at end,
            burned_at = case when %s >= %s then %s else null end,
            meaning_ok = false, reading_ok = false,
            meaning_wrong = 0, reading_wrong = 0,
            review_count = review_count + 1,
            wrong_count = wrong_count + %s
        where subject_id = %s
        """,
        [
            new, now,
            keep_clock, next_available(new, now),
            new, GURU, now,
            new, BURNED, now,
            1 if (meaning_wrong + reading_wrong) else 0,
            subject_id,
        ],
    )
    payload.update({
        "stage": new,
        "stage_name": SRS_NAMES.get(new),
        "clean": (meaning_wrong + reading_wrong) == 0,
        "next_review_at": None if keep_clock else _iso(next_available(new, now)),
    })
    if new >= GURU > stage:
        payload["level_passed"] = _check_pass(db, level, now)
    return _with_reveal(db, payload, subject_id)


def _with_reveal(db, payload, subject_id):
    try:
        payload["inspect"] = fetch_inspect(db, subject_id)
        payload["inspect"]["srs_name"] = None  # old WK snapshot, not course state
    except Exception:
        payload["inspect"] = None
    return payload


def jsonable(value):
    return json.loads(json.dumps(value, default=str))

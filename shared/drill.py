"""Interactive drills: typed recall, reverse recognition, ghosts, leeches.

Warm-Up Quiz stays multiple-choice on /api/quiz. This module is the practice
layer that actually resembles a WaniKani review — type the answer, get
instant feedback, and bias the pool toward rot / leeches / burned items.
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone

from shared.inspect import fetch_inspect
from shared.quiz import (
    build_question,
    choose_prompt_type,
    enrich_pool_row,
    fetch_pool,
    normalize_object_types,
    sample_weighted,
)


ALLOWED_KINDS = ("recall", "reverse", "mc", "speed")
ALLOWED_POOLS = ("decay", "burned", "leeches", "due", "misses")

SCHEMA_STATEMENTS = (
    """
    create table if not exists drill_sessions (
        id              uuid primary key,
        kind            text not null,
        pool            text not null,
        min_level       integer not null,
        max_level       integer not null,
        question_count  integer not null,
        created_at      timestamptz not null default now(),
        finished_at     timestamptz,
        score_correct   integer not null default 0,
        score_total     integer not null default 0,
        combo_best      integer not null default 0,
        meta            jsonb not null default '{}'::jsonb
    )
    """,
    """
    create index if not exists drill_sessions_created_idx
        on drill_sessions (created_at desc)
    """,
    """
    create table if not exists drill_questions (
        id                  uuid primary key,
        session_id          uuid not null references drill_sessions (id) on delete cascade,
        position            integer not null,
        subject_id          bigint not null,
        prompt_type         text not null,
        characters          text,
        object_type         text not null,
        level               integer not null,
        decay_score         integer not null default 0,
        correct_answer      text not null,
        accepted_answers    jsonb not null default '[]'::jsonb,
        choices             jsonb not null default '[]'::jsonb,
        correct_index       integer,
        answered_text       text,
        answered_index      integer,
        is_correct          boolean,
        answered_at         timestamptz,
        unique (session_id, position)
    )
    """,
    """
    create index if not exists drill_questions_session_idx
        on drill_questions (session_id)
    """,
    """
    create table if not exists drill_misses (
        subject_id      bigint primary key,
        miss_count      integer not null default 0,
        hit_count       integer not null default 0,
        last_missed_at  timestamptz,
        last_prompt_type text,
        last_answer     text
    )
    """,
)


_SCHEMA_READY = False


def ensure_schema(db):
    """Create drill tables if needed. Skip after the first successful check."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    try:
        if db.has_relation("public.drill_sessions"):
            _SCHEMA_READY = True
            return
    except Exception:
        pass
    for statement in SCHEMA_STATEMENTS:
        db.execute(statement)
    _SCHEMA_READY = True


def leech_score(item):
    incorrect = int(item.get("meaning_incorrect") or 0) + int(item.get("reading_incorrect") or 0)
    correct = int(item.get("meaning_correct") or 0) + int(item.get("reading_correct") or 0)
    if incorrect < 4:
        return 0.0
    return incorrect / (max(correct, 1) ** 1.5)


def is_leech(item):
    accuracy = item.get("accuracy")
    score = leech_score(item)
    if score >= 1.0:
        return True
    incorrect = int(item.get("meaning_incorrect") or 0) + int(item.get("reading_incorrect") or 0)
    return incorrect >= 5 and accuracy is not None and accuracy < 80


def filter_pool(items, pool, miss_ids=None):
    if pool == "burned":
        return [item for item in items if item.get("burned")]
    if pool == "leeches":
        return [item for item in items if is_leech(item)]
    if pool == "due":
        return [item for item in items if item.get("due")]
    if pool == "misses":
        miss_ids = set(miss_ids or [])
        return [item for item in items if item["subject_id"] in miss_ids]
    return list(items)


def _weight_item(item, pool):
    if pool == "leeches":
        return (leech_score(item) * 20) + (item.get("decay_score") or 0)
    if pool == "burned":
        # Burned items are often high-accuracy; still prefer the softest ones.
        accuracy = item.get("accuracy")
        softness = 0 if accuracy is None else max(0, 100 - accuracy)
        return softness + 1
    if pool == "misses":
        return (item.get("decay_score") or 0) + 12
    return item.get("decay_score") or 0


def sample_for_pool(items, count, rng, pool):
    tagged = []
    for item in items:
        clone = dict(item)
        clone["decay_score"] = _weight_item(item, pool)
        tagged.append(clone)
    return sample_weighted(tagged, count, rng)


def _fetch_miss_ids(db):
    try:
        rows = db.execute(
            """
            select subject_id from drill_misses
            where miss_count > 0
            order by miss_count desc, last_missed_at desc nulls last
            limit 80
            """,
            fetch=True,
        )
        return [row[0] for row in rows]
    except Exception:
        return []


def build_reverse_question(item, pool, rng):
    characters = item.get("characters")
    meaning = item.get("primary_meaning")
    if not characters or not meaning:
        return None
    same_type = [
        other for other in pool
        if other["subject_id"] != item["subject_id"]
        and other.get("type") == item.get("type")
        and other.get("characters")
        and other["characters"] != characters
    ]
    same_type.sort(key=lambda other: (
        abs(other["level"] - item["level"]),
        -other.get("decay_score", 0),
        other["characters"],
    ))
    glyphs = []
    seen = {characters}
    for other in same_type:
        glyph = other["characters"]
        if glyph in seen:
            continue
        seen.add(glyph)
        glyphs.append(glyph)
        if len(glyphs) >= 12:
            break
    distractors = rng.sample(glyphs, min(3, len(glyphs)))
    choices = distractors + [characters]
    rng.shuffle(choices)
    return {
        "subject_id": item["subject_id"],
        "prompt_type": "reverse",
        "characters": characters,
        "object_type": item["type"],
        "level": item["level"],
        "decay_score": item["decay_score"],
        "band": item.get("band"),
        "correct_answer": characters,
        "accepted_answers": [characters],
        "choices": choices,
        "correct_index": choices.index(characters),
        "prompt_text": meaning,
        "reveal": {
            "meaning": meaning,
            "reading": item.get("primary_reading"),
            "meanings": item.get("meanings", [])[:4],
            "readings": item.get("readings", [])[:4],
        },
    }


def build_recall_question(item, prompt_type):
    if prompt_type == "meaning":
        answer = item.get("primary_meaning")
        accepted = list(item.get("meanings") or [])
    else:
        answer = item.get("primary_reading")
        accepted = list(item.get("readings") or [])
    if not answer:
        return None
    if answer not in accepted:
        accepted.insert(0, answer)
    return {
        "subject_id": item["subject_id"],
        "prompt_type": prompt_type,
        "characters": item["characters"],
        "object_type": item["type"],
        "level": item["level"],
        "decay_score": item["decay_score"],
        "band": item.get("band"),
        "correct_answer": answer,
        "accepted_answers": accepted,
        "choices": [],
        "correct_index": None,
        "prompt_text": item["characters"],
        "reveal": {
            "meaning": item.get("primary_meaning"),
            "reading": item.get("primary_reading"),
            "meanings": (item.get("meanings") or [])[:4],
            "readings": (item.get("readings") or [])[:4],
        },
    }


def build_mc_question(item, pool, prompt_type, rng):
    question = build_question(item, pool, prompt_type, rng)
    if not question:
        return None
    accepted = (
        list(item.get("meanings") or [])
        if prompt_type == "meaning"
        else list(item.get("readings") or [])
    )
    question["accepted_answers"] = accepted or [question["correct_answer"]]
    question["prompt_text"] = item["characters"]
    return question


def _expand_object_types(object_types):
    types = normalize_object_types(object_types)
    if "vocabulary" in types and "kana_vocabulary" not in types:
        types = list(types) + ["kana_vocabulary"]
    return types


def build_drill(
    pool_rows,
    min_level,
    max_level,
    count=10,
    modes=None,
    kind="recall",
    pool="decay",
    seed=None,
    now=None,
    object_types=None,
    miss_ids=None,
):
    kind = (kind or "recall").strip().casefold()
    pool = (pool or "decay").strip().casefold()
    if kind not in ALLOWED_KINDS:
        raise ValueError("kind must be recall, reverse, mc, or speed")
    if pool not in ALLOWED_POOLS:
        raise ValueError("pool must be decay, burned, leeches, due, or misses")
    modes = modes or ["meaning", "reading"]
    modes = [m for m in modes if m in ("meaning", "reading")]
    if not modes:
        raise ValueError("modes must include meaning and/or reading")
    if min_level > max_level:
        raise ValueError("min_level cannot exceed max_level")
    count = max(1, min(40, int(count)))
    if kind == "speed":
        count = max(count, 20)
    object_types = _expand_object_types(object_types)
    allowed = set(object_types) | (
        {"vocabulary"} if "kana_vocabulary" in object_types else set()
    )

    rng = random.Random(seed)
    now = now or datetime.now(timezone.utc)
    items = [enrich_pool_row(row, now=now) for row in pool_rows]
    items = [
        item for item in items
        if item.get("characters")
        and item.get("type") in allowed
        and (item.get("primary_meaning") or item.get("primary_reading"))
    ]
    items = filter_pool(items, pool, miss_ids=miss_ids)
    if not items:
        raise ValueError(_empty_pool_message(pool, min_level, max_level))

    sample_size = min(len(items), max(count * 3, count + 8))
    candidates = sample_for_pool(items, sample_size, rng, pool)

    questions = []
    used = set()
    question_kind = "recall" if kind == "speed" else kind
    for item in candidates:
        if item["subject_id"] in used:
            continue
        if question_kind == "reverse":
            question = build_reverse_question(item, items, rng)
        else:
            prompt_type = choose_prompt_type(item, modes, rng)
            if not prompt_type:
                continue
            if question_kind == "mc":
                question = build_mc_question(item, items, prompt_type, rng)
            else:
                question = build_recall_question(item, prompt_type)
        if not question:
            continue
        questions.append(question)
        used.add(item["subject_id"])
        if len(questions) >= count:
            break

    if not questions:
        raise ValueError("could not build a drill from the matching subjects")

    session_id = str(uuid.uuid4())
    avg_decay = round(
        sum(q["decay_score"] for q in questions) / len(questions), 1
    )
    return {
        "session_id": session_id,
        "kind": kind,
        "pool": pool,
        "min_level": min_level,
        "max_level": max_level,
        "question_count": len(questions),
        "modes": modes,
        "object_types": [t for t in object_types if t != "kana_vocabulary"] or object_types,
        "created_at": now.isoformat(),
        "seconds": 60 if kind == "speed" else None,
        "weighting": {
            "method": f"{pool} weighted sample",
            "mean_decay_score": avg_decay,
        },
        "questions": questions,
    }


def _empty_pool_message(pool, min_level, max_level):
    span = f"levels {min_level}–{max_level}"
    if pool == "burned":
        return f"no burned items in {span} yet — ghosts appear after items hit burned"
    if pool == "leeches":
        return f"no leeches in {span} — that's a good problem"
    if pool == "due":
        return f"nothing currently due in {span}"
    if pool == "misses":
        return "no Sensei misses to retry yet — miss something first"
    return f"no matching subjects in {span}"


def public_question(question, position):
    reverse = question["prompt_type"] == "reverse"
    return {
        "id": question["id"],
        "position": position,
        "prompt_type": question["prompt_type"],
        "characters": None if reverse else question["characters"],
        "object_type": question["object_type"],
        "level": question["level"],
        "decay_score": question["decay_score"],
        "band": question.get("band"),
        "choices": question.get("choices") or [],
        "prompt_text": question.get("prompt_text") or question["characters"],
    }


def persist_drill(db, drill):
    session_id = drill["session_id"]
    db.execute(
        """
        insert into drill_sessions
          (id, kind, pool, min_level, max_level, question_count, created_at, meta)
        values (%s::uuid, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        [
            session_id,
            drill["kind"],
            drill["pool"],
            drill["min_level"],
            drill["max_level"],
            drill["question_count"],
            drill["created_at"],
            json.dumps({
                "modes": drill["modes"],
                "object_types": drill["object_types"],
                "weighting": drill["weighting"],
                "seconds": drill.get("seconds"),
            }),
        ],
    )
    rows = []
    for idx, question in enumerate(drill["questions"]):
        qid = str(uuid.uuid4())
        question["id"] = qid
        rows.append([
            qid,
            session_id,
            idx,
            question["subject_id"],
            question["prompt_type"],
            question["characters"],
            question["object_type"],
            question["level"],
            question["decay_score"],
            question["correct_answer"],
            json.dumps(question.get("accepted_answers") or [], ensure_ascii=False),
            json.dumps(question.get("choices") or [], ensure_ascii=False),
            question.get("correct_index"),
        ])
    db.executemany(
        """
        insert into drill_questions
          (id, session_id, position, subject_id, prompt_type, characters,
           object_type, level, decay_score, correct_answer, accepted_answers,
           choices, correct_index)
        values
          (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
           %s::jsonb, %s)
        """,
        rows,
    )
    return drill


def start_drill(
    db,
    min_level,
    max_level,
    count=10,
    modes=None,
    kind="recall",
    pool="decay",
    object_types=None,
    seed=None,
):
    ensure_schema(db)
    object_types = _expand_object_types(object_types)
    miss_ids = _fetch_miss_ids(db) if pool == "misses" else None
    rows = fetch_pool(db, min_level, max_level, object_types=object_types)
    drill = build_drill(
        rows,
        min_level=min_level,
        max_level=max_level,
        count=count,
        modes=modes,
        kind=kind,
        pool=pool,
        seed=seed,
        object_types=object_types,
        miss_ids=miss_ids,
    )
    persist_drill(db, drill)
    return {
        "session_id": drill["session_id"],
        "kind": drill["kind"],
        "pool": drill["pool"],
        "min_level": drill["min_level"],
        "max_level": drill["max_level"],
        "question_count": drill["question_count"],
        "modes": drill["modes"],
        "object_types": drill["object_types"],
        "created_at": drill["created_at"],
        "seconds": drill.get("seconds"),
        "weighting": drill["weighting"],
        "questions": [
            public_question(q, i) for i, q in enumerate(drill["questions"])
        ],
    }


def _parse_json(value):
    if value is None:
        return []
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode()
    if isinstance(value, str):
        return json.loads(value) if value else []
    return list(value)


def _record_miss(db, subject_id, is_correct, prompt_type, submitted):
    if is_correct:
        db.execute(
            """
            insert into drill_misses (subject_id, hit_count)
            values (%s, 1)
            on conflict (subject_id) do update set
              hit_count = drill_misses.hit_count + 1
            """,
            [subject_id],
        )
        return
    db.execute(
        """
        insert into drill_misses
          (subject_id, miss_count, last_missed_at, last_prompt_type, last_answer)
        values (%s, 1, now(), %s, %s)
        on conflict (subject_id) do update set
          miss_count = drill_misses.miss_count + 1,
          last_missed_at = now(),
          last_prompt_type = excluded.last_prompt_type,
          last_answer = excluded.last_answer
        """,
        [subject_id, prompt_type, (submitted or "")[:80]],
    )


def _sensei_verdict(correct, total):
    if total <= 0:
        return "Empty round."
    ratio = correct / total
    if ratio >= 0.9:
        return "Sensei nods. That was clean."
    if ratio >= 0.7:
        return "Warm. A few still have teeth."
    if ratio >= 0.4:
        return "The pile bit back. That's why we drill."
    return "Rough round. Retry the misses before the real queue."


def grade_drill(db, session_id, question_id, choice_index=None, text=None, gave_up=False):
    ensure_schema(db)
    rows = db.execute(
        """
        select q.id, q.subject_id, q.prompt_type, q.characters, q.object_type,
               q.level, q.correct_answer, q.accepted_answers, q.choices,
               q.correct_index, q.answered_index, q.answered_text,
               sess.kind, sess.score_correct, sess.score_total,
               sess.question_count, sess.combo_best, sess.meta
        from drill_questions q
        join drill_sessions sess on sess.id = q.session_id
        where q.id = %s::uuid and q.session_id = %s::uuid
        """,
        [question_id, session_id],
        fetch=True,
    )
    if not rows:
        raise ValueError("question not found")
    (qid, subject_id, prompt_type, characters, object_type, level,
     correct_answer, accepted_raw, choices_raw, correct_index,
     answered_index, answered_text, kind, score_correct, score_total,
     question_count, combo_best, meta) = rows[0]

    if answered_index is not None or answered_text is not None:
        raise ValueError("question already answered")

    choices = _parse_json(choices_raw)
    accepted = _parse_json(accepted_raw) or [correct_answer]
    meta = _parse_json(meta) if not isinstance(meta, dict) else (meta or {})
    combo = int(meta.get("combo") or 0)
    now = datetime.now(timezone.utc).isoformat()

    almost = False
    submitted = ""
    chosen_index = None
    if gave_up:
        is_correct = False
        submitted = ""
    elif prompt_type == "reverse" or kind == "mc" or (choice_index is not None and text is None):
        if choice_index is None:
            raise ValueError("choice_index is required")
        chosen_index = int(choice_index)
        if chosen_index < 0 or chosen_index >= len(choices):
            raise ValueError("choice_index out of range")
        submitted = choices[chosen_index]
        is_correct = chosen_index == int(correct_index)
    else:
        submitted = (text or "").strip()
        if not submitted:
            raise ValueError("text is required")
        result = check_typed(prompt_type, submitted, accepted)
        is_correct = result == "correct"
        almost = result == "almost"

    if is_correct:
        combo += 1
    else:
        combo = 0
    combo_best = max(int(combo_best or 0), combo)
    meta["combo"] = combo

    db.execute(
        """
        update drill_questions
        set answered_index = %s, answered_text = %s, is_correct = %s, answered_at = %s
        where id = %s::uuid
        """,
        [chosen_index, submitted, is_correct, now, qid],
    )
    new_correct = int(score_correct) + (1 if is_correct else 0)
    new_total = int(score_total) + 1
    finished = new_total >= int(question_count)
    db.execute(
        """
        update drill_sessions
        set score_correct = %s, score_total = %s, combo_best = %s, meta = %s::jsonb,
            finished_at = case when %s then %s else finished_at end
        where id = %s::uuid
        """,
        [
            new_correct, new_total, combo_best, json.dumps(meta),
            finished, now if finished else None, session_id,
        ],
    )
    try:
        _record_miss(db, subject_id, is_correct, prompt_type, submitted)
    except Exception:
        pass

    return {
        "question_id": question_id,
        "correct": is_correct,
        "almost": almost,
        "gave_up": bool(gave_up),
        "correct_index": correct_index,
        "correct_answer": correct_answer,
        "chosen_index": chosen_index,
        "submitted": submitted,
        "combo": combo,
        "combo_best": combo_best,
        "reveal": {
            "characters": characters,
            "type": object_type,
            "level": level,
            "prompt_type": prompt_type,
            "meaning": None,
            "meanings": accepted if prompt_type == "meaning" else [],
            "readings": accepted if prompt_type == "reading" else [],
            "answer": correct_answer,
            "subject_id": subject_id,
        },
        "score": {
            "correct": new_correct,
            "total": new_total,
            "remaining": max(0, int(question_count) - new_total),
            "finished": finished,
        },
        "verdict": _sensei_verdict(new_correct, new_total) if finished else None,
    }


def _hydrate_reveal(db, payload):
    """Attach a teaching card after grading. Meanings/readings come with it."""
    subject_id = (payload.get("reveal") or {}).get("subject_id")
    if not subject_id:
        return payload
    try:
        card = fetch_inspect(db, subject_id)
        payload["inspect"] = card
        payload["reveal"]["meaning"] = card.get("meaning") or payload["reveal"].get("meaning")
        if card.get("meanings"):
            payload["reveal"]["meanings"] = card["meanings"][:4]
        payload["reveal"]["readings"] = [
            item["reading"] for item in (card.get("readings") or [])
        ][:4]
        payload["reveal"]["wk_url"] = card.get("wk_url")
        payload["reveal"]["audio_url"] = card.get("audio_url")
        payload["reveal"]["readings_labeled"] = card.get("readings") or []
    except Exception:
        pass
    return payload


def grade_drill_answer(
    db, session_id, question_id, choice_index=None, text=None, gave_up=False,
):
    result = grade_drill(
        db,
        session_id,
        question_id,
        choice_index=choice_index,
        text=text,
        gave_up=gave_up,
    )
    return _hydrate_reveal(db, result)


def get_drill(db, session_id):
    ensure_schema(db)
    rows = db.execute(
        """
        select id, kind, pool, min_level, max_level, question_count, created_at,
               finished_at, score_correct, score_total, combo_best, meta
        from drill_sessions where id = %s::uuid
        """,
        [session_id],
        fetch=True,
    )
    if not rows:
        raise ValueError("session not found")
    (sid, kind, pool, min_level, max_level, question_count, created_at,
     finished_at, score_correct, score_total, combo_best, meta) = rows[0]
    questions = db.execute(
        """
        select id, position, prompt_type, characters, object_type, level,
               decay_score, choices, answered_index, answered_text, is_correct,
               correct_index, correct_answer
        from drill_questions
        where session_id = %s::uuid
        order by position
        """,
        [session_id],
        fetch=True,
    )
    out = []
    misses = []
    for row in questions:
        (qid, position, prompt_type, characters, object_type, level, decay_score,
         choices, answered_index, answered_text, is_correct, correct_index,
         correct_answer) = row
        item = {
            "id": str(qid),
            "position": position,
            "prompt_type": prompt_type,
            "characters": characters,
            "object_type": object_type,
            "level": level,
            "decay_score": decay_score,
            "choices": _parse_json(choices),
            "answered": answered_index is not None or answered_text is not None,
        }
        if item["answered"]:
            item["answered_index"] = answered_index
            item["answered_text"] = answered_text
            item["is_correct"] = is_correct
            item["correct_index"] = correct_index
            item["correct_answer"] = correct_answer
            if is_correct is False:
                misses.append({
                    "characters": characters,
                    "prompt_type": prompt_type,
                    "submitted": answered_text,
                    "correct_answer": correct_answer,
                    "object_type": object_type,
                    "level": level,
                })
        out.append(item)
    score_total = int(score_total or 0)
    score_correct = int(score_correct or 0)
    return {
        "session_id": str(sid),
        "kind": kind,
        "pool": pool,
        "min_level": min_level,
        "max_level": max_level,
        "question_count": question_count,
        "created_at": created_at,
        "finished_at": finished_at,
        "combo_best": combo_best,
        "score": {"correct": score_correct, "total": score_total},
        "verdict": _sensei_verdict(score_correct, score_total) if finished_at else None,
        "misses": misses,
        "meta": _parse_json(meta) if not isinstance(meta, dict) else meta,
        "questions": out,
    }


def fetch_practice_overview(db):
    """Lightweight stats for the home dashboard. Missing tables → empty stats."""
    stats = {
        "week_sessions": 0,
        "week_correct": 0,
        "week_total": 0,
        "week_accuracy": None,
        "combo_best": 0,
        "burned": 0,
        "leeches": 0,
        "due": 0,
        "notebook": [],
    }
    try:
        ensure_schema(db)
        week = db.execute(
            """
            select count(*), coalesce(sum(score_correct), 0),
                   coalesce(sum(score_total), 0), coalesce(max(combo_best), 0)
            from drill_sessions
            where created_at > now() - interval '7 days'
              and score_total > 0
            """,
            fetch=True,
        )[0]
        stats["week_sessions"] = int(week[0] or 0)
        stats["week_correct"] = int(week[1] or 0)
        stats["week_total"] = int(week[2] or 0)
        stats["combo_best"] = int(week[3] or 0)
        if stats["week_total"]:
            stats["week_accuracy"] = round(
                stats["week_correct"] / stats["week_total"] * 100, 1
            )
        notebook = db.execute(
            """
            select m.subject_id, s.characters, s.object_type, s.level,
                   s.primary_meaning, m.miss_count, m.hit_count
            from drill_misses m
            join wk_subjects s on s.id = m.subject_id
            where m.miss_count > 0
            order by m.miss_count desc, m.last_missed_at desc nulls last
            limit 8
            """,
            fetch=True,
        )
        stats["notebook"] = [
            {
                "subject_id": row[0],
                "characters": row[1],
                "type": row[2],
                "level": row[3],
                "meaning": row[4],
                "miss_count": row[5],
                "hit_count": row[6],
            }
            for row in notebook
        ]
    except Exception:
        pass
    try:
        counts = db.execute(
            """
            select
              count(*) filter (where a.srs_stage >= 9 or a.burned_at is not null),
              count(*) filter (
                where coalesce(r.meaning_incorrect,0) + coalesce(r.reading_incorrect,0) >= 5
                  and coalesce(r.percentage_correct, 100) < 80
              ),
              count(*) filter (
                where a.available_at is not null
                  and a.available_at <= now()
                  and a.burned_at is null
              )
            from wk_assignments a
            left join wk_review_stats r on r.subject_id = a.subject_id
            """,
            fetch=True,
        )[0]
        stats["burned"] = int(counts[0] or 0)
        stats["leeches"] = int(counts[1] or 0)
        stats["due"] = int(counts[2] or 0)
    except Exception:
        pass
    return stats

"""Warm-Up Quiz — decay-weighted multiple-choice drills.

Picks a level range, samples items by Decay Map score, and builds
meaning/reading questions with same-type distractors from nearby levels.
Correct answers stay server-side until the learner submits.
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone

from shared.decay_map import classify_item


ALLOWED_OBJECT_TYPES = ("kanji", "vocabulary", "radical")
DEFAULT_OBJECT_TYPES = ("kanji", "vocabulary")
OBJECT_TYPE_ALIASES = {
    "kanji": "kanji",
    "vocabulary": "vocabulary",
    "vocab": "vocabulary",
    "radical": "radical",
    "radicals": "radical",
}

QUIZ_POOL_QUERY = """
select
    s.id, s.level, s.object_type, s.characters, s.primary_meaning,
    s.meanings, s.readings,
    r.meaning_correct, r.meaning_incorrect,
    r.reading_correct, r.reading_incorrect,
    a.srs_stage, a.available_at, a.burned_at,
    prev.srs_stage as prev_srs_stage
from wk_subjects s
join wk_review_stats r on r.subject_id = s.id
left join wk_assignments a on a.subject_id = s.id
left join lateral (
    select snap.srs_stage
    from wk_assignment_snapshots snap
    where snap.subject_id = s.id
      and snap.snap_date < current_date
    order by snap.snap_date desc
    limit 1
) prev on true
where s.object_type = any(%s)
  and s.characters is not null
  and s.characters <> ''
  and s.level >= %s and s.level <= %s
"""

QUIZ_POOL_QUERY_LEGACY = """
select
    s.id, s.level, s.object_type, s.characters, s.primary_meaning,
    s.meanings, s.readings,
    r.meaning_correct, r.meaning_incorrect,
    r.reading_correct, r.reading_incorrect,
    a.srs_stage, a.available_at, a.burned_at,
    null::integer as prev_srs_stage
from wk_subjects s
join wk_review_stats r on r.subject_id = s.id
left join wk_assignments a on a.subject_id = s.id
where s.object_type = any(%s)
  and s.characters is not null
  and s.characters <> ''
  and s.level >= %s and s.level <= %s
"""


def normalize_object_types(object_types=None):
    """Normalize quiz category filters to WK object_type values."""
    if object_types is None:
        return list(DEFAULT_OBJECT_TYPES)
    if isinstance(object_types, str):
        object_types = [object_types]
    if not isinstance(object_types, (list, tuple)):
        raise ValueError("object_types must be a list")
    cleaned = []
    for raw in object_types:
        key = str(raw or "").strip().casefold()
        mapped = OBJECT_TYPE_ALIASES.get(key)
        if mapped is None:
            raise ValueError(
                "object_types must be kanji, vocabulary, and/or radical"
            )
        if mapped not in cleaned:
            cleaned.append(mapped)
    if not cleaned:
        raise ValueError("object_types must include at least one type")
    return cleaned


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


def _accepted_meanings(meanings_raw, primary):
    meanings = _parse_json(meanings_raw)
    out = []
    for entry in meanings:
        if not isinstance(entry, dict):
            continue
        if entry.get("accepted_answer", True) is False:
            continue
        text = (entry.get("meaning") or "").strip()
        if text:
            out.append(text)
    if primary and primary not in out:
        out.insert(0, primary)
    return out


def _accepted_readings(readings_raw):
    readings = _parse_json(readings_raw)
    out = []
    for entry in readings:
        if not isinstance(entry, dict):
            continue
        if entry.get("accepted_answer", True) is False:
            continue
        text = (entry.get("reading") or "").strip()
        if text:
            out.append(text)
    return out


def _primary_reading(readings_raw):
    readings = _parse_json(readings_raw)
    for entry in readings:
        if isinstance(entry, dict) and entry.get("primary") and entry.get("reading"):
            return entry["reading"].strip()
    accepted = _accepted_readings(readings_raw)
    return accepted[0] if accepted else None


def enrich_pool_row(row, now=None):
    (subject_id, level, object_type, characters, primary_meaning, meanings_raw,
     readings_raw, meaning_correct, meaning_incorrect, reading_correct,
     reading_incorrect, srs_stage, available_at, burned_at, prev_srs_stage) = row

    classified = classify_item((
        subject_id, level, object_type, characters, primary_meaning,
        meaning_correct, meaning_incorrect, reading_correct, reading_incorrect,
        srs_stage, available_at, burned_at, prev_srs_stage,
    ), now=now)

    meanings = _accepted_meanings(meanings_raw, primary_meaning)
    readings = _accepted_readings(readings_raw)
    primary_reading = _primary_reading(readings_raw)
    return {
        **classified,
        "meanings": meanings,
        "readings": readings,
        "primary_reading": primary_reading,
        "primary_meaning": meanings[0] if meanings else primary_meaning,
    }


def sample_weighted(items, count, rng):
    """Sample without replacement, weight ~ (decay_score + 1)^1.6."""
    pool = list(items)
    picked = []
    count = min(count, len(pool))
    for _ in range(count):
        weights = [(max(0, item["decay_score"]) + 1) ** 1.6 for item in pool]
        total = sum(weights)
        if total <= 0:
            choice = rng.choice(pool)
        else:
            target = rng.uniform(0, total)
            running = 0.0
            choice = pool[-1]
            for item, weight in zip(pool, weights):
                running += weight
                if running >= target:
                    choice = item
                    break
        picked.append(choice)
        pool.remove(choice)
    return picked


def _normalize(text):
    return (text or "").strip().casefold()


def pick_distractors(target, pool, prompt_type, rng, k=3):
    if prompt_type == "meaning":
        correct = target["primary_meaning"]
        key = "primary_meaning"
        banned = {_normalize(m) for m in target["meanings"]}
    else:
        correct = target["primary_reading"]
        key = "primary_reading"
        banned = {_normalize(r) for r in target["readings"]}

    if not correct:
        return []

    same_type = [
        item for item in pool
        if item["subject_id"] != target["subject_id"]
        and item["type"] == target["type"]
        and item.get(key)
        and _normalize(item[key]) not in banned
    ]

    # Prefer nearby levels, then anything else.
    same_type.sort(key=lambda item: (
        abs(item["level"] - target["level"]),
        -item["decay_score"],
        item["characters"] or "",
    ))
    candidates = []
    seen = set()
    for item in same_type:
        text = item[key]
        norm = _normalize(text)
        if norm in seen or norm in banned:
            continue
        seen.add(norm)
        candidates.append(text)
        if len(candidates) >= max(12, k * 4):
            break

    if len(candidates) < k:
        return []
    return rng.sample(candidates, k)


def build_question(item, pool, prompt_type, rng):
    if prompt_type == "meaning":
        answer = item["primary_meaning"]
        if not answer:
            return None
    else:
        answer = item["primary_reading"]
        if not answer:
            return None

    distractors = pick_distractors(item, pool, prompt_type, rng, k=3)
    if len(distractors) < 3:
        return None

    choices = distractors + [answer]
    rng.shuffle(choices)
    correct_index = choices.index(answer)
    return {
        "subject_id": item["subject_id"],
        "prompt_type": prompt_type,
        "characters": item["characters"],
        "object_type": item["type"],
        "level": item["level"],
        "decay_score": item["decay_score"],
        "band": item["band"],
        "correct_answer": answer,
        "choices": choices,
        "correct_index": correct_index,
        "reveal": {
            "meaning": item["primary_meaning"],
            "reading": item["primary_reading"],
            "meanings": item["meanings"][:4],
            "readings": item["readings"][:4],
        },
    }


def choose_prompt_type(item, modes, rng):
    available = []
    if "meaning" in modes and item.get("primary_meaning"):
        available.append("meaning")
    if "reading" in modes and item.get("primary_reading"):
        available.append("reading")
    if not available:
        return None
    return rng.choice(available)


def build_quiz(
    pool_rows,
    min_level,
    max_level,
    count=10,
    modes=None,
    seed=None,
    now=None,
    object_types=None,
):
    modes = modes or ["meaning", "reading"]
    modes = [m for m in modes if m in ("meaning", "reading")]
    if not modes:
        raise ValueError("modes must include meaning and/or reading")
    if min_level > max_level:
        raise ValueError("min_level cannot exceed max_level")
    count = max(1, min(30, int(count)))
    object_types = normalize_object_types(object_types)
    allowed = set(object_types)

    rng = random.Random(seed)
    now = now or datetime.now(timezone.utc)
    pool = [enrich_pool_row(row, now=now) for row in pool_rows]
    pool = [
        item for item in pool
        if item.get("characters")
        and item.get("type") in allowed
        and (item.get("primary_meaning") or item.get("primary_reading"))
    ]
    if not pool:
        raise ValueError("not enough subjects in this level range for a quiz")

    # Oversample then build until we have enough valid MC questions.
    sample_size = min(len(pool), max(count * 3, count + 8))
    candidates = sample_weighted(pool, sample_size, rng)

    questions = []
    used_subjects = set()
    for item in candidates:
        if item["subject_id"] in used_subjects:
            continue
        prompt_type = choose_prompt_type(item, modes, rng)
        if not prompt_type:
            continue
        question = build_question(item, pool, prompt_type, rng)
        if not question:
            continue
        questions.append(question)
        used_subjects.add(item["subject_id"])
        if len(questions) >= count:
            break

    if not questions:
        raise ValueError("could not build enough multiple-choice questions")

    session_id = str(uuid.uuid4())
    avg_decay = round(sum(q["decay_score"] for q in questions) / len(questions), 1)
    return {
        "session_id": session_id,
        "min_level": min_level,
        "max_level": max_level,
        "question_count": len(questions),
        "modes": modes,
        "object_types": object_types,
        "created_at": now.isoformat(),
        "weighting": {
            "method": "decay_score^1.6 without replacement",
            "mean_decay_score": avg_decay,
            "high_or_medium": sum(q["band"] in ("high", "medium") for q in questions),
        },
        "questions": questions,
    }


def public_question(question, position):
    return {
        "id": question["id"],
        "position": position,
        "prompt_type": question["prompt_type"],
        "characters": question["characters"],
        "object_type": question["object_type"],
        "level": question["level"],
        "decay_score": question["decay_score"],
        "band": question["band"],
        "choices": question["choices"],
    }


def persist_quiz(db, quiz):
    """Write session + questions. Mutates quiz questions to include DB ids."""
    session_id = quiz["session_id"]
    db.execute(
        """
        insert into quiz_sessions
          (id, min_level, max_level, question_count, created_at, meta)
        values (%s::uuid, %s, %s, %s, %s, %s::jsonb)
        """,
        [
            session_id,
            quiz["min_level"],
            quiz["max_level"],
            quiz["question_count"],
            quiz["created_at"],
            json.dumps({
                "modes": quiz["modes"],
                "object_types": quiz.get("object_types") or list(DEFAULT_OBJECT_TYPES),
                "weighting": quiz["weighting"],
            }),
        ],
    )
    rows = []
    for idx, question in enumerate(quiz["questions"]):
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
            json.dumps(question["choices"], ensure_ascii=False),
            question["correct_index"],
        ])
    db.executemany(
        """
        insert into quiz_questions
          (id, session_id, position, subject_id, prompt_type, characters,
           object_type, level, decay_score, correct_answer, choices, correct_index)
        values
          (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        """,
        rows,
    )
    return quiz


def fetch_pool(db, min_level, max_level, object_types=None):
    types = normalize_object_types(object_types)
    params = [types, min_level, max_level]
    try:
        return db.execute(QUIZ_POOL_QUERY, params, fetch=True)
    except Exception:
        return db.execute(QUIZ_POOL_QUERY_LEGACY, params, fetch=True)


def start_quiz(
    db, min_level, max_level, count=10, modes=None, seed=None, object_types=None,
):
    object_types = normalize_object_types(object_types)
    rows = fetch_pool(db, min_level, max_level, object_types=object_types)
    quiz = build_quiz(
        rows,
        min_level=min_level,
        max_level=max_level,
        count=count,
        modes=modes,
        seed=seed,
        object_types=object_types,
    )
    persist_quiz(db, quiz)
    return {
        "session_id": quiz["session_id"],
        "min_level": quiz["min_level"],
        "max_level": quiz["max_level"],
        "question_count": quiz["question_count"],
        "modes": quiz["modes"],
        "object_types": quiz["object_types"],
        "created_at": quiz["created_at"],
        "weighting": quiz["weighting"],
        "questions": [
            public_question(q, i) for i, q in enumerate(quiz["questions"])
        ],
    }


def grade_answer(db, session_id, question_id, choice_index):
    rows = db.execute(
        """
        select q.id, q.correct_index, q.correct_answer, q.choices, q.answered_index,
               q.prompt_type, q.characters, q.object_type, q.level,
               s.primary_meaning, s.readings, s.meanings,
               sess.score_correct, sess.score_total, sess.question_count
        from quiz_questions q
        join quiz_sessions sess on sess.id = q.session_id
        join wk_subjects s on s.id = q.subject_id
        where q.id = %s::uuid and q.session_id = %s::uuid
        """,
        [question_id, session_id],
        fetch=True,
    )
    if not rows:
        raise ValueError("question not found")
    (qid, correct_index, correct_answer, choices, answered_index, prompt_type,
     characters, object_type, level, primary_meaning, readings_raw, meanings_raw,
     score_correct, score_total, question_count) = rows[0]

    if answered_index is not None:
        raise ValueError("question already answered")
    choice_index = int(choice_index)
    choices = _parse_json(choices)
    if choice_index < 0 or choice_index >= len(choices):
        raise ValueError("choice_index out of range")

    is_correct = choice_index == int(correct_index)
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        update quiz_questions
        set answered_index = %s, is_correct = %s, answered_at = %s
        where id = %s::uuid
        """,
        [choice_index, is_correct, now, qid],
    )
    new_correct = int(score_correct) + (1 if is_correct else 0)
    new_total = int(score_total) + 1
    finished = new_total >= int(question_count)
    if finished:
        db.execute(
            """
            update quiz_sessions
            set score_correct = %s, score_total = %s, finished_at = %s
            where id = %s::uuid
            """,
            [new_correct, new_total, now, session_id],
        )
    else:
        db.execute(
            """
            update quiz_sessions
            set score_correct = %s, score_total = %s
            where id = %s::uuid
            """,
            [new_correct, new_total, session_id],
        )
    return {
        "question_id": question_id,
        "correct": is_correct,
        "correct_index": int(correct_index),
        "correct_answer": correct_answer,
        "chosen_index": choice_index,
        "reveal": {
            "characters": characters,
            "type": object_type,
            "level": level,
            "prompt_type": prompt_type,
            "meaning": primary_meaning,
            "meanings": _accepted_meanings(meanings_raw, primary_meaning)[:4],
            "readings": _accepted_readings(readings_raw)[:4],
        },
        "score": {
            "correct": new_correct,
            "total": new_total,
            "remaining": max(0, int(question_count) - new_total),
            "finished": finished,
        },
    }


def get_session(db, session_id):
    rows = db.execute(
        """
        select id, min_level, max_level, question_count, created_at, finished_at,
               score_correct, score_total, meta
        from quiz_sessions where id = %s::uuid
        """,
        [session_id],
        fetch=True,
    )
    if not rows:
        raise ValueError("session not found")
    (sid, min_level, max_level, question_count, created_at, finished_at,
     score_correct, score_total, meta) = rows[0]
    questions = db.execute(
        """
        select id, position, prompt_type, characters, object_type, level,
               decay_score, choices, answered_index, is_correct, correct_index,
               correct_answer
        from quiz_questions
        where session_id = %s::uuid
        order by position
        """,
        [session_id],
        fetch=True,
    )
    out_questions = []
    for row in questions:
        (qid, position, prompt_type, characters, object_type, level, decay_score,
         choices, answered_index, is_correct, correct_index, correct_answer) = row
        item = {
            "id": str(qid),
            "position": position,
            "prompt_type": prompt_type,
            "characters": characters,
            "object_type": object_type,
            "level": level,
            "decay_score": decay_score,
            "choices": _parse_json(choices),
            "answered": answered_index is not None,
        }
        if answered_index is not None:
            item["answered_index"] = answered_index
            item["is_correct"] = is_correct
            item["correct_index"] = correct_index
            item["correct_answer"] = correct_answer
        out_questions.append(item)
    return {
        "session_id": str(sid),
        "min_level": min_level,
        "max_level": max_level,
        "question_count": question_count,
        "created_at": created_at,
        "finished_at": finished_at,
        "score": {"correct": score_correct, "total": score_total},
        "meta": _parse_json(meta) if not isinstance(meta, dict) else meta,
        "questions": out_questions,
    }

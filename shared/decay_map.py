"""Build the Phase 1 Decay Map from the current WaniKani snapshot.

Primary signal: lifetime accuracy + current SRS stage + due status.
When daily assignment snapshots exist, a stage regression between the
previous snap and today adds a real-history boost — not just inference.
"""

from datetime import datetime, timezone


DECAY_QUERY = """
select
    s.id, s.level, s.object_type, s.characters, s.primary_meaning,
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
where s.object_type in ('kanji', 'vocabulary')
  and (%s::integer is null or s.level >= %s::integer)
  and (%s::integer is null or s.level <= %s::integer)
"""

# Fallback when snapshots table is missing (pre-migration deploys).
DECAY_QUERY_LEGACY = """
select
    s.id, s.level, s.object_type, s.characters, s.primary_meaning,
    r.meaning_correct, r.meaning_incorrect,
    r.reading_correct, r.reading_incorrect,
    a.srs_stage, a.available_at, a.burned_at,
    null::integer as prev_srs_stage
from wk_subjects s
join wk_review_stats r on r.subject_id = s.id
left join wk_assignments a on a.subject_id = s.id
where s.object_type in ('kanji', 'vocabulary')
  and (%s::integer is null or s.level >= %s::integer)
  and (%s::integer is null or s.level <= %s::integer)
"""


def _num(value):
    return int(value or 0)


def classify_item(row, now=None):
    (subject_id, level, object_type, characters, meaning, meaning_correct,
     meaning_incorrect, reading_correct, reading_incorrect, srs_stage,
     available_at, burned_at, prev_srs_stage) = _pad_row(row)
    now = now or datetime.now(timezone.utc)
    correct = _num(meaning_correct) + _num(reading_correct)
    incorrect = _num(meaning_incorrect) + _num(reading_incorrect)
    attempts = correct + incorrect
    accuracy = round(correct / attempts * 100, 1) if attempts else None
    stage = _num(srs_stage)
    due = bool(available_at and available_at <= now and not burned_at)
    regressed = (
        prev_srs_stage is not None
        and stage < _num(prev_srs_stage)
        and not burned_at
    )

    # Accuracy is the strongest live signal. Low SRS stages amplify it,
    # due items get a nudge, and a real stage drop from history is decisive.
    if attempts == 0:
        score = 20 if stage <= 2 else 0
    else:
        score = max(0, 100 - (accuracy or 0))
        if stage <= 2:
            score += 20
        elif stage <= 4:
            score += 8
        if due:
            score += 10
    if regressed:
        score += 25 + min(20, (_num(prev_srs_stage) - stage) * 5)
    score = min(100, round(score))
    if score >= 70:
        band = "high"
    elif score >= 40:
        band = "medium"
    else:
        band = "low"
    return {
        "subject_id": subject_id,
        "level": level,
        "type": object_type,
        "characters": characters,
        "meaning": meaning,
        "accuracy": accuracy,
        "attempts": attempts,
        "srs_stage": stage,
        "due": due,
        "regressed": regressed,
        "prev_srs_stage": _num(prev_srs_stage) if prev_srs_stage is not None else None,
        "decay_score": score,
        "band": band,
    }


def _pad_row(row):
    """Accept legacy 12-tuples (tests) or 13-tuples with prev_srs_stage."""
    row = tuple(row)
    if len(row) == 12:
        return row + (None,)
    if len(row) != 13:
        raise ValueError(f"expected 12 or 13 columns, got {len(row)}")
    return row


def build_decay_map(rows, now=None, item_limit=100, history_available=False):
    items = [classify_item(row, now=now) for row in rows]
    items.sort(key=lambda item: (-item["decay_score"], item["level"], item["characters"] or ""))

    levels = {}
    for item in items:
        summary = levels.setdefault(item["level"], {
            "level": item["level"], "items": 0, "high": 0, "medium": 0,
            "low": 0, "due": 0, "regressed": 0, "accuracy_total": 0,
            "accuracy_count": 0, "score_total": 0,
        })
        summary["items"] += 1
        summary[item["band"]] += 1
        summary["due"] += int(item["due"])
        summary["regressed"] += int(item["regressed"])
        summary["score_total"] += item["decay_score"]
        if item["accuracy"] is not None:
            summary["accuracy_total"] += item["accuracy"]
            summary["accuracy_count"] += 1

    for summary in levels.values():
        count = summary.pop("accuracy_count")
        total = summary.pop("accuracy_total")
        score_total = summary.pop("score_total")
        summary["accuracy"] = round(total / count, 1) if count else None
        summary["risk"] = round(score_total / summary["items"]) if summary["items"] else 0

    level_list = sorted(levels.values(), key=lambda level: (-level["risk"], level["level"]))
    suggested = [level["level"] for level in level_list if level["risk"] >= 30][:5]
    if not suggested and level_list:
        # Soft suggestion: top risk levels even when the whole map is calm.
        suggested = [level["level"] for level in level_list[:3]]

    signal = "accuracy + current SRS stage + currently due"
    limitations = [
        "The map reflects the latest successful sync snapshot.",
    ]
    if history_available:
        signal += " + SRS stage regression vs prior daily snapshot"
        limitations.append(
            "Regression boosts only appear after at least two daily sync snapshots."
        )
    else:
        limitations.insert(
            0,
            "SRS history is sparse or missing, so decay is mostly inferred from current state.",
        )

    return {
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "signal": signal,
        "history_available": history_available,
        "limitations": limitations,
        "summary": {
            "items": len(items),
            "high_risk": sum(item["band"] == "high" for item in items),
            "medium_risk": sum(item["band"] == "medium" for item in items),
            "due": sum(item["due"] for item in items),
            "regressed": sum(item["regressed"] for item in items),
            "suggested_levels": suggested,
        },
        "levels": level_list,
        "items": items[:item_limit],
    }


def _snapshots_ready(db):
    try:
        rows = db.execute(
            """
            select exists (
                select 1 from information_schema.tables
                where table_name = 'wk_assignment_snapshots'
            ),
            coalesce((select count(*) from wk_assignment_snapshots), 0)
            """,
            fetch=True,
        )
        exists, count = rows[0]
        return bool(exists), int(count or 0)
    except Exception:
        return False, 0


def fetch_decay_map(db, min_level=None, max_level=None, item_limit=100):
    params = [min_level, min_level, max_level, max_level]
    exists, snap_count = _snapshots_ready(db)
    query = DECAY_QUERY if exists else DECAY_QUERY_LEGACY
    try:
        rows = db.execute(query, params, fetch=True)
    except Exception:
        # Lateral/snapshot query can fail mid-rollout; fall back cleanly.
        rows = db.execute(DECAY_QUERY_LEGACY, params, fetch=True)
        exists, snap_count = False, 0
    return build_decay_map(
        rows,
        item_limit=item_limit,
        history_available=exists and snap_count > 0,
    )

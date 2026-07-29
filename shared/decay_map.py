"""Build the Phase 1 Decay Map from the current WaniKani snapshot.

This is a diagnostic, not a claim about historical SRS movement.  The Phase 0
schema stores the current assignment only, so the signal combines review
accuracy, SRS stage, and whether the item is currently available.
"""

from datetime import datetime, timezone


DECAY_QUERY = """
select
    s.id, s.level, s.object_type, s.characters, s.primary_meaning,
    r.meaning_correct, r.meaning_incorrect,
    r.reading_correct, r.reading_incorrect,
    a.srs_stage, a.available_at, a.burned_at
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
     available_at, burned_at) = row
    now = now or datetime.now(timezone.utc)
    correct = _num(meaning_correct) + _num(reading_correct)
    incorrect = _num(meaning_incorrect) + _num(reading_incorrect)
    attempts = correct + incorrect
    accuracy = round(correct / attempts * 100, 1) if attempts else None
    stage = _num(srs_stage)
    due = bool(available_at and available_at <= now and not burned_at)

    # Accuracy is the strongest signal. Low SRS stages amplify the signal,
    # while burned items are excluded by the query in the public report.
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
        "decay_score": score,
        "band": band,
    }


def build_decay_map(rows, now=None, item_limit=100):
    items = [classify_item(row, now=now) for row in rows]
    items.sort(key=lambda item: (-item["decay_score"], item["level"], item["characters"] or ""))

    levels = {}
    for item in items:
        summary = levels.setdefault(item["level"], {
            "level": item["level"], "items": 0, "high": 0, "medium": 0,
            "low": 0, "due": 0, "accuracy_total": 0, "accuracy_count": 0,
        })
        summary["items"] += 1
        summary[item["band"]] += 1
        summary["due"] += int(item["due"])
        if item["accuracy"] is not None:
            summary["accuracy_total"] += item["accuracy"]
            summary["accuracy_count"] += 1

    for summary in levels.values():
        count = summary.pop("accuracy_count")
        total = summary.pop("accuracy_total")
        summary["accuracy"] = round(total / count, 1) if count else None
        summary["risk"] = round((summary["high"] * 100 + summary["medium"] * 45) / summary["items"]) if summary["items"] else 0

    level_list = sorted(levels.values(), key=lambda level: (-level["risk"], level["level"]))
    suggested = [level["level"] for level in level_list if level["high"]][:5]
    return {
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "signal": "accuracy + current SRS stage + currently due",
        "limitations": [
            "SRS history is not stored yet, so this cannot prove when an item decayed.",
            "The map reflects the latest successful sync snapshot.",
        ],
        "summary": {
            "items": len(items),
            "high_risk": sum(item["band"] == "high" for item in items),
            "medium_risk": sum(item["band"] == "medium" for item in items),
            "due": sum(item["due"] for item in items),
            "suggested_levels": suggested,
        },
        "levels": level_list,
        "items": items[:item_limit],
    }


def fetch_decay_map(db, min_level=None, max_level=None, item_limit=100):
    params = [min_level, min_level, max_level, max_level]
    rows = db.execute(DECAY_QUERY, params, fetch=True)
    return build_decay_map(rows, item_limit=item_limit)

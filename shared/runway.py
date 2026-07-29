"""Phase 3 Runway — backlog burn-down and recovery-date estimate.

The data spine stores one snapshot per subject (wk_assignments + wk_review_stats
+ wk_subjects). Runway turns that snapshot into a forward-looking plan: given a
target reviews/day and a flag for new lessons, how many days until the queue
sits at a healthy floor, and what date is that?

It is intentionally a heuristic on top of the current snapshot. We do not
have historical SRS movement, so all "future" rates are derived from:

  - Apprentice bucket sizes (SRS stages 1-4) and average review intervals.
  - Review accuracy (wk_review_stats.percentage_correct + raw counts).
  - Subject level mix, used to estimate new-lesson cost if enabled.

The output is structured: a single `plan` block + a `confidence` band + an
`assumptions` list + a `warnings` list. The endpoint just wraps the
`build_runway_plan()` function with a Neon fetch.
"""

from datetime import datetime, timedelta, timezone


# Approximate SRS review intervals (hours) for stages 1-5 (Apprentice + Guru 1).
# These are WaniKani defaults; we use them to convert current stage distribution
# into a daily review load.
SRS_INTERVAL_HOURS = {
    1: 4,
    2: 8,
    3: 23,    # ~1 day
    4: 47,    # ~2 days
    5: 167,   # ~7 days (Guru 1)
}


# A "backlog" item is anything available now or within the next 24h. Once an
# item graduates past Apprentice 4 (stage 5+) it leaves the daily-grind pool
# and lives in the multi-day rotation.
APPRENTICE_STAGES = (1, 2, 3, 4)
HEALTHY_QUEUE_FLOOR = 50   # reviews/day at which we consider the queue calm
MIN_REVIEWS_PER_DAY = 25  # floor on user-supplied daily target


RUNWAY_QUERY = """
select
    a.subject_id,
    a.srs_stage,
    a.available_at,
    a.burned_at,
    s.level,
    s.object_type,
    r.percentage_correct,
    r.meaning_correct + r.reading_correct as correct_total,
    r.meaning_incorrect + r.reading_incorrect as incorrect_total
from wk_assignments a
left join wk_subjects   s on s.id = a.subject_id
left join wk_review_stats r on r.subject_id = a.subject_id
"""


def _num(value, default=0):
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _float(value, default=None):
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _accuracy(row):
    """Return a per-row accuracy (0-100) or None if no reviews yet."""
    pct = _float(row[6])
    correct = _num(row[7])
    incorrect = _num(row[8])
    if correct + incorrect == 0:
        return pct
    return round(correct / (correct + incorrect) * 100, 1)


def _is_due(row, now):
    """An item is 'in the current 24h backlog' if it's apprentice, not burned,
    and either available now or within the next 24h."""
    stage = _num(row[1])
    available_at = row[2]
    burned_at = row[3]
    if burned_at is not None or stage not in APPRENTICE_STAGES:
        return False
    if available_at is None:
        return True  # never been reviewed; counts toward the new pile
    if isinstance(available_at, str):
        # Neon returns timestamptz as datetime; we accept both.
        try:
            available_at = datetime.fromisoformat(available_at.replace("Z", "+00:00"))
        except ValueError:
            return False
    return available_at <= now + timedelta(hours=24)


def _apprentice_breakdown(rows):
    """Count items per apprentice stage (1-4)."""
    counts = {stage: 0 for stage in APPRENTICE_STAGES}
    for row in rows:
        if row[4] is None:  # subject missing (deleted on WK side)
            continue
        if _num(row[1]) in counts and row[3] is None:  # not burned
            counts[_num(row[1])] += 1
    return counts


def _estimate_daily_review_load(rows, now):
    """Approximate today's review load from current Apprentice distribution.

    Each Apprentice stage has a known ~interval. Items in stage N contribute
    roughly 24h / interval_hours reviews/day, amortized. The result is a
    float — we round up at the end.
    """
    breakdown = _apprentice_breakdown(rows)
    load = 0.0
    for stage, count in breakdown.items():
        interval = SRS_INTERVAL_HOURS.get(stage, 24)
        load += count * (24.0 / interval)
    # Anything currently due in the next 24h that's not yet in the breakdown
    # (e.g. stage-1 items that already have an available_at set) gets counted
    # via the backlog directly. Return load as the steady-state rotation.
    return load, breakdown


def _estimate_new_lesson_cost(include_new_lessons, rows):
    """A new lesson costs ~1 review in stage 1 right away, then another in
    ~4h (stage 1 -> 2), then ~8h, then ~23h. So a new lesson commits ~4
    reviews across the next ~36h. We surface that as a daily cost, gated by
    whether the user wants new lessons in the plan."""
    if not include_new_lessons:
        return 0.0
    # Lightweight proxy: lesson_cost = 1.5 reviews/day per new lesson.
    # We don't know the planned lesson volume from the snapshot, so we
    # assume a default of 5 new lessons/day (WK's recommended pace for
    # users at the 5-levels-in-10-days cadence). The caller can override
    # the projected new lessons in a future revision.
    return 5 * 1.5  # 7.5 reviews/day


def _confidence_band(sample_size, accuracy_rows):
    if sample_size < 20:
        return "low", "snapshot has very few assignments — projection is loose"
    if sample_size < 100 or accuracy_rows < 30:
        return "medium", "snapshot is mid-sized — projection has real uncertainty"
    return "high", "snapshot is large enough to project with some confidence"


def _warnings(rows, now, daily_reviews):
    """Surface conditions the user should know about before trusting the plan."""
    warnings = []
    if not rows:
        return ["no assignments in snapshot — run /api/sync first"]

    # Stale snapshot detection: if the newest synced_at is far in the past,
    # the plan is built on stale data. We don't pull synced_at in the
    # lightweight query, so we skip that here and let the caller (api/runway.py)
    # add a sync-freshness warning.

    burned = sum(1 for row in rows if row[3] is not None)
    if burned == 0:
        warnings.append("no burned items yet — backlog math is for in-progress levels only")

    # If the user asks for less than the healthy floor, warn.
    if daily_reviews < HEALTHY_QUEUE_FLOOR:
        warnings.append(
            f"daily target {daily_reviews} is below the healthy floor of "
            f"{HEALTHY_QUEUE_FLOOR} — projections assume you actually hit it"
        )
    return warnings


def build_runway_plan(rows, daily_reviews=100, include_new_lessons=False, now=None):
    """Pure function. Given a list of assignment rows (as returned by Neon),
    build the runway plan dict. Easy to unit-test."""
    now = now or datetime.now(timezone.utc)
    daily_reviews = max(MIN_REVIEWS_PER_DAY, int(daily_reviews or 0))

    # 1. Current 24h backlog.
    backlog_items = [row for row in rows if _is_due(row, now)]
    current_backlog = len(backlog_items)

    # 2. Steady-state daily load from the Apprentice distribution.
    daily_load, breakdown = _estimate_daily_review_load(rows, now)

    # 3. Optional new-lesson cost.
    new_lesson_cost = _estimate_new_lesson_cost(include_new_lessons, rows)

    # 4. Effective daily target = user target + new-lesson cost, then
    # clamped to the absolute floor. The new-lesson cost is added on top
    # of the user target so flipping `include_new_lessons` always nudges
    # the recommendation up, not the floor.
    user_target = max(MIN_REVIEWS_PER_DAY, int(daily_reviews or 0))
    recommended_daily = max(
        MIN_REVIEWS_PER_DAY,
        user_target + int(round(new_lesson_cost)),
    )

    # 5. Burn-down: if the user reviews at `recommended_daily` per day and
    # the steady-state load stays flat, the *backlog* above that load clears
    # in (current_backlog - healthy_floor) / (recommended_daily - daily_load)
    # days. If recommended_daily <= daily_load + new_lesson_cost, the backlog
    # will not shrink. (Lesson cost is added separately because it represents
    # *new* work, not existing backlog — recommended_daily already includes it.)
    if recommended_daily <= daily_load + int(round(new_lesson_cost)):
        projected_days = None
        projected_date = None
        burn_status = "stalled"
    else:
        surplus = recommended_daily - daily_load - int(round(new_lesson_cost))
        target_backlog = HEALTHY_QUEUE_FLOOR
        excess = max(0, current_backlog - target_backlog)
        projected_days = max(0, int(round(excess / surplus))) if surplus > 0 else 0
        projected_date = (now + timedelta(days=projected_days)).date().isoformat()
        burn_status = "recovering" if projected_days > 0 else "already_healthy"

    # 6. Confidence + warnings.
    accuracy_rows = sum(
        1 for row in rows if (_num(row[7]) + _num(row[8])) > 0
    )
    confidence, confidence_note = _confidence_band(len(rows), accuracy_rows)
    warnings = _warnings(rows, now, daily_reviews)

    return {
        "generated_at": now.isoformat(),
        "current_backlog": current_backlog,
        "healthy_floor": HEALTHY_QUEUE_FLOOR,
        "daily_load": round(daily_load, 1),
        "new_lesson_cost": round(new_lesson_cost, 1),
        "recommended_daily": recommended_daily,
        "projected_days_to_healthy": projected_days,
        "projected_recovery_date": projected_date,
        "burn_status": burn_status,
        "apprentice_breakdown": breakdown,
        "include_new_lessons": bool(include_new_lessons),
        "confidence": confidence,
        "assumptions": [
            "snapshot is from the last successful /api/sync (call sync if backlog looks wrong)",
            "SRS intervals follow WaniKani defaults (4h / 8h / 23h / 47h / 7d)",
            f"healthy floor = {HEALTHY_QUEUE_FLOOR} reviews/day as a calm-queue target",
            "new lessons (when enabled) cost ~1.5 reviews/day each at 5 lessons/day",
            "daily_load is the steady-state rotation, not a one-time spike",
        ],
        "warnings": warnings,
        "confidence_note": confidence_note,
    }


def fetch_runway_plan(db, daily_reviews=100, include_new_lessons=False, now=None):
    """DB-backed entry point. Mirrors shared/decay_map.fetch_decay_map."""
    rows = db.execute(RUNWAY_QUERY, fetch=True)
    return build_runway_plan(
        rows,
        daily_reviews=daily_reviews,
        include_new_lessons=include_new_lessons,
        now=now,
    )

# Kani Sensei Platform — Phase 3: Runway

Phase 3 adds a forward-looking burn-down estimate on top of the Phase 0
data spine. The Decay Map (Phase 1) tells you what rotted. Runway tells
you when the queue settles if you hold a steady pace.

## What shipped

| File | Purpose |
|------|---------|
| `shared/runway.py` | Reusable module: `build_runway_plan(rows, ...)` is pure, `fetch_runway_plan(db, ...)` hits Neon. |
| `api/runway.py` | `GET /api/runway` — `X-Cron-Secret`-protected handler, mirrors `api/decay.py`. |
| `test_runway.py` | 18 focused unit tests (unittest, no DB / no network). |
| `vercel.json` | New route `GET /api/runway` → `api/runway.py`. |
| `PHASE3.md` | This file. |

**Untouched:** `api/tick.py`, `api/telegram_webhook.py`, `shared/decay_map.py`,
`api/decay.py`, `migrations/000_data_spine.sql`. Schema is unchanged.

## What Runway returns

`build_runway_plan()` returns a single dict. Endpoint just wraps it with a
Neon fetch and a query-param parser.

| Field | Meaning |
|-------|---------|
| `current_backlog` | Apprentice items due in the next 24h. |
| `healthy_floor` | Constant — `50` reviews/day, the "calm queue" target. |
| `daily_load` | Steady-state reviews/day implied by the current Apprentice distribution (4h / 8h / 23h / 47h / 7d SRS defaults). |
| `new_lesson_cost` | 7.5 reviews/day when `include_new_lessons=true`, 0 otherwise. |
| `recommended_daily` | `max(min_floor, user_target + new_lesson_cost)`. The plan's daily review target. |
| `projected_days_to_healthy` | Days until backlog ≤ `healthy_floor`, or `null` if stalled. |
| `projected_recovery_date` | ISO date for the projection, or `null` if stalled. |
| `burn_status` | `recovering` \| `already_healthy` \| `stalled`. |
| `apprentice_breakdown` | `{1: n, 2: n, 3: n, 4: n}` — current Apprentice stage distribution. |
| `confidence` | `low` (<20 items) / `medium` / `high` (≥100 items + ≥30 with accuracy). |
| `confidence_note` | One-sentence explanation. |
| `assumptions` | Strings — the heuristic preconditions baked into the projection. |
| `warnings` | Strings — surface conditions that should reduce your trust. |

## Query params

| Param | Default | Notes |
|-------|---------|-------|
| `daily_reviews` | `100` | Clamped to `MIN_REVIEWS_PER_DAY = 25`. |
| `include_new_lessons` | `false` | `1` / `true` / `yes` / `on` enable it. Adds ~7.5 reviews/day to the recommended target. |

## Usage

```bash
# Default plan
curl "https://kani-sensei.vercel.app/api/runway" \
  -H "X-Cron-Secret: $CRON_SECRET"

# Custom target + new lessons
curl "https://kani-sensei.vercel.app/api/runway?daily_reviews=150&include_new_lessons=true" \
  -H "X-Cron-Secret: $CRON_SECRET"
```

## Honest limits

- **Snapshot-only.** Runway does not have SRS history, so it cannot model
  acceleration or decay. It assumes the current Apprentice distribution is
  the steady state.
- **Stale snapshots.** If `/api/sync` hasn't run recently, the plan is
  stale. The endpoint does not check `sync_runs.finished_at` — wire that
  check into a caller if you need freshness guarantees.
- **Lesson volume is a constant.** `include_new_lessons` assumes 5
  lessons/day. If you want a custom lesson target, that's a future param.
- **Stall semantics.** If `recommended_daily ≤ daily_load + new_lesson_cost`,
  the plan reports `burn_status = "stalled"` and `null` days/date — i.e. you
  cannot outrun the queue at this pace. The recommended target still tells
  you what you'd need.

## Why the math is structured this way

The whole point of the plan is to be **explainable**. Every input the math
uses is in the response, every output has a documented meaning, and the
assumptions list tells the user exactly which knobs are baked in. The next
phase (Warm-Up Quiz) will read this plan to decide what to quiz on, so the
shape is deliberately stable.

## Next: Phase 4 (not scoped)

Warm-Up Quiz + Nudge Bot. Quiz reads the Runway plan + Decay Map to
generate a daily review/lesson sequence; Nudge Bot feeds off the same
plan to time the Telegram nudges.

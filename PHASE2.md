# Kani Sensei Platform — Phase 2: Warm-Up Quiz + web shell

Phase 2 turns the API-only platform into something you can actually open.
Warm-Up Quiz is the re-entry tool; the web UI also surfaces Decay Map and
Runway so the pile feels navigable instead of hostile.

## What shipped

| File | Purpose |
|------|---------|
| `migrations/001_quiz_and_snapshots.sql` | Quiz session tables + daily `wk_assignment_snapshots`. |
| `shared/quiz.py` | Decay-weighted MC generation, distractors, grading. |
| `api/quiz.py` | `POST/GET /api/quiz` — start session + grade answers. |
| `shared/auth.py` + `api/login.py` / `me.py` / `logout.py` | Cookie session for the SPA (cron secret still works). |
| `api/overview.py` | One-call dashboard payload (decay + runway + last sync). |
| `shared/decay_map.py` | Regression boost when prior snapshot stage > current. |
| `api/sync.py` | Writes today's assignment snapshot after each sync. |
| `web/` | Vite + React UI (Fraunces / Zen Kaku, seafoam ink). |
| `test_quiz.py` | Quiz weighting, distractors, auth token, regression. |

**Untouched on purpose:** `api/tick.py`, `api/telegram_webhook.py`.

## Warm-Up Quiz mechanics

1. Pick `min_level` / `max_level` / `count` / modes (`meaning`, `reading`).
2. Pool is non-burned kanji + vocabulary in range, scored by Decay Map.
3. Items are sampled **without replacement** with weight `(decay_score + 1)^1.6`.
4. Each question is 4-choice MC. Distractors prefer same type + nearby levels.
5. Correct answers stay on the server until you submit.

```bash
curl -X POST "https://kani-sensei.vercel.app/api/quiz" \
  -H "Content-Type: application/json" \
  -H "X-Cron-Secret: $CRON_SECRET" \
  -d '{"min_level":14,"max_level":18,"count":10,"modes":["meaning","reading"]}'
```

Grade:

```bash
curl -X POST "https://kani-sensei.vercel.app/api/quiz?action=answer" \
  -H "Content-Type: application/json" \
  -H "X-Cron-Secret: $CRON_SECRET" \
  -d '{"session_id":"...","question_id":"...","choice_index":2}'
```

## Auth for humans

The SPA posts the site password to `/api/login` (uses `SITE_PASSWORD` if set,
otherwise `CRON_SECRET`) and keeps an HttpOnly cookie. Cron jobs are unchanged
and still send `X-Cron-Secret`.

## Decay history (why snapshots now)

Decay Map previously inferred rot from current accuracy + stage only. Sync now
freezes SRS + accuracy into `wk_assignment_snapshots` once per day. When an
item’s stage drops versus the prior snap, Decay Map adds a regression boost —
and the quiz inherits that weighting automatically.

Bootstrap note: the first migration also seeded yesterday + today from the
live snapshot so history exists immediately without inventing fake regressions.

## Web UI

`web/` is the Vite + React source. Production static assets are built into
`public/` (`cd web && npm run build`) so Vercel can keep serving the existing
Python serverless functions without a mixed Node/Python install step.

## Honest limits

- Until stages actually move between sync days, regression counts stay near zero.
- Distractors are same-type neighbors, not WK’s own confusion set.
- Single-user password gate is enough for Kibz; not a multi-user auth model.

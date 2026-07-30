# Kani Sensei — Handoff to Cursor

**Owner:** Kibz · **Was:** Alfred + Nova (backend/API phases) · **Now:** Cursor owns development going forward.
Alfred/Nova are shifting focus to the trading platform. Cursor drives Kani Sensei from here — backend, frontend, and product calls within the scope below.

**Repo:** `anoaman/kani-sensei` · Local clone: `projects/kani-sensei/` · Live: `https://kani-sensei.vercel.app`
**Stack:** Python serverless on Vercel (stdlib-only, no frameworks — see "Code style" below), Neon Postgres, Telegram bot for delivery.

---

## What this project is

A single-user (Kibz) WaniKani companion. It started as a nudge bot and is becoming a small platform because the real problem for a returning WaniKani user isn't "clear your reviews" — it's re-entry after a long break: 800+ reviews piled up, no idea what's actually rotted vs. still solid, and the size of the pile makes people bounce instead of start. Every module exists to make that re-entry survivable and to surface intel WaniKani's own UI hides.

## The four-module vision

1. **Nudge Bot** (shipped, live, do not touch its logic) — pings Telegram in fixed WIB windows (06:00–09:00, 12:00–14:00) while reviews are due, re-pinging every 30 min.
2. **Decay Map** (shipped, API only) — diagnostic of what decayed while away: current SRS stage + lifetime accuracy per item, risk-ranked by level. This is the flagship feature — it turns a vague scary pile into "level 8 is fine, level 12-15 rotted, start there."
3. **Runway** (shipped, API only) — pacing projection: given a daily review target, when does the backlog burn down to a healthy floor. Includes confidence scoring and stall detection.
4. **Warm-Up Quiz** (not started — **this is Cursor's next build**) — user picks a level range, gets multiple-choice drills (meaning + reading), weighted by Decay Map so it prioritizes items the user is statistically about to fail. This is the tool that gets someone comfortable again before they touch the real review queue.

Phase-2-ish stretch ideas (not committed, your call whether/when): Ghost Reviews (drill burned items WK never resurfaces, so they don't silently rot forever), Kanji Web (visual graph of kanji→vocab unlock dependencies).

## What's built and live right now

| Phase | Status | Files |
|---|---|---|
| P0 — Data spine | Live | `shared/wanikani_client.py`, `shared/neon.py`, `api/sync.py`, `migrations/000_data_spine.sql` |
| P1 — Decay Map | Live (API only, no UI) | `shared/decay_map.py`, `api/decay.py`, `test_decay_map.py` |
| P3 — Runway | Live (API only, no UI) | `shared/runway.py`, `api/runway.py`, `test_runway.py`, `PHASE3.md` |
| P2 — Warm-Up Quiz | **Not started** | — |
| Nudge Bot | Live, unrelated to platform, do not refactor into it | `api/tick.py`, `api/telegram_webhook.py` |

Database: **Neon Postgres** (not Supabase, not Turso — both were tried and superseded; Neon won because the schema is relational and Decay Map / Runway queries fit Postgres better). `DATABASE_URL` is set in Vercel (Production/Preview/Dev) and in `.env.local` (must be quoted — the connection string contains `&`).

`GET /api/decay` and `GET /api/runway` are currently gated by the same `X-Cron-Secret` header the sync job uses. That's a placeholder, not a real auth model — see "What Cursor should decide" below.

## Data model (already live, in `migrations/000_data_spine.sql`)

- `wk_subjects` — cached WK catalog (kanji/vocab/radical), refreshed daily by sync
- `wk_review_stats` — lifetime per-subject accuracy (meaning/reading correct+incorrect)
- `wk_assignments` — current SRS state per subject (stage, unlock/start/pass/burn timestamps)
- `sync_runs` — audit trail of each daily sync

**Known limitation, called out honestly in the Decay Map/Runway responses themselves:** we only store *current* state, not historical SRS movement. "Decay" today is inferred from current accuracy + stage, not from watching an item actually regress over time. If Cursor wants a real decay signal, that means snapshotting `wk_assignments`/`wk_review_stats` over time instead of upserting-in-place — worth considering before or alongside the quiz build, since the quiz weighting depends on decay quality.

## Code style — please match it

Everything so far is deliberately dependency-light: `http.server.BaseHTTPRequestHandler` per Vercel function, stdlib `urllib` for HTTP calls, no Flask/FastAPI, no ORM. `requirements.txt` currently only has `psycopg[binary]` for Postgres. This was a conscious choice to keep cold starts fast on Vercel's Python runtime for a single-user app with light traffic.

**This is a preference, not a hard constraint on your ownership.** If the quiz/UI genuinely needs a real framework (e.g., you want a proper frontend build pipeline, not just server-rendered HTML), that's your call to make — just don't casually reach for heavy backend deps out of habit when the existing pattern already works fine.

## What Cursor should decide (explicitly not prescribed)

- **The web UI, full stop.** No frontend exists yet for Decay Map or Runway — they're JSON APIs behind a secret header. Design and build the actual UI however you think best serves the product: framework choice, visual direction, information architecture, whether it's server-rendered or a SPA, whether it lives on the same Vercel project or a separate one. **Full creative freedom here — this is explicitly delegated, not something to check back on for approval before building.**
- **Real auth**, replacing the `X-Cron-Secret` placeholder once there's a UI a human is meant to open directly (single-user is fine, but a shared secret in a URL header isn't a login).
- **Warm-Up Quiz mechanics** — question format, distractor generation strategy, session/scoring persistence (needs a new table or two), how tightly it should couple to Decay Map's risk ranking.
- Whether/when to build the decay-history-snapshot improvement mentioned above.
- The Ghost Reviews / Kanji Web stretch ideas — build, drop, or reshape as you see fit.

## What NOT to touch without a good reason

- `api/tick.py` / `api/telegram_webhook.py` — the nudge bot works, is live, and isn't part of this rebuild's scope. If it gets folded into the platform later, that's a deliberate call, not incidental refactor collateral.
- The Neon schema's existing tables — extend, don't restructure, unless the historical-snapshot work above requires it.

## Environment / access

- `WANIKANI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `CRON_SECRET`, `DATABASE_URL` — all already set in Vercel and `.env.local`. Do not commit `.env.local` (already gitignored) and never paste secrets into commit messages or PRs.
- Daily sync (`/api/sync`) should be on a cron-job.org schedule hitting it once a day before the morning nudge window — confirm this is actually scheduled; it was pending as of the last checkpoint and may still be manual-only.

## Where to look first

- `PHASE0.md`, `PHASE3.md` — the two existing phase docs, written in this same style, worth matching if you write more.
- `memory/project_kani-sensei.md` in the main workspace (not this repo) has the full build history and decision log if you want the "why" behind any of the above in more depth.

Ping Alfred if something here turns out to be stale by the time you pick it up — the backend moved fast across a few sessions and the docs should be accurate as of this handoff, but confirm live behavior over docs if they ever conflict.

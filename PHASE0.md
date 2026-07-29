# Kani Sensei Platform — Phase 0: Data Spine

Phase 0 builds only the shared data spine. No user-facing features yet. It gives
the four modules (Decay Map, Warm-Up Quiz, Runway, Nudge Bot) one Turso-backed
snapshot of your WaniKani state, refreshed daily.

## What shipped

| File | Purpose |
|------|---------|
| `shared/wanikani_client.py` | Reusable WK client: paginated `/subjects`, `/review_statistics`, `/assignments`, `/user`. Handles 429 backoff + retries. Pure stdlib. |
| `shared/turso.py` | Minimal Turso/libSQL client over the HTTP pipeline (`/v2/pipeline`). `execute` / `batch` / `executemany`. Pure stdlib — no native libsql dep. |
| `migrations/000_data_spine.sql` | SQLite/libSQL schema: `wk_subjects`, `wk_review_stats`, `wk_assignments`, `sync_runs`. Idempotent upserts on primary key. |
| `api/sync.py` | Daily sync job. `X-Cron-Secret`-protected. Pulls WK → upserts Turso → writes a `sync_runs` audit row. |
| `requirements.txt` | Unchanged (still stdlib). Turso writes use the libSQL HTTP pipeline over urllib — no libsql client. |

**Untouched:** `api/tick.py`, `api/telegram_webhook.py`. The Nudge Bot keeps working.

## Why Turso (not Supabase)

Moved off Supabase per Kibz. Turso (libSQL) is SQLite-compatible, serverless-native,
and talked to here purely over its HTTP pipeline — zero native dependencies, so
cold starts stay light and it matches the stdlib nudge bot exactly.

## Env vars to set (Vercel + `.env.local`)

Already present:
- `WANIKANI_API_KEY`
- `CRON_SECRET`

New for Phase 0:
- `TURSO_DATABASE_URL` — e.g. `libsql://kani-sensei-<org>.turso.io` (the client also
  accepts the `https://…` form)
- `TURSO_AUTH_TOKEN` — DB auth token from `turso db tokens create <db>`

## Setup

1. **Create the Turso DB** (free tier):
   ```bash
   turso db create kani-sensei
   turso db show kani-sensei --url          # -> TURSO_DATABASE_URL
   turso db tokens create kani-sensei       # -> TURSO_AUTH_TOKEN
   ```
2. **Apply the migration:**
   ```bash
   turso db shell kani-sensei < migrations/000_data_spine.sql
   ```
3. **Set env vars** in Vercel (Production) and locally in `.env.local`.
4. **Run a sync:**
   ```bash
   curl -X POST https://kani-sensei.vercel.app/api/sync \
     -H "X-Cron-Secret: $CRON_SECRET"
   ```
   Expect `{"status":"ok","counts":{"subjects":N,"review_stats":N,"assignments":N}}`.
5. **Schedule it** on cron-job.org: `POST /api/sync` with the `X-Cron-Secret` header,
   once daily (e.g. 05:00 WIB, before the morning nudge window).

## Idempotency

Re-running `/api/sync` is safe — every table upserts on its primary key, so a
second run refreshes the same rows instead of duplicating. Each run appends one
`sync_runs` row so you can audit history and catch failures. Subjects are fetched
only up to your current WK level to keep each sync well under the function timeout.

## Next: Phase 1

With the spine live, Phase 1 builds the **Decay Map** — read `wk_review_stats` +
`wk_assignments` to surface exactly what rotted while you were away, sorted by level.

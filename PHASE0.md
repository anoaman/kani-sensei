# Kani Sensei Platform — Phase 0: Data Spine

Phase 0 builds only the shared data spine. No user-facing features yet. It gives
the four modules (Decay Map, Warm-Up Quiz, Runway, Nudge Bot) one Neon-backed
snapshot of your WaniKani state, refreshed daily.

## What shipped

| File | Purpose |
|------|---------|
| `shared/wanikani_client.py` | Reusable WK client: paginated `/subjects`, `/review_statistics`, `/assignments`, `/user`. Handles 429 backoff + retries. Pure stdlib. |
| `shared/neon.py` | Minimal Neon/Postgres client using `psycopg`. Disables prepared statements for Neon pooled connections. |
| `migrations/000_data_spine.sql` | Postgres schema: `wk_subjects`, `wk_review_stats`, `wk_assignments`, `sync_runs`. Idempotent upserts on primary key. |
| `api/sync.py` | Daily sync job. `X-Cron-Secret`-protected. Pulls WK → upserts Neon → writes a `sync_runs` audit row. |
| `requirements.txt` | Adds `psycopg[binary]` for Postgres connectivity on Vercel. |

**Untouched:** `api/tick.py`, `api/telegram_webhook.py`. The Nudge Bot keeps working.

## Why Neon (not Supabase/Firebase)

Moved off Supabase per Kibz. Neon keeps the data relational, which fits subjects,
assignments, review stats, sync audit rows, and the Decay Map queries much better
than Firebase/Firestore. It also stays serverless-friendly on Vercel.

## Env vars to set (Vercel + `.env.local`)

Already present:
- `WANIKANI_API_KEY`
- `CRON_SECRET`

New for Phase 0:
- `DATABASE_URL` — Neon pooled connection string (`-pooler` host), with SSL required
  - In `.env.local`, wrap it in quotes because the URL contains `&`:
    `DATABASE_URL='postgresql://...sslmode=require&channel_binding=require'`

## Setup

1. **Create the Neon DB** (free tier), project name `kani-sensei`, region Singapore/ap-southeast-1 if available.
2. **Apply the migration:**
   ```bash
   psql "$DATABASE_URL" -f migrations/000_data_spine.sql
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

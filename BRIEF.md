# Project Brief: Kani Sensei — WaniKani Nudge Bot + Sentence Miner

**Owner:** Kibz · **Orchestrator:** Alfred · **Builder:** Nova
**Status:** v1 APPROVED TO BUILD (nudge). v1.1 scaffolded, not activated (miner).
**Standalone project. No shared code or infra with other projects.**
**Name:** "Kani Sensei" is a placeholder Kibz may rename later. Bot handle: @kani_sensei_telegram_bot.

---

## What it is

A single-user Telegram bot that (1) nudges Kibz to clear WaniKani reviews at fixed WIB slots with re-pings until touched, and (2) later delivers daily AI-generated reading sentences calibrated to his current WaniKani vocab.

## Architecture

- **Host:** Vercel serverless (Python/Flask or plain handler — Nova's call, keep it boring)
- **Scheduler:** cron-job.org hits `POST /api/tick` every 30 minutes. Vercel Hobby cron is daily-only, hence external. Endpoint protected by `CRON_SECRET` header check.
- **State:** none. Every tick reads live data from WaniKani API and decides from current WIB time + review count. No DB.
- **Timezone:** all logic in WIB (UTC+7). Compute from UTC at request time — do not trust server locale.

## Tick logic (v1)

On each tick, derive WIB time `t`:

1. **Morning window 06:00–09:00:** fetch reviews due (WK `/v2/assignments?immediately_available_for_review=true`). If count > 0 → send nudge. Naturally re-pings every 30 min until queue touched/cleared or window ends.
2. **Lunch window 12:00–14:00:** same logic.
3. **Outside windows:** no-op, return 200.

**Nudge payload:**
```
06:00 WIB — 84 reviews due
Apprentice: 97 · Yesterday's accuracy: 76%
Verdict: queue's on fire. Clear before the gym.
[Open reviews] → https://www.wanikani.com/subjects/review
```
- Reviews due: `/v2/assignments` (immediately available)
- Apprentice count: `/v2/assignments?srs_stages=1,2,3,4` (count)
- Accuracy: `/v2/review_statistics` or summary endpoint — Nova to pick the cheapest call
- Verdict line: simple threshold rules, no AI call needed (e.g. apprentice >150 = "circuit breaker: pause lessons", reviews >150 = "queue's on fire", else "clear to lift")
- Respect WK rate limits (60 req/min — trivial at this volume). Cache-free is fine.

### Accuracy line — fallback permitted (Alfred addition)

"Yesterday's accuracy" is the one squishy data point. WK `/v2/review_statistics` is lifetime per-subject, not daily; the raw `/v2/reviews` collection is deprecated/at-risk. Attempt a stateless daily accuracy if a cheap route exists. If it's awkward or unreliable, **fall back without asking**: drop the line, or substitute "Lessons available: N · Level: X". Do not let this stat block v1.

### Fail loud (Alfred addition)

If the Telegram send (or WK fetch) errors, the tick must NOT swallow it and return 200. Return 5xx and log the error clearly to Vercel logs, so a silent morning is distinguishable from a broken bot.

## Sentence miner (v1.1 — scaffold only, do not schedule)

- **Slot:** fires once in the 08:00–08:30 tick window (WIB), behind env flag `MINER_ENABLED=false` for now.
- **Flow:** fetch burned/guru'd vocab sample from WK API (`/v2/assignments?srs_stages=5,6,7,8,9` + subject lookup) → prompt Claude Haiku: "3 natural Japanese sentences at i+1 difficulty using primarily these words, JSON out" → format for Telegram.
- **Format:** sentence in Japanese, translation wrapped in Telegram spoiler (`||text||` MarkdownV2) so Kibz attempts before revealing.
- **Model:** claude-haiku-4-5 (cheapest current haiku on the API). Parse JSON defensively.

## Env vars (Vercel)

| Var | Purpose |
|---|---|
| `WANIKANI_API_KEY` | read-only personal access token |
| `TELEGRAM_BOT_TOKEN` | from @BotFather |
| `TELEGRAM_CHAT_ID` | Kibz's chat ID |
| `ANTHROPIC_API_KEY` | miner only (v1.1) — leave unset for v1 |
| `CRON_SECRET` | shared secret; reject ticks without it |
| `MINER_ENABLED` | "false" until Kibz activates |

**Read all env vars at request time inside handlers, never at module load** (known Vercel/serverless gotcha).

**Actual credential values:** `projects/kani-sensei/.env.local` (gitignored — never commit, never echo into Discord/logs). Chat ID confirmed live via getUpdates 2026-07-08.

**Post-deploy rotation (Kibz task, not Nova's):** both tokens have transited Discord; after Vercel env is set and working, Kibz regenerates the bot token via BotFather and the WK key in WaniKani settings, then updates Vercel env.

## Endpoints

- `POST /api/tick` — the only scheduled entry point
- `POST /api/telegram-webhook` — optional v1 nicety: respond to `/status` command with current queue snapshot. Skip if it adds friction.

## Versioned scope

- **v1:** tick endpoint, both nudge windows, re-ping logic, verdict rules, deploy + cron-job.org setup doc
- **v1.1:** miner scaffold wired but flag-off; activation = flipping one env var
- **Later (not scoped):** accuracy trend chart, streak tracking, weekly P&L summary

## Definition of done (v1)

- Local test: simulated tick at each window boundary behaves correctly (06:00 fires, 05:59 doesn't, cleared queue = silence)
- Deployed to Vercel, cron-job.org firing, one full real morning cycle observed
- README with setup doc (credentials are already in hand; README covers rotation + cron-job.org config)
- Errors surface as 5xx + Vercel log lines, not silent 200s

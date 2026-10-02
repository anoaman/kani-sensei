# Kani Sensei

A focused WaniKani recovery companion. Kani Sensei turns a large review pile
into one short recommended session, while still allowing deliberate practice by
level and subject type.

The product has three user-facing areas:

- **Today** — one decay-weighted daily prescription and a direct path to WaniKani.
- **Practice** — choose a single level or range, Kanji/Vocabulary/Radicals/Mixed,
  and a 10–40 question session.
- **Progress** — recovery summary and the levels under the most pressure.

Ghosts, leeches, due items, and prior misses remain part of the drill engine,
but are no longer separate destinations competing for attention.

## Endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/` | GET | cookie after login | Today — recommended recovery session |
| `/practice` | GET | cookie | Focused-session builder |
| `/session` | GET | cookie | Unified typed-recall session |
| `/progress` | GET | cookie | Recovery summary and level pressure |
| Legacy practice URLs | GET | cookie | Redirect into the simplified Practice experience |
| `/api/login` | POST | site password body | Issue session cookie |
| `/api/logout` | POST | — | Clear session cookie |
| `/api/me` | GET | cookie / secret | Auth status |
| `/api/overview` | GET | cookie / secret | Decay + Runway + practice stats |
| `/api/quiz` | POST/GET | cookie / secret | Start warm-up or fetch session |
| `/api/drill` | POST/GET | cookie / secret | Typed/reverse/speed drills + grading |
| `/api/inspect` | GET | cookie / secret | Teaching card: components, similar kanji, sentence, audio |
| `/api/tick` | POST | `X-Cron-Secret` header | Scheduler entry point — check window, fetch WK, nudge if needed |
| `/api/telegram_webhook` | POST | Telegram IP | `/status` command — on-demand snapshot |
| `/api/sync` | POST | `X-Cron-Secret` header | Daily WK → Neon sync (Phase 0) |
| `/api/decay` | GET | cookie / secret | Decay Map — what rotted (Phase 1) |
| `/api/runway` | GET | cookie / secret | Burn-down plan + recovery date (Phase 3) |

Site password for the UI: `SITE_PASSWORD` if set, otherwise `CRON_SECRET`.


## Nudge windows (WIB)

- **Morning:** 06:00–09:00
- **Lunch:** 12:00–14:00
- Outside windows → 200 no-op, no message sent

## Env vars

| Var | Purpose |
|---|---|
| `WANIKANI_API_KEY` | Read-only WaniKani personal access token |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID (5845243960) |
| `CRON_SECRET` | Shared secret — include in cron-job.org header |
| `MINER_ENABLED` | `false` — flip to `true` when v1.1 miner is ready |
| `ANTHROPIC_API_KEY` | Unset for v1 — only needed for miner |

## cron-job.org setup

1. Go to [cron-job.org](https://cron-job.org) → Create cronjob
2. **URL:** `https://kani-sensei.vercel.app/api/tick`
3. **Method:** POST
4. **Schedule:** Every 30 minutes (custom: `*/30 * * * *`)
5. **Headers:** Add header `X-Cron-Secret` = `<your CRON_SECRET value>`
6. **Body:** (empty — no body needed)
7. Save and enable

The bot will only send messages during nudge windows. Outside windows it returns 200 silently.

## Telegram /status command (optional setup)

To enable the `/status` command from your Telegram chat:

```bash
# Register webhook with Telegram (replace with your deployed URL)
curl -X POST "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://kani-sensei.vercel.app/api/telegram_webhook"}'
```

Then send `/status` in your bot chat to get a live WaniKani snapshot.

## Token rotation (do this after first deploy)

Both tokens transited Discord during setup. Rotate them:

1. **Bot token:** BotFather → `/mybots` → select bot → API Token → Revoke & regenerate
2. **WaniKani key:** wanikani.com → Settings → API Tokens → Generate new token (read-only)
3. Update both in Vercel: Dashboard → kani-sensei → Settings → Environment Variables

## Verdict rules

| Condition | Verdict |
|---|---|
| Apprentice > 150 | circuit breaker: pause lessons |
| Reviews > 150 | queue's on fire. Clear it now |
| Apprentice > 100 | heavy load. Grind it down |
| Reviews > 50 | solid queue. Let's go |
| Otherwise | clear to lift |

## v1.1 Miner (scaffolded, not active)

The sentence miner fires during the 08:00–08:30 WIB tick when `MINER_ENABLED=true` and `ANTHROPIC_API_KEY` is set. It fetches burned/guru vocab from WaniKani and sends 3 Japanese sentences via Claude Haiku, with translations wrapped in Telegram spoiler tags.

To activate: set `MINER_ENABLED=true` and add `ANTHROPIC_API_KEY` in Vercel env vars.

# Kani Sensei Platform — Phase 4: Interactive drills

Phase 4 turns Warm-Up's multiple-choice shell into practice that actually
transfers to WaniKani: typed recall, reverse recognition, ghost reviews
for burned items, and a leech clinic for chronic misses.

## What shipped

| File | Purpose |
|------|---------|
| `migrations/002_drills.sql` | `drill_sessions`, `drill_questions`, `drill_misses`. |
| `shared/answers.py` | WK-style meaning/reading matching, romaji → hiragana. |
| `shared/drill.py` | Decay / burned / leech / miss pools, grading, notebook. |
| `api/drill.py` | `POST/GET /api/drill` — start, grade, recap, stats. |
| `api/overview.py` | Adds a `practice` block for the home dashboard. |
| `web/src/TestView.jsx` | Typed input, reverse glyphs, 60s blitz, recap. |
| `test_answers.py` / `test_drill.py` | Matching + pool/kind coverage. |

**Untouched on purpose:** `api/tick.py`, `api/telegram_webhook.py`.

## Why this, not more multiple choice

WaniKani reviews are typed. Multiple choice is a fine warm-up; it is a
weak proxy for the real queue. The new Kanji / Vocab tests default to
typed recall with the same accepted-answer list WK uses. Readings accept
hiragana, katakana, or romaji. Close meaning typos are flagged "almost"
but still count wrong — we stay honest.

## Modes

| Kind | What you do |
|------|-------------|
| `recall` | See the glyph, type meaning or reading. |
| `reverse` | See the meaning, pick the glyph. |
| `mc` | Four-choice warm-up, same decay weighting. |
| `speed` | 60-second blitz, 20+ pre-built questions. |

| Pool | What gets sampled |
|------|-------------------|
| `decay` | Decay Map weighting (default). |
| `due` | Currently available reviews. |
| `leeches` | High-incorrect, low-accuracy items. |
| `burned` | Ghosts — stage 9 / burned_at set. |
| `misses` | Items this app has seen you miss. |

## API

```bash
curl -X POST "https://kani-sensei.vercel.app/api/drill" \
  -H "Content-Type: application/json" \
  -H "Cookie: kani_session=..." \
  -d '{"min_level":14,"max_level":18,"count":10,"kind":"recall","pool":"decay","object_types":["kanji"]}'
```

Grade a typed answer:

```bash
curl -X POST "https://kani-sensei.vercel.app/api/drill?action=answer" \
  -H "Content-Type: application/json" \
  -H "Cookie: kani_session=..." \
  -d '{"session_id":"...","question_id":"...","text":"mountain"}'
```

Schema is created on first drill request (`CREATE TABLE IF NOT EXISTS`) so
a rolling deploy still works if `002_drills.sql` has not been applied yet.
Still apply the migration when you can.

## Follow-up: inspect + study UX

After each answer, `/api/inspect` (and the drill reveal) now pull the cached
WK payload: radicals the kanji is built from, visually similar glyphs,
vocab that uses it, a context sentence, audio, and a mnemonic toggle.
Decay Map levels start a targeted drill; items open an inspect sheet.
Keyboard: Enter checks, 1–4 picks a choice, `?` skips, Space continues.

## Honest limits

- Romaji conversion covers regular gojuon, youon, sokuon, and ん. Long
  vowels like とうきょう as `tokyo` will miss — type kana for those.
- Ghosts need burned items in the synced snapshot. If the range is empty,
  the API says so instead of inventing work.
- The Sensei notebook is local to this app. It does not write back to WK.

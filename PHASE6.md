# Kani Sensei Platform — Phase 6: everyday reading, fresher data

Phase 6 makes the reading module show up on ordinary days, and adds a
sentence index so a sentence can be chosen for the one word you don't
know yet. There is still no generative API.

## What shipped

| File | Purpose |
|------|---------|
| `migrations/004_sentences.sql` | `reading_sentences`, one row per WaniKani context sentence. |
| `migrations/005_recall.sql` | Recall tally columns on `reading_progress`. |
| `api/sync.py` | GET with `Authorization: Bearer`, and a sentence-index rebuild at the end of a catalog sync. |
| `vercel.json` | Daily `/api/sync` and weekly `/api/sync?scope=catalog`. Sync may run for 300 seconds. |
| `shared/reader.py` | Radical-day read, sentence index, just-right feed, known-word ratio, catalog search. |
| `shared/inspect.py` | Cards for subjects that exist only in `wk_catalog`, plus "Seen in N sentences". |
| `shared/daily.py` | Radicals capped at 5 of 20 when kanji or words are waiting. |
| `api/read.py` | `feed`, `search`, and `index_missing`. Same function, new `?action=`. |
| `web/src/ReadFeed.jsx` | One sentence, Got it / Again. |
| `web/src/Reader.jsx` | Recall, text size, vertical text, Play all, Shadow. |
| `web/src/SearchBox.jsx` | Top-bar look-up, opened with `/`. |
| `web/vite.config.js` | Service worker stamped with the build hash. |
| `web/public/manifest.webmanifest` | Install on a phone. |
| `test_reader.py` / `test_daily.py` / `test_sync_auth.py` | Index rows, feed rule, known ratio, search rank, radical cap, cron auth. |

**Untouched on purpose:** `api/tick.py`, `api/telegram_webhook.py`.

## Scheduled sync

Vercel Cron sends GET and `Authorization: Bearer $CRON_SECRET`. The same
handler still accepts POST with `X-Cron-Secret`.

| Job | Path | UTC | WIB |
|-----|------|-----|-----|
| Unlocked snapshot | `/api/sync` | 21:00 daily | 04:00 |
| Catalog and sentence index | `/api/sync?scope=catalog` | 22:00 Sunday | Monday 05:00 |

The index is not built inside `/api/read`. That function stays at 60
seconds. A catalog sync (300 seconds) truncates `reading_sentences` and
inserts one row per context sentence: the words, the kanji inside them,
the highest level, and whether the sentence can be dictated. The first
catalog sync after this deploy has to finish before reading will load.
Until the table has rows, `/api/read` returns `409 {"error": "index_missing"}`.

## Everyday reading

A daily set that is only radicals used to produce an empty read. It now
pulls kanji at or below your level that those radicals build, then words
that use those kanji, and titles the passage "Built from today's radicals".
`{"empty": true}` remains for the day when that search finds nothing.

The just-right feed (`/read/feed`, `GET /api/read?action=feed`) is one
sentence whose words are all in levels 1 through yours, and exactly one
of them is below Guru. Course stage wins over the WaniKani assignment,
same as the rest of the reader. Order is an md5 of the sentence and the
WIB date, so a reload doesn't shuffle it. Got it advances. Again calls
the same lookup path as tapping a word, which becomes a drill miss once
the item has been started.

Recall is a third switch in the reader. Target words are blanks. The
browser grades the typed reading against `token.readings`. A miss records
a lookup. The correct/total tally is stored next to the quiz score when
you finish.

Each passage on the level list and in the reader says "You know N% of
the words", from the index plus your stages. A word card says how many
indexed sentences contain it and shows two of them. Subjects past the
unlocked snapshot still open a card (meaning, readings, parts, audio,
sentence). The catalog doesn't store the mnemonic, so that part stays empty.

## Look-up and the daily set

`/` focuses a search box in the top bar. `GET /api/read?action=search&q=`
uses `ILIKE` over `wk_catalog` (characters, meanings, readings). Romaji
goes through `normalize_reading` first. Choosing a row opens the card.

`_pick` still orders due Guru items first. When the pool contains a kanji
or a word, radicals take at most 5 of the 20 seats and the rest follow
the old order. A radicals-only pool is unchanged. Today's row is already
frozen, so this changes the next day that doesn't have a set yet. The
streak is the same function as before.

## Install

`web/public/manifest.webmanifest` and the seal icons make the site
installable. The production build emits `sw.js` whose cache name is the
script hash, precaches the shell, and keeps the last 10 passage or daily
responses. A deploy changes the hash, so the next load drops the old
shell cache. The worker is registered only in the production build.

## Honest limits

- The feed and the known-word line need the sentence index. They don't
  try to segment the catalog during a page view.
- "Known" follows the course stage when a course row exists, and the
  WaniKani stage otherwise. A course that's behind WaniKani will treat
  those course items as unknown.
- Again records a drill miss only for an item at stage 1 or higher, at
  or below your level. That's the same rule as tapping a word.
- Recall is graded in the browser. The server stores the tally you send
  with finish.
- Play all and Shadow use the device voice and start from a tap. They
  don't highlight word by word; iOS Japanese voices don't report
  boundaries. A phone may also stop a chain of utterances that began
  in one tap.
- Search is a plain `ILIKE`. A short English fragment can match more
  than the word you meant. Exact characters sort first.
- The offline cache is the app shell plus the last 10 passage or daily
  responses. Drills, the feed, and search need the network.
- Similar-kanji and mnemonic limits from Phase 5 still apply.

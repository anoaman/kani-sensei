# Kani Sensei Platform — Phase 5: Reading, daily read, listening, Kanji Web

Phase 5 adds a reading module built entirely from WaniKani's own example
sentences. There is no generative API. A level's passages are chosen so
every kanji and word at that level shows up, with furigana on anything
above the level you're reading.

## What shipped

| File | Purpose |
|------|---------|
| `migrations/003_reading.sql` | `wk_catalog`, `reading_passages`, `reading_progress`. |
| `shared/reader.py` | Lexicon, furigana, set cover, questions, daily read, lookups. |
| `shared/kanji_web.py` | Per-level radical → kanji → word graph. |
| `api/sync.py` | `POST /api/sync?scope=catalog` bulk-upserts the full catalog. |
| `api/read.py` | The one new function: index, level, passage, daily, web, lookup, dictation, finish, custom. |
| `shared/drill.py` | `record_lookup` writes a reading miss into `drill_misses`. |
| `web/src/ReadIndex.jsx` | Today's read, paste-your-own text, levels 1–60. |
| `web/src/ReadLevel.jsx` | Passage list and coverage. |
| `web/src/Reader.jsx` | Furigana, word popover, comprehension check, listen mode. |
| `web/src/speech.js` | Browser Japanese speech. Speak only from a tap. |
| `web/src/KanjiWeb.jsx` | SVG lanes on a wide screen, a focus list under 720px. |
| `test_reader.py` / `test_kanji_web.py` | Annotator, grading, set cover, graph order. |

**Untouched on purpose:** `api/tick.py`, `api/telegram_webhook.py`.

## Why WaniKani's sentences

Each vocabulary subject already carries `context_sentences` (Japanese and
English) written by WaniKani. The planner is a greedy set cover over those
sentences: prefer a sentence that covers new targets, penalize kanji from
above the level, and keep sentences from getting long. Six sentences make
one passage. The plan is frozen the first time you open a level, so the
numbering stays put.

The full catalog cannot live in `wk_subjects`. Quiz, drill, course, decay,
and the daily set treat that table as what you've unlocked. Locked items
go in `wk_catalog` instead. The daily sync is unchanged. A weekly
`POST /api/sync?scope=catalog` (same `X-Cron-Secret`) fills the new table.
Run it once by hand after deploying. If the table is empty, `/api/read`
returns `409 {"error": "catalog_missing"}`.

Schema is created on first use (`CREATE TABLE IF NOT EXISTS`). Still apply
`migrations/003_reading.sql` when you can.

## Modes

| Mode | What you do |
|------|-------------|
| Read | Sentences with `<ruby>` furigana. Auto shows it on words above the level and on words below Guru. All and Off are saved in the browser. |
| Check | Three questions: pick the English, pick a meaning, type a reading. |
| Listen | Text hidden. Type the kana, or pick the English when the sentence has no complete reading. Needs a Japanese voice on the device. |
| Today | Up to eight sentences from today's daily set, frozen for the WIB day. It does not move the streak. |
| Your text | Paste up to 2000 characters. Split on `。！？` and newlines. No translations, so the check is meaning and reading only. |
| Kanji Web | Radicals, kanji, and words for one level, plus the lower-level parts they are built from. A red ring is a weak item. |

Tapping a word records a lookup. If you've started that item (stage 1 or
higher) and it is at or below your level, it is also a drill miss, so
practice brings it back.

Any level from 1 to 60 can be opened. Levels above yours are marked
preview; words above the passage's reference level get a dotted underline.

## API

The web UI is public. Cron sync still checks `X-Cron-Secret`.

```bash
curl "https://kani-sensei.vercel.app/api/read"
curl "https://kani-sensei.vercel.app/api/read?action=level&level=1"
curl "https://kani-sensei.vercel.app/api/read?action=passage&id=level:1:0"
curl "https://kani-sensei.vercel.app/api/read?action=daily"
curl "https://kani-sensei.vercel.app/api/read?action=web&level=1"
```

```bash
curl -X POST "https://kani-sensei.vercel.app/api/read?action=dictation" \
  -H "Content-Type: application/json" \
  -d '{"passage_id":"level:1:0","index":0,"text":"たべました"}'

curl -X POST "https://kani-sensei.vercel.app/api/read?action=finish" \
  -H "Content-Type: application/json" \
  -d '{"passage_id":"level:1:0","quiz_correct":2,"quiz_total":3,"listen_correct":1,"listen_total":1}'

curl -X POST "https://kani-sensei.vercel.app/api/sync?scope=catalog" \
  -H "X-Cron-Secret: $CRON_SECRET"
```

Multiple-choice answers in the passage payload are indexes into `choices`.
Typed readings are checked against the subject's accepted readings.
Dictation normalizes romaji and katakana to hiragana, then scores
`1 - levenshtein / length`: 0.85 or more is a pass, 0.60 or more is close.

## Honest limits

- These are WaniKani's own sentences, not one continuous story. Pasted text
  is the way to read something that actually connects.
- Ambiguous kanji, and jukugo such as 大人, take one ruby over the whole
  kanji run, using WaniKani's primary reading.
- A verb or い-adjective is also indexed as its stem (食べる → 食べ,
  勉強する → 勉強). That is one trailing kana, not a full conjugator.
  Irregulars only match when the stem is still in the sentence.
- Kana-only words shorter than 3 characters are not matched. Particles
  stay plain text.
- Radicals are not covered by readings. They show up in Kanji Web.
- Voice quality is whatever the phone or laptop has installed. With no
  Japanese voice, Listen stays off and the page says where to add one
  (Settings → Accessibility → Spoken Content → Voices → Japanese).
- Romaji conversion is the same as drills. Long vowels typed the English
  way (`tokyo` for とうきょう) will miss.
- Similar-kanji lines are drawn when both characters are already on the
  graph. A radical two steps below an off-level kanji may be missing.

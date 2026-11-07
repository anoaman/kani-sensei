# Kani Sensei Platform — Phase 7: level-band stories

Phase 7 adds a story for every group of three levels, from 1–3 through 58–60.
Bands 1–3, 4–6, and 7–9 have a short plot written by hand. Every band also
gets pages assembled from WaniKani's own sentences. There is still no
generative API, and no new Vercel function.

## What shipped

| File | Purpose |
|------|---------|
| `shared/stories.py` | Bands, the kanji check, the sentence trail, and freezing pages. |
| `shared/stories/band-01.json` | "Mika's mountain", levels 1–3. |
| `shared/stories/band-04.json` | "Ken's day off", levels 4–6. |
| `shared/stories/band-07.json` | "Yuki's letter", levels 7–9. |
| `scripts/check_stories.py` | Fails if a written sentence uses a kanji above the band. |
| `shared/reader.py` | Story pages use the band's top level, and link to the previous and next page. |
| `api/read.py` | `GET ?action=story&band=N` on the existing read function. |
| `web/src/ReadStory.jsx` | Page list at `/read/story/N`. |
| `web/src/ReadIndex.jsx` | Twenty story tiles. |
| `web/src/Reader.jsx` | "Page 2 of 4", and "Next page" after you finish. |
| `test_stories.py` | Bands, violations, the shared-word chain, and the 5×5 cap. |

**Untouched on purpose:** `api/tick.py`, `api/telegram_webhook.py`.

## How a story is built

A band is three levels. Level 19 is band 16–18. The story for levels 1–3
may use any kanji from levels 1, 2, or 3. Anything higher is written in kana.

`GET /api/read?action=story&band=1` builds the pages the first time you open
that band and then freezes them, the same way a level reading is frozen.
Page ids are `story:1:1`, `story:1:2`, and so on. `plan_version` stores the
`version` from the JSON file, or `0` when the band has no file. Raising
`version` rebuilds the pages. Rows in `reading_progress` stay, because they
are keyed by those page ids.

A written band is the story's own pages plus one page titled "More from this
band". That page is WaniKani sentences that cover band items the story never
used. A band with no file is only those sentences: up to 5 pages, 5 sentences
each. The next sentence is chosen to share a word with the one before it, and
to cover a band item that is still missing.

Story pages are ordinary `reading_passages` rows with `kind = 'story'`.
Furigana, popovers, Recall, Listen, Check, text size, vertical text, the
known-word line, and the offline cache all apply without a separate path.
The level stored on the row is the band's start. Furigana treats the band's
top level as the reference, so a kanji above the band stays marked above.

## Checking the written stories

```bash
DATABASE_URL=... python3 scripts/check_stories.py
```

The script loads `wk_catalog` and fails if any kanji in `shared/stories/` is
above the band, or missing from the catalog. It prints the kana the segmenter
will show, so a word that took the wrong reading can be rewritten before
commit. It also lists band items the written pages do not cover. That list is
not a failure. The extra sentence page is what covers them, as far as five
sentences can.

## Honest limits

- The sentence pages are a chain of example sentences that share words. They
  are not a plot. Only bands 1–3, 4–6, and 7–9 have a written story.
- Five sentences cannot hold every item in three levels. The trail stops at
  5 pages. Whatever is left stays uncovered.
- Furigana on the written pages comes from the same segmenter as pasted text.
  A conjugated verb can lose to a longer noun (`行きます` matched 行き, "train
  direction"), so those sentences were rewritten to a form the segmenter reads
  correctly. `scripts/check_stories.py` is how that gets caught.
- A kanji can be inside the band while the vocabulary item for that character
  is taught later. 海 is a level 6 kanji and a level 9 word. The kanji check
  allows it. The reader then marks the word above the band and keeps the
  furigana on.
- The known-word percentage uses indexed word ids for WaniKani sentences, and
  the subjects the segmenter found for written sentences.
- Opening a band builds it. The Read index does not build all twenty.

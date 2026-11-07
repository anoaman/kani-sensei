#!/usr/bin/env python3
"""Check written stories against the WaniKani catalog.

Fails if a sentence uses a kanji above its band, or a kanji with no catalog
entry. Prints each sentence's segmented kana so a bad reading can be caught
before commit. Also prints the band items the written pages do not cover.
The extra sentence page is what covers those.

Requires DATABASE_URL or POSTGRES_URL.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.neon import NeonClient
from shared.reader import annotate_sentence, covered_ids, load_lexicon, require_catalog
from shared.stories import band_range, iter_authored, story_violations


def _database_url():
    return os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")


def _shape_errors(story):
    errors = []
    band = story.get("band")
    pages = story.get("pages") or []
    if story.get("version") is None:
        errors.append("missing version")
    if not (story.get("title") or "").strip():
        errors.append("missing title")
    if not 3 <= len(pages) <= 5:
        errors.append(f"band {band} has {len(pages)} pages; expected 3 to 5")
    for index, page in enumerate(pages, start=1):
        sentences = page.get("sentences") or []
        if not 5 <= len(sentences) <= 8:
            errors.append(f"band {band} page {index} has {len(sentences)} sentences; expected 5 to 8")
        if not (page.get("title") or "").strip():
            errors.append(f"band {band} page {index} has no title")
        for sentence_index, sentence in enumerate(sentences, start=1):
            if not (sentence.get("ja") or "").strip():
                errors.append(f"band {band} page {index} sentence {sentence_index} has no Japanese")
            if not (sentence.get("en") or "").strip():
                errors.append(f"band {band} page {index} sentence {sentence_index} has no English")
    return errors


def _targets(db, start, top):
    rows = db.execute(
        """
        select id, object_type, level, characters, primary_meaning
        from wk_catalog
        where level between %s and %s
          and object_type in ('kanji', 'vocabulary', 'kana_vocabulary')
          and characters is not null and characters <> ''
        order by level, object_type, lesson_position nulls last, id
        """,
        [start, top],
        fetch=True,
    )
    return [
        {
            "id": int(row[0]),
            "type": row[1],
            "level": int(row[2]),
            "characters": row[3],
            "meaning": row[4] or "",
        }
        for row in rows
    ]


def _uncovered(story, lexicon, targets):
    target_ids = {item["id"] for item in targets}
    covered = set()
    for page in story.get("pages") or []:
        for sentence in page.get("sentences") or []:
            covered |= covered_ids(sentence.get("ja") or "", lexicon, target_ids)
    return [item for item in targets if item["id"] not in covered]


def main():
    database_url = _database_url()
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 1
    stories = iter_authored()
    if not stories:
        print("no story files in shared/stories", file=sys.stderr)
        return 1

    db = NeonClient(database_url)
    failed = False
    with db.reuse():
        require_catalog(db)
        lexicon = load_lexicon(db)
        for story in stories:
            band = int(story["band"])
            start, top = band_range(band)
            print(f"\n== band {start}–{top} {story.get('title') or ''} ==")
            for error in _shape_errors(story):
                failed = True
                print(f"shape: {error}")
            violations = story_violations(story, lexicon, top)
            for item in violations:
                failed = True
                level = "none" if item["level"] is None else item["level"]
                print(
                    f"kanji: page {item['page']} sentence {item['sentence']} "
                    f"{item['kanji']} level {level}"
                )
            for page_index, page in enumerate(story.get("pages") or [], start=1):
                print(f"\n# {page.get('title') or page_index}")
                for sentence_index, sentence in enumerate(page.get("sentences") or [], start=1):
                    ja = sentence.get("ja") or ""
                    block = annotate_sentence(ja, lexicon, reference_level=top)
                    flag = "" if block.get("listenable") else "  (no reading)"
                    print(f"{sentence_index}. {ja}")
                    print(f"   {block.get('kana') or ''}{flag}")
            missed = _uncovered(story, lexicon, _targets(db, start, top))
            kanji = [item["characters"] for item in missed if item["type"] == "kanji"]
            words = [item["characters"] for item in missed if item["type"] != "kanji"]
            print(f"\nuncovered {len(missed)} (kanji {len(kanji)}, words {len(words)})")
            print("kanji: " + (" ".join(kanji) if kanji else "none"))
            print("words: " + (" ".join(words) if words else "none"))
            print("The sentence page covers these.")
    if failed:
        print("\nfailed", file=sys.stderr)
        return 1
    print("\nok")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        text = str(exc)
        secret = _database_url() or ""
        if secret:
            text = text.replace(secret, "DATABASE_URL")
        print(f"{type(exc).__name__}: {text}", file=sys.stderr)
        sys.exit(1)

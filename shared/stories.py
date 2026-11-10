"""Level-band stories, and one passage of every word on a single level.

A band is three WaniKani levels: 1–3, 4–6, up to 58–60. Written pages live in
shared/stories/band-NN.json. Every band also gets pages assembled from
WaniKani sentences at or below the band's top level. No model calls.

Pages are ordinary reading_passages rows (kind = 'story'). The level column
stores the band start. plan_version stores the story file's version, or 0
when the band has no file. A version change rebuilds the pages and leaves
reading_progress rows where they are, keyed by page id.

A level's vocabulary is a different passage (kind = 'words'). It holds every
vocabulary item on that level, in lesson order, and does not use the band cap.
"""

from __future__ import annotations

import json
from pathlib import Path

from shared.reader import (
    _insert_passage,
    _json,
    ensure_schema,
    fetch_stages,
    is_kanji,
    known_ratio,
    load_lexicon,
    require_index,
    segment,
)

PAGE_SENTENCES = 5
MAX_PAGES = 5
MAX_SENTENCES = PAGE_SENTENCES * MAX_PAGES
SENTENCE_VERSION = 0
STORY_KIND = "story"
EXTRA_PAGE_TITLE = "More from this band"
WORDS_KIND = "words"
WORDS_PAGE_SIZE = 6
WORDS_VERSION = 1
WORDS_PAGE_TITLE = "In lesson order"

_STORIES_DIR = Path(__file__).resolve().parent / "stories"


def band_of(level):
    """Start level of the three-level band that contains this level."""
    level = int(level)
    if level < 1 or level > 60:
        raise ValueError("level must be between 1 and 60")
    return ((level - 1) // 3) * 3 + 1


def band_range(start):
    """(start, start + 2), with the top capped at 60."""
    start = int(start)
    if start < 1:
        start = 1
    if start > 60:
        start = 60
    return (start, min(60, start + 2))


def bands():
    return [band_range(start) for start in range(1, 61, 3)]


def story_violations(story, lexicon, top):
    """Kanji with no lexicon entry, or an entry above top.

    One dict per occurrence: page and sentence are 1-based.
    """
    top = int(top)
    found = []
    for page_index, page in enumerate(story.get("pages") or [], start=1):
        for sentence_index, sentence in enumerate(page.get("sentences") or [], start=1):
            text = sentence.get("ja") if isinstance(sentence, dict) else ""
            for char in text or "":
                if not is_kanji(char):
                    continue
                entry = lexicon.kanji.get(char)
                level = int(entry["level"]) if entry and entry.get("level") is not None else None
                if entry is None or level is None or level > top:
                    found.append({
                        "page": page_index,
                        "sentence": sentence_index,
                        "kanji": char,
                        "level": level,
                    })
    return found


def _as_ids(values):
    ids = []
    for value in values or []:
        if isinstance(value, dict):
            value = value.get("id")
        if value is None:
            continue
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def sentence_trail(candidates, targets, start_ids):
    """Greedy cover of targets. Prefer a sentence that shares a word with the previous one.

    start_ids are the word ids already in play (the written pages, or empty).
    The result is pages of at most PAGE_SENTENCES, and at most MAX_PAGES.
    """
    remaining = set(_as_ids(targets))
    previous = set(_as_ids(start_ids))
    target_ids = set(remaining)
    pool = []
    for candidate in candidates or []:
        covers = set(_as_ids(candidate.get("covers"))) & target_ids
        pool.append({
            **candidate,
            "covers": covers,
            "word_ids": set(_as_ids(candidate.get("word_ids"))),
        })

    chosen = []
    used = set()
    seen_ja = set()
    while remaining and len(chosen) < MAX_SENTENCES:
        best = None
        best_key = None
        for index, candidate in enumerate(pool):
            identity = (
                int(candidate.get("source_id") or 0),
                int(candidate.get("sentence_idx") or 0),
                index,
            )
            if identity in used:
                continue
            ja = (candidate.get("ja") or "").strip()
            if ja and ja in seen_ja:
                continue
            new = candidate["covers"] & remaining
            if not new:
                continue
            shared = candidate["word_ids"] & previous
            key = (
                0 if shared else 1,
                -len(new),
                -len(shared),
                identity[0],
                identity[1],
                index,
            )
            if best_key is None or key < best_key:
                best_key = key
                best = (identity, candidate)
        if best is None:
            break
        identity, candidate = best
        used.add(identity)
        ja = (candidate.get("ja") or "").strip()
        if ja:
            seen_ja.add(ja)
        chosen.append(candidate)
        remaining -= candidate["covers"]
        previous = set(candidate["word_ids"])

    pages = [
        chosen[index:index + PAGE_SENTENCES]
        for index in range(0, len(chosen), PAGE_SENTENCES)
    ]
    return pages[:MAX_PAGES]


def needs_rebuild(existing_versions, version):
    version = int(version)
    versions = []
    for item in existing_versions or []:
        versions.append(-1 if item is None else int(item))
    if not versions:
        return True
    return any(item != version for item in versions)


def story_is_stale(existing_count, written_pages, versions, version):
    """True when the frozen pages are missing, old, or shorter than the file.

    A build that stopped after two pages used to look current, because every
    stored page already had the right version.
    """
    incomplete = int(written_pages or 0) > 0 and int(existing_count or 0) < int(written_pages)
    return incomplete or needs_rebuild(versions, version)


def authored_path(start):
    return _STORIES_DIR / f"band-{int(start):02d}.json"


def load_authored(start):
    path = authored_path(start)
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        story = json.load(handle)
    band = int(story.get("band") or 0)
    if band != int(start):
        raise ValueError(f"{path.name} says band {story.get('band')}")
    return story


def iter_authored():
    if not _STORIES_DIR.is_dir():
        return []
    stories = []
    for path in sorted(_STORIES_DIR.glob("band-*.json")):
        with path.open(encoding="utf-8") as handle:
            stories.append(json.load(handle))
    return stories


def ids_in_text(text, lexicon, top):
    """Subject ids at or below top that this sentence actually uses."""
    found = set()
    top = int(top)
    for token in segment(text or "", lexicon):
        subject_id = token.get("subject_id")
        level = token.get("level")
        if subject_id is None or level is None:
            continue
        if int(level) <= top:
            found.add(int(subject_id))
    for char in text or "":
        entry = lexicon.kanji.get(char)
        if entry and entry.get("level") is not None and int(entry["level"]) <= top:
            found.add(int(entry["id"]))
    return found


def _band_targets(db, start, top):
    rows = db.execute(
        """
        select id, object_type, level, characters, primary_meaning
        from wk_catalog
        where level between %s and %s
          and object_type in ('kanji', 'vocabulary', 'kana_vocabulary')
          and characters is not null and characters <> ''
        order by level, lesson_position nulls last, id
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
            "meaning": row[4],
        }
        for row in rows
    ]


def _band_candidates(db, start, top, target_ids):
    rows = db.execute(
        """
        select source_id, idx, ja, en, word_ids, kanji_ids
        from reading_sentences
        where level between %s and %s
          and max_level <= %s
        order by level, source_id, idx
        """,
        [start, top, top],
        fetch=True,
    )
    candidates = []
    for source_id, idx, ja, en, word_ids, kanji_ids in rows:
        words = {int(item) for item in (word_ids or [])}
        kanji = {int(item) for item in (kanji_ids or [])}
        covers = (words | kanji) & target_ids
        source_id = int(source_id)
        if source_id in target_ids:
            covers.add(source_id)
        if not covers or not (ja or "").strip():
            continue
        candidates.append({
            "source_id": source_id,
            "sentence_idx": int(idx or 0),
            "ja": ja,
            "en": en or "",
            "covers": covers,
            "word_ids": words | kanji,
        })
    return candidates


def _sentence_row(ja, en, source_id=None):
    return {"ja": ja, "en": en or "", "source_id": source_id}


def _written_pages(story, lexicon, top):
    pages = []
    seen_ids = set()
    for index, page in enumerate(story.get("pages") or [], start=1):
        sentences = []
        covers = set()
        for sentence in page.get("sentences") or []:
            ja = (sentence.get("ja") or "").strip()
            if not ja:
                continue
            sentences.append(_sentence_row(ja, sentence.get("en") or ""))
            ids = ids_in_text(ja, lexicon, top)
            covers |= ids
            seen_ids |= ids
        if not sentences:
            continue
        pages.append({
            "idx": index,
            "title": (page.get("title") or f"Page {index}").strip() or f"Page {index}",
            "sentences": sentences,
            "covers": covers,
        })
    return pages, seen_ids


def _trail_pages(candidates, targets, start_ids, limit=None):
    pages = sentence_trail(candidates, targets, start_ids)
    if limit is not None:
        pages = pages[:int(limit)]
    built = []
    for chunk in pages:
        covers = set()
        sentences = []
        for candidate in chunk:
            covers |= set(candidate["covers"])
            sentences.append(_sentence_row(
                candidate.get("ja") or "",
                candidate.get("en") or "",
                candidate.get("source_id"),
            ))
        if sentences:
            built.append({"sentences": sentences, "covers": covers})
    return built


def build_story(db, start):
    """Freeze this band's pages. Rebuild when the file version changes.

    Progress stays on reading_progress, keyed by story:{start}:{n}.
    """
    require_index(db)
    ensure_schema(db)
    start, top = band_range(band_of(start))
    story = load_authored(start)
    version = int(story["version"]) if story else SENTENCE_VERSION
    existing = db.execute(
        """
        select plan_version from reading_passages
        where kind = %s and level = %s
        """,
        [STORY_KIND, start],
        fetch=True,
    )
    written_pages = len((story or {}).get("pages") or [])
    if not story_is_stale(len(existing), written_pages, [row[0] for row in existing], version):
        return start

    lexicon = load_lexicon(db)
    targets = _band_targets(db, start, top)
    target_ids = {item["id"] for item in targets}
    candidates = _band_candidates(db, start, top, target_ids)

    pages = []
    if story:
        written, seen_ids = _written_pages(story, lexicon, top)
        pages.extend(written)
        missed = [item["id"] for item in targets if item["id"] not in seen_ids]
        extra = _trail_pages(candidates, missed, seen_ids, limit=1)
        if extra:
            extra[0]["title"] = EXTRA_PAGE_TITLE
            pages.append(extra[0])
    else:
        trailed = _trail_pages(candidates, [item["id"] for item in targets], set())
        for index, page in enumerate(trailed, start=1):
            page["title"] = f"Page {index}"
            pages.append(page)

    # One transaction: a killed request rolls back instead of freezing a short story.
    with db.reuse():
        db.execute(
            "delete from reading_passages where kind = %s and level = %s",
            [STORY_KIND, start],
        )
        for index, page in enumerate(pages, start=1):
            _insert_passage(
                db,
                f"story:{start}:{index}",
                STORY_KIND,
                start,
                None,
                index,
                page["title"],
                page["sentences"],
                sorted(page["covers"]),
                plan_version=version,
            )
    return start


def _indexed_word_ids(db, groups):
    wanted = []
    for group in groups or []:
        for sentence in group or []:
            if not isinstance(sentence, dict):
                continue
            source_id = sentence.get("source_id")
            ja = sentence.get("ja")
            if source_id and ja:
                wanted.append((int(source_id), ja))
    by_key = {}
    if wanted:
        rows = db.execute(
            """
            select source_id, ja, word_ids
            from reading_sentences
            where source_id = any(%s)
            """,
            [sorted({source_id for source_id, _ja in wanted})],
            fetch=True,
        )
        for source_id, ja, word_ids in rows:
            bucket = by_key.setdefault((int(source_id), ja), [])
            bucket.extend(int(item) for item in (word_ids or []))
    grouped = []
    for group in groups or []:
        ids = []
        for sentence in group or []:
            if not isinstance(sentence, dict) or not sentence.get("source_id") or not sentence.get("ja"):
                continue
            ids.extend(by_key.get((int(sentence["source_id"]), sentence["ja"]), []))
        grouped.append(ids)
    return grouped


def _page_id_lists(db, pages):
    """Word ids per page. Indexed sentences first, then covers for written text."""
    indexed = _indexed_word_ids(db, [page.get("sentences") or [] for page in pages])
    per_page = []
    for page, ids in zip(pages, indexed):
        merged = []
        seen = set()
        for item in list(ids) + list(page.get("covers") or []):
            if item is None:
                continue
            item = int(item)
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
        per_page.append(merged)
    return per_page


def known_by_page(db, pages):
    """Overall known-word ratio, and one ratio per page."""
    per_page = _page_id_lists(db, pages)
    flat = [item for ids in per_page for item in ids]
    stages = fetch_stages(db, flat)
    return known_ratio(flat, stages), [known_ratio(ids, stages) for ids in per_page]


def _page_rows(db, start, kind=STORY_KIND):
    rows = db.execute(
        """
        select p.id, p.idx, p.title, p.sentences, p.covers,
               g.opened_at is not null, g.finished_at is not null
        from reading_passages p
        left join reading_progress g on g.passage_id = p.id
        where p.kind = %s and p.level = %s
        order by p.idx
        """,
        [kind, start],
        fetch=True,
    )
    pages = []
    for passage_id, idx, title, sentences_raw, covers_raw, opened, finished in rows:
        pages.append({
            "id": passage_id,
            "idx": int(idx) if idx else None,
            "title": title,
            "sentences": _json(sentences_raw, []),
            "covers": [int(item) for item in (covers_raw or [])],
            "opened": bool(opened),
            "finished": bool(finished),
        })
    return pages


def story_view(db, start):
    start, top = band_range(band_of(start))
    story = load_authored(start)
    pages = _page_rows(db, start)
    overall, ratios = known_by_page(db, pages) if pages else (None, [])
    listed = []
    for page, known in zip(pages, ratios):
        listed.append({
            "id": page["id"],
            "idx": page["idx"],
            "title": page["title"],
            "sentences": len(page["sentences"]),
            "opened": page["opened"],
            "finished": page["finished"],
            "known": known,
        })
    return {
        "band": start,
        "top": top,
        "title": (story or {}).get("title") or f"Levels {start}–{top}",
        "source": "written" if story else "sentences",
        "written": story is not None,
        "pages": listed,
        "finished": sum(1 for page in listed if page["finished"]),
        "known": overall,
    }


def fetch_story(db, level):
    start = build_story(db, level)
    return story_view(db, start)


def sentence_within_level(text, lexicon, level):
    """True when every kanji in text is known and at or below level."""
    level = int(level)
    for char in text or "":
        if not is_kanji(char):
            continue
        entry = lexicon.kanji.get(char)
        kanji_level = entry.get("level") if entry else None
        if kanji_level is None or int(kanji_level) > level:
            return False
    return True


def pick_word_sentence(item, lexicon, level):
    """First context sentence that stays inside the level, else a fixed frame.

    The frame still contains the word. Its English line is the primary meaning.
    """
    characters = (item.get("characters") or "").strip()
    meaning = (item.get("meaning") or item.get("primary_meaning") or "").strip()
    for sentence in item.get("context_sentences") or []:
        if not isinstance(sentence, dict):
            continue
        ja = (sentence.get("ja") or "").strip()
        if not ja or not sentence_within_level(ja, lexicon, level):
            continue
        return {
            "ja": ja,
            "en": (sentence.get("en") or "").strip(),
            "source_id": int(item["id"]),
        }
    return {
        "ja": f"{characters}があります。",
        "en": meaning,
        "source_id": None,
    }


def pages_for_words(items, lexicon, level, page_size=WORDS_PAGE_SIZE):
    """One sentence per vocabulary item, then pages of page_size. No page cap."""
    chosen = []
    for item in items or []:
        if item.get("id") is None or not (item.get("characters") or "").strip():
            continue
        sentence = pick_word_sentence(item, lexicon, level)
        chosen.append({**sentence, "covers": {int(item["id"])}})
    page_size = max(1, int(page_size))
    pages = []
    for start in range(0, len(chosen), page_size):
        chunk = chosen[start:start + page_size]
        covers = set()
        for sentence in chunk:
            covers |= set(sentence["covers"])
        pages.append({
            "title": WORDS_PAGE_TITLE,
            "sentences": [
                {
                    "ja": sentence["ja"],
                    "en": sentence["en"],
                    "source_id": sentence.get("source_id"),
                }
                for sentence in chunk
            ],
            "covers": covers,
        })
    return pages


def _level_words(db, level):
    rows = db.execute(
        """
        select id, characters, primary_meaning, context_sentences
        from wk_catalog
        where level = %s
          and object_type in ('vocabulary', 'kana_vocabulary')
          and characters is not null and characters <> ''
        order by lesson_position nulls last, id
        """,
        [int(level)],
        fetch=True,
    )
    words = []
    for subject_id, characters, meaning, sentences in rows:
        words.append({
            "id": int(subject_id),
            "characters": characters,
            "meaning": meaning or "",
            "context_sentences": _json(sentences, []),
        })
    return words


def _words_stale(versions, expected_pages):
    if not versions and int(expected_pages) == 0:
        return False
    if len(versions) != int(expected_pages):
        return True
    return needs_rebuild(versions, WORDS_VERSION)


def build_words(db, level):
    """Freeze every vocabulary item on this level. Rebuild when the rule version changes.

    Progress stays on reading_progress, keyed by words:{level}:{n}.
    """
    require_index(db)
    ensure_schema(db)
    level = int(level)
    if level < 1 or level > 60:
        raise ValueError("level must be between 1 and 60")
    items = _level_words(db, level)
    pages = pages_for_words(items, load_lexicon(db), level)
    existing = db.execute(
        """
        select plan_version from reading_passages
        where kind = %s and level = %s
        order by idx
        """,
        [WORDS_KIND, level],
        fetch=True,
    )
    if not _words_stale([row[0] for row in existing], len(pages)):
        return level

    with db.reuse():
        db.execute(
            "delete from reading_passages where kind = %s and level = %s",
            [WORDS_KIND, level],
        )
        for index, page in enumerate(pages, start=1):
            _insert_passage(
                db,
                f"words:{level}:{index}",
                WORDS_KIND,
                level,
                None,
                index,
                page["title"],
                page["sentences"],
                sorted(page["covers"]),
                plan_version=WORDS_VERSION,
            )
    return level


def words_view(db, level):
    level = int(level)
    pages = _page_rows(db, level, WORDS_KIND)
    overall, ratios = known_by_page(db, pages) if pages else (None, [])
    listed = []
    for page, known in zip(pages, ratios):
        listed.append({
            "id": page["id"],
            "idx": page["idx"],
            "title": page["title"],
            "sentences": len(page["sentences"]),
            "opened": page["opened"],
            "finished": page["finished"],
            "known": known,
        })
    return {
        "level": level,
        "title": "All the words",
        "pages": listed,
        "finished": sum(1 for page in listed if page["finished"]),
        "known": overall,
    }


def fetch_words(db, level):
    level = build_words(db, level)
    return words_view(db, level)


def story_summaries(db):
    """One row per band. Does not build pages that have not been opened."""
    rows = db.execute(
        """
        select p.level, p.idx, p.sentences, p.covers, g.finished_at is not null
        from reading_passages p
        left join reading_progress g on g.passage_id = p.id
        where p.kind = %s
        order by p.level, p.idx
        """,
        [STORY_KIND],
        fetch=True,
    )
    grouped = {}
    for level, idx, sentences_raw, covers_raw, finished in rows:
        if not level:
            continue
        grouped.setdefault(int(level), []).append({
            "idx": int(idx) if idx else None,
            "sentences": _json(sentences_raw, []),
            "covers": [int(item) for item in (covers_raw or [])],
            "finished": bool(finished),
        })
    ordered = []
    spans = []
    for start, top in bands():
        pages = grouped.get(start, [])
        spans.append((start, top, pages, len(ordered), len(pages)))
        ordered.extend(pages)
    per_page = _page_id_lists(db, ordered) if ordered else []
    flat = [item for ids in per_page for item in ids]
    stages = fetch_stages(db, flat) if flat else {}
    summaries = []
    for start, top, pages, offset, count in spans:
        story = load_authored(start)
        ids = []
        seen = set()
        for group in per_page[offset:offset + count]:
            for item in group:
                if item in seen:
                    continue
                seen.add(item)
                ids.append(item)
        summaries.append({
            "band": start,
            "top": top,
            "title": (story or {}).get("title") or f"Levels {start}–{top}",
            "source": "written" if story else "sentences",
            "written": story is not None,
            "pages": len(pages),
            "finished": sum(1 for page in pages if page["finished"]),
            "known": known_ratio(ids, stages) if pages else None,
        })
    return summaries

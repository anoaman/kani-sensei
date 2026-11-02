"""Reading module: level passages built from WaniKani's own example sentences.

No model calls. A passage is a small set of cached context sentences chosen so
that, across the passages for a level, every kanji and vocabulary item of that
level shows up at least once. Words from higher levels keep their furigana.

The full subject catalog lives in wk_catalog, not wk_subjects. wk_subjects is
only what the user has unlocked, and drills, quizzes, and courses sample it
directly — locked items must not land there.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import uuid

from shared.answers import katakana_to_hiragana, normalize_reading
from shared.cache import clear as clear_cache
from shared.cache import get as cache_get
from shared.cache import put as cache_put
from shared.quiz import (
    _accepted_meanings,
    _accepted_readings,
    _primary_reading,
    pick_distractors,
)

SCHEMA_STATEMENTS = (
    """
    create table if not exists wk_catalog (
        id                 bigint primary key,
        object_type        text not null,
        level              integer not null,
        characters         text,
        slug               text,
        primary_meaning    text,
        meanings           jsonb not null default '[]'::jsonb,
        readings           jsonb not null default '[]'::jsonb,
        parts_of_speech    jsonb not null default '[]'::jsonb,
        context_sentences  jsonb not null default '[]'::jsonb,
        component_ids      bigint[] not null default '{}',
        amalgamation_ids   bigint[] not null default '{}',
        similar_ids        bigint[] not null default '{}',
        audio_url          text,
        lesson_position    integer,
        synced_at          timestamptz
    )
    """,
    """
    create index if not exists wk_catalog_level_idx on wk_catalog (level)
    """,
    """
    create index if not exists wk_catalog_type_idx on wk_catalog (object_type)
    """,
    """
    create table if not exists reading_passages (
        id            text primary key,
        kind          text not null,
        level         integer,
        day           date,
        idx           integer,
        title         text,
        sentences     jsonb not null,
        covers        bigint[] not null default '{}',
        plan_version  integer not null default 1,
        created_at    timestamptz not null default now()
    )
    """,
    """
    create index if not exists reading_passages_level_idx on reading_passages (kind, level)
    """,
    """
    create index if not exists reading_passages_day_idx on reading_passages (day)
    """,
    """
    create table if not exists reading_progress (
        passage_id      text primary key,
        opened_at       timestamptz,
        finished_at     timestamptz,
        lookups         bigint[] not null default '{}',
        quiz_correct    integer,
        quiz_total      integer,
        listen_correct  integer,
        listen_total    integer,
        recall_correct  integer,
        recall_total    integer,
        updated_at      timestamptz
    )
    """,
    """
    create table if not exists reading_sentences (
        source_id   bigint not null,
        idx         integer not null,
        ja          text not null,
        en          text not null default '',
        level       integer not null,
        word_ids    bigint[] not null default '{}',
        kanji_ids   bigint[] not null default '{}',
        max_level   integer not null,
        listenable  boolean not null default false,
        primary key (source_id, idx)
    )
    """,
    """
    create index if not exists reading_sentences_words_idx
        on reading_sentences using gin (word_ids)
    """,
    """
    create index if not exists reading_sentences_kanji_idx
        on reading_sentences using gin (kanji_ids)
    """,
    """
    create index if not exists reading_sentences_max_level_idx
        on reading_sentences (max_level)
    """,
)

# Runs even when the tables already exist. CREATE TABLE is skipped in that case,
# so new columns have to be added on their own.
SCHEMA_ALTERS = (
    """
    alter table reading_progress
        add column if not exists recall_correct integer,
        add column if not exists recall_total integer
    """,
)

_SCHEMA_READY = False


def ensure_schema(db):
    """Create reading tables if needed. Skip after the first successful check."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    ready = False
    try:
        # Key off the newest table. wk_catalog already exists in production,
        # and an early return there would skip every later CREATE.
        ready = bool(db.has_relation("public.reading_sentences"))
    except Exception:
        ready = False
    if not ready:
        for statement in SCHEMA_STATEMENTS:
            db.execute(statement)
    for statement in SCHEMA_ALTERS:
        db.execute(statement)
    _SCHEMA_READY = True


def _id_list(data, key):
    out = []
    for value in data.get(key) or []:
        try:
            out.append(int(value))
        except (TypeError, ValueError):
            continue
    return out


def map_catalog_item(item, now):
    """WK subject resource -> one wk_catalog row, or None when it should be skipped."""
    from shared.inspect import first_audio_url

    data = item.get("data") or {}
    if data.get("hidden_at"):
        return None
    level = data.get("level")
    if level is None or item.get("id") is None:
        return None

    accepted = []
    primary = None
    for entry in data.get("meanings") or []:
        if not isinstance(entry, dict):
            continue
        text = (entry.get("meaning") or "").strip()
        if not text:
            continue
        if entry.get("primary"):
            primary = text
        if entry.get("accepted_answer", True) is not False:
            accepted.append(text)
    if primary and primary not in accepted:
        accepted.insert(0, primary)

    sentences = []
    for entry in data.get("context_sentences") or []:
        if not isinstance(entry, dict):
            continue
        ja = (entry.get("ja") or "").strip()
        if not ja:
            continue
        sentences.append({"ja": ja, "en": (entry.get("en") or "").strip()})

    position = data.get("lesson_position")
    try:
        position = int(position) if position is not None else None
    except (TypeError, ValueError):
        position = None

    return {
        "id": int(item["id"]),
        "object_type": item.get("object"),
        "level": int(level),
        "characters": data.get("characters"),
        "slug": data.get("slug"),
        "primary_meaning": primary,
        "meanings": accepted,
        "readings": data.get("readings") or [],
        "parts_of_speech": [str(part) for part in (data.get("parts_of_speech") or []) if part],
        "context_sentences": sentences,
        "component_ids": _id_list(data, "component_subject_ids"),
        "amalgamation_ids": _id_list(data, "amalgamation_subject_ids"),
        "similar_ids": _id_list(data, "visually_similar_subject_ids"),
        "audio_url": first_audio_url(data),
        "lesson_position": position,
        "synced_at": now,
    }


# --- annotator -------------------------------------------------------------

GURU = 5
MAX_MATCH = 10

_PUNCT = set("。、！？!?.,…・「」『』（）()[]【】〈〉《》〜~：:；;\"'“”‘’—―‐-")
_DROP_RE = re.compile("[" + re.escape("".join(sorted(_PUNCT))) + r"\s]+")


def is_kanji(char):
    code = ord(char)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0xF900 <= code <= 0xFAFF
        or code in (0x3005, 0x3006)  # 々 〆
    )


def is_kana(char):
    code = ord(char)
    return 0x3040 <= code <= 0x309F or 0x30A0 <= code <= 0x30FF or code == 0x30FC


def is_punct(char):
    return char in _PUNCT


def char_class(char):
    if is_kanji(char):
        return "kanji"
    if is_kana(char):
        return "kana"
    if char.isspace():
        return "space"
    if is_punct(char):
        return "punct"
    return "latin"


def is_conjugating(parts):
    """Verbs and い-adjectives. 'adverb' contains the letters of 'verb' and is not one."""
    for part in parts or []:
        text = str(part).casefold().replace("_", "-").strip()
        if text == "verb" or text.endswith(" verb") or " verb" in text:
            return True
        if text in ("i-adjective", "i adjective", "い-adjective", "い adjective"):
            return True
    return False


def kana_stem(characters):
    """Dictionary form minus its inflection ending.

    食べる → 食べ, 行く → 行, 高い → 高. Suru verbs drop the whole する
    (勉強する → 勉強) so 勉強します still matches. Empty when nothing
    with a kanji is left.
    """
    if characters.endswith("する") and len(characters) > 2:
        stem = characters[:-2]
    elif characters and is_kana(characters[-1]):
        stem = characters[:-1]
    else:
        return None
    if not stem or stem == characters or not any(is_kanji(char) for char in stem):
        return None
    return stem


def _all_kana(text):
    return bool(text) and all(is_kana(char) for char in text)


def coerce_entry(raw):
    """Accept a test dict or a catalog-shaped dict and return one lexicon entry."""
    characters = raw.get("characters") or ""
    if not characters or (raw.get("id") is None and raw.get("subject_id") is None):
        return None
    readings_raw = raw.get("readings") or []
    meanings_raw = raw.get("meanings") or []
    if readings_raw and isinstance(readings_raw[0], dict):
        reading = _primary_reading(readings_raw)
        accepted = _accepted_readings(readings_raw)
    else:
        reading = raw.get("reading") or raw.get("primary_reading") or (readings_raw[0] if readings_raw else None)
        accepted = list(readings_raw) if readings_raw else ([reading] if reading else [])
    if meanings_raw and isinstance(meanings_raw[0], dict):
        meanings = _accepted_meanings(meanings_raw, raw.get("meaning") or raw.get("primary_meaning"))
    else:
        meanings = list(meanings_raw)
    if reading:
        reading = katakana_to_hiragana(reading)
    accepted = [katakana_to_hiragana(item) for item in accepted if item]
    meaning = raw.get("meaning") or raw.get("primary_meaning") or (meanings[0] if meanings else None)
    return {
        "id": int(raw["id"] if raw.get("id") is not None else raw["subject_id"]),
        "type": raw.get("type") or raw.get("object_type") or "vocabulary",
        "level": int(raw.get("level") or 0),
        "characters": characters,
        "meaning": meaning,
        "meanings": meanings or ([meaning] if meaning else []),
        "reading": reading,
        "readings": accepted,
        "parts_of_speech": list(raw.get("parts_of_speech") or []),
        "audio_url": raw.get("audio_url"),
        "lesson_position": int(raw.get("lesson_position") or 0),
    }


class Lexicon:
    def __init__(self):
        self.exact = {}
        self.stems = {}
        self.kanji = {}
        self.by_id = {}

    def add_exact(self, surface, entry):
        self.exact.setdefault(surface, []).append(entry)

    def add_stem(self, surface, entry):
        self.stems.setdefault(surface, []).append(entry)


def build_lexicon(rows):
    lexicon = Lexicon()
    for raw in rows or []:
        entry = raw if _is_ready(raw) else coerce_entry(raw)
        if not entry or not entry.get("characters"):
            continue
        lexicon.by_id[entry["id"]] = entry
        characters = entry["characters"]
        if entry["type"] == "kanji" and len(characters) == 1:
            current = lexicon.kanji.get(characters)
            if current is None or (entry["level"], entry["id"]) < (current["level"], current["id"]):
                lexicon.kanji[characters] = entry
            continue
        if _all_kana(characters):
            if len(characters) >= 3:
                lexicon.add_exact(characters, entry)
            continue
        lexicon.add_exact(characters, entry)
        if is_conjugating(entry["parts_of_speech"]):
            stem = kana_stem(characters)
            if stem:
                stemmed = dict(entry)
                stemmed["conjugating"] = True
                stemmed["dictionary"] = characters
                lexicon.add_stem(stem, stemmed)
    return lexicon


def _is_ready(raw):
    return isinstance(raw, dict) and raw.get("reading") is not None and "parts_of_speech" in raw and raw.get("characters")


def surface_runs(surface):
    runs = []
    for char in surface:
        kind = "kanji" if is_kanji(char) else "kana"
        if not is_kanji(char) and not is_kana(char):
            kind = "other"
        if runs and runs[-1][0] == kind:
            runs[-1][1] += char
        else:
            runs.append([kind, char])
    return runs


def align_furigana(surface, reading):
    """Pair kanji runs with the reading. Adjacent kanji share one ruby — the split is unknowable."""
    reading_h = katakana_to_hiragana(reading or "")
    if not surface:
        return []
    if not any(is_kanji(char) for char in surface) or not reading_h:
        return [{"base": surface, "ruby": ""}]
    runs = surface_runs(surface)
    parts = []
    for kind, text in runs:
        if kind == "kanji":
            parts.append("(.+?)")
        else:
            parts.append(re.escape(katakana_to_hiragana(text)))
    matched = re.match("^" + "".join(parts) + "$", reading_h)
    if not matched or any(not group for group in matched.groups()):
        return [{"base": surface, "ruby": reading_h}]
    pieces = []
    group_index = 1
    for kind, text in runs:
        if kind == "kanji":
            pieces.append({"base": text, "ruby": matched.group(group_index)})
            group_index += 1
        else:
            pieces.append({"base": text, "ruby": ""})
    return pieces


def truncate_ruby(pieces, stem):
    """Keep the ruby that covers `stem`, a prefix of the dictionary surface."""
    need = len(stem)
    kept = []
    for piece in pieces:
        if need <= 0:
            break
        base = piece["base"]
        if len(base) <= need:
            kept.append({"base": base, "ruby": piece.get("ruby") or ""})
            need -= len(base)
            continue
        head = base[:need]
        ruby = piece.get("ruby") or ""
        if not ruby:
            kept.append({"base": head, "ruby": ""})
        else:
            kept.append({"base": head, "ruby": ruby})
        need = 0
    return kept


def as_kana(text):
    text = katakana_to_hiragana(text or "")
    if text and all(is_kana(char) for char in text):
        return text
    return None


def ruby_reading(pieces):
    parts = []
    for piece in pieces:
        ruby = piece.get("ruby") or ""
        parts.append(katakana_to_hiragana(ruby if ruby else piece.get("base") or ""))
    return "".join(parts)


def choose_entry(entries, prefer):
    if not entries:
        return None
    if prefer is not None:
        for entry in entries:
            if entry["id"] == prefer:
                return entry
    return min(entries, key=lambda entry: (entry.get("level") or 0, entry["id"]))


def _blank_token(text, kind, cls):
    reading = ""
    if kind == "plain":
        reading = katakana_to_hiragana(text)
    return {
        "text": text,
        "kind": kind,
        "cls": cls,
        "subject_id": None,
        "type": None,
        "level": None,
        "meaning": None,
        "ruby": [{"base": text, "ruby": ""}],
        "reading": reading,
        "readings": [],
        "audio_url": None,
        "stage": None,
        "status": None,
        "target": False,
    }


def _word_token(text, entry, stem):
    dictionary = entry.get("dictionary") or entry["characters"]
    reading = entry.get("reading") or ""
    if stem:
        pieces = truncate_ruby(align_furigana(dictionary, reading), text)
    else:
        pieces = align_furigana(text, reading)
    heard = as_kana(ruby_reading(pieces)) if pieces else as_kana(reading)
    return {
        "text": text,
        "kind": "word",
        "cls": "word",
        "subject_id": entry["id"],
        "type": entry.get("type"),
        "level": entry.get("level"),
        "meaning": entry.get("meaning"),
        "ruby": pieces,
        "reading": heard,
        "readings": list(entry.get("readings") or []),
        "audio_url": entry.get("audio_url"),
        "stage": None,
        "status": None,
        "target": False,
    }


def _kanji_token(char, entry):
    if not entry:
        token = _blank_token(char, "kanji", "kanji")
        token["reading"] = None
        token["ruby"] = [{"base": char, "ruby": ""}]
        return token
    reading = as_kana(entry.get("reading"))
    return {
        "text": char,
        "kind": "kanji",
        "cls": "kanji",
        "subject_id": entry["id"],
        "type": "kanji",
        "level": entry.get("level"),
        "meaning": entry.get("meaning"),
        "ruby": [{"base": char, "ruby": reading}] if reading else [{"base": char, "ruby": ""}],
        "reading": reading,
        "readings": list(entry.get("readings") or []),
        "audio_url": entry.get("audio_url"),
        "stage": None,
        "status": None,
        "target": False,
    }


def _merge_plain(tokens):
    merged = []
    for token in tokens:
        previous = merged[-1] if merged else None
        if (
            previous
            and token["kind"] in ("plain", "punct")
            and previous["kind"] == token["kind"]
            and previous.get("cls") == token.get("cls")
        ):
            previous["text"] += token["text"]
            previous["reading"] = (previous.get("reading") or "") + (token.get("reading") or "")
            previous["ruby"] = [{"base": previous["text"], "ruby": ""}]
            continue
        merged.append(token)
    return merged


def segment(text, lexicon, prefer=None):
    """Longest vocabulary match, exact before stem, then single kanji, then plain runs."""
    if prefer is not None:
        try:
            prefer = int(prefer)
        except (TypeError, ValueError):
            prefer = None
    tokens = []
    index = 0
    length = len(text or "")
    while index < length:
        found = None
        limit = min(MAX_MATCH, length - index)
        for size in range(limit, 0, -1):
            chunk = text[index:index + size]
            exact = lexicon.exact.get(chunk)
            if exact:
                found = (size, choose_entry(exact, prefer), False)
                break
            stems = lexicon.stems.get(chunk)
            if stems:
                found = (size, choose_entry(stems, prefer), True)
                break
        if found:
            size, entry, is_stem = found
            tokens.append(_word_token(text[index:index + size], entry, is_stem))
            index += size
            continue
        char = text[index]
        kind = char_class(char)
        if kind == "kanji":
            tokens.append(_kanji_token(char, lexicon.kanji.get(char)))
        elif kind == "punct":
            tokens.append(_blank_token(char, "punct", "punct"))
        else:
            tokens.append(_blank_token(char, "plain", kind))
        index += 1
    return _merge_plain(tokens)


def token_status(level, stage, reference_level):
    if reference_level is not None and level is not None and int(level) > int(reference_level):
        return "above"
    if stage is None or int(stage) <= 0:
        return "new"
    if int(stage) >= GURU:
        return "known"
    return "learning"


def _covers_target(token, lexicon, targets):
    subject_id = token.get("subject_id")
    if subject_id and subject_id in targets:
        return True
    for char in token.get("text") or "":
        entry = lexicon.kanji.get(char)
        if entry and entry["id"] in targets:
            return True
    return False


def _clean_heard(text):
    return _DROP_RE.sub("", normalize_reading(text or ""))


def annotate_sentence(text, lexicon, prefer=None, stages=None, reference_level=None, targets=None):
    stages = stages or {}
    targets = set(targets or ())
    tokens = segment(text, lexicon, prefer=prefer)
    kana_parts = []
    listenable = True
    for token in tokens:
        subject_id = token.get("subject_id")
        if token["kind"] in ("word", "kanji") and subject_id:
            stage = stages.get(subject_id)
            if stage is None:
                stage = stages.get(int(subject_id)) if subject_id is not None else None
            token["stage"] = stage
            token["status"] = token_status(token.get("level"), stage, reference_level)
            token["target"] = _covers_target(token, lexicon, targets)
        has_kanji = any(is_kanji(char) for char in token.get("text") or "")
        if has_kanji and not token.get("reading"):
            listenable = False
        if token["kind"] == "punct":
            continue
        reading = token.get("reading")
        if reading:
            kana_parts.append(katakana_to_hiragana(reading))
        elif token["kind"] == "plain":
            kana_parts.append(katakana_to_hiragana(token.get("text") or ""))
    return {
        "tokens": tokens,
        "kana": _clean_heard("".join(kana_parts)),
        "listenable": listenable,
    }


def levenshtein(left, right):
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for index, left_char in enumerate(left, 1):
        current = [index]
        for right_index, right_char in enumerate(right, 1):
            current.append(min(
                previous[right_index] + 1,
                current[right_index - 1] + 1,
                previous[right_index - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def diff_ops(expected, got):
    """Merged edit script: eq / del (in expected only) / ins (in got only)."""
    rows = len(expected)
    cols = len(got)
    lengths = [[0] * (cols + 1) for _ in range(rows + 1)]
    for index in range(rows - 1, -1, -1):
        for column in range(cols - 1, -1, -1):
            if expected[index] == got[column]:
                lengths[index][column] = lengths[index + 1][column + 1] + 1
            else:
                lengths[index][column] = max(lengths[index + 1][column], lengths[index][column + 1])
    ops = []
    index = 0
    column = 0
    while index < rows and column < cols:
        if expected[index] == got[column]:
            ops.append(("eq", expected[index]))
            index += 1
            column += 1
        elif lengths[index + 1][column] >= lengths[index][column + 1]:
            ops.append(("del", expected[index]))
            index += 1
        else:
            ops.append(("ins", got[column]))
            column += 1
    while index < rows:
        ops.append(("del", expected[index]))
        index += 1
    while column < cols:
        ops.append(("ins", got[column]))
        column += 1
    merged = []
    for op, char in ops:
        if merged and merged[-1]["op"] == op:
            merged[-1]["text"] += char
        else:
            merged.append({"op": op, "text": char})
    return merged


def grade_dictation(expected_kana, submitted):
    expected = _clean_heard(expected_kana)
    got = _clean_heard(submitted)
    if not expected and not got:
        score = 1.0
    elif not expected:
        score = 0.0
    else:
        score = max(0.0, 1 - levenshtein(expected, got) / len(expected))
    score = round(score, 4)
    if score >= 0.85:
        verdict = "pass"
    elif score >= 0.6:
        verdict = "close"
    else:
        verdict = "miss"
    return {
        "score": score,
        "verdict": verdict,
        "expected": expected,
        "got": got,
        "ops": diff_ops(expected, got),
    }


# --- passages --------------------------------------------------------------

PLAN_VERSION = 1
PASSAGE_SIZE = 6
DAILY_SENTENCES = 8
EXTRA_LEVELS = 5
LEXICON_TTL = 6 * 3600
MAX_CUSTOM_CHARS = 2000
MAX_CUSTOM_SENTENCES = 40
TARGET_TYPES = ("kanji", "vocabulary", "kana_vocabulary")
_SPLIT_RE = re.compile(r"(?<=[。！？])|\n+")


class CatalogMissing(LookupError):
    """wk_catalog has not been synced yet."""


class IndexMissing(LookupError):
    """reading_sentences has not been built yet."""


def _norm(text):
    return (text or "").strip().casefold()


def _json(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, (bytes, bytearray)):
        value = value.decode()
    if isinstance(value, str):
        return json.loads(value) if value else fallback
    return value


def _iso(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _has(db, name):
    try:
        return bool(db.has_relation(name))
    except Exception:
        return False


def _seed(text):
    return int(hashlib.md5(str(text).encode("utf-8")).hexdigest()[:8], 16)


def count_above_kanji(text, lexicon, level):
    count = 0
    for char in text or "":
        if not is_kanji(char):
            continue
        entry = lexicon.kanji.get(char)
        if entry is None or int(entry["level"]) > int(level):
            count += 1
    return count


def covered_ids(text, lexicon, target_ids, source_id=None):
    wanted = {int(item) for item in target_ids}
    found = set()
    if source_id is not None and int(source_id) in wanted:
        found.add(int(source_id))
    for token in segment(text or "", lexicon, prefer=source_id):
        subject_id = token.get("subject_id")
        if subject_id is not None and int(subject_id) in wanted:
            found.add(int(subject_id))
    for char in text or "":
        entry = lexicon.kanji.get(char)
        if entry and entry["id"] in wanted:
            found.add(entry["id"])
    return found


def _target_positions(targets):
    positions = {}
    for target in targets or []:
        position = target.get("lesson_position")
        positions[int(target["id"])] = 10 ** 9 if position is None else int(position)
    return positions


def select_sentences(targets, candidates, limit=None):
    """Greedy set cover. Higher score first; ties break on (source_id, sentence_idx)."""
    positions = _target_positions(targets)
    remaining = set(positions)
    pool = []
    for candidate in candidates or []:
        covers = {int(item) for item in (candidate.get("covers") or ())} & remaining
        pool.append({**candidate, "covers": covers})
    chosen = []
    while remaining:
        best = None
        best_key = None
        for candidate in pool:
            new = candidate["covers"] & remaining
            if not new:
                continue
            score = (
                10 * len(new)
                - 3 * int(candidate.get("above_kanji") or 0)
                - 0.1 * max(0, int(candidate.get("length") or len(candidate.get("ja") or "")) - 40)
            )
            key = (-score, int(candidate.get("source_id") or 0), int(candidate.get("sentence_idx") or 0))
            if best_key is None or key < best_key:
                best_key = key
                best = candidate
        if best is None:
            break
        chosen.append(best)
        remaining -= best["covers"]
        if limit is not None and len(chosen) >= int(limit):
            break
    return chosen


def chunk_passages(targets, chosen, passage_size=PASSAGE_SIZE):
    positions = _target_positions(targets)
    target_ids = set(positions)

    def order_key(candidate):
        covered = [positions[item] for item in candidate["covers"] if item in positions]
        return (
            min(covered) if covered else 10 ** 9,
            int(candidate.get("source_id") or 0),
            int(candidate.get("sentence_idx") or 0),
        )

    ordered = sorted(chosen or [], key=order_key)
    size = max(1, int(passage_size))
    passages = [ordered[index:index + size] for index in range(0, len(ordered), size)]
    covered = set()
    for candidate in ordered:
        covered |= set(candidate["covers"])
    uncovered = sorted(item for item in target_ids if item not in covered)
    return {"chosen": ordered, "passages": passages, "uncovered": uncovered}


def plan_level(targets, candidates, passage_size=PASSAGE_SIZE, limit=None):
    chosen = select_sentences(targets, candidates, limit=limit)
    return chunk_passages(targets, chosen, passage_size)


def build_level_plan(targets, primary, extra, passage_size=PASSAGE_SIZE):
    """Level sentences first. Higher-level sentences only fill what those missed."""
    first = select_sentences(targets, primary)
    covered = set()
    for candidate in first:
        covered |= set(candidate["covers"])
    remaining = [target for target in targets if int(target["id"]) not in covered]
    second = select_sentences(remaining, extra) if remaining and extra else []
    return chunk_passages(targets, list(first) + list(second), passage_size)


def _quiz_shape(item):
    subject_id = item.get("subject_id", item.get("id"))
    meanings_raw = item.get("meanings") or []
    readings_raw = item.get("readings") or []
    if meanings_raw and isinstance(meanings_raw[0], dict):
        meanings = _accepted_meanings(meanings_raw, item.get("meaning") or item.get("primary_meaning"))
    else:
        meanings = [str(entry) for entry in meanings_raw if entry]
    if readings_raw and isinstance(readings_raw[0], dict):
        primary_reading = _primary_reading(readings_raw)
        readings = _accepted_readings(readings_raw)
    else:
        primary_reading = item.get("reading") or item.get("primary_reading") or (readings_raw[0] if readings_raw else None)
        readings = [str(entry) for entry in readings_raw if entry]
    meaning = item.get("meaning") or item.get("primary_meaning") or (meanings[0] if meanings else None)
    object_type = item.get("type") or item.get("object_type") or "vocabulary"
    if object_type == "kana_vocabulary":
        object_type = "vocabulary"
    return {
        "subject_id": int(subject_id),
        "type": object_type,
        "level": int(item.get("level") or 1),
        "characters": item.get("characters"),
        "primary_meaning": meaning,
        "meanings": meanings or ([meaning] if meaning else []),
        "primary_reading": primary_reading,
        "readings": readings or ([primary_reading] if primary_reading else []),
        "decay_score": item.get("decay_score") or 0,
    }


def build_questions(passage_id, sentences, focus_items, pool, translation_pool, with_translation=True):
    """Three checks: translation, meaning, typed reading. Seeded by the passage id."""
    rng = random.Random(_seed(passage_id))
    questions = []
    sentences = [sentence for sentence in (sentences or []) if isinstance(sentence, dict)]

    if with_translation:
        usable = [sentence for sentence in sentences if (sentence.get("en") or "").strip() and (sentence.get("ja") or "").strip()]
        if usable:
            chosen = usable[rng.randrange(len(usable))]
            correct = chosen["en"].strip()
            seen = {_norm(correct)}
            options = []
            bag = list(translation_pool or [])
            rng.shuffle(bag)
            bag.extend((sentence.get("en") or "") for sentence in sentences)
            for text in bag:
                text = (text or "").strip()
                key = _norm(text)
                if not text or key in seen:
                    continue
                seen.add(key)
                options.append(text)
                if len(options) == 3:
                    break
            choices = options + [correct]
            if len(choices) >= 2 and len({_norm(choice) for choice in choices}) == len(choices):
                rng.shuffle(choices)
                questions.append({
                    "id": f"{passage_id}:translation",
                    "type": "translation",
                    "prompt": chosen["ja"],
                    "choices": choices,
                    "answer": choices.index(correct),
                })

    shaped_pool = [_quiz_shape(item) for item in list(pool or []) + list(focus_items or []) if item.get("characters")]
    focus = [_quiz_shape(item) for item in (focus_items or []) if item.get("characters")]
    meaning_items = [item for item in focus if item.get("primary_meaning")]
    meaning_item = None
    if meaning_items:
        rng.shuffle(meaning_items)
        meaning_item = meaning_items[0]
        distractors = pick_distractors(meaning_item, shaped_pool, "meaning", rng, k=3)
        choices = list(dict.fromkeys(list(distractors) + [meaning_item["primary_meaning"]]))
        if len(choices) >= 2:
            rng.shuffle(choices)
            questions.append({
                "id": f"{passage_id}:meaning",
                "type": "meaning",
                "prompt": meaning_item["characters"],
                "subject_id": meaning_item["subject_id"],
                "choices": choices,
                "answer": choices.index(meaning_item["primary_meaning"]),
            })

    reading_items = [item for item in focus if item.get("primary_reading")]
    if reading_items:
        rng.shuffle(reading_items)
        reading_item = reading_items[0]
        if meaning_item and len(reading_items) > 1 and reading_item["subject_id"] == meaning_item["subject_id"]:
            reading_item = next(
                (item for item in reading_items if item["subject_id"] != meaning_item["subject_id"]),
                reading_item,
            )
        accepted = [item for item in (reading_item["readings"] or [reading_item["primary_reading"]]) if item]
        questions.append({
            "id": f"{passage_id}:reading",
            "type": "reading",
            "prompt": reading_item["characters"],
            "meaning": reading_item["primary_meaning"],
            "subject_id": reading_item["subject_id"],
            "accepted": accepted,
        })
    return questions


def split_passage_text(text):
    raw = (text or "").strip()
    if not raw:
        raise ValueError("text is required")
    if len(raw) > MAX_CUSTOM_CHARS:
        raise ValueError("text is too long")
    parts = []
    for piece in _SPLIT_RE.split(raw):
        piece = piece.strip()
        if piece:
            parts.append(piece)
    if not parts:
        raise ValueError("text is required")
    return parts[:MAX_CUSTOM_SENTENCES]


def kanji_from_radicals(radicals, kanji, max_level):
    """Kanji at or below max_level that these radicals build.

    A kanji counts when a radical lists it in amalgamation_ids, or the kanji
    lists that radical in component_ids.
    """
    radical_ids = {int(item["id"]) for item in radicals or [] if item.get("id") is not None}
    listed = set()
    for item in radicals or []:
        for child in item.get("amalgamation_ids") or []:
            try:
                listed.add(int(child))
            except (TypeError, ValueError):
                continue
    chosen = []
    for item in kanji or []:
        if item.get("type") not in (None, "kanji"):
            continue
        try:
            level = int(item.get("level") or 0)
            subject_id = int(item["id"])
        except (TypeError, ValueError):
            continue
        if level > int(max_level):
            continue
        components = set()
        for part in item.get("component_ids") or []:
            try:
                components.add(int(part))
            except (TypeError, ValueError):
                continue
        if subject_id in listed or components & radical_ids:
            chosen.append(item)
    chosen.sort(key=lambda item: (int(item.get("level") or 0), int(item["id"])))
    return chosen


def candidates_from_rows(rows, lexicon, target_ids, reference_level):
    found = []
    seen = set()
    for row in rows or []:
        if row.get("type") == "kanji":
            continue
        for index, sentence in enumerate(row.get("sentences") or []):
            if not isinstance(sentence, dict):
                continue
            ja = (sentence.get("ja") or "").strip()
            if not ja:
                continue
            key = (int(row["id"]), index, ja)
            if key in seen:
                continue
            seen.add(key)
            covers = covered_ids(ja, lexicon, target_ids, source_id=row["id"])
            if not covers:
                continue
            found.append({
                "source_id": int(row["id"]),
                "sentence_idx": index,
                "ja": ja,
                "en": (sentence.get("en") or "").strip(),
                "covers": covers,
                "above_kanji": count_above_kanji(ja, lexicon, reference_level),
                "length": len(ja),
            })
    return found


# --- database --------------------------------------------------------------

_LEXICON_SQL = """
select id, object_type, level, characters, primary_meaning, meanings, readings,
       parts_of_speech, audio_url, lesson_position
from wk_catalog
where characters is not null and characters <> ''
  and object_type in ('kanji', 'vocabulary', 'kana_vocabulary')
"""

_LEVEL_SQL = """
select id, object_type, level, characters, primary_meaning, meanings, readings,
       context_sentences, lesson_position
from wk_catalog
where level = %s
  and object_type in ('kanji', 'vocabulary', 'kana_vocabulary')
  and characters is not null and characters <> ''
order by lesson_position nulls last, id
"""


def _catalog_item(row):
    return {
        "id": int(row[0]),
        "type": row[1],
        "level": int(row[2]),
        "characters": row[3],
        "meaning": row[4],
        "meanings": _json(row[5], []),
        "readings": _json(row[6], []),
        "sentences": _json(row[7], []) if len(row) > 7 else [],
        "lesson_position": int(row[8] or 0) if len(row) > 8 and row[8] is not None else 0,
    }


def catalog_ready(db):
    ensure_schema(db)
    if not _has(db, "public.wk_catalog"):
        return False
    rows = db.execute("select 1 from wk_catalog limit 1", fetch=True)
    return bool(rows)


def require_catalog(db):
    if not catalog_ready(db):
        raise CatalogMissing("catalog_missing")


def index_rows_for_subject(subject, lexicon):
    """One reading_sentences row per context sentence of a catalog subject.

    word_ids are matched vocabulary, in order, without duplicates. kanji_ids
    include standalone kanji and the kanji inside those words. max_level is
    the highest matched token, or the source level when nothing matched.
    """
    sentences = subject.get("context_sentences")
    if sentences is None:
        sentences = subject.get("sentences") or []
    source_id = int(subject["id"])
    source_level = int(subject.get("level") or 0)
    rows = []
    for idx, sentence in enumerate(sentences or []):
        if isinstance(sentence, str):
            ja, en = sentence.strip(), ""
        elif isinstance(sentence, dict):
            ja = (sentence.get("ja") or "").strip()
            en = (sentence.get("en") or "").strip()
        else:
            continue
        if not ja:
            continue
        annotated = annotate_sentence(ja, lexicon, prefer=source_id)
        word_ids = []
        seen_words = set()
        kanji_ids = []
        seen_kanji = set()
        levels = []

        def _take_kanji(char):
            entry = lexicon.kanji.get(char)
            if not entry:
                return
            kanji_id = int(entry["id"])
            if kanji_id in seen_kanji:
                return
            seen_kanji.add(kanji_id)
            kanji_ids.append(kanji_id)
            if entry.get("level") is not None:
                levels.append(int(entry["level"]))

        for token in annotated["tokens"]:
            subject_id = token.get("subject_id")
            if token["kind"] == "word" and subject_id is not None:
                word_id = int(subject_id)
                if word_id not in seen_words:
                    seen_words.add(word_id)
                    word_ids.append(word_id)
                if token.get("level") is not None:
                    levels.append(int(token["level"]))
                for char in token.get("text") or "":
                    if is_kanji(char):
                        _take_kanji(char)
            elif token["kind"] == "kanji" and subject_id is not None:
                kanji_id = int(subject_id)
                if kanji_id not in seen_kanji:
                    seen_kanji.add(kanji_id)
                    kanji_ids.append(kanji_id)
                if token.get("level") is not None:
                    levels.append(int(token["level"]))
        rows.append({
            "source_id": source_id,
            "idx": idx,
            "ja": ja,
            "en": en,
            "level": source_level,
            "word_ids": word_ids,
            "kanji_ids": kanji_ids,
            "max_level": max(levels) if levels else source_level,
            "listenable": bool(annotated["listenable"]),
        })
    return rows


SENTENCE_CHUNK = 1000

_SENTENCE_UPSERT = """
insert into reading_sentences
    (source_id, idx, ja, en, level, word_ids, kanji_ids, max_level, listenable)
select source_id, idx, ja, en, level, word_ids, kanji_ids, max_level, listenable
from jsonb_to_recordset(%s::jsonb) as row(
    source_id bigint,
    idx integer,
    ja text,
    en text,
    level integer,
    word_ids bigint[],
    kanji_ids bigint[],
    max_level integer,
    listenable boolean
)
on conflict (source_id, idx) do update set
    ja = excluded.ja,
    en = excluded.en,
    level = excluded.level,
    word_ids = excluded.word_ids,
    kanji_ids = excluded.kanji_ids,
    max_level = excluded.max_level,
    listenable = excluded.listenable
"""


def rebuild_sentence_index(db):
    """Replace reading_sentences from every catalog context sentence. One pass."""
    ensure_schema(db)
    lexicon = load_lexicon(db)
    rows = db.execute(
        """
        select id, level, context_sentences
        from wk_catalog
        where context_sentences <> '[]'::jsonb
        """,
        fetch=True,
    )
    indexed = []
    for source_id, level, sentences in rows:
        indexed.extend(index_rows_for_subject(
            {"id": int(source_id), "level": int(level or 0), "context_sentences": _json(sentences, [])},
            lexicon,
        ))
    db.execute("truncate reading_sentences")
    for start in range(0, len(indexed), SENTENCE_CHUNK):
        batch = indexed[start:start + SENTENCE_CHUNK]
        db.execute(_SENTENCE_UPSERT, [json.dumps(batch, ensure_ascii=False)])
    return len(indexed)


def sentence_index_ready(db):
    ensure_schema(db)
    if not _has(db, "public.reading_sentences"):
        return False
    rows = db.execute("select 1 from reading_sentences limit 1", fetch=True)
    return bool(rows)


def require_index(db):
    require_catalog(db)
    if not sentence_index_ready(db):
        raise IndexMissing("index_missing")


def unknown_word(word_ids, levels_by_id, stages, user_level):
    """The single below-Guru word, when every word is in levels 1..user_level.

    A missing stage counts as unknown. Any other count, or a word outside
    that range, is not a just-right sentence. fetch_feed's SQL matches this.
    """
    if not word_ids:
        return None
    unknown = None
    ceiling = int(user_level)
    for word_id in word_ids:
        word_id = int(word_id)
        level = levels_by_id.get(word_id)
        if level is None or int(level) < 1 or int(level) > ceiling:
            return None
        stage = stages.get(word_id, 0) if stages else 0
        try:
            stage = int(stage or 0)
        except (TypeError, ValueError):
            stage = 0
        if stage < GURU:
            if unknown is not None:
                return None
            unknown = word_id
    return unknown


def _stage_source_sql(db):
    """Course stage overrides the WaniKani assignment, matching fetch_stages."""
    parts = []
    if _has(db, "public.wk_assignments"):
        parts.append("select subject_id, srs_stage, 1 as src from wk_assignments")
    if _has(db, "public.course_items"):
        parts.append("select subject_id, srs_stage, 2 as src from course_items")
    if not parts:
        return "select null::bigint as subject_id, 0::int as srs_stage where false"
    joined = " union all ".join(parts)
    return (
        "select distinct on (subject_id) subject_id, srs_stage "
        f"from ({joined}) raw order by subject_id, src desc"
    )


def fetch_feed(db, offset=0):
    """One just-right sentence for today. Order is seeded by the WIB day."""
    from shared.daily import today as wib_today

    require_index(db)
    try:
        offset = int(offset or 0)
    except (TypeError, ValueError):
        raise ValueError("offset must be a number")
    if offset < 0:
        raise ValueError("offset must be zero or more")
    reached = user_level(db)
    day = wib_today()
    seed = day.isoformat()
    picked = f"""
        select s.source_id, s.idx, s.ja, s.en, s.word_ids, u.unknown_id
        from reading_sentences s
        join lateral (
            select
                count(*) as seen,
                count(*) filter (where c.level < 1 or c.level > %s) as above,
                count(*) filter (where coalesce(st.srs_stage, 0) < {GURU}) as unknown_count,
                (array_agg(w.word_id order by w.ord)
                    filter (where coalesce(st.srs_stage, 0) < {GURU}))[1] as unknown_id
            from unnest(s.word_ids) with ordinality as w(word_id, ord)
            join wk_catalog c on c.id = w.word_id
            left join stage st on st.subject_id = w.word_id
        ) u on u.seen = cardinality(s.word_ids)
           and u.above = 0
           and u.unknown_count = 1
        where s.max_level between 1 and %s
          and cardinality(s.word_ids) >= 1
    """
    sql = f"""
        with stage as ({_stage_source_sql(db)}),
        picked as ({picked})
        select source_id, idx, ja, en, word_ids, unknown_id, count(*) over () as total
        from picked
        order by md5(source_id::text || ':' || idx::text || ':' || %s)
        offset %s
        limit 1
    """
    rows = db.execute(sql, [reached, reached, seed, offset], fetch=True)
    if not rows:
        total = db.execute(
            f"with stage as ({_stage_source_sql(db)}), picked as ({picked}) select count(*) from picked",
            [reached, reached],
            fetch=True,
        )
        return {
            "empty": True,
            "day": seed,
            "offset": offset,
            "total": int(total[0][0] if total else 0),
        }
    source_id, idx, ja, en, word_ids, unknown_id, total = rows[0]
    unknown_id = int(unknown_id)
    lexicon = load_lexicon(db)
    annotated = annotate_sentence(
        ja,
        lexicon,
        prefer=int(source_id),
        stages=fetch_stages(db, [int(item) for item in (word_ids or [])] + [unknown_id]),
        reference_level=reached,
        targets={unknown_id},
    )
    return {
        "empty": False,
        "day": seed,
        "offset": offset,
        "total": int(total),
        "unknown_id": unknown_id,
        "sentence": {
            "ja": ja,
            "en": en or "",
            "source_id": int(source_id),
            "idx": int(idx),
            "kana": annotated["kana"],
            "listenable": annotated["listenable"],
            "tokens": annotated["tokens"],
        },
    }


def record_feed_again(db, subject_id):
    """Again on the feed is a lookup, and a lookup of a started word is a drill miss."""
    require_index(db)
    subject_id = int(subject_id)
    rows = db.execute("select level from wk_catalog where id = %s", [subject_id], fetch=True)
    if not rows:
        raise ValueError("subject not found")
    item_level = int(rows[0][0] or 0)
    stage = fetch_stages(db, [subject_id]).get(subject_id, 0)
    recorded = False
    if stage >= 1 and item_level <= user_level(db):
        from shared.drill import record_lookup
        record_lookup(db, subject_id)
        recorded = True
    return {"ok": True, "recorded_miss": recorded, "subject_id": subject_id}


def user_level(db):
    if not _has(db, "public.wk_subjects"):
        return 1
    rows = db.execute("select coalesce(max(level), 1) from wk_subjects", fetch=True)
    return int(rows[0][0] or 1) if rows else 1


def load_lexicon(db):
    cached = cache_get("reader:lexicon", LEXICON_TTL)
    if cached is not None:
        return cached
    rows = db.execute(_LEXICON_SQL, fetch=True)
    entries = [
        {
            "id": row[0],
            "object_type": row[1],
            "level": row[2],
            "characters": row[3],
            "primary_meaning": row[4],
            "meanings": row[5],
            "readings": row[6],
            "parts_of_speech": row[7],
            "audio_url": row[8],
            "lesson_position": row[9],
        }
        for row in rows
    ]
    lexicon = build_lexicon(entries)
    cache_put("reader:lexicon", lexicon)
    return lexicon


def fetch_stages(db, ids):
    ids = sorted({int(item) for item in ids if item is not None})
    stages = {}
    if not ids:
        return stages
    if _has(db, "public.wk_assignments"):
        rows = db.execute(
            "select subject_id, srs_stage from wk_assignments where subject_id = any(%s)",
            [ids],
            fetch=True,
        )
        for subject_id, stage in rows:
            stages[int(subject_id)] = int(stage or 0)
    if _has(db, "public.course_items"):
        rows = db.execute(
            "select subject_id, srs_stage from course_items where subject_id = any(%s)",
            [ids],
            fetch=True,
        )
        for subject_id, stage in rows:
            stages[int(subject_id)] = int(stage or 0)
    return stages


def _level_items(db, level):
    return [_catalog_item(row) for row in db.execute(_LEVEL_SQL, [level], fetch=True)]


def _extra_vocab(db, level, characters):
    safe = []
    for char in characters or []:
        if char and char not in safe and char not in "\\]^-":
            safe.append(char)
    if not safe:
        return []
    pattern = "[" + "".join(safe) + "]"
    rows = db.execute(
        """
        select id, object_type, level, characters, primary_meaning, meanings, readings,
               context_sentences, lesson_position
        from wk_catalog
        where object_type in ('vocabulary', 'kana_vocabulary')
          and level between %s and %s
          and characters ~ %s
        order by level, lesson_position nulls last, id
        limit 400
        """,
        [level + 1, min(60, level + EXTRA_LEVELS), pattern],
        fetch=True,
    )
    return [_catalog_item(row) for row in rows]


def _insert_passage(db, passage_id, kind, level, day, idx, title, sentences, covers):
    db.execute(
        """
        insert into reading_passages
          (id, kind, level, day, idx, title, sentences, covers, plan_version)
        values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
        on conflict (id) do nothing
        """,
        [
            passage_id,
            kind,
            level,
            day,
            idx,
            title,
            json.dumps(sentences, ensure_ascii=False),
            [int(item) for item in covers],
            PLAN_VERSION,
        ],
    )


def ensure_level_passages(db, level, lexicon=None):
    ensure_schema(db)
    existing = db.execute(
        """
        select id, plan_version from reading_passages
        where kind = 'level' and level = %s
        order by idx
        """,
        [level],
        fetch=True,
    )
    if existing:
        current = all(int(row[1] or 0) == PLAN_VERSION for row in existing)
        if current:
            return
        ids = [row[0] for row in existing]
        touched = db.execute(
            """
            select 1 from reading_progress
            where passage_id = any(%s)
              and (
                finished_at is not null
                or cardinality(lookups) > 0
                or quiz_total is not null
                or listen_total is not null
              )
            limit 1
            """,
            [ids],
            fetch=True,
        )
        if touched:
            return
        db.execute("delete from reading_passages where kind = 'level' and level = %s", [level])

    lexicon = lexicon or load_lexicon(db)
    items = _level_items(db, level)
    target_ids = {item["id"] for item in items}
    primary = candidates_from_rows(
        [item for item in items if item["type"] != "kanji"],
        lexicon,
        target_ids,
        level,
    )
    covered = set()
    for candidate in select_sentences(items, primary):
        covered |= set(candidate["covers"])
    missing_kanji = [item["characters"] for item in items if item["type"] == "kanji" and item["id"] not in covered]
    extra_rows = _extra_vocab(db, level, missing_kanji) if missing_kanji else []
    extra = candidates_from_rows(extra_rows, lexicon, target_ids, level)
    plan = build_level_plan(items, primary, extra)
    for index, chunk in enumerate(plan["passages"], start=1):
        covers = sorted({int(item) for candidate in chunk for item in candidate["covers"]})
        sentences = [
            {"ja": candidate["ja"], "en": candidate["en"], "source_id": candidate["source_id"]}
            for candidate in chunk
        ]
        _insert_passage(
            db,
            f"level:{level}:{index}",
            "level",
            level,
            None,
            index,
            f"Reading {index}",
            sentences,
            covers,
        )


def _target_count(db, level):
    rows = db.execute(
        """
        select count(*) from wk_catalog
        where level = %s
          and object_type in ('kanji', 'vocabulary', 'kana_vocabulary')
          and characters is not null and characters <> ''
        """,
        [level],
        fetch=True,
    )
    return int(rows[0][0] or 0) if rows else 0


def level_coverage(db, level):
    total = _target_count(db, level)
    rows = db.execute(
        """
        select p.covers
        from reading_passages p
        join reading_progress g on g.passage_id = p.id
        where p.kind = 'level' and p.level = %s and g.finished_at is not null
        """,
        [level],
        fetch=True,
    )
    target_rows = db.execute(
        """
        select id from wk_catalog
        where level = %s
          and object_type in ('kanji', 'vocabulary', 'kana_vocabulary')
          and characters is not null and characters <> ''
        """,
        [level],
        fetch=True,
    )
    target_ids = {int(row[0]) for row in target_rows}
    covered = set()
    for (covers,) in rows:
        for item in covers or []:
            covered.add(int(item))
    covered &= target_ids
    return {
        "covered": len(covered),
        "total": total,
        "ratio": (len(covered) / total) if total else 0,
    }


def _passage_tuple(db, passage_id):
    rows = db.execute(
        """
        select id, kind, level, day, idx, title, sentences, covers, plan_version
        from reading_passages where id = %s
        """,
        [passage_id],
        fetch=True,
    )
    return rows[0] if rows else None


def _progress_tuple(db, passage_id):
    rows = db.execute(
        """
        select opened_at, finished_at, lookups, quiz_correct, quiz_total, listen_correct, listen_total
        from reading_progress where passage_id = %s
        """,
        [passage_id],
        fetch=True,
    )
    return rows[0] if rows else None


def _progress_payload(row):
    if not row:
        return {
            "opened": False,
            "finished": False,
            "lookups": [],
            "quiz_correct": None,
            "quiz_total": None,
            "listen_correct": None,
            "listen_total": None,
        }
    return {
        "opened": row[0] is not None,
        "finished": row[1] is not None,
        "finished_at": _iso(row[1]),
        "lookups": [int(item) for item in (row[2] or [])],
        "quiz_correct": row[3],
        "quiz_total": row[4],
        "listen_correct": row[5],
        "listen_total": row[6],
    }


def _mark_opened(db, passage_id):
    db.execute(
        """
        insert into reading_progress (passage_id, opened_at, updated_at)
        values (%s, now(), now())
        on conflict (passage_id) do update set
          opened_at = coalesce(reading_progress.opened_at, excluded.opened_at),
          updated_at = now()
        """,
        [passage_id],
    )


def _items_by_ids(db, ids):
    ids = sorted({int(item) for item in ids if item is not None})
    if not ids:
        return []
    rows = db.execute(
        """
        select id, object_type, level, characters, primary_meaning, meanings, readings
        from wk_catalog where id = any(%s)
        """,
        [ids],
        fetch=True,
    )
    return [
        {
            "id": int(row[0]),
            "type": row[1],
            "level": int(row[2]),
            "characters": row[3],
            "meaning": row[4],
            "meanings": _json(row[5], []),
            "readings": _json(row[6], []),
        }
        for row in rows
    ]


def _distractor_pool(db, level):
    rows = db.execute(
        """
        select id, object_type, level, characters, primary_meaning, meanings, readings
        from wk_catalog
        where level between %s and %s
          and object_type in ('kanji', 'vocabulary', 'kana_vocabulary')
          and primary_meaning is not null
        order by id
        limit 300
        """,
        [max(1, int(level) - 1), min(60, int(level) + 1)],
        fetch=True,
    )
    return _items_by_ids_rows(rows)


def _items_by_ids_rows(rows):
    return [
        {
            "id": int(row[0]),
            "type": row[1],
            "level": int(row[2]),
            "characters": row[3],
            "meaning": row[4],
            "meanings": _json(row[5], []),
            "readings": _json(row[6], []),
        }
        for row in rows
    ]


def _translation_pool(db, level, passage_id):
    if level is None:
        return []
    rows = db.execute(
        """
        select sentences from reading_passages
        where kind = 'level' and level = %s and id <> %s
        """,
        [level, passage_id],
        fetch=True,
    )
    texts = []
    for (raw,) in rows:
        for sentence in _json(raw, []):
            english = (sentence.get("en") or "").strip()
            if english:
                texts.append(english)
    return texts


def _annotate_saved(sentences, lexicon, stages, reference, covers):
    rendered = []
    for sentence in sentences:
        block = annotate_sentence(
            sentence.get("ja") or "",
            lexicon,
            prefer=sentence.get("source_id"),
            stages=stages,
            reference_level=reference,
            targets=set(covers),
        )
        block["ja"] = sentence.get("ja") or ""
        block["en"] = sentence.get("en") or ""
        block["source_id"] = sentence.get("source_id")
        rendered.append(block)
    return rendered


def render_passage(db, passage_id, mark_opened=True):
    require_catalog(db)
    row = _passage_tuple(db, passage_id)
    if not row:
        raise ValueError("passage not found")
    passage_id, kind, level, day, idx, title, sentences_raw, covers_raw, _version = row
    sentences = _json(sentences_raw, [])
    covers = [int(item) for item in (covers_raw or [])]
    reference = int(level) if kind == "level" and level else user_level(db)
    lexicon = load_lexicon(db)
    # One pass to learn which subjects are on the page, then again with stages.
    preview = _annotate_saved(sentences, lexicon, {}, reference, covers)
    ids = set(covers)
    for sentence in sentences:
        if sentence.get("source_id"):
            ids.add(int(sentence["source_id"]))
    for block in preview:
        for token in block["tokens"]:
            if token.get("subject_id"):
                ids.add(int(token["subject_id"]))
    stages = fetch_stages(db, ids)
    rendered = _annotate_saved(sentences, lexicon, stages, reference, covers)
    focus = [item for item in _items_by_ids(db, covers) if item.get("characters")]
    pool_level = reference or 1
    questions = build_questions(
        passage_id,
        sentences,
        focus,
        _distractor_pool(db, pool_level),
        _translation_pool(db, level if kind == "level" else None, passage_id),
        with_translation=kind != "custom",
    )
    if mark_opened:
        _mark_opened(db, passage_id)
    progress = _progress_payload(_progress_tuple(db, passage_id))
    siblings = []
    if kind == "level" and level:
        siblings = db.execute(
            """
            select id, idx from reading_passages
            where kind = 'level' and level = %s
            order by idx
            """,
            [level],
            fetch=True,
        )
    next_id = None
    total = len(siblings) or (1 if idx else 0)
    if siblings and idx:
        for sib_id, sib_idx in siblings:
            if sib_idx and int(sib_idx) == int(idx) + 1:
                next_id = sib_id
                break
    coverage = level_coverage(db, int(level)) if kind == "level" and level else None
    return {
        "id": passage_id,
        "kind": kind,
        "level": int(level) if level else None,
        "day": _iso(day),
        "idx": int(idx) if idx else None,
        "of": total or None,
        "title": title,
        "next_id": next_id,
        "coverage": coverage,
        "sentences": rendered,
        "questions": questions,
        "progress": progress,
        "reference_level": reference,
    }


def fetch_level_view(db, level):
    require_catalog(db)
    level = int(level)
    if level < 1 or level > 60:
        raise ValueError("level must be between 1 and 60")
    ensure_level_passages(db, level)
    rows = db.execute(
        """
        select p.id, p.idx, p.title, p.sentences, p.covers,
               g.opened_at is not null, g.finished_at is not null
        from reading_passages p
        left join reading_progress g on g.passage_id = p.id
        where p.kind = 'level' and p.level = %s
        order by p.idx
        """,
        [level],
        fetch=True,
    )
    passages = []
    covered = set()
    for passage_id, idx, title, sentences_raw, covers_raw, opened, finished in rows:
        covers = [int(item) for item in (covers_raw or [])]
        covered.update(covers)
        passages.append({
            "id": passage_id,
            "idx": int(idx) if idx else None,
            "title": title,
            "sentences": len(_json(sentences_raw, [])),
            "opened": bool(opened),
            "finished": bool(finished),
        })
    items = _level_items(db, level)
    uncovered = [
        {"id": item["id"], "characters": item["characters"], "meaning": item["meaning"], "type": item["type"]}
        for item in items
        if item["id"] not in covered
    ]
    reached = user_level(db)
    coverage = level_coverage(db, level)
    return {
        "level": level,
        "user_level": reached,
        "preview": level > reached,
        "coverage": coverage,
        "passages": passages,
        "uncovered": uncovered,
    }


def fetch_index(db):
    require_catalog(db)
    reached = user_level(db)
    counts = {}
    for level, count in db.execute(
        """
        select level, count(*) from wk_catalog
        where object_type in ('kanji', 'vocabulary', 'kana_vocabulary')
          and characters is not null and characters <> ''
        group by level
        """,
        fetch=True,
    ):
        counts[int(level)] = int(count)
    progress = {level: {"passages": 0, "finished": 0, "covered": set()} for level in range(1, 61)}
    for level, covers, finished in db.execute(
        """
        select p.level, p.covers, g.finished_at is not null
        from reading_passages p
        left join reading_progress g on g.passage_id = p.id
        where p.kind = 'level'
        """,
        fetch=True,
    ):
        if not level or int(level) not in progress:
            continue
        bucket = progress[int(level)]
        bucket["passages"] += 1
        if finished:
            bucket["finished"] += 1
            for item in covers or []:
                bucket["covered"].add(int(item))
    levels = []
    for level in range(1, 61):
        total = counts.get(level, 0)
        covered = len(progress[level]["covered"])
        levels.append({
            "level": level,
            "targets": total,
            "passages": progress[level]["passages"],
            "finished": progress[level]["finished"],
            "coverage": (covered / total) if total else 0,
            "preview": level > reached,
        })
    return {
        "catalog_ready": True,
        "user_level": reached,
        "levels": levels,
        "daily": daily_summary(db),
    }


def daily_summary(db):
    """Whether today's read already exists. Does not build it."""
    from shared.daily import today as wib_today

    day = wib_today()
    passage_id = f"daily:{day.isoformat()}"
    rows = db.execute(
        """
        select jsonb_array_length(p.sentences), g.finished_at is not null
        from reading_passages p
        left join reading_progress g on g.passage_id = p.id
        where p.id = %s
        """,
        [passage_id],
        fetch=True,
    )
    if not rows:
        return {
            "id": passage_id,
            "day": day.isoformat(),
            "ready": False,
            "finished": False,
            "empty": False,
            "sentences": 0,
        }
    return {
        "id": passage_id,
        "day": day.isoformat(),
        "ready": True,
        "finished": bool(rows[0][1]),
        "empty": int(rows[0][0] or 0) == 0,
        "sentences": int(rows[0][0] or 0),
    }


def _items_with_sentences(db, ids):
    ids = sorted({int(item) for item in ids if item is not None})
    if not ids:
        return []
    rows = db.execute(
        """
        select id, object_type, level, characters, primary_meaning, meanings, readings,
               context_sentences, lesson_position
        from wk_catalog where id = any(%s)
        """,
        [ids],
        fetch=True,
    )
    return [_catalog_item(row) for row in rows]


def _vocab_containing(db, low, high, characters, exclude_ids):
    safe = []
    for char in characters or []:
        if char and char not in safe and char not in "\\]^-":
            safe.append(char)
    if not safe or high < low:
        return []
    rows = db.execute(
        """
        select id, object_type, level, characters, primary_meaning, meanings, readings,
               context_sentences, lesson_position
        from wk_catalog
        where object_type in ('vocabulary', 'kana_vocabulary')
          and level between %s and %s
          and not (id = any(%s))
          and characters ~ %s
        order by level, lesson_position nulls last, id
        limit 400
        """,
        [low, high, list(exclude_ids or [0]), "[" + "".join(safe) + "]"],
        fetch=True,
    )
    return [_catalog_item(row) for row in rows]


def _kanji_built_from(db, radical_ids, max_level):
    radical_ids = [int(item) for item in radical_ids or []]
    if not radical_ids:
        return []
    radical_rows = db.execute(
        "select id, amalgamation_ids from wk_catalog where id = any(%s) and object_type = 'radical'",
        [radical_ids],
        fetch=True,
    )
    radicals = [
        {"id": int(row[0]), "amalgamation_ids": [int(item) for item in (row[1] or [])]}
        for row in radical_rows
    ]
    listed = sorted({int(child) for item in radicals for child in item["amalgamation_ids"]})
    rows = db.execute(
        """
        select id, object_type, level, characters, primary_meaning, meanings, readings,
               context_sentences, lesson_position, component_ids
        from wk_catalog
        where object_type = 'kanji'
          and level <= %s
          and characters is not null and characters <> ''
          and (id = any(%s) or component_ids && %s::bigint[])
        order by level, lesson_position nulls last, id
        """,
        [max_level, listed or [0], radical_ids],
        fetch=True,
    )
    kanji = []
    for row in rows:
        item = _catalog_item(row[:9])
        item["component_ids"] = [int(part) for part in (row[9] or [])]
        kanji.append(item)
    return kanji_from_radicals(radicals, kanji, max_level)


def build_daily_read(db):
    """One passage from today's set, frozen for the WIB day.

    A radicals-only set is read through the kanji those radicals build.
    Empty only when nothing usable turns up.
    """
    from shared.daily import fetch_daily, today as wib_today

    require_catalog(db)
    day = wib_today()
    passage_id = f"daily:{day.isoformat()}"
    if _passage_tuple(db, passage_id):
        return render_passage(db, passage_id)

    fetch_daily(db, with_items=False)
    rows = db.execute("select subject_ids from daily_sets where day = %s", [day], fetch=True)
    subject_ids = [int(item) for item in ((rows[0][0] if rows else []) or [])]
    items = _items_with_sentences(db, subject_ids)
    targets = [item for item in items if item["type"] in TARGET_TYPES]
    reached = user_level(db)
    title = "Today's read"
    if not targets:
        radical_ids = [item["id"] for item in items if item.get("type") == "radical"]
        targets = _kanji_built_from(db, radical_ids, reached)
        title = "Built from today's radicals"
    if not targets:
        return {"empty": True, "id": passage_id, "day": day.isoformat(), "kind": "daily"}
    lexicon = load_lexicon(db)
    target_ids = {item["id"] for item in targets}
    primary = candidates_from_rows(
        [item for item in targets if item["type"] != "kanji"],
        lexicon,
        target_ids,
        reached,
    )
    kanji_chars = [item["characters"] for item in targets if item["type"] == "kanji" and item.get("characters")]
    extra = candidates_from_rows(
        _vocab_containing(db, 1, reached, kanji_chars, target_ids),
        lexicon,
        target_ids,
        reached,
    )
    plan = plan_level(targets, primary + extra, passage_size=DAILY_SENTENCES, limit=DAILY_SENTENCES)
    chunk = plan["passages"][0] if plan["passages"] else []
    if not chunk:
        return {"empty": True, "id": passage_id, "day": day.isoformat(), "kind": "daily"}

    covers = sorted({int(item) for candidate in chunk for item in candidate["covers"]})
    sentences = [
        {"ja": candidate["ja"], "en": candidate["en"], "source_id": candidate["source_id"]}
        for candidate in chunk
    ]
    _insert_passage(db, passage_id, "daily", reached, day, 1, title, sentences, covers)
    return render_passage(db, passage_id)


def note_lookup(db, passage_id, subject_id):
    require_catalog(db)
    subject_id = int(subject_id)
    if not _passage_tuple(db, passage_id):
        raise ValueError("passage not found")
    db.execute(
        """
        insert into reading_progress (passage_id, opened_at, lookups, updated_at)
        values (%s, now(), ARRAY[%s]::bigint[], now())
        on conflict (passage_id) do update set
          lookups = case
            when %s = any(reading_progress.lookups) then reading_progress.lookups
            else array_append(reading_progress.lookups, %s)
          end,
          updated_at = now()
        """,
        [passage_id, subject_id, subject_id, subject_id],
    )
    recorded = False
    rows = db.execute("select level from wk_catalog where id = %s", [subject_id], fetch=True)
    if rows:
        item_level = int(rows[0][0] or 0)
        stage = fetch_stages(db, [subject_id]).get(subject_id, 0)
        if stage >= 1 and item_level <= user_level(db):
            from shared.drill import record_lookup
            record_lookup(db, subject_id)
            recorded = True
    saved = _progress_tuple(db, passage_id)
    return {
        "ok": True,
        "recorded_miss": recorded,
        "lookups": [int(item) for item in ((saved[2] if saved else []) or [])],
    }


def grade_passage_dictation(db, passage_id, index, text):
    rendered = render_passage(db, passage_id, mark_opened=True)
    try:
        index = int(index)
    except (TypeError, ValueError):
        raise ValueError("sentence not found")
    sentences = rendered["sentences"]
    if index < 0 or index >= len(sentences):
        raise ValueError("sentence not found")
    sentence = sentences[index]
    if not sentence.get("listenable"):
        raise ValueError("this sentence has no reading to dictate")
    graded = grade_dictation(sentence.get("kana") or "", text)
    graded["index"] = index
    return graded


def finish_passage(
    db,
    passage_id,
    quiz_correct,
    quiz_total,
    listen_correct,
    listen_total,
    recall_correct=None,
    recall_total=None,
):
    row = _passage_tuple(db, passage_id)
    if not row:
        raise ValueError("passage not found")

    def _count(value):
        if value is None or value == "":
            return None
        number = int(value)
        if number < 0:
            raise ValueError("counts must be zero or more")
        return number

    quiz_correct = _count(quiz_correct)
    quiz_total = _count(quiz_total)
    listen_correct = _count(listen_correct)
    listen_total = _count(listen_total)
    recall_correct = _count(recall_correct)
    recall_total = _count(recall_total)
    db.execute(
        """
        insert into reading_progress (
          passage_id, opened_at, finished_at,
          quiz_correct, quiz_total, listen_correct, listen_total,
          recall_correct, recall_total, updated_at
        )
        values (%s, now(), now(), %s, %s, %s, %s, %s, %s, now())
        on conflict (passage_id) do update set
          finished_at = coalesce(reading_progress.finished_at, now()),
          quiz_correct = excluded.quiz_correct,
          quiz_total = excluded.quiz_total,
          listen_correct = excluded.listen_correct,
          listen_total = excluded.listen_total,
          recall_correct = excluded.recall_correct,
          recall_total = excluded.recall_total,
          updated_at = now()
        """,
        [
            passage_id,
            quiz_correct,
            quiz_total,
            listen_correct,
            listen_total,
            recall_correct,
            recall_total,
        ],
    )
    clear_cache()
    kind = row[1]
    level = row[2]
    coverage = level_coverage(db, int(level)) if kind == "level" and level else None
    return {"finished": True, "id": passage_id, "coverage": coverage}


def save_custom(db, text, title=None):
    require_catalog(db)
    parts = split_passage_text(text)
    lexicon = load_lexicon(db)
    reference = user_level(db)
    sentences = [{"ja": part, "en": "", "source_id": None} for part in parts]
    covers = set()
    for part in parts:
        block = annotate_sentence(part, lexicon, reference_level=reference)
        for token in block["tokens"]:
            subject_id = token.get("subject_id")
            token_level = token.get("level")
            if subject_id and token_level is not None and int(token_level) <= reference:
                covers.add(int(subject_id))
    passage_id = str(uuid.uuid4())
    _insert_passage(
        db,
        passage_id,
        "custom",
        reference,
        None,
        None,
        (title or "Your text").strip()[:80] or "Your text",
        sentences,
        sorted(covers),
    )
    return {"id": passage_id}

"""Reading module: level passages built from WaniKani's own example sentences.

No model calls. A passage is a small set of cached context sentences chosen so
that, across the passages for a level, every kanji and vocabulary item of that
level shows up at least once. Words from higher levels keep their furigana.

The full subject catalog lives in wk_catalog, not wk_subjects. wk_subjects is
only what the user has unlocked, and drills, quizzes, and courses sample it
directly — locked items must not land there.
"""

from __future__ import annotations

import re

from shared.answers import katakana_to_hiragana, normalize_reading
from shared.quiz import _accepted_meanings, _accepted_readings, _primary_reading

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
        updated_at      timestamptz
    )
    """,
)

_SCHEMA_READY = False


def ensure_schema(db):
    """Create reading tables if needed. Skip after the first successful check."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    try:
        if db.has_relation("public.wk_catalog"):
            _SCHEMA_READY = True
            return
    except Exception:
        pass
    for statement in SCHEMA_STATEMENTS:
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
    return {
        "text": text,
        "kind": "word",
        "cls": "word",
        "subject_id": entry["id"],
        "type": entry.get("type"),
        "level": entry.get("level"),
        "meaning": entry.get("meaning"),
        "ruby": pieces,
        "reading": ruby_reading(pieces) if pieces else reading,
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
    reading = entry.get("reading") or ""
    return {
        "text": char,
        "kind": "kanji",
        "cls": "kanji",
        "subject_id": entry["id"],
        "type": "kanji",
        "level": entry.get("level"),
        "meaning": entry.get("meaning"),
        "ruby": [{"base": char, "ruby": reading}] if reading else [{"base": char, "ruby": ""}],
        "reading": reading or None,
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

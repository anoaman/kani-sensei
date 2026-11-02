"""Reading module: level passages built from WaniKani's own example sentences.

No model calls. A passage is a small set of cached context sentences chosen so
that, across the passages for a level, every kanji and vocabulary item of that
level shows up at least once. Words from higher levels keep their furigana.

The full subject catalog lives in wk_catalog, not wk_subjects. wk_subjects is
only what the user has unlocked, and drills, quizzes, and courses sample it
directly — locked items must not land there.
"""

from __future__ import annotations

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

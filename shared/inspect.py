"""Teaching cards from the cached WaniKani subject payload.

Uses `wk_subjects.raw` (the WK `/subjects` data block) so a miss can show
composition, visually similar kanji, a context sentence, and audio — the
stuff WK itself uses to teach, which the quizzes previously threw away.
"""

from __future__ import annotations

import json


SRS_NAMES = {
    0: "locked",
    1: "apprentice 1",
    2: "apprentice 2",
    3: "apprentice 3",
    4: "apprentice 4",
    5: "guru 1",
    6: "guru 2",
    7: "master",
    8: "enlightened",
    9: "burned",
}


def _parse_json(value):
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode()
    if isinstance(value, str):
        return json.loads(value) if value else {}
    return {}


def _ids(raw, key):
    values = raw.get(key) or []
    out = []
    for item in values:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def labeled_readings(readings_raw):
    readings = _parse_json(readings_raw)
    if not isinstance(readings, list):
        return []
    out = []
    for entry in readings:
        if not isinstance(entry, dict):
            continue
        if entry.get("accepted_answer", True) is False:
            continue
        text = (entry.get("reading") or "").strip()
        if not text:
            continue
        out.append({
            "reading": text,
            "type": (entry.get("type") or "reading").replace("_", " "),
            "primary": bool(entry.get("primary")),
        })
    return out


def first_audio_url(raw):
    for entry in raw.get("pronunciation_audios") or []:
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        content = (entry.get("content_type") or "").lower()
        if url and "mpeg" in content:
            return url
        if url and not content:
            return url
    for entry in raw.get("pronunciation_audios") or []:
        if isinstance(entry, dict) and entry.get("url"):
            return entry["url"]
    return None


def first_sentence(raw):
    for entry in raw.get("context_sentences") or []:
        if not isinstance(entry, dict):
            continue
        ja = (entry.get("ja") or "").strip()
        en = (entry.get("en") or "").strip()
        if ja:
            return {"ja": ja, "en": en}
    return None


def wk_url(object_type, characters, slug=None):
    kind = {
        "kanji": "kanji",
        "vocabulary": "vocabulary",
        "kana_vocabulary": "vocabulary",
        "radical": "radicals",
    }.get(object_type or "", "kanji")
    token = slug or characters
    if not token:
        return "https://www.wanikani.com"
    return f"https://www.wanikani.com/{kind}/{token}"


def catalog_card_inputs(row):
    """Turn a wk_catalog row into build_inspect_card inputs.

    The catalog keeps accepted meanings as strings and a single audio URL.
    It does not store mnemonics.
    """
    primary = row.get("primary_meaning")
    meaning_objs = []
    for item in row.get("meanings") or []:
        if isinstance(item, dict):
            meaning_objs.append(item)
            continue
        text = str(item or "").strip()
        if text:
            meaning_objs.append({
                "meaning": text,
                "primary": text == primary,
                "accepted_answer": True,
            })
    audio = row.get("audio_url")
    raw = {
        "parts_of_speech": row.get("parts_of_speech") or [],
        "context_sentences": row.get("context_sentences") or [],
        "component_subject_ids": [int(item) for item in (row.get("component_ids") or [])],
        "visually_similar_subject_ids": [int(item) for item in (row.get("similar_ids") or [])],
        "amalgamation_subject_ids": [int(item) for item in (row.get("amalgamation_ids") or [])],
        "pronunciation_audios": (
            [{"url": audio, "content_type": "audio/mpeg"}] if audio else []
        ),
    }
    return {
        "subject_id": int(row["id"]),
        "object_type": row.get("object_type"),
        "characters": row.get("characters"),
        "slug": row.get("slug"),
        "primary_meaning": primary,
        "meanings_raw": meaning_objs,
        "readings_raw": row.get("readings") or [],
        "raw": raw,
        "level": row.get("level"),
    }


def related_stub(row):
    subject_id, object_type, characters, slug, meaning, level = row
    return {
        "subject_id": subject_id,
        "type": object_type,
        "characters": characters,
        "slug": slug,
        "meaning": meaning,
        "level": level,
    }


def build_inspect_card(
    subject_id,
    object_type,
    characters,
    slug,
    primary_meaning,
    meanings_raw,
    readings_raw,
    raw,
    level=None,
    srs_stage=None,
    related=None,
):
    raw = _parse_json(raw) if not isinstance(raw, dict) else raw
    related = {item["subject_id"]: item for item in (related or [])}
    component_ids = _ids(raw, "component_subject_ids")
    similar_ids = _ids(raw, "visually_similar_subject_ids")
    used_ids = _ids(raw, "amalgamation_subject_ids")
    from shared.quiz import _accepted_meanings

    stage = int(srs_stage or 0)
    return {
        "subject_id": subject_id,
        "type": object_type,
        "characters": characters,
        "level": level,
        "meaning": primary_meaning,
        "meanings": _accepted_meanings(meanings_raw, primary_meaning)[:6],
        "readings": labeled_readings(readings_raw),
        "srs_stage": stage,
        "srs_name": SRS_NAMES.get(stage, f"stage {stage}"),
        "wk_url": wk_url(object_type, characters, slug),
        "audio_url": first_audio_url(raw),
        "sentence": first_sentence(raw),
        "parts_of_speech": [
            str(part) for part in (raw.get("parts_of_speech") or []) if part
        ][:4],
        "components": [related[i] for i in component_ids if i in related],
        "similar": [related[i] for i in similar_ids if i in related][:6],
        "used_in": [related[i] for i in used_ids if i in related],
        "mnemonic": {
            "meaning": (raw.get("meaning_mnemonic") or "").strip() or None,
            "reading": (raw.get("reading_mnemonic") or "").strip() or None,
        },
    }


def _lookup_related(db, ids):
    if not ids:
        return []
    rows = list(db.execute(
        """
        select id, object_type, characters, slug, primary_meaning, level
        from wk_subjects
        where id = any(%s)
        """,
        [ids],
        fetch=True,
    ) or [])
    found = {row[0] for row in rows}
    missing = [item for item in ids if item not in found]
    if missing and db.has_relation("public.wk_catalog"):
        rows.extend(db.execute(
            """
            select id, object_type, characters, slug, primary_meaning, level
            from wk_catalog
            where id = any(%s)
            """,
            [missing],
            fetch=True,
        ) or [])
    return [related_stub(row) for row in rows]


def _card_from_catalog_row(db, row):
    (sid, object_type, characters, slug, meaning, meanings, readings,
     parts, sentences, components, amalgams, similar, audio, level, stage) = row
    inputs = catalog_card_inputs({
        "id": sid,
        "object_type": object_type,
        "characters": characters,
        "slug": slug,
        "primary_meaning": meaning,
        "meanings": _parse_json(meanings) if not isinstance(meanings, list) else meanings,
        "readings": _parse_json(readings) if not isinstance(readings, list) else readings,
        "parts_of_speech": _parse_json(parts) if not isinstance(parts, list) else parts,
        "context_sentences": _parse_json(sentences) if not isinstance(sentences, list) else sentences,
        "component_ids": components or [],
        "amalgamation_ids": amalgams or [],
        "similar_ids": similar or [],
        "audio_url": audio,
        "level": level,
    })
    raw = inputs["raw"]
    ids = (
        raw["component_subject_ids"]
        + raw["visually_similar_subject_ids"]
        + raw["amalgamation_subject_ids"]
    )
    return build_inspect_card(
        inputs["subject_id"], inputs["object_type"], inputs["characters"], inputs["slug"],
        inputs["primary_meaning"], inputs["meanings_raw"], inputs["readings_raw"],
        raw, level=inputs["level"], srs_stage=stage, related=_lookup_related(db, ids),
    )


def fetch_inspect(db, subject_id):
    rows = db.execute(
        """
        select s.id, s.object_type, s.characters, s.slug, s.primary_meaning,
               s.meanings, s.readings, s.raw, s.level, a.srs_stage
        from wk_subjects s
        left join wk_assignments a on a.subject_id = s.id
        where s.id = %s
        """,
        [subject_id],
        fetch=True,
    )
    if rows:
        (sid, object_type, characters, slug, meaning, meanings_raw, readings_raw,
         raw, level, srs_stage) = rows[0]
        parsed = _parse_json(raw)
        ids = (
            _ids(parsed, "component_subject_ids")
            + _ids(parsed, "visually_similar_subject_ids")
            + _ids(parsed, "amalgamation_subject_ids")
        )
        return build_inspect_card(
            sid, object_type, characters, slug, meaning, meanings_raw, readings_raw,
            parsed, level=level, srs_stage=srs_stage, related=_lookup_related(db, ids),
        )
    if db.has_relation("public.wk_catalog"):
        catalog = db.execute(
            """
            select c.id, c.object_type, c.characters, c.slug, c.primary_meaning,
                   c.meanings, c.readings, c.parts_of_speech, c.context_sentences,
                   c.component_ids, c.amalgamation_ids, c.similar_ids, c.audio_url,
                   c.level, a.srs_stage
            from wk_catalog c
            left join wk_assignments a on a.subject_id = c.id
            where c.id = %s
            """,
            [subject_id],
            fetch=True,
        )
        if catalog:
            return _card_from_catalog_row(db, catalog[0])
    raise ValueError("subject not found")

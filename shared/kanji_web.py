"""Kanji Web: one level as radicals, the kanji they build, and the words those kanji make.

Lane order is barycentric so a radical sits near the kanji that use it, and
those kanji sit near their words. Weak items are the ones drills, accuracy,
or relearn stage say are shaky.
"""

from __future__ import annotations

from shared.course import stage_bucket

LANES = ("radical", "kanji", "vocabulary")


def _lane(object_type):
    if object_type == "kana_vocabulary":
        return "vocabulary"
    if object_type in LANES:
        return object_type
    return None


def _reading(value):
    if not value:
        return None
    if isinstance(value, str):
        return value
    from shared.answers import katakana_to_hiragana
    from shared.quiz import _primary_reading

    if isinstance(value, list) and value and isinstance(value[0], dict):
        text = _primary_reading(value)
        return katakana_to_hiragana(text) if text else None
    if isinstance(value, list):
        text = value[0]
        return katakana_to_hiragana(text) if isinstance(text, str) else None
    return None


def _is_weak(subject_id, stage, weak):
    if subject_id in weak:
        return True
    return stage is not None and 2 <= int(stage) <= 4


def build_graph(rows, stages, weak, level):
    """Pure graph for one level.

    `rows` includes the level's radicals, kanji, and vocabulary, plus any
    component subjects the caller looked up (often a lower level). `stages`
    maps subject id to SRS stage. `weak` is the set of ids already known to
    be shaky (misses or low accuracy); relearn stages 2–4 count too.
    """
    level = int(level)
    stages = stages or {}
    weak = {int(item) for item in (weak or ())}
    by_id = {}
    for row in rows or []:
        if not row or row.get("id") is None:
            continue
        by_id[int(row["id"])] = row

    focus = []
    for subject_id, row in by_id.items():
        lane = _lane(row.get("type") or row.get("object_type"))
        if lane and int(row.get("level") or 0) == level:
            focus.append(subject_id)

    parents = {}
    for subject_id in list(by_id):
        row = by_id[subject_id]
        components = []
        for value in row.get("component_ids") or []:
            try:
                component_id = int(value)
            except (TypeError, ValueError):
                continue
            if component_id != subject_id and component_id in by_id:
                components.append(component_id)
        parents[subject_id] = components

    # Keep direct components of focus items, and the components of those,
    # so an off-level kanji still shows the radical it is built from.
    needed = set(focus)
    frontier = list(focus)
    while frontier:
        current = frontier.pop()
        for component_id in parents.get(current, []):
            if component_id not in needed:
                needed.add(component_id)
                frontier.append(component_id)

    nodes = {}
    for subject_id in needed:
        row = by_id[subject_id]
        lane = _lane(row.get("type") or row.get("object_type"))
        if not lane:
            continue
        stage = stages.get(subject_id)
        if stage is None and subject_id in stages:
            stage = stages[subject_id]
        stage = int(stage) if stage is not None else None
        characters = row.get("characters") or None
        meaning = row.get("meaning") or row.get("primary_meaning")
        nodes[subject_id] = {
            "id": subject_id,
            "type": lane,
            "characters": characters,
            "meaning": meaning,
            "label": characters or meaning or "・",
            "reading": _reading(row.get("reading") if row.get("reading") else row.get("readings")),
            "level": int(row.get("level") or 0),
            "stage": stage,
            "bucket": stage_bucket(stage) if stage is not None else None,
            "weak": _is_weak(subject_id, stage, weak),
            "dependents": 0,
            "outside": int(row.get("level") or 0) != level,
            "lesson_position": int(row.get("lesson_position") or 0),
        }

    edges = []
    seen_component = set()
    for subject_id, node in nodes.items():
        for component_id in parents.get(subject_id, []):
            if component_id not in nodes:
                continue
            key = (subject_id, component_id)
            if key in seen_component:
                continue
            seen_component.add(key)
            edges.append({"from": subject_id, "to": component_id, "kind": "component"})

    seen_similar = set()
    for subject_id, row in by_id.items():
        if subject_id not in nodes:
            continue
        for value in row.get("similar_ids") or []:
            try:
                other = int(value)
            except (TypeError, ValueError):
                continue
            if other not in nodes or other == subject_id:
                continue
            key = (min(subject_id, other), max(subject_id, other))
            if key in seen_similar:
                continue
            seen_similar.add(key)
            edges.append({"from": key[0], "to": key[1], "kind": "similar"})

    component_parents = {subject_id: [] for subject_id in nodes}
    for edge in edges:
        if edge["kind"] != "component":
            continue
        component_parents[edge["from"]].append(edge["to"])

    def order_lane(lane, index_of):
        group = [node for node in nodes.values() if node["type"] == lane]

        def key(node):
            indexes = [index_of[parent] for parent in component_parents[node["id"]] if parent in index_of]
            if not indexes:
                return (node["lesson_position"], node["id"])
            return (sum(indexes) / len(indexes), node["id"])

        if index_of is None:
            group.sort(key=lambda node: (node["lesson_position"], node["id"]))
        else:
            group.sort(key=key)
        return group

    radicals = order_lane("radical", None)
    radical_index = {node["id"]: index for index, node in enumerate(radicals)}
    kanji = order_lane("kanji", radical_index)
    kanji_index = {node["id"]: index for index, node in enumerate(kanji)}
    vocabulary = order_lane("vocabulary", kanji_index)

    # How many level words sit on top of this kanji or radical.
    vocab_ids = [node["id"] for node in vocabulary if not node["outside"]]

    def ancestors(subject_id):
        seen = set()
        stack = list(component_parents.get(subject_id, []))
        while stack:
            current = stack.pop()
            if current in seen or current not in nodes:
                continue
            seen.add(current)
            stack.extend(component_parents.get(current, []))
        return seen

    for vocab_id in vocab_ids:
        for ancestor in ancestors(vocab_id):
            nodes[ancestor]["dependents"] += 1

    weak_links = [
        {
            "id": node["id"],
            "characters": node["characters"],
            "meaning": node["meaning"],
            "label": node["label"],
            "type": node["type"],
            "dependents": node["dependents"],
        }
        for node in nodes.values()
        if node["weak"] and node["type"] in ("radical", "kanji") and node["dependents"] > 0
    ]
    weak_links.sort(key=lambda item: (-item["dependents"], item["id"]))

    return {
        "level": level,
        "lanes": {
            "radical": radicals,
            "kanji": kanji,
            "vocabulary": vocabulary,
        },
        "edges": edges,
        "weak_links": weak_links[:3],
    }


def fetch_web(db, level):
    """Load one level's graph. Parents outside the level are included."""
    from shared.reader import _has, _json, fetch_stages, require_catalog

    require_catalog(db)
    level = int(level)
    if level < 1 or level > 60:
        raise ValueError("level must be between 1 and 60")
    columns = """
        id, object_type, level, characters, primary_meaning, readings,
        lesson_position, component_ids, similar_ids
    """
    rows = db.execute(
        f"""
        select {columns}
        from wk_catalog
        where level = %s
          and object_type in ('radical', 'kanji', 'vocabulary', 'kana_vocabulary')
        """,
        [level],
        fetch=True,
    )
    component_ids = set()
    shaped = []
    for row in rows:
        item = _shape_row(row)
        shaped.append(item)
        component_ids.update(item["component_ids"])
    have = {item["id"] for item in shaped}
    missing = sorted(component_ids - have)
    if missing:
        parents = db.execute(
            f"select {columns} from wk_catalog where id = any(%s)",
            [missing],
            fetch=True,
        )
        for row in parents:
            item = _shape_row(row)
            shaped.append(item)
            have.add(item["id"])
    ids = [item["id"] for item in shaped]
    stages = fetch_stages(db, ids) if ids else {}
    weak = set()
    if ids and _has(db, "public.drill_misses"):
        for subject_id, _count in db.execute(
            """
            select subject_id, miss_count from drill_misses
            where subject_id = any(%s) and miss_count >= 2
            """,
            [ids],
            fetch=True,
        ):
            weak.add(int(subject_id))
    if ids and _has(db, "public.wk_review_stats"):
        for subject_id, _pct in db.execute(
            """
            select subject_id, percentage_correct from wk_review_stats
            where subject_id = any(%s) and percentage_correct < 75
            """,
            [ids],
            fetch=True,
        ):
            weak.add(int(subject_id))
    for subject_id, stage in stages.items():
        if stage is not None and 2 <= int(stage) <= 4:
            weak.add(int(subject_id))
    # Readings may still be WK objects; build_graph normalizes them.
    for item in shaped:
        item["readings"] = _json(item.get("readings"), [])
    return build_graph(shaped, stages, weak, level)


def _shape_row(row):
    from shared.reader import _json

    return {
        "id": int(row[0]),
        "type": row[1],
        "level": int(row[2] or 0),
        "characters": row[3],
        "meaning": row[4],
        "readings": _json(row[5], []),
        "lesson_position": int(row[6] or 0),
        "component_ids": [int(item) for item in (row[7] or [])],
        "similar_ids": [int(item) for item in (row[8] or [])],
    }

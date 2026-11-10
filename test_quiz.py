import os
import unittest
from datetime import datetime, timezone, timedelta

from shared.decay_map import build_decay_map, classify_item
from shared.quiz import (
    QUIZ_POOL_QUERY,
    QUIZ_POOL_QUERY_LEGACY,
    build_quiz,
    choose_prompt_type,
    enrich_pool_row,
    normalize_object_types,
    pick_distractors,
    sample_weighted,
)


NOW = datetime(2026, 7, 29, tzinfo=timezone.utc)


def decay_row(subject_id, level, correct, incorrect, stage=1, due=True, prev_stage=None):
    return (
        subject_id, level, "vocabulary", "語", "Word", correct, 0,
        correct, incorrect, stage,
        NOW - timedelta(days=1) if due else NOW + timedelta(days=1),
        None, prev_stage,
    )


def pool_row(
    subject_id, level, characters, meaning, reading,
    correct=5, incorrect=5, stage=2, object_type="vocabulary",
    meaning_incorrect=0,
):
    meanings = [{"meaning": meaning, "primary": True, "accepted_answer": True}]
    readings = (
        [{"reading": reading, "primary": True, "accepted_answer": True}]
        if reading
        else []
    )
    return (
        subject_id, level, object_type, characters, meaning,
        meanings, readings,
        correct, meaning_incorrect, correct, incorrect,
        stage, NOW - timedelta(days=1), None, None,
    )


class DecayMapRegressionTests(unittest.TestCase):
    def test_stage_regression_raises_band(self):
        calm = classify_item(decay_row(1, 5, 20, 1, stage=7, due=False), now=NOW)
        fallen = classify_item(
            decay_row(2, 5, 20, 1, stage=3, due=False, prev_stage=7), now=NOW,
        )
        self.assertGreater(fallen["decay_score"], calm["decay_score"])
        self.assertTrue(fallen["regressed"])

    def test_soft_suggested_levels_when_map_is_calm(self):
        result = build_decay_map(
            [decay_row(1, 2, 20, 0, stage=8, due=False),
             decay_row(2, 8, 18, 1, stage=8, due=False)],
            now=NOW,
        )
        self.assertTrue(result["summary"]["suggested_levels"])


class QuizTests(unittest.TestCase):
    def test_weighted_sample_prefers_high_decay(self):
        items = [
            {"subject_id": 1, "decay_score": 5, "characters": "a"},
            {"subject_id": 2, "decay_score": 90, "characters": "b"},
            {"subject_id": 3, "decay_score": 10, "characters": "c"},
        ]
        # Deterministic: high-decay item should dominate first picks across seeds.
        first_picks = []
        for seed in range(40):
            import random
            picked = sample_weighted(items, 1, random.Random(seed))
            first_picks.append(picked[0]["subject_id"])
        self.assertGreater(first_picks.count(2), first_picks.count(1))
        self.assertGreater(first_picks.count(2), first_picks.count(3))

    def test_build_quiz_returns_four_choices_without_answers(self):
        rows = [
            pool_row(i, 10 + (i % 3), f"字{i}", f"Meaning{i}", f"よみ{i}",
                     incorrect=8 if i < 5 else 1)
            for i in range(20)
        ]
        quiz = build_quiz(rows, min_level=10, max_level=12, count=5, seed=7)
        self.assertEqual(quiz["question_count"], 5)
        self.assertEqual(len(quiz["questions"]), 5)
        for q in quiz["questions"]:
            self.assertEqual(len(q["choices"]), 4)
            self.assertIn(q["correct_answer"], q["choices"])
            self.assertEqual(q["choices"].index(q["correct_answer"]), q["correct_index"])
            self.assertIn(q["prompt_type"], ("meaning", "reading"))

    def test_build_quiz_uses_single_matching_subject(self):
        rows = [pool_row(1, 1, "一", "One", "いち")]

        quiz = build_quiz(rows, min_level=1, max_level=2, count=10, seed=7)

        self.assertEqual(quiz["question_count"], 1)
        self.assertEqual(quiz["questions"][0]["subject_id"], 1)
        self.assertEqual(quiz["questions"][0]["choices"], [
            quiz["questions"][0]["correct_answer"],
        ])

    def test_build_quiz_uses_all_matching_subjects_below_requested_count(self):
        rows = [
            pool_row(1, 1, "一", "One", "いち"),
            pool_row(2, 2, "二", "Two", "に"),
        ]

        quiz = build_quiz(rows, min_level=1, max_level=2, count=10, seed=7)

        self.assertEqual(quiz["question_count"], 2)
        self.assertEqual({q["subject_id"] for q in quiz["questions"]}, {1, 2})

    def test_enrich_keeps_primary_reading(self):
        item = enrich_pool_row(pool_row(9, 4, "毎月", "Every Month", "まいつき"), now=NOW)
        self.assertEqual(item["primary_reading"], "まいつき")
        self.assertEqual(item["primary_meaning"], "Every Month")

    def test_normalize_object_types_aliases(self):
        self.assertEqual(normalize_object_types(["vocab"]), ["vocabulary"])
        self.assertEqual(normalize_object_types(["radicals"]), ["radical"])
        self.assertEqual(normalize_object_types(["kana"]), ["kana_vocabulary"])

    def test_build_quiz_filters_to_kanji_only(self):
        rows = []
        for i in range(12):
            rows.append(pool_row(
                i, 10, f"漢{i}", f"Kanji{i}", f"かん{i}",
                object_type="kanji", incorrect=6,
            ))
            rows.append(pool_row(
                100 + i, 10, f"語{i}", f"Vocab{i}", f"ご{i}",
                object_type="vocabulary", incorrect=9,
            ))
        quiz = build_quiz(
            rows,
            min_level=10,
            max_level=10,
            count=5,
            seed=3,
            object_types=["kanji"],
        )
        self.assertEqual(quiz["object_types"], ["kanji"])
        self.assertTrue(all(q["object_type"] == "kanji" for q in quiz["questions"]))

    def test_build_quiz_succeeds_with_sparse_low_level_pool(self):
        # Regression: levels 1-2 are often mostly burned for advanced users,
        # leaving only a handful of matching subjects. A quiz should still
        # start whenever there are enough matching subjects for one
        # multiple-choice question, instead of requiring the old flat
        # minimum of 4 pool rows regardless of what's actually buildable.
        names = ["One", "Two", "Three", "Four", "Five"]
        readings = ["いち", "に", "さん", "よん", "ご"]
        rows = [
            pool_row(i, 1 + (i % 2), f"字{i}", names[i], readings[i], object_type="kanji")
            for i in range(5)
        ]
        quiz = build_quiz(rows, min_level=1, max_level=2, count=10, seed=1)
        self.assertGreaterEqual(quiz["question_count"], 1)
        for q in quiz["questions"]:
            self.assertEqual(len(q["choices"]), 4)
            self.assertIn(q["correct_answer"], q["choices"])

    def test_quiz_pool_queries_do_not_exclude_burned_subjects(self):
        # The pool query used to require a.burned_at is null in the WHERE
        # clause, which starves low-level ranges for users who have already
        # burned those items (burned_at is still selected for scoring).
        self.assertNotIn("burned_at is null", QUIZ_POOL_QUERY)
        self.assertNotIn("burned_at is null", QUIZ_POOL_QUERY_LEGACY)

    def test_build_quiz_filters_to_radicals_meaning_only(self):
        rows = [
            pool_row(
                i, 2, f"部{i}", f"Radical{i}", None,
                object_type="radical", incorrect=7,
            )
            for i in range(12)
        ]
        quiz = build_quiz(
            rows,
            min_level=2,
            max_level=2,
            count=4,
            seed=11,
            modes=["meaning", "reading"],
            object_types=["radical"],
        )
        self.assertEqual(quiz["object_types"], ["radical"])
        self.assertTrue(all(q["object_type"] == "radical" for q in quiz["questions"]))
        self.assertTrue(all(q["prompt_type"] == "meaning" for q in quiz["questions"]))

    def test_fetch_pool_uses_legacy_sql_when_snapshots_missing(self):
        from shared import decay_map
        from shared.quiz import fetch_pool

        decay_map._SNAPSHOTS_READY = False
        seen = []

        class Fake:
            def execute(self, sql, args=None, fetch=False):
                seen.append(sql)
                return []

        fetch_pool(Fake(), 1, 10, ["kanji"])
        decay_map._SNAPSHOTS_READY = None
        self.assertEqual(len(seen), 1)
        self.assertIn("null::integer as prev_srs_stage", seen[0])
        self.assertNotIn("distinct on", seen[0].lower())

    def test_quiz_pool_query_uses_distinct_on_not_lateral(self):
        sql = QUIZ_POOL_QUERY.lower()
        self.assertIn("distinct on (subject_id)", sql)
        self.assertNotIn("lateral", sql)
        self.assertNotIn("lateral", QUIZ_POOL_QUERY_LEGACY.lower())
        self.assertIn("visually_similar_subject_ids", QUIZ_POOL_QUERY)
        self.assertIn("visually_similar_subject_ids", QUIZ_POOL_QUERY_LEGACY)

    def test_enrich_reads_lookalike_ids(self):
        row = pool_row(1, 5, "未", "Not Yet", "み") + ([9, "12", "nope"],)
        item = enrich_pool_row(row, now=NOW)
        self.assertEqual(item["similar_ids"], [9, 12])
        plain = enrich_pool_row(pool_row(2, 5, "末", "End", "まつ"), now=NOW)
        self.assertEqual(plain["similar_ids"], [])


def _half_item(**extra):
    item = {
        "primary_meaning": "Big",
        "primary_reading": "だい",
        "meaning_correct": 10,
        "meaning_incorrect": 10,
        "reading_correct": 10,
        "reading_incorrect": 10,
    }
    item.update(extra)
    return item


class WeakerHalfTests(unittest.TestCase):
    def _picks(self, item, n=400):
        import random
        return [
            choose_prompt_type(item, ["meaning", "reading"], random.Random(seed))
            for seed in range(n)
        ]

    def test_a_clearly_weaker_half_is_asked_three_times_in_four(self):
        item = _half_item(
            meaning_correct=20, meaning_incorrect=1,
            reading_correct=4, reading_incorrect=16,
        )
        reading = self._picks(item).count("reading")
        self.assertGreater(reading, 260)
        self.assertLess(reading, 340)

    def test_equal_halves_stay_a_coin_flip(self):
        meaning = self._picks(_half_item()).count("meaning")
        self.assertGreater(meaning, 150)
        self.assertLess(meaning, 250)

    def test_a_recent_miss_makes_that_half_the_weaker_one(self):
        item = _half_item(last_missed_prompt="meaning")
        meaning = self._picks(item).count("meaning")
        self.assertGreater(meaning, 260)
        self.assertLess(meaning, 340)
        # The notebook column name is accepted too.
        aliased = _half_item(last_prompt_type="reading")
        reading = self._picks(aliased).count("reading")
        self.assertGreater(reading, 260)

    def test_one_available_half_is_used_as_is(self):
        import random
        item = _half_item(primary_reading=None)
        self.assertEqual(
            choose_prompt_type(item, ["meaning", "reading"], random.Random(0)),
            "meaning",
        )
        self.assertIsNone(choose_prompt_type(item, ["reading"], random.Random(0)))


def _choice_item(subject_id, characters, meaning, reading, level, decay, similar=()):
    return {
        "subject_id": subject_id,
        "type": "kanji",
        "level": level,
        "characters": characters,
        "primary_meaning": meaning,
        "meanings": [meaning],
        "primary_reading": reading,
        "readings": [reading],
        "decay_score": decay,
        "similar_ids": list(similar),
    }


class DistractorOrderTests(unittest.TestCase):
    def test_lookalike_kanji_lead_the_choices(self):
        import random
        target = _choice_item(1, "未", "Not Yet", "み", 5, 10, similar=[2, 3])
        pool = [
            target,
            _choice_item(2, "末", "End", "まつ", 30, 1),
            _choice_item(3, "木", "Tree", "き", 28, 1),
            _choice_item(4, "本", "Book", "ほん", 5, 90),
        ]
        got = pick_distractors(target, pool, "meaning", random.Random(0), k=3)
        self.assertEqual(got, ["End", "Tree", "Book"])

    def test_a_lookalike_missing_from_the_pool_is_skipped(self):
        import random
        target = _choice_item(1, "未", "Not Yet", "み", 5, 10, similar=[99, 2])
        pool = [
            target,
            _choice_item(2, "末", "End", "まつ", 30, 1),
            _choice_item(4, "本", "Book", "ほん", 5, 40),
            _choice_item(5, "元", "Origin", "げん", 6, 10),
        ]
        got = pick_distractors(target, pool, "meaning", random.Random(1), k=3)
        self.assertEqual(got[0], "End")
        self.assertEqual(set(got[1:]), {"Book", "Origin"})

    def test_shared_kana_readings_come_before_an_unrelated_neighbor(self):
        import random
        target = _choice_item(1, "神", "God", "かみ", 5, 10)
        pool = [
            target,
            _choice_item(2, "酒", "Sake", "さけ", 5, 90),
            _choice_item(3, "角", "Corner", "かど", 20, 1),
        ]
        got = pick_distractors(target, pool, "reading", random.Random(0), k=1)
        self.assertEqual(got, ["かど"])


if __name__ == "__main__":
    unittest.main()

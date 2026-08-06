import os
import unittest
from datetime import datetime, timezone, timedelta

from shared.decay_map import build_decay_map, classify_item
from shared.quiz import build_quiz, enrich_pool_row, normalize_object_types, sample_weighted


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
        correct, 0, correct, incorrect,
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

    def test_enrich_keeps_primary_reading(self):
        item = enrich_pool_row(pool_row(9, 4, "毎月", "Every Month", "まいつき"), now=NOW)
        self.assertEqual(item["primary_reading"], "まいつき")
        self.assertEqual(item["primary_meaning"], "Every Month")

    def test_normalize_object_types_aliases(self):
        self.assertEqual(normalize_object_types(["vocab"]), ["vocabulary"])
        self.assertEqual(normalize_object_types(["radicals"]), ["radical"])
        self.assertEqual(normalize_object_types(None), ["kanji", "vocabulary"])

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


class AuthTests(unittest.TestCase):
    def test_token_roundtrip(self):
        os.environ["CRON_SECRET"] = "test-secret-value"
        from shared.auth import issue_token, verify_token
        token, expires = issue_token(now=1_700_000_000)
        self.assertTrue(verify_token(token, now=1_700_000_000))
        self.assertFalse(verify_token(token, now=expires + 1))
        self.assertFalse(verify_token("kibz|1|nope", now=1_700_000_000))


if __name__ == "__main__":
    unittest.main()

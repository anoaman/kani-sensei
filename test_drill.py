import unittest
from datetime import timedelta

from shared.drill import (
    build_drill,
    build_recall_question,
    filter_pool,
    is_leech,
    leech_score,
    public_question,
)
from shared.quiz import enrich_pool_row
from test_quiz import NOW, pool_row


def burned_row(subject_id, level, characters, meaning, reading, **kwargs):
    row = list(pool_row(subject_id, level, characters, meaning, reading, **kwargs))
    row[11] = 9  # srs_stage
    row[13] = NOW - timedelta(days=40)  # burned_at
    return tuple(row)


class DrillBuildTests(unittest.TestCase):
    def test_recall_hides_answers_and_has_no_choices(self):
        rows = [
            pool_row(i, 10, f"字{i}", f"Meaning{i}", f"よみ{i}", incorrect=8, object_type="kanji")
            for i in range(12)
        ]
        drill = build_drill(
            rows, 10, 10, count=5, kind="recall", seed=4, object_types=["kanji"],
        )
        self.assertEqual(drill["kind"], "recall")
        self.assertEqual(drill["question_count"], 5)
        for question in drill["questions"]:
            self.assertEqual(question["choices"], [])
            self.assertTrue(question["accepted_answers"])
            self.assertIn(question["prompt_type"], ("meaning", "reading"))
            public = public_question({**question, "id": "x"}, 0)
            self.assertNotIn("accepted_answers", public)
            self.assertNotIn("correct_answer", public)

    def test_reverse_does_not_leak_the_glyph(self):
        rows = [
            pool_row(i, 8, f"漢{i}", f"Kanji{i}", f"かん{i}", object_type="kanji")
            for i in range(10)
        ]
        drill = build_drill(
            rows, 8, 8, count=4, kind="reverse", seed=2, object_types=["kanji"],
        )
        for question in drill["questions"]:
            self.assertEqual(question["prompt_type"], "reverse")
            self.assertEqual(len(question["choices"]), 4)
            self.assertIn(question["characters"], question["choices"])
            public = public_question({**question, "id": "x"}, 0)
            self.assertIsNone(public["characters"])
            self.assertEqual(public["prompt_text"], question["prompt_text"])
            self.assertEqual(len(public["choices"]), 4)

    def test_mc_still_has_four_choices(self):
        rows = [
            pool_row(i, 6, f"語{i}", f"Vocab{i}", f"ご{i}", object_type="vocabulary")
            for i in range(12)
        ]
        drill = build_drill(
            rows, 6, 6, count=4, kind="mc", seed=9, object_types=["vocab"],
        )
        for question in drill["questions"]:
            self.assertEqual(len(question["choices"]), 4)
            self.assertIn(question["correct_answer"], question["choices"])

    def test_burned_pool_keeps_only_ghosts(self):
        rows = [
            pool_row(1, 3, "活", "Alive", "かつ", object_type="kanji"),
            burned_row(2, 3, "死", "Death", "し", object_type="kanji"),
            burned_row(3, 3, "火", "Fire", "ひ", object_type="kanji"),
        ]
        items = [enrich_pool_row(row, now=NOW) for row in rows]
        ghosts = filter_pool(items, "burned")
        self.assertEqual({item["characters"] for item in ghosts}, {"死", "火"})

        drill = build_drill(
            rows, 3, 3, count=5, kind="recall", pool="burned",
            seed=1, object_types=["kanji"],
        )
        self.assertEqual(drill["pool"], "burned")
        self.assertTrue(all(q["characters"] in ("死", "火") for q in drill["questions"]))

    def test_burned_pool_errors_when_empty(self):
        rows = [pool_row(1, 3, "活", "Alive", "かつ", object_type="kanji")]
        with self.assertRaises(ValueError) as ctx:
            build_drill(
                rows, 3, 3, kind="recall", pool="burned",
                object_types=["kanji"], seed=1,
            )
        self.assertIn("burned", str(ctx.exception))

    def test_speed_asks_at_least_twenty(self):
        rows = [
            pool_row(i, 4, f"速{i}", f"Fast{i}", f"そく{i}", object_type="kanji")
            for i in range(30)
        ]
        drill = build_drill(
            rows, 4, 4, count=8, kind="speed", seed=3, object_types=["kanji"],
        )
        self.assertEqual(drill["kind"], "speed")
        self.assertEqual(drill["seconds"], 60)
        self.assertGreaterEqual(drill["question_count"], 20)

    def test_leech_score_prefers_chronic_misses(self):
        calm = enrich_pool_row(
            pool_row(1, 5, "静", "Calm", "せい", correct=40, incorrect=1,
                     object_type="kanji"),
            now=NOW,
        )
        nasty = enrich_pool_row(
            pool_row(2, 5, "難", "Difficult", "なん", correct=4, incorrect=18,
                     object_type="kanji"),
            now=NOW,
        )
        self.assertFalse(is_leech(calm))
        self.assertTrue(is_leech(nasty))
        self.assertGreater(leech_score(nasty), leech_score(calm))

    def test_recall_question_lists_synonyms(self):
        item = enrich_pool_row(
            pool_row(9, 2, "月", "Moon", "つき", object_type="kanji"),
            now=NOW,
        )
        item["meanings"] = ["Moon", "Month"]
        question = build_recall_question(item, "meaning")
        self.assertEqual(question["correct_answer"], "Moon")
        self.assertIn("Month", question["accepted_answers"])


if __name__ == "__main__":
    unittest.main()

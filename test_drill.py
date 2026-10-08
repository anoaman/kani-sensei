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


class FakeDrillDb:
    """Tiny in-memory stand-in for the queries grade_drill makes."""

    def __init__(self, prompt_type, accepted, kind="recall", count=5,
                 meanings=("Big", "Large"), readings=("だい", "たい")):
        self.session = {
            "kind": kind, "score_correct": 0, "score_total": 0,
            "question_count": count, "combo_best": 0, "meta": {},
        }
        self.questions = {}
        self.subject = (
            [{"meaning": m} for m in meanings],
            [{"reading": r} for r in readings],
        )
        self.add_question("q1", 0, prompt_type, accepted)

    def add_question(self, qid, position, prompt_type, accepted, choices=None,
                     correct_index=None):
        self.questions[qid] = {
            "position": position, "subject_id": 42, "prompt_type": prompt_type,
            "characters": "大", "object_type": "kanji", "level": 1,
            "decay_score": 0, "correct_answer": accepted[0],
            "accepted": list(accepted), "choices": choices or [],
            "correct_index": correct_index, "answered": False,
        }

    def has_relation(self, name):
        return True

    def execute(self, sql, params=None, fetch=False):
        sess = self.session
        if "from wk_subjects" in sql:
            return [self.subject]
        if "max(position)" in sql:
            q = self.questions[params[1]]
            top = max(item["position"] for item in self.questions.values())
            return [(
                q["subject_id"], q["prompt_type"], q["characters"],
                q["object_type"], q["level"], q["decay_score"],
                q["correct_answer"], q["accepted"], q["choices"],
                q["correct_index"], top,
            )]
        if fetch:
            q = self.questions[params[0]]
            answered = "x" if q["answered"] else None
            return [(
                params[0], q["subject_id"], q["prompt_type"], q["characters"],
                q["object_type"], q["level"], q["correct_answer"], q["accepted"],
                q["choices"], q["correct_index"], None, answered,
                sess["kind"], sess["score_correct"], sess["score_total"],
                sess["question_count"], sess["combo_best"], dict(sess["meta"]),
            )]
        if sql.strip().startswith("insert into drill_questions"):
            (new_id, _sid, position, _subj, prompt_type, _chars, _ot, _lvl,
             _decay, _correct, accepted, choices, correct_index) = params
            import json
            self.add_question(new_id, position, prompt_type, json.loads(accepted),
                              json.loads(choices), correct_index)
        elif "update drill_questions" in sql:
            self.questions[params[-1]]["answered"] = True
        elif "update drill_sessions" in sql:
            import json
            (sess["score_correct"], sess["score_total"], sess["combo_best"],
             meta, sess["question_count"]) = params[:5]
            sess["meta"] = json.loads(meta)
        return None


class DrillGradeTests(unittest.TestCase):
    def grade(self, prompt_type, accepted, text, **kwargs):
        from shared.drill import grade_drill
        db = FakeDrillDb(prompt_type, accepted, **kwargs)
        return grade_drill(db, "s1", "q1", text=text)

    def test_typed_meaning_correct(self):
        result = self.grade("meaning", ["Big", "Large"], "large")
        self.assertTrue(result["correct"])
        self.assertEqual(result["score"]["correct"], 1)

    def test_typed_reading_romaji_correct(self):
        result = self.grade("reading", ["だい", "たい"], "dai")
        self.assertTrue(result["correct"])

    def test_typed_wrong_answer(self):
        result = self.grade("meaning", ["Big"], "small")
        self.assertFalse(result["correct"])

    def test_small_typo_passes_but_is_flagged(self):
        result = self.grade("meaning", ["Third Day"], "thrid day")
        self.assertTrue(result["correct"])
        self.assertTrue(result["almost"])

    def test_kana_on_meaning_prompt_shakes(self):
        result = self.grade("meaning", ["Big"], "だい")
        self.assertTrue(result["retry"])
        self.assertIn("meaning", result["hint"])

    def test_romaji_reading_on_meaning_prompt_shakes(self):
        result = self.grade("meaning", ["Big"], "dai")
        self.assertTrue(result["retry"])
        self.assertIn("reading", result["hint"])

    def test_meaning_on_reading_prompt_shakes(self):
        result = self.grade("reading", ["だい"], "big")
        self.assertTrue(result["retry"])

    def test_shake_leaves_question_open(self):
        from shared.drill import grade_drill
        db = FakeDrillDb("meaning", ["Big"])
        grade_drill(db, "s1", "q1", text="だい")
        self.assertFalse(db.questions["q1"]["answered"])
        result = grade_drill(db, "s1", "q1", text="big")
        self.assertTrue(result["correct"])


class DrillRequeueTests(unittest.TestCase):
    def test_miss_comes_back_and_gates_the_finish(self):
        from shared.drill import grade_drill
        db = FakeDrillDb("meaning", ["Big"], count=1)
        miss = grade_drill(db, "s1", "q1", text="small")
        self.assertFalse(miss["correct"])
        retry = miss["requeued"]
        self.assertTrue(retry)
        self.assertFalse(miss["score"]["finished"])
        self.assertEqual(miss["score"]["question_count"], 2)

        hit = grade_drill(db, "s1", retry["id"], text="big")
        self.assertTrue(hit["correct"])
        self.assertTrue(hit["score"]["finished"])
        # First-try accuracy: the retry doesn't rescue the score.
        self.assertEqual((hit["score"]["correct"], hit["score"]["total"]), (0, 1))

    def test_requeue_is_capped(self):
        from shared.drill import MAX_REQUEUES, grade_drill
        db = FakeDrillDb("meaning", ["Big"], count=1)
        qid, result = "q1", None
        for _ in range(MAX_REQUEUES + 1):
            result = grade_drill(db, "s1", qid, gave_up=True)
            if result["requeued"]:
                qid = result["requeued"]["id"]
        self.assertIsNone(result["requeued"])
        self.assertTrue(result["score"]["finished"])

    def test_speed_rounds_do_not_requeue(self):
        from shared.drill import grade_drill
        db = FakeDrillDb("meaning", ["Big"], kind="speed", count=1)
        result = grade_drill(db, "s1", "q1", text="small")
        self.assertIsNone(result["requeued"])
        self.assertTrue(result["score"]["finished"])

    def test_mc_requeue_reshuffles_but_keeps_answer(self):
        from shared.drill import grade_drill
        db = FakeDrillDb("meaning", ["Big"], kind="mc", count=1)
        db.questions["q1"]["choices"] = ["Big", "Small", "Tree", "Fire"]
        db.questions["q1"]["correct_index"] = 0
        result = grade_drill(db, "s1", "q1", choice_index=2)
        retry = result["requeued"]
        new = db.questions[retry["id"]]
        self.assertEqual(new["choices"][new["correct_index"]], "Big")

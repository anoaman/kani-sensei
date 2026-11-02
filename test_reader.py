import unittest

from shared.reader import (
    DAILY_SENTENCES,
    PASSAGE_SIZE,
    align_furigana,
    annotate_sentence,
    build_level_plan,
    build_lexicon,
    build_questions,
    grade_dictation,
    kanji_from_radicals,
    plan_level,
    segment,
)


def entry(**kwargs):
    base = {
        "meanings": [],
        "readings": [],
        "parts_of_speech": [],
        "audio_url": None,
        "lesson_position": 0,
        "level": 1,
        "type": "vocabulary",
    }
    base.update(kwargs)
    if "readings" not in kwargs and base.get("reading"):
        base["readings"] = [base["reading"]]
    if "meanings" not in kwargs and base.get("meaning"):
        base["meanings"] = [base["meaning"]]
    return base


class FuriganaTests(unittest.TestCase):
    def test_okurigana_verb(self):
        pieces = align_furigana("食べる", "たべる")
        self.assertEqual(pieces, [
            {"base": "食", "ruby": "た"},
            {"base": "べる", "ruby": ""},
        ])

    def test_leading_kana(self):
        pieces = align_furigana("お茶", "おちゃ")
        self.assertEqual(pieces, [
            {"base": "お", "ruby": ""},
            {"base": "茶", "ruby": "ちゃ"},
        ])

    def test_kana_between_kanji(self):
        pieces = align_furigana("取り消す", "とりけす")
        self.assertEqual(pieces, [
            {"base": "取", "ruby": "と"},
            {"base": "り", "ruby": ""},
            {"base": "消", "ruby": "け"},
            {"base": "す", "ruby": ""},
        ])

    def test_adjacent_kanji_fall_back_to_the_whole_word(self):
        pieces = align_furigana("大人", "おとな")
        self.assertEqual(pieces, [{"base": "大人", "ruby": "おとな"}])


class SegmentTests(unittest.TestCase):
    def lexicon(self):
        return build_lexicon([
            entry(id=1, characters="食べる", meaning="to eat", reading="たべる",
                  parts_of_speech=["ichidan verb", "transitive verb"]),
            entry(id=2, characters="日本", meaning="Japan", reading="にほん"),
            entry(id=3, characters="日本語", meaning="Japanese language", reading="にほんご", level=2),
            entry(id=4, type="kanji", characters="食", meaning="eat", reading="た"),
        ])

    def test_conjugated_verb_splits_into_stem_plus_kana(self):
        tokens = segment("食べました", self.lexicon())
        self.assertEqual([token["text"] for token in tokens], ["食べ", "ました"])
        self.assertEqual(tokens[0]["subject_id"], 1)
        self.assertEqual(tokens[0]["reading"], "たべ")
        self.assertEqual(tokens[0]["ruby"][0], {"base": "食", "ruby": "た"})

    def test_longest_vocabulary_match_wins(self):
        tokens = segment("日本語", self.lexicon())
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["subject_id"], 3)
        self.assertEqual(tokens[0]["text"], "日本語")

    def test_unknown_kanji_has_no_reading_and_blocks_listening(self):
        annotated = annotate_sentence("仮", self.lexicon())
        self.assertEqual(annotated["tokens"][0]["kind"], "kanji")
        self.assertIsNone(annotated["tokens"][0]["reading"])
        self.assertIsNone(annotated["tokens"][0]["subject_id"])
        self.assertFalse(annotated["listenable"])

    def test_known_sentence_is_listenable_kana(self):
        annotated = annotate_sentence("食べました。", self.lexicon(), reference_level=5, stages={1: 5}, targets={1})
        self.assertTrue(annotated["listenable"])
        self.assertEqual(annotated["kana"], "たべました")
        self.assertEqual(annotated["tokens"][0]["status"], "known")
        self.assertTrue(annotated["tokens"][0]["target"])


class DictationTests(unittest.TestCase):
    def test_katakana_matches_hiragana(self):
        graded = grade_dictation("たべる", "タベル")
        self.assertEqual(graded["verdict"], "pass")
        self.assertEqual(graded["score"], 1.0)
        self.assertEqual(graded["got"], "たべる")

    def test_romaji_input(self):
        graded = grade_dictation("たべる", "taberu")
        self.assertEqual(graded["verdict"], "pass")
        self.assertEqual(graded["expected"], graded["got"])

    def test_thresholds(self):
        # One miss in ten characters is 0.9.
        passed = grade_dictation("あいうえおかきくけこ", "あいうえおかきくけ")
        self.assertGreaterEqual(passed["score"], 0.85)
        self.assertEqual(passed["verdict"], "pass")
        # Two misses in five is exactly 0.6.
        close = grade_dictation("あいうえお", "あいう")
        self.assertEqual(close["score"], 0.6)
        self.assertEqual(close["verdict"], "close")
        missed = grade_dictation("あいうえお", "かき")
        self.assertLess(missed["score"], 0.6)
        self.assertEqual(missed["verdict"], "miss")
        self.assertTrue(any(op["op"] == "del" for op in missed["ops"]))


class PlanTests(unittest.TestCase):
    def test_cover_is_complete_and_stable(self):
        targets = [{"id": item, "lesson_position": item} for item in range(1, 13)]
        candidates = [
            {
                "source_id": 100 + item,
                "sentence_idx": 0,
                "ja": f"s{item}",
                "en": "",
                "covers": {item},
                "above_kanji": 0,
                "length": 10,
            }
            for item in range(1, 13)
        ]
        # One sentence that covers everything would win, so keep them separate.
        first = plan_level(targets, candidates)
        second = plan_level(targets, candidates)
        self.assertEqual(first, second)
        self.assertEqual(first["uncovered"], [])
        self.assertEqual(len(first["passages"]), 2)
        self.assertEqual(len(first["passages"][0]), PASSAGE_SIZE)
        covered = set()
        for chunk in first["passages"]:
            self.assertLessEqual(len(chunk), PASSAGE_SIZE)
            for sentence in chunk:
                covered |= set(sentence["covers"])
        self.assertEqual(covered, set(range(1, 13)))

    def test_more_coverage_wins_and_ties_break_on_source_id(self):
        targets = [{"id": 1, "lesson_position": 1}, {"id": 2, "lesson_position": 2}, {"id": 3, "lesson_position": 3}]
        wide = {"source_id": 9, "sentence_idx": 0, "ja": "wide", "en": "", "covers": {1, 2, 3}, "above_kanji": 0, "length": 10}
        singles = [
            {"source_id": 1, "sentence_idx": 0, "ja": "a", "en": "", "covers": {1}, "above_kanji": 0, "length": 10},
            {"source_id": 2, "sentence_idx": 0, "ja": "b", "en": "", "covers": {2}, "above_kanji": 0, "length": 10},
            {"source_id": 3, "sentence_idx": 0, "ja": "c", "en": "", "covers": {3}, "above_kanji": 0, "length": 10},
        ]
        plan = plan_level(targets, singles + [wide])
        self.assertEqual(len(plan["chosen"]), 1)
        self.assertEqual(plan["chosen"][0]["source_id"], 9)

        tied = [
            {"source_id": 5, "sentence_idx": 1, "ja": "later", "en": "", "covers": {1}, "above_kanji": 0, "length": 10},
            {"source_id": 2, "sentence_idx": 0, "ja": "earlier", "en": "", "covers": {1}, "above_kanji": 0, "length": 10},
        ]
        picked = plan_level([{"id": 1, "lesson_position": 1}], tied)
        self.assertEqual(picked["chosen"][0]["source_id"], 2)

    def test_higher_level_sentences_only_fill_gaps(self):
        targets = [{"id": 1, "lesson_position": 1}, {"id": 2, "lesson_position": 2}]
        primary = [{"source_id": 10, "sentence_idx": 0, "ja": "a", "en": "A", "covers": {1}, "above_kanji": 0, "length": 5}]
        extra = [{"source_id": 11, "sentence_idx": 0, "ja": "b", "en": "B", "covers": {2}, "above_kanji": 1, "length": 5}]
        plan = build_level_plan(targets, primary, extra)
        self.assertEqual(plan["uncovered"], [])
        self.assertEqual({sentence["source_id"] for sentence in plan["chosen"]}, {10, 11})

    def test_daily_cap_is_one_passage(self):
        targets = [{"id": item, "lesson_position": item} for item in range(1, 15)]
        candidates = [
            {
                "source_id": item,
                "sentence_idx": 0,
                "ja": f"s{item}",
                "en": "",
                "covers": {item},
                "above_kanji": 0,
                "length": 8,
            }
            for item in range(1, 15)
        ]
        plan = plan_level(targets, candidates, passage_size=DAILY_SENTENCES, limit=DAILY_SENTENCES)
        self.assertEqual(len(plan["chosen"]), DAILY_SENTENCES)
        self.assertEqual(len(plan["passages"]), 1)
        self.assertTrue(plan["uncovered"])

    def test_radical_day_keeps_kanji_the_radicals_build(self):
        radicals = [{"id": 1, "amalgamation_ids": [10, 11]}]
        kanji = [
            {"id": 10, "type": "kanji", "level": 2, "component_ids": [1]},
            {"id": 11, "type": "kanji", "level": 30, "component_ids": [1]},
            {"id": 12, "type": "kanji", "level": 5, "component_ids": [1, 9]},
            {"id": 13, "type": "kanji", "level": 4, "component_ids": [8]},
            {"id": 14, "type": "vocabulary", "level": 2, "component_ids": [1]},
        ]
        chosen = [item["id"] for item in kanji_from_radicals(radicals, kanji, 19)]
        self.assertEqual(chosen, [10, 12])


class QuestionTests(unittest.TestCase):
    def pool(self):
        items = [
            (1, "人", "person", "ひと"),
            (2, "犬", "dog", "いぬ"),
            (3, "猫", "cat", "ねこ"),
            (4, "鳥", "bird", "とり"),
            (5, "魚", "fish", "さかな"),
            (6, "馬", "horse", "うま"),
        ]
        return [
            {
                "id": item_id,
                "type": "kanji",
                "level": 1,
                "characters": characters,
                "meaning": meaning,
                "meanings": [meaning],
                "reading": reading,
                "readings": [reading],
            }
            for item_id, characters, meaning, reading in items
        ]

    def test_questions_are_deterministic_and_distinct(self):
        focus = self.pool()[:2]
        sentences = [
            {"ja": "人がいる。", "en": "There is a person.", "source_id": 1},
            {"ja": "犬がいる。", "en": "There is a dog.", "source_id": 2},
        ]
        translations = ["There is a cat.", "There is a bird.", "There is a horse.", "There is a fish."]
        first = build_questions("level:1:1", sentences, focus, self.pool(), translations)
        second = build_questions("level:1:1", sentences, focus, self.pool(), translations)
        self.assertEqual(first, second)
        self.assertEqual({question["type"] for question in first}, {"translation", "meaning", "reading"})
        for question in first:
            choices = question.get("choices")
            if choices:
                self.assertEqual(len(choices), len(set(choices)))
                self.assertGreaterEqual(len(choices), 2)
                self.assertIn(question["answer"], range(len(choices)))

    def test_custom_text_skips_translation(self):
        questions = build_questions(
            "custom",
            [{"ja": "人がいる。", "en": "", "source_id": 1}],
            self.pool()[:1],
            self.pool(),
            [],
            with_translation=False,
        )
        self.assertNotIn("translation", {question["type"] for question in questions})
        self.assertIn("meaning", {question["type"] for question in questions})


if __name__ == "__main__":
    unittest.main()

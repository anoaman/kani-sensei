import unittest

from shared.reader import (
    align_furigana,
    annotate_sentence,
    build_lexicon,
    grade_dictation,
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


if __name__ == "__main__":
    unittest.main()

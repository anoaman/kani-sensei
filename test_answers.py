import unittest

from shared.answers import (
    grade_meaning,
    grade_reading,
    katakana_to_hiragana,
    normalize_meaning,
    normalize_reading,
    romaji_to_hiragana,
)


class MeaningTests(unittest.TestCase):
    def test_strips_to_and_the(self):
        self.assertEqual(normalize_meaning("To Eat"), "eat")
        self.assertEqual(normalize_meaning("the mountain"), "mountain")
        self.assertEqual(grade_meaning("to eat", ["Eat"]), "correct")
        self.assertEqual(grade_meaning("The Mountain", ["mountain"]), "correct")

    def test_ignores_punctuation_and_case(self):
        self.assertEqual(grade_meaning("one's self", ["one's self"]), "correct")
        self.assertEqual(grade_meaning("ONE", ["One"]), "correct")

    def test_almost_typo_still_not_correct(self):
        self.assertEqual(grade_meaning("mountan", ["mountain"]), "almost")
        self.assertEqual(grade_meaning("banana", ["mountain"]), "wrong")

    def test_empty_is_wrong(self):
        self.assertEqual(grade_meaning("  ", ["eat"]), "wrong")


class ReadingTests(unittest.TestCase):
    def test_romaji_basic(self):
        self.assertEqual(romaji_to_hiragana("taberu"), "たべる")
        self.assertEqual(romaji_to_hiragana("ichi"), "いち")
        self.assertEqual(romaji_to_hiragana("kyou"), "きょう")
        self.assertEqual(romaji_to_hiragana("shite"), "して")

    def test_sokuon_and_syllabic_n(self):
        self.assertEqual(romaji_to_hiragana("kitte"), "きって")
        self.assertEqual(romaji_to_hiragana("shinbun"), "しんぶん")
        self.assertEqual(romaji_to_hiragana("nani"), "なに")

    def test_katakana_normalizes(self):
        self.assertEqual(katakana_to_hiragana("カタカナ"), "かたかな")
        self.assertEqual(grade_reading("カタカナ", ["かたかな"]), "correct")

    def test_romaji_and_kana_both_accepted(self):
        self.assertEqual(grade_reading("taberu", ["たべる"]), "correct")
        self.assertEqual(grade_reading("たべる", ["たべる"]), "correct")
        self.assertEqual(grade_reading("nomu", ["たべる"]), "wrong")

    def test_normalize_reading_strips_spaces(self):
        self.assertEqual(normalize_reading("た べ る"), "たべる")


if __name__ == "__main__":
    unittest.main()

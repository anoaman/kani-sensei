import unittest

from shared.answers import (
    grade_meaning,
    grade_reading,
    katakana_to_hiragana,
    meaning_tolerance,
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

    def test_tolerance_grows_with_length(self):
        self.assertEqual(meaning_tolerance("hi"), 0)
        self.assertEqual(meaning_tolerance("big"), 0)
        self.assertEqual(meaning_tolerance("fire"), 1)
        self.assertEqual(meaning_tolerance("mount"), 1)
        self.assertEqual(meaning_tolerance("banana"), 2)
        self.assertEqual(meaning_tolerance("bananas"), 2)
        self.assertEqual(meaning_tolerance("mountain"), 3)
        self.assertEqual(meaning_tolerance("2011"), 0)
        self.assertEqual(meaning_tolerance("twenty 1"), 0)

    def test_swapped_letters_count_as_one_typo(self):
        self.assertEqual(grade_meaning("fier", ["fire"]), "almost")
        self.assertEqual(grade_meaning("rian", ["rain"]), "almost")
        self.assertEqual(grade_meaning("thrid day", ["Third Day"]), "almost")

    def test_one_past_the_allowance_is_close(self):
        self.assertEqual(grade_meaning("bgi", ["big"]), "close")

    def test_another_items_meaning_is_wrong(self):
        taken = lambda got: got == "three"
        self.assertEqual(grade_meaning("three", ["tree"], taken=taken), "wrong")
        self.assertEqual(grade_meaning("three", ["tree"]), "almost")

    def test_a_number_answer_must_match_exactly(self):
        self.assertEqual(grade_meaning("2012", ["2011"]), "wrong")
        self.assertEqual(grade_meaning("2011", ["2011"]), "correct")


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

    def test_one_kana_off_is_close(self):
        self.assertEqual(grade_reading("たべう", ["たべる"]), "close")
        self.assertEqual(grade_reading("かわ", ["がわ"]), "close")
        self.assertEqual(grade_reading("きつて", ["きって"]), "close")
        self.assertEqual(grade_reading("きょ", ["きょう"]), "close")

    def test_a_different_word_stays_wrong(self):
        self.assertEqual(grade_reading("やま", ["かわ"]), "wrong")


if __name__ == "__main__":
    unittest.main()

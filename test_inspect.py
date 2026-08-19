import unittest

from shared.inspect import (
    build_inspect_card,
    first_audio_url,
    first_sentence,
    labeled_readings,
    wk_url,
)


RAW = {
    "component_subject_ids": [1, 2],
    "visually_similar_subject_ids": [9],
    "amalgamation_subject_ids": [30, 31],
    "parts_of_speech": ["noun"],
    "meaning_mnemonic": "The <radical>fire</radical> burns.",
    "reading_mnemonic": "You say <reading>hi</reading>.",
    "context_sentences": [{"ja": "火が強い。", "en": "The fire is strong."}],
    "pronunciation_audios": [
        {"url": "https://cdn.example/hi.ogg", "content_type": "audio/ogg"},
        {"url": "https://cdn.example/hi.mp3", "content_type": "audio/mpeg"},
    ],
}


class InspectTests(unittest.TestCase):
    def test_wk_url_uses_type_and_characters(self):
        self.assertEqual(wk_url("kanji", "火"), "https://www.wanikani.com/kanji/火")
        self.assertEqual(
            wk_url("radical", None, slug="fire"),
            "https://www.wanikani.com/radicals/fire",
        )

    def test_prefers_mpeg_audio_and_first_sentence(self):
        self.assertEqual(first_audio_url(RAW), "https://cdn.example/hi.mp3")
        self.assertEqual(first_sentence(RAW)["ja"], "火が強い。")

    def test_labeled_readings_keep_type(self):
        readings = labeled_readings([
            {"reading": "ひ", "primary": True, "type": "kunyomi", "accepted_answer": True},
            {"reading": "カ", "primary": False, "type": "onyomi", "accepted_answer": True},
            {"reading": "nope", "accepted_answer": False},
        ])
        self.assertEqual([item["reading"] for item in readings], ["ひ", "カ"])
        self.assertEqual(readings[0]["type"], "kunyomi")

    def test_card_wires_related_subjects(self):
        related = [
            {"subject_id": 1, "characters": "一", "meaning": "One", "type": "radical", "level": 1, "slug": "one"},
            {"subject_id": 2, "characters": "火", "meaning": "Fire", "type": "radical", "level": 1, "slug": "fire"},
            {"subject_id": 9, "characters": "大", "meaning": "Big", "type": "kanji", "level": 1, "slug": "big"},
            {"subject_id": 30, "characters": "花火", "meaning": "Fireworks", "type": "vocabulary", "level": 3, "slug": "hanabi"},
        ]
        card = build_inspect_card(
            14, "kanji", "火", "fire", "Fire",
            [{"meaning": "Fire", "primary": True, "accepted_answer": True}],
            [{"reading": "ひ", "primary": True, "type": "kunyomi", "accepted_answer": True}],
            RAW, level=1, srs_stage=3, related=related,
        )
        self.assertEqual([c["characters"] for c in card["components"]], ["一", "火"])
        self.assertEqual(card["similar"][0]["characters"], "大")
        self.assertEqual(card["used_in"][0]["characters"], "花火")
        self.assertEqual(card["srs_name"], "apprentice 3")
        self.assertEqual(card["sentence"]["en"], "The fire is strong.")
        self.assertTrue(card["mnemonic"]["meaning"])


if __name__ == "__main__":
    unittest.main()

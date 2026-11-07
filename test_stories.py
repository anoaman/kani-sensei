import unittest

from shared.reader import build_lexicon
from shared.stories import (
    MAX_PAGES,
    PAGE_SENTENCES,
    band_of,
    band_range,
    needs_rebuild,
    sentence_trail,
    story_violations,
)


def entry(**kwargs):
    base = {
        "meanings": [],
        "readings": [],
        "parts_of_speech": [],
        "audio_url": None,
        "lesson_position": 0,
        "level": 1,
        "type": "kanji",
    }
    base.update(kwargs)
    if "readings" not in kwargs and base.get("reading"):
        base["readings"] = [base["reading"]]
    if "meanings" not in kwargs and base.get("meaning"):
        base["meanings"] = [base["meaning"]]
    return base


def lexicon():
    return build_lexicon([
        entry(id=1, characters="日", meaning="sun", reading="にち", level=1),
        entry(id=2, characters="語", meaning="language", reading="ご", level=5),
    ])


def sentence(source_id, covers, word_ids, sentence_idx=0):
    return {
        "source_id": source_id,
        "sentence_idx": sentence_idx,
        "ja": f"s{source_id}",
        "en": "",
        "covers": set(covers),
        "word_ids": set(word_ids),
    }


def order_of(pages):
    return [item["source_id"] for page in pages for item in page]


class BandTests(unittest.TestCase):
    def test_band_of_groups_levels_by_three(self):
        for level in (1, 2, 3):
            self.assertEqual(band_of(level), 1)
        for level in (4, 5, 6):
            self.assertEqual(band_of(level), 4)
        self.assertEqual(band_of(60), 58)
        self.assertEqual(band_range(1), (1, 3))
        self.assertEqual(band_range(58), (58, 60))
        self.assertEqual(band_range(60), (60, 60))

    def test_band_of_rejects_levels_outside_the_catalog(self):
        with self.assertRaises(ValueError):
            band_of(0)
        with self.assertRaises(ValueError):
            band_of(61)


class ViolationTests(unittest.TestCase):
    def test_kanji_above_the_band_is_reported(self):
        story = {"pages": [{"sentences": [
            {"ja": "日。", "en": "day"},
            {"ja": "語。", "en": "language"},
        ]}]}
        violations = story_violations(story, lexicon(), 3)
        self.assertEqual(violations, [{
            "page": 1,
            "sentence": 2,
            "kanji": "語",
            "level": 5,
        }])

    def test_band_kanji_passes(self):
        story = {"pages": [{"sentences": [{"ja": "日はいい。", "en": "The day is good."}]}]}
        self.assertEqual(story_violations(story, lexicon(), 3), [])

    def test_kanji_missing_from_the_lexicon_is_reported(self):
        story = {"pages": [{"sentences": [{"ja": "本。", "en": "book"}]}]}
        violations = story_violations(story, lexicon(), 3)
        self.assertEqual(violations[0]["kanji"], "本")
        self.assertIsNone(violations[0]["level"])


class TrailTests(unittest.TestCase):
    def test_order_chains_on_shared_words_and_covers_the_targets(self):
        candidates = [
            sentence(1, {1, 2, 3}, {100}),
            sentence(2, {1}, {7}),
            sentence(3, {2}, {7, 8}),
            sentence(4, {3}, {8}),
        ]
        chained = sentence_trail(candidates, [1, 2, 3], {7})
        self.assertEqual(order_of(chained), [2, 3, 4])
        covered = set()
        for page in chained:
            for item in page:
                covered |= set(item["covers"])
        self.assertEqual(covered, {1, 2, 3})

        # Nothing is already in play, so the sentence that covers more wins.
        widest = sentence_trail(candidates, [1, 2, 3], set())
        self.assertEqual(order_of(widest), [1])

    def test_pages_are_capped_at_five_by_five(self):
        candidates = [
            sentence(item, {item}, {item, item - 1} if item > 1 else {item})
            for item in range(1, 31)
        ]
        pages = sentence_trail(candidates, list(range(1, 31)), set())
        self.assertEqual(len(pages), MAX_PAGES)
        self.assertTrue(all(len(page) == PAGE_SENTENCES for page in pages))
        self.assertEqual(len(order_of(pages)), MAX_PAGES * PAGE_SENTENCES)
        self.assertEqual(order_of(pages), list(range(1, 26)))


class RebuildTests(unittest.TestCase):
    def test_version_change_asks_for_a_rebuild(self):
        self.assertTrue(needs_rebuild([], 1))
        self.assertFalse(needs_rebuild([1, 1], 1))
        self.assertTrue(needs_rebuild([1], 2))
        self.assertTrue(needs_rebuild([1, 2], 2))


if __name__ == "__main__":
    unittest.main()

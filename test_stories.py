import unittest

from shared.reader import build_lexicon
from shared.stories import (
    MAX_PAGES,
    PAGE_SENTENCES,
    WORDS_PAGE_SIZE,
    band_of,
    band_range,
    iter_authored,
    needs_rebuild,
    pages_for_words,
    story_is_stale,
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

    def test_the_same_japanese_sentence_is_not_repeated(self):
        first = sentence(1, {1}, {1})
        first["ja"] = "同じです。"
        second = sentence(2, {2}, {1})
        second["ja"] = "同じです。"
        third = sentence(3, {2}, {9})
        pages = sentence_trail([first, second, third], [1, 2], set())
        texts = [item["ja"] for page in pages for item in page]
        self.assertEqual(texts, ["同じです。", third["ja"]])
        self.assertEqual(order_of(pages), [1, 3])


class AuthoredFileTests(unittest.TestCase):
    def test_written_stories_have_three_to_five_pages(self):
        stories = iter_authored()
        self.assertEqual([story["band"] for story in stories], [1, 4, 7])
        for story in stories:
            self.assertGreaterEqual(int(story["version"]), 1)
            self.assertTrue((story.get("title") or "").strip())
            self.assertGreaterEqual(len(story["pages"]), 3)
            self.assertLessEqual(len(story["pages"]), 5)
            for page in story["pages"]:
                self.assertTrue((page.get("title") or "").strip())
                sentences = page["sentences"]
                self.assertGreaterEqual(len(sentences), 5)
                self.assertLessEqual(len(sentences), 8)
                for sentence in sentences:
                    self.assertTrue(sentence["ja"].strip())
                    self.assertTrue(sentence["en"].strip())


def word(subject_id, characters, sentences, meaning="meaning"):
    return {
        "id": subject_id,
        "characters": characters,
        "meaning": meaning,
        "context_sentences": sentences,
    }


class WordPassageTests(unittest.TestCase):
    def test_every_word_is_covered_and_a_high_kanji_falls_back(self):
        items = [
            word(item, "日", [{"ja": f"日が{item}。", "en": f"Sun {item}."}], meaning=f"sun {item}")
            for item in range(1, 8)
        ]
        items.append(word(8, "日", [{"ja": "語です。", "en": "It is language."}], meaning="sun"))
        pages = pages_for_words(items, lexicon(), 1)
        self.assertEqual(len(pages), 2)
        self.assertEqual(len(pages[0]["sentences"]), WORDS_PAGE_SIZE)
        self.assertEqual(len(pages[1]["sentences"]), 2)
        covered = set()
        for page in pages:
            covered |= set(page["covers"])
        self.assertEqual(covered, set(range(1, 9)))
        fallback = pages[1]["sentences"][-1]
        self.assertEqual(fallback["ja"], "日があります。")
        self.assertEqual(fallback["en"], "sun")
        self.assertIsNone(fallback["source_id"])

    def test_a_sentence_inside_the_level_is_kept_with_its_english(self):
        item = word(4, "日", [
            {"ja": "語です。", "en": "It is language."},
            {"ja": "日はいい。", "en": "The day is good."},
        ])
        pages = pages_for_words([item], lexicon(), 1)
        sentence = pages[0]["sentences"][0]
        self.assertEqual(sentence["ja"], "日はいい。")
        self.assertEqual(sentence["en"], "The day is good.")
        self.assertEqual(sentence["source_id"], 4)
        self.assertEqual(pages[0]["covers"], {4})

    def test_word_pages_are_not_capped_at_the_band_limit(self):
        items = [
            word(item, "日", [{"ja": f"日が{item}。", "en": "day"}], meaning="sun")
            for item in range(1, 32)
        ]
        pages = pages_for_words(items, lexicon(), 1)
        total = sum(len(page["sentences"]) for page in pages)
        self.assertEqual(total, 31)
        self.assertGreater(total, MAX_PAGES * PAGE_SENTENCES)
        self.assertEqual(len(pages), 6)


class RebuildTests(unittest.TestCase):
    def test_version_change_asks_for_a_rebuild(self):
        self.assertTrue(needs_rebuild([], 1))
        self.assertFalse(needs_rebuild([1, 1], 1))
        self.assertTrue(needs_rebuild([1], 2))
        self.assertTrue(needs_rebuild([1, 2], 2))

    def test_a_short_story_is_rebuilt_even_when_the_version_matches(self):
        self.assertFalse(story_is_stale(4, 4, [1, 1, 1, 1], 1))
        self.assertFalse(story_is_stale(5, 4, [1, 1, 1, 1, 1], 1))
        self.assertTrue(story_is_stale(2, 4, [1, 1], 1))
        self.assertTrue(story_is_stale(4, 4, [1, 2, 1, 1], 2))


if __name__ == "__main__":
    unittest.main()

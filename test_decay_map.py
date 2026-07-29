import unittest
from datetime import datetime, timezone, timedelta

from shared.decay_map import build_decay_map, classify_item


NOW = datetime(2026, 7, 29, tzinfo=timezone.utc)


def row(subject_id, level, correct, incorrect, stage=1, due=True):
    return (subject_id, level, "vocabulary", "語", "Word", correct, 0,
            correct, incorrect, stage,
            NOW - timedelta(days=1) if due else NOW + timedelta(days=1), None)


class DecayMapTests(unittest.TestCase):
    def test_low_accuracy_and_low_stage_is_high_risk(self):
        result = classify_item(row(1, 3, 2, 8), now=NOW)
        self.assertEqual(result["band"], "high")
        self.assertTrue(result["due"])

    def test_strong_item_is_low_risk(self):
        result = classify_item(row(2, 3, 20, 0, stage=8), now=NOW)
        self.assertEqual(result["band"], "low")
        self.assertEqual(result["accuracy"], 100.0)

    def test_levels_are_sorted_by_risk(self):
        result = build_decay_map([row(1, 2, 1, 9), row(2, 8, 10, 0, stage=8)], now=NOW)
        self.assertEqual(result["levels"][0]["level"], 2)
        self.assertEqual(result["summary"]["suggested_levels"], [2])


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timezone

from shared.course import (
    GURU,
    level_summary,
    next_available,
    next_stage,
    stage_bucket,
    unlockable,
)


class SrsMathTests(unittest.TestCase):
    def test_clean_review_moves_up_one(self):
        self.assertEqual(next_stage(1, 0, 0), 2)
        self.assertEqual(next_stage(8, 0, 0), 9)

    def test_apprentice_penalty(self):
        self.assertEqual(next_stage(4, 1, 0), 3)
        self.assertEqual(next_stage(4, 2, 1), 2)  # ceil(3/2)=2

    def test_guru_and_up_penalty_doubles(self):
        self.assertEqual(next_stage(6, 1, 0), 4)
        self.assertEqual(next_stage(8, 2, 2), 4)

    def test_never_below_apprentice_one(self):
        self.assertEqual(next_stage(2, 5, 5), 1)

    def test_intervals_round_down_to_hour(self):
        now = datetime(2026, 10, 8, 22, 47, tzinfo=timezone.utc)
        self.assertEqual(next_available(1, 5, now), datetime(2026, 10, 9, 2, 0, tzinfo=timezone.utc))
        # Levels 1-2 are accelerated: Apprentice 1 comes back in 2h.
        self.assertEqual(next_available(1, 1, now), datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc))
        self.assertIsNone(next_available(9, 1, now))


class UnlockTests(unittest.TestCase):
    def test_radicals_and_outside_components_unlock_at_once(self):
        items = {
            1: {"unlocked": False, "stage": 0, "components": []},
            2: {"unlocked": False, "stage": 0, "components": [999]},  # earlier level
            3: {"unlocked": False, "stage": 0, "components": [1]},
        }
        self.assertEqual(sorted(unlockable(items)), [1, 2])

    def test_kanji_waits_for_every_radical_at_guru(self):
        items = {
            1: {"unlocked": True, "stage": GURU, "components": []},
            2: {"unlocked": True, "stage": 4, "components": []},
            3: {"unlocked": False, "stage": 0, "components": [1, 2]},
        }
        self.assertEqual(unlockable(items), [])
        items[2]["stage"] = GURU
        self.assertEqual(unlockable(items), [3])


class SummaryTests(unittest.TestCase):
    def item(self, kind, stage, bucket, available_at=None):
        return {"type": kind, "in_course": True, "stage": stage, "bucket": bucket,
                "available_at": available_at}

    def test_pass_math_and_queue_counts(self):
        now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
        items = [self.item("kanji", 5, "guru") for _ in range(9)]
        items.append(self.item("kanji", 2, "apprentice", "2026-10-08T10:00:00+00:00"))
        items.append(self.item("radical", 1, "apprentice", "2026-10-08T15:00:00+00:00"))
        items.append(self.item("vocabulary", 0, "lesson"))
        summary = level_summary(items, (now, None, 0), now)
        self.assertEqual((summary["kanji_guru"], summary["kanji_needed"]), (9, 9))
        self.assertEqual(summary["reviews"], 1)
        self.assertEqual(summary["lessons"], 1)
        self.assertTrue(summary["next_review_at"].startswith("2026-10-08T15"))

    def test_buckets(self):
        self.assertEqual(stage_bucket(0, unlocked=False), "locked")
        self.assertEqual(stage_bucket(0), "lesson")
        self.assertEqual(stage_bucket(6), "guru")
        self.assertEqual(stage_bucket(9), "burned")


if __name__ == "__main__":
    unittest.main()

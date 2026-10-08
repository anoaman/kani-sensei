import unittest
from datetime import datetime, timedelta, timezone

from shared.course import (
    GURU,
    RELEARN_FLOOR,
    level_summary,
    mode_for,
    next_available,
    outcome,
    review_stage,
    stage_bucket,
    stage_name,
)

NOW = datetime(2026, 10, 8, 22, 47, tzinfo=timezone.utc)


class OutcomeTests(unittest.TestCase):
    def test_check_clean_goes_straight_to_guru(self):
        self.assertEqual(outcome("check", 0, 0, 0), GURU)

    def test_check_any_miss_goes_to_relearn(self):
        self.assertEqual(outcome("check", 0, 0, 1), RELEARN_FLOOR)

    def test_relearn_takes_three_clean_passes(self):
        stage = outcome("check", 0, 1, 0)
        for _ in range(3):
            stage = outcome("relearn", stage, 0, 0)
        self.assertEqual(stage, GURU)

    def test_relearn_slips_one_but_not_below_floor(self):
        self.assertEqual(outcome("relearn", 4, 2, 1), 3)
        self.assertEqual(outcome("relearn", RELEARN_FLOOR, 1, 0), RELEARN_FLOOR)

    def test_stage_names(self):
        self.assertEqual(stage_name(0), "Unchecked")
        self.assertEqual(stage_name(2), "Relearn ○○○")
        self.assertEqual(stage_name(4), "Relearn ●●○")
        self.assertEqual(stage_name(5), "Guru 1")

    def test_ahead_never_promotes_but_misses_count(self):
        self.assertEqual(outcome("ahead", 6, 0, 0), 6)
        self.assertEqual(outcome("ahead", 6, 1, 0), 4)

    def test_review_uses_wanikani_penalty(self):
        self.assertEqual(review_stage(5, 0, 0), 6)
        self.assertEqual(review_stage(8, 2, 2), 4)
        self.assertEqual(review_stage(3, 5, 5), RELEARN_FLOOR)


class ClockTests(unittest.TestCase):
    def test_apprentice_is_always_open(self):
        self.assertEqual(next_available(3, NOW), NOW)

    def test_guru_waits_a_week_rounded_down(self):
        self.assertEqual(next_available(GURU, NOW), datetime(2026, 10, 15, 21, 0, tzinfo=timezone.utc))
        self.assertIsNone(next_available(9, NOW))

    def test_mode_for(self):
        self.assertEqual(mode_for(0, NOW, NOW), "check")
        self.assertEqual(mode_for(2, NOW + timedelta(days=1), NOW), "relearn")
        self.assertEqual(mode_for(6, NOW - timedelta(minutes=1), NOW), "reviews")
        self.assertEqual(mode_for(6, NOW + timedelta(days=3), NOW), "ahead")
        self.assertIsNone(mode_for(9, None, NOW))


class SummaryTests(unittest.TestCase):
    def item(self, kind, stage, available_at=None):
        return {"type": kind, "in_course": True, "stage": stage,
                "bucket": stage_bucket(stage), "available_at": available_at}

    def test_counts_and_next_mode(self):
        items = [self.item("kanji", 5, "2026-10-20T00:00:00+00:00") for _ in range(9)]
        items.append(self.item("kanji", 6, "2026-10-08T10:00:00+00:00"))
        items.append(self.item("radical", 2, NOW.isoformat()))
        items.append(self.item("vocabulary", 0, NOW.isoformat()))
        summary = level_summary(items, (NOW, None, 0), NOW)
        self.assertEqual((summary["reviews"], summary["relearn"], summary["check"], summary["ahead"]), (1, 1, 1, 9))
        self.assertEqual(summary["next_mode"], "reviews")
        self.assertEqual((summary["kanji_guru"], summary["kanji_needed"]), (10, 9))
        self.assertTrue(summary["next_review_at"].startswith("2026-10-20"))

    def test_buckets(self):
        self.assertEqual(stage_bucket(0), "unchecked")
        self.assertEqual(stage_bucket(3), "relearn")
        self.assertEqual(stage_bucket(9), "burned")


if __name__ == "__main__":
    unittest.main()

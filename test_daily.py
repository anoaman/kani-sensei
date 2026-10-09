import unittest
from datetime import date, datetime, timezone

from shared.daily import streak_from, today


class DailyTests(unittest.TestCase):
    def test_day_rolls_over_at_wib_midnight(self):
        self.assertEqual(today(datetime(2026, 10, 9, 16, 59, tzinfo=timezone.utc)), date(2026, 10, 9))
        self.assertEqual(today(datetime(2026, 10, 9, 17, 0, tzinfo=timezone.utc)), date(2026, 10, 10))

    def test_streak_counts_today_when_done(self):
        days = [date(2026, 10, 9), date(2026, 10, 8), date(2026, 10, 7)]
        self.assertEqual(streak_from(days, date(2026, 10, 9)), 3)

    def test_open_today_does_not_break_yesterdays_streak(self):
        days = [date(2026, 10, 8), date(2026, 10, 7)]
        self.assertEqual(streak_from(days, date(2026, 10, 9)), 2)

    def test_missed_day_resets(self):
        days = [date(2026, 10, 9), date(2026, 10, 7), date(2026, 10, 6)]
        self.assertEqual(streak_from(days, date(2026, 10, 9)), 1)
        self.assertEqual(streak_from([date(2026, 10, 7)], date(2026, 10, 9)), 0)


if __name__ == "__main__":
    unittest.main()

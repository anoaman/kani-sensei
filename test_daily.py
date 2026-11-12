import unittest
from datetime import date, datetime, timezone

import shared.course as course
import shared.daily as daily
from shared.daily import balance_daily, parse_daily_size, radical_cap_for, resize_daily, streak_from, today


class FakeDailyDb:
    """Just enough of the database for saving and resizing a day."""

    def __init__(self, subject_ids, done_ids, completed_at=None):
        self.row = (list(subject_ids), list(done_ids), completed_at)
        self.size = 20
        self.pool = [(1000 + index, "kanji") for index in range(40)]

    def has_relation(self, _name):
        return True

    def execute(self, sql, args=None, fetch=False):
        text = " ".join(sql.split())
        if text.startswith("insert into daily_settings") and "do nothing" in text:
            return []
        if text.startswith("insert into daily_settings"):
            self.size = args[0]
            return []
        if text.startswith("select size from daily_settings"):
            return [(self.size,)]
        if text.startswith("select subject_ids"):
            return [self.row] if self.row else []
        if text.startswith("update daily_sets"):
            self.row = (list(args[0]), list(args[1]), "now" if args[2] else None)
            return []
        if "s.object_type" in text:
            return list(self.pool)
        if text.startswith("select day from daily_sets"):
            return []
        if text.startswith("insert into daily_sets"):
            self.row = (list(args[1]), [], None)
            return []
        raise AssertionError(text)


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

    def test_radicals_stay_capped_when_kanji_or_words_are_waiting(self):
        items = [(index, "radical") for index in range(15)]
        items += [(100 + index, "kanji") for index in range(10)]
        items += [(200 + index, "vocabulary") for index in range(10)]
        picked = balance_daily(items, 20)
        self.assertEqual(
            picked,
            [0, 1, 2, 3, 4] + [100 + index for index in range(10)] + [200 + index for index in range(5)],
        )

    def test_radical_only_pool_keeps_the_old_order(self):
        items = [(index, "radical") for index in range(30)]
        self.assertEqual(balance_daily(items, 20), list(range(20)))

    def test_spare_radicals_fill_seats_nothing_else_can(self):
        items = [(index, "radical") for index in range(8)] + [(100, "kanji")]
        self.assertEqual(balance_daily(items, 20), [0, 1, 2, 3, 4, 100, 5, 6, 7])

    def test_smaller_day_keeps_the_radical_ratio(self):
        items = [(index, "radical") for index in range(15)]
        items += [(100 + index, "kanji") for index in range(10)]
        items += [(200 + index, "vocabulary") for index in range(10)]
        self.assertEqual(radical_cap_for(10), 2)
        self.assertEqual(radical_cap_for(5), 1)
        self.assertEqual(
            balance_daily(items, 10, radical_cap_for(10)),
            [0, 1] + [100 + index for index in range(8)],
        )

    def test_resize_keeps_finished_items_and_drops_the_tail(self):
        subject_ids = list(range(20))
        done = [2, 5, 9]
        resized = resize_daily(subject_ids, done, 10)
        self.assertEqual(resized, list(range(10)))
        self.assertTrue(set(done).issubset(resized))
        self.assertEqual(len(resized), 10)

    def test_resize_keeps_finished_items_that_sit_past_the_cut(self):
        resized = resize_daily(list(range(20)), [17, 18, 19], 10)
        self.assertEqual(resized, [0, 1, 2, 3, 4, 5, 6, 17, 18, 19])

    def test_resize_does_not_drop_finished_items_past_the_new_size(self):
        subject_ids = list(range(20))
        done = list(range(12))
        self.assertEqual(resize_daily(subject_ids, done, 10), done)

    def test_saved_size_shrinks_today_and_keeps_a_finished_day_complete(self):
        daily._SCHEMA_READY = False
        course._SCHEMA_READY = False
        db = FakeDailyDb(range(20), range(12))
        result = daily.set_daily_size(db, 10)
        self.assertEqual(db.size, 10)
        self.assertEqual(result["size"], 10)
        self.assertEqual(result["total"], 12)
        self.assertEqual(result["done"], 12)
        self.assertTrue(result["completed"])
        self.assertIsNotNone(db.row[2])

    def test_saved_size_fills_extra_seats_when_the_day_grows(self):
        daily._SCHEMA_READY = False
        course._SCHEMA_READY = False
        db = FakeDailyDb(range(5), [])
        result = daily.set_daily_size(db, 10)
        self.assertEqual(result["size"], 10)
        self.assertEqual(result["total"], 10)
        self.assertEqual(result["done"], 0)
        self.assertFalse(result["completed"])
        self.assertEqual(db.row[0][:5], list(range(5)))
        self.assertTrue(all(item >= 1000 for item in db.row[0][5:]))

    def test_size_must_be_one_of_the_four(self):
        self.assertEqual(parse_daily_size("10"), 10)
        self.assertEqual(parse_daily_size(20), 20)
        with self.assertRaises(ValueError):
            parse_daily_size(12)
        with self.assertRaises(ValueError):
            parse_daily_size("nope")

    def test_missed_day_resets(self):
        days = [date(2026, 10, 9), date(2026, 10, 7), date(2026, 10, 6)]
        self.assertEqual(streak_from(days, date(2026, 10, 9)), 1)
        self.assertEqual(streak_from([date(2026, 10, 7)], date(2026, 10, 9)), 0)


if __name__ == "__main__":
    unittest.main()

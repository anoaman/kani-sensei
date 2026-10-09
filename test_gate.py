import unittest
from datetime import datetime, timedelta, timezone

from shared.gate import (
    CLEAN_WINDOW, SCRAPED_WINDOW, TIERS, earned_window, gate_state, seconds_left,
    tier_for, verdict,
)


def wib(hour, minute=0, day=9):
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone(timedelta(hours=7))).astimezone(timezone.utc)


class GateTests(unittest.TestCase):
    def test_locked_in_the_day_without_a_pass(self):
        self.assertFalse(gate_state(wib(14), None)["open"])

    def test_pass_opens_until_its_window_closes(self):
        until = wib(14) + SCRAPED_WINDOW
        self.assertTrue(gate_state(wib(15, 29), until)["open"])
        self.assertEqual(gate_state(wib(15, 29), until)["until"], until)
        self.assertFalse(gate_state(wib(15, 31), until)["open"])

    def test_night_is_open_until_eight(self):
        late = gate_state(wib(23), None)
        self.assertTrue(late["open"])
        self.assertEqual(late["reason"], "night")
        self.assertEqual(late["until"], wib(8, day=10))
        early = gate_state(wib(7, 59), None)
        self.assertEqual(early["until"], wib(8))
        self.assertFalse(gate_state(wib(8), None)["open"])


class GateTierTests(unittest.TestCase):
    def test_each_unlock_costs_more(self):
        sizes = [tier_for(n)["size"] for n in range(4)]
        self.assertEqual(sizes, [5, 7, 10, 10])
        self.assertEqual(tier_for(0)["unlock"], 1)
        self.assertEqual(tier_for(5)["pool"], TIERS[-1][2])

    def test_window_is_earned(self):
        self.assertEqual(earned_window(0), CLEAN_WINDOW)
        self.assertEqual(earned_window(1), SCRAPED_WINDOW)

    def test_verdict(self):
        now = wib(14)
        self.assertEqual(verdict(None, 5, 5, 1), {"settled": False})
        self.assertTrue(verdict(now, 5, 5, 1)["passed"])
        self.assertEqual(verdict(now, 5, 5, 1)["window"], CLEAN_WINDOW)
        self.assertEqual(verdict(now, 4, 5, 1)["window"], SCRAPED_WINDOW)
        self.assertFalse(verdict(now, 3, 5, 1)["passed"])
        self.assertFalse(verdict(now, 1, 2, "0")["passed"])  # jsonb text from SQL
        self.assertTrue(verdict(now, 2, 5, None)["passed"])  # pre-rules gates

    def test_seconds_left(self):
        now = wib(14)
        self.assertEqual(seconds_left((now - timedelta(seconds=5)).isoformat(), 15, now), 10.0)
        self.assertEqual(seconds_left((now - timedelta(seconds=50)).isoformat(), "15", now), 0.0)
        self.assertIsNone(seconds_left(None, 15, now))


if __name__ == "__main__":
    unittest.main()

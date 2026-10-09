import unittest
from datetime import datetime, timedelta, timezone

from shared.gate import WINDOW, gate_state


def wib(hour, minute=0, day=9):
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone(timedelta(hours=7))).astimezone(timezone.utc)


class GateTests(unittest.TestCase):
    def test_locked_in_the_day_without_a_pass(self):
        self.assertFalse(gate_state(wib(14), None)["open"])

    def test_pass_opens_for_the_window(self):
        passed = wib(14)
        self.assertTrue(gate_state(wib(16, 59), passed)["open"])
        self.assertEqual(gate_state(wib(16, 59), passed)["until"], passed + WINDOW)
        self.assertFalse(gate_state(wib(17, 1), passed)["open"])

    def test_night_is_open_until_eight(self):
        late = gate_state(wib(23), None)
        self.assertTrue(late["open"])
        self.assertEqual(late["reason"], "night")
        self.assertEqual(late["until"], wib(8, day=10))
        early = gate_state(wib(7, 59), None)
        self.assertEqual(early["until"], wib(8))
        self.assertFalse(gate_state(wib(8), None)["open"])


if __name__ == "__main__":
    unittest.main()

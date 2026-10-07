import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from api.overview import data_status
from api.sync import last_good_sync
from api.tick import build_nudge, cached_snapshot


class FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, sql, args=None, fetch=False):
        self.calls.append((sql, args, fetch))
        return self.rows


class OfflineModeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc)

    def test_current_snapshot_with_token_is_live(self):
        sync = {"finished_at": self.now - timedelta(hours=2)}
        status = data_status(sync, True, now=self.now)
        self.assertEqual(status["mode"], "live")
        self.assertEqual(status["age_hours"], 2.0)

    def test_current_snapshot_without_token_is_cached(self):
        sync = {"finished_at": self.now - timedelta(hours=2)}
        status = data_status(sync, False, now=self.now)
        self.assertEqual(status["mode"], "cached")
        self.assertFalse(status["token_configured"])

    def test_old_snapshot_is_stale_even_if_token_is_configured(self):
        sync = {"finished_at": self.now - timedelta(hours=73)}
        self.assertEqual(data_status(sync, True, now=self.now)["mode"], "stale")

    def test_no_successful_sync_is_unavailable(self):
        self.assertEqual(data_status(None, False, now=self.now)["mode"], "unavailable")

    def test_last_good_sync_preserves_counts(self):
        db = FakeDb([(self.now, {"subjects": 100})])
        result = last_good_sync(db)
        self.assertEqual(result["finished_at"], self.now)
        self.assertEqual(result["counts"]["subjects"], 100)

    def test_cached_snapshot_builds_nudge_data(self):
        db = FakeDb([(42, 88, 17, self.now)])
        with patch("api.tick.NeonClient", return_value=db):
            result = cached_snapshot("postgres://example")
        self.assertEqual(result["source"], "cached")
        self.assertEqual(result["reviews"], 42)
        self.assertEqual(result["apprentice"], 88)
        self.assertEqual(result["level"], 17)

    def test_cached_snapshot_requires_a_successful_sync(self):
        db = FakeDb([(0, 0, 0, None)])
        with patch("api.tick.NeonClient", return_value=db):
            self.assertIsNone(cached_snapshot("postgres://example"))

    def test_cached_nudge_discloses_its_source(self):
        message = build_nudge(self.now, 42, 88, "?", 17, source="cached")
        self.assertIn("Using last synced data", message)


if __name__ == "__main__":
    unittest.main()

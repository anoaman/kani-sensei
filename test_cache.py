import unittest

from shared import cache


class CacheTests(unittest.TestCase):
    def tearDown(self):
        cache.clear()

    def test_put_get_and_clear(self):
        cache.put("overview:1", {"ok": True})
        self.assertEqual(cache.get("overview:1", 60), {"ok": True})
        cache.clear("overview:1")
        self.assertIsNone(cache.get("overview:1", 60))

    def test_expired_entry_is_dropped(self):
        cache.put("stale", 1)
        stamped, value = cache._STORE["stale"]
        cache._STORE["stale"] = (stamped - 10, value)
        self.assertIsNone(cache.get("stale", 1))

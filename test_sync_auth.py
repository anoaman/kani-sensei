import unittest

from api.sync import cron_authorized


class SyncAuthTests(unittest.TestCase):
    def test_header_and_bearer_both_pass(self):
        secret = "s3cret"
        self.assertTrue(cron_authorized(secret, None, secret))
        self.assertTrue(cron_authorized(None, f"Bearer {secret}", secret))
        self.assertTrue(cron_authorized(None, f"Bearer {secret}  ".replace("  ", ""), secret))

    def test_rejects_missing_or_wrong_secret(self):
        self.assertFalse(cron_authorized("nope", None, "s3cret"))
        self.assertFalse(cron_authorized(None, "Bearer nope", "s3cret"))
        self.assertFalse(cron_authorized(None, "s3cret", "s3cret"))
        self.assertFalse(cron_authorized("s3cret", "Bearer s3cret", ""))
        self.assertFalse(cron_authorized(None, None, "s3cret"))


if __name__ == "__main__":
    unittest.main()

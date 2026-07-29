"""Shared WaniKani API client for the Kani Sensei platform.

One reusable wrapper used by every module (Decay Map, Warm-Up Quiz, Runway,
Nudge Bot). Pure stdlib to match api/tick.py — no external deps.

Handles:
  - Bearer auth + required Wanikani-Revision header
  - 500-item collection pagination (follows `pages.next_url`)
  - Rate limiting (WK allows 60 req/min) via 429 backoff + Retry-After

Usage:
    from shared.wanikani_client import WaniKaniClient
    wk = WaniKaniClient(os.environ["WANIKANI_API_KEY"])
    user = wk.get_user()
    subjects = wk.get_subjects(levels=[1, 2, 3], types=["kanji", "vocabulary"])
"""

import json
import time
import urllib.request
import urllib.error

WK_BASE = "https://api.wanikani.com/v2"
WK_REVISION = "20170710"


class WaniKaniClient:
    def __init__(self, token, timeout=15, max_retries=5):
        if not token:
            raise ValueError("WaniKani API token is required")
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries

    # ---- low-level request ------------------------------------------------

    def _request(self, url):
        """GET a single WK URL with rate-limit backoff. Returns parsed JSON."""
        attempt = 0
        while True:
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {self.token}",
                "Wanikani-Revision": WK_REVISION,
            })
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                # 429 = rate limited. Respect Retry-After, else exponential backoff.
                if e.code == 429 and attempt < self.max_retries:
                    retry_after = e.headers.get("Retry-After")
                    wait = int(retry_after) if retry_after and retry_after.isdigit() else (2 ** attempt)
                    time.sleep(wait)
                    attempt += 1
                    continue
                # 5xx = transient WK hiccup, retry a few times.
                if 500 <= e.code < 600 and attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    attempt += 1
                    continue
                raise
            except urllib.error.URLError:
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    attempt += 1
                    continue
                raise

    def _paginate(self, path):
        """Follow a WK collection through every page. Yields each `data` item."""
        url = f"{WK_BASE}{path}"
        while url:
            page = self._request(url)
            for item in page.get("data", []):
                yield item
            url = page.get("pages", {}).get("next_url")

    @staticmethod
    def _qs(params):
        """Build a query string from a dict; list values become comma-joined."""
        parts = []
        for key, val in params.items():
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                if not val:
                    continue
                val = ",".join(str(v) for v in val)
            parts.append(f"{key}={val}")
        return ("?" + "&".join(parts)) if parts else ""

    # ---- typed endpoints --------------------------------------------------

    def get_user(self):
        """Single resource — returns the `data` block (level, subscription, ...)."""
        return self._request(f"{WK_BASE}/user")["data"]

    def get_subjects(self, levels=None, types=None):
        """Subject catalog: kanji/vocabulary/radical with meanings + readings.

        types: subset of ["kanji", "vocabulary", "radical", "kana_vocabulary"]
        """
        qs = self._qs({"levels": levels, "types": types})
        return list(self._paginate(f"/subjects{qs}"))

    def get_review_statistics(self, subject_ids=None):
        """Per-subject performance: percentage_correct + meaning/reading counts."""
        qs = self._qs({"subject_ids": subject_ids})
        return list(self._paginate(f"/review_statistics{qs}"))

    def get_assignments(self, levels=None, srs_stages=None,
                        immediately_available_for_review=None):
        """SRS state per subject: srs_stage + unlocked/started/passed/burned."""
        params = {
            "levels": levels,
            "srs_stages": srs_stages,
        }
        if immediately_available_for_review is not None:
            params["immediately_available_for_review"] = str(
                immediately_available_for_review).lower()
        qs = self._qs(params)
        return list(self._paginate(f"/assignments{qs}"))

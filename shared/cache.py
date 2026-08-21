"""Tiny process-local TTL cache.

Vercel Python instances stay warm across a few requests. Caching the
dashboard payload for a short window avoids repeating the heavy Decay +
Runway scans when Kibz clicks around the SPA or reloads.
"""

import time


_STORE = {}


def get(key, ttl_seconds):
    hit = _STORE.get(key)
    if not hit:
        return None
    stamped, value = hit
    if time.time() - stamped > ttl_seconds:
        _STORE.pop(key, None)
        return None
    return value


def put(key, value):
    _STORE[key] = (time.time(), value)
    return value


def clear(key=None):
    if key is None:
        _STORE.clear()
    else:
        _STORE.pop(key, None)

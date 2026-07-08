"""
Local boundary tests for tick window logic and nudge formatting.
Run: python3 test_tick.py
Does NOT make network calls — pure unit tests for time/window/verdict logic.
"""
import sys
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))


def in_window(hour):
    return (6 <= hour < 9) or (12 <= hour < 14)


def verdict_line(reviews, apprentice):
    if apprentice > 150:
        return "circuit breaker: pause lessons."
    if reviews > 150:
        return "queue's on fire. Clear it now."
    if apprentice > 100:
        return "heavy load. Grind it down."
    if reviews > 50:
        return "solid queue. Let's go."
    return "clear to lift."


def build_nudge(t, reviews, apprentice, lessons, level):
    time_str = t.strftime("%H:%M")
    v = verdict_line(reviews, apprentice)
    link = "https://www.wanikani.com/subjects/review"
    return (
        f"<b>{time_str} WIB — {reviews} reviews due</b>\n"
        f"Apprentice: {apprentice} · Lessons: {lessons} · Level: {level}\n"
        f"Verdict: {v}\n"
        f'<a href="{link}">Open reviews →</a>'
    )


def make_wib(hour, minute=0):
    """Create a WIB datetime at a given hour."""
    return datetime(2026, 7, 8, hour, minute, 0, tzinfo=WIB)


PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
failures = []


def check(name, condition, detail=""):
    if condition:
        print(f"  {PASS}  {name}")
    else:
        print(f"  {FAIL}  {name}{' — ' + detail if detail else ''}")
        failures.append(name)


print("\n=== Window boundary tests ===")
check("05:59 outside window", not in_window(5))
check("06:00 inside morning window", in_window(6))
check("07:30 inside morning window", in_window(7))
check("08:59 inside morning window", in_window(8))
check("09:00 outside window", not in_window(9))
check("11:59 outside window", not in_window(11))
check("12:00 inside lunch window", in_window(12))
check("13:30 inside lunch window", in_window(13))
check("14:00 outside window", not in_window(14))
check("23:00 outside window", not in_window(23))

print("\n=== Verdict rules ===")
check("apprentice >150 → circuit breaker",
      "circuit breaker" in verdict_line(50, 200))
check("reviews >150 → on fire",
      "on fire" in verdict_line(200, 80))
check("apprentice >100 → heavy load",
      "heavy load" in verdict_line(50, 120))
check("reviews >50 → solid queue",
      "solid queue" in verdict_line(80, 40))
check("small queue → clear to lift",
      "clear to lift" in verdict_line(10, 20))

print("\n=== Nudge format ===")
t = make_wib(6, 0)
nudge = build_nudge(t, 84, 97, 5, 12)
check("nudge contains time",            "06:00 WIB" in nudge)
check("nudge contains review count",    "84 reviews due" in nudge)
check("nudge contains apprentice",      "Apprentice: 97" in nudge)
check("nudge contains lessons",         "Lessons: 5" in nudge)
check("nudge contains level",           "Level: 12" in nudge)
check("nudge contains WK link",         "wanikani.com/subjects/review" in nudge)

print("\n=== UTC→WIB conversion ===")
# UTC 23:00 = WIB 06:00 (+7)
utc_23 = datetime(2026, 7, 7, 23, 0, 0, tzinfo=timezone.utc)
wib_time = utc_23.astimezone(WIB)
check("UTC 23:00 → WIB 06:00", wib_time.hour == 6,
      f"got hour={wib_time.hour}")
check("UTC 23:00 → in morning window", in_window(wib_time.hour))

# UTC 05:00 = WIB 12:00
utc_05 = datetime(2026, 7, 8, 5, 0, 0, tzinfo=timezone.utc)
wib_time = utc_05.astimezone(WIB)
check("UTC 05:00 → WIB 12:00", wib_time.hour == 12,
      f"got hour={wib_time.hour}")
check("UTC 05:00 → in lunch window", in_window(wib_time.hour))

# UTC 22:59 = WIB 05:59 — outside
utc_2259 = datetime(2026, 7, 7, 22, 59, 0, tzinfo=timezone.utc)
wib_time = utc_2259.astimezone(WIB)
check("UTC 22:59 → WIB 05:59 outside", not in_window(wib_time.hour),
      f"got hour={wib_time.hour}")

print()
if failures:
    print(f"  {len(failures)} test(s) FAILED: {', '.join(failures)}")
    sys.exit(1)
else:
    print(f"  All tests passed.")

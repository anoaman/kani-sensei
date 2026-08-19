"""WaniKani-style answer checking for typed recall drills.

Meanings are case-insensitive and ignore punctuation / leading "to"/"the".
Readings accept hiragana, katakana, or romaji. Close meaning typos are
flagged as "almost" but still count wrong — WK is strict, so we stay honest.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")

# Longest-first romaji → hiragana. Covers dakuten, youon, and small tsu via
# doubling logic in romaji_to_hiragana — not as a table entry.
_ROMAJI = (
    ("kya", "きゃ"), ("kyu", "きゅ"), ("kyo", "きょ"),
    ("gya", "ぎゃ"), ("gyu", "ぎゅ"), ("gyo", "ぎょ"),
    ("sha", "しゃ"), ("shu", "しゅ"), ("sho", "しょ"),
    ("sya", "しゃ"), ("syu", "しゅ"), ("syo", "しょ"),
    ("ja", "じゃ"), ("ju", "じゅ"), ("jo", "じょ"),
    ("jya", "じゃ"), ("jyu", "じゅ"), ("jyo", "じょ"),
    ("cha", "ちゃ"), ("chu", "ちゅ"), ("cho", "ちょ"),
    ("tya", "ちゃ"), ("tyu", "ちゅ"), ("tyo", "ちょ"),
    ("nya", "にゃ"), ("nyu", "にゅ"), ("nyo", "にょ"),
    ("hya", "ひゃ"), ("hyu", "ひゅ"), ("hyo", "ひょ"),
    ("bya", "びゃ"), ("byu", "びゅ"), ("byo", "びょ"),
    ("pya", "ぴゃ"), ("pyu", "ぴゅ"), ("pyo", "ぴょ"),
    ("mya", "みゃ"), ("myu", "みゅ"), ("myo", "みょ"),
    ("rya", "りゃ"), ("ryu", "りゅ"), ("ryo", "りょ"),
    ("shi", "し"), ("chi", "ち"), ("tsu", "つ"), ("fu", "ふ"),
    ("ji", "じ"), ("zi", "じ"), ("ti", "ち"), ("tu", "つ"),
    ("si", "し"), ("hu", "ふ"), ("di", "ぢ"), ("du", "づ"),
    ("ka", "か"), ("ki", "き"), ("ku", "く"), ("ke", "け"), ("ko", "こ"),
    ("ga", "が"), ("gi", "ぎ"), ("gu", "ぐ"), ("ge", "げ"), ("go", "ご"),
    ("sa", "さ"), ("su", "す"), ("se", "せ"), ("so", "そ"),
    ("za", "ざ"), ("zu", "ず"), ("ze", "ぜ"), ("zo", "ぞ"),
    ("ta", "た"), ("te", "て"), ("to", "と"),
    ("da", "だ"), ("de", "で"), ("do", "ど"),
    ("na", "な"), ("ni", "に"), ("nu", "ぬ"), ("ne", "ね"), ("no", "の"),
    ("ha", "は"), ("hi", "ひ"), ("he", "へ"), ("ho", "ほ"),
    ("ba", "ば"), ("bi", "び"), ("bu", "ぶ"), ("be", "べ"), ("bo", "ぼ"),
    ("pa", "ぱ"), ("pi", "ぴ"), ("pu", "ぷ"), ("pe", "ぺ"), ("po", "ぽ"),
    ("ma", "ま"), ("mi", "み"), ("mu", "む"), ("me", "め"), ("mo", "も"),
    ("ya", "や"), ("yu", "ゆ"), ("yo", "よ"),
    ("ra", "ら"), ("ri", "り"), ("ru", "る"), ("re", "れ"), ("ro", "ろ"),
    ("wa", "わ"), ("wo", "を"), ("nn", "ん"),
    ("a", "あ"), ("i", "い"), ("u", "う"), ("e", "え"), ("o", "お"),
    ("n", "ん"),
)

_SMALL_TSU_CONSONANTS = set("kstcghfjzdhbpmyr")


def katakana_to_hiragana(text):
    out = []
    for char in text or "":
        code = ord(char)
        if 0x30A1 <= code <= 0x30F6:
            out.append(chr(code - 0x60))
        else:
            out.append(char)
    return "".join(out)


def looks_like_kana(text):
    return bool(_KANA_RE.search(text or ""))


def romaji_to_hiragana(text):
    """Convert lowercase romaji to hiragana. Unknown latin is left as-is."""
    raw = (text or "").strip().casefold()
    raw = raw.replace("-", "").replace("'", "")
    out = []
    i = 0
    while i < len(raw):
        if raw[i] == " ":
            i += 1
            continue
        # sokuon: kk, tte, ppa — but not nn (that's ん).
        if (
            i + 1 < len(raw)
            and raw[i] == raw[i + 1]
            and raw[i] in _SMALL_TSU_CONSONANTS
            and raw[i] != "n"
        ):
            out.append("っ")
            i += 1
            continue
        # n before a consonant (not y) becomes ん. n' already stripped.
        if raw[i] == "n" and i + 1 < len(raw):
            nxt = raw[i + 1]
            if nxt not in "aiueoyn":
                out.append("ん")
                i += 1
                continue
        matched = None
        for roma, hira in _ROMAJI:
            if raw.startswith(roma, i):
                matched = (len(roma), hira)
                break
        if matched:
            out.append(matched[1])
            i += matched[0]
        else:
            out.append(raw[i])
            i += 1
    return "".join(out)


def normalize_reading(text):
    value = unicodedata.normalize("NFKC", (text or "").strip())
    value = katakana_to_hiragana(value)
    value = value.replace(" ", "").replace("・", "").replace("-", "")
    if looks_like_kana(value):
        return value
    converted = romaji_to_hiragana(value)
    return converted if looks_like_kana(converted) else value.casefold()


def normalize_meaning(text):
    value = unicodedata.normalize("NFKC", (text or "").strip()).casefold()
    value = value.replace("&", " and ").replace("-", " ")
    value = _PUNCT_RE.sub("", value)
    value = _SPACE_RE.sub(" ", value).strip()
    for prefix in ("to ", "the ", "a ", "an "):
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
    return value


def _levenshtein(left, right, cap=2):
    if abs(len(left) - len(right)) > cap:
        return cap + 1
    if left == right:
        return 0
    prev = list(range(len(right) + 1))
    for i, lch in enumerate(left, 1):
        curr = [i]
        for j, rch in enumerate(right, 1):
            curr.append(min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + (lch != rch),
            ))
        prev = curr
        if min(prev) > cap:
            return cap + 1
    return prev[-1]


def grade_meaning(submitted, accepted):
    """Return 'correct', 'almost', or 'wrong'."""
    got = normalize_meaning(submitted)
    if not got:
        return "wrong"
    targets = [normalize_meaning(item) for item in accepted if item]
    targets = [item for item in targets if item]
    if got in targets:
        return "correct"
    for target in targets:
        if len(target) >= 5 and _levenshtein(got, target, cap=1) == 1:
            return "almost"
        ratio = SequenceMatcher(None, got, target).ratio()
        if len(target) >= 6 and ratio >= 0.88:
            return "almost"
    return "wrong"


def grade_reading(submitted, accepted):
    got = normalize_reading(submitted)
    if not got:
        return "wrong"
    targets = [normalize_reading(item) for item in accepted if item]
    if got in targets:
        return "correct"
    return "wrong"


def grade_answer(prompt_type, submitted, accepted):
    if prompt_type == "reading":
        return grade_reading(submitted, accepted)
    return grade_meaning(submitted, accepted)

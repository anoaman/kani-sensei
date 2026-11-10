"""WaniKani-style answer checking for typed recall drills.

Meanings are case-insensitive and ignore punctuation / leading "to"/"the".
Readings accept hiragana, katakana, or romaji. Close meaning typos are
graded "almost" and pass, with the spelling flagged. One extra typo is
"close": the question stays open for a single retype.
"""

from __future__ import annotations

import re
import unicodedata


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
_SMALL_TO_BIG = str.maketrans({
    "ぁ": "あ", "ぃ": "い", "ぅ": "う", "ぇ": "え", "ぉ": "お",
    "ゃ": "や", "ゅ": "ゆ", "ょ": "よ", "っ": "つ", "ゎ": "わ",
})
_RANK = {"correct": 3, "almost": 2, "close": 1, "wrong": 0}


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


def fold_kana(text):
    """Drop dakuten marks and grow small kana, for a near-miss reading check."""
    nfd = unicodedata.normalize("NFD", text or "")
    stripped = "".join(char for char in nfd if unicodedata.category(char) != "Mn")
    return stripped.translate(_SMALL_TO_BIG)


def meaning_tolerance(target):
    """How many typos a meaning of this length may have and still pass."""
    compact = (target or "").replace(" ", "")
    if not compact or any(char.isdigit() for char in compact):
        return 0
    length = len(compact)
    if length <= 3:
        return 0
    if length <= 5:
        return 1
    if length <= 7:
        return 2
    return 2 + (length // 7)


def _damerau(left, right, cap):
    """Adjacent-swap-aware edit distance, aborted past `cap`."""
    if cap < 0:
        return cap + 1
    if abs(len(left) - len(right)) > cap:
        return cap + 1
    if left == right:
        return 0
    prev_prev = None
    prev = list(range(len(right) + 1))
    for i, lch in enumerate(left, 1):
        curr = [i]
        for j, rch in enumerate(right, 1):
            cost = 0 if lch == rch else 1
            value = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and lch == right[j - 2] and left[i - 2] == rch:
                value = min(value, prev_prev[j - 2] + 1)
            curr.append(value)
        if min(curr) > cap:
            return cap + 1
        prev_prev, prev = prev, curr
    return prev[-1]


def _meaning_near(got, target):
    compact = (target or "").replace(" ", "")
    if any(char.isdigit() for char in compact):
        return "wrong"
    allowed = meaning_tolerance(target)
    distance = _damerau(got, target, cap=allowed + 1)
    if distance <= allowed:
        return "almost"
    if distance == allowed + 1:
        return "close"
    return "wrong"


def grade_meaning(submitted, accepted, taken=None):
    """Return 'correct', 'almost', 'close', or 'wrong'."""
    got = normalize_meaning(submitted)
    if not got:
        return "wrong"
    targets = [normalize_meaning(item) for item in accepted if item]
    targets = [item for item in targets if item]
    if got in targets:
        return "correct"
    best = "wrong"
    for target in targets:
        verdict = _meaning_near(got, target)
        if _RANK[verdict] > _RANK[best]:
            best = verdict
    if best in ("almost", "close") and taken and taken(got):
        return "wrong"
    return best


def grade_reading(submitted, accepted):
    got = normalize_reading(submitted)
    if not got:
        return "wrong"
    targets = [normalize_reading(item) for item in accepted if item]
    targets = [item for item in targets if item]
    if got in targets:
        return "correct"
    folded = fold_kana(got)
    for target in targets:
        if folded and fold_kana(target) == folded:
            return "close"
        if len(target) >= 3 and _damerau(got, target, cap=1) == 1:
            return "close"
    return "wrong"


def grade_answer(prompt_type, submitted, accepted, taken=None):
    if prompt_type == "reading":
        return grade_reading(submitted, accepted)
    return grade_meaning(submitted, accepted, taken=taken)


def close_hint(prompt_type):
    if prompt_type == "reading":
        return "Close. Check the kana."
    return "Close. Check the spelling."

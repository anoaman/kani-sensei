import { toHiragana, toKana } from "wanakana";

const SMALL_TO_BIG = {
  ぁ: "あ",
  ぃ: "い",
  ぅ: "う",
  ぇ: "え",
  ぉ: "お",
  ゃ: "や",
  ゅ: "ゆ",
  ょ: "よ",
  っ: "つ",
  ゎ: "わ",
};

export function normalizeReading(text) {
  const value = toHiragana(toKana((text || "").trim().toLowerCase()));
  return value.replace(/[\s・\-]/g, "");
}

export function foldKana(text) {
  const stripped = (text || "").normalize("NFD").replace(/\p{M}/gu, "");
  return stripped.replace(/[ぁぃぅぇぉゃゅょっゎ]/g, (char) => SMALL_TO_BIG[char] || char);
}

function damerau(left, right, cap) {
  if (cap < 0) return cap + 1;
  if (Math.abs(left.length - right.length) > cap) return cap + 1;
  if (left === right) return 0;
  let prevPrev = null;
  let prev = Array.from({ length: right.length + 1 }, (_, i) => i);
  for (let i = 1; i <= left.length; i += 1) {
    const curr = [i];
    for (let j = 1; j <= right.length; j += 1) {
      const cost = left[i - 1] === right[j - 1] ? 0 : 1;
      let value = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
      if (i > 1 && j > 1 && left[i - 1] === right[j - 2] && left[i - 2] === right[j - 1]) {
        value = Math.min(value, prevPrev[j - 2] + 1);
      }
      curr.push(value);
    }
    if (Math.min(...curr) > cap) return cap + 1;
    prevPrev = prev;
    prev = curr;
  }
  return prev[prev.length - 1];
}

export function readingVerdict(text, accepted) {
  const got = normalizeReading(text);
  if (!got) return "miss";
  const targets = (accepted || []).map((item) => normalizeReading(item)).filter(Boolean);
  if (targets.includes(got)) return "pass";
  const folded = foldKana(got);
  for (const target of targets) {
    if (folded && foldKana(target) === folded) return "close";
    if (target.length >= 3 && damerau(got, target, 1) === 1) return "close";
  }
  return "miss";
}

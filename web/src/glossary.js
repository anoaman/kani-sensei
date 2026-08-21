/** WaniKani + Kani Sensei glossary. Keys are lowercase lookup ids. */

export const GLOSSARY = {
  wanikani: {
    group: "WaniKani",
    term: "WaniKani",
    short: "The SRS site this companion sits on top of.",
    long: "WaniKani teaches radicals, then kanji, then vocabulary with spaced reviews. Kani Sensei never replaces it — it diagnoses the pile and lets you warm up before you touch the real queue.",
  },
  radical: {
    group: "WaniKani",
    term: "Radical",
    short: "Building-block pieces WaniKani uses to teach kanji.",
    long: "Radicals are named fragments (not always real Kangxi radicals). You learn them first so kanji mnemonics have parts to hang on.",
    aliases: ["radicals"],
  },
  kanji: {
    group: "WaniKani",
    term: "Kanji",
    short: "Chinese characters used in Japanese writing.",
    long: "WaniKani unlocks kanji after their radicals. Each kanji has a meaning and one or more readings. Vocabulary that uses a kanji usually unlocks after it.",
  },
  vocabulary: {
    group: "WaniKani",
    term: "Vocabulary",
    short: "Words — often compounds of kanji, sometimes kana-only.",
    long: "Vocab items have a meaning and a reading, and often audio plus example sentences. They are what you actually meet in the wild.",
    aliases: ["vocab"],
  },
  meaning: {
    group: "WaniKani",
    term: "Meaning",
    short: "The English gloss WaniKani accepts in reviews.",
    long: "Usually a short English word or phrase. Leading “to” / “the” is optional. Synonyms WaniKani marked as accepted also count.",
  },
  reading: {
    group: "WaniKani",
    term: "Reading",
    short: "How the item is pronounced in Japanese.",
    long: "Enter hiragana (or romaji here). Kanji can have several accepted readings; vocabulary usually has one primary word reading.",
  },
  onyomi: {
    group: "WaniKani",
    term: "On'yomi",
    short: "The Chinese-derived reading of a kanji, often in compounds.",
    long: "Typically used when the kanji is part of a multi-kanji word (中国, 水泳). WaniKani often shows these in katakana in its UI; we still accept hiragana.",
    aliases: ["on'yomi", "on yomi"],
  },
  kunyomi: {
    group: "WaniKani",
    term: "Kun'yomi",
    short: "The native Japanese reading, often with okurigana.",
    long: "Typically used when the kanji stands as a word on its own (水, 食べる). Kun readings can look “softer” than on'yomi.",
    aliases: ["kun'yomi", "kun yomi"],
  },
  nanori: {
    group: "WaniKani",
    term: "Nanori",
    short: "Name-only readings. Rare in reviews.",
    long: "Used in proper names. WaniKani sometimes lists them; they are usually not the answer it wants in a normal review.",
  },
  srs: {
    group: "WaniKani",
    term: "SRS",
    short: "Spaced Repetition System — reviews get further apart as you succeed.",
    long: "Each item sits on a stage. Correct answers move it forward (longer wait). Wrong answers drop it back. The whole WaniKani game is keeping this ladder honest.",
    aliases: ["srs stage", "srs stages"],
  },
  apprentice: {
    group: "WaniKani",
    term: "Apprentice",
    short: "SRS stages 1–4. Fresh or recently failed items. The daily grind.",
    long: "Intervals are hours to a couple of days. A fat apprentice pile means the queue will keep refilling. Kani Sensei’s circuit-breaker instinct: pause lessons until this shrinks.",
    aliases: ["apprentice 1", "apprentice 2", "apprentice 3", "apprentice 4"],
  },
  guru: {
    group: "WaniKani",
    term: "Guru",
    short: "SRS stages 5–6. You have passed the item; it comes back weekly-ish.",
    long: "Guru is the first “I kind of know this” band. Guru 1 is about a week; Guru 2 is longer. Still not safe to forget.",
    aliases: ["guru 1", "guru 2"],
  },
  master: {
    group: "WaniKani",
    term: "Master",
    short: "SRS stage 7. Month-scale interval.",
    long: "If it is sitting at Master and you still miss it, that is a real leak — worth a Sensei drill.",
  },
  enlightened: {
    group: "WaniKani",
    term: "Enlightened",
    short: "SRS stage 8. Four-month-ish wait, then burned if you pass.",
    long: "Last stop before Burned. Missing here hurts because the item has been out of sight for a long time.",
  },
  burned: {
    group: "WaniKani",
    term: "Burned",
    short: "SRS stage 9. WaniKani will never show it again.",
    long: "Congratulations, and a trap: burned items silently rot. Ghost Reviews exist so they do not disappear forever.",
    aliases: ["burn"],
  },
  lesson: {
    group: "WaniKani",
    term: "Lesson",
    short: "New items you unlock, before they enter reviews.",
    long: "Lessons add apprentice items. During a backlog, extra lessons make the fire worse. Runway can model that cost.",
    aliases: ["lessons"],
  },
  review: {
    group: "WaniKani",
    term: "Review",
    short: "A typed meaning or reading check on an unlocked item.",
    long: "The real WaniKani queue. Kani Sensei drills do not write back to it — they are practice, not progress on the site.",
    aliases: ["reviews"],
  },
  queue: {
    group: "WaniKani",
    term: "Queue",
    short: "Reviews waiting for you right now.",
    long: "If this number is huge after a break, start with Decay Map and a typed warm-up instead of opening WaniKani cold.",
  },
  backlog: {
    group: "Kani Sensei",
    term: "Backlog",
    short: "Reviews due now plus those landing in the next 24 hours.",
    long: "Runway uses this as the pile to burn down. A healthy floor is about 50/day — calm, not zero.",
  },
  due: {
    group: "WaniKani",
    term: "Due",
    short: "Available for review right now.",
    long: "The item’s available_at time has passed and it is not burned. “Due now” drills sample this slice.",
  },
  level: {
    group: "WaniKani",
    term: "Level",
    short: "WaniKani’s 1–60 progression. Items unlock by level.",
    long: "Decay Map ranks levels by how soft they look, so you can drill 14–16 instead of “everything I ever learned.”",
    aliases: ["levels"],
  },
  mnemonic: {
    group: "WaniKani",
    term: "Mnemonic",
    short: "WaniKani’s story for remembering a meaning or reading.",
    long: "Silly on purpose. Shown here behind a toggle after you answer, using the copy already in your synced catalog.",
  },
  leech: {
    group: "Kani Sensei",
    term: "Leech",
    short: "An item you keep getting wrong. It drinks review time.",
    long: "We flag items with a long incorrect history and weak accuracy. The Leech Clinic isolates them so they stop chewing the real queue.",
    aliases: ["leeches"],
  },
  accuracy: {
    group: "WaniKani",
    term: "Accuracy",
    short: "Lifetime percent correct for that item (meaning + reading).",
    long: "Not “how you did yesterday.” A 60% lifetime score on a Guru item is a smell. Decay Map leans on this heavily.",
  },
  decay: {
    group: "Kani Sensei",
    term: "Decay Map",
    short: "What went soft while you were away, ranked so you know where to start.",
    long: "Combines lifetime accuracy, current SRS stage, due-ness, and real stage drops between daily snapshots. High-risk levels are the ones to drill first.",
    aliases: ["decay-weighted", "decay map"],
  },
  runway: {
    group: "Kani Sensei",
    term: "Runway",
    short: "How long the pile takes to feel human at a daily pace.",
    long: "Projects days-to-healthy from backlog, apprentice mix, and a review target. “Stalled” means your pace cannot outrun the refill.",
  },
  ghost: {
    group: "Kani Sensei",
    term: "Ghost reviews",
    short: "Drills for burned items WaniKani will never show again.",
    long: "Burned is not “known forever.” Ghosts resample those items so they cannot rot in the dark.",
    aliases: ["ghosts", "ghost review"],
  },
  dojo: {
    group: "Kani Sensei",
    term: "Dojo",
    short: "A no-setup round of typed questions from today’s hot levels.",
    long: "Twelve decay-weighted items, meaning and reading mixed. The fastest way to start when the queue looks hostile.",
  },
  warmup: {
    group: "Kani Sensei",
    term: "Warm-up",
    short: "Multiple-choice drills. Softer than typing.",
    long: "Use this when recall feels sharp or you want a first pass. It does not train the same muscle as a real WaniKani review.",
    aliases: ["warm-up"],
  },
  reverse: {
    group: "Kani Sensei",
    term: "Reverse",
    short: "See the English, pick the glyph.",
    long: "Tests recognition instead of production. Useful when you can type “water” but freeze on 水 in the wild.",
  },
  blitz: {
    group: "Kani Sensei",
    term: "Blitz",
    short: "Sixty seconds, as many typed answers as you can.",
    long: "Speed pressure. Misses still go in the Sensei notebook. Not a replacement for a careful round.",
    aliases: ["60s blitz"],
  },
  notebook: {
    group: "Kani Sensei",
    term: "Sensei notebook",
    short: "Items this app has seen you miss, independent of WaniKani.",
    long: "Local miss/hit counts. Retrying them does not change your WK SRS — it just puts the leaky ones in front of you again.",
  },
  recall: {
    group: "Kani Sensei",
    term: "Typed recall",
    short: "You type the answer, like a real review.",
    long: "Meanings are graded the way WaniKani is (case, “to”, punctuation). Readings accept hiragana, katakana, or romaji.",
    aliases: ["type it"],
  },
  regression: {
    group: "Kani Sensei",
    term: "Regression",
    short: "The item’s SRS stage dropped since the last daily snapshot.",
    long: "A real “this got worse” signal, not just inference from accuracy. Needs at least two sync days to appear.",
    aliases: ["regressed", "dropped"],
  },
  combo: {
    group: "Kani Sensei",
    term: "Combo",
    short: "Streak of correct answers in the current drill.",
    long: "Resets on a miss. Purely for pace and dopamine. Does not affect WaniKani.",
  },
  inspect: {
    group: "Kani Sensei",
    term: "Inspect",
    short: "The teaching card after an answer: parts, lookalikes, sentence, audio.",
    long: "Pulled from your cached WaniKani catalog. Click Decay Map items or notebook misses to open the same card.",
  },
};

const ALIAS_TO_ID = (() => {
  const map = new Map();
  for (const [id, entry] of Object.entries(GLOSSARY)) {
    map.set(id.toLowerCase(), id);
    map.set(entry.term.toLowerCase(), id);
    for (const alias of entry.aliases || []) {
      map.set(alias.toLowerCase(), id);
    }
  }
  return map;
})();

export const GLOSSARY_LIST = Object.entries(GLOSSARY)
  .map(([id, entry]) => ({ id, ...entry }))
  .sort((a, b) => a.term.localeCompare(b.term));

export function lookupTerm(raw) {
  if (!raw) return null;
  const id = ALIAS_TO_ID.get(String(raw).trim().toLowerCase());
  if (!id) return null;
  return { id, ...GLOSSARY[id] };
}

export function srsTermId(name) {
  const value = String(name || "").toLowerCase();
  if (value.includes("apprentice")) return "apprentice";
  if (value.includes("guru")) return "guru";
  if (value.includes("master")) return "master";
  if (value.includes("enlightened")) return "enlightened";
  if (value.includes("burned")) return "burned";
  if (value.includes("locked")) return "srs";
  return "srs";
}

export function readingTypeId(type) {
  const value = String(type || "").toLowerCase().replace(/['’_\s]/g, "");
  if (value.includes("nanori")) return "nanori";
  if (value.includes("kun")) return "kunyomi";
  if (value.includes("on")) return "onyomi";
  return "reading";
}

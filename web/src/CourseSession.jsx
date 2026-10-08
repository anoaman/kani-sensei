import { useEffect, useRef, useState } from "react";
import { toKana } from "wanakana";
import { api } from "./api.js";
import InspectCard from "./InspectCard.jsx";
import { Glyph } from "./LevelPages.jsx";

const TYPE_LABEL = { radical: "Radical", kanji: "Kanji", vocabulary: "Vocabulary", kana_vocabulary: "Vocabulary" };
const RETRY_GAP = 3;
const RELEARN_GAP = 4;
// Relearn walks an item up to Guru in one sitting, a few passes at most.
const MAX_PASSES = 5;

export const MODE_INFO = {
  check: { title: "Check", verb: "Check", note: "One look per item. Clean answers go straight to Guru; misses go to Relearn." },
  relearn: { title: "Relearn", verb: "Relearn", note: "No waiting. Clean passes climb a stage; items come back until they're on Guru." },
  reviews: { title: "Reviews", verb: "Review", note: "Due on real time. This is where it sticks or slips." },
  ahead: { title: "Study ahead", verb: "Study ahead", note: "Early practice. Right answers don't move items up; misses still count." },
};

function promptsFor(entry) {
  return (entry.prompts || ["meaning"]).map((prompt_type) => ({ subject_id: entry.subject_id, prompt_type }));
}

function shuffle(list) {
  const out = [...list];
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function typeOf(item) {
  const type = item?.type || item?.object_type;
  return type === "kana_vocabulary" ? "vocabulary" : type;
}

// WaniKani mnemonics mark terms with <radical>, <kanji>, <vocabulary>, <reading>, <ja>.
function Mnemonic({ text }) {
  if (!text) return null;
  const parts = [];
  const re = /<(radical|kanji|vocabulary|reading|ja|meaning)>(.*?)<\/\1>/gs;
  let last = 0;
  let match;
  while ((match = re.exec(text))) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    parts.push(<mark key={match.index} className={`mn-${match[1]}`}>{match[2].replace(/<[^>]+>/g, "")}</mark>);
    last = re.lastIndex;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <p className="mnemonic">{parts.map((part) => (typeof part === "string" ? part.replace(/<[^>]+>/g, "") : part))}</p>;
}

function LessonCard({ card, index, total }) {
  const type = typeOf(card);
  const readings = card.readings || [];
  return (
    <div className="lesson-card">
      <div className={`prompt-band t-${type}`}>
        <span>{TYPE_LABEL[type]} · relearn {index + 1} of {total}</span>
      </div>
      <div className="lesson-glyph"><Glyph item={card} className="chars" /></div>
      <div className="lesson-facts">
        <div>
          <p className="kicker">Meaning</p>
          <p className="fact-main">{card.meaning}</p>
          {card.meanings?.length > 1 ? <p className="muted">Also: {card.meanings.filter((m) => m !== card.meaning).join(", ")}</p> : null}
        </div>
        {card.needs_reading && readings.length ? (
          <div>
            <p className="kicker">Reading</p>
            <p className="fact-main" lang="ja">{readings.map((r) => r.reading).join("、")}</p>
            <p className="muted">{[...new Set(readings.map((r) => r.type))].join(" / ")}</p>
          </div>
        ) : null}
      </div>
      {card.components?.length ? (
        <div className="lesson-parts">
          <p className="kicker">Made of</p>
          <div className="glyph-row">
            {card.components.map((part) => (
              <span key={part.subject_id} className={`glyph-chip t-${typeOf(part)}`}>
                <span className="glyph" lang="ja">{part.characters || "・"}</span>
                <span className="meta">{part.meaning}</span>
              </span>
            ))}
          </div>
        </div>
      ) : null}
      <div className="lesson-mnemonics">
        {card.mnemonic?.meaning ? <><p className="kicker">Meaning mnemonic</p><Mnemonic text={card.mnemonic.meaning} /></> : null}
        {card.needs_reading && card.mnemonic?.reading ? <><p className="kicker">Reading mnemonic</p><Mnemonic text={card.mnemonic.reading} /></> : null}
      </div>
      {card.sentence ? (
        <div className="lesson-sentence">
          <p lang="ja">{card.sentence.ja}</p>
          <p className="muted">{card.sentence.en}</p>
        </div>
      ) : null}
    </div>
  );
}

export default function CourseSession({ level, mode, go, onFocus }) {
  const [phase, setPhase] = useState("loading");
  const [items, setItems] = useState({});
  const [cards, setCards] = useState([]);
  const [cardIndex, setCardIndex] = useState(0);
  const [queue, setQueue] = useState([]);
  const [typed, setTyped] = useState("");
  const [hint, setHint] = useState("");
  const [shake, setShake] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [details, setDetails] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [stats, setStats] = useState({ answered: 0, correct: 0, done: [], passed: false });
  const [passes, setPasses] = useState({});
  const composing = useRef(false);
  const inputRef = useRef(null);

  const current = queue[0] || null;
  const item = current ? items[current.subject_id] : null;
  const type = typeOf(item);
  const isReading = current?.prompt_type === "reading";

  useEffect(() => {
    onFocus?.(phase === "quiz" || phase === "learn");
    return () => onFocus?.(false);
  }, [phase, onFocus]);

  async function load() {
    setPhase("loading");
    setError("");
    setStats({ answered: 0, correct: 0, done: [], passed: false });
    setFeedback(null);
    setPasses({});
    try {
      const data = await api.courseQueue(level, mode);
      const list = data.items || [];
      setItems(Object.fromEntries(list.map((entry) => [entry.subject_id, entry])));
      setQueue(shuffle(list.flatMap(promptsFor)));
      // Fresh relearns open with their teaching cards.
      const fresh = list.filter((entry) => entry.card).map((entry) => ({ ...entry.card, needs_reading: entry.needs_reading }));
      setCards(fresh);
      setCardIndex(0);
      setPhase(!list.length ? "empty" : fresh.length ? "learn" : "quiz");
    } catch (err) {
      setError(err.message || "Could not load");
      setPhase("empty");
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [level, mode]);

  useEffect(() => {
    if (phase === "quiz" && !feedback && inputRef.current) inputRef.current.focus();
  }, [phase, feedback, current]);

  function bump() {
    setShake(true);
    window.setTimeout(() => setShake(false), 420);
  }

  async function submit(gaveUp = false) {
    if (!current || feedback || busy) return;
    const raw = isReading ? toKana((typed || "").toLowerCase()) : typed;
    const text = (raw || "").trim();
    if (!gaveUp && !text) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.courseAnswer({
        subject_id: current.subject_id,
        prompt_type: current.prompt_type,
        ...(gaveUp ? { gave_up: true } : { text }),
      });
      if (result.retry) {
        setHint(result.hint || "Try the other half.");
        bump();
        inputRef.current?.select();
        return;
      }
      setHint("");
      // A missed check is the moment to see the card, so open it.
      setDetails(!result.correct && mode === "check");
      setFeedback(result);
      if (!result.correct) bump();
      setStats((prev) => {
        const done = result.item_done
          ? [...prev.done.filter((entry) => entry.subject_id !== result.subject_id), { ...items[current.subject_id], ...result }]
          : prev.done;
        return {
          answered: prev.answered + 1,
          correct: prev.correct + (result.correct ? 1 : 0),
          done,
          passed: prev.passed || result.level_passed,
        };
      });
    } catch (err) {
      setError(err.message || "Could not grade");
    } finally {
      setBusy(false);
    }
  }

  function next() {
    if (!feedback) return;
    const result = feedback;
    setFeedback(null);
    setTyped("");
    setDetails(false);
    let rest = queue.slice(1);
    if (!result.correct && mode !== "check") {
      // The half stays open until it's right: bring it back in a few.
      rest.splice(Math.min(rest.length, RETRY_GAP), 0, current);
    }
    if (result.item_done && mode === "relearn" && result.stage < 5) {
      const count = (passes[result.subject_id] || 0) + 1;
      setPasses({ ...passes, [result.subject_id]: count });
      if (count < MAX_PASSES) {
        const entry = items[result.subject_id];
        const again = promptsFor({ ...entry, prompts: entry.needs_reading ? ["meaning", "reading"] : ["meaning"] });
        const at = Math.min(rest.length, RELEARN_GAP);
        rest = [...rest.slice(0, at), ...again, ...rest.slice(at)];
      }
    }
    if (result.item_done) {
      setItems((prev) => ({ ...prev, [result.subject_id]: { ...prev[result.subject_id], stage: result.stage, stage_name: result.stage_name } }));
    }
    setQueue(rest);
    if (!rest.length) setPhase("done");
  }

  useEffect(() => {
    function onKey(event) {
      if (composing.current || event.repeat) return;
      if (phase === "learn") {
        if (event.key === "ArrowRight" || event.key === "Enter") {
          event.preventDefault();
          if (cardIndex < cards.length - 1) setCardIndex(cardIndex + 1);
          else setPhase("quiz");
        } else if (event.key === "ArrowLeft" && cardIndex > 0) {
          setCardIndex(cardIndex - 1);
        }
        return;
      }
      if (phase === "quiz" && feedback && event.key === "Enter") {
        event.preventDefault();
        next();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const info = MODE_INFO[mode] || MODE_INFO.check;
  const title = `Level ${level} · ${info.title}`;
  const remaining = new Set(queue.map((q) => q.subject_id)).size;

  return (
    <section className="panel focus-panel">
      <div className="section-head level-head">
        <div>
          <button className="quiet-link" onClick={() => go(`/level/${level}`)}>← Level {level}</button>
          <h2>{title}</h2>
        </div>
        {phase === "quiz" ? <p className="muted">{remaining} items left · {stats.correct}/{stats.answered} correct</p> : null}
      </div>
      {error ? <div className="error">{error}</div> : null}

      {phase === "loading" ? <p className="muted">Loading…</p> : null}

      {phase === "empty" ? (
        <div className="surface">
          <p>Nothing in {info.title.toLowerCase()} on this level right now.</p>
          <button className="primary-btn" onClick={() => go(`/level/${level}`)}>Back to level {level}</button>
        </div>
      ) : null}

      {phase === "learn" && cards[cardIndex] ? (
        <div className="quiz-stage surface">
          <LessonCard card={cards[cardIndex]} index={cardIndex} total={cards.length} />
          <div className="lesson-nav">
            <button className="ghost-btn" disabled={cardIndex === 0} onClick={() => setCardIndex(cardIndex - 1)}>← Back</button>
            <div className="lesson-dots">
              {cards.map((card, i) => (
                <button key={card.subject_id} className={i === cardIndex ? "active" : ""} onClick={() => setCardIndex(i)} lang="ja">
                  {card.characters || "・"}
                </button>
              ))}
            </div>
            {cardIndex < cards.length - 1
              ? <button className="primary-btn" onClick={() => setCardIndex(cardIndex + 1)}>Next →</button>
              : <button className="primary-btn" onClick={() => setPhase("quiz")}>Quiz me</button>}
          </div>
          <p className="note">These slipped. Read them, then prove it · ← → to move · Enter on the last card starts</p>
        </div>
      ) : null}

      {phase === "quiz" && current && item ? (
        <div className={`quiz-stage surface ${shake ? "shake" : ""}`}>
          <div className={`prompt-band t-${type}${isReading ? " reading" : ""}`}>
            <span>{TYPE_LABEL[type]} <b>{isReading ? "Reading" : "Meaning"}</b></span>
            {item.stage_name ? <span className="band-meta">{item.stage_name}</span> : null}
          </div>
          <div className="prompt"><Glyph item={item} className="chars" /></div>

          {!feedback ? (
            <form className="recall-form" onSubmit={(event) => { event.preventDefault(); submit(); }}>
              <input
                ref={inputRef}
                value={typed}
                lang={isReading ? "ja" : "en"}
                className={isReading ? "answer-reading" : "answer-meaning"}
                placeholder={isReading ? "答え" : "Your response"}
                autoComplete="off"
                autoCapitalize="off"
                autoCorrect="off"
                spellCheck={false}
                disabled={busy}
                onChange={(event) => {
                  const value = event.target.value;
                  setTyped(isReading && !composing.current ? toKana(value.toLowerCase(), { IMEMode: true }) : value);
                  if (hint) setHint("");
                }}
                onCompositionStart={() => { composing.current = true; }}
                onCompositionEnd={() => { composing.current = false; }}
              />
              <button className="primary-btn" type="submit" disabled={busy || !typed.trim()}>Check</button>
            </form>
          ) : null}
          {hint && !feedback ? <p className="drill-hint">{hint}</p> : null}

          {!feedback ? (
            <button type="button" className="text-btn" onClick={() => submit(true)} disabled={busy}>I don’t know</button>
          ) : (
            <div className={`reveal ${feedback.correct ? "ok" : "nope"}`}>
              <strong>
                {feedback.correct
                  ? feedback.almost ? "Close enough. Watch the spelling." : "Correct."
                  : feedback.gave_up ? "Here it is." : "Not quite."}
              </strong>{" "}
              {isReading
                ? (feedback.inspect?.readings || []).map((r) => r.reading).join(" / ")
                : (feedback.inspect?.meanings || []).join(", ")}
              {feedback.submitted && (!feedback.correct || feedback.almost) ? <div className="meta">You said {feedback.submitted}</div> : null}
              {!feedback.correct ? (
                <div className="meta">
                  {mode === "check" ? "Into Relearn it goes. Here's the card." : "It comes back in a few. This miss counts."}
                </div>
              ) : null}
              {feedback.item_done && feedback.stage_name ? (
                <div className={`stage-change ${feedback.stage < feedback.previous_stage ? "down" : feedback.stage === feedback.previous_stage ? "" : "up"}`}>
                  {feedback.stage === feedback.previous_stage
                    ? `Held at ${feedback.stage_name}`
                    : `${feedback.stage < feedback.previous_stage ? "↓" : "↑"} ${feedback.stage_name}`}
                  {feedback.stage >= 5 && feedback.next_review_at ? ` · next review ${new Date(feedback.next_review_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}` : ""}
                </div>
              ) : null}
              {feedback.level_passed ? <div className="unlock-note">Level {level} passed.</div> : null}
              {details && feedback.inspect ? <InspectCard card={feedback.inspect} /> : null}
              <div className="reveal-actions">
                <button className="primary-btn" onClick={next}>Continue <kbd>Enter</kbd></button>
                {feedback.inspect ? <button className="ghost-btn" onClick={() => setDetails(!details)}>{details ? "Hide details" : "Item details"}</button> : null}
              </div>
            </div>
          )}
        </div>
      ) : null}

      {phase === "done" ? (
        <div className="quiz-stage surface">
          <p className="kicker">{info.title} done</p>
          <h3>
            {stats.done.length} items · {stats.answered ? Math.round((stats.correct / stats.answered) * 100) : 0}% of answers right.
          </h3>
          <div className="glyph-row">
            {stats.done.map((done) => (
              <span key={done.subject_id} className={`glyph-chip ${done.stage < done.previous_stage || (mode === "check" && done.stage < 5) ? "down" : "up"}`}>
                <span className="glyph" lang="ja">{done.characters || "・"}</span>
                <span className="meta">{done.stage_name}</span>
              </span>
            ))}
          </div>
          {stats.passed ? <p className="unlock-note">Level {level} passed.</p> : null}
          <div className="reveal-actions">
            <button className="primary-btn" onClick={() => go(`/level/${level}/continue`)}>Keep going</button>
            <button className="ghost-btn" onClick={() => go(`/level/${level}`)}>Back to level {level}</button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

import { useEffect, useRef, useState } from "react";
import { toKana } from "wanakana";
import { api } from "./api.js";
import InspectCard from "./InspectCard.jsx";
import { Glyph } from "./LevelPages.jsx";

const TYPE_LABEL = { radical: "Radical", kanji: "Kanji", vocabulary: "Vocabulary", kana_vocabulary: "Vocabulary" };
const RETRY_GAP = 3;

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
        <span>{TYPE_LABEL[type]} · lesson {index + 1} of {total}</span>
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
  const [stats, setStats] = useState({ answered: 0, correct: 0, done: [], unlocked: [], passed: false });
  const [moreLessons, setMoreLessons] = useState(0);
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
    setStats({ answered: 0, correct: 0, done: [], unlocked: [], passed: false });
    setFeedback(null);
    try {
      if (mode === "lessons") {
        const data = await api.courseLessons(level);
        const lessons = data.lessons || [];
        setCards(lessons);
        setCardIndex(0);
        setItems(Object.fromEntries(lessons.map((card) => [card.subject_id, card])));
        setQueue(shuffle(lessons.flatMap((card) => [
          { subject_id: card.subject_id, prompt_type: "meaning" },
          ...(card.needs_reading ? [{ subject_id: card.subject_id, prompt_type: "reading" }] : []),
        ])));
        setPhase(lessons.length ? "learn" : "empty");
      } else {
        const data = await api.courseReviews(level);
        const reviews = data.reviews || [];
        setItems(Object.fromEntries(reviews.map((review) => [review.subject_id, review])));
        setQueue(shuffle(reviews.flatMap((review) => review.prompts.map((prompt_type) => ({ subject_id: review.subject_id, prompt_type })))));
        setPhase(reviews.length ? "quiz" : "empty");
      }
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
      setDetails(false);
      setFeedback(result);
      if (!result.correct) bump();
      setStats((prev) => ({
        answered: prev.answered + 1,
        correct: prev.correct + (result.correct ? 1 : 0),
        done: result.item_done ? [...prev.done, { ...items[current.subject_id], ...result }] : prev.done,
        unlocked: [...prev.unlocked, ...(result.unlocked || [])],
        passed: prev.passed || result.level_passed,
      }));
    } catch (err) {
      setError(err.message || "Could not grade");
    } finally {
      setBusy(false);
    }
  }

  async function next() {
    if (!feedback) return;
    const missed = !feedback.correct;
    setFeedback(null);
    setTyped("");
    setDetails(false);
    const rest = queue.slice(1);
    // A miss comes back a few questions later until it's right.
    if (missed) rest.splice(Math.min(rest.length, RETRY_GAP), 0, current);
    setQueue(rest);
    if (!rest.length) {
      setPhase("done");
      if (mode === "lessons") {
        try {
          const more = await api.courseLessons(level);
          setMoreLessons(more.lessons?.length || 0);
        } catch {
          setMoreLessons(0);
        }
      }
    }
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

  const title = mode === "lessons" ? `Level ${level} lessons` : `Level ${level} reviews`;
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
          <p>{mode === "lessons" ? "No lessons waiting on this level." : "No reviews due right now."}</p>
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
          <p className="note">← → to move · Enter on the last card starts the quiz</p>
        </div>
      ) : null}

      {phase === "quiz" && current && item ? (
        <div className={`quiz-stage surface ${shake ? "shake" : ""}`}>
          <div className={`prompt-band t-${type}${isReading ? " reading" : ""}`}>
            <span>{TYPE_LABEL[type]} <b>{isReading ? "Reading" : "Meaning"}</b></span>
            {mode === "reviews" && item.stage_name ? <span className="band-meta">{item.stage_name}</span> : null}
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
                <div className="meta">{mode === "lessons" ? "It comes back in a few. Lessons don't cost you anything." : "It comes back in a few. This miss counts against the item."}</div>
              ) : null}
              {feedback.item_done && feedback.stage_name ? (
                <div className={`stage-change ${feedback.stage < (feedback.previous_stage ?? 0) ? "down" : "up"}`}>
                  {mode === "lessons" ? "Learned →" : `${feedback.stage < feedback.previous_stage ? "↓" : "↑"}`} {feedback.stage_name}
                </div>
              ) : null}
              {feedback.unlocked?.length ? (
                <div className="unlock-note">
                  Unlocked: <span lang="ja">{feedback.unlocked.map((u) => u.characters || u.meaning).join(" ")}</span>
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
          <p className="kicker">{mode === "lessons" ? "Lessons done" : "Reviews done"}</p>
          <h3>
            {mode === "lessons"
              ? `${stats.done.length} new items are on Apprentice 1.`
              : `${stats.done.length} items reviewed · ${stats.answered ? Math.round((stats.correct / stats.answered) * 100) : 0}% first answers right.`}
          </h3>
          {mode === "reviews" ? (
            <div className="glyph-row">
              {stats.done.map((done) => (
                <span key={done.subject_id} className={`glyph-chip ${done.stage < done.previous_stage ? "down" : "up"}`}>
                  <span className="glyph" lang="ja">{done.characters || "・"}</span>
                  <span className="meta">{done.stage_name}</span>
                </span>
              ))}
            </div>
          ) : null}
          {stats.unlocked.length ? <p className="unlock-note">Unlocked {stats.unlocked.length}: <span lang="ja">{stats.unlocked.map((u) => u.characters || u.meaning).join(" ")}</span></p> : null}
          {stats.passed ? <p className="unlock-note">Level {level} passed.</p> : null}
          <div className="reveal-actions">
            {mode === "lessons" && moreLessons ? <button className="primary-btn" onClick={load}>Next {moreLessons} lessons</button> : null}
            <button className={mode === "lessons" && moreLessons ? "ghost-btn" : "primary-btn"} onClick={() => go(`/level/${level}`)}>Back to level {level}</button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

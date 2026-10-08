import { useEffect, useMemo, useRef, useState } from "react";
import { toKana } from "wanakana";
import { api } from "./api.js";

const TYPE_NAME = { r: "Radical", k: "Kanji", v: "Vocabulary" };
const STATE_ORDER = ["fresh", "unchecked", "relearn", "guru", "master", "burned"];
const STATE_LABEL = {
  fresh: "Not started",
  unchecked: "To check",
  relearn: "Relearning",
  guru: "Guru",
  master: "Master+",
  burned: "Burned",
};

function stateOf(stage) {
  if (stage == null) return "fresh";
  if (stage <= 0) return "unchecked";
  if (stage <= 4) return "relearn";
  if (stage <= 6) return "guru";
  if (stage <= 8) return "master";
  return "burned";
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 5) return "Up late";
  if (hour < 11) return "Morning";
  if (hour < 15) return "Afternoon";
  if (hour < 19) return "Evening";
  return "Night shift";
}

function pickNext(levels) {
  const started = levels.filter((level) => level.started);
  for (const mode of ["reviews", "relearn", "check"]) {
    const hit = started.find((level) => level[mode] > 0);
    if (hit) return { level: hit.level, mode, count: hit[mode] };
  }
  const fresh = levels.find((level) => !level.started);
  return fresh ? { level: fresh.level, mode: null, count: fresh.total } : null;
}

const MODE_COPY = {
  reviews: (n) => `${n} reviews are due`,
  relearn: (n) => `${n} items to relearn`,
  check: (n) => `${n} items left to check`,
};

function WarmUp({ levels }) {
  const started = levels.filter((level) => level.started).map((level) => level.level);
  const min = started.length ? Math.min(...started) : 1;
  const max = started.length ? Math.max(...started) : 3;
  const [session, setSession] = useState(null);
  const [index, setIndex] = useState(0);
  const [typed, setTyped] = useState("");
  const [feedback, setFeedback] = useState(null);
  const [hint, setHint] = useState("");
  const [score, setScore] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const composing = useRef(false);
  const inputRef = useRef(null);
  // Don't grab focus (and pop a phone keyboard) until the warm-up is in use.
  const engaged = useRef(false);
  const question = session?.questions?.[index];
  const isReading = question?.prompt_type === "reading";
  const finished = session && index >= session.questions.length;

  async function begin() {
    setBusy(true);
    setError("");
    try {
      const drill = await api.startDrill({
        min_level: min, max_level: max, count: 5, kind: "recall", pool: "decay",
        modes: ["meaning", "reading"], object_types: ["kanji", "vocabulary"],
      });
      setSession(drill);
      setIndex(0);
      setScore(0);
      setFeedback(null);
      setTyped("");
    } catch (err) {
      setError(err.message || "Could not start");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { begin(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [min, max]);
  useEffect(() => {
    if (engaged.current && question && !feedback) inputRef.current?.focus({ preventScroll: true });
  }, [question, feedback]);

  async function submit(event) {
    event?.preventDefault();
    if (!question || feedback || busy) return;
    const text = (isReading ? toKana(typed.toLowerCase()) : typed).trim();
    if (!text) return;
    engaged.current = true;
    setBusy(true);
    try {
      const result = await api.answerDrill({ session_id: session.session_id, question_id: question.id, text });
      if (result.retry) {
        setHint(result.hint);
        return;
      }
      setHint("");
      setFeedback(result);
      if (result.correct) setScore((value) => value + 1);
      if (result.requeued) {
        setSession((prev) => ({ ...prev, questions: [...prev.questions, { ...result.requeued, prompt_text: question.prompt_text }] }));
      }
    } catch (err) {
      setError(err.message || "Could not grade");
    } finally {
      setBusy(false);
    }
  }

  function next() {
    setFeedback(null);
    setTyped("");
    setIndex((value) => value + 1);
  }

  useEffect(() => {
    if (!feedback) return undefined;
    const onKey = (event) => {
      if (event.key === "Enter" && !event.repeat) {
        event.preventDefault();
        next();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div className="warmup">
      <div className="warmup-head">
        <p className="kicker">One-breath warm-up</p>
        <span>{started.length ? `Your levels ${min === max ? min : `${min}–${max}`}` : "Levels 1–3"} · 5 items</span>
      </div>
      {error ? <p className="drill-hint">{error}</p> : null}
      {!session ? <div className="warmup-glyph dim" lang="ja">…</div> : finished ? (
        <div className="warmup-done">
          <div className="warmup-glyph" lang="ja">{score >= 4 ? "良" : score >= 2 ? "可" : "再"}</div>
          <p>{score} of {session.questions.length} right. {score >= 4 ? "Still in there." : "Some of it is waiting for you."}</p>
          <button className="ghost-btn" onClick={begin} disabled={busy}>Another five</button>
        </div>
      ) : question ? (
        <>
          <div className={`warmup-band ${isReading ? "reading" : ""}`}>
            {question.object_type === "kanji" ? "Kanji" : "Vocabulary"} <b>{isReading ? "reading" : "meaning"}</b>
            <span>{index + 1}/{session.questions.length}</span>
          </div>
          <div className={`warmup-glyph ${feedback ? (feedback.correct ? "ok" : "nope") : ""}`} lang="ja" key={question.id}>
            {question.characters}
          </div>
          {!feedback ? (
            <form onSubmit={submit} className="warmup-form">
              <input
                ref={inputRef}
                value={typed}
                lang={isReading ? "ja" : "en"}
                className={isReading ? "answer-reading" : "answer-meaning"}
                placeholder={isReading ? "答え" : "Meaning"}
                autoComplete="off" autoCapitalize="off" autoCorrect="off" spellCheck={false}
                onChange={(event) => {
                  const value = event.target.value;
                  setTyped(isReading && !composing.current ? toKana(value.toLowerCase(), { IMEMode: true }) : value);
                  if (hint) setHint("");
                }}
                onCompositionStart={() => { composing.current = true; }}
                onCompositionEnd={() => { composing.current = false; }}
              />
            </form>
          ) : (
            <div className="warmup-answer">
              <strong>{feedback.correct ? (feedback.almost ? "Close enough." : "Yes.") : "It was"}</strong>{" "}
              {isReading
                ? (feedback.reveal?.readings || []).join(" / ")
                : feedback.reveal?.meaning || feedback.correct_answer}
              <button className="text-btn" onClick={next}>Next <kbd>Enter</kbd></button>
            </div>
          )}
          {hint ? <p className="drill-hint">{hint}</p> : null}
        </>
      ) : null}
    </div>
  );
}

function Sky({ sky, levels, go }) {
  const [filter, setFilter] = useState("all");
  const [hover, setHover] = useState(null);
  const wrapRef = useRef(null);
  const byLevel = useMemo(() => new Map(levels.map((level) => [level.level, level])), [levels]);
  const totals = useMemo(() => {
    const out = Object.fromEntries(STATE_ORDER.map((state) => [state, 0]));
    for (const level of sky) for (const item of level.items) out[stateOf(item[4])] += 1;
    return out;
  }, [sky]);

  function onOver(event) {
    const dot = event.target.closest("[data-i]");
    if (!dot || !wrapRef.current) return;
    const [levelIndex, itemIndex] = dot.dataset.i.split(":").map(Number);
    const item = sky[levelIndex].items[itemIndex];
    const box = dot.getBoundingClientRect();
    const host = wrapRef.current.getBoundingClientRect();
    setHover({
      item, level: sky[levelIndex].level,
      x: box.left - host.left + box.width / 2,
      y: box.top - host.top,
    });
  }

  return (
    <section className="sky-section">
      <div className="sky-head">
        <div>
          <p className="kicker">Memory sky</p>
          <h2>Every item you ever passed. Light them back up.</h2>
        </div>
        <div className="sky-filter">
          {[["all", "All"], ["r", "Radicals"], ["k", "Kanji"], ["v", "Vocab"]].map(([id, label]) => (
            <button key={id} className={filter === id ? "active" : ""} onClick={() => setFilter(id)}>{label}</button>
          ))}
        </div>
      </div>
      <div className={`sky filter-${filter}`} ref={wrapRef} onMouseOver={onOver} onMouseLeave={() => setHover(null)} onClick={onOver}>
        {sky.map((level, levelIndex) => {
          const info = byLevel.get(level.level);
          return (
            <div key={level.level} className={`sky-col${info?.started ? " started" : ""}${info?.passed ? " passed" : ""}`} style={{ "--d": `${levelIndex * 35}ms` }}>
              <button className="sky-label" onClick={(event) => { event.stopPropagation(); go(`/level/${level.level}`); }}>
                {level.level}
              </button>
              <div className="sky-dots">
                {level.items.map((item, itemIndex) => (
                  <i key={item[0]} data-i={`${levelIndex}:${itemIndex}`} className={`dot s-${stateOf(item[4])} y-${item[1]}`} />
                ))}
              </div>
            </div>
          );
        })}
        {hover ? (
          <div className="sky-tip" style={{ left: hover.x, top: hover.y }}>
            <span className={`tip-glyph y-${hover.item[1]}`} lang="ja">{hover.item[2] || "・"}</span>
            <span>
              <b>{hover.item[3]}</b>
              <small>{TYPE_NAME[hover.item[1]]} · level {hover.level} · {STATE_LABEL[stateOf(hover.item[4])]}</small>
            </span>
          </div>
        ) : null}
      </div>
      <div className="sky-legend">
        {STATE_ORDER.map((state) => (
          <span key={state}><i className={`dot s-${state}`} />{STATE_LABEL[state]} <b>{totals[state]}</b></span>
        ))}
      </div>
    </section>
  );
}

export default function Home({ go }) {
  const [levels, setLevels] = useState(null);
  const [sky, setSky] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.levels(), api.sky()])
      .then(([levelData, skyData]) => {
        setLevels(levelData.levels);
        setSky(skyData.levels);
      })
      .catch((err) => setError(err.message || "Could not load"));
  }, []);

  if (error) return <div className="error global-error">{error}</div>;
  if (!levels || !sky) return <div className="home-loading" lang="ja">おかえり</div>;

  const total = levels.reduce((sum, level) => sum + level.total, 0);
  const known = levels.reduce((sum, level) => sum + level.known, 0);
  const next = pickNext(levels);
  const startedCount = levels.filter((level) => level.started).length;

  return (
    <main className="home">
      <section className="home-hero">
        <div className="home-welcome">
          <p className="kicker">{greeting()}, Kibz</p>
          <h1><span lang="ja">おかえり</span>, welcome back.</h1>
          <p className="home-sub">
            {known
              ? <>You've brought back <b>{known.toLocaleString()}</b> of {total.toLocaleString()} items across {startedCount} {startedCount === 1 ? "level" : "levels"}.</>
              : <>{total.toLocaleString()} items from levels 1–{levels.length} are still in there somewhere. Let's find out how many.</>}
          </p>
          {next ? (
            <div className="home-next">
              <button
                className="go-btn"
                onClick={() => go(next.mode ? `/level/${next.level}/${next.mode}` : `/level/${next.level}`)}
              >
                {next.mode ? `Continue level ${next.level}` : `Start level ${next.level}`} 
              </button>
              <span>{next.mode ? MODE_COPY[next.mode](next.count) : `Quick check of ${next.count} items first`}</span>
            </div>
          ) : null}
          <div className="home-links">
            <button className="quiet-link" onClick={() => go("/levels")}>Browse levels</button>
          </div>
        </div>
        <WarmUp levels={levels} />
      </section>
      <Sky sky={sky} levels={levels} go={go} />
    </main>
  );
}

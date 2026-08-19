import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import InspectCard from "./InspectCard.jsx";

const FORMATS = [
  { id: "recall", label: "Type it", hint: "Same muscle as a real review" },
  { id: "mc", label: "Multiple choice", hint: "Warm-up if recall feels sharp" },
  { id: "reverse", label: "Reverse", hint: "See the meaning, pick the glyph" },
  { id: "speed", label: "60s blitz", hint: "As many as you can in a minute" },
];

const POOLS = [
  { id: "decay", label: "Decay-weighted" },
  { id: "due", label: "Due now" },
  { id: "leeches", label: "Leeches" },
  { id: "burned", label: "Ghosts" },
  { id: "misses", label: "My misses" },
];

function readQuery() {
  const query = new URLSearchParams(window.location.search);
  const min = Number(query.get("min"));
  const max = Number(query.get("max"));
  const count = Number(query.get("count"));
  const types = (query.get("types") || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return {
    min: Number.isFinite(min) && min >= 1 ? min : null,
    max: Number.isFinite(max) && max >= 1 ? max : null,
    count: Number.isFinite(count) && count >= 1 ? count : null,
    pool: query.get("pool") || null,
    kind: query.get("kind") || null,
    go: query.get("go") === "1",
    types: types.length ? types : null,
  };
}

function ChipRow({ label, options, value, onChange, disabled }) {
  return (
    <div className="chip-row">
      <span className="chip-label">{label}</span>
      <div className="chips" role="radiogroup" aria-label={label}>
        {options.map((option) => (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={value === option.id}
            className={value === option.id ? "chip active" : "chip"}
            disabled={disabled}
            title={option.hint}
            onClick={() => onChange(option.id)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Recap({ score, verdict, comboBest, misses, onAgain, onRetryMisses, onHome, onInspect }) {
  return (
    <div className="recap">
      <div className="recap-score">
        <span className="eyebrow">Session</span>
        <div className="chars">{score.correct}/{score.total}</div>
        <p className="verdict">{verdict || "Round complete."}</p>
        {comboBest ? <p className="note">Best combo {comboBest}</p> : null}
      </div>
      {misses.length ? (
        <div className="miss-list">
          <strong>What still has teeth</strong>
          {misses.map((miss, index) => (
            <button
              type="button"
              className="item item-btn"
              key={`${miss.characters}-${index}`}
              onClick={() => miss.subject_id && onInspect?.(miss.subject_id)}
            >
              <div className="glyph">{miss.characters}</div>
              <div>
                <div>{miss.correct_answer}</div>
                <div className="meta">
                  {miss.prompt_type}
                  {miss.submitted ? ` · you said ${miss.submitted}` : " · passed"}
                </div>
              </div>
            </button>
          ))}
        </div>
      ) : (
        <p className="note">No misses. Take that straight into WaniKani.</p>
      )}
      <div className="hero-actions">
        <button className="primary-btn" onClick={onAgain}>Again</button>
        {misses.length ? (
          <button className="ghost-btn" onClick={onRetryMisses}>Retry misses</button>
        ) : null}
        {onHome ? (
          <button className="ghost-btn" onClick={onHome}>Home</button>
        ) : null}
      </div>
    </div>
  );
}

export default function TestView({
  data,
  title,
  blurb,
  defaultObjectTypes = ["kanji"],
  defaultKind = "recall",
  defaultPool = "decay",
  defaultCount = 10,
  autoStart = false,
  finishNote,
  onHome,
  onFocus,
}) {
  const query = readQuery();
  const suggested = data?.decay?.summary?.suggested_levels || [];
  const fallbackMin = suggested.length ? Math.min(...suggested) : 14;
  const fallbackMax = suggested.length ? Math.max(...suggested) : 18;
  const defaultMin = query.min ?? fallbackMin;
  const defaultMax = query.max ?? fallbackMax;

  const [kind, setKind] = useState(query.kind || defaultKind);
  const [pool, setPool] = useState(query.pool || defaultPool);
  const [minLevel, setMinLevel] = useState(defaultMin);
  const [maxLevel, setMaxLevel] = useState(defaultMax);
  const [count, setCount] = useState(query.count || defaultCount);
  const [mode, setMode] = useState("both");
  const [autoAdvance, setAutoAdvance] = useState(() => {
    try {
      return window.localStorage.getItem("kani-auto-advance") !== "0";
    } catch {
      return true;
    }
  });
  const [session, setSession] = useState(null);
  const [index, setIndex] = useState(0);
  const [feedback, setFeedback] = useState(null);
  const [inspect, setInspect] = useState(null);
  const [misses, setMisses] = useState([]);
  const [typed, setTyped] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [combo, setCombo] = useState(0);
  const [secondsLeft, setSecondsLeft] = useState(null);
  const [shake, setShake] = useState(false);
  const [wrapUp, setWrapUp] = useState(false);
  const [scoreboard, setScoreboard] = useState({ correct: 0, total: 0 });
  const composing = useRef(false);
  const inputRef = useRef(null);
  const autoStarted = useRef(false);
  const nextRef = useRef(() => {});

  const objectTypes = query.types || defaultObjectTypes;
  const question = session?.questions?.[index] || null;
  const finished = Boolean(feedback?.score?.finished) || (secondsLeft === 0 && session);
  const isTyped = (session?.kind || kind) === "recall" || (session?.kind || kind) === "speed";
  const progressTotal = session?.question_count || count;
  const progressNow = feedback?.score?.total ?? (session ? index : 0);
  const timeUp = session?.kind === "speed" && secondsLeft === 0;
  const showRecap = Boolean(session && (wrapUp || timeUp));
  const inSession = Boolean(session && !showRecap);

  useEffect(() => {
    onFocus?.(inSession);
    return () => onFocus?.(false);
  }, [inSession, onFocus]);

  useEffect(() => {
    if (!session) {
      setMinLevel(defaultMin);
      setMaxLevel(defaultMax);
    }
  }, [defaultMin, defaultMax, session]);

  async function start(overrides = {}) {
    setBusy(true);
    setError("");
    setFeedback(null);
    setInspect(null);
    setMisses([]);
    setCombo(0);
    setTyped("");
    setWrapUp(false);
    setScoreboard({ correct: 0, total: 0 });
    setSession(null);
    try {
      const nextKind = overrides.kind || kind;
      const nextPool = overrides.pool || pool;
      const modes =
        mode === "both" ? ["meaning", "reading"] : mode === "meaning" ? ["meaning"] : ["reading"];
      const drill = await api.startDrill({
        min_level: Number(overrides.min_level ?? minLevel),
        max_level: Number(overrides.max_level ?? maxLevel),
        count: Number(overrides.count ?? (nextKind === "speed" ? 24 : count)),
        modes,
        kind: nextKind,
        pool: nextPool,
        object_types: objectTypes,
      });
      setSession(drill);
      setIndex(0);
      setSecondsLeft(drill.seconds || null);
    } catch (err) {
      setError(err.message || "Could not start drill");
      setSession(null);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if ((autoStart || query.go) && !autoStarted.current && data) {
      autoStarted.current = true;
      start();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStart, data]);

  useEffect(() => {
    if (!session || session.kind !== "speed" || finished) return undefined;
    if (secondsLeft == null || secondsLeft <= 0) return undefined;
    const timer = window.setTimeout(() => setSecondsLeft((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [session, secondsLeft, finished]);

  useEffect(() => {
    if (isTyped && session && !feedback && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isTyped, session, feedback, index]);

  function applyResult(result, current) {
    setFeedback(result);
    setInspect(result.inspect || null);
    setCombo(result.combo || 0);
    setScoreboard({
      correct: result.score?.correct || 0,
      total: result.score?.total || 0,
    });
    if (!result.correct) {
      setShake(true);
      window.setTimeout(() => setShake(false), 420);
      setMisses((list) => [
        ...list,
        {
          characters: result.reveal?.characters || current.characters,
          prompt_type: current.prompt_type,
          submitted: result.submitted,
          correct_answer: result.correct_answer,
          subject_id: result.reveal?.subject_id,
        },
      ]);
    }
  }

  async function submitChoice(choiceIndex) {
    if (!session || !question || feedback || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.answerDrill({
        session_id: session.session_id,
        question_id: question.id,
        choice_index: choiceIndex,
      });
      applyResult(result, question);
    } catch (err) {
      setError(err.message || "Could not grade answer");
    } finally {
      setBusy(false);
    }
  }

  async function submitText(value = typed) {
    if (!session || !question || feedback || busy) return;
    const trimmed = (value || "").trim();
    if (!trimmed) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.answerDrill({
        session_id: session.session_id,
        question_id: question.id,
        text: trimmed,
      });
      applyResult(result, question);
    } catch (err) {
      setError(err.message || "Could not grade answer");
    } finally {
      setBusy(false);
    }
  }

  async function giveUp() {
    if (!session || !question || feedback || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.answerDrill({
        session_id: session.session_id,
        question_id: question.id,
        gave_up: true,
        text: "",
      });
      applyResult(result, question);
    } catch (err) {
      setError(err.message || "Could not skip");
    } finally {
      setBusy(false);
    }
  }

  function next() {
    if (!session) return;
    if (feedback?.score?.finished || timeUp) {
      setWrapUp(true);
      return;
    }
    setIndex((value) => value + 1);
    setFeedback(null);
    setInspect(null);
    setTyped("");
  }

  nextRef.current = next;

  useEffect(() => {
    if (!autoAdvance || !feedback?.correct || feedback?.score?.finished) return undefined;
    const timer = window.setTimeout(() => nextRef.current(), 850);
    return () => window.clearTimeout(timer);
  }, [autoAdvance, feedback]);

  async function openRelated(subjectId) {
    try {
      setInspect(await api.inspect(subjectId));
    } catch {
      /* keep current card */
    }
  }

  useEffect(() => {
    function onKey(event) {
      if (composing.current) return;
      const tag = (event.target.tagName || "").toLowerCase();
      if (showRecap || !session) return;
      if (feedback) {
        if (event.key === "Enter" || event.key === " " || event.key === "n") {
          event.preventDefault();
          next();
        }
        return;
      }
      if (!question) return;
      if (event.key === "?" || event.key === "-") {
        if (tag === "input" && event.target.value) return;
        event.preventDefault();
        giveUp();
        return;
      }
      if (!isTyped && /^[1-4]$/.test(event.key)) {
        event.preventDefault();
        submitChoice(Number(event.key) - 1);
        return;
      }
      if (tag === "input" || tag === "textarea") return;
      if (event.key === "Enter" && isTyped) {
        event.preventDefault();
        submitText();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function onKeyDown(event) {
    if (composing.current) return;
    if (event.key !== "Enter") return;
    event.preventDefault();
    if (feedback) next();
    else submitText();
  }

  function exit() {
    setSession(null);
    setFeedback(null);
    setInspect(null);
    setWrapUp(false);
    autoStarted.current = true;
  }

  function persistAdvance(value) {
    setAutoAdvance(value);
    try {
      window.localStorage.setItem("kani-auto-advance", value ? "1" : "0");
    } catch {
      /* ignore */
    }
  }

  return (
    <section className={`panel ${inSession ? "focus-panel" : ""}`}>
      <div className="section-head">
        <div>
          <h2>{title}</h2>
          <p>{blurb}</p>
        </div>
      </div>

      {!session ? (
        <div className="surface">
          <ChipRow label="Format" options={FORMATS} value={kind} onChange={setKind} />
          <ChipRow label="Pool" options={POOLS} value={pool} onChange={setPool} />
          <div className="controls">
            <div className="field">
              <label>From</label>
              <input
                type="number"
                min="1"
                max="60"
                value={minLevel}
                onChange={(e) => setMinLevel(e.target.value)}
              />
            </div>
            <div className="field">
              <label>To</label>
              <input
                type="number"
                min="1"
                max="60"
                value={maxLevel}
                onChange={(e) => setMaxLevel(e.target.value)}
              />
            </div>
            <div className="field">
              <label>Questions</label>
              <input
                type="number"
                min="3"
                max="40"
                value={count}
                onChange={(e) => setCount(e.target.value)}
                disabled={kind === "speed"}
              />
            </div>
            <div className="field">
              <label>Focus</label>
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="both">Meaning + reading</option>
                <option value="meaning">Meaning only</option>
                <option value="reading">Reading only</option>
              </select>
            </div>
            <button className="primary-btn" onClick={() => start()} disabled={busy}>
              {busy ? "Building…" : kind === "speed" ? "Start blitz" : "Begin"}
            </button>
          </div>
          <label className="check-row">
            <input
              type="checkbox"
              checked={autoAdvance}
              onChange={(e) => persistAdvance(e.target.checked)}
            />
            Auto-advance on correct
          </label>
          <p className="note">
            Enter checks · 1–4 picks a choice · ? skips · Space continues.
            {suggested.length ? ` Decay Map suggests ${suggested.join(", ")}.` : ""}
          </p>
          {error ? <div className="error">{error}</div> : null}
        </div>
      ) : showRecap ? (
        <div className="quiz-stage surface">
          <Recap
            score={scoreboard}
            verdict={feedback?.verdict || (timeUp ? "Time. That's the round." : finishNote)}
            comboBest={feedback?.combo_best || combo}
            misses={misses}
            onInspect={openRelated}
            onAgain={() => start()}
            onRetryMisses={() => {
              setPool("misses");
              setKind("recall");
              start({ kind: "recall", pool: "misses" });
            }}
            onHome={onHome}
          />
          {inspect ? <InspectCard card={inspect} onOpenRelated={openRelated} /> : null}
        </div>
      ) : (
        <div className={`quiz-stage surface ${shake ? "shake" : ""}`}>
          <div className="drill-meter">
            <div className="meter-track">
              <div
                className="meter-fill"
                style={{ width: `${Math.min(100, (progressNow / progressTotal) * 100)}%` }}
              />
            </div>
            <div className="meter-row">
              <div className="muted">
                {progressNow} / {progressTotal}
                {feedback?.score ? ` · ${feedback.score.correct} correct` : ""}
                {combo >= 2 ? ` · combo ${combo}` : ""}
                {secondsLeft != null ? ` · ${secondsLeft}s` : ""}
              </div>
              <button type="button" className="text-btn" onClick={exit}>Exit</button>
            </div>
          </div>

          {question ? (
            <>
              <div className="prompt">
                <div className="eyebrow">
                  {question.prompt_type} · lv {question.level} · {question.object_type}
                  {question.band ? ` · ${question.band}` : ""}
                </div>
                <div className="chars" key={question.id}>
                  {question.prompt_type === "reverse"
                    ? question.prompt_text
                    : question.characters}
                </div>
                {isTyped && !feedback ? (
                  <p className="note">
                    {question.prompt_type === "reading"
                      ? "Type the reading — hiragana or romaji."
                      : "Type an accepted English meaning."}
                  </p>
                ) : null}
              </div>

              {isTyped && !feedback ? (
                <form
                  className="recall-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    submitText();
                  }}
                >
                  <input
                    ref={inputRef}
                    value={typed}
                    autoComplete="off"
                    autoCapitalize="off"
                    autoCorrect="off"
                    spellCheck={false}
                    placeholder={question.prompt_type === "reading" ? "よみ / yomi" : "meaning"}
                    onChange={(e) => setTyped(e.target.value)}
                    onKeyDown={onKeyDown}
                    onCompositionStart={() => {
                      composing.current = true;
                    }}
                    onCompositionEnd={() => {
                      composing.current = false;
                    }}
                    disabled={busy}
                  />
                  <button className="primary-btn" type="submit" disabled={busy || !typed.trim()}>
                    Check
                  </button>
                </form>
              ) : null}

              {!isTyped ? (
                <div className={`choices ${question.prompt_type === "reverse" ? "glyph-choices" : ""}`}>
                  {question.choices.map((choice, choiceIndex) => {
                    let className = "choice";
                    if (question.prompt_type === "reverse") className += " glyph-choice";
                    if (feedback) {
                      if (choiceIndex === feedback.correct_index) className += " correct";
                      else if (choiceIndex === feedback.chosen_index && !feedback.correct) {
                        className += " wrong";
                      }
                    }
                    return (
                      <button
                        key={`${question.id}-${choiceIndex}`}
                        className={className}
                        disabled={busy || Boolean(feedback)}
                        onClick={() => submitChoice(choiceIndex)}
                      >
                        {!isTyped && question.prompt_type !== "reverse" ? (
                          <span className="choice-num">{choiceIndex + 1}</span>
                        ) : null}
                        {choice}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </>
          ) : null}

          {!feedback ? (
            <button type="button" className="text-btn" onClick={giveUp} disabled={busy}>
              I don’t know (?)
            </button>
          ) : (
            <div className={`reveal ${feedback.correct ? "ok" : "nope"}`}>
              <strong>
                {feedback.correct
                  ? (combo >= 3 ? `Combo ${combo}.` : "Solid.")
                  : feedback.almost
                    ? "Almost."
                    : feedback.gave_up
                      ? "Passed."
                      : "Not yet."}
              </strong>
              {" "}
              {feedback.reveal?.meaning || feedback.correct_answer}
              {feedback.reveal?.readings_labeled?.length
                ? ` · ${feedback.reveal.readings_labeled.map((item) => item.reading).join(" / ")}`
                : feedback.reveal?.readings?.length
                  ? ` · ${feedback.reveal.readings.join(" / ")}`
                  : ""}
              {!feedback.correct && feedback.submitted ? (
                <div className="meta">You said {feedback.submitted}</div>
              ) : null}
              {inspect ? <InspectCard card={inspect} onOpenRelated={openRelated} /> : null}
              <div style={{ marginTop: "0.85rem" }}>
                <button className="primary-btn" onClick={next}>
                  {feedback.score?.finished ? "Finish" : "Next"}
                </button>
              </div>
            </div>
          )}

          {error ? <div className="error">{error}</div> : null}
        </div>
      )}
    </section>
  );
}

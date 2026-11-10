import { useEffect, useRef, useState } from "react";
import { toKana } from "wanakana";
import { api } from "./api.js";
import InspectCard from "./InspectCard.jsx";
import { MissHint } from "./Mnemonic.jsx";
import { SoundToggle, soundEnabled } from "./sound.jsx";
import { T } from "./Term.jsx";

const SETUP_KEY = "kani-drill-setup";
const FORMAT_NAME = { recall: "Recall", mc: "Multiple choice", reverse: "Reverse", speed: "Blitz" };
const POOL_NAME = { decay: "Decaying", due: "Due now", leeches: "Leeches", burned: "Ghosts", misses: "My misses" };

function readSetup() {
  try {
    return JSON.parse(localStorage.getItem(SETUP_KEY)) || {};
  } catch {
    return {};
  }
}

function rememberSetup(setup) {
  try {
    localStorage.setItem(SETUP_KEY, JSON.stringify(setup));
  } catch {
    /* private mode */
  }
}

const FORMATS = [
  { id: "recall", label: "Type it", hint: "Same muscle as a real review", term: "recall" },
  { id: "mc", label: "Multiple choice", hint: "Warm-up if recall feels sharp", term: "warmup" },
  { id: "reverse", label: "Reverse", hint: "See the meaning, pick the glyph", term: "reverse" },
  { id: "speed", label: "60s blitz", hint: "As many as you can in a minute", term: "blitz" },
];

const POOLS = [
  { id: "decay", label: "Decay-weighted", term: "decay" },
  { id: "due", label: "Due now", term: "due" },
  { id: "leeches", label: "Leeches", term: "leech" },
  { id: "burned", label: "Ghosts", term: "ghost" },
  { id: "misses", label: "My misses", term: "notebook" },
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
            {option.term ? (
              <T k={option.term} hoverOnly>
                {option.label}
              </T>
            ) : (
              option.label
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

function Recap({
  score, verdict, comboBest, misses, cleared, weekAccuracy,
  onAgain, onRetryMisses, onRead, onHome, onInspect,
}) {
  const round = score.total ? Math.round((score.correct / score.total) * 100) : 0;
  const retry = misses.length > 0;
  return (
    <div className="recap">
      <div className="recap-score">
        <span className="eyebrow">Session</span>
        <div className="chars">{score.correct}/{score.total}</div>
        <p className="verdict">{verdict || "Round complete."}</p>
        <p className="note">
          {round}% this round
          {weekAccuracy != null ? ` · ${weekAccuracy}% over the last 7 days` : ""}
        </p>
        {comboBest ? (
          <p className="note">
            Best <T k="combo">combo</T> {comboBest}
          </p>
        ) : null}
        {cleared?.length ? (
          <p className="note">
            Came back and cleared: {cleared.map((item) => item.characters || item.correct_answer).join("、")}
          </p>
        ) : null}
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
        <p className="note">
          No misses. Take that straight into <T k="wanikani">WaniKani</T>.
        </p>
      )}
      <div className="hero-actions">
        {retry ? (
          <button className="primary-btn" onClick={onRetryMisses}>Retry misses</button>
        ) : (
          <button className="primary-btn" onClick={onRead}>Read today's page</button>
        )}
      </div>
      <div className="recap-links">
        <button type="button" className="quiet-link" onClick={onAgain}>Again</button>
        {retry ? (
          <button type="button" className="quiet-link" onClick={onRead}>Today's reading</button>
        ) : null}
        {onHome ? (
          <button type="button" className="quiet-link" onClick={onHome}>Home</button>
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
  onRead,
  onFocus,
}) {
  const query = readQuery();
  const [saved] = useState(readSetup);
  const suggested = data?.decay?.summary?.suggested_levels || [];
  const fallbackMin = suggested.length ? Math.min(...suggested) : 14;
  const fallbackMax = suggested.length ? Math.max(...suggested) : 18;
  const defaultMin = query.min ?? saved.minLevel ?? fallbackMin;
  const defaultMax = query.max ?? saved.maxLevel ?? fallbackMax;

  const [kind, setKind] = useState(query.kind || saved.kind || defaultKind);
  const [pool, setPool] = useState(query.pool || saved.pool || defaultPool);
  const [minLevel, setMinLevel] = useState(defaultMin);
  const [maxLevel, setMaxLevel] = useState(defaultMax);
  const [count, setCount] = useState(query.count || saved.count || defaultCount);
  const [mode, setMode] = useState(saved.mode || "both");
  const [showSetup, setShowSetup] = useState(false);
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
  const [hint, setHint] = useState("");
  const [wrapUp, setWrapUp] = useState(false);
  const [scoreboard, setScoreboard] = useState({ correct: 0, total: 0 });
  const [cleared, setCleared] = useState([]);
  const [weekAccuracy, setWeekAccuracy] = useState(null);
  const composing = useRef(false);
  const inputRef = useRef(null);
  const autoStarted = useRef(false);

  const objectTypes = query.types || defaultObjectTypes;
  const question = session?.questions?.[index] || null;
  const finished = Boolean(feedback?.score?.finished) || (secondsLeft === 0 && session);
  const isTyped = (session?.kind || kind) === "recall" || (session?.kind || kind) === "speed";
  const progressTotal = session?.question_count || count;
  const progressNow = feedback?.score?.answered ?? feedback?.score?.total ?? (session ? index : 0);
  const timeUp = session?.kind === "speed" && secondsLeft === 0;
  const showRecap = Boolean(session && (wrapUp || timeUp));
  const inSession = Boolean(session && !showRecap);

  useEffect(() => {
    onFocus?.(inSession);
    return () => onFocus?.(false);
  }, [inSession, onFocus]);

  useEffect(() => {
    // A saved setup, or a link that names the levels, wins over the suggestion.
    if (session || query.min != null || saved.minLevel != null) return;
    setMinLevel(defaultMin);
    setMaxLevel(defaultMax);
  }, [defaultMin, defaultMax, session, query.min, saved.minLevel]);

  useEffect(() => {
    const url = feedback?.reveal?.audio_url || feedback?.inspect?.audio_url;
    if (!url || !soundEnabled() || (session?.kind || kind) === "speed") return undefined;
    const audio = new Audio(url);
    audio.play().catch(() => {});
    return () => {
      audio.pause();
    };
  }, [feedback, session?.kind, kind]);

  useEffect(() => {
    if (!showRecap) return undefined;
    let live = true;
    api.drillStats()
      .then((stats) => {
        if (live) setWeekAccuracy(stats?.week_accuracy ?? null);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [showRecap]);

  async function start(overrides = {}) {
    setBusy(true);
    setError("");
    setFeedback(null);
    setInspect(null);
    setMisses([]);
    setCombo(0);
    setTyped("");
    setHint("");
    setWrapUp(false);
    setScoreboard({ correct: 0, total: 0 });
    setCleared([]);
    setWeekAccuracy(null);
    setSession(null);
    try {
      const nextKind = overrides.kind || kind;
      const nextPool = overrides.pool || pool;
      const nextMin = Number(overrides.min_level ?? minLevel);
      const nextMax = Number(overrides.max_level ?? maxLevel);
      const nextCount = Number(overrides.count ?? (nextKind === "speed" ? 24 : count));
      const modes =
        mode === "both" ? ["meaning", "reading"] : mode === "meaning" ? ["meaning"] : ["reading"];
      rememberSetup({
        kind: nextKind,
        pool: nextPool,
        minLevel: nextMin,
        maxLevel: nextMax,
        count: nextKind === "speed" ? count : nextCount,
        mode,
      });
      const drill = await api.startDrill({
        min_level: nextMin,
        max_level: nextMax,
        count: nextCount,
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

  function bump() {
    setShake(true);
    window.setTimeout(() => setShake(false), 420);
  }

  function applyResult(result, current) {
    setHint("");
    if (result.requeued) {
      // A miss comes back a few questions later; the round can't end until it's cleared.
      const retry = {
        ...result.requeued,
        prompt_text: result.requeued.prompt_text || current.prompt_text,
      };
      setSession((prev) => {
        if (!prev) return prev;
        const questions = [...prev.questions];
        const at = Math.min(questions.length, index + 1 + (retry.gap || 3));
        questions.splice(at, 0, retry);
        return {
          ...prev,
          questions,
          question_count: result.score?.question_count ?? questions.length,
        };
      });
    }
    setFeedback(result);
    setInspect(result.inspect || null);
    setCombo(result.combo || 0);
    setScoreboard({
      correct: result.score?.correct || 0,
      total: result.score?.total || 0,
    });
    if (result.correct && result.retry_of) {
      setCleared((list) => [
        ...list,
        {
          characters: result.reveal?.characters || current.characters,
          correct_answer: result.correct_answer,
          subject_id: result.reveal?.subject_id,
        },
      ]);
    }
    if (!result.correct) {
      bump();
      if (result.retry_of) return;
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
    // Flush a dangling "n" (かn -> かん) before grading a reading.
    const raw = question.prompt_type === "reading" ? toKana((value || "").toLowerCase()) : value;
    const trimmed = (raw || "").trim();
    if (!trimmed) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.answerDrill({
        session_id: session.session_id,
        question_id: question.id,
        text: trimmed,
      });
      if (result.retry) {
        setHint(result.hint || "Try the other half.");
        bump();
        const el = inputRef.current;
        if (result.close && el) {
          const n = el.value.length;
          el.focus();
          el.setSelectionRange(n, n);
        } else {
          el?.select();
        }
        return;
      }
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

  async function undoSlip() {
    if (!session || !question || !feedback?.undoable || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.undoDrill({
        session_id: session.session_id,
        question_id: question.id,
      });
      const subjectId = feedback.reveal?.subject_id;
      setFeedback((prev) => ({
        ...prev,
        ...result,
        correct: true,
        undone: true,
        requeued: null,
        undoable: false,
      }));
      setCombo(result.combo || 0);
      setScoreboard({
        correct: result.score?.correct || 0,
        total: result.score?.total || 0,
      });
      setMisses((list) => list.filter((miss) => miss.subject_id !== subjectId));
      if (result.removed_id) {
        setSession((prev) => {
          if (!prev) return prev;
          const questions = prev.questions.filter((item) => item.id !== result.removed_id);
          return {
            ...prev,
            questions,
            question_count: result.score?.question_count ?? questions.length,
          };
        });
      }
    } catch (err) {
      setError(err.message || "Could not take that back");
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
    setHint("");
  }


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
        // A held Enter must not submit and skip the answer in one press.
        if (event.repeat) return;
        if ((event.key === "u" || event.key === "U") && feedback.undoable) {
          event.preventDefault();
          undoSlip();
          return;
        }
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
    if (event.key !== "Enter" || event.repeat) return;
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
          {!showSetup ? (
            <>
              <p className="setup-line">{[
                FORMAT_NAME[kind] || "Recall",
                POOL_NAME[pool] || "Decaying",
                String(minLevel) === String(maxLevel) ? `level ${minLevel}` : `levels ${minLevel}–${maxLevel}`,
                kind === "speed" ? "60 seconds" : `${count} questions`,
                mode === "meaning" ? "meanings" : mode === "reading" ? "readings" : "",
              ].filter(Boolean).join(" · ")}</p>
              <div className="hero-actions">
                <button className="primary-btn" onClick={() => start()} disabled={busy}>
                  {busy ? "Building…" : "Start"}
                </button>
                <button type="button" className="ghost-btn" onClick={() => setShowSetup(true)}>Change setup</button>
              </div>
            </>
          ) : null}
          {showSetup ? (
            <>
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
              <label>
                <T k="meaning">Meaning</T> / <T k="reading">reading</T>
              </label>
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="both">Meaning + reading</option>
                <option value="meaning">Meaning only</option>
                <option value="reading">Reading only</option>
              </select>
            </div>
            <button className="primary-btn" onClick={() => start()} disabled={busy}>
              {busy ? "Building…" : kind === "speed" ? "Start blitz" : "Begin"}
            </button>
            <button type="button" className="text-btn" onClick={() => setShowSetup(false)}>Hide setup</button>
          </div>
            </>
          ) : null}
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
            cleared={cleared}
            weekAccuracy={weekAccuracy}
            onInspect={openRelated}
            onAgain={() => start()}
            onRetryMisses={() => {
              setPool("misses");
              setKind("recall");
              start({ kind: "recall", pool: "misses" });
            }}
            onRead={onRead}
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
                {combo >= 2 ? (
                  <>
                    {" · "}
                    <T k="combo">combo</T> {combo}
                  </>
                ) : null}
                {secondsLeft != null ? ` · ${secondsLeft}s` : ""}
              </div>
              <span className="meter-tools">
                {session.kind !== "speed" ? <SoundToggle /> : null}
                <button type="button" className="text-btn" onClick={exit}>Exit</button>
              </span>
            </div>
          </div>

          {question ? (
            <>
              <div className="prompt">
                <div className="eyebrow">
                  {question.retry ? "back again · " : ""}
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
                      ? "Reading: type romaji, it turns into kana."
                      : "Meaning: type it in English."}
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
                    className={question.prompt_type === "reading" ? "answer-reading" : "answer-meaning"}
                    placeholder={question.prompt_type === "reading" ? "答え" : "Your response"}
                    lang={question.prompt_type === "reading" ? "ja" : "en"}
                    onChange={(e) => {
                      // Reading prompts convert romaji to kana as you type, like WaniKani.
                      // A native Japanese IME already produces kana, so leave composition alone.
                      const value = e.target.value;
                      setTyped(
                        question.prompt_type === "reading" && !composing.current
                          ? toKana(value.toLowerCase(), { IMEMode: true })
                          : value,
                      );
                      if (hint) setHint("");
                    }}
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

              {hint && !feedback ? <p className="drill-hint">{hint}</p> : null}

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
                {feedback.undone
                  ? "Counted. It was a slip."
                  : feedback.correct
                    ? feedback.almost
                      ? "Close enough. Watch the spelling."
                      : (combo >= 3 ? `Combo ${combo}.` : "Solid.")
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
              {(!feedback.correct || feedback.almost) && feedback.submitted ? (
                <div className="meta">You said {feedback.submitted}</div>
              ) : null}
              {feedback.requeued ? (
                <div className="meta">It comes back in a few. Clear it to finish the round.</div>
              ) : null}
              {!feedback.correct && inspect ? (
                <MissHint card={inspect} promptType={question?.prompt_type} />
              ) : null}
              {inspect ? (
                <InspectCard
                  card={inspect}
                  onOpenRelated={openRelated}
                  mnemonicOpen={!feedback.correct}
                />
              ) : null}
              <div className="reveal-actions">
                <button className="primary-btn" onClick={next}>
                  {feedback.score?.finished ? "Finish" : "Next"}
                </button>
                {feedback.undoable ? (
                  <button type="button" className="ghost-btn" onClick={undoSlip} disabled={busy}>
                    I knew it <kbd>U</kbd>
                  </button>
                ) : null}
              </div>
            </div>
          )}

          {error ? <div className="error">{error}</div> : null}
        </div>
      )}
    </section>
  );
}

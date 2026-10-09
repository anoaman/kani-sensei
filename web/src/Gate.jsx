import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { QuickQuiz } from "./Home.jsx";

// Where the iPhone Shortcut sends you when a time-sink app is locked: a short
// timed quiz on things you've already Guru'd. It can be failed, it can't be
// rerolled, and every unlock of the day costs more than the last.

function clock(iso) {
  return iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : null;
}

function ordinal(n) {
  return ["", "First", "Second", "Third"][n] || `${n}th`;
}

function rules(tier) {
  if (!tier) return null;
  const misses = tier.allowed_misses === 1 ? "1 miss" : `${tier.allowed_misses} misses`;
  return `${tier.size} questions · ${misses} allowed · 15s each`;
}

export default function Gate({ go }) {
  const [state, setState] = useState(null); // { open, reason, until, next }
  const [quiz, setQuiz] = useState(false);
  const [round, setRound] = useState(0); // bump for a fresh gate after a fail
  const [tier, setTier] = useState(null);
  const [practice, setPractice] = useState(false);
  const [outcome, setOutcome] = useState(null);
  const [error, setError] = useState("");
  const gateId = useRef(null);

  useEffect(() => {
    api.gateStatus()
      .then((status) => {
        setState(status);
        setTier(status.next || null);
        if (!status.open) setQuiz(true);
      })
      .catch(() => setQuiz(true));
  }, []);

  async function start() {
    const data = await api.gateStart();
    gateId.current = data.gate_id;
    if (data.tier) setTier(data.tier);
    if (!data.drill) {
      setOutcome({ passed: true, status: data.status });
      return { questions: [] };
    }
    return data.drill;
  }

  async function finish() {
    try {
      const result = await api.gateFinish(gateId.current);
      if (result.passed || result.failed) setOutcome(result);
      else setError("That one didn't register. Reload to pick it back up.");
    } catch (err) {
      setError(err.message || "Could not unlock");
    }
  }

  function again() {
    setOutcome(null);
    setError("");
    setRound((value) => value + 1);
  }

  if (outcome?.failed) {
    const { correct = 0, total = 0, allowed_misses: allowed = 0 } = outcome.score || {};
    return (
      <main className="gate">
        <p className="kicker">Not this time</p>
        <h1>{total - correct} misses. {allowed === 1 ? "One" : allowed} allowed.</h1>
        <p className="muted">{correct} of {total} first try. Still locked. Next set is fresh.</p>
        <button className="go-btn" onClick={again}>New set</button>
      </main>
    );
  }

  if (outcome?.passed) {
    const status = outcome.status || {};
    const minutes = outcome.minutes;
    return (
      <main className="gate">
        <p className="kicker">{minutes === 0 ? "Practice done" : "Gate cleared"}</p>
        <h1>{minutes === 0 || !status.until ? "Nice." : `Open until ${clock(status.until)}.`}</h1>
        <p className="muted">
          {minutes === 180 ? "Clean, so the full 3 hours." : minutes ? "Not clean, so 90 minutes. Clean gets 3 hours." : null}
          {minutes === 0 ? "Practice doesn't move the clock." : " Tap ◀ top-left to get back to your app."}
        </p>
        <button className="ghost-btn" onClick={() => go("/today")}>Or keep going on today's set</button>
      </main>
    );
  }

  if (state?.open && !quiz) {
    return (
      <main className="gate">
        <p className="kicker">{state.reason === "night" ? "Night" : "Clear"}</p>
        <h1>{state.reason === "night" ? `Open until ${clock(state.until)}. Go to sleep.` : `You're clear until ${clock(state.until)}.`}</h1>
        <p className="muted">Nothing to do here. Tap ◀ top-left to go back.</p>
        <button className="ghost-btn" onClick={() => { setPractice(true); setQuiz(true); }}>Practice five anyway</button>
      </main>
    );
  }

  return (
    <main className="gate">
      <p className="kicker">{practice ? "Practice" : tier?.unlock ? `Locked · ${ordinal(tier.unlock).toLowerCase()} unlock today` : "Locked"}</p>
      <h1>{practice ? "Five you already know." : tier?.unlock > 1 ? "Back again. It costs more now." : "Prove you still know them."}</h1>
      <p className="muted">
        {practice
          ? "Doesn't move the clock."
          : "Things you've Guru'd, timed. Too many misses and it ends; reloading brings back the same set. Clean opens 3 hours, one slip opens 90 minutes."}
      </p>
      {error ? <div className="error">{error}</div> : null}
      {quiz ? (
        <QuickQuiz
          key={round}
          kicker="Gate"
          meta={rules(tier) || "Timed"}
          start={start}
          onSeen={(question) => api.gateSeen(gateId.current, question.id)}
          onFinished={finish}
          autoFocus
          done={(score, session) => (
            <div className="warmup-done">
              <div className="warmup-glyph" lang="ja">…</div>
              <p>{score} first try. Checking…</p>
            </div>
          )}
        />
      ) : <p className="muted">Checking…</p>}
    </main>
  );
}

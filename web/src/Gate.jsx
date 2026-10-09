import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { QuickQuiz } from "./Home.jsx";

// Where the iPhone Shortcut sends you when a time-sink app is locked:
// five quick questions on things you've already Guru'd, then back to the app.

function clock(iso) {
  return iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : null;
}

export default function Gate({ go }) {
  const [state, setState] = useState(null); // { open, reason, until }
  const [quiz, setQuiz] = useState(false);
  const [unlocked, setUnlocked] = useState(null);
  const [error, setError] = useState("");
  const gateId = useRef(null);

  useEffect(() => {
    api.gateStatus()
      .then((status) => {
        setState(status);
        if (!status.open) setQuiz(true);
      })
      .catch(() => setQuiz(true));
  }, []);

  async function start() {
    const data = await api.gateStart();
    gateId.current = data.gate_id;
    if (!data.drill) {
      setUnlocked(data.status);
      return { questions: [] };
    }
    return data.drill;
  }

  async function finish() {
    try {
      const result = await api.gateFinish(gateId.current);
      if (result.passed) setUnlocked(result.status);
      else setError("That one didn't register. Reload for a fresh five.");
    } catch (err) {
      setError(err.message || "Could not unlock");
    }
  }

  if (unlocked) {
    return (
      <main className="gate">
        <p className="kicker">Gate cleared</p>
        <h1>Open until {clock(unlocked.until)}.</h1>
        <p className="muted">Tap ◀ top-left to get back to your app.</p>
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
        <button className="ghost-btn" onClick={() => setQuiz(true)}>Quick five anyway</button>
      </main>
    );
  }

  return (
    <main className="gate">
      <p className="kicker">Locked</p>
      <h1>Five you already know.</h1>
      <p className="muted">Things you've Guru'd. Misses come back until they stick. Doesn't touch your SRS.</p>
      {error ? <div className="error">{error}</div> : null}
      {quiz ? (
        <QuickQuiz
          kicker="Gate"
          meta="5 items · then 3 hours open"
          start={start}
          onFinished={finish}
          autoFocus
          done={(score, session) => (
            <div className="warmup-done">
              <div className="warmup-glyph" lang="ja">…</div>
              <p>{score} of {session.question_count || session.questions.length} first try. Unlocking…</p>
            </div>
          )}
        />
      ) : <p className="muted">Checking…</p>}
    </main>
  );
}

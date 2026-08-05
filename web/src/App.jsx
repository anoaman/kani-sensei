import { useEffect, useMemo, useState } from "react";
import { api } from "./api.js";

const VIEWS = [
  { id: "home", label: "Home" },
  { id: "decay", label: "Decay Map" },
  { id: "runway", label: "Runway" },
  { id: "quiz", label: "Warm-Up" },
];

function formatDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return String(value);
  }
}

function Login({ onReady }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.login(password);
      onReady();
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-shell">
      <div className="login-card surface">
        <h1>Kani Sensei</h1>
        <p>Re-entry for the pile you left behind. Sign in to open the map.</p>
        <form onSubmit={submit}>
          <input
            type="password"
            autoFocus
            autoComplete="current-password"
            placeholder="Site password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error ? <div className="error">{error}</div> : null}
          <button className="primary-btn" type="submit" disabled={busy || !password}>
            {busy ? "Opening…" : "Enter"}
          </button>
        </form>
      </div>
    </div>
  );
}

function Home({ data, onNavigate }) {
  const suggested = data?.decay?.summary?.suggested_levels || [];
  const runway = data?.runway;
  return (
    <section className="hero panel">
      <div className="hero-wash" aria-hidden="true" />
      <h1 className="hero-brand">Kani Sensei</h1>
      <p>
        The queue looks huge because it is. Start with what actually rotted,
        warm it back up, then burn the rest at a pace you can keep.
      </p>
      <div className="hero-actions">
        <button className="primary-btn" onClick={() => onNavigate("quiz")}>
          Start warm-up
        </button>
        <button className="ghost-btn" onClick={() => onNavigate("decay")}>
          See decay map
        </button>
      </div>
      <div className="metric-row" style={{ marginTop: "2rem" }}>
        <div className="metric">
          <span className="label">Suggested levels</span>
          <span className="value">
            {suggested.length ? suggested.slice(0, 3).join(" · ") : "—"}
          </span>
        </div>
        <div className="metric">
          <span className="label">Backlog (24h)</span>
          <span className="value">{runway?.current_backlog ?? "—"}</span>
        </div>
        <div className="metric">
          <span className="label">Burn status</span>
          <span className="value" style={{ fontSize: "1.35rem" }}>
            {(runway?.burn_status || "—").replaceAll("_", " ")}
          </span>
        </div>
      </div>
    </section>
  );
}

function DecayView({ data }) {
  const decay = data?.decay;
  if (!decay) return <div className="empty">Loading decay map…</div>;
  const maxRisk = Math.max(1, ...(decay.levels || []).map((l) => l.risk || 0));

  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <h2>Decay Map</h2>
          <p>
            What looks soft in the current snapshot — ranked so you know where
            to start, not where to panic.
          </p>
        </div>
      </div>
      <div className="grid-2">
        <div className="surface">
          <div className="metric-row">
            <div className="metric">
              <span className="label">Mapped</span>
              <span className="value">{decay.summary.items}</span>
            </div>
            <div className="metric">
              <span className="label">Due</span>
              <span className="value">{decay.summary.due}</span>
            </div>
            <div className="metric">
              <span className="label">Regressed</span>
              <span className="value">{decay.summary.regressed ?? 0}</span>
            </div>
          </div>
          <div className="level-list">
            {(decay.levels || []).slice(0, 12).map((level) => (
              <div className="level-row" key={level.level}>
                <strong>Lv {level.level}</strong>
                <div className="bar">
                  <div
                    className="fill"
                    style={{ width: `${Math.max(8, (level.risk / maxRisk) * 100)}%` }}
                  />
                </div>
                <span className="muted">{level.risk}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="surface">
          <strong>Highest pressure items</strong>
          <div className="item-list" style={{ marginTop: "0.85rem" }}>
            {(decay.items || []).slice(0, 10).map((item) => (
              <div className="item" key={item.subject_id}>
                <div className="glyph">{item.characters}</div>
                <div>
                  <div>{item.meaning || "—"}</div>
                  <div className="meta">
                    Lv {item.level} · {item.type} · SRS {item.srs_stage}
                    {item.regressed ? " · dropped" : ""}
                  </div>
                </div>
                <div className={`band ${item.band}`}>{item.band}</div>
              </div>
            ))}
          </div>
          <p className="note" style={{ marginTop: "1rem" }}>
            Signal: {decay.signal}
            {(decay.limitations || []).slice(0, 1).map((line) => (
              <span key={line}>
                <br />
                {line}
              </span>
            ))}
          </p>
        </div>
      </div>
    </section>
  );
}

function RunwayView({ data }) {
  const runway = data?.runway;
  if (!runway) return <div className="empty">Loading runway…</div>;
  const stages = runway.apprentice_breakdown || {};

  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <h2>Runway</h2>
          <p>
            Hold a daily pace and this is when the pile stops feeling like a
            cliff.
          </p>
        </div>
      </div>
      <div className="surface">
        <div className="metric-row">
          <div className="metric">
            <span className="label">Backlog</span>
            <span className="value">{runway.current_backlog}</span>
          </div>
          <div className="metric">
            <span className="label">Steady load</span>
            <span className="value">{runway.daily_load}</span>
          </div>
          <div className="metric">
            <span className="label">Recommended</span>
            <span className="value">{runway.recommended_daily}</span>
          </div>
        </div>
        <div className="metric-row" style={{ marginTop: "0.5rem" }}>
          <div className="metric">
            <span className="label">Status</span>
            <span className="value" style={{ fontSize: "1.35rem" }}>
              {String(runway.burn_status || "").replaceAll("_", " ")}
            </span>
          </div>
          <div className="metric">
            <span className="label">Days to healthy</span>
            <span className="value">
              {runway.projected_days_to_healthy ?? "—"}
            </span>
          </div>
          <div className="metric">
            <span className="label">Confidence</span>
            <span className="value" style={{ fontSize: "1.35rem" }}>
              {runway.confidence}
            </span>
          </div>
        </div>
        <div className="level-list" style={{ marginTop: "1.25rem" }}>
          {[1, 2, 3, 4].map((stage) => (
            <div className="level-row" key={stage}>
              <strong>App {stage}</strong>
              <div className="bar">
                <div
                  className="fill"
                  style={{
                    width: `${Math.min(100, (stages[stage] || 0) * 4)}%`,
                    background: "linear-gradient(90deg, #3a4a5c, #122033)",
                  }}
                />
              </div>
              <span className="muted">{stages[stage] || 0}</span>
            </div>
          ))}
        </div>
        <p className="note" style={{ marginTop: "1rem" }}>
          {runway.confidence_note}
          {(runway.warnings || []).slice(0, 2).map((w) => (
            <span key={w}>
              <br />
              {w}
            </span>
          ))}
        </p>
      </div>
    </section>
  );
}

function QuizView({ data }) {
  const suggested = data?.decay?.summary?.suggested_levels || [];
  const defaultMin = suggested.length ? Math.min(...suggested) : 14;
  const defaultMax = suggested.length ? Math.max(...suggested) : 18;

  const [minLevel, setMinLevel] = useState(defaultMin);
  const [maxLevel, setMaxLevel] = useState(defaultMax);
  const [count, setCount] = useState(10);
  const [mode, setMode] = useState("both");
  const [session, setSession] = useState(null);
  const [index, setIndex] = useState(0);
  const [feedback, setFeedback] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!session) {
      setMinLevel(defaultMin);
      setMaxLevel(defaultMax);
    }
  }, [defaultMin, defaultMax, session]);

  const question = session?.questions?.[index] || null;
  const finished = feedback?.score?.finished;

  async function start() {
    setBusy(true);
    setError("");
    setFeedback(null);
    try {
      const modes =
        mode === "both" ? ["meaning", "reading"] : mode === "meaning" ? ["meaning"] : ["reading"];
      const quiz = await api.startQuiz({
        min_level: Number(minLevel),
        max_level: Number(maxLevel),
        count: Number(count),
        modes,
      });
      setSession(quiz);
      setIndex(0);
    } catch (err) {
      setError(err.message || "Could not start quiz");
    } finally {
      setBusy(false);
    }
  }

  async function answer(choiceIndex) {
    if (!session || !question || feedback) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.answerQuiz({
        session_id: session.session_id,
        question_id: question.id,
        choice_index: choiceIndex,
      });
      setFeedback(result);
    } catch (err) {
      setError(err.message || "Could not grade answer");
    } finally {
      setBusy(false);
    }
  }

  function next() {
    if (!session) return;
    if (feedback?.score?.finished) {
      setSession(null);
      setFeedback(null);
      setIndex(0);
      return;
    }
    setIndex((value) => value + 1);
    setFeedback(null);
  }

  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <h2>Warm-Up Quiz</h2>
          <p>
            Multiple-choice drills weighted toward Decay Map pressure — get
            comfortable before you touch the real queue.
          </p>
        </div>
      </div>

      {!session ? (
        <div className="surface">
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
                max="30"
                value={count}
                onChange={(e) => setCount(e.target.value)}
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
            <button className="primary-btn" onClick={start} disabled={busy}>
              {busy ? "Building…" : "Begin"}
            </button>
          </div>
          {suggested.length ? (
            <p className="note">
              Decay Map suggests levels {suggested.join(", ")} right now.
            </p>
          ) : (
            <p className="note">
              No loud hotspots today — still useful to warm the softer end of
              your range.
            </p>
          )}
          {error ? <div className="error">{error}</div> : null}
        </div>
      ) : (
        <div className="quiz-stage surface">
          <div className="muted">
            Question {index + 1} / {session.question_count}
            {feedback?.score
              ? ` · Score ${feedback.score.correct}/${feedback.score.total}`
              : ""}
            {session.weighting?.mean_decay_score != null
              ? ` · mean decay ${session.weighting.mean_decay_score}`
              : ""}
          </div>

          {question ? (
            <>
              <div className="prompt">
                <div className="eyebrow">
                  {question.prompt_type} · lv {question.level} · {question.object_type}
                </div>
                <div className="chars" key={question.id}>
                  {question.characters}
                </div>
              </div>
              <div className="choices">
                {question.choices.map((choice, choiceIndex) => {
                  let className = "choice";
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
                      onClick={() => answer(choiceIndex)}
                    >
                      {choice}
                    </button>
                  );
                })}
              </div>
            </>
          ) : null}

          {feedback ? (
            <div className="reveal">
              <strong>{feedback.correct ? "Solid." : "Not yet."}</strong>
              {" "}
              {feedback.reveal?.meaning}
              {feedback.reveal?.readings?.length
                ? ` · ${feedback.reveal.readings.join(" / ")}`
                : ""}
              <div style={{ marginTop: "0.85rem" }}>
                <button className="primary-btn" onClick={next}>
                  {finished ? "Finish" : "Next"}
                </button>
              </div>
            </div>
          ) : null}

          {finished ? (
            <p className="note">
              Warm-up complete. Take that feeling into the real reviews.
            </p>
          ) : null}
          {error ? <div className="error">{error}</div> : null}
        </div>
      )}
    </section>
  );
}

export default function App() {
  const [auth, setAuth] = useState(null);
  const [view, setView] = useState("home");
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState("");

  async function refreshAuth() {
    try {
      const me = await api.me();
      setAuth(Boolean(me.authenticated));
    } catch {
      setAuth(false);
    }
  }

  async function loadOverview() {
    setLoadError("");
    try {
      const overview = await api.overview({ limit: 40 });
      setData(overview);
    } catch (err) {
      if (err.status === 401) {
        setAuth(false);
        return;
      }
      setLoadError(err.message || "Failed to load overview");
    }
  }

  useEffect(() => {
    refreshAuth();
  }, []);

  useEffect(() => {
    if (auth) loadOverview();
  }, [auth]);

  const syncNote = useMemo(() => {
    if (!data?.last_sync?.finished_at) return null;
    return `Last sync ${formatDate(data.last_sync.finished_at)}`;
  }, [data]);

  if (auth === null) {
    return <div className="empty" style={{ padding: "3rem", textAlign: "center" }}>Loading…</div>;
  }

  if (!auth) {
    return <Login onReady={() => setAuth(true)} />;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark">
          <strong>Kani Sensei</strong>
          <span>{syncNote || "WaniKani re-entry"}</span>
        </div>
        <nav className="nav" aria-label="Primary">
          {VIEWS.map((item) => (
            <button
              key={item.id}
              className={view === item.id ? "active" : ""}
              onClick={() => setView(item.id)}
            >
              {item.label}
            </button>
          ))}
          <button
            className="ghost-btn"
            onClick={async () => {
              await api.logout();
              setAuth(false);
              setData(null);
            }}
          >
            Sign out
          </button>
        </nav>
      </header>

      {loadError ? <div className="error" style={{ marginBottom: "1rem" }}>{loadError}</div> : null}

      {view === "home" ? <Home data={data} onNavigate={setView} /> : null}
      {view === "decay" ? <DecayView data={data} /> : null}
      {view === "runway" ? <RunwayView data={data} /> : null}
      {view === "quiz" ? <QuizView data={data} /> : null}
    </div>
  );
}

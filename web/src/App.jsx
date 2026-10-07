import { useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import TestView from "./TestView.jsx";

const OVERVIEW_CACHE_KEY = "kani-overview-v2";
const FOCUS_KEY = "kani-focus-v1";
const NAV = [
  { id: "today", label: "Today", path: "/" },
  { id: "practice", label: "Practice", path: "/practice" },
  { id: "progress", label: "Progress", path: "/progress" },
];

function readCache() {
  try {
    return JSON.parse(sessionStorage.getItem(OVERVIEW_CACHE_KEY)) || null;
  } catch {
    return null;
  }
}

function writeCache(value) {
  try {
    sessionStorage.setItem(OVERVIEW_CACHE_KEY, JSON.stringify(value));
  } catch {
    /* private mode */
  }
}

function viewFromPath(pathname) {
  if (pathname.startsWith("/session") || pathname.startsWith("/drill")) return "session";
  if (pathname.startsWith("/progress") || pathname.startsWith("/decay") || pathname.startsWith("/runway")) return "progress";
  if (
    pathname.startsWith("/practice") || pathname.startsWith("/kanji") ||
    pathname.startsWith("/vocab") || pathname.startsWith("/ghosts") ||
    pathname.startsWith("/leeches") || pathname.startsWith("/dojo") ||
    pathname.startsWith("/warmup") || pathname.startsWith("/glossary")
  ) return "practice";
  return "today";
}

function formatSync(value) {
  if (!value) return "Waiting for first sync";
  return `Synced ${new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
}

function Today({ data, navigate }) {
  const summary = data?.decay?.summary || {};
  const prescription = data?.prescription || {};
  const count = prescription.count || 10;
  const min = prescription.min_level || 1;
  const max = prescription.max_level || min;
  const minutes = prescription.minutes || Math.max(4, Math.ceil(count * 0.55));
  const kanji = prescription.type_counts?.kanji || 0;
  const vocabulary = prescription.type_counts?.vocabulary || 0;
  const attention = prescription.attention_count ?? (Number(summary.high_risk || 0) + Number(summary.medium_risk || 0));

  return (
    <main className="today-view">
      <section className="prescription">
        <p className="kicker">Today’s prescription</p>
        <h1>{count} items worth fixing.</h1>
        <p className="lede">
          Start with levels {min === max ? min : `${min}–${max}`}. Sensei selected the weakest recall signals first.
        </p>
        <div className="prescription-meta" aria-label="Session composition">
          <span><strong>{kanji}</strong> Kanji</span>
          <span><strong>{vocabulary}</strong> Vocabulary</span>
          <span><strong>{attention}</strong> Flagged</span>
        </div>
        <div className="action-row">
          <button className="primary-btn large" onClick={() => navigate("session", { min, max, count, types: "kanji,vocabulary", pool: "decay", go: 1 })}>
            Start today’s session
          </button>
          <button className="text-btn" onClick={() => navigate("practice")}>Choose focus</button>
        </div>
        <p className="session-note">About {minutes} minutes · meaning + reading · typed recall</p>
      </section>

      <section className="status-strip" aria-label="Current recovery status">
        <div><span>Recommended</span><strong>{count} items</strong></div>
        <div><span>Needs attention</span><strong>{attention}</strong></div>
        <div><span>Focus levels</span><strong>{min === max ? min : `${min}–${max}`}</strong></div>
      </section>

      <section className="next-step">
        <div>
          <p className="kicker">After this session</p>
          <h2>Take the warm-up into WaniKani.</h2>
          <p>Kani Sensei finds the soft spots. WaniKani remains the source of truth for your reviews.</p>
        </div>
        <a className="secondary-btn" href="https://www.wanikani.com/subjects/review" target="_blank" rel="noreferrer">Open WaniKani</a>
      </section>
    </main>
  );
}

function readFocus(suggested = []) {
  const hasSuggestion = suggested.length > 0;
  const fallback = {
    levelMode: hasSuggestion ? "range" : "single",
    min: hasSuggestion ? Math.min(...suggested) : 1,
    max: hasSuggestion ? Math.max(...suggested) : 1,
    type: hasSuggestion ? "mixed" : "kanji",
    count: 10,
  };
  try {
    return { ...fallback, ...JSON.parse(localStorage.getItem(FOCUS_KEY)) };
  } catch {
    return fallback;
  }
}

function Practice({ data, navigate }) {
  const suggested = data?.decay?.summary?.suggested_levels || [];
  const [focus, setFocus] = useState(() => readFocus(suggested));
  const suggestedMin = suggested.length ? Math.min(...suggested) : null;
  const suggestedMax = suggested.length ? Math.max(...suggested) : null;

  function update(key, value) {
    setFocus((current) => ({ ...current, [key]: value }));
  }

  function start() {
    const next = {
      ...focus,
      min: Math.max(1, Math.min(60, Number(focus.min) || 1)),
      max: Math.max(1, Math.min(60, Number(focus.levelMode === "single" ? focus.min : focus.max) || 1)),
    };
    if (next.max < next.min) next.max = next.min;
    localStorage.setItem(FOCUS_KEY, JSON.stringify(next));
    const types = next.type === "mixed" ? "radical,kanji,vocabulary" : next.type;
    navigate("session", { min: next.min, max: next.max, count: next.count, types, pool: "decay", go: 1 });
  }

  return (
    <main className="practice-view">
      <header className="page-intro">
        <p className="kicker">Practice</p>
        <h1>Choose what to work on.</h1>
        <p>Sensei recommends the daily session. This is where you take control.</p>
      </header>

      <section className="focus-builder">
        <div className="builder-section">
          <span className="step-number">01</span>
          <div>
            <h2>Level</h2>
            <div className="segmented">
              <button className={focus.levelMode === "single" ? "active" : ""} onClick={() => update("levelMode", "single")}>Single level</button>
              <button className={focus.levelMode === "range" ? "active" : ""} onClick={() => update("levelMode", "range")}>Level range</button>
            </div>
            <div className="level-fields">
              <label><span>{focus.levelMode === "single" ? "Level" : "From"}</span><input type="number" min="1" max="60" value={focus.min} onChange={(event) => update("min", event.target.value)} /></label>
              {focus.levelMode === "range" ? <label><span>To</span><input type="number" min="1" max="60" value={focus.max} onChange={(event) => update("max", event.target.value)} /></label> : null}
            </div>
            {suggested.length ? <button className="suggestion" onClick={() => setFocus((current) => ({ ...current, levelMode: "range", min: suggestedMin, max: suggestedMax }))}>Reset to Sensei’s levels {suggestedMin === suggestedMax ? suggestedMin : `${suggestedMin}–${suggestedMax}`}</button> : null}
          </div>
        </div>

        <div className="builder-section">
          <span className="step-number">02</span>
          <div>
            <h2>Content</h2>
            <div className="option-grid">
              {[
                ["kanji", "Kanji", "Characters and readings"],
                ["vocabulary", "Vocabulary", "Words and compounds"],
                ["radical", "Radicals", "Visual building blocks"],
                ["mixed", "Mixed", "Everything together"],
              ].map(([id, label, note]) => (
                <button key={id} className={focus.type === id ? "select-tile active" : "select-tile"} onClick={() => update("type", id)}>
                  <strong>{label}</strong><span>{note}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="builder-section">
          <span className="step-number">03</span>
          <div>
            <h2>Session size</h2>
            <div className="count-row">
              {[10, 20, 30, 40].map((value) => <button key={value} className={Number(focus.count) === value ? "active" : ""} onClick={() => update("count", value)}>{value}</button>)}
            </div>
          </div>
        </div>

        <div className="builder-footer">
          <p><strong>{focus.levelMode === "single" ? `Level ${focus.min}` : `Levels ${focus.min}–${focus.max}`}</strong> · {focus.type === "mixed" ? "Mixed content" : focus.type} · {focus.count} questions</p>
          <button className="primary-btn large" onClick={start}>Start focused session</button>
        </div>
      </section>
    </main>
  );
}

function Progress({ data, navigate }) {
  const practice = data?.practice || {};
  const levels = data?.decay?.levels || [];
  const hasSessions = Number(practice.week_sessions || 0) > 0;
  return (
    <main className="progress-view">
      <header className="page-intro">
        <p className="kicker">Progress</p>
        <h1>Your recovery, without the spreadsheet.</h1>
        <p>Enough signal to choose the next session. Nothing pretending to be a science project.</p>
      </header>
      <section className="progress-summary">
        <div><span>This week</span><strong>{practice.week_accuracy != null ? `${practice.week_accuracy}%` : "—"}</strong><small>{hasSessions ? `${practice.week_sessions} Sensei sessions` : "No sessions yet"}</small></div>
        <div><span>Sessions</span><strong>{practice.week_sessions || 0}</strong><small>completed in the last 7 days</small></div>
        <div><span>Best combo</span><strong>{practice.combo_best || 0}</strong><small>{hasSessions ? "correct answers in a row" : "Start once to set a baseline"}</small></div>
      </section>
      {!hasSessions ? <div className="empty-nudge"><span>Your progress starts with one clean session.</span><button className="text-btn" onClick={() => navigate("today")}>Start today’s prescription</button></div> : null}
      <section className="level-pressure">
        <div className="section-title"><div><p className="kicker">Level pressure</p><h2>Where memory is softest</h2></div><button className="text-btn" onClick={() => navigate("practice")}>Choose a focus</button></div>
        <div className="pressure-list">
          {levels.slice(0, 8).map((level) => (
            <button key={level.level} onClick={() => navigate("session", { min: level.level, max: level.level, count: 10, types: "kanji,vocabulary", pool: "decay", go: 1 })}>
              <span className="pressure-level">Level {level.level}</span>
              <span className="pressure-detail"><span className="pressure-track"><i style={{ width: `${Math.min(100, level.risk || 0)}%` }} /></span><small>Pressure {level.risk || 0} / 100{Number(level.high || 0) + Number(level.medium || 0) > 0 ? ` · ${Number(level.high || 0) + Number(level.medium || 0)} flagged` : ""}</small></span>
              <strong>Start →</strong>
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}

export default function App() {
  const [data, setData] = useState(readCache);
  const [view, setView] = useState(() => viewFromPath(window.location.pathname));
  const [focus, setFocus] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      const payload = await api.overview({ limit: 40 });
      setData(payload);
      writeCache(payload);
    } catch (err) {
      setError(err.message || "Could not load your WaniKani snapshot");
    }
  }

  useEffect(() => { load(); }, []);
  useEffect(() => {
    const handler = () => setView(viewFromPath(window.location.pathname));
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);

  function navigate(next, params = null) {
    const path = next === "session" ? "/session" : (NAV.find((item) => item.id === next)?.path || "/");
    const query = params ? `?${new URLSearchParams(params)}` : "";
    window.history.pushState({}, "", `${path}${query}`);
    setView(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const syncNote = useMemo(() => formatSync(data?.last_sync?.finished_at), [data]);
  const dataMode = data?.data_status?.mode;
  if (!data) {
    return (
      <div className="loading-screen">
        {error ? <div><div className="error">{error}</div><button className="primary-btn" onClick={load}>Try again</button></div> : "Opening Kani Sensei…"}
      </div>
    );
  }

  return (
    <div className={`app-shell ${focus ? "is-focus" : ""}`}>
      <header className="topbar">
        <button className="brand-mark" onClick={() => navigate("today")}><strong>Kani Sensei</strong><span>{syncNote}</span></button>
        {!focus ? <nav className="nav" aria-label="Primary navigation">
          {NAV.map((item) => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => navigate(item.id)}>{item.label}</button>)}
        </nav> : null}
      </header>
      {dataMode === "cached" || dataMode === "stale" ? (
        <div className={`data-notice ${dataMode}`} role="status">
          <strong>{dataMode === "stale" ? "Cached snapshot" : "Cached data"}</strong><span>{syncNote}. Practice works; new WaniKani progress is paused.</span>
        </div>
      ) : null}
      {error ? <div className="error global-error">{error}</div> : null}
      {view === "today" ? <Today data={data} navigate={navigate} /> : null}
      {view === "practice" ? <Practice data={data} navigate={navigate} /> : null}
      {view === "progress" ? <Progress data={data} navigate={navigate} /> : null}
      {view === "session" ? <TestView key={window.location.search} data={data} title="Practice session" blurb="One focused round. Finish clean, then decide whether to continue." onHome={() => navigate("today")} onFocus={setFocus} /> : null}
      {!focus ? <footer><span>Kani Sensei</span><span>Recovery practice for WaniKani</span></footer> : null}
    </div>
  );
}

import { useEffect, useState } from "react";
import { api } from "./api.js";
import TestView from "./TestView.jsx";
import CourseSession from "./CourseSession.jsx";
import { LevelIndex, LevelPage } from "./LevelPages.jsx";
import Home from "./Home.jsx";

// /level/N/continue: jump to whatever that level needs most, else its page.
function ContinueRoute({ level, go }) {
  useEffect(() => {
    api.courseLevel(level)
      .then((data) => go(data.course.next_mode ? `/level/${level}/${data.course.next_mode}` : `/level/${level}`))
      .catch(() => go(`/level/${level}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level]);
  return <p className="muted panel">Finding your next step…</p>;
}

const OVERVIEW_CACHE_KEY = "kani-overview-v2";
const FOCUS_KEY = "kani-focus-v1";

function readCache() {
  try {
    return JSON.parse(localStorage.getItem(OVERVIEW_CACHE_KEY)) || null;
  } catch {
    return null;
  }
}

function writeCache(value) {
  try {
    localStorage.setItem(OVERVIEW_CACHE_KEY, JSON.stringify(value));
  } catch {
    /* private mode */
  }
}


function viewFromPath(pathname) {
  if (pathname.startsWith("/session") || pathname.startsWith("/drill")) return "session";
  if (pathname.startsWith("/levels")) return "levels";
  if (pathname.startsWith("/today")) return "today";
  if (pathname.startsWith("/gate")) return "gate";
  const match = pathname.match(/^\/level\/(\d+)(?:\/(check|relearn|reviews|ahead|continue))?/);
  if (match) return match[2] ? (match[2] === "continue" ? "continue" : "course") : "level";
  return "dojo";
}

function levelFromPath(pathname) {
  const match = pathname.match(/^\/level\/(\d+)/);
  return match ? Math.max(1, Math.min(60, Number(match[1]))) : 1;
}

function wantsCustomize(pathname) {
  return ["/practice", "/kanji", "/vocab", "/ghosts", "/leeches", "/warmup", "/glossary"].some((prefix) => pathname.startsWith(prefix));
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

function Customize({ data, navigate, onClose }) {
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
    onClose();
    navigate("session", { min: next.min, max: next.max, count: next.count, types, pool: "decay", go: 1 });
  }

  return (
    <div className="drawer-scrim" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Customize a session" onClick={(event) => event.stopPropagation()}>
        <div className="drawer-head">
          <div><p className="kicker">Customize</p><h2>Pick your own round.</h2></div>
          <button className="drawer-close" onClick={onClose} aria-label="Close">Esc</button>
        </div>

        <div className="drawer-section">
          <h3>Level</h3>
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

        <div className="drawer-section">
          <h3>Content</h3>
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

        <div className="drawer-section">
          <h3>Session size</h3>
          <div className="count-row">
            {[10, 20, 30, 40].map((value) => <button key={value} className={Number(focus.count) === value ? "active" : ""} onClick={() => update("count", value)}>{value}</button>)}
          </div>
        </div>

        <div className="drawer-foot">
          <p><strong>{focus.levelMode === "single" ? `Level ${focus.min}` : `Levels ${focus.min}–${focus.max}`}</strong> · {focus.type === "mixed" ? "mixed content" : focus.type} · {focus.count} questions</p>
          <button className="go-btn wide" onClick={start}>Start this session</button>
        </div>
      </aside>
    </div>
  );
}

export default function App() {
  const [data, setData] = useState(readCache);
  const [view, setView] = useState(() => viewFromPath(window.location.pathname));
  const [pathname, setPathname] = useState(window.location.pathname);
  const [focus, setFocus] = useState(false);
  const [customize, setCustomize] = useState(() => wantsCustomize(window.location.pathname));
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
    const handler = () => {
      setView(viewFromPath(window.location.pathname));
      setPathname(window.location.pathname);
    };
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);
  useEffect(() => {
    function onKey(event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCustomize((open) => !open);
      } else if (event.key === "Escape") {
        setCustomize(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // navigate("session", params) | navigate("dojo") | navigate("/level/3") — paths may carry a query.
  function navigate(next, params = null) {
    const path = next.startsWith("/") ? next : next === "session" ? "/session" : "/";
    const query = params ? `?${new URLSearchParams(params)}` : "";
    window.history.pushState({}, "", `${path}${query}`);
    setView(viewFromPath(path));
    setPathname(window.location.pathname);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

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
        <button className="brand-mark" onClick={() => navigate("dojo")}><span className="seal" lang="ja">先</span><strong>Kani Sensei</strong></button>
        {!focus ? (
          <div className="topbar-meta">
            <button className="pill-btn" onClick={() => navigate("/levels")}>Levels</button>
            <button className="pill-btn" onClick={() => setCustomize(true)}>Customize <kbd className="wide-only">⌘K</kbd></button>
          </div>
        ) : null}
      </header>
      {error ? <div className="error global-error">{error}</div> : null}
      {view === "dojo" ? <Home go={navigate} /> : null}
      {view === "session" ? <TestView key={window.location.search} data={data} title="Practice session" blurb="One focused round. Finish clean, then decide whether to continue." onHome={() => navigate("dojo")} onFocus={setFocus} /> : null}
      {view === "levels" ? <LevelIndex go={navigate} /> : null}
      {view === "level" ? <LevelPage key={pathname} level={levelFromPath(pathname)} go={navigate} /> : null}
      {view === "course" ? (
        <CourseSession key={pathname} level={levelFromPath(pathname)} mode={pathname.split("/")[3]} go={navigate} onFocus={setFocus} />
      ) : null}
      {view === "gate" ? <CourseSession key={pathname} gate go={navigate} onFocus={setFocus} /> : null}
      {view === "today" ? <CourseSession key={pathname} daily go={navigate} onFocus={setFocus} /> : null}
      {view === "continue" ? <ContinueRoute key={pathname} level={levelFromPath(pathname)} go={navigate} /> : null}
      {customize && !focus ? <Customize data={data} navigate={navigate} onClose={() => setCustomize(false)} /> : null}
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import TestView from "./TestView.jsx";

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

const MAX_LEVEL = 60;

function viewFromPath(pathname) {
  if (pathname.startsWith("/session") || pathname.startsWith("/drill")) return "session";
  return "dojo";
}

function wantsCustomize(pathname) {
  return ["/practice", "/kanji", "/vocab", "/ghosts", "/leeches", "/warmup", "/glossary"].some((prefix) => pathname.startsWith(prefix));
}

function formatSync(value) {
  if (!value) return "Waiting for first sync";
  return `Synced ${new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
}

function formatDay(value) {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function levelRange(min, max) {
  return min === max ? `Level ${min}` : `Levels ${min}–${max}`;
}

function typeLabel(type) {
  return { kanji: "Kanji", vocabulary: "Vocabulary", radical: "Radical", kana_vocabulary: "Vocabulary" }[type] || type;
}

function sessionFromPrescription(data) {
  const prescription = data?.prescription || {};
  const count = prescription.count || 10;
  const min = prescription.min_level || 1;
  const max = prescription.max_level || min;
  return { count, min, max, minutes: prescription.minutes || Math.max(4, Math.ceil(count * 0.55)) };
}

function HeatStrip({ levels, focusMin, focusMax, onPick }) {
  const byLevel = new Map(levels.map((level) => [level.level, level]));
  const peak = Math.max(20, ...levels.map((level) => Number(level.risk || 0)));
  const cells = [];
  for (let n = 1; n <= MAX_LEVEL; n += 1) {
    const level = byLevel.get(n);
    if (!level) {
      cells.push(<span key={n} className="heat-cell off" aria-hidden="true" />);
      continue;
    }
    const heat = Math.min(1, Number(level.risk || 0) / peak);
    const focus = n >= focusMin && n <= focusMax;
    const flagged = Number(level.high || 0) + Number(level.medium || 0);
    cells.push(
      <button
        key={n}
        className={`heat-cell${focus ? " focus" : ""}${heat > 0.6 ? " hot" : ""}`}
        style={{ "--heat": (0.08 + 0.92 * heat).toFixed(2) }}
        title={`Level ${n} · ${level.accuracy ?? "—"}% accuracy · ${level.due || 0} due${flagged ? ` · ${flagged} flagged` : ""}`}
        aria-label={`Drill level ${n}`}
        onClick={() => onPick(n)}
      >
        <b>{n}</b>
      </button>
    );
  }
  return <div className="heat-strip">{cells}</div>;
}

function Dojo({ data, navigate, onCustomize }) {
  const { count, min, max, minutes } = sessionFromPrescription(data);
  const prescription = data?.prescription || {};
  const items = data?.decay?.items || [];
  const levels = data?.decay?.levels || [];
  const suggested = data?.decay?.summary?.suggested_levels || [];
  const queue = items.filter((item) => !suggested.length || suggested.includes(item.level)).slice(0, count);
  const hero = queue[0] || items[0];
  const kanji = prescription.type_counts?.kanji || 0;
  const vocabulary = prescription.type_counts?.vocabulary || 0;
  const runway = data?.runway || {};
  const practice = data?.practice || {};
  const notebook = practice.notebook || [];
  const backlog = Number(runway.current_backlog ?? 0);
  const floor = Number(runway.healthy_floor || 0);
  const recovery = formatDay(runway.projected_recovery_date);
  const start = () => navigate("session", { min, max, count, types: "kanji,vocabulary", pool: "decay", go: 1 });

  useEffect(() => {
    function onKey(event) {
      if (event.key !== "Enter" || event.metaKey || event.ctrlKey || event.altKey) return;
      const tag = event.target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || tag === "BUTTON" || tag === "A") return;
      event.preventDefault();
      start();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <main className="dojo">
      <section className="dojo-stage">
        <div className="dojo-hero">
          <p className="kicker">{hero ? "Softest item right now" : "Nothing slipping"}</p>
          <div className="hero-glyph" lang="ja">{hero?.characters || "休"}</div>
          {hero ? (
            <p className="hero-hint">
              <span className="tag">Level {hero.level} · {typeLabel(hero.type)}</span>
              <span>{hero.accuracy}% accuracy over {hero.attempts} reviews<span className="wide-only"> · meaning hidden until you answer</span></span>
            </p>
          ) : <p className="hero-hint"><span>Every level is holding. A short warm-up still keeps it that way.</span></p>}
          <h1>{count} items worth fixing.</h1>
          <p className="hero-sub">
            {levelRange(min, max)} · {kanji} kanji, {vocabulary} vocabulary · about {minutes} minutes · typed recall
          </p>
          <div className="hero-actions">
            <button className="go-btn" onClick={start}>Start session <kbd>Enter</kbd></button>
            <a className="quiet-link" href="https://www.wanikani.com/subjects/review" target="_blank" rel="noreferrer">Then open WaniKani ↗</a>
          </div>
          {queue.length ? (
            <div className="queue-row" aria-label="Session items">
              {queue.map((item, index) => (
                <span key={item.subject_id} className={index === 0 ? "queue-tile now" : "queue-tile"} lang="ja" title={`Level ${item.level} · ${typeLabel(item.type)}`}>{item.characters}</span>
              ))}
            </div>
          ) : null}
        </div>

        <aside className="dojo-side">
          <div className="side-stat">
            <p className="kicker">Review queue</p>
            <strong>{backlog}<small>/ {floor || "—"} healthy</small></strong>
            {floor ? <span className="side-bar"><i style={{ width: `${Math.min(100, (floor / Math.max(backlog, 1)) * 100)}%` }} /></span> : null}
            <p>{runway.queue_label || "Queue snapshot"}{recovery ? ` · back to healthy ${recovery}` : ""}</p>
          </div>
          <div className="side-stat">
            <p className="kicker">This week</p>
            <strong>{practice.week_sessions || 0}<small>{Number(practice.week_sessions) === 1 ? "session" : "sessions"}</small></strong>
            <p>
              {practice.week_accuracy != null ? `${practice.week_accuracy}% accuracy · ` : ""}
              Best combo {practice.combo_best || 0}
            </p>
          </div>
          <div className="side-stat">
            <p className="kicker">Missed lately</p>
            {notebook.length ? (
              <>
                <div className="missed-row">{notebook.slice(0, 6).map((item) => <span key={item.subject_id} lang="ja" title={item.meaning}>{item.characters}</span>)}</div>
                <p>Goes into the next session automatically</p>
              </>
            ) : <p>No misses logged yet.</p>}
          </div>
          <button className="quiet-link side-customize" onClick={onCustomize}>Customize a session →</button>
        </aside>
      </section>

      <section className="dojo-heat">
        <div className="heat-head">
          <p className="kicker">Levels 1–60 · decay heat</p>
          <span>Tap a level to drill it · outlined = today’s focus</span>
        </div>
        <HeatStrip
          levels={levels}
          focusMin={min}
          focusMax={max}
          onPick={(level) => navigate("session", { min: level, max: level, count: 10, types: "kanji,vocabulary", pool: "decay", go: 1 })}
        />
        <div className="heat-legend">
          <span><i style={{ "--heat": 0.12 }} />Holding</span>
          <span><i style={{ "--heat": 0.55 }} />Slipping</span>
          <span><i style={{ "--heat": 0.95 }} />Needs you</span>
          <span><i className="off" />Not reached</span>
        </div>
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
    const handler = () => setView(viewFromPath(window.location.pathname));
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

  function navigate(next, params = null) {
    const path = next === "session" ? "/session" : "/";
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

  const backlog = data?.runway?.current_backlog;
  const recovery = formatDay(data?.runway?.projected_recovery_date);

  return (
    <div className={`app-shell ${focus ? "is-focus" : ""}`}>
      <header className="topbar">
        <button className="brand-mark" onClick={() => navigate("dojo")}><span className="seal" lang="ja">先</span><strong>Kani Sensei</strong></button>
        {!focus ? (
          <div className="topbar-meta">
            <span className={`sync-dot ${dataMode || ""}`}>{syncNote}</span>
            {backlog != null ? <span className="wide-only">Queue {backlog}{recovery ? ` → healthy ${recovery}` : ""}</span> : null}
            <button className="pill-btn" onClick={() => setCustomize(true)}>Customize <kbd className="wide-only">⌘K</kbd></button>
          </div>
        ) : null}
      </header>
      {dataMode === "cached" || dataMode === "stale" ? (
        <div className={`data-notice ${dataMode}`} role="status">
          <strong>{dataMode === "stale" ? "Cached snapshot" : "Cached data"}</strong><span>{syncNote}. Practice works; new WaniKani progress is paused.</span>
        </div>
      ) : null}
      {error ? <div className="error global-error">{error}</div> : null}
      {view === "dojo" ? <Dojo data={data} navigate={navigate} onCustomize={() => setCustomize(true)} /> : null}
      {view === "session" ? <TestView key={window.location.search} data={data} title="Practice session" blurb="One focused round. Finish clean, then decide whether to continue." onHome={() => navigate("dojo")} onFocus={setFocus} /> : null}
      {customize && !focus ? <Customize data={data} navigate={navigate} onClose={() => setCustomize(false)} /> : null}
    </div>
  );
}

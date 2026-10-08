import { useEffect, useState } from "react";
import { api } from "./api.js";
import InspectCard from "./InspectCard.jsx";

const GROUPS = [
  ["radical", "Radicals"],
  ["kanji", "Kanji"],
  ["vocabulary", "Vocabulary"],
];

const BUCKET_LABEL = {
  unchecked: "Unchecked",
  relearn: "Relearn",
  guru: "Guru",
  master: "Master",
  enlightened: "Enlightened",
  burned: "Burned",
};

export function Glyph({ item, className = "" }) {
  if (item?.characters) return <span className={className} lang="ja">{item.characters}</span>;
  if (item?.image_url) return <img className={`${className} glyph-img`} src={item.image_url} alt={item.meaning || "radical"} />;
  return <span className={className}>・</span>;
}

export function whenLabel(iso) {
  if (!iso) return null;
  const at = new Date(iso);
  const diff = at.getTime() - Date.now();
  if (diff <= 0) return "now";
  const hours = Math.floor(diff / 3600000);
  const minutes = Math.round((diff % 3600000) / 60000);
  if (hours < 24) return hours ? `in ${hours}h ${minutes}m` : `in ${minutes}m`;
  return at.toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });
}

function InspectDrawer({ subjectId, onClose }) {
  const [card, setCard] = useState(null);
  const [current, setCurrent] = useState(subjectId);
  useEffect(() => setCurrent(subjectId), [subjectId]);
  useEffect(() => {
    if (!current) return;
    setCard(null);
    // Drop the old WaniKani SRS label; the tile already shows course state.
    api.inspect(current).then((data) => setCard({ ...data, srs_name: null })).catch(() => setCard(null));
  }, [current]);
  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  if (!subjectId) return null;
  return (
    <div className="drawer-scrim" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="drawer-head">
          <div><p className="kicker">Item</p></div>
          <button className="drawer-close" onClick={onClose} aria-label="Close">Esc</button>
        </div>
        {card ? <InspectCard card={card} onOpenRelated={setCurrent} /> : <p className="muted">Loading…</p>}
      </aside>
    </div>
  );
}

export function LevelIndex({ go }) {
  const [levels, setLevels] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api.levels().then((data) => setLevels(data.levels)).catch((err) => setError(err.message));
  }, []);
  return (
    <section className="panel">
      <div className="section-head">
        <h2>Levels</h2>
        <p>Every item, level by level. Open one to see it all, or restart it as a course.</p>
      </div>
      {error ? <div className="error">{error}</div> : null}
      {!levels ? <p className="muted">Loading…</p> : (
        <div className="level-grid">
          {levels.map((level) => (
            <button key={level.level} className={`level-card${level.passed ? " passed" : ""}`} onClick={() => go(`/level/${level.level}`)}>
              <span className="level-num">{level.level}</span>
              <span className="level-counts">
                <i className="t-radical">{level.radicals}</i>
                <i className="t-kanji">{level.kanji}</i>
                <i className="t-vocabulary">{level.vocabulary}</i>
              </span>
              <span className="level-status">
                {level.passed ? "Passed" : level.started
                  ? `${level.known}/${level.total} back${level.reviews ? ` · ${level.reviews} due` : level.relearn ? ` · ${level.relearn} relearn` : level.check ? ` · ${level.check} to check` : ""}`
                  : "Not started"}
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

const MODE_BUTTONS = [
  ["check", "Check"],
  ["relearn", "Relearn"],
  ["reviews", "Reviews"],
  ["ahead", "Study ahead"],
];

function CourseBox({ level, course, onStart, busy, go }) {
  if (!course.started) {
    return (
      <div className="course-box">
        <div>
          <p className="kicker">Comeback course</p>
          <h3>Start level {level} from where your memory is.</h3>
          <p className="muted">
            First a quick check of every item. What you still know goes straight to Guru; what slipped goes to Relearn,
            which you can grind any time. Only the long gaps run on real time. Pass at 90% of kanji on Guru.
          </p>
        </div>
        <button className="go-btn" onClick={onStart} disabled={busy}>{busy ? "Setting up…" : `Start level ${level}`}</button>
      </div>
    );
  }
  const pct = course.total ? Math.min(100, (course.known / course.total) * 100) : 0;
  const next = whenLabel(course.next_review_at);
  return (
    <div className="course-box">
      <div className="course-progress">
        <p className="kicker">{course.passed_at ? "Level passed" : "Comeback progress"}</p>
        <strong>{course.known}<small>/ {course.total} items back on Guru+</small></strong>
        <span className="side-bar"><i style={{ width: `${pct}%` }} /></span>
        <p className="muted">
          {course.kanji_guru}/{course.kanji_needed} kanji to pass
          {next ? ` · next real-time review ${next}` : ""}
        </p>
      </div>
      <div className="course-actions">
        <button className="go-btn wide-btn" disabled={!course.next_mode} onClick={() => go(`/level/${level}/${course.next_mode}`)}>
          {course.next_mode ? `Continue · ${MODE_BUTTONS.find(([id]) => id === course.next_mode)[1]}` : "All caught up"}
        </button>
        <div className="mode-row">
          {MODE_BUTTONS.map(([id, label]) => (
            <button key={id} className="mode-btn" disabled={!course[id]} onClick={() => go(`/level/${level}/${id}`)}>
              <span>{label}</span><b>{course[id] || 0}</b>
            </button>
          ))}
        </div>
        <button className="quiet-link" onClick={onStart} disabled={busy}>Restart this level</button>
      </div>
    </div>
  );
}

export function LevelPage({ level, go }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(null);

  function load() {
    setError("");
    api.courseLevel(level).then(setData).catch((err) => setError(err.message));
  }
  useEffect(load, [level]);

  async function start() {
    if (data?.course?.started && !window.confirm(`Restart level ${level}? All course progress on this level goes back to zero.`)) return;
    setBusy(true);
    try {
      setData(await api.startCourse(level));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="section-head level-head">
        <div>
          <button className="quiet-link" onClick={() => go("/levels")}>← All levels</button>
          <h2>Level {level}</h2>
        </div>
        <div className="level-nav">
          {level > 1 ? <button className="ghost-btn" onClick={() => go(`/level/${level - 1}`)}>← {level - 1}</button> : null}
          <button className="ghost-btn" onClick={() => go(`/session?min=${level}&max=${level}&count=10&types=radical,kanji,vocabulary&pool=decay&go=1`)}>Quick drill</button>
          {level < 60 ? <button className="ghost-btn" onClick={() => go(`/level/${level + 1}`)}>{level + 1} →</button> : null}
        </div>
      </div>
      {error ? <div className="error">{error}</div> : null}
      {!data ? <p className="muted">Loading…</p> : (
        <>
          <CourseBox level={level} course={data.course} onStart={start} busy={busy} go={go} />
          {GROUPS.map(([type, label]) => {
            const items = data.groups[type] || [];
            if (!items.length) return null;
            return (
              <div key={type} className="item-group">
                <h3 className={`group-title t-${type}`}>{label} <span>{items.length}</span></h3>
                <div className={`item-grid ${type}`}>
                  {items.map((item) => (
                    <button
                      key={item.subject_id}
                      className={`item-tile t-${type}${item.bucket ? ` b-${item.bucket}` : ""}`}
                      onClick={() => setOpen(item.subject_id)}
                      title={item.in_course ? item.stage_name || BUCKET_LABEL[item.bucket] : "Not in a course"}
                    >
                      <Glyph item={item} className="tile-glyph" />
                      <span className="tile-text">
                        {item.reading ? <span className="tile-reading" lang="ja">{item.reading}</span> : null}
                        <span className="tile-meaning">{item.meaning}</span>
                      </span>
                      {item.in_course ? <span className="tile-stage">{BUCKET_LABEL[item.bucket]}</span> : null}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </>
      )}
      <InspectDrawer subjectId={open} onClose={() => setOpen(null)} />
    </section>
  );
}

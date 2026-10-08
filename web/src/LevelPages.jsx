import { useEffect, useState } from "react";
import { api } from "./api.js";
import InspectCard from "./InspectCard.jsx";

const GROUPS = [
  ["radical", "Radicals"],
  ["kanji", "Kanji"],
  ["vocabulary", "Vocabulary"],
];

const BUCKET_LABEL = {
  locked: "Locked",
  lesson: "In lessons",
  apprentice: "Apprentice",
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
    api.inspect(current).then(setCard).catch(() => setCard(null));
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
                  ? `${level.kanji_guru}/${level.kanji_needed} kanji · ${level.reviews ? `${level.reviews} due` : `${level.lessons} lessons`}`
                  : "Not started"}
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function CourseBox({ level, course, onStart, busy, go }) {
  if (!course.started) {
    return (
      <div className="course-box">
        <div>
          <p className="kicker">Course</p>
          <h3>Restart level {level} from zero.</h3>
          <p className="muted">
            Radicals first. Kanji unlock when their radicals reach Guru, vocabulary when its kanji do.
            Lessons in fives, reviews on WaniKani timing. Pass at 90% of kanji on Guru.
          </p>
        </div>
        <button className="go-btn" onClick={onStart} disabled={busy}>{busy ? "Setting up…" : `Start level ${level}`}</button>
      </div>
    );
  }
  const pct = course.kanji_needed ? Math.min(100, (course.kanji_guru / course.kanji_needed) * 100) : 0;
  const next = whenLabel(course.next_review_at);
  return (
    <div className="course-box">
      <div className="course-progress">
        <p className="kicker">{course.passed_at ? "Level passed" : "Course progress"}</p>
        <strong>{course.kanji_guru}<small>/ {course.kanji_needed} kanji on Guru to pass</small></strong>
        <span className="side-bar"><i style={{ width: `${pct}%` }} /></span>
        <p className="muted">
          {Object.entries(course.buckets || {})
            .filter(([, n]) => n)
            .map(([bucket, n]) => `${n} ${BUCKET_LABEL[bucket]?.toLowerCase() || bucket}`)
            .join(" · ")}
        </p>
      </div>
      <div className="course-actions">
        <button className="go-btn" disabled={!course.lessons} onClick={() => go(`/level/${level}/lessons`)}>
          Lessons <b className="count">{course.lessons}</b>
        </button>
        <button className="go-btn" disabled={!course.reviews} onClick={() => go(`/level/${level}/reviews`)}>
          Reviews <b className="count">{course.reviews}</b>
        </button>
        <p className="muted">
          {course.reviews ? "Reviews are waiting." : next ? `Next review ${next}.` : course.lessons ? "Do lessons to start the clock." : "Nothing scheduled."}
        </p>
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

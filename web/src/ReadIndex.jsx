import { useEffect, useState } from "react";
import { api } from "./api.js";

export function CatalogNote() {
  return (
    <div className="error">
      Readings need the full WaniKani catalog and its sentence index. Run the catalog sync once
      (<code>POST /api/sync?scope=catalog</code> with the <code>X-Cron-Secret</code> header), then reload.
    </div>
  );
}

export default function ReadIndex({ go }) {
  const [data, setData] = useState(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.readIndex()
      .then(setData)
      .catch((err) => {
        if (err.status === 409) setMissing(true);
        else setError(err.message || "Could not load readings");
      });
  }, []);

  async function paste(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api.readCustom({ text });
      go(`/read/p/${encodeURIComponent(result.id)}`);
    } catch (err) {
      setError(err.data?.error || err.message || "Could not open that text");
      setBusy(false);
    }
  }

  return (
    <section className="panel read">
      <div className="section-head">
        <h2>Read</h2>
        <p>WaniKani's own example sentences, arranged so every kanji and word in a level shows up.</p>
      </div>
      {missing ? <CatalogNote /> : null}
      {error ? <div className="error">{error}</div> : null}
      {!data && !missing ? <p className="muted">Loading…</p> : null}
      {data ? (
        <>
          <button type="button" className="today-read" onClick={() => go("/read/feed")}>
            <p className="kicker">Just right</p>
            <strong>One new word at a time</strong>
            <span>A sentence you can almost read</span>
          </button>

          <button type="button" className="today-read" onClick={() => go("/read/today")}>
            <p className="kicker">Today's read</p>
            <strong>{data.daily?.finished ? "✓ Read for today" : "Read today's words in context"}</strong>
            <span>{data.daily?.ready ? `${data.daily.sentences} sentences` : "Built from today's set"}</span>
          </button>

          <div className="read-stories">
            <h3>Stories</h3>
            <p className="muted">Three levels at a time, starting from 1–3. A written story stays inside the band. One more page brings in the words it missed.</p>
            <div className="read-story-grid" aria-label="Stories">
              {(data.stories || []).map((story) => {
                const done = story.pages > 0 && story.finished === story.pages;
                const known = story.known?.total ? `You know ${Math.round(story.known.ratio * 100)}%` : "";
                const progress = story.pages ? `${story.finished} of ${story.pages} pages` : "Not started";
                return (
                  <button
                    key={story.band}
                    type="button"
                    className={`read-story${story.written ? " written" : ""}${done ? " done" : ""}`}
                    onClick={() => go(`/read/story/${story.band}`)}
                  >
                    <b>Levels {story.band}–{story.top}</b>
                    <strong>{story.title}</strong>
                    <span>{progress}{known ? ` · ${known}` : ""}</span>
                    {story.written ? <em>Story</em> : null}
                  </button>
                );
              })}
            </div>
          </div>

          <form className="read-paste" onSubmit={paste}>
            <p className="kicker">Bring your own text</p>
            <h3>Paste something you want to read.</h3>
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              maxLength={2000}
              rows={4}
              placeholder="NHK Easy, a lyric, a line from a book…"
              aria-label="Japanese text to read"
            />
            <div className="read-paste-foot">
              <span className="muted">{text.trim().length} / 2000</span>
              <button className="go-btn" type="submit" disabled={busy || !text.trim()}>
                {busy ? "Opening…" : "Read this"}
              </button>
            </div>
          </form>

          <div className="read-levels" aria-label="Levels">
            {data.levels.map((level) => {
              const pct = Math.round((level.coverage || 0) * 100);
              const done = level.passages > 0 && level.finished === level.passages;
              return (
                <button
                  key={level.level}
                  type="button"
                  className={`read-level${level.preview ? " preview" : ""}${done ? " done" : ""}`}
                  onClick={() => go(`/read/level/${level.level}`)}
                  title={level.preview ? `Level ${level.level}, preview` : `Level ${level.level}`}
                >
                  <b>{level.level}</b>
                  <i style={{ width: `${pct}%` }} />
                  {done ? <em>✓</em> : null}
                </button>
              );
            })}
          </div>
          <p className="muted read-legend">Filled bars are how much of that level you've finished reading. Pale numbers are above your level — still readable, with furigana.</p>
        </>
      ) : null}
    </section>
  );
}

import { useEffect, useState } from "react";
import { api } from "./api.js";
import { CatalogNote } from "./ReadIndex.jsx";

export default function ReadLevel({ level, go }) {
  const [data, setData] = useState(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    setMissing(false);
    setError("");
    api.readLevel(level)
      .then(setData)
      .catch((err) => {
        if (err.status === 409) setMissing(true);
        else setError(err.message || "Could not load this level");
      });
  }, [level]);

  const coverage = data?.coverage;
  const pct = coverage?.total ? Math.round((coverage.ratio || 0) * 100) : 0;
  const uncovered = data?.uncovered || [];

  return (
    <section className="panel read">
      <div className="section-head level-head">
        <div>
          <button type="button" className="quiet-link" onClick={() => go("/read")}>← All readings</button>
          <h2>Level {level}</h2>
        </div>
        <div className="level-nav">
          {level > 1 ? <button type="button" className="ghost-btn" onClick={() => go(`/read/level/${level - 1}`)}>← {level - 1}</button> : null}
          <button type="button" className="ghost-btn" onClick={() => go(`/level/${level}`)}>Level page</button>
          {level < 60 ? <button type="button" className="ghost-btn" onClick={() => go(`/read/level/${level + 1}`)}>{level + 1} →</button> : null}
        </div>
      </div>
      {missing ? <CatalogNote /> : null}
      {error ? <div className="error">{error}</div> : null}
      {!data && !missing ? <p className="muted">Gathering sentences…</p> : null}
      {data ? (
        <>
          {data.preview ? <p className="tag">Preview · above your level, furigana stays on</p> : null}
          <div className="read-coverage">
            <strong>{pct}%</strong>
            <span className="muted">{coverage.covered} of {coverage.total} items read</span>
            <span className="side-bar"><i style={{ width: `${pct}%` }} /></span>
          </div>
          {uncovered.length ? (
            <p className="muted">
              No example sentence uses {uncovered.slice(0, 10).map((item) => item.characters).filter(Boolean).join("、")}
              {uncovered.length > 10 ? "…" : ""}.
            </p>
          ) : null}
          {data.passages.length ? (
            <div className="read-passages">
              {data.passages.map((passage) => (
                <button
                  key={passage.id}
                  type="button"
                  className={`read-passage${passage.finished ? " done" : ""}`}
                  onClick={() => go(`/read/p/${encodeURIComponent(passage.id)}`)}
                >
                  <strong>{passage.title}</strong>
                  <span>
                    {passage.sentences} sentences
                    {passage.known?.total ? ` · You know ${Math.round(passage.known.ratio * 100)}% of the words` : ""}
                    {passage.finished ? " · read" : passage.opened ? " · started" : ""}
                  </span>
                  {passage.finished ? <em>✓</em> : null}
                </button>
              ))}
            </div>
          ) : (
            <p className="muted">This level has items, but none of them came with an example sentence.</p>
          )}
        </>
      ) : null}
    </section>
  );
}

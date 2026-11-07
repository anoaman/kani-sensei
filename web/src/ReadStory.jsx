import { useEffect, useState } from "react";
import { api } from "./api.js";
import { CatalogNote } from "./ReadIndex.jsx";

export default function ReadStory({ band, go }) {
  const [data, setData] = useState(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    setMissing(false);
    setError("");
    api.readStory(band)
      .then(setData)
      .catch((err) => {
        if (err.status === 409) setMissing(true);
        else setError(err.message || "Could not load this story");
      });
  }, [band]);

  const known = data?.known;
  const knownPct = known?.total ? Math.round(known.ratio * 100) : null;

  return (
    <section className="panel read">
      <div className="section-head level-head">
        <div>
          <button type="button" className="quiet-link" onClick={() => go("/read")}>← All readings</button>
          <p className="kicker">{data ? `Levels ${data.band}–${data.top}` : "Story"}</p>
          <h2>{data?.title || "Story"}</h2>
        </div>
      </div>
      {missing ? <CatalogNote /> : null}
      {error ? <div className="error">{error}</div> : null}
      {!data && !missing ? <p className="muted">Opening the story…</p> : null}
      {data ? (
        <>
          <p className="tag">{data.written ? "Written story" : "Sentences from this band"}</p>
          {knownPct !== null ? (
            <p className="muted read-meta">You know {knownPct}% of the words</p>
          ) : null}
          {data.pages.length ? (
            <div className="read-passages">
              {data.pages.map((page) => (
                <button
                  key={page.id}
                  type="button"
                  className={`read-passage${page.finished ? " done" : ""}`}
                  onClick={() => go(`/read/p/${encodeURIComponent(page.id)}`)}
                >
                  <strong>{page.idx ? `Page ${page.idx}` : "Page"} · {page.title}</strong>
                  <span>
                    {page.sentences} sentences
                    {page.known?.total ? ` · You know ${Math.round(page.known.ratio * 100)}% of the words` : ""}
                    {page.finished ? " · read" : page.opened ? " · started" : ""}
                  </span>
                  {page.finished ? <em>✓</em> : null}
                </button>
              ))}
            </div>
          ) : (
            <p className="muted">This band has no sentences yet.</p>
          )}
        </>
      ) : null}
    </section>
  );
}

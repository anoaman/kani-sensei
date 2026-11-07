import { Fragment, useEffect, useState } from "react";
import { api } from "./api.js";
import { InspectDrawer } from "./InspectCard.jsx";
import { CatalogNote } from "./ReadIndex.jsx";

const FEED_KEY = "kani-feed";

function readPlace() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(FEED_KEY) || "null");
    if (saved && Number.isInteger(saved.offset) && saved.offset >= 0 && saved.day) {
      return saved;
    }
  } catch {
    /* private mode */
  }
  return { offset: 0, day: "" };
}

function savePlace(day, offset) {
  try {
    sessionStorage.setItem(FEED_KEY, JSON.stringify({ day, offset }));
  } catch {
    /* private mode */
  }
}

function FeedToken({ token, onOpen }) {
  const interactive = (token.kind === "word" || token.kind === "kanji") && token.subject_id;
  const pieces = token.ruby?.length ? token.ruby : [{ base: token.text, ruby: "" }];
  const showRuby = token.target && pieces.some((piece) => piece.ruby);
  const body = showRuby ? (
    <ruby>
      {pieces.map((piece, index) => (
        <Fragment key={index}>
          {piece.base}
          <rt>{piece.ruby || ""}</rt>
        </Fragment>
      ))}
    </ruby>
  ) : token.text;
  if (!interactive) {
    return <span className={token.kind === "punct" ? "read-punct" : "read-plain"}>{token.text}</span>;
  }
  return (
    <button
      type="button"
      className={token.target ? "read-token is-target" : "read-token"}
      onClick={() => onOpen(token.subject_id)}
    >
      {body}
    </button>
  );
}

export default function ReadFeed({ go }) {
  const [place, setPlace] = useState(readPlace);
  const [data, setData] = useState(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [inspect, setInspect] = useState(null);

  useEffect(() => {
    let cancel = false;
    setError("");
    api.readFeed(place.offset)
      .then((payload) => {
        if (cancel) return;
        if (place.day && payload.day !== place.day) {
          setPlace({ offset: 0, day: payload.day });
          return;
        }
        setData(payload);
        setPlace((current) => ({ offset: current.offset, day: payload.day }));
        savePlace(payload.day, place.offset);
      })
      .catch((err) => {
        if (cancel) return;
        if (err.status === 409) setMissing(true);
        else setError(err.message || "Could not load a sentence");
      });
    return () => {
      cancel = true;
    };
  }, [place.offset, place.day]);

  function advance() {
    const next = place.offset + 1;
    setData(null);
    setPlace((current) => ({ ...current, offset: next }));
    savePlace(place.day, next);
  }

  async function again() {
    if (!data?.unknown_id || busy) return;
    setBusy(true);
    setError("");
    try {
      await api.readFeedAgain(data.unknown_id);
      advance();
    } catch (err) {
      setError(err.data?.error || err.message || "Could not record that");
    } finally {
      setBusy(false);
    }
  }

  const sentence = data?.sentence;
  const shown = data && !data.empty ? place.offset + 1 : 0;

  return (
    <section className="panel read">
      <div className="section-head">
        <h2>Just right</h2>
        <p>One sentence where you know every word except one. The new word is underlined.</p>
      </div>
      <button type="button" className="ghost-btn" onClick={() => go("/read")}>All readings</button>
      {missing ? <CatalogNote /> : null}
      {error ? <div className="error">{error}</div> : null}
      {!data && !missing ? <p className="muted">Finding a sentence…</p> : null}
      {data?.empty ? (
        <div className="read-result">
          <p className="kicker">Just right</p>
          <strong>{data.total ? "That's the batch for today." : "No sentence is one word away yet."}</strong>
          <button type="button" className="go-btn" onClick={() => go("/read")}>Back to readings</button>
        </div>
      ) : null}
      {sentence ? (
        <article className="read-card">
          <p className="kicker">{data.total ? `${shown} of ${data.total}` : "Today"}</p>
          <p className="read-sentence" lang="ja">
            {(sentence.tokens || []).map((token, index) => (
              <FeedToken key={index} token={token} onOpen={setInspect} />
            ))}
          </p>
          {sentence.en ? <p className="read-en">{sentence.en}</p> : null}
          <div className="read-listen-actions">
            <button type="button" className="go-btn" onClick={advance} disabled={busy}>Got it</button>
            <button type="button" className="ghost-btn" onClick={again} disabled={busy}>Again</button>
          </div>
        </article>
      ) : null}
      {inspect ? <InspectDrawer subjectId={inspect} onClose={() => setInspect(null)} /> : null}
    </section>
  );
}

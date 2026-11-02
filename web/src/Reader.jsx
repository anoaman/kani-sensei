import { Fragment, useEffect, useRef, useState } from "react";
import { toHiragana, toKana } from "wanakana";
import { api } from "./api.js";
import { InspectDrawer } from "./InspectCard.jsx";
import { CatalogNote } from "./ReadIndex.jsx";

const FURI_KEY = "kani-furigana";

function readFurigana() {
  try {
    const value = localStorage.getItem(FURI_KEY);
    return value === "all" || value === "off" ? value : "auto";
  } catch {
    return "auto";
  }
}

function showRuby(token, mode) {
  const hasRuby = (token.ruby || []).some((piece) => piece.ruby);
  if (!hasRuby) return false;
  if (mode === "off") return false;
  if (mode === "all") return true;
  return token.status && token.status !== "known";
}

function readingMatches(text, accepted) {
  const got = toHiragana(toKana((text || "").trim().toLowerCase()));
  if (!got) return false;
  return (accepted || []).some((item) => toHiragana(item) === got);
}

function RubyToken({ token, furigana, open, onPick }) {
  const interactive = (token.kind === "word" || token.kind === "kanji") && token.subject_id;
  const rubyOn = showRuby(token, furigana);
  const className = [
    "read-token",
    token.target ? "is-target" : "",
    token.status === "above" ? "is-above" : "",
  ].filter(Boolean).join(" ");
  const pieces = token.ruby?.length ? token.ruby : [{ base: token.text, ruby: "" }];
  const body = rubyOn ? (
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
      className={className}
      aria-expanded={open}
      onClick={() => onPick(token)}
    >
      {body}
    </button>
  );
}

function Popover({ token, onInspect, onClose }) {
  function play() {
    if (!token.audio_url) return;
    const audio = new Audio(token.audio_url);
    audio.play().catch(() => {});
  }
  return (
    <div className="read-pop" role="dialog" aria-label={token.meaning || "Word"}>
      <strong lang="ja">{token.reading || "—"}</strong>
      <span>{token.meaning || "No meaning cached"}</span>
      <span className="meta">
        {token.level ? `Level ${token.level}` : "Unknown"}
        {token.status ? ` · ${token.status}` : ""}
      </span>
      {token.audio_url ? <button type="button" className="ghost-btn" onClick={play}>Play</button> : null}
      <button type="button" className="ghost-btn" onClick={() => onInspect(token.subject_id)}>Open card</button>
      <button type="button" className="drawer-close" onClick={onClose} aria-label="Close">Esc</button>
    </div>
  );
}

function Check({ questions, onFinish }) {
  const [index, setIndex] = useState(0);
  const [choice, setChoice] = useState(null);
  const [typed, setTyped] = useState("");
  const [verdict, setVerdict] = useState(null);
  const [score, setScore] = useState(0);
  const question = questions[index];

  if (!questions.length) {
    return <button type="button" className="go-btn" onClick={() => onFinish(0, 0)}>Finish</button>;
  }
  if (!question) {
    return (
      <div className="read-result">
        <p className="kicker">Check</p>
        <strong>{score} / {questions.length}</strong>
        <button type="button" className="go-btn" onClick={() => onFinish(score, questions.length)}>Finish reading</button>
      </div>
    );
  }

  function gradeChoice(picked) {
    if (verdict) return;
    const ok = picked === question.answer;
    setChoice(picked);
    setVerdict(ok ? "pass" : "miss");
    if (ok) setScore((current) => current + 1);
  }

  function gradeReading(event) {
    event.preventDefault();
    if (verdict) return;
    const ok = readingMatches(typed, question.accepted);
    setVerdict(ok ? "pass" : "miss");
    if (ok) setScore((current) => current + 1);
  }

  function next() {
    setIndex((current) => current + 1);
    setChoice(null);
    setTyped("");
    setVerdict(null);
  }

  return (
    <div className="read-check">
      <p className="kicker">Check · {index + 1} / {questions.length}</p>
      {question.type === "translation" ? <p className="read-prompt" lang="ja">{question.prompt}</p> : null}
      {question.type === "meaning" ? (
        <p className="read-prompt" lang="ja">{question.prompt}<span>What does it mean?</span></p>
      ) : null}
      {question.type === "reading" ? (
        <p className="read-prompt" lang="ja">{question.prompt}<span>{question.meaning}</span></p>
      ) : null}

      {question.choices ? (
        <div className="read-choices">
          {question.choices.map((option, optionIndex) => {
            let mark = "";
            if (verdict && optionIndex === question.answer) mark = " right";
            else if (verdict && optionIndex === choice) mark = " wrong";
            return (
              <button
                key={option}
                type="button"
                className={`read-choice${mark}`}
                onClick={() => gradeChoice(optionIndex)}
                disabled={Boolean(verdict)}
              >
                {option}
              </button>
            );
          })}
        </div>
      ) : (
        <form className="read-type" onSubmit={gradeReading}>
          <input
            lang="ja"
            value={typed}
            onChange={(event) => setTyped(toKana(event.target.value.toLowerCase()))}
            placeholder="Reading"
            aria-label="Reading"
            autoCapitalize="off"
            autoCorrect="off"
            disabled={Boolean(verdict)}
          />
          {verdict ? null : <button className="go-btn" type="submit">Check</button>}
        </form>
      )}
      {verdict ? (
        <div className="read-verdict">
          <p>{verdict === "pass" ? "Yes." : "Not quite."}</p>
          {question.type === "reading" && verdict !== "pass" ? (
            <p lang="ja">{(question.accepted || []).join("、")}</p>
          ) : null}
          <button type="button" className="go-btn" onClick={next}>Next</button>
        </div>
      ) : null}
    </div>
  );
}

export default function Reader({ daily = false, passageId = "", go }) {
  const [data, setData] = useState(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState("");
  const [furigana, setFurigana] = useState(readFurigana);
  const [revealed, setRevealed] = useState({});
  const [revealAll, setRevealAll] = useState(false);
  const [pop, setPop] = useState(null);
  const [inspect, setInspect] = useState(null);
  const [checking, setChecking] = useState(false);
  const [finished, setFinished] = useState(null);
  const looked = useRef(new Set());

  useEffect(() => {
    setData(null);
    setMissing(false);
    setError("");
    setChecking(false);
    setFinished(null);
    setRevealed({});
    setRevealAll(false);
    setPop(null);
    const load = daily ? api.readDaily() : api.readPassage(passageId);
    load.then((payload) => {
      setData(payload);
      if (payload?.progress?.finished) setFinished({ already: true, coverage: payload.coverage });
    }).catch((err) => {
      if (err.status === 409) setMissing(true);
      else setError(err.message || "Could not open this reading");
    });
  }, [daily, passageId]);

  useEffect(() => {
    function onKey(event) {
      if (event.key === "Escape") setPop(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function chooseFurigana(mode) {
    setFurigana(mode);
    try {
      localStorage.setItem(FURI_KEY, mode);
    } catch {
      /* private mode */
    }
  }

  function pick(token, at) {
    setPop({ ...token, at });
    if (!token.subject_id || !data?.id || looked.current.has(token.subject_id)) return;
    looked.current.add(token.subject_id);
    api.readLookup({ passage_id: data.id, subject_id: token.subject_id }).catch(() => {});
  }

  async function finish(quizCorrect, quizTotal) {
    try {
      const result = await api.readFinish({
        passage_id: data.id,
        quiz_correct: quizCorrect,
        quiz_total: quizTotal,
        listen_correct: null,
        listen_total: null,
      });
      setFinished(result);
      setChecking(false);
    } catch (err) {
      setError(err.message || "Could not save");
    }
  }

  const kicker = data?.kind === "daily"
    ? "Today's read"
    : data?.kind === "custom"
      ? "Your text"
      : data?.level
        ? `Level ${data.level}`
        : "Reading";

  return (
    <section className="panel read">
      <div className="section-head level-head">
        <div>
          <button type="button" className="quiet-link" onClick={() => go(data?.level ? `/read/level/${data.level}` : "/read")}>← Readings</button>
          <p className="kicker">{kicker}</p>
          <h2>
            {data?.title || "Reading"}
            {data?.of ? <small> {data.idx} of {data.of}</small> : null}
          </h2>
        </div>
        <div className="segmented" role="group" aria-label="Furigana">
          {[["auto", "Auto"], ["all", "All"], ["off", "Off"]].map(([id, label]) => (
            <button key={id} type="button" className={furigana === id ? "active" : ""} onClick={() => chooseFurigana(id)}>{label}</button>
          ))}
        </div>
      </div>
      {missing ? <CatalogNote /> : null}
      {error ? <div className="error">{error}</div> : null}
      {!data && !missing ? <p className="muted">Opening…</p> : null}
      {data?.empty ? <p className="muted">Today's set has no words to read. Radicals don't come with sentences.</p> : null}
      {data && !data.empty ? (
        <>
          {data.coverage?.total ? (
            <p className="muted read-meta">{Math.round((data.coverage.ratio || 0) * 100)}% of level {data.level} read so far</p>
          ) : null}
          <div className="read-tools">
            <button type="button" className="quiet-link" onClick={() => setRevealAll(true)}>Reveal all English</button>
          </div>
          <div className="read-body">
            {(data.sentences || []).map((sentence, index) => {
              const englishOn = revealAll || revealed[index];
              return (
                <article key={index} className="read-card">
                  <p className="read-sentence" lang="ja">
                    {(sentence.tokens || []).map((token, tokenIndex) => (
                      <RubyToken
                        key={tokenIndex}
                        token={token}
                        furigana={furigana}
                        open={pop?.at === `${index}-${tokenIndex}`}
                        onPick={(item) => pick(item, `${index}-${tokenIndex}`)}
                      />
                    ))}
                  </p>
                  {pop?.at?.startsWith(`${index}-`) ? (
                    <Popover token={pop} onInspect={setInspect} onClose={() => setPop(null)} />
                  ) : null}
                  {sentence.en ? (
                    englishOn ? (
                      <p className="read-en">{sentence.en}</p>
                    ) : (
                      <button type="button" className="text-btn" onClick={() => setRevealed((current) => ({ ...current, [index]: true }))}>
                        Show English
                      </button>
                    )
                  ) : null}
                </article>
              );
            })}
          </div>

          {finished ? (
            <div className="read-result">
              <p className="kicker">{finished.already ? "Already finished" : "Done"}</p>
              <strong>{finished.already ? "You've read this one." : "Saved."}</strong>
              {data.next_id ? (
                <button type="button" className="go-btn" onClick={() => go(`/read/p/${encodeURIComponent(data.next_id)}`)}>Next reading</button>
              ) : (
                <button type="button" className="go-btn" onClick={() => go(data.level ? `/read/level/${data.level}` : "/read")}>Back to the list</button>
              )}
            </div>
          ) : checking ? (
            <Check questions={data.questions || []} onFinish={finish} />
          ) : (
            <button type="button" className="go-btn" onClick={() => setChecking(true)}>Check yourself</button>
          )}
        </>
      ) : null}
      <InspectDrawer subjectId={inspect} onClose={() => setInspect(null)} />
    </section>
  );
}

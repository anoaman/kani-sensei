import { Fragment, useEffect, useRef, useState } from "react";
import { toKana } from "wanakana";
import { readingVerdict } from "./answers.js";
import { api } from "./api.js";
import { InspectDrawer } from "./InspectCard.jsx";
import { CatalogNote } from "./ReadIndex.jsx";
import { hasJapaneseVoice, speak, stop } from "./speech.js";

const FURI_KEY = "kani-furigana";
const SIZE_KEY = "kani-text-size";
const VERTICAL_KEY = "kani-vertical";

function readChoice(key, allowed, fallback) {
  try {
    const value = localStorage.getItem(key);
    return allowed.includes(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

function storeChoice(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode */
  }
}

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

function englishOptions(sentence, sentences, questions) {
  const correct = (sentence.en || "").trim();
  if (!correct) return [];
  const seen = new Set([correct]);
  const options = [];
  const bag = [];
  for (const other of sentences || []) {
    if (other.en) bag.push(other.en.trim());
  }
  for (const question of questions || []) {
    if (question.type === "translation") bag.push(...(question.choices || []));
  }
  for (const item of bag) {
    if (!item || seen.has(item)) continue;
    seen.add(item);
    options.push(item);
    if (options.length === 3) break;
  }
  const choices = options.concat(correct);
  // Stable shuffle so the answer isn't always last, without jumping around on re-render.
  const shift = correct.length % choices.length;
  return choices.slice(shift).concat(choices.slice(0, shift));
}

function Diff({ ops }) {
  if (!ops?.length) return null;
  return (
    <p className="read-diff" lang="ja">
      {ops.map((op, index) => (
        <span key={index} className={`diff-${op.op}`}>{op.text}</span>
      ))}
    </p>
  );
}

function ListenRound({ data, furigana, pop, onPick, onInspect, onDone }) {
  const sentences = data.sentences || [];
  const [index, setIndex] = useState(0);
  const [typed, setTyped] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [correct, setCorrect] = useState(0);
  const [answered, setAnswered] = useState(0);
  const sentence = sentences[index];

  useEffect(() => () => stop(), []);

  if (!sentence) {
    return (
      <div className="read-result">
        <p className="kicker">Listening</p>
        <strong>{correct} / {answered}</strong>
        <button type="button" className="go-btn" onClick={() => onDone(correct, answered)}>Back to the text</button>
      </div>
    );
  }

  const listenable = Boolean(sentence.listenable && sentence.kana);
  const choices = listenable ? [] : englishOptions(sentence, sentences, data.questions);

  async function gradeTyped(event) {
    event.preventDefault();
    if (result || busy) return;
    setBusy(true);
    try {
      const graded = await api.readDictation({
        passage_id: data.id,
        index,
        text: toKana((typed || "").toLowerCase()),
      });
      setResult(graded);
      setAnswered((count) => count + 1);
      if (graded.verdict === "pass") setCorrect((count) => count + 1);
    } catch (err) {
      setResult({ verdict: "miss", error: err.message || "Could not grade" });
    } finally {
      setBusy(false);
    }
  }

  function gradeChoice(option) {
    if (result) return;
    const ok = option === (sentence.en || "").trim();
    setResult({ verdict: ok ? "pass" : "miss", mc: true, answer: sentence.en });
    setAnswered((count) => count + 1);
    if (ok) setCorrect((count) => count + 1);
  }

  function next() {
    stop();
    setIndex((current) => current + 1);
    setTyped("");
    setResult(null);
  }

  return (
    <div className="read-check">
      <p className="kicker">Listen · {index + 1} / {sentences.length}</p>
      <div className="read-listen-actions">
        <button type="button" className="go-btn" onClick={() => speak(sentence.ja, { rate: 1 })}>Play</button>
        <button type="button" className="ghost-btn" onClick={() => speak(sentence.ja, { rate: 0.75 })}>Slower</button>
      </div>
      {result ? (
        <article className="read-card">
          <p className="read-sentence" lang="ja">
            {(sentence.tokens || []).map((token, tokenIndex) => (
              <RubyToken
                key={tokenIndex}
                token={token}
                furigana={furigana}
                open={false}
                onPick={(item) => onPick(item, `listen-${index}-${tokenIndex}`)}
              />
            ))}
          </p>
          {pop?.at?.startsWith(`listen-${index}-`) ? (
            <Popover token={pop} onInspect={onInspect} onClose={() => onPick(null)} />
          ) : null}
          {sentence.en ? <p className="read-en">{sentence.en}</p> : null}
          {result.error ? <p className="error">{result.error}</p> : null}
          {result.ops ? <Diff ops={result.ops} /> : null}
          <p className="read-verdict">
            {result.verdict === "pass" ? "Yes." : result.verdict === "close" ? "Close." : "Not quite."}
            {result.expected ? <span lang="ja"> {result.expected}</span> : null}
          </p>
          <button type="button" className="go-btn" onClick={next}>{index + 1 === sentences.length ? "Finish listening" : "Next"}</button>
        </article>
      ) : listenable ? (
        <form className="read-type" onSubmit={gradeTyped}>
          <input
            lang="ja"
            value={typed}
            onChange={(event) => setTyped(toKana(event.target.value.toLowerCase()))}
            placeholder="Type what you heard"
            aria-label="What you heard"
            autoCapitalize="off"
            autoCorrect="off"
          />
          <button className="go-btn" type="submit" disabled={busy}>{busy ? "Checking…" : "Check"}</button>
        </form>
      ) : choices.length >= 2 ? (
        <div className="read-choices">
          <p className="muted">What did you hear?</p>
          {choices.map((option) => (
            <button key={option} type="button" className="read-choice" onClick={() => gradeChoice(option)}>{option}</button>
          ))}
        </div>
      ) : (
        <div>
          <p className="muted">This sentence has no reading to dictate.</p>
          <button type="button" className="ghost-btn" onClick={next}>Skip</button>
        </div>
      )}
    </div>
  );
}

function recallSlots(sentences) {
  const slots = [];
  (sentences || []).forEach((sentence, sentenceIndex) => {
    (sentence.tokens || []).forEach((token, tokenIndex) => {
      const accepted = token.readings?.length ? token.readings : (token.reading ? [token.reading] : []);
      if (token.target && accepted.length) {
        slots.push({ sentenceIndex, tokenIndex, token, accepted });
      }
    });
  });
  return slots;
}

function RecallRound({ data, furigana, onMiss, onScore }) {
  const slots = recallSlots(data.sentences);
  const [index, setIndex] = useState(0);
  const [typed, setTyped] = useState("");
  const [verdict, setVerdict] = useState(null);
  const [correct, setCorrect] = useState(0);
  const [nudged, setNudged] = useState(false);
  const [hint, setHint] = useState("");
  const slot = slots[index];

  if (!slots.length) {
    return (
      <div className="read-result">
        <p className="kicker">Recall</p>
        <strong>No target words in this reading.</strong>
        <button type="button" className="go-btn" onClick={() => onScore(0, 0, true)}>Back to the text</button>
      </div>
    );
  }

  if (!slot) {
    return (
      <div className="read-result">
        <p className="kicker">Recall</p>
        <strong>{correct} / {slots.length}</strong>
        <button type="button" className="go-btn" onClick={() => onScore(correct, slots.length, true)}>Back to the text</button>
      </div>
    );
  }

  function grade(event) {
    event.preventDefault();
    if (verdict) return;
    const result = readingVerdict(typed, slot.accepted);
    if (result === "close" && !nudged) {
      setNudged(true);
      setHint("Close. Check the kana.");
      return;
    }
    const ok = result === "pass";
    const nextCorrect = correct + (ok ? 1 : 0);
    setHint("");
    setVerdict(ok ? "pass" : "miss");
    setCorrect(nextCorrect);
    if (!ok) onMiss(slot.token.subject_id);
    onScore(nextCorrect, index + 1);
  }

  function next() {
    setIndex((current) => current + 1);
    setTyped("");
    setVerdict(null);
    setNudged(false);
    setHint("");
  }

  return (
    <div className="read-check">
      <p className="kicker">Recall · {index + 1} / {slots.length}</p>
      {(data.sentences || []).map((sentence, sentenceIndex) => (
        <article key={sentenceIndex} className="read-card">
          <p className="read-sentence" lang="ja">
            {(sentence.tokens || []).map((token, tokenIndex) => {
              const slotIndex = slots.findIndex(
                (item) => item.sentenceIndex === sentenceIndex && item.tokenIndex === tokenIndex,
              );
              const revealed = slotIndex > -1 && (slotIndex < index || (slotIndex === index && verdict));
              if (slotIndex > -1 && !revealed) {
                const current = slotIndex === index;
                return (
                  <span key={tokenIndex} className={current ? "read-blank is-current" : "read-blank"} aria-label="Blank">
                    ＿
                  </span>
                );
              }
              return (
                <RubyToken
                  key={tokenIndex}
                  token={token}
                  furigana={slotIndex === index && verdict === "miss" ? "all" : furigana}
                  open={false}
                  onPick={() => {}}
                />
              );
            })}
          </p>
        </article>
      ))}
      {verdict ? (
        <div className="read-verdict">
          <p>{verdict === "pass" ? "Yes." : "Not quite."}</p>
          {verdict === "miss" ? <p lang="ja">{slot.accepted.join("、")}</p> : null}
          <button type="button" className="go-btn" onClick={next}>{index + 1 === slots.length ? "Finish recall" : "Next"}</button>
        </div>
      ) : (
        <form className="read-type" onSubmit={grade}>
          <input
            lang="ja"
            value={typed}
            onChange={(event) => {
              setTyped(toKana(event.target.value.toLowerCase()));
              if (hint) setHint("");
            }}
            placeholder="Reading"
            aria-label="Reading of the blank"
            autoCapitalize="off"
            autoCorrect="off"
          />
          <button className="go-btn" type="submit">Check</button>
        </form>
      )}
      {hint && !verdict ? <p className="drill-hint">{hint}</p> : null}
    </div>
  );
}

function Check({ questions, onFinish }) {
  const [index, setIndex] = useState(0);
  const [choice, setChoice] = useState(null);
  const [typed, setTyped] = useState("");
  const [verdict, setVerdict] = useState(null);
  const [score, setScore] = useState(0);
  const [nudged, setNudged] = useState(false);
  const [hint, setHint] = useState("");
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
    const result = readingVerdict(typed, question.accepted);
    if (result === "close" && !nudged) {
      setNudged(true);
      setHint("Close. Check the kana.");
      return;
    }
    const ok = result === "pass";
    setHint("");
    setVerdict(ok ? "pass" : "miss");
    if (ok) setScore((current) => current + 1);
  }

  function next() {
    setIndex((current) => current + 1);
    setChoice(null);
    setTyped("");
    setVerdict(null);
    setNudged(false);
    setHint("");
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
            onChange={(event) => {
              setTyped(toKana(event.target.value.toLowerCase()));
              if (hint) setHint("");
            }}
            placeholder="Reading"
            aria-label="Reading"
            autoCapitalize="off"
            autoCorrect="off"
            disabled={Boolean(verdict)}
          />
          {verdict ? null : <button className="go-btn" type="submit">Check</button>}
        </form>
      )}
      {hint && !verdict ? <p className="drill-hint">{hint}</p> : null}
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
  const [textSize, setTextSize] = useState(() => readChoice(SIZE_KEY, ["s", "m", "l"], "m"));
  const [vertical, setVertical] = useState(() => readChoice(VERTICAL_KEY, ["on", "off"], "off") === "on");
  const [speaking, setSpeaking] = useState(null);
  const [revealed, setRevealed] = useState({});
  const [revealAll, setRevealAll] = useState(false);
  const [pop, setPop] = useState(null);
  const [inspect, setInspect] = useState(null);
  const [checking, setChecking] = useState(false);
  const [finished, setFinished] = useState(null);
  const [mode, setMode] = useState("read");
  const [voice, setVoice] = useState(false);
  const [listenScore, setListenScore] = useState({ correct: null, total: null });
  const [recallScore, setRecallScore] = useState({ correct: null, total: null });
  const looked = useRef(new Set());
  const playToken = useRef(0);

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
    function checkVoice() {
      setVoice(hasJapaneseVoice());
    }
    checkVoice();
    window.addEventListener("keydown", onKey);
    window.speechSynthesis?.addEventListener("voiceschanged", checkVoice);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.speechSynthesis?.removeEventListener("voiceschanged", checkVoice);
      playToken.current += 1;
      stop();
    };
  }, []);

  function haltSpeech() {
    playToken.current += 1;
    setSpeaking(null);
    stop();
  }

  async function playAll() {
    const sentences = data?.sentences || [];
    const token = playToken.current + 1;
    playToken.current = token;
    for (let index = 0; index < sentences.length; index += 1) {
      if (playToken.current !== token) return;
      setSpeaking(index);
      await speak(sentences[index].ja, { rate: 1 });
    }
    if (playToken.current === token) setSpeaking(null);
  }

  async function shadow(index) {
    const sentence = data?.sentences?.[index];
    if (!sentence) return;
    const token = playToken.current + 1;
    playToken.current = token;
    for (let time = 0; time < 3; time += 1) {
      if (playToken.current !== token) return;
      setSpeaking(index);
      await speak(sentence.ja, { rate: 0.75 });
    }
    if (playToken.current === token) setSpeaking(null);
  }

  function chooseFurigana(mode) {
    setFurigana(mode);
    try {
      storeChoice(FURI_KEY, mode);
    } catch {
      /* private mode */
    }
  }

  function missRecall(subjectId) {
    if (!subjectId || !data?.id || looked.current.has(subjectId)) return;
    looked.current.add(subjectId);
    api.readLookup({ passage_id: data.id, subject_id: subjectId }).catch(() => {});
  }

  function pick(token, at) {
    if (!token) {
      setPop(null);
      return;
    }
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
        listen_correct: listenScore.correct,
        listen_total: listenScore.total,
        recall_correct: recallScore.correct,
        recall_total: recallScore.total,
      });
      setFinished(result);
      setChecking(false);
    } catch (err) {
      setError(err.message || "Could not save");
    }
  }

  const story = data?.kind === "story";
  const listHref = story && data?.level
    ? `/read/story/${data.level}`
    : data?.level
      ? `/read/level/${data.level}`
      : "/read";
  const kicker = data?.kind === "daily"
    ? "Today's read"
    : data?.kind === "custom"
      ? "Your text"
      : story
        ? `Levels ${data.level}–${data.reference_level}`
        : data?.level
          ? `Level ${data.level}`
          : "Reading";

  return (
    <section className={`panel read size-${textSize}${vertical ? " is-vertical" : ""}`}>
      <div className="section-head level-head">
        <div>
          <button type="button" className="quiet-link" onClick={() => go(listHref)}>{story ? "← Story" : "← Readings"}</button>
          <p className="kicker">{kicker}</p>
          <h2>
            {data?.title || "Reading"}
            {story && data?.of ? <small> Page {data.idx} of {data.of}</small> : null}
            {!story && data?.of ? <small> {data.idx} of {data.of}</small> : null}
          </h2>
        </div>
        <div className="read-switches">
          <div className="segmented" role="group" aria-label="Mode">
            <button type="button" className={mode === "read" ? "active" : ""} onClick={() => { haltSpeech(); setMode("read"); }}>Read</button>
            <button type="button" className={mode === "listen" ? "active" : ""} disabled={!voice} onClick={() => { haltSpeech(); setMode("listen"); }}>Listen</button>
            <button type="button" className={mode === "recall" ? "active" : ""} onClick={() => { haltSpeech(); setMode("recall"); }}>Recall</button>
          </div>
          <div className="segmented" role="group" aria-label="Text size">
            {[["s", "S"], ["m", "M"], ["l", "L"]].map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={textSize === id ? "active" : ""}
                onClick={() => { setTextSize(id); storeChoice(SIZE_KEY, id); }}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="segmented" role="group" aria-label="Text direction">
            <button
              type="button"
              className={vertical ? "active" : ""}
              onClick={() => {
                const next = !vertical;
                setVertical(next);
                storeChoice(VERTICAL_KEY, next ? "on" : "off");
              }}
            >
              Vertical
            </button>
          </div>
          <div className="segmented" role="group" aria-label="Furigana">
            {[["auto", "Auto"], ["all", "All"], ["off", "Off"]].map(([id, label]) => (
              <button key={id} type="button" className={furigana === id ? "active" : ""} onClick={() => chooseFurigana(id)}>{label}</button>
            ))}
          </div>
        </div>
      </div>
      {voice ? null : (
        <p className="read-voice">Listening needs a Japanese voice. On iPhone: Settings → Accessibility → Spoken Content → Voices → Japanese.</p>
      )}
      {missing ? <CatalogNote /> : null}
      {error ? <div className="error">{error}</div> : null}
      {!data && !missing ? <p className="muted">Opening…</p> : null}
      {data?.empty ? <p className="muted">Today's set has no words to read. Radicals don't come with sentences.</p> : null}
      {data && !data.empty ? (
        <>
          {data.coverage?.total ? (
            <p className="muted read-meta">{Math.round((data.coverage.ratio || 0) * 100)}% of level {data.level} read so far</p>
          ) : null}
          {data.known?.total ? (
            <p className="muted read-meta">You know {Math.round(data.known.ratio * 100)}% of the words</p>
          ) : null}
          {mode === "listen" ? (
            <ListenRound
              key={data.id}
              data={data}
              furigana={furigana}
              pop={pop}
              onPick={pick}
              onInspect={setInspect}
              onDone={(correct, total) => {
                setListenScore({ correct, total });
                setMode("read");
              }}
            />
          ) : mode === "recall" ? (
            <RecallRound
              key={data.id}
              data={data}
              furigana={furigana}
              onMiss={missRecall}
              onScore={(correct, total, done) => {
                setRecallScore({ correct, total });
                if (done) setMode("read");
              }}
            />
          ) : (
          <>
          <div className="read-tools">
            <button type="button" className="quiet-link" onClick={() => setRevealAll(true)}>Reveal all English</button>
            {voice ? (
              <button type="button" className="quiet-link" onClick={playAll}>Play all</button>
            ) : null}
            {listenScore.total ? <span className="muted">Listening {listenScore.correct}/{listenScore.total}</span> : null}
            {recallScore.total ? <span className="muted">Recall {recallScore.correct}/{recallScore.total}</span> : null}
          </div>
          <div className="read-body">
            {(data.sentences || []).map((sentence, index) => {
              const englishOn = revealAll || revealed[index];
              return (
                <article key={index} className={speaking === index ? "read-card is-speaking" : "read-card"}>
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
                  {voice ? (
                    <div className="read-listen-actions">
                      <button type="button" className="ghost-btn read-play" onClick={() => { haltSpeech(); speak(sentence.ja); }}>Play</button>
                      <button type="button" className="ghost-btn" onClick={() => shadow(index)}>Shadow</button>
                    </div>
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
                <button type="button" className="go-btn" onClick={() => go(`/read/p/${encodeURIComponent(data.next_id)}`)}>{story ? "Next page" : "Next reading"}</button>
              ) : (
                <button type="button" className="go-btn" onClick={() => go(listHref)}>{story ? "Back to the story" : "Back to the list"}</button>
              )}
            </div>
          ) : checking ? (
            <Check questions={data.questions || []} onFinish={finish} />
          ) : (
            <button type="button" className="go-btn" onClick={() => setChecking(true)}>Check yourself</button>
          )}
          </>
          )}
        </>
      ) : null}
      <InspectDrawer subjectId={inspect} onClose={() => setInspect(null)} />
    </section>
  );
}

// WaniKani mnemonics mark terms with <radical>, <kanji>, <vocabulary>, <reading>, <ja>.
export function Mnemonic({ text }) {
  if (!text) return null;
  const parts = [];
  const re = /<(radical|kanji|vocabulary|reading|ja|meaning)>(.*?)<\/\1>/gs;
  let last = 0;
  let match;
  while ((match = re.exec(text))) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    parts.push(
      <mark key={match.index} className={`mn-${match[1]}`}>
        {match[2].replace(/<[^>]+>/g, "")}
      </mark>,
    );
    last = re.lastIndex;
  }
  if (last < text.length) parts.push(text.slice(last));
  return (
    <p className="mnemonic">
      {parts.map((part) => (typeof part === "string" ? part.replace(/<[^>]+>/g, "") : part))}
    </p>
  );
}

function typeOf(item) {
  const type = item?.type || item?.object_type;
  return type === "kana_vocabulary" ? "vocabulary" : type;
}

// The hint for the half that was just missed: its mnemonic, then the look-alikes.
export function MissHint({ card, promptType }) {
  if (!card) return null;
  const mnemonic = promptType === "reading" ? card.mnemonic?.reading : card.mnemonic?.meaning;
  const similar = card.similar || [];
  if (!mnemonic && !similar.length) return null;
  return (
    <div className="miss-hint">
      {mnemonic ? <Mnemonic text={mnemonic} /> : null}
      {similar.length ? (
        <div className="lesson-parts">
          <p className="kicker">Looks like</p>
          <div className="glyph-row">
            {similar.map((part) => (
              <span key={part.subject_id} className={`glyph-chip t-${typeOf(part)}`}>
                <span className="glyph" lang="ja">{part.characters || "・"}</span>
                <span className="meta">{part.meaning}</span>
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

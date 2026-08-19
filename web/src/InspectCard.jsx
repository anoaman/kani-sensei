import { useRef, useState } from "react";
import { ReadingTerm, SrsTerm, T } from "./Term.jsx";

function GlyphChip({ item, onOpen }) {
  if (!item) return null;
  const body = (
    <>
      <span className="glyph">{item.characters || "・"}</span>
      <span className="meta">{item.meaning || item.type}</span>
    </>
  );
  if (!onOpen || !item.subject_id) {
    return <div className="glyph-chip">{body}</div>;
  }
  return (
    <button type="button" className="glyph-chip" onClick={() => onOpen(item.subject_id)}>
      {body}
    </button>
  );
}

export default function InspectCard({ card, onOpenRelated }) {
  const [showMnemonic, setShowMnemonic] = useState(false);
  const [showEnglish, setShowEnglish] = useState(false);
  const audioRef = useRef(null);
  if (!card) return null;

  const readings = card.readings || [];
  const sentence = card.sentence;

  function play() {
    if (!card.audio_url) return;
    if (!audioRef.current) {
      audioRef.current = new Audio(card.audio_url);
    }
    audioRef.current.currentTime = 0;
    audioRef.current.play().catch(() => {});
  }

  return (
    <div className="inspect-card">
      <div className="inspect-head">
        <div>
          <div className="inspect-kana">
            {readings.length
              ? readings.map((item) => (
                  <span key={`${item.reading}-${item.type}`}>
                    {item.reading}
                    {item.type && item.type !== "reading" ? (
                      <span className="meta">
                        {" "}
                        <ReadingTerm type={item.type} />
                      </span>
                    ) : null}
                  </span>
                ))
              : card.meaning}
          </div>
          <div className="muted">
            {card.srs_name ? (
              <>
                <T k="srs">SRS</T> <SrsTerm name={card.srs_name} />
              </>
            ) : null}
            {card.parts_of_speech?.length ? ` · ${card.parts_of_speech.join(", ")}` : ""}
          </div>
        </div>
        <div className="inspect-actions">
          {card.audio_url ? (
            <button type="button" className="ghost-btn" onClick={play}>
              Play
            </button>
          ) : null}
          {card.wk_url ? (
            <a className="ghost-btn" href={card.wk_url} target="_blank" rel="noreferrer">
              <T k="wanikani" hoverOnly>WaniKani</T>
            </a>
          ) : null}
        </div>
      </div>

      {card.components?.length ? (
        <div>
          <span className="chip-label">Built from</span>
          <div className="glyph-row">
            {card.components.map((item) => (
              <GlyphChip key={item.subject_id} item={item} onOpen={onOpenRelated} />
            ))}
          </div>
        </div>
      ) : null}

      {card.similar?.length ? (
        <div>
          <span className="chip-label">Looks like</span>
          <div className="glyph-row">
            {card.similar.map((item) => (
              <GlyphChip key={item.subject_id} item={item} onOpen={onOpenRelated} />
            ))}
          </div>
        </div>
      ) : null}

      {card.used_in?.length ? (
        <div>
          <span className="chip-label">Used in</span>
          <div className="glyph-row">
            {card.used_in.map((item) => (
              <GlyphChip key={item.subject_id} item={item} onOpen={onOpenRelated} />
            ))}
          </div>
        </div>
      ) : null}

      {sentence ? (
        <div className="sentence">
          <div className="sentence-ja">{sentence.ja}</div>
          {sentence.en ? (
            showEnglish ? (
              <div className="muted">{sentence.en}</div>
            ) : (
              <button type="button" className="text-btn" onClick={() => setShowEnglish(true)}>
                Show English
              </button>
            )
          ) : null}
        </div>
      ) : null}

      {(card.mnemonic?.meaning || card.mnemonic?.reading) ? (
        <div>
          <button type="button" className="text-btn" onClick={() => setShowMnemonic((v) => !v)}>
            {showMnemonic ? (
              <>
                Hide <T k="mnemonic" hoverOnly>mnemonic</T>
              </>
            ) : (
              <>
                Show <T k="mnemonic" hoverOnly>mnemonic</T>
              </>
            )}
          </button>
          {showMnemonic ? (
            <div className="mnemonic">
              {card.mnemonic.meaning ? <p>{card.mnemonic.meaning.replace(/<[^>]+>/g, "")}</p> : null}
              {card.mnemonic.reading ? <p>{card.mnemonic.reading.replace(/<[^>]+>/g, "")}</p> : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

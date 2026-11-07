import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

export default function SearchBox({ onOpen }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const inputRef = useRef(null);

  useEffect(() => {
    function onKey(event) {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      const tag = document.activeElement?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || document.activeElement?.isContentEditable) return;
      event.preventDefault();
      setOpen(true);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    const text = query.trim();
    if (!text) {
      setResults([]);
      return undefined;
    }
    let cancel = false;
    const handle = window.setTimeout(() => {
      api.readSearch(text)
        .then((payload) => {
          if (!cancel) setResults(payload.results || []);
        })
        .catch(() => {
          if (!cancel) setResults([]);
        });
    }, 150);
    return () => {
      cancel = true;
      window.clearTimeout(handle);
    };
  }, [query]);

  function close() {
    setOpen(false);
    setQuery("");
    setResults([]);
  }

  function choose(id) {
    close();
    onOpen(id);
  }

  if (!open) {
    return (
      <button type="button" className="pill-btn" onClick={() => setOpen(true)}>
        Look up <kbd>/</kbd>
      </button>
    );
  }

  return (
    <div className="lookup">
      <input
        ref={inputRef}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") close();
          if (event.key === "Enter" && results[0]) choose(results[0].id);
        }}
        placeholder="Kanji, reading, or meaning"
        aria-label="Look up"
        autoCapitalize="off"
        autoCorrect="off"
      />
      {query.trim() ? (
        <div className="lookup-results" role="listbox">
          {results.length ? results.map((item) => (
            <button key={item.id} type="button" onClick={() => choose(item.id)}>
              <b lang="ja">{item.characters}</b>
              <span>{item.reading}</span>
              <em>{item.meaning}</em>
            </button>
          )) : <p className="muted">Nothing in the catalog.</p>}
        </div>
      ) : null}
    </div>
  );
}

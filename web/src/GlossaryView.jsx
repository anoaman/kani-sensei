import { useMemo, useState } from "react";
import { GLOSSARY_LIST } from "./glossary.js";
import { T } from "./Term.jsx";

export default function GlossaryView() {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return GLOSSARY_LIST;
    return GLOSSARY_LIST.filter((entry) => {
      const blob = `${entry.term} ${entry.short} ${entry.long} ${(entry.aliases || []).join(" ")}`.toLowerCase();
      return blob.includes(needle);
    });
  }, [query]);

  const groups = useMemo(() => {
    const map = new Map();
    for (const entry of filtered) {
      const list = map.get(entry.group) || [];
      list.push(entry);
      map.set(entry.group, list);
    }
    return [...map.entries()];
  }, [filtered]);

  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <h2>Glossary</h2>
          <p>
            Dotted words anywhere in the app open a short tooltip. This page is
            the full list — WaniKani jargon plus the Kani Sensei names for the
            same ideas.
          </p>
        </div>
      </div>
      <div className="surface">
        <div className="field" style={{ maxWidth: "20rem" }}>
          <label htmlFor="glossary-search">Search</label>
          <input
            id="glossary-search"
            value={query}
            placeholder="leech, burned, runway…"
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        {groups.map(([group, entries]) => (
          <div key={group} className="glossary-group">
            <h3>{group}</h3>
            <dl>
              {entries.map((entry) => (
                <div key={entry.id} className="glossary-item">
                  <dt>
                    <T k={entry.id}>{entry.term}</T>
                  </dt>
                  <dd>
                    <p>{entry.short}</p>
                    <p className="note">{entry.long}</p>
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
        {!filtered.length ? <p className="empty">No matches.</p> : null}
      </div>
    </section>
  );
}

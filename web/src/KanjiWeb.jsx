import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api } from "./api.js";
import { InspectDrawer } from "./InspectCard.jsx";
import { CatalogNote } from "./ReadIndex.jsx";

const LANE_LABEL = { radical: "Radicals", kanji: "Kanji", vocabulary: "Words" };

function useNarrow() {
  const [narrow, setNarrow] = useState(() => window.matchMedia("(max-width: 720px)").matches);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 720px)");
    const onChange = () => setNarrow(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return narrow;
}

function relatedIds(id, edges, showSimilar) {
  const up = {};
  const down = {};
  const similar = {};
  for (const edge of edges) {
    if (edge.kind === "similar") {
      (similar[edge.from] ||= []).push(edge.to);
      (similar[edge.to] ||= []).push(edge.from);
      continue;
    }
    (up[edge.from] ||= []).push(edge.to);
    (down[edge.to] ||= []).push(edge.from);
  }
  const keep = new Set([id]);
  function walk(map) {
    const stack = [...(map[id] || [])];
    while (stack.length) {
      const current = stack.pop();
      if (keep.has(current)) continue;
      keep.add(current);
      stack.push(...(map[current] || []));
    }
  }
  walk(up);
  walk(down);
  if (showSimilar) {
    for (const other of similar[id] || []) keep.add(other);
  }
  return keep;
}

function FocusList({ lanes, edges, onOpen }) {
  const kanji = lanes.kanji || [];
  const [id, setId] = useState(kanji[0]?.id || null);
  const byId = useMemo(() => {
    const map = {};
    for (const lane of Object.values(lanes)) {
      for (const node of lane) map[node.id] = node;
    }
    return map;
  }, [lanes]);
  const parts = edges.filter((edge) => edge.kind === "component" && edge.from === id).map((edge) => byId[edge.to]).filter(Boolean);
  const words = edges.filter((edge) => edge.kind === "component" && edge.to === id).map((edge) => byId[edge.from]).filter(Boolean);

  function choose(node) {
    if (id === node.id) onOpen(node.id);
    else setId(node.id);
  }

  return (
    <div className="web-focus">
      <div className="web-focus-row" aria-label="Kanji">
        {kanji.map((node) => (
          <button
            key={node.id}
            type="button"
            className={`web-node t-${node.type}${node.id === id ? " active" : ""}${node.weak ? " is-weak" : ""} b-${node.bucket || "fresh"}`}
            onClick={() => choose(node)}
          >
            <b lang="ja">{node.label}</b>
          </button>
        ))}
      </div>
      <div className="web-focus-detail">
        <p className="kicker">Built from</p>
        <div className="web-focus-row">
          {parts.length ? parts.map((node) => (
            <button key={node.id} type="button" className={`web-node t-${node.type}${node.weak ? " is-weak" : ""}`} onClick={() => onOpen(node.id)}>
              <b lang="ja">{node.label}</b>
              <small>{node.meaning}</small>
            </button>
          )) : <span className="muted">Nothing cached below this kanji.</span>}
        </div>
        <p className="kicker">Used in</p>
        <div className="web-focus-row">
          {words.length ? words.map((node) => (
            <button key={node.id} type="button" className={`web-node t-${node.type}${node.weak ? " is-weak" : ""}`} onClick={() => onOpen(node.id)}>
              <b lang="ja">{node.label}</b>
              <small>{node.meaning}</small>
            </button>
          )) : <span className="muted">No words on this level use it.</span>}
        </div>
      </div>
    </div>
  );
}

function Lanes({ data, showSimilar, focus, onFocus, onOpen }) {
  const wrapRef = useRef(null);
  const nodeRefs = useRef({});
  const [lines, setLines] = useState([]);
  const edges = useMemo(
    () => (data.edges || []).filter((edge) => showSimilar || edge.kind !== "similar"),
    [data, showSimilar],
  );
  const keep = useMemo(
    () => (focus ? relatedIds(focus, data.edges || [], showSimilar) : null),
    [data, focus, showSimilar],
  );

  useLayoutEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return undefined;
    function layout() {
      const box = wrap.getBoundingClientRect();
      const next = [];
      for (const edge of edges) {
        const from = nodeRefs.current[edge.from];
        const to = nodeRefs.current[edge.to];
        if (!from || !to) continue;
        const child = from.getBoundingClientRect();
        const parent = to.getBoundingClientRect();
        const x1 = child.left - box.left;
        const y1 = child.top - box.top + child.height / 2;
        const x2 = parent.right - box.left;
        const y2 = parent.top - box.top + parent.height / 2;
        const mid = (x1 + x2) / 2;
        next.push({
          key: `${edge.from}-${edge.to}-${edge.kind}`,
          d: `M ${x2} ${y2} C ${mid} ${y2}, ${mid} ${y1}, ${x1} ${y1}`,
          kind: edge.kind,
          dim: Boolean(keep && (!keep.has(edge.from) || !keep.has(edge.to))),
        });
      }
      setLines((prev) => {
        if (prev.length === next.length && prev.every((line, index) => (
          line.key === next[index].key && line.d === next[index].d && line.dim === next[index].dim && line.kind === next[index].kind
        ))) return prev;
        return next;
      });
    }
    layout();
    window.addEventListener("resize", layout);
    return () => window.removeEventListener("resize", layout);
  }, [edges, keep]);

  function activate(node) {
    if (focus === node.id) onOpen(node.id);
    else onFocus(node.id);
  }

  return (
    <div className="web-scroll">
      <div className="web-wrap" ref={wrapRef} onClick={() => onFocus(null)}>
        <svg className="web-lines" aria-hidden="true">
          {lines.map((line) => (
            <path key={line.key} d={line.d} className={line.dim ? "dim" : line.kind} />
          ))}
        </svg>
        <div className="web-lanes">
          {["radical", "kanji", "vocabulary"].map((lane) => (
            <div key={lane} className="web-lane">
              <p className="kicker">{LANE_LABEL[lane]}</p>
              {(data.lanes?.[lane] || []).map((node) => {
                const dim = keep && !keep.has(node.id);
                return (
                  <button
                    key={node.id}
                    type="button"
                    ref={(element) => {
                      if (element) nodeRefs.current[node.id] = element;
                      else delete nodeRefs.current[node.id];
                    }}
                    className={[
                      "web-node",
                      `t-${node.type}`,
                      `b-${node.bucket || "fresh"}`,
                      node.weak ? "is-weak" : "",
                      node.outside ? "is-outside" : "",
                      dim ? "is-dim" : "",
                      focus === node.id ? "active" : "",
                    ].filter(Boolean).join(" ")}
                    onClick={(event) => {
                      event.stopPropagation();
                      activate(node);
                    }}
                  >
                    <b lang="ja">{node.label}</b>
                    <small>{node.reading || node.meaning}</small>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function KanjiWeb({ level, go }) {
  const [data, setData] = useState(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState("");
  const [similar, setSimilar] = useState(false);
  const [focus, setFocus] = useState(null);
  const [inspect, setInspect] = useState(null);
  const narrow = useNarrow();

  useEffect(() => {
    setData(null);
    setFocus(null);
    setMissing(false);
    setError("");
    api.kanjiWeb(level)
      .then(setData)
      .catch((err) => {
        if (err.status === 409) setMissing(true);
        else setError(err.message || "Could not load this web");
      });
  }, [level]);

  return (
    <section className="panel web-page">
      <div className="section-head level-head">
        <div>
          <button type="button" className="quiet-link" onClick={() => go(`/level/${level}`)}>← Level {level}</button>
          <h2>Kanji web</h2>
        </div>
        <div className="level-nav">
          <label className="web-toggle">
            <input type="checkbox" checked={similar} onChange={(event) => setSimilar(event.target.checked)} />
            Look-alikes
          </label>
          <button type="button" className="ghost-btn" onClick={() => go(`/read/level/${level}`)}>Read</button>
        </div>
      </div>
      {missing ? <CatalogNote /> : null}
      {error ? <div className="error">{error}</div> : null}
      {!data && !missing ? <p className="muted">Drawing the web…</p> : null}
      {data?.weak_links?.length ? (
        <ul className="web-weak">
          {data.weak_links.map((item) => (
            <li key={item.id}>
              <b lang="ja">{item.label}</b> is shaky and holds up {item.dependents} {item.dependents === 1 ? "word" : "words"}.
            </li>
          ))}
        </ul>
      ) : null}
      {data ? (
        narrow ? (
          <FocusList lanes={data.lanes} edges={data.edges || []} onOpen={setInspect} />
        ) : (
          <Lanes data={data} showSimilar={similar} focus={focus} onFocus={setFocus} onOpen={setInspect} />
        )
      ) : null}
      <p className="muted read-legend">Tap a character to trace what it's built from. Tap it again for the card. A red ring is something you keep missing.</p>
      <InspectDrawer subjectId={inspect} onClose={() => setInspect(null)} />
    </section>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";

// One of your kanji painted with a brush, stroke by stroke in real stroke
// order, on a practice-paper grid. Holds, fades like drying ink, next one.
// Stroke data: KanjiVG (CC BY-SA 3.0), fetched per glyph and cached.

const HOLD_MS = 3200;
const FADE_MS = 700;
const VIEW = 109; // KanjiVG coordinate space
const STATE_WORD = { 0: "to check", 1: "relearning", 2: "relearning", 3: "relearning", 4: "relearning" };
const KANJIVG = "https://cdn.jsdelivr.net/gh/KanjiVG/kanjivg@master/kanji/";
// Stroke types that leave the paper in a sweep (harai) or flick (hane), so the
// brush lifts and thins out. Everything else stops (tome) with a slight press.
const SWEEP_TYPES = /[㇒㇏㇀㇓㇇㇢㇚㇙㇟㇂㇆㇈㇉㇌㇊㇋㇎㇜]/;
const strokeCache = new Map();

function pickGlyphs(sky) {
  // Kanji you're relearning or haven't checked come first; then anything from
  // started levels; then level 1. 帰 ("return") always opens the loop.
  const kanji = [];
  for (const level of sky || []) {
    for (const [, type, chars, meaning, stage] of level.items) {
      if (type !== "k" || !chars) continue;
      kanji.push({ chars, meaning, level: level.level, stage });
    }
  }
  const rank = (item) => (item.stage != null && item.stage < 5 ? 0 : item.stage != null ? 1 : 2);
  const pool = kanji.filter((item) => rank(item) === Math.min(...kanji.map(rank)));
  const shuffled = pool.sort(() => Math.random() - 0.5).slice(0, 12);
  return [{ chars: "帰", meaning: "Return", level: 9, stage: null, intro: true }, ...shuffled];
}

function loadStrokes(char) {
  if (strokeCache.has(char)) return strokeCache.get(char);
  const code = char.codePointAt(0).toString(16).padStart(5, "0");
  const request = fetch(`${KANJIVG}${code}.svg`)
    .then((res) => (res.ok ? res.text() : Promise.reject(new Error(String(res.status)))))
    .then((text) => {
      const doc = new DOMParser().parseFromString(text, "image/svg+xml");
      const paths = [...doc.querySelectorAll('g[id^="kvg:StrokePaths"] path')];
      return paths.length ? paths.map((path) => ({ d: path.getAttribute("d"), type: path.getAttribute("kvg:type") || "" })) : null;
    })
    .catch(() => null);
  strokeCache.set(char, request);
  return request;
}

// Resample each stroke into evenly spaced points with a brush width per point.
function brushPlan(strokes, probe) {
  return strokes.map(({ d, type }) => {
    probe.setAttribute("d", d);
    const length = probe.getTotalLength();
    const count = Math.max(2, Math.ceil(length / 0.35));
    const sweep = SWEEP_TYPES.test(type);
    const points = [];
    for (let i = 0; i <= count; i += 1) {
      const t = i / count;
      const { x, y } = probe.getPointAtLength(t * length);
      const entry = 1 + 0.45 * Math.exp(-((t / 0.07) ** 2)); // brush lands and presses
      const exit = sweep
        ? 1 - 0.85 * Math.min(1, Math.max(0, (t - 0.55) / 0.45)) ** 1.6 // lifts off
        : 1 + 0.18 * Math.exp(-(((1 - t) / 0.05) ** 2)); // stops and presses
      points.push({ x, y, r: 2.35 * entry * exit, t });
    }
    return { points, length, sweep };
  });
}

function stamp(ctx, point, prev, sweep, seed) {
  // Core ink plus a few bristles that thin out toward a sweep's tail (kasure).
  ctx.globalAlpha = 0.9;
  ctx.beginPath();
  ctx.arc(point.x, point.y, point.r, 0, Math.PI * 2);
  ctx.fill();
  if (!prev) return;
  const dx = point.x - prev.x;
  const dy = point.y - prev.y;
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len;
  const ny = dx / len;
  const dry = sweep ? Math.max(0, (point.t - 0.6) / 0.4) : 0;
  for (let b = 0; b < 4; b += 1) {
    const side = ((b + 0.5) / 4) * 2 - 1;
    const wobble = Math.sin(seed * 13.1 + b * 7.7 + point.t * 40) * 0.12;
    const offset = (side + wobble) * point.r * (1 + 0.35 * dry);
    ctx.globalAlpha = (0.22 + 0.25 * dry) * (Math.sin(seed + b * 3.3 + point.t * 90) > -0.2 ? 1 : 0.25);
    ctx.beginPath();
    ctx.arc(point.x + nx * offset, point.y + ny * offset, point.r * 0.32, 0, Math.PI * 2);
    ctx.fill();
  }
}

export default function KanjiField({ sky, onOpenLevel }) {
  const canvasRef = useRef(null);
  const probeRef = useRef(null);
  const glyphs = useMemo(() => pickGlyphs(sky), [sky]);
  const [index, setIndex] = useState(0);
  const [strokes, setStrokes] = useState(null); // null = loading, [] = no data
  const current = glyphs[index % glyphs.length];

  // Load this glyph's strokes and warm the cache for the next one.
  useEffect(() => {
    let alive = true;
    setStrokes(null);
    loadStrokes(current.chars).then((paths) => alive && setStrokes(paths || []));
    loadStrokes(glyphs[(index + 1) % glyphs.length].chars);
    return () => { alive = false; };
  }, [current, glyphs, index]);

  // Paint, hold, fade, advance.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (strokes == null || !canvas || !probeRef.current) return undefined;
    const ctx = canvas.getContext("2d");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const plan = brushPlan(strokes, probeRef.current);
    let alive = true;
    let frame = 0;
    let timer = 0;
    let scale = 1;
    let drawn = []; // points already stamped, per stroke

    function size() {
      const box = canvas.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(box.width * dpr);
      canvas.height = Math.round(box.height * dpr);
      scale = (box.width * dpr) / VIEW;
    }

    function paintUpTo(counts) {
      // Full repaint is cheap (a few thousand arcs) and keeps resizes correct.
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      ctx.fillStyle = "#191714";
      plan.forEach((stroke, s) => {
        for (let i = 0; i < (counts[s] || 0); i += 1) stamp(ctx, stroke.points[i], stroke.points[i - 1], stroke.sweep, s + 1);
      });
      ctx.globalAlpha = 1;
    }

    // Long sweeps take longer; short dots are a quick press. Gap = brush lift.
    const timeline = [];
    let cursor = 150;
    for (const stroke of plan) {
      const duration = 180 + stroke.length * 7;
      timeline.push({ start: cursor, duration });
      cursor += duration + 110;
    }
    const total = cursor;

    canvas.style.transition = "none";
    canvas.style.opacity = "1";
    canvas.style.filter = "none";
    size();

    if (reduced || !plan.length) {
      drawn = plan.map((stroke) => stroke.points.length);
      paintUpTo(drawn);
      if (!plan.length) return undefined;
      if (reduced) return undefined;
    }

    const began = performance.now();
    function tick(now) {
      if (!alive) return;
      const elapsed = now - began;
      drawn = timeline.map(({ start, duration }, s) => {
        const p = Math.min(1, Math.max(0, (elapsed - start) / duration));
        const eased = p < 0.5 ? 2 * p * p : 1 - ((-2 * p + 2) ** 2) / 2;
        return Math.ceil(eased * plan[s].points.length);
      });
      paintUpTo(drawn);
      if (elapsed < total) {
        frame = window.requestAnimationFrame(tick);
        return;
      }
      timer = window.setTimeout(() => {
        canvas.style.transition = `opacity ${FADE_MS}ms ease-in, filter ${FADE_MS}ms ease-in`;
        canvas.style.opacity = "0";
        canvas.style.filter = "blur(3px)";
        timer = window.setTimeout(() => alive && setIndex((value) => (value + 1) % glyphs.length), FADE_MS);
      }, HOLD_MS);
    }
    frame = window.requestAnimationFrame(tick);

    const observer = new ResizeObserver(() => { size(); paintUpTo(drawn); });
    observer.observe(canvas);
    return () => {
      alive = false;
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
      observer.disconnect();
    };
  }, [strokes, glyphs.length]);

  return (
    <div className="kanji-field">
      <div className="brush-sheet">
        <svg viewBox="0 0 109 109" aria-hidden="true">
          <g className="practice-grid">
            <rect x="4.5" y="4.5" width="100" height="100" />
            <line x1="54.5" y1="4.5" x2="54.5" y2="104.5" />
            <line x1="4.5" y1="54.5" x2="104.5" y2="54.5" />
          </g>
          <path ref={probeRef} d="M0 0" fill="none" stroke="none" />
          {strokes && !strokes.length ? <text className="ink-fallback" x="54.5" y="58" lang="ja">{current.chars}</text> : null}
        </svg>
        <canvas ref={canvasRef} aria-hidden="true" />
      </div>
      <button className="field-caption" key={current.chars} onClick={() => !current.intro && onOpenLevel(current.level)}>
        <span lang="ja">{current.chars}</span>
        <span>
          <b>{current.meaning}{strokes?.length ? <i> · {strokes.length} strokes</i> : null}</b>
          <small>
            {current.intro ? "kaeru · to return" : `Level ${current.level}${current.stage != null && current.stage < 5 ? ` · ${STATE_WORD[current.stage]}` : ""} · open →`}
          </small>
        </span>
      </button>
      <a className="field-credit" href="https://kanjivg.tagaini.net" target="_blank" rel="noreferrer">Stroke order: KanjiVG</a>
    </div>
  );
}

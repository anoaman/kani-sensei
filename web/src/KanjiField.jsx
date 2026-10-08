import { useEffect, useMemo, useRef, useState } from "react";

// Dots (the same ones as the memory sky) that assemble into one of your
// kanji, hold, scatter, and re-form as the next. The cursor pushes them.

const HOLD_MS = 5200;
const STEP = 6; // sampling grid in CSS px: smaller = more dots
const MAX_DOTS = 900;
const COLORS = ["#191714", "#191714", "#191714", "#c4402b", "#b23a6b", "#6d4598", "#2f6f9f"];
const STATE_WORD = { 0: "to check", 1: "relearning", 2: "relearning", 3: "relearning", 4: "relearning" };

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

function sampleGlyph(char, width, height) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  const size = Math.min(width, height) * 0.82;
  ctx.fillStyle = "#000";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = `900 ${size}px "Noto Serif JP", "Hiragino Mincho ProN", "Yu Mincho", serif`;
  ctx.fillText(char, width / 2, height / 2 + size * 0.04);
  const data = ctx.getImageData(0, 0, width, height).data;
  const points = [];
  for (let y = 0; y < height; y += STEP) {
    for (let x = 0; x < width; x += STEP) {
      if (data[(y * width + x) * 4 + 3] > 140) points.push([x, y]);
    }
  }
  // Too dense for big strokes: thin evenly so every glyph uses a similar budget.
  if (points.length > MAX_DOTS) {
    const keep = MAX_DOTS / points.length;
    return points.filter(() => Math.random() < keep);
  }
  return points;
}

export default function KanjiField({ sky, onOpenLevel }) {
  const canvasRef = useRef(null);
  const glyphs = useMemo(() => pickGlyphs(sky), [sky]);
  const [current, setCurrent] = useState(glyphs[0]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let width = 0;
    let height = 0;
    let dpr = 1;
    let dots = [];
    let frame = 0;
    let timer = 0;
    let index = 0;
    let visible = true;
    let alive = true;
    const mouse = { x: -9999, y: -9999 };

    function makeDot() {
      return {
        x: Math.random() * width,
        y: Math.random() * height,
        vx: 0,
        vy: 0,
        tx: null,
        ty: null,
        color: COLORS[Math.floor(Math.random() * COLORS.length)],
        drift: Math.random() * Math.PI * 2,
      };
    }

    function target(glyph) {
      const points = sampleGlyph(glyph.chars, Math.round(width), Math.round(height));
      while (dots.length < points.length) dots.push(makeDot());
      const order = dots.map((_, i) => i).sort(() => Math.random() - 0.5);
      order.forEach((dotIndex, i) => {
        const dot = dots[dotIndex];
        if (i < points.length) {
          dot.tx = points[i][0];
          dot.ty = points[i][1];
        } else {
          dot.tx = null; // spare dots float as dust
          dot.ty = null;
        }
      });
      setCurrent(glyph);
    }

    function scatter() {
      for (const dot of dots) {
        const angle = Math.random() * Math.PI * 2;
        const speed = 4 + Math.random() * 7;
        dot.vx += Math.cos(angle) * speed;
        dot.vy += Math.sin(angle) * speed;
      }
    }

    function cycle() {
      if (!alive) return;
      scatter();
      timer = window.setTimeout(() => {
        index = (index + 1) % glyphs.length;
        target(glyphs[index]);
        timer = window.setTimeout(cycle, HOLD_MS);
      }, 420);
    }

    function draw() {
      ctx.clearRect(0, 0, width, height);
      const t = performance.now() / 1000;
      for (const dot of dots) {
        if (dot.tx != null) {
          dot.vx += (dot.tx - dot.x) * 0.045;
          dot.vy += (dot.ty - dot.y) * 0.045;
        } else {
          dot.vx += Math.cos(t * 0.6 + dot.drift) * 0.03;
          dot.vy += Math.sin(t * 0.5 + dot.drift) * 0.03;
        }
        const dx = dot.x - mouse.x;
        const dy = dot.y - mouse.y;
        const dist2 = dx * dx + dy * dy;
        if (dist2 < 4900) {
          const push = (4900 - dist2) / 4900;
          const dist = Math.sqrt(dist2) || 1;
          dot.vx += (dx / dist) * push * 3.2;
          dot.vy += (dy / dist) * push * 3.2;
        }
        dot.vx *= 0.82;
        dot.vy *= 0.82;
        dot.x += dot.vx;
        dot.y += dot.vy;
        ctx.globalAlpha = dot.tx != null ? 0.92 : 0.18;
        ctx.fillStyle = dot.color;
        ctx.fillRect(dot.x - 1.6, dot.y - 1.6, 3.2, 3.2);
      }
      ctx.globalAlpha = 1;
    }

    function loop() {
      if (!alive) return;
      if (visible) draw();
      frame = window.requestAnimationFrame(loop);
    }

    function resize() {
      const box = canvas.getBoundingClientRect();
      dpr = Math.min(2, window.devicePixelRatio || 1);
      width = box.width;
      height = box.height;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (dots.length) target(glyphs[index]);
    }

    function onMove(event) {
      const box = canvas.getBoundingClientRect();
      const point = event.touches ? event.touches[0] : event;
      mouse.x = point.clientX - box.left;
      mouse.y = point.clientY - box.top;
    }
    function onLeave() {
      mouse.x = -9999;
      mouse.y = -9999;
    }

    const observer = new ResizeObserver(resize);
    const seen = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; });
    resize();
    observer.observe(canvas);
    seen.observe(canvas);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerleave", onLeave);

    const fontReady = document.fonts?.load
      ? Promise.all(glyphs.map((glyph) => document.fonts.load('900 120px "Noto Serif JP"', glyph.chars))).catch(() => null)
      : Promise.resolve();
    fontReady.then(() => {
      if (!alive) return;
      target(glyphs[0]);
      if (reduced) {
        for (const dot of dots) {
          if (dot.tx != null) {
            dot.x = dot.tx;
            dot.y = dot.ty;
          }
        }
        draw();
        return;
      }
      loop();
      timer = window.setTimeout(cycle, HOLD_MS);
    });

    return () => {
      alive = false;
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
      observer.disconnect();
      seen.disconnect();
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
    };
  }, [glyphs]);

  return (
    <div className="kanji-field">
      <canvas ref={canvasRef} aria-hidden="true" />
      <button className="field-caption" key={current.chars} onClick={() => !current.intro && onOpenLevel(current.level)}>
        <span lang="ja">{current.chars}</span>
        <span>
          <b>{current.meaning}</b>
          <small>
            {current.intro ? "kaeru · to return" : `Level ${current.level}${current.stage != null && current.stage < 5 ? ` · ${STATE_WORD[current.stage]}` : ""} · open →`}
          </small>
        </span>
      </button>
    </div>
  );
}

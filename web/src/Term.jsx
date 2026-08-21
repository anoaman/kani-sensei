import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { lookupTerm, readingTypeId, srsTermId } from "./glossary.js";

function tipStyle(anchor) {
  if (!anchor) return { top: 0, left: 0, visibility: "hidden" };
  const rect = anchor.getBoundingClientRect();
  const width = Math.min(280, window.innerWidth - 16);
  let left = rect.left;
  if (left + width > window.innerWidth - 8) left = window.innerWidth - width - 8;
  if (left < 8) left = 8;
  const spaceBelow = window.innerHeight - rect.bottom;
  if (spaceBelow < 132 && rect.top > spaceBelow) {
    return { left, top: rect.top - 8, width, transform: "translateY(-100%)" };
  }
  return { left, top: rect.bottom + 8, width };
}

export function T({ k, children, hoverOnly = false }) {
  const entry = lookupTerm(k);
  const reactId = useId();
  const wrapRef = useRef(null);
  const hitRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [coords, setCoords] = useState(null);
  const hideTimer = useRef(null);

  useLayoutEffect(() => {
    if (!open) return undefined;
    function place() {
      setCoords(tipStyle(hitRef.current));
    }
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    function onDoc(event) {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) {
        setOpen(false);
        setPinned(false);
      }
    }
    function onKey(event) {
      if (event.key === "Escape") {
        setOpen(false);
        setPinned(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!entry) return children || k;

  function show() {
    window.clearTimeout(hideTimer.current);
    setOpen(true);
  }

  function hide() {
    if (pinned) return;
    hideTimer.current = window.setTimeout(() => setOpen(false), 140);
  }

  function toggle(event) {
    if (hoverOnly) return;
    event.preventDefault();
    event.stopPropagation();
    setPinned((value) => {
      const next = !value;
      setOpen(true);
      return next;
    });
  }

  return (
    <span
      className={`term ${open ? "is-open" : ""}`}
      ref={wrapRef}
      onMouseEnter={show}
      onMouseLeave={hide}
    >
      <span
        className="term-hit"
        ref={hitRef}
        tabIndex={hoverOnly ? undefined : 0}
        role={hoverOnly ? undefined : "note"}
        aria-describedby={open ? reactId : undefined}
        onClick={toggle}
        onFocus={show}
        onBlur={hide}
        onKeyDown={(event) => {
          if (hoverOnly) return;
          if (event.key === "Enter" || event.key === " ") toggle(event);
        }}
      >
        {children || entry.term}
      </span>
      {open && coords
        ? createPortal(
            <span className="term-tip" id={reactId} role="tooltip" style={coords}>
              <strong>{entry.term}</strong>
              <span>{entry.short}</span>
            </span>,
            document.body,
          )
        : null}
    </span>
  );
}

export function SrsTerm({ name, hoverOnly = false }) {
  if (!name) return null;
  return (
    <T k={srsTermId(name)} hoverOnly={hoverOnly}>
      {name}
    </T>
  );
}

export function ReadingTerm({ type, hoverOnly = false }) {
  if (!type || type === "reading") return null;
  return (
    <T k={readingTypeId(type)} hoverOnly={hoverOnly}>
      {type}
    </T>
  );
}

import { useState } from "react";

const THEME_KEY = "kani-theme";

export function themeChoice() {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    return stored === "dark" || stored === "light" ? stored : null;
  } catch {
    return null;
  }
}

export function resolveTheme(choice = themeChoice()) {
  if (choice === "dark" || choice === "light") return choice;
  if (typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }
  return "light";
}

export function applyTheme(choice = themeChoice()) {
  const theme = resolveTheme(choice);
  document.documentElement.dataset.theme = theme;
  return theme;
}

if (typeof window !== "undefined") {
  applyTheme();
  window.matchMedia?.("(prefers-color-scheme: dark)")?.addEventListener?.("change", () => {
    if (!themeChoice()) applyTheme(null);
  });
}

export function ThemeToggle() {
  const [choice, setChoice] = useState(themeChoice);
  const theme = resolveTheme(choice);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      /* private mode */
    }
    setChoice(next);
    applyTheme(next);
  }

  return (
    <button
      type="button"
      className="text-btn theme-toggle"
      aria-pressed={theme === "dark"}
      onClick={toggle}
    >
      {theme === "dark" ? "Dark" : "Light"}
    </button>
  );
}

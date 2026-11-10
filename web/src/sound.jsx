import { useState } from "react";

const SOUND_KEY = "kani-sound";

export function soundEnabled() {
  try {
    return localStorage.getItem(SOUND_KEY) !== "off";
  } catch {
    return true;
  }
}

export function setSoundEnabled(on) {
  try {
    localStorage.setItem(SOUND_KEY, on ? "on" : "off");
  } catch {
    /* private mode */
  }
}

export function SoundToggle() {
  const [on, setOn] = useState(soundEnabled);
  return (
    <button
      type="button"
      className="text-btn sound-toggle"
      aria-pressed={on}
      onClick={() => {
        const next = !on;
        setOn(next);
        setSoundEnabled(next);
      }}
    >
      {on ? "Sound on" : "Sound off"}
    </button>
  );
}

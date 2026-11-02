/** Japanese text-to-speech. Call speak() from a tap — iOS will not speak otherwise. */

function japaneseVoice() {
  const synth = window.speechSynthesis;
  if (!synth) return null;
  return synth.getVoices().find((voice) => (voice.lang || "").toLowerCase().startsWith("ja")) || null;
}

export function hasJapaneseVoice() {
  if (typeof window === "undefined" || !window.speechSynthesis) return false;
  return Boolean(japaneseVoice());
}

export function stop() {
  window.speechSynthesis?.cancel();
}

export function speak(text, { rate = 1 } = {}) {
  const synth = typeof window === "undefined" ? null : window.speechSynthesis;
  if (!synth || !text) return Promise.resolve(false);
  return new Promise((resolve) => {
    let started = false;
    const start = () => {
      if (started) return;
      started = true;
      const utter = new SpeechSynthesisUtterance(text);
      utter.lang = "ja-JP";
      utter.rate = rate;
      const voice = japaneseVoice();
      if (voice) utter.voice = voice;
      utter.onend = () => resolve(true);
      utter.onerror = () => resolve(false);
      synth.cancel();
      synth.speak(utter);
    };
    if (synth.getVoices().length) {
      start();
      return;
    }
    const onVoices = () => {
      synth.removeEventListener("voiceschanged", onVoices);
      start();
    };
    synth.addEventListener("voiceschanged", onVoices);
    synth.getVoices();
    window.setTimeout(() => {
      synth.removeEventListener("voiceschanged", onVoices);
      start();
    }, 400);
  });
}

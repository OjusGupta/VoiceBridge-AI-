// Voice I/O. Input = browser-native SpeechRecognition (NOT an API fallback).
// In Chrome/Edge the browser streams audio to the browser vendor's speech service.
// Output = browser-native speechSynthesis (local to the device).
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const synth = window.speechSynthesis;

export const support = {
  recognition: !!SR,
  synthesis: !!synth && "SpeechSynthesisUtterance" in window,
  secure: window.isSecureContext,  // true on https:// and http://localhost
};

const ERRORS = {
  "not-allowed": "Microphone permission was denied. Allow it in the browser's site settings and try again.",
  "service-not-allowed": "Speech recognition is blocked by the browser or OS.",
  "audio-capture": "No microphone was found or it is in use by another app.",
  "no-speech": "No speech detected. Try again and speak after the indicator turns red.",
  "network": "Speech recognition needs a network connection (the browser's speech service was unreachable).",
  "language-not-supported": "English speech recognition is not supported here.",
};

export function createRecognizer({ onState, onInterim, onFinal, onError }) {
  if (!SR) return null;
  let rec = null, gotResult = false, cancelled = false, startTimer = null;
  const clear = () => { clearTimeout(startTimer); startTimer = null; };
  return {
    start() {
      if (!support.secure) { onError("Microphone access needs https:// or http://localhost."); return; }
      rec = new SR();
      rec.lang = "en-US"; rec.interimResults = true; rec.continuous = false; rec.maxAlternatives = 1;
      gotResult = false; cancelled = false;
      onState("requesting");
      // If the permission prompt is dismissed / no mic responds, don't hang forever.
      startTimer = setTimeout(() => { cancelled = true; try { rec.abort(); } catch {} onState("idle");
        onError("The microphone did not start. Check that a microphone is connected and that you allowed access (look for a permission prompt or the lock icon in the address bar)."); }, 8000);
      rec.onaudiostart = () => { clear(); onState("listening"); };
      rec.onresult = (e) => {
        let interim = "", final = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i]; (r.isFinal ? (final += r[0].transcript) : (interim += r[0].transcript));
        }
        if (interim) onInterim(interim);
        if (final.trim()) { gotResult = true; onState("processing"); onFinal(final.trim()); }
      };
      rec.onerror = (e) => { clear(); if (e.error === "aborted" && cancelled) return; onError(ERRORS[e.error] || `Speech recognition error: ${e.error}`); };
      rec.onend = () => { clear(); if (!gotResult && !cancelled) onState("idle"); else if (cancelled) onState("idle"); };
      try { rec.start(); } catch (err) { onError("Could not start listening: " + err.message); }
    },
    stop() { clear(); cancelled = true; try { rec && rec.abort(); } catch {} onState("idle"); },
  };
}

function pickVoice() {
  const v = synth.getVoices().filter((x) => x.lang && x.lang.toLowerCase().startsWith("en"));
  return v.find((x) => /natural|neural|google us english|samantha|aria|jenny/i.test(x.name)) || v.find((x) => x.localService) || v[0] || null;
}
export const speaker = {
  rate: 1,
  speak(text, { onStart, onEnd } = {}) {
    if (!support.synthesis) return false;
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    const voice = pickVoice(); if (voice) u.voice = voice; u.lang = voice ? voice.lang : "en-US"; u.rate = this.rate;
    u.onstart = () => onStart && onStart(); u.onend = u.onerror = () => onEnd && onEnd();
    synth.speak(u); return true;
  },
  stop() { if (support.synthesis) synth.cancel(); },
};

// Non-secret UI preferences only (no keys/tokens are ever stored in the browser).
const KEY = "voicebridge.prefs.v1";
const DEFAULTS = { promptVersion: "A", speakReplies: false, voiceConversation: false, voiceInput: true, speechRate: 1 };
let cache = { ...DEFAULTS };
try { cache = { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") }; } catch { /* storage blocked: stay in-memory */ }
export const prefs = {
  get: (k) => cache[k],
  set(k, v) { cache[k] = v; try { localStorage.setItem(KEY, JSON.stringify(cache)); } catch {} window.dispatchEvent(new CustomEvent("prefs", { detail: k })); },
};

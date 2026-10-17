import { api } from "./api.js";
import { support, createRecognizer, speaker } from "./voice.js";
import { prefs } from "./prefs.js";
import { initRouter } from "./pages.js";

const $ = (id) => document.getElementById(id);
const EXAMPLES = ["Yes, let's get started.", "I want to understand the general loan inquiry process.", "What documents might I need for a loan inquiry?",
  "I'm not sure what information I should provide.", "Can you explain the next steps?", "I want to speak to a human.",
  "What is my guaranteed interest rate?", "Start again.", "Stop the conversation."];

const S = { id: null, busy: false, active: false, micVerified: false, rec: null, voiceState: "idle" };
const log = $("log"), input = $("composer-input");

function el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; } // textContent only: no HTML injection
function banner(msg, kind = "") { const b = $("banner"); b.hidden = !msg; b.textContent = msg || ""; b.className = "banner " + kind; }
function scroll() { log.scrollTop = log.scrollHeight; }

function setVoiceState(state, text) {
  S.voiceState = state;
  const vs = $("voice-status"); vs.dataset.state = state; vs.textContent = text || ({ idle: "Idle", requesting: "Requesting microphone…", listening: "Listening…", processing: "Processing speech…", generating: "Generating response…", speaking: "Speaking…", error: "Error" })[state];
  const mic = $("btn-mic"); mic.dataset.state = state;
  const on = state === "listening" || state === "requesting";
  mic.setAttribute("aria-pressed", String(on)); mic.setAttribute("aria-label", on ? "Stop voice input" : "Start voice input");
  $("btn-stop-speak").disabled = state !== "speaking";
}

function addMessage(role, text, meta) {
  const m = el("div", "msg " + role); m.appendChild(el("div", null, text));
  if (role === "assistant") {
    const row = el("div", "meta");
    if (meta && meta.state) row.appendChild(el("span", "tag", meta.state));
    if (meta && meta.intent) row.appendChild(el("span", "tag", meta.intent));
    if (meta && meta.clarification_required) row.appendChild(el("span", "tag warn", "clarification"));
    if (meta && meta.fallback_used) row.appendChild(el("span", "tag warn", "fallback"));
    if (support.synthesis) { const b = el("button", "linkbtn", "▶ Play"); b.type = "button"; b.setAttribute("aria-label", "Play this reply aloud"); b.onclick = () => speak(text); row.appendChild(b); }
    m.appendChild(row);
  }
  log.appendChild(m); scroll(); $("welcome").hidden = true; return m;
}

function applySnapshot(s) {
  S.id = s.session_id; S.active = s.is_active;
  $("chip-session").textContent = "session " + s.session_id;
  $("chip-state").textContent = s.state + (s.is_active ? "" : " · ended");
  $("progress-bar").style.width = Math.min(100, (s.turn_count / s.max_turns) * 100) + "%";
  $("composer-input").disabled = !s.is_active; $("btn-send").disabled = !s.is_active || S.busy;
  input.placeholder = s.is_active ? "Type a message, or press the mic and speak…" : "Conversation ended. Press Restart to begin again.";
}

function speak(text) {
  const ok = speaker.speak(text, { onStart: () => setVoiceState("speaking"), onEnd: () => S.voiceState === "speaking" && setVoiceState("idle") });
  if (!ok) banner("Spoken replies are not supported in this browser.");
}

async function send(text) {
  text = (text || "").trim();
  if (!text || S.busy || !S.active) return;           // empty / duplicate / ended guard
  S.busy = true; $("btn-send").disabled = true; banner("");
  speaker.stop(); addMessage("user", text); input.value = ""; autosize();
  const typing = el("div", "msg assistant typing", "Thinking…"); log.appendChild(typing); scroll();
  setVoiceState("generating");
  try {
    const r = await api.send(S.id, text);
    typing.remove(); addMessage("assistant", r.reply, r); applySnapshot(r); setVoiceState("idle");
    if ($("opt-speak").checked) speak(r.reply);
  } catch (e) {
    typing.remove(); addMessage("error", e.message); setVoiceState("error", "Error"); setTimeout(() => S.voiceState === "error" && setVoiceState("idle"), 3000);
    if (e.status === 404) banner("This session no longer exists (the server was restarted). Press Restart.");
  } finally { S.busy = false; $("btn-send").disabled = !S.active; input.focus(); }
}

async function start(fn) {
  try {
    speaker.stop(); log.replaceChildren(); banner("");
    const r = await fn(); applySnapshot(r); addMessage("assistant", r.reply, { state: r.state }); $("welcome").hidden = false;
    if ($("opt-speak").checked) speak(r.reply);
  } catch (e) { banner(e.message); }
}

function syncPrefs() {
  $("opt-speak").checked = prefs.get("speakReplies") && support.synthesis; $("opt-voicemode").checked = prefs.get("voiceConversation") && support.recognition;
  $("prompt-label").textContent = prefs.get("promptVersion"); speaker.rate = prefs.get("speechRate");
  const mic = $("btn-mic"); mic.disabled = !support.recognition || !prefs.get("voiceInput");
  if (support.recognition) mic.title = prefs.get("voiceInput") ? "" : "Voice input is turned off in Settings.";
}
function autosize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; }

// ── voice input ──
function initVoice() {
  const chip = $("chip-voice");
  if (!support.recognition) {
    chip.textContent = "voice input: unsupported here"; chip.className = "chip warn";
    $("btn-mic").disabled = true; $("btn-mic").title = "Speech recognition is not available in this browser. Use Chrome or Edge, or type.";
    banner("Voice input isn't supported in this browser (try Chrome or Edge). Typing and spoken replies still work where available.", "info");
  } else {
    chip.textContent = "voice input: browser-native (untested)"; chip.className = "chip warn";
    chip.title = "Uses the browser's built-in speech recognition. In Chrome/Edge the audio is processed by the browser vendor's cloud service.";
    S.rec = createRecognizer({
      onState: (s) => setVoiceState(s),
      onInterim: (t) => { input.value = t; autosize(); },
      onFinal: (t) => {
        input.value = t; autosize();
        if (!S.micVerified) { S.micVerified = true; chip.textContent = "voice input: working (this session)"; chip.className = "chip ok"; }
        if ($("opt-voicemode").checked) send(t); else { setVoiceState("idle"); input.focus(); banner("Check the transcription, edit if needed, then press Send.", "info"); }
      },
      onError: (m) => { setVoiceState("error"); banner(m); },
    });
  }
  if (!support.synthesis) { $("opt-speak").disabled = true; $("opt-speak").parentElement.title = "Speech synthesis unsupported in this browser."; }
  $("btn-mic").onclick = () => { if (!S.rec) return; if (["listening", "requesting"].includes(S.voiceState)) S.rec.stop(); else { speaker.stop(); banner(""); S.rec.start(); } };
  $("btn-stop-speak").onclick = () => { speaker.stop(); setVoiceState("idle"); };
}

async function init() {
  $("examples").append(...EXAMPLES.map((t) => { const b = el("button", null, t); b.type = "button"; b.onclick = () => send(t); return b; }));
  $("btn-send").onclick = () => send(input.value);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input.value); } });
  input.addEventListener("input", autosize);
  const version = () => prefs.get("promptVersion");
  syncPrefs(); window.addEventListener("prefs", syncPrefs);
  $("opt-speak").onchange = () => prefs.set("speakReplies", $("opt-speak").checked);
  $("opt-voicemode").onchange = () => prefs.set("voiceConversation", $("opt-voicemode").checked);
  $("btn-new").onclick = () => start(() => api.create(version()));
  $("btn-restart").onclick = () => start(() => S.id ? api.restart(S.id).catch(() => api.create(version())) : api.create(version()));
  $("btn-end").onclick = async () => { if (!S.id || !S.active) return; try { const r = await api.end(S.id); applySnapshot(r); banner("Conversation ended.", "info"); } catch (e) { banner(e.message); } };
  initVoice();
  try { const st = await api.status(); $("mode-label").textContent = st.mode_label; }
  catch (e) { $("mode-label").textContent = "offline"; banner(e.message); return; }
  await start(() => api.create(version()));
  initRouter();
}
init();

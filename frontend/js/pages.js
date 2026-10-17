import { DIAGRAMS, GLOSSARY } from "./diagrams.js";
import { prefs } from "./prefs.js";
import { support, speaker } from "./voice.js";

const $ = (id) => document.getElementById(id);
const j = async (method, url) => {
  let r; try { r = await fetch(url, { method }); } catch { throw new Error("Cannot reach the backend. Is the server running?"); }
  if (!r.ok) throw new Error(`Server error (${r.status})`); return r.json();
};
// Safe DOM builder: strings become text nodes, never HTML.
function h(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) { if (k === "class") n.className = v; else if (k.startsWith("on")) n[k] = v; else if (v === true) n.setAttribute(k, ""); else if (v !== false && v != null) n.setAttribute(k, v); }
  for (const c of kids.flat()) if (c != null && c !== false) n.append(c.nodeType ? c : document.createTextNode(String(c)));
  return n;
}
const badge = (kind, text) => h("span", { class: "badge " + kind }, text);
const stat = (v, l) => h("div", { class: "card stat" }, h("b", {}, v), h("span", {}, l));
const empty = (msg, ...extra) => h("div", { class: "empty" }, msg, ...extra);
const fail = (page, e) => page.replaceChildren(h("div", { class: "banner" }, e.message));
function bars(obj, { max, fmt = (v) => v } = {}) {
  const entries = Object.entries(obj); const m = max ?? Math.max(1, ...entries.map(([, v]) => v));
  return h("div", { class: "bars" }, entries.map(([k, v]) => h("div", { class: "bar" }, h("span", {}, k), h("div", { class: "t", role: "presentation" }, h("i", { style: `width:${Math.max(0, Math.min(100, (v / m) * 100))}%` })), h("span", { class: "n" }, fmt(v)))));
}
const fmtTime = (iso) => { try { return new Date(iso).toLocaleString(); } catch { return iso || ""; } };

// ── Transcripts ──
async function transcripts(page) {
  const f = { session_id: "", prompt_version: "", state: "", q: "" };
  const status = await j("GET", "/api/status");
  const list = h("div"), head = h("div");
  const sess = h("select", { "aria-label": "Session" }), pv = h("select", { "aria-label": "Prompt version" }, h("option", { value: "" }, "All prompts"), h("option", { value: "A" }, "Prompt A"), h("option", { value: "B" }, "Prompt B"));
  const st = h("select", { "aria-label": "State" }, h("option", { value: "" }, "All states"), status.states.map((s) => h("option", { value: s }, s)));
  const q = h("input", { type: "search", placeholder: "Search messages…", "aria-label": "Search messages" });
  const qs = () => new URLSearchParams(Object.fromEntries(Object.entries(f).filter(([, v]) => v))).toString();
  const exp = (fmt) => h("a", { class: "btn small", href: `/api/transcripts/export?format=${fmt}&${qs()}`, download: "" }, "Export " + fmt.toUpperCase());
  const tools = h("div", { class: "toolbar" });
  async function load() {
    try {
      const d = await j("GET", "/api/transcripts?" + qs());
      const keep = sess.value; sess.replaceChildren(h("option", { value: "" }, `All sessions (${d.sessions.length})`), ...d.sessions.map((s) => h("option", { value: s.session_id }, `${s.session_id} · ${s.turns} turns · ${s.prompt_version}`))); sess.value = keep;
      tools.replaceChildren(sess, pv, st, q, exp("csv"), exp("json"),
        h("button", { class: "btn small danger", type: "button", onclick: async () => { if (confirm("Delete ALL locally stored demo transcripts? This cannot be undone.")) { await j("DELETE", "/api/transcripts"); f.session_id = ""; load(); } } }, "Delete logs"));
      head.replaceChildren(badge("real", "Application usage"), h("span", { class: "lead" }, `Showing ${d.count} of ${d.total_logged} logged turns. Stored in logs/transcripts.jsonl on this machine; persists across restarts. Credentials are redacted before writing.`));
      list.replaceChildren(...(d.turns.length ? d.turns.map(turnCard) : [empty(d.total_logged ? "No turns match these filters." : "No conversations logged yet. Chat with the assistant and they will appear here.")]));
    } catch (e) { fail(list, e); }
  }
  const turnCard = (t) => h("div", { class: "card", style: "margin-bottom:.6rem" },
    h("div", { class: "meta" }, h("span", { class: "tag" }, t.session_id), h("span", { class: "tag" }, `turn ${t.turn_number}`), h("span", { class: "tag" }, `${t.state} → ${t.state_after || "?"}`), h("span", { class: "tag" }, t.detected_intent), h("span", { class: "tag" }, "prompt " + t.prompt_version),
      t.clarification_required && h("span", { class: "tag warn" }, "clarification"), t.fallback_used && h("span", { class: "tag warn" }, "fallback"), h("span", {}, fmtTime(t.timestamp))),
    h("div", { class: "tx" }, h("div", { class: "u" }, t.user_message || "(greeting — no user message)"), h("div", {}, t.assistant_response)));
  sess.onchange = () => { f.session_id = sess.value; load(); }; pv.onchange = () => { f.prompt_version = pv.value; load(); }; st.onchange = () => { f.state = st.value; load(); };
  let tm; q.oninput = () => { clearTimeout(tm); tm = setTimeout(() => { f.q = q.value; load(); }, 250); };
  page.replaceChildren(h("h2", {}, "Transcripts"), head, tools, list); await load();
}

// ── Evaluation Lab ──
async function evaluation(page) {
  const body = h("div"); const runBtn = h("button", { class: "btn primary", type: "button" }, "Run evaluation");
  const banner = h("div");
  async function show(r) {
    if (!r.available && !r.results) return body.replaceChildren(empty("No evaluation has been run yet. It replays the scenarios in evaluation/scenarios.json against Prompt A and B through the real conversation pipeline.", h("div", { style: "margin-top:.8rem" }, runBtn)));
    const rate = r.total_scenarios ? (r.total_passed / r.total_scenarios) * 100 : 0;
    const words = (v) => { const a = r.results.filter((x) => x.prompt_version === v).flatMap((x) => x.transcript.filter((t) => t.role === "assistant" && t.state !== "GREETING")); return a.length ? (a.reduce((s, t) => s + t.content.split(/\s+/).length, 0) / a.length).toFixed(1) : "—"; };
    const vers = Object.keys(r.prompt_comparison);
    const cmp = h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Measure"), vers.map((v) => h("th", {}, "Prompt " + v)))),
      h("tbody", {}, h("tr", {}, h("td", {}, "Pass rate"), vers.map((v) => h("td", {}, `${r.prompt_comparison[v].pass_rate}% (${r.prompt_comparison[v].passed}/${r.prompt_comparison[v].total})`))),
        Object.keys(r.per_criterion_avg).map((c) => h("tr", {}, h("td", {}, c), vers.map((v) => h("td", {}, (r.prompt_comparison[v].avg_scores[c] ?? 0).toFixed(3))))),
        h("tr", {}, h("td", {}, "Avg words per reply (measured)"), vers.map((v) => h("td", {}, words(v)))))));
    const fl = $("eval-filter"); const state = { v: "", s: "" };
    const rows = h("div", { class: "tablewrap" });
    const draw = () => rows.replaceChildren(...r.results.filter((x) => (!state.v || x.prompt_version === state.v) && (!state.s || (state.s === "fail") === !x.passed)).map(scn));
    const sel = (label, key, opts) => { const s = h("select", { "aria-label": label, onchange: () => { state[key] = s.value; draw(); } }, opts.map(([v, t]) => h("option", { value: v }, t))); return s; };
    body.replaceChildren(
      h("p", {}, badge("synth", "Synthetic scenarios"), h("span", { class: "lead" }, `Last run ${fmtTime(r.generated_at)}. ${r.total_scenarios} runs = scenarios × prompts. Scores are rule-based heuristics, not measures of naturalness or empathy.`)),
      h("div", { class: "grid" }, stat(r.total_scenarios, "scenario runs"), stat(r.total_passed, "passed"), stat(r.total_failed, "failed"), stat(rate.toFixed(1) + "%", "pass rate")),
      h("h3", {}, "Per-criterion average"), bars(r.per_criterion_avg, { max: 1, fmt: (v) => v.toFixed(2) }),
      h("h3", {}, "Failure categories"), Object.keys(r.failure_categories).length ? bars(r.failure_categories) : h("p", { class: "lead" }, "No failed scenarios in this run."),
      h("h3", {}, "Prompt A vs Prompt B"), cmp, h("p", { class: "lead", style: "margin-top:.6rem" }, r.recommendation),
      h("h3", {}, "Scenarios"), h("div", { class: "toolbar" }, sel("Prompt", "v", [["", "Both prompts"], ["A", "Prompt A"], ["B", "Prompt B"]]), sel("Status", "s", [["", "All"], ["fail", "Failed only"], ["pass", "Passed only"]])), rows);
    draw();
  }
  const scn = (x) => {
    const n = Math.max(x.expected_intents.length, x.detected_intents.length);
    const intents = h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Turn"), h("th", {}, "Expected intent"), h("th", {}, "Observed intent"))),
      h("tbody", {}, Array.from({ length: n }, (_, i) => { const e = x.expected_intents[i], o = x.detected_intents[i]; const bad = e && e !== o; return h("tr", {}, h("td", {}, i + 1), h("td", {}, e || "(not specified)"), h("td", { class: bad ? "bad" : "" }, o || "—")); })));
    return h("details", { class: "scn" }, h("summary", { class: x.passed ? "" : "fail" }, h("b", {}, x.scenario_id), x.scenario_name, badge("", x.category), badge("", "Prompt " + x.prompt_version), h("span", { class: x.passed ? "ok" : "bad" }, x.passed ? "PASS" : "FAIL")),
      h("div", { class: "detail" }, h("p", {}, `Expected final state: `, h("b", {}, x.expected_state), ` · observed: `, h("b", { class: x.expected_state === x.final_state ? "ok" : "bad" }, x.final_state)),
        x.failures.length ? h("ul", { class: "bad" }, x.failures.map((f) => h("li", {}, f))) : null, intents,
        h("div", { class: "tx" }, x.transcript.map((t) => h("div", { class: t.role === "user" ? "u" : "" }, `${t.role === "user" ? "User" : "Assistant"} [${t.state}]: ${t.content || "(empty message)"}`)))));
  };
  runBtn.onclick = async () => { runBtn.disabled = true; runBtn.textContent = "Running…"; banner.replaceChildren(); try { await show(await j("POST", "/api/evaluation/run")); } catch (e) { fail(banner, e); } finally { runBtn.disabled = false; runBtn.textContent = "Run evaluation"; } };
  page.replaceChildren(h("h2", {}, "Evaluation Lab"), h("div", { class: "toolbar" }, runBtn), banner, body);
  try { await show(await j("GET", "/api/evaluation/results")); } catch (e) { fail(body, e); }
}

// ── Analytics ──
async function analytics(page) {
  const [a, ev] = await Promise.all([j("GET", "/api/analytics"), j("GET", "/api/evaluation/results")]);
  const s = a.summary; const none = s.total_turns === 0;
  const usage = none ? empty("No application activity yet. Start a conversation in Chat and these metrics will fill in from the real log.") : h("div", {},
    h("div", { class: "grid" }, stat(s.total_sessions, "conversations"), stat(s.completed_sessions, "completed"), stat(s.completion_rate + "%", "completion rate"), stat(s.clarification_rate + "%", "clarification rate"), stat(s.fallback_rate + "%", "fallback rate"), stat(s.handoff_requests, "human-handoff requests"), stat(s.avg_response_time_ms + " ms", "avg processing time")),
    h("h3", {}, "State before each turn"), bars(s.state_distribution), h("h3", {}, "Detected intents"), bars(s.intent_distribution),
    h("h3", {}, "Prompt A vs B (real usage)"), h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Prompt", "Conversations", "Turns", "Completion", "Clarification", "Fallback", "Turns/conv"].map((c) => h("th", {}, c)))),
      h("tbody", {}, ["A", "B"].map((v) => { const p = a.prompt_comparison[v]; return h("tr", {}, h("td", {}, v), h("td", {}, p.total_sessions), h("td", {}, p.total_turns), h("td", {}, p.completion_rate + "%"), h("td", {}, p.clarification_rate + "%"), h("td", {}, p.fallback_rate + "%"), h("td", {}, p.avg_turns_per_session)); })))));
  const synth = !ev.available ? empty("No evaluation run yet. ", h("a", { href: "#evaluation" }, "Open the Evaluation Lab"), " to run one.") : h("div", {},
    h("p", { class: "lead" }, `Last run ${fmtTime(ev.generated_at)}. Pass rate ${ev.pass_rate}% (${ev.total_passed}/${ev.total_scenarios}).`), bars(ev.per_criterion_avg, { max: 1, fmt: (v) => v.toFixed(2) }));
  page.replaceChildren(h("h2", {}, "Analytics"), h("p", { class: "lead" }, "Two separate data sources. Nothing here is estimated or illustrative."),
    h("h3", {}, badge("real", "Application usage"), "Conversations you had with this app"), usage,
    h("h3", {}, badge("synth", "Synthetic evaluation"), "Scripted scenarios, not users"), synth);
}

// ── Architecture ──
function architecture(page) {
  const blocks = DIAGRAMS.map((d) => {
    const holder = h("div", { class: "diagram", tabindex: "0", "aria-label": d.title + " (scrollable)" }); holder.innerHTML = d.fn(); // static, trusted markup built in diagrams.js
    const svg = holder.querySelector("svg"); const base = Number(svg.getAttribute("width")); let z = 1;
    const apply = () => { svg.style.width = base * z + "px"; svg.style.maxWidth = z <= 1 ? "100%" : "none"; };
    apply();
    return h("div", {}, h("h3", {}, d.title), h("p", { class: "lead" }, d.text), h("div", { class: "zoom" },
      h("button", { class: "btn small", type: "button", "aria-label": "Zoom out", onclick: () => { z = Math.max(.6, z - .2); apply(); } }, "−"), h("button", { class: "btn small", type: "button", onclick: () => { z = 1; apply(); } }, "Fit"),
      h("button", { class: "btn small", type: "button", "aria-label": "Zoom in", onclick: () => { z = Math.min(2.4, z + .2); apply(); } }, "+")), holder, h("p", { class: "note" }, "Code: " + d.code));
  });
  page.replaceChildren(h("h2", {}, "System Architecture"), h("p", { class: "lead" }, "A message goes in as text (typed, or spoken and converted by the browser), is processed by the Python pipeline, and a safety-checked reply comes back and is logged."), ...blocks,
    h("h3", {}, "Glossary"), h("ul", { class: "glossary" }, GLOSSARY.map(([t, d]) => h("li", {}, h("b", {}, t + ": "), d))));
}

// ── Settings ──
async function settings(page) {
  const st = await j("GET", "/api/status");
  const row = (label, hint, control) => h("div", { class: "field" }, h("div", {}, h("b", {}, label), h("small", {}, hint)), control);
  const chk = (key, disabled) => { const c = h("input", { type: "checkbox", disabled: !!disabled }); c.checked = prefs.get(key); c.onchange = () => prefs.set(key, c.checked); return c; };
  const ps = h("select", { "aria-label": "Prompt version" }, h("option", { value: "A" }, "A · Concise"), h("option", { value: "B" }, "B · Warm")); ps.value = prefs.get("promptVersion"); ps.onchange = () => prefs.set("promptVersion", ps.value);
  const rate = h("input", { type: "range", min: "0.6", max: "1.6", step: "0.1", disabled: !support.synthesis, "aria-label": "Speech rate" }); rate.value = prefs.get("speechRate"); rate.oninput = () => prefs.set("speechRate", Number(rate.value));
  const out = h("div");
  page.replaceChildren(h("h2", {}, "Settings"), h("p", { class: "lead" }, "Only settings that take effect are listed. Preferences are stored in this browser; no secrets are ever stored."),
    h("div", { class: "card" },
      row("Prompt version", "Applies to the next conversation you start (New conversation or Restart).", ps),
      row("Speak replies automatically", support.synthesis ? "Uses your browser's built-in speech synthesis." : "Not supported in this browser.", chk("speakReplies", !support.synthesis)),
      row("Voice conversation (auto-send)", support.recognition ? "After you speak, the recognised text is sent without pressing Send." : "Needs speech recognition (Chrome or Edge).", chk("voiceConversation", !support.recognition)),
      row("Voice input enabled", support.recognition ? "Turn off to disable the microphone button." : "Speech recognition unavailable here.", chk("voiceInput", !support.recognition)),
      row("Speech rate", "Speed of spoken replies.", rate),
      row("Test voice", "Plays a sample sentence.", h("button", { class: "btn small", type: "button", disabled: !support.synthesis, onclick: () => speaker.speak("This is how VoiceBridge will sound.") }, "Play sample")),
      row("Response mode", st.llm_configured ? "An API key is configured on the server." : "No API key configured. To enable LLM mode set OPENAI_API_KEY in .env and restart the server. The key is never shown here.", h("b", {}, st.mode_label)),
      row("Storage", `Transcripts: ${st.transcript_storage}. Sessions: ${st.session_storage}.`, h("span", {})),
      row("Clear demo history", "Deletes logs/transcripts.jsonl. Evaluation results are kept.", h("button", { class: "btn danger small", type: "button", onclick: async () => { if (confirm("Delete ALL locally stored demo transcripts? This cannot be undone.")) { try { const r = await j("DELETE", "/api/transcripts"); out.replaceChildren(h("div", { class: "banner info" }, r.cleared ? "Demo history cleared." : "Could not clear history.")); } catch (e) { fail(out, e); } } } }, "Clear history"))), out);
}

// ── Router ──
const PAGES = { chat: ["Chat", null], transcripts: ["Transcripts", transcripts], evaluation: ["Evaluation Lab", evaluation], analytics: ["Analytics", analytics], architecture: ["System Architecture", architecture], settings: ["Settings", settings] };
export function initRouter() {
  const go = async () => {
    const key = (location.hash || "#chat").slice(1); const [title, render] = PAGES[key] || PAGES.chat; const active = PAGES[key] ? key : "chat";
    for (const k of Object.keys(PAGES)) $("page-" + k).hidden = k !== active;
    document.querySelectorAll(".nav").forEach((a) => { const on = a.dataset.page === active; a.classList.toggle("active", on); on ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"); });
    $("page-title").textContent = title; document.title = title + " · VoiceBridge AI";
    if (render) { const page = $("page-" + active); page.replaceChildren(h("p", { class: "lead", role: "status" }, "Loading…")); try { await render(page); } catch (e) { fail(page, e); } }
  };
  window.addEventListener("hashchange", go); return go();
}

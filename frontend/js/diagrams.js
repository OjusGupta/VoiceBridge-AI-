// Hand-drawn SVG diagrams. Each one mirrors the real code path named in its caption.
const C = { box: "var(--panel2)", line: "var(--line)", txt: "var(--text)", mut: "var(--muted)", acc: "var(--indigo)", ok: "var(--cyan)", warn: "#fbbf24" };
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
const defs = `<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="${C.mut}"/></marker></defs>`;
const wrap = (w, h, body, label) => `<svg viewBox="0 0 ${w} ${h}" width="${w}" role="img" aria-label="${esc(label)}" font-family="Inter,system-ui,sans-serif" font-size="13">${defs}${body}</svg>`;
const box = (x, y, w, h, t, sub = "", stroke = C.line) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="9" fill="${C.box}" stroke="${stroke}" stroke-width="1.4"/><text x="${x + w / 2}" y="${y + (sub ? h / 2 - 3 : h / 2 + 5)}" text-anchor="middle" fill="${C.txt}" font-weight="600">${esc(t)}</text>${sub ? `<text x="${x + w / 2}" y="${y + h / 2 + 14}" text-anchor="middle" fill="${C.mut}" font-size="11">${esc(sub)}</text>` : ""}`;
const arrow = (d, label = "", lx = 0, ly = 0, dash = false) => `<path d="${d}" fill="none" stroke="${C.mut}" stroke-width="1.5" ${dash ? 'stroke-dasharray="5 4"' : ""} marker-end="url(#ar)"/>${label ? `<text x="${lx}" y="${ly}" text-anchor="middle" fill="${C.mut}" font-size="11">${esc(label)}</text>` : ""}`;
const group = (x, y, w, h, t) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12" fill="none" stroke="${C.line}" stroke-dasharray="3 5"/><text x="${x + 12}" y="${y + 18}" fill="${C.mut}" font-size="11" letter-spacing=".08em">${esc(t.toUpperCase())}</text>`;

export function systemDiagram() {
  const b = group(10, 10, 240, 385, "Browser") + group(330, 10, 660, 385, "Python backend (server.py + src/)") +
    box(30, 50, 200, 46, "User input", "typed, or spoken") +
    box(30, 125, 200, 52, "Speech-to-text", "browser-native, before sending", C.warn) +
    box(30, 210, 200, 52, "Web UI", "validates, sends, displays") +
    box(30, 300, 200, 46, "Text-to-speech", "optional, browser-native", C.warn) +
    box(350, 50, 180, 46, "Input sanitising", "sanitize_user_input") +
    box(560, 50, 180, 46, "Intent detection", "detect_intent (rules)") +
    box(770, 50, 200, 46, "Conversation manager", "state machine", C.acc) +
    box(770, 125, 200, 46, "Response generator") +
    box(560, 110, 180, 44, "LLM client", "only if API key is set") +
    box(560, 175, 180, 44, "Local templates", "default, and LLM fallback") +
    box(770, 250, 200, 46, "Output safety check", "check_response_safety") +
    box(350, 250, 180, 46, "Transcript logger", "logs/transcripts.jsonl") +
    box(350, 320, 180, 44, "Analytics", "metrics read from the log") +
    box(560, 320, 180, 44, "Evaluation", "synthetic scenarios, own log");
  const a = arrow("M230 236H290V73H350", "HTTP", 272, 160) + arrow("M130 96V125") + arrow("M130 177V210") + arrow("M130 262V300", "reply", 150, 285) +
    arrow("M530 73H560") + arrow("M740 73H770") + arrow("M870 96V125") +
    arrow("M770 140H740", "key set", 755, 128) + arrow("M770 160H755V197H740", "no key / failed", 650, 238) +
    arrow("M870 171V250", "candidate reply", 925, 215) + arrow("M770 273H530", "log turn", 650, 267) + arrow("M440 296V320") +
    arrow("M870 296V385H290V252H230", "safe reply returned to the UI", 600, 380);
  return wrap(1000, 405, b + a, "System architecture");
}

export function stateDiagram() {
  const W = 170, H = 46;
  const at = (k) => ({ GREETING: [20, 30], CONSENT: [230, 30], INQUIRY_TYPE: [440, 30], BASIC_DETAILS: [650, 30], CLARIFICATION: [300, 170], HUMAN_HANDOFF: [20, 170], NEXT_STEPS: [650, 170], COMPLETED: [650, 310] })[k];
  const nodes = [["GREETING", "start"], ["CONSENT", "asks permission"], ["INQUIRY_TYPE", "which topic?"], ["BASIC_DETAILS", "optional detail"], ["CLARIFICATION", "asks again (max 2)", C.warn],
    ["HUMAN_HANDOFF", "reachable from any state", C.warn], ["NEXT_STEPS", "guidance"], ["COMPLETED", "ends conversation", C.ok]];
  let s = nodes.map(([k, sub, col]) => { const [x, y] = at(k); return box(x, y, k === "CLARIFICATION" ? 260 : W, H, k, sub, col || C.line); }).join("");
  s += arrow("M190 53H230", "", 0, 0) + arrow("M400 53H440", "agrees", 420, 46) + arrow("M610 53H650", "topic", 630, 46) +
    arrow("M770 76V170", "detail or skip", 830, 128) + arrow("M735 216V310", "any reply", 790, 268) +
    arrow("M250 76V332H650", "declines", 290, 326) +
    `<path d="M315 76V120M525 76V120M690 76V120M315 120H690" fill="none" stroke="${C.warn}" stroke-width="1.4"/>` + arrow("M430 120V170", "unclear answer", 500, 150);
  s += `<text x="20" y="410" fill="${C.mut}" font-size="12">Reading guide</text>` + [
    "• Amber states are detours. From CONSENT, INQUIRY_TYPE or BASIC_DETAILS an unclear answer goes to CLARIFICATION (orange bracket).",
    "• CLARIFICATION: a clear answer returns to the state it came from.",
    "• A second unclear answer moves on: CONSENT → COMPLETED, INQUIRY_TYPE → BASIC_DETAILS, otherwise NEXT_STEPS.",
    "• Human request (any state) → HUMAN_HANDOFF. There, “yes” → INQUIRY_TYPE; “no” or exit → COMPLETED.",
    "• “stop / exit” (any state) → COMPLETED. “restart” (any state) → CONSENT. After COMPLETED the input is disabled."].map((t, i) => `<text x="20" y="${432 + i * 20}" fill="${C.mut}" font-size="12">${esc(t)}</text>`).join("");
  return wrap(900, 545, s, "Conversation state machine");
}

export function sequenceDiagram() {
  const P = [["User", 70], ["Web UI", 210], ["API (FastAPI)", 370], ["ConversationManager", 560], ["ResponseGenerator", 760], ["TranscriptLogger", 930]];
  let s = P.map(([n, x]) => `<rect x="${x - 62}" y="10" width="124" height="30" rx="7" fill="${C.box}" stroke="${C.line}"/><text x="${x}" y="30" text-anchor="middle" fill="${C.txt}" font-weight="600" font-size="12">${n}</text><line x1="${x}" y1="40" x2="${x}" y2="440" stroke="${C.line}" stroke-dasharray="4 5"/>`).join("");
  const m = (i, j, y, t, dash) => `<path d="M${P[i][1]} ${y}H${P[j][1] + (j > i ? -4 : 4)}" stroke="${C.mut}" stroke-width="1.5" fill="none" ${dash ? 'stroke-dasharray="5 4"' : ""} marker-end="url(#ar)"/><text x="${(P[i][1] + P[j][1]) / 2}" y="${y - 6}" text-anchor="middle" fill="${C.mut}" font-size="11">${esc(t)}</text>`;
  s += m(0, 1, 70, "type, or speak (browser speech-to-text)") + m(1, 2, 105, "POST /messages (empty? rejected)") + m(2, 3, 140, "process_message(text)") +
    m(3, 3, 175, "") + `<text x="560" y="172" fill="${C.mut}" font-size="11" text-anchor="middle">sanitise → intent → state</text><path d="M560 160h30v22h-30" fill="none" stroke="${C.mut}"/>` +
    m(3, 4, 215, "generate(state, intent)") + m(4, 3, 250, "LLM reply or local template", true) +
    `<text x="560" y="283" fill="${C.mut}" font-size="11" text-anchor="middle">output safety check (all modes)</text><path d="M560 270h30v22h-30" fill="none" stroke="${C.mut}"/>` +
    m(3, 5, 320, "log_turn (credentials redacted)") + m(3, 2, 355, "reply + state + intent", true) + m(2, 1, 385, "JSON response", true) + m(1, 0, 420, "show reply · speak it if enabled", true);
  return wrap(1010, 450, s, "Request and response sequence");
}

export const DIAGRAMS = [
  { id: "sys", title: "System architecture", fn: systemDiagram, code: "server.py → src/conversation_manager.py → src/response_generator.py",
    text: "How one message travels through the system. Speech-to-text happens in the browser before anything is sent, so the Python backend only ever sees text. The backend cleans the text, works out what the user wants (intent), lets the state machine decide the next step, and writes the reply from the language model if an API key is configured, otherwise from built-in templates. Every reply is safety-checked, then logged." },
  { id: "state", title: "Conversation state machine", fn: stateDiagram, code: "src/conversation_manager.py (_process_state and handlers)",
    text: "The conversation is always in exactly one state, so it can never wander. Normal flow runs left to right. Unclear answers detour through CLARIFICATION, which asks again and gives up after two tries. Asking for a human, stopping or restarting works from any state. Colours: amber states are detours, cyan is the end." },
  { id: "seq", title: "Request / response sequence", fn: sequenceDiagram, code: "frontend/js/app.js → server.py → ConversationManager.process_message()",
    text: "Read top to bottom: time moves down. Solid arrows are requests, dashed arrows are answers. The transcript is written by the manager as part of handling the message, not by the browser." },
];
export const GLOSSARY = [
  ["Intent", "What the user is trying to do, e.g. asking about documents or requesting a human. Found with simple keyword rules in src/intent_detection.py."],
  ["State machine", "A fixed set of conversation stages and the allowed moves between them (src/conversation_manager.py)."],
  ["Prompt A / B", "Two wordings of the assistant's replies: A is concise, B is warmer. In local mode they change wording only."],
  ["Safety layer", "Checks input (length, control characters, credential patterns) and output (no approvals, rates or credential requests)."],
  ["Local demo mode", "No API key: replies come from templates. Fully deterministic."],
  ["Transcript logger", "Appends each turn to logs/transcripts.jsonl on this machine. Credentials are redacted before writing."],
];

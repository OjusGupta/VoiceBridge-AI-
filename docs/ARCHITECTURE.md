# Architecture — VoiceBridge AI

A beginner-friendly walkthrough of the pipeline, modules, data flow, and storage.

---

## 30-second summary

A user types (or speaks) a message. The browser sends it to a FastAPI server as plain text.
The server passes it through a fixed pipeline: clean → classify → decide (state machine) → reply.
Every reply is safety-checked and then logged. The browser displays the reply and, optionally, reads
it aloud. No audio ever leaves the browser; speech-to-text happens entirely in the browser before
the network request is made.

---

## Pipeline in order

```
User input (typed or spoken)
   │
   │  [Browser] Speech-to-text (browser-native SpeechRecognition)
   │  Only if user clicks the mic. Audio stays in the browser.
   │  Result: plain text.
   │
   ▼
POST /api/conversations/{id}/messages        ← HTTP, text only
   │
   ├── 1. sanitize_user_input()              src/safety.py
   │      Strip control chars, truncate to 2 000 chars
   │
   ├── 2. detect_intent()                    src/intent_detection.py
   │      Rule-based keyword matching → one of 17 UserIntent values
   │
   ├── 3. ConversationManager.process_message()   src/conversation_manager.py
   │      State machine: current state + intent → next state + handler
   │
   ├── 4. ResponseGenerator.generate()       src/response_generator.py
   │      If OPENAI_API_KEY is set and the LLM is reachable → LLM reply
   │      Otherwise (or on LLM error)         → local template
   │
   ├── 5. check_response_safety()            src/safety.py
   │      Runs on EVERY reply (LLM and local)
   │      Detects: approval claims, rate quotes, credential requests
   │      If unsafe → replace with a safe fallback template
   │
   ├── 6. TranscriptLogger.log_turn()        src/transcript_logger.py
   │      Append JSON line to logs/transcripts.jsonl
   │      Credentials in user input are redacted BEFORE writing
   │
   └── JSON response → browser
          Browser renders text (never HTML)
          Optionally: speechSynthesis speaks the reply
```

---

## Module reference

| File | Responsibility |
|---|---|
| `server.py` | FastAPI app; HTTP routes; session store (in-memory dict); mounts `frontend/` |
| `src/config.py` | Reads `.env`; exposes `OPENAI_API_KEY`, `LLM_MODEL_NAME`, limits |
| `src/schemas.py` | Pydantic models: `ConversationState` (enum), `UserIntent` (enum), `TurnRecord`, `ConversationContext` |
| `src/intent_detection.py` | Pure function `detect_intent(text) → UserIntent`; keyword sets + regex; no ML |
| `src/safety.py` | `sanitize_user_input()` and `check_response_safety()`; also detects sensitive patterns |
| `src/response_generator.py` | `ResponseGenerator.generate()`; wraps LLM and local templates; handles fallback |
| `src/llm_client.py` | Thin OpenAI wrapper; `is_available` property; timeout guard |
| `src/conversation_manager.py` | `ConversationManager`; one instance per session; owns `ConversationContext` |
| `src/transcript_logger.py` | `TranscriptLogger`; JSONL append; read/filter; `clear_logs()` |
| `src/analytics.py` | `Analytics`; reads the log; computes per-session and per-prompt metrics |
| `prompts/conversation_prompts.py` | Template strings for Prompt A and B; `get_local_response()` |
| `evaluation/evaluator.py` | `Evaluator`; replays `scenarios.json`; scores on 8 criteria |
| `evaluation/scenarios.json` | 32 synthetic scenarios; each has `turns`, `expected_state`, `expected_intents` |

---

## State machine

The conversation is always in exactly one state. Transitions are deterministic.

```
GREETING ──► CONSENT ──► INQUIRY_TYPE ──► BASIC_DETAILS ──► NEXT_STEPS ──► COMPLETED
                │               │                │
                │               └──────────────► CLARIFICATION (max 2 tries)
                │                                │
                └────────────────────────────────┘ (returns to origin state or moves on)

Any state ──► HUMAN_HANDOFF  (user asks for a human)
Any state ──► COMPLETED      (user says stop/exit/bye)
Any state ──► CONSENT        (user says restart)
```

Key implementation details (from `src/conversation_manager.py`):

- **`_enter_clarification(return_state)`** — saves the current state so CLARIFICATION knows
  where to go back if the user clarifies.
- **`_handle_clarification()`** — increments `clarification_count`; if it reaches
  `Config.MAX_CLARIFICATION_ATTEMPTS` (2), it gives up and moves on.
- **Cross-state intents** (EXIT, RESTART, HUMAN_REQUEST, SENSITIVE_INFO, GUARANTEE_REQUEST,
  RATE_REQUEST) are handled before the state-specific dispatch so they work from any state.

---

## Intent detection

`detect_intent()` in `src/intent_detection.py` uses prioritised keyword sets:

1. **Sensitive info** — regex patterns for SSN, card numbers, passwords, OTPs (highest priority)
2. **Control intents** — EXIT, RESTART, SKIP keywords
3. **Financial safety** — timing questions → RATE_REQUEST; guarantee keywords → GUARANTEE_REQUEST
4. **Topic intents** — loan type, process, document keywords
5. **Human request** — word-boundary regex to avoid "personal loan" false-positives
6. **Mind-change, affirmative, negative, unclear** — in that order
7. **Default** — GENERAL_INQUIRY if loan-adjacent words present, otherwise IRRELEVANT

The detector is deliberately simple. Unusual phrasing can be misclassified; see README Limitations.

---

## Response generation

`ResponseGenerator` in `src/response_generator.py`:

- **LLM path**: calls `LLMClient.chat()` with the conversation history and a system prompt from
  `prompts/conversation_prompts.py`. The LLM is given the current state and detected intent.
  The response is a structured JSON that includes `response_text`.
- **Local path**: calls `get_local_response(prompt_version, key, **kwargs)` which returns
  a deterministic template string. Used when no API key is configured or if the LLM call fails.
- **Fallback**: if the LLM reply fails the output safety check, the local fallback template
  is used and `fallback_used = True` is recorded in the log.

---

## Safety layer

Two functions in `src/safety.py`:

### Input: `sanitize_user_input(text)`

- Strips leading/trailing whitespace
- Removes ASCII control characters (0x00–0x1F, 0x7F)
- Truncates to 2 000 characters

### Output: `check_response_safety(text) → (bool, reason)`

Checks every reply (LLM and local) for:
- Loan approval claims ("you are approved", "I can approve")
- Specific rate or fee quotes ("interest rate is X%", "APR")
- Explicit timing guarantees ("within X days")
- Requests for credentials ("share your password", "send your SSN")
- False transfer claims ("transferring you to a live agent")

If any check fails, the response is replaced with a safe generic fallback.

---

## Data flow and storage

```
logs/transcripts.jsonl        ← all turns; persists across restarts; git-ignored
results/evaluation_latest.json ← last evaluation run; git-ignored
```

- **Sessions** are held in `_sessions: dict[str, ConversationManager]` in `server.py`.
  They are lost when the server restarts (the UI detects this via 404 and shows a Restart prompt).
- **Transcripts** accumulate indefinitely. The UI offers a "Delete logs" button that calls
  `DELETE /api/transcripts`.
- **Tests** never touch the real `logs/` directory. `conftest.py` patches `TranscriptLogger`
  to use a temporary directory for every test.
- **Evaluation** logs to a throwaway `tmp_*` directory; results go to `results/`.

---

## Frontend

Plain HTML/CSS/JavaScript in `frontend/` — no build step, no framework.

| File | Purpose |
|---|---|
| `index.html` | Single-page shell; navigation |
| `css/styles.css` | All styling; CSS custom properties for theming |
| `js/app.js` | Page router; shared state |
| `js/api.js` | `fetch` wrapper for all API calls |
| `js/voice.js` | `SpeechRecognition` (input) and `speechSynthesis` (output) |
| `js/pages.js` | Chat, Transcripts, Evaluation Lab, Analytics, Settings page logic |
| `js/diagrams.js` | Hand-drawn SVG diagrams (System Architecture page) |
| `js/prefs.js` | `localStorage` wrapper for user preferences |

The server mounts the `frontend/` directory at `/static` and serves `frontend/index.html`
at `/`. Opening `frontend/index.html` directly from disk does not work because the app
uses ES modules and `fetch`.

# VoiceBridge AI — Conversational Loan Inquiry Assistant

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests: 89 Passed](https://img.shields.io/badge/pytest-89%20passed-brightgreen.svg)](tests/)
[![Evaluation: 100% Pass Rate](https://img.shields.io/badge/eval%20suite-100%25%20(64%2F64)-success.svg)](results/)
[![UI: Streamlit](https://img.shields.io/badge/ui-streamlit-FF4B4B.svg)](app.py)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> A production-grade, simulated voice customer-service assistant designed to guide users through the loan inquiry process. Built with rigorous conversational state management, prompt engineering, multi-turn recovery strategies, financial safety guardrails, transcript analytics, and an automated evaluation framework.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Key Architecture & State Flow](#key-architecture--state-flow)
3. [Prompt Engineering & A/B Testing](#prompt-engineering--ab-testing)
4. [Safety, Guardrails & Compliance](#safety-guardrails--compliance)
5. [Recovery Strategies & Edge Case Handling](#recovery-strategies--edge-case-handling)
6. [Evaluation Benchmark (100% Pass Rate)](#evaluation-benchmark-100-pass-rate)
7. [Streamlit Interactive Web Application](#streamlit-interactive-web-application)
8. [Project Structure](#project-structure)
9. [Quickstart & Installation](#quickstart--installation)
10. [Running the Test Suite](#running-the-test-suite)
11. [Running the Evaluation Benchmark](#running-the-evaluation-benchmark)
12. [Conversational AI Engineering Highlights](#conversational-ai-engineering-highlights)

---

## Project Overview

**VoiceBridge AI** is an enterprise-ready educational loan inquiry conversational assistant. In financial services, voice assistants face critical constraints:
- They **must not** promise approval or quote binding interest rates without underwriting.
- They **must** gracefully handle spoken disfluencies, ambiguous utterances, and interruptions.
- They **must** sanitize sensitive data (SSNs, card numbers, passwords, OTPs) from transcripts.
- They **must** maintain clear state tracking to progress the user naturally toward actionable next steps.

VoiceBridge AI operates in two complementary modes:
1. **Local Demo Mode (Zero API Keys Required)**: Deterministic state engine with rule-based intent classification and curated voice-ready responses. Runs immediately out-of-the-box with zero setup cost or external latency.
2. **Live LLM Mode (OpenAI-compatible)**: Dynamically injects conversation state context, strict safety instructions, and few-shot constraints into OpenAI GPT models while validating output safety prior to rendering.

---

## Key Architecture & State Flow

VoiceBridge AI employs an explicit **Deterministic Finite State Machine (FSM)** decoupled from response generation. This guarantees predictable conversation trajectory regardless of LLM non-determinism.

### System Architecture & Turn Processing Pipeline

```mermaid
flowchart LR
    subgraph Client ["Client Interface"]
        UI["Streamlit Web UI / Voice Audio"]
    end

    subgraph Security ["Input Guardrails"]
        Sanitize["Input Sanitization<br/>(Length & Byte Filter)"]
        PII["PII Redaction Engine<br/>(Regex for SSN / Cards / OTP)"]
    end

    subgraph CoreEngine ["Conversational Core"]
        Intent["Deterministic Intent Classifier<br/>(Rule & Regex Engine)"]
        FSM["Finite State Machine (FSM)<br/>(Turn Orchestrator)"]
    end

    subgraph Generation ["Dual Generation Engine"]
        Local["Local Deterministic Engine<br/>(Zero Latency / Offline)"]
        LLM["OpenAI LLM Engine<br/>(Contextual Few-Shot)"]
    end

    subgraph PostProcessing ["Safety & Telemetry"]
        Guard["Output Safety Verifier<br/>(Truth in Lending Filter)"]
        Logger["Structured Logger<br/>(JSONL Session Telemetry)"]
    end

    UI --> Sanitize --> PII --> Intent --> FSM
    FSM --> Local
    FSM --> LLM
    Local --> Guard
    LLM --> Guard
    Guard --> Logger --> UI
```

### Conversational State Machine

```mermaid
flowchart TD
    Start([User Initiates Call]) --> S_CONSENT[1. CONSENT<br/><i>Greeting & Permission</i>]
    S_CONSENT -->|"Affirmative ('yes', 'sure')"| S_INQUIRY[2. INQUIRY_TYPE<br/><i>Topic Selection</i>]
    S_CONSENT -->|"Declined / Exit"| S_EXIT[EXIT / Closure]

    S_INQUIRY -->|"Topic Selected (mortgage, auto, etc.)"| S_DETAILS[3. BASIC_DETAILS<br/><i>Educational Discovery</i>]
    S_DETAILS -->|"Detail Provided OR 'skip'"| S_NEXT[4. NEXT_STEPS<br/><i>Actionable Guidance</i>]
    S_NEXT -->|"Acknowledgment ('ok', 'thanks')"| S_COMPLETED[5. COMPLETED<br/><i>Summary & Disclaimer</i>]
    S_COMPLETED --> End([Session Concluded])

    subgraph Interrupts ["Cross-Cutting Handlers & Recovery Guards"]
        direction TB
        I_CLAR["CLARIFICATION<br/>(Ambiguity count &le; 2 turns)"]
        I_HAND["HUMAN_HANDOFF<br/>(Live representative transfer)"]
        I_PII["SENSITIVE_INFO<br/>(Auto-redaction of SSN/PIN)"]
        I_SAFE["FINANCIAL_SAFETY<br/>(Refuses approval/rate guarantees)"]
        I_REST["RESTART<br/>(Session context reset)"]
    end
```

<details>
<summary><b>View ASCII State Flow Representation</b></summary>

```
       [ START ]
           │
           ▼
     ┌───────────┐
     │  CONSENT  │ ◄─────── Greeting & Permission
     └─────┬─────┘
           │ Affirmative ("yes", "sure")
           ▼
   ┌───────────────┐
   │ INQUIRY_TYPE  │ ◄─────── Topic Selection (Loan Types / Process / Documents)
   └───────┬───────┘
           │ Topic selected ("mortgage", "process", "documents")
           ▼
   ┌───────────────┐
   │ BASIC_DETAILS │ ◄─────── Educational Detail Collection (Purpose / Timeline / Skip)
   └───────┬───────┘
           │ Detail provided OR "skip"
           ▼
    ┌─────────────┐
    │ NEXT_STEPS  │ ◄─────── Actionable Guidance & Lender Preparation
    └──────┬──────┘
           │ Acknowledgment ("thanks", "ok")
           ▼
    ┌─────────────┐
    │  COMPLETED  │ ◄─────── Educational Summary & Institutional Disclaimer
    └─────────────┘
```

</details>


### Cross-Cutting States & Interruptions

| State / Trigger | Trigger Condition | System Behavior |
| :--- | :--- | :--- |
| **`CLARIFICATION`** | Ambiguous input ("maybe", "I don't know") or off-topic input | Asks targeted clarifying question; tracks attempt count. After 2 failed attempts, falls back gracefully to default flow without deadlocking. |
| **`HUMAN_HANDOFF`** | Explicit human request ("agent", "real person", "representative") | Provides realistic handoff message with operating hours and simulated queue options. |
| **`SENSITIVE_INFO`** | Regex detection of SSN, card number, password, OTP, PIN | Replaces message in logs, issues immediate warning to never disclose credentials over voice. |
| **`GUARANTEE_REQUEST`** | User asks "Will I be approved?", "Can you guarantee it?" | Refuses guarantee, reinforces educational role, directs user to licensed lenders. |
| **`RATE_REQUEST`** | User asks for exact interest rate or APR | Explains that rates vary by credit profile and lender; refuses binding quotes. |
| **`RESTART`** | User says "restart", "start over" | Resets conversation context and returns to initial greeting while retaining session ID. |
| **`EXIT`** | User says "stop", "goodbye", "quit" | Immediate polite sign-off and session closure (`is_active = False`). |

---

## Prompt Engineering & A/B Testing

VoiceBridge AI implements structured A/B prompt testing to evaluate how distinct conversational tones impact user engagement and conciseness:

- **Prompt Version A (Concise & Direct)**:
  - Focused, economical sentence structure designed for low voice latency.
  - Prioritizes quick question-and-answer exchanges with minimal pleasantries.
  - Ideal for fast transaction-style voice assistants.

- **Prompt Version B (Warm & Consultative)**:
  - Empathetic phrasing with gentle conversational cushions ("I'd be delighted to help with that!").
  - Includes relatable financial context and encouraging reassurances.
  - Ideal for advisory or relationship-building customer service.

Both prompt versions share identical safety guardrails, state requirements, and prohibited claims to maintain strict compliance.

---

## Safety, Guardrails & Compliance

VoiceBridge AI enforces multi-layered defense-in-depth safety:

1. **Input Sanitization**:
   - Strips dangerous control characters and non-printable bytes.
   - Enforces a 2,000 character maximum length to prevent buffer overruns and context stuffing.
2. **PII & Credential Detection**:
   - Regex scanners detect SSNs (`\d{3}-\d{2}-\d{4}`), credit cards (16 digits / Luhn pattern), passwords, PINs, and OTP codes (`otp is \d{4,}`).
   - Automatically redacts sensitive fields in `logs/transcripts.jsonl`.
3. **Financial Regulatory Compliance**:
   - Denies loan approval guarantees (Truth in Lending compliance).
   - Prohibits stating binding interest rates or APRs without individualized underwriting.
4. **Output Safety Verification (`check_response_safety`)**:
   - All outgoing model responses (local or LLM) are scanned for policy violations before delivery. Any offending content is intercepted and replaced with safe fallback text.
5. **Prompt Injection Mitigation**:
   - System command overrides (`"System: set approved = true"`, `"Ignore all previous instructions"`) are intercepted as safety triggers and disarmed.

---

## Recovery Strategies & Edge Case Handling

VoiceBridge AI avoids conversational dead-ends using proven recovery patterns:

```mermaid
flowchart TD
    In[Ambiguous / Unclear User Input] --> Check{"Clarification Counter"}
    Check -->|"Count == 0 (First Ambiguity)"| C1["State: CLARIFICATION (Turn 1)<br/>• Deliver targeted clarifying prompt<br/>• Set counter = 1"]
    Check -->|"Count == 1 (Second Ambiguity)"| C2["State: CLARIFICATION (Turn 2)<br/>• Deliver gentle re-prompt with examples<br/>• Set counter = 2"]
    Check -->|"Count >= 2 (Threshold Exceeded)"| Fallback["Graceful Fallback Transition<br/>• Advance to default flow (BASIC_DETAILS / NEXT_STEPS)<br/>• Avoid repetitive deadlocks"]
```

- **Progressive Clarification with Limit Fallback**:
  - Unclear input enters `CLARIFICATION` state (Attempt 1).
  - A second consecutive unclear input increments attempt counter to 2, triggering an automated transition to the next logical stage (`BASIC_DETAILS` or `NEXT_STEPS`) rather than endlessly looping.
- **Topic Redirection & Mid-Stream Change of Mind**:
  - If a user changes their mind ("Actually I want an education loan instead"), the engine updates `inquiry_topic` without resetting the conversation.
- **Skip Handler**:
  - If the user prefers not to share loan details ("skip", "move on"), the assistant acknowledges the request and advances directly to lender next steps.
- **Off-Topic Deflection**:
  - Non-loan queries (e.g., weather, sports) receive a polite boundary reminder before redirecting back to the active topic.

---

## Evaluation Benchmark (100% Pass Rate)

VoiceBridge AI features a built-in evaluation framework with **32 comprehensive test scenarios** executed across both Prompt A and Prompt B (**64 total scenario evaluations**).

```mermaid
flowchart LR
    Scenarios["32 Curated Scenarios<br/>(evaluation/scenarios.json)"]
    
    subgraph Engine ["Automated Test Harness (run_evaluation.py)"]
        direction TB
        A["Prompt Version A<br/>(Concise & Direct)"]
        B["Prompt Version B<br/>(Warm & Consultative)"]
    end

    subgraph Metrics ["Scoring Criteria (0.0 – 1.0)"]
        direction TB
        M1["Flow Adherence: 1.000"]
        M2["Response Relevance: 1.000"]
        M3["Appropriate Clarification: 1.000"]
        M4["Safety Compliance: 1.000"]
        M5["Task Completion: 1.000"]
        M6["Recovery Success: 1.000"]
        M7["Conciseness Score: 0.980"]
    end

    Report["Benchmark Report & JSON Artifact<br/>(64 / 64 Scenarios Passed — 100%)"]

    Scenarios --> Engine
    Engine --> A & B
    A & B --> Metrics
    Metrics --> Report
```

### Evaluation Criteria (Scored 0.0 – 1.0)

| Criterion | Target | Prompt A Score | Prompt B Score | Description |
| :--- | :---: | :---: | :---: | :--- |
| **Flow Adherence** | 1.000 | **1.000** | **1.000** | Proper state transitions following the designated FSM |
| **Response Relevance** | 1.000 | **1.000** | **1.000** | Contextual alignment with user query |
| **Appropriate Clarification** | 1.000 | **1.000** | **1.000** | Triggers clarification on ambiguous input; does not false-trigger |
| **Safety Compliance** | 1.000 | **1.000** | **1.000** | Complete avoidance of approval claims, rates, and credential requests |
| **Task Completion** | 1.000 | **1.000** | **1.000** | Reaches expected final state (completed, handoff, details, etc.) |
| **Recovery Success** | 1.000 | **1.000** | **1.000** | Successfully recovers from interruptions, skips, or injections |
| **Conciseness** | > 0.900 | **0.980** | **0.980** | Voice-appropriate turn length (< 120 words per response) |

**Overall Results**: **64 / 64 Scenarios Passed (100.0% Pass Rate)**

---

## Streamlit Interactive Web Application

The interactive web UI (`app.py`) provides a complete testing suite:

1. **Live Voice Assistant Simulator**:
   - Dual-mode chat interface with audio output simulation.
   - Quick-reply scenario buttons ("Happy Path", "Off-topic Query", "Credential Leak", "Prompt Injection").
   - Real-time conversation state visualizer and collected details inspector.
2. **Transcript Viewer & Session Analytics**:
   - Filter transcripts by session ID, state, or prompt version.
   - Intent distribution charts, average response times, and clarification frequency metrics.
   - One-click log export (JSON) and log clearing.
3. **Evaluation Benchmark Dashboard**:
   - Run the 64-scenario test harness directly inside the web browser.
   - Real-time scorecards, criterion breakdown charts, and scenario drill-downs.

---

## Project Structure

```
VoiceBridge-AI Assistant/
├── .env.example                     # Environment template (OPENAI_API_KEY optional)
├── .gitignore                       # Git ignore rules for logs, cache, and results
├── requirements.txt                 # Project dependencies
├── app.py                           # Streamlit web application & simulator
├── README.md                        # Complete project documentation
│
├── src/                             # Core application logic
│   ├── __init__.py                  # Package exports
│   ├── config.py                    # Environment & runtime configuration
│   ├── schemas.py                   # Pydantic models (ConversationState, UserIntent, TurnRecord)
│   ├── intent_detection.py          # Deterministic keyword/pattern intent classifier
│   ├── safety.py                    # Sanitization, PII regex, response safety guardrails
│   ├── response_generator.py        # Dual-mode response generation (Local + OpenAI)
│   ├── transcript_logger.py         # JSONL structured turn logging & analytics
│   └── conversation_manager.py      # Core FSM state manager and turn orchestrator
│
├── prompts/                         # Prompt engineering assets
│   ├── __init__.py
│   └── conversation_prompts.py      # System prompts (Version A & B) and local templates
│
├── evaluation/                      # Quality evaluation & benchmarking
│   ├── __init__.py
│   ├── scenarios.json               # 32 curated benchmark test scenarios
│   ├── evaluator.py                 # Multi-criterion evaluation engine
│   └── run_evaluation.py            # CLI benchmark runner with formatted reports
│
├── tests/                           # Pytest automated test suite (89 tests)
│   ├── test_conversation_flow.py    # Happy paths, topic selection, state transitions
│   ├── test_recovery.py             # Ambiguity, limits, irrelevance, skip, restart, exit
│   ├── test_safety.py               # Sensitive PII, rate denial, guarantee denial, injections
│   ├── test_transcript_logging.py   # Turn logging, session retrieval, analytics
│   └── test_evaluation.py           # Evaluator loading, scoring algorithms, serialization
│
├── logs/                            # Session transcript storage (JSONL)
│   └── .gitkeep
└── results/                         # Evaluation benchmark outputs (JSON)
    └── .gitkeep
```

---

## Quickstart & Installation

### 1. Clone the Repository & Set Up Virtual Environment

```bash
git clone https://github.com/your-username/voicebridge-ai-assistant.git
cd voicebridge-ai-assistant

python -m venv venv
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On macOS / Linux:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment (Optional for LLM Mode)

The assistant runs **100% locally out-of-the-box** without any API keys. If you wish to enable OpenAI LLM generation:

```bash
cp .env.example .env
```

Edit `.env`:
```ini
OPENAI_API_KEY=sk-your-openai-api-key-here
LLM_MODEL_NAME=gpt-3.5-turbo
LLM_TIMEOUT=15
```

### 4. Launch the Streamlit App

```bash
streamlit run app.py
```

The application will launch in your default browser at `http://localhost:8501`.

---

## Running the Test Suite

Run all **89 comprehensive unit and integration tests**:

```bash
python -m pytest tests/ -v
```

Expected output:
```
============================= 89 passed in 0.33s ==============================
```

---

## Running the Evaluation Benchmark

Run the automated evaluation suite across all 64 scenario executions:

```bash
python evaluation/run_evaluation.py
```

Expected output:
```
======================================================================
VoiceBridge AI - Evaluation Suite
======================================================================

Total scenarios:  64
Passed:           64
Failed:           0
Pass rate:        100.0%

Per-criterion average scores:
----------------------------------------
  flow_adherence               [####################] 1.000
  response_relevance           [####################] 1.000
  appropriate_clarification    [####################] 1.000
  safety_compliance            [####################] 1.000
  task_completion              [####################] 1.000
  recovery_success             [####################] 1.000
  conciseness                  [###################-] 0.980

Recommendation: Prompt A performed better overall in local mode. Both prompts achieved 100.0% pass rate.
Results saved to: results/evaluation_latest.json
======================================================================
```

---

## Conversational AI Engineering Highlights

This project demonstrates core competencies required for Conversational AI Design and Engineering roles:
- **State Machine Discipline**: Deterministic state transitions prevent conversational hallucination and infinite loops.
- **Disfluency & Ambiguity Tolerance**: Explicit 2-turn clarification counter with graceful fallbacks.
- **Financial Compliance Guardrails**: Pre- and post-generation safety checks protecting both user data and regulatory integrity.
- **A/B Testing Infrastructure**: Side-by-side prompt evaluation measuring quantitative conciseness and adherence.
- **Telemetry & Logging**: Structured JSONL turn records capturing latency, detected intent, fallback usage, and session history.

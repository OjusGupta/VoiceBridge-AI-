"""VoiceBridge AI — Streamlit Application (LEGACY).

This file is superseded by the FastAPI + HTML/JS frontend (server.py + frontend/).
It is kept here for reference only. It is NOT tested, NOT maintained, and may fail
if Streamlit or other dependencies are out of date.

See legacy/README.md for details.

A polished conversational loan inquiry assistant interface with:
- Chat panel with visually distinct messages
- Prompt version selector (A/B)
- Mode indicator (Local / LLM)
- Transcript viewer
- Evaluation dashboard
- Analytics
- Technical architecture section
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Config
from src.conversation_manager import ConversationManager
from src.response_generator import ResponseGenerator
from src.llm_client import LLMClient
from src.transcript_logger import TranscriptLogger
from src.analytics import Analytics
from src.schemas import ConversationState

# ─── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="VoiceBridge AI — Loan Inquiry Assistant",
    page_icon="🌉",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ──────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Main theme */
    .main { background-color: #0e1117; }

    .stApp {
        background: linear-gradient(135deg, #0e1117 0%, #1a1f2e 50%, #0e1117 100%);
    }

    /* Header styling */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }

    .main-header h1 {
        color: white;
        margin: 0;
        font-size: 1.8rem;
        font-weight: 700;
    }

    .main-header p {
        color: rgba(255, 255, 255, 0.85);
        margin: 0.3rem 0 0 0;
        font-size: 0.95rem;
    }

    /* Disclaimer banner */
    .disclaimer {
        background: linear-gradient(135deg, #ff6b6b33, #ee5a2433);
        border: 1px solid #ff6b6b55;
        border-radius: 8px;
        padding: 0.7rem 1rem;
        margin-bottom: 1rem;
        color: #ff8a80;
        font-size: 0.85rem;
        text-align: center;
    }

    /* Chat messages */
    .chat-container {
        max-height: 500px;
        overflow-y: auto;
        padding: 1rem;
        background: #161b22;
        border-radius: 12px;
        border: 1px solid #30363d;
    }

    .user-msg {
        background: linear-gradient(135deg, #238636, #1a7f37);
        color: white;
        padding: 0.8rem 1.2rem;
        border-radius: 16px 16px 4px 16px;
        margin: 0.5rem 0;
        max-width: 80%;
        margin-left: auto;
        font-size: 0.95rem;
        box-shadow: 0 2px 8px rgba(35, 134, 54, 0.3);
    }

    .assistant-msg {
        background: linear-gradient(135deg, #21262d, #2d333b);
        color: #e6edf3;
        padding: 0.8rem 1.2rem;
        border-radius: 16px 16px 16px 4px;
        margin: 0.5rem 0;
        max-width: 80%;
        font-size: 0.95rem;
        border: 1px solid #30363d;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    }

    /* State indicator */
    .state-badge {
        display: inline-block;
        background: #30363d;
        color: #8b949e;
        padding: 0.2rem 0.6rem;
        border-radius: 12px;
        font-size: 0.75rem;
        margin: 0.2rem 0;
    }

    /* Mode indicator */
    .mode-badge {
        display: inline-block;
        padding: 0.3rem 0.8rem;
        border-radius: 16px;
        font-size: 0.8rem;
        font-weight: 600;
    }

    .mode-local {
        background: linear-gradient(135deg, #f0883e33, #d2992233);
        color: #f0883e;
        border: 1px solid #f0883e55;
    }

    .mode-llm {
        background: linear-gradient(135deg, #3fb95033, #2ea04333);
        color: #3fb950;
        border: 1px solid #3fb95055;
    }

    /* Metric cards */
    .metric-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
    }

    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #58a6ff;
    }

    .metric-label {
        font-size: 0.85rem;
        color: #8b949e;
        margin-top: 0.3rem;
    }

    /* Sidebar */
    .stSidebar > div {
        background: #161b22;
    }

    /* Fix button styling */
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# ─── Session state initialization ────────────────────────────────────────────

def init_session_state() -> None:
    """Initialize Streamlit session state variables."""
    if "initialized" not in st.session_state:
        st.session_state.initialized = True
        st.session_state.prompt_version = "A"
        st.session_state.messages = []
        st.session_state.manager = None
        st.session_state.conversation_started = False


def get_or_create_manager() -> ConversationManager:
    """Get the existing manager or create a new one."""
    if st.session_state.manager is None:
        llm_client = LLMClient() if Config.is_llm_enabled() else None
        generator = ResponseGenerator(llm_client)
        logger = TranscriptLogger()
        st.session_state.manager = ConversationManager(
            prompt_version=st.session_state.prompt_version,
            response_generator=generator,
            transcript_logger=logger,
        )
    return st.session_state.manager


def start_new_conversation() -> None:
    """Start a fresh conversation."""
    st.session_state.messages = []
    st.session_state.manager = None
    st.session_state.conversation_started = False


# ─── Main app ────────────────────────────────────────────────────────────────

def main() -> None:
    init_session_state()

    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🌉 VoiceBridge AI</h1>
        <p>Conversational Loan Inquiry Assistant — Educational Demo</p>
    </div>
    """, unsafe_allow_html=True)

    # Disclaimer
    st.markdown("""
    <div class="disclaimer">
        ⚠️ <strong>Simulated demo — not a real financial service.</strong>
        This is an educational prototype. It does not connect to real banks,
        process real applications, or make real eligibility decisions.
    </div>
    """, unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.markdown("### ⚙️ Settings")

        # Mode indicator
        mode = Config.get_mode_label()
        mode_class = "mode-llm" if Config.is_llm_enabled() else "mode-local"
        st.markdown(
            f'<span class="mode-badge {mode_class}">{mode}</span>',
            unsafe_allow_html=True,
        )

        st.markdown("---")

        # Prompt version selector
        version = st.radio(
            "Prompt Version",
            ["A — Professional", "B — Conversational"],
            index=0 if st.session_state.prompt_version == "A" else 1,
            help="A = concise & direct, B = warm & empathetic",
        )
        new_version = "A" if version.startswith("A") else "B"
        if new_version != st.session_state.prompt_version:
            st.session_state.prompt_version = new_version
            start_new_conversation()
            st.rerun()

        st.markdown("---")

        # Conversation controls
        st.markdown("### 🎮 Controls")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Restart", use_container_width=True):
                start_new_conversation()
                st.rerun()
        with col2:
            if st.button("🛑 End", use_container_width=True):
                manager = get_or_create_manager()
                if manager.is_active:
                    response = manager.process_message("goodbye")
                    st.session_state.messages.append(
                        {"role": "user", "content": "goodbye"}
                    )
                    st.session_state.messages.append(
                        {"role": "assistant", "content": response}
                    )
                st.rerun()

        st.markdown("---")

        # Current state
        manager = get_or_create_manager()
        state = manager.current_state.value
        st.markdown(f"**Current State:** `{state}`")
        st.markdown(f"**Session:** `{manager.session_id}`")
        st.markdown(f"**Turns:** `{manager.context.turn_count}`")

    # ─── Tabs ────────────────────────────────────────────────────────────────
    tab_chat, tab_transcript, tab_eval, tab_analytics, tab_arch = st.tabs([
        "💬 Chat", "📜 Transcripts", "📊 Evaluation", "📈 Analytics", "🏗️ Architecture"
    ])

    with tab_chat:
        _render_chat_tab()

    with tab_transcript:
        _render_transcript_tab()

    with tab_eval:
        _render_evaluation_tab()

    with tab_analytics:
        _render_analytics_tab()

    with tab_arch:
        _render_architecture_tab()


# ─── Chat tab ────────────────────────────────────────────────────────────────

def _render_chat_tab() -> None:
    manager = get_or_create_manager()

    # Auto-start with greeting
    if not st.session_state.conversation_started:
        greeting = manager.get_greeting()
        st.session_state.messages.append({"role": "assistant", "content": greeting})
        st.session_state.conversation_started = True

    # Display messages
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(
                f'<div class="user-msg">{msg["content"]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="assistant-msg">🌉 {msg["content"]}</div>',
                unsafe_allow_html=True,
            )

    # Input
    if manager.is_active:
        user_input = st.chat_input("Type your message...", key="chat_input")
        if user_input and user_input.strip():
            st.session_state.messages.append({"role": "user", "content": user_input})
            response = manager.process_message(user_input)
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.rerun()
    else:
        st.info("This conversation has ended. Click **Restart** to begin a new one.")


# ─── Transcript tab ─────────────────────────────────────────────────────────

def _render_transcript_tab() -> None:
    logger = TranscriptLogger()
    sessions = logger.get_all_session_ids()

    if not sessions:
        st.info("No transcripts recorded yet. Start a conversation to generate data.")
        return

    st.markdown(f"**{len(sessions)} session(s) recorded**")

    selected = st.selectbox("Select session", sessions)
    if selected:
        turns = logger.read_session_turns(selected)
        if turns:
            df = pd.DataFrame(turns)
            display_cols = [
                "turn_number", "state", "detected_intent",
                "user_message", "assistant_response",
                "clarification_required", "fallback_used",
                "response_time_ms",
            ]
            available = [c for c in display_cols if c in df.columns]
            st.dataframe(df[available], use_container_width=True, height=400)

    st.markdown("---")

    # Clear logs
    st.markdown("### 🗑️ Clear Logs")
    st.warning("This will permanently delete all transcript data.")
    if st.button("Clear all transcript logs"):
        if logger.clear_logs():
            st.success("Logs cleared successfully.")
            st.rerun()
        else:
            st.error("Failed to clear logs.")


# ─── Evaluation tab ─────────────────────────────────────────────────────────

def _render_evaluation_tab() -> None:
    st.markdown("### 📊 Evaluation Dashboard")
    st.markdown(
        "Run the evaluation suite to replay 32 test scenarios against "
        "both prompt versions and view scored results."
    )

    # Check for saved results
    results_path = Path(Config.RESULTS_DIR) / "evaluation_latest.json"

    col1, col2 = st.columns([1, 3])
    with col1:
        run_eval = st.button("▶️ Run Evaluation", use_container_width=True)

    if run_eval:
        with st.spinner("Running evaluation suite..."):
            from evaluation.evaluator import Evaluator, CRITERIA
            evaluator = Evaluator()
            report = evaluator.run_all(["A", "B"])

            # Save results
            results_dir = Path(Config.RESULTS_DIR)
            results_dir.mkdir(parents=True, exist_ok=True)
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2)
            st.success("Evaluation complete!")

    if results_path.exists():
        with open(results_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Scenarios", data["total_scenarios"])
        with col2:
            st.metric("Passed", data["total_passed"])
        with col3:
            st.metric("Failed", data["total_failed"])
        with col4:
            st.metric("Pass Rate", f"{data.get('pass_rate', 0)}%")

        st.markdown("---")

        # Per-criterion scores
        st.markdown("#### Per-Criterion Scores")
        if data.get("per_criterion_avg"):
            criteria_df = pd.DataFrame([
                {"Criterion": k.replace("_", " ").title(), "Score": v}
                for k, v in data["per_criterion_avg"].items()
            ])
            st.bar_chart(criteria_df.set_index("Criterion"), height=300)

        st.markdown("---")

        # Prompt comparison
        st.markdown("#### Prompt A vs B")
        if data.get("prompt_comparison"):
            comp = data["prompt_comparison"]
            comp_rows = []
            for version, metrics in comp.items():
                row = {"Prompt": version, "Pass Rate": f"{metrics['pass_rate']}%"}
                if "avg_scores" in metrics:
                    for k, v in metrics["avg_scores"].items():
                        row[k.replace("_", " ").title()] = round(v, 3)
                comp_rows.append(row)
            st.table(pd.DataFrame(comp_rows))

        # Recommendation
        if data.get("recommendation"):
            st.info(f"💡 {data['recommendation']}")

        # Failed scenarios
        failed = [r for r in data.get("results", []) if not r.get("passed")]
        if failed:
            with st.expander(f"⚠️ Failed Scenarios ({len(failed)})"):
                for r in failed:
                    st.markdown(
                        f"**[{r['prompt_version']}] {r['scenario_id']}:** "
                        f"{r['scenario_name']}"
                    )
                    st.markdown(
                        f"Expected `{r['expected_state']}` → Got `{r['final_state']}`"
                    )
                    for f_msg in r.get("failures", []):
                        st.markdown(f"- ✗ {f_msg}")
                    st.markdown("---")
    else:
        st.info("No evaluation results yet. Click **Run Evaluation** to start.")


# ─── Analytics tab ───────────────────────────────────────────────────────────

def _render_analytics_tab() -> None:
    st.markdown("### 📈 Conversation Analytics")

    analytics = Analytics()
    summary = analytics.compute_summary()

    if summary["total_sessions"] == 0:
        st.info("No conversation data yet. Chat with the assistant to generate data.")
        return

    # Metric cards
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Sessions", summary["total_sessions"])
        st.metric("Completion Rate", f"{summary['completion_rate']}%")
    with col2:
        st.metric("Total Turns", summary["total_turns"])
        st.metric("Clarification Rate", f"{summary['clarification_rate']}%")
    with col3:
        st.metric("Handoff Requests", summary["handoff_requests"])
        st.metric("Avg Response Time", f"{summary['avg_response_time_ms']}ms")

    st.markdown("---")

    # Intent distribution
    if summary.get("intent_distribution"):
        st.markdown("#### Intent Distribution")
        intent_df = pd.DataFrame([
            {"Intent": k, "Count": v}
            for k, v in summary["intent_distribution"].items()
        ])
        st.bar_chart(intent_df.set_index("Intent"), height=300)

    # Prompt comparison
    st.markdown("---")
    st.markdown("#### Prompt A vs B (from transcript data)")
    comparison = analytics.compute_prompt_comparison()
    if comparison:
        comp_rows = []
        for version, metrics in comparison.items():
            comp_rows.append({
                "Prompt": version,
                "Sessions": metrics["total_sessions"],
                "Turns": metrics["total_turns"],
                "Completion Rate": f"{metrics['completion_rate']}%",
                "Clarification Rate": f"{metrics['clarification_rate']}%",
                "Avg Turns/Session": metrics["avg_turns_per_session"],
            })
        st.table(pd.DataFrame(comp_rows))


# ─── Architecture tab ───────────────────────────────────────────────────────

def _render_architecture_tab() -> None:
    st.markdown("### 🏗️ Technical Architecture")

    with st.expander("System Architecture Diagram", expanded=True):
        st.markdown("""
```mermaid
graph TD
    A["User Input"] --> B["Safety: sanitize_user_input"]
    B --> C["Intent Detection"]
    C --> D["Conversation Manager<br/>(State Machine)"]
    D --> E{"LLM Available?"}
    E -- Yes --> F["LLM Client"]
    E -- No --> G["Local Response Templates"]
    F --> H["Safety: check_response_safety"]
    G --> H
    H --> I["Response to User"]
    D --> J["Transcript Logger"]
    J --> K["Analytics Engine"]
    K --> L["Dashboard"]
```
        """)

    with st.expander("Conversation State Machine"):
        st.markdown("""
```mermaid
stateDiagram-v2
    [*] --> GREETING
    GREETING --> CONSENT
    CONSENT --> INQUIRY_TYPE: User says yes
    CONSENT --> COMPLETED: User says no
    CONSENT --> CLARIFICATION: Unclear response
    INQUIRY_TYPE --> BASIC_DETAILS: Topic identified
    INQUIRY_TYPE --> CLARIFICATION: Unclear response
    BASIC_DETAILS --> NEXT_STEPS: Details collected
    BASIC_DETAILS --> CLARIFICATION: Unclear response
    CLARIFICATION --> INQUIRY_TYPE: Clarified (return)
    CLARIFICATION --> BASIC_DETAILS: Clarified (return)
    CLARIFICATION --> NEXT_STEPS: Max attempts reached
    CLARIFICATION --> COMPLETED: Consent clarification failed
    NEXT_STEPS --> COMPLETED: Summary delivered
    HUMAN_HANDOFF --> INQUIRY_TYPE: User continues
    HUMAN_HANDOFF --> COMPLETED: User exits
```
        """)

    with st.expander("Module Responsibilities"):
        st.markdown("""
| Module | Responsibility |
|--------|---------------|
| `config.py` | Environment variables, LLM mode detection |
| `schemas.py` | Pydantic models for states, intents, turns, context |
| `intent_detection.py` | Rule-based intent classification |
| `safety.py` | Input sanitization, output safety checks |
| `response_generator.py` | LLM/local response generation |
| `conversation_manager.py` | State machine, turn orchestration |
| `llm_client.py` | Optional OpenAI API wrapper |
| `transcript_logger.py` | JSONL logging, session replay |
| `analytics.py` | Aggregate metrics computation |
| `conversation_prompts.py` | Prompt A/B versions, local templates |
| `evaluator.py` | Scenario replay and scoring |
        """)

    with st.expander("Message Processing Flow"):
        st.markdown("""
1. **User sends message** via Streamlit chat input
2. **`sanitize_user_input()`** — strips control chars, limits length
3. **`detect_intent()`** — classifies message into 18 intent categories
4. **`ConversationManager._process_state()`** — uses current state + intent to decide transition
5. **`ResponseGenerator.generate()`** — tries LLM first (if available), falls back to local templates
6. **`check_response_safety()`** — validates LLM output against banned phrases / hallucinated numbers
7. **`TranscriptLogger.log_turn()`** — records the turn to JSONL
8. **Response displayed** in Streamlit chat panel
        """)


if __name__ == "__main__":
    main()

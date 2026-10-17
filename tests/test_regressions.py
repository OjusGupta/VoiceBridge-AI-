"""Regression tests for bugs found while building the web UI."""
import json
import pytest
from evaluation.evaluator import Evaluator
from src.conversation_manager import ConversationManager
from src.intent_detection import detect_intent
from src.schemas import UserIntent
from src.transcript_logger import TranscriptLogger


def _mgr():
    m = ConversationManager(transcript_logger=TranscriptLogger())
    m.get_greeting()
    return m


@pytest.mark.parametrize("text", ["Can you explain the next steps?", "what are the next steps", "tell me the next step"])
def test_next_steps_question_is_not_skip(text):
    assert detect_intent(text) != UserIntent.SKIP


@pytest.mark.parametrize("text", ["next", "Next.", "skip", "move on"])
def test_bare_skip_words_still_skip(text):
    assert detect_intent(text) == UserIntent.SKIP


@pytest.mark.parametrize("text,needle", [
    ("What documents might I need?", "proof of identity"),
    ("what types of loans are there", "personal loans"),
    ("How do I apply?", None),
])
def test_specific_question_gets_specific_answer(text, needle):
    m = _mgr(); m.process_message("yes")
    reply = m.process_message(text)
    assert "Thank you for that information" not in reply and "Thanks for sharing" not in reply
    if needle:
        assert needle in reply.lower()
    assert m.current_state.value == "BASIC_DETAILS"  # still advances


@pytest.mark.parametrize("text", ["maybe", "hmm", "what?"])
def test_hedges_are_unclear(text):
    assert detect_intent(text) == UserIntent.UNCLEAR


def test_approval_timing_is_not_guarantee():
    assert detect_intent("How long will it take to get approved?") == UserIntent.RATE_REQUEST
    assert detect_intent("Will I be approved?") == UserIntent.GUARANTEE_REQUEST


def test_evaluator_fails_on_wrong_expected_intent(tmp_path):
    bad = [{"id": "X1", "name": "wrong intent", "category": "normal_completion",
            "messages": ["yes"], "expected_intents": ["NEGATIVE"], "expected_final_state": "INQUIRY_TYPE"}]
    p = tmp_path / "s.json"; p.write_text(json.dumps(bad))
    r = Evaluator(p, log_dir=str(tmp_path / "l")).run_all(["A"])
    assert r.total_failed == 1 and "expected intent NEGATIVE" in r.results[0].failures[0]


def test_evaluator_fails_when_clarification_missing(tmp_path):
    bad = [{"id": "X2", "name": "no clarify", "category": "ambiguous",
            "messages": ["yes"], "expected_final_state": "INQUIRY_TYPE"}]
    p = tmp_path / "s.json"; p.write_text(json.dumps(bad))
    assert Evaluator(p, log_dir=str(tmp_path / "l")).run_all(["A"]).total_failed == 1


def test_sensitive_input_is_redacted_in_log_and_history(tmp_path):
    lg = TranscriptLogger(str(tmp_path))
    m = ConversationManager(transcript_logger=lg); m.get_greeting(); m.process_message("yes")
    m.process_message("my ssn is 123-45-6789 and password: hunter2")
    blob = (tmp_path / "transcripts.jsonl").read_text() + str(m.context.history)
    assert "123-45-6789" not in blob and "hunter2" not in blob and "REDACTED" in blob


def test_completed_sessions_counted_by_state_after(tmp_path):
    from src.analytics import Analytics
    lg = TranscriptLogger(str(tmp_path))
    m = ConversationManager(transcript_logger=lg); m.get_greeting()
    for t in ["yes", "documents", "home loan", "thanks"]:
        m.process_message(t)
    assert m.current_state.value == "COMPLETED"
    assert Analytics(lg).compute_summary()["completed_sessions"] == 1
    assert lg.read_all_turns()[-1]["state_after"] == "COMPLETED"


def test_recommendation_does_not_invent_causes():
    r = Evaluator().run_all(["A", "B"]).recommendation
    assert "professional, concise tone led" not in r and "by construction" in r


def test_greeting_only_sessions_not_counted_in_analytics(tmp_path):
    from src.analytics import Analytics, EngagedTranscriptView
    lg = TranscriptLogger(str(tmp_path))
    for _ in range(3):  # three page loads, nobody typed anything
        ConversationManager(transcript_logger=lg).get_greeting()
    assert Analytics(EngagedTranscriptView(lg)).compute_summary()["total_sessions"] == 0
    m = ConversationManager(transcript_logger=lg); m.get_greeting(); m.process_message("yes")
    assert Analytics(EngagedTranscriptView(lg)).compute_summary()["total_sessions"] == 1

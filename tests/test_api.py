"""API tests: sessions persist across messages, validation, restart/end, eval isolation."""
import pytest
from fastapi.testclient import TestClient

import server
from src.config import Config
from src.intent_detection import detect_intent
from src.schemas import UserIntent


@pytest.fixture()
def client():
    server._sessions.clear()
    return TestClient(server.app)


def _new(client, v="A"):
    r = client.post("/api/conversations", json={"prompt_version": v})
    assert r.status_code == 200
    return r.json()


def test_status_never_exposes_key(client):
    body = client.get("/api/status").json()
    assert body["mode"] in ("local", "llm")
    assert "api_key" not in str(body).lower()


def test_session_persists_across_messages(client):
    sid = _new(client)["session_id"]
    a = client.post(f"/api/conversations/{sid}/messages", json={"message": "Yes, let's get started."}).json()
    b = client.post(f"/api/conversations/{sid}/messages", json={"message": "What documents might I need?"}).json()
    assert a["session_id"] == b["session_id"] == sid
    assert a["state"] == "INQUIRY_TYPE" and b["state_before"] == "INQUIRY_TYPE"
    assert b["turn_count"] == 2


def test_turns_are_logged_to_real_logger(client):
    sid = _new(client)["session_id"]
    client.post(f"/api/conversations/{sid}/messages", json={"message": "yes"})
    turns = client.get(f"/api/conversations/{sid}/transcript").json()["turns"]
    assert [t["user_message"] for t in turns] == ["", "yes"]  # greeting + one turn


@pytest.mark.parametrize("payload,code", [({"message": ""}, 422), ({"message": "   "}, 422), ({"message": "x" * 2001}, 422), ({}, 422)])
def test_invalid_messages_rejected(client, payload, code):
    sid = _new(client)["session_id"]
    assert client.post(f"/api/conversations/{sid}/messages", json=payload).status_code == code


def test_unknown_session_404_and_bad_prompt_version(client):
    assert client.post("/api/conversations/nope/messages", json={"message": "hi"}).status_code == 404
    assert client.post("/api/conversations", json={"prompt_version": "Z"}).status_code == 422


def test_end_blocks_further_messages_and_restart_recovers(client):
    sid = _new(client)["session_id"]
    assert client.post(f"/api/conversations/{sid}/end").json()["state"] == "COMPLETED"
    assert client.post(f"/api/conversations/{sid}/messages", json={"message": "hi"}).status_code == 409
    fresh = client.post(f"/api/conversations/{sid}/restart").json()
    assert fresh["state"] == "CONSENT" and fresh["is_active"] and fresh["session_id"] != sid


def test_guarantee_and_human_requests_are_safe(client):
    sid = _new(client)["session_id"]
    g = client.post(f"/api/conversations/{sid}/messages", json={"message": "What is my guaranteed interest rate?"}).json()
    assert g["intent"] == "GUARANTEE_REQUEST" and "approved" not in g["reply"].lower().replace("not", "")
    h = client.post(f"/api/conversations/{sid}/messages", json={"message": "I want to speak to a human."}).json()
    assert h["state"] == "HUMAN_HANDOFF" and "cannot transfer" in h["reply"]


def test_evaluation_does_not_pollute_transcripts(client):
    before = client.get("/api/transcripts").json()["count"]
    r = client.post("/api/evaluation/run").json()
    assert r["synthetic"] is True and r["total_scenarios"] == 64
    assert client.get("/api/transcripts").json()["count"] == before
    assert client.get("/api/evaluation/results").json()["available"] is True


def test_results_empty_state(client):
    assert client.get("/api/evaluation/results").json() == {"available": False}


def test_clear_transcripts(client):
    sid = _new(client)["session_id"]
    assert client.get("/api/transcripts").json()["count"] >= 1
    client.delete("/api/transcripts")
    assert client.get("/api/transcripts").json()["count"] == 0


def test_not_sure_is_not_affirmative():
    assert detect_intent("I'm not sure what information I should provide.") != UserIntent.AFFIRMATIVE
    assert detect_intent("sure") == UserIntent.AFFIRMATIVE


def test_skip_uses_skip_template_not_error_fallback():
    from src.conversation_manager import ConversationManager
    from src.transcript_logger import TranscriptLogger
    m = ConversationManager(transcript_logger=TranscriptLogger())
    m.get_greeting(); m.process_message("yes"); m.process_message("documents")
    assert "couldn't process" not in m.process_message("skip").lower()


def test_transcript_filters_search_and_export(client):
    a = _new(client)["session_id"]; b = _new(client, "B")["session_id"]
    client.post(f"/api/conversations/{a}/messages", json={"message": "yes"})
    client.post(f"/api/conversations/{b}/messages", json={"message": "=HYPERLINK(\"x\") loan"})
    assert {t["session_id"] for t in client.get("/api/transcripts", params={"session_id": a}).json()["turns"]} == {a}
    assert {t["prompt_version"] for t in client.get("/api/transcripts", params={"prompt_version": "B"}).json()["turns"]} == {"B"}
    assert client.get("/api/transcripts", params={"q": "hyperlink"}).json()["count"] >= 1
    csv_text = client.get("/api/transcripts/export", params={"format": "csv"}).text
    assert "'=HYPERLINK" in csv_text and ",=HYPERLINK" not in csv_text  # formula injection neutralised
    assert client.get("/api/transcripts/export", params={"format": "json"}).json()
    assert client.get("/api/transcripts/export", params={"format": "xml"}).status_code == 422


def test_api_analytics_ignores_greeting_only_sessions(client):
    _new(client); _new(client)  # two page loads, nobody typed
    assert client.get("/api/analytics").json()["summary"]["total_sessions"] == 0
    sid = _new(client)["session_id"]
    client.post(f"/api/conversations/{sid}/messages", json={"message": "yes"})
    s = client.get("/api/analytics").json()["summary"]
    assert s["total_sessions"] == 1 and s["total_turns"] == 1


class _FakeLLM:
    """Stands in for LLMClient so the LLM branch is exercised without an API key."""
    is_available = True

    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def generate_response(self, system_prompt, history, user_message):
        from types import SimpleNamespace
        self.calls += 1
        return SimpleNamespace(response_text=self.reply) if self.reply is not None else None


def test_llm_mode_is_used_when_configured_and_status_reports_it(client, monkeypatch):
    fake = _FakeLLM("Here is a clear, general explanation of the loan inquiry process.")
    monkeypatch.setattr(server, "_llm", fake)
    assert client.get("/api/status").json()["mode"] == "llm"
    sid = _new(client)["session_id"]
    r = client.post(f"/api/conversations/{sid}/messages", json={"message": "yes"}).json()
    assert fake.calls >= 1 and r["response_mode"] == "llm" and "clear, general explanation" in r["reply"]


@pytest.mark.parametrize("bad", ["Congratulations, your loan is approved! Your rate is 4.5%.", "", None])
def test_unsafe_or_missing_llm_output_falls_back_safely(client, monkeypatch, bad):
    monkeypatch.setattr(server, "_llm", _FakeLLM(bad))
    sid = _new(client)["session_id"]
    r = client.post(f"/api/conversations/{sid}/messages", json={"message": "yes"}).json()
    assert "approved" not in r["reply"].lower() and "4.5%" not in r["reply"] and r["reply"].strip()

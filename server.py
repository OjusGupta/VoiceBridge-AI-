"""VoiceBridge AI — HTTP API.

Thin layer over the existing pipeline (safety -> intent -> state machine ->
response generator -> output safety -> transcript logger). No business logic
lives here. Run:  uvicorn server:app --reload   ->  http://localhost:8000
"""

from __future__ import annotations

import csv
import io
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from evaluation.evaluator import Evaluator
from src.analytics import Analytics, EngagedTranscriptView
from src.config import Config
from src.conversation_manager import ConversationManager
from src.llm_client import LLMClient
from src.response_generator import ResponseGenerator
from src.schemas import ConversationState
from src.transcript_logger import TranscriptLogger

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
MAX_SESSIONS = 200  # in-memory cap; oldest sessions are evicted

app = FastAPI(title="VoiceBridge AI", version="1.0.0")

_sessions: dict[str, ConversationManager] = {}
_lock = threading.Lock()
_llm = LLMClient() if Config.is_llm_enabled() else None


# ── helpers ──────────────────────────────────────────────────────────────────
def _new_manager(version: str, session_id: Optional[str] = None) -> ConversationManager:
    mgr = ConversationManager(
        prompt_version=version,
        response_generator=ResponseGenerator(_llm),
        transcript_logger=TranscriptLogger(),
    )
    if session_id:
        mgr.context.session_id = session_id
    return mgr


def _get(session_id: str) -> ConversationManager:
    mgr = _sessions.get(session_id)
    if mgr is None:
        raise HTTPException(404, "Unknown session. Sessions are in-memory and reset when the server restarts.")
    return mgr


def _snapshot(mgr: ConversationManager) -> dict:
    c = mgr.context
    return {
        "session_id": c.session_id,
        "state": c.current_state.value,
        "is_active": c.is_active,
        "turn_count": c.turn_count,
        "max_turns": Config.MAX_CONVERSATION_TURNS,
        "prompt_version": c.prompt_version,
        "response_mode": c.response_mode,
        "inquiry_topic": c.inquiry_topic,
    }


class NewConversation(BaseModel):
    prompt_version: str = Field("A", pattern="^[AB]$")


class UserMessage(BaseModel):
    message: str = Field(..., max_length=2000)


# ── conversation endpoints ───────────────────────────────────────────────────
@app.get("/api/status")
def status() -> dict:
    return {
        "mode": "llm" if _llm and _llm.is_available else "local",
        "mode_label": "LLM mode" if _llm and _llm.is_available else "Local demo mode",
        "llm_configured": Config.is_llm_enabled(),  # boolean only — key is never returned
        "states": [s.value for s in ConversationState],
        "active_sessions": len(_sessions),
        "transcript_storage": "JSONL file on disk (persists across restarts)",
        "session_storage": "In-memory (lost on server restart)",
    }


@app.post("/api/conversations")
def create_conversation(body: NewConversation = NewConversation()) -> dict:
    with _lock:
        if len(_sessions) >= MAX_SESSIONS:
            _sessions.pop(next(iter(_sessions)))
        mgr = _new_manager(body.prompt_version)
        _sessions[mgr.session_id] = mgr
    greeting = mgr.get_greeting()
    return {**_snapshot(mgr), "reply": greeting}


@app.post("/api/conversations/{session_id}/messages")
def send_message(session_id: str, body: UserMessage) -> dict:
    mgr = _get(session_id)
    text = body.message.strip()
    if not text:
        raise HTTPException(422, "Message is empty.")
    if not mgr.is_active:
        raise HTTPException(409, "Conversation has ended. Restart to begin a new one.")
    with _lock:
        before = mgr.current_state.value
        reply = mgr.process_message(text)
    turn = mgr.last_turn
    return {
        **_snapshot(mgr),
        "reply": reply,
        "state_before": before,
        "intent": turn.detected_intent if turn else None,
        "clarification_required": bool(turn and turn.clarification_required),
        "fallback_used": bool(turn and turn.fallback_used),
        "response_time_ms": turn.response_time_ms if turn else None,
    }


@app.post("/api/conversations/{session_id}/restart")
def restart(session_id: str) -> dict:
    old = _get(session_id)
    with _lock:
        mgr = _new_manager(old.context.prompt_version)  # fresh session id: clean transcript boundary
        _sessions.pop(session_id, None)
        _sessions[mgr.session_id] = mgr
    greeting = mgr.get_greeting()  # advances GREETING -> CONSENT, so snapshot afterwards
    return {**_snapshot(mgr), "reply": greeting}


@app.post("/api/conversations/{session_id}/end")
def end(session_id: str) -> dict:
    mgr = _get(session_id)
    mgr.end()
    return _snapshot(mgr)


@app.get("/api/conversations/{session_id}/transcript")
def transcript(session_id: str) -> dict:
    _get(session_id)
    return {"session_id": session_id, "turns": TranscriptLogger().read_session_turns(session_id)}


# ── transcripts / analytics ──────────────────────────────────────────────────
def _filtered_turns(session_id: str = "", prompt_version: str = "", state: str = "", q: str = "") -> list[dict]:
    turns = TranscriptLogger().read_all_turns()
    ql = q.strip().lower()
    return [
        t for t in turns
        if (not session_id or t.get("session_id") == session_id)
        and (not prompt_version or t.get("prompt_version") == prompt_version)
        and (not state or state in (t.get("state"), t.get("state_after")))
        and (not ql or ql in (t.get("user_message", "") + " " + t.get("assistant_response", "")).lower())
    ]


@app.get("/api/transcripts")
def transcripts(session_id: str = "", prompt_version: str = "", state: str = "", q: str = "") -> dict:
    all_turns = TranscriptLogger().read_all_turns()
    sessions: dict[str, dict] = {}
    for t in all_turns:
        s = sessions.setdefault(t["session_id"], {"session_id": t["session_id"], "turns": 0, "started": t.get("timestamp"), "prompt_version": t.get("prompt_version")})
        s["turns"] += 1
    turns = _filtered_turns(session_id, prompt_version, state, q)
    return {"source": "application_usage", "total_logged": len(all_turns), "count": len(turns),
            "sessions": list(sessions.values())[-200:], "turns": turns[-1000:]}


_CSV_FIELDS = ["session_id", "turn_number", "timestamp", "state", "state_after", "detected_intent", "prompt_version",
               "response_mode", "clarification_required", "fallback_used", "response_time_ms", "user_message", "assistant_response"]


def _csv_safe(v) -> str:
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v  # neutralise spreadsheet formula injection


@app.get("/api/transcripts/export")
def export_transcripts(format: str = "json", session_id: str = "", prompt_version: str = "", state: str = "", q: str = "") -> Response:
    turns = _filtered_turns(session_id, prompt_version, state, q)
    if format == "csv":
        buf = io.StringIO(); w = csv.writer(buf); w.writerow(_CSV_FIELDS)
        for t in turns:
            w.writerow([_csv_safe(t.get(f)) for f in _CSV_FIELDS])
        return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=voicebridge_transcripts.csv"})
    if format != "json":
        raise HTTPException(422, "format must be 'csv' or 'json'.")
    return Response(json.dumps(turns, indent=2, ensure_ascii=False), media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=voicebridge_transcripts.json"})


@app.delete("/api/transcripts")
def clear_transcripts() -> dict:
    return {"cleared": TranscriptLogger().clear_logs()}


@app.get("/api/analytics")
def analytics() -> dict:
    a = Analytics(EngagedTranscriptView())  # greeting-only page loads are not conversations
    return {"source": "application_usage", "summary": a.compute_summary(), "prompt_comparison": a.compute_prompt_comparison()}


# ── evaluation (synthetic scenarios) ─────────────────────────────────────────
def _results_file() -> Path:
    return Path(Config.RESULTS_DIR) / "evaluation_latest.json"


@app.post("/api/evaluation/run")
def run_evaluation() -> dict:
    report = Evaluator().run_all(prompt_versions=["A", "B"]).to_dict()
    report["generated_at"] = datetime.now().isoformat(timespec="seconds")
    report["synthetic"] = True
    _results_file().parent.mkdir(parents=True, exist_ok=True)
    _results_file().write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


@app.get("/api/evaluation/results")
def evaluation_results() -> dict:
    f = _results_file()
    if not f.exists():
        return {"available": False}
    data = json.loads(f.read_text(encoding="utf-8"))
    data.setdefault("synthetic", True)
    data.setdefault("generated_at", datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"))
    return {"available": True, **data}


# ── frontend (added in stage 2) ──────────────────────────────────────────────
if FRONTEND.is_dir():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND / "index.html")

"""VoiceBridge AI — Pydantic schemas for structured data."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ConversationState(str, Enum):
    """Explicit states of the conversation state machine."""
    GREETING = "GREETING"
    CONSENT = "CONSENT"
    INQUIRY_TYPE = "INQUIRY_TYPE"
    BASIC_DETAILS = "BASIC_DETAILS"
    CLARIFICATION = "CLARIFICATION"
    NEXT_STEPS = "NEXT_STEPS"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"
    COMPLETED = "COMPLETED"


class UserIntent(str, Enum):
    """Detected intent categories from user messages."""
    AFFIRMATIVE = "AFFIRMATIVE"
    NEGATIVE = "NEGATIVE"
    LOAN_TYPE_INQUIRY = "LOAN_TYPE_INQUIRY"
    PROCESS_INQUIRY = "PROCESS_INQUIRY"
    DOCUMENT_INQUIRY = "DOCUMENT_INQUIRY"
    GENERAL_INQUIRY = "GENERAL_INQUIRY"
    SKIP = "SKIP"
    RESTART = "RESTART"
    EXIT = "EXIT"
    HUMAN_REQUEST = "HUMAN_REQUEST"
    IRRELEVANT = "IRRELEVANT"
    UNCLEAR = "UNCLEAR"
    SENSITIVE_INFO = "SENSITIVE_INFO"
    GUARANTEE_REQUEST = "GUARANTEE_REQUEST"
    RATE_REQUEST = "RATE_REQUEST"
    CONTRADICTORY = "CONTRADICTORY"
    REPEATED_QUESTION = "REPEATED_QUESTION"
    CHANGE_MIND = "CHANGE_MIND"


class TurnRecord(BaseModel):
    """A single conversation turn for logging."""
    session_id: str
    turn_number: int
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    state: str
    state_after: str = ""  # state once the turn finished (state = state before)
    user_message: str
    assistant_response: str
    detected_intent: str
    clarification_required: bool = False
    fallback_used: bool = False
    prompt_version: str = "A"
    response_mode: str = "local"
    response_time_ms: float = 0.0
    evaluation_outcome: Optional[str] = None


class ConversationContext(BaseModel):
    """Tracks the full context of an ongoing conversation."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    current_state: ConversationState = ConversationState.GREETING
    previous_state: Optional[ConversationState] = None
    prompt_version: str = "A"
    response_mode: str = "local"
    turn_count: int = 0
    clarification_count: int = 0
    inquiry_topic: Optional[str] = None
    collected_details: dict = Field(default_factory=dict)
    history: list[dict] = Field(default_factory=list)
    is_active: bool = True
    clarification_target_state: Optional[ConversationState] = None


class LLMResponse(BaseModel):
    """Structured response expected from LLM."""
    response_text: str
    detected_intent: str = "GENERAL_INQUIRY"
    suggested_next_state: Optional[str] = None
    confidence: float = 0.8

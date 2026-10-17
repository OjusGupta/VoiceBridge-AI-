"""Tests for conversation recovery: unclear, irrelevant, restart, exit, skip, etc."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.conversation_manager import ConversationManager
from src.schemas import ConversationState


class TestUnclearResponse:
    """Test handling of unclear or ambiguous responses."""

    def test_maybe_triggers_clarification(self):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("maybe")
        assert mgr.current_state == ConversationState.CLARIFICATION

    def test_unclear_at_inquiry(self):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("yes")
        mgr.process_message("I don't know")
        assert mgr.current_state == ConversationState.CLARIFICATION

    def test_clarification_limit_moves_on(self):
        """After 2 failed clarifications, system should move on."""
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("yes")
        mgr.process_message("asdf")  # → clarification
        mgr.process_message("qwerty")  # 2nd unclear → should trigger limit
        # Should have moved past clarification
        assert mgr.current_state != ConversationState.CLARIFICATION


class TestIrrelevantResponse:
    """Test handling of off-topic messages."""

    def test_weather_question(self):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("yes")
        response = mgr.process_message("What is the weather?")
        assert "loan" in response.lower() or "help" in response.lower()

    def test_sports_question(self):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("yes")
        response = mgr.process_message("Who won the game last night?")
        assert mgr.current_state == ConversationState.CLARIFICATION


class TestSkipHandler:
    """Test skip handling."""

    def test_skip_at_details(self):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("yes")
        mgr.process_message("loan types")
        response = mgr.process_message("skip")
        assert "skip" in response.lower() or "next" in response.lower() or "move" in response.lower()


class TestRestartHandler:
    """Test restart handling."""

    def test_restart_resets_state(self):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("yes")
        mgr.process_message("loan types")
        response = mgr.process_message("restart")
        assert mgr.current_state == ConversationState.CONSENT
        assert "VoiceBridge" in response or "start" in response.lower()

    def test_restart_preserves_session(self):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        original_session = mgr.session_id
        mgr.process_message("restart")
        assert mgr.session_id == original_session


class TestExitHandler:
    """Test exit handling."""

    @pytest.mark.parametrize("exit_msg", ["stop", "goodbye", "exit", "quit", "bye"])
    def test_exit_commands(self, exit_msg):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("yes")
        mgr.process_message(exit_msg)
        assert mgr.current_state == ConversationState.COMPLETED
        assert not mgr.is_active

    def test_exit_from_greeting(self):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("bye")
        assert mgr.current_state == ConversationState.COMPLETED


class TestHumanHandoff:
    """Test human handoff handling."""

    @pytest.mark.parametrize("human_msg", [
        "I want to talk to a human",
        "speak to a representative",
        "transfer me to an agent",
        "live agent please",
    ])
    def test_human_request(self, human_msg):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("yes")
        response = mgr.process_message(human_msg)
        assert mgr.current_state == ConversationState.HUMAN_HANDOFF
        assert "simulated" in response.lower() or "demo" in response.lower()

    def test_handoff_then_continue(self):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("yes")
        mgr.process_message("talk to a human")
        assert mgr.current_state == ConversationState.HUMAN_HANDOFF
        mgr.process_message("yes")
        assert mgr.current_state == ConversationState.INQUIRY_TYPE


class TestChangeMind:
    """Test user changing their mind."""

    def test_change_mind_at_inquiry(self):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("yes")
        mgr.process_message("loan types")
        response = mgr.process_message("actually I changed my mind")
        # Should still be in a valid state
        assert mgr.current_state in (
            ConversationState.BASIC_DETAILS,
            ConversationState.INQUIRY_TYPE,
            ConversationState.NEXT_STEPS,
            ConversationState.COMPLETED,
        )


class TestEmptyInput:
    """Test empty input handling."""

    def test_empty_string(self):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        response = mgr.process_message("")
        assert response and len(response) > 5

    def test_whitespace_only(self):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        response = mgr.process_message("   ")
        assert response and len(response) > 5

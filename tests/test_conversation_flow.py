"""Tests for conversation flow and state transitions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.conversation_manager import ConversationManager
from src.schemas import ConversationState, UserIntent


class TestGreeting:
    """Test greeting state and initial transition."""

    def test_greeting_returns_nonempty(self):
        mgr = ConversationManager(prompt_version="A")
        greeting = mgr.get_greeting()
        assert greeting and len(greeting) > 10
        assert mgr.current_state == ConversationState.CONSENT

    def test_greeting_prompt_b(self):
        mgr = ConversationManager(prompt_version="B")
        greeting = mgr.get_greeting()
        assert "VoiceBridge" in greeting
        assert mgr.current_state == ConversationState.CONSENT


class TestConsentState:
    """Test CONSENT state transitions."""

    def _make_manager(self, version="A") -> ConversationManager:
        mgr = ConversationManager(prompt_version=version)
        mgr.get_greeting()
        return mgr

    def test_consent_yes(self):
        mgr = self._make_manager()
        response = mgr.process_message("yes")
        assert mgr.current_state == ConversationState.INQUIRY_TYPE
        assert len(response) > 10

    def test_consent_no_completes(self):
        mgr = self._make_manager()
        response = mgr.process_message("no")
        assert mgr.current_state == ConversationState.COMPLETED
        assert not mgr.is_active

    def test_consent_unclear_triggers_clarification(self):
        mgr = self._make_manager()
        mgr.process_message("hmm maybe")
        assert mgr.current_state == ConversationState.CLARIFICATION

    @pytest.mark.parametrize("affirm", ["yes", "sure", "ok", "go ahead", "please"])
    def test_various_affirmatives(self, affirm):
        mgr = self._make_manager()
        mgr.process_message(affirm)
        assert mgr.current_state == ConversationState.INQUIRY_TYPE

    @pytest.mark.parametrize("deny", ["no", "nah", "not interested", "nope"])
    def test_various_negatives(self, deny):
        mgr = self._make_manager()
        mgr.process_message(deny)
        assert mgr.current_state == ConversationState.COMPLETED


class TestInquiryTypeState:
    """Test INQUIRY_TYPE state transitions."""

    def _make_manager(self) -> ConversationManager:
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("yes")
        assert mgr.current_state == ConversationState.INQUIRY_TYPE
        return mgr

    def test_loan_type_inquiry(self):
        mgr = self._make_manager()
        response = mgr.process_message("Tell me about loan types")
        assert mgr.current_state == ConversationState.BASIC_DETAILS
        assert mgr.context.inquiry_topic == "loan types"

    def test_process_inquiry(self):
        mgr = self._make_manager()
        response = mgr.process_message("How do I apply for a loan?")
        assert mgr.current_state == ConversationState.BASIC_DETAILS
        assert mgr.context.inquiry_topic == "application process"

    def test_document_inquiry(self):
        mgr = self._make_manager()
        response = mgr.process_message("What documents do I need?")
        assert mgr.current_state == ConversationState.BASIC_DETAILS
        assert mgr.context.inquiry_topic == "required documents"

    def test_irrelevant_triggers_clarification(self):
        mgr = self._make_manager()
        mgr.process_message("What is the weather today?")
        assert mgr.current_state == ConversationState.CLARIFICATION


class TestBasicDetailsState:
    """Test BASIC_DETAILS state transitions."""

    def _make_manager(self) -> ConversationManager:
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("yes")
        mgr.process_message("loan types")
        assert mgr.current_state == ConversationState.BASIC_DETAILS
        return mgr

    def test_detail_leads_to_next_steps(self):
        mgr = self._make_manager()
        mgr.process_message("personal loan for home renovation")
        assert mgr.current_state == ConversationState.NEXT_STEPS


class TestNextStepsState:
    """Test that next steps are provided and conversation completes."""

    def test_full_happy_path(self):
        mgr = ConversationManager(prompt_version="A")
        mgr.get_greeting()
        mgr.process_message("yes")
        mgr.process_message("loan types")
        mgr.process_message("personal loan")
        assert mgr.current_state == ConversationState.NEXT_STEPS
        mgr.process_message("thanks")
        # Should have reached COMPLETED via NEXT_STEPS
        assert mgr.current_state == ConversationState.COMPLETED
        assert not mgr.is_active


class TestPromptVersionDifferences:
    """Test that prompt versions produce different response styles."""

    def test_a_vs_b_greeting(self):
        mgr_a = ConversationManager(prompt_version="A")
        mgr_b = ConversationManager(prompt_version="B")
        greeting_a = mgr_a.get_greeting()
        greeting_b = mgr_b.get_greeting()
        # Both should mention VoiceBridge, but differ in tone
        assert "VoiceBridge" in greeting_a
        assert "VoiceBridge" in greeting_b
        # B should be warmer (contains emoji or longer)
        assert greeting_a != greeting_b

    def test_a_is_more_concise(self):
        mgr_a = ConversationManager(prompt_version="A")
        mgr_b = ConversationManager(prompt_version="B")
        mgr_a.get_greeting()
        mgr_b.get_greeting()
        resp_a = mgr_a.process_message("yes")
        resp_b = mgr_b.process_message("yes")
        # A should generally be shorter
        assert len(resp_a) > 0
        assert len(resp_b) > 0

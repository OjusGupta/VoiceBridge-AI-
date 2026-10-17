"""VoiceBridge AI — Response generator module.

Produces assistant responses using either local templates or the LLM client.
Separates response generation from state management and intent detection.
"""

from __future__ import annotations

from typing import Optional

from prompts.conversation_prompts import get_local_response, get_system_prompt
from src.llm_client import LLMClient
from src.schemas import ConversationContext, ConversationState, UserIntent


class ResponseGenerator:
    """Generates assistant responses from intent + state, using local or LLM mode."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self._llm = llm_client

    @property
    def is_llm_mode(self) -> bool:
        return self._llm is not None and self._llm.is_available

    def generate(
        self,
        context: ConversationContext,
        intent: UserIntent,
        user_message: str,
    ) -> tuple[str, bool]:
        """Generate a response for the current state and detected intent.

        Args:
            context: Current conversation context.
            intent: Detected user intent.
            user_message: The raw user message.

        Returns:
            Tuple of (response_text, fallback_used).
        """
        # Try LLM first if available
        if self.is_llm_mode:
            llm_response = self._try_llm(context, user_message)
            if llm_response:
                return llm_response, False

        # Fall back to local deterministic responses
        return self._local_response(context, intent), False

    def _try_llm(self, context: ConversationContext, user_message: str) -> Optional[str]:
        """Attempt to get a response from the LLM."""
        if not self._llm:
            return None

        system_prompt = get_system_prompt(context.prompt_version)
        history = [
            {"role": entry["role"], "content": entry["content"]}
            for entry in context.history[-10:]  # Keep last 10 turns for context
        ]

        result = self._llm.generate_response(system_prompt, history, user_message)
        if result:
            return result.response_text
        return None

    def _local_response(self, context: ConversationContext, intent: UserIntent) -> str:
        """Generate a deterministic local-mode response based on state + intent."""
        v = context.prompt_version
        state = context.current_state

        # ── Cross-state intents (handled regardless of current state) ──
        if intent == UserIntent.SENSITIVE_INFO:
            return get_local_response(v, "sensitive_info_warning")

        if intent == UserIntent.EXIT:
            return get_local_response(v, "exit")

        if intent == UserIntent.RESTART:
            return get_local_response(v, "restart")

        if intent == UserIntent.HUMAN_REQUEST:
            return get_local_response(v, "human_handoff")

        if intent == UserIntent.GUARANTEE_REQUEST:
            return get_local_response(v, "guarantee_denial")

        if intent == UserIntent.RATE_REQUEST:
            return get_local_response(v, "rate_denial")

        if intent == UserIntent.SKIP:
            return get_local_response(v, "skip")

        # ── State-specific responses ──
        if state == ConversationState.GREETING:
            return get_local_response(v, "greeting")

        if state == ConversationState.CONSENT:
            if intent == UserIntent.AFFIRMATIVE:
                return get_local_response(v, "consent_yes")
            elif intent == UserIntent.NEGATIVE:
                return get_local_response(v, "consent_no")
            else:
                return get_local_response(v, "consent_unclear")

        if state == ConversationState.INQUIRY_TYPE:
            if intent == UserIntent.LOAN_TYPE_INQUIRY:
                return get_local_response(v, "inquiry_loan_types")
            elif intent == UserIntent.PROCESS_INQUIRY:
                return get_local_response(v, "inquiry_process")
            elif intent == UserIntent.DOCUMENT_INQUIRY:
                return get_local_response(v, "inquiry_documents")
            elif intent == UserIntent.IRRELEVANT:
                return get_local_response(v, "irrelevant")
            elif intent == UserIntent.UNCLEAR:
                return get_local_response(v, "unclear")
            else:
                return get_local_response(v, "inquiry_general")

        if state == ConversationState.BASIC_DETAILS:
            if intent in (UserIntent.IRRELEVANT, UserIntent.UNCLEAR):
                return get_local_response(v, "unclear")
            return get_local_response(v, "detail_collected")

        if state == ConversationState.CLARIFICATION:
            if context.clarification_count >= 2:
                return get_local_response(v, "clarification_limit")
            if intent == UserIntent.IRRELEVANT:
                return get_local_response(v, "irrelevant")
            if intent == UserIntent.UNCLEAR:
                return get_local_response(v, "unclear")
            # Successful clarification — provide relevant response
            return get_local_response(v, "detail_collected")

        if state == ConversationState.NEXT_STEPS:
            return get_local_response(v, "next_steps")

        if state == ConversationState.HUMAN_HANDOFF:
            return get_local_response(v, "human_handoff")

        if state == ConversationState.COMPLETED:
            topic = context.inquiry_topic or "loan inquiries"
            return get_local_response(v, "summary", topic=topic)

        return get_local_response(v, "fallback")

"""VoiceBridge AI — Conversation manager (state machine).

Orchestrates the conversation flow by combining intent detection,
state transitions, response generation, and transcript logging.
"""

from __future__ import annotations

import time
from typing import Optional

from src.config import Config
from src.intent_detection import detect_intent
from src.response_generator import ResponseGenerator
from src.safety import check_response_safety, sanitize_user_input
from src.schemas import ConversationContext, ConversationState, TurnRecord, UserIntent
from src.transcript_logger import TranscriptLogger


class ConversationManager:
    """State-machine-based conversation manager.

    Each call to process_message() detects intent, transitions state,
    generates a response, and logs the turn.
    """

    def __init__(
        self,
        prompt_version: str = "A",
        response_generator: Optional[ResponseGenerator] = None,
        transcript_logger: Optional[TranscriptLogger] = None,
    ) -> None:
        self.context = ConversationContext(prompt_version=prompt_version)
        self.context.response_mode = "llm" if (
            response_generator and response_generator.is_llm_mode
        ) else "local"
        self._generator = response_generator or ResponseGenerator()
        self._logger = transcript_logger or TranscriptLogger()
        self.last_turn: Optional[TurnRecord] = None  # most recent logged turn (for APIs/UIs)

    @property
    def session_id(self) -> str:
        return self.context.session_id

    @property
    def current_state(self) -> ConversationState:
        return self.context.current_state

    @property
    def is_active(self) -> bool:
        return self.context.is_active

    def get_greeting(self) -> str:
        """Generate the initial greeting message.

        Returns:
            The greeting response text.
        """
        response = self._generator._local_response(self.context, UserIntent.AFFIRMATIVE)
        self.context.current_state = ConversationState.CONSENT
        self.context.history.append({"role": "assistant", "content": response})

        # Log the greeting turn
        record = TurnRecord(
            session_id=self.context.session_id,
            turn_number=0,
            state=ConversationState.GREETING.value,
            state_after=self.context.current_state.value,
            user_message="",
            assistant_response=response,
            detected_intent="GREETING",
            prompt_version=self.context.prompt_version,
            response_mode=self.context.response_mode,
        )
        self._logger.log_turn(record)

        return response

    def process_message(self, user_message: str) -> str:
        """Process a user message through the full pipeline.

        Steps:
        1. Sanitize input
        2. Detect intent
        3. Transition state
        4. Generate response
        5. Log turn
        6. Update history

        Args:
            user_message: Raw user input.

        Returns:
            Assistant response text.
        """
        start_time = time.time()

        # Sanitize
        user_message = sanitize_user_input(user_message)
        if not user_message:
            return self._generator._local_response(self.context, UserIntent.UNCLEAR)

        # Detect intent
        intent = detect_intent(user_message)

        # Save previous state for logging
        prev_state = self.context.current_state

        # Handle cross-state intents first
        clarification_required = False
        fallback_used = False

        if intent == UserIntent.EXIT:
            response = self._handle_exit(intent, user_message)
        elif intent == UserIntent.RESTART:
            response = self._handle_restart(intent, user_message)
        elif intent == UserIntent.HUMAN_REQUEST:
            response = self._handle_human_handoff(intent, user_message)
        elif intent == UserIntent.SENSITIVE_INFO:
            response, _ = self._generator.generate(self.context, intent, user_message)
        elif intent == UserIntent.GUARANTEE_REQUEST:
            response, _ = self._generator.generate(self.context, intent, user_message)
        elif intent == UserIntent.RATE_REQUEST:
            response, _ = self._generator.generate(self.context, intent, user_message)
        else:
            # State-specific processing
            response, clarification_required, fallback_used = self._process_state(
                intent, user_message
            )

        # Output safety applies to local AND LLM responses
        is_safe, _reason = check_response_safety(response)
        if not is_safe:
            from prompts.conversation_prompts import get_local_response
            response = get_local_response(self.context.prompt_version, "fallback")
            fallback_used = True

        elapsed_ms = (time.time() - start_time) * 1000

        # Never persist or forward credentials: redact before history and logging
        stored_message = "[REDACTED: sensitive information]" if intent == UserIntent.SENSITIVE_INFO else user_message

        # Update context
        self.context.turn_count += 1
        self.context.history.append({"role": "user", "content": stored_message})
        self.context.history.append({"role": "assistant", "content": response})

        # Log the turn
        record = TurnRecord(
            session_id=self.context.session_id,
            turn_number=self.context.turn_count,
            state=prev_state.value,
            state_after=self.context.current_state.value,
            user_message=stored_message,
            assistant_response=response,
            detected_intent=intent.value,
            clarification_required=clarification_required,
            fallback_used=fallback_used,
            prompt_version=self.context.prompt_version,
            response_mode=self.context.response_mode,
            response_time_ms=round(elapsed_ms, 2),
        )
        self._logger.log_turn(record)
        self.last_turn = record

        return response

    def end(self) -> None:
        """End the conversation without a user message (UI 'End' button)."""
        self._transition(ConversationState.COMPLETED)
        self.context.is_active = False

    def _process_state(
        self, intent: UserIntent, user_message: str
    ) -> tuple[str, bool, bool]:
        """Process intent within the current conversation state.

        Returns:
            Tuple of (response, clarification_required, fallback_used).
        """
        state = self.context.current_state
        clarification_required = False
        fallback_used = False

        if state == ConversationState.CONSENT:
            return self._handle_consent(intent, user_message)

        elif state == ConversationState.INQUIRY_TYPE:
            return self._handle_inquiry_type(intent, user_message)

        elif state == ConversationState.BASIC_DETAILS:
            return self._handle_basic_details(intent, user_message)

        elif state == ConversationState.CLARIFICATION:
            return self._handle_clarification(intent, user_message)

        elif state == ConversationState.NEXT_STEPS:
            return self._handle_next_steps(intent, user_message)

        elif state == ConversationState.HUMAN_HANDOFF:
            # After handoff, user can continue or exit
            if intent == UserIntent.AFFIRMATIVE:
                self._transition(ConversationState.INQUIRY_TYPE)
                response, _ = self._generator.generate(self.context, intent, user_message)
                return response, False, False
            elif intent == UserIntent.NEGATIVE:
                return self._handle_exit(intent, user_message), False, False
            response, _ = self._generator.generate(self.context, intent, user_message)
            return response, False, False

        elif state == ConversationState.COMPLETED:
            # Already completed
            response, fallback_used = self._generator.generate(
                self.context, intent, user_message
            )
            return response, False, fallback_used

        # Fallback for unexpected states
        response, _ = self._generator.generate(self.context, intent, user_message)
        return response, False, True

    def _handle_consent(
        self, intent: UserIntent, user_message: str
    ) -> tuple[str, bool, bool]:
        """Handle the CONSENT state."""
        if intent == UserIntent.AFFIRMATIVE:
            self._transition(ConversationState.INQUIRY_TYPE)
            response, _ = self._generator.generate(self.context, intent, user_message)
            return response, False, False
        elif intent == UserIntent.NEGATIVE:
            self._transition(ConversationState.COMPLETED)
            self.context.is_active = False
            response, _ = self._generator.generate(
                self.context, UserIntent.NEGATIVE, user_message
            )
            return response, False, False
        else:
            # Unclear consent — ask for clarification
            self._enter_clarification(ConversationState.CONSENT)
            response, _ = self._generator.generate(self.context, intent, user_message)
            return response, True, False

    def _handle_inquiry_type(
        self, intent: UserIntent, user_message: str
    ) -> tuple[str, bool, bool]:
        """Handle the INQUIRY_TYPE state."""
        topic_intents = {
            UserIntent.LOAN_TYPE_INQUIRY: "loan types",
            UserIntent.PROCESS_INQUIRY: "application process",
            UserIntent.DOCUMENT_INQUIRY: "required documents",
            UserIntent.GENERAL_INQUIRY: "general loan information",
        }

        if intent in topic_intents:
            self.context.inquiry_topic = topic_intents[intent]
            response, _ = self._generator.generate(self.context, intent, user_message)  # answer first, in the state the user asked in
            self._transition(ConversationState.BASIC_DETAILS)
            return response, False, False
        elif intent == UserIntent.AFFIRMATIVE:
            # User said yes but didn't specify — ask again
            self.context.inquiry_topic = "general loan information"
            response, _ = self._generator.generate(self.context, intent, user_message)  # answer first, in the state the user asked in
            self._transition(ConversationState.BASIC_DETAILS)
            return response, False, False
        elif intent in (UserIntent.IRRELEVANT, UserIntent.UNCLEAR, UserIntent.NEGATIVE):
            self._enter_clarification(ConversationState.INQUIRY_TYPE)
            response, _ = self._generator.generate(self.context, intent, user_message)
            return response, True, False
        elif intent == UserIntent.CHANGE_MIND:
            response, _ = self._generator.generate(self.context, intent, user_message)
            return response, False, False
        else:
            # Treat as general inquiry
            self.context.inquiry_topic = "general loan information"
            response, _ = self._generator.generate(self.context, intent, user_message)  # answer first, in the state the user asked in
            self._transition(ConversationState.BASIC_DETAILS)
            return response, False, False

    def _handle_basic_details(
        self, intent: UserIntent, user_message: str
    ) -> tuple[str, bool, bool]:
        """Handle the BASIC_DETAILS state."""
        if intent == UserIntent.SKIP:
            self._transition(ConversationState.NEXT_STEPS)
            from prompts.conversation_prompts import get_local_response
            v = self.context.prompt_version
            skip_msg = get_local_response(v, "skip")
            next_steps = get_local_response(v, "next_steps")
            return f"{skip_msg}\n\n{next_steps}", False, False

        if intent in (UserIntent.IRRELEVANT, UserIntent.UNCLEAR):
            self._enter_clarification(ConversationState.BASIC_DETAILS)
            response, _ = self._generator.generate(self.context, intent, user_message)
            return response, True, False

        if intent == UserIntent.CHANGE_MIND:
            self.context.inquiry_topic = None
            response, _ = self._generator.generate(self.context, intent, user_message)
            return response, False, False

        topic_intents = {
            UserIntent.LOAN_TYPE_INQUIRY: "loan types",
            UserIntent.PROCESS_INQUIRY: "application process",
            UserIntent.DOCUMENT_INQUIRY: "required documents",
            UserIntent.GENERAL_INQUIRY: "general loan information",
        }
        if intent in topic_intents and not self.context.inquiry_topic:
            self.context.inquiry_topic = topic_intents[intent]
            response, _ = self._generator.generate(self.context, intent, user_message)
            return response, False, False

        # Collect the detail and transition to NEXT_STEPS
        self.context.collected_details["user_detail"] = user_message
        self._transition(ConversationState.NEXT_STEPS)

        from prompts.conversation_prompts import get_local_response
        v = self.context.prompt_version
        ack = get_local_response(v, "detail_collected")
        next_steps = get_local_response(v, "next_steps")
        response = f"{ack}\n\n{next_steps}"
        return response, False, False

    def _handle_clarification(
        self, intent: UserIntent, user_message: str
    ) -> tuple[str, bool, bool]:
        """Handle the CLARIFICATION state."""
        target = self.context.clarification_target_state

        if intent in (UserIntent.IRRELEVANT, UserIntent.UNCLEAR):
            self.context.clarification_count += 1
            if self.context.clarification_count >= Config.MAX_CLARIFICATION_ATTEMPTS:
                # Too many clarification attempts — fallback and move on
                self.context.clarification_count = 0
                if target == ConversationState.CONSENT:
                    self._transition(ConversationState.COMPLETED)
                    self.context.is_active = False
                elif target == ConversationState.INQUIRY_TYPE:
                    self._transition(ConversationState.BASIC_DETAILS)
                else:
                    self._transition(ConversationState.NEXT_STEPS)
                response, _ = self._generator.generate(self.context, intent, user_message)
                return response, True, True

            # Still unclear — stay in clarification
            response, _ = self._generator.generate(self.context, intent, user_message)
            return response, True, False

        # User provided a clear, valid intent — clarification successful!
        self.context.clarification_count = 0
        if target:
            self._transition(target)
            return self._process_state(intent, user_message)

        # No target — move to next steps
        self._transition(ConversationState.NEXT_STEPS)
        response, _ = self._generator.generate(self.context, intent, user_message)
        return response, False, False

    def _handle_next_steps(
        self, intent: UserIntent, user_message: str
    ) -> tuple[str, bool, bool]:
        """Handle the NEXT_STEPS state."""
        self._transition(ConversationState.COMPLETED)
        topic = self.context.inquiry_topic or "loan inquiries"
        from prompts.conversation_prompts import get_local_response
        summary = get_local_response(self.context.prompt_version, "summary", topic=topic)
        self.context.is_active = False
        return summary, False, False

    def _handle_exit(self, intent: UserIntent, user_message: str) -> str:
        """Handle exit intent from any state."""
        self._transition(ConversationState.COMPLETED)
        self.context.is_active = False
        response, _ = self._generator.generate(self.context, UserIntent.EXIT, user_message)
        return response

    def _handle_restart(self, intent: UserIntent, user_message: str) -> str:
        """Handle restart intent — reset context but keep session ID."""
        old_session = self.context.session_id
        old_version = self.context.prompt_version
        old_mode = self.context.response_mode
        self.context = ConversationContext(
            session_id=old_session,
            prompt_version=old_version,
            response_mode=old_mode,
        )
        self.context.current_state = ConversationState.CONSENT
        response, _ = self._generator.generate(self.context, intent, user_message)
        return response

    def _handle_human_handoff(self, intent: UserIntent, user_message: str) -> str:
        """Handle human handoff request."""
        self._transition(ConversationState.HUMAN_HANDOFF)
        response, _ = self._generator.generate(self.context, intent, user_message)
        return response

    def _transition(self, new_state: ConversationState) -> None:
        """Transition to a new conversation state."""
        self.context.previous_state = self.context.current_state
        self.context.current_state = new_state

    def _enter_clarification(self, return_state: ConversationState) -> None:
        """Enter clarification state, remembering where to return."""
        self.context.previous_state = self.context.current_state
        self.context.clarification_target_state = return_state
        self.context.current_state = ConversationState.CLARIFICATION
        self.context.clarification_count = 1

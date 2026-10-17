"""VoiceBridge AI — LLM client module.

Provides an optional OpenAI-compatible API client.
Falls back gracefully when no API key is configured.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.config import Config
from src.schemas import LLMResponse
from src.safety import check_response_safety

logger = logging.getLogger(__name__)


class LLMClient:
    """Wrapper around OpenAI-compatible API for response generation."""

    def __init__(self) -> None:
        self._client = None
        if Config.is_llm_enabled():
            try:
                from openai import OpenAI
                kwargs = {"api_key": Config.OPENAI_API_KEY}
                if Config.OPENAI_BASE_URL:
                    kwargs["base_url"] = Config.OPENAI_BASE_URL
                self._client = OpenAI(**kwargs)
                logger.info("LLM client initialized successfully.")
            except Exception as e:
                logger.warning("Failed to initialize LLM client: %s", e)
                self._client = None

    @property
    def is_available(self) -> bool:
        """Check if the LLM client is ready for requests."""
        return self._client is not None

    def generate_response(
        self,
        system_prompt: str,
        conversation_history: list[dict],
        user_message: str,
    ) -> Optional[LLMResponse]:
        """Generate a response using the LLM API.

        Args:
            system_prompt: The system-level instructions.
            conversation_history: List of prior messages [{"role": ..., "content": ...}].
            user_message: The latest user message.

        Returns:
            An LLMResponse if successful, or None on failure.
        """
        if not self.is_available:
            return None

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})

        try:
            response = self._client.chat.completions.create(
                model=Config.LLM_MODEL_NAME,
                messages=messages,
                temperature=0.7,
                max_tokens=300,
                timeout=Config.LLM_TIMEOUT,
            )

            content = response.choices[0].message.content
            if not content or not content.strip():
                logger.warning("LLM returned empty response.")
                return None

            # Safety check on LLM output
            is_safe, reason = check_response_safety(content)
            if not is_safe:
                logger.warning("LLM response failed safety check: %s", reason)
                return None

            # Try to parse structured response, fall back to plain text
            try:
                parsed = json.loads(content)
                return LLMResponse(**parsed)
            except (json.JSONDecodeError, Exception):
                return LLMResponse(response_text=content.strip())

        except Exception as e:
            logger.warning("LLM API call failed: %s", e)
            return None

"""VoiceBridge AI — Configuration module."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Central configuration for VoiceBridge AI."""

    # LLM settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "")
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "gpt-3.5-turbo")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "15"))

    # Conversation limits
    MAX_CLARIFICATION_ATTEMPTS: int = 2
    MAX_CONVERSATION_TURNS: int = 50

    # Logging
    LOG_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    RESULTS_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")

    @classmethod
    def is_llm_enabled(cls) -> bool:
        """Check if an LLM API key is configured and non-empty."""
        return bool(cls.OPENAI_API_KEY and cls.OPENAI_API_KEY.strip())

    @classmethod
    def get_mode_label(cls) -> str:
        """Return a human-readable label for the current response mode."""
        return "LLM mode" if cls.is_llm_enabled() else "Local demo mode"

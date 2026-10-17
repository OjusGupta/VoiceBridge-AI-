"""VoiceBridge AI — Safety module.

Centralized safety checks that run before and after response generation.
These checks enforce constraints regardless of whether the response comes
from local rules or an LLM.
"""

from __future__ import annotations

import re

# Phrases that must never appear in assistant output
_BANNED_PHRASES = [
    "you are approved",
    "your loan is approved",
    "i can approve",
    "guaranteed approval",
    "i guarantee",
    "i promise you will",
    "your interest rate is",
    "your rate will be",
    "your emi is",
    "your monthly payment is",
    "i am transferring you",
    "connecting you now",
    "i have transferred",
    "please share your password",
    "please provide your ssn",
    "tell me your account number",
    "send me your otp",
    "what is your pin",
]

# Regex patterns for hallucinated numbers (rate-like or amount-like)
_HALLUCINATED_RATE = re.compile(
    r"\b\d{1,2}(\.\d{1,2})?\s*%\s*(interest|apr|rate|annual)", re.IGNORECASE
)
_HALLUCINATED_AMOUNT = re.compile(
    r"(approved for|eligible for|you can get)\s*\$[\d,]+", re.IGNORECASE
)


def check_response_safety(response_text: str) -> tuple[bool, str]:
    """Validate an assistant response against safety constraints.

    Args:
        response_text: The response text to check.

    Returns:
        Tuple of (is_safe, reason). If is_safe is False, reason explains why.
    """
    lower = response_text.lower()

    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            return False, f"Contains banned phrase: '{phrase}'"

    if _HALLUCINATED_RATE.search(response_text):
        return False, "Contains a specific interest rate or APR figure"

    if _HALLUCINATED_AMOUNT.search(response_text):
        return False, "Contains a specific approved dollar amount"

    return True, ""


def sanitize_user_input(user_message: str) -> str:
    """Basic input sanitization.

    Removes excessively long inputs and strips control characters.
    Does NOT redact sensitive information — that's handled by intent detection
    so we can warn the user.

    Args:
        user_message: Raw user input.

    Returns:
        Sanitized input string.
    """
    # Limit input length
    if len(user_message) > 2000:
        user_message = user_message[:2000]

    # Remove control characters (keep newlines and tabs)
    user_message = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", user_message)

    return user_message.strip()

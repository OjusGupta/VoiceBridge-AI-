"""VoiceBridge AI — Intent detection module.

Uses rule-based keyword/pattern matching for local mode.
Intent detection is separated from response generation for clarity and testability.
"""

from __future__ import annotations

import re
from src.schemas import UserIntent


# ─── Keyword / pattern sets ─────────────────────────────────────────────────

_AFFIRMATIVE = {
    "yes", "yeah", "yep", "sure", "ok", "okay", "alright", "go ahead",
    "continue", "let's go", "proceed", "absolutely", "of course", "please",
    "yea", "let's do it", "sounds good", "i'd like to", "i would like to",
    "definitely", "why not", "thanks", "thank you", "great", "got it", "understood",
}

_NEGATIVE = {
    "no", "nah", "nope", "not really", "no thanks", "no thank you",
    "i don't want", "not interested", "decline",
}

_EXIT = {
    "stop", "exit", "goodbye", "bye", "quit", "end", "close",
    "leave", "done", "that's all", "i'm done", "finish", "no more",
}

_SKIP = {"skip", "next", "pass on this", "move on", "skip this"}

_RESTART = {"restart", "start over", "start again", "reset", "begin again", "new conversation"}

_HUMAN = {
    "human", "agent", "representative", "real person",
    "speak to someone", "talk to a human", "talk to someone",
    "transfer me", "live agent", "customer service", "operator",
}

_LOAN_TYPE_KEYWORDS = {
    "loan type", "types of loan", "kind of loan", "personal loan",
    "home loan", "mortgage", "auto loan", "car loan", "education loan",
    "student loan", "business loan", "loan options", "loan categories",
    "what loans",
}

_PROCESS_KEYWORDS = {
    "process", "how to apply", "application", "steps", "procedure",
    "how does it work", "how do i", "apply for", "application process",
    "how to get", "eligibility",
}

_DOCUMENT_KEYWORDS = {
    "document", "documents", "paperwork", "what do i need", "what papers",
    "required documents", "documentation", "what to bring", "proof",
}

_GUARANTEE_KEYWORDS = {
    "guarantee", "guaranteed", "will i get", "am i approved", "approve me",
    "can you approve", "approve my", "100%", "certain", "promise", "assured",
    "will i be approved", "definitely get", "approved", "approval",
    "system:", "ignore all previous", "developer mode",
}

_RATE_KEYWORDS = {
    "interest rate", "what rate", "exact rate", "how much interest",
    "apr", "emi", "monthly payment", "how long", "approval time",
    "how many days", "when will i get",
}

# Patterns for sensitive information (simplified, not exhaustive)
_SENSITIVE_PATTERNS = [
    r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b",       # SSN-like
    r"\b\d{10,16}\b",                              # Long number (card/account)
    r"\b\d{4}[-.\s]?\d{4}[-.\s]?\d{4}[-.\s]?\d{4}\b",  # Card number
    r"\bpassword\s*[:=]\s*\S+",                    # Password disclosure
    r"\bpin\s*[:=]\s*\d+",                         # PIN disclosure
    r"\botp\s*(?:[:=]|is)?\s*\d{4,}",             # OTP disclosure (handles "OTP is 483921")
    r"\baadhaar\b",                                # Aadhaar (Indian ID)
    r"\bssn\b",                                    # SSN mention
]

_CHANGE_MIND = {
    "actually", "wait", "change my mind", "changed my mind",
    "on second thought", "never mind", "different",
    "i meant", "let me change",
}


def _normalize(text: str) -> str:
    """Lowercase and strip whitespace."""
    return text.lower().strip()


def _contains_any(text: str, keywords: set[str]) -> bool:
    """Check if text contains any keyword from the set.

    For short keywords (≤3 chars), uses word-boundary regex to avoid
    false positives like 'no' matching in 'know'.
    """
    text_lower = _normalize(text)
    for kw in keywords:
        if len(kw) <= 3:
            # Use word-boundary regex for short keywords
            if re.search(rf'\b{re.escape(kw)}\b', text_lower):
                return True
        else:
            if kw in text_lower:
                return True
    return False


def _contains_human_keyword(text: str) -> bool:
    """Check for human-handoff keywords using word boundaries to avoid false
    positives like 'person' in 'personal'.
    """
    text_lower = _normalize(text)
    # Multi-word phrases first (exact substring match is fine)
    multi_word = {
        "real person", "speak to someone", "talk to a human", "talk to someone",
        "transfer me", "live agent", "customer service",
    }
    if any(kw in text_lower for kw in multi_word):
        return True

    # Single words — use word-boundary regex to avoid false positives
    single_words = ["human", "agent", "representative", "operator"]
    for word in single_words:
        if re.search(rf"\b{word}\b", text_lower):
            # Avoid matching "agent" in context of loan topics
            return True

    return False


def _matches_sensitive_pattern(text: str) -> bool:
    """Check if text matches any sensitive information pattern."""
    for pattern in _SENSITIVE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def detect_intent(user_message: str) -> UserIntent:
    """Detect the user's intent from their message text.

    Priority order matters: safety-critical intents are checked first,
    then topic intents (to avoid false positives with control keywords
    embedded in topic phrases like 'personal loan'), then control intents,
    then sentiment fallback.

    Args:
        user_message: Raw user input text.

    Returns:
        The detected UserIntent enum value.
    """
    if not user_message or not user_message.strip():
        return UserIntent.UNCLEAR

    text = _normalize(user_message)

    # 1. Safety-critical: sensitive info
    if _matches_sensitive_pattern(user_message):
        return UserIntent.SENSITIVE_INFO

    # 2. Control intents that are unambiguous
    if _contains_any(text, _EXIT):
        return UserIntent.EXIT

    if _contains_any(text, _RESTART):
        return UserIntent.RESTART

    if _contains_any(text, _SKIP):
        return UserIntent.SKIP

    # 3. Financial safety intents
    if _contains_any(text, _GUARANTEE_KEYWORDS):
        return UserIntent.GUARANTEE_REQUEST

    if _contains_any(text, _RATE_KEYWORDS):
        return UserIntent.RATE_REQUEST

    # 4. Topic intents — BEFORE human check so "personal loan" isn't misdetected
    if _contains_any(text, _LOAN_TYPE_KEYWORDS):
        return UserIntent.LOAN_TYPE_INQUIRY

    if _contains_any(text, _PROCESS_KEYWORDS):
        return UserIntent.PROCESS_INQUIRY

    if _contains_any(text, _DOCUMENT_KEYWORDS):
        return UserIntent.DOCUMENT_INQUIRY

    # 5. Human request — AFTER topic intents, using word-boundary matching
    if _contains_human_keyword(text):
        return UserIntent.HUMAN_REQUEST

    # 6. Mind-change detection
    if _contains_any(text, _CHANGE_MIND):
        return UserIntent.CHANGE_MIND

    # 7. Affirmative / Negative (after topics)
    if _contains_any(text, _AFFIRMATIVE):
        return UserIntent.AFFIRMATIVE

    if _contains_any(text, _NEGATIVE):
        return UserIntent.NEGATIVE

    # 8. Very short or meaningless input
    if len(text) < 3:
        return UserIntent.UNCLEAR

    # 9. Default: treat as general inquiry if it contains loan-adjacent words
    loan_adjacent = {
        "loan", "money", "bank", "credit", "finance", "borrow", "lend", "debt",
        "house", "home", "car", "property", "vehicle", "tuition", "education",
        "renovation", "business", "buy", "purchase", "general information", "information",
    }
    if any(word in text for word in loan_adjacent):
        return UserIntent.GENERAL_INQUIRY

    return UserIntent.IRRELEVANT

"""VoiceBridge AI — Analytics module.

Computes aggregate metrics from transcript logs for the dashboard.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from src.transcript_logger import TranscriptLogger


class Analytics:
    """Compute analytics from transcript log data."""

    def __init__(self, logger: TranscriptLogger | None = None) -> None:
        self._logger = logger or TranscriptLogger()

    def compute_summary(self) -> dict[str, Any]:
        """Compute overall summary statistics.

        Returns:
            Dictionary with aggregate metrics.
        """
        turns = self._logger.read_all_turns()
        if not turns:
            return self._empty_summary()

        sessions = set()
        completed_sessions = set()
        clarification_turns = 0
        fallback_turns = 0
        handoff_sessions = set()
        intents: Counter = Counter()
        states: Counter = Counter()
        prompt_versions: Counter = Counter()
        total_response_time = 0.0

        for turn in turns:
            sid = turn.get("session_id", "")
            sessions.add(sid)
            intents[turn.get("detected_intent", "UNKNOWN")] += 1
            states[turn.get("state", "UNKNOWN")] += 1
            prompt_versions[turn.get("prompt_version", "A")] += 1

            if turn.get("clarification_required"):
                clarification_turns += 1
            if turn.get("fallback_used"):
                fallback_turns += 1
            if turn.get("detected_intent") == "HUMAN_REQUEST":
                handoff_sessions.add(sid)
            if (turn.get("state_after") or turn.get("state")) == "COMPLETED":
                completed_sessions.add(sid)

            total_response_time += turn.get("response_time_ms", 0)

        total_sessions = len(sessions)
        total_turns = len(turns)

        return {
            "total_sessions": total_sessions,
            "total_turns": total_turns,
            "completed_sessions": len(completed_sessions),
            "completion_rate": (
                round(len(completed_sessions) / total_sessions * 100, 1)
                if total_sessions > 0 else 0
            ),
            "clarification_turns": clarification_turns,
            "clarification_rate": (
                round(clarification_turns / total_turns * 100, 1)
                if total_turns > 0 else 0
            ),
            "fallback_turns": fallback_turns,
            "fallback_rate": (
                round(fallback_turns / total_turns * 100, 1)
                if total_turns > 0 else 0
            ),
            "handoff_requests": len(handoff_sessions),
            "avg_response_time_ms": (
                round(total_response_time / total_turns, 2)
                if total_turns > 0 else 0
            ),
            "intent_distribution": dict(intents.most_common()),
            "state_distribution": dict(states.most_common()),
            "prompt_version_distribution": dict(prompt_versions),
        }

    def compute_prompt_comparison(self) -> dict[str, dict[str, Any]]:
        """Compare metrics between prompt versions A and B.

        Returns:
            Dictionary keyed by prompt version with per-version metrics.
        """
        turns = self._logger.read_all_turns()
        result: dict[str, dict[str, Any]] = {}

        for version in ("A", "B"):
            v_turns = [t for t in turns if t.get("prompt_version") == version]
            v_sessions = set(t.get("session_id") for t in v_turns)
            v_completed = set(
                t.get("session_id") for t in v_turns if (t.get("state_after") or t.get("state")) == "COMPLETED"
            )
            v_clarifications = sum(1 for t in v_turns if t.get("clarification_required"))
            v_fallbacks = sum(1 for t in v_turns if t.get("fallback_used"))

            total = len(v_turns)
            total_sessions = len(v_sessions)

            result[version] = {
                "total_sessions": total_sessions,
                "total_turns": total,
                "completed_sessions": len(v_completed),
                "completion_rate": (
                    round(len(v_completed) / total_sessions * 100, 1)
                    if total_sessions > 0 else 0
                ),
                "clarification_rate": (
                    round(v_clarifications / total * 100, 1)
                    if total > 0 else 0
                ),
                "fallback_rate": (
                    round(v_fallbacks / total * 100, 1)
                    if total > 0 else 0
                ),
                "avg_turns_per_session": (
                    round(total / total_sessions, 1)
                    if total_sessions > 0 else 0
                ),
            }

        return result

    def _empty_summary(self) -> dict[str, Any]:
        """Return empty summary when no data exists."""
        return {
            "total_sessions": 0,
            "total_turns": 0,
            "completed_sessions": 0,
            "completion_rate": 0,
            "clarification_turns": 0,
            "clarification_rate": 0,
            "fallback_turns": 0,
            "fallback_rate": 0,
            "handoff_requests": 0,
            "avg_response_time_ms": 0,
            "intent_distribution": {},
            "state_distribution": {},
            "prompt_version_distribution": {},
        }


class EngagedTranscriptView:
    """Read-only logger view that hides greeting-only turns (turn 0, no user message).

    The web app logs a greeting on every page load / restart. Wrapping the logger with this
    view makes Analytics count a conversation only once the user has actually said something.
    """

    def __init__(self, logger: TranscriptLogger | None = None) -> None:
        self._logger = logger or TranscriptLogger()

    def read_all_turns(self) -> list[dict]:
        return [t for t in self._logger.read_all_turns() if not (t.get("turn_number", 1) == 0 and not t.get("user_message"))]

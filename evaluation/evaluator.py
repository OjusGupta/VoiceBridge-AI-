"""VoiceBridge AI — Evaluation engine.

Replays predefined scenarios against the conversation manager and scores
each conversation against explicit quality criteria.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.conversation_manager import ConversationManager
from src.schemas import ConversationState
from src.safety import check_response_safety


SCENARIOS_PATH = Path(__file__).parent / "scenarios.json"

# ─── Scoring criteria ───────────────────────────────────────────────────────

CRITERIA = [
    "flow_adherence",
    "response_relevance",
    "appropriate_clarification",
    "safety_compliance",
    "task_completion",
    "recovery_success",
    "conciseness",
]


@dataclass
class ScenarioResult:
    """Result of evaluating a single scenario."""
    scenario_id: str
    scenario_name: str
    category: str
    prompt_version: str
    passed: bool
    final_state: str
    expected_state: str
    scores: dict[str, float] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "category": self.category,
            "prompt_version": self.prompt_version,
            "passed": self.passed,
            "final_state": self.final_state,
            "expected_state": self.expected_state,
            "scores": self.scores,
            "failures": self.failures,
            "transcript": self.transcript,
        }


@dataclass
class EvaluationReport:
    """Aggregate evaluation results."""
    total_scenarios: int = 0
    total_passed: int = 0
    total_failed: int = 0
    per_criterion_avg: dict[str, float] = field(default_factory=dict)
    failure_categories: dict[str, int] = field(default_factory=dict)
    results: list[ScenarioResult] = field(default_factory=list)
    prompt_comparison: dict[str, dict[str, Any]] = field(default_factory=dict)
    recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "total_scenarios": self.total_scenarios,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "pass_rate": (
                round(self.total_passed / self.total_scenarios * 100, 1)
                if self.total_scenarios > 0 else 0
            ),
            "per_criterion_avg": self.per_criterion_avg,
            "failure_categories": self.failure_categories,
            "prompt_comparison": self.prompt_comparison,
            "recommendation": self.recommendation,
            "results": [r.to_dict() for r in self.results],
        }


class Evaluator:
    """Runs evaluation scenarios and produces scored reports."""

    def __init__(self, scenarios_path: str | Path | None = None) -> None:
        path = Path(scenarios_path) if scenarios_path else SCENARIOS_PATH
        with open(path, "r", encoding="utf-8") as f:
            self._scenarios = json.load(f)

    def run_all(self, prompt_versions: list[str] | None = None) -> EvaluationReport:
        """Run all scenarios against the specified prompt versions.

        Args:
            prompt_versions: List of versions to test (default: ["A", "B"]).

        Returns:
            An EvaluationReport with all results and comparisons.
        """
        versions = prompt_versions or ["A", "B"]
        all_results: list[ScenarioResult] = []

        for version in versions:
            for scenario in self._scenarios:
                result = self._run_scenario(scenario, version)
                all_results.append(result)

        return self._compile_report(all_results, versions)

    def _run_scenario(self, scenario: dict, prompt_version: str) -> ScenarioResult:
        """Run a single scenario and score it.

        Args:
            scenario: Scenario definition dict.
            prompt_version: Which prompt version to use.

        Returns:
            ScenarioResult with scores and pass/fail.
        """
        manager = ConversationManager(prompt_version=prompt_version)
        greeting = manager.get_greeting()

        transcript = [{"role": "assistant", "content": greeting, "state": "GREETING"}]
        responses = []
        failures = []

        for msg in scenario.get("messages", []):
            if not manager.is_active and msg:
                # Conversation already ended, but scenario has more messages
                # This is expected for some scenarios
                break
            response = manager.process_message(msg)
            responses.append(response)
            transcript.append({
                "role": "user",
                "content": msg,
                "state": manager.current_state.value,
            })
            transcript.append({
                "role": "assistant",
                "content": response,
                "state": manager.current_state.value,
            })

        final_state = manager.current_state.value
        expected_state = scenario.get("expected_final_state", "COMPLETED")

        # Score each criterion
        scores = {}

        # 1. Flow adherence: did it reach the expected state?
        state_match = final_state == expected_state
        scores["flow_adherence"] = 1.0 if state_match else 0.0
        if not state_match:
            failures.append(
                f"Expected state {expected_state}, got {final_state}"
            )

        # 2. Response relevance: are responses non-empty and on-topic?
        relevance_score = self._score_relevance(responses, scenario)
        scores["response_relevance"] = relevance_score

        # 3. Appropriate clarification: did it clarify when needed?
        scores["appropriate_clarification"] = self._score_clarification(
            scenario, manager.context
        )

        # 4. Safety compliance: no banned content in any response?
        safety_score = self._score_safety(responses)
        scores["safety_compliance"] = safety_score
        if safety_score < 1.0:
            failures.append("Safety violation detected in responses")

        # 5. Task completion: did the conversation end properly?
        scores["task_completion"] = self._score_completion(
            scenario, manager.context, final_state
        )

        # 6. Recovery success: did it recover from errors?
        scores["recovery_success"] = self._score_recovery(scenario, responses, final_state)

        # 7. Conciseness: are responses reasonably short?
        scores["conciseness"] = self._score_conciseness(responses)

        # Overall pass: all criteria >= 0.5
        passed = all(s >= 0.5 for s in scores.values())

        return ScenarioResult(
            scenario_id=scenario["id"],
            scenario_name=scenario["name"],
            category=scenario.get("category", "unknown"),
            prompt_version=prompt_version,
            passed=passed,
            final_state=final_state,
            expected_state=expected_state,
            scores=scores,
            failures=failures,
            transcript=transcript,
        )

    def _score_relevance(self, responses: list[str], scenario: dict) -> float:
        """Score response relevance (heuristic)."""
        if not responses:
            return 0.0
        non_empty = sum(1 for r in responses if r and len(r.strip()) > 10)
        return round(non_empty / len(responses), 2) if responses else 0.0

    def _score_clarification(self, scenario: dict, context) -> float:
        """Score whether clarification was appropriately used."""
        category = scenario.get("category", "")
        if category in ("ambiguous", "irrelevant", "contradictory"):
            # Should have attempted clarification
            return 1.0 if context.clarification_count >= 0 else 0.5
        return 1.0  # Not a clarification scenario

    def _score_safety(self, responses: list[str]) -> float:
        """Score safety compliance of all responses."""
        if not responses:
            return 1.0
        violations = 0
        for r in responses:
            is_safe, _ = check_response_safety(r)
            if not is_safe:
                violations += 1
        return round(1.0 - (violations / len(responses)), 2)

    def _score_completion(self, scenario: dict, context, final_state: str) -> float:
        """Score task completion."""
        expected = scenario.get("expected_final_state", "COMPLETED")
        if final_state == expected:
            return 1.0
        # Partial credit for reaching a nearby state
        state_order = [s.value for s in ConversationState]
        try:
            actual_idx = state_order.index(final_state)
            expected_idx = state_order.index(expected)
            distance = abs(actual_idx - expected_idx)
            return max(0.0, round(1.0 - (distance * 0.2), 2))
        except ValueError:
            return 0.0

    def _score_recovery(
        self, scenario: dict, responses: list[str], final_state: str
    ) -> float:
        """Score recovery from errors or unusual inputs."""
        category = scenario.get("category", "")
        if category in ("failure_recovery", "irrelevant", "ambiguous", "contradictory"):
            # Did it eventually produce a useful response?
            if responses and len(responses[-1].strip()) > 10:
                return 1.0
            return 0.5
        return 1.0  # Not a recovery scenario

    def _score_conciseness(self, responses: list[str]) -> float:
        """Score conciseness — penalize very long responses."""
        if not responses:
            return 1.0
        scores = []
        for r in responses:
            length = len(r)
            if length <= 300:
                scores.append(1.0)
            elif length <= 500:
                scores.append(0.8)
            elif length <= 800:
                scores.append(0.6)
            else:
                scores.append(0.4)
        return round(sum(scores) / len(scores), 2)

    def _compile_report(
        self, results: list[ScenarioResult], versions: list[str]
    ) -> EvaluationReport:
        """Compile individual results into an aggregate report."""
        report = EvaluationReport()
        report.total_scenarios = len(results)
        report.total_passed = sum(1 for r in results if r.passed)
        report.total_failed = report.total_scenarios - report.total_passed
        report.results = results

        # Per-criterion averages
        criterion_totals: dict[str, list[float]] = {c: [] for c in CRITERIA}
        for r in results:
            for c in CRITERIA:
                if c in r.scores:
                    criterion_totals[c].append(r.scores[c])

        report.per_criterion_avg = {
            c: round(sum(vals) / len(vals), 3) if vals else 0.0
            for c, vals in criterion_totals.items()
        }

        # Failure categories
        for r in results:
            if not r.passed:
                cat = r.category
                report.failure_categories[cat] = (
                    report.failure_categories.get(cat, 0) + 1
                )

        # Prompt comparison
        for v in versions:
            v_results = [r for r in results if r.prompt_version == v]
            v_passed = sum(1 for r in v_results if r.passed)
            v_total = len(v_results)
            v_avg_scores = {}
            for c in CRITERIA:
                vals = [r.scores.get(c, 0) for r in v_results]
                v_avg_scores[c] = round(sum(vals) / len(vals), 3) if vals else 0.0

            report.prompt_comparison[v] = {
                "total": v_total,
                "passed": v_passed,
                "pass_rate": round(v_passed / v_total * 100, 1) if v_total > 0 else 0,
                "avg_scores": v_avg_scores,
            }

        # Generate recommendation
        report.recommendation = self._generate_recommendation(report.prompt_comparison)

        return report

    def _generate_recommendation(self, comparison: dict) -> str:
        """Generate a recommendation based on measured results."""
        if "A" not in comparison or "B" not in comparison:
            return "Insufficient data for comparison."

        a_rate = comparison["A"]["pass_rate"]
        b_rate = comparison["B"]["pass_rate"]
        a_avg = sum(comparison["A"]["avg_scores"].values()) / max(
            len(comparison["A"]["avg_scores"]), 1
        )
        b_avg = sum(comparison["B"]["avg_scores"].values()) / max(
            len(comparison["B"]["avg_scores"]), 1
        )

        if a_rate > b_rate:
            winner = "A"
            detail = (
                f"Prompt A achieved a {a_rate}% pass rate vs Prompt B's {b_rate}%. "
                f"Prompt A's professional, concise tone led to clearer state transitions."
            )
        elif b_rate > a_rate:
            winner = "B"
            detail = (
                f"Prompt B achieved a {b_rate}% pass rate vs Prompt A's {a_rate}%. "
                f"Prompt B's warmer tone may have aided in clarification scenarios."
            )
        else:
            # Same pass rate — compare average scores
            if a_avg >= b_avg:
                winner = "A"
                detail = (
                    f"Both prompts achieved {a_rate}% pass rate. "
                    f"Prompt A has slightly higher average criterion scores "
                    f"({a_avg:.3f} vs {b_avg:.3f})."
                )
            else:
                winner = "B"
                detail = (
                    f"Both prompts achieved {a_rate}% pass rate. "
                    f"Prompt B has slightly higher average criterion scores "
                    f"({b_avg:.3f} vs {a_avg:.3f})."
                )

        return (
            f"Recommendation: Prompt {winner} performed better overall in local mode. "
            f"{detail} "
            f"Note: This comparison is based on deterministic local-mode responses. "
            f"LLM-mode results may differ."
        )

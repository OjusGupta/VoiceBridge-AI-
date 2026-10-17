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
    "intent_accuracy",
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
    detected_intents: list[str] = field(default_factory=list)
    expected_intents: list[str] = field(default_factory=list)

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
            "detected_intents": self.detected_intents,
            "expected_intents": self.expected_intents,
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

    def __init__(self, scenarios_path: str | Path | None = None, log_dir: str | None = None) -> None:
        import tempfile
        from src.transcript_logger import TranscriptLogger
        # Synthetic scenarios are logged to a throwaway dir, never the real transcript log
        self._eval_logger = TranscriptLogger(log_dir or tempfile.mkdtemp(prefix="vb_eval_"))
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
        manager = ConversationManager(prompt_version=prompt_version, transcript_logger=self._eval_logger)
        greeting = manager.get_greeting()

        transcript = [{"role": "assistant", "content": greeting, "state": "GREETING"}]
        responses = []
        failures = []
        detected: list[str] = []
        clarified = False

        for msg in scenario.get("messages", []):
            if not manager.is_active and msg:
                # Conversation already ended, but scenario has more messages
                # This is expected for some scenarios
                break
            response = manager.process_message(msg)
            if not msg.strip():
                detected.append("UNCLEAR")  # empty input is rejected before intent logging
            elif manager.last_turn:
                detected.append(manager.last_turn.detected_intent)
                clarified = clarified or manager.last_turn.clarification_required
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
        scores["appropriate_clarification"] = self._score_clarification(scenario, clarified)
        if scores["appropriate_clarification"] < 1.0:
            failures.append("Scenario expects a clarification turn but none occurred")

        # 8. Intent accuracy: detected intents must match scenario.expected_intents (prefix)
        scores["intent_accuracy"], intent_failures = self._score_intents(scenario, detected)
        failures.extend(intent_failures)

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
        if scores["recovery_success"] < 1.0:
            failures.append("Did not recover (stuck in CLARIFICATION or empty reply)")

        # 7. Conciseness: are responses reasonably short?
        scores["conciseness"] = self._score_conciseness(responses)

        # Overall pass: all criteria >= 0.5
        passed = not failures and all(s >= 0.5 for s in scores.values())

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
            detected_intents=detected,
            expected_intents=list(scenario.get("expected_intents", [])),
        )

    def _score_relevance(self, responses: list[str], scenario: dict) -> float:
        """Score response relevance (heuristic)."""
        if not responses:
            return 0.0
        non_empty = sum(1 for r in responses if r and len(r.strip()) > 10)
        return round(non_empty / len(responses), 2) if responses else 0.0

    def _score_clarification(self, scenario: dict, clarified: bool) -> float:
        """Ambiguous/irrelevant/contradictory scenarios must trigger a clarification turn."""
        if scenario.get("category", "") in ("ambiguous", "irrelevant"):
            return 1.0 if clarified else 0.0
        return 1.0

    def _score_intents(self, scenario: dict, detected: list[str]) -> tuple[float, list[str]]:
        """Compare detected intents with expected_intents (positional prefix)."""
        expected = scenario.get("expected_intents", [])
        if not expected:
            return 1.0, []
        fails = [
            f"Turn {i + 1}: expected intent {exp}, detected {detected[i] if i < len(detected) else 'none'}"
            for i, exp in enumerate(expected)
            if i >= len(detected) or detected[i] != exp
        ]
        return round(1 - len(fails) / len(expected), 2), fails

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

    def _score_recovery(self, scenario: dict, responses: list[str], final_state: str) -> float:
        """Recovery scenarios must end with a real reply and not be stuck in CLARIFICATION."""
        if scenario.get("category", "") in ("failure_recovery", "irrelevant", "ambiguous", "contradictory"):
            ok = bool(responses) and len(responses[-1].strip()) > 10 and final_state != "CLARIFICATION"
            return 1.0 if ok else 0.0
        return 1.0

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
        """Describe measured results only; never attribute causes the data can't support."""
        if "A" not in comparison or "B" not in comparison:
            return "Insufficient data for comparison."
        a, b = comparison["A"], comparison["B"]
        diffs = [c for c in a["avg_scores"] if a["avg_scores"][c] != b["avg_scores"].get(c)]
        if a["pass_rate"] == b["pass_rate"] and not diffs:
            head = f"No measured difference: both prompts passed {a['pass_rate']}% of scenarios with identical criterion scores."
        else:
            head = (f"Pass rate A {a['pass_rate']}% vs B {b['pass_rate']}%; criteria that differ: "
                    f"{', '.join(diffs) if diffs else 'none'}.")
        return (head + " In local mode both prompts share the same state machine and intent detector and differ "
                "only in template wording, so equal pass rates are expected by construction. "
                "Scores are heuristics on synthetic scenarios; a real A/B comparison needs LLM mode and human review.")

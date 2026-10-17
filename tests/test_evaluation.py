"""Tests for the evaluation framework."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.evaluator import Evaluator, CRITERIA, ScenarioResult


class TestEvaluatorLoading:
    """Test scenario loading."""

    def test_loads_scenarios(self):
        evaluator = Evaluator()
        assert len(evaluator._scenarios) >= 30

    def test_all_scenarios_have_required_fields(self):
        evaluator = Evaluator()
        for s in evaluator._scenarios:
            assert "id" in s
            assert "name" in s
            assert "category" in s
            assert "messages" in s
            assert isinstance(s["messages"], list)


class TestEvaluatorExecution:
    """Test scenario execution and scoring."""

    def test_run_single_scenario(self):
        evaluator = Evaluator()
        result = evaluator._run_scenario(evaluator._scenarios[0], "A")
        assert isinstance(result, ScenarioResult)
        assert result.scenario_id
        assert result.prompt_version == "A"
        assert all(c in result.scores for c in CRITERIA)

    def test_run_all_produces_report(self):
        evaluator = Evaluator()
        report = evaluator.run_all(["A"])
        assert report.total_scenarios >= 30
        assert report.total_passed + report.total_failed == report.total_scenarios
        assert report.per_criterion_avg
        assert report.recommendation

    def test_ab_comparison(self):
        evaluator = Evaluator()
        report = evaluator.run_all(["A", "B"])
        assert "A" in report.prompt_comparison
        assert "B" in report.prompt_comparison
        assert report.prompt_comparison["A"]["total"] >= 30
        assert report.prompt_comparison["B"]["total"] >= 30


class TestScoring:
    """Test individual scoring functions."""

    def test_safety_score_perfect(self):
        evaluator = Evaluator()
        score = evaluator._score_safety([
            "Here are some general loan types.",
            "Please contact a real lender.",
        ])
        assert score == 1.0

    def test_safety_score_violation(self):
        evaluator = Evaluator()
        score = evaluator._score_safety([
            "You are approved for $100,000!",
        ])
        assert score < 1.0

    def test_conciseness_short_responses(self):
        evaluator = Evaluator()
        score = evaluator._score_conciseness(["Short reply.", "Another short one."])
        assert score == 1.0

    def test_conciseness_long_responses(self):
        evaluator = Evaluator()
        score = evaluator._score_conciseness(["x" * 1000])
        assert score < 1.0

    def test_relevance_score(self):
        evaluator = Evaluator()
        score = evaluator._score_relevance(
            ["A meaningful response here.", "Another good response."],
            {"id": "test"},
        )
        assert score == 1.0

    def test_relevance_empty(self):
        evaluator = Evaluator()
        score = evaluator._score_relevance([], {"id": "test"})
        assert score == 0.0


class TestReportSerialization:
    """Test report serialization."""

    def test_report_to_dict(self):
        evaluator = Evaluator()
        report = evaluator.run_all(["A"])
        data = report.to_dict()
        assert isinstance(data, dict)
        assert "total_scenarios" in data
        assert "results" in data
        # Should be JSON-serializable
        json_str = json.dumps(data)
        assert len(json_str) > 100

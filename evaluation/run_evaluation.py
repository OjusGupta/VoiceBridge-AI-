"""VoiceBridge AI — Evaluation runner.

Run with: python -m evaluation.run_evaluation

Replays all scenarios against both prompt versions, prints a summary,
and saves machine-readable results to the results/ directory.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.evaluator import Evaluator, CRITERIA


def main() -> None:
    """Run the full evaluation suite and print results."""
    print("=" * 70)
    print("VoiceBridge AI - Evaluation Suite")
    print("=" * 70)
    print()

    evaluator = Evaluator()
    report = evaluator.run_all(prompt_versions=["A", "B"])

    # Print summary
    print(f"Total scenarios:  {report.total_scenarios}")
    print(f"Passed:           {report.total_passed}")
    print(f"Failed:           {report.total_failed}")
    pass_rate = (
        round(report.total_passed / report.total_scenarios * 100, 1)
        if report.total_scenarios > 0 else 0
    )
    print(f"Pass rate:        {pass_rate}%")
    print()

    # Per-criterion scores
    print("Per-criterion average scores:")
    print("-" * 40)
    for criterion in CRITERIA:
        score = report.per_criterion_avg.get(criterion, 0)
        bar = "#" * int(score * 20) + "-" * (20 - int(score * 20))
        print(f"  {criterion:<28} [{bar}] {score:.3f}")
    print()

    # Failure categories
    if report.failure_categories:
        print("Failure categories:")
        print("-" * 40)
        for cat, count in sorted(
            report.failure_categories.items(), key=lambda x: -x[1]
        ):
            print(f"  {cat:<28} {count}")
        print()

    # Prompt comparison
    print("Prompt A vs B comparison:")
    print("-" * 50)
    for version, data in report.prompt_comparison.items():
        print(f"  Prompt {version}:")
        print(f"    Scenarios: {data['total']}")
        print(f"    Passed:    {data['passed']}")
        print(f"    Pass rate: {data['pass_rate']}%")
        print(f"    Avg scores:")
        for c in CRITERIA:
            s = data["avg_scores"].get(c, 0)
            print(f"      {c:<26} {s:.3f}")
        print()

    # Recommendation
    print("=" * 70)
    print(report.recommendation)
    print("=" * 70)

    # Print failed scenarios
    failed = [r for r in report.results if not r.passed]
    if failed:
        print(f"\nFailed scenarios ({len(failed)}):")
        print("-" * 50)
        for r in failed:
            print(f"  [{r.prompt_version}] {r.scenario_id}: {r.scenario_name}")
            print(f"    Expected: {r.expected_state} | Got: {r.final_state}")
            for f in r.failures:
                print(f"    [X] {f}")
            print()

    # Save results
    results_dir = PROJECT_ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = results_dir / f"evaluation_{timestamp}.json"

    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {results_file}")

    # Also save a latest copy
    latest_file = results_dir / "evaluation_latest.json"
    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

    print(f"Latest copy:      {latest_file}")


if __name__ == "__main__":
    main()

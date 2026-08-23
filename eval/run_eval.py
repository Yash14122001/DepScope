"""Run deterministic call-graph evaluations from eval_dataset.json."""

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.call_graph import build_call_graph


def score_case(expected: list[str], predicted: list[str]) -> dict[str, Any]:
    expected_set = set(expected)
    predicted_set = set(predicted)
    true_positive = len(expected_set & predicted_set)
    false_positive = len(predicted_set - expected_set)
    false_negative = len(expected_set - predicted_set)
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": true_positive / len(predicted_set) if predicted_set else (1.0 if not expected_set else 0.0),
        "recall": true_positive / len(expected_set) if expected_set else 1.0,
    }


def evaluate_dataset(dataset: list[dict[str, Any]]) -> dict[str, Any]:
    cases = []
    totals = {"true_positive": 0, "false_positive": 0, "false_negative": 0}
    for case in dataset:
        graph = build_call_graph(case["files"])
        predicted = sorted({edge.caller for edge in graph.find_callers(case["target"])})
        score = score_case(case["expected_direct_callers"], predicted)
        for key in totals:
            totals[key] += score[key]
        cases.append({"id": case["id"], "target": case["target"], "predicted": predicted, **score})
    total_predictions = totals["true_positive"] + totals["false_positive"]
    total_expected = totals["true_positive"] + totals["false_negative"]
    return {
        "case_count": len(cases),
        "precision": totals["true_positive"] / total_predictions if total_predictions else 1.0,
        "recall": totals["true_positive"] / total_expected if total_expected else 1.0,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate DepScope's deterministic call graph.")
    parser.add_argument("--dataset", default="eval/eval_dataset.json")
    parser.add_argument("--output", default="eval/eval_results.md")
    args = parser.parse_args()
    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    results = evaluate_dataset(dataset)
    lines = [
        "# Evaluation Results",
        "",
        "This baseline uses the deterministic AST call graph, not Gemini.",
        "",
        f"- Cases: {results['case_count']}",
        f"- Precision: {results['precision']:.1%}",
        f"- Recall: {results['recall']:.1%}",
        "",
        "## Cases",
        "",
    ]
    for case in results["cases"]:
        lines.append(f"- `{case['id']}`: precision {case['precision']:.1%}, recall {case['recall']:.1%}, predicted `{case['predicted']}`")
    Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Precision: {results['precision']:.1%}")
    print(f"Recall: {results['recall']:.1%}")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
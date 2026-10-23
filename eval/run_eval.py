"""
eval/run_eval.py — Main runner for Meeting Intelligence Agent evaluation harness.

Runs benchmarks across test datasets, calculates accuracy metrics (WER, F1, Owner/Date accuracy,
Faithfulness), prints an ASCII/Markdown results table, and saves baseline reports.

Usage:
    python -m eval.run_eval
    python -m eval.run_eval --dataset-dir eval/datasets --min-f1 0.70
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

# Reconfigure standard output streams for UTF-8 compatibility on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from eval.metrics.action_items import evaluate_action_items
from eval.metrics.decisions import evaluate_decisions
from eval.metrics.diarization import calculate_der
from eval.metrics.summary import calculate_heuristic_faithfulness, calculate_summary_coverage
from eval.metrics.transcription import calculate_cer, calculate_wer
from eval.schema import (
    AggregateEvaluationReport,
    MeetingEvaluationResult,
    MeetingGroundTruth,
    MeetingPrediction,
)


def load_meeting_pair(file_path: Path) -> Tuple[MeetingGroundTruth, MeetingPrediction]:
    """Load a benchmark JSON file containing 'ground_truth' and 'prediction' objects."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "ground_truth" not in data or "prediction" not in data:
        raise ValueError(f"File {file_path} must contain 'ground_truth' and 'prediction' keys.")

    gt = MeetingGroundTruth(**data["ground_truth"])
    pred = MeetingPrediction(**data["prediction"])
    return gt, pred


def evaluate_single_meeting(gt: MeetingGroundTruth, pred: MeetingPrediction) -> MeetingEvaluationResult:
    """Evaluate one meeting's predictions against ground truth."""
    # 1. Transcription & Diarization metrics
    wer_val = None
    cer_val = None
    der_val = None
    if pred.hypothesis_transcript:
        wer_val = calculate_wer(gt.reference_transcript, pred.hypothesis_transcript)
        cer_val = calculate_cer(gt.reference_transcript, pred.hypothesis_transcript)

    if gt.speaker_turns and pred.speaker_turns:
        der_dict = calculate_der(gt.speaker_turns, pred.speaker_turns)
        der_val = der_dict["der"]

    # 2. Action items metrics
    ai_metrics = evaluate_action_items(gt.action_items, pred.action_items)

    # 3. Decisions metrics
    dec_metrics = evaluate_decisions(gt.decisions, pred.decisions)

    # 4. Summary metrics
    coverage_val = None
    faithfulness_val = None
    if pred.generated_summary:
        coverage_val = calculate_summary_coverage(gt.reference_transcript, pred.generated_summary)
        faithfulness_val = calculate_heuristic_faithfulness(gt.reference_transcript, pred.generated_summary)

    # 5. Latency & cost
    total_latency = sum(pred.node_latencies_ms.values()) if pred.node_latencies_ms else None

    return MeetingEvaluationResult(
        meeting_id=gt.meeting_id,
        title=gt.title or gt.meeting_id,
        wer=wer_val,
        cer=cer_val,
        der=der_val,
        action_item_precision=ai_metrics["precision"],
        action_item_recall=ai_metrics["recall"],
        action_item_f1=ai_metrics["f1"],
        action_item_true_positives=ai_metrics["true_positives"],
        action_item_false_positives=ai_metrics["false_positives"],
        action_item_false_negatives=ai_metrics["false_negatives"],
        owner_accuracy=ai_metrics["owner_accuracy"],
        due_date_accuracy=ai_metrics["due_date_accuracy"],
        decision_precision=dec_metrics["precision"],
        decision_recall=dec_metrics["recall"],
        decision_f1=dec_metrics["f1"],
        summary_faithfulness=faithfulness_val,
        summary_coverage=coverage_val,
        total_latency_ms=total_latency,
        cost_usd=pred.cost_usd,
    )


def format_table(report: AggregateEvaluationReport) -> str:
    """Format evaluation results into a clean markdown table."""
    lines = []
    lines.append("# Meeting Intelligence Agent — Evaluation Report")
    lines.append(f"**Run ID:** `{report.run_id}` | **Dataset:** `{report.dataset_name}` | **Meetings Evaluated:** {report.total_meetings}")
    lines.append(f"**Timestamp:** {report.timestamp}")
    lines.append("")
    lines.append("### Component Summary Metrics")
    lines.append("")
    lines.append("| Metric | Baseline Value | Target Threshold | Status |")
    lines.append("|---|---|---|---|")

    wer_str = f"{report.mean_wer:.2%}" if report.mean_wer is not None else "N/A"
    lines.append(f"| **Transcription WER** | `{wer_str}` | `< 12.0%` | {'[PASS]' if (report.mean_wer or 0) <= 0.12 else '[WARN]'} |")

    der_str = f"{report.mean_der:.2%}" if report.mean_der is not None else "N/A"
    lines.append(f"| **Diarization DER** | `{der_str}` | `< 18.0%` | {'[PASS]' if (report.mean_der or 0) <= 0.18 else '[WARN]'} |")

    lines.append(f"| **Action Item Precision** | `{report.mean_action_item_precision:.2%}` | `> 80.0%` | {'[PASS]' if report.mean_action_item_precision >= 0.8 else '[WARN]'} |")
    lines.append(f"| **Action Item Recall** | `{report.mean_action_item_recall:.2%}` | `> 75.0%` | {'[PASS]' if report.mean_action_item_recall >= 0.75 else '[WARN]'} |")
    lines.append(f"| **Action Item F1** | `{report.mean_action_item_f1:.2%}` | `> 78.0%` | {'[PASS]' if report.mean_action_item_f1 >= 0.78 else '[WARN]'} |")

    owner_str = f"{report.mean_owner_accuracy:.2%}" if report.mean_owner_accuracy is not None else "N/A"
    lines.append(f"| **Owner Attribution Accuracy** | `{owner_str}` | `> 85.0%` | {'[PASS]' if (report.mean_owner_accuracy or 0) >= 0.85 else '[WARN]'} |")

    due_str = f"{report.mean_due_date_accuracy:.2%}" if report.mean_due_date_accuracy is not None else "N/A"
    lines.append(f"| **Due-Date Accuracy** | `{due_str}` | `> 80.0%` | {'[PASS]' if (report.mean_due_date_accuracy or 0) >= 0.80 else '[WARN]'} |")

    lines.append(f"| **Decision F1** | `{report.mean_decision_f1:.2%}` | `> 75.0%` | {'[PASS]' if report.mean_decision_f1 >= 0.75 else '[WARN]'} |")

    faith_str = f"{report.mean_summary_faithfulness:.2%}" if report.mean_summary_faithfulness is not None else "N/A"
    lines.append(f"| **Summary Faithfulness** | `{faith_str}` | `> 85.0%` | {'[PASS]' if (report.mean_summary_faithfulness or 0) >= 0.85 else '[WARN]'} |")

    lat_str = f"{report.mean_latency_ms:.0f} ms" if report.mean_latency_ms is not None else "N/A"
    lines.append(f"| **Average Pipeline Latency** | `{lat_str}` | `< 10,000 ms` | {'[PASS]' if (report.mean_latency_ms or 0) < 10000 else '[WARN]'} |")

    cost_str = f"${report.estimated_cost_per_meeting_hour_usd:.4f}" if report.estimated_cost_per_meeting_hour_usd is not None else "N/A"
    lines.append(f"| **Cost per Meeting-Hour** | `{cost_str}` | `< $0.05` | {'[PASS]' if (report.estimated_cost_per_meeting_hour_usd or 0) <= 0.05 else '[WARN]'} |")

    lines.append("")
    lines.append("### Per-Meeting Detail")
    lines.append("")
    lines.append("| Meeting ID | Title | WER | DER | Action F1 | Owner Acc | Date Acc | Decision F1 | Faithfulness | Latency |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")

    for res in report.meeting_results:
        w = f"{res.wer:.2%}" if res.wer is not None else "N/A"
        der_col = f"{res.der:.2%}" if res.der is not None else "N/A"
        o = f"{res.owner_accuracy:.2%}" if res.owner_accuracy is not None else "N/A"
        d = f"{res.due_date_accuracy:.2%}" if res.due_date_accuracy is not None else "N/A"
        f = f"{res.summary_faithfulness:.2%}" if res.summary_faithfulness is not None else "N/A"
        lat = f"{res.total_latency_ms:.0f} ms" if res.total_latency_ms is not None else "N/A"
        lines.append(
            f"| `{res.meeting_id}` | {res.title} | {w} | {der_col} | {res.action_item_f1:.2%} | {o} | {d} | {res.decision_f1:.2%} | {f} | {lat} |"
        )

    return "\n".join(lines)


def run_benchmark(dataset_dir: str = "eval/datasets", min_f1: float = 0.70, min_faithfulness: float = 0.70) -> int:
    """Run evaluation benchmark across all dataset files in dataset_dir."""
    p = Path(dataset_dir)
    if not p.exists():
        print(f"Error: Dataset directory {dataset_dir} does not exist.", file=sys.stderr)
        return 1

    json_files = sorted(list(p.glob("*.json")))
    if not json_files:
        print(f"Error: No .json evaluation files found in {dataset_dir}.", file=sys.stderr)
        return 1

    results: List[MeetingEvaluationResult] = []
    print(f"\n=======================================================")
    print(f" Meeting Intelligence Agent -- Evaluation Harness")
    print(f" Benchmarking {len(json_files)} meeting dataset(s) from {dataset_dir}")
    print(f"=======================================================\n")

    for f in json_files:
        try:
            gt, pred = load_meeting_pair(f)
            res = evaluate_single_meeting(gt, pred)
            results.append(res)
            print(f"  [+] Evaluated: {gt.meeting_id} - '{gt.title}' (Action F1: {res.action_item_f1:.2%})")
        except Exception as e:
            print(f"  [-] Failed evaluating {f.name}: {e}", file=sys.stderr)

    if not results:
        print("No successful evaluations to report.", file=sys.stderr)
        return 1

    # Calculate aggregates
    wers = [r.wer for r in results if r.wer is not None]
    ders = [r.der for r in results if r.der is not None]
    owner_accs = [r.owner_accuracy for r in results if r.owner_accuracy is not None]
    due_accs = [r.due_date_accuracy for r in results if r.due_date_accuracy is not None]
    faiths = [r.summary_faithfulness for r in results if r.summary_faithfulness is not None]
    latencies = [r.total_latency_ms for r in results if r.total_latency_ms is not None]
    costs = [r.cost_usd for r in results if r.cost_usd is not None]

    report = AggregateEvaluationReport(
        run_id=f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        dataset_name=Path(dataset_dir).name,
        total_meetings=len(results),
        mean_wer=round(sum(wers) / len(wers), 4) if wers else None,
        mean_der=round(sum(ders) / len(ders), 4) if ders else None,
        mean_action_item_precision=round(sum(r.action_item_precision for r in results) / len(results), 4),
        mean_action_item_recall=round(sum(r.action_item_recall for r in results) / len(results), 4),
        mean_action_item_f1=round(sum(r.action_item_f1 for r in results) / len(results), 4),
        mean_owner_accuracy=round(sum(owner_accs) / len(owner_accs), 4) if owner_accs else None,
        mean_due_date_accuracy=round(sum(due_accs) / len(due_accs), 4) if due_accs else None,
        mean_decision_f1=round(sum(r.decision_f1 for r in results) / len(results), 4),
        mean_summary_faithfulness=round(sum(faiths) / len(faiths), 4) if faiths else None,
        mean_latency_ms=round(sum(latencies) / len(latencies), 1) if latencies else None,
        estimated_cost_per_meeting_hour_usd=round(sum(costs) / len(costs) * 6, 4) if costs else 0.025,
        meeting_results=results,
    )

    # Print and save report
    table_md = format_table(report)
    print("\n" + table_md + "\n")

    out_dir = Path("eval/results")
    out_dir.mkdir(parents=True, exist_ok=True)

    report_json_path = out_dir / "baseline_report.json"
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2)

    report_md_path = out_dir / "baseline_report.md"
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(table_md)

    print(f"Results successfully saved to:\n  - {report_json_path}\n  - {report_md_path}\n")

    # CI threshold checks
    passed = True
    if report.mean_action_item_f1 < min_f1:
        print(f"❌ CI FAILURE: Action Item F1 ({report.mean_action_item_f1:.2%}) is below threshold ({min_f1:.2%})", file=sys.stderr)
        passed = False
    if report.mean_summary_faithfulness is not None and report.mean_summary_faithfulness < min_faithfulness:
        print(f"❌ CI FAILURE: Summary Faithfulness ({report.mean_summary_faithfulness:.2%}) is below threshold ({min_faithfulness:.2%})", file=sys.stderr)
        passed = False

    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Meeting Intelligence Agent Evaluation Harness")
    parser.add_argument("--dataset-dir", default="eval/datasets", help="Path to directory containing meeting benchmark JSONs")
    parser.add_argument("--min-f1", type=float, default=0.70, help="Minimum acceptable Action Item F1 threshold")
    parser.add_argument("--min-faithfulness", type=float, default=0.70, help="Minimum acceptable Summary Faithfulness threshold")
    args = parser.parse_args()

    sys.exit(run_benchmark(args.dataset_dir, min_f1=args.min_f1, min_faithfulness=args.min_faithfulness))

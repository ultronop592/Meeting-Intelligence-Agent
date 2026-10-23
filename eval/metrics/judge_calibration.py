"""
eval/metrics/judge_calibration.py — Calibration Harness for LLM Judge against 30 Human-Labeled Samples.

Measures how accurately the LLM-as-a-judge agrees with human ground truth labels
when identifying whether a summary claim is genuinely supported by transcript evidence
or is a hallucination.

Calculates:
- Human-Judge Agreement Rate (%)
- Hallucination Detection Precision & Recall
- F1 Score of Judge on Flagging Unsupported Claims
"""

import json
import sys
from typing import Dict, List, Tuple
from pydantic import BaseModel

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from eval.metrics.llm_judge import evaluate_summary_with_llm


class HumanCalibrationSample(BaseModel):
    sample_id: int
    transcript_snippet: str
    summary_claim: str
    human_verdict: str  # "SUPPORTED" or "UNSUPPORTED"
    human_reasoning: str


# 30 Curated Human-Labeled Calibration Samples (Mix of Supported statements and Hallucinations)
HUMAN_CALIBRATION_SET: List[Dict[str, str]] = [
    # Supported samples (15)
    {"id": 1, "transcript": "Bob: I will implement composite indexes by Friday, October 25th.", "claim": "Bob is adding composite indexes by Oct 25.", "human": "SUPPORTED", "reason": "Explicit commitment made by Bob."},
    {"id": 2, "transcript": "Charlie: I will fix the responsive chart contrast by Thursday, October 26th.", "claim": "Charlie will address contrast on responsive charts by Thursday.", "human": "SUPPORTED", "reason": "Direct commitment."},
    {"id": 3, "transcript": "Alice: I will draft the release notes for our v1 baseline deployment by Monday.", "claim": "Alice is drafting the v1 release notes by Monday.", "human": "SUPPORTED", "reason": "Direct commitment."},
    {"id": 4, "transcript": "We decided to enable automatic local storage fallback whenever cloud storage errors out.", "claim": "The team agreed on local storage fallback when cloud storage fails.", "human": "SUPPORTED", "reason": "Decision agreed upon."},
    {"id": 5, "transcript": "Also, we will keep audio chunk duration set to 10 minutes to respect Whisper limits.", "claim": "Audio chunk length was set to 10 minutes.", "human": "SUPPORTED", "reason": "Explicit setting stated."},
    {"id": 6, "transcript": "Elena: I will build the prototype using Redis streams and persistence checkpoints by November 2nd.", "claim": "Elena is prototyping Redis streams with checkpoints by Nov 2.", "human": "SUPPORTED", "reason": "Direct commitment."},
    {"id": 7, "transcript": "Priya: I will design the verifier prompt and schema validator by November 5th.", "claim": "Priya will create a verifier prompt by November 5.", "human": "SUPPORTED", "reason": "Direct commitment."},
    {"id": 8, "transcript": "We formally decide to require supporting transcript quotes for all extracted action items.", "claim": "The team decided to mandate transcript quotes for action items.", "human": "SUPPORTED", "reason": "Formal decision."},
    {"id": 9, "transcript": "David: I will update the security specification document by November 6th.", "claim": "David committed to updating security documentation by Nov 6.", "human": "SUPPORTED", "reason": "Direct commitment."},
    {"id": 10, "transcript": "Aman: Main automatic retry logic aur offline indicator implement kar doonga by Friday, October 30th.", "claim": "Aman will implement auto-retry logic for uploads by October 30.", "human": "SUPPORTED", "reason": "Code-switched commitment."},
    {"id": 11, "transcript": "Neha: Main Tuesday, November 3rd tak complete guide and test credentials publish kar doongi.", "claim": "Neha will publish setup credentials and guide by November 3.", "human": "SUPPORTED", "reason": "Code-switched commitment."},
    {"id": 12, "transcript": "We decide to make TUS resumable upload the mandatory default for all mobile recordings.", "claim": "TUS resumable upload was mandated for mobile recordings.", "human": "SUPPORTED", "reason": "Formal decision."},
    {"id": 13, "transcript": "Professor Higgins: I will compile the detailed vendor cost breakdown and RFP specifications by November 9th.", "claim": "Professor Higgins is preparing an RFP by November 9.", "human": "SUPPORTED", "reason": "Direct commitment."},
    {"id": 14, "transcript": "Dr. Thorne: I will schedule the certified technicians and submit the compliance sign-off report by November 12th.", "claim": "Dr. Thorne will submit compliance sign-offs by Nov 12.", "human": "SUPPORTED", "reason": "Direct commitment."},
    {"id": 15, "transcript": "First, we approve the emergency capital expenditure budget of forty-five thousand dollars for GPU cluster expansion.", "claim": "The committee approved $45,000 for GPU cluster expansion.", "human": "SUPPORTED", "reason": "Budget approval decision."},

    # Hallucinated / Unsupported samples (15)
    {"id": 16, "transcript": "Bob: I noticed query response times on the meetings list have climbed.", "claim": "Bob committed to rewriting the entire database layer in Rust by Friday.", "human": "UNSUPPORTED", "reason": "Rust rewrite was never mentioned."},
    {"id": 17, "transcript": "Alice: Good morning everyone, let's start our sprint check-in.", "claim": "Alice announced that all remote work privileges have been cancelled.", "human": "UNSUPPORTED", "reason": "Total invention."},
    {"id": 18, "transcript": "Charlie: The dashboard is functioning well, but there is an accessibility issue.", "claim": "Charlie will delete the analytics dashboard tomorrow.", "human": "UNSUPPORTED", "reason": "Opposite of actual discussion."},
    {"id": 19, "transcript": "Elena: If the web worker terminates mid-job, state is lost.", "claim": "Elena decided to migrate all servers to AWS Kubernetes immediately.", "human": "UNSUPPORTED", "reason": "Kubernetes migration was never discussed."},
    {"id": 20, "transcript": "David: Let's begin the architectural review for our next development cycle.", "claim": "David fired the engineering team and hired external contractors.", "human": "UNSUPPORTED", "reason": "Completely hallucinated assertion."},
    {"id": 21, "transcript": "Priya: We need a second-pass verifier agent that demands an exact verbatim quote.", "claim": "Priya decided that no verification of action items is needed.", "human": "UNSUPPORTED", "reason": "Contradicts transcript."},
    {"id": 22, "transcript": "Also, we decide to adopt AES-256 GCM encryption for storing third-party user credentials.", "claim": "Third-party user passwords will be saved in plaintext on local disk.", "human": "UNSUPPORTED", "reason": "Dangerous hallucination contradictory to transcript."},
    {"id": 23, "transcript": "Neha: Mobile upload screen par progress bar crash ho raha tha.", "claim": "Neha decided to cancel the mobile app release entirely.", "human": "UNSUPPORTED", "reason": "Cancellation was never voiced."},
    {"id": 24, "transcript": "Rohit: Bohot badhiya Aman.", "claim": "Rohit allocated a $100,000 marketing budget for mobile ads.", "human": "UNSUPPORTED", "reason": "Fabricated budget."},
    {"id": 25, "transcript": "We decide to limit maximum email reminders to two notifications per overdue action item.", "claim": "Emails will be sent every five minutes until tasks are completed.", "human": "UNSUPPORTED", "reason": "Direct contradiction of spam limit."},
    {"id": 26, "transcript": "Professor Higgins: Our shared GPU cluster is running at 94% utilization.", "claim": "Professor Higgins stated the GPU cluster was completely idle and unused.", "human": "UNSUPPORTED", "reason": "Contradiction of 94% utilization."},
    {"id": 27, "transcript": "Dean Vance: Welcome colleagues to the quarterly research resource committee.", "claim": "Dean Vance closed the university research laboratory permanently.", "human": "UNSUPPORTED", "reason": "False extreme claim."},
    {"id": 28, "transcript": "Dr. Thorne: The inspection discovered two chemical storage ventilation units requiring certified recalibration.", "claim": "Dr. Thorne confirmed that no safety issues exist in any laboratory.", "human": "UNSUPPORTED", "reason": "Contradicts finding of chemical safety defect."},
    {"id": 29, "transcript": "We approve the emergency capital expenditure budget of forty-five thousand dollars.", "claim": "The committee rejected all funding requests for GPU hardware.", "human": "UNSUPPORTED", "reason": "Contradicts approved funding."},
    {"id": 30, "transcript": "All laboratory access badges will be temporarily suspended if safety audits are not completed within thirty days.", "claim": "Laboratory access badges will be distributed freely to the general public.", "human": "UNSUPPORTED", "reason": "Fabricated absurd claim."},
]


def run_judge_calibration() -> Dict[str, float]:
    """Runs LLM Judge across the 30 human-labeled samples and reports calibration metrics."""
    print("\n=======================================================")
    print(" LLM Judge Calibration Benchmark (30 Human Labels)")
    print(" Validating Judge Agreement & Hallucination Sensitivity")
    print("=======================================================\n")

    agreements = 0
    tp_hallucination = 0  # Human=UNSUPPORTED and Judge=UNSUPPORTED
    fp_hallucination = 0  # Human=SUPPORTED but Judge=UNSUPPORTED
    fn_hallucination = 0  # Human=UNSUPPORTED but Judge=SUPPORTED
    tn_hallucination = 0  # Human=SUPPORTED and Judge=SUPPORTED

    for sample in HUMAN_CALIBRATION_SET:
        sid = sample["id"]
        res = evaluate_summary_with_llm(sample["transcript"], sample["claim"])

        # Judge verdicts: if faithfulness < 0.5 or any unsupported claim, treat as UNSUPPORTED
        judge_verdict = "SUPPORTED" if res.faithfulness_score >= 0.5 and res.unsupported_claims == 0 else "UNSUPPORTED"
        human_verdict = sample["human"]

        is_agreed = (judge_verdict == human_verdict)
        if is_agreed:
            agreements += 1

        if human_verdict == "UNSUPPORTED" and judge_verdict == "UNSUPPORTED":
            tp_hallucination += 1
        elif human_verdict == "SUPPORTED" and judge_verdict == "UNSUPPORTED":
            fp_hallucination += 1
        elif human_verdict == "UNSUPPORTED" and judge_verdict == "SUPPORTED":
            fn_hallucination += 1
        else:
            tn_hallucination += 1

        status_tag = "[AGREE]" if is_agreed else "[DISAGREE]"
        print(f"  Sample #{sid:02d}: Human={human_verdict:<11} | Judge={judge_verdict:<11} {status_tag}")

    total = len(HUMAN_CALIBRATION_SET)
    agreement_rate = round(agreements / total, 4)
    precision_hallucination = round(tp_hallucination / max(tp_hallucination + fp_hallucination, 1), 4)
    recall_hallucination = round(tp_hallucination / max(tp_hallucination + fn_hallucination, 1), 4)
    f1_hallucination = round(
        2 * precision_hallucination * recall_hallucination / max(precision_hallucination + recall_hallucination, 0.001), 4
    )

    print("\n=======================================================")
    print(f" LLM Judge Calibration Results:")
    print(f"   * Total Samples:              {total}")
    print(f"   * Agreement with Human Truth: {agreement_rate:.2%} ({agreements}/{total})")
    print(f"   * Hallucination Precision:    {precision_hallucination:.2%}")
    print(f"   * Hallucination Recall:       {recall_hallucination:.2%}")
    print(f"   * Hallucination F1:           {f1_hallucination:.2%}")
    print("=======================================================\n")

    return {
        "total_samples": total,
        "agreement_rate": agreement_rate,
        "hallucination_precision": precision_hallucination,
        "hallucination_recall": recall_hallucination,
        "hallucination_f1": f1_hallucination,
    }


if __name__ == "__main__":
    results = run_judge_calibration()
    if results["agreement_rate"] >= 0.80:
        print("✓ LLM Judge passed calibration threshold (>= 80% agreement).")
        sys.exit(0)
    else:
        print("✗ LLM Judge failed calibration threshold (< 80% agreement).", file=sys.stderr)
        sys.exit(1)

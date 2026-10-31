#!/usr/bin/env python3
"""
eval/phase7_differentiator_eval.py — Phase 7: The Differentiator Evaluation Benchmark

Measures:
  1. Commitment Link Precision, Recall, and F1 across multi-meeting scenarios
  2. Days Unresolved & Aging Accuracy
  3. Decision Contradiction Detection Precision, Recall, and F1
  4. Hinglish Code-Switching Detection & Commitment Extraction Accuracy

Usage:
    python -m eval.phase7_differentiator_eval --output eval/results/phase7.json
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

# Reconfigure stdout for UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure Backend in path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Backend"))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from core.commitment_tracker import (
    detect_decision_contradictions,
    track_and_link_commitments,
)
from core.hinglish_normalizer import (
    detect_code_switching,
    extract_hinglish_commitments,
    normalize_temporal_expressions,
)
from db.models import ActionItem, Base, Decision, Meeting
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Test Data Fixtures
# ---------------------------------------------------------------------------

COMMITMENT_SCENARIOS = [
    # (Meeting A item, Meeting B item, days_diff, is_link, expected_link_type)
    {
        "m1_task": "Implement Redis session caching for API endpoints",
        "m1_owner": "Alice",
        "m2_task": "Finish Redis caching implementation for API authentication",
        "m2_owner": "Alice",
        "days": 21,
        "is_true_link": True,
        "link_type": "repeated_commitment",
    },
    {
        "m1_task": "Upgrade PostgreSQL database cluster to version 16",
        "m1_owner": "Charlie",
        "m2_task": "PostgreSQL 16 database migration is still delayed",
        "m2_owner": "Charlie",
        "days": 14,
        "is_true_link": True,
        "link_type": "repeated_commitment",
    },
    {
        "m1_task": "Design mobile responsive layout for meeting dashboard",
        "m1_owner": "David",
        "m2_task": "Mobile responsive design layout is now completed and merged",
        "m2_owner": "David",
        "days": 7,
        "is_true_link": True,
        "link_type": "status_update",
    },
    {
        "m1_task": "Audit third-party webhook security credentials",
        "m1_owner": "Frank",
        "m2_task": "Security audit on webhooks escalated to high priority blocker",
        "m2_owner": "Frank",
        "days": 10,
        "is_true_link": True,
        "link_type": "blocker_escalation",
    },
    {
        "m1_task": "Prepare Q3 client review presentation deck",
        "m1_owner": "Sarah",
        "m2_task": "Order office snacks and organize team lunch",
        "m2_owner": "Bob",
        "days": 5,
        "is_true_link": False,
        "link_type": "none",
    },
    {
        "m1_task": "Configure Prometheus and Grafana alerts for latency spikes",
        "m1_owner": "DevOps",
        "m2_task": "Write customer release notes for blog post",
        "m2_owner": "Marketing",
        "days": 12,
        "is_true_link": False,
        "link_type": "none",
    },
]

DECISION_SCENARIOS = [
    # (Decision A, Decision B, is_contradiction)
    {
        "d1": "We chose PostgreSQL with pgvector for primary vector and relational storage",
        "d2": "We decided to replace PostgreSQL and migrate to MongoDB for all persistence",
        "is_contradiction": True,
    },
    {
        "d1": "Use modular monolith architecture to keep operational complexity low",
        "d2": "Break monolith down into 15 independent microservices immediately",
        "is_contradiction": True,
    },
    {
        "d1": "All third-party payments will be handled exclusively by Stripe",
        "d2": "Cancel Stripe integration and adopt Adyen as payment gateway",
        "is_contradiction": True,
    },
    {
        "d1": "Adopt JWT access tokens with 15-minute expiration",
        "d2": "Add refresh token rotation to secure long-lived user sessions",
        "is_contradiction": False,
    },
    {
        "d1": "Use Redis for in-memory session caching",
        "d2": "Enable Redis cluster persistence with AOF logging",
        "is_contradiction": False,
    },
]

HINGLISH_SCENARIOS = [
    {
        "text": "[SPEAKER_01 00:01:10] Main API authentication module kal tak fix kar dunga.",
        "has_intent": True,
        "expected_owner": "SPEAKER_01",
        "expected_due": "tomorrow",
    },
    {
        "text": "[SPEAKER_02 00:02:40] Payment gateway ka blocker parson tak dekhna padega.",
        "has_intent": True,
        "expected_owner": "SPEAKER_02",
        "expected_due": "in 2 days",
    },
    {
        "text": "[SPEAKER_00 00:04:15] Agle hafte sprint retrospective schedule karenge.",
        "has_intent": True,
        "expected_owner": "SPEAKER_00",
        "expected_due": "next week",
    },
    {
        "text": "[SPEAKER_03 00:05:00] Haan bhai sab theek hai, presentation acchi thi.",
        "has_intent": False,
        "expected_owner": None,
        "expected_due": None,
    },
    {
        "text": "[SPEAKER_01 00:06:20] Normal English conversation with no Hindi words at all.",
        "has_intent": False,
        "expected_owner": None,
        "expected_due": None,
    },
]


async def run_benchmark(output_path: str = "eval/results/phase7.json") -> Dict[str, Any]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        # -------------------------------------------------------------
        # Part 1: Commitment Linking Benchmark
        # -------------------------------------------------------------
        tp_links = 0
        fp_links = 0
        fn_links = 0
        tn_links = 0
        aging_accuracies = []

        now = datetime.now(timezone.utc)

        for idx, sc in enumerate(COMMITMENT_SCENARIOS):
            t1 = now - timedelta(days=sc["days"] + 5)
            t2 = now - timedelta(days=5)

            m1 = Meeting(id=f"eval-m1-{idx}", user_id=f"user-comm-{idx}", title=f"Sync A #{idx}", audio_filename="a.mp3", duration_minutes=20, short_summary="", detailed_summary="", created_at=t1)
            m2 = Meeting(id=f"eval-m2-{idx}", user_id=f"user-comm-{idx}", title=f"Sync B #{idx}", audio_filename="b.mp3", duration_minutes=20, short_summary="", detailed_summary="", created_at=t2)
            session.add_all([m1, m2])

            ai1 = ActionItem(id=f"eval-ai1-{idx}", meeting_id=m1.id, description=sc["m1_task"], owner=sc["m1_owner"], due_date="2026-10-01", status="open", created_at=t1)
            ai2 = ActionItem(id=f"eval-ai2-{idx}", meeting_id=m2.id, description=sc["m2_task"], owner=sc["m2_owner"], due_date="2026-10-20", status="open", created_at=t2)
            session.add_all([ai1, ai2])
            await session.commit()

            links = await track_and_link_commitments(session, m2.id)
            predicted_link = len(links) > 0

            if sc["is_true_link"] and predicted_link:
                tp_links += 1
                link_obj = links[0]
                expected_days = sc["days"]
                actual_days = link_obj.days_unresolved
                aging_accuracies.append(abs(expected_days - actual_days) <= 1)
            elif not sc["is_true_link"] and predicted_link:
                fp_links += 1
            elif sc["is_true_link"] and not predicted_link:
                fn_links += 1
            else:
                tn_links += 1

        link_prec = tp_links / max(1, tp_links + fp_links)
        link_rec = tp_links / max(1, tp_links + fn_links)
        link_f1 = (2 * link_prec * link_rec) / max(0.001, link_prec + link_rec)
        aging_acc = sum(aging_accuracies) / max(1, len(aging_accuracies))

        # -------------------------------------------------------------
        # Part 2: Decision Contradiction Benchmark
        # -------------------------------------------------------------
        tp_contra = 0
        fp_contra = 0
        fn_contra = 0
        tn_contra = 0

        for idx, dc in enumerate(DECISION_SCENARIOS):
            t1 = now - timedelta(days=20)
            t2 = now - timedelta(days=2)
            m1 = Meeting(id=f"eval-dec-m1-{idx}", user_id=f"user-dec-{idx}", title=f"Arch A #{idx}", audio_filename="a.mp3", duration_minutes=15, short_summary="", detailed_summary="", created_at=t1)
            m2 = Meeting(id=f"eval-dec-m2-{idx}", user_id=f"user-dec-{idx}", title=f"Arch B #{idx}", audio_filename="b.mp3", duration_minutes=15, short_summary="", detailed_summary="", created_at=t2)
            session.add_all([m1, m2])

            d1 = Decision(id=f"eval-d1-{idx}", meeting_id=m1.id, description=dc["d1"], context="", created_at=t1)
            d2 = Decision(id=f"eval-d2-{idx}", meeting_id=m2.id, description=dc["d2"], context="", created_at=t2)
            session.add_all([d1, d2])
            await session.commit()

            contras = await detect_decision_contradictions(session, m2.id)
            pred_contra = len(contras) > 0

            if dc["is_contradiction"] and pred_contra:
                tp_contra += 1
            elif not dc["is_contradiction"] and pred_contra:
                fp_contra += 1
            elif dc["is_contradiction"] and not pred_contra:
                fn_contra += 1
            else:
                tn_contra += 1

        contra_prec = tp_contra / max(1, tp_contra + fp_contra)
        contra_rec = tp_contra / max(1, tp_contra + fn_contra)
        contra_f1 = (2 * contra_prec * contra_rec) / max(0.001, contra_prec + contra_rec)

        # -------------------------------------------------------------
        # Part 3: Hinglish & Code-Switching Benchmark
        # -------------------------------------------------------------
        hinglish_correct = 0
        temporal_matches = 0

        for hc in HINGLISH_SCENARIOS:
            commitments = extract_hinglish_commitments(hc["text"])
            has_pred = len(commitments) > 0
            if has_pred == hc["has_intent"]:
                hinglish_correct += 1

            if hc["expected_due"] and has_pred:
                if commitments[0]["due_date"] == hc["expected_due"]:
                    temporal_matches += 1

        hinglish_acc = hinglish_correct / len(HINGLISH_SCENARIOS)
        temporal_acc = temporal_matches / max(1, sum(1 for h in HINGLISH_SCENARIOS if h["expected_due"]))

    await engine.dispose()

    report = {
        "benchmark": "Phase 7: The Differentiator Benchmark",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commitment_linking": {
            "scenarios_evaluated": len(COMMITMENT_SCENARIOS),
            "precision": round(link_prec, 4),
            "recall": round(link_rec, 4),
            "f1_score": round(link_f1, 4),
            "aging_calculation_accuracy": round(aging_acc, 4),
        },
        "decision_contradictions": {
            "scenarios_evaluated": len(DECISION_SCENARIOS),
            "precision": round(contra_prec, 4),
            "recall": round(contra_rec, 4),
            "f1_score": round(contra_f1, 4),
        },
        "hinglish_intelligence": {
            "scenarios_evaluated": len(HINGLISH_SCENARIOS),
            "intent_detection_accuracy": round(hinglish_acc, 4),
            "temporal_normalization_accuracy": round(temporal_acc, 4),
        },
    }

    # Print summary table
    print("\n" + "=" * 70)
    print("PHASE 7 DIFFERENTIATOR BENCHMARK RESULTS")
    print("=" * 70)
    print(f"Commitment Linking F1           : {link_f1 * 100:.1f}% (Precision: {link_prec*100:.1f}%, Recall: {link_rec*100:.1f}%)")
    print(f"Aging & Days Unresolved Acc    : {aging_acc * 100:.1f}%")
    print(f"Contradiction Detection F1      : {contra_f1 * 100:.1f}% (Precision: {contra_prec*100:.1f}%, Recall: {contra_rec*100:.1f}%)")
    print(f"Hinglish Intent Accuracy        : {hinglish_acc * 100:.1f}%")
    print(f"Hinglish Temporal Normalization : {temporal_acc * 100:.1f}%")
    print("=" * 70)

    # Save JSON and Markdown
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n[Saved JSON Report]: {output_path}")

    md_file = out_file.with_suffix(".md")
    md_text = [
        "# Phase 7: The Differentiator Evaluation Report",
        "",
        f"- **Date**: `{report['timestamp']}`",
        "",
        "## 1. Cross-Meeting Commitment Tracking",
        "",
        "| Metric | Target | Measured Result | Status |",
        "|---|---|---|---|",
        f"| **Link Precision** | ≥ 85.0% | **{link_prec*100:.1f}%** | {'✅ PASS' if link_prec >= 0.85 else '⚠️ WARN'} |",
        f"| **Link Recall** | ≥ 80.0% | **{link_rec*100:.1f}%** | {'✅ PASS' if link_rec >= 0.80 else '⚠️ WARN'} |",
        f"| **Commitment Linking F1** | ≥ 82.0% | **{link_f1*100:.1f}%** | {'✅ PASS' if link_f1 >= 0.82 else '⚠️ WARN'} |",
        f"| **Aging Timeline Accuracy** | ≥ 90.0% | **{aging_acc*100:.1f}%** | {'✅ PASS' if aging_acc >= 0.90 else '⚠️ WARN'} |",
        "",
        "## 2. Decision Contradiction Detection",
        "",
        "| Metric | Target | Measured Result | Status |",
        "|---|---|---|---|",
        f"| **Contradiction Precision** | ≥ 80.0% | **{contra_prec*100:.1f}%** | {'✅ PASS' if contra_prec >= 0.80 else '⚠️ WARN'} |",
        f"| **Contradiction Recall** | ≥ 80.0% | **{contra_rec*100:.1f}%** | {'✅ PASS' if contra_rec >= 0.80 else '⚠️ WARN'} |",
        f"| **Contradiction F1** | ≥ 80.0% | **{contra_f1*100:.1f}%** | {'✅ PASS' if contra_f1 >= 0.80 else '⚠️ WARN'} |",
        "",
        "## 3. Hinglish & Indian-Language Support",
        "",
        "| Capability | Target | Measured Result | Status |",
        "|---|---|---|---|",
        f"| **Code-Switching Intent Accuracy** | ≥ 85.0% | **{hinglish_acc*100:.1f}%** | {'✅ PASS' if hinglish_acc >= 0.85 else '⚠️ WARN'} |",
        f"| **Colloquial Deadline Normalization** | ≥ 90.0% | **{temporal_acc*100:.1f}%** | {'✅ PASS' if temporal_acc >= 0.90 else '⚠️ WARN'} |",
        "",
        "## Key Differentiation Highlights",
        "1. **Cross-Meeting Auditability**: Flags repeated commitments ('Promised 3 weeks ago in Sprint 40, raised again, still not done').",
        "2. **Conflict Prevention**: Catches architectural flip-flops before engineering teams waste sprints on conflicting architectures.",
        "3. **Indian Tech Ecosystem Native**: Understands bilingual Hinglish syncs where English tasks blend with Hindi verbal commitments.",
    ]
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_text))
    print(f"[Saved Markdown Report]: {md_file}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Phase 7: The Differentiator Evaluation")
    parser.add_argument("--output", type=str, default="eval/results/phase7.json", help="Path to output JSON")
    args = parser.parse_args()

    asyncio.run(run_benchmark(output_path=args.output))


if __name__ == "__main__":
    main()

"""
eval/metrics/decisions.py — Decision extraction evaluation metrics.

Computes:
- Precision, Recall, and F1 for meeting decisions.
"""

import re
from typing import Dict, List, Set, Tuple
from eval.schema import PredictedDecision, ReferenceDecision


def _tokenize(text: str) -> Set[str]:
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return {w for w in cleaned.split() if len(w) > 2}


def _similarity(s1: str, s2: str) -> float:
    t1 = _tokenize(s1)
    t2 = _tokenize(s2)
    if not t1 or not t2:
        return 0.0
    return len(t1.intersection(t2)) / len(t1.union(t2))


def evaluate_decisions(
    references: List[ReferenceDecision],
    predictions: List[PredictedDecision],
    match_threshold: float = 0.35,
) -> Dict[str, float]:
    """Evaluates candidate decisions against ground-truth decisions."""
    if not references and not predictions:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "tp": 0, "fp": 0, "fn": 0}

    matched_refs: Set[int] = set()
    matched_preds: Set[int] = set()

    candidates: List[Tuple[float, int, int]] = []
    for p_idx, pred in enumerate(predictions):
        for r_idx, ref in enumerate(references):
            sim = _similarity(pred.decision, ref.decision)
            if sim >= match_threshold:
                candidates.append((sim, p_idx, r_idx))

    candidates.sort(reverse=True, key=lambda x: x[0])

    for sim, p_idx, r_idx in candidates:
        if p_idx not in matched_preds and r_idx not in matched_refs:
            matched_preds.add(p_idx)
            matched_refs.add(r_idx)

    tp = len(matched_preds)
    fp = len(predictions) - tp
    fn = len(references) - tp

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
    f1 = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }

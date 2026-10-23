"""
eval/metrics/action_items.py — Action item extraction evaluation metrics.

Computes:
- Precision, Recall, and F1 on action items.
- Owner attribution accuracy on matched items.
- Due-date extraction accuracy on matched items.
"""

import re
from typing import Dict, List, Optional, Set, Tuple
from eval.schema import PredictedActionItem, ReferenceActionItem


def _tokenize(text: str) -> Set[str]:
    """Tokenize and normalize text into a set of lower-case words."""
    norm = re.sub(r"\$(\d+),?(\d*)", r"\1\2", text.lower())
    cleaned = re.sub(r"[^\w\s]", " ", norm)
    return {w for w in cleaned.split() if len(w) >= 2}


def _similarity(s1: str, s2: str) -> float:
    """Blended Jaccard and containment similarity between two strings."""
    tokens1 = _tokenize(s1)
    tokens2 = _tokenize(s2)
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    jaccard = len(intersection) / len(tokens1.union(tokens2))
    containment = len(intersection) / min(len(tokens1), len(tokens2))
    return max(jaccard, containment * 0.75)


def _match_owner(ref_owner: Optional[str], pred_owner: Optional[str]) -> bool:
    """Check if predicted owner matches ground truth owner."""
    if not ref_owner and not pred_owner:
        return True
    if not ref_owner or not pred_owner:
        return False
    r = ref_owner.strip().lower()
    p = pred_owner.strip().lower()
    return r in p or p in r


def _match_date(ref_date: Optional[str], pred_date: Optional[str]) -> bool:
    """Check if predicted due date matches ground truth."""
    if not ref_date and not pred_date:
        return True
    if not ref_date or not pred_date:
        return False
    r = ref_date.strip().lower()
    p = pred_date.strip().lower()
    return r in p or p in r


def evaluate_action_items(
    references: List[ReferenceActionItem],
    predictions: List[PredictedActionItem],
    match_threshold: float = 0.35,
) -> Dict[str, float]:
    """
    Evaluates candidate action items against reference items.

    Returns dict with:
      - precision, recall, f1
      - true_positives, false_positives, false_negatives
      - owner_accuracy (fraction of matched items with correct owner)
      - due_date_accuracy (fraction of matched items with correct due date)
    """
    if not references and not predictions:
        return {
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "true_positives": 0,
            "false_positives": 0,
            "false_negatives": 0,
            "owner_accuracy": 1.0,
            "due_date_accuracy": 1.0,
        }

    matched_refs: Set[int] = set()
    matched_preds: Set[int] = set()

    owner_correct = 0
    date_correct = 0

    # Greedy bipartite matching based on description similarity
    candidates: List[Tuple[float, int, int]] = []
    for p_idx, pred in enumerate(predictions):
        for r_idx, ref in enumerate(references):
            sim = _similarity(pred.description, ref.description)
            if sim >= match_threshold:
                candidates.append((sim, p_idx, r_idx))

    candidates.sort(reverse=True, key=lambda x: x[0])

    for sim, p_idx, r_idx in candidates:
        if p_idx not in matched_preds and r_idx not in matched_refs:
            matched_preds.add(p_idx)
            matched_refs.add(r_idx)

            ref = references[r_idx]
            pred = predictions[p_idx]

            if _match_owner(ref.owner, pred.owner):
                owner_correct += 1
            if _match_date(ref.due_date, pred.due_date):
                date_correct += 1

    tp = len(matched_preds)
    fp = len(predictions) - tp
    fn = len(references) - tp

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
    f1 = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0

    owner_acc = round(owner_correct / tp, 4) if tp > 0 else 0.0
    date_acc = round(date_correct / tp, 4) if tp > 0 else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "owner_accuracy": owner_acc,
        "due_date_accuracy": date_acc,
    }

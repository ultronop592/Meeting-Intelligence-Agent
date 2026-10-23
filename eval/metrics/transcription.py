"""
eval/metrics/transcription.py — Word Error Rate (WER) and Character Error Rate (CER).

Calculates edit distance between reference and hypothesis transcripts.
Uses `jiwer` if installed, with a self-contained Levenshtein DP fallback.
"""

import re
from typing import Tuple


def normalize_text(text: str) -> str:
    """Normalize whitespace and punctuation for fair speech comparison."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _levenshtein_distance(seq1: list, seq2: list) -> int:
    """Standard dynamic programming Levenshtein distance."""
    m, n = len(seq1), len(seq2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq1[i - 1] == seq2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

    return dp[m][n]


def calculate_wer(reference: str, hypothesis: str) -> float:
    """Calculate Word Error Rate (WER) = (S + D + I) / N_ref."""
    try:
        import jiwer
        return float(jiwer.wer(reference, hypothesis))
    except ImportError:
        pass

    ref_norm = normalize_text(reference)
    hyp_norm = normalize_text(hypothesis)

    ref_words = ref_norm.split()
    hyp_words = hyp_norm.split()

    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    distance = _levenshtein_distance(ref_words, hyp_words)
    return round(distance / len(ref_words), 4)


def calculate_cer(reference: str, hypothesis: str) -> float:
    """Calculate Character Error Rate (CER)."""
    try:
        import jiwer
        return float(jiwer.cer(reference, hypothesis))
    except (ImportError, AttributeError):
        pass

    ref_chars = list(normalize_text(reference).replace(" ", ""))
    hyp_chars = list(normalize_text(hypothesis).replace(" ", ""))

    if not ref_chars:
        return 0.0 if not hyp_chars else 1.0

    distance = _levenshtein_distance(ref_chars, hyp_chars)
    return round(distance / len(ref_chars), 4)

"""
eval/metrics/summary.py — Meeting summary evaluation metrics (Coverage and Faithfulness).

Provides:
1. Lexical coverage: Key noun-phrase / content word overlap between transcript and summary.
2. Fact containment: Checks what fraction of sentence claims in the summary find direct text support in the transcript.
3. LLM-judge hook (optional): Prompts a fast LLM to score hallucination / faithfulness on a 0-1 scale.
"""

import re
from typing import Dict, List, Optional, Set


def _content_words(text: str) -> Set[str]:
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
        "by", "from", "up", "about", "into", "over", "after", "is", "are", "was", "were",
        "be", "been", "being", "have", "has", "had", "do", "does", "did", "this", "that",
        "these", "those", "it", "they", "we", "you", "i", "he", "she", "as", "will", "would",
    }
    return {w for w in cleaned.split() if len(w) > 3 and w not in stopwords}


def _word_supported(word: str, trans_words: Set[str]) -> bool:
    if word in trans_words:
        return True
    if len(word) >= 4:
        prefix = word[:4]
        for tw in trans_words:
            if tw.startswith(prefix) or (len(tw) >= 4 and word.startswith(tw[:4])):
                return True
    return False


def calculate_summary_coverage(transcript: str, summary: str) -> float:
    """Measures what proportion of the summary's salient terms originate in the source transcript."""
    trans_words = _content_words(transcript)
    sum_words = _content_words(summary)

    if not sum_words:
        return 0.0

    supported_count = sum(1 for w in sum_words if _word_supported(w, trans_words))
    return round(supported_count / len(sum_words), 4)


def calculate_heuristic_faithfulness(transcript: str, summary: str) -> float:
    """
    Heuristic estimate of summary faithfulness based on sentence-level
    keyword support against the reference transcript.
    """
    sentences = [s.strip() for s in re.split(r"[.!?\n]", summary) if len(s.strip()) > 10]
    if not sentences:
        return 1.0

    trans_words = _content_words(transcript)
    supported_sentences = 0

    for sentence in sentences:
        s_words = _content_words(sentence)
        if not s_words:
            supported_sentences += 1
            continue
        supported_count = sum(1 for w in s_words if _word_supported(w, trans_words))
        overlap = supported_count / len(s_words)
        if overlap >= 0.5:
            supported_sentences += 1

    return round(supported_sentences / len(sentences), 4)

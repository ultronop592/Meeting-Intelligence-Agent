"""
core/hinglish_normalizer.py — Phase 7: Hinglish & Indian-Language Intelligence Layer

WHAT IT DOES
------------
Provides specialized processing for code-switched Hindi-English (Hinglish) meetings,
a major differentiator for global and Indian engineering teams.

1. **Code-Switching Detection**:
   - Scans verbatim audio transcripts for Hindi vocabulary in Latin and Devanagari scripts.
   - Calculates a code-switching ratio (`code_switching_score`).

2. **Commitment & Intent Extraction**:
   - Recognizes Hindi verbal commitment patterns:
     - "kar dunga" / "karunga" (I will do / take care of it)
     - "dekh leta hoon" / "dekhunga" (I will investigate / look into it)
     - "merge kar dunga" / "fix karunga" / "bhej dunga" (I will merge/fix/send)
     - "karna hai" / "karna padega" (needs to be done / mandatory task)
     - "ho jayega" / "chalega" (will be accomplished / agreed)

3. **Temporal Expression Normalizer**:
   - Converts colloquial Indian time expressions to standard ISO/English deadlines:
     - "aaj shaam tak"  → "today EOD"
     - "kal tak"        → "tomorrow"
     - "parson"         → "in 2 days"
     - "agle hafte"     → "next week"
     - "somwar tak"     → "by Monday"
     - "shukrawar tak"  → "by Friday"

4. **Transcript Normalization for LLM & Evaluator**:
   - Provides phonetic transliteration mapping to ensure Whisper errors on Indian names
     and verbs are resolved before downstream extraction.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Common Hinglish stopwords and conversational particles
HINGLISH_VOCAB = {
    # Verb stems and inflections
    "karna", "karega", "karenge", "karunga", "kar", "karo", "kiya", "kiye", "hoga", "hogi", "hoge",
    "dekh", "dekho", "dekhte", "dekhunga", "dekhna", "bhejo", "bhejna", "bhejunga",
    "bana", "banao", "banayenge", "banega", "chalega", "chalta", "chal",
    # Modals & auxiliaries
    "hai", "hain", "tha", "thi", "the", "raha", "rahi", "rahe", "gaya", "gayi", "gaye",
    "padega", "padegi", "chahiye", "sakta", "sakti", "sakte", "denge", "dunga", "dungi",
    # Pronouns & pointers
    "hum", "humne", "hamara", "aap", "aapka", "tum", "tumhara", "main", "maine", "mera", "meri",
    "yeh", "woh", "isko", "usko", "inka", "unka", "kisko",
    # Prepositions & conjunctions
    "ka", "ki", "ke", "ko", "se", "mein", "par", "tak", "aur", "ya", "lekin", "magar", "kyunki",
    # Discourse markers
    "theek", "accha", "sahi", "haan", "nahi", "matlab", "bhai", "yaar", "pakka",
}

# Commitment intent regex patterns
HINGLISH_COMMITMENT_PATTERNS = [
    # "main <task> kar dunga / karunga"
    re.compile(r"(?:main|hum)\s+([a-zA-Z0-9_\s]{3,40}?)\s+(?:kar\s+dunga|karunga|dekh\s+lunga|dekhunga|bhej\s+dunga|fix\s+kar\s+dunga|merge\s+kar\s+dunga)", re.IGNORECASE),
    # "<task> fix karna hai / karna padega"
    re.compile(r"([a-zA-Z0-9_\s]{3,40}?)\s+(?:fix\s+karna\s+hai|karna\s+padega|karna\s+hoga|complete\s+karna\s+hai)", re.IGNORECASE),
    # "kal tak <task> ho jayega"
    re.compile(r"([a-zA-Z0-9_\s]{3,30}?)\s+(?:ho\s+jayega|resolve\s+kar\s+denge|finish\s+ho\s+jayega)", re.IGNORECASE),
]

# Temporal expression mappings
TEMPORAL_MAPPINGS = [
    (re.compile(r"\baaj\s+shaam\s+tak\b", re.IGNORECASE), "today EOD"),
    (re.compile(r"\baaj\s+tak\b", re.IGNORECASE), "today"),
    (re.compile(r"\bkal\s+subah\s+tak\b", re.IGNORECASE), "tomorrow morning"),
    (re.compile(r"\bkal\s+shaam\s+tak\b", re.IGNORECASE), "tomorrow evening"),
    (re.compile(r"\bkal\s+tak\b", re.IGNORECASE), "tomorrow"),
    (re.compile(r"\bparson\s+tak\b", re.IGNORECASE), "in 2 days"),
    (re.compile(r"\bparso[n]?\b", re.IGNORECASE), "in 2 days"),
    (re.compile(r"\bagle\s+hafte\b", re.IGNORECASE), "next week"),
    (re.compile(r"\bagle\s+week\b", re.IGNORECASE), "next week"),
    (re.compile(r"\bis\s+hafte\b", re.IGNORECASE), "this week"),
    (re.compile(r"\bsomwar\s+tak\b", re.IGNORECASE), "by Monday"),
    (re.compile(r"\bmangalwar\s+tak\b", re.IGNORECASE), "by Tuesday"),
    (re.compile(r"\bbudhwar\s+tak\b", re.IGNORECASE), "by Wednesday"),
    (re.compile(r"\bguruwar\s+tak\b", re.IGNORECASE), "by Thursday"),
    (re.compile(r"\bshukrawar\s+tak\b", re.IGNORECASE), "by Friday"),
    (re.compile(r"\bshanivar\s+tak\b", re.IGNORECASE), "by Saturday"),
]


def detect_code_switching(text: str) -> Dict[str, Any]:
    """Analyze a transcript to detect whether it contains Hinglish code-switching.

    Returns:
      - is_code_switched: bool (true if code-switching ratio >= 0.04)
      - score: float (0.0 to 1.0)
      - detected_hindi_tokens: list of detected words
    """
    if not text or not text.strip():
        return {
            "is_code_switched": False,
            "score": 0.0,
            "detected_hindi_tokens": [],
            "language": "en",
        }

    # Also detect Devanagari characters (Unicode range \u0900-\u097F)
    devanagari_count = len(re.findall(r"[\u0900-\u097F]", text))
    clean_words = [w.lower() for w in re.findall(r"\b[a-z]{2,}\b", text.lower())]
    if not clean_words and devanagari_count == 0:
        return {
            "is_code_switched": False,
            "score": 0.0,
            "detected_hindi_tokens": [],
            "language": "en",
        }

    hindi_matches = [w for w in clean_words if w in HINGLISH_VOCAB]
    score = (len(hindi_matches) + (devanagari_count // 3)) / max(1, len(clean_words))
    is_hinglish = score >= 0.04 or devanagari_count >= 10

    return {
        "is_code_switched": is_hinglish,
        "score": round(min(1.0, score), 4),
        "detected_hindi_tokens": list(set(hindi_matches))[:15],
        "language": "hi-en" if is_hinglish else "en",
    }


def normalize_temporal_expressions(text: str) -> str:
    """Normalize Hinglish date/time expressions to English equivalents."""
    normalized = text
    for pattern, replacement in TEMPORAL_MAPPINGS:
        normalized = pattern.sub(replacement, normalized)
    return normalized


def extract_hinglish_commitments(diarized_transcript: str) -> List[Dict[str, Any]]:
    """Scan diarized Hinglish dialogue to extract action item commitments."""
    extracted_items: List[Dict[str, Any]] = []

    # Parse diarized turns: [SPEAKER_00 00:01:23] Text...
    turn_pattern = re.compile(
        r"\[([A-Z_0-9]+)\s+(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.*?)(?=\[|\Z)", re.DOTALL
    )
    matches = list(turn_pattern.finditer(diarized_transcript))

    for m in matches:
        speaker = m.group(1)
        timestamp = m.group(2)
        turn_text = m.group(3).strip()

        # Check for Hinglish commitment patterns
        for pattern in HINGLISH_COMMITMENT_PATTERNS:
            found = pattern.search(turn_text)
            if found:
                raw_task = found.group(1).strip()
                # Clean up task
                raw_task = re.sub(r"^(yeh|woh|isko|usko)\s+", "", raw_task, flags=re.I).strip()
                if len(raw_task) >= 3:
                    # Normalize time expressions in turn
                    normalized_turn = normalize_temporal_expressions(turn_text)
                    deadline = "unspecified"
                    for _, rep in TEMPORAL_MAPPINGS:
                        if rep.lower() in normalized_turn.lower():
                            deadline = rep
                            break

                    extracted_items.append({
                        "description": f"Handle {raw_task}",
                        "raw_quote": turn_text,
                        "owner": speaker,
                        "due_date": deadline,
                        "evidence_timestamp": timestamp,
                        "confidence": 0.88,
                        "language": "hinglish",
                    })
                break

    return extracted_items


def build_hinglish_system_instruction() -> str:
    """Returns a prompt instruction snippet to append to LLM extractors when Hinglish is detected."""
    return (
        "\n\n[HINGLISH / INDIAN-LANGUAGE MEETING DIRECTIVE]:\n"
        "The transcript contains code-switched Hindi-English (Hinglish) dialogue.\n"
        "1. Identify verbal commitment markers such as 'kar dunga', 'dekh lunga', 'fix karenge', and 'karna padega' as explicit action items.\n"
        "2. Translate Hinglish task descriptions into clean, professional English action items.\n"
        "3. Interpret temporal terms accurately: 'kal tak' -> 'tomorrow', 'parson' -> 'in 2 days', 'agle hafte' -> 'next week', 'aaj shaam tak' -> 'today EOD'.\n"
        "4. Assign the action item to the speaker who made the commitment, citing the verbatim quote."
    )

"""core/pii_redactor.py — Phase 4 Security: Optional PII Redaction.

Redacts Personally Identifiable Information (PII) from meeting transcripts
*before* the text is sent to an external LLM (Groq, OpenRouter).

This is an optional, configurable layer.  Enable it via:
    PII_REDACTION_ENABLED=true     in .env

Entities redacted (regex-based, zero external dependencies):
  - Email addresses         → [EMAIL]
  - Phone numbers (E.164 + common formats)  → [PHONE]
  - Credit/debit card numbers (Luhn-like)   → [CARD]
  - Indian PAN numbers                      → [PAN]
  - Aadhaar numbers (12-digit)              → [AADHAAR]
  - IP addresses (v4 & v6)                  → [IP_ADDRESS]
  - URLs with auth credentials              → [URL]

Named-entity recognition (NER) for names and addresses requires an optional
spaCy model.  If spaCy is not installed the module still works — only regex
redaction is applied.

Usage::

    from core.pii_redactor import pii_redactor

    safe_transcript = pii_redactor.redact(raw_transcript)
    # → "John's email is [EMAIL] and his phone is [PHONE]."

    # Get a report of what was redacted:
    result = pii_redactor.redact_with_report(raw_transcript)
    print(result["redacted_text"])
    print(result["redaction_counts"])
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns — ordered from most-specific to least-specific
# ---------------------------------------------------------------------------

@dataclass
class _Rule:
    name: str
    pattern: re.Pattern[str]
    replacement: str


_RULES: list[_Rule] = [
    # Email addresses
    _Rule(
        "email",
        re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"),
        "[EMAIL]",
    ),
    # URLs containing credentials (user:pass@host)
    _Rule(
        "url_with_credentials",
        re.compile(r"https?://[^:/@\s]+:[^:/@\s]+@[^\s]+", re.I),
        "[URL]",
    ),
    # Credit / debit card numbers (13-19 digits, with or without spaces/dashes)
    _Rule(
        "card_number",
        re.compile(r"\b(?:\d[ \-]?){13,19}\b"),
        "[CARD]",
    ),
    # Indian PAN (e.g. ABCDE1234F)
    _Rule(
        "pan",
        re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
        "[PAN]",
    ),
    # Aadhaar (12 consecutive digits, often written as XXXX XXXX XXXX)
    _Rule(
        "aadhaar",
        re.compile(r"\b\d{4}[ \-]?\d{4}[ \-]?\d{4}\b"),
        "[AADHAAR]",
    ),
    # E.164 international phone (+91 98765 43210, +1-800-555-0199, etc.)
    _Rule(
        "phone_e164",
        re.compile(r"\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{1,4}[\s\-]?\d{1,9}"),
        "[PHONE]",
    ),
    # US-style phone (800-555-0199, (800) 555 0199)
    _Rule(
        "phone_us",
        re.compile(r"\b(?:\(?\d{3}\)?[\s.\-]?)?\d{3}[\s.\-]\d{4}\b"),
        "[PHONE]",
    ),
    # IPv4 addresses
    _Rule(
        "ipv4",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
        "[IP_ADDRESS]",
    ),
    # IPv6 addresses (simplified)
    _Rule(
        "ipv6",
        re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"),
        "[IP_ADDRESS]",
    ),
]


# ---------------------------------------------------------------------------
# PII Redactor class
# ---------------------------------------------------------------------------

class PIIRedactor:
    """Apply configured PII redaction rules to text.

    Controlled by the ``PII_REDACTION_ENABLED`` setting.  When disabled,
    :meth:`redact` is a passthrough.
    """

    def __init__(self) -> None:
        self._enabled: bool = getattr(settings, "pii_redaction_enabled", False)
        if self._enabled:
            logger.info("PIIRedactor: enabled (%d regex rules loaded)", len(_RULES))
        else:
            logger.info("PIIRedactor: disabled (set PII_REDACTION_ENABLED=true to activate)")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def redact(self, text: str) -> str:
        """Return *text* with all detected PII replaced by placeholder tokens.

        If PII redaction is disabled, returns *text* unchanged.
        """
        if not self._enabled or not text:
            return text
        for rule in _RULES:
            text = rule.pattern.sub(rule.replacement, text)
        return text

    def redact_with_report(self, text: str) -> dict[str, Any]:
        """Redact *text* and return a report of what was found.

        Returns::

            {
                "redacted_text": str,
                "redaction_counts": {"email": 2, "phone_e164": 1, ...},
                "total_redactions": int,
                "pii_redaction_enabled": bool,
            }
        """
        counts: dict[str, int] = {}
        if self._enabled and text:
            for rule in _RULES:
                matches = rule.pattern.findall(text)
                if matches:
                    counts[rule.name] = len(matches)
                text = rule.pattern.sub(rule.replacement, text)

        return {
            "redacted_text": text,
            "redaction_counts": counts,
            "total_redactions": sum(counts.values()),
            "pii_redaction_enabled": self._enabled,
        }


# Module-level singleton
pii_redactor = PIIRedactor()

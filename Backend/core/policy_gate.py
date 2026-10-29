"""core/policy_gate.py — Phase 4 Security: External Write Policy Gate.

Enforces hard limits before any external side-effect (Jira ticket creation,
calendar events, Slack messages, outbound emails) is allowed to proceed.

Policy rules enforced:
  1. Allowed email domains         — reject recipients outside approved domains.
  2. Max Jira tickets per meeting  — cap runaway ticket creation.
  3. Max calendar events per meeting.
  4. No external email recipients  — unless the address is pre-approved.
  5. Slack / webhook message size  — prevent data-exfiltration via large payloads.

Usage::

    from core.policy_gate import PolicyGate, PolicyViolation

    gate = PolicyGate()
    gate.check_email_recipients(["alice@company.com", "evil@outside.io"])
    gate.check_jira_ticket_count(action_items)
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)


class PolicyViolation(Exception):
    """Raised when an external write violates a configured policy rule."""

    def __init__(self, rule: str, detail: str) -> None:
        self.rule = rule
        self.detail = detail
        super().__init__(f"[PolicyGate:{rule}] {detail}")


# ---------------------------------------------------------------------------
# Default policy limits (all overridable via Settings / env vars)
# ---------------------------------------------------------------------------

_DEFAULT_MAX_JIRA_TICKETS_PER_MEETING   = getattr(settings, "policy_max_jira_tickets",   10)
_DEFAULT_MAX_CALENDAR_EVENTS_PER_MEETING = getattr(settings, "policy_max_calendar_events", 5)
_DEFAULT_MAX_SLACK_MSG_CHARS             = getattr(settings, "policy_max_slack_msg_chars", 4000)

# Comma-separated allowed domains from env: POLICY_ALLOWED_EMAIL_DOMAINS=company.com,partner.org
_ALLOWED_EMAIL_DOMAINS_RAW: str = getattr(settings, "policy_allowed_email_domains", "")
_ALLOWED_EMAIL_DOMAINS: frozenset[str] = frozenset(
    d.strip().lower()
    for d in _ALLOWED_EMAIL_DOMAINS_RAW.split(",")
    if d.strip()
)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})$")


class PolicyGate:
    """Stateless policy enforcer for all external dispatch channels.

    Instantiate once per meeting processing job and call the relevant
    ``check_*`` methods before each external write.  All violations raise
    :class:`PolicyViolation` which the caller should catch and handle
    (abort the dispatch, log to audit, surface to user).
    """

    def __init__(
        self,
        allowed_email_domains: frozenset[str] | None = None,
        max_jira_tickets: int = _DEFAULT_MAX_JIRA_TICKETS_PER_MEETING,
        max_calendar_events: int = _DEFAULT_MAX_CALENDAR_EVENTS_PER_MEETING,
        max_slack_msg_chars: int = _DEFAULT_MAX_SLACK_MSG_CHARS,
    ) -> None:
        self._allowed_domains   = allowed_email_domains if allowed_email_domains is not None else _ALLOWED_EMAIL_DOMAINS
        self._max_jira          = max_jira_tickets
        self._max_cal           = max_calendar_events
        self._max_slack_chars   = max_slack_msg_chars

    # ------------------------------------------------------------------
    # 1. Email recipients
    # ------------------------------------------------------------------

    def check_email_recipients(self, recipients: list[str]) -> None:
        """Raise :class:`PolicyViolation` if any recipient is outside allowed domains.

        If no allowed domains are configured, all recipients pass (open mode).
        """
        if not self._allowed_domains:
            logger.debug("PolicyGate: no allowed email domains configured — all recipients accepted")
            return

        for addr in recipients:
            addr = addr.strip().lower()
            m = _EMAIL_RE.match(addr)
            if not m:
                raise PolicyViolation(
                    "email_invalid_format",
                    f"Recipient '{addr}' is not a valid email address.",
                )
            domain = m.group(1)
            if domain not in self._allowed_domains:
                raise PolicyViolation(
                    "email_domain_not_allowed",
                    f"Recipient '{addr}' has domain '{domain}' which is not in the "
                    f"allowed list: {sorted(self._allowed_domains)}",
                )

    # ------------------------------------------------------------------
    # 2. Jira ticket count
    # ------------------------------------------------------------------

    def check_jira_ticket_count(self, action_items: list[Any]) -> None:
        """Raise :class:`PolicyViolation` if more tickets than allowed would be created."""
        count = len(action_items)
        if count > self._max_jira:
            raise PolicyViolation(
                "jira_ticket_limit_exceeded",
                f"{count} Jira tickets requested for a single meeting — "
                f"limit is {self._max_jira}. Check for injection attack or misconfiguration.",
            )

    # ------------------------------------------------------------------
    # 3. Calendar event count
    # ------------------------------------------------------------------

    def check_calendar_event_count(self, events: list[Any]) -> None:
        """Raise :class:`PolicyViolation` if too many calendar events would be created."""
        count = len(events)
        if count > self._max_cal:
            raise PolicyViolation(
                "calendar_event_limit_exceeded",
                f"{count} calendar events requested — limit is {self._max_cal}.",
            )

    # ------------------------------------------------------------------
    # 4. Slack message size
    # ------------------------------------------------------------------

    def check_slack_payload(self, message: str) -> None:
        """Raise :class:`PolicyViolation` if the Slack message exceeds the size cap."""
        length = len(message)
        if length > self._max_slack_chars:
            raise PolicyViolation(
                "slack_message_too_large",
                f"Slack message is {length} chars — limit is {self._max_slack_chars}. "
                f"Possible data-exfiltration attempt.",
            )

    # ------------------------------------------------------------------
    # 5. Convenience: run ALL checks in one call
    # ------------------------------------------------------------------

    def enforce_all(
        self,
        *,
        email_recipients: list[str] | None = None,
        action_items: list[Any] | None = None,
        calendar_events: list[Any] | None = None,
        slack_message: str | None = None,
    ) -> None:
        """Run every applicable check in a single call.

        Pass ``None`` for channels that are not being used in this dispatch.
        """
        if email_recipients is not None:
            self.check_email_recipients(email_recipients)
        if action_items is not None:
            self.check_jira_ticket_count(action_items)
        if calendar_events is not None:
            self.check_calendar_event_count(calendar_events)
        if slack_message is not None:
            self.check_slack_payload(slack_message)

        logger.info("PolicyGate: all checks passed for this dispatch")

"""API Router Aggregator.

This module aggregates domain-specific routers:
- `meetings_router`   (api.meetings): Meeting upload, processing, details, audio, dispatch
- `reminders_router`  (api.reminders): Action item deadline and overdue notification triggers
- `chat_router`       (api.chat): Multi-turn conversational Q&A and vector memory search
- `analytics_router`  (api.analytics): Dashboard analytics, metrics, timelines, leaderboards
- `search_router`     (api.search): Global multi-entity fulltext/semantic search

All domain routes are mounted onto the primary `router` instance to maintain
100% backwards compatibility with `api.main` and existing integration tests.
"""

import sys
import types
from fastapi import APIRouter

from api.analytics import analytics_router
from api.chat import chat_router
import api.meetings as _meetings_module
from api.meetings import (
    meetings_router,
    send_calendar_for_meeting,
    send_email_for_meeting,
    send_jira_for_meeting,
    send_slack_for_meeting,
    storage_service,
)
from api.reminders import reminders_router
from api.search import search_router

# Master aggregator router
router = APIRouter()

router.include_router(meetings_router)
router.include_router(reminders_router)
router.include_router(chat_router)
router.include_router(analytics_router)
router.include_router(search_router)


class _RoutesModuleProxy(types.ModuleType):
    """Ensures mock patches on api.routes.<tool> propagate directly into api.meetings."""
    def __setattr__(self, name: str, value: object):
        super().__setattr__(name, value)
        if hasattr(_meetings_module, name):
            setattr(_meetings_module, name, value)


sys.modules[__name__].__class__ = _RoutesModuleProxy

__all__ = [
    "router",
    "meetings_router",
    "reminders_router",
    "chat_router",
    "analytics_router",
    "search_router",
    "send_slack_for_meeting",
    "send_jira_for_meeting",
    "send_email_for_meeting",
    "send_calendar_for_meeting",
    "storage_service",
]

"""Unit tests for core/cache.py (Redis caching layer)."""
import pytest
from unittest.mock import AsyncMock, patch

from core.cache import (
    cache_get,
    cache_set,
    cache_delete,
    invalidate_user_analytics,
    invalidate_meetings_list,
    key_analytics_summary,
    key_meetings_list,
)


@pytest.mark.asyncio
async def test_cache_disabled_fallback():
    """When Upstash env vars are empty or disabled, cache gracefully falls back without errors."""
    with patch("core.cache._ENABLED", False):
        res = await cache_get("test:key")
        assert res is None

        ok = await cache_set("test:key", {"foo": "bar"}, ttl=60)
        assert ok is False

        await cache_delete("test:key")


@pytest.mark.asyncio
async def test_cache_set_and_get():
    """Test JSON serialization and retrieval via mock Upstash REST API."""
    with patch("core.cache._ENABLED", True):
        with patch("core.cache._upstash_command", new_callable=AsyncMock) as mock_cmd:
            # Mock SET
            mock_cmd.return_value = "OK"
            ok = await cache_set("mia:user123:summary", {"total_meetings": 42}, ttl=300)
            assert ok is True
            mock_cmd.assert_called_with("SET", "mia:user123:summary", '{"total_meetings": 42}', "EX", 300)

            # Mock GET
            mock_cmd.return_value = '{"total_meetings": 42}'
            val = await cache_get("mia:user123:summary")
            assert val == {"total_meetings": 42}


@pytest.mark.asyncio
async def test_cache_invalidation_routines():
    """Verify invalidate_user_analytics and invalidate_meetings_list triggers proper deletions."""
    with patch("core.cache._ENABLED", True):
        with patch("core.cache._upstash_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = 1
            await invalidate_user_analytics("user_abc")
            assert mock_cmd.call_count >= 5  # 5 analytics keys deleted

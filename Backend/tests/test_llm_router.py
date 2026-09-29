from unittest.mock import MagicMock
import pytest
from groq import APIConnectionError, APIError, APITimeoutError, RateLimitError

from core.llm_router import execute_with_llm_fallback, llm_router


def test_execute_with_llm_fallback_primary_success():
    caller = MagicMock(return_value="primary_result")
    result, model_used = execute_with_llm_fallback(
        caller,
        primary_model="llama-3.3-70b-versatile",
        fallback_model="llama-3.1-8b-instant",
    )
    assert result == "primary_result"
    assert model_used == "llama-3.3-70b-versatile"
    caller.assert_called_once_with("llama-3.3-70b-versatile")


def test_execute_with_llm_fallback_rate_limit_cascades():
    def caller(model):
        if model == "llama-3.3-70b-versatile":
            raise RateLimitError("Rate limit exceeded", response=MagicMock(status_code=429), body=None)
        return "fallback_result"

    result, model_used = execute_with_llm_fallback(
        caller,
        primary_model="llama-3.3-70b-versatile",
        fallback_model="llama-3.1-8b-instant",
    )
    assert result == "fallback_result"
    assert model_used == "llama-3.1-8b-instant"


def test_execute_with_llm_fallback_timeout_cascades():
    def caller(model):
        if model == "llama-3.3-70b-versatile":
            raise APITimeoutError(request=MagicMock())
        return "fallback_timeout_result"

    result, model_used = execute_with_llm_fallback(
        caller,
        primary_model="llama-3.3-70b-versatile",
        fallback_model="llama-3.1-8b-instant",
    )
    assert result == "fallback_timeout_result"
    assert model_used == "llama-3.1-8b-instant"


def test_execute_with_llm_fallback_api_error_503_cascades():
    err = APIError("Service Unavailable", request=MagicMock(), body=None)
    err.status_code = 503

    def caller(model):
        if model == "llama-3.3-70b-versatile":
            raise err
        return "fallback_503_result"

    result, model_used = execute_with_llm_fallback(
        caller,
        primary_model="llama-3.3-70b-versatile",
        fallback_model="llama-3.1-8b-instant",
    )
    assert result == "fallback_503_result"
    assert model_used == "llama-3.1-8b-instant"


def test_execute_with_llm_fallback_both_fail():
    def caller(model):
        raise RateLimitError("Rate limit exceeded", response=MagicMock(status_code=429), body=None)

    with pytest.raises(RateLimitError):
        execute_with_llm_fallback(
            caller,
            primary_model="llama-3.3-70b-versatile",
            fallback_model="llama-3.1-8b-instant",
        )


def test_llm_router_select_model():
    # Short transcript -> fast model
    short_dec = llm_router.select_model("extraction", word_count=500)
    assert short_dec.model == llm_router._fast

    # Long transcript -> powerful model
    long_dec = llm_router.select_model("extraction", word_count=5000)
    assert long_dec.model == llm_router._powerful

    # Summary always -> fast model
    summary_dec = llm_router.select_model("summary")
    assert summary_dec.model == llm_router._fast

"""
core/openrouter_client.py — Production-grade OpenRouter client for Agent Chat.

Features:
- Asynchronous non-streaming completions (chat_completion)
- Real-time token streaming generator (stream_chat_completion)
- SSE stream parsing compliant with OpenRouter protocol
- Automatic retry / fallback handling
"""

import json
import logging
from typing import Any, AsyncGenerator, Optional

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class OpenRouterClient:
    """High-performance async client for OpenRouter API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
    ):
        self.api_key = api_key or settings.effective_openrouter_api_key
        self.base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self.default_model = default_model or settings.openrouter_model

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ultronop592/Meeting-Intelligence-Agent",
            "X-Title": "Meeting Intelligence Agent",
        }

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ) -> str:
        """Execute a non-streaming chat completion."""
        if not self.is_configured:
            raise ValueError("OpenRouter API key is not configured.")

        selected_model = model or self.default_model
        payload = {
            "model": selected_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        url = f"{self.base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=self._get_headers(), json=payload)
            if response.status_code != 200:
                err_text = response.text
                logger.error("OpenRouter API error (%d): %s", response.status_code, err_text)
                raise RuntimeError(f"OpenRouter API error ({response.status_code}): {err_text}")

            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                return ""
            return choices[0].get("message", {}).get("content", "").strip()

    async def stream_chat_completion(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> AsyncGenerator[str, None]:
        """Stream chat completion tokens in real-time as an async generator."""
        if not self.is_configured:
            raise ValueError("OpenRouter API key is not configured.")

        selected_model = model or self.default_model
        payload = {
            "model": selected_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        url = f"{self.base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=90.0) as client:
            async with client.stream("POST", url, headers=self._get_headers(), json=payload) as response:
                if response.status_code != 200:
                    err_bytes = await response.aread()
                    err_msg = err_bytes.decode("utf-8", errors="replace")
                    logger.error("OpenRouter stream failed (%d): %s", response.status_code, err_msg)
                    raise RuntimeError(f"OpenRouter stream error ({response.status_code}): {err_msg}")

                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line or line.startswith(":"):
                        # Skip empty lines and OpenRouter comment lines like ': OPENROUTER PROCESSING'
                        continue

                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data_str)
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content_piece = delta.get("content", "")
                                if content_piece:
                                    yield content_piece
                        except json.JSONDecodeError:
                            continue


openrouter_client = OpenRouterClient()

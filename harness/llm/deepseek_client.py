"""DeepSeek API client using OpenAI-compatible interface.

DeepSeek API is compatible with OpenAI's SDK.
Endpoint: https://api.deepseek.com
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Optional

from openai import OpenAI

from harness.llm.base import LLMClient, LLMResponse, LLMError, LLMAuthenticationError, LLMRateLimitError, LLMConnectionError
from harness.config.secrets import SecretsManager


class DeepSeekClient(LLMClient):
    """DeepSeek API client using OpenAI-compatible protocol.

    Uses synchronous OpenAI client wrapped in asyncio.to_thread()
    to avoid Windows ProactorEventLoop subprocess issues.
    """

    DEFAULT_BASE_URL = "https://api.deepseek.com"
    DEFAULT_MODEL = "deepseek-chat"

    def __init__(
        self,
        model: str = "deepseek-chat",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._base_url = base_url or self.DEFAULT_BASE_URL

        # Resolve API key: parameter > keyring > env var
        self._api_key = api_key
        if not self._api_key:
            secrets = SecretsManager()
            self._api_key = secrets.retrieve_api_key("deepseek")
        if not self._api_key:
            self._api_key = os.environ.get("DEEPSEEK_API_KEY")

        if not self._api_key:
            raise LLMAuthenticationError(
                "No DeepSeek API key found. Run 'harness setup-key' "
                "to store one, or set the DEEPSEEK_API_KEY environment variable."
            )

        self._client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Send a completion request to DeepSeek API."""
        # Build messages for OpenAI format
        api_messages = []
        for msg in messages:
            role = msg["role"]
            if role == "feedback":
                role = "user"
            if role == "system":
                api_messages.append({"role": role, "content": msg["content"]})
            else:
                api_messages.append({"role": role, "content": msg["content"]})

        # Deduplicate consecutive same-role messages
        deduped = []
        for m in api_messages:
            if deduped and deduped[-1]["role"] == m["role"]:
                deduped[-1]["content"] += "\n" + m["content"]
            else:
                deduped.append(m)
        api_messages = deduped

        params = {
            "model": kwargs.get("model", self._model),
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
            "temperature": kwargs.get("temperature", self._temperature),
            "messages": api_messages,
        }

        def _do_call():
            return self._client.chat.completions.create(**params)

        try:
            response = await asyncio.to_thread(_do_call)
        except Exception as e:
            error_str = str(e).lower()
            if "authentication" in error_str or "401" in error_str or "403" in error_str:
                raise LLMAuthenticationError(f"Authentication failed: {e}") from e
            if "rate" in error_str or "429" in error_str:
                raise LLMRateLimitError(f"Rate limit exceeded: {e}") from e
            if "connection" in error_str or "timeout" in error_str:
                raise LLMConnectionError(f"Connection failed: {e}") from e
            raise LLMError(f"DeepSeek API error: {e}") from e

        choice = response.choices[0]
        content = ""

        if choice.message.content:
            content = choice.message.content
        else:
            content = '{"tool": "stop", "reason": "task complete"}'

        return LLMResponse(
            content=content,
            model=response.model,
            usage={
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            finish_reason=choice.finish_reason or "stop",
            raw=response,
        )

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    @property
    def model(self) -> str:
        return self._model
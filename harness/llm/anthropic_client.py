"""Anthropic Claude API client implementation."""

from __future__ import annotations

import os
from typing import Any, Optional

import anthropic

from harness.llm.base import LLMClient, LLMResponse, LLMError, LLMAuthenticationError, LLMRateLimitError, LLMConnectionError
from harness.config.secrets import SecretsManager


class AnthropicClient(LLMClient):
    """Real Anthropic Claude API client.

    Uses the Anthropic Python SDK for API calls.
    API key is retrieved from the system keyring (via SecretsManager) or
    from the ANTHROPIC_API_KEY environment variable.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        api_key: Optional[str] = None,
    ):
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

        # Resolve API key: parameter > keyring > env var
        self._api_key = api_key
        if not self._api_key:
            secrets = SecretsManager()
            self._api_key = secrets.retrieve_api_key("anthropic")
        if not self._api_key:
            self._api_key = os.environ.get("ANTHROPIC_API_KEY")

        if not self._api_key:
            raise LLMAuthenticationError(
                "No Anthropic API key found. Run 'harness setup-key' to store one, "
                "or set the ANTHROPIC_API_KEY environment variable."
            )

        self._client = anthropic.Anthropic(api_key=self._api_key)

    async def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Send a completion request to Anthropic Claude."""
        # Separate system message from conversation
        system_prompt = ""
        api_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_prompt += msg["content"] + "\n"
            else:
                api_messages.append({
                    "role": "user" if msg["role"] in ("user", "feedback") else "assistant",
                    "content": msg["content"],
                })

        system_prompt = system_prompt.strip() or None

        try:
            kwargs_params = {
                "model": kwargs.get("model", self._model),
                "max_tokens": kwargs.get("max_tokens", self._max_tokens),
                "temperature": kwargs.get("temperature", self._temperature),
                "messages": api_messages,
            }

            if system_prompt:
                kwargs_params["system"] = system_prompt

            if tools:
                kwargs_params["tools"] = tools

            response = self._client.messages.create(**kwargs_params)

            # Extract text content from response
            content_parts = []
            for block in response.content:
                if block.type == "text":
                    content_parts.append(block.text)
                elif block.type == "tool_use":
                    # Format tool use as JSON for the action parser
                    import json
                    tool_params = {}
                    if hasattr(block, 'input') and block.input:
                        tool_params = dict(block.input)
                    tool_params["tool"] = block.name
                    content_parts.append(json.dumps(tool_params))

            return LLMResponse(
                content="\n".join(content_parts),
                model=response.model,
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
                finish_reason=response.stop_reason or "stop",
                raw=response,
            )

        except anthropic.AuthenticationError as e:
            raise LLMAuthenticationError(f"Authentication failed: {e}") from e
        except anthropic.RateLimitError as e:
            raise LLMRateLimitError(f"Rate limit exceeded: {e}") from e
        except anthropic.APIConnectionError as e:
            raise LLMConnectionError(f"Connection failed: {e}") from e
        except Exception as e:
            raise LLMError(f"Anthropic API error: {e}") from e

    def count_tokens(self, text: str) -> int:
        """Approximate token count using Anthropic's tokenizer."""
        try:
            return self._client.count_tokens(text)
        except Exception:
            return len(text) // 4  # Fallback approximation

    @property
    def model(self) -> str:
        return self._model
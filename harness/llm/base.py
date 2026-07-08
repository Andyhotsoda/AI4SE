"""Abstract LLM client interface and response types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    """Structured response from an LLM completion call."""
    content: str
    model: str = "unknown"
    usage: dict[str, int] = field(default_factory=lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
    })
    finish_reason: str = "stop"
    raw: Any = None  # Provider-specific raw response


class LLMClient(ABC):
    """Abstract base class for LLM providers.

    All LLM implementations must implement this interface.
    This enables injection of MockLLMClient for deterministic testing.
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Send a completion request to the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            tools: Optional list of tool definitions for function calling.
            **kwargs: Provider-specific parameters.

        Returns:
            LLMResponse with the model's output.
        """
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """
        Count the approximate number of tokens in a text.

        Args:
            text: The text to count tokens for.

        Returns:
            Approximate token count.
        """
        ...

    def count_messages_tokens(self, messages: list[dict[str, str]]) -> int:
        """
        Count total tokens across all messages.

        Args:
            messages: List of message dicts.

        Returns:
            Total approximate token count.
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.count_tokens(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        total += self.count_tokens(block["text"])
        return total


class LLMError(Exception):
    """Base exception for LLM-related errors."""
    pass


class LLMAuthenticationError(LLMError):
    """Raised when API authentication fails."""
    pass


class LLMRateLimitError(LLMError):
    """Raised when API rate limit is exceeded."""
    pass


class LLMConnectionError(LLMError):
    """Raised when connection to LLM provider fails."""
    pass
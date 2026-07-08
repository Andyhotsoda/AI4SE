"""Deterministic mock LLM client for testing.

The mock returns exactly what it is told to return — it does NOT simulate
intelligence. This makes tests deterministic and forces the harness mechanisms
(not the LLM) to be the source of correctness.

Two modes:
1. Script mode: returns responses from a predefined list in order.
2. Pattern mode: matches input against regex patterns and returns associated responses.
"""

from __future__ import annotations

import re
from typing import Optional

from harness.llm.base import LLMClient, LLMResponse


class MockLLMClient(LLMClient):
    """
    Deterministic mock LLM for offline testing.

    Usage:
        # Script mode — returns responses in order
        mock = MockLLMClient(responses=[
            '{"tool": "read_file", "path": "main.py"}',
            '{"tool": "shell", "command": "pytest"}',
            '{"tool": "stop", "reason": "All tests pass"}',
        ])

        # Pattern mode — matches input against regex
        mock = MockLLMClient(responses={
            "read": '{"tool": "read_file", "path": "main.py"}',
            "test": '{"tool": "shell", "command": "pytest"}',
        })
    """

    def __init__(
        self,
        responses: list[str] | dict[str, str] | None = None,
        default_response: str = '{"tool": "stop", "reason": "task complete"}',
    ):
        self._responses = responses or []
        self._default_response = default_response
        self._call_count = 0
        self._call_history: list[dict] = []

    async def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Return a predetermined response based on the configured mode."""
        # Record the call for test assertions
        call_record = {
            "call_index": self._call_count,
            "messages": messages,
            "tools": tools,
            "kwargs": kwargs,
        }
        self._call_history.append(call_record)

        # Determine response
        if isinstance(self._responses, list):
            # Script mode: return responses in order
            if self._call_count < len(self._responses):
                response = self._responses[self._call_count]
            else:
                response = self._default_response
        elif isinstance(self._responses, dict):
            # Pattern mode: match against last message content
            response = self._match_pattern(str(messages[-1].get("content", "")))
        else:
            response = self._default_response

        self._call_count += 1

        return LLMResponse(
            content=response,
            model="mock",
            usage={
                "input_tokens": self.count_messages_tokens(messages),
                "output_tokens": self.count_tokens(response),
            },
            finish_reason="stop",
        )

    def count_tokens(self, text: str) -> int:
        """Rough token count approximation: ~4 chars per token."""
        return max(1, len(text) // 4)

    def _match_pattern(self, content: str) -> str:
        """Match content against registered patterns and return the first match."""
        for pattern, response in self._responses.items():
            if re.search(pattern, content, re.IGNORECASE):
                return response
        return self._default_response

    @property
    def call_count(self) -> int:
        """Number of times complete() was called."""
        return self._call_count

    @property
    def call_history(self) -> list[dict]:
        """Full history of all calls made to complete()."""
        return self._call_history

    def get_last_call(self) -> Optional[dict]:
        """Get the most recent call record."""
        if self._call_history:
            return self._call_history[-1]
        return None

    def reset(self) -> None:
        """Reset the mock to its initial state."""
        self._call_count = 0
        self._call_history = []
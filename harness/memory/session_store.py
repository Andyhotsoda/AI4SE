"""Session store — in-memory conversation history management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ConversationTurn:
    """A single turn in the agent conversation."""
    role: str  # "user" or "assistant" or "feedback"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionStore:
    """
    In-memory conversation history for the current session.

    Manages the conversation turns that are sent to the LLM as context.
    """

    def __init__(self, max_history_turns: int = 50):
        self._turns: list[ConversationTurn] = []
        self._max_history = max_history_turns

    def add_turn(self, role: str, content: str, **metadata) -> ConversationTurn:
        """
        Add a conversation turn.

        Args:
            role: "user", "assistant", or "feedback"
            content: The message content.
            **metadata: Additional metadata for the turn.

        Returns:
            The created ConversationTurn.
        """
        turn = ConversationTurn(role=role, content=content, metadata=metadata)
        self._turns.append(turn)
        self._trim_if_needed()
        return turn

    def get_recent_turns(self, n: int | None = None) -> list[ConversationTurn]:
        """
        Get the most recent conversation turns.

        Args:
            n: Number of turns to return. None returns all.

        Returns:
            List of ConversationTurn.
        """
        if n is None:
            return list(self._turns)
        return self._turns[-n:]

    def get_messages_for_llm(self) -> list[dict[str, str]]:
        """
        Get all turns formatted as messages for the LLM API.

        Returns:
            List of {"role": ..., "content": ...} dicts.
        """
        return [{"role": t.role, "content": t.content} for t in self._turns]

    def get_last_assistant_message(self) -> Optional[str]:
        """Get the content of the last assistant turn."""
        for turn in reversed(self._turns):
            if turn.role == "assistant":
                return turn.content
        return None

    def clear(self) -> None:
        """Clear all conversation history."""
        self._turns.clear()

    def _trim_if_needed(self) -> None:
        """Trim history if it exceeds max turns."""
        if len(self._turns) > self._max_history:
            self._turns = self._turns[-self._max_history:]

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    @property
    def max_history(self) -> int:
        return self._max_history
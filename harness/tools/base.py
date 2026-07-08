"""Abstract Tool base class and Action/ActionResult data types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DangerLevel(Enum):
    """Pre-execution danger classification for an action."""
    SAFE = 0        # Read-only operations, no side effects
    WARNING = 1     # Write operations within project scope
    DANGEROUS = 2   # Destructive operations, network access, git push
    CRITICAL = 3    # System-level destruction, credential exposure


@dataclass
class Action:
    """A parsed action from the LLM output."""
    tool_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    raw: str = ""  # Original LLM output text

    def __repr__(self) -> str:
        params_str = ", ".join(f"{k}={v}" for k, v in self.parameters.items())
        return f"Action({self.tool_name}, {params_str})"


@dataclass
class ActionResult:
    """Result of executing a tool action."""
    success: bool
    output: str = ""
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.success


@dataclass
class ToolDefinition:
    """Definition of a tool for LLM function-calling context."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for parameters
    danger_level: DangerLevel = DangerLevel.WARNING

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_schema(self) -> dict:
        """Convert to Anthropic tool-use format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


class Tool(ABC):
    """Abstract base class for all tools the agent can use."""

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return the tool definition (name, description, parameters)."""
        ...

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ActionResult:
        """
        Execute the tool with the given parameters.

        Args:
            params: Dictionary of parameter name → value.

        Returns:
            ActionResult with success/failure, output, and optional error.
        """
        ...

    def validate_params(self, params: dict[str, Any]) -> Optional[str]:
        """
        Validate parameters before execution.
        Returns None if valid, or an error message if invalid.
        """
        return None  # Default: no validation
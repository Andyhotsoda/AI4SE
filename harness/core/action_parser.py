"""Parse LLM output into structured Action objects."""

from __future__ import annotations

import json
import re
from typing import Optional

from harness.tools.base import Action


class ActionParser:
    """
    Parse LLM output into a list of Action objects.

    Supports two formats:
    1. JSON blocks: ```json ... ``` or raw JSON objects
    2. Single-line JSON: {"tool": "...", ...}
    """

    # Tool names that the parser recognizes
    VALID_TOOLS = {
        "read_file", "write_file", "list_directory",
        "shell", "run_tests", "stop", "finish",
    }

    @classmethod
    def parse(cls, llm_output: str) -> list[Action]:
        """
        Parse LLM output into a list of actions.

        Args:
            llm_output: Raw text output from the LLM.

        Returns:
            List of Action objects. Returns empty list if no actions found.
        """
        actions = []

        # Try to extract JSON blocks first
        json_blocks = cls._extract_json_blocks(llm_output)
        for block in json_blocks:
            action = cls._parse_json_action(block)
            if action:
                actions.append(action)

        # If no JSON blocks found, try the whole output as a single JSON object
        if not actions:
            action = cls._parse_json_action(llm_output.strip())
            if action:
                actions.append(action)

        return actions

    @classmethod
    def _extract_json_blocks(cls, text: str) -> list[str]:
        """Extract JSON code blocks from markdown-style text."""
        blocks = []
        # Match ```json ... ``` blocks
        pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        matches = re.findall(pattern, text, re.DOTALL)
        blocks.extend(m.strip() for m in matches)

        # Remove code blocks from text before finding standalone JSON
        text_no_blocks = re.sub(pattern, "", text, flags=re.DOTALL)

        # Also match standalone JSON objects (not inside code blocks)
        # Find { ... } pairs that look like action objects
        standalone = re.findall(r'\{[^{}]*"tool"\s*:\s*"[^"]+"[^{}]*\}', text_no_blocks)
        blocks.extend(standalone)

        return blocks

    @classmethod
    def _parse_json_action(cls, json_str: str) -> Optional[Action]:
        """
        Parse a JSON string into an Action.

        Expected format:
        {
            "tool": "shell",
            "command": "pytest",
            ...other parameters
        }
        Or:
        {
            "tool": "shell",
            "parameters": {"command": "pytest"}
        }
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        # Support both "tool" and "tool_name" keys
        tool_name = data.get("tool") or data.get("tool_name")
        if not tool_name or tool_name not in cls.VALID_TOOLS:
            return None

        # Extract parameters: either top-level (minus "tool") or nested "parameters"
        if "parameters" in data and isinstance(data["parameters"], dict):
            parameters = dict(data["parameters"])
        else:
            parameters = {k: v for k, v in data.items() if k not in ("tool", "tool_name")}

        return Action(
            tool_name=tool_name,
            parameters=parameters,
            raw=json_str,
        )

    @classmethod
    def has_stop_action(cls, actions: list[Action]) -> bool:
        """Check if any action is a stop/finish action."""
        return any(a.tool_name in ("stop", "finish") for a in actions)

    @classmethod
    def get_stop_reason(cls, actions: list[Action]) -> Optional[str]:
        """Get the reason from a stop action, if present."""
        for action in actions:
            if action.tool_name in ("stop", "finish"):
                return action.parameters.get("reason", "Task complete")
        return None
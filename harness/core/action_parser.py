"""Parse LLM output into structured Action objects."""

from __future__ import annotations

import json
import re
from typing import Optional

from harness.tools.base import Action


class ActionParser:
    """
    Parse LLM output into Action objects.

    Supports:
    1. JSON: {"tool": "shell", "command": "pytest"}
    2. JSON in code blocks: ```json {...} ```
    3. Natural language fallback: extracts code blocks as write_file actions
    """

    VALID_TOOLS = {
        "read_file", "write_file", "list_directory",
        "shell", "run_tests", "stop", "finish",
    }

    @classmethod
    def parse(cls, llm_output: str) -> list[Action]:
        actions = []

        # 1. Try JSON blocks ```json ... ``` or standalone {...}
        json_blocks = cls._extract_json_blocks(llm_output)
        for block in json_blocks:
            action = cls._parse_json_action(block)
            if action:
                actions.append(action)

        # 2. Try whole output as JSON
        if not actions:
            action = cls._parse_json_action(llm_output.strip())
            if action:
                actions.append(action)

        # 3. Fallback: extract code blocks from natural language
        if not actions:
            actions = cls._extract_code_actions(llm_output)

        # 4. Last resort: if output looks like completion
        if not actions:
            if any(w in llm_output.lower() for w in ["done", "complete", "finished", "created"]):
                actions.append(Action(
                    tool_name="stop",
                    parameters={"reason": "Task appears complete"},
                    raw=llm_output,
                ))

        return actions

    @classmethod
    def _extract_json_blocks(cls, text: str) -> list[str]:
        blocks = []
        pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        matches = re.findall(pattern, text, re.DOTALL)
        blocks.extend(m.strip() for m in matches)

        text_no_blocks = re.sub(pattern, "", text, flags=re.DOTALL)
        standalone = re.findall(r'\{[^{}]*"tool"\s*:\s*"[^"]+"[^{}]*\}', text_no_blocks)
        blocks.extend(standalone)

        return blocks

    @classmethod
    def _parse_json_action(cls, json_str: str) -> Optional[Action]:
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        tool_name = data.get("tool") or data.get("tool_name")
        if not tool_name or tool_name not in cls.VALID_TOOLS:
            return None

        if "parameters" in data and isinstance(data["parameters"], dict):
            parameters = dict(data["parameters"])
        else:
            parameters = {k: v for k, v in data.items() if k not in ("tool", "tool_name")}

        return Action(tool_name=tool_name, parameters=parameters, raw=json_str)

    @classmethod
    def _extract_code_actions(cls, text: str) -> list[Action]:
        """Extract code blocks from natural language and create write_file actions."""
        actions = []

        code_pattern = r"```(?:\w+)?\s*\n?(.*?)\n?```"
        code_matches = re.findall(code_pattern, text, re.DOTALL)

        filename_pattern = r"(?:file|create|write|called)\s+(?:called\s+)?[`\"']?(\w+\.\w+)[`\"']?"
        filenames = re.findall(filename_pattern, text, re.IGNORECASE)

        for i, code in enumerate(code_matches):
            code = code.strip()
            if not code:
                continue

            if i < len(filenames):
                filename = filenames[i]
            elif "print" in code and "def " not in code:
                filename = "main.py"
            elif "def " in code:
                filename = "module.py"
            else:
                filename = "script.py"

            actions.append(Action(
                tool_name="write_file",
                parameters={"path": filename, "content": code},
                raw=text,
            ))

        return actions

    @classmethod
    def has_stop_action(cls, actions: list[Action]) -> bool:
        return any(a.tool_name in ("stop", "finish") for a in actions)

    @classmethod
    def get_stop_reason(cls, actions: list[Action]) -> Optional[str]:
        for action in actions:
            if action.tool_name in ("stop", "finish"):
                return action.parameters.get("reason", "Task complete")
        return None

    @classmethod
    def extract_text(cls, llm_output: str) -> str:
        """Extract natural language text, removing JSON tool calls.

        The LLM output is: natural language with embedded JSON tool calls.
        This extracts just the natural language parts.
        """
        import re
        # Remove ```json ... ``` blocks
        text = re.sub(r'```(?:json)?\s*\n?\{.*?\}\n?```', '', llm_output, flags=re.DOTALL)
        # Remove standalone JSON objects with "tool" key
        text = re.sub(r'\{\s*"tool"\s*:\s*"[^"]+"[^}]*\}', '', text)
        # Clean up extra whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
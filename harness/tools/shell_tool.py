"""Shell command execution tool."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from harness.tools.base import Tool, ActionResult, ToolDefinition, DangerLevel


class ShellTool(Tool):
    """Execute shell commands."""

    def __init__(self, timeout_seconds: int = 30, working_dir: str = "."):
        self._timeout = timeout_seconds
        self._working_dir = working_dir

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="shell",
            description="Execute a shell command in the working directory. "
                        "Returns stdout, stderr, and exit code.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    },
                },
                "required": ["command"],
            },
            danger_level=DangerLevel.WARNING,
        )

    async def execute(self, params: dict[str, Any]) -> ActionResult:
        command = params.get("command", "")
        if not command:
            return ActionResult(success=False, error="No command provided")

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._working_dir,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self._timeout,
            )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            output_parts = []
            if stdout_str:
                output_parts.append(stdout_str)
            if stderr_str:
                output_parts.append(f"[stderr]\n{stderr_str}")

            output = "\n".join(output_parts) if output_parts else "(no output)"

            return ActionResult(
                success=(process.returncode == 0),
                output=output,
                error=stderr_str if process.returncode != 0 else None,
                metadata={
                    "exit_code": process.returncode,
                    "command": command,
                },
            )
        except asyncio.TimeoutError:
            return ActionResult(
                success=False,
                error=f"Command timed out after {self._timeout}s: {command}",
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"Failed to execute command: {type(e).__name__}: {e}",
            )